# File: tests/panels/test_corner_handler.py
"""Unit tests for corner handler."""

import pytest
from src.timber_framing_generator.panels.corner_handler import (
    detect_wall_corners,
    calculate_corner_adjustments,
    apply_corner_adjustments,
    get_adjusted_wall_length,
    WallCornerInfo,
)


def create_mock_wall(
    wall_id: str,
    start: tuple,
    end: tuple,
    thickness: float = 0.5,
) -> dict:
    """Create a mock wall data dictionary."""
    length = ((end[0] - start[0])**2 + (end[1] - start[1])**2)**0.5

    # Calculate direction
    if length > 0:
        dx = (end[0] - start[0]) / length
        dy = (end[1] - start[1]) / length
    else:
        dx, dy = 1.0, 0.0

    return {
        "wall_id": wall_id,
        "wall_length": length,
        "wall_thickness": thickness,
        "base_curve_start": {"x": start[0], "y": start[1], "z": start[2]},
        "base_curve_end": {"x": end[0], "y": end[1], "z": end[2]},
        "base_plane": {
            "origin": {"x": start[0], "y": start[1], "z": start[2]},
            "x_axis": {"x": dx, "y": dy, "z": 0},
            "y_axis": {"x": 0, "y": 0, "z": 1},
            "z_axis": {"x": -dy, "y": dx, "z": 0},
        },
    }


class TestDetectWallCorners:
    """Tests for detect_wall_corners function."""

    def test_two_walls_corner(self):
        """Test detection of corner between two walls."""
        # Two walls meeting at origin
        wall_a = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        wall_b = create_mock_wall("wall_b", (0, 0, 0), (0, 10, 0))

        corners = detect_wall_corners([wall_a, wall_b])

        # Should find 2 corner infos (one for each wall at the corner)
        assert len(corners) == 2

        wall_ids = {c.wall_id for c in corners}
        assert wall_ids == {"wall_a", "wall_b"}

    def test_l_shaped_walls(self):
        """Test L-shaped walls (end to start connection)."""
        wall_a = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        wall_b = create_mock_wall("wall_b", (10, 0, 0), (10, 10, 0))

        corners = detect_wall_corners([wall_a, wall_b])

        assert len(corners) == 2

        # Check positions
        for corner in corners:
            if corner.wall_id == "wall_a":
                assert corner.corner_position == "end"
            else:
                assert corner.corner_position == "start"

    def test_no_corners(self):
        """Test walls that don't meet."""
        wall_a = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        wall_b = create_mock_wall("wall_b", (20, 0, 0), (30, 0, 0))

        corners = detect_wall_corners([wall_a, wall_b])

        assert len(corners) == 0

    def test_tolerance(self):
        """Test corner detection with tolerance."""
        wall_a = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        wall_b = create_mock_wall("wall_b", (10.05, 0, 0), (10.05, 10, 0))

        # Should not find with default tolerance
        corners = detect_wall_corners([wall_a, wall_b], tolerance=0.01)
        assert len(corners) == 0

        # Should find with larger tolerance
        corners = detect_wall_corners([wall_a, wall_b], tolerance=0.1)
        assert len(corners) == 2


