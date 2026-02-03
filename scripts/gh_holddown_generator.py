# File: scripts/gh_holddown_generator.py
"""Holddown Generator for Grasshopper.

Generates holddown anchor locations at shear wall ends and panel splice points.
Outputs both JSON data for documentation and Rhino Point3d objects for
visualization and coordination with structural engineers.

Key Features:
1. Wall End Holddowns
   - Automatic placement at both ends of each wall
   - Offset from wall end by half stud width (configurable)
   - Tracks load-bearing status for structural coordination

2. Panel Splice Holddowns
   - Optional holddowns at panel boundaries for panelized walls
   - Supports prefab/offsite construction workflows
   - Can be disabled via configuration

3. Visualization
   - Outputs Rhino Point3d objects for display in Grasshopper
   - Points can be baked for Revit coordination
   - Color-code by position type (left/right/splice)

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Point3d creation
    - Grasshopper: Component framework, DataTree
    - timber_framing_generator.framing_elements.holddowns: Holddown logic

Performance Considerations:
    - Very fast: O(n) where n = number of walls + panels
    - Minimal memory usage (point objects only)
    - Suitable for large projects

Usage:
    1. Connect 'walls_json' from Wall Analyzer component
    2. Optionally connect 'panels_json' from Panel Decomposer
    3. Configure offset and splice options via 'config_json'
    4. Set 'run' to True to execute
    5. Collect 'holddown_points' for visualization
    6. Use 'holddowns_json' for documentation

Input Requirements:
    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer with wall geometry data
        Required: Yes
        Access: Item

    Panels JSON (panels_json) - str:
        Optional JSON from Panel Decomposer for panelized walls
        Required: No
        Access: Item

    Config JSON (config_json) - str:
        Optional JSON configuration with:
        - stud_width: Width of end studs in feet (default 0.125 = 1.5")
        - offset_from_end: Distance from wall end (default half stud width)
        - include_splices: Include panel splice holddowns (default True)
        Required: No
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Holddowns JSON (holddowns_json) - str:
        JSON string with holddown locations and metadata

    Holddown Points (holddown_points) - Point3d list:
        Rhino Point3d objects for visualization

    Summary (summary) - str:
        Count summary of holddown types

    Log (log) - str:
        Processing log with debug information

Technical Details:
    - Points created at bottom plate elevation (base of wall)
    - U-coordinate offset accounts for stud centerline
    - Load-bearing flag passed through from wall data
    - Serialization includes XYZ coordinates for external tools

Error Handling:
    - Invalid JSON returns empty results with error in log
    - Walls without base_plane use XY coordinates only
    - Missing panel data falls back to wall-end-only mode

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
# Module Reload (Development Only)
# =============================================================================

FORCE_RELOAD = True

if FORCE_RELOAD:
    modules_to_reload = [key for key in sys.modules.keys()
                         if 'timber_framing_generator' in key]
    for mod_name in modules_to_reload:
        del sys.modules[mod_name]

# =============================================================================
# Project Imports (after reload)
# =============================================================================

from src.timber_framing_generator.framing_elements.holddowns import (
    generate_holddown_locations,
    get_holddown_summary,
    HolddownPosition,
)

# Try to import geometry factory for RhinoCommon points
try:
    from src.timber_framing_generator.utils.geometry_factory import get_factory
    FACTORY_AVAILABLE = True
except ImportError:
    FACTORY_AVAILABLE = False

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Holddown Generator"
COMPONENT_NICKNAME = "Holddown"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "5-Connections"

DEFAULT_CONFIG = {
    "stud_width": 0.125,  # 1.5 inches in feet
    "offset_from_end": None,  # Will default to half stud width
    "include_splices": True,
}

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message."""
    print(f"[{level.upper()}] {message}")

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)


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
    """Initialize and configure the Grasshopper component."""
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Walls JSON", "walls_json", "JSON string from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Panels JSON", "panels_json", "Optional JSON from Panel Decomposer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json", "Optional configuration JSON",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run", "Boolean to trigger execution",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1)
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Holddowns JSON", "holddowns_json", "JSON with holddown location data"),
        ("Holddown Points", "holddown_points", "Rhino Point3d objects"),
        ("Summary", "summary", "Count summary"),
        ("Log", "log", "Processing log"),
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
    """Validate component inputs."""
    if not run:
        return False, "Run is False - component disabled"

    if walls_json is None or not walls_json.strip():
        return False, "walls_json is required"

    return True, None


