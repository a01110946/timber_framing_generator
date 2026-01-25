# File: src/timber_framing_generator/mep/plumbing/pipe_router.py
"""
Pipe routing from plumbing fixtures to walls.

This module calculates pipe routes from plumbing fixture connectors
to wall entry points. The routing follows real plumbing patterns:

Routing Strategy:
1. **Initial Drop**: Connector → Drop following BasisZ direction
2. **Fixture Merge**: Same-system connectors on a fixture merge
3. **Horizontal Run**: Merge point → Wall entry (horizontal)
4. **Wall Entry**: Horizontal to wall face → Vertical inside wall

System-Specific Behavior:
- **Sanitary (drains)**: Drop DOWN from fixture, gravity flow
- **Vent**: Route UP to roof
- **Supply (water)**: Follow BasisZ, typically horizontal from wall

Example for double sink (Sanitary):
    Drain 1 → DROP 1ft → ┐
                         ├→ MERGE → Horizontal to wall → DOWN in wall
    Drain 2 → DROP 1ft → ┘
"""

from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
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


# =============================================================================
# Constants
# =============================================================================

# Initial drop distance from connector (feet)
INITIAL_DROP_DISTANCE = 1.0

# Vertical run distance inside wall (feet)
WALL_VERTICAL_DISTANCE = 1.0


# =============================================================================
# Routing Direction Helpers
# =============================================================================

def get_initial_drop_direction(system_type: str) -> Tuple[float, float, float]:
    """
    Get the initial drop direction from connector based on system type.

    Args:
        system_type: Plumbing system type (Sanitary, DomesticColdWater, etc.)

    Returns:
        Direction vector (x, y, z) for initial drop from connector
    """
    system_lower = system_type.lower() if system_type else ""

    # Sanitary (drains) - always drop DOWN (gravity flow)
    if "sanitary" in system_lower or "drain" in system_lower:
        return (0.0, 0.0, -1.0)

    # Vent - routes UP
    if "vent" in system_lower:
        return (0.0, 0.0, 1.0)

    # Supply water - typically comes from below or side
    # For supply, we follow the connector direction but ensure some drop
    return (0.0, 0.0, -1.0)  # Default to down for supply too


def get_vertical_routing_direction(system_type: str) -> float:
    """
    Get vertical routing direction multiplier for inside-wall routing.

    Args:
        system_type: Plumbing system type

    Returns:
        Vertical multiplier: -1.0 for DOWN, +1.0 for UP
    """
    system_lower = system_type.lower() if system_type else ""

    # Sanitary (drains) - gravity flow DOWN
    if "sanitary" in system_lower or "drain" in system_lower:
        return -1.0

    # Vent - routes UP to roof
    if "vent" in system_lower:
        return 1.0

    # Supply water (DomesticColdWater, DomesticHotWater) - routes UP
    # Supply lines in walls typically run vertically from basement/crawlspace
    # Fixture connections tie into the vertical supply risers
    return 1.0


def find_nearest_wall_perpendicular(
    origin: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
    max_distance: float
) -> Optional[Dict[str, Any]]:
    """
    Find the nearest wall and return perpendicular approach info.

    Instead of shooting toward wall center (diagonal), this finds the
    closest wall and calculates the perpendicular distance to its face.

    Args:
        origin: Starting point
        walls: Available walls
        max_distance: Maximum search distance

    Returns:
        Dictionary with:
        - wall: The nearest wall data
        - perpendicular_dir: Direction perpendicular to wall face (toward wall)
        - distance: Perpendicular distance to wall
        - entry_point: Point on wall face (perpendicular projection)
        Or None if no wall found
    """
    if not walls:
        return None

    best_result = None
    best_distance = max_distance

    for wall in walls:
        wall_plane = get_wall_face_plane(wall)
        if wall_plane is None:
            continue

        plane_origin = wall_plane["origin"]
        plane_normal = wall_plane["normal"]

        # Calculate perpendicular distance to wall plane
        # Distance = dot(origin - plane_origin, plane_normal)
        to_origin = (
            origin[0] - plane_origin[0],
            origin[1] - plane_origin[1],
            origin[2] - plane_origin[2]
        )
        signed_dist = dot_product(to_origin, plane_normal)

        # We want to approach wall, so distance should be positive
        # (origin is on the normal side of the wall)
        if signed_dist <= 0:
            # Origin is behind the wall or on it - try opposite normal
            signed_dist = -signed_dist
            approach_dir = (plane_normal[0], plane_normal[1], 0.0)  # Keep horizontal
        else:
            # Origin is in front of wall, approach by going opposite to normal
            approach_dir = (-plane_normal[0], -plane_normal[1], 0.0)  # Keep horizontal

        # Normalize the horizontal approach direction
        mag = math.sqrt(approach_dir[0]**2 + approach_dir[1]**2)
        if mag < 0.001:
            continue  # Skip if no horizontal component
        approach_dir = (approach_dir[0] / mag, approach_dir[1] / mag, 0.0)

        dist = abs(signed_dist)
        if dist >= best_distance or dist < 0.01:
            continue

        # Get wall thickness to calculate face position
        wall_thickness = wall.get("thickness", 0.333)
        half_thickness = wall_thickness / 2

        # The wall plane is at the CENTER LINE of the wall.
        # The wall FACE (where pipe enters) is half-thickness BEFORE the center.
        # So we travel (dist - half_thickness) to reach the face.
        face_distance = dist - half_thickness
        if face_distance < 0.01:
            continue  # Origin is already inside or past the wall

        # Calculate entry point on wall FACE (not center line)
        entry_point = (
            origin[0] + approach_dir[0] * face_distance,
            origin[1] + approach_dir[1] * face_distance,
            origin[2]  # Keep same Z for horizontal approach
        )

        # Check if entry point is within wall bounds
        if not point_in_wall_bounds(entry_point, wall):
            continue

        best_distance = dist
        best_result = {
            "wall": wall,
            "perpendicular_dir": approach_dir,
            "distance": dist,
            "entry_point": entry_point,
            "wall_normal": plane_normal,
            "wall_thickness": wall.get("thickness", 0.333),
        }

    return best_result


