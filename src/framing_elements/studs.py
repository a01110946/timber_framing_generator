# File: src/framing_elements/studs.py

import Rhino.Geometry as rg
from src.config.framing import FRAMING_PARAMS, PROFILES

def calculate_stud_locations(
    cell, 
    stud_spacing=0.6, 
    start_location=None, 
    remove_first=False, 
    remove_last=False
):
    """
    Calculates stud locations for a given wall cell (or segment) based on its base geometry.
    This intermediate step takes a cell (which should include a base line or a segment)
    and returns a list of points representing the locations for studs.
    
    Keyword Args:
        stud_spacing (float): Desired spacing between studs.
        start_location: Optional starting point (rg.Point3d) or parameter on the base geometry
                        where stud distribution should begin.
        remove_first (bool): If True, skip the first stud (to avoid collision with a king stud).
        remove_last (bool): If True, skip the last stud.
    
    Returns:
        list: A list of rg.Point3d objects representing stud locations.
    """
    # Assume the cell contains a key "base_line" with a Rhino.Geometry.Curve representing the stud area.
    base_line = cell.get("base_line")
    if not base_line or not isinstance(base_line, rg.Curve):
        raise ValueError("Cell must contain a valid 'base_line' (Rhino.Geometry.Curve) for stud placement.")
    
    # Determine the starting parameter. If start_location is given and is a point, get its parameter on the line.
    if start_location and isinstance(start_location, rg.Point3d):
        success, t0 = base_line.ClosestPoint(start_location)
    else:
        t0 = 0.0

    # Compute the total length of the base_line.
    length = base_line.GetLength()
    # Determine number of studs (using stud_spacing)
    num_intervals = int(length / stud_spacing)
    # Create stud locations uniformly along the line.
    stud_points = [base_line.PointAt(t0 + (i / float(num_intervals)) * length) for i in range(num_intervals + 1)]
    
    # Optionally remove the first and/or last stud.
    if remove_first and stud_points:
        stud_points = stud_points[1:]
    if remove_last and stud_points:
        stud_points = stud_points[:-1]
    
    return stud_points

def generate_stud(profile="2x4", stud_height=2.4, stud_thickness=None, stud_width=None):
    dimensions = PROFILES.get(profile, {})
    thickness = stud_thickness or dimensions.get("thickness", 0.04)
    width = stud_width or dimensions.get("width", 0.09)

    if thickness is None or width is None:
        raise ValueError("Explicit dimensions must be provided for custom profiles.")

    stud = {
        "type": "stud",
        "profile": profile,
        "thickness": thickness,
        "width": width,
        "height": stud_height,
        "geometry": "placeholder_for_geometry"
    }

    return stud