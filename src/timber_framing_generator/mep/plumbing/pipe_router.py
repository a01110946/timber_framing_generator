# File: src/timber_framing_generator/mep/plumbing/pipe_router.py
"""
Pipe routing from plumbing fixtures to walls.

This module calculates pipe routes from plumbing fixture connectors
to wall entry points. The routing strategy is:

1. Fixture Connector → Wall Entry (horizontal run)
2. Wall Entry → Vertical Connection (first connection inside wall)

The router finds the nearest wall using ray-plane intersection
and calculates the route path through the wall framing.
"""

from typing import Dict, List, Any, Tuple, Optional
import math
import logging

from src.timber_framing_generator.core.mep_system import (
    MEPDomain,
    MEPConnector,
    MEPRoute,
)
from src.timber_framing_generator.mep.core.base import (
    distance_3d,
    normalize_vector,
    dot_product,
)

logger = logging.getLogger(__name__)


def calculate_pipe_routes(
    connectors: List[MEPConnector],
    framing_data: Dict[str, Any],
    target_points: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> List[MEPRoute]:
    """
    Calculate pipe routes from connectors to wall entries.

    Strategy: Fixture → Wall Entry → First Vertical Connection

    Args:
        connectors: Source connectors from plumbing fixtures
        framing_data: Wall framing data containing wall geometry
            Expected keys: walls (list of wall data dicts)
        target_points: Not used in Phase 1 (auto-find nearest wall)
        config: Routing configuration:
            - max_search_distance: Max distance to find wall (default 10 ft)
            - wall_thickness: Default wall thickness (default 0.333 ft = 4")

    Returns:
        List of MEPRoute objects with path points

    Example:
        >>> routes = calculate_pipe_routes(connectors, framing_data, [], {})
        >>> for route in routes:
        ...     print(f"Route {route.id}: {len(route.path_points)} points")
    """
    routes = []
    walls = extract_walls_from_framing(framing_data)
    max_distance = config.get("max_search_distance", 10.0)
    default_thickness = config.get("wall_thickness", 0.333)  # 4" default

    logger.info(f"Calculating routes for {len(connectors)} connectors with {len(walls)} walls")

    for connector in connectors:
        route = _calculate_single_route(
            connector,
            walls,
            max_distance,
            default_thickness
        )
        if route is not None:
            routes.append(route)
        else:
            logger.warning(f"No route found for connector {connector.id}")

    logger.info(f"Calculated {len(routes)} routes")
    return routes


def _calculate_single_route(
    connector: MEPConnector,
    walls: List[Dict[str, Any]],
    max_distance: float,
    default_thickness: float
) -> Optional[MEPRoute]:
    """
    Calculate route for a single connector.

    Args:
        connector: Source connector
        walls: List of wall data
        max_distance: Maximum search distance
        default_thickness: Default wall thickness

    Returns:
        MEPRoute if wall found, None otherwise
    """
    # Step 1: Find nearest wall entry point
    wall_entry = find_wall_entry(
        connector.origin,
        connector.direction,
        walls,
        max_distance
    )

    if wall_entry is None:
        return None

    # Step 2: Calculate vertical connection point
    wall_thickness = wall_entry.get("wall_thickness", default_thickness)
    vertical_point = calculate_vertical_connection_point(
        wall_entry["entry_point"],
        wall_thickness,
        wall_entry["wall_normal"],
        connector.system_type
    )

    # Step 3: Build route path
    path_points = [
        connector.origin,           # Start at fixture connector
        wall_entry["entry_point"],  # Horizontal run to wall face
        vertical_point,             # First connection inside wall
    ]

    # Step 4: Determine pipe size from connector
    pipe_size = connector.radius * 2 if connector.radius else 0.0833  # Default 1"

    # Create route
    route = MEPRoute(
        id=f"route_{connector.id}",
        domain=MEPDomain.PLUMBING,
        system_type=connector.system_type,
        path_points=path_points,
        start_connector_id=connector.id,
        end_point_type="vertical_connection",
        pipe_size=pipe_size,
        end_point=vertical_point,
    )

    return route


def find_wall_entry(
    origin: Tuple[float, float, float],
    direction: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
    max_distance: float
) -> Optional[Dict[str, Any]]:
    """
    Find where a ray from connector intersects nearest wall.

    Uses ray-plane intersection for each wall face, then checks
    if the intersection point is within the wall boundaries.

    Args:
        origin: Connector position (x, y, z)
        direction: Connector direction vector (should be normalized)
        walls: List of wall data dictionaries
        max_distance: Maximum search distance in feet

    Returns:
        Dictionary with wall entry information:
        - wall_id: ID of the nearest wall
        - entry_point: (x, y, z) point on wall face
        - distance: Distance from connector to entry
        - wall_normal: Wall normal at entry point
        - wall_thickness: Wall thickness
        Or None if no wall found
    """
    best_entry = None
    best_distance = max_distance

    # Normalize direction vector
    direction = normalize_vector(direction)

    for wall in walls:
        # Get wall face plane
        wall_plane = get_wall_face_plane(wall)
        if wall_plane is None:
            continue

        # Ray-plane intersection
        intersection = ray_plane_intersection(
            origin,
            direction,
            wall_plane
        )

        if intersection is None:
            continue

        # Check distance
        dist = distance_3d(origin, intersection)
        if dist >= best_distance:
            continue

        # Check if intersection is within wall bounds
        if not point_in_wall_bounds(intersection, wall):
            continue

        # Update best entry
        best_distance = dist
        best_entry = {
            "wall_id": wall.get("id", wall.get("wall_id", "unknown")),
            "entry_point": intersection,
            "distance": dist,
            "wall_normal": wall_plane["normal"],
            "wall_thickness": wall.get("thickness", 0.333),
        }

    return best_entry


def get_wall_face_plane(wall: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get the face plane of a wall.

    The wall face plane is defined by:
    - Origin: Wall start point
    - Normal: Wall Z-axis (perpendicular to wall face)

    Args:
        wall: Wall data dictionary with base_plane or geometry info

    Returns:
        Dictionary with plane data:
        - origin: (x, y, z) point on plane
        - normal: (x, y, z) plane normal vector
        Or None if wall data insufficient
    """
    # Try to get from base_plane
    base_plane = wall.get("base_plane")
    if base_plane:
        origin = base_plane.get("origin", {})
        z_axis = base_plane.get("z_axis", {})

        plane_origin = (
            origin.get("x", 0),
            origin.get("y", 0),
            origin.get("z", 0)
        )

        plane_normal = (
            z_axis.get("x", 0),
            z_axis.get("y", 0),
            z_axis.get("z", 1)
        )

        return {
            "origin": plane_origin,
            "normal": normalize_vector(plane_normal)
        }

    # Try to derive from wall geometry
    start_point = wall.get("start_point")
    end_point = wall.get("end_point")

    if start_point and end_point:
        # Wall direction
        dx = end_point.get("x", 0) - start_point.get("x", 0)
        dy = end_point.get("y", 0) - start_point.get("y", 0)
        dz = 0  # Walls are typically horizontal

        # Normal is perpendicular to wall direction (rotate 90 degrees in XY)
        normal = normalize_vector((-dy, dx, dz))

        plane_origin = (
            start_point.get("x", 0),
            start_point.get("y", 0),
            start_point.get("z", 0)
        )

        return {
            "origin": plane_origin,
            "normal": normal
        }

    return None


def ray_plane_intersection(
    ray_origin: Tuple[float, float, float],
    ray_direction: Tuple[float, float, float],
    plane: Dict[str, Any]
) -> Optional[Tuple[float, float, float]]:
    """
    Calculate intersection of a ray with a plane.

    Uses the parametric ray equation: P = O + t * D
    And plane equation: dot(P - P0, N) = 0

    Args:
        ray_origin: Ray start point (O)
        ray_direction: Ray direction vector (D), should be normalized
        plane: Plane definition with origin and normal

    Returns:
        Intersection point (x, y, z), or None if no intersection
        (ray parallel to plane or intersection behind ray origin)
    """
    plane_origin = plane["origin"]
    plane_normal = plane["normal"]

    # Calculate denominator: dot(D, N)
    denom = dot_product(ray_direction, plane_normal)

    # Check if ray is parallel to plane
    if abs(denom) < 1e-10:
        return None

    # Calculate t parameter: t = dot(P0 - O, N) / dot(D, N)
    p0_minus_o = (
        plane_origin[0] - ray_origin[0],
        plane_origin[1] - ray_origin[1],
        plane_origin[2] - ray_origin[2]
    )
    t = dot_product(p0_minus_o, plane_normal) / denom

    # Check if intersection is behind ray origin
    if t < 0:
        return None

    # Calculate intersection point
    intersection = (
        ray_origin[0] + t * ray_direction[0],
        ray_origin[1] + t * ray_direction[1],
        ray_origin[2] + t * ray_direction[2]
    )

    return intersection


def point_in_wall_bounds(
    point: Tuple[float, float, float],
    wall: Dict[str, Any]
) -> bool:
    """
    Check if a point is within wall boundaries.

    The point should be within:
    - U range: 0 to wall_length
    - V range: base_elevation to base_elevation + wall_height

    Args:
        point: Point to check (x, y, z)
        wall: Wall data with geometry info

    Returns:
        True if point is within wall bounds
    """
    # Get wall bounds
    wall_length = wall.get("length", wall.get("wall_length", 100))
    wall_height = wall.get("height", wall.get("wall_height", 10))
    base_elevation = wall.get("base_elevation", 0)

    # Get wall base plane for coordinate conversion
    base_plane = wall.get("base_plane")
    if base_plane:
        origin = base_plane.get("origin", {})
        x_axis = base_plane.get("x_axis", {"x": 1, "y": 0, "z": 0})

        wall_origin = (
            origin.get("x", 0),
            origin.get("y", 0),
            origin.get("z", 0)
        )
        wall_x_axis = (
            x_axis.get("x", 1),
            x_axis.get("y", 0),
            x_axis.get("z", 0)
        )

        # Calculate point relative to wall origin
        dx = point[0] - wall_origin[0]
        dy = point[1] - wall_origin[1]

        # Project onto wall X axis to get U coordinate
        u = dx * wall_x_axis[0] + dy * wall_x_axis[1]

        # Z coordinate relative to base
        v = point[2] - wall_origin[2]

    else:
        # Simplified bounds check using start/end points
        start_point = wall.get("start_point", {"x": 0, "y": 0, "z": 0})
        end_point = wall.get("end_point", {"x": wall_length, "y": 0, "z": 0})

        min_x = min(start_point.get("x", 0), end_point.get("x", 0))
        max_x = max(start_point.get("x", 0), end_point.get("x", 0))
        min_y = min(start_point.get("y", 0), end_point.get("y", 0))
        max_y = max(start_point.get("y", 0), end_point.get("y", 0))

        # Allow some tolerance
        tolerance = 0.5  # 6 inches

        if point[0] < min_x - tolerance or point[0] > max_x + tolerance:
            return False
        if point[1] < min_y - tolerance or point[1] > max_y + tolerance:
            return False

        u = 0  # Simplified, assume within bounds
        v = point[2] - base_elevation

    # Check U bounds (along wall length)
    tolerance = 0.1  # 1.2 inches
    if u < -tolerance or u > wall_length + tolerance:
        return False

    # Check V bounds (vertical)
    if v < -tolerance or v > wall_height + tolerance:
        return False

    return True


def calculate_vertical_connection_point(
    entry_point: Tuple[float, float, float],
    wall_thickness: float,
    wall_normal: Tuple[float, float, float],
    system_type: str
) -> Tuple[float, float, float]:
    """
    Calculate the vertical connection point inside a wall.

    After entering a wall, pipes typically run vertically. This function
    calculates the point where the horizontal run meets the vertical,
    offset into the wall by half the thickness.

    Args:
        entry_point: Point where pipe enters wall face
        wall_thickness: Wall thickness in feet
        wall_normal: Wall normal vector (points outward from wall)
        system_type: System type for offset rules

    Returns:
        Vertical connection point (x, y, z) inside wall
    """
    # Offset into wall by half thickness
    # Wall normal points outward, so we go opposite direction
    offset = wall_thickness / 2

    connection_point = (
        entry_point[0] - wall_normal[0] * offset,
        entry_point[1] - wall_normal[1] * offset,
        entry_point[2]  # Same elevation for now
    )

    return connection_point


def extract_walls_from_framing(framing_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract wall data from framing data structure.

    The framing data may contain walls directly or nested in results.

    Args:
        framing_data: Framing data dictionary

    Returns:
        List of wall data dictionaries
    """
    # Direct walls list
    if "walls" in framing_data:
        return framing_data["walls"]

    # Nested in results
    if "results" in framing_data:
        results = framing_data["results"]
        if isinstance(results, dict) and "walls" in results:
            return results["walls"]

    # Try wall_data key
    if "wall_data" in framing_data:
        wall_data = framing_data["wall_data"]
        if isinstance(wall_data, list):
            return wall_data
        elif isinstance(wall_data, dict):
            return [wall_data]

    # Single wall
    if "wall_id" in framing_data or "base_plane" in framing_data:
        return [framing_data]

    logger.warning("No walls found in framing data")
    return []
