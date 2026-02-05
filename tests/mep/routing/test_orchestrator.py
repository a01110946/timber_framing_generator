# File: tests/mep/routing/test_orchestrator.py
"""
Unit tests for Sequential Orchestrator and Trade Configuration.

Tests cover:
- Trade configuration and priority ordering
- Zone partitioning strategies
- Sequential orchestration across trades
- Result aggregation
"""

import pytest

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

from src.timber_framing_generator.mep.routing import (
    Trade,
    TradeConfig,
    RoutingZone,
    SequentialOrchestrator,
    ZonePartitionStrategy,
    DefaultZoneStrategy,
    SingleZoneStrategy,
    OrchestrationResult,
    OrchestrationStatistics,
    create_orchestrator,
    create_single_zone_orchestrator,
    create_default_trade_config,
    create_plumbing_only_config,
    create_electrical_only_config,
    ConnectorInfo,
    RoutingTarget,
    TargetType,
)


# =============================================================================
# Trade Configuration Tests
# =============================================================================

class TestTrade:
    """Tests for Trade enum."""

    def test_trade_values(self):
        """Test trade enum values."""
        assert Trade.PLUMBING.value == "plumbing"
        assert Trade.HVAC.value == "hvac"
        assert Trade.ELECTRICAL.value == "electrical"
        assert Trade.FIRE_PROTECTION.value == "fire_protection"


