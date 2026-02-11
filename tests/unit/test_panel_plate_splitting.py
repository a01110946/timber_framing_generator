# File: tests/unit/test_panel_plate_splitting.py
"""Tests for panel-aware plate splitting and panel_id on FramingElementData.

Validates:
1. compute_effective_segment_bounds() helper logic
2. panel_id field on FramingElementData serialization round-trip
"""

import json
import sys
import os
import pytest
from dataclasses import asdict

# Ensure project root is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Import the helper directly from the GH script module
import importlib.util

_GH_SCRIPT_PATH = os.path.join(_PROJECT_ROOT, "scripts", "gh_framing_generator.py")


def _load_compute_effective_segment_bounds():
    """Load compute_effective_segment_bounds from gh_framing_generator.py
    without executing Grasshopper-dependent code.

    We parse the source and exec just the function definition.
    """
    with open(_GH_SCRIPT_PATH, "r", encoding="utf-8") as f:
        source = f.read()

    # Extract the function definition
    func_start = source.index("def compute_effective_segment_bounds(")
    # Find the next top-level def or class after it
    rest = source[func_start:]
    lines = rest.split("\n")
    func_lines = [lines[0]]
    for line in lines[1:]:
        # Stop at next top-level definition (not indented)
        if line and not line[0].isspace() and (line.startswith("def ") or line.startswith("class ")):
            break
        func_lines.append(line)

    func_source = "\n".join(func_lines)
    namespace = {}
    exec(func_source, namespace)
    return namespace["compute_effective_segment_bounds"]


compute_effective_segment_bounds = _load_compute_effective_segment_bounds()


# Import json_schemas for panel_id serialization tests
from src.timber_framing_generator.core.json_schemas import (
    FramingElementData,
    FramingResults,
    ProfileData,
    Point3D,
    Vector3D,
    serialize_framing_results,
    deserialize_framing_results,
    FramingJSONEncoder,
)


# =============================================================================
# Tests: compute_effective_segment_bounds
# =============================================================================


