# File: src/constructai_demo/revit_creator.py
"""Create Revit walls, doors, and windows from converted Kreo data.

All Revit API interaction is isolated here. Requires Rhino.Inside.Revit
environment (import clr, Autodesk.Revit.DB).

This module is only importable inside a GHPython/RiR context.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .coordinate_converter import ConvertedOpening, ConvertedWall
from .opening_matcher import MatchedOpening
from .wall_classifier import (
    WALL_CLASS_NAMES,
    WALL_CLASS_THICKNESS_FT,
    WallClass,
    classify_wall,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Family name aliases
# ---------------------------------------------------------------------------

# Maps common shorthand names (lowercased) to actual Revit family names.
# Used to handle cases where the agent sends abbreviated or generic names.
DOOR_FAMILY_ALIASES: Dict[str, str] = {
    "pocket":                        "Sliding_Door_Pocket",
    "pocket door":                   "Sliding_Door_Pocket",
    "sliding_door_pocket":           "Sliding_Door_Pocket",
    "sliding door pocket":           "Sliding_Door_Pocket",
    "sliding bypass":                "Doors_Sliding_Interior_Integrated",
    "bypass":                        "Doors_Sliding_Interior_Integrated",
    "barn":                          "Doors_Sliding_Interior_Integrated",
    "barn door":                     "Doors_Sliding_Interior_Integrated",
    "doors_sliding_interior":        "Doors_Sliding_Interior_Integrated",
    "sliding interior":              "Doors_Sliding_Interior_Integrated",
    "overhead":                      "Overhead-Garage-Door",
    "overhead-sectional":            "Overhead-Garage-Door",
    "overhead sectional":            "Overhead-Garage-Door",
    "garage":                        "Overhead-Garage-Door",
    "overhead garage":               "Overhead-Garage-Door",
    "overhead-garage":               "Overhead-Garage-Door",
    "overhead-garage-door":          "Overhead-Garage-Door",
}

WINDOW_FAMILY_ALIASES: Dict[str, str] = {
    "fixed":                         "Fixed",
    "casement":                      "Casement with Trim",
    "double hung":                   "Double Hung",
    "slider":                        "Slider with Trim",
    "sliding":                       "Slider with Trim",
    "awning":                        "Awning",
}


def _normalize_family_name(
    doc,
    requested_name: str,
    category,
    aliases: Dict[str, str],
) -> str:
    """Resolve a shorthand/alias family name to an actual loaded Revit family.

    Resolution order:
    1. Hardcoded alias table (most reliable for known families)
    2. Exact match against families loaded in the document
    3. Case-insensitive exact match
    4. Substring match (requested name contained in loaded family name)
    5. Original name (unchanged, will fail later with a clear error)

    Args:
        doc: Active Revit document.
        requested_name: Family name from the agent/schedule (may be abbreviated).
        category: Revit BuiltInCategory for the element type.
        aliases: Alias dict (e.g., DOOR_FAMILY_ALIASES).

    Returns:
        Resolved family name string.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    alias_key = requested_name.lower().strip()

    # 1. Hardcoded aliases
    if alias_key in aliases:
        resolved = aliases[alias_key]
        if resolved != requested_name:
            logger.info("Family alias: '%s' -> '%s'", requested_name, resolved)
        return resolved

    # Collect all loaded family names from document
    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(category)
        .OfClass(DB.FamilySymbol)
    )
    loaded: Dict[str, str] = {}  # lower -> original
    for sym in collector:
        fname = sym.Family.Name
        loaded[fname.lower()] = fname

    # 2. Exact match (case-insensitive)
    if alias_key in loaded:
        return loaded[alias_key]

    # 3. Substring match: requested name appears in loaded family name
    req_norm = alias_key.replace("-", "").replace("_", "").replace(" ", "")
    for fname_lower, fname_orig in loaded.items():
        fname_norm = fname_lower.replace("-", "").replace("_", "").replace(" ", "")
        if req_norm and (req_norm in fname_norm or fname_norm in req_norm):
            logger.info(
                "Family partial match: '%s' -> '%s'", requested_name, fname_orig
            )
            return fname_orig

    # 4. No match found — return original (will cause a clear lookup failure)
    return requested_name


def _eid_int(element_id) -> int:
    """Get integer from ElementId (Revit 2025+: .Value, older: .IntegerValue)."""
    if hasattr(element_id, "Value"):
        return int(element_id.Value)
    return int(element_id.IntegerValue)


