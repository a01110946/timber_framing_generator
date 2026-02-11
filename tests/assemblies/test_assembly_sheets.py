# File: tests/assemblies/test_assembly_sheets.py
"""Tests for assembly sheet creation and viewport layout.

Tests cover SheetResult dataclass, _calculate_viewport_layout() with
various view combinations, and create_assembly_sheet() behavior when
Revit is unavailable.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.timber_framing_generator.assemblies.assembly_sheets import (
    SheetResult,
    _calculate_viewport_layout,
    LAYOUT_START_X,
    LAYOUT_START_Y,
    VIEWPORT_H_SPACING,
    VIEWPORT_V_SPACING,
    APPROX_VIEW_WIDTH,
    APPROX_VIEW_HEIGHT,
)
from src.timber_framing_generator.assemblies.assembly_views import (
    CreatedViewInfo,
)


# =============================================================================
# SheetResult Tests
# =============================================================================

class TestSheetResult:
    """Tests for SheetResult dataclass."""

    def test_basic_creation(self) -> None:
        sr = SheetResult(sheet_id=500, sheet_name="W1-P01", viewport_count=4)
        assert sr.sheet_id == 500
        assert sr.sheet_name == "W1-P01"
        assert sr.viewport_count == 4

    def test_zero_viewports(self) -> None:
        sr = SheetResult(sheet_id=501, sheet_name="Empty", viewport_count=0)
        assert sr.viewport_count == 0


# =============================================================================
# Viewport Layout Tests
# =============================================================================

class TestCalculateViewportLayout:
    """Tests for _calculate_viewport_layout()."""

    def test_empty_view_list(self) -> None:
        result = _calculate_viewport_layout([])
        assert result == []

    def test_single_3d_view(self) -> None:
        views = [
            CreatedViewInfo("3D Orthographic", view_id=1, view_type="3d"),
        ]
        result = _calculate_viewport_layout(views)
        assert len(result) == 1
        view_id, x, y = result[0]
        assert view_id == 1
        assert x == LAYOUT_START_X
        assert y == LAYOUT_START_Y

    def test_3d_plus_elevations(self) -> None:
        views = [
            CreatedViewInfo("3D Orthographic", view_id=1, view_type="3d"),
            CreatedViewInfo("Front Elevation", view_id=2, view_type="elevation"),
            CreatedViewInfo("Back Elevation", view_id=3, view_type="elevation"),
        ]
        result = _calculate_viewport_layout(views)
        assert len(result) == 3
        # All should be on the same row (y = LAYOUT_START_Y)
        for _, x, y in result:
            assert y == LAYOUT_START_Y
        # X positions should increase
        xs = [x for _, x, _ in result]
        assert xs[0] < xs[1] < xs[2]

    def test_overflow_to_second_row(self) -> None:
        """More than 4 graphical views should wrap to a second row."""
        views = [
            CreatedViewInfo("3D", view_id=i, view_type="3d" if i == 0 else "elevation")
            for i in range(6)
        ]
        result = _calculate_viewport_layout(views)
        assert len(result) == 6

        # First 4 on row 1
        row1_ys = [y for _, _, y in result[:4]]
        assert all(y == LAYOUT_START_Y for y in row1_ys)

        # Next 2 on row 2 (lower y)
        row2_ys = [y for _, _, y in result[4:]]
        expected_row2_y = LAYOUT_START_Y - (APPROX_VIEW_HEIGHT + VIEWPORT_V_SPACING)
        assert all(abs(y - expected_row2_y) < 0.01 for y in row2_ys)

    def test_schedules_on_separate_row(self) -> None:
        """Schedule views should be placed below graphical views."""
        views = [
            CreatedViewInfo("3D", view_id=1, view_type="3d"),
            CreatedViewInfo("Front", view_id=2, view_type="elevation"),
            CreatedViewInfo("Takeoff", view_id=3, view_type="takeoff"),
            CreatedViewInfo("Schedule", view_id=4, view_type="schedule"),
        ]
        result = _calculate_viewport_layout(views)
        assert len(result) == 4

        # Graphical views (3d + elevation) on row 1
        graphical_ys = [y for vid, _, y in result if vid in (1, 2)]
        assert all(y == LAYOUT_START_Y for y in graphical_ys)

        # Schedule views on a lower row
        schedule_ys = [y for vid, _, y in result if vid in (3, 4)]
        assert all(y < LAYOUT_START_Y for y in schedule_ys)

    def test_only_schedules(self) -> None:
        """When only schedules exist, they start at LAYOUT_START_Y."""
        views = [
            CreatedViewInfo("Takeoff", view_id=1, view_type="takeoff"),
        ]
        result = _calculate_viewport_layout(views)
        assert len(result) == 1
        _, _, y = result[0]
        assert y == LAYOUT_START_Y

    def test_skips_views_with_none_id(self) -> None:
        """Views with None view_id are skipped."""
        views = [
            CreatedViewInfo("3D", view_id=1, view_type="3d"),
            CreatedViewInfo("Missing", view_id=None, view_type="elevation"),
            CreatedViewInfo("Front", view_id=3, view_type="elevation"),
        ]
        result = _calculate_viewport_layout(views)
        assert len(result) == 2
        ids = [vid for vid, _, _ in result]
        assert ids == [1, 3]


# =============================================================================
# create_assembly_sheet Tests (Mocked Revit)
# =============================================================================

class TestCreateAssemblySheet:
    """Tests for create_assembly_sheet() with mocked Revit API."""

    def test_returns_none_when_revit_unavailable(self) -> None:
        """When REVIT_AVAILABLE is False, returns None."""
        with patch(
            "src.timber_framing_generator.assemblies.assembly_sheets.REVIT_AVAILABLE",
            False,
        ):
            from src.timber_framing_generator.assemblies.assembly_sheets import (
                create_assembly_sheet,
            )
            views = [
                CreatedViewInfo("3D", view_id=MagicMock(), view_type="3d"),
            ]
            result = create_assembly_sheet(
                MagicMock(), MagicMock(), views,
                assembly_name="W1-P01",
            )
            assert result is None

    def test_returns_none_for_empty_views(self) -> None:
        """Empty view list returns None."""
        with patch(
            "src.timber_framing_generator.assemblies.assembly_sheets.REVIT_AVAILABLE",
            False,
        ):
            from src.timber_framing_generator.assemblies.assembly_sheets import (
                create_assembly_sheet,
            )
            result = create_assembly_sheet(
                MagicMock(), MagicMock(), [],
                assembly_name="W1-P01",
            )
            assert result is None
