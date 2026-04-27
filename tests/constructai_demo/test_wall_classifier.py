# File: tests/constructai_demo/test_wall_classifier.py
"""Tests for wall thickness classification."""

import pytest

from src.constructai_demo.coordinate_converter import ConvertedPoint, ConvertedWall
from src.constructai_demo.wall_classifier import (
    EXTERIOR_2X6_THRESHOLD_M,
    INTERIOR_THRESHOLD_M,
    WallClass,
    classify_wall,
    classify_walls,
    get_classification_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_converted_wall(thickness_m: float, idx: int = 0) -> ConvertedWall:
    return ConvertedWall(
        p1=ConvertedPoint(0.0, 0.0),
        p2=ConvertedPoint(10.0, 0.0),
        length_ft=10.0,
        thickness_ft=thickness_m * 3.28084,
        thickness_m=thickness_m,
        original_index=idx,
    )


# ---------------------------------------------------------------------------
# Single wall classification
# ---------------------------------------------------------------------------

class TestClassifyWall:
    def test_thin_wall_is_interior_2x4(self):
        """Typical interior wall ~3.5" = 0.089m -> interior 2x4."""
        assert classify_wall(0.089) == WallClass.INTERIOR_2X4

    def test_medium_wall_is_exterior_2x4(self):
        """Typical exterior wall ~4.7" = 0.120m -> exterior 2x4."""
        assert classify_wall(0.120) == WallClass.EXTERIOR_2X4

    def test_thick_wall_is_exterior_2x6(self):
        """Garage front wall ~6" = 0.153m -> exterior 2x6."""
        assert classify_wall(0.153) == WallClass.EXTERIOR_2X6

    def test_interior_threshold_exact(self):
        """At exactly 0.115m -> exterior 2x4 (at threshold = exterior)."""
        assert classify_wall(INTERIOR_THRESHOLD_M) == WallClass.EXTERIOR_2X4

    def test_just_below_interior_threshold(self):
        """Just below 0.115m -> interior 2x4."""
        assert classify_wall(0.1149) == WallClass.INTERIOR_2X4

    def test_exterior_2x6_threshold_exact(self):
        """At exactly 0.14m -> exterior 2x6."""
        assert classify_wall(EXTERIOR_2X6_THRESHOLD_M) == WallClass.EXTERIOR_2X6

    def test_just_below_exterior_2x6_threshold(self):
        """Just below 0.14m -> exterior 2x4."""
        assert classify_wall(0.1399) == WallClass.EXTERIOR_2X4

    def test_very_thin_wall(self):
        """Thinnest from data: 0.078m -> interior 2x4."""
        assert classify_wall(0.078) == WallClass.INTERIOR_2X4

    def test_very_thick_wall(self):
        """Thickest from data: 0.208m -> exterior 2x6."""
        assert classify_wall(0.208) == WallClass.EXTERIOR_2X6


# ---------------------------------------------------------------------------
# Batch classification
# ---------------------------------------------------------------------------

class TestClassifyWalls:
    def test_mixed_walls(self):
        walls = [
            _make_converted_wall(0.089, idx=0),  # interior 2x4
            _make_converted_wall(0.120, idx=1),  # exterior 2x4
            _make_converted_wall(0.153, idx=2),  # exterior 2x6
            _make_converted_wall(0.100, idx=3),  # interior 2x4
        ]
        classified = classify_walls(walls)
        assert len(classified) == 4
        assert classified[0][1] == WallClass.INTERIOR_2X4
        assert classified[1][1] == WallClass.EXTERIOR_2X4
        assert classified[2][1] == WallClass.EXTERIOR_2X6
        assert classified[3][1] == WallClass.INTERIOR_2X4

    def test_empty_list(self):
        assert classify_walls([]) == []


class TestClassificationSummary:
    def test_summary_counts(self):
        walls = [
            _make_converted_wall(0.089, idx=0),  # interior 2x4
            _make_converted_wall(0.089, idx=1),  # interior 2x4
            _make_converted_wall(0.120, idx=2),  # exterior 2x4
            _make_converted_wall(0.153, idx=3),  # exterior 2x6
        ]
        summary = get_classification_summary(walls)
        assert summary["interior_2x4"] == 2
        assert summary["exterior_2x4"] == 1
        assert summary["exterior_2x6"] == 1