def create_walls(
    doc,  # Autodesk.Revit.DB.Document
    walls: List[ConvertedWall],
    level,  # Autodesk.Revit.DB.Level
    wall_height_ft: float = 8.0,
    structural: bool = True,
) -> List[Tuple[int, object]]:
    """Create Revit walls from converted Kreo wall data.

    Args:
        doc: Active Revit document.
        walls: List of ConvertedWall objects in Revit feet.
        level: Revit Level to place walls on.
        wall_height_ft: Wall height in feet (default 8.0).
        structural: Whether walls are structural.

    Returns:
        List of (original_wall_index, DB.Wall) tuples.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    created: List[Tuple[int, object]] = []

    # Build wall type cache
    wall_type_map = _build_wall_type_map(doc)

    t = DB.Transaction(doc, "Create Kreo Walls")
    t.Start()
    try:
        for wall in walls:
            wall_class = classify_wall(wall.thickness_m, wall.is_exterior)
            wall_type = wall_type_map.get(wall_class)

            # Create line
            p1 = DB.XYZ(wall.p1.x, wall.p1.y, 0.0)
            p2 = DB.XYZ(wall.p2.x, wall.p2.y, 0.0)

            # Skip degenerate walls
            if p1.DistanceTo(p2) < 0.01:
                logger.warning(
                    "Skipping degenerate wall %d (length < 0.01 ft)",
                    wall.original_index,
                )
                continue

            line = DB.Line.CreateBound(p1, p2)

            if wall_type is not None:
                revit_wall = DB.Wall.Create(
                    doc, line, wall_type.Id, level.Id,
                    wall_height_ft, 0.0, False, structural,
                )
            else:
                # Fallback: use default wall type
                revit_wall = DB.Wall.Create(
                    doc, line, level.Id,
                    structural,
                )
                # Set height manually
                param = revit_wall.get_Parameter(
                    DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM
                )
                if param and not param.IsReadOnly:
                    param.Set(wall_height_ft)

            created.append((wall.original_index, revit_wall))
            logger.debug(
                "Created wall %d: %s (%.1f ft)",
                wall.original_index, wall_class.value, wall.length_ft,
            )

        t.Commit()
        logger.info("Created %d walls in Revit", len(created))
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise

    return created


def place_openings(
    doc,  # Autodesk.Revit.DB.Document
    matched_openings: Dict[int, List[MatchedOpening]],
    host_walls: Dict[int, object],  # wall_index -> DB.Wall
    level,  # Autodesk.Revit.DB.Level
    door_symbol=None,  # DB.FamilySymbol
    window_symbol=None,  # DB.FamilySymbol
    default_sill_height_ft: float = 3.0,
) -> List[Tuple[str, object]]:
    """Place door and window family instances on host walls.

    Args:
        doc: Active Revit document.
        matched_openings: Dict from match_openings_to_walls.
        host_walls: Dict mapping wall_index -> Revit DB.Wall.
        level: Revit Level.
        door_symbol: Door FamilySymbol (auto-found if None).
        window_symbol: Window FamilySymbol (auto-found if None).
        default_sill_height_ft: Default sill height for windows.

    Returns:
        List of (opening_type, FamilyInstance) tuples.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    if door_symbol is None:
        door_symbol = find_door_family(doc)
    if window_symbol is None:
        window_symbol = find_window_family(doc)

    created: List[Tuple[str, object]] = []

    t = DB.Transaction(doc, "Place Kreo Openings")
    t.Start()
    try:
        for wall_idx, matches in matched_openings.items():
            host_wall = host_walls.get(wall_idx)
            if host_wall is None:
                logger.warning(
                    "No host wall for index %d, skipping %d openings",
                    wall_idx, len(matches),
                )
                continue

            for match in matches:
                opening = match.opening
                ip = match.insertion_point
                point = DB.XYZ(ip.x, ip.y, 0.0)

                if opening.opening_type == "door" and door_symbol is not None:
                    _ensure_activated(doc, door_symbol)
                    instance = doc.Create.NewFamilyInstance(
                        point, door_symbol, host_wall, level,
                        DB.Structure.StructuralType.NonStructural,
                    )
                    created.append(("door", instance))
                elif opening.opening_type == "window" and window_symbol is not None:
                    _ensure_activated(doc, window_symbol)
                    instance = doc.Create.NewFamilyInstance(
                        point, window_symbol, host_wall, level,
                        DB.Structure.StructuralType.NonStructural,
                    )
                    # Set sill height
                    sill_param = instance.get_Parameter(
                        DB.BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM
                    )
                    if sill_param and not sill_param.IsReadOnly:
                        sill_param.Set(default_sill_height_ft)
                    created.append(("window", instance))
                else:
                    logger.warning(
                        "No family symbol for %s, skipping",
                        opening.opening_type,
                    )

        t.Commit()
        door_count = sum(1 for typ, _ in created if typ == "door")
        window_count = sum(1 for typ, _ in created if typ == "window")
        logger.info(
            "Placed %d doors and %d windows in Revit",
            door_count, window_count,
        )
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise

    return created


