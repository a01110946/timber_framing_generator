# File: src/timber_framing_generator/assemblies/assembly_views.py
"""Assembly view creation utilities for Revit Assemblies.

Creates standard assembly views (3D orthographic, detail sections, structural
schedules, material takeoffs) using AssemblyViewUtils. All views are optional
and configurable via AssemblyViewConfig.

Provides AssemblyViewConfig for controlling which views to create, detail
level, display style, schedule fields, view templates, and section marker
visibility.

CRITICAL: Assembly views can only be created AFTER the assembly creation
transaction has been committed. The assembly type must exist before views
can be generated.

Usage:
    from src.timber_framing_generator.assemblies.assembly_views import (
        AssemblyViewConfig,
        CreatedViewInfo,
        create_assembly_views,
    )

    config = AssemblyViewConfig(detail_level="Fine", display_style="HiddenLine")
    view_infos = create_assembly_views(doc, assembly.Id, config=config)
    for vi in view_infos:
        print(vi.view_name, vi.view_type)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
        AssemblyDetailViewOrientation,
        BuiltInCategory,
        DisplayStyle,
        ElementId,
        FilteredElementCollector,
        View,
        ViewDetailLevel,
    )
    REVIT_AVAILABLE = True
    print("[assembly_views] Revit API imports OK")
except ImportError as e:
    REVIT_ERROR = str(e)
    print("[assembly_views] ImportError: %s" % e)
except Exception as e:
    REVIT_ERROR = str(e)
    print("[assembly_views] Error: %s" % e)


def _eid_int(element_id: Any) -> int:
    """Version-safe ElementId integer conversion (Revit 2025+ removed IntegerValue)."""
    if hasattr(element_id, "Value"):
        return int(element_id.Value)
    return int(element_id.IntegerValue)


# =============================================================================
# Configuration
# =============================================================================

# String -> Revit enum attribute name mapping (resolved at runtime)
DETAIL_LEVEL_MAP: Dict[str, str] = {
    "Coarse": "Coarse",
    "Medium": "Medium",
    "Fine": "Fine",
}

DISPLAY_STYLE_MAP: Dict[str, str] = {
    "Wireframe": "Wireframe",
    "HiddenLine": "HLR",
    "Shaded": "Shading",
    "Shaded with Edges": "ShadingWithEdges",
    "Consistent Colors": "FlatColors",
    "Realistic": "Realistic",
    "Realistic with Edges": "RealisticWithEdges",
}

# Default schedule field lists
# Column schedule uses "Length" (the instance length parameter);
# Framing schedule uses "Cut Length" (the fabrication cut length).
DEFAULT_COLUMN_SCHEDULE_FIELDS: List[str] = ["Family", "Type", "System Length"]
DEFAULT_FRAMING_SCHEDULE_FIELDS: List[str] = ["Family", "Type", "Cut Length"]
DEFAULT_TAKEOFF_FIELDS: List[str] = ["Type", "Count", "Material: Name", "Material: Area"]

# Schedule column widths in feet (sheet coordinates).
# Revit default is ~0.083' (1"). Widen "Family" to fit "TFG_Timber_Framing"
# without wrapping (18 chars at 3/32" ≈ 1.7" minimum → use 0.50' = 6").
FAMILY_COLUMN_WIDTH: float = 0.20
TYPE_COLUMN_WIDTH: float = 0.10
LENGTH_COLUMN_WIDTH: float = 0.10

# Map from field name to desired SheetColumnWidth (feet).
# Revit 2024+ uses SheetColumnWidth (on-sheet) and GridColumnWidth (view).
# Fields not listed here keep Revit's default width.
SCHEDULE_COLUMN_WIDTHS: Dict[str, float] = {
    "Family": FAMILY_COLUMN_WIDTH,
    "Type": TYPE_COLUMN_WIDTH,
    "Length": LENGTH_COLUMN_WIDTH,
    "Cut Length": LENGTH_COLUMN_WIDTH,
    "System Length": LENGTH_COLUMN_WIDTH,
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CreatedViewInfo:
    """Information about a successfully created assembly view.

    Attributes:
        view_name: Human-readable name (e.g., "Front Elevation", "3D Orthographic")
        view_id: Revit ElementId of the created view (None in tests)
        view_type: Category string: "3d", "elevation", "schedule", "takeoff"
    """
    view_name: str
    view_id: Any = None
    view_type: str = "elevation"


@dataclass
class AssemblyViewConfig:
    """Configuration for assembly view creation.

    Controls which views to create and their visual settings. All new fields
    have backward-compatible defaults -- old JSON with only 6 keys still works
    via .get() defaults in from_dict().

    Attributes:
        include_3d: Create 3D orthographic view
        include_front_elevation: Create front elevation section
        include_top_elevation: Create top elevation section
        include_material_takeoff: Create material takeoff schedule
        detail_level: View detail level ("Coarse", "Medium", "Fine")
        display_style: View display style (see DISPLAY_STYLE_MAP keys)
        include_back_elevation: Create back elevation section
        include_bottom_elevation: Create bottom elevation section
        include_left_elevation: Create left elevation section
        include_right_elevation: Create right elevation section
        include_column_schedule: Create structural column schedule
        include_framing_schedule: Create structural framing schedule
        schedule_fields: Comma-separated field names for structural schedules
        schedule_template_name: View template name for structural schedules
        takeoff_fields: Comma-separated field names for material takeoff
        takeoff_template_name: View template name for material takeoff
        hide_section_markers: Hide section markers in elevation views
        include_sheet: Create a sheet with all views as viewports
        titleblock_name: Title block family name for sheet creation
    """
    # Original fields (backward-compatible)
    include_3d: bool = True
    include_front_elevation: bool = True
    include_top_elevation: bool = False
    include_material_takeoff: bool = False
    detail_level: str = "Fine"
    display_style: str = "HiddenLine"

    # R1: New elevations
    include_back_elevation: bool = False
    include_bottom_elevation: bool = False
    include_left_elevation: bool = False
    include_right_elevation: bool = False

    # R2: Structural schedules
    include_column_schedule: bool = False
    include_framing_schedule: bool = False
    schedule_fields: str = ""
    schedule_template_name: str = ""

    # R3: Material takeoff field config
    takeoff_fields: str = ""
    takeoff_template_name: str = ""

    # R5: Section markers
    hide_section_markers: bool = True

    # R7: Sheet
    include_sheet: bool = False
    titleblock_name: str = ""

    # R8: View scale (Revit scale denominator: 96 = 1/8"=1'-0", 48 = 1/4", 24 = 1/2")
    view_scale: int = 96

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]] = None) -> "AssemblyViewConfig":
        """Create config from a dictionary, using defaults for missing keys.

        Backward-compatible: old 6-key dicts produce valid configs with new
        fields at their defaults.

        Args:
            data: Dictionary with config keys. None or empty dict gives defaults.

        Returns:
            AssemblyViewConfig instance
        """
        if not data:
            return cls()

        return cls(
            # Original fields
            include_3d=data.get("include_3d", True),
            include_front_elevation=data.get("include_front_elevation", True),
            include_top_elevation=data.get("include_top_elevation", False),
            include_material_takeoff=data.get("include_material_takeoff", False),
            detail_level=data.get("detail_level", "Fine"),
            display_style=data.get("display_style", "HiddenLine"),
            # New elevations
            include_back_elevation=data.get("include_back_elevation", False),
            include_bottom_elevation=data.get("include_bottom_elevation", False),
            include_left_elevation=data.get("include_left_elevation", False),
            include_right_elevation=data.get("include_right_elevation", False),
            # Structural schedules
            include_column_schedule=data.get("include_column_schedule", False),
            include_framing_schedule=data.get("include_framing_schedule", False),
            schedule_fields=data.get("schedule_fields", ""),
            schedule_template_name=data.get("schedule_template_name", ""),
            # Material takeoff config
            takeoff_fields=data.get("takeoff_fields", ""),
            takeoff_template_name=data.get("takeoff_template_name", ""),
            # Section markers
            hide_section_markers=data.get("hide_section_markers", True),
            # Sheet
            include_sheet=data.get("include_sheet", False),
            titleblock_name=data.get("titleblock_name", ""),
            # View scale
            view_scale=int(data.get("view_scale", 96)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary with all config fields
        """
        return {
            "include_3d": self.include_3d,
            "include_front_elevation": self.include_front_elevation,
            "include_top_elevation": self.include_top_elevation,
            "include_material_takeoff": self.include_material_takeoff,
            "detail_level": self.detail_level,
            "display_style": self.display_style,
            "include_back_elevation": self.include_back_elevation,
            "include_bottom_elevation": self.include_bottom_elevation,
            "include_left_elevation": self.include_left_elevation,
            "include_right_elevation": self.include_right_elevation,
            "include_column_schedule": self.include_column_schedule,
            "include_framing_schedule": self.include_framing_schedule,
            "schedule_fields": self.schedule_fields,
            "schedule_template_name": self.schedule_template_name,
            "takeoff_fields": self.takeoff_fields,
            "takeoff_template_name": self.takeoff_template_name,
            "hide_section_markers": self.hide_section_markers,
            "include_sheet": self.include_sheet,
            "titleblock_name": self.titleblock_name,
            "view_scale": self.view_scale,
        }


