# File: src/timber_framing_generator/config/assembly_resolver.py

"""Assembly resolution strategy for variable-quality Revit wall data.

Resolves the correct wall assembly for each wall based on available data
quality and user-selected override mode. Supports two primary modes:

- **auto** (default): Uses best available source (Revit > catalog > inferred > default).
- **revit** (trust Revit): Uses Revit CompoundStructure. Falls back to auto if absent.

Legacy modes also supported for backward compatibility:
- **revit_only**: Only uses Revit CompoundStructure. Skips walls without it.
- **catalog**: Ignores Revit layers, matches Wall Type name to catalog.
- **custom**: Per-Wall-Type mappings. Unmapped types fall back to auto.

Both primary modes support ``assembly_overrides`` — per-Wall-Type
mappings that take priority over the mode's default resolution.

The ``framing_system`` parameter ("timber" or "cfs") determines how wall
thickness is mapped to framing depth: timber uses nominal lumber sizes
(3.5", 5.5", ...) while CFS uses actual web depths (4.0", 6.0", ...).

Each resolved wall receives metadata: assembly_source, assembly_confidence,
assembly_notes, and assembly_name for downstream transparency.

Usage:
    from src.timber_framing_generator.config.assembly_resolver import (
        resolve_assembly,
        resolve_all_walls,
    )

    resolution = resolve_assembly(wall_data, mode="auto")
    print(resolution.source, resolution.confidence)

    enriched = resolve_all_walls(walls_list, mode="auto",
                                 assembly_overrides={"My Wall": "2x6_exterior"},
                                 framing_system="timber")
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple


# =============================================================================
# Assembly Resolution Result
# =============================================================================


@dataclass
class AssemblyResolution:
    """Result of resolving an assembly for a wall.

    Attributes:
        assembly: Resolved assembly as a dict with "name", "layers", "source"
            keys. None if resolution failed (e.g., revit_only with no data).
        source: Where the assembly came from. One of:
            "explicit", "custom", "catalog", "inferred", "default", "skipped".
        confidence: Confidence score from 0.0 to 1.0.
        notes: Human-readable explanation of how the assembly was resolved.
        assembly_name: Assembly catalog key or custom name.
    """

    assembly: Optional[Dict[str, Any]]
    source: str
    confidence: float
    notes: str
    assembly_name: str

    def to_metadata(self) -> Dict[str, Any]:
        """Return metadata fields for enriching wall output."""
        return {
            "assembly_source": self.source,
            "assembly_confidence": self.confidence,
            "assembly_notes": self.notes,
            "assembly_name": self.assembly_name,
        }


# =============================================================================
# Valid Modes
# =============================================================================

VALID_MODES = {"auto", "revit", "revit_only", "catalog", "custom"}


# =============================================================================
# Catalog Keyword Matching
# =============================================================================

# Keywords used to fuzzy-match Revit Wall Type names to catalog entries.
# Each catalog entry has:
#   - required: keywords that MUST appear (all must match)
#   - required_any: at least ONE must appear (alternative to required)
#   - size_hint: keywords that boost confidence when present
#   - negative: keywords that disqualify this match
CATALOG_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "2x4_exterior": {
        "required": ["exterior"],
        "size_hint": ["2x4", '4"', "3.5", "3-1/2"],
        "negative": ["2x6", "2x8", "2x10", "2x12"],
    },
    "2x6_exterior": {
        "required": ["exterior"],
        "size_hint": ["2x6", '6"', "5.5", "5-1/2"],
        "negative": ["2x4", "2x8", "2x10"],
    },
    "2x4_interior": {
        "required_any": ["interior", "partition"],
        "size_hint": ["2x4", '4"', "3.5"],
        "negative": ["exterior"],
    },
}


def match_wall_type_to_catalog(
    wall_type: str,
) -> Optional[Tuple[str, float]]:
    """Fuzzy match a Revit Wall Type name to the assembly catalog.

    Extracts keywords from the Wall Type name and matches against
    CATALOG_KEYWORDS entries. Returns the best match with a confidence score.

    Args:
        wall_type: Revit Wall Type name (e.g., "Basic Wall - 2x6 Exterior").

    Returns:
        Tuple of (catalog_key, confidence) for the best match, or None
        if no catalog entry matches.
    """
    if not wall_type:
        return None

    normalized = wall_type.lower().strip()

    best_match: Optional[str] = None
    best_score: float = 0.0

    for catalog_key, keywords in CATALOG_KEYWORDS.items():
        score = _score_match(normalized, keywords)
        if score > best_score:
            best_score = score
            best_match = catalog_key

    if best_match and best_score > 0:
        return (best_match, best_score)

    return None


def _score_match(normalized_type: str, keywords: Dict[str, Any]) -> float:
    """Score how well a normalized wall type name matches a keyword spec.

    Args:
        normalized_type: Lowercased Wall Type name.
        keywords: Keyword spec with required/required_any/size_hint/negative.

    Returns:
        Score from 0.0 to 1.0. 0.0 means no match.
    """
    # Check negative keywords first — any match disqualifies
    for neg in keywords.get("negative", []):
        if neg.lower() in normalized_type:
            return 0.0

    # Check required keywords — ALL must match
    required = keywords.get("required", [])
    if required:
        if not all(kw.lower() in normalized_type for kw in required):
            return 0.0
        base_score = 0.6
    else:
        # Check required_any — at least ONE must match
        required_any = keywords.get("required_any", [])
        if required_any:
            if not any(kw.lower() in normalized_type for kw in required_any):
                return 0.0
            base_score = 0.6
        else:
            return 0.0

    # Boost score for size hint matches
    size_hints = keywords.get("size_hint", [])
    if size_hints:
        hits = sum(1 for kw in size_hints if kw.lower() in normalized_type)
        if hits > 0:
            # Each size hint match adds up to 0.3 total
            base_score += min(0.3, hits * 0.15)

    return min(1.0, base_score)


# =============================================================================
# Framing-Hint Inference (Option B)
# =============================================================================

# Standard nominal-to-actual lumber depths (inches).
# Used by _infer_from_framing_hint() and _nearest_lumber_size().
_LUMBER_ACTUAL_DEPTHS: Dict[str, float] = {
    "4": 3.5,
    "6": 5.5,
    "8": 7.25,
    "10": 9.25,
    "12": 11.25,
}


def _infer_from_framing_hint(
    wall_data: Dict[str, Any],
) -> Optional[Tuple[str, float]]:
    """Infer a catalog assembly from framing_hint injected by the GH component.

    When framing_json is connected, the MLSheath component extracts the actual
    stud profile depth per wall and stores it as ``framing_hint`` on the wall
    dict. This function maps that depth to the nearest standard lumber size
    and returns the corresponding catalog key.

    Args:
        wall_data: Wall dict, possibly containing framing_hint with depth_ft.

    Returns:
        Tuple of (catalog_key, confidence) or None if no hint present.
    """
    hint = wall_data.get("framing_hint")
    if not hint or not isinstance(hint, dict):
        return None

    depth_ft = hint.get("depth_ft")
    if depth_ft is None or depth_ft <= 0:
        return None

    depth_in = depth_ft * 12.0
    nominal = _nearest_lumber_size(depth_in)
    is_exterior = wall_data.get("is_exterior", False)

    # Map nominal lumber size to catalog key
    if is_exterior:
        if nominal == "6" or int(nominal) >= 6:
            return ("2x6_exterior", 0.85)
        return ("2x4_exterior", 0.85)
    else:
        return ("2x4_interior", 0.85)


def _nearest_lumber_size(depth_inches: float) -> str:
    """Map a depth in inches to the nearest standard lumber nominal size.

    Uses midpoints between consecutive standard actual depths as thresholds:
        2x4 (3.5") -- 4.5" -- 2x6 (5.5") -- 6.375" -- 2x8 (7.25") -- ...

    Args:
        depth_inches: Actual depth measurement in inches.

    Returns:
        Nominal size string (e.g., "4", "6", "8").
    """
    sizes = sorted(_LUMBER_ACTUAL_DEPTHS.items(), key=lambda x: x[1])
    for i, (nominal, actual) in enumerate(sizes):
        if i == len(sizes) - 1:
            return nominal
        next_actual = sizes[i + 1][1]
        midpoint = (actual + next_actual) / 2.0
        if depth_inches < midpoint:
            return nominal
    return sizes[-1][0]


# =============================================================================
# CFS Depth Mapping
# =============================================================================

# Standard CFS stud web depths (inches).
_CFS_WEB_DEPTHS = [2.5, 3.5, 4.0, 5.5, 6.0, 8.0, 10.0]


def _nearest_cfs_depth(depth_inches: float) -> float:
    """Map a depth in inches to the nearest CFS stud web depth using midpoints.

    CFS studs use nominal = actual web depth (unlike timber where nominal > actual).
    Standard depths: 250S (2.5"), 350S (3.5"), 400S (4.0"), 550S (5.5"),
    600S (6.0"), 800S (8.0"), 1000S (10.0").

    Args:
        depth_inches: Depth measurement in inches.

    Returns:
        Nearest CFS web depth in inches.
    """
    if depth_inches <= 0:
        return 3.5  # default: 350S

    best = _CFS_WEB_DEPTHS[0]
    for i in range(1, len(_CFS_WEB_DEPTHS)):
        midpoint = (_CFS_WEB_DEPTHS[i - 1] + _CFS_WEB_DEPTHS[i]) / 2.0
        if depth_inches >= midpoint:
            best = _CFS_WEB_DEPTHS[i]
        else:
            break
    return best


def _nearest_framing_depth(depth_inches: float, framing_system: str = "timber") -> float:
    """Map a depth in inches to the nearest actual framing depth.

    Dispatches to timber (_nearest_lumber_size → actual depth) or CFS
    (_nearest_cfs_depth) based on framing_system.

    Args:
        depth_inches: Wall thickness or framing depth in inches.
        framing_system: "timber" or "cfs".

    Returns:
        Actual framing depth in inches.
    """
    if framing_system == "cfs":
        return _nearest_cfs_depth(depth_inches)
    # Timber: _nearest_lumber_size returns nominal string, convert to actual depth
    nominal = _nearest_lumber_size(depth_inches)
    return _LUMBER_ACTUAL_DEPTHS.get(nominal, 3.5)


# =============================================================================
# Thickness-Based Inference (Option C — nearest lumber fallback)
# =============================================================================


def _infer_assembly_from_thickness(
    wall_data: Dict[str, Any],
    framing_system: str = "timber",
) -> Optional[Tuple[str, float]]:
    """Infer a catalog assembly from wall thickness and is_exterior flag.

    Uses the framing system's mapping table to determine the nominal framing
    depth from wall thickness, then selects the appropriate catalog assembly.

    Args:
        wall_data: Wall dict with wall_thickness and is_exterior.
        framing_system: "timber" or "cfs" — determines mapping table.

    Returns:
        Tuple of (catalog_key, confidence) or None.
    """
    is_exterior = wall_data.get("is_exterior", False)
    thickness = wall_data.get("wall_thickness", 0.0)

    if not is_exterior:
        return ("2x4_interior", 0.4)

    # Exterior wall — map thickness to nearest framing depth
    if thickness > 0:
        depth_inches = thickness * 12.0 if thickness < 2.0 else thickness
        actual_depth = _nearest_framing_depth(depth_inches, framing_system)

        # Map actual depth to catalog key (catalog uses timber naming)
        if actual_depth >= 5.5:
            return ("2x6_exterior", 0.4)
        return ("2x4_exterior", 0.4)

    # No thickness info — default by exterior/interior
    return ("2x4_exterior", 0.3) if is_exterior else ("2x4_interior", 0.3)


# =============================================================================
# Core Resolution Logic
# =============================================================================


def _has_explicit_assembly(wall_data: Dict[str, Any]) -> bool:
    """Check if a wall has a Revit-extracted multi-layer assembly.

    An explicit assembly must have a "layers" list with at least 2 layers
    and a source of "revit".

    Args:
        wall_data: Wall dict from walls_json.

    Returns:
        True if wall has an explicit Revit assembly.
    """
    assembly = wall_data.get("wall_assembly")
    if not assembly or not isinstance(assembly, dict):
        return False

    layers = assembly.get("layers", [])
    source = assembly.get("source", "")

    return len(layers) >= 2 and source == "revit"


def _get_catalog_assembly(catalog_key: str) -> Optional[Dict[str, Any]]:
    """Get an assembly dict from the catalog by key.

    Args:
        catalog_key: Key in WALL_ASSEMBLIES (e.g., "2x6_exterior").

    Returns:
        Assembly as a dict, or None if key not found.
    """
    try:
        from src.timber_framing_generator.config.assembly import WALL_ASSEMBLIES

        assembly_def = WALL_ASSEMBLIES.get(catalog_key)
        if assembly_def is None:
            return None

        # Convert WallAssemblyDef to dict for consistent handling
        return {
            "name": assembly_def.name,
            "layers": [
                {
                    "name": layer.name,
                    "function": layer.function.value,
                    "side": layer.side.value,
                    "thickness": layer.thickness,
                    "material": layer.material,
                    "priority": layer.priority,
                }
                for layer in assembly_def.layers
            ],
            "source": assembly_def.source,
        }
    except Exception:
        return None


def _parse_custom_value(value: Any) -> Optional[Dict[str, Any]]:
    """Parse a custom map value into an assembly dict.

    Values can be:
    - String: catalog key (e.g., "2x6_exterior")
    - Dict: inline assembly definition with "layers" list

    Args:
        value: Custom map value.

    Returns:
        Assembly dict, or None if invalid.
    """
    if isinstance(value, str):
        return _get_catalog_assembly(value)

    if isinstance(value, dict):
        # Validate minimal structure
        layers = value.get("layers", [])
        if not layers:
            return None
        # Ensure it has a name
        if "name" not in value:
            value = dict(value)
            value["name"] = "custom"
        if "source" not in value:
            value = dict(value)
            value["source"] = "custom"
        return value

    return None


def resolve_assembly(
    wall_data: Dict[str, Any],
    mode: str = "auto",
    custom_map: Optional[Dict[str, Any]] = None,
    assembly_overrides: Optional[Dict[str, Any]] = None,
    framing_system: str = "timber",
) -> AssemblyResolution:
    """Resolve the assembly for a single wall.

    Args:
        wall_data: Wall dict from walls_json with wall_type, wall_assembly,
            is_exterior, wall_thickness.
        mode: Resolution mode ("auto", "revit", "revit_only", "catalog", "custom").
        custom_map: Per-Wall-Type assembly mappings for legacy "custom" mode.
            Deprecated — use ``assembly_overrides`` instead.
        assembly_overrides: Per-Wall-Type assembly mappings applied in ANY mode.
            Keys are Revit Wall Type names. Values are catalog key strings or
            inline assembly dicts. Takes priority over mode-specific resolution.
        framing_system: "timber" or "cfs" — determines thickness-to-depth mapping.

    Returns:
        AssemblyResolution with the chosen assembly and metadata.
    """
    if mode not in VALID_MODES:
        mode = "auto"

    wall_type = wall_data.get("wall_type", "")

    # --- Assembly overrides: highest priority in ALL modes ---
    overrides = assembly_overrides or custom_map
    if overrides:
        override_assembly = _lookup_custom_map(wall_type, overrides)
        if override_assembly is not None:
            return AssemblyResolution(
                assembly=override_assembly,
                source="custom",
                confidence=1.0,
                notes=f"User-mapped Wall Type '{wall_type}'",
                assembly_name=override_assembly.get("name", "custom"),
            )

    # --- Legacy custom mode (unmapped types fall through to auto) ---
    # (kept for backward compat — assembly_overrides is the preferred path)

    # --- Revit mode: trust Revit, fall back to auto if absent ---
    if mode == "revit":
        if _has_explicit_assembly(wall_data):
            return AssemblyResolution(
                assembly=wall_data["wall_assembly"],
                source="explicit",
                confidence=1.0,
                notes="Revit CompoundStructure (revit mode)",
                assembly_name=wall_data["wall_assembly"].get("name", "revit"),
            )
        # Fall back to auto for walls without CompoundStructure
        return _resolve_auto(wall_data, wall_type, framing_system)

    # --- Revit-only mode (legacy — no fallback) ---
    if mode == "revit_only":
        if _has_explicit_assembly(wall_data):
            return AssemblyResolution(
                assembly=wall_data["wall_assembly"],
                source="explicit",
                confidence=1.0,
                notes="Revit CompoundStructure (revit_only mode)",
                assembly_name=wall_data["wall_assembly"].get("name", "revit"),
            )
        return AssemblyResolution(
            assembly=None,
            source="skipped",
            confidence=0.0,
            notes=f"No Revit CompoundStructure on Wall Type '{wall_type}' (revit_only mode)",
            assembly_name="",
        )

    # --- Catalog mode: ignore Revit layers, match by name ---
    if mode == "catalog":
        return _resolve_catalog(wall_data, wall_type, framing_system)

    # --- Auto mode (default, or custom/revit fallback for unmapped types) ---
    return _resolve_auto(wall_data, wall_type, framing_system)


def _lookup_custom_map(
    wall_type: str,
    custom_map: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Look up a Wall Type in the custom map.

    Tries exact match first, then case-insensitive match.

    Args:
        wall_type: Revit Wall Type name.
        custom_map: User-provided per-Wall-Type mappings.

    Returns:
        Parsed assembly dict, or None if not found or invalid.
    """
    # Exact match
    if wall_type in custom_map:
        return _parse_custom_value(custom_map[wall_type])

    # Case-insensitive fallback
    wall_type_lower = wall_type.lower()
    for key, value in custom_map.items():
        if key.lower() == wall_type_lower:
            return _parse_custom_value(value)

    return None


def _resolve_auto(
    wall_data: Dict[str, Any],
    wall_type: str,
    framing_system: str = "timber",
) -> AssemblyResolution:
    """Resolve assembly in auto mode (best available source).

    Priority: explicit Revit > catalog name match > framing hint > thickness > default.

    Args:
        wall_data: Wall dict.
        wall_type: Revit Wall Type name.
        framing_system: "timber" or "cfs" — passed to thickness inference.

    Returns:
        AssemblyResolution with the best available assembly.
    """
    # 1. Explicit Revit assembly (highest priority)
    if _has_explicit_assembly(wall_data):
        return AssemblyResolution(
            assembly=wall_data["wall_assembly"],
            source="explicit",
            confidence=1.0,
            notes="Revit CompoundStructure",
            assembly_name=wall_data["wall_assembly"].get("name", "revit"),
        )

    # 2. Catalog match by Wall Type name
    catalog_match = match_wall_type_to_catalog(wall_type)
    if catalog_match:
        catalog_key, confidence = catalog_match
        assembly = _get_catalog_assembly(catalog_key)
        if assembly:
            return AssemblyResolution(
                assembly=assembly,
                source="catalog",
                confidence=confidence,
                notes=f"Matched Wall Type '{wall_type}' to catalog '{catalog_key}'",
                assembly_name=catalog_key,
            )

    # 3. Framing hint (from framing_json stud depth — Option B)
    framing_hint = _infer_from_framing_hint(wall_data)
    if framing_hint:
        hint_key, confidence = framing_hint
        assembly = _get_catalog_assembly(hint_key)
        if assembly:
            depth_ft = wall_data.get("framing_hint", {}).get("depth_ft", 0)
            return AssemblyResolution(
                assembly=assembly,
                source="framing_hint",
                confidence=confidence,
                notes=f"Inferred from framing stud depth {depth_ft:.4f} ft -> '{hint_key}'",
                assembly_name=hint_key,
            )

    # 4. Infer from thickness + is_exterior (uses framing_system for mapping)
    inferred = _infer_assembly_from_thickness(wall_data, framing_system)
    if inferred:
        inferred_key, confidence = inferred
        assembly = _get_catalog_assembly(inferred_key)
        if assembly:
            is_exterior = wall_data.get("is_exterior", False)
            return AssemblyResolution(
                assembly=assembly,
                source="inferred",
                confidence=confidence,
                notes=f"Inferred from is_exterior={is_exterior}, thickness={wall_data.get('wall_thickness', 'unknown')}, system={framing_system}",
                assembly_name=inferred_key,
            )

    # 5. Default fallback
    is_exterior = wall_data.get("is_exterior", False)
    default_key = "2x4_exterior" if is_exterior else "2x4_interior"
    assembly = _get_catalog_assembly(default_key)
    return AssemblyResolution(
        assembly=assembly,
        source="default",
        confidence=0.1,
        notes=f"Default assembly (is_exterior={is_exterior})",
        assembly_name=default_key,
    )


def _resolve_catalog(
    wall_data: Dict[str, Any],
    wall_type: str,
    framing_system: str = "timber",
) -> AssemblyResolution:
    """Resolve assembly in catalog mode (ignore Revit layers).

    Priority: catalog name match > framing hint > thickness inference > default.

    Args:
        wall_data: Wall dict.
        wall_type: Revit Wall Type name.
        framing_system: "timber" or "cfs" — passed to thickness inference.

    Returns:
        AssemblyResolution with catalog-based assembly.
    """
    # 1. Catalog match by Wall Type name
    catalog_match = match_wall_type_to_catalog(wall_type)
    if catalog_match:
        catalog_key, confidence = catalog_match
        assembly = _get_catalog_assembly(catalog_key)
        if assembly:
            return AssemblyResolution(
                assembly=assembly,
                source="catalog",
                confidence=confidence,
                notes=f"Catalog match: '{wall_type}' -> '{catalog_key}' (catalog mode)",
                assembly_name=catalog_key,
            )

    # 2. Framing hint (from framing_json stud depth — Option B)
    framing_hint = _infer_from_framing_hint(wall_data)
    if framing_hint:
        hint_key, confidence = framing_hint
        assembly = _get_catalog_assembly(hint_key)
        if assembly:
            depth_ft = wall_data.get("framing_hint", {}).get("depth_ft", 0)
            return AssemblyResolution(
                assembly=assembly,
                source="framing_hint",
                confidence=confidence,
                notes=f"Inferred from framing stud depth {depth_ft:.4f} ft -> '{hint_key}' (catalog mode)",
                assembly_name=hint_key,
            )

    # 3. Infer from thickness + is_exterior
    inferred = _infer_assembly_from_thickness(wall_data, framing_system)
    if inferred:
        inferred_key, confidence = inferred
        assembly = _get_catalog_assembly(inferred_key)
        if assembly:
            return AssemblyResolution(
                assembly=assembly,
                source="inferred",
                confidence=confidence,
                notes=f"Inferred (catalog mode, no name match for '{wall_type}')",
                assembly_name=inferred_key,
            )

    # 4. Default fallback
    is_exterior = wall_data.get("is_exterior", False)
    default_key = "2x4_exterior" if is_exterior else "2x4_interior"
    assembly = _get_catalog_assembly(default_key)
    return AssemblyResolution(
        assembly=assembly,
        source="default",
        confidence=0.1,
        notes=f"Default (catalog mode, no match for '{wall_type}')",
        assembly_name=default_key,
    )


# =============================================================================
# Batch Resolution
# =============================================================================


def resolve_all_walls(
    walls_data: List[Dict[str, Any]],
    mode: str = "auto",
    custom_map: Optional[Dict[str, Any]] = None,
    assembly_overrides: Optional[Dict[str, Any]] = None,
    framing_system: str = "timber",
) -> List[Dict[str, Any]]:
    """Resolve assemblies for all walls, enriching each with metadata.

    For each wall, resolves the assembly and adds metadata fields:
    - wall_assembly: Resolved assembly dict (if not already present or overridden)
    - assembly_source: "explicit", "custom", "catalog", "inferred", "default", "skipped"
    - assembly_confidence: 0.0 to 1.0
    - assembly_notes: Human-readable explanation
    - assembly_name: Catalog key or custom name

    Args:
        walls_data: List of wall dicts from walls_json.
        mode: Resolution mode ("auto", "revit", "revit_only", "catalog", "custom").
        custom_map: Per-Wall-Type assembly mappings (legacy — use assembly_overrides).
        assembly_overrides: Per-Wall-Type assembly mappings, applied in ALL modes.
        framing_system: "timber" or "cfs" — determines thickness-to-depth mapping.

    Returns:
        List of enriched wall dicts (new dicts, originals not mutated).
    """
    enriched: List[Dict[str, Any]] = []

    for wall_data in walls_data:
        resolution = resolve_assembly(
            wall_data,
            mode=mode,
            custom_map=custom_map,
            assembly_overrides=assembly_overrides,
            framing_system=framing_system,
        )

        # Create enriched copy
        enriched_wall = dict(wall_data)
        enriched_wall.update(resolution.to_metadata())

        # Set wall_assembly if resolved (and not skipped)
        if resolution.assembly is not None:
            enriched_wall["wall_assembly"] = resolution.assembly

        enriched.append(enriched_wall)

    return enriched


def summarize_resolutions(
    walls_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarize assembly resolution quality across walls.

    Reads the assembly_source metadata from enriched wall dicts.

    Args:
        walls_data: List of enriched wall dicts (after resolve_all_walls).

    Returns:
        Dict with counts per source and average confidence.
    """
    counts: Dict[str, int] = {}
    confidences: List[float] = []

    for wall in walls_data:
        source = wall.get("assembly_source", "unknown")
        counts[source] = counts.get(source, 0) + 1
        conf = wall.get("assembly_confidence", 0.0)
        confidences.append(conf)

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "total_walls": len(walls_data),
        "by_source": counts,
        "average_confidence": round(avg_confidence, 2),
    }
