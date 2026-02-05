# File: tests/mep/routing/test_fixture_router.py
"""Tests for Phase 1: Fixture-to-Penetration Router.

Tests the fixture_router module which projects MEP connectors onto wall
surfaces to compute penetration points. Uses the 4-room minimal test case
from Issue #37.

Test layout (4-Room Building):
    +----------------+----------------+
    |                |                |
    |   Bathroom     |   Bedroom      |
    |   (fixtures)   |                |
    |                |                |
    +----------------+----------------+
    |                |                |
    |   Corridor     |   Mech Shaft   |
    |                |   (riser)      |
    |                |                |
    +----------------+----------------+

Coordinate system:
    - Origin at bottom-left corner
    - X increases to the right
    - Y increases upward (in plan)
    - Z is vertical (elevation)
"""

import math

import pytest

from src.timber_framing_generator.mep.routing.fixture_router import (
    CONNECTION_PROFILES,
    ConnectionProfile,
    DEFAULT_CONNECTION_PROFILE,
    FixtureRoutingResult,
    PenetrationResult,
    UnassignedConnector,
    _get_connection_profile,
    find_nearest_wall,
    generate_stats,
    route_fixtures_to_walls,
)


# --- Test Helpers ---


def make_wall(
    wall_id: str = "wall_1",
    origin: tuple = (0.0, 0.0, 0.0),
    direction: tuple = (1.0, 0.0, 0.0),
    length: float = 10.0,
    height: float = 9.0,
    thickness: float = 0.333,
) -> dict:
    """Create a wall data dict matching walls_json format.

    Args:
        wall_id: Unique wall identifier.
        origin: Wall start point (x, y, z).
        direction: Unit vector along wall length (U direction).
        length: Wall length in feet.
        height: Wall height in feet.
        thickness: Wall thickness in feet.

    Returns:
        Wall dict compatible with walls_json["walls"][i].
    """
    # Compute wall normal (z_axis) as cross product of direction × world Z
    dx, dy, dz = direction
    # Normal = direction × (0, 0, 1) = (dy, -dx, 0)
    norm_len = math.sqrt(dy * dy + dx * dx)
    if norm_len > 0:
        nx, ny, nz = dy / norm_len, -dx / norm_len, 0.0
    else:
        nx, ny, nz = 0.0, -1.0, 0.0

    return {
        "wall_id": wall_id,
        "wall_length": length,
        "wall_height": height,
        "wall_thickness": thickness,
        "base_elevation": origin[2],
        "top_elevation": origin[2] + height,
        "base_plane": {
            "origin": {"x": origin[0], "y": origin[1], "z": origin[2]},
            "x_axis": {"x": dx, "y": dy, "z": dz},
            "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
            "z_axis": {"x": nx, "y": ny, "z": nz},
        },
    }


def make_connector(
    conn_id: str = "conn_0",
    origin: tuple = (5.0, 2.0, 3.0),
    system_type: str = "DomesticColdWater",
    radius: float = 0.0625,
    fixture_type: str = None,
) -> dict:
    """Create a connector data dict matching connectors_json format.

    Args:
        conn_id: Unique connector identifier.
        origin: World (x, y, z) of the connector.
        system_type: MEP system type.
        radius: Pipe radius in feet.
        fixture_type: Normalized fixture type (e.g., "toilet", "sink").

    Returns:
        Connector dict compatible with connectors_json["connectors"][i].
    """
    result = {
        "id": conn_id,
        "origin": {"x": origin[0], "y": origin[1], "z": origin[2]},
        "system_type": system_type,
        "radius": radius,
        "direction": {"x": 0.0, "y": 0.0, "z": -1.0},
        "domain": "plumbing",
    }
    if fixture_type is not None:
        result["fixture_type"] = fixture_type
    return result