def parse_config(config_json):
    """Parse configuration JSON with defaults."""
    config = dict(DEFAULT_CONFIG)

    if config_json and config_json.strip():
        try:
            user_config = json.loads(config_json)
            config.update(user_config)
            log_info(f"Applied user config: {list(user_config.keys())}")
        except json.JSONDecodeError as e:
            log_warning(f"Invalid config_json, using defaults: {e}")

    # Set offset_from_end default if not specified
    if config["offset_from_end"] is None:
        config["offset_from_end"] = config["stud_width"] / 2

    return config


def reconstruct_base_plane(plane_data):
    """Reconstruct Rhino Plane from JSON data.

    Args:
        plane_data: Dict with origin, x_axis, y_axis or None

    Returns:
        rg.Plane or None
    """
    if plane_data is None:
        return None

    try:
        if isinstance(plane_data, dict):
            origin = plane_data.get("origin", [0, 0, 0])
            x_axis = plane_data.get("x_axis", [1, 0, 0])
            y_axis = plane_data.get("y_axis", [0, 0, 1])

            return rg.Plane(
                rg.Point3d(origin[0], origin[1], origin[2]),
                rg.Vector3d(x_axis[0], x_axis[1], x_axis[2]),
                rg.Vector3d(y_axis[0], y_axis[1], y_axis[2])
            )
        elif hasattr(plane_data, 'Origin'):
            # Already a Plane object
            return plane_data
    except Exception as e:
        log_warning(f"Failed to reconstruct plane: {e}")

    return None


def holddown_to_point(holddown):
    """Convert HolddownLocation to Rhino Point3d.

    Args:
        holddown: HolddownLocation object

    Returns:
        rg.Point3d or None
    """
    point = holddown.point

    if point is None:
        return None

    try:
        if hasattr(point, 'X'):
            # Already a Point3d
            return rg.Point3d(float(point.X), float(point.Y), float(point.Z))
        elif isinstance(point, (list, tuple)) and len(point) >= 3:
            # Tuple coordinates
            return rg.Point3d(float(point[0]), float(point[1]), float(point[2]))
    except Exception as e:
        log_warning(f"Failed to convert holddown point: {e}")

    return None


