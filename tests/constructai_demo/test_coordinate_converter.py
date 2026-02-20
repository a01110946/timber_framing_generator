# File: tests/constructai_demo/test_coordinate_converter.py
"""Tests for coordinate conversion (pixel -> meters -> feet)."""

import math

import pytest

from src.constructai_demo.coordinate_converter import (
    METERS_TO_FEET,
    ConvertedElements,
    ConvertedPoint,
    compute_scale,
    convert_all_elements,
    convert_point,
    find_max_y,
)
from src.constructai_demo.kreo_parser import KreoOpening, KreoPoint, KreoWall


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_wall(p1_x, p1_y, p2_x, p2_y, length_m, thickness_m=0.1, idx=0):
    """Create a KreoWall for testing."""
    return KreoWall(
        p1=KreoPoint(p1_x, p1_y),
        p2=KreoPoint(p2_x, p2_y),
        length=length_m,
        thickness=thickness_m,
        index=idx,
    )


def _make_opening(p1_x, p1_y, p2_x, p2_y, length_m, opening_type="door", idx=0):
    return KreoOpening(
        p1=KreoPoint(p1_x, p1_y),
        p2=KreoPoint(p2_x, p2_y),
        length=length_m,
        thickness=0.1,
        opening_type=opening_type,
        index=idx,
    )


# ---------------------------------------------------------------------------
# Scale computation tests
# ---------------------------------------------------------------------------

class TestComputeScale:
    def test_known_scale(self):
        """Vertical wall: 447.17 px tall, 7.572 m long -> ~0.01693 m/px."""
        wall = _make_wall(545.13, 815.82, 545.13, 1262.99, 7.572)
        scale = compute_scale([wall])
        assert pytest.approx(scale, rel=1e-3) == 0.01693

    def test_multiple_walls_average(self):
        """Scale should be averaged across walls."""
        w1 = _make_wall(0, 0, 100, 0, 1.6933)  # scale = 0.016933
        w2 = _make_wall(0, 0, 0, 200, 3.3866)  # scale = 0.016933
        scale = compute_scale([w1, w2])
        assert pytest.approx(scale, rel=1e-4) == 0.016933

    def test_empty_walls_raises(self):
        with pytest.raises(ValueError, match="empty wall list"):
            compute_scale([])

    def test_zero_length_wall_skipped(self):
        """Wall with same p1/p2 should be skipped, not cause div by zero."""
        w1 = _make_wall(100, 100, 100, 100, 0.0, idx=0)  # zero pixel distance
        w2 = _make_wall(0, 0, 100, 0, 1.6933, idx=1)
        scale = compute_scale([w1, w2])
        assert pytest.approx(scale, rel=1e-3) == 0.016933


# ---------------------------------------------------------------------------
# Max Y tests
# ---------------------------------------------------------------------------

class TestFindMaxY:
    def test_walls_only(self):
        walls = [_make_wall(0, 100, 50, 200, 1.0)]
        assert find_max_y(walls) == 200.0

    def test_with_openings(self):
        walls = [_make_wall(0, 0, 0, 100, 1.0)]
        doors = [_make_opening(0, 150, 10, 150, 0.5)]
        windows = [_make_opening(0, 0, 0, 250, 0.5, "window")]
        assert find_max_y(walls, doors, windows) == 250.0


# ---------------------------------------------------------------------------
# Point conversion tests
# ---------------------------------------------------------------------------

class TestConvertPoint:
    def test_origin_bottom_left(self):
        """Point at top-left pixel (0, max_y) should map to (0, 0) in feet."""
        scale = 0.016933
        max_y = 1000.0
        pt = convert_point(0, max_y, scale, max_y)
        assert pytest.approx(pt.x, abs=0.01) == 0.0
        assert pytest.approx(pt.y, abs=0.01) == 0.0

    def test_y_flip(self):
        """Point at pixel (0, 0) should map to max_y * scale * 3.28084 in feet."""
        scale = 0.016933
        max_y = 1000.0
        pt = convert_point(0, 0, scale, max_y)
        expected_y_ft = max_y * scale * METERS_TO_FEET
        assert pytest.approx(pt.y, abs=0.1) == expected_y_ft

    def test_known_conversion(self):
        """Known pixel -> expected feet."""
        scale = 0.016933  # m/px
        max_y_px = 1300.0
        # Pixel (500, 800) -> meters: x=8.4665, y=(1300-800)*0.016933=8.4665
        # -> feet: 8.4665 * 3.28084 = 27.77 ft
        pt = convert_point(500, 800, scale, max_y_px)
        expected_x = 500 * scale * METERS_TO_FEET
        expected_y = (1300 - 800) * scale * METERS_TO_FEET
        assert pytest.approx(pt.x, abs=0.01) == expected_x
        assert pytest.approx(pt.y, abs=0.01) == expected_y


# ---------------------------------------------------------------------------
# Full conversion tests
# ---------------------------------------------------------------------------

class TestConvertAllElements:
    def test_walls_converted(self):
        walls = [_make_wall(0, 0, 100, 0, 1.6933, 0.1)]
        result = convert_all_elements(walls)
        assert len(result.walls) == 1
        assert result.scale_m_per_px > 0

    def test_wall_length_in_feet(self):
        walls = [_make_wall(0, 0, 100, 0, 1.6933, 0.1)]
        result = convert_all_elements(walls)
        expected_ft = 1.6933 * METERS_TO_FEET
        assert pytest.approx(result.walls[0].length_ft, abs=0.01) == expected_ft

    def test_preserves_thickness_m(self):
        walls = [_make_wall(0, 0, 100, 0, 1.6933, 0.089)]
        result = convert_all_elements(walls)
        assert result.walls[0].thickness_m == 0.089

    def test_doors_and_windows(self):
        walls = [_make_wall(0, 0, 100, 0, 1.6933)]
        doors = [_make_opening(50, 0, 60, 0, 0.169)]
        windows = [_make_opening(70, 0, 80, 0, 0.169, "window")]
        result = convert_all_elements(walls, doors, windows)
        assert len(result.doors) == 1
        assert len(result.windows) == 1
        assert result.doors[0].opening_type == "door"
        assert result.windows[0].opening_type == "window"

    def test_original_index_preserved(self):
        walls = [
            _make_wall(0, 0, 100, 0, 1.6933, idx=0),
            _make_wall(0, 0, 0, 100, 1.6933, idx=1),
        ]
        result = convert_all_elements(walls)
        assert result.walls[0].original_index == 0
        assert result.walls[1].original_index == 1