def make_4room_walls() -> list:
    """Create the 4-room test case walls.

    Layout (plan view, Y-up):
        Wall arrangement:
        - wall_south: bottom edge (y=0, x: 0→20)
        - wall_north: top edge (y=16, x: 0→20)
        - wall_west: left edge (x=0, y: 0→16)
        - wall_east: right edge (x=20, y: 0→16)
        - wall_center_h: horizontal center (y=8, x: 0→20)
        - wall_center_v: vertical center (x=10, y: 0→16)
    """
    return [
        # South wall (bottom, facing north/interior)
        make_wall("wall_south", origin=(0, 0, 0), direction=(1, 0, 0), length=20),
        # North wall (top, facing south/interior)
        make_wall("wall_north", origin=(0, 16, 0), direction=(1, 0, 0), length=20),
        # West wall (left, facing east/interior)
        make_wall("wall_west", origin=(0, 0, 0), direction=(0, 1, 0), length=16),
        # East wall (right, facing west/interior)
        make_wall("wall_east", origin=(20, 0, 0), direction=(0, 1, 0), length=16),
        # Center horizontal wall (y=8)
        make_wall("wall_center_h", origin=(0, 8, 0), direction=(1, 0, 0), length=20),
        # Center vertical wall (x=10)
        make_wall("wall_center_v", origin=(10, 0, 0), direction=(0, 1, 0), length=16),
    ]


# --- Tests for find_nearest_wall ---


class TestFindNearestWall:
    """Tests for the find_nearest_wall function."""

    def test_direct_projection(self) -> None:
        """Connector directly in front of wall projects correctly."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        result = find_nearest_wall((5.0, 2.0, 4.0), [wall])

        assert result is not None
        assert result["wall_id"] == "wall_1"
        assert abs(result["wall_uv"][0] - 5.0) < 0.01  # U along wall
        assert abs(result["wall_uv"][1] - 4.0) < 0.01  # V = height
        assert result["distance"] < 3.0  # Should be close

    def test_connector_at_wall_midpoint(self) -> None:
        """Connector at exact wall midpoint, 1 ft away."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        # 1 ft in front of wall (in -Y direction since normal is (0, -1, 0))
        result = find_nearest_wall((5.0, -1.0, 4.5), [wall])

        assert result is not None
        assert abs(result["wall_uv"][0] - 5.0) < 0.01
        assert abs(result["wall_uv"][1] - 4.5) < 0.01
        assert abs(result["distance"] - 1.0) < 0.01

    def test_out_of_range(self) -> None:
        """Connector too far from any wall returns None."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        result = find_nearest_wall((5.0, 50.0, 4.0), [wall], search_radius=5.0)

        assert result is None

    def test_outside_wall_bounds_u(self) -> None:
        """Connector projects outside wall length bounds."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        # At u=-2 (before wall start)
        result = find_nearest_wall((-2.0, 0.5, 4.0), [wall])

        assert result is None

    def test_outside_wall_bounds_v(self) -> None:
        """Connector projects above wall height."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        # At z=12 (above 9 ft wall)
        result = find_nearest_wall((5.0, 0.5, 12.0), [wall])

        assert result is None

    def test_below_wall_base(self) -> None:
        """Connector below wall base elevation."""
        wall = make_wall(
            origin=(0, 0, 5), direction=(1, 0, 0), length=10, height=9
        )
        # At z=2 (below base at z=5)
        result = find_nearest_wall((5.0, 0.5, 2.0), [wall])

        assert result is None

    def test_multiple_walls_selects_closest(self) -> None:
        """With multiple walls, selects the closest one."""
        wall_a = make_wall(
            "wall_a", origin=(0, 0, 0), direction=(1, 0, 0), length=10
        )
        wall_b = make_wall(
            "wall_b", origin=(0, 5, 0), direction=(1, 0, 0), length=10
        )

        # Connector at y=4 — closer to wall_b (y=5, dist=1) than wall_a (y=0, dist=4)
        result = find_nearest_wall((5.0, 4.0, 4.0), [wall_a, wall_b])

        assert result is not None
        assert result["wall_id"] == "wall_b"

    def test_angled_wall(self) -> None:
        """Wall at 45 degrees projects connector correctly."""
        # Wall along (1, 1, 0) normalized
        d = 1.0 / math.sqrt(2)
        wall = make_wall(
            origin=(0, 0, 0), direction=(d, d, 0), length=10, height=9
        )

        # Connector at (3, 3, 4) should project onto the wall
        result = find_nearest_wall((3.0, 3.0, 4.0), [wall])

        assert result is not None
        # U should be the distance along the wall direction
        expected_u = 3.0 * d + 3.0 * d  # dot product of (3,3,0) with (d,d,0)
        assert abs(result["wall_uv"][0] - expected_u) < 0.1

    def test_side_detection_interior(self) -> None:
        """Connector on positive-normal side is interior."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        # Wall normal is (0, -1, 0), so positive W is in -Y direction
        # Connector at y=-1 (positive W side)
        result = find_nearest_wall((5.0, -1.0, 4.0), [wall])

        assert result is not None
        # W > 0 when connector is in the positive normal direction
        assert result["side"] == "interior"

    def test_side_detection_exterior(self) -> None:
        """Connector on negative-normal side is exterior."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        # Connector at y=1 (negative W side, opposite to normal)
        result = find_nearest_wall((5.0, 1.0, 4.0), [wall])

        assert result is not None
        assert result["side"] == "exterior"

    def test_wall_at_elevation(self) -> None:
        """Wall with non-zero base elevation handles V correctly."""
        wall = make_wall(
            origin=(0, 0, 10), direction=(1, 0, 0), length=10, height=9
        )
        # Connector at z=14 → V = 14 - 10 = 4
        result = find_nearest_wall((5.0, 0.5, 14.0), [wall])

        assert result is not None
        assert abs(result["wall_uv"][1] - 4.0) < 0.01
        assert abs(result["world_location"][2] - 14.0) < 0.01

    def test_connector_at_wall_edge(self) -> None:
        """Connector at exact wall boundary (u=0) should be in bounds."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        result = find_nearest_wall((0.0, -0.5, 4.0), [wall])

        assert result is not None
        assert abs(result["wall_uv"][0]) < 0.01  # U = 0


