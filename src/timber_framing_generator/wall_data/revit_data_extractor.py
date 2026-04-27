# File: src/wall_data/revit_data_extractor.py

from typing import List, Dict, Union
import logging

from src.timber_framing_generator.utils.safe_rhino import safe_closest_point
from Autodesk.Revit import DB
import Rhino.Geometry as rg
import RhinoInside.Revit.Convert.Geometry as Geometry

from src.timber_framing_generator.wall_data.wall_helpers import (
    compute_wall_base_elevation,
    get_wall_base_curve,
    get_wall_base_plane,
)
from src.timber_framing_generator.cell_decomposition.cell_segmentation import decompose_wall_to_cells
from src.timber_framing_generator.cell_decomposition.cell_types import deconstruct_all_cells
from src.timber_framing_generator.utils.geometry_helpers import curve_length
from src.timber_framing_generator.utils.safe_rhino import safe_closest_point

logger = logging.getLogger(__name__)

WallInputData = Dict[
    str, Union[rg.Curve, float, bool, List[Dict[str, Union[str, float]]], rg.Plane]
]


def _get_opening_dimension(element, symbol, param_names: List[str], bip_list=None) -> float:
    """
    Try multiple approaches to get an opening dimension (width or height).

    Checks in order:
    1. BuiltInParameters on symbol (type) — most reliable for standard Revit families
    2. Named parameters on instance
    3. Named parameters on symbol (type)
    4. Diagnostic dump of all symbol params when all else fails

    Args:
        element: The FamilyInstance (door/window)
        symbol: The FamilySymbol (type)
        param_names: List of parameter names to try (e.g., ["Rough Width", "Width"])
        bip_list: Optional list of BuiltInParameter values to try first

    Returns:
        The dimension value in feet, or 0.0 if not found
    """
    # 1. Try BuiltInParameters on symbol (type) — standard Revit door/window families
    #    store their dimensions as BIPs, which are language-independent.
    if bip_list:
        for bip in bip_list:
            try:
                param = symbol.get_Parameter(bip)
                if param and param.HasValue:
                    value = param.AsDouble()
                    if value > 0:
                        print(f"    Found BIP {bip} on type: {value:.4f} ft")
                        return value
            except Exception:
                pass

    # 2. Try named parameters on instance
    for name in param_names:
        try:
            param = element.LookupParameter(name)
            if param and param.HasValue:
                value = param.AsDouble()
                if value > 0:
                    print(f"    Found '{name}' on instance: {value:.4f} ft")
                    return value
        except Exception as e:
            print(f"    Error reading instance param '{name}': {e}")

    # 3. Try named parameters on symbol (type)
    for name in param_names:
        try:
            param = symbol.LookupParameter(name)
            if param and param.HasValue:
                value = param.AsDouble()
                if value > 0:
                    print(f"    Found '{name}' on type: {value:.4f} ft")
                    return value
        except Exception as e:
            print(f"    Error reading type param '{name}': {e}")

    # 4. All methods failed — print available numeric params on the symbol for diagnosis
    print(f"    WARNING: dimension not found. Symbol numeric params (value > 0):")
    try:
        for p in symbol.Parameters:
            try:
                if p.HasValue:
                    v = p.AsDouble()
                    if v > 0:
                        print(f"      '{p.Definition.Name}' = {v:.4f} ft")
            except Exception:
                pass
    except Exception as e:
        print(f"      Cannot list symbol params: {e}")

    return 0.0

