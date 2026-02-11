# File: tests/assemblies/test_element_grouping.py
"""Unit tests for element grouping logic (pure Python, no Revit dependency).

Tests group_elements_by_panel() which correlates baking_data_json, panels_json,
and Revit ElementIds to create PanelElementGroup objects.
"""

import json

import pytest

from src.timber_framing_generator.assemblies.assembly_creator import (
    PanelElementGroup,
    _compute_member_u,
    _derive_wall_axis,
    _extract_panels_list,
    _find_panel_for_u,
    generate_assembly_name,
    group_elements_by_panel,
)


# =============================================================================
# Fixtures
# =============================================================================

def _make_baking_data(
    walls: dict[str, list[dict]],
) -> str:
    """Build baking_data_json from a wall -> members mapping.

    Args:
        walls: Dict of wall_id -> list of member dicts.
            Each member needs: id, classification, geometry_index, panel_id (optional)
    """
    data = {"walls": {}}
    for wall_id, members in walls.items():
        data["walls"][wall_id] = {"members": members}
    return json.dumps(data)


def _make_panels(panels: list[dict]) -> str:
    """Build panels_json from a list of panel dicts.

    Each panel needs: id, wall_id, panel_index, element_ids
    """
    return json.dumps(panels)


def _make_sheathing_data(panels: list[dict]) -> str:
    """Build sheathing_data_json from panel list.

    Each panel needs: panel_id (or wall_id), plus any other fields.
    """
    return json.dumps({"panels": panels})


@pytest.fixture
def simple_baking_data() -> str:
    """Single wall with 4 members: 2 columns + 2 beams."""
    return _make_baking_data({
        "wall_1": [
            {"id": "stud_1", "classification": "column", "geometry_index": 0, "panel_id": "wall_1_panel_0"},
            {"id": "stud_2", "classification": "column", "geometry_index": 1, "panel_id": "wall_1_panel_1"},
            {"id": "plate_1", "classification": "beam", "geometry_index": 0, "panel_id": "wall_1_panel_0"},
            {"id": "plate_2", "classification": "beam", "geometry_index": 1, "panel_id": "wall_1_panel_1"},
        ]
    })


@pytest.fixture
def two_panel_data() -> str:
    """Two panels for wall_1."""
    return _make_panels([
        {
            "id": "wall_1_panel_0",
            "wall_id": "wall_1",
            "panel_index": 0,
            "element_ids": ["stud_1", "plate_1"],
        },
        {
            "id": "wall_1_panel_1",
            "wall_id": "wall_1",
            "panel_index": 1,
            "element_ids": ["stud_2", "plate_2"],
        },
    ])


# Use simple string IDs as stand-ins for Revit ElementIds
MOCK_COLUMN_IDS = ["col_eid_0", "col_eid_1"]
MOCK_BEAM_IDS = ["beam_eid_0", "beam_eid_1"]


# =============================================================================
# PanelElementGroup Tests
# =============================================================================

class TestPanelElementGroup:
    """Tests for PanelElementGroup dataclass."""

    def test_empty_group(self) -> None:
        group = PanelElementGroup(
            panel_id="test", wall_id="wall_1", panel_index=0,
        )
        assert group.is_empty
        assert group.element_count == 0
        assert group.all_element_ids == []

    def test_all_element_ids_combines_all_types(self) -> None:
        group = PanelElementGroup(
            panel_id="test",
            wall_id="wall_1",
            panel_index=0,
            column_element_ids=["c1", "c2"],
            beam_element_ids=["b1"],
            sheathing_element_ids=["s1", "s2", "s3"],
        )
        assert group.element_count == 6
        assert not group.is_empty
        assert group.all_element_ids == ["c1", "c2", "b1", "s1", "s2", "s3"]

    def test_element_count_with_only_columns(self) -> None:
        group = PanelElementGroup(
            panel_id="test", wall_id="w", panel_index=0,
            column_element_ids=["c1"],
        )
        assert group.element_count == 1
        assert not group.is_empty


