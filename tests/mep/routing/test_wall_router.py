# File: tests/mep/routing/test_wall_router.py
"""Tests for Phase 2: In-Wall MEP Router.

Tests the wall_router module which routes MEP pipes through wall cavities
from penetration points (Phase 1) to wall exit points (top/bottom plate).

Uses a simplified wall model: 10 ft long, 8 ft tall, 2x4 studs at 16" OC.
"""

import math

import pytest

from src.timber_framing_generator.mep.routing.domains import (
    Obstacle,
    RoutingDomain,
    RoutingDomainType,
    add_opening_obstacles,
    create_wall_domain,
)
from src.timber_framing_generator.mep.routing.wall_router import (
    DEFAULT_EXIT_EDGE,
    EXIT_POINT_RULES,
    UnroutedPenetration,
    WallExitPoint,
    WallRoute,
    WallRoutingResult,
    _count_stud_crossings,
    _create_framing_obstacles,
    _select_exit_point,
    _uv_to_world,
    create_wall_routing_domain,
    generate_stats,
    route_all_walls,
    route_wall,
)


# --- Test Helpers ---


def make_wall(
    wall_id: str = "wall_A",
    origin: tuple = (0.0, 0.0, 0.0),
    direction: tuple = (1.0, 0.0, 0.0),
    length: float = 10.0,
    height: float = 8.0,
    thickness: float = 0.292,
    openings: list = None,
) -> dict:
    """Create a wall data dict matching walls_json format."""
    dx, dy, dz = direction
    norm_len = math.sqrt(dy * dy + dx * dx)
    if norm_len > 0:
        nx, ny, nz = dy / norm_len, -dx / norm_len, 0.0
    else:
        nx, ny, nz = 0.0, -1.0, 0.0

    wall = {
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
    if openings:
        wall["openings"] = openings
    return wall


def make_penetration(
    connector_id: str = "conn_1",
    system_type: str = "DomesticColdWater",
    wall_id: str = "wall_A",
    wall_uv: tuple = (5.0, 4.0),
    target: str = "wall",
    fixture_type: str = None,
) -> dict:
    """Create a penetration dict matching Phase 1 output."""
    result = {
        "connector_id": connector_id,
        "system_type": system_type,
        "wall_id": wall_id,
        "wall_uv": list(wall_uv),
        "world_location": [5.0, 0.0, 4.0],
        "distance": 0.5,
        "side": "interior",
        "connector_origin": [5.0, 0.5, 4.0],
        "target": target,
    }
    if fixture_type is not None:
        result["fixture_type"] = fixture_type
    return result


def make_framing(
    wall_id: str = "wall_A",
    elements: list = None,
) -> dict:
    """Create a framing data dict matching framing_json format."""
    if elements is None:
        elements = [
            # Bottom plate
            {
                "id": "bp_1",
                "element_type": "bottom_plate",
                "profile": {"width": 0.125, "depth": 0.292},
                "u_coord": 5.0,
                "v_start": 0.0,
                "v_end": 0.125,
            },
            # Top plate
            {
                "id": "tp_1",
                "element_type": "top_plate",
                "profile": {"width": 0.125, "depth": 0.292},
                "u_coord": 5.0,
                "v_start": 7.875,
                "v_end": 8.0,
            },
            # Stud at u=0.0625
            {
                "id": "s_0",
                "element_type": "stud",
                "profile": {"width": 0.125, "depth": 0.292},
                "u_coord": 0.0625,
                "v_start": 0.125,
                "v_end": 7.875,
            },
            # Stud at u=1.333
            {
                "id": "s_1",
                "element_type": "stud",
                "profile": {"width": 0.125, "depth": 0.292},
                "u_coord": 1.333,
                "v_start": 0.125,
                "v_end": 7.875,
            },
            # Stud at u=2.666
            {
                "id": "s_2",
                "element_type": "stud",
                "profile": {"width": 0.125, "depth": 0.292},
                "u_coord": 2.666,
                "v_start": 0.125,
                "v_end": 7.875,
            },
        ]
    return {
        "wall_id": wall_id,
        "material_system": "timber",
        "elements": elements,
    }


def make_window_opening(
    opening_id: str = "win_1",
    u_start: float = 3.0,
    u_end: float = 6.0,
    v_start: float = 3.0,
    v_end: float = 6.5,
) -> dict:
    """Create a window opening dict matching OpeningData format."""
    return {
        "id": opening_id,
        "opening_type": "window",
        "u_start": u_start,
        "u_end": u_end,
        "v_start": v_start,
        "v_end": v_end,
        "width": u_end - u_start,
        "height": v_end - v_start,
        "sill_height": v_start,
    }


def make_door_opening(
    opening_id: str = "door_1",
    u_start: float = 3.0,
    u_end: float = 6.0,
    v_start: float = 0.0,
    v_end: float = 6.833,
) -> dict:
    """Create a door opening dict matching OpeningData format."""
    return {
        "id": opening_id,
        "opening_type": "door",
        "u_start": u_start,
        "u_end": u_end,
        "v_start": v_start,
        "v_end": v_end,
        "width": u_end - u_start,
        "height": v_end - v_start,
    }


# --- Tests for add_opening_obstacles (domains.py) ---


class TestAddOpeningObstacles:
    """Tests for add_opening_obstacles function in domains.py."""

    def test_window_creates_bounded_obstacle(self) -> None:
        """Window creates obstacle only within its UV bounds."""
        domain = create_wall_domain("w1", length=10.0, height=8.0)
        initial_count = len(domain.obstacles)

        window = make_window_opening(u_start=3.0, u_end=6.0, v_start=3.0, v_end=6.5)
        add_opening_obstacles(domain, [window])

        assert len(domain.obstacles) == initial_count + 1
        opening_obs = domain.obstacles[-1]
        assert opening_obs.obstacle_type == "opening"
        assert opening_obs.is_penetrable is False
        assert opening_obs.bounds == (3.0, 3.0, 6.0, 6.5)

    def test_door_creates_full_height_obstacle(self) -> None:
        """Door creates obstacle spanning full domain height."""
        domain = create_wall_domain("w1", length=10.0, height=8.0)
        initial_count = len(domain.obstacles)

        door = make_door_opening(u_start=3.0, u_end=6.0)
        add_opening_obstacles(domain, [door])

        assert len(domain.obstacles) == initial_count + 1
        door_obs = domain.obstacles[-1]
        assert door_obs.obstacle_type == "opening"
        assert door_obs.is_penetrable is False
        # Door spans full height
        assert door_obs.min_v == domain.min_v  # 0.0
        assert door_obs.max_v == domain.max_v  # 8.0

    def test_multiple_openings(self) -> None:
        """Multiple openings create multiple obstacles."""
        domain = create_wall_domain("w1", length=20.0, height=8.0)
        initial_count = len(domain.obstacles)

        openings = [
            make_window_opening("win_1", u_start=2.0, u_end=5.0),
            make_door_opening("door_1", u_start=8.0, u_end=11.0),
            make_window_opening("win_2", u_start=14.0, u_end=17.0),
        ]
        add_opening_obstacles(domain, openings)

        assert len(domain.obstacles) == initial_count + 3

    def test_empty_openings_list(self) -> None:
        """Empty openings list adds no obstacles."""
        domain = create_wall_domain("w1", length=10.0, height=8.0)
        initial_count = len(domain.obstacles)
        add_opening_obstacles(domain, [])
        assert len(domain.obstacles) == initial_count


# --- Tests for _create_framing_obstacles ---


class TestCreateFramingObstacles:
    """Tests for framing element to obstacle conversion."""

    def test_stud_is_penetrable(self) -> None:
        """Studs are penetrable with 40% max ratio."""
        elements = [{
            "id": "s_1",
            "element_type": "stud",
            "profile": {"width": 0.125, "depth": 0.292},
            "u_coord": 1.333,
            "v_start": 0.125,
            "v_end": 7.875,
        }]
        obstacles = _create_framing_obstacles(elements, "wall_A", 10.0)

        assert len(obstacles) == 1
        obs = obstacles[0]
        assert obs.is_penetrable is True
        assert obs.max_penetration_ratio == 0.4
        assert obs.obstacle_type == "stud"
        # U bounds: 1.333 +/- 0.0625
        assert abs(obs.min_u - (1.333 - 0.0625)) < 1e-6
        assert abs(obs.max_u - (1.333 + 0.0625)) < 1e-6

    def test_plate_is_non_penetrable(self) -> None:
        """Plates are non-penetrable and span full wall length."""
        elements = [{
            "id": "bp_1",
            "element_type": "bottom_plate",
            "profile": {"width": 0.125, "depth": 0.292},
            "u_coord": 5.0,
            "v_start": 0.0,
            "v_end": 0.125,
        }]
        obstacles = _create_framing_obstacles(elements, "wall_A", 10.0)

        assert len(obstacles) == 1
        obs = obstacles[0]
        assert obs.is_penetrable is False
        assert obs.obstacle_type == "plate"
        assert obs.min_u == 0.0
        assert obs.max_u == 10.0

    def test_king_stud_penetrable(self) -> None:
        """King studs are penetrable like regular studs."""
        elements = [{
            "id": "ks_1",
            "element_type": "king_stud",
            "profile": {"width": 0.125, "depth": 0.292},
            "u_coord": 3.0,
            "v_start": 0.125,
            "v_end": 7.875,
        }]
        obstacles = _create_framing_obstacles(elements, "wall_A", 10.0)

        assert len(obstacles) == 1
        assert obstacles[0].is_penetrable is True
        assert obstacles[0].max_penetration_ratio == 0.4

    def test_header_limited_penetration(self) -> None:
        """Headers are penetrable but with lower ratio (25%)."""
        elements = [{
            "id": "h_1",
            "element_type": "header",
            "profile": {"width": 0.125, "depth": 0.292},
            "u_coord": 4.5,
            "v_start": 6.5,
            "v_end": 7.0,
        }]
        obstacles = _create_framing_obstacles(elements, "wall_A", 10.0)

        assert len(obstacles) == 1
        assert obstacles[0].is_penetrable is True
        assert obstacles[0].max_penetration_ratio == 0.25

    def test_zero_height_element_skipped(self) -> None:
        """Elements with zero height are skipped."""
        elements = [{
            "id": "z_1",
            "element_type": "stud",
            "profile": {"width": 0.125, "depth": 0.292},
            "u_coord": 1.0,
            "v_start": 3.0,
            "v_end": 3.0,
        }]
        obstacles = _create_framing_obstacles(elements, "wall_A", 10.0)
        assert len(obstacles) == 0

    def test_mixed_elements(self) -> None:
        """Mix of studs, plates, and cripples creates correct obstacles."""
        framing = make_framing()
        obstacles = _create_framing_obstacles(
            framing["elements"], "wall_A", 10.0,
        )

        # 2 plates + 3 studs = 5
        assert len(obstacles) == 5

        plate_obs = [o for o in obstacles if o.obstacle_type == "plate"]
        stud_obs = [o for o in obstacles if o.obstacle_type == "stud"]
        assert len(plate_obs) == 2
        assert len(stud_obs) == 3

        # All plates non-penetrable
        for p in plate_obs:
            assert p.is_penetrable is False

        # All studs penetrable
        for s in stud_obs:
            assert s.is_penetrable is True


# --- Tests for create_wall_routing_domain ---


class TestCreateWallRoutingDomain:
    """Tests for routing domain creation with progressive refinement."""

    def test_derived_mode_without_framing(self) -> None:
        """Without framing, creates derived studs at 16" OC."""
        wall = make_wall(length=10.0, height=8.0)
        domain, source = create_wall_routing_domain(wall)

        assert source == "derived"
        assert domain.domain_type == RoutingDomainType.WALL_CAVITY
        assert domain.width == 10.0
        assert domain.height == 8.0

        # Should have studs + plates from create_wall_domain
        studs = [o for o in domain.obstacles if o.obstacle_type == "stud"]
        plates = [o for o in domain.obstacles if o.obstacle_type == "plate"]
        assert len(studs) > 0
        assert len(plates) == 2  # top + bottom

    def test_framing_mode_with_framing(self) -> None:
        """With framing, uses exact element positions."""
        wall = make_wall(length=10.0, height=8.0)
        framing = make_framing()
        domain, source = create_wall_routing_domain(wall, framing)

        assert source == "framing"
        assert domain.domain_type == RoutingDomainType.WALL_CAVITY

        # Should have exactly the elements from framing data
        studs = [o for o in domain.obstacles if o.obstacle_type == "stud"]
        plates = [o for o in domain.obstacles if o.obstacle_type == "plate"]
        assert len(studs) == 3
        assert len(plates) == 2

    def test_openings_added_in_derived_mode(self) -> None:
        """Opening obstacles added on top of derived studs."""
        window = make_window_opening()
        wall = make_wall(openings=[window])
        domain, source = create_wall_routing_domain(wall)

        assert source == "derived"
        opening_obs = [o for o in domain.obstacles if o.obstacle_type == "opening"]
        assert len(opening_obs) == 1
        assert opening_obs[0].is_penetrable is False

    def test_openings_added_in_framing_mode(self) -> None:
        """Opening obstacles added on top of framing elements."""
        window = make_window_opening()
        wall = make_wall(openings=[window])
        framing = make_framing()
        domain, source = create_wall_routing_domain(wall, framing)

        assert source == "framing"
        opening_obs = [o for o in domain.obstacles if o.obstacle_type == "opening"]
        assert len(opening_obs) == 1

    def test_no_openings(self) -> None:
        """Wall without openings has no opening obstacles."""
        wall = make_wall()
        domain, _ = create_wall_routing_domain(wall)

        opening_obs = [o for o in domain.obstacles if o.obstacle_type == "opening"]
        assert len(opening_obs) == 0


# --- Tests for _select_exit_point ---


class TestSelectExitPoint:
    """Tests for system_type to exit edge mapping."""

    def test_sanitary_exits_bottom(self) -> None:
        """Sanitary pipes exit through bottom plate."""
        pen = make_penetration(system_type="Sanitary", wall_uv=(5.0, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, exit_edge = _select_exit_point(pen, wall, domain)
        assert exit_edge == "bottom"
        assert exit_uv[1] < 1.0  # Near bottom

    def test_vent_exits_top(self) -> None:
        """Vent pipes exit through top plate."""
        pen = make_penetration(system_type="Vent", wall_uv=(5.0, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, exit_edge = _select_exit_point(pen, wall, domain)
        assert exit_edge == "top"
        assert exit_uv[1] > 7.0  # Near top

    def test_supply_exits_bottom(self) -> None:
        """Supply pipes exit through bottom plate."""
        pen = make_penetration(system_type="DomesticColdWater", wall_uv=(5.0, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, exit_edge = _select_exit_point(pen, wall, domain)
        assert exit_edge == "bottom"

    def test_hot_water_exits_bottom(self) -> None:
        """Hot water supply exits through bottom plate."""
        pen = make_penetration(system_type="DomesticHotWater", wall_uv=(5.0, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, exit_edge = _select_exit_point(pen, wall, domain)
        assert exit_edge == "bottom"

    def test_unknown_system_exits_bottom(self) -> None:
        """Unknown system types default to bottom exit."""
        pen = make_penetration(system_type="SomeUnknownSystem", wall_uv=(5.0, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, exit_edge = _select_exit_point(pen, wall, domain)
        assert exit_edge == DEFAULT_EXIT_EDGE

    def test_exit_u_matches_entry_u(self) -> None:
        """Exit U coordinate matches entry U (vertical route preferred)."""
        pen = make_penetration(system_type="Sanitary", wall_uv=(7.5, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, _ = _select_exit_point(pen, wall, domain)
        assert abs(exit_uv[0] - 7.5) < 0.1

    def test_exit_clamped_to_bounds(self) -> None:
        """Exit point clamped to domain bounds when entry is at edge."""
        pen = make_penetration(system_type="Sanitary", wall_uv=(0.01, 4.0))
        wall = make_wall()
        domain = create_wall_domain("wall_A", length=10.0, height=8.0)

        exit_uv, _ = _select_exit_point(pen, wall, domain)
        assert exit_uv[0] >= 0.05  # Clamped to margin


# --- Tests for _uv_to_world ---


class TestUvToWorld:
    """Tests for UV to world coordinate conversion."""

    def test_origin_point(self) -> None:
        """UV (0, 0) maps to wall origin."""
        wall = make_wall(origin=(10.0, 20.0, 5.0))
        world = _uv_to_world((0.0, 0.0), wall)
        assert abs(world[0] - 10.0) < 1e-6
        assert abs(world[1] - 20.0) < 1e-6
        assert abs(world[2] - 5.0) < 1e-6

    def test_u_along_wall(self) -> None:
        """U moves along wall x_axis direction."""
        wall = make_wall(origin=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0))
        world = _uv_to_world((5.0, 0.0), wall)
        assert abs(world[0] - 5.0) < 1e-6
        assert abs(world[1] - 0.0) < 1e-6

    def test_v_is_elevation(self) -> None:
        """V adds to base elevation for Z."""
        wall = make_wall(origin=(0.0, 0.0, 3.0))
        world = _uv_to_world((0.0, 4.0), wall)
        assert abs(world[2] - 7.0) < 1e-6

    def test_angled_wall(self) -> None:
        """UV conversion works for walls not aligned to axes."""
        wall = make_wall(
            origin=(0.0, 0.0, 0.0),
            direction=(1.0 / math.sqrt(2), 1.0 / math.sqrt(2), 0.0),
        )
        world = _uv_to_world((math.sqrt(2), 0.0), wall)
        assert abs(world[0] - 1.0) < 1e-4
        assert abs(world[1] - 1.0) < 1e-4


# --- Tests for route_wall ---


class TestRouteWall:
    """Tests for single wall routing."""

    def test_simple_wall_routes_to_bottom(self) -> None:
        """Penetration on simple wall routes vertically to bottom plate."""
        wall = make_wall(length=10.0, height=8.0)
        pen = make_penetration(
            system_type="DomesticColdWater",
            wall_uv=(5.0, 4.0),
        )

        result = route_wall("wall_A", [pen], wall)

        assert len(result.wall_routes) == 1
        assert len(result.unrouted) == 0
        wr = result.wall_routes[0]
        assert wr.exit_edge == "bottom"
        assert wr.entry_uv == (5.0, 4.0)
        assert wr.route.segments  # Has path segments
        assert result.obstacle_source == "derived"

    def test_vent_routes_to_top(self) -> None:
        """Vent penetration routes to top plate."""
        wall = make_wall(length=10.0, height=8.0)
        pen = make_penetration(
            system_type="Vent",
            wall_uv=(5.0, 4.0),
        )

        result = route_wall("wall_A", [pen], wall)

        assert len(result.wall_routes) == 1
        wr = result.wall_routes[0]
        assert wr.exit_edge == "top"

    def test_multiple_penetrations_same_wall(self) -> None:
        """Multiple penetrations on same wall each route independently."""
        wall = make_wall(length=10.0, height=8.0)
        pens = [
            make_penetration("conn_1", "DomesticColdWater", wall_uv=(2.0, 4.0)),
            make_penetration("conn_2", "DomesticHotWater", wall_uv=(8.0, 4.0)),
        ]

        result = route_wall("wall_A", pens, wall)

        assert len(result.wall_routes) == 2
        assert len(result.unrouted) == 0
        ids = {wr.connector_id for wr in result.wall_routes}
        assert ids == {"conn_1", "conn_2"}

    def test_with_framing_json(self) -> None:
        """Framing mode uses exact stud positions."""
        wall = make_wall(length=10.0, height=8.0)
        framing = make_framing()
        pen = make_penetration(wall_uv=(5.0, 4.0))

        result = route_wall("wall_A", [pen], wall, framing=framing)

        assert result.obstacle_source == "framing"
        assert len(result.wall_routes) == 1

    def test_exit_point_created(self) -> None:
        """Each route creates a corresponding exit point."""
        wall = make_wall(length=10.0, height=8.0)
        pen = make_penetration(wall_uv=(5.0, 4.0))

        result = route_wall("wall_A", [pen], wall)

        assert len(result.exit_points) == 1
        ep = result.exit_points[0]
        assert ep.wall_id == "wall_A"
        assert ep.exit_edge == "bottom"
        assert ep.system_type == "DomesticColdWater"
        assert len(ep.world_location) == 3

    def test_empty_penetrations(self) -> None:
        """No penetrations returns empty result."""
        wall = make_wall()
        result = route_wall("wall_A", [], wall)

        assert len(result.wall_routes) == 0
        assert len(result.unrouted) == 0

    def test_fixture_type_preserved(self) -> None:
        """Fixture type flows from penetration to wall route."""
        wall = make_wall(length=10.0, height=8.0)
        pen = make_penetration(
            wall_uv=(5.0, 4.0),
            fixture_type="sink",
        )

        result = route_wall("wall_A", [pen], wall)

        assert len(result.wall_routes) == 1
        assert result.wall_routes[0].fixture_type == "sink"

    def test_wall_with_window_routes_around(self) -> None:
        """Penetration in a wall with window finds route around it."""
        window = make_window_opening(u_start=4.0, u_end=7.0, v_start=3.0, v_end=6.5)
        wall = make_wall(length=10.0, height=8.0, openings=[window])
        # Penetration above window, should route to bottom going around window
        pen = make_penetration(
            system_type="DomesticColdWater",
            wall_uv=(5.5, 7.0),
        )

        result = route_wall("wall_A", [pen], wall)

        # Should route successfully (going around the window)
        assert len(result.wall_routes) == 1
        assert len(result.unrouted) == 0

    def test_status_ready_when_all_routed(self) -> None:
        """Status is 'ready' when all penetrations are routed."""
        wall = make_wall(length=10.0, height=8.0)
        pen = make_penetration(wall_uv=(5.0, 4.0))

        result = route_wall("wall_A", [pen], wall)

        assert result.status == "ready"


# --- Tests for route_all_walls ---


class TestRouteAllWalls:
    """Tests for multi-wall routing orchestration."""

    def test_multi_wall_routing(self) -> None:
        """Routes penetrations across multiple walls."""
        walls_json = {
            "walls": [
                make_wall("wall_A", origin=(0, 0, 0), length=10.0),
                make_wall("wall_B", origin=(0, 10, 0), length=10.0),
            ],
        }
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_A", (5.0, 4.0)),
                make_penetration("c2", "DomesticColdWater", "wall_B", (5.0, 4.0)),
            ],
        }

        result = route_all_walls(pen_json, walls_json)

        assert len(result.wall_routes) == 2
        wall_ids = {wr.wall_id for wr in result.wall_routes}
        assert wall_ids == {"wall_A", "wall_B"}

    def test_floor_penetrations_passed_through(self) -> None:
        """Floor penetrations are not routed, just passed through."""
        walls_json = {"walls": [make_wall("wall_A")]}
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_A", (5.0, 4.0)),
                make_penetration(
                    "c2", "Sanitary", "floor", (5.0, 4.0), target="floor",
                ),
            ],
        }

        result = route_all_walls(pen_json, walls_json)

        assert len(result.wall_routes) == 1
        assert len(result.floor_passthroughs) == 1
        assert result.floor_passthroughs[0]["connector_id"] == "c2"

    def test_missing_wall_creates_unrouted(self) -> None:
        """Penetration referencing non-existent wall becomes unrouted."""
        walls_json = {"walls": [make_wall("wall_A")]}
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_MISSING", (5.0, 4.0)),
            ],
        }

        result = route_all_walls(pen_json, walls_json)

        assert len(result.wall_routes) == 0
        assert len(result.unrouted) == 1
        assert "not found" in result.unrouted[0].reason

    def test_empty_penetrations(self) -> None:
        """No penetrations returns empty result."""
        walls_json = {"walls": [make_wall("wall_A")]}
        pen_json = {"penetrations": []}

        result = route_all_walls(pen_json, walls_json)

        assert len(result.wall_routes) == 0

    def test_empty_walls(self) -> None:
        """No walls returns needs_input status."""
        walls_json = {"walls": []}
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_A"),
            ],
        }

        result = route_all_walls(pen_json, walls_json)

        assert result.status == "needs_input"

    def test_with_framing_json_single_wall(self) -> None:
        """Framing JSON for a single wall uses exact obstacles."""
        walls_json = {"walls": [make_wall("wall_A", length=10.0)]}
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_A", (5.0, 4.0)),
            ],
        }
        framing = make_framing("wall_A")

        result = route_all_walls(pen_json, walls_json, framing_json=framing)

        assert result.obstacle_source == "framing"
        assert len(result.wall_routes) == 1

    def test_with_framing_json_multi_wall(self) -> None:
        """Framing JSON with 'walls' list routes multiple walls."""
        walls_json = {
            "walls": [
                make_wall("wall_A", length=10.0),
                make_wall("wall_B", origin=(0, 10, 0), length=10.0),
            ],
        }
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_A", (5.0, 4.0)),
                make_penetration("c2", "DomesticColdWater", "wall_B", (5.0, 4.0)),
            ],
        }
        framing = {
            "walls": [
                make_framing("wall_A"),
                make_framing("wall_B"),
            ],
        }

        result = route_all_walls(pen_json, walls_json, framing_json=framing)

        assert result.obstacle_source == "framing"
        assert len(result.wall_routes) == 2


