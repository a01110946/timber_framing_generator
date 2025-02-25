# File: src/framing_elements/framing_geometry.py

import Rhino.Geometry as rg
from typing import Dict, Any

def create_stud_profile(
    base_point: rg.Point3d,
    base_plane: rg.Plane,
    stud_width: float,
    stud_depth: float
) -> rg.Rectangle3d:
    """
    Creates a rectangular profile for a stud element, centered on its reference point.
    
    This function creates a profile that:
    1. Is centered on the base_point
    2. Is oriented according to the base_plane
    3. Has dimensions specified by stud_width and stud_depth
    
    Args:
        base_point: Center point for the profile
        base_plane: Reference plane for orientation
        stud_width: Width of the stud (across the wall thickness)
        stud_depth: Depth of the stud (along the wall direction)
        
    Returns:
        A Rectangle3d representing the stud profile
    """
    # Create a profile plane where:
    # - XAxis goes into the wall (for width)
    # - YAxis goes along the wall (for depth)
    profile_plane = rg.Plane(
        base_point,
        base_plane.XAxis,  # Normal points into wall
        base_plane.YAxis   # Profile's up direction along wall
    )

    profile_rect = rg.Rectangle3d(
        profile_plane,
        rg.Interval(-stud_width/2, stud_width/2),  # Centered depth
        rg.Interval(-stud_depth/2, stud_depth/2)   # Centered width
    )
    
    # Create the rectangle with width going into wall, depth along wall
    return profile_rect