def ensure_door_types(
    doc,  # Autodesk.Revit.DB.Document
    door_schedule: List[dict],
) -> Tuple[Dict[str, str], List[dict]]:
    """Ensure all door types from a schedule exist in the Revit document.

    For each schedule entry:
    1. Build target revit_type string "Family : Width x Height"
    2. Try to find an existing FamilySymbol
    3. If the family exists but the type doesn't, duplicate and set dimensions
    4. If the family isn't loaded, try loading .rfa from families/ manifest
    5. If the family doesn't exist anywhere, use Single-Flush fallback

    Args:
        doc: Active Revit document.
        door_schedule: List of schedule entries, each with:
            - id: Schedule identifier (e.g., "A", "B")
            - width_in: Door width in inches
            - height_in: Door height in inches
            - family: Revit family name (e.g., "Single-Flush")

    Returns:
        Tuple of:
            - type_map: Dict mapping schedule_id -> revit_type string
            - fallbacks: List of dicts describing fallback substitutions
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    type_map: Dict[str, str] = {}
    fallbacks: List[dict] = []

    # Find a fallback symbol (first available door family)
    fallback_symbol = find_door_family(doc)
    fallback_type: Optional[str] = None
    if fallback_symbol:
        fallback_type = f"{fallback_symbol.Family.Name} : {fallback_symbol.Name}"

    # Collect entries that need type duplication
    entries_needing_duplication: List[Tuple[dict, str, object]] = []

    for entry in door_schedule:
        schedule_id = str(entry.get("id", ""))
        width_in = float(entry.get("width_in", 36))
        height_in = float(entry.get("height_in", 80))
        raw_family = str(entry.get("family", "Single-Flush"))

        # Resolve alias/shorthand to actual loaded family name
        family_name = _normalize_family_name(
            doc, raw_family, DB.BuiltInCategory.OST_Doors, DOOR_FAMILY_ALIASES
        )

        type_name = f'{int(width_in)}" x {int(height_in)}"'
        revit_type = f"{family_name} : {type_name}"

        # Try to find existing symbol
        symbol = find_family_symbol_by_name(
            doc, revit_type, DB.BuiltInCategory.OST_Doors
        )
        if symbol:
            type_map[schedule_id] = revit_type
            logger.info("Schedule %s: found '%s'", schedule_id, revit_type)
            continue

        # Try to find any type in the requested family for duplication
        source = _find_any_type_in_family(
            doc, family_name, DB.BuiltInCategory.OST_Doors
        )
        if source:
            entries_needing_duplication.append((entry, type_name, source))
            continue

        # Family not in document -- try loading from families/ manifest
        loaded_family = _load_family_from_manifest(doc, family_name)
        if loaded_family:
            # Re-check for a source symbol after loading
            source = _find_any_type_in_family(
                doc, family_name, DB.BuiltInCategory.OST_Doors
            )
            if source:
                entries_needing_duplication.append((entry, type_name, source))
                continue

        # Family not available anywhere -- fall back
        if fallback_type:
            type_map[schedule_id] = fallback_type
            fallbacks.append({
                "schedule_id": schedule_id,
                "requested": revit_type,
                "resolved": fallback_type,
                "reason": f"Family '{family_name}' not loaded in document",
            })
            logger.warning(
                "Schedule %s: '%s' not found, fallback -> '%s'",
                schedule_id, revit_type, fallback_type,
            )
        else:
            fallbacks.append({
                "schedule_id": schedule_id,
                "requested": revit_type,
                "resolved": None,
                "reason": "No door families loaded in document",
            })
            logger.error(
                "Schedule %s: '%s' not found, no fallback available",
                schedule_id, revit_type,
            )

    # Duplicate types that were missing (requires a transaction)
    if entries_needing_duplication:
        t = DB.Transaction(doc, "Create Door Types from Schedule")
        t.Start()
        try:
            for entry, type_name, source in entries_needing_duplication:
                schedule_id = str(entry.get("id", ""))
                width_in = float(entry.get("width_in", 36))
                height_in = float(entry.get("height_in", 80))
                family_name = str(entry.get("family", "Single-Flush"))
                revit_type = f"{family_name} : {type_name}"

                new_symbol = _duplicate_door_type(
                    doc, source, type_name, width_in, height_in
                )
                if new_symbol:
                    type_map[schedule_id] = revit_type
                    logger.info(
                        "Schedule %s: duplicated '%s' -> '%s'",
                        schedule_id, source.Name, type_name,
                    )
                elif fallback_type:
                    type_map[schedule_id] = fallback_type
                    fallbacks.append({
                        "schedule_id": schedule_id,
                        "requested": revit_type,
                        "resolved": fallback_type,
                        "reason": f"Failed to duplicate type '{type_name}'",
                    })
                    logger.warning(
                        "Schedule %s: duplication failed, fallback -> '%s'",
                        schedule_id, fallback_type,
                    )
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise

    logger.info(
        "ensure_door_types: %d types resolved, %d fallbacks",
        len(type_map), len(fallbacks),
    )
    return type_map, fallbacks


def match_door_to_schedule(
    detected_width_ft: float,
    door_schedule: List[dict],
    tolerance_in: float = 2.0,
) -> Optional[str]:
    """Match a detected door width to the best schedule entry.

    Args:
        detected_width_ft: Detected door width in feet.
        door_schedule: List of schedule entries with width_in.
        tolerance_in: Maximum allowed difference in inches.

    Returns:
        Schedule entry 'id', or None if no match within tolerance.
    """
    detected_width_in = detected_width_ft * 12.0
    best_id: Optional[str] = None
    best_diff = float("inf")

    for entry in door_schedule:
        schedule_width_in = float(entry.get("width_in", 0))
        diff = abs(detected_width_in - schedule_width_in)
        if diff < best_diff and diff <= tolerance_in:
            best_diff = diff
            best_id = str(entry.get("id", ""))

    return best_id


def find_family_symbol_by_name(
    doc,
    family_type_name: str,
    category,
) -> Optional[object]:
    """Look up a FamilySymbol by 'Family : Type' name string.

    Args:
        doc: Active Revit document.
        family_type_name: String in format "FamilyName : TypeName".
        category: Revit BuiltInCategory (e.g., OST_Doors, OST_Windows).

    Returns:
        DB.FamilySymbol or None if not found.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    parts = family_type_name.split(" : ", 1)
    if len(parts) != 2:
        logger.warning("Invalid revit_type format '%s', expected 'Family : Type'", family_type_name)
        return None

    family_name, type_name = parts[0].strip(), parts[1].strip()

    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(category)
        .OfClass(DB.FamilySymbol)
    )
    for symbol in collector:
        if symbol.Family.Name == family_name and symbol.Name == type_name:
            return symbol

    logger.warning("FamilySymbol '%s : %s' not found in document", family_name, type_name)
    return None


