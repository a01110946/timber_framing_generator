# File: src/timber_framing_generator/mep/routing/pathfinding.py
"""
A* pathfinding for MEP routing.

Implements optimal single-path finding through routing graphs with
obstacle-aware heuristics and support for cross-domain routing.
"""

import heapq
import logging
import math
from dataclasses import dataclass, field
from typing import (
    List, Tuple, Optional, Dict, Set, Callable, Any
)

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

from .route_segment import RouteSegment, SegmentDirection, Route

logger = logging.getLogger(__name__)


@dataclass
class PathResult:
    """
    Result of a pathfinding operation.

    Attributes:
        path: List of node IDs from source to target
        cost: Total path cost
        visited_count: Number of nodes visited during search
        success: Whether a path was found
        domains_crossed: List of domain IDs traversed
    """
    path: List[int] = field(default_factory=list)
    cost: float = 0.0
    visited_count: int = 0
    success: bool = False
    domains_crossed: List[str] = field(default_factory=list)


class AStarPathfinder:
    """
    A* pathfinding for MEP routing.

    Finds optimal paths through routing graphs considering:
    - Edge weights (base cost + penetration penalties)
    - Cross-domain transitions
    - Occupancy conflicts

    The A* algorithm uses f(n) = g(n) + h(n) where:
    - g(n): Actual cost from start to node n
    - h(n): Heuristic estimate from n to goal

    For optimal paths, h(n) must be admissible (never overestimate).
    Manhattan distance is used as the default heuristic.
    """

    def __init__(
        self,
        graph: 'nx.Graph',
        heuristic: Optional[Callable[[int, int], float]] = None
    ):
        """
        Initialize A* pathfinder.

        Args:
            graph: NetworkX graph with weighted edges
            heuristic: Optional custom heuristic function h(node, target) -> float
        """
        if not HAS_NETWORKX:
            raise ImportError("networkx required for AStarPathfinder")

        self.graph = graph
        self._custom_heuristic = heuristic

    def find_path(
        self,
        source: int,
        target: int,
        blocked_nodes: Optional[Set[int]] = None
    ) -> Optional[List[int]]:
        """
        Find optimal path from source to target.

        Args:
            source: Source node ID
            target: Target node ID
            blocked_nodes: Optional set of nodes to avoid

        Returns:
            List of node IDs forming the path, or None if no path exists
        """
        result = self.find_path_with_result(source, target, blocked_nodes)
        return result.path if result.success else None

    def find_path_with_cost(
        self,
        source: int,
        target: int,
        blocked_nodes: Optional[Set[int]] = None
    ) -> Tuple[Optional[List[int]], float]:
        """
        Find path and return total cost.

        Args:
            source: Source node ID
            target: Target node ID
            blocked_nodes: Optional set of nodes to avoid

        Returns:
            Tuple of (path, cost) where path is None if not found
        """
        result = self.find_path_with_result(source, target, blocked_nodes)
        if result.success:
            return result.path, result.cost
        return None, float('inf')

    def find_path_with_result(
        self,
        source: int,
        target: int,
        blocked_nodes: Optional[Set[int]] = None
    ) -> PathResult:
        """
        Find path with full result details.

        Args:
            source: Source node ID
            target: Target node ID
            blocked_nodes: Optional set of nodes to avoid

        Returns:
            PathResult with path, cost, and statistics
        """
        blocked = blocked_nodes or set()

        # Handle trivial case
        if source == target:
            return PathResult(
                path=[source],
                cost=0.0,
                visited_count=1,
                success=True
            )

        # Check if nodes exist
        if source not in self.graph or target not in self.graph:
            logger.warning(f"Source {source} or target {target} not in graph")
            return PathResult(success=False)

        # Priority queue: (f_score, g_score, counter, node, path)
        # Counter ensures stable sorting when f_scores are equal
        counter = 0
        open_set = [(0.0, 0.0, counter, source, [source])]
        g_scores: Dict[int, float] = {source: 0.0}
        visited: Set[int] = set()
        visited_count = 0

        while open_set:
            f, g, _, current, path = heapq.heappop(open_set)

            if current == target:
                # Extract domains from path
                domains = self._extract_domains(path)
                return PathResult(
                    path=path,
                    cost=g,
                    visited_count=visited_count,
                    success=True,
                    domains_crossed=domains
                )

            if current in visited:
                continue

            visited.add(current)
            visited_count += 1

            for neighbor in self.graph.neighbors(current):
                if neighbor in visited or neighbor in blocked:
                    continue

                # Get edge weight
                edge_data = self.graph[current][neighbor]
                edge_cost = edge_data.get('weight', 1.0)

                if edge_cost == float('inf'):
                    continue

                tentative_g = g + edge_cost

                if tentative_g < g_scores.get(neighbor, float('inf')):
                    g_scores[neighbor] = tentative_g
                    h = self._heuristic(neighbor, target)
                    f_score = tentative_g + h
                    counter += 1
                    new_path = path + [neighbor]
                    heapq.heappush(
                        open_set,
                        (f_score, tentative_g, counter, neighbor, new_path)
                    )

        # No path found
        logger.debug(
            f"No path found from {source} to {target} "
            f"(visited {visited_count} nodes)"
        )
        return PathResult(success=False, visited_count=visited_count)

    def _heuristic(self, node: int, target: int) -> float:
        """
        Compute heuristic estimate from node to target.

        Uses Manhattan distance by default, or custom heuristic if provided.
        """
        if self._custom_heuristic:
            return self._custom_heuristic(node, target)

        return self._manhattan_heuristic(node, target)

    def _manhattan_heuristic(self, node: int, target: int) -> float:
        """
        Manhattan distance heuristic.

        Admissible for rectilinear routing graphs.
        """
        node_loc = self._get_location(node)
        target_loc = self._get_location(target)

        if node_loc is None or target_loc is None:
            return 0.0  # Fallback to Dijkstra

        return abs(node_loc[0] - target_loc[0]) + abs(node_loc[1] - target_loc[1])

    def _get_location(self, node: int) -> Optional[Tuple[float, float]]:
        """Get node location from graph data."""
        if node not in self.graph:
            return None

        data = self.graph.nodes[node]
        return data.get('location') or data.get('pos')

    def _extract_domains(self, path: List[int]) -> List[str]:
        """Extract unique domain IDs from path nodes."""
        domains = []
        seen = set()

        for node in path:
            data = self.graph.nodes.get(node, {})
            domain_id = data.get('domain_id', '')
            if domain_id and domain_id not in seen:
                domains.append(domain_id)
                seen.add(domain_id)

        return domains


