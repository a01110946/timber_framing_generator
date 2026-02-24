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
VIEWPORT_H_SPACING = 0.10  # Horizontal gap between viewports
VIEWPORT_V_SPACING = 0.10  # Vertical gap between rows

# Starting position: near top-left of ARCH D sheet (0,0 = lower-left)
# LAYOUT_START_X is the CENTER x of the first viewport. Set to half of
# APPROX_VIEW_WIDTH + left margin (0.15) so the left edge stays on the sheet.
# Sheet height 2.0'; graphical view half-height ~0.275'; start at 1.55
# so view top edge = 1.55 + 0.275 = 1.825 < 2.0 (stays within sheet)
LAYOUT_START_X = 0.40   # = left_margin(0.15) + half_view_width(0.275) ≈ 0.40
LAYOUT_START_Y = 1.55

# Max viewports per row before wrapping.
# 4 per row fits 7 graphical views (1 3D + 6 elevations) in 2 rows,
# avoiding the third-row break that previously skipped the last elevation.
MAX_PER_ROW = 4

# Approximate viewport sizes for layout calculation
# These only affect row-wrapping decisions, NOT actual viewport size.
# Reduced to fit 4 views per row within ARCH D sheet width (3.0').
# Row step = APPROX_VIEW_WIDTH + VIEWPORT_H_SPACING = 0.55 + 0.15 = 0.70
# 4 view centers: 0.40, 1.10, 1.80, 2.50 → right edge 2.775 < 3.0 ✓
APPROX_VIEW_WIDTH = 0.55
APPROX_VIEW_HEIGHT = 0.55
APPROX_SCHEDULE_WIDTH = 0.45  # Family(0.20) + Type(0.10) + Length(0.10) + margin
APPROX_SCHEDULE_HEIGHT = 0.50

# Fixed Y position for schedule/takeoff views (center of schedule row)
# Anchored near bottom of sheet regardless of how many graphical rows exist.
# At Y=0.30 center: top edge ~0.55, bottom edge ~0.05 (within 0 to 2.0 sheet)
LAYOUT_SCHEDULE_Y = 0.60

# Minimum Y for graphical view rows — stop adding rows if Y would drop below
# this to avoid overlapping the schedule area.
LAYOUT_MIN_GRAPHICAL_Y = 0.65


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

    # Graphical views in rows of MAX_PER_ROW.
    # Stop adding rows if Y would drop into the schedule area (LAYOUT_MIN_GRAPHICAL_Y).
    x = LAYOUT_START_X
    y = LAYOUT_START_Y

    for i, vi in enumerate(graphical_views):
        if i > 0 and i % MAX_PER_ROW == 0:
            new_y = y - (APPROX_VIEW_HEIGHT + VIEWPORT_V_SPACING)
            if new_y < LAYOUT_MIN_GRAPHICAL_Y:
                # No room for another graphical row — skip remaining views
                print(
                    "[assembly_sheets] Layout: stopping at %d graphical views "
                    "(Y=%.2f would be below min %.2f)" % (i, new_y, LAYOUT_MIN_GRAPHICAL_Y)
                )
                break
            x = LAYOUT_START_X
            y = new_y

        positions.append((vi.view_id, x, y, "graphical"))
        x += APPROX_VIEW_WIDTH + VIEWPORT_H_SPACING

    # Schedule/takeoff views at a fixed bottom position (LAYOUT_SCHEDULE_Y).
    # This is independent of how many graphical rows were placed above.
    if schedule_views:
        x = LAYOUT_START_X
        for vi in schedule_views:
            positions.append((vi.view_id, x, LAYOUT_SCHEDULE_Y, vi.view_type))
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
