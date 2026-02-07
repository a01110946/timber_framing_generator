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

        # Step 2: Determine needed families
        needed_profiles = self._extract_needed_profiles(framing_json)
        if needed_profiles:
            needed_families = get_families_for_elements(manifest, needed_profiles)
            result.log.append(
                f"Framing uses {len(needed_profiles)} profiles, "
                f"requiring {len(needed_families)} families"
            )
        else:
            needed_families = manifest.families
            result.log.append(
                f"No framing_json provided — resolving all {len(needed_families)} families"
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

        # Step 7: Build profile -> type mapping from resolved families
        profile_map = get_required_profiles(manifest)
        for profile_name, family_key in profile_map.items():
            if family_key in result.already_loaded or family_key in result.loaded or family_key in result.cached:
                # Map profile name to itself (the Revit type name)
                result.resolved[profile_name] = profile_name

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
        # Check if already loaded in Revit
        if family_key in loaded_in_revit:
            result.already_loaded.append(family_key)
            result.log.append(f"  {family_key}: already loaded in Revit")
            return

        # Check local cache
        is_cached = self._cache.is_cached(family_key, family_entry.sha256)
        cached_path = self._cache.get_cached_path(family_key) if is_cached else None

        if not cached_path:
            # Download from provider
            cached_path = self._download_and_cache(family_key, family_entry, result)
            if not cached_path:
                result.missing.append(family_key)
                return
        else:
            result.cached.append(family_key)
            result.log.append(f"  {family_key}: using cached file")

        # Load into Revit if doc is available
        if doc is not None:
            success = self._load_into_revit(
                doc, family_key, family_entry, cached_path, result
            )
            if success:
                result.loaded.append(family_key)
            else:
                result.missing.append(family_key)
        else:
            # No Revit doc — mark as cached-only
            if family_key not in result.cached:
                result.cached.append(family_key)
            result.log.append(f"  {family_key}: cached (no Revit doc to load into)")

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
    ) -> bool:
        """Load a .rfa file into Revit and activate its types.

        Args:
            doc: Revit Document
            family_key: Manifest family key
            family_entry: FamilyEntry with type info
            rfa_path: Path to .rfa file
            result: ResolutionResult for logging

        Returns:
            True if family was loaded and types activated
        """
        try:
            from src.timber_framing_generator.families.revit_loader import (
                load_family,
                activate_family_type,
            )
        except ImportError:
            result.log.append(f"  {family_key}: Revit loader not available")
            return False

        family = load_family(doc, rfa_path)
        if family is None:
            result.log.append(f"  {family_key}: LoadFamily FAILED for {rfa_path}")
            return False

        # Activate all types defined in manifest
        all_activated = True
        for type_name in family_entry.types:
            symbol = activate_family_type(doc, family, type_name)
            if symbol is None:
                result.log.append(
                    f"  {family_key}: type '{type_name}' activation FAILED"
                )
                all_activated = False
            else:
                result.log.append(f"  {family_key}: type '{type_name}' activated")

        return all_activated

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
        if manifest is None:
            # Try to build profile map from result.resolved
            profile_map = {}
        else:
            profile_map = get_required_profiles(manifest)

        for element in data.get("elements", []):
            profile = element.get("profile", {})
            profile_name = profile.get("name", "")

            if profile_name in result.resolved:
                family_key = profile_map.get(profile_name, "")
                element["revit_family"] = family_key
                element["revit_type"] = profile_name

        return json.dumps(data, indent=2)
