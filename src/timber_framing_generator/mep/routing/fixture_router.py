# File: src/timber_framing_generator/mep/routing/fixture_router.py
"""Phase 1: Fixture-to-Penetration Router.

Projects MEP fixture connectors onto the nearest wall surface to compute
penetration points. This is purely geometric — no graph traversal needed.

Each connector is projected onto all walls within search_radius, and the
closest valid projection (within wall bounds) is selected. Output includes
both world coordinates and wall-local UV coordinates for downstream phases.

Follows the user-in-the-loop design philosophy (Issue #37):
- Reports unassigned connectors with actionable guidance
- Status output: "ready" if all assigned, "needs_input" if some unassigned
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConnectionProfile:
    """Defines how a fixture type connects to the building MEP system.

    Determines whether a connector routes to a wall or through the floor,
    and any vertical drop to apply before wall projection.
    """

    target: str  # "wall" or "floor"
    origin_drop: float  # Vertical drop in feet before wall search
    description: str


# Connection profiles keyed by (fixture_type, system_type).
# Lookup order: exact match -> (fixture_type, None) -> default.
CONNECTION_PROFILES: Dict[Tuple[Optional[str], Optional[str]], ConnectionProfile] = {
    # Toilet sanitary: closet flange through floor
    ("toilet", "Sanitary"): ConnectionProfile(
        target="floor", origin_drop=0.0, description="Closet flange through floor"
    ),
    # Sink sanitary: P-trap drop then horizontal to wall
    ("sink", "Sanitary"): ConnectionProfile(
        target="wall", origin_drop=0.5, description="P-trap drop then horizontal"
    ),
    # Bathtub sanitary: floor-level drain, P-trap below floor
    ("bathtub", "Sanitary"): ConnectionProfile(
        target="floor", origin_drop=0.0, description="Tub drain through floor"
    ),
    # Shower sanitary: floor-level drain
    ("shower", "Sanitary"): ConnectionProfile(
        target="floor", origin_drop=0.0, description="Floor-level drain"
    ),
    # Floor drain sanitary: through floor
    ("floor_drain", "Sanitary"): ConnectionProfile(
        target="floor", origin_drop=0.0, description="Floor drain through floor"
    ),
    # Urinal sanitary: wall-mounted drain to wall
    ("urinal", "Sanitary"): ConnectionProfile(
        target="wall", origin_drop=0.25, description="Urinal drain to wall"
    ),
}

# Default profile: direct wall projection (supply lines, unknown fixtures)
DEFAULT_CONNECTION_PROFILE = ConnectionProfile(
    target="wall", origin_drop=0.0, description="Direct wall projection"
)


def _get_connection_profile(
    fixture_type: Optional[str], system_type: str
) -> ConnectionProfile:
    """Look up the connection profile for a fixture + system combination.

    Lookup priority:
    1. Exact (fixture_type, system_type) match
    2. Default profile (direct wall projection)

    Args:
        fixture_type: Normalized fixture type or None.
        system_type: MEP system type string.

    Returns:
        ConnectionProfile for routing this connector.
    """
    if fixture_type is not None:
        key = (fixture_type, system_type)
        if key in CONNECTION_PROFILES:
            return CONNECTION_PROFILES[key]
    return DEFAULT_CONNECTION_PROFILE


@dataclass
class PenetrationResult:
    """Result of projecting a connector onto a wall or floor."""

    connector_id: str
    system_type: str
    wall_id: str
    world_location: Tuple[float, float, float]
    wall_uv: Tuple[float, float]
    distance: float
    side: str  # "interior" or "exterior"
    connector_origin: Tuple[float, float, float]
    radius: Optional[float] = None
    fixture_type: Optional[str] = None
    target: str = "wall"  # "wall" or "floor"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result: Dict[str, Any] = {
            "connector_id": self.connector_id,
            "system_type": self.system_type,
            "wall_id": self.wall_id,
            "world_location": list(self.world_location),
            "wall_uv": list(self.wall_uv),
            "distance": round(self.distance, 4),
            "side": self.side,
            "connector_origin": list(self.connector_origin),
            "target": self.target,
        }
        if self.radius is not None:
            result["radius"] = self.radius
        if self.fixture_type is not None:
            result["fixture_type"] = self.fixture_type
        return result


@dataclass
class UnassignedConnector:
    """A connector that could not be assigned to any wall."""

    connector_id: str
    system_type: str
    origin: Tuple[float, float, float]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "connector_id": self.connector_id,
            "system_type": self.system_type,
            "origin": list(self.origin),
            "reason": self.reason,
        }


@dataclass
class FixtureRoutingResult:
    """Complete result of Phase 1 fixture-to-penetration routing."""

    penetrations: List[PenetrationResult] = field(default_factory=list)
    unassigned: List[UnassignedConnector] = field(default_factory=list)
    status: str = "ready"  # "ready" | "needs_input"
    needs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "penetrations": [p.to_dict() for p in self.penetrations],
            "unassigned": [u.to_dict() for u in self.unassigned],
            "status": self.status,
            "needs": self.needs,
        }


def _extract_vec(data: Dict[str, float]) -> Tuple[float, float, float]:
    """Extract (x, y, z) tuple from a dict with x, y, z keys."""
    return (float(data["x"]), float(data["y"]), float(data["z"]))


def _dot(
    a: Tuple[float, float, float], b: Tuple[float, float, float]
) -> float:
    """Dot product of two 3D vectors."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _estimate_floor_z(
    connector_origin: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
) -> float:
    """Estimate floor elevation from nearby wall base elevations.

    Uses the minimum base_elevation from all walls as the floor level.
    Falls back to 0.0 if no walls have base_elevation data.

    Args:
        connector_origin: Connector (x, y, z) for proximity context.
        walls: Wall data dicts.

    Returns:
        Estimated floor Z elevation in feet.
    """
    elevations = []
    for wall in walls:
        bp = wall.get("base_plane", {})
        origin = bp.get("origin", {})
        base_elev = float(wall.get("base_elevation", origin.get("z", 0.0)))
        elevations.append(base_elev)
    return min(elevations) if elevations else 0.0


