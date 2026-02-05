# File: tests/mep/routing/test_target_generator.py
"""Tests for Target Candidate Generator and heuristics."""

import pytest
from src.timber_framing_generator.mep.routing.target_generator import (
    TargetCandidateGenerator,
    detect_wet_walls,
    generate_targets_from_walls,
    WetWallInfo,
)
from src.timber_framing_generator.mep.routing.heuristics.base import (
    ConnectorInfo,
    TargetHeuristic,
    FallbackHeuristic,
)
from src.timber_framing_generator.mep.routing.heuristics.plumbing import (
    SanitaryHeuristic,
    VentHeuristic,
    SupplyHeuristic,
)
from src.timber_framing_generator.mep.routing.heuristics.electrical import (
    PowerHeuristic,
    DataHeuristic,
    LightingHeuristic,
)
from src.timber_framing_generator.mep.routing.targets import (
    RoutingTarget,
    TargetType,
)
from src.timber_framing_generator.mep.routing.domains import (
    RoutingDomain,
    RoutingDomainType,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_targets():
    """Create sample routing targets for testing."""
    return [
        # Wet wall target - plumbing
        RoutingTarget(
            id="wet_wall_1",
            target_type=TargetType.WET_WALL,
            location=(10.0, 5.0, 0.0),
            domain_id="wall_A",
            plane_location=(10.0, 5.0),
            systems_served=["Sanitary", "Vent", "DomesticHotWater", "DomesticColdWater"],
            capacity=0.333,
            priority=0
        ),
        # Wet wall target - higher elevation
        RoutingTarget(
            id="wet_wall_2",
            target_type=TargetType.WET_WALL,
            location=(15.0, 5.0, 10.0),
            domain_id="wall_B",
            plane_location=(15.0, 5.0),
            systems_served=["Sanitary", "Vent", "DomesticHotWater"],
            capacity=0.333,
            priority=0
        ),
        # Floor penetration
        RoutingTarget(
            id="floor_pen_1",
            target_type=TargetType.FLOOR_PENETRATION,
            location=(5.0, 5.0, -1.0),
            domain_id="floor_0",
            plane_location=(5.0, 5.0),
            systems_served=["Sanitary", "DomesticHotWater"],
            capacity=0.25,
            priority=5
        ),
        # Ceiling penetration
        RoutingTarget(
            id="ceiling_pen_1",
            target_type=TargetType.CEILING_PENETRATION,
            location=(5.0, 5.0, 8.0),
            domain_id="ceiling_0",
            plane_location=(5.0, 5.0),
            systems_served=["Vent", "Power", "Lighting"],
            capacity=0.167,
            priority=3
        ),
        # Electrical panel boundary
        RoutingTarget(
            id="panel_1",
            target_type=TargetType.PANEL_BOUNDARY,
            location=(20.0, 0.0, 4.0),
            domain_id="wall_C",
            plane_location=(20.0, 4.0),
            systems_served=["Power", "Lighting"],
            capacity=0.167,
            priority=0,
            metadata={"panel_type": "electrical"}
        ),
        # Data panel
        RoutingTarget(
            id="data_panel_1",
            target_type=TargetType.PANEL_BOUNDARY,
            location=(22.0, 0.0, 4.0),
            domain_id="wall_C",
            plane_location=(22.0, 4.0),
            systems_served=["Data", "LowVoltage"],
            capacity=0.125,
            priority=0,
            metadata={"panel_type": "data"}
        ),
    ]


@pytest.fixture
def sample_domains():
    """Create sample routing domains."""
    return [
        RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 20, 0, 8),
            thickness=0.292
        ),
        RoutingDomain(
            id="wall_B",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 20, 10, 18),
            thickness=0.292
        ),
        RoutingDomain(
            id="floor_0",
            domain_type=RoutingDomainType.FLOOR_CAVITY,
            bounds=(0, 30, 0, 20),
            thickness=0.833  # 10" joists
        ),
    ]


@pytest.fixture
def sanitary_connector():
    """Create a sanitary drain connector."""
    return ConnectorInfo(
        id="sink_drain_1",
        system_type="Sanitary",
        location=(8.0, 5.0, 3.0),
        direction="outward",
        diameter=0.125,  # 1.5" drain
        fixture_id="sink_1",
        fixture_type="Sink",
        wall_id="wall_A",
        elevation=3.0
    )