def find_door_family(doc) -> Optional[object]:
    """Find the first available single door FamilySymbol.

    Args:
        doc: Active Revit document.

    Returns:
        DB.FamilySymbol or None if no door family found.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_Doors)
        .OfClass(DB.FamilySymbol)
    )
    for symbol in collector:
        return symbol  # Return first available
    logger.warning("No door family found in document")
    return None


def find_window_family(doc) -> Optional[object]:
    """Find the first available window FamilySymbol.

    Args:
        doc: Active Revit document.

    Returns:
        DB.FamilySymbol or None if no window family found.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_Windows)
        .OfClass(DB.FamilySymbol)
    )
    for symbol in collector:
        return symbol
    logger.warning("No window family found in document")
    return None


def find_level(doc, name: Optional[str] = None) -> Optional[object]:
    """Find a Revit Level by name, or return the lowest level.

    Args:
        doc: Active Revit document.
        name: Optional level name to search for.

    Returns:
        DB.Level or None.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    collector = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Level)
    )
    levels = list(collector)
    if not levels:
        logger.warning("No levels found in document")
        return None

    if name:
        for level in levels:
            if level.Name == name:
                return level
        logger.warning("Level '%s' not found, using lowest level", name)

    # Return level with lowest elevation
    return min(levels, key=lambda lv: lv.Elevation)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_wall_type_map(doc) -> Dict[WallClass, object]:
    """Build a map of WallClass -> best matching Revit WallType.

    Strategy (per wall class, in order):
    1. Exact name match against WALL_CLASS_NAMES target name
    2. Keyword + width match (INT/EXT keyword to distinguish same-width types)
    3. Width-only match, skipping types already assigned to another class
    4. Fallback to first available WallType

    The keyword strategy is critical because INTERIOR_2X4 and EXTERIOR_2X4
    both target 3.5" width but need distinct Revit wall types.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    collector = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.WallType)
    )
    all_types = list(collector)
    if not all_types:
        return {}

    # Build a name cache: WallType -> type name string
    type_names: Dict[int, str] = {}
    basic_types = []
    for wt in all_types:
        try:
            if wt.Kind == DB.WallKind.Basic:
                basic_types.append(wt)
                name_param = wt.get_Parameter(
                    DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
                )
                if name_param:
                    type_names[_eid_int(wt.Id)] = str(name_param.AsString())
        except Exception:
            continue

    # Keywords to distinguish same-width wall types
    _WALL_CLASS_KEYWORDS: Dict[WallClass, list] = {
        WallClass.INTERIOR_2X4: ["INT", "Interior", "interior"],
        WallClass.EXTERIOR_2X4: ["EXT", "Exterior", "exterior"],
        WallClass.EXTERIOR_2X6: ["EXT", "Exterior", "exterior"],
    }

    result: Dict[WallClass, object] = {}
    used_type_ids: set = set()

    for wall_class in WallClass:
        target_ft = WALL_CLASS_THICKNESS_FT[wall_class]
        target_name = WALL_CLASS_NAMES[wall_class]
        keywords = _WALL_CLASS_KEYWORDS.get(wall_class, [])

        # Strategy 1: Exact name match
        exact_match = None
        for wt in basic_types:
            wt_name = type_names.get(_eid_int(wt.Id), "")
            if wt_name == target_name:
                exact_match = wt
                break

        if exact_match:
            result[wall_class] = exact_match
            used_type_ids.add(_eid_int(exact_match.Id))
            continue

        # Strategy 2: Width match + keyword (to distinguish INT vs EXT at 3.5")
        keyword_match = None
        for wt in basic_types:
            if _eid_int(wt.Id) in used_type_ids:
                continue
            wt_name = type_names.get(_eid_int(wt.Id), "")
            width = wt.Width
            if abs(width - target_ft) < 0.05:  # within ~0.6"
                for kw in keywords:
                    if kw in wt_name:
                        keyword_match = wt
                        break
                if keyword_match:
                    break

        if keyword_match:
            result[wall_class] = keyword_match
            used_type_ids.add(_eid_int(keyword_match.Id))
            continue

        # Strategy 3: Width-only match, skip already-assigned types
        best_type = None
        best_diff = float("inf")
        for wt in basic_types:
            if _eid_int(wt.Id) in used_type_ids:
                continue
            diff = abs(wt.Width - target_ft)
            if diff < best_diff:
                best_diff = diff
                best_type = wt

        if best_type:
            result[wall_class] = best_type
            used_type_ids.add(_eid_int(best_type.Id))

    return result


