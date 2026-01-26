# File: scripts/gh_panel_decomposer.py
"""Panel Decomposer for Grasshopper.

Decomposes framed walls into manufacturable panels with optimized joint placement.
Handles wall corner geometry adjustments for accurate panel dimensions suitable
for offsite construction and prefabrication workflows.

Key Features:
1. Panel Decomposition
   - Splits walls into panels respecting max length constraints
   - Optimizes joint locations using dynamic programming
   - Aligns joints with stud locations for structural support

2. Corner Adjustment Calculation
   - Detects wall corners from endpoint proximity
   - Calculates extend/recede adjustments for face-to-face dimensions
   - Applies adjustments to panel geometry output (not Revit walls)

3. Exclusion Zone Handling
   - Avoids joints near openings (12" per GA-216)
   - Avoids joints near wall corners (24" default)
   - Respects shear panel boundaries

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Curve and point creation for visualization
    - Grasshopper: DataTree for multi-wall output organization
    - timber_framing_generator.panels: Core panelization logic

Performance Considerations:
    - DP algorithm is O(n²) where n = number of stud positions
    - Typical walls process in < 100ms
    - Corner detection is O(w²) where w = number of walls

Usage:
    1. Connect 'walls_json' from Wall Analyzer component
    2. Optionally connect 'framing_json' from Framing Generator
    3. Configure panel constraints (max_length, joint offsets, etc.)
    4. Set 'run' to True to execute
    5. Use 'panels_json' for downstream processing or shop drawings

Input Requirements:
    walls_json (walls_json) - str:
        JSON string from Wall Analyzer component containing wall geometry
        Required: Yes
        Access: Item

    framing_json (framing_json) - str:
        JSON string from Framing Generator with framing elements
        Required: No (enhances joint stud detection)
        Access: Item

    max_panel_length (max_length) - float:
        Maximum panel length in feet
        Required: No (defaults to 24.0)
        Access: Item

    min_joint_to_opening (joint_opening) - float:
        Minimum distance from joint to opening edge in feet
        Required: No (defaults to 1.0 per GA-216)
        Access: Item

    min_joint_to_corner (joint_corner) - float:
        Minimum distance from joint to wall corner in feet
        Required: No (defaults to 2.0)
        Access: Item

    stud_spacing (stud_space) - float:
        Stud spacing in feet for joint alignment
        Required: No (defaults to 1.333 = 16" OC)
        Access: Item

    run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    panels_json (panels_json) - str:
        JSON string containing panel data for all walls

    panel_curves (panel_curves) - DataTree[Curve]:
        Panel boundary curves for visualization (closed polylines)

    joint_points (joint_points) - DataTree[Point3d]:
        Joint location points at mid-wall height

    debug_info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Panel geometry uses adjusted dimensions (not Revit centerlines)
    - Corner adjustments stored in results but don't modify Revit
    - Use gh_wall_corner_adjuster.py to apply changes to Revit walls

Error Handling:
    - Invalid JSON returns empty outputs with error in debug_info
    - Missing optional inputs use sensible defaults
    - Processing errors logged but don't halt execution

Author: Timber Framing Generator
Version: 1.0.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import sys
import json
import traceback

# .NET / CLR
import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

# Rhino / Grasshopper
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================

_modules_to_clear = [k for k in sys.modules.keys() if 'timber_framing_generator' in k]
for mod in _modules_to_clear:
    del sys.modules[mod]

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.panels import (
    PanelConfig,
    decompose_all_walls,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Panel Decomposer"
COMPONENT_NICKNAME = "PanelDecomp"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Panels"

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log
        level: One of "info", "debug", "warning", "error", "remark"
    """
    print(f"[{level.upper()}] {message}")

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


def log_debug(message):
    """Log debug message (console only)."""
    print(f"[DEBUG] {message}")


def log_info(message):
    """Log info message (console only)."""
    print(f"[INFO] {message}")