@pytest.fixture
def toilet_connector():
    """Create a toilet drain connector."""
    return ConnectorInfo(
        id="toilet_drain_1",
        system_type="Sanitary",
        location=(12.0, 5.0, 0.5),
        direction="outward",
        diameter=0.25,  # 3" drain
        fixture_id="toilet_1",
        fixture_type="Toilet",
        wall_id="wall_A",
        elevation=0.5
    )


@pytest.fixture
def vent_connector():
    """Create a vent connector."""
    return ConnectorInfo(
        id="sink_vent_1",
        system_type="Vent",
        location=(8.0, 5.0, 3.5),
        direction="outward",
        diameter=0.083,  # 1" vent
        fixture_id="sink_1",
        fixture_type="Sink",
        wall_id="wall_A",
        elevation=3.5
    )


@pytest.fixture
def power_connector():
    """Create a power outlet connector."""
    return ConnectorInfo(
        id="outlet_1",
        system_type="Power",
        location=(15.0, 0.0, 1.0),
        direction="inward",
        diameter=0.042,  # 1/2" conduit
        fixture_id="receptacle_1",
        fixture_type="Outlet",
        wall_id="wall_C",
        elevation=1.0
    )


@pytest.fixture
def data_connector():
    """Create a data jack connector."""
    return ConnectorInfo(
        id="data_jack_1",
        system_type="Data",
        location=(18.0, 0.0, 1.0),
        direction="inward",
        diameter=0.042,
        fixture_id="data_outlet_1",
        fixture_type="DataJack",
        wall_id="wall_C",
        elevation=1.0
    )


# ============================================================================
# ConnectorInfo Tests
# ============================================================================

class TestConnectorInfo:
    """Tests for ConnectorInfo dataclass."""

    def test_create_connector(self, sanitary_connector):
        """Test creating a connector."""
        assert sanitary_connector.id == "sink_drain_1"
        assert sanitary_connector.system_type == "Sanitary"
        assert sanitary_connector.diameter == 0.125
        assert sanitary_connector.fixture_type == "Sink"

    def test_serialization(self, sanitary_connector):
        """Test to_dict and from_dict."""
        data = sanitary_connector.to_dict()
        restored = ConnectorInfo.from_dict(data)

        assert restored.id == sanitary_connector.id
        assert restored.system_type == sanitary_connector.system_type
        assert restored.location == sanitary_connector.location
        assert restored.diameter == sanitary_connector.diameter


# ============================================================================
# Sanitary Heuristic Tests
# ============================================================================

class TestSanitaryHeuristic:
    """Tests for SanitaryHeuristic."""

    def test_system_types(self):
        """Test that heuristic handles correct systems."""
        heuristic = SanitaryHeuristic()
        assert "Sanitary" in heuristic.system_types

    def test_preferred_targets(self):
        """Test preferred target types."""
        heuristic = SanitaryHeuristic()
        assert TargetType.WET_WALL in heuristic.preferred_target_types
        assert TargetType.FLOOR_PENETRATION in heuristic.preferred_target_types
        assert TargetType.CEILING_PENETRATION not in heuristic.preferred_target_types

    def test_prefers_wet_wall(self, sample_targets, sample_domains, sanitary_connector):
        """Test that sanitary prefers wet wall over floor penetration."""
        heuristic = SanitaryHeuristic()
        candidates = heuristic.find_candidates(
            sanitary_connector, sample_targets, sample_domains, max_candidates=5
        )

        assert len(candidates) > 0
        # First candidate should be wet wall (bonus scoring)
        assert candidates[0].target.target_type == TargetType.WET_WALL

    def test_rejects_upward_routing(self, sample_targets, sample_domains, sanitary_connector):
        """Test that sanitary rejects targets above connector."""
        heuristic = SanitaryHeuristic()
        candidates = heuristic.find_candidates(
            sanitary_connector, sample_targets, sample_domains, max_candidates=10
        )

        # wet_wall_2 is at elevation 10, connector at 3 - should be rejected
        for candidate in candidates:
            assert candidate.target.location[2] <= sanitary_connector.elevation

    def test_toilet_requires_minimum_size(self, sample_targets, sample_domains, toilet_connector):
        """Test that toilet drains require 3" minimum."""
        heuristic = SanitaryHeuristic()
        candidates = heuristic.find_candidates(
            toilet_connector, sample_targets, sample_domains, max_candidates=10
        )

        # All candidates should have sufficient capacity for 3" pipe
        for candidate in candidates:
            assert candidate.target.capacity >= toilet_connector.diameter


# ============================================================================
# Vent Heuristic Tests
# ============================================================================