# --- Tests for route_fixtures_to_walls ---


class TestRouteFixturesToWalls:
    """Tests for the main routing function."""

    def test_single_connector_single_wall(self) -> None:
        """One connector, one wall — simple case."""
        connectors = [make_connector("conn_0", origin=(5.0, -1.0, 4.0))]
        walls = [make_wall()]

        result = route_fixtures_to_walls(connectors, walls)

        assert isinstance(result, FixtureRoutingResult)
        assert len(result.penetrations) == 1
        assert len(result.unassigned) == 0
        assert result.status == "ready"
        assert result.penetrations[0].connector_id == "conn_0"
        assert result.penetrations[0].wall_id == "wall_1"

    def test_multiple_connectors(self) -> None:
        """Multiple connectors route to correct walls."""
        walls = make_4room_walls()
        connectors = [
            # Sink in bathroom (near center_v wall at x=10, y=12)
            make_connector("conn_sink", origin=(9.5, 12.0, 3.0), system_type="DomesticColdWater"),
            # Toilet in bathroom (near center_v wall at x=10, y=10)
            make_connector("conn_toilet", origin=(9.5, 10.0, 1.0), system_type="Sanitary"),
        ]

        result = route_fixtures_to_walls(connectors, walls)

        assert len(result.penetrations) == 2
        assert len(result.unassigned) == 0
        assert result.status == "ready"

        # Both should route to wall_center_v (x=10) since it's closest
        wall_ids = {p.wall_id for p in result.penetrations}
        assert "wall_center_v" in wall_ids

    def test_unassigned_connector_status(self) -> None:
        """Unassigned connectors produce needs_input status."""
        walls = [make_wall()]
        connectors = [
            make_connector("conn_0", origin=(5.0, -1.0, 4.0)),  # In range
            make_connector("conn_far", origin=(5.0, 50.0, 4.0)),  # Out of range
        ]

        result = route_fixtures_to_walls(connectors, walls, search_radius=5.0)

        assert len(result.penetrations) == 1
        assert len(result.unassigned) == 1
        assert result.status == "needs_input"
        assert len(result.needs) == 1
        assert "conn_far" in result.needs[0]

    def test_empty_connectors(self) -> None:
        """No connectors returns empty result."""
        result = route_fixtures_to_walls([], [make_wall()])

        assert len(result.penetrations) == 0
        assert len(result.unassigned) == 0
        assert result.status == "ready"

    def test_empty_walls(self) -> None:
        """No walls returns needs_input with all connectors unassigned."""
        connectors = [make_connector()]
        result = route_fixtures_to_walls(connectors, [])

        assert len(result.penetrations) == 0
        assert len(result.unassigned) == 1
        assert result.status == "needs_input"
        assert len(result.needs) >= 1

    def test_search_radius_parameter(self) -> None:
        """Custom search_radius affects what's in range."""
        wall = make_wall()
        # Connector 3 ft from wall
        connectors = [make_connector(origin=(5.0, -3.0, 4.0))]

        # With radius=2, should fail
        result_small = route_fixtures_to_walls(connectors, [wall], search_radius=2.0)
        assert len(result_small.unassigned) == 1

        # With radius=5, should succeed
        result_large = route_fixtures_to_walls(connectors, [wall], search_radius=5.0)
        assert len(result_large.penetrations) == 1

    def test_4room_bathroom_fixtures(self) -> None:
        """Full 4-room test case with bathroom fixtures.

        Bathroom is in top-left quadrant (x: 0→10, y: 8→16).
        Sink at (2, 12, 3) and toilet at (2, 10, 1).
        Both should route to nearest walls.
        """
        walls = make_4room_walls()
        connectors = [
            make_connector("sink_cold", origin=(2.0, 12.0, 3.0), system_type="DomesticColdWater"),
            make_connector("sink_hot", origin=(2.0, 12.0, 3.0), system_type="DomesticHotWater"),
            make_connector("toilet_cold", origin=(2.0, 10.0, 1.0), system_type="DomesticColdWater"),
            make_connector("toilet_san", origin=(2.0, 10.0, 0.5), system_type="Sanitary"),
        ]

        result = route_fixtures_to_walls(connectors, walls, search_radius=5.0)

        assert result.status == "ready"
        assert len(result.penetrations) == 4
        assert len(result.unassigned) == 0

        # All fixtures should route to nearby walls
        for p in result.penetrations:
            assert p.distance < 5.0

    def test_serialization(self) -> None:
        """Result serializes to valid JSON-compatible dict."""
        walls = [make_wall()]
        connectors = [
            make_connector("conn_0", origin=(5.0, -1.0, 4.0)),
            make_connector("conn_far", origin=(5.0, 50.0, 4.0)),
        ]

        result = route_fixtures_to_walls(connectors, walls, search_radius=5.0)
        data = result.to_dict()

        assert "penetrations" in data
        assert "unassigned" in data
        assert "status" in data
        assert "needs" in data
        assert isinstance(data["penetrations"], list)
        assert isinstance(data["unassigned"], list)
        assert len(data["penetrations"]) == 1
        assert len(data["unassigned"]) == 1

        # Check penetration fields
        p = data["penetrations"][0]
        assert "connector_id" in p
        assert "wall_id" in p
        assert "world_location" in p
        assert "wall_uv" in p
        assert "distance" in p
        assert "side" in p
        assert isinstance(p["world_location"], list)
        assert len(p["world_location"]) == 3