# --- Tests for serialization ---


class TestSerialization:
    """Tests for to_dict / from_dict round-trip serialization."""

    def test_wall_exit_point_round_trip(self) -> None:
        """WallExitPoint serializes and deserializes correctly."""
        ep = WallExitPoint(
            wall_id="wall_A",
            exit_edge="bottom",
            wall_uv=(5.0, 0.167),
            world_location=(5.0, 0.0, 0.167),
            system_type="DomesticColdWater",
            connector_id="conn_1",
        )
        data = ep.to_dict()
        restored = WallExitPoint.from_dict(data)

        assert restored.wall_id == ep.wall_id
        assert restored.exit_edge == ep.exit_edge
        assert restored.wall_uv == ep.wall_uv
        assert restored.world_location == ep.world_location

    def test_unrouted_penetration_round_trip(self) -> None:
        """UnroutedPenetration serializes and deserializes correctly."""
        ur = UnroutedPenetration(
            connector_id="conn_2",
            system_type="Sanitary",
            wall_id="wall_B",
            entry_uv=(3.0, 4.0),
            reason="No path found",
        )
        data = ur.to_dict()
        restored = UnroutedPenetration.from_dict(data)

        assert restored.connector_id == ur.connector_id
        assert restored.reason == ur.reason

    def test_wall_routing_result_round_trip(self) -> None:
        """WallRoutingResult to_dict -> from_dict preserves structure."""
        wall = make_wall(length=10.0, height=8.0)
        pen = make_penetration(wall_uv=(5.0, 4.0))

        original = route_wall("wall_A", [pen], wall)
        data = original.to_dict()
        restored = WallRoutingResult.from_dict(data)

        assert len(restored.wall_routes) == len(original.wall_routes)
        assert len(restored.exit_points) == len(original.exit_points)
        assert restored.obstacle_source == original.obstacle_source
        assert restored.status == original.status

        if restored.wall_routes:
            wr = restored.wall_routes[0]
            assert wr.connector_id == original.wall_routes[0].connector_id
            assert wr.exit_edge == original.wall_routes[0].exit_edge