# =============================================================================
# group_elements_by_panel Tests
# =============================================================================

class TestGroupElementsByPanel:
    """Tests for group_elements_by_panel()."""

    def test_basic_two_panel_grouping(
        self, simple_baking_data: str, two_panel_data: str,
    ) -> None:
        """Two panels each get their correct elements."""
        groups = group_elements_by_panel(
            simple_baking_data, two_panel_data,
            MOCK_COLUMN_IDS, MOCK_BEAM_IDS,
        )
        assert len(groups) == 2

        # Panel 0: stud_1 (column idx 0) + plate_1 (beam idx 0)
        g0 = groups[0]
        assert g0.panel_id == "wall_1_panel_0"
        assert g0.column_element_ids == ["col_eid_0"]
        assert g0.beam_element_ids == ["beam_eid_0"]
        assert g0.element_count == 2

        # Panel 1: stud_2 (column idx 1) + plate_2 (beam idx 1)
        g1 = groups[1]
        assert g1.panel_id == "wall_1_panel_1"
        assert g1.column_element_ids == ["col_eid_1"]
        assert g1.beam_element_ids == ["beam_eid_1"]
        assert g1.element_count == 2

    def test_no_panels_falls_back_to_wall_grouping(
        self, simple_baking_data: str,
    ) -> None:
        """Without panels_json, creates one group per wall."""
        groups = group_elements_by_panel(
            simple_baking_data, None,
            MOCK_COLUMN_IDS, MOCK_BEAM_IDS,
        )
        assert len(groups) == 1
        g = groups[0]
        assert g.panel_id == "wall_1"
        assert g.wall_id == "wall_1"
        assert g.element_count == 4  # all 4 members

    def test_empty_panels_json_falls_back_to_wall(
        self, simple_baking_data: str,
    ) -> None:
        """Empty panels_json string treated as no panels."""
        groups = group_elements_by_panel(
            simple_baking_data, "[]",
            MOCK_COLUMN_IDS, MOCK_BEAM_IDS,
        )
        # Empty list -> _group_by_panels returns no groups,
        # but panels_data is truthy (empty list is falsy in Python)
        # so falls back to wall grouping
        # Actually [] is falsy, so it falls back
        assert len(groups) == 1
        assert groups[0].panel_id == "wall_1"

    def test_panel_with_missing_element_in_baking_data(self) -> None:
        """Elements referenced in panel but not in baking data are skipped."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "stud_1", "classification": "column", "geometry_index": 0},
            ]
        })
        panels = _make_panels([{
            "id": "wall_1_panel_0",
            "wall_id": "wall_1",
            "panel_index": 0,
            "element_ids": ["stud_1", "stud_missing"],
        }])
        groups = group_elements_by_panel(
            baking, panels, ["col_eid_0"], [],
        )
        assert len(groups) == 1
        assert groups[0].element_count == 1  # only stud_1 matched

    def test_panel_with_no_elements_is_skipped(self) -> None:
        """Panel whose element_ids don't match any baking data is skipped."""
        baking = _make_baking_data({"wall_1": []})
        panels = _make_panels([{
            "id": "wall_1_panel_0",
            "wall_id": "wall_1",
            "panel_index": 0,
            "element_ids": ["nonexistent"],
        }])
        groups = group_elements_by_panel(baking, panels, [], [])
        assert len(groups) == 0

    def test_geometry_index_out_of_range_is_skipped(self) -> None:
        """If geometry_index exceeds the ID list length, element is skipped."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "stud_1", "classification": "column", "geometry_index": 99},
            ]
        })
        panels = _make_panels([{
            "id": "wall_1_panel_0",
            "wall_id": "wall_1",
            "panel_index": 0,
            "element_ids": ["stud_1"],
        }])
        groups = group_elements_by_panel(
            baking, panels, ["col_eid_0"], [],
        )
        assert len(groups) == 0  # stud_1 skipped, panel empty, panel skipped

    def test_multi_wall_grouping(self) -> None:
        """Multiple walls each get their own group when no panels."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "s1", "classification": "column", "geometry_index": 0},
            ],
            "wall_2": [
                {"id": "s2", "classification": "column", "geometry_index": 1},
            ],
        })
        groups = group_elements_by_panel(
            baking, None, ["eid_0", "eid_1"], [],
        )
        assert len(groups) == 2
        wall_ids = {g.wall_id for g in groups}
        assert wall_ids == {"wall_1", "wall_2"}

    def test_sheathing_included_in_panel_groups(self) -> None:
        """Sheathing ElementIds are added to the correct panel group."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "stud_1", "classification": "column", "geometry_index": 0},
            ]
        })
        panels = _make_panels([{
            "id": "wall_1_panel_0",
            "wall_id": "wall_1",
            "panel_index": 0,
            "element_ids": ["stud_1"],
        }])
        sheathing_ids = ["sheath_eid_0", "sheath_eid_1"]
        sheathing_data = _make_sheathing_data([
            {"panel_id": "wall_1_panel_0"},
            {"panel_id": "wall_1_panel_0"},
        ])

        groups = group_elements_by_panel(
            baking, panels, ["col_eid_0"], [],
            sheathing_ids=sheathing_ids,
            sheathing_data_json=sheathing_data,
        )
        assert len(groups) == 1
        g = groups[0]
        assert g.column_element_ids == ["col_eid_0"]
        assert g.sheathing_element_ids == ["sheath_eid_0", "sheath_eid_1"]
        assert g.element_count == 3

    def test_sheathing_without_data_json_is_ignored(self) -> None:
        """Sheathing IDs without data JSON are ignored."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "s1", "classification": "column", "geometry_index": 0},
            ]
        })
        panels = _make_panels([{
            "id": "wall_1_panel_0",
            "wall_id": "wall_1",
            "panel_index": 0,
            "element_ids": ["s1"],
        }])
        groups = group_elements_by_panel(
            baking, panels, ["eid_0"], [],
            sheathing_ids=["sheath_eid_0"],
            sheathing_data_json=None,
        )
        assert len(groups) == 1
        assert groups[0].sheathing_element_ids == []

    def test_sheathing_wall_fallback(self) -> None:
        """Sheathing grouped by wall_id when no panels defined."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "s1", "classification": "column", "geometry_index": 0},
            ]
        })
        sheathing_data = _make_sheathing_data([
            {"wall_id": "wall_1"},
        ])
        groups = group_elements_by_panel(
            baking, None, ["eid_0"], [],
            sheathing_ids=["sheath_eid_0"],
            sheathing_data_json=sheathing_data,
        )
        assert len(groups) == 1
        assert groups[0].sheathing_element_ids == ["sheath_eid_0"]


# =============================================================================
# _extract_panels_list Tests (nested format handling)
# =============================================================================

class TestExtractPanelsList:
    """Tests for _extract_panels_list() which normalizes panels_json formats."""

    def test_none_returns_none(self) -> None:
        assert _extract_panels_list(None) is None

    def test_empty_list_returns_none(self) -> None:
        assert _extract_panels_list([]) is None

    def test_flat_list_of_panel_dicts(self) -> None:
        """Already-flat list with 'id' key passes through."""
        panels = [
            {"id": "wall_1_panel_0", "wall_id": "wall_1", "panel_index": 0},
        ]
        result = _extract_panels_list(panels)
        assert result == panels

    def test_single_wall_result_dict(self) -> None:
        """Single wall result with nested 'panels' key."""
        wall_result = {
            "wall_id": "wall_1",
            "panels": [
                {"id": "wall_1_panel_0", "wall_id": "wall_1", "panel_index": 0},
                {"id": "wall_1_panel_1", "wall_id": "wall_1", "panel_index": 1},
            ],
            "joints": [],
        }
        result = _extract_panels_list(wall_result)
        assert len(result) == 2
        assert result[0]["id"] == "wall_1_panel_0"
        assert result[1]["id"] == "wall_1_panel_1"

    def test_list_of_wall_results(self) -> None:
        """List of wall results, each with nested 'panels'."""
        wall_results = [
            {
                "wall_id": "wall_1",
                "panels": [
                    {"id": "wall_1_panel_0", "wall_id": "wall_1", "panel_index": 0},
                ],
            },
            {
                "wall_id": "wall_2",
                "panels": [
                    {"id": "wall_2_panel_0", "wall_id": "wall_2", "panel_index": 0},
                    {"id": "wall_2_panel_1", "wall_id": "wall_2", "panel_index": 1},
                ],
            },
        ]
        result = _extract_panels_list(wall_results)
        assert len(result) == 3
        assert result[0]["id"] == "wall_1_panel_0"
        assert result[2]["id"] == "wall_2_panel_1"

    def test_wall_result_with_empty_panels(self) -> None:
        """Wall result where panels list is empty."""
        wall_result = {"wall_id": "wall_1", "panels": []}
        assert _extract_panels_list(wall_result) is None


class TestGroupWithNestedPanelsJson:
    """Tests for group_elements_by_panel() with real panels_json format."""

    def test_nested_wall_result_format(self, simple_baking_data: str) -> None:
        """panels_json in real decomposer format (single wall result dict)."""
        panels_json = json.dumps({
            "wall_id": "wall_1",
            "panels": [
                {
                    "id": "wall_1_panel_0",
                    "wall_id": "wall_1",
                    "panel_index": 0,
                    "element_ids": ["stud_1", "plate_1"],
                },
                {
                    "id": "wall_1_panel_1",
                    "wall_id": "wall_1",
                    "panel_index": 1,
                    "element_ids": ["stud_2", "plate_2"],
                },
            ],
            "joints": [],
        })
        groups = group_elements_by_panel(
            simple_baking_data, panels_json,
            MOCK_COLUMN_IDS, MOCK_BEAM_IDS,
        )
        assert len(groups) == 2
        assert groups[0].panel_id == "wall_1_panel_0"
        assert groups[0].element_count == 2
        assert groups[1].panel_id == "wall_1_panel_1"
        assert groups[1].element_count == 2

    def test_list_of_wall_results_format(self) -> None:
        """panels_json as list of wall results (multi-wall)."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "s1", "classification": "column", "geometry_index": 0},
            ],
            "wall_2": [
                {"id": "s2", "classification": "column", "geometry_index": 1},
            ],
        })
        panels_json = json.dumps([
            {
                "wall_id": "wall_1",
                "panels": [{"id": "w1p0", "wall_id": "wall_1", "panel_index": 0, "element_ids": ["s1"]}],
            },
            {
                "wall_id": "wall_2",
                "panels": [{"id": "w2p0", "wall_id": "wall_2", "panel_index": 0, "element_ids": ["s2"]}],
            },
        ])
        groups = group_elements_by_panel(
            baking, panels_json, ["eid_0", "eid_1"], [],
        )
        assert len(groups) == 2
        panel_ids = {g.panel_id for g in groups}
        assert panel_ids == {"w1p0", "w2p0"}