class TestVentHeuristic:
    """Tests for VentHeuristic."""

    def test_system_types(self):
        """Test that heuristic handles correct systems."""
        heuristic = VentHeuristic()
        assert "Vent" in heuristic.system_types

    def test_prefers_wet_wall(self, sample_targets, sample_domains, vent_connector):
        """Test that vent prefers wet wall."""
        heuristic = VentHeuristic()
        candidates = heuristic.find_candidates(
            vent_connector, sample_targets, sample_domains, max_candidates=5
        )

        assert len(candidates) > 0
        # First candidate should be wet wall
        assert candidates[0].target.target_type == TargetType.WET_WALL


# ============================================================================
# Supply Heuristic Tests
# ============================================================================

class TestSupplyHeuristic:
    """Tests for SupplyHeuristic (DHW/DCW)."""

    def test_system_types(self):
        """Test that heuristic handles correct systems."""
        heuristic = SupplyHeuristic()
        assert "DomesticHotWater" in heuristic.system_types
        assert "DomesticColdWater" in heuristic.system_types
        assert "DHW" in heuristic.system_types
        assert "DCW" in heuristic.system_types

    def test_flexible_routing(self, sample_targets, sample_domains):
        """Test that supply allows flexible routing directions."""
        heuristic = SupplyHeuristic()

        # Create connector below target
        connector = ConnectorInfo(
            id="supply_1",
            system_type="DomesticHotWater",
            location=(8.0, 5.0, 2.0),
            direction="inward",
            diameter=0.083,
            elevation=2.0
        )

        candidates = heuristic.find_candidates(
            connector, sample_targets, sample_domains, max_candidates=10
        )

        # Should find candidates both above and below
        assert len(candidates) > 0


# ============================================================================
# Power Heuristic Tests
# ============================================================================

class TestPowerHeuristic:
    """Tests for PowerHeuristic."""

    def test_system_types(self):
        """Test that heuristic handles correct systems."""
        heuristic = PowerHeuristic()
        assert "Power" in heuristic.system_types
        assert "Electrical" in heuristic.system_types

    def test_prefers_panel(self, sample_targets, sample_domains, power_connector):
        """Test that power prefers panel boundary."""
        heuristic = PowerHeuristic()
        candidates = heuristic.find_candidates(
            power_connector, sample_targets, sample_domains, max_candidates=5
        )

        assert len(candidates) > 0
        # First candidate should be panel boundary
        assert candidates[0].target.target_type == TargetType.PANEL_BOUNDARY


# ============================================================================
# Data Heuristic Tests
# ============================================================================

class TestDataHeuristic:
    """Tests for DataHeuristic."""

    def test_system_types(self):
        """Test that heuristic handles correct systems."""
        heuristic = DataHeuristic()
        assert "Data" in heuristic.system_types
        assert "LowVoltage" in heuristic.system_types

    def test_prefers_data_panel(self, sample_targets, sample_domains, data_connector):
        """Test that data prefers data panel over electrical panel."""
        heuristic = DataHeuristic()
        candidates = heuristic.find_candidates(
            data_connector, sample_targets, sample_domains, max_candidates=5
        )

        assert len(candidates) > 0
        # Should prefer the data panel
        data_panel_candidates = [
            c for c in candidates
            if c.target.metadata.get("panel_type") == "data"
        ]
        assert len(data_panel_candidates) > 0


# ============================================================================
# Target Candidate Generator Tests
# ============================================================================

