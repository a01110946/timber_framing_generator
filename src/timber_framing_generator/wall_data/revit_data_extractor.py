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


def _get_opening_dimension(element, symbol, param_names: List[str]) -> float:
    """
    Try multiple parameter names to get an opening dimension.

    Checks in order:
    1. Named parameters on instance
    2. Named parameters on symbol (type)

    Args:
        element: The FamilyInstance (door/window)
        symbol: The FamilySymbol (type)
        param_names: List of parameter names to try (e.g., ["Rough Width", "Width"])

    Returns:
        The dimension value, or 0.0 if not found
    """
    # Try instance parameters first
    for name in param_names:
        try:
            param = element.LookupParameter(name)
            if param and param.HasValue:
                value = param.AsDouble()
                if value > 0:
                    print(f"    Found {name} on instance: {value}")
                    return value
        except Exception as e:
            print(f"    Error reading instance param '{name}': {e}")

    # Try type (symbol) parameters
    for name in param_names:
        try:
            param = symbol.LookupParameter(name)
            if param and param.HasValue:
                value = param.AsDouble()
                if value > 0:
                    print(f"    Found {name} on type: {value}")
                    return value
        except Exception as e:
            print(f"    Error reading type param '{name}': {e}")

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
        print(f"Wall {revit_wall.Id} has {len(revit_wall.FindInserts(True, False, True, True))} openings")
        insert_ids = revit_wall.FindInserts(True, False, True, True)
        print(f"Wall {revit_wall.Id} has {len(insert_ids)} inserts")
        for insert_id in insert_ids:
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

                # Try multiple parameter names for width/height
                # Different Revit families use different names
                width_param_names = [
                    "Rough Width", "Width", "Default Width", "Frame Width",
                    "Opening Width", "Clear Width", "Nominal Width"
                ]
                height_param_names = [
                    "Rough Height", "Height", "Default Height", "Frame Height",
                    "Opening Height", "Clear Height", "Nominal Height"
                ]

                # Get dimensions using helper function with fallbacks
                opening_width_value = _get_opening_dimension(
                    insert_element, family_symbol, width_param_names
                )
                opening_height_value = _get_opening_dimension(
                    insert_element, family_symbol, height_param_names
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

                            # Use the Line to find the closest point
                            t = line.ClosestParameter(opening_location_point_rhino)

                            # Calculate the relative parameter on the curve (0-1)
                            t_normalized = t / wall_base_curve_rhino.GetLength()

                            success = True
                            t = t_normalized
                        else:
                            # Another approach: convert to NurbsCurve which should have ClosestPoint
                            nurbs_curve = wall_base_curve_rhino.ToNurbsCurve()
                            success, t = nurbs_curve.ClosestPoint(opening_location_point_rhino)

                    print(f"Opening {insert_id} has t (normalized 0-1): {t}")

                    # BUG FIX: t is a normalized parameter (0-1), not an absolute coordinate
                    # We need to convert it to absolute distance along the wall
                    # Use curve_length helper to handle LineCurve (no GetLength method)
                    wall_curve_length = curve_length(wall_base_curve_rhino)
                    opening_center_u = t * wall_curve_length  # Convert normalized to absolute
                    print(f"Opening {insert_id} - wall_curve_length: {wall_curve_length}, opening_center_u: {opening_center_u}")

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

                    # NEW CODE: Validate opening is within wall bounds
                    end_u_coordinate = start_u_coordinate + opening_width_value
                    if start_u_coordinate >= 0 and end_u_coordinate <= wall_curve_length:
                        openings_data.append(opening_data)
                    else:
                        print(f"WARNING: Skipping opening {insert_id} - outside wall bounds "
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