# =============================================================================
# Helpers
# =============================================================================

def _parse_field_names(csv_string: str, defaults: List[str]) -> List[str]:
    """Parse comma-separated field names, falling back to defaults if empty.

    Args:
        csv_string: Comma-separated field names (may be empty)
        defaults: Default field list if csv_string is empty

    Returns:
        List of stripped, non-empty field name strings
    """
    if not csv_string or not csv_string.strip():
        return list(defaults)
    return [f.strip() for f in csv_string.split(",") if f.strip()]


def _hide_section_markers(view: Any) -> None:
    """Hide section markers (detail view symbols) in an elevation view.

    Must be called inside an active transaction.

    Args:
        view: Revit ViewSection object
    """
    if not REVIT_AVAILABLE or view is None:
        return
    try:
        view.SetCategoryHidden(
            ElementId(BuiltInCategory.OST_Sections), True,
        )
    except Exception as e:
        print("[assembly_views] Could not hide section markers: %s" % e)


def _find_view_template(doc: Any, template_name: str) -> Any:
    """Find a view template by name in the Revit document.

    Args:
        doc: Revit Document object
        template_name: Name of the view template to find

    Returns:
        ElementId of the template, or None if not found
    """
    if not REVIT_AVAILABLE or not template_name:
        return None
    try:
        collector = FilteredElementCollector(doc).OfClass(View)
        for v in collector:
            if v.IsTemplate and v.Name == template_name:
                return v.Id
    except Exception as e:
        print("[assembly_views] Error searching for template '%s': %s" % (template_name, e))
    return None


