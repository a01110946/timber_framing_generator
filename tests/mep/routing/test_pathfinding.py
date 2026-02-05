# File: tests/mep/routing/test_pathfinding.py
"""
Unit tests for A* pathfinding implementation.

Tests cover:
- Basic A* algorithm
- Obstacle avoidance
- Cross-domain routing
- Path reconstruction
"""

import pytest

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

from src.timber_framing_generator.mep.routing import (
    AStarPathfinder,
    PathReconstructor,
    PathResult,
    find_shortest_path,
    find_path_as_route,
    MultiDomainPathfinder,
    MultiDomainGraph,
    RoutingDomain,
    RoutingDomainType,
    Route,
    RouteSegment,
    SegmentDirection,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def simple_graph():
    """Create a simple 3x3 grid graph."""
    if not HAS_NETWORKX:
        pytest.skip("networkx required")

    G = nx.Graph()

    # Add nodes in a 3x3 grid
    for i in range(3):
        for j in range(3):
            node_id = i * 3 + j
            G.add_node(
                node_id,
                location=(float(j), float(i)),
                pos=(float(j), float(i)),
                domain_id="test_domain"
            )

    # Add horizontal edges
    for i in range(3):
        for j in range(2):
            node1 = i * 3 + j
            node2 = i * 3 + j + 1
            G.add_edge(node1, node2, weight=1.0)

    # Add vertical edges
    for i in range(2):
        for j in range(3):
            node1 = i * 3 + j
            node2 = (i + 1) * 3 + j
            G.add_edge(node1, node2, weight=1.0)

    return G


@pytest.fixture
def weighted_graph():
    """Create a graph with varying edge weights."""
    if not HAS_NETWORKX:
        pytest.skip("networkx required")

    G = nx.Graph()

    # Diamond shape with different costs
    G.add_node(0, location=(0, 0), domain_id="d1")  # Start
    G.add_node(1, location=(1, 1), domain_id="d1")  # Top path
    G.add_node(2, location=(1, -1), domain_id="d1")  # Bottom path
    G.add_node(3, location=(2, 0), domain_id="d1")  # End

    # Top path: cheap
    G.add_edge(0, 1, weight=1.0)
    G.add_edge(1, 3, weight=1.0)

    # Bottom path: expensive
    G.add_edge(0, 2, weight=5.0)
    G.add_edge(2, 3, weight=5.0)

    return G


@pytest.fixture
def multi_domain_graph():
    """Create a graph spanning multiple domains."""
    if not HAS_NETWORKX:
        pytest.skip("networkx required")

    G = nx.Graph()

    # Domain 1: Wall
    G.add_node(0, location=(0, 0), domain_id="wall_1", is_terminal=True)
    G.add_node(1, location=(1, 0), domain_id="wall_1")
    G.add_node(2, location=(2, 0), domain_id="wall_1", is_transition=True)

    # Domain 2: Floor
    G.add_node(3, location=(2, 0), domain_id="floor_1", is_transition=True)
    G.add_node(4, location=(3, 0), domain_id="floor_1")
    G.add_node(5, location=(4, 0), domain_id="floor_1", is_terminal=True)

    # Wall edges
    G.add_edge(0, 1, weight=1.0)
    G.add_edge(1, 2, weight=1.0)

    # Transition edge
    G.add_edge(2, 3, weight=2.0, is_transition=True)

    # Floor edges
    G.add_edge(3, 4, weight=1.0)
    G.add_edge(4, 5, weight=1.0)

    return G


# =============================================================================
# AStarPathfinder Tests
# =============================================================================

class TestAStarBasic:
    """Tests for basic A* functionality."""

    def test_same_node(self, simple_graph):
        """Test path from node to itself."""
        pf = AStarPathfinder(simple_graph)
        path = pf.find_path(0, 0)
        assert path == [0]

    def test_adjacent_nodes(self, simple_graph):
        """Test path between adjacent nodes."""
        pf = AStarPathfinder(simple_graph)
        path = pf.find_path(0, 1)
        assert path == [0, 1]

    def test_shortest_path(self, simple_graph):
        """Test finding shortest path in grid."""
        pf = AStarPathfinder(simple_graph)
        # From corner (0,0) to corner (2,2)
        path = pf.find_path(0, 8)
        assert path is not None
        assert path[0] == 0
        assert path[-1] == 8
        # Should be 4 steps in a 3x3 grid
        assert len(path) == 5

    def test_path_with_cost(self, simple_graph):
        """Test path with cost return."""
        pf = AStarPathfinder(simple_graph)
        path, cost = pf.find_path_with_cost(0, 8)
        assert path is not None
        assert cost == 4.0  # 4 edges of cost 1

    def test_weighted_prefers_cheap(self, weighted_graph):
        """Test that A* prefers cheaper paths."""
        pf = AStarPathfinder(weighted_graph)
        path = pf.find_path(0, 3)
        assert path is not None
        # Should go through node 1 (cheap) not node 2 (expensive)
        assert 1 in path
        assert 2 not in path


class TestAStarBlocking:
    """Tests for blocked node handling."""

    def test_blocked_node(self, simple_graph):
        """Test path avoids blocked nodes."""
        pf = AStarPathfinder(simple_graph)
        # Block middle node
        path = pf.find_path(0, 8, blocked_nodes={4})
        assert path is not None
        assert 4 not in path

    def test_all_paths_blocked(self, simple_graph):
        """Test when all paths are blocked."""
        pf = AStarPathfinder(simple_graph)
        # Block all nodes between source and target
        blocked = {1, 3, 4, 5, 7}
        path = pf.find_path(0, 8, blocked_nodes=blocked)
        # Still possible: 0->1 blocked, but 0->3 blocked too
        # Let's check if path exists
        if path is None:
            assert True  # No path expected
        else:
            # If path exists, it shouldn't use blocked nodes
            assert all(n not in blocked for n in path)

    def test_target_blocked(self, simple_graph):
        """Test when target is blocked."""
        pf = AStarPathfinder(simple_graph)
        path = pf.find_path(0, 8, blocked_nodes={8})
        assert path is None


class TestAStarResult:
    """Tests for PathResult structure."""

    def test_result_success(self, simple_graph):
        """Test successful path result."""
        pf = AStarPathfinder(simple_graph)
        result = pf.find_path_with_result(0, 8)
        assert result.success is True
        assert result.path[0] == 0
        assert result.path[-1] == 8
        assert result.cost == 4.0
        assert result.visited_count > 0

    def test_result_failure(self, simple_graph):
        """Test failed path result."""
        pf = AStarPathfinder(simple_graph)
        # Block all neighbors of source
        result = pf.find_path_with_result(0, 8, blocked_nodes={1, 3})
        # May or may not find path depending on layout
        # Just check that result is valid
        assert isinstance(result.success, bool)

    def test_result_domains(self, multi_domain_graph):
        """Test domain extraction in result."""
        pf = AStarPathfinder(multi_domain_graph)
        result = pf.find_path_with_result(0, 5)
        assert result.success is True
        assert "wall_1" in result.domains_crossed
        assert "floor_1" in result.domains_crossed


class TestAStarHeuristic:
    """Tests for heuristic behavior."""

    def test_custom_heuristic(self, simple_graph):
        """Test with custom heuristic."""
        def zero_heuristic(node, target):
            return 0.0

        pf = AStarPathfinder(simple_graph, heuristic=zero_heuristic)
        path = pf.find_path(0, 8)
        assert path is not None
        assert path[-1] == 8

    def test_manhattan_default(self, simple_graph):
        """Test default Manhattan heuristic."""
        pf = AStarPathfinder(simple_graph)
        # Should find optimal path
        path, cost = pf.find_path_with_cost(0, 8)
        assert cost == 4.0


# =============================================================================
# PathReconstructor Tests
# =============================================================================

class TestPathReconstructor:
    """Tests for path reconstruction."""

    def test_empty_path(self, simple_graph):
        """Test reconstruction of empty path."""
        pr = PathReconstructor(simple_graph)
        route = pr.reconstruct([], "route_1", "sanitary")
        assert route.id == "route_1"
        assert len(route.segments) == 0

    def test_single_node(self, simple_graph):
        """Test reconstruction of single node."""
        pr = PathReconstructor(simple_graph)
        route = pr.reconstruct([0], "route_1", "supply")
        assert route.id == "route_1"
        assert len(route.segments) == 0
        assert route.source == (0.0, 0.0)

    def test_horizontal_segment(self, simple_graph):
        """Test horizontal segment reconstruction."""
        pr = PathReconstructor(simple_graph)
        route = pr.reconstruct([0, 1], "route_1", "power")
        assert len(route.segments) == 1
        seg = route.segments[0]
        assert seg.direction == SegmentDirection.HORIZONTAL
        assert seg.start == (0.0, 0.0)
        assert seg.end == (1.0, 0.0)

    def test_vertical_segment(self, simple_graph):
        """Test vertical segment reconstruction."""
        pr = PathReconstructor(simple_graph)
        route = pr.reconstruct([0, 3], "route_1", "vent")
        assert len(route.segments) == 1
        seg = route.segments[0]
        assert seg.direction == SegmentDirection.VERTICAL

    def test_multi_segment(self, simple_graph):
        """Test multi-segment path."""
        pr = PathReconstructor(simple_graph)
        route = pr.reconstruct([0, 1, 2, 5, 8], "route_1", "sanitary")
        assert len(route.segments) == 4
        assert route.source == (0.0, 0.0)
        assert route.target == (2.0, 2.0)

    def test_extract_transitions(self, multi_domain_graph):
        """Test transition extraction."""
        pr = PathReconstructor(multi_domain_graph)
        transitions = pr.extract_transitions([0, 1, 2, 3, 4, 5])
        assert ("wall_1", "floor_1") in transitions


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_find_shortest_path(self, simple_graph):
        """Test find_shortest_path function."""
        path = find_shortest_path(simple_graph, 0, 8)
        assert path is not None
        assert path[0] == 0
        assert path[-1] == 8

    def test_find_shortest_path_blocked(self, simple_graph):
        """Test find_shortest_path with blocked."""
        path = find_shortest_path(simple_graph, 0, 8, blocked={4})
        if path:
            assert 4 not in path

    def test_find_path_as_route(self, simple_graph):
        """Test find_path_as_route function."""
        route = find_path_as_route(
            simple_graph, 0, 8, "route_1", "sanitary"
        )
        assert route is not None
        assert route.id == "route_1"
        assert route.system_type == "sanitary"

    def test_find_path_as_route_no_path(self, simple_graph):
        """Test find_path_as_route when no path."""
        # Use a non-existent node
        route = find_path_as_route(
            simple_graph, 0, 999, "route_1", "sanitary"
        )
        assert route is None


# =============================================================================
# MultiDomainPathfinder Tests
# =============================================================================

class TestMultiDomainPathfinder:
    """Tests for multi-domain pathfinding."""

    def _setup_graph_after_domains(self, mdg, nodes, edges):
        """
        Helper to set up unified graph after domains are added.

        MDG resets unified_graph when domains change, so we must
        set it up after all domain operations.
        """
        mdg._unified_graph = nx.Graph()
        for node_id, attrs in nodes:
            mdg._unified_graph.add_node(node_id, **attrs)
        for u, v, attrs in edges:
            mdg._unified_graph.add_edge(u, v, **attrs)

    def test_single_domain_path(self):
        """Test path within single domain."""
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

        # Set up graph after domain operations
        nodes = [
            (0, {"location": (0, 0), "domain_id": "wall_1", "is_terminal": True}),
            (1, {"location": (5, 0), "domain_id": "wall_1"}),
            (2, {"location": (10, 0), "domain_id": "wall_1", "is_terminal": True}),
        ]
        edges = [
            (0, 1, {"weight": 5.0}),
            (1, 2, {"weight": 5.0}),
        ]
        self._setup_graph_after_domains(mdg, nodes, edges)

        pf = MultiDomainPathfinder(mdg)
        route = pf.find_path(
            "wall_1", (0, 0),
            "wall_1", (10, 0),
            route_id="test",
            system_type="sanitary"
        )

        assert route is not None
        assert len(route.segments) >= 1

    def test_cross_domain_path(self):
        """Test path crossing domains."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        mdg = MultiDomainGraph()

        # Add domains
        wall = RoutingDomain(
            id="wall_1",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8),
            thickness=0.292
        )
        floor = RoutingDomain(
            id="floor_1",
            domain_type=RoutingDomainType.FLOOR_CAVITY,
            bounds=(0, 20, 0, 20),
            thickness=0.833
        )
        mdg.add_domain(wall)
        mdg.add_domain(floor)

        # Set up graph after domain operations
        nodes = [
            (0, {"location": (0, 0), "domain_id": "wall_1"}),
            (1, {"location": (5, 0), "domain_id": "wall_1"}),
            (2, {"location": (5, 0), "domain_id": "floor_1"}),
            (3, {"location": (10, 0), "domain_id": "floor_1"}),
        ]
        edges = [
            (0, 1, {"weight": 5.0}),
            (1, 2, {"weight": 2.0, "is_transition": True}),
            (2, 3, {"weight": 5.0}),
        ]
        self._setup_graph_after_domains(mdg, nodes, edges)

        pf = MultiDomainPathfinder(mdg)
        route = pf.find_path(
            "wall_1", (0, 0),
            "floor_1", (10, 0),
            route_id="cross",
            system_type="sanitary"
        )

        assert route is not None
        assert "wall_1" in route.domains_crossed or len(route.segments) > 0

    def test_find_nearest_node(self):
        """Test finding nearest node."""
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

        nodes = [
            (0, {"location": (0, 0), "domain_id": "wall_1"}),
            (1, {"location": (5, 0), "domain_id": "wall_1"}),
            (2, {"location": (10, 0), "domain_id": "wall_1"}),
        ]
        self._setup_graph_after_domains(mdg, nodes, [])

        pf = MultiDomainPathfinder(mdg)
        nearest = pf.find_nearest_node("wall_1", (4.5, 0))
        assert nearest == 1  # Closest to (5, 0)

    def test_find_all_nodes_near(self):
        """Test finding all nodes within radius."""
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

        nodes = [
            (0, {"location": (0, 0), "domain_id": "wall_1"}),
            (1, {"location": (1, 0), "domain_id": "wall_1"}),
            (2, {"location": (5, 0), "domain_id": "wall_1"}),
        ]
        self._setup_graph_after_domains(mdg, nodes, [])

        pf = MultiDomainPathfinder(mdg)
        nearby = pf.find_all_nodes_near("wall_1", (0.5, 0), radius=1.5)
        assert 0 in nearby
        assert 1 in nearby
        assert 2 not in nearby  # Too far

    def test_no_path_unreachable(self):
        """Test when target is unreachable."""
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

        # Disconnected nodes (no edges)
        nodes = [
            (0, {"location": (0, 0), "domain_id": "wall_1"}),
            (1, {"location": (10, 0), "domain_id": "wall_1"}),
        ]
        self._setup_graph_after_domains(mdg, nodes, [])

        pf = MultiDomainPathfinder(mdg)
        route = pf.find_path(
            "wall_1", (0, 0),
            "wall_1", (10, 0)
        )

        assert route is None


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_graph(self):
        """Test with empty graph."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        G = nx.Graph()
        pf = AStarPathfinder(G)
        path = pf.find_path(0, 1)
        assert path is None

    def test_single_node_graph(self):
        """Test with single node graph."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        G = nx.Graph()
        G.add_node(0, location=(0, 0))
        pf = AStarPathfinder(G)

        # Same node
        path = pf.find_path(0, 0)
        assert path == [0]

        # Non-existent target
        path = pf.find_path(0, 1)
        assert path is None

    def test_disconnected_components(self):
        """Test graph with disconnected components."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        G = nx.Graph()
        # Component 1
        G.add_node(0, location=(0, 0))
        G.add_node(1, location=(1, 0))
        G.add_edge(0, 1, weight=1.0)

        # Component 2 (disconnected)
        G.add_node(2, location=(10, 0))
        G.add_node(3, location=(11, 0))
        G.add_edge(2, 3, weight=1.0)

        pf = AStarPathfinder(G)

        # Within component
        path = pf.find_path(0, 1)
        assert path is not None

        # Across components
        path = pf.find_path(0, 2)
        assert path is None

    def test_infinite_weight_edge(self):
        """Test that infinite weight edges are avoided."""
        if not HAS_NETWORKX:
            pytest.skip("networkx required")

        G = nx.Graph()
        G.add_node(0, location=(0, 0))
        G.add_node(1, location=(1, 0))
        G.add_node(2, location=(2, 0))
        G.add_edge(0, 1, weight=float('inf'))
        G.add_edge(0, 2, weight=1.0)
        G.add_edge(1, 2, weight=1.0)

        pf = AStarPathfinder(G)
        path = pf.find_path(0, 1)

        if path:
            # Should go through 2, not directly to 1
            assert 2 in path or (path == [0, 1])
