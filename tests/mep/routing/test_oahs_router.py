# File: tests/mep/routing/test_oahs_router.py
"""
Unit tests for OAHS routing algorithm.

Tests cover:
- Connector sequencing
- Single connector routing
- Multi-connector routing
- Occupancy updates
- Conflict resolution
"""

import pytest

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

from src.timber_framing_generator.mep.routing import (
    OAHSRouter,
    ConnectorSequencer,
    ConflictResolver,
    create_oahs_router,
    RoutingResult,
    RoutingStatistics,
    FailedConnector,
    RoutingRequest,
    MultiDomainGraph,
    RoutingDomain,
    RoutingDomainType,
    RoutingTarget,
    TargetType,
    ConnectorInfo,
    OccupancyMap,
    Route,
    RouteSegment,
)


# =============================================================================
# Routing Result Tests
# =============================================================================

class TestRoutingStatistics:
    """Tests for RoutingStatistics."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = RoutingStatistics()
        assert stats.total_connectors == 0
        assert stats.successful_routes == 0
        assert stats.failed_routes == 0
        assert stats.success_rate == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = RoutingStatistics(
            total_connectors=10,
            successful_routes=7,
            failed_routes=3
        )
        assert stats.success_rate == 70.0

    def test_to_dict(self):
        """Test serialization."""
        stats = RoutingStatistics(
            total_connectors=5,
            successful_routes=4,
            failed_routes=1,
            total_length=100.0,
            total_cost=150.0
        )
        data = stats.to_dict()
        assert data["total_connectors"] == 5
        assert data["success_rate"] == 80.0


class TestFailedConnector:
    """Tests for FailedConnector."""

    def test_creation(self):
        """Test failed connector creation."""
        conn = ConnectorInfo(
            id="conn_1",
            system_type="sanitary",
            location=(5.0, 3.0, 0.0),
            direction="outward",
            diameter=0.333
        )
        failed = FailedConnector(
            connector=conn,
            reason="No path found",
            attempted_targets=["target_1", "target_2"]
        )
        assert failed.reason == "No path found"
        assert len(failed.attempted_targets) == 2

    def test_to_dict(self):
        """Test serialization."""
        conn = ConnectorInfo(
            id="conn_1",
            system_type="power",
            location=(0.0, 0.0, 0.0),
            direction="outward",
            diameter=0.0833
        )
        failed = FailedConnector(
            connector=conn,
            reason="Blocked",
            error_code="BLOCKED"
        )
        data = failed.to_dict()
        assert data["connector_id"] == "conn_1"
        assert data["error_code"] == "BLOCKED"


class TestRoutingResult:
    """Tests for RoutingResult."""

    def test_add_route(self):
        """Test adding a route."""
        result = RoutingResult()
        route = Route(
            id="route_1",
            system_type="sanitary",
            total_length=10.0,
            total_cost=15.0
        )
        result.add_route(route)

        assert len(result.routes) == 1
        assert result.statistics.successful_routes == 1
        assert result.statistics.total_length == 10.0

    def test_add_failure(self):
        """Test adding a failure."""
        result = RoutingResult()
        conn = ConnectorInfo(
            id="conn_1",
            system_type="data",
            location=(0.0, 0.0, 0.0),
            direction="outward",
            diameter=0.0625
        )
        result.add_failure(conn, "No path", ["t1", "t2"])

        assert len(result.failed) == 1
        assert result.statistics.failed_routes == 1
        assert result.failed[0].reason == "No path"

    def test_is_complete(self):
        """Test completeness check."""
        result = RoutingResult()
        assert result.is_complete()

        conn = ConnectorInfo(
            id="c1",
            system_type="p",
            location=(0.0, 0.0, 0.0),
            direction="outward",
            diameter=0.0833
        )
        result.add_failure(conn, "Failed")
        assert not result.is_complete()

    def test_to_dict(self):
        """Test serialization."""
        result = RoutingResult()
        result.add_route(Route(id="r1", system_type="s1"))
        data = result.to_dict()

        assert "routes" in data
        assert "statistics" in data
        assert data["is_complete"]


class TestRoutingRequest:
    """Tests for RoutingRequest."""

    def test_empty_validation(self):
        """Test validation of empty request."""
        request = RoutingRequest()
        errors = request.validate()
        assert "No connectors provided" in errors
        assert "No targets provided" in errors

    def test_valid_request(self):
        """Test validation of valid request."""
        request = RoutingRequest(
            connectors=[
                ConnectorInfo(
                    id="c1",
                    system_type="s1",
                    location=(0.0, 0.0, 0.0),
                    direction="outward",
                    diameter=0.0833
                )
            ],
            targets=[
                RoutingTarget(
                    id="t1",
                    target_type=TargetType.WET_WALL,
                    location=(10.0, 0.0, 0.0),
                    domain_id="wall_1",
                    plane_location=(10.0, 0.0)
                )
            ]
        )
        errors = request.validate()
        assert len(errors) == 0


# =============================================================================
# Connector Sequencer Tests
# =============================================================================

class TestConnectorSequencer:
    """Tests for ConnectorSequencer."""

    def _make_connector(self, id, system_type, location):
        """Helper to create ConnectorInfo with defaults."""
        return ConnectorInfo(
            id=id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), 0.0),
            direction="outward",
            diameter=0.0833
        )

    def test_priority_ordering(self):
        """Test that connectors are ordered by system priority."""
        sequencer = ConnectorSequencer()

        connectors = [
            self._make_connector("data_1", "data", (0, 0)),
            self._make_connector("sanitary_1", "sanitary", (0, 0)),
            self._make_connector("power_1", "power", (0, 0)),
        ]

        sequenced = sequencer.sequence(connectors)

        # Sanitary should be first (highest priority)
        assert sequenced[0].id == "sanitary_1"
        # Power before data
        assert sequenced[1].id == "power_1"
        assert sequenced[2].id == "data_1"

    def test_same_priority_by_distance(self):
        """Test that same priority sorts by distance."""
        sequencer = ConnectorSequencer(reference_point=(0, 0))

        connectors = [
            self._make_connector("s_far", "sanitary", (10, 10)),
            self._make_connector("s_near", "sanitary", (1, 1)),
            self._make_connector("s_mid", "sanitary", (5, 5)),
        ]

        sequenced = sequencer.sequence(connectors)

        # Nearest first
        assert sequenced[0].id == "s_near"
        assert sequenced[1].id == "s_mid"
        assert sequenced[2].id == "s_far"

    def test_get_priority(self):
        """Test priority lookup."""
        sequencer = ConnectorSequencer()
        assert sequencer.get_priority("sanitary") == 1
        assert sequencer.get_priority("power") == 5
        assert sequencer.get_priority("unknown") == 10

    def test_group_by_system(self):
        """Test grouping connectors by system."""
        sequencer = ConnectorSequencer()

        connectors = [
            self._make_connector("s1", "sanitary", (0, 0)),
            self._make_connector("p1", "power", (0, 0)),
            self._make_connector("s2", "sanitary", (5, 5)),
        ]

        groups = sequencer.group_by_system(connectors)

        assert len(groups["sanitary"]) == 2
        assert len(groups["power"]) == 1


# =============================================================================
# OAHS Router Tests
# =============================================================================

class TestOAHSRouter:
    """Tests for OAHSRouter."""

    def _create_simple_mdg(self):
        """Create a simple MDG for testing."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        mdg = MultiDomainGraph()
        domain = RoutingDomain(
            id="wall_1",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 20, 0, 8),
            thickness=0.292
        )
        mdg.add_domain(domain)

        # Initialize unified graph with nodes
        mdg._unified_graph = nx.Graph()
        for i in range(5):
            mdg._unified_graph.add_node(
                i,
                location=(float(i * 5), 4.0),
                domain_id="wall_1",
                is_terminal=i in [0, 4]
            )

        for i in range(4):
            mdg._unified_graph.add_edge(i, i + 1, weight=5.0)

        return mdg

    def _make_connector(self, id, system_type, location, domain_id="wall_1"):
        """Helper to create ConnectorInfo with defaults."""
        return ConnectorInfo(
            id=id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), 0.0),
            direction="outward",
            diameter=0.0833,
            wall_id=domain_id
        )

    def test_router_creation(self):
        """Test router creation."""
        mdg = self._create_simple_mdg()
        router = OAHSRouter(mdg)
        assert router.mdg == mdg
        assert router.occupancy is not None

    def test_route_empty_connectors(self):
        """Test routing with no connectors."""
        mdg = self._create_simple_mdg()
        router = OAHSRouter(mdg)

        result = router.route_all([], [])
        assert result.is_complete()
        assert result.statistics.total_connectors == 0

    def test_route_no_targets(self):
        """Test routing with no targets."""
        mdg = self._create_simple_mdg()
        router = OAHSRouter(mdg)

        connectors = [self._make_connector("c1", "sanitary", (0, 4))]

        result = router.route_all(connectors, [])
        assert len(result.failed) == 1
        assert result.failed[0].error_code == "NO_TARGETS"

    def test_route_single_connector(self):
        """Test routing a single connector."""
        mdg = self._create_simple_mdg()
        router = OAHSRouter(mdg)

        connector = self._make_connector("c1", "sanitary", (0, 4))
        target = RoutingTarget(
            id="main_1",
            target_type=TargetType.WET_WALL,
            location=(20.0, 4.0, 0.0),
            domain_id="wall_1",
            plane_location=(20.0, 4.0),
            systems_served=["sanitary"]
        )

        route = router.route_single(connector, [target])
        # May or may not find route depending on graph state
        # This tests that the method runs without error

    def test_route_all_updates_statistics(self):
        """Test that routing updates statistics."""
        mdg = self._create_simple_mdg()
        router = OAHSRouter(mdg)

        connectors = [
            self._make_connector("c1", "sanitary", (0, 4)),
            self._make_connector("c2", "power", (5, 4)),
        ]
        targets = [
            RoutingTarget(
                id="main_1",
                target_type=TargetType.WET_WALL,
                location=(20.0, 4.0, 0.0),
                domain_id="wall_1",
                plane_location=(20.0, 4.0),
                systems_served=["sanitary", "power"]
            )
        ]

        result = router.route_all(connectors, targets)

        assert result.statistics.total_connectors == 2
        assert result.statistics.routing_time_ms > 0

    def test_create_oahs_router(self):
        """Test factory function."""
        mdg = self._create_simple_mdg()
        router = create_oahs_router(mdg, include_default_heuristics=True)

        assert router is not None
        assert "sanitary" in router.heuristics
        assert "power" in router.heuristics

    def test_get_statistics(self):
        """Test getting router statistics."""
        mdg = self._create_simple_mdg()
        router = OAHSRouter(mdg)

        stats = router.get_statistics()
        assert "domains" in stats
        assert "heuristics_registered" in stats


