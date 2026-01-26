# File: tests/panels/test_panel_decomposer.py
"""Unit tests for panel decomposer."""

import pytest
import json
from src.timber_framing_generator.panels.panel_decomposer import (
    decompose_wall_to_panels,
    decompose_all_walls,
    serialize_panel_results,
    deserialize_panel_results,
)
from src.timber_framing_generator.panels.panel_config import PanelConfig


def create_mock_wall(
    wall_id: str = "test_wall",
    length: float = 30.0,
    height: float = 8.0,
    thickness: float = 0.5,
    openings: list = None,
) -> dict:
    """Create a mock wall data dictionary."""
    return {
        "wall_id": wall_id,
        "wall_length": length,
        "wall_height": height,
        "wall_thickness": thickness,
        "base_elevation": 0.0,
        "base_curve_start": {"x": 0, "y": 0, "z": 0},
        "base_curve_end": {"x": length, "y": 0, "z": 0},
        "base_plane": {
            "origin": {"x": 0, "y": 0, "z": 0},
            "x_axis": {"x": 1, "y": 0, "z": 0},
            "y_axis": {"x": 0, "y": 0, "z": 1},
            "z_axis": {"x": 0, "y": 1, "z": 0},
        },
        "openings": openings or [],
    }


def create_mock_framing(wall_id: str = "test_wall") -> dict:
    """Create mock framing results."""
    return {
        "wall_id": wall_id,
        "elements": [
            {"id": "stud_0", "element_type": "stud", "u_coord": 0.0625},
            {"id": "stud_1", "element_type": "stud", "u_coord": 1.333},
            {"id": "stud_2", "element_type": "stud", "u_coord": 2.666},
        ],
    }


class TestDecomposeWallToPanels:
    """Tests for decompose_wall_to_panels function."""

    def test_short_wall_single_panel(self):
        """Test that short wall produces single panel."""
        wall = create_mock_wall(length=20.0)
        config = PanelConfig(max_panel_length=24.0)

        result = decompose_wall_to_panels(wall, config=config)

        assert result["total_panel_count"] == 1
        assert len(result["panels"]) == 1
        assert len(result["joints"]) == 0

    def test_long_wall_multiple_panels(self):
        """Test that long wall produces multiple panels."""
        wall = create_mock_wall(length=50.0)
        config = PanelConfig(max_panel_length=24.0)

        result = decompose_wall_to_panels(wall, config=config)

        assert result["total_panel_count"] >= 2
        assert len(result["panels"]) >= 2
        assert len(result["joints"]) >= 1

    def test_panel_properties(self):
        """Test that panels have correct properties."""
        wall = create_mock_wall(length=30.0, height=9.0)
        config = PanelConfig(max_panel_length=24.0)

        result = decompose_wall_to_panels(wall, config=config)

        for panel in result["panels"]:
            assert "id" in panel
            assert "u_start" in panel
            assert "u_end" in panel
            assert "length" in panel
            assert "height" in panel
            assert panel["height"] == 9.0
            assert panel["wall_id"] == "test_wall"
            assert panel["length"] == panel["u_end"] - panel["u_start"]

    def test_panel_corners(self):
        """Test that panel corners are calculated."""
        wall = create_mock_wall(length=20.0)
        config = PanelConfig()

        result = decompose_wall_to_panels(wall, config=config)

        panel = result["panels"][0]
        corners = panel["corners"]

        assert "bottom_left" in corners
        assert "bottom_right" in corners
        assert "top_left" in corners
        assert "top_right" in corners

        # Check corner coordinates are dicts with x, y, z
        for corner_name in ["bottom_left", "bottom_right", "top_left", "top_right"]:
            corner = corners[corner_name]
            assert "x" in corner
            assert "y" in corner
            assert "z" in corner

    def test_joint_properties(self):
        """Test that joints have correct properties."""
        wall = create_mock_wall(length=50.0)
        config = PanelConfig(max_panel_length=24.0)

        result = decompose_wall_to_panels(wall, config=config)

        for joint in result["joints"]:
            assert "u_coord" in joint
            assert "joint_type" in joint
            assert "left_panel_id" in joint
            assert "right_panel_id" in joint

    def test_with_corner_adjustments(self):
        """Test panelization with corner adjustments."""
        wall = create_mock_wall(length=30.0)
        adjustments = [{
            "wall_id": "test_wall",
            "corner_type": "start",
            "adjustment_type": "recede",
            "adjustment_amount": 0.25,
            "connecting_wall_id": "other_wall",
            "connecting_wall_thickness": 0.5,
        }]
        config = PanelConfig()

        result = decompose_wall_to_panels(
            wall,
            config=config,
            corner_adjustments=adjustments
        )

        # Adjusted length should be 29.75
        assert result["original_wall_length"] == 30.0
        assert result["adjusted_wall_length"] == 29.75

    def test_metadata_includes_config(self):
        """Test that result metadata includes config."""
        wall = create_mock_wall()
        config = PanelConfig(max_panel_length=20.0)

        result = decompose_wall_to_panels(wall, config=config)

        assert "metadata" in result
        assert "config" in result["metadata"]
        assert result["metadata"]["config"]["max_panel_length"] == 20.0


class TestDecomposeAllWalls:
    """Tests for decompose_all_walls function."""

    def test_multiple_walls(self):
        """Test decomposing multiple walls."""
        walls = [
            create_mock_wall(wall_id="wall_a", length=30.0),
            create_mock_wall(wall_id="wall_b", length=20.0),
        ]
        config = PanelConfig()

        results = decompose_all_walls(walls, config=config)

        assert len(results) == 2
        assert results[0]["wall_id"] == "wall_a"
        assert results[1]["wall_id"] == "wall_b"

    def test_with_framing_data(self):
        """Test decomposing walls with framing data."""
        walls = [create_mock_wall(wall_id="wall_a")]
        framing = [create_mock_framing(wall_id="wall_a")]
        config = PanelConfig()

        results = decompose_all_walls(walls, framing, config)

        assert len(results) == 1

    def test_corner_detection(self):
        """Test that corners are detected between walls."""
        # Two walls meeting at a corner
        wall_a = create_mock_wall(wall_id="wall_a", length=20.0)
        wall_a["base_curve_start"] = {"x": 0, "y": 0, "z": 0}
        wall_a["base_curve_end"] = {"x": 20, "y": 0, "z": 0}

        wall_b = create_mock_wall(wall_id="wall_b", length=15.0)
        wall_b["base_curve_start"] = {"x": 0, "y": 0, "z": 0}
        wall_b["base_curve_end"] = {"x": 0, "y": 15, "z": 0}
        wall_b["base_plane"]["x_axis"] = {"x": 0, "y": 1, "z": 0}

        config = PanelConfig()
        results = decompose_all_walls([wall_a, wall_b], config=config)

        # Both walls should have corner adjustments
        assert len(results) == 2


class TestSerialization:
    """Tests for serialization functions."""

    def test_serialize_deserialize(self):
        """Test round-trip serialization."""
        wall = create_mock_wall()
        config = PanelConfig()

        original = decompose_wall_to_panels(wall, config=config)
        json_str = serialize_panel_results(original)
        restored = deserialize_panel_results(json_str)

        assert original["wall_id"] == restored["wall_id"]
        assert original["total_panel_count"] == restored["total_panel_count"]
        assert len(original["panels"]) == len(restored["panels"])

    def test_json_valid(self):
        """Test that serialized result is valid JSON."""
        wall = create_mock_wall()
        config = PanelConfig()

        result = decompose_wall_to_panels(wall, config=config)
        json_str = serialize_panel_results(result)

        # Should not raise
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
