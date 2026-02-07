# File: tests/wall_junctions/test_junction_detector.py

"""Tests for wall junction detection and classification.

Tests cover:
- Endpoint matching (L-corners)
- T-intersection detection (endpoint near wall mid-span)
- Junction classification (FREE_END, L_CORNER, T_INTERSECTION, etc.)
- Edge cases (inline walls, no walls, single wall)
- Tolerance sensitivity
"""

import pytest
import math

from src.timber_framing_generator.wall_junctions.junction_detector import (
    build_junction_graph,
    _points_close,
    _point_to_segment_distance,
    _calculate_angle,
    _extract_point,
    _extract_direction,
)
from src.timber_framing_generator.wall_junctions.junction_types import (
    JunctionType,
)


# =============================================================================
# Geometry Utility Tests
# =============================================================================


class TestPointsClose:
    """Tests for _points_close distance check."""

    def test_identical_points(self):
        assert _points_close((0, 0, 0), (0, 0, 0), 0.1) is True

    def test_points_within_tolerance(self):
        assert _points_close((0, 0, 0), (0.05, 0, 0), 0.1) is True

    def test_points_at_tolerance_boundary(self):
        assert _points_close((0, 0, 0), (0.1, 0, 0), 0.1) is True

    def test_points_outside_tolerance(self):
        assert _points_close((0, 0, 0), (0.2, 0, 0), 0.1) is False

    def test_3d_distance(self):
        # Distance = sqrt(0.05^2 + 0.05^2 + 0.05^2) ≈ 0.087
        assert _points_close((0, 0, 0), (0.05, 0.05, 0.05), 0.1) is True


class TestPointToSegmentDistance:
    """Tests for _point_to_segment_distance."""

    def test_point_at_segment_midpoint(self):
        dist, t = _point_to_segment_distance(
            (5.0, 1.0, 0.0),  # Point 1 ft away from mid-segment
            (0.0, 0.0, 0.0),  # Segment start
            (10.0, 0.0, 0.0),  # Segment end
        )
        assert abs(dist - 1.0) < 0.001
        assert abs(t - 0.5) < 0.001

    def test_point_at_segment_start(self):
        dist, t = _point_to_segment_distance(
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0),
        )
        assert abs(dist - 1.0) < 0.001
        assert abs(t - 0.0) < 0.001

    def test_point_beyond_segment_end(self):
        dist, t = _point_to_segment_distance(
            (15.0, 0.0, 0.0),  # Beyond segment end
            (0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0),
        )
        # Clamped to t=1.0, distance = 5.0
        assert abs(dist - 5.0) < 0.001
        assert abs(t - 1.0) < 0.001

    def test_degenerate_segment(self):
        dist, t = _point_to_segment_distance(
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),  # Zero-length segment
        )
        assert abs(dist - 1.0) < 0.001
        assert t == 0.0


class TestCalculateAngle:
    """Tests for _calculate_angle."""

    def test_parallel_vectors(self):
        angle = _calculate_angle((1, 0, 0), (1, 0, 0))
        assert abs(angle - 0.0) < 0.1

    def test_perpendicular_vectors(self):
        angle = _calculate_angle((1, 0, 0), (0, 1, 0))
        assert abs(angle - 90.0) < 0.1

    def test_opposite_vectors(self):
        angle = _calculate_angle((1, 0, 0), (-1, 0, 0))
        assert abs(angle - 180.0) < 0.1

    def test_45_degree_angle(self):
        angle = _calculate_angle((1, 0, 0), (1, 1, 0))
        assert abs(angle - 45.0) < 0.1


# =============================================================================
# Graph Construction Tests
# =============================================================================


