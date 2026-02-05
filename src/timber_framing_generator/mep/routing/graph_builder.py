# File: src/timber_framing_generator/mep/routing/graph_builder.py
"""
Unified graph builder for MEP routing.

Assembles multi-domain routing graphs from wall and floor data,
including transition edges between domains.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
import json
import logging
import math

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

if TYPE_CHECKING:
    import networkx as nx

from .domains import RoutingDomain, RoutingDomainType, Point2D
from .graph import MultiDomainGraph, TransitionEdge, TransitionType
from .wall_graph import WallGraphBuilder, build_wall_graph_from_data
from .floor_graph import FloorGraphBuilder, build_floor_graph_from_bounds
from .occupancy import OccupancyMap
from .targets import RoutingTarget

logger = logging.getLogger(__name__)


class TransitionGenerator:
    """
    Generates transition edges between routing domains.

    Handles:
    - Wall-to-floor transitions at base plates
    - Wall-to-wall transitions at corners
    - Wall-to-shaft transitions (future)
    """

    # Default transition costs
    WALL_TO_FLOOR_COST: float = 2.0
    WALL_TO_WALL_COST: float = 1.5
    FLOOR_TO_CEILING_COST: float = 2.5

    def __init__(self):
        self._transition_counter = 0

    def generate_wall_to_floor_transitions(
        self,
        wall_domain: RoutingDomain,
        floor_domain: RoutingDomain,
        wall_graph: nx.Graph,
        floor_graph: nx.Graph,
        wall_world_position: Tuple[float, float, float] = (0, 0, 0),
        wall_direction: Tuple[float, float] = (1, 0)
    ) -> List[TransitionEdge]:
        """
        Generate transitions at wall base to floor cavity.

        Creates transition points at intervals along the wall base
        that connect to the floor graph below.

        Args:
            wall_domain: The wall routing domain
            floor_domain: The floor routing domain
            wall_graph: NetworkX graph for wall
            floor_graph: NetworkX graph for floor
            wall_world_position: Wall origin in world XY
            wall_direction: Wall direction vector in world XY

        Returns:
            List of TransitionEdge objects
        """
        transitions = []

        # Get wall bounds (U along wall, V vertical)
        wall_min_u, wall_max_u, wall_min_v, wall_max_v = wall_domain.bounds

        # Find nodes at bottom of wall (V near min_v)
        bottom_tolerance = 0.5  # Within 6" of bottom
        wall_bottom_nodes = [
            (node, data) for node, data in wall_graph.nodes(data=True)
            if abs(data['location'][1] - wall_min_v) < bottom_tolerance
        ]

        # For each bottom node, find corresponding floor node
        for wall_node, wall_data in wall_bottom_nodes:
            wall_u = wall_data['location'][0]

            # Convert wall U to world XY
            world_x = wall_world_position[0] + wall_u * wall_direction[0]
            world_y = wall_world_position[1] + wall_u * wall_direction[1]

            # Find closest floor node
            closest_floor_node = None
            closest_distance = float('inf')

            for floor_node, floor_data in floor_graph.nodes(data=True):
                floor_x, floor_y = floor_data['location']
                dist = abs(world_x - floor_x) + abs(world_y - floor_y)
                if dist < closest_distance:
                    closest_distance = dist
                    closest_floor_node = floor_node

            if closest_floor_node is not None and closest_distance < 2.0:
                floor_loc = floor_graph.nodes[closest_floor_node]['location']

                transition = TransitionEdge(
                    id=f"trans_w2f_{self._transition_counter}",
                    transition_type=TransitionType.WALL_TO_FLOOR,
                    from_domain=wall_domain.id,
                    from_node=wall_node,
                    from_location=wall_data['location'],
                    to_domain=floor_domain.id,
                    to_node=closest_floor_node,
                    to_location=floor_loc,
                    cost=self.WALL_TO_FLOOR_COST,
                    is_bidirectional=True,
                    metadata={
                        "wall_u": wall_u,
                        "world_xy": (world_x, world_y)
                    }
                )
                transitions.append(transition)
                self._transition_counter += 1

        logger.debug(
            f"Generated {len(transitions)} wall-to-floor transitions "
            f"between {wall_domain.id} and {floor_domain.id}"
        )

        return transitions

    def generate_wall_to_wall_transitions(
        self,
        wall_a: RoutingDomain,
        wall_b: RoutingDomain,
        graph_a: nx.Graph,
        graph_b: nx.Graph,
        corner_location: Tuple[float, float]
    ) -> List[TransitionEdge]:
        """
        Generate transitions at wall corners.

        Creates transition at the corner point where two walls meet.

        Args:
            wall_a: First wall domain
            wall_b: Second wall domain
            graph_a: Graph for wall_a
            graph_b: Graph for wall_b
            corner_location: World XY position of corner

        Returns:
            List of TransitionEdge objects
        """
        transitions = []

        # Find nodes nearest to corner in each graph
        # For wall_a, corner is at U=max (end of wall)
        # For wall_b, corner is at U=0 (start of wall)

        # Get end node from wall_a (highest U)
        node_a = None
        max_u = -float('inf')
        for node, data in graph_a.nodes(data=True):
            if data['location'][0] > max_u:
                max_u = data['location'][0]
                node_a = node

        # Get start node from wall_b (lowest U)
        node_b = None
        min_u = float('inf')
        for node, data in graph_b.nodes(data=True):
            if data['location'][0] < min_u:
                min_u = data['location'][0]
                node_b = node

        if node_a is not None and node_b is not None:
            loc_a = graph_a.nodes[node_a]['location']
            loc_b = graph_b.nodes[node_b]['location']

            transition = TransitionEdge(
                id=f"trans_w2w_{self._transition_counter}",
                transition_type=TransitionType.WALL_TO_WALL,
                from_domain=wall_a.id,
                from_node=node_a,
                from_location=loc_a,
                to_domain=wall_b.id,
                to_node=node_b,
                to_location=loc_b,
                cost=self.WALL_TO_WALL_COST,
                is_bidirectional=True,
                metadata={"corner_xy": corner_location}
            )
            transitions.append(transition)
            self._transition_counter += 1

        return transitions


class UnifiedGraphBuilder:
    """
    Builds complete multi-domain routing graphs from wall and floor data.

    Integrates with WallData JSON format from the framing pipeline.
    """

    def __init__(
        self,
        wall_grid_resolution: float = 0.333,
        floor_grid_resolution: float = 1.0
    ):
        """
        Initialize unified graph builder.

        Args:
            wall_grid_resolution: Grid resolution for wall graphs
            floor_grid_resolution: Grid resolution for floor graphs
        """
        if not HAS_NETWORKX:
            raise ImportError("networkx required for UnifiedGraphBuilder")

        self.wall_resolution = wall_grid_resolution
        self.floor_resolution = floor_grid_resolution
        self._transition_gen = TransitionGenerator()

    def build_from_walls(
        self,
        walls_data: List[Dict[str, Any]],
        floor_bounds: Optional[Tuple[float, float, float, float]] = None,
        connectors: Optional[List[Dict]] = None,
        targets: Optional[List[Dict]] = None,
        occupancy: Optional[OccupancyMap] = None
    ) -> MultiDomainGraph:
        """
        Build complete routing graph from wall data.

        Args:
            walls_data: List of wall dictionaries
            floor_bounds: Optional (x_min, x_max, y_min, y_max) for floor
            connectors: Optional connector positions to add as terminals
            targets: Optional target positions to add as terminals
            occupancy: Optional occupancy map for conflict checking

        Returns:
            MultiDomainGraph with all domains and transitions
        """
        mdg = MultiDomainGraph()

        # Build wall graphs
        wall_graphs = {}
        wall_positions = {}  # Store world positions for transitions

        for wall_data in walls_data:
            wall_id = wall_data.get('id') or wall_data.get('wall_id')
            if not wall_id:
                continue

            domain, graph = build_wall_graph_from_data(
                wall_data,
                grid_resolution=self.wall_resolution
            )

            mdg.add_domain(domain)
            wall_graphs[wall_id] = (domain, graph)

            # Extract world position if available
            if 'start' in wall_data:
                wall_positions[wall_id] = {
                    'start': tuple(wall_data['start'][:2]),
                    'end': tuple(wall_data.get('end', wall_data['start'])[:2])
                }

            # Add nodes and edges to multi-domain graph
            self._add_domain_graph_to_mdg(mdg, domain.id, graph)

        # Build floor graph if bounds provided
        floor_domain = None
        floor_graph = None

        if floor_bounds:
            x_min, x_max, y_min, y_max = floor_bounds
            floor_domain, floor_graph = build_floor_graph_from_bounds(
                "floor_0",
                x_min, x_max, y_min, y_max,
                grid_resolution=self.floor_resolution
            )

            mdg.add_domain(floor_domain)
            self._add_domain_graph_to_mdg(mdg, floor_domain.id, floor_graph)

            # Generate wall-to-floor transitions
            for wall_id, (wall_domain, wall_graph) in wall_graphs.items():
                pos = wall_positions.get(wall_id, {})
                start = pos.get('start', (0, 0))
                end = pos.get('end', (1, 0))

                # Calculate direction
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    direction = (dx/length, dy/length)
                else:
                    direction = (1, 0)

                transitions = self._transition_gen.generate_wall_to_floor_transitions(
                    wall_domain, floor_domain,
                    wall_graph, floor_graph,
                    wall_world_position=(start[0], start[1], 0),
                    wall_direction=direction
                )

                for trans in transitions:
                    mdg.add_transition(trans)

        # Generate wall-to-wall transitions at corners
        self._generate_wall_corner_transitions(
            mdg, walls_data, wall_graphs, wall_positions
        )

        # Add terminal nodes for connectors
        if connectors:
            self._add_connector_terminals(mdg, connectors, wall_graphs)

        # Add terminal nodes for targets
        if targets:
            self._add_target_terminals(mdg, targets, wall_graphs)

        # Build unified graph
        mdg.build_unified_graph()

        logger.info(
            f"Built unified graph with {len(mdg.domains)} domains, "
            f"{len(mdg.transitions)} transitions"
        )

        return mdg

    def build_from_json(
        self,
        walls_json: str,
        cells_json: Optional[str] = None,
        connectors_json: Optional[str] = None,
        targets_json: Optional[str] = None
    ) -> MultiDomainGraph:
        """
        Build graph from JSON input strings.

        Args:
            walls_json: JSON string with wall data
            cells_json: Optional JSON with cell decomposition
            connectors_json: Optional JSON with connectors
            targets_json: Optional JSON with targets

        Returns:
            MultiDomainGraph
        """
        # Parse walls
        walls_data = json.loads(walls_json)
        if isinstance(walls_data, dict) and 'walls' in walls_data:
            walls_data = walls_data['walls']

        # Determine floor bounds from walls
        floor_bounds = self._calculate_floor_bounds(walls_data)

        # Parse optional inputs
        connectors = None
        if connectors_json:
            connectors_data = json.loads(connectors_json)
            if isinstance(connectors_data, dict) and 'connectors' in connectors_data:
                connectors = connectors_data['connectors']
            elif isinstance(connectors_data, list):
                connectors = connectors_data

        targets = None
        if targets_json:
            targets_data = json.loads(targets_json)
            if isinstance(targets_data, dict) and 'targets' in targets_data:
                targets = targets_data['targets']
            elif isinstance(targets_data, list):
                targets = targets_data

        return self.build_from_walls(
            walls_data,
            floor_bounds=floor_bounds,
            connectors=connectors,
            targets=targets
        )

    def _add_domain_graph_to_mdg(
        self,
        mdg: MultiDomainGraph,
        domain_id: str,
        graph: nx.Graph
    ) -> Dict[int, int]:
        """Add a domain's graph nodes/edges to the multi-domain graph."""
        node_mapping = {}  # local_id -> mdg_id

        # Keys to exclude from extra attributes
        excluded_keys = {'location', 'is_terminal', 'is_transition', 'domain_id', 'pos'}

        for local_id, data in graph.nodes(data=True):
            extra_attrs = {k: v for k, v in data.items() if k not in excluded_keys}
            mdg_id = mdg.add_node_to_domain(
                domain_id,
                data['location'],
                is_terminal=data.get('is_terminal', False),
                is_transition=data.get('is_transition', False),
                **extra_attrs
            )
            node_mapping[local_id] = mdg_id

        for u, v, edge_data in graph.edges(data=True):
            edge_attrs = {k: val for k, val in edge_data.items() if k != 'weight'}
            mdg.add_edge_to_domain(
                domain_id,
                node_mapping[u],
                node_mapping[v],
                weight=edge_data.get('weight'),
                **edge_attrs
            )

        return node_mapping

    def _generate_wall_corner_transitions(
        self,
        mdg: MultiDomainGraph,
        walls_data: List[Dict],
        wall_graphs: Dict[str, Tuple[RoutingDomain, nx.Graph]],
        wall_positions: Dict[str, Dict]
    ) -> None:
        """Generate transitions at wall corners."""
        # Find walls that share endpoints
        wall_endpoints = {}  # endpoint -> list of (wall_id, 'start'|'end')

        for wall_data in walls_data:
            wall_id = wall_data.get('id') or wall_data.get('wall_id')
            pos = wall_positions.get(wall_id, {})

            if 'start' in pos:
                key = self._round_point(pos['start'])
                if key not in wall_endpoints:
                    wall_endpoints[key] = []
                wall_endpoints[key].append((wall_id, 'start'))

            if 'end' in pos:
                key = self._round_point(pos['end'])
                if key not in wall_endpoints:
                    wall_endpoints[key] = []
                wall_endpoints[key].append((wall_id, 'end'))

        # For each shared endpoint, create transitions
        for corner, wall_list in wall_endpoints.items():
            if len(wall_list) >= 2:
                for i in range(len(wall_list)):
                    for j in range(i + 1, len(wall_list)):
                        wall_a_id, _ = wall_list[i]
                        wall_b_id, _ = wall_list[j]

                        if wall_a_id not in wall_graphs or wall_b_id not in wall_graphs:
                            continue

                        domain_a, graph_a = wall_graphs[wall_a_id]
                        domain_b, graph_b = wall_graphs[wall_b_id]

                        transitions = self._transition_gen.generate_wall_to_wall_transitions(
                            domain_a, domain_b,
                            graph_a, graph_b,
                            corner
                        )

                        for trans in transitions:
                            mdg.add_transition(trans)

    def _add_connector_terminals(
        self,
        mdg: MultiDomainGraph,
        connectors: List[Dict],
        wall_graphs: Dict[str, Tuple[RoutingDomain, nx.Graph]]
    ) -> None:
        """Add connector positions as terminal nodes."""
        for conn in connectors:
            wall_id = conn.get('wall_id')
            if wall_id and wall_id in wall_graphs:
                domain, graph = wall_graphs[wall_id]
                location = conn.get('location', (0, 0, 0))
                # Use U from location (along wall) and Z as V (elevation)
                u = location[0] if len(location) > 0 else 0
                v = location[2] if len(location) > 2 else 0

                builder = WallGraphBuilder(domain, self.wall_resolution)
                builder._node_counter = max(
                    (n for n in graph.nodes()), default=0
                ) + 1
                builder.add_terminal_nodes(graph, [(u, v)], is_source=True)

    def _add_target_terminals(
        self,
        mdg: MultiDomainGraph,
        targets: List[Dict],
        wall_graphs: Dict[str, Tuple[RoutingDomain, nx.Graph]]
    ) -> None:
        """Add target positions as terminal nodes."""
        for target in targets:
            domain_id = target.get('domain_id')
            if domain_id and domain_id in wall_graphs:
                domain, graph = wall_graphs[domain_id]
                plane_loc = target.get('plane_location', (0, 0))

                builder = WallGraphBuilder(domain, self.wall_resolution)
                builder._node_counter = max(
                    (n for n in graph.nodes()), default=0
                ) + 1
                builder.add_terminal_nodes(graph, [plane_loc], is_source=False)

    def _calculate_floor_bounds(
        self,
        walls_data: List[Dict]
    ) -> Optional[Tuple[float, float, float, float]]:
        """Calculate floor bounds from wall positions."""
        x_coords = []
        y_coords = []

        for wall in walls_data:
            if 'start' in wall:
                x_coords.append(wall['start'][0])
                y_coords.append(wall['start'][1])
            if 'end' in wall:
                x_coords.append(wall['end'][0])
                y_coords.append(wall['end'][1])

        if not x_coords or not y_coords:
            return None

        # Add padding
        padding = 1.0
        return (
            min(x_coords) - padding,
            max(x_coords) + padding,
            min(y_coords) - padding,
            max(y_coords) + padding
        )

    def _round_point(
        self,
        point: Tuple[float, float],
        precision: int = 2
    ) -> Tuple[float, float]:
        """Round point coordinates for comparison."""
        return (round(point[0], precision), round(point[1], precision))


def build_routing_graph(
    walls_json: str,
    connectors_json: Optional[str] = None,
    targets_json: Optional[str] = None,
    wall_resolution: float = 0.333,
    floor_resolution: float = 1.0
) -> MultiDomainGraph:
    """
    Convenience function to build a complete routing graph.

    Args:
        walls_json: JSON string with wall data
        connectors_json: Optional JSON with MEP connectors
        targets_json: Optional JSON with routing targets
        wall_resolution: Wall graph grid resolution
        floor_resolution: Floor graph grid resolution

    Returns:
        MultiDomainGraph ready for pathfinding
    """
    builder = UnifiedGraphBuilder(
        wall_grid_resolution=wall_resolution,
        floor_grid_resolution=floor_resolution
    )

    return builder.build_from_json(
        walls_json,
        connectors_json=connectors_json,
        targets_json=targets_json
    )
