# File: tests/constructai_demo/test_opening_matcher.py
"""Tests for opening-to-wall matching."""

import math

import pytest

from src.constructai_demo.coordinate_converter import ConvertedPoint, ConvertedWall, ConvertedOpening
from src.constructai_demo.opening_matcher import (
    MatchedOpening,
    get_unmatched_openings,
    match_openings_to_walls,
    point_to_segment_distance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wall(x1, y1, x2, y2, idx=0) -> ConvertedWall:
    return ConvertedWall(
        p1=ConvertedPoint(x1, y1),
        p2=ConvertedPoint(x2, y2),
        length_ft=math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2),
        thickness_ft=0.3,
        thickness_m=0.1,
        original_index=idx,
    )


def _opening(x1, y1, x2, y2, opening_type="door", idx=0) -> ConvertedOpening:
    return ConvertedOpening(
        p1=ConvertedPoint(x1, y1),
        p2=ConvertedPoint(x2, y2),
        width_ft=math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2),
        opening_type=opening_type,
        original_index=idx,
    )


# ---------------------------------------------------------------------------
# Point-to-segment distance tests
# ---------------------------------------------------------------------------

class TestPointToSegmentDistance:
    def test_perpendicular_projection(self):
        """Point directly above segment midpoint."""
        dist, t, closest = point_to_segment_distance(
            ConvertedPoint(5.0, 1.0),
            ConvertedPoint(0.0, 0.0),
            ConvertedPoint(10.0, 0.0),
        )
        assert pytest.approx(dist, abs=1e-6) == 1.0
        assert pytest.approx(t, abs=1e-6) == 0.5
        assert pytest.approx(closest.x, abs=1e-6) == 5.0
        assert pytest.approx(closest.y, abs=1e-6) == 0.0

    def test_point_at_start(self):
        dist, t, closest = point_to_segment_distance(
            ConvertedPoint(0.0, 1.0),
            ConvertedPoint(0.0, 0.0),
            ConvertedPoint(10.0, 0.0),
        )
        assert pytest.approx(dist, abs=1e-6) == 1.0
        assert pytest.approx(t, abs=1e-6) == 0.0

    def test_point_at_end(self):
        dist, t, closest = point_to_segment_distance(
            ConvertedPoint(10.0, 1.0),
            ConvertedPoint(0.0, 0.0),
            ConvertedPoint(10.0, 0.0),
        )
        assert pytest.approx(dist, abs=1e-6) == 1.0
        assert pytest.approx(t, abs=1e-6) == 1.0

    def test_point_beyond_end(self):
        """Point past the end clamps to t=1."""
        dist, t, closest = point_to_segment_distance(
            ConvertedPoint(15.0, 0.0),
            ConvertedPoint(0.0, 0.0),
            ConvertedPoint(10.0, 0.0),
        )
        assert pytest.approx(dist, abs=1e-6) == 5.0
        assert pytest.approx(t, abs=1e-6) == 1.0
        assert pytest.approx(closest.x, abs=1e-6) == 10.0

    def test_degenerate_segment(self):
        """Zero-length segment."""
        dist, t, closest = point_to_segment_distance(
            ConvertedPoint(3.0, 4.0),
            ConvertedPoint(0.0, 0.0),
            ConvertedPoint(0.0, 0.0),
        )
        assert pytest.approx(dist, abs=1e-6) == 5.0  # 3-4-5 triangle
        assert t == 0.0

    def test_vertical_segment(self):
        """Vertical wall segment."""
        dist, t, closest = point_to_segment_distance(
            ConvertedPoint(1.0, 5.0),
            ConvertedPoint(0.0, 0.0),
            ConvertedPoint(0.0, 10.0),
        )
        assert pytest.approx(dist, abs=1e-6) == 1.0
        assert pytest.approx(t, abs=1e-6) == 0.5


# ---------------------------------------------------------------------------
# Opening matching tests
# ---------------------------------------------------------------------------

class TestMatchOpeningsToWalls:
    def test_door_on_horizontal_wall(self):
        """Door midpoint near a horizontal wall -> matched."""
        walls = [_wall(0, 0, 20, 0, idx=0)]
        # Door centered at (10, 0.1) - very close to wall
        doors = [_opening(9, 0.1, 11, 0.1, "door", idx=0)]
        result = match_openings_to_walls(walls, doors)
        assert 0 in result
        assert len(result[0]) == 1
        assert result[0][0].host_wall_index == 0
        assert result[0][0].distance_ft < 0.2

    def test_window_on_vertical_wall(self):
        """Window near a vertical wall."""
        walls = [_wall(0, 0, 0, 20, idx=0)]
        windows = [_opening(0.1, 8, 0.1, 12, "window", idx=0)]
        result = match_openings_to_walls(walls, windows)
        assert 0 in result
        assert result[0][0].opening.opening_type == "window"

    def test_multiple_openings_same_wall(self):
        """Two doors on the same wall."""
        walls = [_wall(0, 0, 30, 0, idx=0)]
        doors = [
            _opening(5, 0.1, 8, 0.1, "door", idx=0),
            _opening(20, 0.1, 23, 0.1, "door", idx=1),
        ]
        result = match_openings_to_walls(walls, doors)
        assert len(result[0]) == 2

    def test_opening_matched_to_nearest_wall(self):
        """Opening closer to wall 1 than wall 0."""
        walls = [
            _wall(0, 0, 20, 0, idx=0),  # y=0
            _wall(0, 5, 20, 5, idx=1),  # y=5
        ]
        # Door at y=4.8 -> closer to wall 1 (y=5)
        doors = [_opening(10, 4.8, 12, 4.8, "door", idx=0)]
        result = match_openings_to_walls(walls, doors)
        assert 1 in result
        assert 0 not in result

    def test_opening_beyond_tolerance(self):
        """Opening too far from any wall -> unmatched."""
        walls = [_wall(0, 0, 20, 0, idx=0)]
        doors = [_opening(10, 5.0, 12, 5.0, "door", idx=0)]
        result = match_openings_to_walls(walls, doors, tolerance_ft=1.0)
        assert len(result) == 0

    def test_empty_openings(self):
        walls = [_wall(0, 0, 20, 0)]
        result = match_openings_to_walls(walls, [])
        assert result == {}

    def test_parameter_t_along_wall(self):
        """Check the parameter t correctly represents position along wall."""
        walls = [_wall(0, 0, 20, 0, idx=0)]
        # Door centered at x=15 on wall from x=0 to x=20
        doors = [_opening(14, 0.05, 16, 0.05, "door", idx=0)]
        result = match_openings_to_walls(walls, doors)
        matched = result[0][0]
        assert pytest.approx(matched.parameter_t, abs=0.02) == 0.75


# ---------------------------------------------------------------------------
# Unmatched openings test
# ---------------------------------------------------------------------------

class TestGetUnmatchedOpenings:
    def test_finds_unmatched(self):
        walls = [_wall(0, 0, 20, 0)]
        openings = [
            _opening(10, 0.1, 12, 0.1, "door", idx=0),   # will match
            _opening(10, 50.0, 12, 50.0, "door", idx=1),  # too far
        ]
        matched = match_openings_to_walls(walls, openings, tolerance_ft=1.0)
        unmatched = get_unmatched_openings(openings, matched)
        assert len(unmatched) == 1
        assert unmatched[0].original_index == 1

    def test_all_matched(self):
        walls = [_wall(0, 0, 20, 0)]
        openings = [_opening(10, 0.1, 12, 0.1, "door", idx=0)]
        matched = match_openings_to_walls(walls, openings)
        unmatched = get_unmatched_openings(openings, matched)
        assert unmatched == []
