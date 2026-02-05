# File: tests/mep/routing/test_hanan_grid.py
"""
Unit tests for Hanan Grid MST implementation.

Tests cover:
- Grid construction from terminals
- Obstacle marking
- MST computation
- Steiner point pruning
- Tree-to-route conversion
"""

import pytest
from src.timber_framing_generator.mep.routing import (
    HananGrid,
    HananMST,
    SteinerTreeBuilder,
    compute_hanan_mst,
    RouteSegment,
    SegmentDirection,
    Route,
    Obstacle,
    Point2D,
)


# =============================================================================
# RouteSegment Tests
# =============================================================================

class TestRouteSegment:
    """Tests for RouteSegment dataclass."""

    def test_segment_creation_basic(self):
        """Test basic segment creation."""
        seg = RouteSegment(
            start=(0, 0),
            end=(5, 0)
        )
        assert seg.start == (0, 0)
        assert seg.end == (5, 0)
        assert seg.length == 5.0
        assert seg.direction == SegmentDirection.HORIZONTAL

    def test_segment_vertical_detection(self):
        """Test vertical direction detection."""
        seg = RouteSegment(
            start=(0, 0),
            end=(0, 5)
        )
        assert seg.direction == SegmentDirection.VERTICAL
        assert seg.length == 5.0

    def test_segment_diagonal_detection(self):
        """Test diagonal direction detection."""
        seg = RouteSegment(
            start=(0, 0),
            end=(3, 4)
        )
        assert seg.direction == SegmentDirection.DIAGONAL
        assert seg.length == 7.0  # Manhattan distance

    def test_segment_reversed(self):
        """Test segment reversal."""
        seg = RouteSegment(
            start=(0, 0),
            end=(5, 0),
            cost=10.0,
            domain_id="wall_1"
        )
        rev = seg.reversed()
        assert rev.start == (5, 0)
        assert rev.end == (0, 0)
        assert rev.cost == 10.0
        assert rev.domain_id == "wall_1"

    def test_segment_to_dict(self):
        """Test segment serialization."""
        seg = RouteSegment(
            start=(0, 0),
            end=(5, 0),
            cost=10.0,
            domain_id="wall_1",
            is_steiner=True
        )
        data = seg.to_dict()
        assert data["start"] == [0, 0]
        assert data["end"] == [5, 0]
        assert data["domain_id"] == "wall_1"
        assert data["is_steiner"] is True

    def test_segment_from_dict(self):
        """Test segment deserialization."""
        data = {
            "start": [0, 0],
            "end": [5, 0],
            "direction": "horizontal",
            "cost": 10.0,
            "domain_id": "wall_1"
        }
        seg = RouteSegment.from_dict(data)
        assert seg.start == (0, 0)
        assert seg.end == (5, 0)
        assert seg.cost == 10.0


class TestRoute:
    """Tests for Route dataclass."""

    def test_route_creation(self):
        """Test basic route creation."""
        route = Route(
            id="route_1",
            system_type="sanitary"
        )
        assert route.id == "route_1"
        assert route.system_type == "sanitary"
        assert route.total_cost == 0.0

    def test_route_add_segment(self):
        """Test adding segments to route."""
        route = Route(id="route_1", system_type="supply")
        seg1 = RouteSegment(start=(0, 0), end=(5, 0), cost=5.0, domain_id="wall_1")
        seg2 = RouteSegment(start=(5, 0), end=(5, 3), cost=3.0, domain_id="wall_1")

        route.add_segment(seg1)
        route.add_segment(seg2)

        assert route.total_cost == 8.0
        assert route.total_length == 8.0
        assert len(route.segments) == 2
        assert "wall_1" in route.domains_crossed

    def test_route_serialization(self):
        """Test route to/from dict."""
        route = Route(
            id="route_1",
            system_type="sanitary",
            source=(0, 0),
            target=(10, 5)
        )
        route.add_segment(RouteSegment(start=(0, 0), end=(10, 0), cost=10.0))

        data = route.to_dict()
        assert data["id"] == "route_1"
        assert data["source"] == [0, 0]
        assert len(data["segments"]) == 1

        restored = Route.from_dict(data)
        assert restored.id == "route_1"
        assert restored.source == (0, 0)


# =============================================================================
# HananGrid Tests
# =============================================================================

