# File: src/timber_framing_generator/mep/routing/floor_graph.py
"""
Floor cavity routing graph builder.

Builds 2D grid graphs for routing in floor cavities, with proper
obstacle marking for joists/trusses.
"""

from typing import Dict, List, Optional, Tuple, Any
import logging

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

from .domains import RoutingDomain, RoutingDomainType, Obstacle, Point2D
from .occupancy import OccupancyMap

logger = logging.getLogger(__name__)


class FloorGraphBuilder:
    """
    Builds routing graphs for floor cavities.

    Creates a 2D grid graph in XY coordinates where:
    - X axis: Along floor width
    - Y axis: Along floor length

    Floor routing considers joist/truss web openings and penetration
    limitations through framing members.

    Attributes:
        domain: The floor routing domain
        resolution_x: Grid spacing in X (feet)
        resolution_y: Grid spacing in Y (feet)
        joist_penetration_cost: Cost multiplier for crossing joists
        max_penetration_ratio: Max diameter/depth ratio for penetration
    """

    # Default grid resolution (coarser than walls)
    DEFAULT_RESOLUTION: float = 1.0  # 12 inches

    # Cost multipliers
    JOIST_PENETRATION_COST: float = 3.0
    SOLID_JOIST_COST: float = 8.0  # Higher for solid joists vs web trusses

    def __init__(
        self,
        domain: RoutingDomain,
        resolution_x: float = None,
        resolution_y: float = None
    ):
        """
        Initialize floor graph builder.

        Args:
            domain: Floor routing domain with joist info
            resolution_x: Grid spacing in X (default 12")
            resolution_y: Grid spacing in Y (default 12")
        """
        if not HAS_NETWORKX:
            raise ImportError("networkx required for FloorGraphBuilder")

        if domain.domain_type != RoutingDomainType.FLOOR_CAVITY:
            logger.warning(
                f"Domain {domain.id} is not a FLOOR_CAVITY type, "
                f"got {domain.domain_type}"
            )

        self.domain = domain
        self.resolution_x = resolution_x or self.DEFAULT_RESOLUTION
        self.resolution_y = resolution_y or self.DEFAULT_RESOLUTION
        self._node_lookup: Dict[Tuple[int, int], int] = {}
        self._node_counter = 0

    def build_grid_graph(
        self,
        occupancy: Optional[OccupancyMap] = None
    ) -> nx.Graph:
        """
        Build grid graph for floor cavity routing.

        Creates nodes at regular grid intervals and connects them
        with edges. Marks joist crossings with cost penalties.

        Args:
            occupancy: Optional occupancy map to check for conflicts

        Returns:
            NetworkX graph with nodes and weighted edges
        """
        graph = nx.Graph()

        # Get domain bounds (min_u, max_u, min_v, max_v for floor is min_x, max_x, min_y, max_y)
        min_x, max_x, min_y, max_y = self.domain.bounds

        # Calculate grid dimensions
        num_x = max(2, int((max_x - min_x) / self.resolution_x) + 1)
        num_y = max(2, int((max_y - min_y) / self.resolution_y) + 1)

        logger.debug(
            f"Building floor graph: {num_x}x{num_y} grid "
            f"({num_x * num_y} nodes max)"
        )

        # Generate grid nodes
        self._node_lookup.clear()
        self._node_counter = 0

        for i in range(num_x):
            for j in range(num_y):
                x = min_x + i * self.resolution_x
                y = min_y + j * self.resolution_y

                # Clamp to domain bounds
                x = min(x, max_x)
                y = min(y, max_y)

                # Check if node is blocked by occupancy
                if occupancy and not self._check_node_available(
                    occupancy, (x, y)
                ):
                    continue

                node_id = self._add_node(graph, i, j, (x, y))

        # Generate edges
        for i in range(num_x):
            for j in range(num_y):
                if (i, j) not in self._node_lookup:
                    continue

                node_id = self._node_lookup[(i, j)]
                node_loc = graph.nodes[node_id]['location']

                # Edge in X direction (right)
                if i + 1 < num_x and (i + 1, j) in self._node_lookup:
                    neighbor_id = self._node_lookup[(i + 1, j)]
                    neighbor_loc = graph.nodes[neighbor_id]['location']
                    self._add_edge(
                        graph, node_id, neighbor_id,
                        node_loc, neighbor_loc, 'x_direction'
                    )

                # Edge in Y direction (up)
                if j + 1 < num_y and (i, j + 1) in self._node_lookup:
                    neighbor_id = self._node_lookup[(i, j + 1)]
                    neighbor_loc = graph.nodes[neighbor_id]['location']
                    self._add_edge(
                        graph, node_id, neighbor_id,
                        node_loc, neighbor_loc, 'y_direction'
                    )

        logger.info(
            f"Floor graph built: {graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges"
        )

        return graph

    def add_terminal_nodes(
        self,
        graph: nx.Graph,
        terminals: List[Tuple[float, float]],
        is_source: bool = False
    ) -> List[int]:
        """
        Add terminal nodes (floor penetrations, equipment) to graph.

        Terminals are connected to nearby grid nodes.

        Args:
            graph: The graph to add terminals to
            terminals: List of (x, y) positions
            is_source: Whether these are source nodes

        Returns:
            List of added terminal node IDs
        """
        terminal_ids = []

        for x, y in terminals:
            # Add terminal node
            node_id = self._node_counter
            self._node_counter += 1

            graph.add_node(
                node_id,
                domain_id=self.domain.id,
                location=(x, y),
                pos=(x, y),
                is_terminal=True,
                is_source=is_source
            )

            # Connect to nearest grid nodes
            self._connect_to_grid(graph, node_id, (x, y))

            terminal_ids.append(node_id)

        return terminal_ids

    def add_web_opening_zones(
        self,
        graph: nx.Graph,
        web_openings: List[Dict[str, Any]]
    ) -> None:
        """
        Mark zones where joist web openings allow easier penetration.

        For engineered joists (I-joists, trusses), web openings provide
        preferred routing paths.

        Args:
            graph: The graph to modify
            web_openings: List of opening zones with bounds
        """
        for opening in web_openings:
            x_min = opening.get('x_min', 0)
            x_max = opening.get('x_max', 0)
            y_min = opening.get('y_min', 0)
            y_max = opening.get('y_max', 0)

            # Find edges within this zone and reduce cost
            for u, v, data in list(graph.edges(data=True)):
                loc_u = graph.nodes[u]['location']
                loc_v = graph.nodes[v]['location']
                mid_x = (loc_u[0] + loc_v[0]) / 2
                mid_y = (loc_u[1] + loc_v[1]) / 2

                if x_min <= mid_x <= x_max and y_min <= mid_y <= y_max:
                    # This edge is in web opening zone - reduce cost
                    if data.get('crosses_joist'):
                        graph[u][v]['weight'] = data['base_cost'] * 1.5
                        graph[u][v]['in_web_opening'] = True

    def _add_node(
        self,
        graph: nx.Graph,
        i: int,
        j: int,
        location: Tuple[float, float]
    ) -> int:
        """Add a grid node to the graph."""
        node_id = self._node_counter
        self._node_counter += 1

        graph.add_node(
            node_id,
            domain_id=self.domain.id,
            grid_index=(i, j),
            location=location,
            pos=location,
            is_terminal=False,
            is_transition=False
        )

        self._node_lookup[(i, j)] = node_id
        return node_id

    def _add_edge(
        self,
        graph: nx.Graph,
        node1: int,
        node2: int,
        loc1: Tuple[float, float],
        loc2: Tuple[float, float],
        direction: str
    ) -> None:
        """Add an edge with proper cost based on joist crossings."""
        # Base cost is Manhattan distance
        base_cost = abs(loc1[0] - loc2[0]) + abs(loc1[1] - loc2[1])

        # Check for joist crossings
        crossing_obstacles = self._get_crossing_obstacles(loc1, loc2)

        cost_multiplier = 1.0
        crosses_joist = False

        for obstacle in crossing_obstacles:
            if obstacle.obstacle_type == 'joist':
                if obstacle.is_penetrable:
                    # Assume penetrable joists have web openings (lower cost)
                    # Non-penetrable or solid joists have higher cost
                    if obstacle.max_penetration_ratio > 0.5:
                        # Higher penetration ratio = web truss (easier)
                        cost_multiplier = max(
                            cost_multiplier, self.JOIST_PENETRATION_COST
                        )
                    else:
                        # Lower penetration ratio = solid joist (harder)
                        cost_multiplier = max(
                            cost_multiplier, self.SOLID_JOIST_COST
                        )
                    crosses_joist = True
                else:
                    cost_multiplier = float('inf')

        if cost_multiplier == float('inf'):
            return  # Don't add blocked edges

        weight = base_cost * cost_multiplier

        graph.add_edge(
            node1, node2,
            weight=weight,
            base_cost=base_cost,
            direction=direction,
            crosses_joist=crosses_joist
        )

    def _get_crossing_obstacles(
        self,
        loc1: Tuple[float, float],
        loc2: Tuple[float, float]
    ) -> List[Obstacle]:
        """Get obstacles that this edge crosses."""
        crossings = []
        pt1 = Point2D(loc1[0], loc1[1])
        pt2 = Point2D(loc2[0], loc2[1])

        for obstacle in self.domain.obstacles:
            if obstacle.intersects_segment(pt1, pt2):
                crossings.append(obstacle)

        return crossings

    def _connect_to_grid(
        self,
        graph: nx.Graph,
        terminal_id: int,
        location: Tuple[float, float]
    ) -> None:
        """Connect a terminal node to nearby grid nodes."""
        min_x, max_x, min_y, max_y = self.domain.bounds

        # Find the grid cell containing this point
        i = int((location[0] - min_x) / self.resolution_x)
        j = int((location[1] - min_y) / self.resolution_y)

        # Connect to surrounding grid nodes (up to 4)
        for di in range(2):
            for dj in range(2):
                grid_idx = (i + di, j + dj)
                if grid_idx in self._node_lookup:
                    grid_node = self._node_lookup[grid_idx]
                    grid_loc = graph.nodes[grid_node]['location']

                    # Calculate cost
                    distance = (
                        abs(location[0] - grid_loc[0]) +
                        abs(location[1] - grid_loc[1])
                    )

                    graph.add_edge(
                        terminal_id, grid_node,
                        weight=distance,
                        base_cost=distance,
                        direction='terminal_connection'
                    )

    def _check_node_available(
        self,
        occupancy: OccupancyMap,
        location: Tuple[float, float]
    ) -> bool:
        """Check if a node location is available (not occupied)."""
        segments = occupancy.get_segments(self.domain.id)
        for seg in segments:
            if self._point_near_segment(
                location, seg.start, seg.end, seg.diameter / 2 + 0.1
            ):
                return False
        return True

    def _point_near_segment(
        self,
        point: Tuple[float, float],
        seg_start: Tuple[float, float],
        seg_end: Tuple[float, float],
        threshold: float
    ) -> bool:
        """Check if point is within threshold of a segment."""
        dx = seg_end[0] - seg_start[0]
        dy = seg_end[1] - seg_start[1]
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-10:
            return (
                (point[0] - seg_start[0])**2 +
                (point[1] - seg_start[1])**2
            ) < threshold**2

        t = max(0, min(1, (
            (point[0] - seg_start[0]) * dx +
            (point[1] - seg_start[1]) * dy
        ) / length_sq))

        proj_x = seg_start[0] + t * dx
        proj_y = seg_start[1] + t * dy

        dist_sq = (point[0] - proj_x)**2 + (point[1] - proj_y)**2
        return dist_sq < threshold**2


