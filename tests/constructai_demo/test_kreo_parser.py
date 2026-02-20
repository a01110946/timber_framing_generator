# File: tests/constructai_demo/test_kreo_parser.py
"""Tests for Kreo JSON parser."""

import json

import pytest

from src.constructai_demo.kreo_parser import (
    KreoOpening,
    KreoPoint,
    KreoSpace,
    KreoWall,
    parse_doors,
    parse_spaces,
    parse_walls,
    parse_windows,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WALL_JSON = json.dumps({
    "status": "Ready",
    "lines": [
        {
            "p1": [545.13, 815.82],
            "p2": [545.13, 1262.99],
            "length": 7.572,
            "thickness": 0.1105,
        },
        {
            "p1": [1136.43, 729.74],
            "p2": [1136.43, 821.67],
            "length": 1.557,
            "thickness": 0.0897,
        },
    ],
})

SAMPLE_DOOR_JSON = json.dumps({
    "status": "Ready",
    "lines": [
        {
            "p1": [724.54, 688.26],
            "p2": [669.31, 688.26],
            "length": 0.935,
            "thickness": 0.1245,
        },
    ],
})

SAMPLE_WINDOW_JSON = json.dumps({
    "status": "Ready",
    "lines": [
        {
            "p1": [142.73, 534.72],
            "p2": [142.73, 600.98],
            "length": 1.122,
            "thickness": 0.1199,
        },
    ],
})

SAMPLE_SPACE_JSON = json.dumps({
    "status": "Ready",
    "contours": [
        {
            "points": [
                [540.81, 831.11],
                [540.81, 811.72],
                [618.12, 812.04],
                [618.12, 630.12],
                [434.16, 630.12],
                [434.16, 831.36],
            ],
            "text": ["BEDROOM3", "109S.F.", "9'-0\"CLG"],
            "area": 10.179,
            "perimeter": 13.047,
        },
    ],
})


# ---------------------------------------------------------------------------
# Wall parsing tests
# ---------------------------------------------------------------------------

class TestParseWalls:
    def test_basic_parsing(self):
        walls = parse_walls(SAMPLE_WALL_JSON)
        assert len(walls) == 2

    def test_wall_coordinates(self):
        walls = parse_walls(SAMPLE_WALL_JSON)
        w0 = walls[0]
        assert isinstance(w0, KreoWall)
        assert pytest.approx(w0.p1.x, abs=0.01) == 545.13
        assert pytest.approx(w0.p1.y, abs=0.01) == 815.82
        assert pytest.approx(w0.p2.x, abs=0.01) == 545.13
        assert pytest.approx(w0.p2.y, abs=0.01) == 1262.99

    def test_wall_measurements(self):
        walls = parse_walls(SAMPLE_WALL_JSON)
        assert pytest.approx(walls[0].length, abs=0.001) == 7.572
        assert pytest.approx(walls[0].thickness, abs=0.001) == 0.1105

    def test_wall_indices(self):
        walls = parse_walls(SAMPLE_WALL_JSON)
        assert walls[0].index == 0
        assert walls[1].index == 1

    def test_empty_lines(self):
        data = json.dumps({"status": "Ready", "lines": []})
        walls = parse_walls(data)
        assert walls == []

    def test_missing_lines_key(self):
        data = json.dumps({"status": "Ready"})
        with pytest.raises(ValueError, match="Missing 'lines' key"):
            parse_walls(data)

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_walls("not json")

    def test_missing_field(self):
        data = json.dumps({
            "status": "Ready",
            "lines": [{"p1": [0, 0], "p2": [1, 1], "length": 1.0}],
        })
        with pytest.raises(ValueError, match="missing required field 'thickness'"):
            parse_walls(data)

    def test_invalid_point_format(self):
        data = json.dumps({
            "status": "Ready",
            "lines": [{
                "p1": "not_a_point",
                "p2": [1, 1],
                "length": 1.0,
                "thickness": 0.1,
            }],
        })
        with pytest.raises(ValueError, match="Cannot parse point"):
            parse_walls(data)

    def test_bare_array_format(self):
        """Bare array (no wrapper object) should be auto-wrapped."""
        bare = json.dumps([
            {"p1": [0, 0], "p2": [10, 0], "length": 1.0, "thickness": 0.1},
        ])
        walls = parse_walls(bare)
        assert len(walls) == 1
        assert walls[0].length == 1.0

    def test_filtered_format_with_line_key(self):
        """Filtered format: points nested in 'line' as {x, y} objects."""
        filtered = json.dumps([{
            "line": {
                "p1": {"x": 545.13, "y": 815.82},
                "p2": {"x": 545.13, "y": 1262.99},
            },
            "length": 7.572,
            "thickness": 0.1105,
        }])
        walls = parse_walls(filtered)
        assert len(walls) == 1
        assert pytest.approx(walls[0].p1.x, abs=0.01) == 545.13
        assert pytest.approx(walls[0].p1.y, abs=0.01) == 815.82
        assert pytest.approx(walls[0].length, abs=0.001) == 7.572


# ---------------------------------------------------------------------------
# Door/Window parsing tests
# ---------------------------------------------------------------------------

class TestParseOpenings:
    def test_parse_doors(self):
        doors = parse_doors(SAMPLE_DOOR_JSON)
        assert len(doors) == 1
        assert doors[0].opening_type == "door"
        assert isinstance(doors[0], KreoOpening)

    def test_parse_windows(self):
        windows = parse_windows(SAMPLE_WINDOW_JSON)
        assert len(windows) == 1
        assert windows[0].opening_type == "window"

    def test_door_coordinates(self):
        doors = parse_doors(SAMPLE_DOOR_JSON)
        d0 = doors[0]
        assert pytest.approx(d0.p1.x, abs=0.01) == 724.54
        assert pytest.approx(d0.length, abs=0.001) == 0.935

    def test_window_coordinates(self):
        windows = parse_windows(SAMPLE_WINDOW_JSON)
        w0 = windows[0]
        assert pytest.approx(w0.p1.x, abs=0.01) == 142.73
        assert pytest.approx(w0.length, abs=0.001) == 1.122


# ---------------------------------------------------------------------------
# Space parsing tests
# ---------------------------------------------------------------------------

class TestParseSpaces:
    def test_basic_parsing(self):
        spaces = parse_spaces(SAMPLE_SPACE_JSON)
        assert len(spaces) == 1

    def test_space_contour(self):
        spaces = parse_spaces(SAMPLE_SPACE_JSON)
        s0 = spaces[0]
        assert isinstance(s0, KreoSpace)
        assert len(s0.contour) == 6
        assert pytest.approx(s0.contour[0].x, abs=0.01) == 540.81

    def test_space_text(self):
        spaces = parse_spaces(SAMPLE_SPACE_JSON)
        assert "BEDROOM3" in spaces[0].text

    def test_space_measurements(self):
        spaces = parse_spaces(SAMPLE_SPACE_JSON)
        assert pytest.approx(spaces[0].area, abs=0.001) == 10.179
        assert pytest.approx(spaces[0].perimeter, abs=0.001) == 13.047

    def test_missing_contours_key(self):
        data = json.dumps({"status": "Ready"})
        with pytest.raises(ValueError, match="Missing 'contours' key"):
            parse_spaces(data)


# ---------------------------------------------------------------------------
# KreoPoint tests
# ---------------------------------------------------------------------------

class TestKreoPoint:
    def test_from_array(self):
        pt = KreoPoint.from_array([100.5, 200.3])
        assert pt.x == 100.5
        assert pt.y == 200.3

    def test_from_array_int(self):
        pt = KreoPoint.from_array([100, 200])
        assert isinstance(pt.x, float)
        assert isinstance(pt.y, float)