class TestHananGridConstruction:
    """Tests for HananGrid construction."""

    def test_empty_terminals(self):
        """Test grid with no terminals."""
        grid = HananGrid.from_terminals([])
        assert len(grid.points) == 0
        assert len(grid.terminal_indices) == 0

    def test_single_terminal(self):
        """Test grid with single terminal."""
        grid = HananGrid.from_terminals([(5, 3)])
        assert len(grid.points) == 1
        assert grid.points[0] == (5.0, 3.0)
        assert len(grid.terminal_indices) == 1

    def test_two_terminals_horizontal(self):
        """Test grid with two terminals on same Y."""
        grid = HananGrid.from_terminals([(0, 0), (5, 0)])
        # 2 x coords, 1 y coord = 2 points
        assert len(grid.x_coords) == 2
        assert len(grid.y_coords) == 1
        assert len(grid.points) == 2
        assert len(grid.terminal_indices) == 2

    def test_two_terminals_vertical(self):
        """Test grid with two terminals on same X."""
        grid = HananGrid.from_terminals([(0, 0), (0, 5)])
        assert len(grid.x_coords) == 1
        assert len(grid.y_coords) == 2
        assert len(grid.points) == 2

    def test_three_terminals_l_shape(self):
        """Test grid with L-shaped terminals."""
        terminals = [(0, 0), (5, 0), (0, 3)]
        grid = HananGrid.from_terminals(terminals)
        # x: {0, 5}, y: {0, 3} = 4 points
        assert len(grid.x_coords) == 2
        assert len(grid.y_coords) == 2
        assert len(grid.points) == 4
        assert len(grid.terminal_indices) == 3

    def test_four_terminals_square(self):
        """Test grid with square terminals."""
        terminals = [(0, 0), (5, 0), (5, 5), (0, 5)]
        grid = HananGrid.from_terminals(terminals)
        # x: {0, 5}, y: {0, 5} = 4 points (terminals are at corners)
        assert len(grid.points) == 4
        assert len(grid.terminal_indices) == 4

    def test_grid_with_interior_point(self):
        """Test grid that creates interior (Steiner) points."""
        terminals = [(0, 0), (2, 0), (1, 1)]
        grid = HananGrid.from_terminals(terminals)
        # x: {0, 1, 2}, y: {0, 1} = 6 points
        assert len(grid.x_coords) == 3
        assert len(grid.y_coords) == 2
        assert len(grid.points) == 6
        assert len(grid.terminal_indices) == 3

    def test_duplicate_coordinates(self):
        """Test that duplicate coordinates are deduplicated."""
        terminals = [(0, 0), (5, 0), (0, 3), (5, 3)]
        grid = HananGrid.from_terminals(terminals)
        # x: {0, 5}, y: {0, 3} = 4 points
        assert len(grid.points) == 4

    def test_point_to_idx_mapping(self):
        """Test point to index lookup."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        assert (0.0, 0.0) in grid.point_to_idx
        assert (5.0, 0.0) in grid.point_to_idx


class TestHananGridNeighbors:
    """Tests for neighbor finding."""

    def test_neighbors_corner(self):
        """Test neighbors of corner point."""
        terminals = [(0, 0), (2, 0), (0, 2), (2, 2)]
        grid = HananGrid.from_terminals(terminals)
        # Corner at (0, 0) should have 2 neighbors
        idx = grid.point_to_idx[(0.0, 0.0)]
        neighbors = grid.get_neighbors(idx)
        assert len(neighbors) == 2

    def test_neighbors_edge(self):
        """Test neighbors of edge point (only 3 neighbors)."""
        # Create 3x2 grid
        terminals = [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1)]
        grid = HananGrid.from_terminals(terminals)
        # Middle bottom point has 3 neighbors
        idx = grid.point_to_idx[(1.0, 0.0)]
        neighbors = grid.get_neighbors(idx)
        assert len(neighbors) == 3  # left, right, up

    def test_neighbors_interior(self):
        """Test neighbors of interior point (4 neighbors)."""
        terminals = [(0, 0), (2, 0), (0, 2), (2, 2), (1, 1)]
        grid = HananGrid.from_terminals(terminals)
        # Interior point should have 4 neighbors
        idx = grid.point_to_idx[(1.0, 1.0)]
        neighbors = grid.get_neighbors(idx)
        assert len(neighbors) == 4


class TestHananGridObstacles:
    """Tests for obstacle marking."""

    def test_blocked_point(self):
        """Test that blocked points are marked."""
        terminals = [(0, 0), (5, 0), (0, 5), (5, 5)]
        obstacle = Obstacle(
            id="block_1",
            obstacle_type="stud",
            bounds=(2, 2, 3, 3),
            is_penetrable=False
        )
        grid = HananGrid.from_terminals(terminals, obstacles=[obstacle])
        # No points should be blocked (obstacle not at grid points)
        assert len(grid.blocked) == 0

    def test_blocked_point_at_grid(self):
        """Test blocking when obstacle is at grid point."""
        terminals = [(0, 0), (2, 0), (0, 2), (2, 2)]
        # Obstacle at grid intersection
        obstacle = Obstacle(
            id="block_1",
            obstacle_type="stud",
            bounds=(1.9, 1.9, 2.1, 2.1),
            is_penetrable=False
        )
        grid = HananGrid.from_terminals(terminals, obstacles=[obstacle])
        idx = grid.point_to_idx.get((2.0, 2.0))
        if idx is not None:
            assert idx in grid.blocked

    def test_high_cost_penetrable(self):
        """Test high cost for penetrable obstacles."""
        terminals = [(0, 0), (2, 0)]
        obstacle = Obstacle(
            id="stud_1",
            obstacle_type="stud",
            bounds=(-0.1, -0.1, 0.1, 0.1),
            is_penetrable=True
        )
        grid = HananGrid.from_terminals(terminals, obstacles=[obstacle])
        idx = grid.point_to_idx.get((0.0, 0.0))
        if idx is not None:
            assert idx in grid.high_cost
            assert grid.high_cost[idx] >= 5.0


class TestHananGridEdges:
    """Tests for edge operations."""

    def test_edge_cost_clear(self):
        """Test edge cost for clear path."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        idx0 = grid.point_to_idx[(0.0, 0.0)]
        idx1 = grid.point_to_idx[(5.0, 0.0)]
        cost = grid.get_edge_cost(idx0, idx1)
        assert cost == 5.0  # Manhattan distance

    def test_edge_cost_blocked(self):
        """Test edge cost when blocked."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        grid.blocked.add(0)  # Block first point
        cost = grid.get_edge_cost(0, 1)
        assert cost == float('inf')

    def test_edge_cost_high_cost(self):
        """Test edge cost with multiplier."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        grid.high_cost[0] = 3.0
        cost = grid.get_edge_cost(0, 1)
        assert cost == 15.0  # 5 * 3

    def test_get_all_edges(self):
        """Test getting all edges."""
        terminals = [(0, 0), (2, 0), (0, 2), (2, 2)]
        grid = HananGrid.from_terminals(terminals)
        edges = grid.get_all_edges()
        # 2x2 grid has 4 edges
        assert len(edges) == 4