def extract_wall_data_from_revit(revit_wall: DB.Wall, doc) -> WallInputData:
    """
    Extracts timber framing data from a Revit wall, decomposes the wall into cells,
    and returns a dictionary with wall geometry, openings, and cell data.
    """
    try:
        print(f"Extracting wall data from Revit wall: {revit_wall.Id}")
        # 1. Compute the wall base curve.
        wall_base_curve_rhino = get_wall_base_curve(revit_wall)
        if wall_base_curve_rhino is None:
            print(f"Failed to extract wall base curve from Revit wall: {revit_wall.Id}")
            return None
        else:
            print(f"Wall base curve extracted successfully for Revit wall: {revit_wall.Id}")

        # 2. Compute the wall base elevation (using our helper).
        wall_base_elevation = compute_wall_base_elevation(revit_wall, doc)
        print(f"Wall base elevation computed: {wall_base_elevation}")
        print(f"Type of Wall base elevation computed: {type(wall_base_elevation)}")
        if wall_base_elevation is None:
            print(f"Failed to compute wall base elevation for Revit wall: {revit_wall.Id}")
            return None
        else:
            print(f"Wall base elevation computed successfully for Revit wall: {revit_wall.Id}")

        # 3. Get Base and Top Elevations:
        base_level_param = revit_wall.get_Parameter(
            DB.BuiltInParameter.WALL_BASE_CONSTRAINT
        )
        base_offset_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET)
        top_level_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE)
        top_offset_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET)
        if base_level_param is None or top_level_param is None:
            print(f"Failed to extract base or top level parameters from Revit wall: {revit_wall.Id}")
            return None
        else:
            print(f"Base and top level parameters extracted successfully for Revit wall: {revit_wall.Id}")

        # Get base level and offset (unchanged)
        base_level = (
            doc.GetElement(base_level_param.AsElementId())
            if base_level_param
            and base_level_param.AsElementId() != DB.ElementId.InvalidElementId
            else None
        )
        print(f"Base level computed: {base_level}")
        if base_level is None:
            print(f"Failed to extract base level from Revit wall: {revit_wall.Id}")
            return None
        base_offset = base_offset_param.AsDouble() if base_offset_param else 0.0
        print(f"Base offset computed: {base_offset}")

        # Get top level and offset - NEW CODE: Fallback to unconnected height
        top_level = (
            doc.GetElement(top_level_param.AsElementId())
            if top_level_param
            and top_level_param.AsElementId() != DB.ElementId.InvalidElementId
            else None
        )
        print(f"Top level computed: {top_level}")

        # Instead of returning None, use unconnected height if available
        if top_level is None:
            print(f"No top level constraint for wall: {revit_wall.Id}, checking unconnected height...")
            # Try to get the unconnected height parameter
            unconnected_height_param = revit_wall.LookupParameter("Unconnected Height")
            
            if unconnected_height_param and unconnected_height_param.HasValue:
                unconnected_height = unconnected_height_param.AsDouble()
                print(f"Using unconnected height: {unconnected_height}")
                wall_top_elevation = wall_base_elevation + unconnected_height
                print(f"Calculated top elevation from unconnected height: {wall_top_elevation}")
                # Continue processing with the calculated top elevation
                top_offset = 0.0  # No offset when using unconnected height
            else:
                print(f"No top level constraint or unconnected height found for wall: {revit_wall.Id}")
                return None
        else:
            # Original code for top level offset
            top_offset = top_offset_param.AsDouble() if top_offset_param else 0.0
            # Calculate wall_top_elevation
            wall_top_elevation = top_level.Elevation + top_offset

        # NOTE: "Top is Attached" walls have geometry cut by floors/roofs
        # but Revit's bounding box and solid geometry don't always reflect this accurately
        # For now, we use level-based elevation. A future improvement could check
        # the attached floor's bottom elevation directly.

        # 4. Determine if the wall is exterior.
        wall_type = revit_wall.WallType
        wall_function_param = wall_type.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM)
        is_exterior_wall = wall_function_param and (wall_function_param.AsInteger() == 1)

        # 4a. Get wall flip state.
        # When Flipped=True, the exterior face is on the negative Z-axis side
        # (opposite to the default cross(curve_direction, world_Z) direction).
        is_flipped = bool(revit_wall.Flipped)

        # 4a-ii. Store wall.Orientation as the geometric exterior normal.
        # wall.Orientation = cross(curve_tangent, world_Z) — purely geometric,
        # does NOT change when wall.Flipped=True.
        # The flip correction (negating when Flipped=True) is applied in the
        # Wall Analyzer GH component (gh_wall_analyzer.py) to avoid module
        # cache issues with this imported module.
        orientation = revit_wall.Orientation
        exterior_normal = {
            "x": float(orientation.X),
            "y": float(orientation.Y),
            "z": float(orientation.Z),
        }

        # 4b. Determine if the wall is load-bearing.
        # WALL_STRUCTURAL_USAGE_PARAM values:
        # 0 = Non-bearing, 1 = Bearing, 2 = Shear, 3 = Structural Combined
        structural_usage_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_USAGE_PARAM)
        is_load_bearing = False
        if structural_usage_param and structural_usage_param.HasValue:
            usage_value = structural_usage_param.AsInteger()
            # Values 1 (Bearing), 2 (Shear), 3 (Combined) are structural/load-bearing
            is_load_bearing = usage_value >= 1

        # 5. Get openings.
        openings_data: List[Dict[str, Union[str, float]]] = []

        # Helper: version-safe ElementId -> int
        def _eid_int_local(eid):
            if hasattr(eid, "Value"):
                return int(eid.Value)
            return int(eid.IntegerValue)

        _wall_id_int = _eid_int_local(revit_wall.Id)

        # --- DIAGNOSTIC BLOCK ---
        # Both old and new FindInserts signatures side-by-side so we can see
        # what each variant returns in the Rhino console.
        _fi_old = revit_wall.FindInserts(True, False, True, True)
        _fi_new = revit_wall.FindInserts(False, False, False, False)
        print(f"[DBG] Wall {_wall_id_int}:")
        print(f"  FindInserts(T,F,T,T) = {len(_fi_old)}  ids={[_eid_int_local(x) for x in _fi_old]}")
        print(f"  FindInserts(F,F,F,F) = {len(_fi_new)}  ids={[_eid_int_local(x) for x in _fi_new]}")

        # Total doors and windows in the document — collect once, reuse below
        _all_doors = []
        _all_wins = []
        try:
            _all_doors = list(
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Doors)
                .OfClass(DB.FamilyInstance)
                .ToElements()
            )
            _all_wins = list(
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Windows)
                .OfClass(DB.FamilyInstance)
                .ToElements()
            )
            print(f"  Doc totals: {len(_all_doors)} doors, {len(_all_wins)} windows")

            # For every door/window in the doc print: its id, host id, and
            # whether it matches this wall. This is the key diagnostic.
            for _e in _all_doors + _all_wins:
                try:
                    _cat = _e.Category.Name if _e.Category else "?"
                    _eid = _eid_int_local(_e.Id)
                    _host_obj = getattr(_e, "Host", None)
                    _host_id = _eid_int_local(_host_obj.Id) if _host_obj is not None else None
                    _match = (_host_id == _wall_id_int)
                    print(f"    {_cat} id={_eid}  host_id={_host_id}  wall_id={_wall_id_int}  match={_match}")
                except Exception as _pe:
                    print(f"    ERROR inspecting element: {_pe}")
        except Exception as _de:
            print(f"  Doc door/window scan ERROR: {_de}")
        # --- END DIAGNOSTIC BLOCK ---

        # Build final insert list: FindInserts(F,F,F,F) + Host.Id scan merged
        _seen_int_ids = set()
        _all_insert_ids = []
        for _id in _fi_new:
            _iv = _eid_int_local(_id)
            if _iv not in _seen_int_ids:
                _seen_int_ids.add(_iv)
                _all_insert_ids.append(_id)

        for _elem in _all_doors + _all_wins:
            try:
                _host_obj = getattr(_elem, "Host", None)
                if _host_obj is not None:
                    if _eid_int_local(_host_obj.Id) == _wall_id_int:
                        _ev = _eid_int_local(_elem.Id)
                        if _ev not in _seen_int_ids:
                            _seen_int_ids.add(_ev)
                            _all_insert_ids.append(_elem.Id)
            except Exception:
                pass

        print(f"  Total inserts to process for wall {_wall_id_int}: {len(_all_insert_ids)}")
        for insert_id in _all_insert_ids:
            insert_element = revit_wall.Document.GetElement(insert_id)
            if isinstance(insert_element, DB.FamilyInstance):
                if not (insert_element.Category and insert_element.Category.Name):
                    continue
                category_name = insert_element.Category.Name
                if category_name == "Doors":
                    opening_type = "door"
                elif category_name == "Windows":
                    opening_type = "window"
                else:
                    continue
                print(f"Opening {insert_id} is {opening_type}")

                family_symbol = insert_element.Symbol

                # BuiltInParameters to try first — language-independent, work for
                # standard Revit door/window families regardless of template locale.
                width_bips = [
                    DB.BuiltInParameter.DOOR_WIDTH,          # doors (type param)
                    DB.BuiltInParameter.FAMILY_WIDTH_PARAM,  # generic family width (type)
                ]
                height_bips = [
                    DB.BuiltInParameter.DOOR_HEIGHT,          # doors (type param)
                    DB.BuiltInParameter.FAMILY_HEIGHT_PARAM,  # generic family height (type)
                ]

                # Named-parameter fallbacks for non-standard/custom families.
                width_param_names = [
                    "Rough Width", "Width", "Default Width", "Frame Width",
                    "Opening Width", "Clear Width", "Nominal Width"
                ]
                height_param_names = [
                    "Rough Height", "Height", "Default Height", "Frame Height",
                    "Opening Height", "Clear Height", "Nominal Height"
                ]

                # Get dimensions: BIPs first, then named params, then diagnostic dump
                opening_width_value = _get_opening_dimension(
                    insert_element, family_symbol, width_param_names, bip_list=width_bips
                )
                opening_height_value = _get_opening_dimension(
                    insert_element, family_symbol, height_param_names, bip_list=height_bips
                )

                print(f"Opening {insert_id} - width={opening_width_value}, height={opening_height_value}")

                # If standard parameters failed, try to get dimensions from the opening cut
                if opening_width_value <= 0 or opening_height_value <= 0:
                    print(f"  WARNING: Could not find dimensions via parameters, trying opening cut...")
                    try:
                        # Get the opening cut from the wall
                        opening_cut = insert_element.GetSubComponentIds()
                        bbox = insert_element.get_BoundingBox(None)
                        if bbox:
                            # Use bounding box as fallback (less accurate but better than nothing)
                            if opening_width_value <= 0:
                                # Width is typically along X or Y depending on wall orientation
                                dx = abs(bbox.Max.X - bbox.Min.X)
                                dy = abs(bbox.Max.Y - bbox.Min.Y)
                                opening_width_value = max(dx, dy)  # Use larger dimension as width
                            if opening_height_value <= 0:
                                opening_height_value = abs(bbox.Max.Z - bbox.Min.Z)
                            print(f"  Using bounding box fallback: width={opening_width_value}, height={opening_height_value}")
                    except Exception as bbox_err:
                        print(f"  Failed to get bounding box: {bbox_err}")

                # Get sill height parameter
                sill_height_param = insert_element.LookupParameter("Sill Height")
                sill_height_builtin = None
                try:
                    sill_height_builtin = insert_element.get_Parameter(DB.BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)
                    if sill_height_builtin:
                        print(f"  Built-in INSTANCE_SILL_HEIGHT_PARAM value: {sill_height_builtin.AsDouble()}")
                except Exception as e:
                    print(f"  Could not get INSTANCE_SILL_HEIGHT_PARAM: {e}")

                # Get sill height value (raw)
                sill_height_value_raw = 0.0
                try:
                    if sill_height_builtin and sill_height_builtin.HasValue:
                        sill_height_value_raw = sill_height_builtin.AsDouble()
                    elif sill_height_param and sill_height_param.HasValue:
                        sill_height_value_raw = sill_height_param.AsDouble()
                except Exception as e:
                    print(f"  Error getting sill height: {e}")

                # Only process if we have valid dimensions
                if opening_width_value > 0 and opening_height_value > 0:

                    opening_location_point = insert_element.Location.Point
                    opening_location_point_rhino = rg.Point3d(
                        opening_location_point.X,
                        opening_location_point.Y,
                        opening_location_point.Z,
                    )

                    # FIX: Use built-in parameter as primary source, it's more reliable
                    # The INSTANCE_SILL_HEIGHT_PARAM is specifically designed for this purpose
                    sill_height_value = None

                    if sill_height_builtin and sill_height_builtin.HasValue:
                        sill_height_value = sill_height_builtin.AsDouble()
                    elif sill_height_param and sill_height_param.HasValue:
                        sill_height_value = sill_height_value_raw

                    # If parameter values are negative or None, calculate from geometry
                    # Calculate sill as: opening_bottom_Z - wall_base_elevation
                    # where opening_bottom_Z = opening_center_Z - half_height
                    # BUT: Some families have location point at sill, some at center
                    # We need to detect which case we're in

                    # Calculate what sill would be if location point is at CENTER
                    sill_from_center = opening_location_point.Z - (opening_height_value / 2.0) - wall_base_elevation
                    # Calculate what sill would be if location point is at SILL
                    sill_from_sill_point = opening_location_point.Z - wall_base_elevation

                    # If we got a parameter value, use it but validate
                    if sill_height_value is not None and sill_height_value >= 0:
                        # Check if calculated values are close to parameter
                        # This helps verify the parameter is correct
                        diff_from_center = abs(sill_height_value - sill_from_center)
                        diff_from_sill = abs(sill_height_value - sill_from_sill_point)

                        # If parameter doesn't match either calculation within tolerance,
                        # prefer the sill-point calculation (more common in Revit families)
                        if diff_from_center > 1.0 and diff_from_sill > 1.0:
                            sill_height_value = sill_from_sill_point
                    else:
                        # No valid parameter, use sill-point calculation
                        # (assumes location point is at sill, which is common)
                        sill_height_value = sill_from_sill_point

                    # Final sanity check: sill should be >= 0 and < wall_height
                    wall_height = wall_top_elevation - wall_base_elevation
                    if sill_height_value < 0:
                        sill_height_value = 0.0
                    elif sill_height_value >= wall_height:
                        sill_height_value = wall_height - opening_height_value

                    try:
                        # Try to use ClosestPoint directly if available
                        success, t = safe_closest_point(wall_base_curve_rhino, opening_location_point_rhino)
                    except AttributeError:
                        # Fallback for LineCurve
                        if isinstance(wall_base_curve_rhino, rg.LineCurve):
                            # Get the underlying Line
                            line = wall_base_curve_rhino.Line

                            # ClosestParameter on a Line returns arc-length in feet
                            # (same coordinate system as LineCurve domain [0, L]).
                            t = line.ClosestParameter(opening_location_point_rhino)

                            success = True
                        else:
                            # Another approach: convert to NurbsCurve which should have ClosestPoint
                            nurbs_curve = wall_base_curve_rhino.ToNurbsCurve()
                            success, t = nurbs_curve.ClosestPoint(opening_location_point_rhino)

                    # Normalize t to [0, 1] from the curve's own domain, so this
                    # works whether the underlying API returns arc-length
                    # (LineCurve.Line.ClosestParameter → domain [0, L]) or a
                    # pre-normalized parameter (some Curve.ClosestPoint paths).
                    domain = wall_base_curve_rhino.Domain
                    domain_length = domain.T1 - domain.T0
                    t_normalized = (
                        (t - domain.T0) / domain_length
                        if domain_length > 1e-9 else 0.0
                    )
                    wall_curve_length = curve_length(wall_base_curve_rhino)
                    opening_center_u = t_normalized * wall_curve_length
                    print(f"Opening {insert_id} centered at u={opening_center_u:.3f} "
                          f"(t={t:.4f}, t_norm={t_normalized:.4f}, "
                          f"wall_length={wall_curve_length:.3f})")

                    rough_width_half = opening_width_value / 2.0
                    start_u_coordinate = opening_center_u - rough_width_half if success else 0.0

                    # Note: Revit's "Sill Height" parameter is the height above the floor level,
                    # which is the same as relative to wall base (since wall is on that level).
                    # No need to subtract wall_base_elevation - it's already relative.
                    opening_data = {
                        "opening_type": opening_type,
                        "opening_location_point": opening_location_point_rhino,
                        "start_u_coordinate": start_u_coordinate,
                        "rough_width": opening_width_value,
                        "rough_height": opening_height_value,
                        "base_elevation_relative_to_wall_base": sill_height_value,
                    }

                    # Clamp opening to wall bounds rather than rejecting it.
                    # Doors/windows near wall ends have center_u within the wall,
                    # but start_u = center_u - half_width can be slightly < 0.
                    end_u_coordinate = start_u_coordinate + opening_width_value
                    start_u_clamped = max(0.0, start_u_coordinate)
                    end_u_clamped = min(wall_curve_length, end_u_coordinate)

                    if end_u_clamped > start_u_clamped + 0.01:
                        if start_u_clamped != start_u_coordinate:
                            print(f"Note: Opening {insert_id} u_start clamped "
                                  f"{start_u_coordinate:.3f} -> {start_u_clamped:.3f}")
                        opening_data["start_u_coordinate"] = start_u_clamped
                        openings_data.append(opening_data)
                    else:
                        print(f"WARNING: Skipping opening {insert_id} - entirely outside wall "
                              f"(u={start_u_coordinate:.2f} to {end_u_coordinate:.2f}, "
                              f"wall_length={wall_curve_length:.2f})")
                else:
                    print(f"WARNING: Skipping opening {insert_id} - invalid dimensions (width={opening_width_value}, height={opening_height_value})")

        # 6. Get the wall's base plane using our helper.
        wall_base_plane = get_wall_base_plane(
            revit_wall, wall_base_curve_rhino, wall_base_elevation
        )
        if wall_base_plane is None:
            return None

        # 7. Compute wall length and height.
        wall_length = curve_length(wall_base_curve_rhino)
        wall_height = wall_top_elevation - wall_base_elevation

        # 7b. Get wall thickness from wall type
        wall_thickness = wall_type.Width  # In Revit internal units (feet)
        print(f"Wall thickness from WallType.Width: {wall_thickness} ft ({wall_thickness * 12:.2f} inches)")

        # 7c. Extract CompoundStructure for multi-layer assembly data.
        wall_assembly_dict = None
        try:
            from src.timber_framing_generator.wall_data.assembly_extractor import (
                extract_compound_structure,
            )
            wall_assembly_dict = extract_compound_structure(wall_type, doc)
            if wall_assembly_dict:
                layer_count = len(wall_assembly_dict.get("layers", []))
                print(f"Extracted CompoundStructure: {layer_count} layers from {wall_type.Name}")
            else:
                print(f"No CompoundStructure available for {wall_type.Name}, using defaults")
        except Exception as cs_err:
            print(f"CompoundStructure extraction failed: {cs_err}")

        # 8. Decompose the wall into cells.
        cell_data_dict = decompose_wall_to_cells(
            wall_length=wall_length,
            wall_height=wall_height,
            opening_data_list=openings_data,
            base_plane=wall_base_plane,
        )
        cells_list = deconstruct_all_cells(cell_data_dict)

        # 9. Build and return the final wall data dictionary.
        wall_input_data_final: WallInputData = {
            "wall_type": wall_type.Name,
            "wall_base_curve": wall_base_curve_rhino,
            "wall_length": wall_length,
            "wall_thickness": wall_thickness,  # For CFS profile selection
            "base_plane": wall_base_plane,
            "base_level": base_level,
            "base_offset": base_offset,
            "wall_base_elevation": wall_base_elevation,
            "top_level": top_level,
            "top_offset": top_offset,
            "wall_top_elevation": wall_top_elevation,
            "wall_height": wall_height,
            "is_exterior_wall": is_exterior_wall,
            "is_flipped": is_flipped,
            "exterior_normal": exterior_normal,
            "is_load_bearing": is_load_bearing,
            "wall_assembly": wall_assembly_dict,
            "openings": openings_data,
            "cells": cells_list,
        }
        return wall_input_data_final
    except Exception as e:
        print(f"Failed to extract wall data from Revit wall: {revit_wall.Id}")
        print(f"Error: {str(e)}")
        return None
