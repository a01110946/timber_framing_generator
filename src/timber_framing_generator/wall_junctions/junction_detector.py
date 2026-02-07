# File: src/timber_framing_generator/wall_junctions/junction_detector.py

"""Wall junction graph construction and classification.

Builds a graph of wall junctions by:
1. Extracting wall endpoints from walls_json
2. Matching nearby endpoints (L-corners, X-crossings)
3. Matching endpoints to wall mid-spans (T-intersections)
4. Grouping matches into junction nodes
5. Classifying each node by type

Reuses endpoint-matching patterns from panels/corner_handler.py.

All measurements are in feet. Coordinates are world XYZ.
"""

import math
import logging
from typing import List, Dict, Tuple, Optional

from .junction_types import (
    JunctionNode,
    JunctionType,
    WallConnection,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Geometry Utilities
# =============================================================================


def _points_close(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    tolerance: float,
) -> bool:
    """Check if two 3D points are within tolerance (Euclidean distance)."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    dz = p1[2] - p2[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz) <= tolerance


def _point_to_segment_distance(
    point: Tuple[float, float, float],
    seg_start: Tuple[float, float, float],
    seg_end: Tuple[float, float, float],
) -> Tuple[float, float]:
    """Distance from a point to a line segment, and parameter t along segment.

    Args:
        point: The query point (x, y, z).
        seg_start: Segment start point.
        seg_end: Segment end point.

    Returns:
        (distance, t) where t is 0.0 at seg_start, 1.0 at seg_end,
        clamped to [0, 1].
    """
    dx = seg_end[0] - seg_start[0]
    dy = seg_end[1] - seg_start[1]
    dz = seg_end[2] - seg_start[2]
    seg_len_sq = dx * dx + dy * dy + dz * dz

    if seg_len_sq < 1e-12:
        # Degenerate segment (zero length)
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, seg_start)))
        return dist, 0.0

    # Project point onto the infinite line, get parameter t
    t = (
        (point[0] - seg_start[0]) * dx
        + (point[1] - seg_start[1]) * dy
        + (point[2] - seg_start[2]) * dz
    ) / seg_len_sq

    # Clamp to segment
    t = max(0.0, min(1.0, t))

    # Closest point on segment
    closest = (
        seg_start[0] + t * dx,
        seg_start[1] + t * dy,
        seg_start[2] + t * dz,
    )

    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, closest)))
    return dist, t


def _calculate_angle(
    dir1: Tuple[float, float, float],
    dir2: Tuple[float, float, float],
) -> float:
    """Angle between two direction vectors in degrees (0-180)."""
    dot = dir1[0] * dir2[0] + dir1[1] * dir2[1] + dir1[2] * dir2[2]
    mag1 = math.sqrt(sum(d * d for d in dir1))
    mag2 = math.sqrt(sum(d * d for d in dir2))

    if mag1 < 1e-12 or mag2 < 1e-12:
        return 0.0

    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def _negate_direction(
    direction: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Negate a direction vector."""
    return (-direction[0], -direction[1], -direction[2])


def _outward_direction_at_junction(
    conn: WallConnection,
) -> Tuple[float, float, float]:
    """Get the direction vector pointing AWAY from the junction.

    If the junction is at the wall's "end", the wall direction (start→end)
    points TOWARD the junction, so we negate it to get outward.
    If at "start", direction already points away from junction.

    For midspan connections, the direction is perpendicular from the
    continuous wall — we return the wall's direction as-is since the
    continuous wall passes through.
    """
    if conn.is_midspan:
        return conn.direction

    if conn.end == "end":
        # Wall direction points toward junction → negate for outward
        return _negate_direction(conn.direction)
    else:
        # Wall direction points away from junction → already outward
        return conn.direction


# =============================================================================
# Endpoint Extraction
# =============================================================================


def _extract_point(wall: Dict, which: str) -> Tuple[float, float, float]:
    """Extract a wall endpoint as a tuple.

    Args:
        wall: Wall data dictionary.
        which: "start" or "end".
    """
    key = f"base_curve_{which}"
    pt = wall[key]

    # Handle both dict and object-style access
    if isinstance(pt, dict):
        return (pt["x"], pt["y"], pt["z"])
    return (pt.x, pt.y, pt.z)


def _extract_direction(wall: Dict) -> Tuple[float, float, float]:
    """Extract wall direction vector from base_plane.x_axis."""
    bp = wall["base_plane"]
    x_axis = bp["x_axis"]
    if isinstance(x_axis, dict):
        return (x_axis["x"], x_axis["y"], x_axis["z"])
    return (x_axis.x, x_axis.y, x_axis.z)


def _extract_endpoints(walls_data: List[Dict]) -> List[Dict]:
    """Extract all wall endpoints with metadata.

    Returns list of endpoint dicts with wall info attached.
    """
    endpoints = []
    for wall in walls_data:
        wall_id = wall["wall_id"]
        direction = _extract_direction(wall)
        thickness = wall.get("wall_thickness", 0.3958)
        length = wall.get("wall_length", 0.0)
        is_exterior = wall.get("is_exterior", False)

        for end_name in ("start", "end"):
            position = _extract_point(wall, end_name)
            endpoints.append({
                "wall_id": wall_id,
                "end": end_name,
                "position": position,
                "direction": direction,
                "thickness": thickness,
                "length": length,
                "is_exterior": is_exterior,
                "is_midspan": False,
                "midspan_u": None,
                "group_id": None,  # Assigned during grouping
            })

    return endpoints


# =============================================================================
# Grouping / Union-Find
# =============================================================================


def _group_close_endpoints(
    endpoints: List[Dict],
    tolerance: float,
) -> Dict[int, List[Dict]]:
    """Group endpoints that are within tolerance of each other.

    Uses a simple union-find approach: iterate all pairs, merge groups
    when two endpoints from different walls are close.

    The tolerance parameter serves as a **minimum floor**. For each pair
    of endpoints, the effective tolerance is:
        max(tolerance, (thickness_i + thickness_j) / 2)
    This accounts for Revit wall centerline offsets at corners, where
    perpendicular walls have endpoints offset by approximately
    sqrt((t1/2)^2 + (t2/2)^2).

    Args:
        endpoints: List of endpoint dicts (each must have "thickness" key).
        tolerance: Minimum distance to consider endpoints as connected (feet).

    Returns:
        Dict mapping group_id to list of endpoints in that group.
    """
    n = len(endpoints)

    # Initialize: each endpoint is its own group
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # Path compression
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # Compare all pairs — only merge endpoints from DIFFERENT walls
    for i in range(n):
        for j in range(i + 1, n):
            if endpoints[i]["wall_id"] == endpoints[j]["wall_id"]:
                continue  # Skip same-wall endpoints

            # Thickness-aware tolerance: accounts for Revit centerline offsets
            thick_i = endpoints[i].get("thickness", 0.0)
            thick_j = endpoints[j].get("thickness", 0.0)
            pair_tol = max(tolerance, (thick_i + thick_j) / 2.0)

            if _points_close(
                endpoints[i]["position"],
                endpoints[j]["position"],
                pair_tol,
            ):
                union(i, j)
                if pair_tol > tolerance:
                    logger.debug(
                        "Thickness-aware match: %s/%s <-> %s/%s "
                        "(pair_tol=%.4f > base_tol=%.4f)",
                        endpoints[i]["wall_id"], endpoints[i]["end"],
                        endpoints[j]["wall_id"], endpoints[j]["end"],
                        pair_tol, tolerance,
                    )

    # Build groups
    groups: Dict[int, List[Dict]] = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(endpoints[i])

    return groups


# =============================================================================
# T-Intersection Detection
# =============================================================================


def _detect_t_intersections(
    endpoints: List[Dict],
    walls_data: List[Dict],
    groups: Dict[int, List[Dict]],
    tolerance: float,
    endpoint_exclusion_t: float = 0.05,
) -> None:
    """Find endpoints that meet wall mid-spans (T-intersections).

    For each endpoint that is alone in its group (free end), check if it's
    close to the mid-span of any other wall segment. If so, create a
    midspan connection and merge into or create a group.

    The tolerance parameter serves as a **minimum floor**. For each
    endpoint-segment pair, the effective tolerance is:
        max(tolerance, (ep_thickness + wall_thickness) / 2)
    This accounts for Revit wall centerline offsets at T-intersections.

    Args:
        endpoints: All endpoint dicts (modified in-place with group_id).
        walls_data: Original wall data list.
        groups: Existing groups from endpoint matching (modified in-place).
        tolerance: Minimum distance for point-to-segment matching (feet).
        endpoint_exclusion_t: Exclude matches near segment endpoints
            (t < exclusion or t > 1-exclusion) to avoid double-counting
            as L-corners.
    """
    # Build a wall lookup for segment geometry
    wall_lookup = {w["wall_id"]: w for w in walls_data}

    # Find endpoints that are alone in their group (potential free ends)
    singleton_indices = []
    for group_id, members in groups.items():
        if len(members) == 1:
            singleton_indices.append((group_id, members[0]))

    for group_id, ep in singleton_indices:
        ep_pos = ep["position"]

        for wall in walls_data:
            if wall["wall_id"] == ep["wall_id"]:
                continue  # Skip self

            seg_start = _extract_point(wall, "start")
            seg_end = _extract_point(wall, "end")

            dist, t = _point_to_segment_distance(ep_pos, seg_start, seg_end)

            # Thickness-aware tolerance for T-intersection detection
            ep_thickness = ep.get("thickness", 0.0)
            wall_thickness = wall.get("wall_thickness", 0.0)
            t_tol = max(tolerance, (ep_thickness + wall_thickness) / 2.0)

            # Must be close to segment AND not near endpoints
            if (
                dist <= t_tol
                and endpoint_exclusion_t < t < (1.0 - endpoint_exclusion_t)
            ):
                # T-intersection found!
                midspan_u = t * wall.get("wall_length", 0.0)
                direction = _extract_direction(wall)

                logger.debug(
                    "T-intersection: %s meets %s at u=%.2f "
                    "(t=%.3f, dist=%.4f, eff_tol=%.4f)",
                    ep["wall_id"],
                    wall["wall_id"],
                    midspan_u,
                    t,
                    dist,
                    t_tol,
                )

                # Create a midspan connection for the continuous wall
                midspan_ep = {
                    "wall_id": wall["wall_id"],
                    "end": "midspan",
                    "position": ep_pos,  # Use endpoint position as meeting point
                    "direction": direction,
                    "thickness": wall.get("wall_thickness", 0.3958),
                    "length": wall.get("wall_length", 0.0),
                    "is_exterior": wall.get("is_exterior", False),
                    "is_midspan": True,
                    "midspan_u": midspan_u,
                    "group_id": None,
                }

                # Add midspan connection to the same group as the endpoint
                groups[group_id].append(midspan_ep)

                # Only match the first (closest) wall for this endpoint
                break


# =============================================================================
# Junction Classification
# =============================================================================


def _classify_junction(
    connections: List[WallConnection],
    inline_threshold: float = 170.0,
) -> JunctionType:
    """Classify a junction based on connection count and angles.

    Args:
        connections: Wall connections at this junction.
        inline_threshold: Angles >= this are considered inline (degrees).

    Returns:
        The classified JunctionType.
    """
    n = len(connections)

    if n <= 1:
        return JunctionType.FREE_END

    # Check for midspan connections (definitive T-intersection marker)
    has_midspan = any(c.is_midspan for c in connections)

    if n == 2:
        if has_midspan:
            return JunctionType.T_INTERSECTION

        # Calculate angle between the two walls' outward directions
        out1 = _outward_direction_at_junction(connections[0])
        out2 = _outward_direction_at_junction(connections[1])
        angle = _calculate_angle(out1, out2)

        # Outward directions at a junction:
        # - For L-corner (~90°): outward directions point ~90° apart
        # - For inline (~180°): outward directions point ~180° apart
        if angle >= inline_threshold:
            return JunctionType.INLINE
        return JunctionType.L_CORNER

    if n == 3:
        if has_midspan:
            return JunctionType.T_INTERSECTION

        # Check if any pair of non-midspan connections is ~inline
        non_midspan = [c for c in connections if not c.is_midspan]
        for i in range(len(non_midspan)):
            for j in range(i + 1, len(non_midspan)):
                out_i = _outward_direction_at_junction(non_midspan[i])
                out_j = _outward_direction_at_junction(non_midspan[j])
                angle = _calculate_angle(out_i, out_j)
                if angle >= inline_threshold:
                    return JunctionType.T_INTERSECTION

        return JunctionType.MULTI_WAY

    if n == 4:
        # Check if we have two inline pairs → X-crossing
        inline_pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                out_i = _outward_direction_at_junction(connections[i])
                out_j = _outward_direction_at_junction(connections[j])
                angle = _calculate_angle(out_i, out_j)
                if angle >= inline_threshold:
                    inline_pairs += 1
        if inline_pairs >= 2:
            return JunctionType.X_CROSSING

    return JunctionType.MULTI_WAY


# =============================================================================
# Main Entry Point
# =============================================================================


def build_junction_graph(
    walls_data: List[Dict],
    tolerance: float = 0.1,
    t_intersection_tolerance: float = 0.15,
    inline_angle_threshold: float = 170.0,
) -> Dict[str, JunctionNode]:
    """Build a junction graph from wall data.

    This is the main entry point for junction detection. It:
    1. Extracts all wall endpoints
    2. Groups nearby endpoints (L-corners, X-crossings)
    3. Detects T-intersections (endpoint near wall mid-span)
    4. Creates JunctionNode for each group
    5. Classifies each node by type

    Args:
        walls_data: List of wall dicts from walls_json.
        tolerance: Max distance for endpoint-to-endpoint matching (feet).
        t_intersection_tolerance: Max distance for endpoint-to-segment (feet).
        inline_angle_threshold: Angles >= this are inline, not junctions (degrees).

    Returns:
        Dict mapping junction_id to JunctionNode.
    """
    if not walls_data:
        logger.info("No walls provided, returning empty junction graph")
        return {}

    logger.info(
        "Building junction graph for %d walls "
        "(base_tol=%.3f, t_base_tol=%.3f, thickness-aware matching active)",
        len(walls_data),
        tolerance,
        t_intersection_tolerance,
    )

    # Step 1: Extract all endpoints
    endpoints = _extract_endpoints(walls_data)
    logger.debug("Extracted %d endpoints from %d walls", len(endpoints), len(walls_data))

    # Step 2: Group close endpoints (L-corners, X-crossings)
    groups = _group_close_endpoints(endpoints, tolerance)
    multi_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    logger.debug(
        "Found %d endpoint groups (%d with 2+ walls)",
        len(groups),
        len(multi_groups),
    )

    # Step 3: Detect T-intersections
    _detect_t_intersections(
        endpoints, walls_data, groups, t_intersection_tolerance
    )

    # Step 4: Create JunctionNodes
    nodes: Dict[str, JunctionNode] = {}
    node_counter = 0

    for group_id, group_endpoints in groups.items():
        # Build WallConnection list
        connections = []
        for ep in group_endpoints:
            conn = WallConnection(
                wall_id=ep["wall_id"],
                end=ep["end"],
                direction=ep["direction"],
                angle_at_junction=0.0,  # Computed below
                wall_thickness=ep["thickness"],
                wall_length=ep["length"],
                is_exterior=ep.get("is_exterior", False),
                is_midspan=ep.get("is_midspan", False),
                midspan_u=ep.get("midspan_u"),
            )
            connections.append(conn)

        # Average position of all endpoints in the group
        positions = [ep["position"] for ep in group_endpoints]
        avg_pos = (
            sum(p[0] for p in positions) / len(positions),
            sum(p[1] for p in positions) / len(positions),
            sum(p[2] for p in positions) / len(positions),
        )

        junction_id = f"junction_{node_counter}"
        node_counter += 1

        node = JunctionNode(
            id=junction_id,
            position=avg_pos,
            junction_type=JunctionType.FREE_END,  # Classified in step 5
            connections=connections,
        )
        nodes[junction_id] = node

    # Step 5: Classify each node
    for node in nodes.values():
        node.junction_type = _classify_junction(
            node.connections, inline_angle_threshold
        )

    # Log summary
    type_counts: Dict[str, int] = {}
    for node in nodes.values():
        key = node.junction_type.value
        type_counts[key] = type_counts.get(key, 0) + 1

    logger.info(
        "Junction graph: %d nodes — %s",
        len(nodes),
        ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items())),
    )

    return nodes
