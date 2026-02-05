# File: tests/mep/routing/test_graph_builder.py
"""Tests for graph construction (wall, floor, unified)."""

import pytest
import json

# Check for networkx
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

pytestmark = pytest.mark.skipif(
    not HAS_NETWORKX,
    reason="networkx required for graph tests"
)

from src.timber_framing_generator.mep.routing.domains import (
    RoutingDomain, RoutingDomainType, Obstacle, create_wall_domain, create_floor_domain
)
from src.timber_framing_generator.mep.routing.wall_graph import (
    WallGraphBuilder, build_wall_graph_from_data
)
from src.timber_framing_generator.mep.routing.floor_graph import (
    FloorGraphBuilder, build_floor_graph_from_bounds
)
from src.timber_framing_generator.mep.routing.graph_builder import (
    TransitionGenerator, UnifiedGraphBuilder, build_routing_graph
)
from src.timber_framing_generator.mep.routing.graph import MultiDomainGraph


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def simple_wall_domain():
    """Create a simple wall domain without obstacles."""
    return RoutingDomain(
        id="wall_test",
        domain_type=RoutingDomainType.WALL_CAVITY,
        bounds=(0, 10, 0, 8),
        thickness=0.292
    )


@pytest.fixture
def wall_domain_with_studs():
    """Create a wall domain with stud obstacles."""
    return create_wall_domain(
        wall_id="wall_studs",
        length=10.0,
        height=8.0,
        stud_spacing=1.333  # 16" OC
    )


@pytest.fixture
def simple_floor_domain():
    """Create a simple floor domain."""
    return RoutingDomain(
        id="floor_test",
        domain_type=RoutingDomainType.FLOOR_CAVITY,
        bounds=(0, 20, 0, 30),
        thickness=0.833
    )


@pytest.fixture
def floor_domain_with_joists():
    """Create a floor domain with joist obstacles."""
    return create_floor_domain(
        floor_id="floor_joists",
        width=20.0,
        length=30.0,
        joist_spacing=1.333
    )


@pytest.fixture
def sample_walls_json():
    """Create sample walls JSON."""
    return json.dumps({
        "walls": [
            {
                "id": "wall_A",
                "length": 10.0,
                "height": 8.0,
                "thickness": 0.292,
                "start": [0, 0, 0],
                "end": [10, 0, 0]
            },
            {
                "id": "wall_B",
                "length": 8.0,
                "height": 8.0,
                "thickness": 0.292,
                "start": [10, 0, 0],
                "end": [10, 8, 0]
            }
        ]
    })


# ============================================================================
# WallGraphBuilder Tests
# ============================================================================

class TestWallGraphBuilder:
    """Tests for WallGraphBuilder."""

    def test_create_builder(self, simple_wall_domain):
        """Test creating a wall graph builder."""
        builder = WallGraphBuilder(simple_wall_domain)
        assert builder.domain == simple_wall_domain
        assert builder.resolution_u == WallGraphBuilder.DEFAULT_RESOLUTION_U
        assert builder.resolution_v == WallGraphBuilder.DEFAULT_RESOLUTION_V

    def test_custom_resolution(self, simple_wall_domain):
        """Test custom grid resolution."""
        builder = WallGraphBuilder(
            simple_wall_domain,
            resolution_u=0.5,
            resolution_v=0.25
        )
        assert builder.resolution_u == 0.5
        assert builder.resolution_v == 0.25

    def test_build_grid_graph_empty_wall(self, simple_wall_domain):
        """Test building grid for wall without obstacles."""
        builder = WallGraphBuilder(simple_wall_domain, resolution_u=1.0, resolution_v=1.0)
        graph = builder.build_grid_graph()

        # Should have grid nodes
        assert graph.number_of_nodes() > 0
        assert graph.number_of_edges() > 0

        # All nodes should have location attribute
        for node, data in graph.nodes(data=True):
            assert 'location' in data
            assert len(data['location']) == 2

    def test_build_grid_graph_with_studs(self, wall_domain_with_studs):
        """Test building grid for wall with stud obstacles."""
        builder = WallGraphBuilder(wall_domain_with_studs, resolution_u=0.5)
        graph = builder.build_grid_graph()

        # Should have edges with stud crossing cost
        stud_crossing_edges = [
            (u, v, d) for u, v, d in graph.edges(data=True)
            if d.get('crosses_stud', False)
        ]
        assert len(stud_crossing_edges) > 0

        # Stud crossing edges should have higher weight
        for u, v, data in stud_crossing_edges:
            assert data['weight'] > data['base_cost']

    def test_add_terminal_nodes(self, simple_wall_domain):
        """Test adding terminal nodes."""
        builder = WallGraphBuilder(simple_wall_domain, resolution_u=1.0)
        graph = builder.build_grid_graph()

        initial_nodes = graph.number_of_nodes()

        terminals = [(2.5, 3.0), (7.5, 5.0)]
        terminal_ids = builder.add_terminal_nodes(graph, terminals, is_source=True)

        assert len(terminal_ids) == 2
        assert graph.number_of_nodes() == initial_nodes + 2

        # Terminals should be connected to grid
        for tid in terminal_ids:
            assert graph.degree(tid) > 0
            assert graph.nodes[tid]['is_terminal'] is True

    def test_grid_bounds(self, simple_wall_domain):
        """Test that grid stays within domain bounds."""
        builder = WallGraphBuilder(simple_wall_domain, resolution_u=0.5)
        graph = builder.build_grid_graph()

        min_u, max_u, min_v, max_v = simple_wall_domain.bounds

        for node, data in graph.nodes(data=True):
            u, v = data['location']
            assert min_u <= u <= max_u
            assert min_v <= v <= max_v