class TestBuildJunctionGraph:
    """Tests for build_junction_graph main function."""

    def test_empty_walls(self):
        nodes = build_junction_graph([])
        assert len(nodes) == 0

    def test_single_wall_two_free_ends(self, free_end_wall):
        nodes = build_junction_graph(free_end_wall)

        # Single wall should produce 2 free-end nodes
        free_ends = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.FREE_END
        ]
        assert len(free_ends) == 2

    def test_l_corner_detection(self, l_corner_walls):
        nodes = build_junction_graph(l_corner_walls)

        # Should detect 1 L-corner and 2 free ends
        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        free_ends = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.FREE_END
        ]
        assert len(l_corners) == 1
        assert len(free_ends) == 2

    def test_l_corner_has_two_connections(self, l_corner_walls):
        nodes = build_junction_graph(l_corner_walls)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners) == 1
        assert len(l_corners[0].connections) == 2

        # Check both walls are represented
        wall_ids = {c.wall_id for c in l_corners[0].connections}
        assert wall_ids == {"wall_A", "wall_B"}

    def test_l_corner_position(self, l_corner_walls):
        nodes = build_junction_graph(l_corner_walls)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        pos = l_corners[0].position
        # Should be near (20, 0, 0)
        assert abs(pos[0] - 20.0) < 0.1
        assert abs(pos[1] - 0.0) < 0.1

    def test_t_intersection_detection(self, t_intersection_walls):
        nodes = build_junction_graph(t_intersection_walls)

        t_ints = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        ]
        assert len(t_ints) == 1

    def test_t_intersection_has_midspan_connection(self, t_intersection_walls):
        nodes = build_junction_graph(t_intersection_walls)

        t_ints = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        ]
        assert len(t_ints) == 1

        # Should have one midspan connection (continuous wall)
        midspan_conns = [c for c in t_ints[0].connections if c.is_midspan]
        assert len(midspan_conns) == 1
        assert midspan_conns[0].wall_id == "wall_A"

        # midspan_u should be ~15.0 (middle of 30 ft wall)
        assert abs(midspan_conns[0].midspan_u - 15.0) < 0.5

    def test_inline_walls_classified_as_inline(self, inline_walls):
        nodes = build_junction_graph(inline_walls)

        inline_nodes = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.INLINE
        ]
        # The shared endpoint should be classified as inline
        assert len(inline_nodes) == 1

    def test_four_room_layout(self, four_room_layout):
        nodes = build_junction_graph(four_room_layout)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        # Rectangle has 4 corners
        assert len(l_corners) == 4

    def test_tolerance_too_small_misses_junction(self, l_corner_walls):
        # Use extremely small tolerance — endpoints are exactly coincident
        # so they should still match
        nodes = build_junction_graph(l_corner_walls, tolerance=0.001)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        # Endpoints are at the same point, so even small tolerance works
        assert len(l_corners) == 1

    def test_angled_corner_detected(self, angled_corner_walls):
        nodes = build_junction_graph(angled_corner_walls)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners) == 1


# =============================================================================
# Extraction Tests
# =============================================================================


class TestExtraction:
    """Tests for wall data extraction helpers."""

    def test_extract_point_dict(self, l_corner_walls):
        pt = _extract_point(l_corner_walls[0], "start")
        assert abs(pt[0] - 0.0) < 0.001
        assert abs(pt[1] - 0.0) < 0.001
        assert abs(pt[2] - 0.0) < 0.001

    def test_extract_point_end(self, l_corner_walls):
        pt = _extract_point(l_corner_walls[0], "end")
        assert abs(pt[0] - 20.0) < 0.001

    def test_extract_direction(self, l_corner_walls):
        direction = _extract_direction(l_corner_walls[0])
        # Wall A goes from (0,0,0) to (20,0,0) → direction = (1, 0, 0)
        assert abs(direction[0] - 1.0) < 0.001
        assert abs(direction[1] - 0.0) < 0.001


# =============================================================================
# Thickness-Aware Matching Tests
# =============================================================================


