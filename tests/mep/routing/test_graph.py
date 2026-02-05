# File: tests/mep/routing/test_graph.py
"""Tests for multi-domain graph structures."""

import pytest

# Check if networkx is available
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

from src.timber_framing_generator.mep.routing.domains import (
    RoutingDomain,
    RoutingDomainType
)
from src.timber_framing_generator.mep.routing.graph import (
    TransitionType,
    TransitionEdge,
    GraphNode,
    MultiDomainGraph
)


@pytest.mark.skipif(not HAS_NETWORKX, reason="networkx not installed")
class TestTransitionEdge:
    """Tests for TransitionEdge dataclass."""

    def test_create_transition(self):
        """Test creating a transition edge."""
        trans = TransitionEdge(
            id="trans_1",
            transition_type=TransitionType.WALL_TO_FLOOR,
            from_domain="wall_A",
            from_node=5,
            from_location=(3.0, 0.0),
            to_domain="floor_1",
            to_node=10,
            to_location=(3.0, 2.0),
            cost=1.5,
            is_bidirectional=True
        )

        assert trans.id == "trans_1"
        assert trans.transition_type == TransitionType.WALL_TO_FLOOR
        assert trans.from_domain == "wall_A"
        assert trans.to_domain == "floor_1"
        assert trans.cost == 1.5
        assert trans.is_bidirectional is True

    def test_serialization(self):
        """Test to_dict and from_dict."""
        trans = TransitionEdge(
            id="trans_1",
            transition_type=TransitionType.WALL_TO_WALL,
            from_domain="wall_A",
            from_node=5,
            from_location=(10.0, 4.0),
            to_domain="wall_B",
            to_node=0,
            to_location=(0.0, 4.0),
            cost=2.0
        )

        data = trans.to_dict()
        restored = TransitionEdge.from_dict(data)

        assert restored.id == trans.id
        assert restored.transition_type == trans.transition_type
        assert restored.from_domain == trans.from_domain
        assert restored.to_domain == trans.to_domain
        assert restored.cost == trans.cost


@pytest.mark.skipif(not HAS_NETWORKX, reason="networkx not installed")
class TestGraphNode:
    """Tests for GraphNode dataclass."""

    def test_create_node(self):
        """Test creating a graph node."""
        node = GraphNode(
            id=5,
            domain_id="wall_A",
            location=(3.5, 4.0),
            is_terminal=True
        )

        assert node.id == 5
        assert node.domain_id == "wall_A"
        assert node.location == (3.5, 4.0)
        assert node.is_terminal is True
        assert node.is_transition is False

    def test_serialization(self):
        """Test to_dict and from_dict."""
        node = GraphNode(
            id=5,
            domain_id="wall_A",
            location=(3.5, 4.0),
            is_terminal=True,
            is_transition=False,
            connected_transitions=["trans_1"]
        )

        data = node.to_dict()
        restored = GraphNode.from_dict(data)

        assert restored.id == node.id
        assert restored.domain_id == node.domain_id
        assert restored.location == node.location
        assert restored.connected_transitions == node.connected_transitions


