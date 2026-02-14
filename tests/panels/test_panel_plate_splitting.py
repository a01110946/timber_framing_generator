# File: tests/panels/test_panel_plate_splitting.py
"""Unit tests for panel-aware plate splitting and panel ID assignment.

The actual plate geometry splitting (_split_reference_line_at_panel_boundaries)
requires Rhino and is tested via Grasshopper integration tests.
This module tests the pure-Python logic for panel ID assignment.
"""

import pytest
from src.timber_framing_generator.panels.panel_decomposer import (
    assign_panel_ids_to_elements,
)


class TestAssignPanelIdsToElements:
    """Tests for assign_panel_ids_to_elements function."""

    def test_single_panel_all_assigned(self):
        """All elements in a single-panel wall get the same panel_id."""
        panels = [{"id": "w1_panel_0", "u_start": 0.0, "u_end": 20.0}]
        elements = [
            {"u_coord": 0.0625},
            {"u_coord": 5.0},
            {"u_coord": 10.0},
            {"u_coord": 19.9375},
            {"u_coord": 20.0},  # right boundary, inclusive for last panel
        ]

        assign_panel_ids_to_elements(elements, panels)

        for elem in elements:
            assert elem["panel_id"] == "w1_panel_0"

    def test_two_panels_boundary_goes_right(self):
        """Element exactly at a non-last panel boundary goes to right panel."""
        panels = [
            {"id": "p0", "u_start": 0.0, "u_end": 12.0},
            {"id": "p1", "u_start": 12.0, "u_end": 24.0},
        ]
        elements = [
            {"u_coord": 6.0},    # middle of p0
            {"u_coord": 12.0},   # boundary -> p1 (exclusive upper on p0)
            {"u_coord": 18.0},   # middle of p1
        ]

        assign_panel_ids_to_elements(elements, panels)

        assert elements[0]["panel_id"] == "p0"
        assert elements[1]["panel_id"] == "p1"
        assert elements[2]["panel_id"] == "p1"

    def test_four_panels_correct_assignment(self):
        """Elements across 4 panels are assigned correctly."""
        panels = [
            {"id": "p0", "u_start": 0.0, "u_end": 12.0},
            {"id": "p1", "u_start": 12.0, "u_end": 24.0},
            {"id": "p2", "u_start": 24.0, "u_end": 36.0},
            {"id": "p3", "u_start": 36.0, "u_end": 48.0},
        ]
        elements = [
            {"u_coord": 0.0},
            {"u_coord": 6.0},
            {"u_coord": 11.99},
            {"u_coord": 12.0},
            {"u_coord": 24.0},
            {"u_coord": 36.0},
            {"u_coord": 48.0},
        ]

        assign_panel_ids_to_elements(elements, panels)

        assert elements[0]["panel_id"] == "p0"
        assert elements[1]["panel_id"] == "p0"
        assert elements[2]["panel_id"] == "p0"
        assert elements[3]["panel_id"] == "p1"
        assert elements[4]["panel_id"] == "p2"
        assert elements[5]["panel_id"] == "p3"
        assert elements[6]["panel_id"] == "p3"  # inclusive upper on last panel

    def test_no_panels_returns_elements_unchanged(self):
        """Empty panels list returns elements without panel_id."""
        elements = [{"u_coord": 5.0}, {"u_coord": 15.0}]
        result = assign_panel_ids_to_elements(elements, [])
        # Elements should be returned unchanged
        assert result is elements

    def test_element_outside_all_panels_gets_none(self):
        """Elements outside all panel ranges get panel_id=None."""
        panels = [{"id": "p0", "u_start": 5.0, "u_end": 10.0}]
        elements = [
            {"u_coord": 2.0},   # before all panels
            {"u_coord": 15.0},  # after all panels
        ]

        assign_panel_ids_to_elements(elements, panels)

        assert elements[0]["panel_id"] is None
        assert elements[1]["panel_id"] is None

    def test_element_without_u_coord_gets_none(self):
        """Elements missing u_coord field get panel_id=None."""
        panels = [{"id": "p0", "u_start": 0.0, "u_end": 24.0}]
        elements = [{"some_field": "value"}]

        assign_panel_ids_to_elements(elements, panels)

        assert elements[0]["panel_id"] is None

    def test_all_element_types_represented(self):
        """Mixed element types all get correct panel_id based on u_coord."""
        panels = [
            {"id": "p0", "u_start": 0.0, "u_end": 12.0},
            {"id": "p1", "u_start": 12.0, "u_end": 24.0},
        ]
        elements = [
            {"element_type": "stud", "u_coord": 1.333},
            {"element_type": "king_stud", "u_coord": 5.0},
            {"element_type": "trimmer", "u_coord": 5.125},
            {"element_type": "header_cripple", "u_coord": 7.0},
            {"element_type": "sill_cripple", "u_coord": 7.0},
            {"element_type": "stud", "u_coord": 15.0},
            {"element_type": "blocking", "u_coord": 18.0},
        ]

        assign_panel_ids_to_elements(elements, panels)

        assert elements[0]["panel_id"] == "p0"
        assert elements[1]["panel_id"] == "p0"
        assert elements[2]["panel_id"] == "p0"
        assert elements[3]["panel_id"] == "p0"
        assert elements[4]["panel_id"] == "p0"
        assert elements[5]["panel_id"] == "p1"
        assert elements[6]["panel_id"] == "p1"

    def test_unsorted_panels_still_work(self):
        """Panels provided in non-sorted order still assign correctly."""
        panels = [
            {"id": "p1", "u_start": 12.0, "u_end": 24.0},
            {"id": "p0", "u_start": 0.0, "u_end": 12.0},
        ]
        elements = [
            {"u_coord": 3.0},
            {"u_coord": 18.0},
        ]

        assign_panel_ids_to_elements(elements, panels)

        assert elements[0]["panel_id"] == "p0"
        assert elements[1]["panel_id"] == "p1"

    def test_panel_id_preserved_on_repeated_calls(self):
        """Calling assignment twice overwrites panel_id cleanly."""
        panels_v1 = [{"id": "old_p0", "u_start": 0.0, "u_end": 24.0}]
        panels_v2 = [
            {"id": "new_p0", "u_start": 0.0, "u_end": 12.0},
            {"id": "new_p1", "u_start": 12.0, "u_end": 24.0},
        ]
        elements = [{"u_coord": 6.0}, {"u_coord": 18.0}]

        assign_panel_ids_to_elements(elements, panels_v1)
        assert elements[0]["panel_id"] == "old_p0"
        assert elements[1]["panel_id"] == "old_p0"

        assign_panel_ids_to_elements(elements, panels_v2)
        assert elements[0]["panel_id"] == "new_p0"
        assert elements[1]["panel_id"] == "new_p1"