# --- Tests for generate_stats ---


class TestGenerateStats:
    """Tests for statistics generation."""

    def test_basic_stats(self) -> None:
        """Stats include expected fields."""
        walls = [make_wall()]
        connectors = [make_connector(origin=(5.0, -1.0, 4.0))]

        result = route_fixtures_to_walls(connectors, walls)
        stats = generate_stats(result)

        assert stats["total_connectors"] == 1
        assert stats["assigned"] == 1
        assert stats["unassigned"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["walls_with_penetrations"] == 1
        assert "avg_distance" in stats

    def test_stats_with_unassigned(self) -> None:
        """Stats reflect unassigned connectors."""
        walls = [make_wall()]
        connectors = [
            make_connector("c1", origin=(5.0, -1.0, 4.0)),
            make_connector("c2", origin=(5.0, 50.0, 4.0)),
        ]

        result = route_fixtures_to_walls(connectors, walls, search_radius=5.0)
        stats = generate_stats(result)

        assert stats["total_connectors"] == 2
        assert stats["assigned"] == 1
        assert stats["unassigned"] == 1
        assert stats["success_rate"] == 0.5

    def test_empty_stats(self) -> None:
        """Stats handle empty results."""
        result = FixtureRoutingResult()
        stats = generate_stats(result)

        assert stats["total_connectors"] == 0
        assert stats["assigned"] == 0
        assert "avg_distance" not in stats


# --- Tests for fixture type routing ---


class TestFixtureTypeRouting:
    """Tests for fixture-type-aware routing dispatch."""

    def test_toilet_sanitary_routes_to_floor(self) -> None:
        """Toilet + Sanitary connector routes through floor, not wall."""
        walls = [make_wall()]
        connectors = [
            make_connector(
                "toilet_san", origin=(5.0, -1.0, 0.5),
                system_type="Sanitary", fixture_type="toilet",
            )
        ]

        result = route_fixtures_to_walls(connectors, walls)

        assert len(result.penetrations) == 1
        assert len(result.unassigned) == 0
        p = result.penetrations[0]
        assert p.target == "floor"
        assert p.wall_id == "floor"
        assert p.fixture_type == "toilet"
        # Floor penetration at plan (x, y) position
        assert abs(p.world_location[0] - 5.0) < 0.01
        assert abs(p.world_location[1] - (-1.0)) < 0.01
        assert p.world_location[2] == 0.0  # Floor z

    def test_sink_sanitary_adjusts_origin(self) -> None:
        """Sink + Sanitary drops 0.5 ft before wall projection."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        # Connector at z=3.0, should drop to z=2.5 for wall projection
        connectors = [
            make_connector(
                "sink_san", origin=(5.0, -1.0, 3.0),
                system_type="Sanitary", fixture_type="sink",
            )
        ]

        result = route_fixtures_to_walls(connectors, [wall])

        assert len(result.penetrations) == 1
        p = result.penetrations[0]
        assert p.target == "wall"
        assert p.wall_id == "wall_1"
        assert p.fixture_type == "sink"
        # V should reflect the dropped origin (z=3.0 - 0.5 = 2.5)
        assert abs(p.wall_uv[1] - 2.5) < 0.01

    def test_supply_unchanged_with_fixture_type(self) -> None:
        """Supply connector (DCW) with fixture_type still projects normally."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        connectors = [
            make_connector(
                "sink_dcw", origin=(5.0, -1.0, 3.0),
                system_type="DomesticColdWater", fixture_type="sink",
            )
        ]

        result = route_fixtures_to_walls(connectors, [wall])

        assert len(result.penetrations) == 1
        p = result.penetrations[0]
        assert p.target == "wall"
        assert p.wall_id == "wall_1"
        # No drop — default profile has origin_drop=0.0
        assert abs(p.wall_uv[1] - 3.0) < 0.01

    def test_no_fixture_type_fallback(self) -> None:
        """Connector without fixture_type uses default wall projection."""
        wall = make_wall(
            origin=(0, 0, 0), direction=(1, 0, 0), length=10, height=9
        )
        connectors = [
            make_connector("conn_notype", origin=(5.0, -1.0, 4.0)),
        ]

        result = route_fixtures_to_walls(connectors, [wall])

        assert len(result.penetrations) == 1
        p = result.penetrations[0]
        assert p.target == "wall"
        assert p.fixture_type is None

    def test_shower_sanitary_routes_to_floor(self) -> None:
        """Shower + Sanitary drains through floor."""
        walls = [make_wall()]
        connectors = [
            make_connector(
                "shower_san", origin=(5.0, -1.0, 0.1),
                system_type="Sanitary", fixture_type="shower",
            )
        ]

        result = route_fixtures_to_walls(connectors, walls)

        assert len(result.penetrations) == 1
        p = result.penetrations[0]
        assert p.target == "floor"
        assert p.wall_id == "floor"
        assert p.fixture_type == "shower"

    def test_serialization_includes_new_fields(self) -> None:
        """Serialized penetrations include target and fixture_type."""
        walls = [make_wall()]
        connectors = [
            make_connector(
                "toilet_san", origin=(5.0, -1.0, 0.5),
                system_type="Sanitary", fixture_type="toilet",
            ),
            make_connector(
                "sink_dcw", origin=(5.0, -1.0, 3.0),
                system_type="DomesticColdWater", fixture_type="sink",
            ),
        ]

        result = route_fixtures_to_walls(connectors, walls)
        data = result.to_dict()

        for p_dict in data["penetrations"]:
            assert "target" in p_dict
            assert p_dict["target"] in ("wall", "floor")

        # Toilet should have fixture_type in serialized output
        toilet_p = [p for p in data["penetrations"] if p["connector_id"] == "toilet_san"][0]
        assert toilet_p["fixture_type"] == "toilet"
        assert toilet_p["target"] == "floor"

    def test_stats_include_fixture_counts(self) -> None:
        """Stats include targets_routed and fixture_types breakdowns."""
        walls = [make_wall()]
        connectors = [
            make_connector(
                "toilet_san", origin=(5.0, -1.0, 0.5),
                system_type="Sanitary", fixture_type="toilet",
            ),
            make_connector(
                "sink_dcw", origin=(5.0, -1.0, 3.0),
                system_type="DomesticColdWater", fixture_type="sink",
            ),
        ]

        result = route_fixtures_to_walls(connectors, walls)
        stats = generate_stats(result)

        assert "targets_routed" in stats
        assert "fixture_types" in stats
        assert stats["targets_routed"]["floor"] == 1
        assert stats["targets_routed"]["wall"] == 1
        assert stats["fixture_types"]["toilet"] == 1
        assert stats["fixture_types"]["sink"] == 1

    def test_connection_profile_lookup(self) -> None:
        """_get_connection_profile returns correct profiles."""
        # Toilet + Sanitary -> floor
        profile = _get_connection_profile("toilet", "Sanitary")
        assert profile.target == "floor"

        # Sink + Sanitary -> wall with drop
        profile = _get_connection_profile("sink", "Sanitary")
        assert profile.target == "wall"
        assert profile.origin_drop == 0.5

        # Unknown fixture_type -> default
        profile = _get_connection_profile("unknown_thing", "Sanitary")
        assert profile.target == "wall"
        assert profile.origin_drop == 0.0

        # None fixture_type -> default
        profile = _get_connection_profile(None, "Sanitary")
        assert profile.target == "wall"
        assert profile.origin_drop == 0.0

    def test_bathtub_sanitary_routes_to_floor(self) -> None:
        """Bathtub + Sanitary drains through floor (floor-level drain)."""
        walls = [make_wall()]
        connectors = [
            make_connector(
                "tub_san", origin=(5.0, -1.0, 0.0),
                system_type="Sanitary", fixture_type="bathtub",
            )
        ]

        result = route_fixtures_to_walls(connectors, walls)

        assert len(result.penetrations) == 1
        p = result.penetrations[0]
        assert p.target == "floor"
        assert p.wall_id == "floor"
        assert p.fixture_type == "bathtub"
