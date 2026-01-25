# File: tests/mep/test_pipe_router.py
"""Tests for pipe routing module."""

import pytest
from src.timber_framing_generator.mep.plumbing.pipe_router import (
    calculate_pipe_routes,
    find_wall_entry,
    get_wall_face_plane,
    ray_plane_intersection,
    point_in_wall_bounds,
    calculate_vertical_connection_point,
    extract_walls_from_framing,
)
from src.timber_framing_generator.core import MEPDomain, MEPConnector


class TestRayPlaneIntersection:
    """Test ray-plane intersection calculations."""

    def test_perpendicular_hit(self):
        """Ray perpendicular to plane hits correctly."""
        ray_origin = (0.0, 0.0, 0.0)
        ray_direction = (0.0, 1.0, 0.0)  # +Y direction
        plane = {
            "origin": (0.0, 5.0, 0.0),
            "normal": (0.0, 1.0, 0.0)  # Facing +Y
        }

        result = ray_plane_intersection(ray_origin, ray_direction, plane)

        assert result is not None
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(5.0)
        assert result[2] == pytest.approx(0.0)

    def test_parallel_ray_no_hit(self):
        """Ray parallel to plane returns None."""
        ray_origin = (0.0, 0.0, 0.0)
        ray_direction = (1.0, 0.0, 0.0)  # +X direction
        plane = {
            "origin": (0.0, 5.0, 0.0),
            "normal": (0.0, 1.0, 0.0)  # Facing +Y
        }

        result = ray_plane_intersection(ray_origin, ray_direction, plane)
        assert result is None

    def test_behind_ray_no_hit(self):
        """Intersection behind ray origin returns None."""
        ray_origin = (0.0, 10.0, 0.0)  # Behind plane
        ray_direction = (0.0, 1.0, 0.0)  # +Y (away from plane)
        plane = {
            "origin": (0.0, 5.0, 0.0),
            "normal": (0.0, 1.0, 0.0)
        }

        result = ray_plane_intersection(ray_origin, ray_direction, plane)
        assert result is None

    def test_angled_ray(self):
        """Angled ray hits plane correctly."""
        ray_origin = (0.0, 0.0, 0.0)
        ray_direction = (0.707, 0.707, 0.0)  # 45 degrees in XY
        plane = {
            "origin": (5.0, 0.0, 0.0),
            "normal": (1.0, 0.0, 0.0)  # Facing +X
        }

        result = ray_plane_intersection(ray_origin, ray_direction, plane)

        assert result is not None
        assert result[0] == pytest.approx(5.0, rel=0.01)


class TestGetWallFacePlane:
    """Test wall face plane extraction."""

    def test_from_base_plane(self):
        """Extract plane from base_plane data."""
        wall = {
            "base_plane": {
                "origin": {"x": 10.0, "y": 5.0, "z": 0.0},
                "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0}
            }
        }

        result = get_wall_face_plane(wall)

        assert result is not None
        assert result["origin"] == (10.0, 5.0, 0.0)
        assert result["normal"][1] == pytest.approx(1.0)

    def test_from_start_end_points(self):
        """Extract plane from start/end points."""
        wall = {
            "start_point": {"x": 0.0, "y": 0.0, "z": 0.0},
            "end_point": {"x": 10.0, "y": 0.0, "z": 0.0}  # Wall along X
        }

        result = get_wall_face_plane(wall)

        assert result is not None
        # Normal should be perpendicular to wall (in Y direction)
        assert abs(result["normal"][1]) == pytest.approx(1.0, rel=0.01)

    def test_empty_wall_returns_none(self):
        """Wall without geometry returns None."""
        wall = {}
        result = get_wall_face_plane(wall)
        assert result is None


class TestPointInWallBounds:
    """Test point-in-wall-bounds checking."""

    def test_point_inside(self):
        """Point inside wall bounds returns True."""
        point = (5.0, 0.0, 5.0)
        wall = {
            "start_point": {"x": 0.0, "y": 0.0, "z": 0.0},
            "end_point": {"x": 10.0, "y": 0.0, "z": 0.0},
            "length": 10.0,
            "height": 9.0,
            "base_elevation": 0.0,
        }

        assert point_in_wall_bounds(point, wall) is True

    def test_point_outside_length(self):
        """Point outside wall length returns False."""
        point = (15.0, 0.0, 5.0)  # Beyond wall end
        wall = {
            "start_point": {"x": 0.0, "y": 0.0, "z": 0.0},
            "end_point": {"x": 10.0, "y": 0.0, "z": 0.0},
            "length": 10.0,
            "height": 9.0,
            "base_elevation": 0.0,
        }

        assert point_in_wall_bounds(point, wall) is False

    def test_point_outside_height(self):
        """Point outside wall height returns False."""
        point = (5.0, 0.0, 15.0)  # Above wall top
        wall = {
            "start_point": {"x": 0.0, "y": 0.0, "z": 0.0},
            "end_point": {"x": 10.0, "y": 0.0, "z": 0.0},
            "length": 10.0,
            "height": 9.0,
            "base_elevation": 0.0,
        }

        assert point_in_wall_bounds(point, wall) is False


