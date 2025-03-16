# File: timber_framing_generator/framing_elements/location_data.py

# First, detect the environment and import appropriate modules
import sys
import os

# Check if we're running in Grasshopper/Rhino
is_rhino_environment = 'rhinoscriptsyntax' in sys.modules or 'Rhino' in sys.modules

# First, try to import our CI mocks
try:
    from src.timber_framing_generator.ci_mock import is_ci_environment

    # Only do regular imports if we're not in CI and not in Rhino
    if not is_ci_environment() and not is_rhino_environment:
        import rhinoinside
        rhinoinside.load()
        import Rhino.Geometry as rg
    else:
        # In CI or already in Rhino, we won't use rhinoinside
        import Rhino.Geometry as rg
except ImportError:
    # Fall back based on environment
    if not is_rhino_environment:
        # Only import rhinoinside if we're not already in Rhino
        import rhinoinside
        rhinoinside.load()
    
    # Import Rhino.Geometry directly if we're already in Rhino
    import Rhino.Geometry as rg

from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass


@dataclass
class WallCornerPoints:
    """
    Stores and validates wall corner points in a consistent order.

    The corner points are stored in this order:
    - bottom_left (0)  - bottom_right (1)
    - top_right (2)    - top_left (3)
    """

    bottom_left: rg.Point3d
    bottom_right: rg.Point3d
    top_right: rg.Point3d
    top_left: rg.Point3d

    @classmethod
    def from_corner_points(cls, points: List[rg.Point3d]) -> "WallCornerPoints":
        """
        Creates a WallCornerPoints instance from a list of points,
        validating the order and structure.

        Args:
            points: List of 4 corner points from the wall boundary cell

        Returns:
            WallCornerPoints instance with validated corner points

        Raises:
            ValueError: If points list doesn't contain exactly 4 points
            TypeError: If any point is not a Rhino.Geometry.Point3d
        """
        if len(points) != 4:
            raise ValueError(f"Expected 4 corner points, got {len(points)}")

        if not all(isinstance(p, rg.Point3d) for p in points):
            raise TypeError("All points must be Rhino.Geometry.Point3d objects")

        return cls(
            bottom_left=points[0],
            bottom_right=points[1],
            top_right=points[2],
            top_left=points[3],
        )


def get_plate_location_data(
    wall_data: Dict[str, Union[str, rg.Curve, float, bool, List, rg.Plane]],
    plate_type: str = "bottom_plate",
    representation_type: str = "structural",
) -> Dict[str, Union[rg.Curve, rg.Plane, float, str]]:
    """
    Extracts pure location data for plates without making geometry decisions.

    Args:
        wall_data: Dictionary containing wall information and cells
        plate_type: Type of plate to locate. Valid options are:
                   "bottom_plate", "top_plate", "cap_plate", "sole_plate"
        representation_type: How the plate should be represented. Valid options are:
                           "structural" (true center location) or
                           "schematic" (visual representation location)

    Returns:
        Dictionary containing:
            - reference_line: rg.Curve - The base line from wall geometry
            - base_plane: rg.Plane - The wall's base plane for orientation
            - reference_elevation: float - Elevation for positioning
            - wall_type: str - Original wall type name for reference
            - representation_type: str - The requested representation type

    Raises:
        ValueError: If wall boundary cell (WBC) is not found
        ValueError: If plate_type is not recognized
        ValueError: If representation_type is not "structural" or "schematic"
    """
    # Validate representation_type
    if representation_type not in ["structural", "schematic"]:
        raise ValueError(
            f"representation_type must be 'structural' or 'schematic', got '{representation_type}'"
        )

    # Find wall boundary cell
    wbc_cell = next(
        (cell for cell in wall_data["cells"] if cell["cell_type"] == "WBC"), None
    )
    if wbc_cell is None:
        raise ValueError("Wall Boundary Cell (WBC) not found in wall data")

    # Validate and organize corner points
    corner_points = WallCornerPoints.from_corner_points(wbc_cell["corner_points"])
    base_plane = wall_data["base_plane"]

    # Select points and elevation based on plate type
    if plate_type in ["bottom_plate", "sole_plate"]:
        start_point = corner_points.bottom_left
        end_point = corner_points.bottom_right
        reference_elevation = wall_data["wall_base_elevation"]
    elif plate_type in ["top_plate", "cap_plate"]:
        start_point = corner_points.top_left
        end_point = corner_points.top_right
        reference_elevation = wall_data["wall_top_elevation"]
    else:
        raise ValueError(
            f"plate_type must be one of: bottom_plate, sole_plate, top_plate, cap_plate. "
            f"Got: {plate_type}"
        )

    reference_line = rg.LineCurve(start_point, end_point)

    return {
        "reference_line": reference_line,
        "base_plane": base_plane,
        "reference_elevation": reference_elevation,
        "wall_type": wall_data["wall_type"],
        "representation_type": representation_type,  # Include this in the output
    }