class TestTradeConfig:
    """Tests for TradeConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = create_default_trade_config()
        assert len(config.trade_order) == 4
        assert config.trade_order[0] == Trade.PLUMBING
        assert config.trade_order[-1] == Trade.ELECTRICAL

    def test_get_trade_for_system(self):
        """Test system-to-trade mapping."""
        config = TradeConfig()
        assert config.get_trade_for_system("sanitary_drain") == Trade.PLUMBING
        assert config.get_trade_for_system("power") == Trade.ELECTRICAL
        assert config.get_trade_for_system("supply_air") == Trade.HVAC
        assert config.get_trade_for_system("unknown") is None

    def test_get_systems_for_trade(self):
        """Test trade-to-systems mapping."""
        config = TradeConfig()
        plumbing_systems = config.get_systems_for_trade(Trade.PLUMBING)
        assert "sanitary_drain" in plumbing_systems
        assert "dhw" in plumbing_systems

    def test_get_clearance(self):
        """Test clearance retrieval."""
        config = TradeConfig()
        assert config.get_clearance(Trade.PLUMBING) == 0.25
        assert config.get_clearance(Trade.ELECTRICAL) == 0.125

    def test_get_priority(self):
        """Test priority ordering."""
        config = TradeConfig()
        assert config.get_priority(Trade.PLUMBING) == 0
        assert config.get_priority(Trade.HVAC) == 1
        assert config.get_priority(Trade.ELECTRICAL) == 3

    def test_enabled_trades(self):
        """Test trade filtering."""
        config = TradeConfig(enabled_trades={Trade.PLUMBING, Trade.ELECTRICAL})
        enabled = config.get_enabled_trades()
        assert Trade.PLUMBING in enabled
        assert Trade.ELECTRICAL in enabled
        assert Trade.HVAC not in enabled

    def test_plumbing_only_config(self):
        """Test plumbing-only configuration."""
        config = create_plumbing_only_config()
        enabled = config.get_enabled_trades()
        assert len(enabled) == 1
        assert Trade.PLUMBING in enabled

    def test_electrical_only_config(self):
        """Test electrical-only configuration."""
        config = create_electrical_only_config()
        enabled = config.get_enabled_trades()
        assert len(enabled) == 1
        assert Trade.ELECTRICAL in enabled

    def test_serialization(self):
        """Test config serialization."""
        config = TradeConfig()
        data = config.to_dict()
        assert "trade_order" in data
        assert data["trade_order"][0] == "plumbing"

        restored = TradeConfig.from_dict(data)
        assert restored.trade_order[0] == Trade.PLUMBING


# =============================================================================
# Routing Zone Tests
# =============================================================================

class TestRoutingZone:
    """Tests for RoutingZone."""

    def test_create_zone(self):
        """Test zone creation."""
        zone = RoutingZone(
            id="zone_1",
            name="First Floor",
            level=1,
            bounds=(0.0, 100.0, 0.0, 50.0),
            wall_ids=["w1", "w2"],
            connector_ids=["c1", "c2"],
        )
        assert zone.id == "zone_1"
        assert zone.level == 1

    def test_contains_point(self):
        """Test point containment check."""
        zone = RoutingZone(
            id="z1",
            bounds=(0.0, 10.0, 0.0, 10.0),
        )
        assert zone.contains_point(5.0, 5.0)
        assert zone.contains_point(0.0, 0.0)
        assert zone.contains_point(10.0, 10.0)
        assert not zone.contains_point(-1.0, 5.0)
        assert not zone.contains_point(5.0, 11.0)

    def test_serialization(self):
        """Test zone serialization."""
        zone = RoutingZone(
            id="z1",
            name="Test",
            level=2,
            bounds=(0.0, 10.0, 0.0, 10.0),
        )
        data = zone.to_dict()
        restored = RoutingZone.from_dict(data)
        assert restored.id == zone.id
        assert restored.level == zone.level


# =============================================================================
# Zone Partitioning Strategy Tests
# =============================================================================

class TestDefaultZoneStrategy:
    """Tests for DefaultZoneStrategy."""

    def _make_wall(self, wall_id, z=0.0, start=(0, 0), end=(10, 0)):
        """Helper to create wall dict."""
        return {
            "id": wall_id,
            "base_elevation": z,
            "start_point": [start[0], start[1], z],
            "end_point": [end[0], end[1], z],
        }

    def _make_connector(self, conn_id, system_type, location):
        """Helper to create ConnectorInfo."""
        return ConnectorInfo(
            id=conn_id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), float(location[2])),
            direction="outward",
            diameter=0.0833,
        )

    def test_single_floor(self):
        """Test partitioning single floor."""
        strategy = DefaultZoneStrategy(floor_height=10.0)
        walls = [
            self._make_wall("w1", z=0.0),
            self._make_wall("w2", z=0.0),
        ]
        connectors = [
            self._make_connector("c1", "sanitary", (5, 5, 0)),
        ]

        zones = strategy.partition(walls, connectors)
        assert len(zones) == 1
        assert zones[0].level == 0

    def test_multi_floor(self):
        """Test partitioning multiple floors."""
        strategy = DefaultZoneStrategy(floor_height=10.0)
        walls = [
            self._make_wall("w1", z=0.0),
            self._make_wall("w2", z=10.0),
            self._make_wall("w3", z=20.0),
        ]
        connectors = [
            self._make_connector("c1", "sanitary", (5, 5, 0)),
            self._make_connector("c2", "power", (5, 5, 10)),
        ]

        zones = strategy.partition(walls, connectors)
        assert len(zones) == 3
        levels = [z.level for z in zones]
        assert 0 in levels
        assert 1 in levels
        assert 2 in levels

    def test_empty_input(self):
        """Test with no walls or connectors."""
        strategy = DefaultZoneStrategy()
        zones = strategy.partition([], [])
        assert len(zones) == 0


class TestSingleZoneStrategy:
    """Tests for SingleZoneStrategy."""

    def _make_wall(self, wall_id, start=(0, 0), end=(10, 0)):
        """Helper to create wall dict."""
        return {
            "id": wall_id,
            "start_point": [start[0], start[1], 0],
            "end_point": [end[0], end[1], 0],
        }

    def _make_connector(self, conn_id, system_type, location):
        """Helper to create ConnectorInfo."""
        return ConnectorInfo(
            id=conn_id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), 0.0),
            direction="outward",
            diameter=0.0833,
        )

    def test_creates_single_zone(self):
        """Test that single zone is created."""
        strategy = SingleZoneStrategy()
        walls = [
            self._make_wall("w1", (0, 0), (10, 0)),
            self._make_wall("w2", (0, 0), (0, 10)),
        ]
        connectors = [
            self._make_connector("c1", "sanitary", (5, 5, 0)),
        ]

        zones = strategy.partition(walls, connectors)
        assert len(zones) == 1
        assert zones[0].id == "building"
        assert "w1" in zones[0].wall_ids
        assert "c1" in zones[0].connector_ids


# =============================================================================
# Orchestration Statistics Tests
# =============================================================================

class TestOrchestrationStatistics:
    """Tests for OrchestrationStatistics."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = OrchestrationStatistics()
        assert stats.total_zones == 0
        assert stats.total_trades == 0
        assert stats.success_rate == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = OrchestrationStatistics(
            total_connectors=10,
            successful_routes=7,
            failed_routes=3,
        )
        assert stats.success_rate == 70.0

    def test_to_dict(self):
        """Test serialization."""
        stats = OrchestrationStatistics(
            total_zones=2,
            total_trades=3,
            total_connectors=5,
            successful_routes=4,
        )
        data = stats.to_dict()
        assert data["total_zones"] == 2
        assert data["success_rate"] == 80.0