class TestTargetCandidateGenerator:
    """Tests for TargetCandidateGenerator."""

    def test_create_generator(self):
        """Test creating generator with default heuristics."""
        generator = TargetCandidateGenerator()

        # Should have default heuristics registered
        assert generator.get_heuristic("Sanitary") is not None
        assert generator.get_heuristic("Vent") is not None
        assert generator.get_heuristic("Power") is not None

    def test_register_custom_heuristic(self):
        """Test registering a custom heuristic."""
        generator = TargetCandidateGenerator()

        class CustomHeuristic(FallbackHeuristic):
            @property
            def system_types(self):
                return ["CustomSystem"]

        custom = CustomHeuristic()
        generator.register_heuristic(custom)

        assert generator.get_heuristic("CustomSystem") == custom

    def test_add_targets(self, sample_targets):
        """Test adding targets."""
        generator = TargetCandidateGenerator()
        generator.add_targets(sample_targets)

        assert len(generator.targets) == len(sample_targets)

    def test_add_domains(self, sample_domains):
        """Test adding domains."""
        generator = TargetCandidateGenerator()
        generator.add_domains(sample_domains)

        assert len(generator.domains) == len(sample_domains)
        assert generator.get_domain("wall_A") is not None

    def test_find_candidates_sanitary(
        self, sample_targets, sample_domains, sanitary_connector
    ):
        """Test finding candidates for sanitary connector."""
        generator = TargetCandidateGenerator()
        generator.add_targets(sample_targets)
        generator.add_domains(sample_domains)

        candidates = generator.find_candidates(sanitary_connector, max_candidates=3)

        assert len(candidates) > 0
        assert len(candidates) <= 3

    def test_find_candidates_power(
        self, sample_targets, sample_domains, power_connector
    ):
        """Test finding candidates for power connector."""
        generator = TargetCandidateGenerator()
        generator.add_targets(sample_targets)
        generator.add_domains(sample_domains)

        candidates = generator.find_candidates(power_connector, max_candidates=3)

        assert len(candidates) > 0

    def test_find_all_candidates(
        self, sample_targets, sample_domains, sanitary_connector, power_connector
    ):
        """Test finding candidates for multiple connectors."""
        generator = TargetCandidateGenerator()
        generator.add_targets(sample_targets)
        generator.add_domains(sample_domains)

        results = generator.find_all_candidates(
            [sanitary_connector, power_connector],
            max_candidates_per_connector=3
        )

        assert sanitary_connector.id in results
        assert power_connector.id in results
        assert len(results[sanitary_connector.id]) > 0
        assert len(results[power_connector.id]) > 0

    def test_unknown_system_uses_fallback(self, sample_targets, sample_domains):
        """Test that unknown systems use fallback heuristic."""
        generator = TargetCandidateGenerator()
        generator.add_targets(sample_targets)
        generator.add_domains(sample_domains)

        connector = ConnectorInfo(
            id="unknown_1",
            system_type="UnknownSystem",
            location=(5.0, 5.0, 2.0),
            direction="outward",
            diameter=0.083,
            elevation=2.0
        )

        # Should not raise, should use fallback
        candidates = generator.find_candidates(connector)
        # Fallback returns empty if no compatible targets
        assert isinstance(candidates, list)

    def test_serialization(self, sample_targets, sample_domains):
        """Test to_dict and from_dict."""
        generator = TargetCandidateGenerator()
        generator.add_targets(sample_targets)
        generator.add_domains(sample_domains)

        data = generator.to_dict()
        restored = TargetCandidateGenerator.from_dict(data)

        assert len(restored.targets) == len(sample_targets)
        assert len(restored.domains) == len(sample_domains)


# ============================================================================
# Wet Wall Detection Tests
# ============================================================================

class TestWetWallDetection:
    """Tests for wet wall detection."""

    def test_detect_wet_walls(self):
        """Test detecting wet walls from fixtures."""
        walls = [
            {"id": "wall_A", "start": [0, 0, 0], "end": [10, 0, 0]},
            {"id": "wall_B", "start": [0, 5, 0], "end": [10, 5, 0]},
        ]

        connectors = [
            ConnectorInfo(
                id="c1", system_type="Sanitary", location=(2, 0, 3),
                direction="outward", diameter=0.125, wall_id="wall_A",
                fixture_type="Sink"
            ),
            ConnectorInfo(
                id="c2", system_type="DomesticHotWater", location=(3, 0, 3),
                direction="inward", diameter=0.083, wall_id="wall_A",
                fixture_type="Sink"
            ),
            ConnectorInfo(
                id="c3", system_type="Sanitary", location=(5, 0, 1),
                direction="outward", diameter=0.25, wall_id="wall_A",
                fixture_type="Toilet"
            ),
        ]

        wet_walls = detect_wet_walls(walls, connectors)

        assert len(wet_walls) >= 1
        assert wet_walls[0].wall_id == "wall_A"
        assert wet_walls[0].fixture_count == 3

    def test_no_wet_walls_single_fixture(self):
        """Test that single fixture doesn't create wet wall."""
        walls = [
            {"id": "wall_A", "start": [0, 0, 0], "end": [10, 0, 0]},
        ]

        connectors = [
            ConnectorInfo(
                id="c1", system_type="Sanitary", location=(2, 0, 3),
                direction="outward", diameter=0.125, wall_id="wall_A",
                fixture_type="Sink"
            ),
        ]

        wet_walls = detect_wet_walls(walls, connectors)
        assert len(wet_walls) == 0

    def test_toilet_increases_score(self):
        """Test that toilet fixtures increase wet wall score."""
        walls = [
            {"id": "wall_A", "start": [0, 0, 0], "end": [10, 0, 0]},
            {"id": "wall_B", "start": [0, 5, 0], "end": [10, 5, 0]},
        ]

        # Wall A: sink + toilet
        # Wall B: two sinks
        connectors = [
            ConnectorInfo(
                id="c1", system_type="Sanitary", location=(2, 0, 3),
                direction="outward", diameter=0.125, wall_id="wall_A",
                fixture_type="Sink"
            ),
            ConnectorInfo(
                id="c2", system_type="Sanitary", location=(5, 0, 1),
                direction="outward", diameter=0.25, wall_id="wall_A",
                fixture_type="Toilet"
            ),
            ConnectorInfo(
                id="c3", system_type="Sanitary", location=(2, 5, 3),
                direction="outward", diameter=0.125, wall_id="wall_B",
                fixture_type="Sink"
            ),
            ConnectorInfo(
                id="c4", system_type="Sanitary", location=(5, 5, 3),
                direction="outward", diameter=0.125, wall_id="wall_B",
                fixture_type="Sink"
            ),
        ]

        wet_walls = detect_wet_walls(walls, connectors)

        # Wall A should have higher score due to toilet
        wall_a = next((w for w in wet_walls if w.wall_id == "wall_A"), None)
        wall_b = next((w for w in wet_walls if w.wall_id == "wall_B"), None)

        assert wall_a is not None
        assert wall_b is not None
        assert wall_a.score > wall_b.score


