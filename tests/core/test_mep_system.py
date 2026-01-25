# File: tests/core/test_mep_system.py
"""Tests for MEP system abstractions."""

import pytest
from src.timber_framing_generator.core.mep_system import (
    MEPDomain,
    MEPConnector,
    MEPRoute,
    MEPSystem,
)


class TestMEPDomain:
    """Test cases for MEPDomain enum."""

    def test_all_domains_defined(self):
        """All expected MEP domains are defined."""
        assert hasattr(MEPDomain, "PLUMBING")
        assert hasattr(MEPDomain, "HVAC")
        assert hasattr(MEPDomain, "ELECTRICAL")

    def test_values(self):
        """MEP domains have correct string values."""
        assert MEPDomain.PLUMBING.value == "plumbing"
        assert MEPDomain.HVAC.value == "hvac"
        assert MEPDomain.ELECTRICAL.value == "electrical"

    def test_str(self):
        """String representation returns value."""
        assert str(MEPDomain.PLUMBING) == "plumbing"

    def test_from_string_valid(self):
        """from_string creates correct domain from valid string."""
        assert MEPDomain.from_string("plumbing") == MEPDomain.PLUMBING
        assert MEPDomain.from_string("HVAC") == MEPDomain.HVAC

    def test_from_string_invalid(self):
        """from_string raises ValueError for invalid string."""
        with pytest.raises(ValueError, match="Unknown MEP domain"):
            MEPDomain.from_string("invalid")


class TestMEPConnector:
    """Test cases for MEPConnector dataclass."""

    @pytest.fixture
    def sample_connector(self):
        """Create a sample connector for testing."""
        return MEPConnector(
            id="conn_1",
            origin=(10.0, 5.0, 2.0),
            direction=(0.0, 1.0, 0.0),
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            owner_element_id=12345,
            radius=0.125,  # 1.5" pipe
            flow_direction="Out",
        )

    def test_creation(self, sample_connector):
        """Connector is created with correct attributes."""
        assert sample_connector.id == "conn_1"
        assert sample_connector.origin == (10.0, 5.0, 2.0)
        assert sample_connector.direction == (0.0, 1.0, 0.0)
        assert sample_connector.domain == MEPDomain.PLUMBING
        assert sample_connector.system_type == "Sanitary"
        assert sample_connector.owner_element_id == 12345
        assert sample_connector.radius == 0.125
        assert sample_connector.flow_direction == "Out"

    def test_to_dict(self, sample_connector):
        """to_dict serializes connector correctly."""
        data = sample_connector.to_dict()

        assert data["id"] == "conn_1"
        assert data["origin"]["x"] == 10.0
        assert data["origin"]["y"] == 5.0
        assert data["origin"]["z"] == 2.0
        assert data["direction"]["x"] == 0.0
        assert data["direction"]["y"] == 1.0
        assert data["direction"]["z"] == 0.0
        assert data["domain"] == "plumbing"
        assert data["system_type"] == "Sanitary"
        assert data["owner_element_id"] == 12345
        assert data["radius"] == 0.125
        assert data["flow_direction"] == "Out"

    def test_from_dict(self):
        """from_dict deserializes connector correctly."""
        data = {
            "id": "conn_2",
            "origin": {"x": 1.0, "y": 2.0, "z": 3.0},
            "direction": {"x": 0.0, "y": 0.0, "z": -1.0},
            "domain": "plumbing",
            "system_type": "DomesticColdWater",
            "owner_element_id": 67890,
            "radius": 0.0417,  # 1/2" pipe
        }

        connector = MEPConnector.from_dict(data)

        assert connector.id == "conn_2"
        assert connector.origin == (1.0, 2.0, 3.0)
        assert connector.direction == (0.0, 0.0, -1.0)
        assert connector.domain == MEPDomain.PLUMBING
        assert connector.system_type == "DomesticColdWater"
        assert connector.owner_element_id == 67890
        assert connector.radius == 0.0417

    def test_optional_fields(self):
        """Optional fields default to None."""
        connector = MEPConnector(
            id="minimal",
            origin=(0, 0, 0),
            direction=(0, 0, 1),
            domain=MEPDomain.ELECTRICAL,
            system_type="PowerCircuit",
            owner_element_id=1,
        )

        assert connector.radius is None
        assert connector.flow_direction is None
        assert connector.width is None
        assert connector.height is None


