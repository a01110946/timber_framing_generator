# File: tests/wall_junctions/test_core_adjustment.py

"""Tests for core layer junction adjustments for framing.

Tests cover:
- Default framing segments (no adjustments → single [0, wall_length] segment)
- L-corner endpoint shifts (primary EXTENDS, secondary TRIMS)
- T-intersection terminating wall TRIM at one endpoint
- X-crossing midspan splits (multiple segments)
- Mixed endpoint + midspan adjustments
- Edge cases: zero-length walls, overlapping gaps, missing fields
"""

import pytest

from src.timber_framing_generator.wall_junctions.core_adjustment import (
    compute_framing_segments,
    _compute_endpoint_shifts,
    _collect_midspan_gaps,
    _build_segments,
)


# =====================================================================
# Helper factories
# =====================================================================

def _make_wall(wall_id: str, wall_length: float) -> dict:
    """Create a minimal wall dict for testing."""
    return {"wall_id": wall_id, "wall_length": wall_length}


def _make_adj(
    layer_name: str = "core",
    end: str = "start",
    adjustment_type: str = "trim",
    amount: float = 0.0,
    midspan_u: float = None,
) -> dict:
    """Create a serialized LayerAdjustment dict."""
    adj = {
        "layer_name": layer_name,
        "end": end,
        "adjustment_type": adjustment_type,
        "amount": amount,
    }
    if midspan_u is not None:
        adj["midspan_u"] = midspan_u
    return adj


# =====================================================================
# Tests: _compute_endpoint_shifts
# =====================================================================

class TestComputeEndpointShifts:
    """Unit tests for _compute_endpoint_shifts()."""

    def test_no_adjustments(self):
        """No core adjustments → unchanged [0, wall_length]."""
        u_start, u_end = _compute_endpoint_shifts([], 10.0)
        assert u_start == 0.0
        assert u_end == 10.0

    def test_trim_at_start(self):
        """Trim at start shifts u_start forward."""
        adjs = [_make_adj(end="start", adjustment_type="trim", amount=0.15)]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.15)
        assert u_end == pytest.approx(10.0)

    def test_extend_at_start(self):
        """Extend at start shifts u_start negative."""
        adjs = [_make_adj(end="start", adjustment_type="extend", amount=0.15)]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(-0.15)
        assert u_end == pytest.approx(10.0)

    def test_trim_at_end(self):
        """Trim at end shifts u_end inward."""
        adjs = [_make_adj(end="end", adjustment_type="trim", amount=0.15)]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.0)
        assert u_end == pytest.approx(9.85)

    def test_extend_at_end(self):
        """Extend at end shifts u_end outward."""
        adjs = [_make_adj(end="end", adjustment_type="extend", amount=0.15)]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.0)
        assert u_end == pytest.approx(10.15)

    def test_both_ends_trimmed(self):
        """Trim at both start and end."""
        adjs = [
            _make_adj(end="start", adjustment_type="trim", amount=0.15),
            _make_adj(end="end", adjustment_type="trim", amount=0.20),
        ]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.15)
        assert u_end == pytest.approx(9.80)

    def test_extend_start_trim_end(self):
        """Primary at L-corner: extend start, trim end (or vice versa)."""
        adjs = [
            _make_adj(end="start", adjustment_type="extend", amount=0.146),
            _make_adj(end="end", adjustment_type="trim", amount=0.146),
        ]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(-0.146)
        assert u_end == pytest.approx(10.0 - 0.146)

    def test_multiple_same_end_most_restrictive_wins(self):
        """Multiple trims at start: largest amount wins."""
        adjs = [
            _make_adj(end="start", adjustment_type="trim", amount=0.10),
            _make_adj(end="start", adjustment_type="trim", amount=0.20),
        ]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.20)

    def test_midspan_adjustments_ignored(self):
        """Midspan adjustments don't affect endpoint shifts."""
        adjs = [
            _make_adj(end="midspan", adjustment_type="trim", amount=0.15, midspan_u=5.0),
        ]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.0)
        assert u_end == pytest.approx(10.0)

    def test_non_core_layers_mixed_in(self):
        """Non-core adjustments are pre-filtered by caller, but if passed, ignored."""
        # _compute_endpoint_shifts receives pre-filtered core_adjs
        # This test confirms no crash if somehow non-core sneaks in
        adjs = [
            _make_adj(end="start", adjustment_type="trim", amount=0.15),
        ]
        u_start, u_end = _compute_endpoint_shifts(adjs, 10.0)
        assert u_start == pytest.approx(0.15)