class TestVerticalConnectionPoint:
    """Test vertical connection point calculation."""

    def test_offset_into_wall(self):
        """Connection point is offset into wall."""
        entry = (10.0, 5.0, 2.0)
        thickness = 0.333
        normal = (0.0, 1.0, 0.0)  # Wall facing +Y
        system_type = "Sanitary"

        result = calculate_vertical_connection_point(
            entry, thickness, normal, system_type
        )

        # Should be offset into wall (opposite of normal)
        expected_y = entry[1] - (thickness / 2)
        assert result[1] == pytest.approx(expected_y)

    def test_same_elevation(self):
        """Connection point is at same elevation."""
        entry = (10.0, 5.0, 2.5)
        thickness = 0.333
        normal = (0.0, 1.0, 0.0)
        system_type = "Sanitary"

        result = calculate_vertical_connection_point(
            entry, thickness, normal, system_type
        )

        assert result[2] == entry[2]


class TestExtractWallsFromFraming:
    """Test wall extraction from framing data."""

    def test_direct_walls_list(self):
        """Extract walls from direct list."""
        data = {"walls": [{"id": "wall_1"}, {"id": "wall_2"}]}
        result = extract_walls_from_framing(data)
        assert len(result) == 2

    def test_single_wall(self):
        """Extract single wall."""
        data = {"wall_id": "wall_1", "length": 10.0}
        result = extract_walls_from_framing(data)
        assert len(result) == 1

    def test_nested_in_results(self):
        """Extract walls nested in results."""
        data = {
            "results": {
                "walls": [{"id": "wall_1"}]
            }
        }
        result = extract_walls_from_framing(data)
        assert len(result) == 1

    def test_empty_data_returns_empty(self):
        """Empty data returns empty list."""
        result = extract_walls_from_framing({})
        assert result == []


class TestCalculatePipeRoutes:
    """Test the main route calculation function."""

    @pytest.fixture
    def sample_connector(self):
        """Create sample connector."""
        return MEPConnector(
            id="sink_drain",
            origin=(5.0, 2.0, 3.0),
            direction=(0.0, 1.0, 0.0),  # Points toward wall in +Y
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            owner_element_id=12345,
            radius=0.0625,  # 1.5" OD = 0.75" radius
        )

    def test_empty_connectors(self):
        """Empty connectors returns empty routes."""
        result = calculate_pipe_routes([], {}, [], {})
        assert result == []

    def test_no_walls_returns_empty(self, sample_connector):
        """No walls in data returns empty routes."""
        result = calculate_pipe_routes(
            [sample_connector],
            {"walls": []},
            [],
            {}
        )
        assert result == []

    def test_wall_too_far_returns_empty(self, sample_connector):
        """Wall beyond max distance returns no route."""
        walls = {
            "walls": [{
                "id": "wall_1",
                "base_plane": {
                    "origin": {"x": 5.0, "y": 100.0, "z": 0.0},  # 100 ft away
                    "z_axis": {"x": 0.0, "y": -1.0, "z": 0.0}
                },
                "length": 20.0,
                "height": 9.0,
            }]
        }

        result = calculate_pipe_routes(
            [sample_connector],
            walls,
            [],
            {"max_search_distance": 10.0}  # Only search 10 ft
        )

        assert result == []


class TestFindWallEntry:
    """Test wall entry point finding."""

    def test_finds_nearest_wall(self):
        """Finds entry on nearest wall."""
        origin = (5.0, 0.0, 3.0)
        direction = (0.0, 1.0, 0.0)  # +Y direction

        walls = [
            {
                "id": "wall_far",
                "base_plane": {
                    "origin": {"x": 0.0, "y": 20.0, "z": 0.0},
                    "z_axis": {"x": 0.0, "y": -1.0, "z": 0.0}
                },
                "length": 20.0,
                "height": 9.0,
            },
            {
                "id": "wall_near",
                "base_plane": {
                    "origin": {"x": 0.0, "y": 10.0, "z": 0.0},
                    "z_axis": {"x": 0.0, "y": -1.0, "z": 0.0}
                },
                "length": 20.0,
                "height": 9.0,
            },
        ]

        result = find_wall_entry(origin, direction, walls, 25.0)

        assert result is not None
        assert result["wall_id"] == "wall_near"
        assert result["distance"] == pytest.approx(10.0)

    def test_no_wall_in_direction(self):
        """Returns None when no wall in ray direction."""
        origin = (5.0, 0.0, 3.0)
        direction = (0.0, -1.0, 0.0)  # -Y direction (opposite of wall)

        walls = [{
            "id": "wall_1",
            "base_plane": {
                "origin": {"x": 0.0, "y": 10.0, "z": 0.0},
                "z_axis": {"x": 0.0, "y": -1.0, "z": 0.0}
            },
            "length": 20.0,
            "height": 9.0,
        }]

        result = find_wall_entry(origin, direction, walls, 25.0)
        assert result is None
