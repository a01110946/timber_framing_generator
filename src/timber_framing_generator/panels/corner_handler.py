# File: src/timber_framing_generator/panels/corner_handler.py
"""
Wall corner adjustment for accurate panel geometry.

Revit walls join at centerlines, but for panelization we need face-to-face
dimensions. This module detects corners and calculates the extend/recede
adjustments needed for accurate panel geometry.

Problem:
    Revit walls meet at their centerlines, creating:
    1. Overlap in the corner region
    2. Incorrect panel lengths if measured from centerline joins

Solution:
    - Wall A (Primary): Extends to outer face of Wall B
    - Wall B (Secondary): Recedes by Wall A's half-thickness

Example:
    >>> corners = detect_wall_corners(walls_data)
    >>> adjustments = calculate_corner_adjustments(corners, "longer_wall")
    >>> adjusted_wall = apply_corner_adjustments(wall_data, adjustments)
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math


@dataclass
class WallEndpoint:
    """Information about one end of a wall.

    Attributes:
        wall_id: ID of the wall
        position: "start" or "end"
        point: World XYZ coordinates of endpoint
        wall_length: Total wall length (feet)
        wall_thickness: Wall thickness (feet)
        direction: Unit vector along wall direction at this endpoint
    """
    wall_id: str
    position: str  # "start" or "end"
    point: Tuple[float, float, float]
    wall_length: float
    wall_thickness: float
    direction: Tuple[float, float, float]


@dataclass
class WallCornerInfo:
    """Information about a wall corner connection.

    Attributes:
        wall_id: ID of the wall at this corner
        corner_position: "start" or "end" of the wall
        corner_point: World XYZ of the corner
        connecting_wall_id: ID of the wall being connected to
        connecting_wall_thickness: Thickness of connecting wall (feet)
        angle: Angle between walls at corner (degrees)
        wall_length: Length of this wall (feet)
        wall_thickness: Thickness of this wall (feet)
    """
    wall_id: str
    corner_position: str
    corner_point: Tuple[float, float, float]
    connecting_wall_id: str
    connecting_wall_thickness: float
    angle: float
    wall_length: float
    wall_thickness: float


def _get_wall_endpoint(
    wall_data: Dict,
    position: str
) -> Tuple[float, float, float]:
    """Get endpoint coordinates from wall data.

    Args:
        wall_data: WallData dictionary
        position: "start" or "end"

    Returns:
        Tuple of (x, y, z) coordinates
    """
    if position == "start":
        pt = wall_data.get("base_curve_start", wall_data.get("base_plane", {}).get("origin", {}))
    else:
        pt = wall_data.get("base_curve_end", {})

    # Handle different formats
    if isinstance(pt, dict):
        return (pt.get("x", 0), pt.get("y", 0), pt.get("z", 0))
    elif hasattr(pt, "x"):
        return (pt.x, pt.y, pt.z)
    else:
        return (0, 0, 0)


def _get_wall_direction(wall_data: Dict) -> Tuple[float, float, float]:
    """Get wall direction vector from wall data.

    Args:
        wall_data: WallData dictionary

    Returns:
        Unit vector along wall direction
    """
    base_plane = wall_data.get("base_plane", {})
    x_axis = base_plane.get("x_axis", {})

    if isinstance(x_axis, dict):
        return (x_axis.get("x", 1), x_axis.get("y", 0), x_axis.get("z", 0))
    elif hasattr(x_axis, "x"):
        return (x_axis.x, x_axis.y, x_axis.z)
    else:
        return (1, 0, 0)


def _points_close(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    tolerance: float
) -> bool:
    """Check if two points are within tolerance distance.

    Args:
        p1: First point
        p2: Second point
        tolerance: Maximum distance to be considered close

    Returns:
        True if points are within tolerance
    """
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    dz = p1[2] - p2[2]
    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dist <= tolerance


def _calculate_angle_between_walls(
    dir1: Tuple[float, float, float],
    dir2: Tuple[float, float, float]
) -> float:
    """Calculate angle between two wall directions.

    Args:
        dir1: Direction vector of first wall
        dir2: Direction vector of second wall

    Returns:
        Angle in degrees (0-180)
    """
    # Dot product
    dot = dir1[0]*dir2[0] + dir1[1]*dir2[1] + dir1[2]*dir2[2]

    # Clamp to avoid numerical issues with acos
    dot = max(-1.0, min(1.0, dot))

    # Angle in degrees
    angle = math.degrees(math.acos(abs(dot)))

    return angle


def detect_wall_corners(
    walls_data: List[Dict],
    tolerance: float = 0.1
) -> List[WallCornerInfo]:
    """Detect corners where walls meet.

    Examines all wall endpoints and finds pairs that are close enough
    to be considered connected at a corner.

    Args:
        walls_data: List of WallData dictionaries
        tolerance: Distance tolerance for corner detection (feet)

    Returns:
        List of WallCornerInfo for each wall at each detected corner
    """
    corners = []

    # Build list of all endpoints
    endpoints: List[WallEndpoint] = []
    for wall in walls_data:
        wall_id = wall.get("wall_id", wall.get("id", "unknown"))
        wall_length = wall.get("wall_length", wall.get("length", 0))
        wall_thickness = wall.get("wall_thickness", wall.get("thickness", 0.5))
        direction = _get_wall_direction(wall)

        for position in ["start", "end"]:
            point = _get_wall_endpoint(wall, position)
            endpoints.append(WallEndpoint(
                wall_id=wall_id,
                position=position,
                point=point,
                wall_length=wall_length,
                wall_thickness=wall_thickness,
                direction=direction,
            ))

    # Find pairs of close endpoints (different walls)
    for i, ep1 in enumerate(endpoints):
        for j, ep2 in enumerate(endpoints):
            if i >= j:  # Avoid duplicates and self-comparison
                continue
            if ep1.wall_id == ep2.wall_id:  # Same wall
                continue

            if _points_close(ep1.point, ep2.point, tolerance):
                # Found a corner
                angle = _calculate_angle_between_walls(ep1.direction, ep2.direction)

                # Create corner info for wall 1
                corners.append(WallCornerInfo(
                    wall_id=ep1.wall_id,
                    corner_position=ep1.position,
                    corner_point=ep1.point,
                    connecting_wall_id=ep2.wall_id,
                    connecting_wall_thickness=ep2.wall_thickness,
                    angle=angle,
                    wall_length=ep1.wall_length,
                    wall_thickness=ep1.wall_thickness,
                ))

                # Create corner info for wall 2
                corners.append(WallCornerInfo(
                    wall_id=ep2.wall_id,
                    corner_position=ep2.position,
                    corner_point=ep2.point,
                    connecting_wall_id=ep1.wall_id,
                    connecting_wall_thickness=ep1.wall_thickness,
                    angle=angle,
                    wall_length=ep2.wall_length,
                    wall_thickness=ep2.wall_thickness,
                ))

    return corners


def _group_corners_by_location(
    corners: List[WallCornerInfo],
    tolerance: float = 0.1
) -> Dict[Tuple[float, float, float], List[WallCornerInfo]]:
    """Group corner infos by their location.

    Args:
        corners: List of WallCornerInfo
        tolerance: Distance tolerance for grouping

    Returns:
        Dictionary mapping corner points to list of WallCornerInfo at that corner
    """
    groups: Dict[Tuple[float, float, float], List[WallCornerInfo]] = {}

    for corner in corners:
        # Find existing group within tolerance
        found_group = None
        for group_point in groups:
            if _points_close(corner.corner_point, group_point, tolerance):
                found_group = group_point
                break

        if found_group:
            groups[found_group].append(corner)
        else:
            groups[corner.corner_point] = [corner]

    return groups


def calculate_corner_adjustments(
    corners: List[WallCornerInfo],
    priority: str = "longer_wall"
) -> List[Dict]:
    """Calculate extend/recede adjustments for each wall at corners.

    At each corner, one wall extends to cover the other wall's thickness,
    and the other wall recedes. The priority parameter determines which
    wall gets which treatment.

    Args:
        corners: Detected corner information
        priority: How to determine which wall extends:
            - "longer_wall": Longer wall extends (default)
            - "specified": Based on explicit specification (not implemented)
            - "alternate": Alternating pattern

    Returns:
        List of WallCornerAdjustment dictionaries
    """
    adjustments = []

    # Group corners by location
    corner_groups = _group_corners_by_location(corners)

    for corner_point, corner_walls in corner_groups.items():
        if len(corner_walls) != 2:
            # Skip complex intersections (3+ walls meeting)
            continue

        wall_a, wall_b = corner_walls

        # Determine which wall extends based on priority
        if priority == "longer_wall":
            if wall_a.wall_length >= wall_b.wall_length:
                primary, secondary = wall_a, wall_b
            else:
                primary, secondary = wall_b, wall_a
        elif priority == "alternate":
            # Use wall_id comparison for consistent alternating
            if wall_a.wall_id < wall_b.wall_id:
                primary, secondary = wall_a, wall_b
            else:
                primary, secondary = wall_b, wall_a
        else:
            # Default to wall_a
            primary, secondary = wall_a, wall_b

        # Primary wall extends by secondary wall's half-thickness
        # (to reach the outer face of secondary wall from centerline)
        adjustments.append({
            "wall_id": primary.wall_id,
            "corner_type": primary.corner_position,
            "adjustment_type": "extend",
            "adjustment_amount": secondary.wall_thickness / 2,
            "connecting_wall_id": secondary.wall_id,
            "connecting_wall_thickness": secondary.wall_thickness,
        })

        # Secondary wall recedes by primary wall's half-thickness
        adjustments.append({
            "wall_id": secondary.wall_id,
            "corner_type": secondary.corner_position,
            "adjustment_type": "recede",
            "adjustment_amount": primary.wall_thickness / 2,
            "connecting_wall_id": primary.wall_id,
            "connecting_wall_thickness": primary.wall_thickness,
        })

    return adjustments


def apply_corner_adjustments(
    wall_data: Dict,
    adjustments: List[Dict]
) -> Dict:
    """Apply corner adjustments to wall data.

    Creates a new wall_data dict with adjusted length and endpoints.
    The original wall data is not modified.

    Args:
        wall_data: Original WallData dictionary
        adjustments: Adjustments for this wall

    Returns:
        Modified wall_data with adjusted geometry
    """
    # Create a copy
    adjusted = dict(wall_data)

    wall_id = wall_data.get("wall_id", wall_data.get("id", ""))
    original_length = wall_data.get("wall_length", wall_data.get("length", 0))

    # Track total adjustments
    start_adjustment = 0.0
    end_adjustment = 0.0

    for adj in adjustments:
        if adj["wall_id"] != wall_id:
            continue

        amount = adj["adjustment_amount"]

        if adj["corner_type"] == "start":
            if adj["adjustment_type"] == "extend":
                start_adjustment -= amount  # Negative = move start backward
            else:  # recede
                start_adjustment += amount  # Positive = move start forward
        else:  # "end"
            if adj["adjustment_type"] == "extend":
                end_adjustment += amount  # Positive = move end forward
            else:  # recede
                end_adjustment -= amount  # Negative = move end backward

    # Calculate new length
    new_length = original_length - start_adjustment + end_adjustment

    # Update length in adjusted data
    if "wall_length" in adjusted:
        adjusted["wall_length"] = new_length
    if "length" in adjusted:
        adjusted["length"] = new_length

    # Adjust start point if needed
    if start_adjustment != 0:
        direction = _get_wall_direction(wall_data)
        start_pt = _get_wall_endpoint(wall_data, "start")

        new_start = (
            start_pt[0] + direction[0] * start_adjustment,
            start_pt[1] + direction[1] * start_adjustment,
            start_pt[2] + direction[2] * start_adjustment,
        )

        # Update base_curve_start
        if "base_curve_start" in adjusted:
            if isinstance(adjusted["base_curve_start"], dict):
                adjusted["base_curve_start"] = {
                    "x": new_start[0],
                    "y": new_start[1],
                    "z": new_start[2]
                }

        # Update base_plane origin
        if "base_plane" in adjusted and isinstance(adjusted["base_plane"], dict):
            if "origin" in adjusted["base_plane"]:
                adjusted["base_plane"]["origin"] = {
                    "x": new_start[0],
                    "y": new_start[1],
                    "z": new_start[2]
                }

    # Adjust end point if needed
    if end_adjustment != 0:
        direction = _get_wall_direction(wall_data)
        end_pt = _get_wall_endpoint(wall_data, "end")

        new_end = (
            end_pt[0] + direction[0] * end_adjustment,
            end_pt[1] + direction[1] * end_adjustment,
            end_pt[2] + direction[2] * end_adjustment,
        )

        # Update base_curve_end
        if "base_curve_end" in adjusted:
            if isinstance(adjusted["base_curve_end"], dict):
                adjusted["base_curve_end"] = {
                    "x": new_end[0],
                    "y": new_end[1],
                    "z": new_end[2]
                }

    # Store adjustment metadata
    if "metadata" not in adjusted:
        adjusted["metadata"] = {}
    adjusted["metadata"]["corner_adjustments"] = {
        "start_adjustment": start_adjustment,
        "end_adjustment": end_adjustment,
        "original_length": original_length,
        "adjusted_length": new_length,
    }

    return adjusted


def get_adjusted_wall_length(
    wall_data: Dict,
    adjustments: List[Dict]
) -> float:
    """Get the adjusted wall length after corner adjustments.

    Args:
        wall_data: Original WallData dictionary
        adjustments: List of adjustments to apply

    Returns:
        Adjusted wall length (feet)
    """
    wall_id = wall_data.get("wall_id", wall_data.get("id", ""))
    original_length = wall_data.get("wall_length", wall_data.get("length", 0))

    length_change = 0.0

    for adj in adjustments:
        if adj["wall_id"] != wall_id:
            continue

        if adj["adjustment_type"] == "extend":
            length_change += adj["adjustment_amount"]
        else:  # recede
            length_change -= adj["adjustment_amount"]

    return original_length + length_change