def log_warning(message):
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message):
    """Log error message (console + GH UI)."""
    log_message(message, "error")

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component.

    This function handles:
    1. Setting component metadata (name, category, etc.)
    2. Configuring input parameters
    3. Configuring output parameters

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Walls JSON", "walls_json", "JSON string from Wall Analyzer", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Framing JSON", "framing_json", "JSON string from Framing Generator (optional)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Max Panel Length", "max_length", "Maximum panel length in feet (default 24.0)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Joint to Opening", "joint_opening", "Min distance from joint to opening in feet (default 1.0)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Joint to Corner", "joint_corner", "Min distance from joint to corner in feet (default 2.0)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Stud Spacing", "stud_space", "Stud spacing in feet (default 1.333 = 16\" OC)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run", "Boolean to trigger execution", Grasshopper.Kernel.GH_ParamAccess.item),
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
        ("Panels JSON", "panels_json", "JSON string containing panel data"),
        ("Panel Curves", "panel_curves", "Panel boundary curves for visualization"),
        ("Joint Points", "joint_points", "Joint location points"),
        ("Debug Info", "debug_info", "Debug information and status"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc

# =============================================================================
# Helper Functions
# =============================================================================

def validate_inputs(walls_json, run):
    """Validate component inputs.

    Args:
        walls_json: JSON string with wall data
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not walls_json:
        return False, "No walls_json input provided"

    try:
        json.loads(walls_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


def parse_walls_json(walls_json):
    """Parse walls JSON to list of wall dictionaries.

    Args:
        walls_json: JSON string

    Returns:
        List of wall dictionaries
    """
    data = json.loads(walls_json)
    return data if isinstance(data, list) else [data]


def parse_framing_json(framing_json):
    """Parse framing JSON to list of framing dictionaries.

    Args:
        framing_json: JSON string or None

    Returns:
        List of framing dictionaries or None
    """
    if not framing_json:
        return None
    data = json.loads(framing_json)
    return data if isinstance(data, list) else [data]


def create_panel_boundary_curve(corners):
    """Create boundary curve from panel corners.

    Args:
        corners: Dictionary with bottom_left, bottom_right, top_right, top_left

    Returns:
        Closed polyline curve or None on failure
    """
    try:
        factory = get_factory()
        bl, br, tr, tl = corners["bottom_left"], corners["bottom_right"], corners["top_right"], corners["top_left"]

        points = [
            factory.create_point3d(bl["x"], bl["y"], bl["z"]),
            factory.create_point3d(br["x"], br["y"], br["z"]),
            factory.create_point3d(tr["x"], tr["y"], tr["z"]),
            factory.create_point3d(tl["x"], tl["y"], tl["z"]),
            factory.create_point3d(bl["x"], bl["y"], bl["z"]),  # Close loop
        ]
        return factory.create_polyline_curve(points)
    except Exception as e:
        log_debug(f"Error creating panel curve: {e}")
        return None


def create_joint_point(u_coord, wall_data):
    """Create point at joint location.

    Args:
        u_coord: U coordinate of joint
        wall_data: Wall data dictionary

    Returns:
        Point3d at joint location or None on failure
    """
    try:
        factory = get_factory()
        base_plane = wall_data.get("base_plane", {})
        origin = base_plane.get("origin", {})
        x_axis = base_plane.get("x_axis", {})
        height = wall_data.get("wall_height", wall_data.get("height", 8.0))
        base_elev = wall_data.get("base_elevation", 0.0)

        ox, oy = origin.get("x", 0), origin.get("y", 0)
        xx, xy = x_axis.get("x", 1), x_axis.get("y", 0)

        return factory.create_point3d(
            ox + u_coord * xx,
            oy + u_coord * xy,
            base_elev + height / 2
        )
    except Exception as e:
        log_debug(f"Error creating joint point: {e}")
        return None


def process_panelization(walls_data, framing_data, config):
    """Process walls through panelization pipeline.

    Args:
        walls_data: List of wall dictionaries
        framing_data: List of framing dictionaries or None
        config: PanelConfig instance

    Returns:
        tuple: (all_results, panel_curves_tree, joint_points_tree, info_lines)
    """
    log_info(f"Processing {len(walls_data)} walls")

    all_results = decompose_all_walls(walls_data, framing_data, config)

    panel_curves = DataTree[object]()
    joint_points = DataTree[object]()
    info_lines = []

    total_panels = 0
    total_joints = 0

    for wall_idx, result in enumerate(all_results):
        wall_id = result["wall_id"]
        panels = result["panels"]
        joints = result["joints"]
        wall_data = walls_data[wall_idx] if wall_idx < len(walls_data) else {}

        info_lines.append(f"Wall {wall_id}: {len(panels)} panels, {len(joints)} joints")

        # Create panel curves
        for panel_idx, panel in enumerate(panels):
            curve = create_panel_boundary_curve(panel["corners"])
            if curve:
                panel_curves.Add(curve, GH_Path(wall_idx, panel_idx))

        # Create joint points
        for joint_idx, joint in enumerate(joints):
            point = create_joint_point(joint["u_coord"], wall_data)
            if point:
                joint_points.Add(point, GH_Path(wall_idx, joint_idx))

        total_panels += len(panels)
        total_joints += len(joints)

    info_lines.append(f"Total: {total_panels} panels, {total_joints} joints")
    log_info(f"Completed: {total_panels} panels, {total_joints} joints")

    return all_results, panel_curves, joint_points, info_lines

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Returns:
        tuple: (panels_json, panel_curves, joint_points, debug_info)
    """
    setup_component()

    # Initialize outputs
    panels_json = ""
    panel_curves = DataTree[object]()
    joint_points = DataTree[object]()
    debug_lines = []

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            debug_lines.append(error_msg)
            return panels_json, panel_curves, joint_points, "\n".join(debug_lines)

        # Parse inputs
        walls_data = parse_walls_json(walls_json)
        framing_data = parse_framing_json(framing_json) if framing_json else None
        debug_lines.append(f"Parsed {len(walls_data)} walls")

        # Build configuration
        config = PanelConfig(
            max_panel_length=max_length if max_length else 24.0,
            min_joint_to_opening=joint_opening if joint_opening else 1.0,
            min_joint_to_corner=joint_corner if joint_corner else 2.0,
            stud_spacing=stud_space if stud_space else 1.333,
        )
        debug_lines.append(f"Config: max={config.max_panel_length}ft, stud={config.stud_spacing}ft")

        # Process panelization
        all_results, panel_curves, joint_points, info_lines = process_panelization(
            walls_data, framing_data, config
        )
        debug_lines.extend(info_lines)

        # Serialize results
        panels_json = json.dumps(all_results, indent=2)

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return panels_json, panel_curves, joint_points, "\n".join(debug_lines)

# =============================================================================
# Execution
# =============================================================================

# Set default values for optional inputs
try:
    walls_json
except NameError:
    walls_json = None

try:
    framing_json
except NameError:
    framing_json = None

try:
    max_length
except NameError:
    max_length = None

try:
    joint_opening
except NameError:
    joint_opening = None

try:
    joint_corner
except NameError:
    joint_corner = None

try:
    stud_space
except NameError:
    stud_space = None

try:
    run
except NameError:
    run = False

# Execute main
if __name__ == "__main__":
    panels_json, panel_curves, joint_points, debug_info = main()
