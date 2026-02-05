# File: src/timber_framing_generator/mep/routing/wall_graph.py
"""
Wall cavity routing graph builder.

Builds 2D grid graphs for routing in wall cavities, with proper
obstacle marking for studs and other framing members.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
import logging

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

if TYPE_CHECKING:
    import networkx as nx

from .domains import RoutingDomain, RoutingDomainType, Obstacle, Point2D
from .occupancy import OccupancyMap

logger = logging.getLogger(__name__)


class WallGraphBuilder:
    """
    Builds routing graphs for wall cavities.

    Creates a 2D grid graph in UV coordinates where:
    - U axis: Along wall length
    - V axis: Vertical (height)

    Nodes are placed at grid intersections, with edges connecting
    adjacent nodes. Edges crossing studs are marked with penetration
    cost penalties.

    Attributes:
        domain: The wall routing domain
        resolution_u: Grid spacing along wall (feet)
        resolution_v: Grid spacing vertical (feet)
        stud_penetration_cost: Cost multiplier for crossing studs
        plate_blocked: Whether to block routing through plates
    """

    # Default grid resolution
    DEFAULT_RESOLUTION_U: float = 0.333  # ~4 inches
    DEFAULT_RESOLUTION_V: float = 0.5    # 6 inches

    # Cost multipliers
    STUD_PENETRATION_COST: float = 5.0
    PLATE_BLOCKED_COST: float = float('inf')

    def __init__(
        self,
        domain: RoutingDomain,
        resolution_u: float = None,
        resolution_v: float = None
    ):
        """
        Initialize wall graph builder.

        Args:
            domain: Wall routing domain with obstacle info
            resolution_u: Grid spacing along wall (default 4")
            resolution_v: Grid spacing vertical (default 6")
        """
        if not HAS_NETWORKX:
            raise ImportError("networkx required for WallGraphBuilder")

        if domain.domain_type != RoutingDomainType.WALL_CAVITY:
            logger.warning(
                f"Domain {domain.id} is not a WALL_CAVITY type, "
                f"got {domain.domain_type}"
            )

        self.domain = domain
        self.resolution_u = resolution_u or self.DEFAULT_RESOLUTION_U
        self.resolution_v = resolution_v or self.DEFAULT_RESOLUTION_V
        self._node_lookup: Dict[Tuple[int, int], int] = {}
        self._node_counter = 0

    def build_grid_graph(
        self,
        occupancy: Optional[OccupancyMap] = None,
        clear_plate_zones: bool = True
    ) -> nx.Graph:
        """
        Build grid graph for wall cavity routing.

        Creates nodes at regular grid intervals and connects them
        with edges. Marks obstacle crossings with cost penalties.

        Args:
            occupancy: Optional occupancy map to check for conflicts
            clear_plate_zones: If True, avoid routing through plate zones

        Returns:
            NetworkX graph with nodes and weighted edges
        """
        graph = nx.Graph()

        # Get domain bounds
        min_u, max_u, min_v, max_v = self.domain.bounds

        # Calculate grid dimensions
        num_u = max(2, int((max_u - min_u) / self.resolution_u) + 1)
        num_v = max(2, int((max_v - min_v) / self.resolution_v) + 1)

        logger.debug(
            f"Building wall graph: {num_u}x{num_v} grid "
            f"({num_u * num_v} nodes max)"
        )

        # Generate grid nodes
        self._node_lookup.clear()
        self._node_counter = 0

        for i in range(num_u):
            for j in range(num_v):
                u = min_u + i * self.resolution_u
                v = min_v + j * self.resolution_v

                # Clamp to domain bounds
                u = min(u, max_u)
                v = min(v, max_v)

                # Check if node is blocked by occupancy
                if occupancy and not self._check_node_available(
                    occupancy, (u, v)
                ):
                    continue

                node_id = self._add_node(graph, i, j, (u, v))

        # Generate edges
        for i in range(num_u):
            for j in range(num_v):
                if (i, j) not in self._node_lookup:
                    continue

                node_id = self._node_lookup[(i, j)]
                node_loc = graph.nodes[node_id]['location']

                # Horizontal edge (right)
                if i + 1 < num_u and (i + 1, j) in self._node_lookup:
                    neighbor_id = self._node_lookup[(i + 1, j)]
                    neighbor_loc = graph.nodes[neighbor_id]['location']
                    self._add_edge(
                        graph, node_id, neighbor_id,
                        node_loc, neighbor_loc,
                        'horizontal', clear_plate_zones
                    )

                # Vertical edge (up)
                if j + 1 < num_v and (i, j + 1) in self._node_lookup:
                    neighbor_id = self._node_lookup[(i, j + 1)]
                    neighbor_loc = graph.nodes[neighbor_id]['location']
                    self._add_edge(
                        graph, node_id, neighbor_id,
                        node_loc, neighbor_loc,
                        'vertical', clear_plate_zones
                    )

        logger.info(
            f"Wall graph built: {graph.number_of_nodes()} nodes, "
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
        Add terminal nodes (fixtures, targets) to graph.

        Terminals are connected to nearby grid nodes.

        Args:
            graph: The graph to add terminals to
            terminals: List of (u, v) positions
            is_source: Whether these are source nodes (fixtures)

        Returns:
            List of added terminal node IDs
        """
        terminal_ids = []

        for u, v in terminals:
            # Add terminal node
            node_id = self._node_counter
            self._node_counter += 1

            graph.add_node(
                node_id,
                domain_id=self.domain.id,
                location=(u, v),
                pos=(u, v),
                is_terminal=True,
                is_source=is_source
            )

            # Connect to nearest grid nodes
            self._connect_to_grid(graph, node_id, (u, v))

            terminal_ids.append(node_id)

        return terminal_ids

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
        direction: str,
        check_plates: bool
    ) -> None:
        """Add an edge with proper cost based on obstacle crossings."""
        # Base cost is Manhattan distance
        base_cost = abs(loc1[0] - loc2[0]) + abs(loc1[1] - loc2[1])

        # Check for obstacle crossings
        crossing_obstacles = self._get_crossing_obstacles(loc1, loc2)

        cost_multiplier = 1.0
        crosses_stud = False
        crosses_plate = False

        for obstacle in crossing_obstacles:
            if obstacle.obstacle_type == 'stud':
                if obstacle.is_penetrable:
                    cost_multiplier = max(cost_multiplier, self.STUD_PENETRATION_COST)
                    crosses_stud = True
                else:
                    cost_multiplier = self.PLATE_BLOCKED_COST
            elif obstacle.obstacle_type == 'plate':
                if check_plates and not obstacle.is_penetrable:
                    cost_multiplier = self.PLATE_BLOCKED_COST
                    crosses_plate = True
            else:
                # Unknown obstacle types (openings, etc.): block if non-penetrable
                if not obstacle.is_penetrable:
                    cost_multiplier = self.PLATE_BLOCKED_COST
                elif obstacle.is_penetrable:
                    cost_multiplier = max(cost_multiplier, self.STUD_PENETRATION_COST)

        if cost_multiplier == float('inf'):
            return  # Don't add blocked edges

        weight = base_cost * cost_multiplier

        graph.add_edge(
            node1, node2,
            weight=weight,
            base_cost=base_cost,
            direction=direction,
            crosses_stud=crosses_stud,
            crosses_plate=crosses_plate
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
        min_u, max_u, min_v, max_v = self.domain.bounds

        # Find the grid cell containing this point
        i = int((location[0] - min_u) / self.resolution_u)
        j = int((location[1] - min_v) / self.resolution_v)

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
        # Check if any existing segment is at this point
        segments = occupancy.get_segments(self.domain.id)
        for seg in segments:
            # Simple point check - is location on the segment?
            if self._point_near_segment(
                location, seg.start, seg.end, seg.diameter / 2 + 0.05
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
        # Vector from start to end
        dx = seg_end[0] - seg_start[0]
        dy = seg_end[1] - seg_start[1]
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-10:
            # Segment is a point
            return (
                (point[0] - seg_start[0])**2 +
                (point[1] - seg_start[1])**2
            ) < threshold**2

        # Project point onto line
        t = max(0, min(1, (
            (point[0] - seg_start[0]) * dx +
            (point[1] - seg_start[1]) * dy
        ) / length_sq))

        proj_x = seg_start[0] + t * dx
        proj_y = seg_start[1] + t * dy

        dist_sq = (point[0] - proj_x)**2 + (point[1] - proj_y)**2
        return dist_sq < threshold**2


def build_wall_graph_from_data(
    wall_data: Dict[str, Any],
    stud_spacing: float = 1.333,
    grid_resolution: float = 0.333
) -> Tuple[RoutingDomain, nx.Graph]:
    """
    Build a wall routing domain and graph from wall data dictionary.

    Convenience function for creating wall graphs from JSON data.

    Args:
        wall_data: Dictionary with wall info (length, height, etc.)
        stud_spacing: Stud spacing in feet (default 16" OC)
        grid_resolution: Graph grid resolution

    Returns:
        Tuple of (RoutingDomain, nx.Graph)
    """
    wall_id = wall_data.get('id') or wall_data.get('wall_id', 'wall_0')
    length = wall_data.get('length', 10.0)
    height = wall_data.get('height', 8.0)
    thickness = wall_data.get('thickness', 0.292)

    # Create domain
    from .domains import create_wall_domain

    domain = create_wall_domain(
        wall_id=wall_id,
        length=length,
        height=height,
        thickness=thickness,
        stud_spacing=stud_spacing
    )

    # Build graph
    builder = WallGraphBuilder(domain, resolution_u=grid_resolution)
    graph = builder.build_grid_graph()

    return domain, graph