# --- Tests for generate_stats ---


class TestGenerateStats:
    """Tests for statistics generation."""

    def test_stats_basic(self) -> None:
        """Stats include expected keys and values."""
        wall = make_wall(length=10.0, height=8.0)
        pens = [
            make_penetration("c1", "DomesticColdWater", wall_uv=(3.0, 4.0)),
            make_penetration("c2", "Sanitary", wall_uv=(7.0, 4.0)),
        ]

        result = route_wall("wall_A", pens, wall)
        stats = generate_stats(result)

        assert stats["routed"] == 2
        assert stats["unrouted"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["walls_routed"] == 1
        assert "wall_A" in stats["routes_per_wall"]
        assert "DomesticColdWater" in stats["systems_routed"]
        assert "Sanitary" in stats["systems_routed"]

    def test_stats_with_floor_passthroughs(self) -> None:
        """Stats count floor passthroughs."""
        walls_json = {"walls": [make_wall("wall_A")]}
        pen_json = {
            "penetrations": [
                make_penetration("c1", "DomesticColdWater", "wall_A", (5.0, 4.0)),
                make_penetration("c2", "Sanitary", "floor", target="floor"),
            ],
        }

        result = route_all_walls(pen_json, walls_json)
        stats = generate_stats(result)

        assert stats["floor_passthroughs"] == 1

    def test_stats_empty_result(self) -> None:
        """Stats handle empty result gracefully."""
        result = WallRoutingResult()
        stats = generate_stats(result)

        assert stats["routed"] == 0
        assert stats["unrouted"] == 0
        assert stats["success_rate"] == 0.0
