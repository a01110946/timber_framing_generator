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
        
        # 4. Determine if the wall is exterior.
        wall_type = revit_wall.WallType
        wall_function_param = wall_type.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM)
        is_exterior_wall = wall_function_param and (wall_function_param.AsInteger() == 1)
        print(f"Wall {revit_wall.Id} is exterior: {is_exterior_wall}")

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
                rough_width_param = family_symbol.LookupParameter("Rough Width")
                rough_height_param = family_symbol.LookupParameter("Rough Height")
                print(f"Opening {insert_id} has rough width: {rough_width_param}")
                sill_height_param = insert_element.LookupParameter("Sill Height")
                print(f"Opening {insert_id} has sill height: {sill_height_param}")
                if rough_width_param and rough_height_param and sill_height_param:
                    opening_width_value = rough_width_param.AsDouble()
                    opening_height_value = rough_height_param.AsDouble()
                    sill_height_value = sill_height_param.AsDouble()
                    opening_location_point = insert_element.Location.Point
                    opening_location_point_rhino = rg.Point3d(
                        opening_location_point.X,
                        opening_location_point.Y,
                        opening_location_point.Z,
                    )
                    print(f"Opening {insert_id} has opening location point: {opening_location_point_rhino}")
                    try:
                        print(f"Opening {insert_id} has wall base curve: {wall_base_curve_rhino} and opening location point: {opening_location_point_rhino}")
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

                    print(f"Opening {insert_id} has t: {t}")
                    rough_width_half = opening_width_value / 2.0
                    print(f"Opening {insert_id} has rough width half: {rough_width_half}")
                    start_u_coordinate = t - rough_width_half if success else 0.0
                    print(f"Opening {insert_id} has start u coordinate: {start_u_coordinate}")

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
                    print(f"DEBUG: Sill height value from Revit: {sill_height_value}")
                    print(f"Opening {insert_id} has opening data: {opening_data}")
                    openings_data.append(opening_data)

        # 6. Get the wall's base plane using our helper.
        wall_base_plane = get_wall_base_plane(
            revit_wall, wall_base_curve_rhino, wall_base_elevation
        )
        print(f"Wall {revit_wall.Id} has base curve: {wall_base_curve_rhino} of type {type(wall_base_curve_rhino)}")
        print(f"Wall {revit_wall.Id} has base plane: {wall_base_plane}")
        if wall_base_plane is None:
            print(f"Failed to extract wall base plane from Revit wall: {revit_wall.Id}")
            return None

        # 7. Compute wall length and height.
        wall_length = curve_length(wall_base_curve_rhino)
        wall_height = wall_top_elevation - wall_base_elevation
        print(f"Wall {revit_wall.Id} has length: {wall_length} and height: {wall_height}")

        # 8. Decompose the wall into cells.
        cell_data_dict = decompose_wall_to_cells(
            wall_length=wall_length,
            wall_height=wall_height,
            opening_data_list=openings_data,
            base_plane=wall_base_plane,
        )
        cells_list = deconstruct_all_cells(cell_data_dict)
        print(f"Wall {revit_wall.Id} has cells: {cells_list}")

        # 9. Build and return the final wall data dictionary.
        wall_input_data_final: WallInputData = {
            "wall_type": wall_type.Name,
            "wall_base_curve": wall_base_curve_rhino,
            "wall_length": wall_length,
            "base_plane": wall_base_plane,
            "base_level": base_level,
            "base_offset": base_offset,
            "wall_base_elevation": wall_base_elevation,
            "top_level": top_level,
            "top_offset": top_offset,
            "wall_top_elevation": wall_top_elevation,
            "wall_height": wall_height,
            "is_exterior_wall": is_exterior_wall,
            "openings": openings_data,
            "cells": cells_list,
        }
        print(f"Wall {revit_wall.Id} has final data: {wall_input_data_final}")
        return wall_input_data_final
    except Exception as e:
        print(f"Failed to extract wall data from Revit wall: {revit_wall.Id}")
        print(f"Error: {str(e)}")
        return None
