# File: src/timber_framing_generator/mep/plumbing/penetration_rules.py
"""
Plumbing penetration rules and generation.

This module handles penetration specifications for pipes passing
through wall framing members. It includes:

- Penetration sizing with clearance
- Code compliance checks (max hole diameter ratios)
- Reinforcement requirements
- Standard pipe sizes

The rules follow typical residential framing codes which limit
penetrations to 40% of member depth without reinforcement.
"""

from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
import logging

from src.timber_framing_generator.core.mep_system import MEPRoute
from src.timber_framing_generator.mep.core.base import (
    calculate_penetration_size,
    check_penetration_allowed,
    distance_3d,
)

logger = logging.getLogger(__name__)


# Standard plumbing pipe sizes (nominal → outer diameter in feet)
STANDARD_PIPE_SIZES = {
    "1/2": 0.0729,   # 0.875" OD
    "3/4": 0.0875,   # 1.05" OD
    "1": 0.1104,     # 1.325" OD
    "1-1/4": 0.1396, # 1.675" OD
    "1-1/2": 0.1583, # 1.9" OD
    "2": 0.1979,     # 2.375" OD
    "3": 0.2917,     # 3.5" OD
    "4": 0.375,      # 4.5" OD
}

# Default clearance around pipes
PLUMBING_PENETRATION_CLEARANCE = 0.0208  # 1/4" = 0.0208 ft

# Maximum penetration ratio (hole diameter / member depth)
MAX_PENETRATION_RATIO = 0.40  # 40% - typical code limit

# Reinforcement threshold (above this ratio, reinforcement required)
REINFORCEMENT_THRESHOLD = 0.33  # 33%


@dataclass
class PipeSize:
    """Standard plumbing pipe size information."""
    nominal_size: str  # e.g., "1/2", "3/4", "1", "1-1/2", "2", "3", "4"
    outer_diameter: float  # feet

    @classmethod
    def from_diameter(cls, diameter_ft: float) -> "PipeSize":
        """
        Infer nominal size from pipe diameter.

        Args:
            diameter_ft: Pipe outer diameter in feet

        Returns:
            PipeSize with matching nominal size
        """
        # Find closest matching size
        best_match = None
        best_diff = float('inf')

        for nominal, od in STANDARD_PIPE_SIZES.items():
            diff = abs(od - diameter_ft)
            if diff < best_diff:
                best_diff = diff
                best_match = nominal

        if best_match:
            return cls(best_match, STANDARD_PIPE_SIZES[best_match])

        # No match found, use actual diameter
        return cls("custom", diameter_ft)


def generate_plumbing_penetrations(
    routes: List[MEPRoute],
    framing_elements: List[Any]
) -> List[Dict[str, Any]]:
    """
    Generate penetration specifications for pipes through framing.

    For each route segment that passes through a stud or other
    vertical framing member, creates a penetration specification.

    Args:
        routes: Calculated MEP routes with path points
        framing_elements: List of framing element dictionaries

    Returns:
        List of penetration specifications:
            - id: Unique penetration ID
            - route_id: ID of route this penetration serves
            - element_id: ID of framing element to penetrate
            - element_type: Type of element (stud, header, etc.)
            - location: {x, y, z} center of penetration
            - diameter: Hole diameter (pipe size + clearance)
            - pipe_size: Actual pipe diameter
            - system_type: Plumbing system type
            - is_allowed: Whether penetration meets code limits
            - warning: Description if not allowed
            - reinforcement_required: Whether reinforcement is needed
    """
    penetrations = []

    # Convert framing elements to searchable format
    studs = _filter_vertical_elements(framing_elements)

    for route in routes:
        route_penetrations = _process_route_penetrations(route, studs)
        penetrations.extend(route_penetrations)

    logger.info(f"Generated {len(penetrations)} penetrations for {len(routes)} routes")
    return penetrations


def _filter_vertical_elements(
    framing_elements: List[Any]
) -> List[Dict[str, Any]]:
    """
    Filter framing elements to only vertical members.

    Penetrations are typically through:
    - Studs
    - King studs
    - Trimmers
    - Cripple studs

    Args:
        framing_elements: All framing elements

    Returns:
        List of vertical elements (studs and similar)
    """
    vertical_types = {
        "stud", "king_stud", "trimmer",
        "header_cripple", "sill_cripple",
        "cripple_stud"
    }

    vertical = []

    for elem in framing_elements:
        # Handle dict format
        if isinstance(elem, dict):
            elem_type = elem.get("element_type", "").lower()
            if elem_type in vertical_types:
                vertical.append(elem)
        # Handle object format
        elif hasattr(elem, "element_type"):
            elem_type = str(getattr(elem, "element_type", "")).lower()
            if elem_type in vertical_types:
                vertical.append(elem)

    return vertical


