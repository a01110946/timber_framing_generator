# File: src/timber_framing_generator/mep/routing/hanan_grid.py
"""
Hanan Grid construction and MST computation for MEP routing.

Implements the Hanan Grid approach for Rectilinear Steiner Tree (RST)
construction, which provides optimal multi-terminal routing paths.

The Hanan Grid is formed by drawing horizontal and vertical lines through
each terminal point. Hanan's theorem guarantees that an optimal RST uses
only points from this grid.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set, Any
import logging
from collections import defaultdict

from .domains import Obstacle, Point2D
from .route_segment import RouteSegment, SegmentDirection, Route

logger = logging.getLogger(__name__)


@dataclass
class HananGrid:
    """
    Hanan Grid for rectilinear Steiner tree construction.

    The grid is formed by drawing horizontal and vertical lines through
    each terminal point, creating a lattice of intersection points.

    Attributes:
        terminals: Original terminal points (x, y)
        x_coords: Sorted unique X coordinates
        y_coords: Sorted unique Y coordinates
        points: All grid intersection points
        point_to_idx: Map from (x, y) to point index
        terminal_indices: Indices of terminal points in the grid
        blocked: Set of blocked point indices
        high_cost: Set of high-cost point indices (penetrations)
    """
    terminals: List[Tuple[float, float]] = field(default_factory=list)
    x_coords: List[float] = field(default_factory=list)
    y_coords: List[float] = field(default_factory=list)
    points: List[Tuple[float, float]] = field(default_factory=list)
    point_to_idx: Dict[Tuple[float, float], int] = field(default_factory=dict)
    terminal_indices: List[int] = field(default_factory=list)
    blocked: Set[int] = field(default_factory=set)
    high_cost: Dict[int, float] = field(default_factory=dict)

    @classmethod
    def from_terminals(
        cls,
        terminals: List[Tuple[float, float]],
        obstacles: Optional[List[Obstacle]] = None,
        tolerance: float = 1e-6
    ) -> 'HananGrid':
        """
        Construct Hanan grid from terminal points.

        Args:
            terminals: List of terminal (x, y) coordinates
            obstacles: Optional list of obstacles to mark as blocked
            tolerance: Coordinate comparison tolerance

        Returns:
            Constructed HananGrid
        """
        if not terminals:
            return cls()

        # Extract unique coordinates with tolerance
        x_set: Set[float] = set()
        y_set: Set[float] = set()

        for x, y in terminals:
            # Round to avoid floating point issues
            x_rounded = round(x / tolerance) * tolerance
            y_rounded = round(y / tolerance) * tolerance
            x_set.add(x_rounded)
            y_set.add(y_rounded)

        x_coords = sorted(x_set)
        y_coords = sorted(y_set)

        logger.debug(
            f"Hanan grid: {len(x_coords)} x {len(y_coords)} = "
            f"{len(x_coords) * len(y_coords)} points from {len(terminals)} terminals"
        )

        # Generate all grid points
        points = []
        point_to_idx = {}

        for y in y_coords:
            for x in x_coords:
                idx = len(points)
                pt = (x, y)
                points.append(pt)
                point_to_idx[pt] = idx

        # Find terminal indices
        terminal_indices = []
        for tx, ty in terminals:
            tx_rounded = round(tx / tolerance) * tolerance
            ty_rounded = round(ty / tolerance) * tolerance
            pt = (tx_rounded, ty_rounded)
            if pt in point_to_idx:
                terminal_indices.append(point_to_idx[pt])

        grid = cls(
            terminals=list(terminals),
            x_coords=x_coords,
            y_coords=y_coords,
            points=points,
            point_to_idx=point_to_idx,
            terminal_indices=terminal_indices
        )

        # Mark blocked points from obstacles
        if obstacles:
            grid._mark_obstacles(obstacles)

        return grid

    def _mark_obstacles(self, obstacles: List[Obstacle]) -> None:
        """Mark grid points blocked by obstacles."""
        for idx, (x, y) in enumerate(self.points):
            pt = Point2D(x, y)
            for obstacle in obstacles:
                if obstacle.contains_point(pt):
                    if not obstacle.is_penetrable:
                        self.blocked.add(idx)
                    else:
                        # High cost for penetrable obstacles
                        current = self.high_cost.get(idx, 1.0)
                        self.high_cost[idx] = max(current, 5.0)

    def get_neighbors(self, point_idx: int) -> List[int]:
        """
        Get adjacent grid points (up, down, left, right).

        Args:
            point_idx: Index of the point

        Returns:
            List of neighbor point indices
        """
        if point_idx < 0 or point_idx >= len(self.points):
            return []

        x, y = self.points[point_idx]
        neighbors = []

        # Find position in coordinate lists
        try:
            xi = self.x_coords.index(x)
            yi = self.y_coords.index(y)
        except ValueError:
            return []

        # Left neighbor
        if xi > 0:
            left_pt = (self.x_coords[xi - 1], y)
            if left_pt in self.point_to_idx:
                neighbors.append(self.point_to_idx[left_pt])

        # Right neighbor
        if xi < len(self.x_coords) - 1:
            right_pt = (self.x_coords[xi + 1], y)
            if right_pt in self.point_to_idx:
                neighbors.append(self.point_to_idx[right_pt])

        # Down neighbor
        if yi > 0:
            down_pt = (x, self.y_coords[yi - 1])
            if down_pt in self.point_to_idx:
                neighbors.append(self.point_to_idx[down_pt])

        # Up neighbor
        if yi < len(self.y_coords) - 1:
            up_pt = (x, self.y_coords[yi + 1])
            if up_pt in self.point_to_idx:
                neighbors.append(self.point_to_idx[up_pt])

        return neighbors

    def get_edge_cost(
        self,
        from_idx: int,
        to_idx: int,
        cost_map: Optional[Dict[Tuple[int, int], float]] = None
    ) -> float:
        """
        Get edge cost between adjacent points.

        Args:
            from_idx: Source point index
            to_idx: Target point index
            cost_map: Optional custom cost mapping

        Returns:
            Edge cost (infinity if blocked)
        """
        # Check if either endpoint is blocked
        if from_idx in self.blocked or to_idx in self.blocked:
            return float('inf')

        # Check custom cost map
        if cost_map:
            edge_key = (min(from_idx, to_idx), max(from_idx, to_idx))
            if edge_key in cost_map:
                return cost_map[edge_key]

        # Calculate Manhattan distance
        p1 = self.points[from_idx]
        p2 = self.points[to_idx]
        base_cost = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

        # Apply high cost multipliers
        multiplier = 1.0
        if from_idx in self.high_cost:
            multiplier = max(multiplier, self.high_cost[from_idx])
        if to_idx in self.high_cost:
            multiplier = max(multiplier, self.high_cost[to_idx])

        return base_cost * multiplier

    def get_all_edges(self) -> List[Tuple[int, int, float]]:
        """
        Get all edges in the grid with costs.

        Returns:
            List of (from_idx, to_idx, cost) tuples
        """
        edges = []
        seen = set()

        for idx in range(len(self.points)):
            for neighbor_idx in self.get_neighbors(idx):
                edge_key = (min(idx, neighbor_idx), max(idx, neighbor_idx))
                if edge_key not in seen:
                    cost = self.get_edge_cost(idx, neighbor_idx)
                    if cost < float('inf'):
                        edges.append((idx, neighbor_idx, cost))
                    seen.add(edge_key)

        return edges

    def is_terminal(self, point_idx: int) -> bool:
        """Check if a point is a terminal."""
        return point_idx in self.terminal_indices


class HananMST:
    """
    Minimum Spanning Tree computation on Hanan Grid.

    Uses Kruskal's algorithm with Union-Find for efficient MST
    construction. The resulting tree connects all terminal points
    with minimum total edge cost.
    """

    def __init__(self, grid: HananGrid):
        """
        Initialize MST solver.

        Args:
            grid: The Hanan grid to compute MST on
        """
        self.grid = grid
        self._parent: Dict[int, int] = {}
        self._rank: Dict[int, int] = {}

    def compute_mst(
        self,
        terminal_indices: Optional[List[int]] = None,
        cost_map: Optional[Dict[Tuple[int, int], float]] = None
    ) -> List[Tuple[int, int, float]]:
        """
        Compute MST connecting terminal points using Kruskal's algorithm.

        Uses a modified approach that finds the minimum Steiner tree
        connecting terminals through potentially non-terminal grid points.

        Args:
            terminal_indices: Terminals to connect (default: all grid terminals)
            cost_map: Optional custom edge costs

        Returns:
            List of (from_idx, to_idx, cost) edges forming the MST
        """
        if terminal_indices is None:
            terminal_indices = self.grid.terminal_indices

        if len(terminal_indices) < 2:
            return []

        # Initialize Union-Find
        self._parent.clear()
        self._rank.clear()

        # Get all edges and sort by cost
        all_edges = []
        for from_idx, to_idx, base_cost in self.grid.get_all_edges():
            if cost_map:
                edge_key = (min(from_idx, to_idx), max(from_idx, to_idx))
                cost = cost_map.get(edge_key, base_cost)
            else:
                cost = base_cost
            all_edges.append((cost, from_idx, to_idx))

        all_edges.sort()

        # Build MST using Kruskal's algorithm
        # We need to connect all terminals, possibly through Steiner points
        mst_edges = []
        terminal_set = set(terminal_indices)

        # Initialize each point as its own component
        for idx in range(len(self.grid.points)):
            self._parent[idx] = idx
            self._rank[idx] = 0

        # Process edges in cost order
        for cost, u, v in all_edges:
            if self._find(u) != self._find(v):
                self._union(u, v)
                mst_edges.append((u, v, cost))

                # Check if all terminals are connected
                if self._all_terminals_connected(terminal_set):
                    break

        # Prune edges not needed for terminal connectivity
        mst_edges = self._prune_unnecessary_edges(mst_edges, terminal_set)

        logger.debug(f"MST computed: {len(mst_edges)} edges")
        return mst_edges

    def _find(self, x: int) -> int:
        """Union-Find: find with path compression."""
        if self._parent[x] != x:
            self._parent[x] = self._find(self._parent[x])
        return self._parent[x]

    def _union(self, x: int, y: int) -> bool:
        """Union-Find: union by rank."""
        root_x = self._find(x)
        root_y = self._find(y)

        if root_x == root_y:
            return False

        if self._rank[root_x] < self._rank[root_y]:
            root_x, root_y = root_y, root_x

        self._parent[root_y] = root_x
        if self._rank[root_x] == self._rank[root_y]:
            self._rank[root_x] += 1

        return True

    def _all_terminals_connected(self, terminal_set: Set[int]) -> bool:
        """Check if all terminals are in the same component."""
        if not terminal_set:
            return True

        terminals = list(terminal_set)
        first_root = self._find(terminals[0])
        return all(self._find(t) == first_root for t in terminals[1:])

    def _prune_unnecessary_edges(
        self,
        edges: List[Tuple[int, int, float]],
        terminal_set: Set[int]
    ) -> List[Tuple[int, int, float]]:
        """
        Remove edges not needed for terminal connectivity.

        This removes "tails" - paths that don't lead to terminals.
        """
        # Build adjacency list
        adj: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
        for u, v, cost in edges:
            adj[u].append((v, cost))
            adj[v].append((u, cost))

        # Find nodes to keep using BFS from terminals
        to_keep: Set[int] = set()
        for terminal in terminal_set:
            to_keep.add(terminal)

        # Iteratively remove leaf nodes that aren't terminals
        changed = True
        while changed:
            changed = False
            for node in list(adj.keys()):
                if node not in terminal_set and len(adj[node]) == 1:
                    # This is a non-terminal leaf - remove it
                    neighbor, _ = adj[node][0]
                    adj[neighbor] = [(n, c) for n, c in adj[neighbor] if n != node]
                    del adj[node]
                    changed = True

        # Build pruned edge list
        pruned = []
        seen = set()
        for u, v, cost in edges:
            if u in adj and v in adj:
                edge_key = (min(u, v), max(u, v))
                if edge_key not in seen:
                    # Verify edge still exists in adjacency
                    if any(n == v for n, _ in adj.get(u, [])):
                        pruned.append((u, v, cost))
                        seen.add(edge_key)

        return pruned


class SteinerTreeBuilder:
    """
    Builds Steiner trees from Hanan Grid MST.

    Handles identification of Steiner points (non-terminal junctions)
    and conversion of the MST to directed route segments.
    """

    def __init__(
        self,
        grid: HananGrid,
        mst_edges: List[Tuple[int, int, float]]
    ):
        """
        Initialize builder.

        Args:
            grid: The Hanan grid
            mst_edges: MST edges from HananMST
        """
        self.grid = grid
        self.mst_edges = mst_edges
        self._adjacency: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
        self._build_adjacency()

    def _build_adjacency(self) -> None:
        """Build adjacency list from MST edges."""
        self._adjacency.clear()
        for u, v, cost in self.mst_edges:
            self._adjacency[u].append((v, cost))
            self._adjacency[v].append((u, cost))

    def prune_steiner_points(self) -> List[Tuple[int, int, float]]:
        """
        Remove degree-2 Steiner points that are collinear pass-throughs.

        A degree-2 non-terminal can be removed if its neighbors are
        collinear (the path goes straight through).

        Returns:
            Pruned list of MST edges
        """
        # Find prunable nodes
        prunable = set()
        terminal_set = set(self.grid.terminal_indices)

        for node, neighbors in self._adjacency.items():
            if node in terminal_set:
                continue  # Don't prune terminals

            if len(neighbors) != 2:
                continue  # Only prune degree-2 nodes

            # Check collinearity
            n1_idx, _ = neighbors[0]
            n2_idx, _ = neighbors[1]

            p = self.grid.points[node]
            p1 = self.grid.points[n1_idx]
            p2 = self.grid.points[n2_idx]

            # Collinear if all same x or all same y
            same_x = abs(p[0] - p1[0]) < 1e-6 and abs(p[0] - p2[0]) < 1e-6
            same_y = abs(p[1] - p1[1]) < 1e-6 and abs(p[1] - p2[1]) < 1e-6

            if same_x or same_y:
                prunable.add(node)

        if not prunable:
            return self.mst_edges

        # Rebuild edges without prunable nodes
        new_edges = []
        for u, v, cost in self.mst_edges:
            if u not in prunable and v not in prunable:
                new_edges.append((u, v, cost))

        # Add direct edges for pruned nodes
        for node in prunable:
            neighbors = self._adjacency[node]
            if len(neighbors) == 2:
                n1_idx, c1 = neighbors[0]
                n2_idx, c2 = neighbors[1]
                new_cost = c1 + c2
                new_edges.append((n1_idx, n2_idx, new_cost))

        # Update adjacency and recurse
        self.mst_edges = new_edges
        self._build_adjacency()

        # May need multiple passes
        if prunable:
            return self.prune_steiner_points()

        return self.mst_edges

    def to_route_segments(
        self,
        source_idx: int,
        domain_id: str = ""
    ) -> List[RouteSegment]:
        """
        Convert tree to directed route segments from source.

        Uses BFS to traverse the tree from the source terminal,
        creating RouteSegments for each edge.

        Args:
            source_idx: Index of the source terminal
            domain_id: Domain ID for the segments

        Returns:
            List of RouteSegments forming the route tree
        """
        if source_idx not in self._adjacency:
            return []

        segments = []
        visited = {source_idx}
        queue = [source_idx]
        terminal_set = set(self.grid.terminal_indices)

        while queue:
            current = queue.pop(0)
            current_pt = self.grid.points[current]

            for neighbor_idx, cost in self._adjacency[current]:
                if neighbor_idx in visited:
                    continue

                visited.add(neighbor_idx)
                queue.append(neighbor_idx)

                neighbor_pt = self.grid.points[neighbor_idx]

                # Determine direction
                dx = abs(neighbor_pt[0] - current_pt[0])
                dy = abs(neighbor_pt[1] - current_pt[1])
                if dx > dy:
                    direction = SegmentDirection.HORIZONTAL
                else:
                    direction = SegmentDirection.VERTICAL

                # Create segment
                segment = RouteSegment(
                    start=current_pt,
                    end=neighbor_pt,
                    direction=direction,
                    length=dx + dy,
                    cost=cost,
                    domain_id=domain_id,
                    is_steiner=neighbor_idx not in terminal_set
                )
                segments.append(segment)

        return segments

    def get_steiner_points(self) -> List[Tuple[float, float]]:
        """
        Get coordinates of Steiner points (non-terminal junctions).

        Returns:
            List of (x, y) coordinates of Steiner points
        """
        terminal_set = set(self.grid.terminal_indices)
        tree_nodes = set()

        for u, v, _ in self.mst_edges:
            tree_nodes.add(u)
            tree_nodes.add(v)

        steiner = []
        for node in tree_nodes:
            if node not in terminal_set:
                steiner.append(self.grid.points[node])

        return steiner

    def to_route(
        self,
        route_id: str,
        system_type: str,
        source_idx: int,
        target_idx: int,
        domain_id: str = ""
    ) -> Route:
        """
        Convert MST path to a Route object.

        Args:
            route_id: Unique route identifier
            system_type: MEP system type
            source_idx: Source terminal index
            target_idx: Target terminal index
            domain_id: Domain ID

        Returns:
            Route object with segments
        """
        segments = self.to_route_segments(source_idx, domain_id)

        source_pt = self.grid.points[source_idx] if source_idx < len(self.grid.points) else None
        target_pt = self.grid.points[target_idx] if target_idx < len(self.grid.points) else None

        return Route(
            id=route_id,
            system_type=system_type,
            segments=segments,
            source=source_pt,
            target=target_pt,
            domains_crossed=[domain_id] if domain_id else []
        )


def compute_hanan_mst(
    terminals: List[Tuple[float, float]],
    obstacles: Optional[List[Obstacle]] = None,
    prune: bool = True
) -> Tuple[HananGrid, List[Tuple[int, int, float]]]:
    """
    Convenience function to compute Hanan MST from terminals.

    Args:
        terminals: List of terminal (x, y) coordinates
        obstacles: Optional obstacles to avoid
        prune: Whether to prune Steiner points

    Returns:
        Tuple of (HananGrid, MST edges)
    """
    grid = HananGrid.from_terminals(terminals, obstacles)
    mst = HananMST(grid)
    edges = mst.compute_mst()

    if prune and edges:
        builder = SteinerTreeBuilder(grid, edges)
        edges = builder.prune_steiner_points()

    return grid, edges