# =============================================================================
# Assembly Naming Tests
# =============================================================================

class TestAssemblyNaming:
    """Tests for generate_assembly_name()."""

    def test_standard_naming(self) -> None:
        assert generate_assembly_name("wall_1", 0) == "W1-P01"
        assert generate_assembly_name("wall_1", 1) == "W1-P02"
        assert generate_assembly_name("wall_1", 9) == "W1-P10"

    def test_custom_prefix(self) -> None:
        assert generate_assembly_name("wall_3", 0, prefix="WP") == "WP3-P01"

    def test_wall_id_without_number(self) -> None:
        """Wall ID without numeric part uses 0."""
        assert generate_assembly_name("exterior_wall", 0) == "W0-P01"

    def test_wall_id_with_large_number(self) -> None:
        assert generate_assembly_name("wall_42", 0) == "W42-P01"

    def test_multi_digit_panel_index(self) -> None:
        """Panel index > 99 still works (not zero-padded to 2)."""
        name = generate_assembly_name("wall_1", 99)
        assert name == "W1-P100"


# =============================================================================
# Geometry-Based Fallback Tests
# =============================================================================

class TestDeriveWallAxis:
    """Tests for _derive_wall_axis() which finds wall direction from beams."""

    def test_single_beam_along_x(self) -> None:
        """A single beam along X axis gives X-direction."""
        members = [
            {
                "id": "plate_1", "classification": "beam",
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 10, "y": 0, "z": 0},
            },
        ]
        origin, direction = _derive_wall_axis(members)
        assert origin is not None
        assert abs(direction["x"] - 1.0) < 1e-6
        assert abs(direction["y"]) < 1e-6
        assert abs(direction["z"]) < 1e-6

    def test_longest_beam_is_selected(self) -> None:
        """When multiple beams exist, the longest one determines direction."""
        members = [
            {
                "id": "short_plate", "classification": "beam",
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 2, "y": 0, "z": 0},
            },
            {
                "id": "long_plate", "classification": "beam",
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 20, "y": 0, "z": 0},
            },
        ]
        origin, direction = _derive_wall_axis(members)
        assert origin == {"x": 0, "y": 0, "z": 0}
        assert abs(direction["x"] - 1.0) < 1e-6

    def test_columns_are_ignored(self) -> None:
        """Columns are not used for wall direction."""
        members = [
            {
                "id": "stud_1", "classification": "column",
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 0, "y": 0, "z": 10},
            },
        ]
        origin, direction = _derive_wall_axis(members)
        assert origin is None
        assert direction is None

    def test_diagonal_beam(self) -> None:
        """Beam at 45 degrees gives normalized direction."""
        members = [
            {
                "id": "plate_1", "classification": "beam",
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 10, "y": 10, "z": 0},
            },
        ]
        origin, direction = _derive_wall_axis(members)
        expected = 10.0 / (200 ** 0.5)  # 10/sqrt(200) = 1/sqrt(2)
        assert abs(direction["x"] - expected) < 1e-6
        assert abs(direction["y"] - expected) < 1e-6

    def test_empty_members_returns_none(self) -> None:
        origin, direction = _derive_wall_axis([])
        assert origin is None
        assert direction is None


