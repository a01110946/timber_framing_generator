# File: scripts/gh_assembly_view_config.py
"""Assembly View Config Builder for Grasshopper.

Builds a view_config_json string for the Revit Assembly Creator component.
Each AssemblyViewConfig option is exposed as a separate GH input with sensible
defaults, so users can configure assembly views without hand-writing JSON.

Key Features:
1. One Input per Config Option
   - Boolean toggles for each view type (3D, 6 elevations, material takeoff,
     structural schedules, sheet)
   - String inputs for Detail Level, Display Style, schedule fields, templates,
     and title block name
   - All inputs are optional; defaults match AssemblyViewConfig

2. Validated Output
   - Validates Detail Level and Display Style against allowed values
   - Warns on invalid values and falls back to defaults
   - Outputs compact JSON ready to connect to Assembly Creator

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and runtime messages

Performance Considerations:
    - Lightweight component, no Revit or geometry dependencies
    - Instant execution, no toggle required

Usage:
    1. Drop the component onto the canvas
    2. Optionally adjust inputs (all have defaults)
    3. Connect 'view_config_json' output to Assembly Creator's
       'View Config JSON' input

Input Requirements:
    Include 3D (include_3d) - bool:
        Create a 3D orthographic assembly view.
        Required: No (defaults to True)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Front Elevation (include_front) - bool:
        Create a front elevation section view.
        Required: No (defaults to True)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Top Elevation (include_top) - bool:
        Create a top elevation section view.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Material Takeoff (include_takeoff) - bool:
        Create a material takeoff schedule.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Detail Level (detail_level) - str:
        View detail level. One of: "Coarse", "Medium", "Fine".
        Required: No (defaults to "Fine")
        Access: Item
        Type hint: str (set via GH UI)

    Display Style (display_style) - str:
        View display style. One of: "Wireframe", "HiddenLine", "Shaded",
        "Shaded with Edges", "Consistent Colors", "Realistic",
        "Realistic with Edges".
        Required: No (defaults to "HiddenLine")
        Access: Item
        Type hint: str (set via GH UI)

    Include Back Elevation (include_back) - bool:
        Create a back elevation section view.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Bottom Elevation (include_bottom) - bool:
        Create a bottom elevation section view.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Left Elevation (include_left) - bool:
        Create a left elevation section view.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Right Elevation (include_right) - bool:
        Create a right elevation section view.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Column Schedule (include_col_sched) - bool:
        Create a structural column schedule.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Framing Schedule (include_frm_sched) - bool:
        Create a structural framing schedule.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Schedule Fields (schedule_fields) - str:
        Comma-separated field names for structural schedules.
        Empty = defaults (Family, Type, Cut Length).
        Required: No (defaults to "")
        Access: Item
        Type hint: str (set via GH UI)

    Schedule Template (schedule_template) - str:
        View template name to apply to structural schedules.
        Required: No (defaults to "")
        Access: Item
        Type hint: str (set via GH UI)

    Takeoff Fields (takeoff_fields) - str:
        Comma-separated field names for material takeoff.
        Empty = defaults (Type, Count, Material: Name, Material: Area).
        Required: No (defaults to "")
        Access: Item
        Type hint: str (set via GH UI)

    Takeoff Template (takeoff_template) - str:
        View template name to apply to material takeoff.
        Required: No (defaults to "")
        Access: Item
        Type hint: str (set via GH UI)

    Hide Section Markers (hide_markers) - bool:
        Hide section markers in elevation views.
        Required: No (defaults to True)
        Access: Item
        Type hint: bool (set via GH UI)

    Include Sheet (include_sheet) - bool:
        Create a sheet per assembly with all views as viewports.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    Titleblock Name (titleblock_name) - str:
        Title block family name for sheet creation. Empty = no title block.
        Required: No (defaults to "")
        Access: Item
        Type hint: str (set via GH UI)

Outputs:
    View Config JSON (view_config_json) - str:
        JSON string with assembly view configuration, ready to connect
        to the Assembly Creator component's View Config JSON input.

    Info (info) - str:
        Summary of the current configuration.

Technical Details:
    - No Revit or RhinoCommon dependency -- pure Python JSON builder
    - Reads inputs by parameter index (NickName injection is unreliable)
    - Validates string inputs against allowed values

Error Handling:
    - Invalid detail_level: warns and falls back to "Fine"
    - Invalid display_style: warns and falls back to "HiddenLine"
    - Missing inputs: uses defaults silently

Author: Fernando Maytorena
Version: 2.0.0
"""