def place_openings_by_id(
    doc,  # Autodesk.Revit.DB.Document
    matched_openings: Dict[int, List[MatchedOpening]],  # wall_list_index -> matches
    wall_ids: List[int],  # wall_list_index -> ElementId integer
    level,  # Autodesk.Revit.DB.Level
    family_symbol=None,  # DB.FamilySymbol
    opening_type: str = "door",  # "door" or "window"
    sill_height_ft: float = 0.0,
) -> List[Tuple[str, int]]:
    """Place openings using ElementId integers instead of DB.Wall references.

    Avoids stale DB.Wall references by looking up each host wall fresh
    from the document using its ElementId.

    Args:
        doc: Active Revit document.
        matched_openings: Dict mapping wall list index -> list of MatchedOpening.
        wall_ids: List where wall_ids[list_idx] is the Revit ElementId integer.
        level: Revit Level for placement.
        family_symbol: Default FamilySymbol (auto-found if None).
            Used when opening has no revit_type override.
        opening_type: "door" or "window".
        sill_height_ft: Sill height in feet. Default 0.0 for doors, 3.0 for windows.

    Returns:
        List of (opening_type, element_id_int) tuples for placed instances.
    """
    import clr
    import System
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    # Determine category for family lookup
    if opening_type == "door":
        category = DB.BuiltInCategory.OST_Doors
    else:
        category = DB.BuiltInCategory.OST_Windows

    # Find default family symbol
    if family_symbol is None:
        if opening_type == "door":
            family_symbol = find_door_family(doc)
        else:
            family_symbol = find_window_family(doc)

    if family_symbol is None:
        logger.warning("No family symbol found for %s, skipping all", opening_type)
        return []

    created: List[Tuple[str, int]] = []

    # Cache for per-opening family symbol lookup by revit_type string
    symbol_cache: Dict[str, Optional[object]] = {}

    # Pre-scan: collect unique revit_type strings and resolve them.
    # Loading families from manifest requires its own transaction,
    # so this must happen BEFORE the placement transaction.
    unique_types: set = set()
    for matches in matched_openings.values():
        for match in matches:
            rt = getattr(match.opening, "revit_type", None)
            if rt:
                unique_types.add(rt)

    print(
        "[PRE-SCAN] %d unique revit_type strings: %s"
        % (len(unique_types), list(unique_types))
    )

    # Load manifest once for dimension_params + type-specific dims
    manifest_families = {}
    try:
        import os as _os
        _this = _os.path.dirname(_os.path.abspath(__file__))
        _root = _os.path.dirname(_os.path.dirname(_this))
        _mpath = _os.path.join(_root, "families", "manifest.json")
        if _os.path.exists(_mpath):
            import json as _json
            with open(_mpath, "r") as _f:
                manifest_families = _json.load(_f).get("families", {})
    except Exception as _me:
        print("[PRE-SCAN] Could not load manifest: %s" % _me)

    for rt in unique_types:
        found = find_family_symbol_by_name(doc, rt, category)
        if found:
            print("[PRE-SCAN]   '%s' -> found existing symbol" % rt)
        if not found:
            # Try loading the family from families/manifest.json
            parts = rt.split(" : ", 1)
            if len(parts) == 2:
                family_name = parts[0].strip()
                type_name = parts[1].strip()

                # Get manifest entry for this family
                m_entry = manifest_families.get(family_name, {})
                m_dim_params = m_entry.get("dimension_params")
                m_types = m_entry.get("types", {})
                m_type_data = m_types.get(type_name, {})
                if m_dim_params:
                    print(
                        "[PRE-SCAN]   '%s' -> manifest dimension_params: %s"
                        % (rt, m_dim_params)
                    )
                if m_type_data:
                    print(
                        "[PRE-SCAN]   '%s' -> manifest type dims: w=%s h=%s"
                        % (rt, m_type_data.get("width_in"),
                           m_type_data.get("height_in"))
                    )

                # Step A: Check if family already exists in document
                # (handles template-resident families with no .rfa)
                source = _find_any_type_in_family(
                    doc, family_name, category
                )
                if source:
                    print(
                        "[PRE-SCAN]   '%s' -> family '%s' already in doc "
                        "(source type='%s')"
                        % (rt, family_name, source.Name)
                    )
                else:
                    # Step B: Try loading from manifest .rfa
                    loaded = _load_family_from_manifest(doc, family_name)
                    if loaded:
                        loaded_name = getattr(loaded, "Name", "???")
                        print(
                            "[PRE-SCAN]   '%s' -> loaded family from manifest "
                            "(internal name='%s')" % (rt, loaded_name)
                        )
                        # Retry exact lookup after loading
                        found = find_family_symbol_by_name(
                            doc, rt, category
                        )
                        if found:
                            print(
                                "[PRE-SCAN]   '%s' -> found after manifest "
                                "load" % rt
                            )
                        if not found:
                            source = _find_any_type_in_family(
                                doc, family_name, category
                            )
                            if not source and loaded_name != family_name:
                                print(
                                    "[PRE-SCAN]   '%s' -> name mismatch! "
                                    "file='%s' revit='%s', retrying..."
                                    % (rt, family_name, loaded_name)
                                )
                                source = _find_any_type_in_family(
                                    doc, loaded_name, category
                                )
                            if not source:
                                print(
                                    "[PRE-SCAN]   '%s' -> collector failed, "
                                    "trying GetFamilySymbolIds()..." % rt
                                )
                                sym_ids = loaded.GetFamilySymbolIds()
                                for sid in sym_ids:
                                    source = doc.GetElement(sid)
                                    if source:
                                        print(
                                            "[PRE-SCAN]   '%s' -> found via "
                                            "GetFamilySymbolIds: '%s'"
                                            % (rt, source.Name)
                                        )
                                        break
                    else:
                        print(
                            "[PRE-SCAN]   '%s' -> not in doc and manifest "
                            "load failed for '%s'" % (rt, family_name)
                        )

                # Step C: Duplicate type from source symbol
                # (works for both template-resident and manifest-loaded)
                if source and not found:
                    print(
                        "[PRE-SCAN]   '%s' -> duplicating from '%s : %s'"
                        % (rt, source.Family.Name, source.Name)
                    )
                    if m_type_data:
                        dims = (
                            m_type_data.get("width_in"),
                            m_type_data.get("height_in"),
                        )
                        if dims[0] is None or dims[1] is None:
                            dims = _parse_type_dimensions(type_name)
                    else:
                        dims = _parse_type_dimensions(type_name)
                    if dims:
                        dup_t = DB.Transaction(
                            doc, "Create Type: %s" % type_name
                        )
                        dup_t.Start()
                        try:
                            found = _duplicate_door_type(
                                doc, source, type_name,
                                dims[0], dims[1],
                                dimension_params=m_dim_params,
                            )
                            dup_t.Commit()
                            print(
                                "[PRE-SCAN]   '%s' -> duplicated: %s"
                                % (rt, found is not None)
                            )
                        except Exception as dup_ex:
                            print(
                                "[PRE-SCAN]   '%s' -> duplication error: %s"
                                % (rt, dup_ex)
                            )
                            if dup_t.HasStarted() and not dup_t.HasEnded():
                                dup_t.RollBack()
                    else:
                        print(
                            "[PRE-SCAN]   '%s' -> could not parse dims "
                            "from '%s'" % (rt, type_name)
                        )
                elif not source and not found:
                    print(
                        "[PRE-SCAN]   '%s' -> no source symbol for "
                        "family '%s'" % (rt, family_name)
                    )
            else:
                print("[PRE-SCAN]   '%s' -> invalid format (no ' : ')" % rt)
        symbol_cache[rt] = found
        print(
            "[PRE-SCAN]   symbol_cache['%s'] = %s"
            % (rt, "RESOLVED" if found is not None else "None (will use default)")
        )

    t = DB.Transaction(doc, f"Place Kreo {opening_type.title()}s")
    t.Start()
    try:
        _ensure_activated(doc, family_symbol)

        # Activate all pre-resolved symbols inside the transaction
        for sym_obj in symbol_cache.values():
            if sym_obj is not None:
                _ensure_activated(doc, sym_obj)

        for wall_list_idx, matches in matched_openings.items():
            if wall_list_idx >= len(wall_ids):
                logger.warning(
                    "Wall list index %d out of range (have %d wall_ids), skipping",
                    wall_list_idx, len(wall_ids),
                )
                continue

            # Look up host wall fresh from document
            # Revit 2025+: ElementId(long) requires explicit System.Int64
            # to avoid null ElementId from CPython3/pythonnet overload mismatch
            eid = DB.ElementId(System.Int64(int(wall_ids[wall_list_idx])))
            host_wall = doc.GetElement(eid)
            if host_wall is None:
                logger.warning(
                    "Wall ElementId %d not found in document, skipping %d openings",
                    wall_ids[wall_list_idx], len(matches),
                )
                continue

            for match in matches:
                ip = match.insertion_point

                # Resolve family symbol: per-opening override or default
                sym = family_symbol
                revit_type = getattr(match.opening, "revit_type", None)
                if revit_type:
                    # symbol_cache was pre-populated above
                    if revit_type not in symbol_cache:
                        found = find_family_symbol_by_name(doc, revit_type, category)
                        if found:
                            _ensure_activated(doc, found)
                        symbol_cache[revit_type] = found
                    cached = symbol_cache.get(revit_type)
                    if cached is not None:
                        sym = cached
                    print(
                        "[PLACE] %s %d: revit_type='%s' cached=%s -> '%s : %s'"
                        % (
                            opening_type,
                            match.opening.original_index,
                            revit_type,
                            cached is not None,
                            sym.Family.Name,
                            sym.Name,
                        )
                    )
                else:
                    print(
                        "[PLACE] %s %d: no revit_type -> default '%s : %s'"
                        % (
                            opening_type,
                            match.opening.original_index,
                            sym.Family.Name,
                            sym.Name,
                        )
                    )

                # Resolve sill height:
                #   1. Instance data from JSON (sill_height_in on opening)
                #   2. Manifest lookup by revit_type
                #   3. Global default (sill_height_ft param)
                actual_sill_ft = sill_height_ft
                opening_sill_in = getattr(
                    match.opening, "sill_height_in", None
                )
                if opening_sill_in is not None:
                    actual_sill_ft = float(opening_sill_in) / 12.0
                    print(
                        "[PLACE] %s %d: sill from JSON = %.1f in (%.3f ft)"
                        % (opening_type, match.opening.original_index,
                           opening_sill_in, actual_sill_ft)
                    )
                elif revit_type:
                    # Fallback: manifest lookup by family:type
                    parts_s = revit_type.split(" : ", 1)
                    if len(parts_s) == 2:
                        s_entry = manifest_families.get(
                            parts_s[0].strip(), {}
                        )
                        s_sill = s_entry.get("types", {}).get(
                            parts_s[1].strip(), {}
                        ).get("sill_height_in")
                        if s_sill is not None:
                            actual_sill_ft = float(s_sill) / 12.0
                            print(
                                "[PLACE] %s %d: sill from manifest = %.1f in "
                                "(%.3f ft)"
                                % (opening_type,
                                   match.opening.original_index,
                                   s_sill, actual_sill_ft)
                            )

                # Wall-hosted elements: point.Z is additive with Sill Height
                # parameter, so always use Z=0 and set sill via parameter.
                point = DB.XYZ(ip.x, ip.y, 0.0)

                # Apply placement offset for families like pocket doors
                # whose Revit origin is at the rough opening center,
                # not at the visible panel center detected by Kreo.
                family_name = sym.Family.Name
                m_fam = manifest_families.get(family_name, {})
                offset_in = m_fam.get("placement_offset_in", 0.0)
                if offset_in and host_wall is not None:
                    try:
                        loc_curve = host_wall.Location.Curve
                        wall_start = loc_curve.GetEndPoint(0)
                        wall_end = loc_curve.GetEndPoint(1)
                        wall_dir = DB.XYZ(
                            wall_end.X - wall_start.X,
                            wall_end.Y - wall_start.Y,
                            0.0,
                        ).Normalize()
                        # Offset toward whichever wall end has more
                        # length (room for the pocket cavity).
                        d_to_start = point.DistanceTo(wall_start)
                        d_to_end = point.DistanceTo(wall_end)
                        sign = 1.0 if d_to_start < d_to_end else -1.0
                        offset_ft = sign * offset_in / 12.0
                        point = DB.XYZ(
                            point.X + wall_dir.X * offset_ft,
                            point.Y + wall_dir.Y * offset_ft,
                            point.Z,
                        )
                        print(
                            "[PLACE] %s %d: offset %.1f in (%.3f ft) "
                            "along wall dir (sign=%.0f)"
                            % (opening_type, match.opening.original_index,
                               offset_in, offset_ft, sign)
                        )
                    except Exception as oe:
                        print(
                            "[PLACE] %s %d: offset failed: %s"
                            % (opening_type, match.opening.original_index, oe)
                        )

                instance = doc.Create.NewFamilyInstance(
                    point, sym, host_wall, level,
                    DB.Structure.StructuralType.NonStructural,
                )

                eid_int = _eid_int(instance.Id)

                created.append((opening_type, eid_int, actual_sill_ft))

        t.Commit()
        logger.info(
            "Placed %d %ss in Revit via ElementId lookup",
            len(created), opening_type,
        )
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise

    # Set sill heights in a separate transaction AFTER placement commits.
    # Revit may override instance parameter values during element creation,
    # so we explicitly set sill height post-creation for ALL instances
    # (including doors at 0.0 to override any family defaults).
    sill_entries = [(eid_int, sill_ft) for _, eid_int, sill_ft in created]
    if sill_entries:
        t2 = DB.Transaction(doc, "Set Sill Heights")
        t2.Start()
        try:
            for eid_int, sill_ft in sill_entries:
                elem = doc.GetElement(
                    DB.ElementId(System.Int64(int(eid_int)))
                )
                if elem is None:
                    continue

                sill_set = False

                sill_param = elem.get_Parameter(
                    DB.BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM
                )
                if sill_param and not sill_param.IsReadOnly:
                    sill_param.Set(sill_ft)
                    sill_set = True

                if not sill_set:
                    sill_param = elem.LookupParameter("Sill Height")
                    if sill_param and not sill_param.IsReadOnly:
                        sill_param.Set(sill_ft)
                        sill_set = True

                if sill_set:
                    print(
                        "[SILL] EID %d: sill = %.3f ft" % (eid_int, sill_ft)
                    )
                else:
                    print(
                        "[SILL] EID %d: WARNING - no writable sill param"
                        % eid_int
                    )

            t2.Commit()
            print("[SILL] Set sill heights on %d instances" % len(sill_entries))
        except Exception:
            if t2.HasStarted() and not t2.HasEnded():
                t2.RollBack()
            raise

    # Strip sill_ft from tuples for return value
    return [(typ, eid_int) for typ, eid_int, _ in created]