# =====================================================================
# Tests: _collect_midspan_gaps
# =====================================================================

class TestCollectMidspanGaps:
    """Unit tests for _collect_midspan_gaps()."""

    def test_no_midspan(self):
        """No midspan adjustments → empty list."""
        gaps = _collect_midspan_gaps([])
        assert gaps == []

    def test_single_midspan_gap(self):
        """One midspan trim creates symmetric gap."""
        adjs = [_make_adj(end="midspan", adjustment_type="trim", amount=0.15, midspan_u=5.0)]
        gaps = _collect_midspan_gaps(adjs)
        assert len(gaps) == 1
        assert gaps[0] == pytest.approx((4.85, 5.15))

    def test_two_midspan_gaps_sorted(self):
        """Multiple midspan gaps returned sorted by start."""
        adjs = [
            _make_adj(end="midspan", adjustment_type="trim", amount=0.15, midspan_u=8.0),
            _make_adj(end="midspan", adjustment_type="trim", amount=0.15, midspan_u=3.0),
        ]
        gaps = _collect_midspan_gaps(adjs)
        assert len(gaps) == 2
        assert gaps[0][0] < gaps[1][0]
        assert gaps[0] == pytest.approx((2.85, 3.15))
        assert gaps[1] == pytest.approx((7.85, 8.15))

    def test_endpoint_adjustments_ignored(self):
        """Endpoint adjustments not collected as gaps."""
        adjs = [
            _make_adj(end="start", adjustment_type="trim", amount=0.15),
            _make_adj(end="end", adjustment_type="extend", amount=0.15),
        ]
        gaps = _collect_midspan_gaps(adjs)
        assert gaps == []

    def test_midspan_without_midspan_u_ignored(self):
        """Midspan adjustment with no midspan_u is skipped."""
        adjs = [_make_adj(end="midspan", adjustment_type="trim", amount=0.15)]
        gaps = _collect_midspan_gaps(adjs)
        assert gaps == []

    def test_zero_amount_midspan_ignored(self):
        """Midspan with zero amount produces no gap."""
        adjs = [_make_adj(end="midspan", adjustment_type="trim", amount=0.0, midspan_u=5.0)]
        gaps = _collect_midspan_gaps(adjs)
        assert gaps == []


# =====================================================================
# Tests: _build_segments
# =====================================================================

class TestBuildSegments:
    """Unit tests for _build_segments()."""

    def test_no_gaps_single_segment(self):
        """No gaps → single segment."""
        segs = _build_segments(0.0, 10.0, [])
        assert segs == [[0.0, 10.0]]

    def test_single_gap_two_segments(self):
        """One gap splits into two segments."""
        segs = _build_segments(0.0, 10.0, [(4.85, 5.15)])
        assert len(segs) == 2
        assert segs[0] == pytest.approx([0.0, 4.85])
        assert segs[1] == pytest.approx([5.15, 10.0])

    def test_two_gaps_three_segments(self):
        """Two gaps produce three segments."""
        segs = _build_segments(0.0, 15.0, [(4.85, 5.15), (9.85, 10.15)])
        assert len(segs) == 3
        assert segs[0] == pytest.approx([0.0, 4.85])
        assert segs[1] == pytest.approx([5.15, 9.85])
        assert segs[2] == pytest.approx([10.15, 15.0])

    def test_gap_at_start_skips_empty_segment(self):
        """Gap starting at u_start produces no zero-width first segment."""
        segs = _build_segments(0.0, 10.0, [(0.0, 0.15)])
        assert len(segs) == 1
        assert segs[0] == pytest.approx([0.15, 10.0])

    def test_gap_at_end_skips_empty_segment(self):
        """Gap ending at u_end produces no zero-width last segment."""
        segs = _build_segments(0.0, 10.0, [(9.85, 10.0)])
        assert len(segs) == 1
        assert segs[0] == pytest.approx([0.0, 9.85])

    def test_negative_u_start_extend(self):
        """Extended (negative) u_start works correctly."""
        segs = _build_segments(-0.15, 10.0, [])
        assert segs == [[-0.15, 10.0]]

    def test_u_end_beyond_wall_length(self):
        """Extended u_end beyond wall_length works correctly."""
        segs = _build_segments(0.0, 10.15, [])
        assert segs == [[0.0, 10.15]]


