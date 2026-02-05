# File: src/timber_framing_generator/mep/routing/graph.py
"""
Multi-domain graph structures for MEP routing.

Provides a unified graph representation spanning multiple routing domains
(walls, floors, shafts) with transition edges between domains.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

from .domains import RoutingDomain, RoutingDomainType, Point2D
from .occupancy import OccupancyMap


class TransitionType(Enum):
    """Types of transitions between routing domains."""
    WALL_TO_FLOOR = "wall_to_floor"
    FLOOR_TO_WALL = "floor_to_wall"
    WALL_TO_WALL = "wall_to_wall"      # Corner transitions
    WALL_TO_SHAFT = "wall_to_shaft"
    FLOOR_TO_SHAFT = "floor_to_shaft"
    FLOOR_TO_CEILING = "floor_to_ceiling"


@dataclass
class TransitionEdge:
    """
    An edge connecting two routing domains.

    Represents physical connection points where routes can transition
    between domains (e.g., wall cavity to floor cavity).

    Attributes:
        id: Unique identifier
        transition_type: Type of transition
        from_domain: Source domain ID
        from_node: Node ID in source domain graph
        from_location: 2D location in source domain
        to_domain: Target domain ID
        to_node: Node ID in target domain graph
        to_location: 2D location in target domain
        cost: Transition cost (for routing optimization)
        is_bidirectional: Whether transition works both ways
        metadata: Additional transition data
    """
    id: str
    transition_type: TransitionType
    from_domain: str
    from_node: int
    from_location: Tuple[float, float]
    to_domain: str
    to_node: int
    to_location: Tuple[float, float]
    cost: float = 1.0
    is_bidirectional: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "transition_type": self.transition_type.value,
            "from_domain": self.from_domain,
            "from_node": self.from_node,
            "from_location": list(self.from_location),
            "to_domain": self.to_domain,
            "to_node": self.to_node,
            "to_location": list(self.to_location),
            "cost": self.cost,
            "is_bidirectional": self.is_bidirectional,
            "metadata": self.metadata.copy()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TransitionEdge":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            transition_type=TransitionType(data["transition_type"]),
            from_domain=data["from_domain"],
            from_node=data["from_node"],
            from_location=tuple(data["from_location"]),
            to_domain=data["to_domain"],
            to_node=data["to_node"],
            to_location=tuple(data["to_location"]),
            cost=data.get("cost", 1.0),
            is_bidirectional=data.get("is_bidirectional", True),
            metadata=data.get("metadata", {})
        )


@dataclass
class GraphNode:
    """
    A node in the routing graph.

    Represents a point where routes can pass through or change direction.

    Attributes:
        id: Unique node ID (unique within domain)
        domain_id: Domain this node belongs to
        location: 2D location in domain coordinates
        is_terminal: Whether this is a source/sink (fixture, target)
        is_transition: Whether this connects to another domain
        connected_transitions: List of transition edge IDs
    """
    id: int
    domain_id: str
    location: Tuple[float, float]
    is_terminal: bool = False
    is_transition: bool = False
    connected_transitions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "domain_id": self.domain_id,
            "location": list(self.location),
            "is_terminal": self.is_terminal,
            "is_transition": self.is_transition,
            "connected_transitions": self.connected_transitions.copy()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            domain_id=data["domain_id"],
            location=tuple(data["location"]),
            is_terminal=data.get("is_terminal", False),
            is_transition=data.get("is_transition", False),
            connected_transitions=data.get("connected_transitions", [])
        )


class MultiDomainGraph:
    """
    A routing graph spanning multiple domains with transitions.

    Manages separate graphs for each domain plus a unified graph
    that includes cross-domain transition edges.

    Example:
        >>> mdg = MultiDomainGraph()
        >>> mdg.add_domain(wall_domain)
        >>> mdg.add_domain(floor_domain)
        >>> mdg.add_transition(wall_to_floor_edge)
        >>> mdg.build_unified_graph()
        >>> path = mdg.find_path(start_node, end_node)
    """

    def __init__(self):
        """Initialize empty multi-domain graph."""
        if not HAS_NETWORKX:
            raise ImportError(
                "networkx is required for MultiDomainGraph. "
                "Install with: pip install networkx"
            )

        self._domains: Dict[str, RoutingDomain] = {}
        self._domain_graphs: Dict[str, nx.Graph] = {}
        self._transitions: List[TransitionEdge] = []
        self._unified_graph: Optional[nx.Graph] = None
        self._node_counter: int = 0
        self._node_domain_map: Dict[int, str] = {}  # unified_node → domain_id

    @property
    def domains(self) -> Dict[str, RoutingDomain]:
        """Get all routing domains."""
        return self._domains

    @property
    def domain_graphs(self) -> Dict[str, nx.Graph]:
        """Get all domain-specific graphs."""
        return self._domain_graphs

    @property
    def transitions(self) -> List[TransitionEdge]:
        """Get all transition edges."""
        return self._transitions

    @property
    def unified_graph(self) -> Optional[nx.Graph]:
        """Get the unified multi-domain graph."""
        return self._unified_graph

    def add_domain(self, domain: RoutingDomain) -> None:
        """
        Add a routing domain to the graph.

        Args:
            domain: The routing domain to add
        """
        self._domains[domain.id] = domain
        self._domain_graphs[domain.id] = nx.Graph()
        # Mark unified graph as stale
        self._unified_graph = None

    def remove_domain(self, domain_id: str) -> bool:
        """
        Remove a domain and its associated graph.

        Returns True if found and removed.
        """
        if domain_id not in self._domains:
            return False

        del self._domains[domain_id]
        del self._domain_graphs[domain_id]

        # Remove transitions involving this domain
        self._transitions = [
            t for t in self._transitions
            if t.from_domain != domain_id and t.to_domain != domain_id
        ]

        self._unified_graph = None
        return True

    def get_domain(self, domain_id: str) -> Optional[RoutingDomain]:
        """Get a domain by ID."""
        return self._domains.get(domain_id)

    def get_domain_graph(self, domain_id: str) -> Optional[nx.Graph]:
        """Get the graph for a specific domain."""
        return self._domain_graphs.get(domain_id)

    def add_node_to_domain(
        self,
        domain_id: str,
        location: Tuple[float, float],
        is_terminal: bool = False,
        is_transition: bool = False,
        **attrs
    ) -> int:
        """
        Add a node to a domain's graph.

        Args:
            domain_id: ID of the domain
            location: 2D location in domain coordinates
            is_terminal: Whether this is a source/sink
            is_transition: Whether this connects to another domain
            **attrs: Additional node attributes

        Returns:
            The node ID
        """
        if domain_id not in self._domain_graphs:
            raise ValueError(f"Domain {domain_id} not found")

        node_id = self._node_counter
        self._node_counter += 1

        graph = self._domain_graphs[domain_id]
        graph.add_node(
            node_id,
            domain_id=domain_id,
            location=location,
            pos=location,  # For visualization
            is_terminal=is_terminal,
            is_transition=is_transition,
            **attrs
        )

        self._unified_graph = None
        return node_id

    def add_edge_to_domain(
        self,
        domain_id: str,
        node1: int,
        node2: int,
        weight: Optional[float] = None,
        **attrs
    ) -> None:
        """
        Add an edge to a domain's graph.

        Args:
            domain_id: ID of the domain
            node1: First node ID
            node2: Second node ID
            weight: Edge weight (default: Manhattan distance)
            **attrs: Additional edge attributes
        """
        if domain_id not in self._domain_graphs:
            raise ValueError(f"Domain {domain_id} not found")

        graph = self._domain_graphs[domain_id]

        if node1 not in graph or node2 not in graph:
            raise ValueError(f"Node {node1} or {node2} not in domain {domain_id}")

        # Calculate weight if not provided
        if weight is None:
            loc1 = graph.nodes[node1]['location']
            loc2 = graph.nodes[node2]['location']
            weight = abs(loc1[0] - loc2[0]) + abs(loc1[1] - loc2[1])

        graph.add_edge(node1, node2, weight=weight, **attrs)
        self._unified_graph = None

    def add_transition(self, transition: TransitionEdge) -> None:
        """
        Add a transition edge between domains.

        Args:
            transition: The transition edge to add
        """
        # Validate domains exist
        if transition.from_domain not in self._domains:
            raise ValueError(f"From domain {transition.from_domain} not found")
        if transition.to_domain not in self._domains:
            raise ValueError(f"To domain {transition.to_domain} not found")

        self._transitions.append(transition)
        self._unified_graph = None

    def remove_transition(self, transition_id: str) -> bool:
        """Remove a transition by ID. Returns True if found."""
        for i, t in enumerate(self._transitions):
            if t.id == transition_id:
                self._transitions.pop(i)
                self._unified_graph = None
                return True
        return False

    def build_unified_graph(self) -> nx.Graph:
        """
        Build the unified graph from all domains and transitions.

        The unified graph includes:
        - All nodes from all domain graphs (with prefixed IDs)
        - All edges from all domain graphs
        - Transition edges between domains

        Returns:
            The unified networkx Graph
        """
        unified = nx.Graph()

        # Track node ID mapping: (domain_id, local_node) → unified_node
        node_mapping: Dict[Tuple[str, int], int] = {}
        unified_node_id = 0

        # Add nodes and edges from each domain
        for domain_id, domain_graph in self._domain_graphs.items():
            for local_node, data in domain_graph.nodes(data=True):
                node_mapping[(domain_id, local_node)] = unified_node_id
                self._node_domain_map[unified_node_id] = domain_id

                unified.add_node(
                    unified_node_id,
                    unified_id=unified_node_id,
                    local_id=local_node,
                    **data
                )
                unified_node_id += 1

            for u, v, data in domain_graph.edges(data=True):
                unified_u = node_mapping[(domain_id, u)]
                unified_v = node_mapping[(domain_id, v)]
                unified.add_edge(unified_u, unified_v, **data)

        # Add transition edges
        for trans in self._transitions:
            from_key = (trans.from_domain, trans.from_node)
            to_key = (trans.to_domain, trans.to_node)

            if from_key not in node_mapping or to_key not in node_mapping:
                continue  # Skip if nodes don't exist

            unified_from = node_mapping[from_key]
            unified_to = node_mapping[to_key]

            unified.add_edge(
                unified_from,
                unified_to,
                weight=trans.cost,
                is_transition=True,
                transition_type=trans.transition_type.value,
                transition_id=trans.id
            )

            # Add reverse edge if bidirectional
            if trans.is_bidirectional:
                unified.add_edge(
                    unified_to,
                    unified_from,
                    weight=trans.cost,
                    is_transition=True,
                    transition_type=trans.transition_type.value,
                    transition_id=trans.id
                )

        self._unified_graph = unified
        return unified

    def find_path(
        self,
        start_node: int,
        end_node: int,
        use_manhattan_heuristic: bool = True
    ) -> Optional[List[int]]:
        """
        Find shortest path between two nodes using A*.

        Args:
            start_node: Start node ID (in unified graph)
            end_node: End node ID (in unified graph)
            use_manhattan_heuristic: Use Manhattan distance as heuristic

        Returns:
            List of node IDs forming the path, or None if no path exists
        """
        if self._unified_graph is None:
            self.build_unified_graph()

        if start_node not in self._unified_graph:
            raise ValueError(f"Start node {start_node} not in graph")
        if end_node not in self._unified_graph:
            raise ValueError(f"End node {end_node} not in graph")

        def heuristic(u, v):
            if not use_manhattan_heuristic:
                return 0

            loc_u = self._unified_graph.nodes[u].get('location', (0, 0))
            loc_v = self._unified_graph.nodes[v].get('location', (0, 0))
            return abs(loc_u[0] - loc_v[0]) + abs(loc_u[1] - loc_v[1])

        try:
            path = nx.astar_path(
                self._unified_graph,
                start_node,
                end_node,
                heuristic=heuristic,
                weight='weight'
            )
            return path
        except nx.NetworkXNoPath:
            return None

    def get_path_cost(self, path: List[int]) -> float:
        """Calculate total cost of a path."""
        if self._unified_graph is None:
            self.build_unified_graph()

        total_cost = 0.0
        for i in range(len(path) - 1):
            edge_data = self._unified_graph.get_edge_data(path[i], path[i + 1])
            if edge_data:
                total_cost += edge_data.get('weight', 0)
        return total_cost

    def get_path_domains(self, path: List[int]) -> List[str]:
        """Get list of domains traversed by a path."""
        if self._unified_graph is None:
            self.build_unified_graph()

        domains = []
        for node in path:
            domain_id = self._unified_graph.nodes[node].get('domain_id')
            if domain_id and (not domains or domains[-1] != domain_id):
                domains.append(domain_id)
        return domains

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics."""
        stats = {
            "num_domains": len(self._domains),
            "num_transitions": len(self._transitions),
            "domains": {}
        }

        for domain_id, graph in self._domain_graphs.items():
            stats["domains"][domain_id] = {
                "num_nodes": graph.number_of_nodes(),
                "num_edges": graph.number_of_edges()
            }

        if self._unified_graph:
            stats["unified"] = {
                "num_nodes": self._unified_graph.number_of_nodes(),
                "num_edges": self._unified_graph.number_of_edges()
            }

        return stats

    def clear(self) -> None:
        """Clear all domains, graphs, and transitions."""
        self._domains.clear()
        self._domain_graphs.clear()
        self._transitions.clear()
        self._unified_graph = None
        self._node_counter = 0
        self._node_domain_map.clear()

    def to_dict(self) -> dict:
        """Serialize to dictionary (domains and transitions only, not graphs)."""
        return {
            "domains": {
                domain_id: domain.to_dict()
                for domain_id, domain in self._domains.items()
            },
            "transitions": [t.to_dict() for t in self._transitions]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MultiDomainGraph":
        """Deserialize from dictionary."""
        mdg = cls()

        for domain_id, domain_data in data.get("domains", {}).items():
            mdg.add_domain(RoutingDomain.from_dict(domain_data))

        for trans_data in data.get("transitions", []):
            mdg.add_transition(TransitionEdge.from_dict(trans_data))

        return mdg
