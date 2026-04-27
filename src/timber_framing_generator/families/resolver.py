# File: src/timber_framing_generator/families/resolver.py
"""
Family Resolver orchestrator — the main entry point for family resolution.

Coordinates between manifest parsing, provider downloads, local cache,
and Revit API loading to ensure all required families are available
before the bake step.

Usage:
    from src.timber_framing_generator.families.resolver import FamilyResolver
    from src.timber_framing_generator.families.providers import GitHubProvider

    resolver = FamilyResolver(provider=GitHubProvider())
    result = resolver.resolve(doc=revit_doc, framing_json=framing_json_str)

    if result.status == "all_resolved":
        enriched_json = resolver.enrich_framing_json(framing_json_str, result)
"""

import json
import logging
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.timber_framing_generator.families.manifest import (
    FamilyManifest,
    FamilyEntry,
    get_required_profiles,
    get_families_for_elements,
    get_families_for_material,
    parse_manifest,
)
from src.timber_framing_generator.families.cache import FamilyCache
from src.timber_framing_generator.families.providers import (
    FamilyProvider,
    GitHubProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    """Result of the family resolution process.

    Attributes:
        status: Overall status — "all_resolved", "partial", "failed", "offline"
        resolved: Mapping of profile_name -> revit_type_name for resolved families
        missing: Family keys that could not be resolved
        loaded: Families that were newly downloaded and loaded into Revit
        cached: Families served from local cache
        already_loaded: Families already present in the Revit document
        log: Ordered list of diagnostic messages
    """
    status: str = "pending"
    resolved: Dict[str, str] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    loaded: List[str] = field(default_factory=list)
    cached: List[str] = field(default_factory=list)
    already_loaded: List[str] = field(default_factory=list)
    log: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "status": self.status,
            "resolved_count": len(self.resolved),
            "missing_count": len(self.missing),
            "loaded": self.loaded,
            "cached": self.cached,
            "already_loaded": self.already_loaded,
            "missing": self.missing,
        }


