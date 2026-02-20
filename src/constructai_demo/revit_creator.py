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
            wall_class = classify_wall(wall.thickness_m)
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
        family_name = str(entry.get("family", "Single-Flush"))

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

    Strategy:
    1. Search by name containing "Generic" + approximate width
    2. Search by WallType.Width closest to target
    3. Fallback to first available WallType
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

    result: Dict[WallClass, object] = {}

    for wall_class in WallClass:
        target_ft = WALL_CLASS_THICKNESS_FT[wall_class]
        target_name = WALL_CLASS_NAMES[wall_class]

        # Strategy 1: Name match
        name_match = None
        for wt in all_types:
            try:
                if wt.Kind == DB.WallKind.Basic:
                    wt_name = wt.get_Parameter(
                        DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
                    )
                    if wt_name and "Generic" in str(wt_name.AsString()):
                        width = wt.Width  # feet
                        if abs(width - target_ft) < 0.05:  # within ~0.6"
                            name_match = wt
                            break
            except Exception:
                continue

        if name_match:
            result[wall_class] = name_match
            continue

        # Strategy 2: Closest width match among Basic wall types
        best_type = None
        best_diff = float("inf")
        for wt in all_types:
            try:
                if wt.Kind == DB.WallKind.Basic:
                    diff = abs(wt.Width - target_ft)
                    if diff < best_diff:
                        best_diff = diff
                        best_type = wt
            except Exception:
                continue

        if best_type:
            result[wall_class] = best_type

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

                loaded = _load_family_from_manifest(doc, family_name)
                if loaded:
                    loaded_name = getattr(loaded, "Name", "???")
                    print(
                        "[PRE-SCAN]   '%s' -> loaded family from manifest "
                        "(internal name='%s')" % (rt, loaded_name)
                    )
                    # Retry lookup after loading
                    found = find_family_symbol_by_name(doc, rt, category)
                    if found:
                        print("[PRE-SCAN]   '%s' -> found after manifest load" % rt)
                    if not found:
                        # Try collector-based lookup by family name
                        source = _find_any_type_in_family(
                            doc, family_name, category
                        )
                        # If internal name differs, retry with that
                        if not source and loaded_name != family_name:
                            print(
                                "[PRE-SCAN]   '%s' -> name mismatch! file='%s' "
                                "revit='%s', retrying..." % (rt, family_name, loaded_name)
                            )
                            source = _find_any_type_in_family(
                                doc, loaded_name, category
                            )
                        # Last resort: use Family.GetFamilySymbolIds() directly
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
                        if source:
                            print(
                                "[PRE-SCAN]   '%s' -> duplicating from '%s : %s'"
                                % (rt, source.Family.Name, source.Name)
                            )
                            # Prefer manifest type dims over parsing from name
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
                        else:
                            print(
                                "[PRE-SCAN]   '%s' -> no source symbol for "
                                "family '%s'" % (rt, family_name)
                            )
                else:
                    print(
                        "[PRE-SCAN]   '%s' -> manifest load FAILED for '%s'"
                        % (rt, family_name)
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
                point = DB.XYZ(ip.x, ip.y, 0.0)

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
                        "[PLACE] Door %d: revit_type='%s' cached=%s -> '%s : %s'"
                        % (
                            match.opening.original_index,
                            revit_type,
                            cached is not None,
                            sym.Family.Name,
                            sym.Name,
                        )
                    )
                else:
                    print(
                        "[PLACE] Door %d: no revit_type -> default '%s : %s'"
                        % (
                            match.opening.original_index,
                            sym.Family.Name,
                            sym.Name,
                        )
                    )

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
                            "[PLACE] Door %d: offset %.1f in (%.3f ft) "
                            "along wall dir (sign=%.0f)"
                            % (match.opening.original_index,
                               offset_in, offset_ft, sign)
                        )
                    except Exception as oe:
                        print(
                            "[PLACE] Door %d: offset failed: %s"
                            % (match.opening.original_index, oe)
                        )

                instance = doc.Create.NewFamilyInstance(
                    point, sym, host_wall, level,
                    DB.Structure.StructuralType.NonStructural,
                )

                # Set sill height (0 for doors, configurable for windows)
                sill_param = instance.get_Parameter(
                    DB.BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM
                )
                if sill_param and not sill_param.IsReadOnly:
                    sill_param.Set(sill_height_ft)

                # Extract ElementId as integer
                if hasattr(instance.Id, "IntegerValue"):
                    eid_int = instance.Id.IntegerValue
                elif hasattr(instance.Id, "Value"):
                    eid_int = instance.Id.Value
                else:
                    eid_int = int(str(instance.Id))

                created.append((opening_type, eid_int))

        t.Commit()
        logger.info(
            "Placed %d %ss in Revit via ElementId lookup",
            len(created), opening_type,
        )
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise

    return created


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
