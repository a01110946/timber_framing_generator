# File: src/wall_data/revit_data_extractor.py

from typing import List, Dict, Union, Optional
from Autodesk.Revit import DB
import Rhino.Geometry as rg
from RhinoInside.Revit import Revit
import RhinoInside.Revit.Convert.Geometry as Geometry

from wall_data.wall_helpers import compute_wall_base_elevation, get_wall_base_curve, get_wall_base_plane
from cell_decomposition.cell_segmentation import decompose_wall_to_cells
from cell_decomposition.cell_types import deconstruct_all_cells

WallInputData = Dict[str, Union[rg.Curve, float, bool, List[Dict[str, Union[str, float]]], rg.Plane]]

def extract_wall_data_from_revit(revit_wall: DB.Wall, doc) -> WallInputData:
    """
    Extracts timber framing data from a Revit wall, decomposes the wall into cells,
    and returns a dictionary with wall geometry, openings, and cell data.
    """
    # 1. Compute the wall base curve.
    wall_base_curve_rhino = get_wall_base_curve(revit_wall)
    
    # 2. Compute the wall base elevation (using our helper).
    wall_base_elevation = compute_wall_base_elevation(revit_wall, doc)
    
    # 3. Get Base and Top Elevations:
    base_level_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT)
    base_offset_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET)
    top_level_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE)
    top_offset_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET)
    
    base_level = doc.GetElement(base_level_param.AsElementId()) if base_level_param and base_level_param.AsElementId() != DB.ElementId.InvalidElementId else None
    base_offset = base_offset_param.AsDouble() if base_offset_param else 0.0
    top_level = doc.GetElement(top_level_param.AsElementId()) if top_level_param and top_level_param.AsElementId() != DB.ElementId.InvalidElementId else None
    top_offset = top_offset_param.AsDouble() if top_offset_param else 0.0
    
    wall_top_elevation = (top_level.Elevation if top_level else wall_base_elevation + revit_wall.LookupParameter("Unconnected Height").AsDouble()) + top_offset

    # 4. Determine if the wall is exterior.
    wall_type = revit_wall.WallType
    wall_function_param = wall_type.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM)
    is_exterior_wall = wall_function_param and (wall_function_param.AsInteger() == 1)

    # 5. Get openings.
    openings_data: List[Dict[str, Union[str, float]]] = []
    insert_ids = revit_wall.FindInserts(True, False, True, True)
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

            family_symbol = insert_element.Symbol
            rough_width_param = family_symbol.LookupParameter("Rough Width")
            rough_height_param = family_symbol.LookupParameter("Rough Height")
            sill_height_param = insert_element.LookupParameter("Sill Height")
            if rough_width_param and rough_height_param and sill_height_param:
                opening_width_value = rough_width_param.AsDouble()
                opening_height_value = rough_height_param.AsDouble()
                sill_height_value = sill_height_param.AsDouble()
                opening_location_point = insert_element.Location.Point
                opening_location_point_rhino = rg.Point3d(opening_location_point.X, opening_location_point.Y, opening_location_point.Z)
                success, t = wall_base_curve_rhino.ClosestPoint(opening_location_point_rhino)
                rough_width_half = opening_width_value / 2.0
                start_u_coordinate = t - rough_width_half if success else 0.0

                opening_data = {
                    "opening_type": opening_type,
                    "opening_location_point": opening_location_point_rhino,
                    "start_u_coordinate": start_u_coordinate,
                    "rough_width": opening_width_value,
                    "rough_height": opening_height_value,
                    "base_elevation_relative_to_wall_base": sill_height_value - wall_base_elevation
                }
                openings_data.append(opening_data)
    
    # 6. Get the wall's base plane using our helper.
    wall_base_plane = get_wall_base_plane(revit_wall, wall_base_curve_rhino, wall_base_elevation)
    
    # 7. Compute wall length and height.
    wall_length = wall_base_curve_rhino.GetLength()
    wall_height = wall_top_elevation - wall_base_elevation

    # 8. Decompose the wall into cells.
    cell_data_dict = decompose_wall_to_cells(
        wall_length=wall_length,
        wall_height=wall_height,
        opening_data_list=openings_data,
        base_plane=wall_base_plane
    )
    cells_list = deconstruct_all_cells(cell_data_dict)

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
        "cells": cells_list
    }
    
    return wall_input_data_final
