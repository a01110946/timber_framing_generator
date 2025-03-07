import sys
import System
import Rhino
import Rhino.Geometry as rg
from typing import List, Dict, Union, Optional

# Revit API imports
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (
    Wall,
    XYZ,
    BuiltInParameter,
    BuiltInCategory,
    ElementId,
    FilteredElementCollector,
    FamilyInstance,
    Document,
)
import Autodesk.Revit.DB as DB
from Autodesk.Revit.UI import UIApplication

# Import your modules
from cell_decomposition import cell_segmentation
from wall_data import wall_input


# --- Helper Functions for Revit API Data Extraction ---


def get_wall_base_curve(wall: DB.Wall) -> rg.Curve:
    """Gets the base curve of a Revit wall as a Rhino curve."""
    location_curve = DB.LocationCurve
    curve = location_curve.Curve

    # Convert the Revit API curve to a Rhino NurbsCurve
    rhino_curve = curve.ToNurbsCurve()

    # Add the NurbsCurve to the Rhino document
    rhino_object = Rhino.RhinoDoc.ActiveDoc.Objects.AddCurve(rhino_curve)

    # Cast the Rhino object to a Rhino curve if needed
    if rhino_object:
        rhino_curve = rs.coercecurve(rhino_object)

    return rhino_curve


'''
def get_wall_base_elevation(wall: DB.Wall) -> float:
    """Gets the base elevation of a Revit wall."""
    base_level_id = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId()
    base_level = doc.GetElement(base_level_id)
    return base_level.Elevation

def get_wall_top_elevation(wall: DB.Wall) -> float:
    """Gets the top elevation of a Revit wall."""
    top_level_id = wall.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()
    top_level = doc.GetElement(top_level_id)
    return top_level.Elevation

def get_wall_function(wall: DB.Wall) -> str:
    """Gets the function of a Revit wall (e.g., 'Exterior', 'Interior')."""
    return wall.WallType.Function.ToString() # Returns "Exterior" or "Interior"

def get_wall_openings(wall: DB.Wall) -> List[DB.FamilyInstance]:
    """Gets the openings (doors and windows) associated with a Revit wall."""
    opening_ids = wall.FindInserts(True, False, False, False)
    openings = [doc.GetElement(id) for id in opening_ids if doc.GetElement(id) is not None]
    return openings

def get_opening_data(
    opening: DB.FamilyInstance, 
    wall_base_elevation: float
) -> Dict[str, Union[str, float]]:
    """
    Extracts data for a single opening (door or window).

    Args:
        opening (DB.FamilyInstance): The Revit FamilyInstance representing 
            the opening.
        wall_base_elevation (float): The base elevation of the wall the opening 
            is in.

    Returns:
        Dict[str, Union[str, float]]: A dictionary containing the opening data.
    """
    # Determine if it's a door or window
    if opening.Category.Id == ElementId(BuiltInCategory.OST_Doors):
        opening_type = "door"
    elif opening.Category.Id == ElementId(BuiltInCategory.OST_Windows):
        opening_type = "window"
    else:
        opening_type = "unknown"  # Handle cases where it's not a door or window

    # Get location point - for simplicity, use insertion point
    location = opening.Location.Point
    
    # Get the wall's base curve to calculate the U coordinate
    host_wall = opening.Host
    wall_location_curve = host_wall.Location as DB.LocationCurve
    wall_curve = wall_location_curve.Curve

    # Project location point onto wall curve to get U coordinate
    param = wall_curve.ClosestPoint(location, True)  # True to extend curve
    start_point = wall_curve.Evaluate(0, True)  # Get start point
    # Approximate U coordinate along the wall
    u_coordinate = location.DistanceTo(start_point)  

    # Get opening dimensions
    rough_width = opening.Symbol.get_Parameter(
        BuiltInParameter.FAMILY_ROUGH_WIDTH_PARAM
    ).AsDouble()
    rough_height = opening.Symbol.get_Parameter(
        BuiltInParameter.FAMILY_ROUGH_HEIGHT_PARAM
    ).AsDouble()

    # Calculate base elevation relative to wall base
    sill_height = opening.get_Parameter(
        BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM
    ).AsDouble()
    base_elevation_relative_to_wall_base = sill_height

    return {
        "opening_type": opening_type,
        "start_u_coordinate": u_coordinate,
        "rough_width": rough_width,
        "rough_height": rough_height,
        "base_elevation_relative_to_wall_base": base_elevation_relative_to_wall_base
    }
'''