@pytest.mark.skipif(not HAS_NETWORKX, reason="networkx not installed")
class TestMultiDomainGraph:
    """Tests for MultiDomainGraph class."""

    def test_create_empty_graph(self):
        """Test creating an empty multi-domain graph."""
        mdg = MultiDomainGraph()

        assert len(mdg.domains) == 0
        assert len(mdg.domain_graphs) == 0
        assert len(mdg.transitions) == 0

    def test_add_domain(self):
        """Test adding a domain."""
        mdg = MultiDomainGraph()

        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        )

        mdg.add_domain(domain)

        assert "wall_A" in mdg.domains
        assert "wall_A" in mdg.domain_graphs
        assert mdg.get_domain("wall_A") == domain

    def test_remove_domain(self):
        """Test removing a domain."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        removed = mdg.remove_domain("wall_A")
        assert removed is True
        assert "wall_A" not in mdg.domains

        removed_again = mdg.remove_domain("wall_A")
        assert removed_again is False

    def test_add_node_to_domain(self):
        """Test adding nodes to a domain's graph."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        node_id = mdg.add_node_to_domain(
            "wall_A",
            location=(5.0, 4.0),
            is_terminal=True
        )

        graph = mdg.get_domain_graph("wall_A")
        assert node_id in graph.nodes
        assert graph.nodes[node_id]['location'] == (5.0, 4.0)
        assert graph.nodes[node_id]['is_terminal'] is True

    def test_add_node_to_nonexistent_domain(self):
        """Test that adding to nonexistent domain raises error."""
        mdg = MultiDomainGraph()

        with pytest.raises(ValueError):
            mdg.add_node_to_domain("nonexistent", location=(0, 0))

    def test_add_edge_to_domain(self):
        """Test adding edges to a domain's graph."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_A", location=(3, 4))

        mdg.add_edge_to_domain("wall_A", n1, n2)

        graph = mdg.get_domain_graph("wall_A")
        assert graph.has_edge(n1, n2)

        # Check weight is Manhattan distance
        weight = graph.edges[n1, n2]['weight']
        assert weight == pytest.approx(7.0)  # |3-0| + |4-0| = 7

    def test_add_edge_custom_weight(self):
        """Test adding edge with custom weight."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_A", location=(3, 4))

        mdg.add_edge_to_domain("wall_A", n1, n2, weight=10.0)

        graph = mdg.get_domain_graph("wall_A")
        assert graph.edges[n1, n2]['weight'] == 10.0

    def test_add_transition(self):
        """Test adding a transition between domains."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_domain(RoutingDomain(
            id="floor_1",
            domain_type=RoutingDomainType.FLOOR_CAVITY,
            bounds=(0, 20, 0, 30)
        ))

        trans = TransitionEdge(
            id="trans_1",
            transition_type=TransitionType.WALL_TO_FLOOR,
            from_domain="wall_A",
            from_node=0,
            from_location=(5.0, 0.0),
            to_domain="floor_1",
            to_node=0,
            to_location=(5.0, 0.0)
        )

        mdg.add_transition(trans)
        assert len(mdg.transitions) == 1

    def test_add_transition_invalid_domain(self):
        """Test that adding transition to invalid domain raises error."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        trans = TransitionEdge(
            id="trans_1",
            transition_type=TransitionType.WALL_TO_FLOOR,
            from_domain="wall_A",
            from_node=0,
            from_location=(5.0, 0.0),
            to_domain="nonexistent",  # Invalid
            to_node=0,
            to_location=(5.0, 0.0)
        )

        with pytest.raises(ValueError):
            mdg.add_transition(trans)

    def test_build_unified_graph(self):
        """Test building unified graph from domains."""
        mdg = MultiDomainGraph()

        # Add two domains
        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_domain(RoutingDomain(
            id="wall_B",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        # Add nodes to each
        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_A", location=(10, 0))
        n3 = mdg.add_node_to_domain("wall_B", location=(0, 0))
        n4 = mdg.add_node_to_domain("wall_B", location=(10, 0))

        # Add edges within domains
        mdg.add_edge_to_domain("wall_A", n1, n2)
        mdg.add_edge_to_domain("wall_B", n3, n4)

        # Add transition
        mdg.add_transition(TransitionEdge(
            id="corner",
            transition_type=TransitionType.WALL_TO_WALL,
            from_domain="wall_A",
            from_node=n2,
            from_location=(10, 0),
            to_domain="wall_B",
            to_node=n3,
            to_location=(0, 0),
            cost=0.5
        ))

        # Build unified graph
        unified = mdg.build_unified_graph()

        assert unified.number_of_nodes() == 4
        assert unified.number_of_edges() == 3  # 2 domain edges + 1 transition

    def test_find_path(self):
        """Test finding path across domains."""
        mdg = MultiDomainGraph()

        # Create simple two-domain setup
        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_domain(RoutingDomain(
            id="wall_B",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        # Linear path: n1 -- n2 (wall_A) === n3 -- n4 (wall_B)
        n1 = mdg.add_node_to_domain("wall_A", location=(0, 4))
        n2 = mdg.add_node_to_domain("wall_A", location=(10, 4))
        n3 = mdg.add_node_to_domain("wall_B", location=(0, 4))
        n4 = mdg.add_node_to_domain("wall_B", location=(10, 4))

        mdg.add_edge_to_domain("wall_A", n1, n2)
        mdg.add_edge_to_domain("wall_B", n3, n4)

        mdg.add_transition(TransitionEdge(
            id="corner",
            transition_type=TransitionType.WALL_TO_WALL,
            from_domain="wall_A",
            from_node=n2,
            from_location=(10, 4),
            to_domain="wall_B",
            to_node=n3,
            to_location=(0, 4),
            cost=1.0
        ))

        mdg.build_unified_graph()

        # Find path from n1 to n4
        path = mdg.find_path(n1, n4)

        assert path is not None
        assert path[0] == n1
        assert path[-1] == n4
        assert len(path) == 4  # n1 -> n2 -> n3 -> n4

    def test_find_path_no_path(self):
        """Test finding path when no path exists."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_domain(RoutingDomain(
            id="wall_B",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_B", location=(0, 0))

        # No transition between domains
        mdg.build_unified_graph()

        path = mdg.find_path(n1, n2)
        assert path is None

    def test_get_path_cost(self):
        """Test calculating path cost."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_A", location=(5, 0))
        n3 = mdg.add_node_to_domain("wall_A", location=(5, 3))

        mdg.add_edge_to_domain("wall_A", n1, n2)  # Cost: 5
        mdg.add_edge_to_domain("wall_A", n2, n3)  # Cost: 3

        mdg.build_unified_graph()

        path = [n1, n2, n3]
        cost = mdg.get_path_cost(path)

        assert cost == pytest.approx(8.0)

    def test_get_path_domains(self):
        """Test getting domains traversed by a path."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_domain(RoutingDomain(
            id="wall_B",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_A", location=(10, 0))
        n3 = mdg.add_node_to_domain("wall_B", location=(0, 0))

        mdg.add_edge_to_domain("wall_A", n1, n2)

        mdg.add_transition(TransitionEdge(
            id="t1",
            transition_type=TransitionType.WALL_TO_WALL,
            from_domain="wall_A",
            from_node=n2,
            from_location=(10, 0),
            to_domain="wall_B",
            to_node=n3,
            to_location=(0, 0)
        ))

        mdg.build_unified_graph()

        path = [n1, n2, n3]
        domains = mdg.get_path_domains(path)

        assert domains == ["wall_A", "wall_B"]

    def test_get_statistics(self):
        """Test getting graph statistics."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))

        n1 = mdg.add_node_to_domain("wall_A", location=(0, 0))
        n2 = mdg.add_node_to_domain("wall_A", location=(10, 0))
        mdg.add_edge_to_domain("wall_A", n1, n2)

        mdg.build_unified_graph()

        stats = mdg.get_statistics()

        assert stats["num_domains"] == 1
        assert stats["domains"]["wall_A"]["num_nodes"] == 2
        assert stats["domains"]["wall_A"]["num_edges"] == 1
        assert stats["unified"]["num_nodes"] == 2

    def test_clear(self):
        """Test clearing the graph."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_node_to_domain("wall_A", location=(0, 0))

        mdg.clear()

        assert len(mdg.domains) == 0
        assert len(mdg.domain_graphs) == 0
        assert mdg.unified_graph is None

    def test_serialization(self):
        """Test to_dict and from_dict."""
        mdg = MultiDomainGraph()

        mdg.add_domain(RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        ))
        mdg.add_domain(RoutingDomain(
            id="floor_1",
            domain_type=RoutingDomainType.FLOOR_CAVITY,
            bounds=(0, 20, 0, 30)
        ))

        mdg.add_transition(TransitionEdge(
            id="t1",
            transition_type=TransitionType.WALL_TO_FLOOR,
            from_domain="wall_A",
            from_node=0,
            from_location=(5, 0),
            to_domain="floor_1",
            to_node=0,
            to_location=(5, 0)
        ))

        data = mdg.to_dict()
        restored = MultiDomainGraph.from_dict(data)

        assert "wall_A" in restored.domains
        assert "floor_1" in restored.domains
        assert len(restored.transitions) == 1
