# File: src/timber_framing_generator/config/assembly_resolver.py

"""Assembly resolution strategy for variable-quality Revit wall data.

Resolves the correct wall assembly for each wall based on available data
quality and user-selected override mode. Supports four resolution modes:

- **auto** (default): Uses best available source (Revit > catalog > inferred > default).
- **revit_only**: Only uses Revit CompoundStructure data. Skips walls without it.
- **catalog**: Ignores Revit layers, matches Wall Type name to catalog using keywords.
- **custom**: User provides per-Wall-Type assembly mappings. Unmapped types fall back to auto.

Each resolved wall receives metadata: assembly_source, assembly_confidence,
assembly_notes, and assembly_name for downstream transparency.

Usage:
    from src.timber_framing_generator.config.assembly_resolver import (
        resolve_assembly,
        resolve_all_walls,
    )

    resolution = resolve_assembly(wall_data, mode="auto")
    print(resolution.source, resolution.confidence)

    enriched = resolve_all_walls(walls_list, mode="custom", custom_map={...})
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

VALID_MODES = {"auto", "revit_only", "catalog", "custom"}


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
# Thickness-Based Inference
# =============================================================================


def _infer_assembly_from_thickness(
    wall_data: Dict[str, Any],
) -> Optional[Tuple[str, float]]:
    """Infer a catalog assembly from wall thickness and is_exterior flag.

    This is the lowest-confidence automatic resolution, used when the
    Wall Type name doesn't match any catalog entry.

    Args:
        wall_data: Wall dict with wall_thickness and is_exterior.

    Returns:
        Tuple of (catalog_key, confidence) or None.
    """
    is_exterior = wall_data.get("is_exterior", False)
    thickness = wall_data.get("wall_thickness", 0.0)

    if not is_exterior:
        return ("2x4_interior", 0.4)

    # Exterior wall — try to distinguish 2x4 vs 2x6 by thickness
    # 2x4 exterior total ~4.9" (0.41 ft), 2x6 exterior total ~7.1" (0.59 ft)
    if thickness > 0:
        if thickness > 0.5:  # > 6 inches total
            return ("2x6_exterior", 0.4)
        else:
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
) -> AssemblyResolution:
    """Resolve the assembly for a single wall.

    Args:
        wall_data: Wall dict from walls_json with wall_type, wall_assembly,
            is_exterior, wall_thickness.
        mode: Resolution mode ("auto", "revit_only", "catalog", "custom").
        custom_map: Per-Wall-Type assembly mappings for "custom" mode.
            Keys are Revit Wall Type names (case-sensitive match first,
            then case-insensitive fallback).
            Values are catalog key strings or inline assembly dicts.

    Returns:
        AssemblyResolution with the chosen assembly and metadata.
    """
    if mode not in VALID_MODES:
        mode = "auto"

    wall_type = wall_data.get("wall_type", "")

    # --- Custom mode: check per-Wall-Type map first ---
    if mode == "custom" and custom_map:
        custom_assembly = _lookup_custom_map(wall_type, custom_map)
        if custom_assembly is not None:
            return AssemblyResolution(
                assembly=custom_assembly,
                source="custom",
                confidence=1.0,
                notes=f"User-mapped Wall Type '{wall_type}'",
                assembly_name=custom_assembly.get("name", "custom"),
            )
        # Unmapped types fall through to auto behavior

    # --- Revit-only mode ---
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
        return _resolve_catalog(wall_data, wall_type)

    # --- Auto mode (or custom fallback for unmapped types) ---
    return _resolve_auto(wall_data, wall_type)


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
) -> AssemblyResolution:
    """Resolve assembly in auto mode (best available source).

    Priority: explicit Revit > catalog name match > thickness inference > default.

    Args:
        wall_data: Wall dict.
        wall_type: Revit Wall Type name.

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

    # 3. Infer from thickness + is_exterior
    inferred = _infer_assembly_from_thickness(wall_data)
    if inferred:
        inferred_key, confidence = inferred
        assembly = _get_catalog_assembly(inferred_key)
        if assembly:
            is_exterior = wall_data.get("is_exterior", False)
            return AssemblyResolution(
                assembly=assembly,
                source="inferred",
                confidence=confidence,
                notes=f"Inferred from is_exterior={is_exterior}, thickness={wall_data.get('wall_thickness', 'unknown')}",
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
        notes=f"Default assembly (is_exterior={is_exterior})",
        assembly_name=default_key,
    )


def _resolve_catalog(
    wall_data: Dict[str, Any],
    wall_type: str,
) -> AssemblyResolution:
    """Resolve assembly in catalog mode (ignore Revit layers).

    Priority: catalog name match > thickness inference > default.

    Args:
        wall_data: Wall dict.
        wall_type: Revit Wall Type name.

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

    # 2. Infer from thickness + is_exterior
    inferred = _infer_assembly_from_thickness(wall_data)
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

    # 3. Default fallback
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
        mode: Resolution mode ("auto", "revit_only", "catalog", "custom").
        custom_map: Per-Wall-Type assembly mappings for "custom" mode.

    Returns:
        List of enriched wall dicts (new dicts, originals not mutated).
    """
    enriched: List[Dict[str, Any]] = []

    for wall_data in walls_data:
        resolution = resolve_assembly(wall_data, mode=mode, custom_map=custom_map)

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