def _apply_view_template(view: Any, template_id: Any) -> None:
    """Apply a view template to a view.

    Args:
        view: Revit View object
        template_id: ElementId of the view template (or None to skip)
    """
    if template_id is None or view is None:
        return
    try:
        view.ViewTemplateId = template_id
    except Exception as e:
        print("[assembly_views] Could not apply template: %s" % e)


def _set_field_column_width_reflection(sf: Any, col_name: str, desired_width: float) -> bool:
    """Set ScheduleField.ColumnWidth via .NET reflection.

    pythonnet cannot resolve ScheduleField.ColumnWidth as a Python attribute
    (AttributeError), and setting it directly on AddField() return values is a
    silent no-op (pythonnet adds a Python-level attribute, never calls the C#
    setter).  Reflection bypasses pythonnet's binding layer entirely and calls
    the .NET property setter directly.

    Args:
        sf: Revit ScheduleField object (from GetField(), not AddField() return)
        col_name: Field name for logging
        desired_width: Column width in feet

    Returns:
        True if width was set, False otherwise
    """
    try:
        # Revit 2024+ split ColumnWidth into GridColumnWidth (schedule view) and
        # SheetColumnWidth (schedule placed on a sheet).  Use SheetColumnWidth.
        prop = sf.GetType().GetProperty("SheetColumnWidth")
        if prop is not None and prop.CanWrite:
            prop.SetValue(sf, float(desired_width))
            print("[assembly_views] Set '%s' SheetColumnWidth=%.3f ft" % (col_name, desired_width))
            return True
        if prop is None:
            all_props = sorted(p.Name for p in sf.GetType().GetProperties())
            print("[assembly_views] SheetColumnWidth not found on ScheduleField. Has: %s" % all_props)
        else:
            print("[assembly_views] SheetColumnWidth property is read-only for '%s'" % col_name)
    except Exception as ref_err:
        print("[assembly_views] Reflection error for '%s': %s %s" % (col_name, type(ref_err).__name__, ref_err))
    return False