def _get_wall_center(wall: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    """Get approximate center point of a wall."""
    base_plane = wall.get("base_plane")
    if base_plane:
        origin = base_plane.get("origin", {})
        x_axis = base_plane.get("x_axis", {"x": 1, "y": 0, "z": 0})
        wall_length = wall.get("length", wall.get("wall_length", 10))
        wall_height = wall.get("height", wall.get("wall_height", 10))

        cx = origin.get("x", 0) + x_axis.get("x", 1) * wall_length / 2
        cy = origin.get("y", 0) + x_axis.get("y", 0) * wall_length / 2
        cz = origin.get("z", 0) + wall_height / 2

        return (cx, cy, cz)

    start = wall.get("start_point")
    end = wall.get("end_point")
    if start and end:
        return (
            (start.get("x", 0) + end.get("x", 0)) / 2,
            (start.get("y", 0) + end.get("y", 0)) / 2,
            wall.get("base_elevation", 0) + wall.get("height", 10) / 2
        )

    return None


# =============================================================================
# Fixture Grouping
# =============================================================================

def group_connectors_by_fixture(
    connectors: List[MEPConnector]
) -> Dict[int, List[MEPConnector]]:
    """
    Group connectors by their parent fixture (owner_element_id).

    Args:
        connectors: List of all connectors

    Returns:
        Dictionary mapping fixture_id -> list of connectors
    """
    groups = defaultdict(list)
    for conn in connectors:
        fixture_id = conn.owner_element_id or 0
        groups[fixture_id].append(conn)
    return dict(groups)


def group_by_system_type(
    connectors: List[MEPConnector]
) -> Dict[str, List[MEPConnector]]:
    """
    Group connectors by system type within a fixture.

    Args:
        connectors: Connectors from a single fixture

    Returns:
        Dictionary mapping system_type -> list of connectors
    """
    groups = defaultdict(list)
    for conn in connectors:
        system_type = conn.system_type or "Unknown"
        groups[system_type].append(conn)
    return dict(groups)


def calculate_merge_point(
    connectors: List[MEPConnector],
    drop_distance: float
) -> Tuple[float, float, float]:
    """
    Calculate the merge point for multiple connectors of the same system.

    The merge point is below/above the centroid of the connectors,
    after the initial drop.

    Args:
        connectors: Connectors to merge
        drop_distance: Vertical drop distance

    Returns:
        Merge point coordinates (x, y, z)
    """
    if not connectors:
        return (0.0, 0.0, 0.0)

    # Get average position
    avg_x = sum(c.origin[0] for c in connectors) / len(connectors)
    avg_y = sum(c.origin[1] for c in connectors) / len(connectors)
    avg_z = sum(c.origin[2] for c in connectors) / len(connectors)

    # Get drop direction from first connector's system type
    drop_dir = get_initial_drop_direction(connectors[0].system_type)

    # Apply drop
    merge_x = avg_x + drop_dir[0] * drop_distance
    merge_y = avg_y + drop_dir[1] * drop_distance
    merge_z = avg_z + drop_dir[2] * drop_distance

    return (merge_x, merge_y, merge_z)


# =============================================================================
# Main Routing Functions
# =============================================================================

def calculate_pipe_routes(
    connectors: List[MEPConnector],
    framing_data: Dict[str, Any],
    target_points: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> List[MEPRoute]:
    """
    Calculate pipe routes from connectors to wall entries.

    Routes are calculated with proper plumbing patterns:
    1. Initial drop from each connector
    2. Merge same-system connectors per fixture
    3. Horizontal run to nearest wall
    4. Vertical run inside wall

    Args:
        connectors: Source connectors from plumbing fixtures
        framing_data: Wall framing data containing wall geometry
        target_points: Not used in Phase 1 (auto-find nearest wall)
        config: Routing configuration:
            - max_search_distance: Max distance to find wall (default 10 ft)
            - wall_thickness: Default wall thickness (default 0.333 ft = 4")
            - drop_distance: Initial drop from connector (default 1 ft)

    Returns:
        List of MEPRoute objects with path points
    """
    routes = []
    walls = extract_walls_from_framing(framing_data)
    max_distance = config.get("max_search_distance", 10.0)
    default_thickness = config.get("wall_thickness", 0.333)
    drop_distance = config.get("drop_distance", INITIAL_DROP_DISTANCE)

    logger.info(f"Calculating routes for {len(connectors)} connectors with {len(walls)} walls")

    # Group connectors by fixture
    fixture_groups = group_connectors_by_fixture(connectors)
    logger.info(f"Grouped into {len(fixture_groups)} fixtures")

    for fixture_id, fixture_connectors in fixture_groups.items():
        # Group by system type within this fixture
        system_groups = group_by_system_type(fixture_connectors)

        for system_type, system_connectors in system_groups.items():
            # Calculate routes for this system group
            group_routes = _calculate_system_group_routes(
                fixture_id,
                system_type,
                system_connectors,
                walls,
                max_distance,
                default_thickness,
                drop_distance
            )
            routes.extend(group_routes)

    logger.info(f"Calculated {len(routes)} routes")
    return routes


def _calculate_system_group_routes(
    fixture_id: int,
    system_type: str,
    connectors: List[MEPConnector],
    walls: List[Dict[str, Any]],
    max_distance: float,
    default_thickness: float,
    drop_distance: float
) -> List[MEPRoute]:
    """
    Calculate routes for a group of same-system connectors on one fixture.

    Pattern (all segments are orthogonal):
    1. Each connector drops vertically to drop point
    2. Horizontal run to merge point (if multiple connectors)
    3. Horizontal run perpendicular to wall face
    4. Horizontal into wall cavity (perpendicular to face)
    5. Vertical run inside wall (up or down based on system)

    Args:
        fixture_id: Parent fixture ID
        system_type: System type (Sanitary, DomesticColdWater, etc.)
        connectors: Connectors of this system type on this fixture
        walls: Available walls
        max_distance: Max wall search distance
        default_thickness: Default wall thickness
        drop_distance: Initial drop distance

    Returns:
        List of routes (one per connector, all meeting at merge point)
    """
    routes = []

    if not connectors:
        return routes

    # Calculate merge point (where all connectors of this system meet)
    merge_point = calculate_merge_point(connectors, drop_distance)

    # Find nearest wall with perpendicular approach
    wall_info = find_nearest_wall_perpendicular(merge_point, walls, max_distance)

    if wall_info is None:
        logger.warning(f"No wall found for fixture {fixture_id} system {system_type}")
        # Still create partial routes (connector → merge point)
        for conn in connectors:
            route = _create_partial_route(conn, merge_point, drop_distance)
            if route:
                routes.append(route)
        return routes

    # Extract wall info
    wall_entry_point = wall_info["entry_point"]
    approach_direction = wall_info["perpendicular_dir"]  # Direction we used to approach
    wall_thickness = wall_info.get("wall_thickness", default_thickness)

    # Calculate inside-wall point (continue in approach direction into wall cavity)
    inside_wall_point = calculate_inside_wall_point(
        wall_entry_point,
        wall_thickness,
        approach_direction  # Use approach direction, NOT wall normal
    )

    # Calculate vertical point (purely vertical from inside-wall point)
    vertical_point = calculate_vertical_point(inside_wall_point, system_type)

    # Create route for each connector
    for conn in connectors:
        route = _create_full_route(
            conn,
            merge_point,
            wall_entry_point,
            inside_wall_point,
            vertical_point,
            drop_distance
        )
        if route:
            routes.append(route)

    return routes


def _create_partial_route(
    connector: MEPConnector,
    merge_point: Tuple[float, float, float],
    drop_distance: float
) -> Optional[MEPRoute]:
    """
    Create a partial route when no wall is found.

    Path: Connector → Drop Point → Merge Point
    """
    # Calculate drop point from connector
    drop_dir = get_initial_drop_direction(connector.system_type)
    drop_point = (
        connector.origin[0] + drop_dir[0] * drop_distance,
        connector.origin[1] + drop_dir[1] * drop_distance,
        connector.origin[2] + drop_dir[2] * drop_distance
    )

    # Build path
    path_points = [connector.origin]

    # Add drop point if different from merge (multiple connectors case)
    if distance_3d(drop_point, merge_point) > 0.01:
        path_points.append(drop_point)

    path_points.append(merge_point)

    # Pipe size
    pipe_size = connector.radius * 2 if connector.radius else 0.0833

    return MEPRoute(
        id=f"route_{connector.id}",
        domain=MEPDomain.PLUMBING,
        system_type=connector.system_type,
        path_points=path_points,
        start_connector_id=connector.id,
        end_point_type="merge_point",
        pipe_size=pipe_size,
        end_point=merge_point,
    )


def _create_full_route(
    connector: MEPConnector,
    merge_point: Tuple[float, float, float],
    wall_entry: Tuple[float, float, float],
    inside_wall_point: Tuple[float, float, float],
    vertical_point: Tuple[float, float, float],
    drop_distance: float
) -> Optional[MEPRoute]:
    """
    Create a full route from connector to wall with orthogonal segments.

    Path (all segments are orthogonal):
    1. Connector → Drop Point (vertical)
    2. Drop Point → Merge Point (horizontal, if multiple connectors)
    3. Merge Point → Wall Entry (horizontal, perpendicular to wall)
    4. Wall Entry → Inside Wall (horizontal, into wall cavity)
    5. Inside Wall → Vertical Point (vertical, up or down)
    """
    # Calculate drop point from connector (vertical drop)
    drop_dir = get_initial_drop_direction(connector.system_type)
    drop_point = (
        connector.origin[0] + drop_dir[0] * drop_distance,
        connector.origin[1] + drop_dir[1] * drop_distance,
        connector.origin[2] + drop_dir[2] * drop_distance
    )

    # Build path - skip intermediate points if they're nearly coincident
    path_points = [connector.origin]

    # 1. Add drop point (vertical segment)
    if distance_3d(connector.origin, drop_point) > 0.01:
        path_points.append(drop_point)

    # 2. Add merge point (horizontal segment to merge)
    if distance_3d(drop_point, merge_point) > 0.01:
        path_points.append(merge_point)

    # 3. Add wall entry (horizontal segment, perpendicular to wall)
    if distance_3d(merge_point, wall_entry) > 0.01:
        path_points.append(wall_entry)

    # 4. Add inside wall point (horizontal into wall cavity)
    if distance_3d(wall_entry, inside_wall_point) > 0.01:
        path_points.append(inside_wall_point)

    # 5. Add vertical point (vertical segment inside wall)
    if distance_3d(inside_wall_point, vertical_point) > 0.01:
        path_points.append(vertical_point)

    # Pipe size
    pipe_size = connector.radius * 2 if connector.radius else 0.0833

    return MEPRoute(
        id=f"route_{connector.id}",
        domain=MEPDomain.PLUMBING,
        system_type=connector.system_type,
        path_points=path_points,
        start_connector_id=connector.id,
        end_point_type="vertical_connection",
        pipe_size=pipe_size,
        end_point=vertical_point,
    )


# =============================================================================
# Wall Finding Functions
# =============================================================================

def find_wall_entry(
    origin: Tuple[float, float, float],
    direction: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
    max_distance: float
) -> Optional[Dict[str, Any]]:
    """
    Find where a ray from origin intersects nearest wall.

    Args:
        origin: Starting point (x, y, z)
        direction: Search direction vector (should be normalized, horizontal)
        walls: List of wall data dictionaries
        max_distance: Maximum search distance in feet

    Returns:
        Dictionary with wall entry information or None
    """
    best_entry = None
    best_distance = max_distance

    direction = normalize_vector(direction)

    for wall in walls:
        wall_plane = get_wall_face_plane(wall)
        if wall_plane is None:
            continue

        intersection = ray_plane_intersection(origin, direction, wall_plane)
        if intersection is None:
            continue

        dist = distance_3d(origin, intersection)
        if dist >= best_distance:
            continue

        if not point_in_wall_bounds(intersection, wall):
            continue

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
    """Get the face plane of a wall."""
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

    start_point = wall.get("start_point")
    end_point = wall.get("end_point")

    if start_point and end_point:
        dx = end_point.get("x", 0) - start_point.get("x", 0)
        dy = end_point.get("y", 0) - start_point.get("y", 0)
        dz = 0

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
    """Calculate intersection of a ray with a plane."""
    plane_origin = plane["origin"]
    plane_normal = plane["normal"]

    denom = dot_product(ray_direction, plane_normal)

    if abs(denom) < 1e-10:
        return None

    p0_minus_o = (
        plane_origin[0] - ray_origin[0],
        plane_origin[1] - ray_origin[1],
        plane_origin[2] - ray_origin[2]
    )
    t = dot_product(p0_minus_o, plane_normal) / denom

    if t < 0:
        return None

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
    """Check if a point is within wall boundaries."""
    wall_length = wall.get("length", wall.get("wall_length", 100))
    wall_height = wall.get("height", wall.get("wall_height", 10))
    base_elevation = wall.get("base_elevation", 0)

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

        dx = point[0] - wall_origin[0]
        dy = point[1] - wall_origin[1]
        u = dx * wall_x_axis[0] + dy * wall_x_axis[1]
        v = point[2] - wall_origin[2]
    else:
        start_point = wall.get("start_point", {"x": 0, "y": 0, "z": 0})
        end_point = wall.get("end_point", {"x": wall_length, "y": 0, "z": 0})

        min_x = min(start_point.get("x", 0), end_point.get("x", 0))
        max_x = max(start_point.get("x", 0), end_point.get("x", 0))
        min_y = min(start_point.get("y", 0), end_point.get("y", 0))
        max_y = max(start_point.get("y", 0), end_point.get("y", 0))

        tolerance = 0.5
        if point[0] < min_x - tolerance or point[0] > max_x + tolerance:
            return False
        if point[1] < min_y - tolerance or point[1] > max_y + tolerance:
            return False

        u = 0
        v = point[2] - base_elevation

    tolerance = 0.1
    if u < -tolerance or u > wall_length + tolerance:
        return False
    if v < -tolerance or v > wall_height + tolerance:
        return False

    return True


def calculate_inside_wall_point(
    entry_point: Tuple[float, float, float],
    wall_thickness: float,
    approach_direction: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """
    Calculate point inside the wall (horizontal offset from entry).

    This is a purely horizontal move into the wall cavity,
    continuing in the same direction we used to approach the wall.

    Args:
        entry_point: Point where pipe enters wall face
        wall_thickness: Wall thickness in feet
        approach_direction: Direction we used to approach wall (NOT wall normal)

    Returns:
        Point at center of wall cavity (same Z as entry)
    """
    offset = wall_thickness / 2

    # Continue in the same direction we were traveling (into the wall)
    inside_point = (
        entry_point[0] + approach_direction[0] * offset,
        entry_point[1] + approach_direction[1] * offset,
        entry_point[2]  # Same Z - purely horizontal
    )

    return inside_point


def calculate_vertical_point(
    inside_wall_point: Tuple[float, float, float],
    system_type: str
) -> Tuple[float, float, float]:
    """
    Calculate the vertical connection point from inside-wall point.

    This is a purely vertical move (only Z changes).

    Args:
        inside_wall_point: Point inside wall cavity
        system_type: System type for vertical direction

    Returns:
        Point after vertical run (same X, Y - only Z changes)
    """
    vertical_dir = get_vertical_routing_direction(system_type)
    z_offset = WALL_VERTICAL_DISTANCE * vertical_dir

    # Purely vertical - only Z changes
    vertical_point = (
        inside_wall_point[0],  # Same X
        inside_wall_point[1],  # Same Y
        inside_wall_point[2] + z_offset  # Only Z changes
    )

    return vertical_point


def extract_walls_from_framing(framing_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract wall data from framing data structure."""
    if "walls" in framing_data:
        return framing_data["walls"]

    if "results" in framing_data:
        results = framing_data["results"]
        if isinstance(results, dict) and "walls" in results:
            return results["walls"]

    if "wall_data" in framing_data:
        wall_data = framing_data["wall_data"]
        if isinstance(wall_data, list):
            return wall_data
        elif isinstance(wall_data, dict):
            return [wall_data]

    if "wall_id" in framing_data or "base_plane" in framing_data:
        return [framing_data]

    logger.warning("No walls found in framing data")
    return []