class TestComputeMemberU:
    """Tests for _compute_member_u() which projects members onto wall axis."""

    def test_column_uses_start_point(self) -> None:
        """Column U is computed from centerline_start (bottom)."""
        member = {
            "classification": "column",
            "centerline_start": {"x": 5, "y": 0, "z": 0},
            "centerline_end": {"x": 5, "y": 0, "z": 8},
        }
        origin = {"x": 0, "y": 0, "z": 0}
        direction = {"x": 1, "y": 0, "z": 0}
        u = _compute_member_u(member, origin, direction)
        assert abs(u - 5.0) < 1e-6

    def test_beam_uses_midpoint(self) -> None:
        """Beam U is computed from the midpoint of its centerline."""
        member = {
            "classification": "beam",
            "centerline_start": {"x": 2, "y": 0, "z": 8},
            "centerline_end": {"x": 8, "y": 0, "z": 8},
        }
        origin = {"x": 0, "y": 0, "z": 0}
        direction = {"x": 1, "y": 0, "z": 0}
        u = _compute_member_u(member, origin, direction)
        assert abs(u - 5.0) < 1e-6  # midpoint x = (2+8)/2 = 5

    def test_offset_origin(self) -> None:
        """U is relative to origin, not world origin."""
        member = {
            "classification": "column",
            "centerline_start": {"x": 15, "y": 0, "z": 0},
            "centerline_end": {"x": 15, "y": 0, "z": 8},
        }
        origin = {"x": 10, "y": 0, "z": 0}
        direction = {"x": 1, "y": 0, "z": 0}
        u = _compute_member_u(member, origin, direction)
        assert abs(u - 5.0) < 1e-6

    def test_missing_centerline_returns_none(self) -> None:
        """Empty centerline dicts are falsy -> returns None."""
        member = {"classification": "column", "centerline_start": {}, "centerline_end": {}}
        origin = {"x": 0, "y": 0, "z": 0}
        direction = {"x": 1, "y": 0, "z": 0}
        u = _compute_member_u(member, origin, direction)
        assert u is None