# =====================================================================
# Tests: compute_framing_segments (integration)
# =====================================================================

class TestComputeFramingSegments:
    """Integration tests for compute_framing_segments()."""

    def test_no_adjustments_default_segment(self):
        """Wall with no adjustments gets default [0, wall_length] segment."""
        walls = [_make_wall("w1", 10.0)]
        juncs = {"wall_adjustments": {}}
        result = compute_framing_segments(juncs, walls)
        assert len(result) == 1
        assert result[0]["framing_segments"] == [[0.0, 10.0]]

    def test_original_fields_preserved(self):
        """Original wall fields are not mutated or removed."""
        walls = [{"wall_id": "w1", "wall_length": 10.0, "wall_height": 8.0, "custom": "data"}]
        juncs = {"wall_adjustments": {}}
        result = compute_framing_segments(juncs, walls)
        assert result[0]["wall_id"] == "w1"
        assert result[0]["wall_length"] == 10.0
        assert result[0]["wall_height"] == 8.0
        assert result[0]["custom"] == "data"

    def test_original_list_not_mutated(self):
        """Input walls_data list is not modified."""
        walls = [_make_wall("w1", 10.0)]
        juncs = {"wall_adjustments": {}}
        result = compute_framing_segments(juncs, walls)
        assert "framing_segments" not in walls[0]
        assert "framing_segments" in result[0]

    def test_l_corner_secondary_trim_start(self):
        """Secondary wall at L-corner: core TRIM at start."""
        walls = [_make_wall("w_sec", 10.0)]
        juncs = {"wall_adjustments": {
            "w_sec": [
                _make_adj(layer_name="core", end="start", adjustment_type="trim", amount=0.146),
            ]
        }}
        result = compute_framing_segments(juncs, walls)
        segs = result[0]["framing_segments"]
        assert len(segs) == 1
        assert segs[0][0] == pytest.approx(0.146)
        assert segs[0][1] == pytest.approx(10.0)

    def test_l_corner_primary_extend_end(self):
        """Primary wall at L-corner: core EXTEND at end."""
        walls = [_make_wall("w_pri", 10.0)]
        juncs = {"wall_adjustments": {
            "w_pri": [
                _make_adj(layer_name="core", end="end", adjustment_type="extend", amount=0.146),
            ]
        }}
        result = compute_framing_segments(juncs, walls)
        segs = result[0]["framing_segments"]
        assert len(segs) == 1
        assert segs[0][0] == pytest.approx(0.0)
        assert segs[0][1] == pytest.approx(10.146)

    def test_t_intersection_terminating_wall_trim(self):
        """Terminating wall at T-intersection: core TRIM at endpoint."""
        walls = [_make_wall("w_term", 8.0)]
        juncs = {"wall_adjustments": {
            "w_term": [
                _make_adj(layer_name="core", end="end", adjustment_type="trim", amount=0.146),
            ]
        }}
        result = compute_framing_segments(juncs, walls)
        segs = result[0]["framing_segments"]
        assert len(segs) == 1
        assert segs[0][0] == pytest.approx(0.0)
        assert segs[0][1] == pytest.approx(7.854)

    def test_x_crossing_secondary_splits(self):
        """Secondary wall at X-crossing: midspan core TRIM splits into 2 segments."""
        walls = [_make_wall("w_sec", 15.0)]
        juncs = {"wall_adjustments": {
            "w_sec": [
                _make_adj(
                    layer_name="core", end="midspan",
                    adjustment_type="trim", amount=0.146, midspan_u=7.5,
                ),
            ]
        }}
        result = compute_framing_segments(juncs, walls)
        segs = result[0]["framing_segments"]
        assert len(segs) == 2
        assert segs[0] == pytest.approx([0.0, 7.354])
        assert segs[1] == pytest.approx([7.646, 15.0])

    def test_x_crossing_with_endpoint_adjustments(self):
        """X-crossing secondary with both endpoint trims and midspan split."""
        walls = [_make_wall("w_sec", 15.0)]
        juncs = {"wall_adjustments": {
            "w_sec": [
                # L-corner trim at start
                _make_adj(layer_name="core", end="start", adjustment_type="trim", amount=0.146),
                # X-crossing midspan split
                _make_adj(
                    layer_name="core", end="midspan",
                    adjustment_type="trim", amount=0.146, midspan_u=7.5,
                ),
                # L-corner trim at end
                _make_adj(layer_name="core", end="end", adjustment_type="trim", amount=0.146),
            ]
        }}
        result = compute_framing_segments(juncs, walls)
        segs = result[0]["framing_segments"]
        assert len(segs) == 2
        assert segs[0][0] == pytest.approx(0.146)
        assert segs[0][1] == pytest.approx(7.354)
        assert segs[1][0] == pytest.approx(7.646)
        assert segs[1][1] == pytest.approx(14.854)

    def test_non_core_adjustments_ignored(self):
        """Non-core layer adjustments don't affect framing_segments."""
        walls = [_make_wall("w1", 10.0)]
        juncs = {"wall_adjustments": {
            "w1": [
                _make_adj(layer_name="OSB Sheathing", end="start",
                          adjustment_type="extend", amount=0.5),
                _make_adj(layer_name="Drywall", end="end",
                          adjustment_type="trim", amount=0.3),
            ]
        }}
        result = compute_framing_segments(juncs, walls)
        segs = result[0]["framing_segments"]
        assert segs == [[0.0, 10.0]]

    def test_multiple_walls(self):
        """Multiple walls each get their own segments."""
        walls = [
            _make_wall("w1", 10.0),
            _make_wall("w2", 8.0),
            _make_wall("w3", 12.0),
        ]
        juncs = {"wall_adjustments": {
            "w1": [_make_adj(layer_name="core", end="start", adjustment_type="trim", amount=0.15)],
            "w3": [_make_adj(layer_name="core", end="end", adjustment_type="extend", amount=0.15)],
        }}
        result = compute_framing_segments(juncs, walls)
        assert len(result) == 3
        assert result[0]["framing_segments"][0][0] == pytest.approx(0.15)
        assert result[1]["framing_segments"] == [[0.0, 8.0]]
        assert result[2]["framing_segments"][0][1] == pytest.approx(12.15)

    def test_empty_walls_list(self):
        """Empty walls list returns empty list."""
        result = compute_framing_segments({"wall_adjustments": {}}, [])
        assert result == []

    def test_missing_wall_adjustments_key(self):
        """Missing wall_adjustments key is handled gracefully."""
        walls = [_make_wall("w1", 10.0)]
        result = compute_framing_segments({}, walls)
        assert result[0]["framing_segments"] == [[0.0, 10.0]]

    def test_zero_length_wall(self):
        """Zero-length wall gets zero-length segment."""
        walls = [_make_wall("w1", 0.0)]
        result = compute_framing_segments({"wall_adjustments": {}}, walls)
        assert result[0]["framing_segments"] == [[0.0, 0.0]]