def process_walls(walls_json, panels_json, config):
    """Process walls and generate holddown locations.

    Args:
        walls_json: JSON string with wall data
        panels_json: Optional JSON string with panel data
        config: Configuration dictionary

    Returns:
        tuple: (all_holddowns, points_list, summary_text, log_lines)
    """
    log_lines = []
    all_holddowns = []
    all_points = []

    # Parse walls JSON
    try:
        walls_data = json.loads(walls_json)
    except json.JSONDecodeError as e:
        log_error(f"Failed to parse walls_json: {e}")
        return [], [], "Error: Invalid JSON", [f"JSON parse error: {e}"]

    # Handle single wall or list
    if isinstance(walls_data, dict):
        walls_list = [walls_data]
    elif isinstance(walls_data, list):
        walls_list = walls_data
    else:
        log_error("walls_json must be a dict or list")
        return [], [], "Error: Invalid format", ["Invalid walls_json format"]

    # Parse panels JSON if provided
    panels_by_wall = {}
    if panels_json and panels_json.strip():
        try:
            panels_data = json.loads(panels_json)
            # Index panels by wall_id
            if isinstance(panels_data, list):
                for panel in panels_data:
                    wall_id = panel.get("wall_id", "unknown")
                    if wall_id not in panels_by_wall:
                        panels_by_wall[wall_id] = []
                    panels_by_wall[wall_id].append(panel)
            log_info(f"Loaded panels for {len(panels_by_wall)} walls")
        except json.JSONDecodeError as e:
            log_warning(f"Invalid panels_json, ignoring: {e}")

    log_info(f"Processing {len(walls_list)} walls")
    log_lines.append(f"Processing {len(walls_list)} walls")

    for i, wall_data in enumerate(walls_list):
        wall_id = str(wall_data.get("wall_id", f"wall_{i}"))
        log_info(f"Processing wall {wall_id}")

        try:
            # Reconstruct base_plane if it's serialized
            base_plane = wall_data.get("base_plane")
            if isinstance(base_plane, dict):
                wall_data["base_plane"] = reconstruct_base_plane(base_plane)

            # Get panels for this wall (if any)
            wall_panels = panels_by_wall.get(wall_id, None)

            # Generate holddowns
            holddowns = generate_holddown_locations(
                wall_data,
                config=config,
                panels_data=wall_panels
            )

            all_holddowns.extend(holddowns)

            # Convert to points
            for h in holddowns:
                pt = holddown_to_point(h)
                if pt is not None:
                    all_points.append(pt)

            log_lines.append(f"  Wall {wall_id}: {len(holddowns)} holddowns")

        except Exception as e:
            log_warning(f"Error processing wall {wall_id}: {e}")
            log_lines.append(f"  Wall {wall_id}: ERROR - {e}")
            continue

    # Build summary
    summary_dict = get_holddown_summary(all_holddowns)
    summary_text = (
        f"Total Holddowns: {summary_dict['total_holddowns']}\n"
        f"Wall End: {summary_dict['wall_end_holddowns']}\n"
        f"Splice: {summary_dict['splice_holddowns']}\n"
        f"Load-Bearing: {summary_dict['load_bearing_count']}"
    )

    log_info(f"Total: {len(all_holddowns)} holddowns")

    return all_holddowns, all_points, summary_text, log_lines


# =============================================================================
# Main Function
# =============================================================================

def main(walls_json_in, panels_json_in, config_json_in, run_in):
    """Main entry point for the component.

    Args:
        walls_json_in: JSON string from Wall Analyzer
        panels_json_in: Optional JSON from Panel Decomposer
        config_json_in: Optional configuration JSON
        run_in: Boolean to trigger execution
    """
    setup_component()

    try:
        # Use inputs passed as arguments
        walls_json_input = walls_json_in
        panels_json_input = panels_json_in
        config_json_input = config_json_in
        run_input = run_in

        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json_input, run_input)
        if not is_valid:
            log_info(error_msg)
            return "", [], error_msg, error_msg

        # Parse configuration
        config = parse_config(config_json_input)

        # Process walls
        holddowns, points, summary_text, log_lines = process_walls(
            walls_json_input, panels_json_input, config
        )

        # Serialize holddowns to JSON
        holddowns_dicts = [h.to_dict() for h in holddowns]
        holddowns_json_output = json.dumps(holddowns_dicts, indent=2)

        log_output = "\n".join(log_lines)

        return holddowns_json_output, points, summary_text, log_output

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return "", [], error_msg, traceback.format_exc()


# =============================================================================
# Execution
# =============================================================================

# In GHPython, input variables are injected as globals based on NickName.
# We access them directly here and pass to main() for clarity.
# NOTE: After pasting this script, you may need to:
#   1. Set the correct number of inputs (4) and outputs (4)
#   2. Right-click each input and rename the NickName to match:
#      Input 0: walls_json
#      Input 1: panels_json
#      Input 2: config_json
#      Input 3: run

try:
    _walls_json = walls_json
except NameError:
    _walls_json = None

try:
    _panels_json = panels_json
except NameError:
    _panels_json = None

try:
    _config_json = config_json
except NameError:
    _config_json = None

try:
    _run = run
except NameError:
    _run = False

holddowns_json, holddown_points, summary, log = main(
    _walls_json, _panels_json, _config_json, _run
)