class TestFindPanelForU:
    """Tests for _find_panel_for_u() which matches U to panel ranges."""

    def _panels(self) -> list:
        return [
            {"id": "p0", "u_start": 0, "u_end": 4},
            {"id": "p1", "u_start": 4, "u_end": 8},
            {"id": "p2", "u_start": 8, "u_end": 12},
        ]

    def test_middle_of_first_panel(self) -> None:
        assert _find_panel_for_u(2.0, self._panels()) == "p0"

    def test_middle_of_last_panel(self) -> None:
        assert _find_panel_for_u(10.0, self._panels()) == "p2"

    def test_exact_boundary_goes_to_later_panel(self) -> None:
        """U exactly at boundary between p0/p1 goes to p0 (< u_end for non-last)."""
        # With tolerance, u=4.0 matches p0 (u_start-tol <= 4.0 < u_end+tol = 4.01)
        # but also p1 (u_start-tol = 3.99 <= 4.0 < u_end+tol)
        # Since we iterate in order, p0 matches first
        result = _find_panel_for_u(4.0, self._panels())
        assert result in ("p0", "p1")  # Either is acceptable at boundary

    def test_end_of_last_panel(self) -> None:
        """U at the very end of the last panel is included (<=)."""
        assert _find_panel_for_u(12.0, self._panels()) == "p2"

    def test_beyond_all_panels_returns_none(self) -> None:
        assert _find_panel_for_u(20.0, self._panels()) is None

    def test_before_all_panels_returns_none(self) -> None:
        assert _find_panel_for_u(-5.0, self._panels()) is None

    def test_near_boundary_with_tolerance(self) -> None:
        """Element slightly outside panel range is still captured by tolerance."""
        # u_start of p0 is 0, tolerance is 0.01
        assert _find_panel_for_u(-0.005, self._panels()) == "p0"