def _configure_schedule_fields(
    doc: Any,
    schedule: Any,
    field_names: List[str],
) -> None:
    """Configure fields on a schedule view and set column widths.

    Clears existing fields, adds requested fields in order, then applies
    column-width overrides via .NET reflection.

    Key discoveries (diagnosed 2026-02):
    - AddField() return value is NOT a ScheduleFieldId — passing it to
      GetField() causes TypeError.  Do NOT use the AddField() return value.
    - ScheduleField.ColumnWidth raises AttributeError via pythonnet direct
      attribute access; sf.ColumnWidth = x on AddField() return is a silent
      no-op (pythonnet sets Python attr, never calls C# setter).
    - Fix: add all fields first, then use GetFieldOrder() + GetField() for
      live references, then set width via reflection.

    Args:
        doc: Revit Document object
        schedule: Revit ViewSchedule object
        field_names: List of field names to add
    """
    if not REVIT_AVAILABLE or schedule is None or not field_names:
        return

    try:
        definition = schedule.Definition

        # Build lookup: field name -> SchedulableField
        available = {}
        for sf in definition.GetSchedulableFields():
            name = sf.GetName(doc)
            available[name] = sf

        # Clear existing fields
        definition.ClearFields()

        # Add requested fields; discard AddField() return value (unreliable type)
        added_names = []
        for name in field_names:
            if name in available:
                definition.AddField(available[name])
                added_names.append(name)
            else:
                print("[assembly_views] Schedule field '%s' not found, skipping" % name)

        # Set column widths: get live ScheduleField refs via GetFieldOrder() +
        # GetField(), then set ColumnWidth via .NET reflection.
        try:
            field_ids = list(definition.GetFieldOrder())
            for i, fid in enumerate(field_ids):
                if i >= len(added_names):
                    break
                col_name = added_names[i]
                desired_width = SCHEDULE_COLUMN_WIDTHS.get(col_name)
                if desired_width is None:
                    continue
                try:
                    live_sf = definition.GetField(fid)
                    if live_sf is not None:
                        _set_field_column_width_reflection(live_sf, col_name, desired_width)
                except Exception as gf_err:
                    print("[assembly_views] GetField error for '%s': %s" % (col_name, gf_err))
        except Exception as fo_err:
            print("[assembly_views] GetFieldOrder error: %s" % fo_err)

    except Exception as e:
        print("[assembly_views] _configure_schedule_fields failed: %s %s" % (type(e).__name__, e))


# =============================================================================
# View Settings
# =============================================================================

def _apply_view_scale(view: Any, scale: int) -> None:
    """Apply a view scale to a graphical view (3D or elevation).

    Silently skips if scale is invalid or the view does not support scaling.

    Args:
        view: Revit View object (View3D or ViewSection)
        scale: Revit scale denominator (96 = 1/8"=1'-0", 48 = 1/4", 24 = 1/2")
    """
    if not REVIT_AVAILABLE or view is None or scale <= 0:
        return
    try:
        view.Scale = scale
    except Exception as e:
        print("[assembly_views] Could not set Scale %d: %s" % (scale, e))


def _apply_view_settings(
    view: Any,
    detail_level: str,
    display_style: str,
) -> None:
    """Apply detail level and display style to a view.

    Maps string config values to Revit enum values and sets them on the view.
    Silently skips if Revit API is not available or mapping fails.

    Args:
        view: Revit View object (View3D or ViewSection)
        detail_level: String key ("Coarse", "Medium", "Fine")
        display_style: String key (see DISPLAY_STYLE_MAP)
    """
    if not REVIT_AVAILABLE or view is None:
        return

    # Apply detail level
    try:
        level_attr = DETAIL_LEVEL_MAP.get(detail_level, "Fine")
        revit_level = getattr(ViewDetailLevel, level_attr, None)
        if revit_level is not None:
            view.DetailLevel = revit_level
    except Exception as e:
        print("[assembly_views] Could not set DetailLevel '%s': %s" % (detail_level, e))

    # Apply display style
    try:
        style_attr = DISPLAY_STYLE_MAP.get(display_style, "HLR")
        revit_style = getattr(DisplayStyle, style_attr, None)
        if revit_style is not None:
            view.DisplayStyle = revit_style
    except Exception as e:
        print("[assembly_views] Could not set DisplayStyle '%s': %s" % (display_style, e))