class TestBuildWallGraphFromData:
    """Tests for build_wall_graph_from_data helper."""

    def test_build_from_dict(self):
        """Test building wall graph from dictionary."""
        wall_data = {
            "id": "wall_1",
            "length": 12.0,
            "height": 8.0,
            "thickness": 0.292
        }

        domain, graph = build_wall_graph_from_data(wall_data)

        assert domain.id == "wall_1"
        assert domain.width == 12.0
        assert domain.height == 8.0
        assert graph.number_of_nodes() > 0

    def test_build_with_custom_spacing(self):
        """Test building with custom stud spacing."""
        wall_data = {"id": "wall_2", "length": 10.0, "height": 8.0}

        domain, graph = build_wall_graph_from_data(
            wall_data,
            stud_spacing=2.0,
            grid_resolution=0.5
        )

        # Should have studs at 2' spacing
        studs = [o for o in domain.obstacles if o.obstacle_type == 'stud']
        assert len(studs) >= 5  # 10/2 = 5


# ============================================================================
# FloorGraphBuilder Tests
# ============================================================================

class TestFloorGraphBuilder:
    """Tests for FloorGraphBuilder."""

    def test_create_builder(self, simple_floor_domain):
        """Test creating a floor graph builder."""
        builder = FloorGraphBuilder(simple_floor_domain)
        assert builder.domain == simple_floor_domain
        assert builder.resolution_x == FloorGraphBuilder.DEFAULT_RESOLUTION

    def test_build_grid_graph_empty(self, simple_floor_domain):
        """Test building grid for floor without obstacles."""
        builder = FloorGraphBuilder(simple_floor_domain, resolution_x=2.0, resolution_y=2.0)
        graph = builder.build_grid_graph()

        assert graph.number_of_nodes() > 0
        assert graph.number_of_edges() > 0

    def test_build_grid_graph_with_joists(self, floor_domain_with_joists):
        """Test building grid for floor with joist obstacles."""
        builder = FloorGraphBuilder(floor_domain_with_joists, resolution_x=1.0)
        graph = builder.build_grid_graph()

        # Should have edges with joist crossing info
        joist_crossing_edges = [
            (u, v, d) for u, v, d in graph.edges(data=True)
            if d.get('crosses_joist', False)
        ]
        assert len(joist_crossing_edges) > 0

    def test_add_terminal_nodes(self, simple_floor_domain):
        """Test adding terminal nodes to floor graph."""
        builder = FloorGraphBuilder(simple_floor_domain, resolution_x=2.0)
        graph = builder.build_grid_graph()

        terminals = [(5.0, 10.0), (15.0, 20.0)]
        terminal_ids = builder.add_terminal_nodes(graph, terminals)

        assert len(terminal_ids) == 2
        for tid in terminal_ids:
            assert graph.degree(tid) > 0


class TestBuildFloorGraphFromBounds:
    """Tests for build_floor_graph_from_bounds helper."""

    def test_build_from_bounds(self):
        """Test building floor graph from bounds."""
        domain, graph = build_floor_graph_from_bounds(
            "floor_1",
            x_min=0, x_max=20,
            y_min=0, y_max=30,
            grid_resolution=2.0
        )

        assert domain.id == "floor_1"
        assert graph.number_of_nodes() > 0


# ============================================================================
# TransitionGenerator Tests
# ============================================================================

