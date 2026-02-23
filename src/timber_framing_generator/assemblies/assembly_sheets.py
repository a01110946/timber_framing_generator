# File: src/timber_framing_generator/assemblies/assembly_sheets.py
"""Assembly sheet creation with viewport layout for Revit Assemblies.

Creates one Sheet per assembly with all views placed as viewports in a
grid layout. Supports optional title blocks.

CRITICAL: Sheet creation must happen within an active transaction, AFTER
assembly views have been created.

Usage:
    from src.timber_framing_generator.assemblies.assembly_sheets import (
        SheetResult,
        create_assembly_sheet,
    )

    sheet = create_assembly_sheet(
        doc, assembly_id, view_infos,
        titleblock_name="E1 30x42 Horizontal",
        assembly_name="W1-P01",
    )
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Conditional Revit Imports
# =============================================================================

REVIT_AVAILABLE = False
REVIT_ERROR: Optional[str] = None

try:
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        AssemblyViewUtils,
        BuiltInCategory,
        ElementId,
        FilteredElementCollector,
        ScheduleSheetInstance,
        Viewport,
        XYZ,
    )
    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_ERROR = str(e)
except Exception as e:
    REVIT_ERROR = str(e)


def _eid_int(element_id: Any) -> int:
    """Version-safe ElementId integer conversion (Revit 2025+ removed IntegerValue)."""
    if hasattr(element_id, "Value"):
        return int(element_id.Value)
    return int(element_id.IntegerValue)


# =============================================================================
# Layout Constants (in feet)
# =============================================================================

# Viewport spacing (in feet, for ARCH D 24"x36" = 2.0' x 3.0' sheet)
VIEWPORT_H_SPACING = 0.25  # Horizontal gap between viewports
VIEWPORT_V_SPACING = 0.25  # Vertical gap between rows

# Starting position: near top-left of ARCH D sheet (0,0 = lower-left)
# Sheet height ~2.0 ft; start 0.3 ft from top = Y=1.7
LAYOUT_START_X = 0.2
LAYOUT_START_Y = 1.7

# Max viewports per row before wrapping
MAX_PER_ROW = 3

# Approximate viewport sizes for layout calculation
APPROX_VIEW_WIDTH = 0.9
APPROX_VIEW_HEIGHT = 0.7
APPROX_SCHEDULE_WIDTH = 0.9
APPROX_SCHEDULE_HEIGHT = 0.5


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SheetResult:
    """Result of creating a single assembly sheet.

    Attributes:
        sheet_id: Revit ElementId integer of the created sheet
        sheet_name: Display name of the sheet
        viewport_count: Number of viewports placed on the sheet
    """
    sheet_id: int
    sheet_name: str
    viewport_count: int


# =============================================================================
# Helpers
# =============================================================================

def _find_titleblock(doc: Any, name: str) -> Any:
    """Find a title block FamilySymbol by name.

    Searches the document for title block types matching the given name.

    Args:
        doc: Revit Document object
        name: Title block family or type name to search for

    Returns:
        ElementId of the title block, or ElementId.InvalidElementId if
        not found or name is empty
    """
    if not REVIT_AVAILABLE:
        return None

    if not name or not name.strip():
        return ElementId.InvalidElementId

    try:
        collector = FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_TitleBlocks,
        ).WhereElementIsElementType()

        for tb in collector:
            # Match by type name or family name
            if tb.Name == name:
                return tb.Id
            family = tb.Family
            if family and family.Name == name:
                return tb.Id

    except Exception as e:
        print("[assembly_sheets] Error finding title block '%s': %s" % (name, e))

    print("[assembly_sheets] Title block '%s' not found, using none" % name)
    return ElementId.InvalidElementId


def _calculate_viewport_layout(
    view_infos: List[Any],
) -> List[Tuple[Any, float, float, str]]:
    """Calculate grid positions for viewports on a sheet.

    Groups views by type into rows:
    - Row 1+: 3D + elevation views (max MAX_PER_ROW per row)
    - Final row: Schedules and takeoffs

    Args:
        view_infos: List of CreatedViewInfo objects with view_id and view_type

    Returns:
        List of (view_id, x, y, view_type) tuples for placement.
        view_type is "schedule"/"takeoff" for schedule views, else "graphical".
    """
    # Separate views by type
    graphical_views = []  # 3d + elevation
    schedule_views = []   # schedule + takeoff

    for vi in view_infos:
        if vi.view_id is None:
            continue
        if vi.view_type in ("3d", "elevation"):
            graphical_views.append(vi)
        elif vi.view_type in ("schedule", "takeoff"):
            schedule_views.append(vi)

    positions: List[Tuple[Any, float, float, str]] = []

    # Graphical views in rows of MAX_PER_ROW
    x = LAYOUT_START_X
    y = LAYOUT_START_Y

    for i, vi in enumerate(graphical_views):
        if i > 0 and i % MAX_PER_ROW == 0:
            x = LAYOUT_START_X
            y -= (APPROX_VIEW_HEIGHT + VIEWPORT_V_SPACING)

        positions.append((vi.view_id, x, y, "graphical"))
        x += APPROX_VIEW_WIDTH + VIEWPORT_H_SPACING

    # Schedule views in next row
    if schedule_views:
        if graphical_views:
            y -= (APPROX_VIEW_HEIGHT + VIEWPORT_V_SPACING)
        x = LAYOUT_START_X

        for vi in schedule_views:
            positions.append((vi.view_id, x, y, vi.view_type))
            x += APPROX_SCHEDULE_WIDTH + VIEWPORT_H_SPACING

    return positions


# =============================================================================
# Sheet Creation
# =============================================================================

def create_assembly_sheet(
    doc: Any,
    assembly_id: Any,
    view_infos: List[Any],
    titleblock_name: str = "",
    assembly_name: str = "",
) -> Optional[SheetResult]:
    """Create a sheet for an assembly and place all views as viewports.

    Must be called inside an active transaction.

    Args:
        doc: Revit Document object
        assembly_id: ElementId of the AssemblyInstance
        view_infos: List of CreatedViewInfo from create_assembly_views()
        titleblock_name: Title block family name (empty = no title block)
        assembly_name: Assembly name for the sheet title

    Returns:
        SheetResult if successful, None if failed
    """
    if not REVIT_AVAILABLE:
        print("[assembly_sheets] REVIT_AVAILABLE=False, skipping sheet: %s" % REVIT_ERROR)
        return None

    if not view_infos:
        print("[assembly_sheets] No views to place on sheet")
        return None

    try:
        # Find title block
        tb_id = _find_titleblock(doc, titleblock_name)

        # Create assembly sheet
        sheet = AssemblyViewUtils.CreateSheet(doc, assembly_id, tb_id)
        if sheet is None:
            print("[assembly_sheets] CreateSheet returned None")
            return None

        sheet_name = assembly_name or "Assembly Sheet"
        print(
            "[assembly_sheets] Created sheet '%s' (id=%s)"
            % (sheet_name, _eid_int(sheet.Id))
        )

        # Calculate viewport positions
        positions = _calculate_viewport_layout(view_infos)

        # Place viewports — schedules need ScheduleSheetInstance, not Viewport
        viewport_count = 0
        for view_id, x, y, vtype in positions:
            try:
                if vtype in ("schedule", "takeoff"):
                    # Schedules cannot use Viewport.Create; use ScheduleSheetInstance
                    ScheduleSheetInstance.Create(doc, sheet.Id, view_id, XYZ(x, y, 0))
                    viewport_count += 1
                elif Viewport.CanAddViewToSheet(doc, sheet.Id, view_id):
                    Viewport.Create(doc, sheet.Id, view_id, XYZ(x, y, 0))
                    viewport_count += 1
                else:
                    print(
                        "[assembly_sheets] Cannot add view %s to sheet"
                        % _eid_int(view_id)
                    )
            except Exception as e:
                print(
                    "[assembly_sheets] Failed to place viewport for view %s: %s"
                    % (_eid_int(view_id), e)
                )

        logger.info(
            "Created sheet '%s' with %d viewports",
            sheet_name, viewport_count,
        )

        return SheetResult(
            sheet_id=_eid_int(sheet.Id),
            sheet_name=sheet_name,
            viewport_count=viewport_count,
        )

    except Exception as e:
        print("[assembly_sheets] Failed to create sheet: %s" % e)
        return None
