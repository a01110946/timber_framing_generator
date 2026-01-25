# File: src/timber_framing_generator/mep/core/base.py
"""
Base MEP utilities and helper functions.

This module provides common utilities used across all MEP domains:
- Geometry helpers for route calculations
- Penetration size calculations
- Validation utilities
"""

from typing import Dict, List, Any, Tuple, Optional
import math


def calculate_penetration_size(
    pipe_diameter: float,
    clearance: float = 0.0208  # 1/4" = 0.0208 ft default clearance
) -> float:
    """
    Calculate penetration hole size for a pipe.

    Args:
        pipe_diameter: Pipe outer diameter in feet
        clearance: Additional clearance around pipe in feet

    Returns:
        Penetration hole diameter in feet
    """
    return pipe_diameter + (2 * clearance)


def check_penetration_allowed(
    hole_diameter: float,
    member_depth: float,
    max_ratio: float = 0.4,  # Code typically limits to 40% of depth
    edge_distance: float = None,  # Minimum distance from edges
) -> Tuple[bool, Optional[str]]:
    """
    Check if a penetration is allowed in a framing member.

    Args:
        hole_diameter: Proposed hole diameter in feet
        member_depth: Depth of framing member in feet
        max_ratio: Maximum allowed ratio of hole to member depth
        edge_distance: Minimum distance from member edges in feet

    Returns:
        Tuple of (is_allowed, reason_if_not_allowed)
    """
    ratio = hole_diameter / member_depth

    if ratio > max_ratio:
        return (
            False,
            f"Hole diameter ({hole_diameter*12:.2f}in) exceeds {max_ratio*100}% "
            f"of member depth ({member_depth*12:.2f}in)"
        )

    if edge_distance is not None:
        min_edge = (member_depth - hole_diameter) / 2
        if min_edge < edge_distance:
            return (
                False,
                f"Insufficient edge distance ({min_edge*12:.2f}in < {edge_distance*12:.2f}in)"
            )

    return (True, None)


def distance_3d(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float]
) -> float:
    """
    Calculate 3D distance between two points.

    Args:
        p1: First point (x, y, z)
        p2: Second point (x, y, z)

    Returns:
        Distance in same units as input
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dz = p2[2] - p1[2]
    return math.sqrt(dx**2 + dy**2 + dz**2)


def normalize_vector(
    v: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """
    Normalize a 3D vector to unit length.

    Args:
        v: Vector (x, y, z)

    Returns:
        Unit vector (x, y, z)
    """
    length = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if length < 1e-10:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def dot_product(
    v1: Tuple[float, float, float],
    v2: Tuple[float, float, float]
) -> float:
    """
    Calculate dot product of two 3D vectors.

    Args:
        v1: First vector (x, y, z)
        v2: Second vector (x, y, z)

    Returns:
        Dot product scalar
    """
    return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]


def find_nearest_wall_entry(
    connector_origin: Tuple[float, float, float],
    connector_direction: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
    max_distance: float = 10.0  # feet
) -> Optional[Dict[str, Any]]:
    """
    Find the nearest wall entry point from a connector.

    Args:
        connector_origin: Connector position (x, y, z)
        connector_direction: Connector direction vector
        walls: List of wall data dictionaries
        max_distance: Maximum search distance in feet

    Returns:
        Dictionary with wall entry information, or None if not found:
        - wall_id: ID of the nearest wall
        - entry_point: (x, y, z) point on wall face
        - distance: Distance from connector to entry
        - normal: Wall normal at entry point
    """
    # This is a placeholder - actual implementation will need
    # to intersect connector ray with wall geometry
    # For now, return None to indicate not implemented
    return None


def calculate_vertical_connection_point(
    entry_point: Tuple[float, float, float],
    wall_thickness: float,
    connector_system_type: str
) -> Tuple[float, float, float]:
    """
    Calculate the vertical connection point inside a wall.

    After entering a wall, pipes typically run vertically. This function
    calculates the point where the horizontal run meets the vertical.

    Args:
        entry_point: Point where pipe enters wall (x, y, z)
        wall_thickness: Wall thickness in feet
        connector_system_type: Type of system for offset rules

    Returns:
        Vertical connection point (x, y, z)
    """
    # For now, offset into wall by half thickness
    # Actual implementation would consider system type and code requirements
    offset = wall_thickness / 2

    # Return point at same location (actual direction depends on wall normal)
    return entry_point