# =============================================================================
# View Creation
# =============================================================================

def create_assembly_views(
    doc: Any,
    assembly_id: Any,
    config: Optional[AssemblyViewConfig] = None,
) -> List[CreatedViewInfo]:
    """Create standard assembly views for a given assembly instance.

    Must be called within an active transaction, AFTER the assembly creation
    transaction has been committed.

    Creates views in order: 3D, elevations, material takeoff, structural
    schedules. Each view is optional based on config flags.

    Args:
        doc: Revit Document object
        assembly_id: ElementId of the AssemblyInstance
        config: View configuration. If None, uses defaults (3D + Front Elevation,
            Fine detail, HiddenLine display).

    Returns:
        List of CreatedViewInfo for successfully created views
    """
    if not REVIT_AVAILABLE:
        print("[assembly_views] REVIT_AVAILABLE=False, skipping views: %s" % REVIT_ERROR)
        return []

    if config is None:
        config = AssemblyViewConfig()

    created: List[CreatedViewInfo] = []

    # Pre-parse field name lists (column and framing schedules have different defaults)
    column_schedule_field_names = _parse_field_names(
        config.schedule_fields, DEFAULT_COLUMN_SCHEDULE_FIELDS,
    )
    framing_schedule_field_names = _parse_field_names(
        config.schedule_fields, DEFAULT_FRAMING_SCHEDULE_FIELDS,
    )
    takeoff_field_names = _parse_field_names(
        config.takeoff_fields, DEFAULT_TAKEOFF_FIELDS,
    )

    # Pre-resolve view templates
    schedule_template_id = _find_view_template(doc, config.schedule_template_name)
    takeoff_template_id = _find_view_template(doc, config.takeoff_template_name)

    # --- 1. 3D Orthographic ---
    if config.include_3d:
        view = _create_3d_orthographic(doc, assembly_id)
        if view:
            _apply_view_settings(view, config.detail_level, config.display_style)
            _apply_view_scale(view, config.view_scale)
            created.append(CreatedViewInfo("3D Orthographic", view.Id, "3d"))

    # --- 2-7. Elevation Views ---
    elevation_specs = [
        (config.include_front_elevation, "ElevationFront", "Front Elevation"),
        (config.include_back_elevation, "ElevationBack", "Back Elevation"),
        (config.include_top_elevation, "ElevationTop", "Top Elevation"),
        (config.include_bottom_elevation, "ElevationBottom", "Bottom Elevation"),
        (config.include_left_elevation, "ElevationLeft", "Left Elevation"),
        (config.include_right_elevation, "ElevationRight", "Right Elevation"),
    ]

    for include_flag, orientation_attr, label in elevation_specs:
        if not include_flag:
            continue
        orientation = getattr(AssemblyDetailViewOrientation, orientation_attr, None)
        if orientation is None:
            print("[assembly_views] Unknown orientation: %s" % orientation_attr)
            continue
        view = _create_detail_section(doc, assembly_id, orientation, label)
        if view:
            _apply_view_settings(view, config.detail_level, config.display_style)
            _apply_view_scale(view, config.view_scale)
            if config.hide_section_markers:
                _hide_section_markers(view)
            created.append(CreatedViewInfo(label, view.Id, "elevation"))

    # --- 8. Material Takeoff ---
    if config.include_material_takeoff:
        view = _create_material_takeoff(
            doc, assembly_id, takeoff_field_names, takeoff_template_id,
        )
        if view:
            created.append(CreatedViewInfo("Material Takeoff", view.Id, "takeoff"))

    # --- 9. Structural Column Schedule ---
    if config.include_column_schedule:
        view = _create_single_category_schedule(
            doc, assembly_id,
            BuiltInCategory.OST_StructuralColumns,
            "Structural Column Schedule",
            column_schedule_field_names,   # uses "Length" not "Cut Length"
            schedule_template_id,
        )
        if view:
            created.append(CreatedViewInfo(
                "Structural Column Schedule", view.Id, "schedule",
            ))

    # --- 10. Structural Framing Schedule ---
    if config.include_framing_schedule:
        view = _create_single_category_schedule(
            doc, assembly_id,
            BuiltInCategory.OST_StructuralFraming,
            "Structural Framing Schedule",
            framing_schedule_field_names,  # uses "Cut Length"
            schedule_template_id,
        )
        if view:
            created.append(CreatedViewInfo(
                "Structural Framing Schedule", view.Id, "schedule",
            ))

    logger.info(
        "Created %d views for assembly %s: %s",
        len(created),
        _eid_int(assembly_id),
        ", ".join(vi.view_name for vi in created),
    )
    return created