class PathReconstructor:
    """
    Converts node paths to RouteSegments.

    Handles coordinate extraction, direction assignment, and
    domain transition marking.
    """

    def __init__(self, graph: 'nx.Graph'):
        """
        Initialize reconstructor.

        Args:
            graph: NetworkX graph with node locations
        """
        self.graph = graph

    def reconstruct(
        self,
        node_path: List[int],
        route_id: str,
        system_type: str
    ) -> Route:
        """
        Convert node sequence to Route with segments.

        Args:
            node_path: List of node IDs
            route_id: Unique route identifier
            system_type: MEP system type

        Returns:
            Route object with segments
        """
        if not node_path:
            return Route(id=route_id, system_type=system_type)

        segments = []
        source = self._get_location(node_path[0])
        target = self._get_location(node_path[-1]) if len(node_path) > 1 else source

        for i in range(len(node_path) - 1):
            current = node_path[i]
            next_node = node_path[i + 1]

            segment = self._create_segment(current, next_node)
            if segment:
                segments.append(segment)

        return Route(
            id=route_id,
            system_type=system_type,
            segments=segments,
            source=source,
            target=target
        )

    def _create_segment(
        self,
        from_node: int,
        to_node: int
    ) -> Optional[RouteSegment]:
        """Create a RouteSegment between two nodes."""
        from_loc = self._get_location(from_node)
        to_loc = self._get_location(to_node)

        if from_loc is None or to_loc is None:
            return None

        from_data = self.graph.nodes.get(from_node, {})
        to_data = self.graph.nodes.get(to_node, {})

        # Get edge data
        edge_data = {}
        if self.graph.has_edge(from_node, to_node):
            edge_data = self.graph[from_node][to_node]

        # Determine direction
        dx = abs(to_loc[0] - from_loc[0])
        dy = abs(to_loc[1] - from_loc[1])
        if dx > 1e-6 and dy > 1e-6:
            direction = SegmentDirection.DIAGONAL
        elif dy > dx:
            direction = SegmentDirection.VERTICAL
        else:
            direction = SegmentDirection.HORIZONTAL

        # Determine domain
        domain_id = from_data.get('domain_id', '')
        to_domain = to_data.get('domain_id', '')
        is_transition = (domain_id != to_domain) if to_domain else False

        # Check obstacle crossing
        crosses_obstacle = edge_data.get('crosses_stud', False) or \
                          edge_data.get('crosses_joist', False)
        obstacle_type = None
        if edge_data.get('crosses_stud'):
            obstacle_type = 'stud'
        elif edge_data.get('crosses_joist'):
            obstacle_type = 'joist'

        return RouteSegment(
            start=from_loc,
            end=to_loc,
            direction=direction,
            length=dx + dy,
            cost=edge_data.get('weight', dx + dy),
            domain_id=domain_id,
            is_steiner=not to_data.get('is_terminal', False),
            crosses_obstacle=crosses_obstacle,
            obstacle_type=obstacle_type,
            metadata={'is_transition': is_transition}
        )

    def _get_location(self, node: int) -> Optional[Tuple[float, float]]:
        """Get node location from graph data."""
        if node not in self.graph:
            return None

        data = self.graph.nodes[node]
        return data.get('location') or data.get('pos')

    def extract_transitions(
        self,
        node_path: List[int]
    ) -> List[Tuple[str, str]]:
        """
        Extract domain transitions from path.

        Returns list of (from_domain, to_domain) tuples.
        """
        transitions = []
        prev_domain = None

        for node in node_path:
            data = self.graph.nodes.get(node, {})
            domain = data.get('domain_id', '')

            if prev_domain and domain and domain != prev_domain:
                transitions.append((prev_domain, domain))

            if domain:
                prev_domain = domain

        return transitions


def find_shortest_path(
    graph: 'nx.Graph',
    source: int,
    target: int,
    blocked: Optional[Set[int]] = None
) -> Optional[List[int]]:
    """
    Convenience function to find shortest path.

    Args:
        graph: NetworkX graph
        source: Source node ID
        target: Target node ID
        blocked: Optional blocked nodes

    Returns:
        List of node IDs or None
    """
    pathfinder = AStarPathfinder(graph)
    return pathfinder.find_path(source, target, blocked)


def find_path_as_route(
    graph: 'nx.Graph',
    source: int,
    target: int,
    route_id: str,
    system_type: str
) -> Optional[Route]:
    """
    Find path and return as Route object.

    Args:
        graph: NetworkX graph
        source: Source node ID
        target: Target node ID
        route_id: Route identifier
        system_type: MEP system type

    Returns:
        Route object or None
    """
    pathfinder = AStarPathfinder(graph)
    path = pathfinder.find_path(source, target)

    if path is None:
        return None

    reconstructor = PathReconstructor(graph)
    return reconstructor.reconstruct(path, route_id, system_type)