def _process_route_penetrations(
    route: MEPRoute,
    studs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate penetrations for a single route.

    Args:
        route: MEP route with path points
        studs: List of stud elements

    Returns:
        List of penetration specifications
    """
    penetrations = []

    if len(route.path_points) < 2:
        return penetrations

    # Get pipe size
    pipe_diameter = route.pipe_size or 0.0833  # Default 1" pipe

    # Check each segment of the route
    for i in range(len(route.path_points) - 1):
        p1 = route.path_points[i]
        p2 = route.path_points[i + 1]

        # Find studs that this segment crosses
        crossed_studs = _find_crossed_studs(p1, p2, studs)

        for stud in crossed_studs:
            penetration = _create_penetration(
                route,
                stud,
                p1,
                p2,
                pipe_diameter
            )
            if penetration:
                penetrations.append(penetration)

    return penetrations


def _find_crossed_studs(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    studs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Find studs that a line segment crosses.

    A stud is crossed if the segment intersects the stud's
    horizontal extent (U position ± half width).

    Args:
        p1: Segment start point
        p2: Segment end point
        studs: List of stud elements

    Returns:
        List of studs crossed by the segment
    """
    crossed = []

    for stud in studs:
        if _segment_crosses_stud(p1, p2, stud):
            crossed.append(stud)

    return crossed


def _segment_crosses_stud(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    stud: Dict[str, Any]
) -> bool:
    """
    Check if a segment crosses through a stud.

    Uses the stud's centerline and width to determine crossing.

    Args:
        p1: Segment start point
        p2: Segment end point
        stud: Stud element dictionary

    Returns:
        True if segment crosses stud
    """
    # Get stud centerline
    centerline = stud.get("centerline", {})
    start = centerline.get("start", stud.get("centerline_start", {}))
    end = centerline.get("end", stud.get("centerline_end", {}))

    if not start or not end:
        return False

    # Get stud X position (simplified - assumes studs are vertical)
    stud_x = start.get("x", 0)
    stud_y = start.get("y", 0)

    # Get stud width (half on each side of centerline)
    profile = stud.get("profile", {})
    stud_width = profile.get("width", 0.125)  # Default 1.5"
    half_width = stud_width / 2

    # Check if segment crosses stud's X range
    min_x = min(p1[0], p2[0])
    max_x = max(p1[0], p2[0])

    stud_min_x = stud_x - half_width
    stud_max_x = stud_x + half_width

    # X axis crossing
    x_crosses = (min_x <= stud_max_x) and (max_x >= stud_min_x)

    # Also check Y for walls not aligned with X
    min_y = min(p1[1], p2[1])
    max_y = max(p1[1], p2[1])

    stud_min_y = stud_y - half_width
    stud_max_y = stud_y + half_width

    y_crosses = (min_y <= stud_max_y) and (max_y >= stud_min_y)

    # Check vertical range
    stud_z_start = start.get("z", 0)
    stud_z_end = end.get("z", 10)

    min_z = min(p1[2], p2[2])
    max_z = max(p1[2], p2[2])

    z_in_range = (min_z <= stud_z_end) and (max_z >= stud_z_start)

    return (x_crosses or y_crosses) and z_in_range


def _create_penetration(
    route: MEPRoute,
    stud: Dict[str, Any],
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    pipe_diameter: float
) -> Optional[Dict[str, Any]]:
    """
    Create a penetration specification for a pipe through a stud.

    Args:
        route: The MEP route
        stud: The stud being penetrated
        p1: Segment start point
        p2: Segment end point
        pipe_diameter: Pipe outer diameter

    Returns:
        Penetration specification dictionary
    """
    stud_id = stud.get("id", stud.get("element_id", "unknown"))
    elem_type = stud.get("element_type", "stud")

    # Calculate penetration center (intersection with stud centerline)
    centerline = stud.get("centerline", {})
    start = centerline.get("start", stud.get("centerline_start", {}))

    # Use stud position for penetration center X/Y
    center_x = start.get("x", (p1[0] + p2[0]) / 2)
    center_y = start.get("y", (p1[1] + p2[1]) / 2)

    # Z at the horizontal run level
    center_z = p1[2]  # Use segment start Z

    center = (center_x, center_y, center_z)

    # Calculate penetration size with clearance
    hole_diameter = calculate_penetration_size(
        pipe_diameter,
        PLUMBING_PENETRATION_CLEARANCE
    )

    # Get stud depth for code check
    profile = stud.get("profile", {})
    stud_depth = profile.get("depth", 0.292)  # Default 3.5"

    # Check if penetration is allowed
    is_allowed, warning = check_penetration_allowed(
        hole_diameter,
        stud_depth,
        MAX_PENETRATION_RATIO
    )

    # Check if reinforcement is required
    ratio = hole_diameter / stud_depth
    reinforcement_required = ratio > REINFORCEMENT_THRESHOLD

    return {
        "id": f"pen_{route.id}_{stud_id}",
        "route_id": route.id,
        "element_id": stud_id,
        "element_type": elem_type,
        "location": {
            "x": center[0],
            "y": center[1],
            "z": center[2]
        },
        "diameter": hole_diameter,
        "pipe_size": pipe_diameter,
        "system_type": route.system_type,
        "is_allowed": is_allowed,
        "warning": warning,
        "reinforcement_required": reinforcement_required,
        "penetration_ratio": ratio,
    }


def get_pipe_size_info(diameter_ft: float) -> Dict[str, Any]:
    """
    Get standard pipe size information from diameter.

    Args:
        diameter_ft: Pipe outer diameter in feet

    Returns:
        Dictionary with:
        - nominal_size: Standard nominal size (e.g., "1-1/2")
        - outer_diameter: Actual OD in feet
        - outer_diameter_inches: OD in inches
    """
    pipe_size = PipeSize.from_diameter(diameter_ft)

    return {
        "nominal_size": pipe_size.nominal_size,
        "outer_diameter": pipe_size.outer_diameter,
        "outer_diameter_inches": pipe_size.outer_diameter * 12,
    }