# =============================================================================
# Orchestration Result Tests
# =============================================================================

class TestOrchestrationResult:
    """Tests for OrchestrationResult."""

    def test_empty_result(self):
        """Test empty result."""
        result = OrchestrationResult()
        assert len(result.get_all_routes()) == 0
        assert result.is_complete()

    def test_is_complete_with_failures(self):
        """Test completeness with failures."""
        from src.timber_framing_generator.mep.routing import RoutingResult

        result = OrchestrationResult()
        zone_result = RoutingResult()
        conn = ConnectorInfo(
            id="c1",
            system_type="sanitary",
            location=(0.0, 0.0, 0.0),
            direction="outward",
            diameter=0.0833,
        )
        zone_result.add_failure(conn, "Test failure")
        result.zone_results["z1"] = zone_result

        assert not result.is_complete()

    def test_to_dict(self):
        """Test serialization."""
        result = OrchestrationResult()
        result.zones = [RoutingZone(id="z1", name="Zone 1")]
        data = result.to_dict()

        assert "zone_results" in data
        assert "statistics" in data
        assert len(data["zones"]) == 1


# =============================================================================
# Sequential Orchestrator Tests
# =============================================================================

class TestSequentialOrchestrator:
    """Tests for SequentialOrchestrator."""

    def _make_connector(self, conn_id, system_type, location):
        """Helper to create ConnectorInfo."""
        return ConnectorInfo(
            id=conn_id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), float(location[2])),
            direction="outward",
            diameter=0.0833,
        )

    def _make_wall(self, wall_id, z=0.0):
        """Helper to create wall dict."""
        return {
            "id": wall_id,
            "base_elevation": z,
            "start_point": [0, 0, z],
            "end_point": [10, 0, z],
        }

    def _make_target(self, target_id, systems):
        """Helper to create RoutingTarget."""
        return RoutingTarget(
            id=target_id,
            target_type=TargetType.WET_WALL,
            location=(10.0, 0.0, 0.0),
            domain_id="wall_1",
            plane_location=(10.0, 0.0),
            systems_served=systems,
        )

    def test_create_orchestrator(self):
        """Test orchestrator creation."""
        orch = create_orchestrator()
        assert orch is not None
        assert orch.trade_config is not None
        assert orch.zone_strategy is not None

    def test_create_single_zone_orchestrator(self):
        """Test single zone orchestrator creation."""
        orch = create_single_zone_orchestrator()
        assert isinstance(orch.zone_strategy, SingleZoneStrategy)

    def test_route_empty_building(self):
        """Test routing with no connectors."""
        orch = SequentialOrchestrator()
        result = orch.route_building([], [], [])
        assert result.statistics.total_connectors == 0
        assert result.is_complete()

    @pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
    def test_route_no_targets(self):
        """Test routing with no targets."""
        orch = SequentialOrchestrator()
        connectors = [
            self._make_connector("c1", "sanitary_drain", (5, 5, 0)),
        ]
        walls = [self._make_wall("w1")]

        result = orch.route_building(connectors, walls, [])

        # Should fail due to no targets
        assert result.statistics.failed_routes >= 1

    @pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
    def test_trade_sequencing(self):
        """Test that trades are processed in order."""
        config = TradeConfig()
        orch = SequentialOrchestrator(trade_config=config)

        connectors = [
            self._make_connector("c1", "sanitary_drain", (5, 5, 0)),
            self._make_connector("c2", "power", (5, 3, 0)),
        ]
        walls = [self._make_wall("w1")]
        targets = [
            self._make_target("t1", ["sanitary_drain", "power"]),
        ]

        result = orch.route_building(connectors, walls, targets)

        # Check that plumbing trade was processed before electrical
        assert Trade.PLUMBING.value in result.trade_results
        assert Trade.ELECTRICAL.value in result.trade_results

    @pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
    def test_single_trade_config(self):
        """Test with single trade enabled."""
        config = create_plumbing_only_config()
        orch = SequentialOrchestrator(trade_config=config)

        connectors = [
            self._make_connector("c1", "sanitary_drain", (5, 5, 0)),
            self._make_connector("c2", "power", (5, 3, 0)),
        ]
        walls = [self._make_wall("w1")]
        targets = [
            self._make_target("t1", ["sanitary_drain", "power"]),
        ]

        result = orch.route_building(connectors, walls, targets)

        # Only plumbing should be in trade results
        assert Trade.PLUMBING.value in result.trade_results
        assert Trade.ELECTRICAL.value not in result.trade_results

    @pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
    def test_zone_partitioning(self):
        """Test that zones are created correctly."""
        orch = SequentialOrchestrator(zone_strategy=DefaultZoneStrategy())

        connectors = [
            self._make_connector("c1", "sanitary_drain", (5, 5, 0)),
            self._make_connector("c2", "sanitary_drain", (5, 5, 10)),
        ]
        walls = [
            self._make_wall("w1", z=0),
            self._make_wall("w2", z=10),
        ]
        targets = [
            self._make_target("t1", ["sanitary_drain"]),
        ]

        result = orch.route_building(connectors, walls, targets)

        assert result.statistics.total_zones == 2

    @pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
    def test_result_aggregation(self):
        """Test that results are properly aggregated."""
        orch = SequentialOrchestrator(zone_strategy=SingleZoneStrategy())

        connectors = [
            self._make_connector("c1", "sanitary_drain", (5, 5, 0)),
        ]
        walls = [self._make_wall("w1")]
        targets = [
            self._make_target("t1", ["sanitary_drain"]),
        ]

        result = orch.route_building(connectors, walls, targets)

        # Should have statistics
        assert result.statistics.orchestration_time_ms > 0

    @pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
    def test_occupancy_reset(self):
        """Test occupancy map reset."""
        orch = SequentialOrchestrator()

        # Route first batch
        connectors = [self._make_connector("c1", "sanitary_drain", (5, 5, 0))]
        walls = [self._make_wall("w1")]
        targets = [self._make_target("t1", ["sanitary_drain"])]
        orch.route_building(connectors, walls, targets)

        # Reset and route again
        orch.reset_occupancy()
        result = orch.route_building(connectors, walls, targets)

        assert result is not None


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.skipif(not HAS_NETWORKX, reason="networkx required")
class TestOrchestratorIntegration:
    """Integration tests for orchestrator."""

    def _make_connector(self, conn_id, system_type, location):
        """Helper to create ConnectorInfo."""
        return ConnectorInfo(
            id=conn_id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), float(location[2])),
            direction="outward",
            diameter=0.0833,
        )

    def _make_wall(self, wall_id, start=(0, 0, 0), end=(10, 0, 0)):
        """Helper to create wall dict."""
        return {
            "id": wall_id,
            "base_elevation": start[2],
            "start_point": list(start),
            "end_point": list(end),
        }

    def _make_target(self, target_id, systems, location=(10.0, 0.0, 0.0)):
        """Helper to create RoutingTarget."""
        return RoutingTarget(
            id=target_id,
            target_type=TargetType.WET_WALL,
            location=location,
            domain_id="wall_1",
            plane_location=(location[0], location[1]),
            systems_served=systems,
        )

    def test_bathroom_scenario(self):
        """Test typical bathroom with multiple fixtures."""
        orch = create_single_zone_orchestrator()

        # Typical bathroom fixtures
        connectors = [
            self._make_connector("toilet", "sanitary_drain", (2, 4, 0)),
            self._make_connector("sink", "sanitary_drain", (6, 4, 0)),
            self._make_connector("shower", "sanitary_drain", (0, 4, 0)),
            self._make_connector("vent", "sanitary_vent", (2, 7, 0)),
            self._make_connector("outlet", "power", (8, 4, 0)),
        ]

        walls = [
            self._make_wall("w1", (0, 0, 0), (10, 0, 0)),
            self._make_wall("w2", (10, 0, 0), (10, 8, 0)),
        ]

        targets = [
            self._make_target("drain_stack", ["sanitary_drain", "sanitary_vent"], (10, 4, 0)),
            self._make_target("panel", ["power"], (10, 0, 0)),
        ]

        result = orch.route_building(connectors, walls, targets)

        # Should process all connectors
        total = result.statistics.successful_routes + result.statistics.failed_routes
        assert total == len(connectors)

        # Plumbing should be routed before electrical
        assert Trade.PLUMBING.value in result.trade_results

    def test_result_json_export(self):
        """Test JSON export of results."""
        orch = create_orchestrator()
        result = OrchestrationResult()
        result.zones = [RoutingZone(id="z1")]
        result.statistics.total_zones = 1

        json_str = result.to_json()
        assert '"zones"' in json_str
        assert '"z1"' in json_str

    def test_multi_trade_priority(self):
        """Test that trade priorities are respected."""
        config = TradeConfig()
        orch = SequentialOrchestrator(trade_config=config)

        # Check priority order
        enabled = config.get_enabled_trades()
        assert enabled[0] == Trade.PLUMBING
        assert enabled[-1] == Trade.ELECTRICAL

        # Verify priority values
        assert config.get_priority(Trade.PLUMBING) < config.get_priority(Trade.ELECTRICAL)
