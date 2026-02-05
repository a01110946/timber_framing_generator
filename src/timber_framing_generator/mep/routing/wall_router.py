# File: src/timber_framing_generator/mep/routing/wall_router.py
"""Phase 2: In-Wall MEP Router.

Routes MEP pipes/conduits through wall cavities from penetration points
(Phase 1 output) to wall exit points (top plate, bottom plate, or side edge).

Supports progressive refinement:
- walls_json alone: derives studs at 16" OC
- walls_json + framing_json: uses exact framing element positions

Follows the user-in-the-loop design philosophy (Issue #37):
- Reports unrouted penetrations with actionable guidance
- Status output: "ready" if all routed, "needs_input" if some failed
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .domains import (
    Obstacle,
    RoutingDomain,
    RoutingDomainType,
    add_opening_obstacles,
    create_wall_domain,
)
from .pathfinding import AStarPathfinder, PathReconstructor
from .route_segment import Route
from .wall_graph import WallGraphBuilder

logger = logging.getLogger(__name__)


# --- Framing element type classification ---

# Penetrable elements: (element_type -> max_penetration_ratio)
PENETRABLE_ELEMENT_TYPES: Dict[str, float] = {
    "stud": 0.4,
    "king_stud": 0.4,
    "trimmer": 0.4,
    "sill_cripple": 0.4,
    "header_cripple": 0.4,
    "header": 0.25,
    "sill_plate": 0.25,
}

NON_PENETRABLE_ELEMENT_TYPES = {"top_plate", "bottom_plate"}

VERTICAL_ELEMENT_TYPES = {
    "stud", "king_stud", "trimmer", "sill_cripple", "header_cripple",
}


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
        obstacle_source: "derived" (16" OC), "framing" (exact), or "mixed".
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


# --- Obstacle creation ---


def _create_framing_obstacles(
    framing_elements: List[Dict[str, Any]],
    wall_id: str,
    wall_length: float,
) -> List[Obstacle]:
    """Convert framing element dicts to Obstacle objects.

    Vertical elements (studs, king studs, trimmers, cripples): penetrable
    with 40% max penetration ratio per structural code.
    Headers: penetrable but limited (25%).
    Plates: non-penetrable (routing exits through plate zone via exit points).

    Args:
        framing_elements: List of FramingElementData-style dicts.
        wall_id: Wall identifier for obstacle naming.
        wall_length: Wall length for plate U bounds.

    Returns:
        List of Obstacle objects.
    """
    obstacles = []

    for elem in framing_elements:
        elem_id = elem.get("id", "unknown")
        elem_type = elem.get("element_type", "")
        profile = elem.get("profile", {})
        profile_width = float(profile.get("width", 0.125))
        u_coord = float(elem.get("u_coord", 0))
        v_start = float(elem.get("v_start", 0))
        v_end = float(elem.get("v_end", 0))

        # Skip zero-height elements
        if abs(v_end - v_start) < 1e-6:
            continue

        # Determine penetrability
        if elem_type in NON_PENETRABLE_ELEMENT_TYPES:
            is_penetrable = False
            max_pen = 0.0
        elif elem_type in PENETRABLE_ELEMENT_TYPES:
            is_penetrable = True
            max_pen = PENETRABLE_ELEMENT_TYPES[elem_type]
        else:
            # Unknown element type: treat as penetrable stud-like
            is_penetrable = True
            max_pen = 0.4

        # Compute U bounds based on element orientation
        if elem_type in NON_PENETRABLE_ELEMENT_TYPES:
            # Plates span full wall length
            u_min = 0.0
            u_max = wall_length
        else:
            # Vertical elements and others: u_coord +/- half width
            u_min = u_coord - profile_width / 2
            u_max = u_coord + profile_width / 2

        obstacle_type = (
            "plate" if elem_type in NON_PENETRABLE_ELEMENT_TYPES else "stud"
        )

        obstacles.append(Obstacle(
            id=f"{wall_id}_frame_{elem_id}",
            obstacle_type=obstacle_type,
            bounds=(u_min, v_start, u_max, v_end),
            is_penetrable=is_penetrable,
            max_penetration_ratio=max_pen,
        ))

    return obstacles


def create_wall_routing_domain(
    wall: Dict[str, Any],
    framing: Optional[Dict[str, Any]] = None,
) -> Tuple[RoutingDomain, str]:
    """Create routing domain for a wall with progressive refinement.

    Without framing: calls create_wall_domain() for derived studs at 16" OC,
    then adds opening obstacles from wall data.

    With framing: creates empty domain, adds exact framing elements as
    obstacles, then adds opening obstacles.

    Args:
        wall: Wall data dict (from walls_json).
        framing: Optional framing data dict (from framing_json).

    Returns:
        Tuple of (RoutingDomain, obstacle_source) where obstacle_source
        is "derived" or "framing".
    """
    wall_id = wall["wall_id"]
    wall_length = float(wall["wall_length"])
    wall_height = float(wall.get("wall_height", wall.get("height", 8.0)))
    wall_thickness = float(wall.get("wall_thickness", 0.292))
    openings = wall.get("openings", [])

    if framing is not None:
        # Framing mode: exact obstacles from framing data
        domain = RoutingDomain(
            id=wall_id,
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, wall_length, 0, wall_height),
            thickness=wall_thickness,
        )

        elements = framing.get("elements", [])
        framing_obstacles = _create_framing_obstacles(
            elements, wall_id, wall_length,
        )
        for obs in framing_obstacles:
            domain.add_obstacle(obs)

        obstacle_source = "framing"
    else:
        # Derived mode: 16" OC studs + standard plates
        domain = create_wall_domain(
            wall_id=wall_id,
            length=wall_length,
            height=wall_height,
            thickness=wall_thickness,
        )
        obstacle_source = "derived"

    # Add opening obstacles (applies in both modes)
    if openings:
        add_opening_obstacles(domain, openings)

    return domain, obstacle_source


# --- Exit point selection ---


def _select_exit_point(
    penetration: Dict[str, Any],
    wall: Dict[str, Any],
    domain: RoutingDomain,
    plate_thickness: float = 0.125,
) -> Tuple[Tuple[float, float], str]:
    """Select wall exit point (U, V) for a penetration.

    Uses system_type to determine preferred exit edge (top/bottom).
    Exit V is placed just inside the plate zone with clearance.
    Exit U matches the penetration U for a vertical drop/rise.

    Args:
        penetration: Penetration dict from Phase 1.
        wall: Wall data dict.
        domain: The routing domain for UV bounds.
        plate_thickness: Plate thickness in feet.

    Returns:
        Tuple of ((exit_u, exit_v), exit_edge).
    """
    system_type = penetration.get("system_type", "")
    wall_uv = penetration.get("wall_uv", [0, 0])
    entry_u = float(wall_uv[0])

    # Determine exit edge from system type
    exit_edge = EXIT_POINT_RULES.get(system_type, DEFAULT_EXIT_EDGE)

    # Compute exit V position (just inside the plate zone)
    clearance = 0.042  # ~0.5 inch clearance from plate edge
    if exit_edge == "top":
        exit_v = domain.max_v - plate_thickness - clearance
    else:  # "bottom"
        exit_v = domain.min_v + plate_thickness + clearance

    # Exit U: same as entry U (vertical drop preferred)
    exit_u = entry_u

    # Clamp to domain bounds with margin
    margin = 0.05
    exit_u = max(domain.min_u + margin, min(domain.max_u - margin, exit_u))
    exit_v = max(domain.min_v + margin, min(domain.max_v - margin, exit_v))

    return (exit_u, exit_v), exit_edge


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


# --- Core routing ---


def route_wall(
    wall_id: str,
    penetrations: List[Dict[str, Any]],
    wall: Dict[str, Any],
    framing: Optional[Dict[str, Any]] = None,
    grid_resolution_u: float = 0.333,
    grid_resolution_v: float = 0.5,
) -> WallRoutingResult:
    """Route all penetrations for a single wall.

    Steps:
    1. Create routing domain (with or without framing)
    2. Build grid graph via WallGraphBuilder
    3. For each penetration:
       a. Select exit point based on system_type
       b. Add source and target as terminal nodes
       c. Run A* pathfinding
       d. Convert to Route via PathReconstructor
    4. Return results with routes, unrouted, stats

    Args:
        wall_id: Wall identifier.
        penetrations: List of penetration dicts from Phase 1.
        wall: Wall data dict from walls_json.
        framing: Optional framing data dict from framing_json.
        grid_resolution_u: Grid spacing along wall (feet).
        grid_resolution_v: Grid spacing vertical (feet).

    Returns:
        WallRoutingResult for this wall.
    """
    result = WallRoutingResult()

    if not penetrations:
        return result

    # Create routing domain
    domain, obstacle_source = create_wall_routing_domain(wall, framing)
    result.obstacle_source = obstacle_source

    # Build grid graph
    builder = WallGraphBuilder(
        domain,
        resolution_u=grid_resolution_u,
        resolution_v=grid_resolution_v,
    )
    graph = builder.build_grid_graph()

    # Route each penetration
    for pen in penetrations:
        conn_id = pen.get("connector_id", "unknown")
        system_type = pen.get("system_type", "unknown")
        wall_uv = pen.get("wall_uv", [0, 0])
        entry_uv = (float(wall_uv[0]), float(wall_uv[1]))
        fixture_type = pen.get("fixture_type")

        # Select exit point
        exit_uv, exit_edge = _select_exit_point(pen, wall, domain)

        # Add terminal nodes
        source_ids = builder.add_terminal_nodes(
            graph, [entry_uv], is_source=True,
        )
        target_ids = builder.add_terminal_nodes(
            graph, [exit_uv], is_source=False,
        )

        if not source_ids or not target_ids:
            result.unrouted.append(UnroutedPenetration(
                connector_id=conn_id,
                system_type=system_type,
                wall_id=wall_id,
                entry_uv=entry_uv,
                reason="Failed to add terminal nodes to graph",
            ))
            continue

        # Find path
        pathfinder = AStarPathfinder(graph)
        path_result = pathfinder.find_path_with_result(
            source_ids[0], target_ids[0],
        )

        if not path_result.success:
            result.unrouted.append(UnroutedPenetration(
                connector_id=conn_id,
                system_type=system_type,
                wall_id=wall_id,
                entry_uv=entry_uv,
                reason=(
                    f"No path found to {exit_edge} plate "
                    f"(visited {path_result.visited_count} nodes)"
                ),
            ))
            continue

        # Reconstruct route
        reconstructor = PathReconstructor(graph)
        route = reconstructor.reconstruct(
            path_result.path,
            route_id=f"wall_route_{conn_id}",
            system_type=system_type,
        )

        stud_crossings = _count_stud_crossings(route)

        # Create WallRoute
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
            "%s, %d stud crossings, cost=%.2f",
            conn_id, wall_id,
            entry_uv[0], entry_uv[1],
            exit_uv[0], exit_uv[1],
            exit_edge, stud_crossings,
            route.total_cost,
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
) -> WallRoutingResult:
    """Main entry point for Phase 2.

    Groups penetrations by wall_id, routes each wall independently.
    Floor penetrations (target="floor") are passed through unchanged.

    Args:
        penetrations_json: Phase 1 output with "penetrations" list.
        walls_json: Wall analyzer output with "walls" list.
        framing_json: Optional framing generator output. Can be a single
            wall's framing dict or a list under "walls" key.

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

        wall_result = route_wall(
            wall_id=wall_id,
            penetrations=pens,
            wall=wall,
            framing=framing,
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
