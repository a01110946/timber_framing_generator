# File: tests/mep/test_plumbing_system.py
"""Tests for PlumbingSystem class."""

import pytest
from src.timber_framing_generator.mep.plumbing import PlumbingSystem
from src.timber_framing_generator.core import (
    MEPDomain,
    MEPConnector,
    MEPRoute,
)


class TestPlumbingSystemDomain:
    """Test PlumbingSystem domain property."""

    def test_domain_is_plumbing(self):
        """PlumbingSystem returns PLUMBING domain."""
        system = PlumbingSystem()
        assert system.domain == MEPDomain.PLUMBING

    def test_domain_value(self):
        """Domain value is 'plumbing'."""
        system = PlumbingSystem()
        assert system.domain.value == "plumbing"


class TestPlumbingSystemExtractConnectors:
    """Test PlumbingSystem.extract_connectors method."""

    def test_empty_list_returns_empty(self):
        """Empty input returns empty list."""
        system = PlumbingSystem()
        result = system.extract_connectors([])
        assert result == []

    def test_none_input_returns_empty(self):
        """None input returns empty list."""
        system = PlumbingSystem()
        result = system.extract_connectors(None)
        assert result == []


class TestPlumbingSystemCalculateRoutes:
    """Test PlumbingSystem.calculate_routes method."""

    @pytest.fixture
    def sample_connector(self):
        """Create a sample connector for testing."""
        return MEPConnector(
            id="conn_1",
            origin=(10.0, 5.0, 2.0),
            direction=(0.0, 1.0, 0.0),  # Points in Y direction
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            owner_element_id=12345,
            radius=0.0625,  # 1.5" pipe radius = 0.75" = 0.0625'
        )

    @pytest.fixture
    def sample_wall_data(self):
        """Create sample wall data for routing."""
        return {
            "walls": [
                {
                    "id": "wall_1",
                    "base_plane": {
                        "origin": {"x": 10.0, "y": 10.0, "z": 0.0},
                        "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
                        "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                        "z_axis": {"x": 0.0, "y": -1.0, "z": 0.0},  # Normal points -Y
                    },
                    "length": 20.0,
                    "height": 9.0,
                    "thickness": 0.333,
                }
            ]
        }

    def test_empty_connectors_returns_empty(self):
        """Empty connectors list returns empty routes."""
        system = PlumbingSystem()
        result = system.calculate_routes([], {}, [], {})
        assert result == []

    def test_routes_have_correct_domain(self, sample_connector, sample_wall_data):
        """Routes have PLUMBING domain."""
        system = PlumbingSystem()
        routes = system.calculate_routes(
            [sample_connector],
            sample_wall_data,
            [],
            {"max_search_distance": 20.0}
        )

        # Even if route not found due to geometry, test the system
        for route in routes:
            assert route.domain == MEPDomain.PLUMBING


class TestPlumbingSystemGeneratePenetrations:
    """Test PlumbingSystem.generate_penetrations method."""

    def test_empty_routes_returns_empty(self):
        """Empty routes returns empty penetrations."""
        system = PlumbingSystem()
        result = system.generate_penetrations([], [])
        assert result == []


class TestPlumbingSystemValidation:
    """Test PlumbingSystem validation methods."""

    @pytest.fixture
    def sample_route(self):
        """Create a sample route for testing."""
        return MEPRoute(
            id="route_1",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[
                (10.0, 5.0, 2.0),
                (10.0, 10.0, 2.0),
                (10.0, 10.0, 2.0),
            ],
            start_connector_id="conn_1",
            end_point_type="vertical_connection",
            pipe_size=0.125,  # 1.5" diameter
        )

    def test_valid_route_no_issues(self, sample_route):
        """Valid route has no validation issues."""
        system = PlumbingSystem()
        issues = system.validate_routes([sample_route], {})
        assert len(issues) == 0

    def test_missing_pipe_size_flagged(self):
        """Route without pipe size is flagged."""
        route = MEPRoute(
            id="route_no_size",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[(0, 0, 0), (1, 0, 0)],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=None,
        )

        system = PlumbingSystem()
        issues = system.validate_routes([route], {})

        assert len(issues) == 1
        assert issues[0]["issue_type"] == "missing_pipe_size"

    def test_invalid_system_type_flagged(self):
        """Route with unknown system type is flagged."""
        route = MEPRoute(
            id="route_bad_type",
            domain=MEPDomain.PLUMBING,
            system_type="InvalidType",
            path_points=[(0, 0, 0), (1, 0, 0)],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=0.125,
        )

        system = PlumbingSystem()
        issues = system.validate_routes([route], {})

        assert any(i["issue_type"] == "unknown_system_type" for i in issues)

    def test_single_point_route_flagged(self):
        """Route with single point is flagged."""
        route = MEPRoute(
            id="route_short",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[(0, 0, 0)],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=0.125,
        )

        system = PlumbingSystem()
        issues = system.validate_routes([route], {})

        assert any(i["issue_type"] == "invalid_path" for i in issues)


class TestPlumbingSystemSizing:
    """Test PlumbingSystem sizing methods."""

    def test_size_elements_passthrough(self):
        """Phase 1 sizing just passes routes through."""
        route = MEPRoute(
            id="route_1",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[(0, 0, 0), (1, 0, 0)],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=0.125,
        )

        system = PlumbingSystem()
        result = system.size_elements([route], {})

        assert len(result) == 1
        assert result[0].id == route.id