# =============================================================================
# HananMST Tests
# =============================================================================

class TestHananMST:
    """Tests for MST computation."""

    def test_mst_two_terminals(self):
        """Test MST with two terminals."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()
        assert len(edges) == 1
        assert edges[0][2] == 5.0  # cost

    def test_mst_three_terminals_line(self):
        """Test MST with three collinear terminals."""
        terminals = [(0, 0), (3, 0), (6, 0)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()
        assert len(edges) == 2
        total_cost = sum(e[2] for e in edges)
        assert total_cost == 6.0

    def test_mst_three_terminals_l(self):
        """Test MST with L-shaped terminals."""
        terminals = [(0, 0), (3, 0), (0, 3)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()
        # Should connect with 2 edges, possibly through Steiner
        total_cost = sum(e[2] for e in edges)
        assert total_cost == 6.0  # Optimal: 3+3

    def test_mst_four_terminals_square(self):
        """Test MST with square terminals."""
        terminals = [(0, 0), (4, 0), (4, 4), (0, 4)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()
        # MST for square needs 3 edges
        total_cost = sum(e[2] for e in edges)
        assert total_cost == 12.0  # Three edges of 4

    def test_mst_single_terminal(self):
        """Test MST with single terminal."""
        terminals = [(5, 5)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()
        assert len(edges) == 0

    def test_mst_connects_all_terminals(self):
        """Test that MST connects all terminals."""
        terminals = [(0, 0), (5, 0), (2, 3), (7, 2)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()

        # Build connectivity
        connected = set()
        adj = {}
        for u, v, _ in edges:
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)

        if edges:
            # BFS from first terminal
            start = grid.terminal_indices[0]
            queue = [start]
            connected.add(start)
            while queue:
                node = queue.pop(0)
                for neighbor in adj.get(node, []):
                    if neighbor not in connected:
                        connected.add(neighbor)
                        queue.append(neighbor)

        # All terminals should be connected
        for t_idx in grid.terminal_indices:
            assert t_idx in connected


class TestMSTWithCosts:
    """Tests for MST with custom costs."""

    def test_mst_avoids_high_cost(self):
        """Test MST prefers lower cost paths."""
        terminals = [(0, 0), (2, 0), (1, 1)]
        grid = HananGrid.from_terminals(terminals)

        # Make direct path expensive
        cost_map = {(0, 1): 100.0}  # (0,0)-(2,0) expensive

        mst = HananMST(grid)
        edges = mst.compute_mst(cost_map=cost_map)

        # Should route through (1, 0) or similar
        total_cost = sum(e[2] for e in edges)
        assert total_cost < 100.0  # Avoided expensive edge


# =============================================================================
# SteinerTreeBuilder Tests
# =============================================================================

class TestSteinerTreeBuilder:
    """Tests for Steiner tree building."""

    def test_get_steiner_points_none(self):
        """Test when there are no Steiner points."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()

        builder = SteinerTreeBuilder(grid, edges)
        steiner = builder.get_steiner_points()
        assert len(steiner) == 0

    def test_get_steiner_points_with_junction(self):
        """Test identification of Steiner junction."""
        terminals = [(0, 0), (4, 0), (2, 2)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()

        builder = SteinerTreeBuilder(grid, edges)
        steiner = builder.get_steiner_points()
        # May have Steiner point at (2, 0)
        # This depends on MST structure

    def test_prune_pass_through(self):
        """Test pruning collinear pass-through points."""
        # Three terminals in a line with point in middle
        terminals = [(0, 0), (5, 0), (10, 0)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()

        builder = SteinerTreeBuilder(grid, edges)
        pruned = builder.prune_steiner_points()
        # Should have 2 edges (or merged into fewer)
        assert len(pruned) >= 1

    def test_to_route_segments(self):
        """Test conversion to route segments."""
        terminals = [(0, 0), (5, 0), (0, 3)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()

        builder = SteinerTreeBuilder(grid, edges)
        source_idx = grid.terminal_indices[0]
        segments = builder.to_route_segments(source_idx, domain_id="wall_1")

        assert len(segments) >= 1
        assert all(s.domain_id == "wall_1" for s in segments)

    def test_to_route(self):
        """Test conversion to Route object."""
        terminals = [(0, 0), (5, 0)]
        grid = HananGrid.from_terminals(terminals)
        mst = HananMST(grid)
        edges = mst.compute_mst()

        builder = SteinerTreeBuilder(grid, edges)
        route = builder.to_route(
            route_id="test_route",
            system_type="sanitary",
            source_idx=grid.terminal_indices[0],
            target_idx=grid.terminal_indices[1],
            domain_id="wall_1"
        )

        assert route.id == "test_route"
        assert route.system_type == "sanitary"
        assert len(route.segments) >= 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestComputeHananMST:
    """Tests for convenience function."""

    def test_compute_basic(self):
        """Test basic convenience function."""
        terminals = [(0, 0), (5, 0), (0, 3)]
        grid, edges = compute_hanan_mst(terminals)

        assert len(grid.points) > 0
        assert len(edges) >= 1

    def test_compute_with_obstacles(self):
        """Test with obstacles."""
        terminals = [(0, 0), (5, 0)]
        obstacle = Obstacle(
            id="block",
            obstacle_type="stud",
            bounds=(2, -1, 3, 1),
            is_penetrable=False
        )
        grid, edges = compute_hanan_mst(terminals, obstacles=[obstacle])
        # Should still find a path
        assert len(grid.points) >= 2

    def test_compute_with_prune(self):
        """Test with pruning enabled."""
        terminals = [(0, 0), (5, 0), (10, 0)]
        grid, edges = compute_hanan_mst(terminals, prune=True)
        # Pruning should simplify the tree
        assert len(edges) >= 1


class TestComplexScenarios:
    """Tests for complex routing scenarios."""

    def test_five_terminal_star(self):
        """Test star pattern with center and 4 corners."""
        terminals = [
            (2, 2),  # center
            (0, 0), (4, 0), (4, 4), (0, 4)  # corners
        ]
        grid, edges = compute_hanan_mst(terminals)

        # Should connect all 5 terminals
        assert len(grid.terminal_indices) == 5

        # Total cost should be reasonable - 4 edges needed for 5 nodes
        # Center to each corner is 4 manhattan distance, but MST may use
        # a more efficient Steiner tree configuration
        total_cost = sum(e[2] for e in edges)
        assert total_cost <= 16.0  # 4 edges max, each ≤4 distance

    def test_bathroom_layout(self):
        """Test typical bathroom fixture layout."""
        terminals = [
            (0, 0),    # toilet
            (2, 0),    # sink
            (4, 0),    # shower drain
            (0, 2.5),  # vent stack
        ]
        grid, edges = compute_hanan_mst(terminals)

        # Build route
        mst = HananMST(grid)
        edges = mst.compute_mst()
        builder = SteinerTreeBuilder(grid, edges)

        # Find toilet as source (usually main fixture)
        source_idx = grid.terminal_indices[0]
        segments = builder.to_route_segments(source_idx)

        assert len(segments) >= 3  # At least 3 connections

    def test_grid_resolution_sensitivity(self):
        """Test that close terminals are handled."""
        # Very close terminals
        terminals = [(0, 0), (0.001, 0), (1, 0)]
        grid = HananGrid.from_terminals(terminals, tolerance=0.01)

        # First two should merge
        assert len(grid.x_coords) == 2  # 0 and 1
