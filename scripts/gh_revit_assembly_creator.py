# File: scripts/gh_revit_assembly_creator.py
"""Revit Assembly Creator for Grasshopper.

Creates Revit Assemblies from framing and sheathing elements grouped by panel_id.
This component sits at the end of the pipeline after the Revit Baker and RiR
baking components (Add Structural Column, Add Structural Framing). It correlates
the baking_data_json geometry_index mapping with actual Revit ElementIds and
groups them into Assemblies per panel or per wall.

Key Features:
1. Element Grouping by Panel
   - Correlates baking_data_json geometry_index with Revit ElementIds
   - Groups columns, beams, and sheathing by panel_id
   - Falls back to one assembly per wall if panels_json is not provided

2. Two-Transaction Assembly Creation
   - Transaction 1: Create AssemblyInstance (commit immediately)
   - Transaction 2: Rename type, fix orientation, create views (type only exists after T1 commit)
   - Handles Revit API requirement for separate transactions

3. Optional Assembly Views with Configurable Settings
   - Creates 3D, front/top elevation, and material takeoff views per assembly
   - Controlled by create_views toggle and optional view_config_json
   - Configurable detail level (Coarse/Medium/Fine) and display style
   - Material takeoff disabled by default (appears under Schedules, not Assembly node)

4. Assembly Orientation Fix
   - Rotates assembly transform so BasisX aligns with wall direction
   - Ensures ElevationFront shows actual front view, not side view
   - Automatically derived from baking data beam centerlines

5. Structured JSON Output
   - Reports assembly_id, status, element_count per panel
   - Summary with total/successful/failed counts
   - Full diagnostic info output

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and runtime messages
    - RhinoCommon: CLR reference for .NET interop
    - RhinoInside.Revit: Revit document access (conditional)
    - timber_framing_generator.assemblies.assembly_creator: Grouping and creation logic

Performance Considerations:
    - Each assembly requires two Revit transactions (~0.5-1s per assembly)
    - View creation adds ~1-2s per assembly (if enabled)
    - For >20 panels, expect 30-60 seconds total execution time
    - Run only when ready (use the run toggle)

Usage:
    1. Connect 'baking_data_json' from Revit Baker component
    2. Connect 'column_ids' from RiR "Add Structural Column" output
    3. Connect 'beam_ids' from RiR "Add Structural Framing" output
    4. Optionally connect 'panels_json' for panel-level grouping
    5. Connect 'framing_json' from Framing Generator for accurate panel grouping
    6. Optionally connect 'sheathing_ids' and 'sheathing_data_json'
    7. Set 'run' to True to create assemblies
    8. Optionally connect 'view_config_json' to customize view settings
    9. Check 'assembly_json' and 'info' for results

Input Requirements:
    Baking Data JSON (baking_data_json) - str:
        JSON string from gh_revit_baker.py with geometry_index mapping
        per member, organized by wall. Contains classification, centerline,
        and geometry_index fields for each element.
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Panels JSON (panels_json) - str:
        JSON from panel decomposer with panel boundaries and element_ids.
        If not provided, falls back to one assembly per wall.
        Required: No
        Access: Item
        Type hint: str (set via GH UI)

    Column IDs (column_ids) - list:
        Revit ElementIds from RiR "Add Structural Column" output.
        Must be in geometry_index order matching baking_data_json.
        Required: Yes (at least column_ids or beam_ids must have elements)
        Access: List
        Type hint: No type hint (set via GH UI)

    Beam IDs (beam_ids) - list:
        Revit ElementIds from RiR "Add Structural Framing" output.
        Must be in geometry_index order matching baking_data_json.
        Required: Yes (at least column_ids or beam_ids must have elements)
        Access: List
        Type hint: No type hint (set via GH UI)

    Sheathing IDs (sheathing_ids) - list:
        Revit ElementIds from sheathing baking. Optional.
        Required: No
        Access: List
        Type hint: No type hint (set via GH UI)

    Sheathing Data JSON (sheathing_data_json) - str:
        JSON mapping sheathing elements to panel_ids.
        Required only if sheathing_ids is provided.
        Required: No
        Access: Item
        Type hint: str (set via GH UI)

    Naming Prefix (naming_prefix) - str:
        Prefix for assembly names (e.g., "W" -> "W1-P01").
        Required: No (defaults to "W")
        Access: Item
        Type hint: str (set via GH UI)

    Create Views (create_views) - bool:
        Whether to create 3D, section, and takeoff views per assembly.
        Required: No (defaults to False)
        Access: Item
        Type hint: bool (set via GH UI)

    View Config JSON (view_config_json) - str:
        Optional JSON string configuring assembly views. Keys:
        - include_3d (bool, default True)
        - include_front_elevation (bool, default True)
        - include_top_elevation (bool, default False)
        - include_material_takeoff (bool, default False)
        - detail_level ("Coarse"|"Medium"|"Fine", default "Fine")
        - display_style ("Wireframe"|"HiddenLine"|"Shaded"|"Realistic", default "HiddenLine")
        Omitted keys use defaults. Empty/missing uses all defaults.
        Required: No
        Access: Item
        Type hint: str (set via GH UI)

    Framing JSON (framing_json) - str:
        JSON from Framing Generator (gh_framing_generator.py) with panel_id
        on each element. When provided, enriches panels_json with element_ids
        for accurate panel-level grouping. Without this, falls back to
        geometry-based grouping which can misassign elements near panel
        boundaries.
        Required: No (but strongly recommended for panel-level assemblies)
        Access: Item
        Type hint: str (set via GH UI)

    Run (run) - bool:
        Boolean toggle to trigger execution. Assembly creation modifies
        the Revit document, so this acts as a safety guard.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

Outputs:
    Assembly JSON (assembly_json) - str:
        JSON with assembly results: per-panel assembly_id, status,
        element_count, views_created. Also includes summary.

    Assembly IDs (assembly_ids) - list of int:
        List of created assembly ElementIds as integers.
        Empty list if none created.

    Info (info) - str:
        Processing information with counts and per-assembly status.

Technical Details:
    - Uses group_elements_by_panel() for pure-Python element correlation
    - Uses create_assemblies() for Revit API calls (two-transaction pattern)
    - AssemblyInstance.Create requires ICollection<ElementId> as .NET List, not Python list
    - Assembly type is only assigned AFTER first transaction commits
    - Reads inputs by parameter index (NickName injection is unreliable)
    - Wall directions derived from baking_data via _derive_wall_axis() for orientation fix
    - AssemblyViewConfig controls view types, detail level, and display style

Error Handling:
    - Missing baking_data_json: returns empty outputs with warning
    - No column_ids and no beam_ids: returns empty outputs with warning
    - Revit unavailable: returns empty outputs with error
    - Per-assembly failures: logged individually, batch continues
    - All errors reported via dual logging (console + GH runtime messages)

Author: Fernando Maytorena
Version: 1.3.0
"""