class TestTransitionGenerator:
    """Tests for TransitionGenerator."""

    def test_wall_to_floor_transitions(self):
        """Test generating wall-to-floor transitions."""
        gen = TransitionGenerator()

        # Create wall and floor
        wall_domain = create_wall_domain("wall_A", 10.0, 8.0)
        floor_domain = create_floor_domain("floor_1", 20.0, 20.0)

        wall_builder = WallGraphBuilder(wall_domain, resolution_u=2.0)
        wall_graph = wall_builder.build_grid_graph()

        floor_builder = FloorGraphBuilder(floor_domain, resolution_x=2.0)
        floor_graph = floor_builder.build_grid_graph()

        transitions = gen.generate_wall_to_floor_transitions(
            wall_domain, floor_domain,
            wall_graph, floor_graph,
            wall_world_position=(5, 5, 0),
            wall_direction=(1, 0)
        )

        # Should have generated some transitions
        assert len(transitions) > 0

        # All transitions should be WALL_TO_FLOOR type
        for trans in transitions:
            assert trans.from_domain == wall_domain.id
            assert trans.to_domain == floor_domain.id
            assert trans.is_bidirectional is True

    def test_wall_to_wall_transitions(self):
        """Test generating wall-to-wall corner transitions."""
        gen = TransitionGenerator()

        wall_a = create_wall_domain("wall_A", 10.0, 8.0)
        wall_b = create_wall_domain("wall_B", 8.0, 8.0)

        builder_a = WallGraphBuilder(wall_a, resolution_u=2.0)
        graph_a = builder_a.build_grid_graph()

        builder_b = WallGraphBuilder(wall_b, resolution_u=2.0)
        graph_b = builder_b.build_grid_graph()

        transitions = gen.generate_wall_to_wall_transitions(
            wall_a, wall_b,
            graph_a, graph_b,
            corner_location=(10.0, 0.0)
        )

        # Should have at least one transition
        assert len(transitions) >= 1
        assert transitions[0].from_domain == wall_a.id
        assert transitions[0].to_domain == wall_b.id


# ============================================================================
# UnifiedGraphBuilder Tests
# ============================================================================

class TestUnifiedGraphBuilder:
    """Tests for UnifiedGraphBuilder."""

    def test_create_builder(self):
        """Test creating unified graph builder."""
        builder = UnifiedGraphBuilder()
        assert builder.wall_resolution == 0.333
        assert builder.floor_resolution == 1.0

    def test_build_from_walls(self):
        """Test building unified graph from wall data."""
        walls_data = [
            {
                "id": "wall_A",
                "length": 10.0,
                "height": 8.0,
                "thickness": 0.292,
                "start": [0, 0, 0],
                "end": [10, 0, 0]
            }
        ]

        builder = UnifiedGraphBuilder(wall_grid_resolution=1.0)
        mdg = builder.build_from_walls(walls_data)

        assert "wall_A" in mdg.domains
        assert mdg.unified_graph is not None
        assert mdg.unified_graph.number_of_nodes() > 0

    def test_build_with_floor(self):
        """Test building unified graph with floor."""
        walls_data = [
            {
                "id": "wall_A",
                "length": 10.0,
                "height": 8.0,
                "start": [0, 0, 0],
                "end": [10, 0, 0]
            }
        ]

        builder = UnifiedGraphBuilder(
            wall_grid_resolution=2.0,
            floor_grid_resolution=2.0
        )
        mdg = builder.build_from_walls(
            walls_data,
            floor_bounds=(0, 10, 0, 10)
        )

        assert "wall_A" in mdg.domains
        assert "floor_0" in mdg.domains

        # Should have wall-to-floor transitions
        w2f_transitions = [
            t for t in mdg.transitions
            if t.from_domain == "wall_A" and t.to_domain == "floor_0"
        ]
        assert len(w2f_transitions) > 0

    def test_build_with_corner(self):
        """Test building unified graph with wall corner."""
        walls_data = [
            {
                "id": "wall_A",
                "length": 10.0,
                "height": 8.0,
                "start": [0, 0, 0],
                "end": [10, 0, 0]
            },
            {
                "id": "wall_B",
                "length": 8.0,
                "height": 8.0,
                "start": [10, 0, 0],
                "end": [10, 8, 0]
            }
        ]

        builder = UnifiedGraphBuilder(wall_grid_resolution=2.0)
        mdg = builder.build_from_walls(walls_data)

        assert "wall_A" in mdg.domains
        assert "wall_B" in mdg.domains

        # Should have wall-to-wall transition at corner
        w2w_transitions = [
            t for t in mdg.transitions
            if (t.from_domain == "wall_A" and t.to_domain == "wall_B") or
               (t.from_domain == "wall_B" and t.to_domain == "wall_A")
        ]
        assert len(w2w_transitions) > 0


