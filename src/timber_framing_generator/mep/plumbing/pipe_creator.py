# File: src/timber_framing_generator/mep/plumbing/pipe_creator.py
"""
Pipe creation logic for baking routes to Revit.

This module handles:
1. Parsing route JSON into pipe segments
2. Building pipe networks with branch/trunk topology
3. Detecting merge points for T-fittings
4. Grouping routes by fixture and system type

The actual Revit API calls are in the GHPython component,
but this module provides the data structures and logic.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional
import json
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Fitting gap distances (feet)
WYE_FITTING_GAP = 0.167  # 2 inches - minimum gap for fitting
MIN_PIPE_LENGTH = 0.0833  # 1 inch - minimum remaining pipe length


# =============================================================================
# Vector Helper Functions
# =============================================================================

def vector_subtract(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Subtract vector b from vector a."""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vector_add(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Add vectors a and b."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vector_scale(v: Tuple[float, float, float], s: float) -> Tuple[float, float, float]:
    """Scale vector v by scalar s."""
    return (v[0] * s, v[1] * s, v[2] * s)


def vector_normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Normalize vector to unit length."""
    length = (v[0]**2 + v[1]**2 + v[2]**2) ** 0.5
    if length < 0.0001:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def vector_length(v: Tuple[float, float, float]) -> float:
    """Calculate vector length."""
    return (v[0]**2 + v[1]**2 + v[2]**2) ** 0.5


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PipeSegment:
    """Represents a single pipe segment between two points."""
    start_point: Tuple[float, float, float]
    end_point: Tuple[float, float, float]
    system_type: str
    pipe_size: float
    route_id: str
    segment_index: int
    is_branch: bool = True  # True = unique per connector, False = shared trunk

    def get_length(self) -> float:
        """Calculate segment length."""
        dx = self.end_point[0] - self.start_point[0]
        dy = self.end_point[1] - self.start_point[1]
        dz = self.end_point[2] - self.start_point[2]
        return (dx**2 + dy**2 + dz**2) ** 0.5


@dataclass
class MergePointInfo:
    """Geometry information for wye fitting insertion at merge points.

    When multiple branches merge, we need to create a gap where the wye fitting
    will connect three separate pipe ends. This class stores the trimmed endpoints
    for each branch and the trunk.

    Attributes:
        original_point: The original merge point coordinates (x, y, z)
        branch_endpoints: List of trimmed endpoint for each branch (pulled back from merge)
        trunk_startpoint: Trimmed start point for trunk (pushed forward from merge)
        branch_directions: Unit vectors pointing from branch toward merge point
        trunk_direction: Unit vector pointing from merge toward trunk end
    """
    original_point: Tuple[float, float, float]
    branch_endpoints: List[Tuple[float, float, float]]
    trunk_startpoint: Tuple[float, float, float]
    branch_directions: List[Tuple[float, float, float]]
    trunk_direction: Tuple[float, float, float]


@dataclass
class PipeNetwork:
    """
    Represents a pipe network for a single fixture + system type.

    For a double sink sanitary system:
    - branches: [[Drain1→Merge], [Drain2→Merge]] - unique per connector
    - trunk: [Merge→Wall→Down] - shared, created once
    - merge_point: location where branches join
    - merge_info: geometry for wye fitting insertion (trimmed endpoints)
    """
    system_type: str
    fixture_id: int
    branches: List[List[PipeSegment]] = field(default_factory=list)
    trunk: List[PipeSegment] = field(default_factory=list)
    merge_point: Optional[Tuple[float, float, float]] = None
    merge_info: Optional[MergePointInfo] = None

    def get_total_segment_count(self) -> int:
        """Total segments to create (branches + trunk)."""
        branch_count = sum(len(b) for b in self.branches)
        return branch_count + len(self.trunk)

    def needs_tee_fitting(self) -> bool:
        """True if multiple branches merge (need T-fitting)."""
        return len(self.branches) > 1 and self.merge_point is not None


# =============================================================================
# System Type Mapping
# =============================================================================

# Map our system type strings to Revit PipingSystemType names
SYSTEM_TYPE_MAPPING = {
    "Sanitary": "Sanitary",
    "DomesticColdWater": "Domestic Cold Water",
    "DomesticHotWater": "Domestic Hot Water",
    "Vent": "Sanitary Vent",
}


def get_revit_system_type_name(system_type: str) -> str:
    """
    Get Revit piping system type name from our system type string.

    Args:
        system_type: Our system type (e.g., "Sanitary", "DomesticColdWater")

    Returns:
        Revit system type name (e.g., "Sanitary", "Domestic Cold Water")
    """
    return SYSTEM_TYPE_MAPPING.get(system_type, system_type)


# =============================================================================
# Route Parsing
# =============================================================================

def parse_routes_json(routes_json: str) -> List[Dict[str, Any]]:
    """
    Parse routes JSON string to list of route dictionaries.

    Args:
        routes_json: JSON string from pipe router component

    Returns:
        List of route dictionaries
    """
    try:
        data = json.loads(routes_json)
        return data.get("routes", [])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse routes JSON: {e}")
        return []


def extract_segments_from_route(route: Dict[str, Any]) -> List[PipeSegment]:
    """
    Extract pipe segments from a single route.

    Each consecutive pair of path_points becomes one segment.

    Args:
        route: Route dictionary with path_points, system_type, etc.

    Returns:
        List of PipeSegment objects
    """
    segments = []

    path_points = route.get("path_points", [])
    if len(path_points) < 2:
        return segments

    route_id = route.get("id", "unknown")
    system_type = route.get("system_type", "Unknown")

    # Get pipe_size - handle None values explicitly
    # Default to 1.5" (0.125 ft) for sanitary, 0.5" (0.0417 ft) for supply
    raw_pipe_size = route.get("pipe_size")
    if raw_pipe_size is None or raw_pipe_size <= 0:
        # Use sensible defaults based on system type
        if "sanitary" in system_type.lower():
            pipe_size = 0.125  # 1.5" for drains
        elif "vent" in system_type.lower():
            pipe_size = 0.125  # 1.5" for vents
        else:
            pipe_size = 0.0417  # 0.5" for supply water
    else:
        pipe_size = raw_pipe_size

    for i in range(len(path_points) - 1):
        start = path_points[i]
        end = path_points[i + 1]

        # Handle both dict and tuple formats
        if isinstance(start, dict):
            start_pt = (start.get("x", 0), start.get("y", 0), start.get("z", 0))
        else:
            start_pt = tuple(start)

        if isinstance(end, dict):
            end_pt = (end.get("x", 0), end.get("y", 0), end.get("z", 0))
        else:
            end_pt = tuple(end)

        segment = PipeSegment(
            start_point=start_pt,
            end_point=end_pt,
            system_type=system_type,
            pipe_size=pipe_size,
            route_id=route_id,
            segment_index=i,
            is_branch=True  # Will be updated by network builder
        )
        segments.append(segment)

    return segments


def parse_routes_to_segments(routes_json: str) -> List[PipeSegment]:
    """
    Parse all routes to flat list of segments.

    Note: This does NOT handle merge detection. Use build_pipe_networks()
    for proper branch/trunk handling.

    Args:
        routes_json: JSON string from pipe router

    Returns:
        Flat list of all segments from all routes
    """
    routes = parse_routes_json(routes_json)
    all_segments = []

    for route in routes:
        segments = extract_segments_from_route(route)
        all_segments.extend(segments)

    return all_segments


# =============================================================================
# Route Grouping
# =============================================================================

def group_routes_by_fixture_system(routes: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """
    Group routes by fixture ID and system type.

    This groups routes that should share a trunk (e.g., two sanitary
    drains from the same sink).

    Args:
        routes: List of route dictionaries

    Returns:
        Dictionary with keys like "12345_Sanitary" -> list of routes
    """
    groups = {}

    for route in routes:
        # Extract fixture ID from start_connector_id (format: "elementId_connectorIndex")
        connector_id = route.get("start_connector_id", "")
        parts = connector_id.split("_")
        fixture_id = parts[0] if parts else "unknown"

        system_type = route.get("system_type", "Unknown")
        group_key = f"{fixture_id}_{system_type}"

        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(route)

    return groups


# =============================================================================
# Merge Point Detection
# =============================================================================

def points_equal(p1: Tuple, p2: Tuple, tolerance: float = 0.01) -> bool:
    """Check if two points are equal within tolerance."""
    dx = abs(p1[0] - p2[0])
    dy = abs(p1[1] - p2[1])
    dz = abs(p1[2] - p2[2])
    return dx < tolerance and dy < tolerance and dz < tolerance


def find_merge_point(routes: List[Dict[str, Any]]) -> Optional[Tuple[float, float, float]]:
    """
    Find the merge point where multiple routes converge.

    The merge point is where path_points from different routes
    start sharing the same coordinates.

    Args:
        routes: Routes from the same fixture + system type

    Returns:
        Merge point coordinates, or None if routes don't merge
    """
    if len(routes) < 2:
        return None

    # Get path points from first route
    route1_points = routes[0].get("path_points", [])
    if not route1_points:
        return None

    # Convert to tuples
    def to_tuple(p):
        if isinstance(p, dict):
            return (p.get("x", 0), p.get("y", 0), p.get("z", 0))
        return tuple(p)

    route1_pts = [to_tuple(p) for p in route1_points]

    # Check each point in route1 against other routes
    for i, pt1 in enumerate(route1_pts):
        # Check if this point exists in all other routes
        all_have_point = True
        for other_route in routes[1:]:
            other_points = [to_tuple(p) for p in other_route.get("path_points", [])]
            found = any(points_equal(pt1, opt) for opt in other_points)
            if not found:
                all_have_point = False
                break

        if all_have_point and i > 0:  # Skip connector origin (i=0)
            return pt1

    return None


def find_merge_point_index(path_points: List, merge_point: Tuple) -> int:
    """
    Find the index of merge point in path_points.

    Args:
        path_points: List of points (dict or tuple)
        merge_point: The merge point to find

    Returns:
        Index of merge point, or -1 if not found
    """
    for i, pt in enumerate(path_points):
        if isinstance(pt, dict):
            pt_tuple = (pt.get("x", 0), pt.get("y", 0), pt.get("z", 0))
        else:
            pt_tuple = tuple(pt)

        if points_equal(pt_tuple, merge_point):
            return i

    return -1


# =============================================================================
# Merge Geometry Calculation
# =============================================================================

def calculate_merge_geometry(
    merge_point: Tuple[float, float, float],
    branches: List[List[PipeSegment]],
    trunk: List[PipeSegment],
    gap_distance: float = WYE_FITTING_GAP
) -> Optional[MergePointInfo]:
    """Calculate trimmed endpoints for wye fitting insertion.

    Creates a gap at the merge point where branches meet the trunk, allowing
    Revit's NewTeeFitting to connect three separate pipe ends.

    Args:
        merge_point: The original merge point coordinates
        branches: List of branch segment lists (each branch ends at merge)
        trunk: Trunk segment list (trunk starts at merge)
        gap_distance: Distance to pull back endpoints from merge point

    Returns:
        MergePointInfo with trimmed endpoints, or None if calculation fails
    """
    print(f"[CALC_MERGE] Called with merge_point={merge_point}, {len(branches)} branches, {len(trunk)} trunk segments")

    if not merge_point:
        print("[CALC_MERGE] ERROR: merge_point is None/empty")
        return None

    branch_endpoints = []
    branch_directions = []

    # Process each branch - find direction and calculate trimmed endpoint
    for branch_segments in branches:
        if not branch_segments:
            continue

        last_seg = branch_segments[-1]

        # Direction from segment start toward end (toward merge point)
        direction = vector_subtract(last_seg.end_point, last_seg.start_point)
        direction = vector_normalize(direction)

        # Validate we have a valid direction
        if vector_length(direction) < 0.001:
            logger.warning("Branch has zero-length direction vector")
            continue

        # Trim endpoint: move back from merge point along branch direction
        # This creates a gap for the fitting
        offset = vector_scale(direction, gap_distance)
        trimmed_endpoint = vector_subtract(merge_point, offset)

        # Verify the trimmed endpoint doesn't go past the segment start
        seg_length = last_seg.get_length()
        if seg_length < gap_distance + MIN_PIPE_LENGTH:
            # Reduce gap to leave minimum pipe length
            adjusted_gap = max(0, seg_length - MIN_PIPE_LENGTH)
            offset = vector_scale(direction, adjusted_gap)
            trimmed_endpoint = vector_subtract(merge_point, offset)
            logger.info(f"Adjusted gap from {gap_distance:.3f} to {adjusted_gap:.3f} for short branch")

        branch_endpoints.append(trimmed_endpoint)
        branch_directions.append(direction)

    # Process trunk - find direction and calculate trimmed startpoint
    if trunk:
        first_seg = trunk[0]
        # Direction from merge point toward trunk end
        trunk_dir = vector_subtract(first_seg.end_point, first_seg.start_point)
        trunk_dir = vector_normalize(trunk_dir)

        # Validate trunk direction
        if vector_length(trunk_dir) < 0.001:
            trunk_dir = (0.0, 0.0, -1.0)  # Default: down
            logger.warning("Trunk has zero-length direction, using default (0,0,-1)")

        # Trim startpoint: move forward from merge point along trunk direction
        offset = vector_scale(trunk_dir, gap_distance)
        trunk_start = vector_add(merge_point, offset)

        # Verify the trimmed startpoint doesn't go past segment end
        seg_length = first_seg.get_length()
        if seg_length < gap_distance + MIN_PIPE_LENGTH:
            adjusted_gap = max(0, seg_length - MIN_PIPE_LENGTH)
            offset = vector_scale(trunk_dir, adjusted_gap)
            trunk_start = vector_add(merge_point, offset)
            logger.info(f"Adjusted trunk gap from {gap_distance:.3f} to {adjusted_gap:.3f}")
    else:
        # No trunk segments - use default direction
        trunk_dir = (0.0, 0.0, -1.0)  # Default: down
        offset = vector_scale(trunk_dir, gap_distance)
        trunk_start = vector_add(merge_point, offset)
        logger.info("No trunk segments, using default direction (down)")

    if not branch_endpoints:
        logger.warning("No valid branch endpoints calculated")
        return None

    return MergePointInfo(
        original_point=merge_point,
        branch_endpoints=branch_endpoints,
        trunk_startpoint=trunk_start,
        branch_directions=branch_directions,
        trunk_direction=trunk_dir
    )


def apply_merge_trimming(network: 'PipeNetwork') -> None:
    """Apply trimmed endpoints from merge_info to actual pipe segments.

    NOTE: After extensive testing, we found that trimming pipes PREVENTS
    Revit from inserting tee/cross fittings. For NewTeeFitting to work,
    all connectors must be at the EXACT same location.

    This function now does NO trimming - all pipes meet at the merge point.
    The merge_info is still calculated for reference but not applied.

    Args:
        network: PipeNetwork with merge_info already calculated
    """
    if network.merge_info is None:
        return

    # NO TRIMMING - all pipes must meet at exact merge point for NewTeeFitting to work
    # If we trim, ConnectTo just extends pipes without inserting fittings
    print(f"[APPLY_TRIM] NO trimming applied - all pipes meet at merge point")
    print(f"[APPLY_TRIM] Branch endpoints remain at merge point: {network.merge_info.original_point}")
    print(f"[APPLY_TRIM] Trunk starts at merge point: {network.trunk[0].start_point if network.trunk else 'N/A'}")


# =============================================================================
# Pipe Network Building
# =============================================================================

def build_pipe_network(
    fixture_id: int,
    system_type: str,
    routes: List[Dict[str, Any]]
) -> PipeNetwork:
    """
    Build a pipe network from routes of the same fixture + system.

    Handles:
    - Single route: all segments are "trunk" (no merge)
    - Multiple routes: detect merge point, separate branch/trunk

    Args:
        fixture_id: Parent fixture Revit element ID
        system_type: System type string
        routes: Routes to process (same fixture + system)

    Returns:
        PipeNetwork with branches and trunk separated
    """
    network = PipeNetwork(
        system_type=system_type,
        fixture_id=fixture_id
    )

    if not routes:
        return network

    # Single route case: no merge needed
    if len(routes) == 1:
        segments = extract_segments_from_route(routes[0])
        # All segments are "trunk" (no branching)
        for seg in segments:
            seg.is_branch = False
        network.trunk = segments
        return network

    # Multiple routes: find merge point
    merge_point = find_merge_point(routes)
    network.merge_point = merge_point

    if merge_point is None:
        # No common merge point found - treat all as separate trunks
        logger.warning(f"No merge point found for fixture {fixture_id} {system_type}")
        for route in routes:
            segments = extract_segments_from_route(route)
            for seg in segments:
                seg.is_branch = False
            network.branches.append(segments)  # Store as separate "branches"
        return network

    # Split each route into branch (before merge) and trunk (after merge)
    trunk_set = False

    for route in routes:
        path_points = route.get("path_points", [])
        merge_idx = find_merge_point_index(path_points, merge_point)

        if merge_idx < 0:
            # Route doesn't contain merge point - add all as branch
            segments = extract_segments_from_route(route)
            network.branches.append(segments)
            continue

        # Extract branch segments (connector → merge)
        branch_segments = []
        all_segments = extract_segments_from_route(route)

        for i, seg in enumerate(all_segments):
            if i < merge_idx:
                seg.is_branch = True
                branch_segments.append(seg)
            else:
                seg.is_branch = False
                # Only add trunk once (shared by all routes)
                if not trunk_set:
                    network.trunk.append(seg)

        network.branches.append(branch_segments)
        trunk_set = True

    # Calculate merge geometry for wye fitting insertion (for 2+ branches)
    if network.merge_point is not None and len(network.branches) >= 2:
        print(f"[PIPE_CREATOR] Calculating merge geometry for {len(network.branches)} branches")
        print(f"[PIPE_CREATOR] Merge point: {network.merge_point}")
        print(f"[PIPE_CREATOR] Branch counts: {[len(b) for b in network.branches]}")
        print(f"[PIPE_CREATOR] Trunk segments: {len(network.trunk)}")

        network.merge_info = calculate_merge_geometry(
            network.merge_point,
            network.branches,
            network.trunk
        )

        if network.merge_info is not None:
            # Apply trimming to create gaps for wye fitting
            apply_merge_trimming(network)
            print(f"[PIPE_CREATOR] Applied merge trimming: {len(network.merge_info.branch_endpoints)} branch endpoints")
            print(f"[PIPE_CREATOR] Trunk startpoint: {network.merge_info.trunk_startpoint}")
        else:
            print("[PIPE_CREATOR] WARNING: Failed to calculate merge geometry")

    return network


def build_all_pipe_networks(routes_json: str) -> List[PipeNetwork]:
    """
    Build pipe networks for all fixtures and system types.

    Args:
        routes_json: JSON string from pipe router

    Returns:
        List of PipeNetwork objects, one per fixture+system combination
    """
    routes = parse_routes_json(routes_json)
    groups = group_routes_by_fixture_system(routes)

    networks = []
    for group_key, group_routes in groups.items():
        parts = group_key.split("_", 1)
        fixture_id = int(parts[0]) if parts[0].isdigit() else 0
        system_type = parts[1] if len(parts) > 1 else "Unknown"

        network = build_pipe_network(fixture_id, system_type, group_routes)
        networks.append(network)

    logger.info(f"Built {len(networks)} pipe networks from {len(routes)} routes")
    return networks


# =============================================================================
# Summary and Debug
# =============================================================================

def get_networks_summary(networks: List[PipeNetwork]) -> Dict[str, Any]:
    """
    Generate summary statistics for pipe networks.

    Args:
        networks: List of PipeNetwork objects

    Returns:
        Summary dictionary
    """
    total_branches = 0
    total_trunk_segments = 0
    tee_fittings_needed = 0

    by_system = {}

    for network in networks:
        branch_count = sum(len(b) for b in network.branches)
        trunk_count = len(network.trunk)
        total_branches += branch_count
        total_trunk_segments += trunk_count

        if network.needs_tee_fitting():
            tee_fittings_needed += 1

        st = network.system_type
        if st not in by_system:
            by_system[st] = {"networks": 0, "branches": 0, "trunk": 0}
        by_system[st]["networks"] += 1
        by_system[st]["branches"] += branch_count
        by_system[st]["trunk"] += trunk_count

    return {
        "total_networks": len(networks),
        "total_branch_segments": total_branches,
        "total_trunk_segments": total_trunk_segments,
        "total_segments": total_branches + total_trunk_segments,
        "tee_fittings_needed": tee_fittings_needed,
        "by_system_type": by_system
    }
