# File: src/timber_framing_generator/mep/routing/multi_domain_pathfinder.py
"""
Multi-domain pathfinding for MEP routing.

Handles pathfinding across multiple routing domains (walls, floors)
using the unified graph from MultiDomainGraph.
"""

import logging
import math
from typing import List, Tuple, Optional, Dict, Set

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

from .graph import MultiDomainGraph
from .pathfinding import AStarPathfinder, PathReconstructor, PathResult
from .route_segment import Route, RouteSegment

logger = logging.getLogger(__name__)


class MultiDomainPathfinder:
    """
    Pathfinding across multiple routing domains.

    Uses the unified graph from MultiDomainGraph to find paths
    that may cross wall-to-floor or wall-to-wall transitions.

    This class provides high-level pathfinding operations that
    abstract away the graph node details and work directly with
    domain IDs and coordinates.
    """

    def __init__(self, mdg: MultiDomainGraph):
        """
        Initialize multi-domain pathfinder.

        Args:
            mdg: MultiDomainGraph with unified routing graph
        """
        self.mdg = mdg
        self._pathfinder: Optional[AStarPathfinder] = None
        self._reconstructor: Optional[PathReconstructor] = None
        self._setup_pathfinder()

    def _setup_pathfinder(self) -> None:
        """Initialize internal pathfinder with unified graph."""
        if self.mdg.unified_graph is None:
            logger.warning("MultiDomainGraph has no unified graph")
            return

        self._pathfinder = AStarPathfinder(
            self.mdg.unified_graph,
            heuristic=self._multi_domain_heuristic
        )
        self._reconstructor = PathReconstructor(self.mdg.unified_graph)

    def _multi_domain_heuristic(self, node: int, target: int) -> float:
        """
        Multi-domain aware heuristic.

        Accounts for potential domain transitions by using
        Manhattan distance plus a small transition estimate.
        """
        if self.mdg.unified_graph is None:
            return 0.0

        node_data = self.mdg.unified_graph.nodes.get(node, {})
        target_data = self.mdg.unified_graph.nodes.get(target, {})

        node_loc = node_data.get('location') or node_data.get('pos')
        target_loc = target_data.get('location') or target_data.get('pos')

        if node_loc is None or target_loc is None:
            return 0.0

        # Manhattan distance
        base = abs(node_loc[0] - target_loc[0]) + abs(node_loc[1] - target_loc[1])

        # Add small penalty if in different domains (transition likely)
        node_domain = node_data.get('domain_id', '')
        target_domain = target_data.get('domain_id', '')

        if node_domain and target_domain and node_domain != target_domain:
            # Estimate one transition cost
            base += 1.0

        return base

    def find_path(
        self,
        source_domain: str,
        source_location: Tuple[float, float],
        target_domain: str,
        target_location: Tuple[float, float],
        route_id: str = "route",
        system_type: str = "generic"
    ) -> Optional[Route]:
        """
        Find path between points in potentially different domains.

        Args:
            source_domain: ID of source domain
            source_location: (u, v) or (x, y) coordinates in source domain
            target_domain: ID of target domain
            target_location: (u, v) or (x, y) coordinates in target domain
            route_id: Identifier for the resulting route
            system_type: MEP system type

        Returns:
            Route object or None if no path found
        """
        if self._pathfinder is None:
            logger.error("Pathfinder not initialized")
            return None

        # Find nearest nodes
        source_node = self.find_nearest_node(source_domain, source_location)
        target_node = self.find_nearest_node(target_domain, target_location)

        if source_node is None:
            logger.warning(
                f"No node found near {source_location} in domain {source_domain}"
            )
            return None

        if target_node is None:
            logger.warning(
                f"No node found near {target_location} in domain {target_domain}"
            )
            return None

        # Find path
        result = self._pathfinder.find_path_with_result(source_node, target_node)

        if not result.success:
            logger.debug(
                f"No path from ({source_domain}, {source_location}) "
                f"to ({target_domain}, {target_location})"
            )
            return None

        # Reconstruct as Route
        route = self._reconstructor.reconstruct(result.path, route_id, system_type)

        # Override source/target with actual requested locations
        route.source = source_location
        route.target = target_location

        logger.debug(
            f"Found path: {len(result.path)} nodes, cost={result.cost:.2f}, "
            f"domains={result.domains_crossed}"
        )

        return route

    def find_path_between_nodes(
        self,
        source_node: int,
        target_node: int,
        route_id: str = "route",
        system_type: str = "generic"
    ) -> Optional[Route]:
        """
        Find path between specific graph nodes.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            route_id: Route identifier
            system_type: MEP system type

        Returns:
            Route object or None
        """
        if self._pathfinder is None:
            return None

        result = self._pathfinder.find_path_with_result(source_node, target_node)

        if not result.success:
            return None

        return self._reconstructor.reconstruct(result.path, route_id, system_type)

    def find_nearest_node(
        self,
        domain_id: str,
        location: Tuple[float, float]
    ) -> Optional[int]:
        """
        Find graph node nearest to a location in a domain.

        Args:
            domain_id: Domain to search in
            location: (u, v) or (x, y) coordinates

        Returns:
            Node ID or None if no nodes in domain
        """
        if self.mdg.unified_graph is None:
            return None

        best_node = None
        best_dist = float('inf')

        for node, data in self.mdg.unified_graph.nodes(data=True):
            if data.get('domain_id') != domain_id:
                continue

            node_loc = data.get('location') or data.get('pos')
            if node_loc is None:
                continue

            # Manhattan distance
            dist = abs(node_loc[0] - location[0]) + abs(node_loc[1] - location[1])

            if dist < best_dist:
                best_dist = dist
                best_node = node

        return best_node

    def find_all_nodes_near(
        self,
        domain_id: str,
        location: Tuple[float, float],
        radius: float
    ) -> List[int]:
        """
        Find all nodes within radius of a location.

        Args:
            domain_id: Domain to search in
            location: Center coordinates
            radius: Search radius

        Returns:
            List of node IDs within radius
        """
        if self.mdg.unified_graph is None:
            return []

        nearby = []

        for node, data in self.mdg.unified_graph.nodes(data=True):
            if data.get('domain_id') != domain_id:
                continue

            node_loc = data.get('location') or data.get('pos')
            if node_loc is None:
                continue

            dist = math.sqrt(
                (node_loc[0] - location[0])**2 +
                (node_loc[1] - location[1])**2
            )

            if dist <= radius:
                nearby.append(node)

        return nearby

    def get_path_result(
        self,
        source_node: int,
        target_node: int
    ) -> PathResult:
        """
        Get full path result with statistics.

        Args:
            source_node: Source node ID
            target_node: Target node ID

        Returns:
            PathResult with path, cost, and statistics
        """
        if self._pathfinder is None:
            return PathResult(success=False)

        return self._pathfinder.find_path_with_result(source_node, target_node)

    def find_paths_to_targets(
        self,
        source_domain: str,
        source_location: Tuple[float, float],
        targets: List[Tuple[str, Tuple[float, float]]],
        route_id_prefix: str = "route",
        system_type: str = "generic"
    ) -> List[Route]:
        """
        Find paths from source to multiple targets.

        Args:
            source_domain: Source domain ID
            source_location: Source coordinates
            targets: List of (domain_id, location) tuples
            route_id_prefix: Prefix for route IDs
            system_type: MEP system type

        Returns:
            List of Route objects (only successful paths)
        """
        routes = []

        source_node = self.find_nearest_node(source_domain, source_location)
        if source_node is None:
            return routes

        for i, (target_domain, target_location) in enumerate(targets):
            target_node = self.find_nearest_node(target_domain, target_location)
            if target_node is None:
                continue

            route = self.find_path_between_nodes(
                source_node,
                target_node,
                route_id=f"{route_id_prefix}_{i}",
                system_type=system_type
            )

            if route:
                route.source = source_location
                route.target = target_location
                routes.append(route)

        return routes

    def get_domain_statistics(self) -> Dict[str, dict]:
        """
        Get statistics about nodes and edges per domain.

        Returns:
            Dictionary mapping domain IDs to statistics
        """
        if self.mdg.unified_graph is None:
            return {}

        stats: Dict[str, dict] = {}

        for node, data in self.mdg.unified_graph.nodes(data=True):
            domain_id = data.get('domain_id', 'unknown')
            if domain_id not in stats:
                stats[domain_id] = {
                    'num_nodes': 0,
                    'num_terminals': 0,
                    'num_transitions': 0
                }

            stats[domain_id]['num_nodes'] += 1
            if data.get('is_terminal'):
                stats[domain_id]['num_terminals'] += 1
            if data.get('is_transition'):
                stats[domain_id]['num_transitions'] += 1

        return stats