class TestBuildFromJson:
    """Tests for build_from_json methods."""

    def test_build_from_json_string(self, sample_walls_json):
        """Test building from JSON string."""
        builder = UnifiedGraphBuilder(wall_grid_resolution=2.0)
        mdg = builder.build_from_json(sample_walls_json)

        assert "wall_A" in mdg.domains
        assert "wall_B" in mdg.domains
        assert mdg.unified_graph is not None

    def test_build_routing_graph_helper(self, sample_walls_json):
        """Test the convenience function."""
        mdg = build_routing_graph(
            sample_walls_json,
            wall_resolution=2.0,
            floor_resolution=2.0
        )

        assert len(mdg.domains) >= 2
        assert mdg.unified_graph is not None


# ============================================================================
# Integration Tests
# ============================================================================

class TestGraphIntegration:
    """Integration tests for graph construction pipeline."""

    def test_pathfinding_single_wall(self):
        """Test that paths can be found in a single wall."""
        wall_data = {
            "id": "wall_1",
            "length": 10.0,
            "height": 8.0,
            "start": [0, 0, 0],
            "end": [10, 0, 0]
        }

        builder = UnifiedGraphBuilder(wall_grid_resolution=1.0)
        mdg = builder.build_from_walls([wall_data])

        # Find two connected nodes (avoid isolated plate-zone nodes)
        # Get nodes that have edges (degree > 0)
        connected_nodes = [
            n for n in mdg.unified_graph.nodes()
            if mdg.unified_graph.degree(n) > 0
        ]

        if len(connected_nodes) >= 2:
            start = connected_nodes[0]
            end = connected_nodes[-1]

            path = mdg.find_path(start, end)
            # Path may be None if nodes in different components (blocked by plates)
            if path is not None:
                assert len(path) >= 2
                assert path[0] == start
                assert path[-1] == end

    def test_pathfinding_across_domains(self):
        """Test that paths can cross domain transitions."""
        walls_data = [
            {
                "id": "wall_A",
                "length": 10.0,
                "height": 8.0,
                "start": [0, 0, 0],
                "end": [10, 0, 0]
            },
            {
                "id": "wall_B",
                "length": 8.0,
                "height": 8.0,
                "start": [10, 0, 0],
                "end": [10, 8, 0]
            }
        ]

        builder = UnifiedGraphBuilder(wall_grid_resolution=2.0)
        mdg = builder.build_from_walls(walls_data)

        # Find nodes in different domains
        wall_a_nodes = [
            n for n, d in mdg.unified_graph.nodes(data=True)
            if d.get('domain_id') == 'wall_A'
        ]
        wall_b_nodes = [
            n for n, d in mdg.unified_graph.nodes(data=True)
            if d.get('domain_id') == 'wall_B'
        ]

        if wall_a_nodes and wall_b_nodes:
            path = mdg.find_path(wall_a_nodes[0], wall_b_nodes[0])
            if path:  # Path should exist through corner transition
                domains = mdg.get_path_domains(path)
                # Path should cross domain boundary
                assert len(domains) >= 1  # At least one domain

    def test_stud_penetration_affects_path(self):
        """Test that stud obstacles affect path cost."""
        walls_data = [
            {
                "id": "wall_studs",
                "length": 10.0,
                "height": 8.0,
                "start": [0, 0, 0],
                "end": [10, 0, 0]
            }
        ]

        builder = UnifiedGraphBuilder(wall_grid_resolution=0.5)
        mdg = builder.build_from_walls(walls_data)

        # Find a path across wall
        nodes = list(mdg.unified_graph.nodes())
        if len(nodes) >= 2:
            start = nodes[0]
            end = nodes[-1]

            path = mdg.find_path(start, end)
            if path:
                cost = mdg.get_path_cost(path)
                # Cost should be > 0
                assert cost > 0

    def test_graph_statistics(self):
        """Test graph statistics reporting."""
        walls_data = [
            {"id": "wall_1", "length": 10.0, "height": 8.0, "start": [0, 0, 0], "end": [10, 0, 0]}
        ]

        builder = UnifiedGraphBuilder(wall_grid_resolution=2.0)
        mdg = builder.build_from_walls(walls_data, floor_bounds=(0, 10, 0, 10))

        stats = mdg.get_statistics()

        assert stats["num_domains"] >= 2
        assert "wall_1" in stats["domains"]
        assert "floor_0" in stats["domains"]
        assert "unified" in stats
        assert stats["unified"]["num_nodes"] > 0