import sys
import json
import traceback

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================
# Clear cached modules to ensure fresh imports when script changes.
# IMPORTANT: Must also clear 'src' package -- other GH components may have
# loaded it from a different PROJECT_PATH, and its __path__ would point there.
_modules_to_clear = [k for k in sys.modules.keys()
                     if 'timber_framing_generator' in k or k == 'src']
for _mod in _modules_to_clear:
    del sys.modules[_mod]
print("[RELOAD] Cleared %d cached modules" % len(_modules_to_clear))

# =============================================================================
# .NET / CLR
# =============================================================================

import clr

clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')

# Conditional RhinoInside.Revit import
REVIT_AVAILABLE = False
REVIT_DOC = None

try:
    clr.AddReference('RhinoInside.Revit')
    from RhinoInside.Revit import Revit
    REVIT_DOC = Revit.ActiveDBDocument
    if REVIT_DOC is not None:
        REVIT_AVAILABLE = True
except Exception as _revit_err:
    print("[INFO] RhinoInside.Revit not available: %s" % str(_revit_err))

# =============================================================================
# Rhino / Grasshopper
# =============================================================================

import Grasshopper

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.assemblies.assembly_creator import (
    enrich_panels_with_framing_data,
    group_elements_by_panel,
    create_assemblies,
    _derive_wall_axis,
)
from src.timber_framing_generator.assemblies.assembly_views import (
    AssemblyViewConfig,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Revit Assembly Creator"
COMPONENT_NICKNAME = "AssemCr"
COMPONENT_MESSAGE = "v1.3"
COMPONENT_CATEGORY = "TFG"
COMPONENT_SUBCATEGORY = "Revit"

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


def log_debug(message: str) -> None:
    """Log debug message (console only)."""
    print("[DEBUG] %s" % message)


def log_info(message: str) -> None:
    """Log info message (console only)."""
    print("[INFO] %s" % message)


def log_warning(message: str) -> None:
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message: str) -> None:
    """Log error message (console + GH UI)."""
    log_message(message, "error")


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
        baking_data_json: str
        panels_json: str
        column_ids: No type hint (GH default)
        beam_ids: No type hint (GH default)
        sheathing_ids: No type hint (GH default)
        sheathing_data_json: str
        naming_prefix: str
        create_views: bool
        view_config_json: str
        framing_json: str
        run: bool
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # IMPORTANT: NickName becomes the Python variable name
    # Format: (DisplayName, variable_name, Description, Access)
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Baking Data JSON", "baking_data_json",
         "JSON from Revit Baker with geometry_index mapping",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Panels JSON", "panels_json",
         "JSON from Panel Decomposer with panel boundaries (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Column IDs", "column_ids",
         "Revit ElementIds from RiR Add Structural Column",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Beam IDs", "beam_ids",
         "Revit ElementIds from RiR Add Structural Framing",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Sheathing IDs", "sheathing_ids",
         "Revit ElementIds from sheathing baking (optional)",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Sheathing Data JSON", "sheathing_data_json",
         "JSON mapping sheathing elements to panels (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Naming Prefix", "naming_prefix",
         "Prefix for assembly names, default 'W' (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Create Views", "create_views",
         "Whether to create assembly views, default False (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("View Config JSON", "view_config_json",
         "JSON configuring assembly views (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Framing JSON", "framing_json",
         "JSON from Framing Generator with panel_id per element (optional, enables accurate panel grouping)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Boolean to trigger execution",
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
        ("Assembly JSON", "assembly_json",
         "JSON with assembly results and summary"),
        ("Assembly IDs", "assembly_ids",
         "List of created assembly ElementIds as integers"),
        ("Info", "info",
         "Processing information"),
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

    Handles both typed (GH_Structure[GH_String]) and untyped
    (GH_Structure[IGH_Goo]) parameters. CPython3/pythonnet does not
    always expose .Branch() on the generic IGH_Goo variant.

    Args:
        param: A GH input parameter object

    Returns:
        List-like branch data, or None if empty
    """
    data = param.VolatileData

    # Try .Branch(0) first (works for typed parameters)
    if hasattr(data, 'Branch'):
        try:
            return data.Branch(0)
        except Exception:
            pass

    # Try get_Branch (pythonnet explicit getter)
    if hasattr(data, 'get_Branch'):
        try:
            return data.get_Branch(0)
        except Exception:
            pass

    # Fallback: iterate Branches property
    if hasattr(data, 'Branches'):
        try:
            branches = list(data.Branches)
            if branches:
                return branches[0]
        except Exception:
            pass

    # Last resort: AllData gives flat list of all items
    if hasattr(data, 'AllData'):
        try:
            all_items = data.AllData(True)
            return all_items
        except Exception:
            pass

    return None


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


def _read_list_input(inputs, index):
    """Read a list of values from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index

    Returns:
        list of values (may be empty)
    """
    result = []
    if index >= inputs.Count:
        return result
    if inputs[index].VolatileDataCount == 0:
        return result
    branch = _get_first_branch(inputs[index])
    if branch is None:
        return result
    for item in branch:
        val = item.Value if hasattr(item, 'Value') else item
        result.append(val)
    return result


def validate_inputs(baking_data_json_val, column_ids_val, beam_ids_val, run_val):
    """Validate component inputs.

    Args:
        baking_data_json_val: Raw baking data JSON string
        column_ids_val: List of column ElementIds
        beam_ids_val: List of beam ElementIds
        run_val: Boolean run toggle

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_val:
        return False, "Set 'run' to True to execute"

    if baking_data_json_val is None or not baking_data_json_val.strip():
        return False, "baking_data_json is required"

    # Validate JSON is parseable
    try:
        data = json.loads(baking_data_json_val)
        if not isinstance(data, dict):
            return False, "baking_data_json must be a JSON object"
        walls = data.get("walls", {})
        if not walls:
            return False, "baking_data_json contains no walls"
    except json.JSONDecodeError as e:
        return False, "Invalid JSON in baking_data_json: %s" % str(e)

    # At least one set of element IDs required
    has_columns = column_ids_val and len(column_ids_val) > 0
    has_beams = beam_ids_val and len(beam_ids_val) > 0
    if not has_columns and not has_beams:
        return False, "At least column_ids or beam_ids must have elements"

    # Check Revit availability
    if not REVIT_AVAILABLE:
        return False, "Revit document is not available (RhinoInside.Revit required)"

    return True, None


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the Revit Assembly Creator component.

    Coordinates the overall workflow:
    1. Read inputs by parameter index
    2. Setup component metadata (display only)
    3. Validate inputs
    4. Group elements by panel using baking_data_json correlation
    5. Create Revit assemblies via two-transaction pattern
    6. Return results as JSON, IDs, and info

    Returns:
        tuple: (assembly_json, assembly_ids, info)
    """
    # Default outputs
    default_outputs = ("", [], "")

    # -----------------------------------------------------------------
    # Read inputs by parameter index (CRITICAL: NickName injection is unreliable)
    # -----------------------------------------------------------------
    inputs = ghenv.Component.Params.Input

    baking_data_json_val = _read_string_input(inputs, 0)
    panels_json_val = _read_string_input(inputs, 1)
    column_ids_val = _read_list_input(inputs, 2)
    beam_ids_val = _read_list_input(inputs, 3)
    sheathing_ids_val = _read_list_input(inputs, 4)
    sheathing_data_json_val = _read_string_input(inputs, 5)
    naming_prefix_val = _read_string_input(inputs, 6)
    create_views_val = _read_bool_input(inputs, 7, default=False)
    view_config_json_val = _read_string_input(inputs, 8)
    framing_json_val = _read_string_input(inputs, 9)
    run_val = _read_bool_input(inputs, 10, default=False)

    # -----------------------------------------------------------------
    # Setup component metadata (display only, AFTER inputs are captured)
    # -----------------------------------------------------------------
    setup_component()

    try:
        # -----------------------------------------------------------------
        # Validate inputs
        # -----------------------------------------------------------------
        is_valid, error_msg = validate_inputs(
            baking_data_json_val, column_ids_val, beam_ids_val, run_val,
        )

        if not is_valid:
            if run_val:
                log_warning(error_msg)
            else:
                log_info(error_msg or "Component disabled (run=False)")
            return ("", [], error_msg or "Not running")

        # -----------------------------------------------------------------
        # Build diagnostic info
        # -----------------------------------------------------------------
        info_lines = [
            "Revit Assembly Creator v1.3",
            "=" * 40,
        ]

        # Apply defaults for optional inputs
        prefix = naming_prefix_val if naming_prefix_val else "W"
        do_create_views = create_views_val

        # Parse view config JSON
        view_config = None
        if view_config_json_val:
            try:
                config_data = json.loads(view_config_json_val)
                view_config = AssemblyViewConfig.from_dict(config_data)
                log_info("View config: %s" % str(config_data))
            except (json.JSONDecodeError, Exception) as e:
                log_warning("Invalid view_config_json, using defaults: %s" % str(e))
                view_config = None

        info_lines.append("Naming Prefix: %s" % prefix)
        info_lines.append("Create Views: %s" % str(do_create_views))
        if view_config:
            info_lines.append("View Config: detail=%s, display=%s"
                              % (view_config.detail_level, view_config.display_style))
        info_lines.append("Revit Document: %s" % (REVIT_DOC.Title if REVIT_DOC else "N/A"))

        # Count input elements
        info_lines.append("")
        info_lines.append("Input Counts:")
        info_lines.append("  Column IDs: %d" % len(column_ids_val))
        info_lines.append("  Beam IDs: %d" % len(beam_ids_val))
        info_lines.append("  Sheathing IDs: %d" % len(sheathing_ids_val))
        info_lines.append("  Panels JSON: %s" % ("provided" if panels_json_val else "not provided (wall-level grouping)"))
        info_lines.append("  Sheathing Data JSON: %s" % ("provided" if sheathing_data_json_val else "not provided"))

        # Parse baking data for summary
        baking_data = json.loads(baking_data_json_val)
        wall_count = len(baking_data.get("walls", {}))
        total_members = sum(
            len(w.get("members", []))
            for w in baking_data.get("walls", {}).values()
        )
        info_lines.append("")
        info_lines.append("Baking Data:")
        info_lines.append("  Walls: %d" % wall_count)
        info_lines.append("  Members: %d" % total_members)

        # -----------------------------------------------------------------
        # Enrich panels with element_ids from framing data
        # -----------------------------------------------------------------
        # The panel decomposer runs before the framing generator, so
        # panels_json has empty element_ids. If framing_json is provided,
        # map each element's panel_id back to its panel's element_ids list.
        # This enables the reliable element-ID-based grouping path.
        enriched_panels_json = panels_json_val
        if framing_json_val and panels_json_val:
            try:
                enriched_panels_json = enrich_panels_with_framing_data(
                    panels_json_val, framing_json_val,
                )
                log_info("Enriched panels with framing element_ids")
                info_lines.append("  Framing JSON: provided (panels enriched with element_ids)")
            except Exception as e:
                log_warning("Failed to enrich panels: %s" % str(e))
                enriched_panels_json = panels_json_val
                info_lines.append("  Framing JSON: provided but enrichment failed: %s" % str(e))
        elif framing_json_val:
            info_lines.append("  Framing JSON: provided but no panels_json to enrich")
        else:
            info_lines.append("  Framing JSON: not provided (using geometry-based grouping)")

        # -----------------------------------------------------------------
        # Group elements by panel
        # -----------------------------------------------------------------
        log_info("Grouping elements by panel...")

        groups = group_elements_by_panel(
            baking_data_json_val,
            enriched_panels_json,
            column_ids_val,
            beam_ids_val,
            sheathing_ids_val if sheathing_ids_val else None,
            sheathing_data_json_val,
        )

        info_lines.append("")
        info_lines.append("Grouping Results:")
        info_lines.append("  Groups created: %d" % len(groups))
        total_grouped = sum(g.element_count for g in groups)
        info_lines.append("  Total elements grouped: %d" % total_grouped)

        for g in groups:
            info_lines.append(
                "  %s: %d cols, %d beams, %d sheathing"
                % (g.panel_id, len(g.column_element_ids),
                   len(g.beam_element_ids), len(g.sheathing_element_ids))
            )

        # Check for duplicate Revit ElementIds across groups
        if groups:
            all_eid_strs = []
            eid_to_panel = {}
            dup_samples = []
            for g in groups:
                for eid in g.all_element_ids:
                    eid_str = str(eid)
                    if eid_str in eid_to_panel:
                        if len(dup_samples) < 10:
                            dup_samples.append(
                                (eid_str, eid_to_panel[eid_str], g.panel_id)
                            )
                    else:
                        eid_to_panel[eid_str] = g.panel_id
                    all_eid_strs.append(eid_str)

            unique_count = len(eid_to_panel)
            dup_count = len(all_eid_strs) - unique_count
            info_lines.append("")
            info_lines.append("Duplicate Element Check:")
            info_lines.append(
                "  Total element refs: %d, Unique: %d, Duplicates: %d"
                % (len(all_eid_strs), unique_count, dup_count)
            )
            if dup_count > 0:
                log_warning(
                    "DUPLICATE ELEMENTS: %d elements shared across panels!"
                    % dup_count
                )
                for eid_str, first_panel, second_panel in dup_samples:
                    info_lines.append(
                        "  ElementId '%s': in '%s' AND '%s'"
                        % (eid_str, first_panel, second_panel)
                    )
            else:
                info_lines.append("  No duplicates -- all elements unique")

        if not groups:
            msg = "No element groups created -- check baking_data_json and panels_json"
            log_warning(msg)
            info_lines.append("")
            info_lines.append("WARNING: %s" % msg)

            # Diagnostic: show sample data to help identify the mismatch
            info_lines.append("")
            info_lines.append("=== DIAGNOSTIC: Sample Data ===")

            # Sample baking member IDs
            sample_member_ids = []
            for wid, wd in baking_data.get("walls", {}).items():
                for m in wd.get("members", [])[:3]:
                    sample_member_ids.append(m.get("id", "?"))
                if sample_member_ids:
                    break
            info_lines.append("Baking member IDs (first 3): %s" % sample_member_ids)

            # Sample baking member panel_ids
            sample_panel_ids = []
            for wid, wd in baking_data.get("walls", {}).items():
                for m in wd.get("members", [])[:3]:
                    sample_panel_ids.append(m.get("panel_id", "MISSING"))
                if sample_panel_ids:
                    break
            info_lines.append("Baking member panel_ids (first 3): %s" % sample_panel_ids)

            # Sample baking wall IDs
            baking_wall_ids = list(baking_data.get("walls", {}).keys())[:3]
            info_lines.append("Baking wall IDs: %s" % baking_wall_ids)

            # Panels data
            if panels_json_val:
                try:
                    panels_raw = json.loads(panels_json_val)
                    info_lines.append("Panels JSON type: %s" % type(panels_raw).__name__)
                    if isinstance(panels_raw, dict):
                        info_lines.append("Panels JSON keys: %s" % list(panels_raw.keys()))
                        nested = panels_raw.get("panels", [])
                        if nested:
                            p0 = nested[0]
                            info_lines.append("First panel keys: %s" % list(p0.keys()))
                            info_lines.append("First panel id: %s" % p0.get("id", "MISSING"))
                            info_lines.append("First panel element_ids (first 3): %s"
                                              % p0.get("element_ids", [])[:3])
                    elif isinstance(panels_raw, list) and panels_raw:
                        p0 = panels_raw[0]
                        info_lines.append("First item keys: %s" % list(p0.keys()))
                        if "panels" in p0:
                            nested = p0.get("panels", [])
                            if nested:
                                info_lines.append("First nested panel id: %s"
                                                  % nested[0].get("id", "MISSING"))
                                info_lines.append("First nested panel element_ids (first 3): %s"
                                                  % nested[0].get("element_ids", [])[:3])
                except Exception as diag_err:
                    info_lines.append("Failed to parse panels_json: %s" % diag_err)
            else:
                info_lines.append("Panels JSON: not provided")

            info_lines.append("Column IDs sample (first 3): %s"
                              % [str(c) for c in column_ids_val[:3]])
            info_lines.append("Beam IDs sample (first 3): %s"
                              % [str(b) for b in beam_ids_val[:3]])
            info_lines.append("=== END DIAGNOSTIC ===")

            return ("", [], "\n".join(info_lines))

        # -----------------------------------------------------------------
        # Extract wall directions for orientation fix
        # -----------------------------------------------------------------
        wall_directions = {}
        for wall_id, wall_data in baking_data.get("walls", {}).items():
            members = wall_data.get("members", [])
            if members:
                origin, direction = _derive_wall_axis(members)
                if direction is not None:
                    wall_directions[wall_id] = direction

        if wall_directions:
            info_lines.append("  Wall directions extracted: %d" % len(wall_directions))

        # -----------------------------------------------------------------
        # Create assemblies
        # -----------------------------------------------------------------
        log_info("Creating %d assemblies (create_views=%s)..." % (len(groups), do_create_views))

        result = create_assemblies(
            REVIT_DOC,
            groups,
            naming_prefix=prefix,
            create_views=do_create_views,
            view_config=view_config,
            wall_directions=wall_directions if wall_directions else None,
        )

        # -----------------------------------------------------------------
        # Build output
        # -----------------------------------------------------------------
        assembly_json_val = json.dumps(result.to_dict(), indent=2)

        assembly_ids_val = [
            r.assembly_id
            for r in result.results
            if r.assembly_id is not None
        ]

        info_lines.append("")
        info_lines.append("Assembly Creation Results:")
        info_lines.append("  Total: %d" % result.total_assemblies)
        info_lines.append("  Created: %d" % result.successful)
        info_lines.append("  Failed: %d" % result.failed)
        info_lines.append("")

        for r in result.results:
            if r.status == "created":
                status_str = "[OK]"
            else:
                status_str = "[FAIL]"
            line = "  %s %s (%d elements)" % (status_str, r.assembly_name, r.element_count)
            if r.error:
                line += " - %s" % r.error
            if r.views_created:
                line += " views: %s" % ", ".join(r.views_created)
            info_lines.append(line)

        # Summary GH message
        if result.failed == 0 and result.successful > 0:
            log_message(
                "Created %d assemblies successfully" % result.successful,
                "remark",
            )
        elif result.failed > 0 and result.successful > 0:
            log_warning(
                "Partial: %d created, %d failed" % (result.successful, result.failed)
            )
        elif result.successful == 0:
            log_error(
                "All %d assemblies failed" % result.failed
            )

        info_val = "\n".join(info_lines)
        return (assembly_json_val, assembly_ids_val, info_val)

    except Exception as e:
        error_msg = "Unexpected error: %s" % str(e)
        log_error(error_msg)
        log_debug(traceback.format_exc())
        return ("", [], error_msg + "\n" + traceback.format_exc())


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    assembly_json, assembly_ids, info = main()
    # Print info to console so it's always visible regardless of output binding
    if info:
        print(info)