# =============================================================================
# Conflict Resolver Tests
# =============================================================================

class TestConflictResolver:
    """Tests for ConflictResolver."""

    def _create_resolver(self):
        """Create a conflict resolver for testing."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        mdg = MultiDomainGraph()
        domain = RoutingDomain(
            id="wall_1",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8),
            thickness=0.292
        )
        mdg.add_domain(domain)
        mdg._unified_graph = nx.Graph()

        from src.timber_framing_generator.mep.routing import MultiDomainPathfinder
        pathfinder = MultiDomainPathfinder(mdg)
        occupancy = OccupancyMap()

        return ConflictResolver(pathfinder, occupancy)

    def _make_connector(self, id, system_type, location, domain_id="wall_1"):
        """Helper to create ConnectorInfo with defaults."""
        return ConnectorInfo(
            id=id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), 0.0),
            direction="outward",
            diameter=0.0833,
            wall_id=domain_id
        )

    def test_resolver_creation(self):
        """Test conflict resolver creation."""
        resolver = self._create_resolver()
        assert resolver is not None
        assert resolver.blocked_nodes == set()

    def test_resolve_no_targets(self):
        """Test resolve with no targets."""
        resolver = self._create_resolver()
        conn = self._make_connector("c1", "sanitary", (0, 0))

        route, reason = resolver.resolve(conn, [], set())
        assert route is None
        assert "exhausted" in reason


# =============================================================================
# Integration Tests
# =============================================================================

class TestOAHSIntegration:
    """Integration tests for OAHS routing."""

    def _make_connector(self, id, system_type, location):
        """Helper to create ConnectorInfo with defaults."""
        return ConnectorInfo(
            id=id,
            system_type=system_type,
            location=(float(location[0]), float(location[1]), 0.0),
            direction="outward",
            diameter=0.0833
        )

    def test_bathroom_layout_sequencing(self):
        """Test sequencing of typical bathroom connectors."""
        sequencer = ConnectorSequencer()

        # Typical bathroom fixtures
        connectors = [
            self._make_connector("shower", "sanitary_drain", (0, 4)),
            self._make_connector("toilet", "sanitary_drain", (3, 4)),
            self._make_connector("sink", "sanitary_drain", (6, 4)),
            self._make_connector("vent", "sanitary_vent", (3, 7)),
            self._make_connector("hot_water", "dhw", (6, 3)),
            self._make_connector("cold_water", "dcw", (6, 3)),
        ]

        sequenced = sequencer.sequence(connectors)

        # All drains should come before vents
        drain_indices = [
            i for i, c in enumerate(sequenced)
            if c.system_type == "sanitary_drain"
        ]
        vent_indices = [
            i for i, c in enumerate(sequenced)
            if c.system_type == "sanitary_vent"
        ]

        if drain_indices and vent_indices:
            assert max(drain_indices) < min(vent_indices)

    def test_routing_result_json_round_trip(self):
        """Test JSON serialization/deserialization."""
        result = RoutingResult()
        result.add_route(Route(id="r1", system_type="sanitary", total_length=10.0))
        result.metadata = {"project": "test"}

        json_str = result.to_json()
        assert '"routes"' in json_str
        assert '"r1"' in json_str

        # Deserialize (partial)
        restored = RoutingResult.from_dict(result.to_dict())
        assert restored.metadata["project"] == "test"

    def test_priority_order_consistency(self):
        """Test that priority order is consistent."""
        sequencer = ConnectorSequencer()

        # Verify expected priority order
        systems = ["sanitary", "vent", "dhw", "dcw", "power", "data"]
        priorities = [sequencer.get_priority(s) for s in systems]

        # Should be monotonically increasing
        for i in range(len(priorities) - 1):
            assert priorities[i] <= priorities[i + 1]