class FamilyResolver:
    """Orchestrates the full family resolution pipeline.

    Pipeline steps:
    1. Fetch manifest from provider (or use cached manifest)
    2. Parse framing_json to determine which profiles are needed
    3. Check which families are already loaded in Revit
    4. For missing families: check cache, download if needed
    5. Load .rfa files into Revit via Document.LoadFamily()
    6. Activate all required FamilySymbols
    7. Return resolution status with diagnostics

    Args:
        provider: FamilyProvider for fetching manifest and .rfa files.
                 Defaults to GitHubProvider.
        cache: FamilyCache for local caching. Defaults to standard cache dir.
        manifest: Pre-loaded manifest (skips fetching from provider).
    """

    def __init__(
        self,
        provider: Optional[FamilyProvider] = None,
        cache: Optional[FamilyCache] = None,
        manifest: Optional[FamilyManifest] = None,
    ) -> None:
        self._provider = provider or GitHubProvider()
        self._cache = cache or FamilyCache()
        self._manifest = manifest

    @property
    def provider(self) -> FamilyProvider:
        return self._provider

    @property
    def cache(self) -> FamilyCache:
        return self._cache

    def _fetch_manifest(self, result: ResolutionResult) -> Optional[FamilyManifest]:
        """Fetch manifest from provider, with error handling.

        Args:
            result: ResolutionResult to log messages to

        Returns:
            FamilyManifest or None if fetch failed
        """
        if self._manifest:
            result.log.append("Using pre-loaded manifest")
            return self._manifest

        try:
            manifest = self._provider.get_manifest()
            result.log.append(
                f"Fetched manifest from {self._provider.provider_name}: "
                f"{len(manifest.families)} families"
            )
            return manifest
        except ConnectionError as e:
            result.log.append(f"Network error: {e}")
            return None
        except ValueError as e:
            result.log.append(f"Invalid manifest: {e}")
            return None

    def _extract_material_system(self, framing_json: Optional[str]) -> str:
        """Extract the material_system field from framing JSON top level.

        Args:
            framing_json: JSON string from framing generator

        Returns:
            Material system string (e.g. "timber", "cfs"), or "" if absent
        """
        if not framing_json:
            return ""
        try:
            data = json.loads(framing_json)
            return str(data.get("material_system", "")).strip().lower()
        except (json.JSONDecodeError, AttributeError):
            return ""

    def _extract_needed_profiles(
        self, framing_json: Optional[str]
    ) -> List[str]:
        """Extract unique profile names from framing JSON.

        Args:
            framing_json: JSON string from framing generator

        Returns:
            List of unique profile names
        """
        if not framing_json:
            return []

        try:
            data = json.loads(framing_json)
            profiles = set()
            for element in data.get("elements", []):
                profile = element.get("profile", {})
                name = profile.get("name", "")
                if name:
                    profiles.add(name)
            return list(profiles)
        except (json.JSONDecodeError, AttributeError):
            return []

    def resolve(
        self,
        doc: Optional[Any] = None,
        framing_json: Optional[str] = None,
    ) -> ResolutionResult:
        """Execute the full family resolution pipeline.

        Args:
            doc: Revit Document (None if running outside Revit)
            framing_json: JSON string from Framing Generator component.
                         If provided, only resolves families needed for
                         the actual elements. If None, resolves all manifest families.

        Returns:
            ResolutionResult with status, resolved mappings, and diagnostics
        """
        result = ResolutionResult()
        result.log.append(f"Starting family resolution (provider: {self._provider.provider_name})")

        # Step 1: Fetch manifest
        manifest = self._fetch_manifest(result)
        if manifest is None:
            # Try offline mode with cached manifest
            result.log.append("Falling back to offline/cache-only mode")
            return self._resolve_cache_only(result, framing_json)

        # Persist manifest so enrich_framing_json() can build profile_map
        self._manifest = manifest

        # Step 2: Determine needed families
        material_system = self._extract_material_system(framing_json)
        needed_profiles = self._extract_needed_profiles(framing_json)

        if needed_profiles:
            # Profile-matched families (may miss families whose types share names
            # with another family — e.g. Timber_Framing "2x4" vs Timber_Stud "2x4")
            needed_families = get_families_for_elements(manifest, needed_profiles)
            # Also add material-system families whose types overlap with the
            # current job's profiles — ensures Timber_Framing is included even
            # when "2x4" maps to Timber_Stud in the profile map (last-wins).
            # Families with NO overlapping types (e.g. LVL_Beam when job has
            # only studs/plates) are intentionally excluded to avoid failed
            # downloads for placeholder .rfa files.
            if material_system:
                for key, entry in get_families_for_material(manifest, material_system).items():
                    if key not in needed_families:
                        if any(t in needed_profiles for t in entry.types):
                            needed_families[key] = entry
            result.log.append(
                f"Framing uses {len(needed_profiles)} profiles "
                f"(material_system={material_system or 'unknown'}), "
                f"requiring {len(needed_families)} families"
            )
        elif material_system:
            # framing_json present but has no elements yet — load only the
            # correct material system instead of everything in the manifest
            needed_families = get_families_for_material(manifest, material_system)
            result.log.append(
                f"No profiles in framing_json — loading all {len(needed_families)} "
                f"{material_system} families"
            )
        else:
            # No framing_json and no material hint — load all framing families
            # (doors/windows excluded by domain check in _resolve_single_family)
            needed_families = {
                k: v for k, v in manifest.families.items()
                if v.domain == "framing"
            }
            result.log.append(
                f"No framing_json or material hint — resolving all "
                f"{len(needed_families)} framing families"
            )

        # Step 3: Check Revit for already-loaded families
        loaded_in_revit: Dict[str, Dict] = {}
        if doc is not None:
            try:
                from src.timber_framing_generator.families.revit_loader import (
                    get_loaded_families,
                )
                loaded_in_revit = get_loaded_families(doc)
                result.log.append(
                    f"Found {len(loaded_in_revit)} families already loaded in Revit"
                )
            except ImportError:
                result.log.append("Revit loader not available (not in Revit environment)")

        # Step 4-6: Process each needed family
        for family_key, family_entry in needed_families.items():
            self._resolve_single_family(
                family_key, family_entry, doc, loaded_in_revit, result
            )

        # Step 7: Determine final status.
        # ``result.resolved`` is populated authoritatively by each
        # ``_resolve_single_family`` call — only types that were either
        # found in the Revit family or successfully created via Duplicate
        # are in it. Manifest types missing from a loaded .rfa that
        # couldn't be duplicated intentionally do NOT appear here, so
        # downstream enrichment won't claim them as available.

        # Determine final status
        if not result.missing:
            result.status = "all_resolved"
        elif result.resolved:
            result.status = "partial"
        else:
            result.status = "failed"

        result.log.append(
            f"Resolution complete: {result.status} "
            f"(resolved={len(result.resolved)}, missing={len(result.missing)})"
        )
        return result

    def _resolve_single_family(
        self,
        family_key: str,
        family_entry: FamilyEntry,
        doc: Optional[Any],
        loaded_in_revit: Dict[str, Dict],
        result: ResolutionResult,
    ) -> None:
        """Resolve a single family through the full pipeline.

        Args:
            family_key: Manifest family key
            family_entry: FamilyEntry from manifest
            doc: Revit Document (or None)
            loaded_in_revit: Already-loaded families from Revit
            result: ResolutionResult to update
        """
        # Check if already loaded in Revit.
        # loaded_in_revit is keyed by Revit family name (e.g. "TFG_Timber_Framing"),
        # which comes from the .rfa filename — NOT the manifest key ("Timber_Framing").
        import os as _os
        revit_family_name = _os.path.splitext(_os.path.basename(family_entry.file))[0]
        loaded_record = (
            loaded_in_revit.get(revit_family_name)
            or loaded_in_revit.get(family_key)
        )

        family_obj: Optional[Any] = None

        if loaded_record is not None:
            # Family already present — skip download/load, but still ensure
            # every manifest type exists and is activated below.
            family_obj = loaded_record.get("family")
            result.already_loaded.append(family_key)
            result.log.append(
                f"  {family_key}: already loaded in Revit (as '{revit_family_name}')"
            )
        else:
            # Not yet in Revit — fetch from cache or provider
            is_cached = self._cache.is_cached(family_key, family_entry.sha256)
            cached_path = self._cache.get_cached_path(family_key) if is_cached else None

            if not cached_path:
                cached_path = self._download_and_cache(family_key, family_entry, result)
                if not cached_path:
                    result.missing.append(family_key)
                    return
            else:
                result.cached.append(family_key)
                result.log.append(f"  {family_key}: using cached file")

            if doc is None:
                # No Revit doc — mark as cached-only and trust manifest offline
                if family_key not in result.cached:
                    result.cached.append(family_key)
                result.log.append(
                    f"  {family_key}: cached (no Revit doc to load into)"
                )
                for type_name in family_entry.types:
                    result.resolved.setdefault(type_name, type_name)
                return

            # Load .rfa into Revit
            family_obj = self._load_into_revit(
                doc, family_key, family_entry, cached_path, result
            )
            if family_obj is None:
                result.missing.append(family_key)
                return
            result.loaded.append(family_key)

        # -----------------------------------------------------------------
        # Ensure each manifest type exists in Revit and is activated.
        # Types that can't be found/created are deliberately NOT added to
        # result.resolved, so downstream enrichment won't claim they're
        # available. That keeps "resolved" honest when a loaded family is
        # missing types the manifest declares (e.g. TFG_Timber_Framing
        # lacking 2x10 when the manifest lists 2x4/2x6/2x8/2x10/2x12).
        # -----------------------------------------------------------------
        if doc is None or family_obj is None:
            # Fall back to manifest-authoritative when we can't verify
            for type_name in family_entry.types:
                result.resolved.setdefault(type_name, type_name)
            return

        try:
            from src.timber_framing_generator.families.revit_loader import (
                ensure_type_exists,
            )
        except ImportError:
            result.log.append(
                f"  {family_key}: revit_loader unavailable; trusting manifest"
            )
            for type_name in family_entry.types:
                result.resolved.setdefault(type_name, type_name)
            return

        for type_name, type_info in family_entry.types.items():
            sym = ensure_type_exists(
                doc, family_obj, type_name,
                width_in=type_info.width_in,
                depth_in=type_info.depth_in,
            )
            if sym is not None:
                result.resolved[type_name] = type_name
                result.log.append(
                    f"  {family_key}: type '{type_name}' ready"
                )
            else:
                result.log.append(
                    f"  {family_key}: type '{type_name}' UNAVAILABLE (not in "
                    f"family and could not duplicate)"
                )

    def _download_and_cache(
        self,
        family_key: str,
        family_entry: FamilyEntry,
        result: ResolutionResult,
    ) -> Optional[str]:
        """Download a family and store in cache.

        Args:
            family_key: Manifest family key
            family_entry: FamilyEntry with file path
            result: ResolutionResult for logging

        Returns:
            Path to cached file, or None if download failed
        """
        try:
            # Download to a temp file first
            import tempfile
            with tempfile.NamedTemporaryFile(
                suffix=".rfa", delete=False
            ) as tmp:
                tmp_path = tmp.name

            success = self._provider.download_family(family_entry, tmp_path)
            if not success:
                result.log.append(f"  {family_key}: download FAILED")
                return None

            # Store in cache
            cached_path = self._cache.store(
                family_key,
                tmp_path,
                family_entry.file,
                family_entry.sha256,
            )

            # Clean up temp file
            import os
            if os.path.exists(tmp_path) and tmp_path != cached_path:
                os.remove(tmp_path)

            result.log.append(f"  {family_key}: downloaded and cached")
            return cached_path

        except Exception as e:
            result.log.append(f"  {family_key}: download error: {e}")
            return None

    def _load_into_revit(
        self,
        doc: Any,
        family_key: str,
        family_entry: FamilyEntry,
        rfa_path: str,
        result: ResolutionResult,
    ) -> Optional[Any]:
        """Load a .rfa file into Revit.

        Per-type activation (and creation via Duplicate for any types the .rfa
        lacks) is handled by the caller via ``ensure_type_exists``.

        Args:
            doc: Revit Document
            family_key: Manifest family key
            family_entry: FamilyEntry with type info
            rfa_path: Path to .rfa file
            result: ResolutionResult for logging

        Returns:
            Loaded Family object, or None if load failed
        """
        try:
            from src.timber_framing_generator.families.revit_loader import (
                load_family,
            )
        except ImportError:
            result.log.append(f"  {family_key}: Revit loader not available")
            return None

        family = load_family(doc, rfa_path)
        if family is None:
            result.log.append(f"  {family_key}: LoadFamily FAILED for {rfa_path}")
            return None

        result.log.append(f"  {family_key}: loaded from {rfa_path}")
        return family

    def _resolve_cache_only(
        self,
        result: ResolutionResult,
        framing_json: Optional[str],
    ) -> ResolutionResult:
        """Resolve families using only the local cache (offline mode).

        Args:
            result: ResolutionResult to update
            framing_json: Optional framing JSON to filter needed families

        Returns:
            Updated ResolutionResult
        """
        result.status = "offline"
        cached_families = self._cache.list_cached()

        if not cached_families:
            result.log.append("No cached families available for offline mode")
            result.status = "failed"
            return result

        result.log.append(
            f"Offline mode: {len(cached_families)} families in cache"
        )

        for family_key in cached_families:
            path = self._cache.get_cached_path(family_key)
            if path:
                result.cached.append(family_key)

        if result.cached:
            result.status = "offline"
        else:
            result.status = "failed"

        return result

    def enrich_framing_json(
        self,
        framing_json: str,
        result: ResolutionResult,
        manifest: Optional[FamilyManifest] = None,
    ) -> str:
        """Enrich framing JSON with resolved family/type information.

        Adds ``revit_family`` and ``revit_type`` fields to each element
        in the framing JSON based on the resolution result.

        Args:
            framing_json: Original framing JSON from generator
            result: ResolutionResult from resolve()
            manifest: Optional manifest (uses cached if available)

        Returns:
            Enriched JSON string with revit_family/revit_type fields
        """
        try:
            data = json.loads(framing_json)
        except json.JSONDecodeError:
            return framing_json

        manifest = manifest or self._manifest

        # Build candidate map: type_name -> {revit_category: family_key}.
        # This lets us pick the right family when the same type name exists
        # in multiple families across different Revit categories — e.g.
        # "600S162-54" lives in both CFS_Stud (OST_StructuralColumns) and
        # CFS_Joist (OST_StructuralFraming). The element's element_type
        # tells us which category it belongs in; we pick accordingly.
        import os as _os

        candidates: Dict[str, Dict[str, str]] = {}
        if manifest is not None:
            for family_key, entry in manifest.families.items():
                for type_name in entry.types:
                    candidates.setdefault(type_name, {})[entry.category] = family_key

        # element_type -> expected Revit BuiltInCategory (matches
        # gh_revit_baker.COLUMN_ELEMENT_TYPES / BEAM_ELEMENT_TYPES).
        COLUMN_ELEMENT_TYPES = {
            "stud", "king_stud", "trimmer",
            "header_cripple", "sill_cripple",
        }

        for element in data.get("elements", []):
            profile = element.get("profile", {})
            profile_name = profile.get("name", "")
            element_type = element.get("element_type", "")

            if profile_name not in result.resolved:
                continue

            expected_cat = (
                "OST_StructuralColumns"
                if element_type in COLUMN_ELEMENT_TYPES
                else "OST_StructuralFraming"
            )

            by_cat = candidates.get(profile_name, {})
            # Prefer the family whose category matches the element; fall back
            # to any family that provides the type if no category match (keeps
            # behavior intact for timber, where each type lives in one family).
            family_key = by_cat.get(expected_cat) or next(iter(by_cat.values()), "")

            # Use the actual Revit family name (from .rfa filename); the
            # Revit Baker looks up families by Revit name, not manifest key.
            if family_key and manifest and family_key in manifest.families:
                entry = manifest.families[family_key]
                revit_name = _os.path.splitext(_os.path.basename(entry.file))[0]
                element["revit_family"] = revit_name
            else:
                element["revit_family"] = family_key
            element["revit_type"] = profile_name

        return json.dumps(data, indent=2)