def _create_floor_penetration(
    conn_id: str,
    system_type: str,
    connector_origin: Tuple[float, float, float],
    floor_z: float,
    radius: Optional[float] = None,
    fixture_type: Optional[str] = None,
) -> PenetrationResult:
    """Create a floor penetration result for fixtures that drain through floor.

    Args:
        conn_id: Connector identifier.
        system_type: MEP system type.
        connector_origin: Connector (x, y, z) position.
        floor_z: Floor elevation Z.
        radius: Optional pipe radius.
        fixture_type: Normalized fixture type.

    Returns:
        PenetrationResult with target="floor" and wall_id="floor".
    """
    # Floor penetration location is directly below connector at floor level
    world_location = (connector_origin[0], connector_origin[1], floor_z)
    # UV for floor = (x, y) plan position
    wall_uv = (connector_origin[0], connector_origin[1])
    distance = abs(connector_origin[2] - floor_z)

    return PenetrationResult(
        connector_id=conn_id,
        system_type=system_type,
        wall_id="floor",
        world_location=world_location,
        wall_uv=wall_uv,
        distance=distance,
        side="interior",
        connector_origin=connector_origin,
        radius=radius,
        fixture_type=fixture_type,
        target="floor",
    )


def find_nearest_wall(
    connector_origin: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
    search_radius: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """Project a connector onto the nearest wall surface.

    For each wall within search_radius, projects the connector location
    onto the wall plane and checks if the projection falls within the
    wall bounds (U: 0 to wall_length, V: 0 to wall_height).

    Args:
        connector_origin: World (x, y, z) of the fixture connector.
        walls: Wall data dicts with base_plane, wall_length, wall_height.
        search_radius: Maximum perpendicular distance to consider (feet).

    Returns:
        Dict with wall_id, uv coords, world_location, distance, side —
        or None if no wall is within range and bounds.
    """
    cx, cy, cz = connector_origin
    best: Optional[Dict[str, Any]] = None
    best_dist = search_radius

    for wall in walls:
        bp = wall["base_plane"]
        origin = _extract_vec(bp["origin"])
        x_axis = _extract_vec(bp["x_axis"])
        z_axis = _extract_vec(bp["z_axis"])
        wall_length = float(wall["wall_length"])
        wall_height = float(wall.get("wall_height", wall.get("height", 0.0)))
        base_elev = float(wall.get("base_elevation", origin[2]))

        # Vector from wall origin to connector
        dx = cx - origin[0]
        dy = cy - origin[1]
        dz = cz - origin[2]
        delta = (dx, dy, dz)

        # Project onto wall local axes
        u = _dot(delta, x_axis)  # Along wall length
        v = cz - base_elev  # Vertical (world Z relative to wall base)
        w = _dot(delta, z_axis)  # Through-wall (perpendicular distance)

        # Check if projection is within wall bounds
        if 0 <= u <= wall_length and 0 <= v <= wall_height:
            dist = abs(w)
            if dist < best_dist:
                best_dist = dist
                # Compute world location of the penetration point on the wall face
                world_x = origin[0] + x_axis[0] * u
                world_y = origin[1] + x_axis[1] * u
                world_z = base_elev + v

                best = {
                    "wall_id": wall["wall_id"],
                    "wall_uv": (u, v),
                    "world_location": (world_x, world_y, world_z),
                    "distance": dist,
                    "side": "interior" if w > 0 else "exterior",
                }

    return best


def route_fixtures_to_walls(
    connectors: List[Dict[str, Any]],
    walls: List[Dict[str, Any]],
    search_radius: float = 5.0,
) -> FixtureRoutingResult:
    """Route all fixture connectors to their nearest wall penetration points.

    This is the main entry point for Phase 1. For each connector, finds the
    nearest wall surface and computes the penetration point in both world
    and wall-local UV coordinates.

    Args:
        connectors: List of connector dicts from connectors_json["connectors"].
        walls: List of wall dicts from walls_json["walls"].
        search_radius: Maximum distance to search for wall (feet).

    Returns:
        FixtureRoutingResult with penetrations, unassigned connectors, and status.
    """
    result = FixtureRoutingResult()

    if not connectors:
        logger.warning("No connectors provided")
        return result

    if not walls:
        logger.warning("No walls provided")
        result.status = "needs_input"
        result.needs.append(
            "No walls provided. Ensure walls_json contains wall data."
        )
        for conn in connectors:
            conn_id = conn.get("id", "unknown")
            system_type = conn.get("system_type", "unknown")
            origin_data = conn.get("origin", {"x": 0, "y": 0, "z": 0})
            origin = _extract_vec(origin_data)
            result.unassigned.append(
                UnassignedConnector(
                    connector_id=conn_id,
                    system_type=system_type,
                    origin=origin,
                    reason="No walls provided",
                )
            )
        return result

    # Pre-compute floor elevation for floor penetrations
    floor_z = _estimate_floor_z((0, 0, 0), walls)

    for conn in connectors:
        conn_id = conn.get("id", "unknown")
        system_type = conn.get("system_type", "unknown")
        origin_data = conn.get("origin", {"x": 0, "y": 0, "z": 0})
        origin = _extract_vec(origin_data)
        radius = conn.get("radius")
        fixture_type = conn.get("fixture_type")

        # Look up connection profile for this fixture+system combination
        profile = _get_connection_profile(fixture_type, system_type)

        if profile.target == "floor":
            # Floor penetration: always succeeds (no wall search needed)
            penetration = _create_floor_penetration(
                conn_id, system_type, origin, floor_z,
                radius=radius, fixture_type=fixture_type,
            )
            result.penetrations.append(penetration)
            logger.debug(
                "Connector %s -> floor (fixture=%s, %s)",
                conn_id,
                fixture_type,
                profile.description,
            )
            continue

        # Wall target: apply origin_drop before projection
        search_origin = origin
        if profile.origin_drop > 0:
            search_origin = (origin[0], origin[1], origin[2] - profile.origin_drop)

        wall_result = find_nearest_wall(search_origin, walls, search_radius)

        if wall_result is not None:
            penetration = PenetrationResult(
                connector_id=conn_id,
                system_type=system_type,
                wall_id=wall_result["wall_id"],
                world_location=wall_result["world_location"],
                wall_uv=wall_result["wall_uv"],
                distance=wall_result["distance"],
                side=wall_result["side"],
                connector_origin=origin,
                radius=radius,
                fixture_type=fixture_type,
                target="wall",
            )
            result.penetrations.append(penetration)
            logger.debug(
                "Connector %s -> wall %s (dist=%.2f ft, uv=(%.2f, %.2f), fixture=%s)",
                conn_id,
                wall_result["wall_id"],
                wall_result["distance"],
                wall_result["wall_uv"][0],
                wall_result["wall_uv"][1],
                fixture_type,
            )
        else:
            unassigned = UnassignedConnector(
                connector_id=conn_id,
                system_type=system_type,
                origin=origin,
                reason=f"No wall within {search_radius:.1f} ft",
            )
            result.unassigned.append(unassigned)
            logger.warning(
                "Connector %s (%s) at (%.1f, %.1f, %.1f): no wall within %.1f ft",
                conn_id,
                system_type,
                origin[0],
                origin[1],
                origin[2],
                search_radius,
            )

    # Set status based on results
    if result.unassigned:
        result.status = "needs_input"
        for ua in result.unassigned:
            result.needs.append(
                f"{ua.connector_id} ({ua.system_type}) at "
                f"({ua.origin[0]:.1f}, {ua.origin[1]:.1f}, {ua.origin[2]:.1f}): "
                f"{ua.reason}. Increase search_radius or add a wall near this fixture."
            )
    else:
        result.status = "ready"

    logger.info(
        "Phase 1 complete: %d penetrations, %d unassigned, status=%s",
        len(result.penetrations),
        len(result.unassigned),
        result.status,
    )

    return result


def generate_stats(result: FixtureRoutingResult) -> Dict[str, Any]:
    """Generate statistics for Phase 1 output.

    Args:
        result: The fixture routing result.

    Returns:
        Stats dict for stats_json output.
    """
    wall_counts: Dict[str, int] = {}
    system_counts: Dict[str, int] = {}
    target_counts: Dict[str, int] = {}
    fixture_type_counts: Dict[str, int] = {}
    distances: List[float] = []

    for p in result.penetrations:
        wall_counts[p.wall_id] = wall_counts.get(p.wall_id, 0) + 1
        system_counts[p.system_type] = system_counts.get(p.system_type, 0) + 1
        target_counts[p.target] = target_counts.get(p.target, 0) + 1
        ft = p.fixture_type or "unclassified"
        fixture_type_counts[ft] = fixture_type_counts.get(ft, 0) + 1
        distances.append(p.distance)

    stats: Dict[str, Any] = {
        "total_connectors": len(result.penetrations) + len(result.unassigned),
        "assigned": len(result.penetrations),
        "unassigned": len(result.unassigned),
        "success_rate": (
            len(result.penetrations)
            / max(
                1, len(result.penetrations) + len(result.unassigned)
            )
        ),
        "walls_with_penetrations": len(wall_counts),
        "penetrations_per_wall": wall_counts,
        "systems_routed": system_counts,
        "targets_routed": target_counts,
        "fixture_types": fixture_type_counts,
    }

    if distances:
        stats["avg_distance"] = round(sum(distances) / len(distances), 4)
        stats["max_distance"] = round(max(distances), 4)
        stats["min_distance"] = round(min(distances), 4)

    return stats
