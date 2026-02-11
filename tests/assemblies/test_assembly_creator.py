# File: tests/assemblies/test_assembly_creator.py
"""Tests for AssemblyResult, AssemblyBatchResult, and create_assemblies().

The Revit API is mocked since tests run outside the Revit environment.
Focus is on data model correctness, serialization, and error handling.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.timber_framing_generator.assemblies.assembly_creator import (
    AssemblyBatchResult,
    AssemblyResult,
    PanelElementGroup,
    enrich_panels_with_framing_data,
)


# =============================================================================
# AssemblyResult Tests
# =============================================================================

class TestAssemblyResult:
    """Tests for AssemblyResult dataclass."""

    def test_default_state(self) -> None:
        r = AssemblyResult(
            panel_id="wall_1_panel_0",
            wall_id="wall_1",
            assembly_name="W1-P01",
        )
        assert r.status == "pending"
        assert r.assembly_id is None
        assert r.element_count == 0
        assert r.views_created == []
        assert r.view_ids == []
        assert r.sheet_id is None
        assert r.error is None

    def test_created_state(self) -> None:
        r = AssemblyResult(
            panel_id="wall_1_panel_0",
            wall_id="wall_1",
            assembly_name="W1-P01",
            assembly_id=12345,
            element_count=8,
            views_created=["3D Orthographic", "Front Elevation"],
            view_ids=[100, 101],
            status="created",
        )
        assert r.assembly_id == 12345
        assert r.status == "created"
        assert len(r.views_created) == 2
        assert r.view_ids == [100, 101]

    def test_created_with_sheet(self) -> None:
        r = AssemblyResult(
            panel_id="wall_1_panel_0",
            wall_id="wall_1",
            assembly_name="W1-P01",
            assembly_id=12345,
            element_count=8,
            views_created=["3D Orthographic", "Sheet: W1-P01"],
            view_ids=[100],
            sheet_id=200,
            status="created",
        )
        assert r.sheet_id == 200
        assert "Sheet: W1-P01" in r.views_created

    def test_failed_state(self) -> None:
        r = AssemblyResult(
            panel_id="wall_1_panel_0",
            wall_id="wall_1",
            assembly_name="W1-P01",
            status="failed",
            error="Invalid element IDs",
        )
        assert r.status == "failed"
        assert r.error == "Invalid element IDs"
        assert r.view_ids == []
        assert r.sheet_id is None


# =============================================================================
# AssemblyBatchResult Tests
# =============================================================================

class TestAssemblyBatchResult:
    """Tests for AssemblyBatchResult dataclass."""

    def test_empty_batch(self) -> None:
        batch = AssemblyBatchResult()
        d = batch.to_dict()
        assert d["assemblies"] == []
        assert d["summary"]["total"] == 0
        assert d["summary"]["successful"] == 0
        assert d["summary"]["failed"] == 0

    def test_batch_with_mixed_results(self) -> None:
        batch = AssemblyBatchResult(
            results=[
                AssemblyResult(
                    panel_id="w1p0", wall_id="wall_1",
                    assembly_name="W1-P01", assembly_id=100,
                    element_count=5, status="created",
                ),
                AssemblyResult(
                    panel_id="w1p1", wall_id="wall_1",
                    assembly_name="W1-P02", status="failed",
                    error="No elements",
                ),
            ],
            total_assemblies=2,
            successful=1,
            failed=1,
        )
        d = batch.to_dict()
        assert d["summary"]["total"] == 2
        assert d["summary"]["successful"] == 1
        assert d["summary"]["failed"] == 1
        assert len(d["assemblies"]) == 2
        assert d["assemblies"][0]["status"] == "created"
        assert d["assemblies"][1]["error"] == "No elements"

    def test_to_dict_includes_new_fields(self) -> None:
        """to_dict() includes view_ids and sheet_id."""
        batch = AssemblyBatchResult(
            results=[
                AssemblyResult(
                    panel_id="w1p0", wall_id="wall_1",
                    assembly_name="W1-P01", assembly_id=100,
                    element_count=5,
                    views_created=["3D Orthographic", "Front Elevation"],
                    view_ids=[200, 201],
                    sheet_id=300,
                    status="created",
                ),
            ],
            total_assemblies=1,
            successful=1,
            failed=0,
        )
        d = batch.to_dict()
        a = d["assemblies"][0]
        assert a["view_ids"] == [200, 201]
        assert a["sheet_id"] == 300

    def test_to_dict_new_fields_default_none_and_empty(self) -> None:
        """New fields default to None/empty in serialization."""
        batch = AssemblyBatchResult(
            results=[
                AssemblyResult(
                    panel_id="w1p0", wall_id="wall_1",
                    assembly_name="W1-P01", status="created",
                ),
            ],
            total_assemblies=1,
            successful=1,
            failed=0,
        )
        d = batch.to_dict()
        a = d["assemblies"][0]
        assert a["view_ids"] == []
        assert a["sheet_id"] is None

    def test_to_dict_is_json_serializable(self) -> None:
        """Ensure to_dict() output can be serialized to JSON."""
        batch = AssemblyBatchResult(
            results=[
                AssemblyResult(
                    panel_id="w1p0", wall_id="wall_1",
                    assembly_name="W1-P01", assembly_id=100,
                    element_count=5, views_created=["3D Orthographic"],
                    view_ids=[200],
                    sheet_id=300,
                    status="created",
                ),
            ],
            total_assemblies=1,
            successful=1,
            failed=0,
        )
        json_str = json.dumps(batch.to_dict())
        parsed = json.loads(json_str)
        assert parsed["summary"]["successful"] == 1
        assert parsed["assemblies"][0]["views_created"] == ["3D Orthographic"]
        assert parsed["assemblies"][0]["view_ids"] == [200]
        assert parsed["assemblies"][0]["sheet_id"] == 300

    def test_batch_counts_consistency(self) -> None:
        """Verify that manual counts are consistent with result list."""
        results = [
            AssemblyResult(
                panel_id="p%d" % i, wall_id="w", assembly_name="W-P%02d" % i,
                status="created" if i % 2 == 0 else "failed",
            )
            for i in range(6)
        ]
        batch = AssemblyBatchResult(
            results=results,
            total_assemblies=6,
            successful=3,
            failed=3,
        )
        created = [r for r in batch.results if r.status == "created"]
        failed = [r for r in batch.results if r.status == "failed"]
        assert len(created) == batch.successful
        assert len(failed) == batch.failed
        assert batch.total_assemblies == len(batch.results)


# =============================================================================
# create_assemblies Tests (Mocked Revit API)
# =============================================================================

class TestCreateAssemblies:
    """Tests for create_assemblies() with mocked Revit API."""

    def test_returns_empty_when_revit_unavailable(self) -> None:
        """When REVIT_AVAILABLE is False, returns empty batch."""
        with patch(
            "src.timber_framing_generator.assemblies.assembly_creator.REVIT_AVAILABLE",
            False,
        ):
            from src.timber_framing_generator.assemblies.assembly_creator import (
                create_assemblies,
            )
            groups = [
                PanelElementGroup(
                    panel_id="w1p0", wall_id="wall_1", panel_index=0,
                    column_element_ids=["c1"],
                ),
            ]
            result = create_assemblies(MagicMock(), groups)
            assert result.total_assemblies == 0
            assert result.successful == 0

    def test_accepts_view_config_param(self) -> None:
        """Verify create_assemblies() accepts view_config without error."""
        with patch(
            "src.timber_framing_generator.assemblies.assembly_creator.REVIT_AVAILABLE",
            False,
        ):
            from src.timber_framing_generator.assemblies.assembly_creator import (
                create_assemblies,
            )
            from src.timber_framing_generator.assemblies.assembly_views import (
                AssemblyViewConfig,
            )
            groups = [
                PanelElementGroup(
                    panel_id="w1p0", wall_id="wall_1", panel_index=0,
                    column_element_ids=["c1"],
                ),
            ]
            config = AssemblyViewConfig(detail_level="Fine")
            result = create_assemblies(
                MagicMock(), groups,
                create_views=True,
                view_config=config,
            )
            # Returns empty because REVIT_AVAILABLE is False
            assert result.total_assemblies == 0

    def test_accepts_wall_directions_param(self) -> None:
        """Verify create_assemblies() accepts wall_directions without error."""
        with patch(
            "src.timber_framing_generator.assemblies.assembly_creator.REVIT_AVAILABLE",
            False,
        ):
            from src.timber_framing_generator.assemblies.assembly_creator import (
                create_assemblies,
            )
            groups = [
                PanelElementGroup(
                    panel_id="w1p0", wall_id="wall_1", panel_index=0,
                    column_element_ids=["c1"],
                ),
            ]
            directions = {"wall_1": {"x": 1.0, "y": 0.0, "z": 0.0}}
            result = create_assemblies(
                MagicMock(), groups,
                wall_directions=directions,
            )
            assert result.total_assemblies == 0

    def test_group_ordering_preserved_in_results(self) -> None:
        """Results maintain the same order as input groups."""
        groups = [
            PanelElementGroup(
                panel_id="wall_1_panel_%d" % i,
                wall_id="wall_1",
                panel_index=i,
                column_element_ids=["c%d" % i],
            )
            for i in range(3)
        ]
        # Without Revit, just verify the ordering concept at the data model level
        batch = AssemblyBatchResult()
        for g in groups:
            batch.results.append(
                AssemblyResult(
                    panel_id=g.panel_id,
                    wall_id=g.wall_id,
                    assembly_name="W1-P%02d" % (g.panel_index + 1),
                )
            )
        assert [r.panel_id for r in batch.results] == [
            "wall_1_panel_0", "wall_1_panel_1", "wall_1_panel_2",
        ]


# =============================================================================
# enrich_panels_with_framing_data Tests
# =============================================================================

class TestEnrichPanelsWithFramingData:
    """Tests for enrich_panels_with_framing_data()."""

    def _make_framing_json(self, elements):
        """Helper: build framing_json string from element dicts."""
        return json.dumps({"elements": elements})

    def _make_panels_json_wall_results(self, wall_results):
        """Helper: build panels_json as list of wall results."""
        return json.dumps(wall_results)

    def test_basic_enrichment(self) -> None:
        """Elements with panel_id populate the correct panel's element_ids."""
        panels_json = self._make_panels_json_wall_results([
            {
                "wall_id": "wall_1",
                "panels": [
                    {"id": "wall_1_panel_0", "u_start": 0, "u_end": 10, "element_ids": []},
                    {"id": "wall_1_panel_1", "u_start": 10, "u_end": 20, "element_ids": []},
                ],
            },
        ])
        framing_json = self._make_framing_json([
            {"id": "stud_1", "panel_id": "wall_1_panel_0"},
            {"id": "stud_2", "panel_id": "wall_1_panel_0"},
            {"id": "stud_3", "panel_id": "wall_1_panel_1"},
        ])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        p0 = result[0]["panels"][0]
        p1 = result[0]["panels"][1]

        assert sorted(p0["element_ids"]) == ["stud_1", "stud_2"]
        assert p1["element_ids"] == ["stud_3"]

    def test_no_panel_ids_returns_unchanged(self) -> None:
        """When framing elements have no panel_id, panels_json is unchanged."""
        panels_json = json.dumps([
            {
                "wall_id": "wall_1",
                "panels": [
                    {"id": "wall_1_panel_0", "u_start": 0, "u_end": 10, "element_ids": []},
                ],
            },
        ])
        framing_json = self._make_framing_json([
            {"id": "stud_1"},  # No panel_id
            {"id": "stud_2", "panel_id": None},
        ])

        result = enrich_panels_with_framing_data(panels_json, framing_json)
        parsed = json.loads(result)
        assert parsed[0]["panels"][0]["element_ids"] == []

    def test_multi_wall(self) -> None:
        """Enrichment works across multiple walls."""
        panels_json = self._make_panels_json_wall_results([
            {
                "wall_id": "wall_1",
                "panels": [
                    {"id": "w1p0", "u_start": 0, "u_end": 10, "element_ids": []},
                ],
            },
            {
                "wall_id": "wall_2",
                "panels": [
                    {"id": "w2p0", "u_start": 0, "u_end": 8, "element_ids": []},
                ],
            },
        ])
        framing_json = self._make_framing_json([
            {"id": "e1", "panel_id": "w1p0"},
            {"id": "e2", "panel_id": "w2p0"},
            {"id": "e3", "panel_id": "w2p0"},
        ])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        assert result[0]["panels"][0]["element_ids"] == ["e1"]
        assert sorted(result[1]["panels"][0]["element_ids"]) == ["e2", "e3"]

    def test_flat_panel_list_format(self) -> None:
        """Handles flat list of panel dicts (no wall_id wrapper)."""
        panels_json = json.dumps([
            {"id": "p0", "u_start": 0, "u_end": 10, "element_ids": []},
            {"id": "p1", "u_start": 10, "u_end": 20, "element_ids": []},
        ])
        framing_json = self._make_framing_json([
            {"id": "s1", "panel_id": "p0"},
            {"id": "s2", "panel_id": "p1"},
        ])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        assert result[0]["element_ids"] == ["s1"]
        assert result[1]["element_ids"] == ["s2"]

    def test_single_wall_result_format(self) -> None:
        """Handles single wall result dict: {"wall_id": ..., "panels": [...]}."""
        panels_json = json.dumps({
            "wall_id": "wall_1",
            "panels": [
                {"id": "wall_1_panel_0", "u_start": 0, "u_end": 10, "element_ids": []},
            ],
        })
        framing_json = self._make_framing_json([
            {"id": "e1", "panel_id": "wall_1_panel_0"},
        ])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        assert result["panels"][0]["element_ids"] == ["e1"]

    def test_empty_framing_elements(self) -> None:
        """Empty elements list returns panels unchanged."""
        panels_json = json.dumps([
            {
                "wall_id": "w1",
                "panels": [{"id": "p0", "element_ids": []}],
            },
        ])
        framing_json = self._make_framing_json([])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        assert result[0]["panels"][0]["element_ids"] == []

    def test_unmatched_panel_id_ignored(self) -> None:
        """Elements with panel_ids not in panels_json are silently skipped."""
        panels_json = json.dumps([
            {
                "wall_id": "w1",
                "panels": [{"id": "p0", "element_ids": []}],
            },
        ])
        framing_json = self._make_framing_json([
            {"id": "e1", "panel_id": "nonexistent_panel"},
            {"id": "e2", "panel_id": "p0"},
        ])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        assert result[0]["panels"][0]["element_ids"] == ["e2"]

    def test_overwrites_existing_empty_element_ids(self) -> None:
        """Enrichment replaces existing empty element_ids with actual IDs."""
        panels_json = json.dumps([
            {
                "wall_id": "w1",
                "panels": [{"id": "p0", "element_ids": []}],
            },
        ])
        framing_json = self._make_framing_json([
            {"id": "stud_1", "panel_id": "p0"},
            {"id": "plate_1", "panel_id": "p0"},
        ])

        result = json.loads(enrich_panels_with_framing_data(panels_json, framing_json))
        assert len(result[0]["panels"][0]["element_ids"]) == 2