def build_floor_graph_from_bounds(
    floor_id: str,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    joist_spacing: float = 1.333,
    grid_resolution: float = 1.0,
    joist_direction: str = 'x'
) -> Tuple[RoutingDomain, nx.Graph]:
    """
    Build a floor routing domain and graph from bounds.

    Convenience function for creating floor graphs.

    Args:
        floor_id: Unique identifier for this floor
        x_min, x_max: X bounds
        y_min, y_max: Y bounds
        joist_spacing: Joist spacing in feet (default 16" OC)
        grid_resolution: Graph grid resolution
        joist_direction: 'x' or 'y' for joist span direction

    Returns:
        Tuple of (RoutingDomain, nx.Graph)
    """
    # Create domain directly with correct bounds
    domain = RoutingDomain(
        id=floor_id,
        domain_type=RoutingDomainType.FLOOR_CAVITY,
        bounds=(x_min, x_max, y_min, y_max),
        thickness=0.833  # Default 10" floor depth
    )

    # Add joist obstacles
    width = x_max - x_min
    num_joists = int(width / joist_spacing) + 1
    joist_width = 0.146  # 1.75" standard joist width

    for i in range(num_joists):
        joist_x = x_min + i * joist_spacing
        if joist_x > x_max:
            break

        joist = Obstacle(
            id=f"joist_{floor_id}_{i}",
            obstacle_type="joist",
            bounds=(
                joist_x,
                y_min,
                joist_x + joist_width,
                y_max
            ),
            is_penetrable=True,
            max_penetration_ratio=0.6  # Web trusses allow larger openings
        )
        domain.add_obstacle(joist)

    # Build graph
    builder = FloorGraphBuilder(domain, resolution_x=grid_resolution)
    graph = builder.build_grid_graph()

    return domain, graph