# =============================================================================
# Individual View Creators
# =============================================================================

def _create_3d_orthographic(doc: Any, assembly_id: Any) -> Any:
    """Create a 3D orthographic assembly view.

    Args:
        doc: Revit Document object
        assembly_id: ElementId of the AssemblyInstance

    Returns:
        Created View3D or None if failed
    """
    try:
        view = AssemblyViewUtils.Create3DOrthographic(doc, assembly_id)
        print("[assembly_views] Created 3D view for %s" % _eid_int(assembly_id))
        return view
    except Exception as e:
        print("[assembly_views] Failed 3D view: %s" % e)
        return None


def _create_detail_section(
    doc: Any,
    assembly_id: Any,
    orientation: Any,
    label: str,
) -> Any:
    """Create a detail section assembly view with given orientation.

    Args:
        doc: Revit Document object
        assembly_id: ElementId of the AssemblyInstance
        orientation: AssemblyDetailViewOrientation enum value
        label: Human-readable label for logging

    Returns:
        Created ViewSection or None if failed
    """
    try:
        view = AssemblyViewUtils.CreateDetailSection(
            doc, assembly_id, orientation,
        )
        print("[assembly_views] Created %s for %s" % (label, _eid_int(assembly_id)))
        return view
    except Exception as e:
        print("[assembly_views] Failed %s: %s" % (label, e))
        return None


def _create_material_takeoff(
    doc: Any,
    assembly_id: Any,
    field_names: Optional[List[str]] = None,
    template_id: Any = None,
) -> Any:
    """Create a material takeoff schedule for the assembly.

    Args:
        doc: Revit Document object
        assembly_id: ElementId of the AssemblyInstance
        field_names: Optional list of field names to configure
        template_id: Optional view template ElementId to apply

    Returns:
        Created ViewSchedule or None if failed
    """
    try:
        view = AssemblyViewUtils.CreateMaterialTakeoff(doc, assembly_id)
        print("[assembly_views] Created takeoff for %s" % _eid_int(assembly_id))

        if field_names:
            _configure_schedule_fields(doc, view, field_names)
        if template_id is not None:
            _apply_view_template(view, template_id)

        return view
    except Exception as e:
        print("[assembly_views] Failed takeoff: %s" % e)
        return None


def _create_single_category_schedule(
    doc: Any,
    assembly_id: Any,
    category: Any,
    label: str,
    field_names: Optional[List[str]] = None,
    template_id: Any = None,
) -> Any:
    """Create a single-category schedule for the assembly.

    Args:
        doc: Revit Document object
        assembly_id: ElementId of the AssemblyInstance
        category: BuiltInCategory enum value (e.g., OST_StructuralColumns)
        label: Human-readable label for logging
        field_names: Optional list of field names to configure
        template_id: Optional view template ElementId to apply

    Returns:
        Created ViewSchedule or None if failed
    """
    try:
        category_id = ElementId(category)
        view = AssemblyViewUtils.CreateSingleCategorySchedule(
            doc, assembly_id, category_id,
        )
        print("[assembly_views] Created %s for %s" % (label, _eid_int(assembly_id)))

        if field_names:
            _configure_schedule_fields(doc, view, field_names)
        if template_id is not None:
            _apply_view_template(view, template_id)

        return view
    except Exception as e:
        print("[assembly_views] Failed %s: %s" % (label, e))
        return None