import json

# =============================================================================
# .NET / CLR
# =============================================================================

import clr

clr.AddReference('Grasshopper')

# =============================================================================
# Rhino / Grasshopper
# =============================================================================

import Grasshopper

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Assembly View Config"
COMPONENT_NICKNAME = "ViewCfg"
COMPONENT_MESSAGE = "v2.0"
COMPONENT_CATEGORY = "TFG"
COMPONENT_SUBCATEGORY = "Revit"

VALID_DETAIL_LEVELS = ("Coarse", "Medium", "Fine")
VALID_DISPLAY_STYLES = (
    "Wireframe", "HiddenLine", "Shaded", "Shaded with Edges",
    "Consistent Colors", "Realistic", "Realistic with Edges",
)

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message: str, level: str = "info") -> None:
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log (ASCII only -- no unicode)
        level: One of "info", "debug", "warning", "error", "remark"
    """
    print("[%s] %s" % (level.upper(), message))

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


def log_info(message: str) -> None:
    """Log info message (console only)."""
    print("[INFO] %s" % message)


def log_warning(message: str) -> None:
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


# =============================================================================
# Component Setup
# =============================================================================

def setup_component() -> None:
    """Initialize and configure the Grasshopper component.

    Sets component metadata, input parameters, and output parameters.

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1].

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    Required type hints:
        Inputs 0-3, 6-9, 10-11, 16-17: bool
        Inputs 4-5, 12-15, 18: str
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        # Idx 0-5: Original inputs (backward-compatible positions)
        ("Include 3D", "include_3d",
         "Create 3D orthographic view (default True)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Front Elevation", "include_front",
         "Create front elevation view (default True)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Top Elevation", "include_top",
         "Create top elevation view (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Material Takeoff", "include_takeoff",
         "Create material takeoff schedule (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Detail Level", "detail_level",
         "Coarse, Medium, or Fine (default Fine)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Display Style", "display_style",
         "Wireframe, HiddenLine, Shaded, etc. (default HiddenLine)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Idx 6-9: New elevations
        ("Include Back Elevation", "include_back",
         "Create back elevation view (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Bottom Elevation", "include_bottom",
         "Create bottom elevation view (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Left Elevation", "include_left",
         "Create left elevation view (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Right Elevation", "include_right",
         "Create right elevation view (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Idx 10-11: Structural schedules
        ("Include Column Schedule", "include_col_sched",
         "Create structural column schedule (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Include Framing Schedule", "include_frm_sched",
         "Create structural framing schedule (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Idx 12-13: Schedule config
        ("Schedule Fields", "schedule_fields",
         "Comma-separated field names for schedules (default: Family, Type, Cut Length)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Schedule Template", "schedule_template",
         "View template name for structural schedules (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Idx 14-15: Takeoff config
        ("Takeoff Fields", "takeoff_fields",
         "Comma-separated field names for takeoff (default: Type, Count, Material: Name, Material: Area)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Takeoff Template", "takeoff_template",
         "View template name for material takeoff (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Idx 16: Section markers
        ("Hide Section Markers", "hide_markers",
         "Hide section markers in elevation views (default True)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Idx 17-18: Sheet
        ("Include Sheet", "include_sheet",
         "Create sheet per assembly with viewports (default False)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Titleblock Name", "titleblock_name",
         "Title block family name for sheets (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("View Config JSON", "view_config_json",
         "JSON string for Assembly Creator view_config_json input"),
        ("Info", "info",
         "Configuration summary"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1  # Skip Output[0]
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc


# =============================================================================
# Helper Functions
# =============================================================================

def _get_first_branch(param):
    """Get the first branch of data from a GH parameter's VolatileData.

    Args:
        param: A GH input parameter object

    Returns:
        List-like branch data, or None if empty
    """
    data = param.VolatileData

    if hasattr(data, 'Branch'):
        try:
            return data.Branch(0)
        except Exception:
            pass

    if hasattr(data, 'get_Branch'):
        try:
            return data.get_Branch(0)
        except Exception:
            pass

    if hasattr(data, 'Branches'):
        try:
            branches = list(data.Branches)
            if branches:
                return branches[0]
        except Exception:
            pass

    if hasattr(data, 'AllData'):
        try:
            return data.AllData(True)
        except Exception:
            pass

    return None


def _read_bool_input(inputs, index, default=False):
    """Read a boolean value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index
        default: Default value if input is empty

    Returns:
        bool
    """
    if index >= inputs.Count:
        return default
    if inputs[index].VolatileDataCount == 0:
        return default
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return default
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return default
    return bool(val)


def _read_string_input(inputs, index):
    """Read a string value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index

    Returns:
        str or None if input is empty or missing
    """
    if index >= inputs.Count:
        return None
    if inputs[index].VolatileDataCount == 0:
        return None
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return None
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return None
    return str(val)


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the Assembly View Config component.

    Reads individual config inputs, validates string values, builds
    a config dictionary, and serializes to JSON.

    Returns:
        tuple: (view_config_json, info)
    """
    # -----------------------------------------------------------------
    # Read inputs by parameter index (NickName injection is unreliable)
    # -----------------------------------------------------------------
    inputs = ghenv.Component.Params.Input

    # Original inputs (idx 0-5)
    include_3d_val = _read_bool_input(inputs, 0, default=True)
    include_front_val = _read_bool_input(inputs, 1, default=True)
    include_top_val = _read_bool_input(inputs, 2, default=False)
    include_takeoff_val = _read_bool_input(inputs, 3, default=False)
    detail_level_val = _read_string_input(inputs, 4)
    display_style_val = _read_string_input(inputs, 5)

    # New elevations (idx 6-9)
    include_back_val = _read_bool_input(inputs, 6, default=False)
    include_bottom_val = _read_bool_input(inputs, 7, default=False)
    include_left_val = _read_bool_input(inputs, 8, default=False)
    include_right_val = _read_bool_input(inputs, 9, default=False)

    # Structural schedules (idx 10-11)
    include_col_sched_val = _read_bool_input(inputs, 10, default=False)
    include_frm_sched_val = _read_bool_input(inputs, 11, default=False)

    # Schedule config (idx 12-13)
    schedule_fields_val = _read_string_input(inputs, 12)
    schedule_template_val = _read_string_input(inputs, 13)

    # Takeoff config (idx 14-15)
    takeoff_fields_val = _read_string_input(inputs, 14)
    takeoff_template_val = _read_string_input(inputs, 15)

    # Section markers (idx 16)
    hide_markers_val = _read_bool_input(inputs, 16, default=True)

    # Sheet (idx 17-18)
    include_sheet_val = _read_bool_input(inputs, 17, default=False)
    titleblock_name_val = _read_string_input(inputs, 18)

    # -----------------------------------------------------------------
    # Setup component metadata (display only, AFTER inputs are captured)
    # -----------------------------------------------------------------
    setup_component()

    # -----------------------------------------------------------------
    # Validate and apply defaults for string inputs
    # -----------------------------------------------------------------
    if detail_level_val and detail_level_val in VALID_DETAIL_LEVELS:
        detail_level = detail_level_val
    else:
        if detail_level_val:
            log_warning(
                "Invalid detail_level '%s'. Valid: %s. Using 'Fine'."
                % (detail_level_val, ", ".join(VALID_DETAIL_LEVELS))
            )
        detail_level = "Fine"

    if display_style_val and display_style_val in VALID_DISPLAY_STYLES:
        display_style = display_style_val
    else:
        if display_style_val:
            log_warning(
                "Invalid display_style '%s'. Valid: %s. Using 'HiddenLine'."
                % (display_style_val, ", ".join(VALID_DISPLAY_STYLES))
            )
        display_style = "HiddenLine"

    # -----------------------------------------------------------------
    # Build config dict and serialize
    # -----------------------------------------------------------------
    config = {
        "include_3d": include_3d_val,
        "include_front_elevation": include_front_val,
        "include_top_elevation": include_top_val,
        "include_material_takeoff": include_takeoff_val,
        "detail_level": detail_level,
        "display_style": display_style,
        "include_back_elevation": include_back_val,
        "include_bottom_elevation": include_bottom_val,
        "include_left_elevation": include_left_val,
        "include_right_elevation": include_right_val,
        "include_column_schedule": include_col_sched_val,
        "include_framing_schedule": include_frm_sched_val,
        "schedule_fields": schedule_fields_val or "",
        "schedule_template_name": schedule_template_val or "",
        "takeoff_fields": takeoff_fields_val or "",
        "takeoff_template_name": takeoff_template_val or "",
        "hide_section_markers": hide_markers_val,
        "include_sheet": include_sheet_val,
        "titleblock_name": titleblock_name_val or "",
    }

    view_config_json = json.dumps(config)

    # -----------------------------------------------------------------
    # Build info summary
    # -----------------------------------------------------------------
    info_lines = [
        "Assembly View Config v2.0",
        "=" * 30,
        "Views:",
        "  3D Orthographic:  %s" % ("ON" if include_3d_val else "OFF"),
        "  Front Elevation:  %s" % ("ON" if include_front_val else "OFF"),
        "  Back Elevation:   %s" % ("ON" if include_back_val else "OFF"),
        "  Top Elevation:    %s" % ("ON" if include_top_val else "OFF"),
        "  Bottom Elevation: %s" % ("ON" if include_bottom_val else "OFF"),
        "  Left Elevation:   %s" % ("ON" if include_left_val else "OFF"),
        "  Right Elevation:  %s" % ("ON" if include_right_val else "OFF"),
        "",
        "Schedules:",
        "  Material Takeoff: %s" % ("ON" if include_takeoff_val else "OFF"),
        "  Column Schedule:  %s" % ("ON" if include_col_sched_val else "OFF"),
        "  Framing Schedule: %s" % ("ON" if include_frm_sched_val else "OFF"),
        "",
        "Settings:",
        "  Detail Level:      %s" % detail_level,
        "  Display Style:     %s" % display_style,
        "  Hide Sec. Markers: %s" % ("ON" if hide_markers_val else "OFF"),
        "",
        "Sheet:",
        "  Include Sheet:  %s" % ("ON" if include_sheet_val else "OFF"),
        "  Titleblock:     %s" % (titleblock_name_val or "(none)"),
    ]

    # Show schedule/takeoff field config if relevant
    if include_col_sched_val or include_frm_sched_val:
        info_lines.append("")
        info_lines.append("Schedule Fields: %s" % (schedule_fields_val or "(defaults)"))
        if schedule_template_val:
            info_lines.append("Schedule Template: %s" % schedule_template_val)

    if include_takeoff_val:
        info_lines.append("")
        info_lines.append("Takeoff Fields: %s" % (takeoff_fields_val or "(defaults)"))
        if takeoff_template_val:
            info_lines.append("Takeoff Template: %s" % takeoff_template_val)

    info = "\n".join(info_lines)
    log_info("Config built: %s" % view_config_json)

    return (view_config_json, info)


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    view_config_json, info = main()
    if info:
        print(info)
