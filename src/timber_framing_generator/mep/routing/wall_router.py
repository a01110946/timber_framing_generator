# File: src/timber_framing_generator/mep/routing/wall_router.py
"""Phase 2: In-Wall MEP Router (cavity-based).

Routes MEP pipes/conduits through wall cavities from penetration points
(Phase 1 output) to wall exit points (top plate, bottom plate, or side edge).

Uses cavity decomposition instead of grid-based A*:
- Each pipe is assigned to a cavity (rectangular void between studs/plates)
- Pipes edge-pack against cavity walls (nearest edge + radius + gap)
- Routes are trivially vertical within a cavity (zero stud crossings)
- Cross-cavity routes (rare, stud-snap cases) use 2-segment L-shapes

Supports progressive refinement:
- walls_json alone: derives studs at configured spacing
- walls_json + framing_json + cell_json: uses exact framing element positions

Follows the user-in-the-loop design philosophy (Issue #37):
- Reports unrouted penetrations with actionable guidance
- Status output: "ready" if all routed, "needs_input" if some failed
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .occupancy import OccupancyMap, OccupiedSegment
from .route_segment import Route, RouteSegment, SegmentDirection

from ...cavity import (
    Cavity,
    CavityConfig,
    decompose_wall_cavities,
    find_cavity_for_uv,
    find_nearest_cavity,
)

logger = logging.getLogger(__name__)


# --- Exit point rules ---
# Maps system_type to preferred exit edge.

EXIT_POINT_RULES: Dict[str, str] = {
    "Sanitary": "bottom",
    "DomesticColdWater": "bottom",
    "DomesticHotWater": "bottom",
    "Vent": "top",
}

DEFAULT_EXIT_EDGE = "bottom"


# --- Dataclasses ---

@dataclass
class WallExitPoint:
    """Where a route exits the wall cavity.

    Provides the handoff point for Phase 3 (wall-to-wall connector).

    Attributes:
        wall_id: ID of the wall containing this exit.
        exit_edge: Which edge the route exits through ("top", "bottom").
        wall_uv: UV position on the exit edge.
        world_location: World XYZ of the exit point.
        system_type: MEP system type.
        connector_id: ID of the originating connector.
    """

    wall_id: str
    exit_edge: str
    wall_uv: Tuple[float, float]
    world_location: Tuple[float, float, float]
    system_type: str
    connector_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "wall_id": self.wall_id,
            "exit_edge": self.exit_edge,
            "wall_uv": list(self.wall_uv),
            "world_location": list(self.world_location),
            "system_type": self.system_type,
            "connector_id": self.connector_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WallExitPoint":
        """Deserialize from dict."""
        return cls(
            wall_id=data["wall_id"],
            exit_edge=data["exit_edge"],
            wall_uv=tuple(data["wall_uv"]),
            world_location=tuple(data["world_location"]),
            system_type=data["system_type"],
            connector_id=data["connector_id"],
        )


@dataclass
class WallRoute:
    """A single in-wall route from penetration to exit.

    Attributes:
        connector_id: ID of the originating connector.
        system_type: MEP system type.
        wall_id: ID of the wall containing this route.
        entry_uv: UV position where the pipe enters the wall.
        exit_uv: UV position where the pipe exits the wall.
        exit_edge: Which edge the route exits through.
        route: Route object with path segments.
        stud_crossings: Number of framing members penetrated.
        fixture_type: Normalized fixture type (from Phase 1).
    """

    connector_id: str
    system_type: str
    wall_id: str
    entry_uv: Tuple[float, float]
    exit_uv: Tuple[float, float]
    exit_edge: str
    route: Route
    stud_crossings: int
    fixture_type: Optional[str] = None
    world_segments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result: Dict[str, Any] = {
            "connector_id": self.connector_id,
            "system_type": self.system_type,
            "wall_id": self.wall_id,
            "entry_uv": list(self.entry_uv),
            "exit_uv": list(self.exit_uv),
            "exit_edge": self.exit_edge,
            "route": self.route.to_dict(),
            "stud_crossings": self.stud_crossings,
        }
        if self.fixture_type is not None:
            result["fixture_type"] = self.fixture_type
        if self.world_segments:
            result["world_segments"] = self.world_segments
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WallRoute":
        """Deserialize from dict."""
        return cls(
            connector_id=data["connector_id"],
            system_type=data["system_type"],
            wall_id=data["wall_id"],
            entry_uv=tuple(data["entry_uv"]),
            exit_uv=tuple(data["exit_uv"]),
            exit_edge=data["exit_edge"],
            route=Route.from_dict(data["route"]),
            stud_crossings=data["stud_crossings"],
            fixture_type=data.get("fixture_type"),
            world_segments=data.get("world_segments", []),
        )


@dataclass
class UnroutedPenetration:
    """A penetration that could not be routed through the wall.

    Attributes:
        connector_id: ID of the originating connector.
        system_type: MEP system type.
        wall_id: ID of the wall.
        entry_uv: UV position of the penetration.
        reason: Human-readable explanation of why routing failed.
    """

    connector_id: str
    system_type: str
    wall_id: str
    entry_uv: Tuple[float, float]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "connector_id": self.connector_id,
            "system_type": self.system_type,
            "wall_id": self.wall_id,
            "entry_uv": list(self.entry_uv),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnroutedPenetration":
        """Deserialize from dict."""
        return cls(
            connector_id=data["connector_id"],
            system_type=data["system_type"],
            wall_id=data["wall_id"],
            entry_uv=tuple(data["entry_uv"]),
            reason=data["reason"],
        )


@dataclass
class WallRoutingResult:
    """Complete Phase 2 result.

    Attributes:
        wall_routes: Successfully routed in-wall paths.
        exit_points: Exit points for downstream Phase 3.
        unrouted: Penetrations that could not be routed.
        floor_passthroughs: Floor penetrations passed through unchanged.
        status: "ready" if all routed, "needs_input" if some failed.
        needs: Actionable guidance for unrouted penetrations.
        obstacle_source: "derived" (configured spacing), "framing" (exact),
            or "mixed".
    """

    wall_routes: List[WallRoute] = field(default_factory=list)
    exit_points: List[WallExitPoint] = field(default_factory=list)
    unrouted: List[UnroutedPenetration] = field(default_factory=list)
    floor_passthroughs: List[Dict] = field(default_factory=list)
    status: str = "ready"
    needs: List[str] = field(default_factory=list)
    obstacle_source: str = "derived"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "wall_routes": [r.to_dict() for r in self.wall_routes],
            "exit_points": [e.to_dict() for e in self.exit_points],
            "unrouted": [u.to_dict() for u in self.unrouted],
            "floor_passthroughs": self.floor_passthroughs,
            "status": self.status,
            "needs": self.needs,
            "obstacle_source": self.obstacle_source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WallRoutingResult":
        """Deserialize from dict."""
        return cls(
            wall_routes=[
                WallRoute.from_dict(r) for r in data.get("wall_routes", [])
            ],
            exit_points=[
                WallExitPoint.from_dict(e) for e in data.get("exit_points", [])
            ],
            unrouted=[
                UnroutedPenetration.from_dict(u)
                for u in data.get("unrouted", [])
            ],
            floor_passthroughs=data.get("floor_passthroughs", []),
            status=data.get("status", "ready"),
            needs=data.get("needs", []),
            obstacle_source=data.get("obstacle_source", "derived"),
        )


# --- Exit point selection ---


def _select_exit_point(
    penetration: Dict[str, Any],
    wall: Dict[str, Any],
    plate_thickness: float = 0.125,
) -> Tuple[str, float]:
    """Select exit edge and exit V for a penetration.

    Uses system_type to determine preferred exit edge (top/bottom).
    Exit V is placed just inside the plate zone with clearance.

    Args:
        penetration: Penetration dict from Phase 1.
        wall: Wall data dict.
        plate_thickness: Plate thickness in feet.

    Returns:
        Tuple of (exit_edge, exit_v).
    """
    system_type = penetration.get("system_type", "")
    wall_height = float(wall.get("wall_height", wall.get("height", 8.0)))

    exit_edge = EXIT_POINT_RULES.get(system_type, DEFAULT_EXIT_EDGE)

    clearance = 0.042  # ~0.5 inch from plate edge
    if exit_edge == "top":
        exit_v = wall_height - plate_thickness - clearance
    else:
        exit_v = plate_thickness + clearance

    return exit_edge, exit_v


def _uv_to_world(
    uv: Tuple[float, float],
    wall: Dict[str, Any],
) -> Tuple[float, float, float]:
    """Convert wall UV coordinates to world XYZ.

    Args:
        uv: (u, v) position on wall face.
        wall: Wall data dict with base_plane.

    Returns:
        (x, y, z) world coordinates.
    """
    u, v = uv
    bp = wall["base_plane"]
    origin = bp["origin"]
    x_axis = bp["x_axis"]
    base_elev = float(wall.get("base_elevation", origin.get("z", 0.0)))

    ox, oy = float(origin["x"]), float(origin["y"])
    xx, xy = float(x_axis["x"]), float(x_axis["y"])

    world_x = ox + xx * u
    world_y = oy + xy * u
    world_z = base_elev + v

    return (world_x, world_y, world_z)


def _count_stud_crossings(route: Route) -> int:
    """Count how many framing member crossings a route makes."""
    return sum(1 for seg in route.segments if seg.crosses_obstacle)


# --- Cavity-based routing helpers ---


def _edge_pack_u(
    cavity: Cavity,
    entry_u: float,
    pipe_radius: float,
    tolerance_gap: float,
    occupancy: OccupancyMap,
    wall_id: str,
) -> float:
    """Find the best U position within a cavity for a pipe.

    Strategy: prefer straight vertical drop at entry_u. Only shift
    when entry_u collides with an existing pipe or is outside the cavity.
    When shifting is needed, scan outward from entry_u in both directions
    to minimize horizontal jog distance.

    Args:
        cavity: Target cavity.
        entry_u: Original U-coordinate of the penetration.
        pipe_radius: Pipe outer radius in feet.
        tolerance_gap: Minimum clearance from cavity edge and other pipes.
        occupancy: OccupancyMap tracking reserved pipe space.
        wall_id: Wall ID for occupancy lookup.

    Returns:
        U-coordinate for the pipe within the cavity.
    """
    pipe_diameter = pipe_radius * 2.0
    min_u = cavity.u_min + pipe_radius + tolerance_gap
    max_u = cavity.u_max - pipe_radius - tolerance_gap

    # Clamp entry_u into the valid cavity range
    clamped_u = max(min_u, min(entry_u, max_u))

    # Try the clamped entry position first (straight vertical drop)
    available, _ = occupancy.is_available(
        wall_id,
        ((clamped_u, cavity.v_min), (clamped_u, cavity.v_max)),
        pipe_diameter,
        tolerance_gap,
    )
    if available:
        return clamped_u

    # Collision detected -- scan outward from clamped_u in both directions
    step = pipe_diameter + tolerance_gap
    left_u = clamped_u - step
    right_u = clamped_u + step

    while left_u >= min_u or right_u <= max_u:
        # Try left
        if left_u >= min_u:
            available, _ = occupancy.is_available(
                wall_id,
                ((left_u, cavity.v_min), (left_u, cavity.v_max)),
                pipe_diameter,
                tolerance_gap,
            )
            if available:
                return left_u
            left_u -= step

        # Try right
        if right_u <= max_u:
            available, _ = occupancy.is_available(
                wall_id,
                ((right_u, cavity.v_min), (right_u, cavity.v_max)),
                pipe_diameter,
                tolerance_gap,
            )
            if available:
                return right_u
            right_u += step

    # Fallback: cavity center (all positions occupied)
    return cavity.center_u


def _create_route(
    conn_id: str,
    system_type: str,
    wall_id: str,
    entry_uv: Tuple[float, float],
    packed_u: float,
    exit_v: float,
    crosses_stud: bool,
) -> Tuple[Route, int]:
    """Create the in-wall route from entry to exit.

    For most cases this is a single vertical segment (zero stud crossings).
    When the packed_u differs from entry_u (stud snap), a horizontal
    segment is prepended.

    Args:
        conn_id: Connector ID.
        system_type: MEP system type.
        wall_id: Wall ID.
        entry_uv: Original penetration (u, v).
        packed_u: Edge-packed U position in the assigned cavity.
        exit_v: Exit V position (near plate).
        crosses_stud: Whether the horizontal jog crosses a stud.

    Returns:
        Tuple of (Route, stud_crossings).
    """
    entry_u, entry_v = entry_uv
    segments: List[RouteSegment] = []
    stud_crossings = 0

    # Horizontal jog (if entry_u != packed_u)
    if abs(entry_u - packed_u) > 1e-6:
        segments.append(RouteSegment(
            start=(entry_u, entry_v),
            end=(packed_u, entry_v),
            direction=SegmentDirection.HORIZONTAL,
            domain_id=wall_id,
            crosses_obstacle=crosses_stud,
            obstacle_type="stud" if crosses_stud else None,
        ))
        if crosses_stud:
            stud_crossings = 1

    # Vertical segment (main drop/rise)
    start_v = entry_v
    if abs(start_v - exit_v) > 1e-6:
        segments.append(RouteSegment(
            start=(packed_u, start_v),
            end=(packed_u, exit_v),
            direction=SegmentDirection.VERTICAL,
            domain_id=wall_id,
        ))

    exit_uv = (packed_u, exit_v)
    route = Route(
        id=f"wall_route_{conn_id}",
        system_type=system_type,
        segments=segments,
        source=entry_uv,
        target=exit_uv,
    )
    return route, stud_crossings


# --- Core routing ---


def route_wall(
    wall_id: str,
    penetrations: List[Dict[str, Any]],
    wall: Dict[str, Any],
    framing: Optional[Dict[str, Any]] = None,
    cell_data: Optional[Dict[str, Any]] = None,
    occupancy: Optional[OccupancyMap] = None,
    pipe_radius: float = 0.0417,
    tolerance_gap: float = 0.0417,
) -> WallRoutingResult:
    """Route all penetrations for a single wall using cavity-based routing.

    Steps:
    1. Decompose wall into cavities (framing mode or derived mode)
    2. For each penetration:
       a. Assign to a cavity (or nearest if on a stud)
       b. Edge-pack U within the cavity
       c. Select exit edge and V from system_type
       d. Create route (vertical segment, optional horizontal jog)
       e. Reserve space in occupancy map
    3. Return results with routes, unrouted, stats

    Args:
        wall_id: Wall identifier.
        penetrations: List of penetration dicts from Phase 1.
        wall: Wall data dict from walls_json.
        framing: Optional framing data dict from framing_json.
        cell_data: Optional cell decomposition dict.
        occupancy: Optional shared OccupancyMap (created internally if None).
        pipe_radius: Pipe outer radius in feet (~1" OD default).
        tolerance_gap: Clearance between pipe and cavity edge/other pipes.

    Returns:
        WallRoutingResult for this wall.
    """
    result = WallRoutingResult()

    if not penetrations:
        return result

    # Determine obstacle source
    if framing and cell_data:
        obstacle_source = "framing"
    else:
        obstacle_source = "derived"
    result.obstacle_source = obstacle_source

    # Build wall_data dict for cavity decomposer
    wall_length = float(wall.get("wall_length", wall.get("length", 10.0)))
    wall_height = float(wall.get("wall_height", wall.get("height", 8.0)))
    wall_thickness = float(wall.get("wall_thickness", 0.292))

    cavity_wall_data = {
        "wall_id": wall_id,
        "wall_length": wall_length,
        "wall_height": wall_height,
        "wall_thickness": wall_thickness,
        "openings": wall.get("openings", []),
    }

    # Decompose wall into cavities
    cavities = decompose_wall_cavities(
        cavity_wall_data,
        cell_data=cell_data,
        framing_data=framing,
        config=CavityConfig(),
    )

    if not cavities:
        for pen in penetrations:
            result.unrouted.append(UnroutedPenetration(
                connector_id=pen.get("connector_id", "unknown"),
                system_type=pen.get("system_type", "unknown"),
                wall_id=wall_id,
                entry_uv=tuple(pen.get("wall_uv", [0, 0])),
                reason="No cavities found in wall (wall may be too short or fully blocked)",
            ))
        result.status = "needs_input"
        return result

    # Create internal occupancy map if not provided
    if occupancy is None:
        occupancy = OccupancyMap()

    # Route each penetration
    for pen in penetrations:
        conn_id = pen.get("connector_id", "unknown")
        system_type = pen.get("system_type", "unknown")
        wall_uv = pen.get("wall_uv", [0, 0])
        entry_uv = (float(wall_uv[0]), float(wall_uv[1]))
        fixture_type = pen.get("fixture_type")
        entry_u, entry_v = entry_uv

        # 1. Find cavity for this penetration
        cavity = find_cavity_for_uv(cavities, entry_u, entry_v)
        crosses_stud = False

        if cavity is None:
            # Entry point is on a stud or outside cavities -> snap to nearest
            cavity = find_nearest_cavity(cavities, entry_u, entry_v)
            if cavity is None:
                result.unrouted.append(UnroutedPenetration(
                    connector_id=conn_id,
                    system_type=system_type,
                    wall_id=wall_id,
                    entry_uv=entry_uv,
                    reason="No suitable cavity found near penetration point",
                ))
                continue
            crosses_stud = True  # Snapping from stud to cavity crosses a member

        # 2. Edge-pack U within the cavity
        packed_u = _edge_pack_u(
            cavity, entry_u, pipe_radius, tolerance_gap, occupancy, wall_id,
        )

        # 3. Determine exit edge and V
        exit_edge, exit_v = _select_exit_point(pen, wall)

        # 4. Create route
        exit_uv = (packed_u, exit_v)
        route, stud_crossings = _create_route(
            conn_id, system_type, wall_id,
            entry_uv, packed_u, exit_v, crosses_stud,
        )

        # 5. Reserve space in occupancy map
        occupancy.reserve(wall_id, OccupiedSegment(
            route_id=f"wall_route_{conn_id}",
            system_type=system_type,
            trade="plumbing",
            start=(packed_u, min(entry_v, exit_v)),
            end=(packed_u, max(entry_v, exit_v)),
            diameter=pipe_radius * 2.0,
        ))

        # 6. Compute world-coordinate segments for visualization
        world_segs: List[Dict[str, Any]] = []
        for seg in route.segments:
            ws = _uv_to_world(seg.start, wall)
            we = _uv_to_world(seg.end, wall)
            world_segs.append({"start": list(ws), "end": list(we)})

        # 7. Create WallRoute
        wall_route = WallRoute(
            connector_id=conn_id,
            system_type=system_type,
            wall_id=wall_id,
            entry_uv=entry_uv,
            exit_uv=exit_uv,
            exit_edge=exit_edge,
            route=route,
            stud_crossings=stud_crossings,
            fixture_type=fixture_type,
            world_segments=world_segs,
        )
        result.wall_routes.append(wall_route)

        # Create exit point
        world_loc = _uv_to_world(exit_uv, wall)
        exit_point = WallExitPoint(
            wall_id=wall_id,
            exit_edge=exit_edge,
            wall_uv=exit_uv,
            world_location=world_loc,
            system_type=system_type,
            connector_id=conn_id,
        )
        result.exit_points.append(exit_point)

        logger.debug(
            "Routed %s in wall %s: entry=(%.2f, %.2f) -> exit=(%.2f, %.2f) "
            "%s, %d stud crossings, cost=%.2f, cavity=%s",
            conn_id, wall_id,
            entry_uv[0], entry_uv[1],
            exit_uv[0], exit_uv[1],
            exit_edge, stud_crossings,
            route.total_cost, cavity.id,
        )

    # Set status
    if result.unrouted:
        result.status = "needs_input"
        for ur in result.unrouted:
            result.needs.append(
                f"{ur.connector_id} ({ur.system_type}) in wall {ur.wall_id}: "
                f"{ur.reason}"
            )

    return result


def route_all_walls(
    penetrations_json: Dict[str, Any],
    walls_json: Dict[str, Any],
    framing_json: Optional[Dict[str, Any]] = None,
    cell_json: Optional[Dict[str, Any]] = None,
) -> WallRoutingResult:
    """Main entry point for Phase 2.

    Groups penetrations by wall_id, routes each wall independently.
    Floor penetrations (target="floor") are passed through unchanged.

    Args:
        penetrations_json: Phase 1 output with "penetrations" list.
        walls_json: Wall analyzer output with "walls" list.
        framing_json: Optional framing generator output. Can be a single
            wall's framing dict or a list under "walls" key.
        cell_json: Optional cell decomposition output. Can be a single
            wall's cell data or a list under "walls" key.

    Returns:
        WallRoutingResult with all routes, exit points, and floor passthroughs.
    """
    result = WallRoutingResult()

    penetrations = penetrations_json.get("penetrations", [])
    walls = walls_json.get("walls", [])

    if not penetrations:
        logger.warning("No penetrations provided")
        return result

    if not walls:
        logger.warning("No walls provided")
        result.status = "needs_input"
        result.needs.append("No walls provided in walls_json")
        return result

    # Build wall lookup
    wall_lookup: Dict[str, Dict[str, Any]] = {
        w["wall_id"]: w for w in walls
    }

    # Build framing lookup (optional)
    framing_lookup: Dict[str, Dict[str, Any]] = {}
    if framing_json:
        if "walls" in framing_json:
            for fw in framing_json["walls"]:
                fid = fw.get("wall_id", "")
                if fid:
                    framing_lookup[fid] = fw
        elif "wall_id" in framing_json:
            fid = framing_json["wall_id"]
            framing_lookup[fid] = framing_json

    # Build cell data lookup (optional)
    cell_lookup: Dict[str, Dict[str, Any]] = {}
    if cell_json:
        if "walls" in cell_json:
            for cw in cell_json["walls"]:
                cid = cw.get("wall_id", "")
                if cid:
                    cell_lookup[cid] = cw
        elif "wall_id" in cell_json:
            cid = cell_json["wall_id"]
            cell_lookup[cid] = cell_json

    # Shared occupancy map across all walls
    occupancy = OccupancyMap()

    # Separate floor penetrations from wall penetrations
    wall_penetrations: Dict[str, List[Dict[str, Any]]] = {}

    for pen in penetrations:
        target = pen.get("target", "wall")
        if target == "floor":
            result.floor_passthroughs.append(pen)
            continue

        wall_id = pen.get("wall_id", "")
        if wall_id not in wall_lookup:
            result.unrouted.append(UnroutedPenetration(
                connector_id=pen.get("connector_id", "unknown"),
                system_type=pen.get("system_type", "unknown"),
                wall_id=wall_id,
                entry_uv=tuple(pen.get("wall_uv", [0, 0])),
                reason=f"Wall '{wall_id}' not found in walls_json",
            ))
            continue

        if wall_id not in wall_penetrations:
            wall_penetrations[wall_id] = []
        wall_penetrations[wall_id].append(pen)

    # Route each wall
    obstacle_sources = set()
    for wall_id, pens in wall_penetrations.items():
        wall = wall_lookup[wall_id]
        framing = framing_lookup.get(wall_id)
        cell_data = cell_lookup.get(wall_id)

        wall_result = route_wall(
            wall_id=wall_id,
            penetrations=pens,
            wall=wall,
            framing=framing,
            cell_data=cell_data,
            occupancy=occupancy,
        )

        result.wall_routes.extend(wall_result.wall_routes)
        result.exit_points.extend(wall_result.exit_points)
        result.unrouted.extend(wall_result.unrouted)
        obstacle_sources.add(wall_result.obstacle_source)

    # Set overall obstacle source
    if "framing" in obstacle_sources and "derived" in obstacle_sources:
        result.obstacle_source = "mixed"
    elif "framing" in obstacle_sources:
        result.obstacle_source = "framing"
    else:
        result.obstacle_source = "derived"

    # Set status
    if result.unrouted:
        result.status = "needs_input"
        for ur in result.unrouted:
            result.needs.append(
                f"{ur.connector_id} ({ur.system_type}) in wall {ur.wall_id}: "
                f"{ur.reason}"
            )

    logger.info(
        "Phase 2 complete: %d wall routes, %d exit points, "
        "%d unrouted, %d floor passthroughs, obstacle_source=%s",
        len(result.wall_routes),
        len(result.exit_points),
        len(result.unrouted),
        len(result.floor_passthroughs),
        result.obstacle_source,
    )

    return result


def generate_stats(result: WallRoutingResult) -> Dict[str, Any]:
    """Generate statistics for Phase 2 output.

    Args:
        result: The wall routing result.

    Returns:
        Stats dict for stats_json output.
    """
    wall_counts: Dict[str, int] = {}
    system_counts: Dict[str, int] = {}
    exit_edge_counts: Dict[str, int] = {}
    stud_crossing_list: List[int] = []
    costs: List[float] = []

    for wr in result.wall_routes:
        wall_counts[wr.wall_id] = wall_counts.get(wr.wall_id, 0) + 1
        system_counts[wr.system_type] = (
            system_counts.get(wr.system_type, 0) + 1
        )
        exit_edge_counts[wr.exit_edge] = (
            exit_edge_counts.get(wr.exit_edge, 0) + 1
        )
        stud_crossing_list.append(wr.stud_crossings)
        costs.append(wr.route.total_cost)

    total = len(result.wall_routes) + len(result.unrouted)

    stats: Dict[str, Any] = {
        "total_wall_penetrations": total,
        "routed": len(result.wall_routes),
        "unrouted": len(result.unrouted),
        "floor_passthroughs": len(result.floor_passthroughs),
        "success_rate": len(result.wall_routes) / max(1, total),
        "walls_routed": len(wall_counts),
        "routes_per_wall": wall_counts,
        "systems_routed": system_counts,
        "exit_edges": exit_edge_counts,
        "obstacle_source": result.obstacle_source,
    }

    if stud_crossing_list:
        stats["total_stud_crossings"] = sum(stud_crossing_list)
        stats["avg_stud_crossings"] = round(
            sum(stud_crossing_list) / len(stud_crossing_list), 2,
        )

    if costs:
        stats["avg_route_cost"] = round(sum(costs) / len(costs), 4)
        stats["max_route_cost"] = round(max(costs), 4)

    return stats