class TestComputeEffectiveSegmentBounds:
    """Tests for the panel-aware bounds computation helper."""

    def test_panel_mode_uses_panel_bounds(self):
        """3 panels on a 20ft wall — each gets its own bounds."""
        wall_length = 20.0
        seg_start = -0.146  # junction extension at start
        seg_end = 20.146    # junction extension at end

        # Panel 1: first panel (0→8)
        result = compute_effective_segment_bounds(
            panel_start=0.0, panel_end=8.0,
            seg_start=seg_start, seg_end=seg_end,
            wall_length=wall_length,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(seg_start)  # inherits junction
        assert eff_end == pytest.approx(8.0)           # panel edge

        # Panel 2: middle panel (8→14)
        result = compute_effective_segment_bounds(
            panel_start=8.0, panel_end=14.0,
            seg_start=seg_start, seg_end=seg_end,
            wall_length=wall_length,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(8.0)   # panel edge
        assert eff_end == pytest.approx(14.0)     # panel edge

        # Panel 3: last panel (14→20)
        result = compute_effective_segment_bounds(
            panel_start=14.0, panel_end=20.0,
            seg_start=seg_start, seg_end=seg_end,
            wall_length=wall_length,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(14.0)       # panel edge
        assert eff_end == pytest.approx(seg_end)       # inherits junction

    def test_first_panel_inherits_junction_extension(self):
        """First panel (panel_start=0) inherits negative seg_start."""
        result = compute_effective_segment_bounds(
            panel_start=0.0, panel_end=8.0,
            seg_start=-0.146, seg_end=20.146,
            wall_length=20.0,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(-0.146)
        assert eff_end == pytest.approx(8.0)

    def test_last_panel_inherits_junction_extension(self):
        """Last panel (panel_end=wall_length) inherits extended seg_end."""
        result = compute_effective_segment_bounds(
            panel_start=14.0, panel_end=20.0,
            seg_start=-0.146, seg_end=20.146,
            wall_length=20.0,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(14.0)
        assert eff_end == pytest.approx(20.146)

    def test_middle_panel_no_junction_extension(self):
        """Middle panel gets exact panel bounds, no junction adjustment."""
        result = compute_effective_segment_bounds(
            panel_start=8.0, panel_end=14.0,
            seg_start=-0.146, seg_end=20.146,
            wall_length=20.0,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(8.0)
        assert eff_end == pytest.approx(14.0)

    def test_segment_only_mode_no_panels(self):
        """Without panel bounds, falls back to raw segment bounds."""
        result = compute_effective_segment_bounds(
            panel_start=None, panel_end=None,
            seg_start=-0.146, seg_end=20.146,
            wall_length=20.0,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(-0.146)
        assert eff_end == pytest.approx(20.146)

    def test_no_bounds_returns_none(self):
        """No panel or segment bounds returns None (no injection)."""
        result = compute_effective_segment_bounds(
            panel_start=None, panel_end=None,
            seg_start=None, seg_end=None,
            wall_length=20.0,
        )
        assert result is None

    def test_panel_without_segment_bounds(self):
        """Panel mode with no segment metadata uses plain panel bounds."""
        result = compute_effective_segment_bounds(
            panel_start=4.0, panel_end=12.0,
            seg_start=None, seg_end=None,
            wall_length=20.0,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(4.0)
        assert eff_end == pytest.approx(12.0)

    def test_single_panel_inherits_both_junctions(self):
        """Single panel spanning full wall inherits both junction extensions."""
        result = compute_effective_segment_bounds(
            panel_start=0.0, panel_end=10.0,
            seg_start=-0.125, seg_end=10.125,
            wall_length=10.0,
        )
        assert result is not None
        eff_start, eff_end = result
        assert eff_start == pytest.approx(-0.125)
        assert eff_end == pytest.approx(10.125)


# =============================================================================
# Tests: panel_id on FramingElementData
# =============================================================================


class TestPanelIdOnFramingElementData:
    """Tests for panel_id field on FramingElementData."""

    def _make_element(self, panel_id: str = None) -> FramingElementData:
        """Create a minimal FramingElementData for testing."""
        return FramingElementData(
            id="elem_001",
            element_type="stud",
            profile=ProfileData(
                name="2x4", width=0.125, depth=0.292,
                material_system="timber",
            ),
            centerline_start=Point3D(0.0, 0.0, 0.0),
            centerline_end=Point3D(0.0, 0.0, 8.0),
            u_coord=1.333,
            v_start=0.0,
            v_end=8.0,
            cell_id="cell_wbc_001",
            panel_id=panel_id,
        )

    def test_panel_id_default_none(self):
        """panel_id defaults to None when not specified."""
        elem = self._make_element()
        assert elem.panel_id is None

    def test_panel_id_set(self):
        """panel_id can be set explicitly."""
        elem = self._make_element(panel_id="W1_P1")
        assert elem.panel_id == "W1_P1"

    def test_panel_id_serialization_roundtrip(self):
        """panel_id survives JSON serialization and deserialization."""
        elem = self._make_element(panel_id="W1_P2")
        results = FramingResults(
            wall_id="wall_001",
            material_system="timber",
            elements=[elem],
            element_counts={"stud": 1},
        )

        json_str = serialize_framing_results(results)
        restored = deserialize_framing_results(json_str)

        assert len(restored.elements) == 1
        assert restored.elements[0].panel_id == "W1_P2"

    def test_panel_id_none_serialization_roundtrip(self):
        """panel_id=None serializes as null and deserializes back to None."""
        elem = self._make_element(panel_id=None)
        results = FramingResults(
            wall_id="wall_001",
            material_system="timber",
            elements=[elem],
        )

        json_str = serialize_framing_results(results)
        restored = deserialize_framing_results(json_str)

        assert restored.elements[0].panel_id is None

    def test_panel_id_in_json_output(self):
        """panel_id appears as a key in the serialized JSON."""
        elem = self._make_element(panel_id="W3_P1")
        data = asdict(elem)
        assert "panel_id" in data
        assert data["panel_id"] == "W3_P1"