class TestMEPRoute:
    """Test cases for MEPRoute dataclass."""

    @pytest.fixture
    def sample_route(self):
        """Create a sample route for testing."""
        return MEPRoute(
            id="route_1",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[
                (10.0, 5.0, 2.0),
                (10.0, 5.0, 0.5),
                (10.0, 0.0, 0.5),
            ],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=0.125,
        )

    def test_creation(self, sample_route):
        """Route is created with correct attributes."""
        assert sample_route.id == "route_1"
        assert sample_route.domain == MEPDomain.PLUMBING
        assert sample_route.system_type == "Sanitary"
        assert len(sample_route.path_points) == 3
        assert sample_route.start_connector_id == "conn_1"
        assert sample_route.end_point_type == "wall_entry"
        assert sample_route.pipe_size == 0.125

    def test_to_dict(self, sample_route):
        """to_dict serializes route correctly."""
        data = sample_route.to_dict()

        assert data["id"] == "route_1"
        assert data["domain"] == "plumbing"
        assert len(data["path_points"]) == 3
        assert data["path_points"][0]["x"] == 10.0
        assert data["end_point_type"] == "wall_entry"

    def test_from_dict(self):
        """from_dict deserializes route correctly."""
        data = {
            "id": "route_2",
            "domain": "hvac",
            "system_type": "SupplyAir",
            "path_points": [
                {"x": 0.0, "y": 0.0, "z": 8.0},
                {"x": 5.0, "y": 0.0, "z": 8.0},
            ],
            "start_connector_id": "conn_5",
            "end_point_type": "main_line",
            "pipe_size": 0.5,  # 6" duct
        }

        route = MEPRoute.from_dict(data)

        assert route.id == "route_2"
        assert route.domain == MEPDomain.HVAC
        assert len(route.path_points) == 2
        assert route.path_points[1] == (5.0, 0.0, 8.0)

    def test_get_length(self, sample_route):
        """get_length calculates route length correctly."""
        # Path: (10,5,2) -> (10,5,0.5) -> (10,0,0.5)
        # Segment 1: vertical drop of 1.5 ft
        # Segment 2: horizontal run of 5 ft
        # Total: 6.5 ft
        length = sample_route.get_length()
        assert abs(length - 6.5) < 0.001

    def test_get_length_single_point(self):
        """get_length returns 0 for single point."""
        route = MEPRoute(
            id="short",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[(0, 0, 0)],
            start_connector_id="c1",
            end_point_type="wall_entry",
        )
        assert route.get_length() == 0.0


class TestMEPSystemABC:
    """Test that MEPSystem is properly abstract."""

    def test_cannot_instantiate(self):
        """Cannot instantiate MEPSystem directly."""
        with pytest.raises(TypeError, match="abstract"):
            MEPSystem()

    def test_subclass_must_implement(self):
        """Subclass must implement abstract methods."""

        class IncompleteSystem(MEPSystem):
            @property
            def domain(self):
                return MEPDomain.PLUMBING

        # Missing other abstract methods
        with pytest.raises(TypeError, match="abstract"):
            IncompleteSystem()


class TestMEPImports:
    """Test that MEP types can be imported from various paths."""

    def test_import_from_core(self):
        """Can import from core module."""
        from src.timber_framing_generator.core import (
            MEPDomain,
            MEPConnector,
            MEPRoute,
            MEPSystem,
        )
        assert MEPDomain.PLUMBING.value == "plumbing"

    def test_import_from_mep_module(self):
        """Can import from mep module."""
        from src.timber_framing_generator.mep import (
            MEPDomain,
            MEPConnector,
            MEPRoute,
        )
        assert MEPDomain.HVAC.value == "hvac"

    def test_import_from_mep_core(self):
        """Can import from mep.core module."""
        from src.timber_framing_generator.mep.core import MEPConnector
        connector = MEPConnector(
            id="test",
            origin=(0, 0, 0),
            direction=(0, 0, 1),
            domain=MEPDomain.ELECTRICAL,
            system_type="PowerCircuit",
            owner_element_id=1,
        )
        assert connector.id == "test"