class TestCalculateCornerAdjustments:
    """Tests for calculate_corner_adjustments function."""

    def test_longer_wall_extends(self):
        """Test that longer wall extends at corner."""
        # Wall A is longer (20 ft vs 10 ft)
        wall_a = create_mock_wall("wall_a", (0, 0, 0), (20, 0, 0), thickness=0.5)
        wall_b = create_mock_wall("wall_b", (0, 0, 0), (0, 10, 0), thickness=0.5)

        corners = detect_wall_corners([wall_a, wall_b])
        adjustments = calculate_corner_adjustments(corners, "longer_wall")

        # Find adjustments for each wall
        a_adj = next(a for a in adjustments if a["wall_id"] == "wall_a")
        b_adj = next(a for a in adjustments if a["wall_id"] == "wall_b")

        # Longer wall (A) should extend
        assert a_adj["adjustment_type"] == "extend"
        # Shorter wall (B) should recede
        assert b_adj["adjustment_type"] == "recede"

    def test_adjustment_amount(self):
        """Test that adjustment amount is half the connecting wall thickness."""
        wall_a = create_mock_wall("wall_a", (0, 0, 0), (20, 0, 0), thickness=0.5)
        wall_b = create_mock_wall("wall_b", (0, 0, 0), (0, 10, 0), thickness=0.6)

        corners = detect_wall_corners([wall_a, wall_b])
        adjustments = calculate_corner_adjustments(corners, "longer_wall")

        a_adj = next(a for a in adjustments if a["wall_id"] == "wall_a")
        b_adj = next(a for a in adjustments if a["wall_id"] == "wall_b")

        # A extends by B's half-thickness
        assert a_adj["adjustment_amount"] == 0.3  # 0.6 / 2

        # B recedes by A's half-thickness
        assert b_adj["adjustment_amount"] == 0.25  # 0.5 / 2


class TestApplyCornerAdjustments:
    """Tests for apply_corner_adjustments function."""

    def test_extend_end(self):
        """Test extending wall at end."""
        wall = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        adjustments = [{
            "wall_id": "wall_a",
            "corner_type": "end",
            "adjustment_type": "extend",
            "adjustment_amount": 0.25,
            "connecting_wall_id": "wall_b",
            "connecting_wall_thickness": 0.5,
        }]

        adjusted = apply_corner_adjustments(wall, adjustments)

        assert adjusted["wall_length"] == 10.25  # Extended by 0.25

    def test_recede_start(self):
        """Test receding wall at start."""
        wall = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        adjustments = [{
            "wall_id": "wall_a",
            "corner_type": "start",
            "adjustment_type": "recede",
            "adjustment_amount": 0.25,
            "connecting_wall_id": "wall_b",
            "connecting_wall_thickness": 0.5,
        }]

        adjusted = apply_corner_adjustments(wall, adjustments)

        assert adjusted["wall_length"] == 9.75  # Receded by 0.25
        # Start point should have moved forward
        assert adjusted["base_curve_start"]["x"] == 0.25

    def test_multiple_adjustments(self):
        """Test applying adjustments at both ends."""
        wall = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        adjustments = [
            {
                "wall_id": "wall_a",
                "corner_type": "start",
                "adjustment_type": "extend",
                "adjustment_amount": 0.25,
                "connecting_wall_id": "wall_b",
                "connecting_wall_thickness": 0.5,
            },
            {
                "wall_id": "wall_a",
                "corner_type": "end",
                "adjustment_type": "recede",
                "adjustment_amount": 0.3,
                "connecting_wall_id": "wall_c",
                "connecting_wall_thickness": 0.6,
            },
        ]

        adjusted = apply_corner_adjustments(wall, adjustments)

        # Extend start: +0.25 to length
        # Recede end: -0.3 to length
        # Net: 10 + 0.25 - 0.3 = 9.95
        assert abs(adjusted["wall_length"] - 9.95) < 0.001


class TestGetAdjustedWallLength:
    """Tests for get_adjusted_wall_length function."""

    def test_no_adjustments(self):
        """Test with no adjustments."""
        wall = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        length = get_adjusted_wall_length(wall, [])
        assert length == 10.0

    def test_with_extend(self):
        """Test with extend adjustment."""
        wall = create_mock_wall("wall_a", (0, 0, 0), (10, 0, 0))
        adjustments = [{
            "wall_id": "wall_a",
            "corner_type": "end",
            "adjustment_type": "extend",
            "adjustment_amount": 0.5,
            "connecting_wall_id": "wall_b",
            "connecting_wall_thickness": 1.0,
        }]
        length = get_adjusted_wall_length(wall, adjustments)
        assert length == 10.5
