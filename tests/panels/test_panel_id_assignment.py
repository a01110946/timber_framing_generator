# File: tests/panels/test_panel_id_assignment.py
"""Unit tests for panel_id field in FramingElementData and serialization.

Tests that panel_id is correctly serialized/deserialized and that the
schema changes are backward-compatible with existing data.
"""

import pytest
import json
from dataclasses import asdict

from src.timber_framing_generator.core.json_schemas import (
    FramingElementData,
    FramingResults,
    ProfileData,
    Point3D,
    FramingJSONEncoder,
    serialize_framing_results,
    deserialize_framing_results,
)


def _make_element(
    element_id: str = "stud_0",
    u_coord: float = 5.0,
    panel_id: str = None,
) -> FramingElementData:
    """Create a minimal FramingElementData for testing."""
    return FramingElementData(
        id=element_id,
        element_type="stud",
        profile=ProfileData(
            name="2x4",
            width=0.125,
            depth=0.292,
            material_system="timber",
        ),
        centerline_start=Point3D(x=u_coord, y=0.0, z=0.0),
        centerline_end=Point3D(x=u_coord, y=0.0, z=8.0),
        u_coord=u_coord,
        v_start=0.0,
        v_end=8.0,
        panel_id=panel_id,
    )


class TestFramingElementDataPanelId:
    """Tests for panel_id on FramingElementData."""

    def test_panel_id_default_none(self):
        """panel_id defaults to None when not specified."""
        elem = _make_element()
        assert elem.panel_id is None

    def test_panel_id_set(self):
        """panel_id can be set to a string value."""
        elem = _make_element(panel_id="wall1_panel_0")
        assert elem.panel_id == "wall1_panel_0"

    def test_panel_id_in_asdict(self):
        """panel_id is included in asdict() output."""
        elem = _make_element(panel_id="wall1_panel_2")
        d = asdict(elem)
        assert "panel_id" in d
        assert d["panel_id"] == "wall1_panel_2"

    def test_panel_id_none_in_asdict(self):
        """panel_id=None is included in asdict() output."""
        elem = _make_element()
        d = asdict(elem)
        assert "panel_id" in d
        assert d["panel_id"] is None


class TestFramingResultsSerialization:
    """Tests for panel_id serialization/deserialization in FramingResults."""

    def test_serialize_with_panel_id(self):
        """panel_id is present in serialized JSON output."""
        elem = _make_element(panel_id="w1_panel_0")
        results = FramingResults(
            wall_id="w1",
            material_system="timber",
            elements=[elem],
        )
        json_str = serialize_framing_results(results)
        data = json.loads(json_str)

        assert len(data["elements"]) == 1
        assert data["elements"][0]["panel_id"] == "w1_panel_0"

    def test_serialize_without_panel_id(self):
        """panel_id is null in serialized JSON when not set."""
        elem = _make_element()
        results = FramingResults(
            wall_id="w1",
            material_system="timber",
            elements=[elem],
        )
        json_str = serialize_framing_results(results)
        data = json.loads(json_str)

        assert data["elements"][0]["panel_id"] is None

    def test_deserialize_with_panel_id(self):
        """panel_id is correctly deserialized from JSON."""
        elem = _make_element(panel_id="w1_panel_1")
        results = FramingResults(
            wall_id="w1",
            material_system="timber",
            elements=[elem],
        )
        json_str = serialize_framing_results(results)

        restored = deserialize_framing_results(json_str)
        assert restored.elements[0].panel_id == "w1_panel_1"

    def test_deserialize_without_panel_id_field(self):
        """Deserialization handles missing panel_id (backward compatibility)."""
        # Simulate old JSON without panel_id field
        old_json = json.dumps({
            "wall_id": "w1",
            "material_system": "timber",
            "elements": [{
                "id": "stud_0",
                "element_type": "stud",
                "profile": {
                    "name": "2x4",
                    "width": 0.125,
                    "depth": 0.292,
                    "material_system": "timber",
                    "properties": {},
                },
                "centerline_start": {"x": 1.0, "y": 0.0, "z": 0.0},
                "centerline_end": {"x": 1.0, "y": 0.0, "z": 8.0},
                "u_coord": 1.0,
                "v_start": 0.0,
                "v_end": 8.0,
                "cell_id": None,
                "metadata": {},
            }],
            "element_counts": {},
            "metadata": {},
        })

        restored = deserialize_framing_results(old_json)
        # panel_id should be None (missing from JSON -> .get() returns None)
        assert restored.elements[0].panel_id is None

    def test_roundtrip_multiple_panels(self):
        """Multiple elements with different panel_ids survive roundtrip."""
        elems = [
            _make_element("s0", u_coord=3.0, panel_id="p0"),
            _make_element("s1", u_coord=15.0, panel_id="p1"),
            _make_element("s2", u_coord=27.0, panel_id="p2"),
            _make_element("s3", u_coord=40.0, panel_id=None),
        ]
        results = FramingResults(
            wall_id="w1",
            material_system="timber",
            elements=elems,
        )
        json_str = serialize_framing_results(results)
        restored = deserialize_framing_results(json_str)

        assert restored.elements[0].panel_id == "p0"
        assert restored.elements[1].panel_id == "p1"
        assert restored.elements[2].panel_id == "p2"
        assert restored.elements[3].panel_id is None