def _find_any_type_in_family(
    doc, family_name: str, category
) -> Optional[object]:
    """Find any FamilySymbol belonging to a given family name.

    Args:
        doc: Active Revit document.
        family_name: Revit family name (e.g., "Single-Flush").
        category: Revit BuiltInCategory (e.g., OST_Doors).

    Returns:
        First FamilySymbol found, or None.
    """
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB

    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(category)
        .OfClass(DB.FamilySymbol)
    )
    for symbol in collector:
        if symbol.Family.Name == family_name:
            return symbol
    return None


def _duplicate_door_type(
    doc, source_symbol, new_type_name: str,
    width_in: float, height_in: float,
    dimension_params: Optional[Dict[str, str]] = None,
) -> Optional[object]:
    """Duplicate a door FamilySymbol and set its dimensions.

    Must be called inside an active transaction.

    Uses manifest-provided ``dimension_params`` when available to determine
    the correct Revit parameter names for each family.  Falls back to
    hardcoded variants when no manifest data is supplied.

    Args:
        doc: Active Revit document.
        source_symbol: Existing FamilySymbol to duplicate from.
        new_type_name: Name for the new type (e.g., '36" x 80"').
        width_in: Door width in inches.
        height_in: Door height in inches.
        dimension_params: Optional dict from manifest with keys
            ``"width"`` and ``"height"`` mapping to Revit parameter names
            (e.g., ``{"width": "Door Panel Width", "height": "Door Panel Height"}``).

    Returns:
        New FamilySymbol, or None on failure.
    """
    # Build ordered lists of param names to try.
    # Manifest-specified param comes first, then generic fallbacks.
    FALLBACK_WIDTH = ["Width", "Rough Width"]
    FALLBACK_HEIGHT = ["Height", "Rough Height"]

    if dimension_params:
        manifest_w = dimension_params.get("width")
        manifest_h = dimension_params.get("height")
        width_params = (
            [manifest_w] + [p for p in FALLBACK_WIDTH if p != manifest_w]
            if manifest_w else FALLBACK_WIDTH
        )
        height_params = (
            [manifest_h] + [p for p in FALLBACK_HEIGHT if p != manifest_h]
            if manifest_h else FALLBACK_HEIGHT
        )
    else:
        width_params = FALLBACK_WIDTH
        height_params = FALLBACK_HEIGHT

    try:
        new_symbol = source_symbol.Duplicate(new_type_name)

        # Set width
        width_ft = width_in / 12.0
        width_set = False
        for param_name in width_params:
            width_param = new_symbol.LookupParameter(param_name)
            if width_param and not width_param.IsReadOnly:
                width_param.Set(width_ft)
                width_set = True
                print(
                    "  Set '%s' = %.4f ft (%.1f in) on '%s'"
                    % (param_name, width_ft, width_in, new_type_name)
                )
                break
        if not width_set:
            print(
                "  WARNING: No width param found on '%s' (tried: %s)"
                % (new_type_name, width_params)
            )

        # Set height
        height_ft = height_in / 12.0
        height_set = False
        for param_name in height_params:
            height_param = new_symbol.LookupParameter(param_name)
            if height_param and not height_param.IsReadOnly:
                height_param.Set(height_ft)
                height_set = True
                print(
                    "  Set '%s' = %.4f ft (%.1f in) on '%s'"
                    % (param_name, height_ft, height_in, new_type_name)
                )
                break
        if not height_set:
            print(
                "  WARNING: No height param found on '%s' (tried: %s)"
                % (new_type_name, height_params)
            )

        _ensure_activated(doc, new_symbol)
        return new_symbol
    except Exception as e:
        logger.warning(
            "Failed to duplicate type '%s': %s", new_type_name, e
        )
        return None