# ============================================================================
# Target Generation Tests
# ============================================================================

class TestTargetGeneration:
    """Tests for automatic target generation."""

    def test_generate_targets_from_walls(self):
        """Test generating targets from wall and connector data."""
        walls = [
            {"id": "wall_A", "start": [0, 0, 0], "end": [10, 0, 0]},
        ]

        connectors = [
            ConnectorInfo(
                id="c1", system_type="Sanitary", location=(2, 0, 3),
                direction="outward", diameter=0.125, wall_id="wall_A",
                fixture_type="Sink"
            ),
            ConnectorInfo(
                id="c2", system_type="Sanitary", location=(5, 0, 1),
                direction="outward", diameter=0.25, wall_id="wall_A",
                fixture_type="Toilet"
            ),
        ]

        targets = generate_targets_from_walls(
            walls, connectors, include_floor_penetrations=True
        )

        assert len(targets) >= 1
        # Should have wet wall target
        wet_wall_targets = [t for t in targets if t.target_type == TargetType.WET_WALL]
        assert len(wet_wall_targets) >= 1

    def test_floor_penetration_for_island(self):
        """Test floor penetration generated for island fixtures."""
        walls = [
            {"id": "wall_A", "start": [0, 0, 0], "end": [10, 0, 0]},
        ]

        # Island fixture - no wall_id
        connectors = [
            ConnectorInfo(
                id="island_sink_1", system_type="Sanitary", location=(5, 5, 3),
                direction="outward", diameter=0.125, wall_id=None,  # No wall
                fixture_type="Sink", fixture_id="island_sink"
            ),
        ]

        targets = generate_targets_from_walls(
            walls, connectors, include_floor_penetrations=True
        )

        # Should have floor penetration for island
        floor_pen_targets = [
            t for t in targets if t.target_type == TargetType.FLOOR_PENETRATION
        ]
        assert len(floor_pen_targets) >= 1


# ============================================================================
# FallbackHeuristic Tests
# ============================================================================

class TestFallbackHeuristic:
    """Tests for FallbackHeuristic."""

    def test_accepts_any_system(self):
        """Test that fallback accepts any system type."""
        heuristic = FallbackHeuristic()
        assert heuristic.system_types == []  # Empty = accepts any

    def test_accepts_any_target_type(self):
        """Test that fallback accepts all target types."""
        heuristic = FallbackHeuristic()
        assert len(heuristic.preferred_target_types) == len(TargetType)

    def test_simple_distance_ranking(self, sample_targets, sample_domains):
        """Test that fallback uses simple distance ranking."""
        heuristic = FallbackHeuristic()

        connector = ConnectorInfo(
            id="test_1",
            system_type="Generic",
            location=(5.0, 5.0, 0.0),
            direction="outward",
            diameter=0.083,
            elevation=0.0
        )

        # Add Generic to systems_served for testing
        for target in sample_targets:
            target.systems_served.append("Generic")

        candidates = heuristic.find_candidates(
            connector, sample_targets, sample_domains, max_candidates=10
        )

        # Should return candidates sorted by distance
        if len(candidates) >= 2:
            assert candidates[0].score <= candidates[1].score