class TestThicknessAwareMatching:
    """Tests for thickness-aware endpoint matching.

    Verifies that junction detection works correctly when wall
    endpoints are offset due to Revit's centerline representation.
    """

    def test_l_corner_detected_with_offset_endpoints(
        self, l_corner_offset_walls
    ):
        """L-corner is detected even though endpoints are ~0.301 ft apart."""
        nodes = build_junction_graph(l_corner_offset_walls)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners) == 1, (
            f"Expected 1 L-corner, got {len(l_corners)}. "
            f"Types: {[n.junction_type.value for n in nodes.values()]}"
        )

    def test_l_corner_offset_has_both_walls(self, l_corner_offset_walls):
        """Both walls are present in the L-corner connection list."""
        nodes = build_junction_graph(l_corner_offset_walls)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        wall_ids = {c.wall_id for c in l_corners[0].connections}
        assert wall_ids == {"wall_A", "wall_B"}

    def test_l_corner_offset_position_is_average(
        self, l_corner_offset_walls
    ):
        """Junction position is the average of the two offset endpoints."""
        nodes = build_junction_graph(l_corner_offset_walls)

        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        pos = l_corners[0].position
        # Average of (20.0, 0.0, 0.0) and (20.25, -0.167, 0.0)
        assert abs(pos[0] - 20.125) < 0.01
        assert abs(pos[1] - (-0.0835)) < 0.01

    def test_t_intersection_detected_with_offset(
        self, t_intersection_offset_walls
    ):
        """T-intersection is detected despite centerline offset of 0.25 ft."""
        nodes = build_junction_graph(t_intersection_offset_walls)

        t_ints = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        ]
        assert len(t_ints) == 1, (
            f"Expected 1 T-intersection, got {len(t_ints)}. "
            f"Types: {[n.junction_type.value for n in nodes.values()]}"
        )

    def test_t_intersection_offset_has_midspan_connection(
        self, t_intersection_offset_walls
    ):
        """T-intersection has a midspan connection for the continuous wall."""
        nodes = build_junction_graph(t_intersection_offset_walls)

        t_ints = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        ]
        midspan_conns = [c for c in t_ints[0].connections if c.is_midspan]
        assert len(midspan_conns) == 1
        assert midspan_conns[0].wall_id == "wall_A"

    def test_parallel_walls_not_merged(self, parallel_close_walls):
        """Two parallel walls 0.6 ft apart should NOT be merged.

        Even with thickness-aware tolerance of 0.5 ft, the distance
        (0.6 ft) exceeds the threshold.
        """
        nodes = build_junction_graph(parallel_close_walls)

        # All 4 endpoints should be free ends (no merging)
        free_ends = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.FREE_END
        ]
        assert len(free_ends) == 4

    def test_existing_coincident_fixtures_still_work(
        self, l_corner_walls, t_intersection_walls, four_room_layout
    ):
        """Backward compatibility: fixtures with coincident endpoints still pass."""
        # L-corner
        nodes_l = build_junction_graph(l_corner_walls)
        l_corners = [
            n for n in nodes_l.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners) == 1

        # T-intersection
        nodes_t = build_junction_graph(t_intersection_walls)
        t_ints = [
            n for n in nodes_t.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        ]
        assert len(t_ints) == 1

        # Four room layout
        nodes_4 = build_junction_graph(four_room_layout)
        l_corners_4 = [
            n for n in nodes_4.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners_4) == 4

    def test_thin_walls_use_base_tolerance(self):
        """For very thin walls, the base tolerance governs (not inflated lower)."""
        from tests.wall_junctions.conftest import create_mock_wall

        walls = [
            create_mock_wall(
                "wall_A", (0.0, 0.0, 0.0), (10.0, 0.0, 0.0),
                thickness=0.05,
            ),
            create_mock_wall(
                "wall_B", (10.0, 0.0, 0.0), (10.0, 10.0, 0.0),
                thickness=0.05,
            ),
        ]
        # (0.05 + 0.05) / 2 = 0.05, but base tolerance = 0.1
        # max(0.1, 0.05) = 0.1, so base tolerance governs
        nodes = build_junction_graph(walls, tolerance=0.1)
        l_corners = [
            n for n in nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners) == 1

    def test_thickness_aware_tolerance_formula(self):
        """Verify that (t1+t2)/2 >= sqrt((t1/2)^2 + (t2/2)^2) for all cases."""
        test_pairs = [
            (0.333, 0.5),    # 4" and 6" walls
            (0.5, 0.5),      # Two 6" walls
            (0.25, 0.667),   # 3" and 8" walls
            (0.083, 0.083),  # Two 1" walls
        ]
        for t1, t2 in test_pairs:
            formula = (t1 + t2) / 2.0
            geometric = math.sqrt((t1 / 2.0) ** 2 + (t2 / 2.0) ** 2)
            assert formula >= geometric, (
                f"Formula {formula} < geometric {geometric} "
                f"for t1={t1}, t2={t2}"
            )