def _parse_type_dimensions(type_name: str) -> Optional[Tuple[float, float]]:
    """Parse width and height in inches from a type name string.

    Handles formats like:
        '36" x 80"'  -> (36.0, 80.0)
        "9' x 7'"    -> (108.0, 84.0)

    Args:
        type_name: Type name string (e.g., '36" x 80"').

    Returns:
        Tuple of (width_in, height_in), or None if parsing fails.
    """
    import re

    # Try inches format: 36" x 80"
    match = re.match(r'(\d+(?:\.\d+)?)"?\s*x\s*(\d+(?:\.\d+)?)"?', type_name)
    if match:
        return float(match.group(1)), float(match.group(2))

    # Try feet format: 9' x 7'
    match = re.match(r"(\d+(?:\.\d+)?)'\s*x\s*(\d+(?:\.\d+)?)'", type_name)
    if match:
        return float(match.group(1)) * 12.0, float(match.group(2)) * 12.0

    return None


def _load_family_from_manifest(doc, family_name: str) -> Optional[object]:
    """Try to load a door family from the families/ directory via manifest.

    Looks up the family name in families/manifest.json. If found under
    the 'doors' domain, loads the .rfa file into the Revit document using
    the existing revit_loader infrastructure.

    Args:
        doc: Active Revit document.
        family_name: Revit family name (e.g., "Sliding_Door_Pocket").

    Returns:
        Loaded Family object, or None if not found or load failed.
    """
    import json
    import os

    try:
        # Find the project root (where families/ lives)
        this_dir = os.path.dirname(os.path.abspath(__file__))
        # src/constructai_demo/ -> project root (up 2 levels)
        project_root = os.path.dirname(os.path.dirname(this_dir))
        manifest_path = os.path.join(project_root, "families", "manifest.json")

        if not os.path.exists(manifest_path):
            print("[MANIFEST] No manifest.json at %s" % manifest_path)
            return None

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        families = manifest.get("families", {})

        # Search manifest for the family name
        rfa_rel_path = None
        for manifest_name, entry in families.items():
            if manifest_name == family_name:
                rfa_rel_path = entry.get("file")
                break

        if not rfa_rel_path:
            print("[MANIFEST] '%s' not in manifest (keys: %s)"
                  % (family_name, list(families.keys())))
            return None

        rfa_abs_path = os.path.join(project_root, "families", rfa_rel_path)
        if not os.path.exists(rfa_abs_path):
            print("[MANIFEST] RFA not found: %s" % rfa_abs_path)
            return None

        # Use the existing revit_loader to load the family
        from src.timber_framing_generator.families.revit_loader import (
            load_family,
        )

        print("[MANIFEST] Loading '%s' from %s" % (family_name, rfa_abs_path))
        result = load_family(doc, rfa_abs_path)
        if result:
            print("[MANIFEST] Loaded OK (internal name='%s')"
                  % getattr(result, "Name", "???"))
        else:
            print("[MANIFEST] load_family() returned None!")
        return result

    except Exception as e:
        print("[MANIFEST] EXCEPTION loading '%s': %s" % (family_name, e))
        return None


def _ensure_activated(doc, symbol) -> None:
    """Activate a FamilySymbol if not already active."""
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