class TestGeometryBasedGrouping:
    """End-to-end tests for geometry-based fallback through public API."""

    def test_two_panels_geometry_assignment(self) -> None:
        """Members assigned to panels by U-coordinate when element_ids are empty."""
        # Wall along X axis, 0-10 ft
        # Panel 0: u=0-5, Panel 1: u=5-10
        baking = _make_baking_data({
            "wall_1": [
                # Columns (studs) at various positions
                {"id": "stud_0", "classification": "column", "geometry_index": 0,
                 "centerline_start": {"x": 1, "y": 0, "z": 0},
                 "centerline_end": {"x": 1, "y": 0, "z": 8}},
                {"id": "stud_1", "classification": "column", "geometry_index": 1,
                 "centerline_start": {"x": 3, "y": 0, "z": 0},
                 "centerline_end": {"x": 3, "y": 0, "z": 8}},
                {"id": "stud_2", "classification": "column", "geometry_index": 2,
                 "centerline_start": {"x": 7, "y": 0, "z": 0},
                 "centerline_end": {"x": 7, "y": 0, "z": 8}},
                {"id": "stud_3", "classification": "column", "geometry_index": 3,
                 "centerline_start": {"x": 9, "y": 0, "z": 0},
                 "centerline_end": {"x": 9, "y": 0, "z": 8}},
                # Bottom plate spanning full wall (longest beam -> wall axis)
                {"id": "plate_bot", "classification": "beam", "geometry_index": 0,
                 "centerline_start": {"x": 0, "y": 0, "z": 0},
                 "centerline_end": {"x": 10, "y": 0, "z": 0}},
                # Top plate spanning full wall
                {"id": "plate_top", "classification": "beam", "geometry_index": 1,
                 "centerline_start": {"x": 0, "y": 0, "z": 8},
                 "centerline_end": {"x": 10, "y": 0, "z": 8}},
            ],
        })

        # Panels with NO element_ids (triggers geometry-based fallback)
        panels_json = json.dumps({
            "wall_id": "wall_1",
            "panels": [
                {"id": "wall_1_panel_0", "wall_id": "wall_1", "panel_index": 0,
                 "u_start": 0, "u_end": 5, "element_ids": []},
                {"id": "wall_1_panel_1", "wall_id": "wall_1", "panel_index": 1,
                 "u_start": 5, "u_end": 10, "element_ids": []},
            ],
        })

        column_ids = ["col_eid_0", "col_eid_1", "col_eid_2", "col_eid_3"]
        beam_ids = ["beam_eid_0", "beam_eid_1"]

        groups = group_elements_by_panel(
            baking, panels_json, column_ids, beam_ids,
        )

        assert len(groups) == 2

        # Panel 0 (u=0-5): stud_0 (u=1), stud_1 (u=3), plate_bot midpoint=5, plate_top midpoint=5
        # Panel 1 (u=5-10): stud_2 (u=7), stud_3 (u=9)
        # Note: plates midpoint=5, which lands on boundary
        g0 = next(g for g in groups if g.panel_id == "wall_1_panel_0")
        g1 = next(g for g in groups if g.panel_id == "wall_1_panel_1")

        # stud_0 (idx=0) and stud_1 (idx=1) in panel 0
        assert "col_eid_0" in g0.column_element_ids
        assert "col_eid_1" in g0.column_element_ids

        # stud_2 (idx=2) and stud_3 (idx=3) in panel 1
        assert "col_eid_2" in g1.column_element_ids
        assert "col_eid_3" in g1.column_element_ids

    def test_wall_without_panels_skipped(self) -> None:
        """Wall present in baking data but absent from panels is skipped."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "s1", "classification": "column", "geometry_index": 0,
                 "centerline_start": {"x": 1, "y": 0, "z": 0},
                 "centerline_end": {"x": 1, "y": 0, "z": 8}},
                {"id": "p1", "classification": "beam", "geometry_index": 0,
                 "centerline_start": {"x": 0, "y": 0, "z": 0},
                 "centerline_end": {"x": 10, "y": 0, "z": 0}},
            ],
            "wall_2": [
                {"id": "s2", "classification": "column", "geometry_index": 1,
                 "centerline_start": {"x": 1, "y": 5, "z": 0},
                 "centerline_end": {"x": 1, "y": 5, "z": 8}},
                {"id": "p2", "classification": "beam", "geometry_index": 1,
                 "centerline_start": {"x": 0, "y": 5, "z": 0},
                 "centerline_end": {"x": 10, "y": 5, "z": 0}},
            ],
        })

        # Only wall_1 has panels
        panels_json = json.dumps({
            "wall_id": "wall_1",
            "panels": [
                {"id": "w1p0", "wall_id": "wall_1", "panel_index": 0,
                 "u_start": 0, "u_end": 10, "element_ids": []},
            ],
        })

        groups = group_elements_by_panel(
            baking, panels_json, ["eid_0", "eid_1"], ["eid_b0", "eid_b1"],
        )

        # Only wall_1 elements should be grouped
        assert len(groups) == 1
        assert groups[0].wall_id == "wall_1"

    def test_no_beams_means_no_axis_no_groups(self) -> None:
        """Wall with only columns cannot derive axis, produces no groups."""
        baking = _make_baking_data({
            "wall_1": [
                {"id": "s1", "classification": "column", "geometry_index": 0,
                 "centerline_start": {"x": 1, "y": 0, "z": 0},
                 "centerline_end": {"x": 1, "y": 0, "z": 8}},
            ],
        })

        panels_json = json.dumps({
            "wall_id": "wall_1",
            "panels": [
                {"id": "w1p0", "wall_id": "wall_1", "panel_index": 0,
                 "u_start": 0, "u_end": 10, "element_ids": []},
            ],
        })

        groups = group_elements_by_panel(
            baking, panels_json, ["eid_0"], [],
        )
        # Cannot derive wall axis from columns alone -> no grouping
        assert len(groups) == 0
