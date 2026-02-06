# File: scripts/gh_mep_route_visualizer.py
"""MEP Route Visualizer for Grasshopper.

Converts MEP route JSON from the OAHS routing algorithm into visual Rhino
geometry for display and inspection. This component is the visualization
endpoint of the MEP routing pipeline.

Key Features:
1. Route Visualization
   - Converts route segments to Line/Curve geometry
   - Supports system-type based color coding
   - Creates junction/Steiner point markers

2. System Color Coding
   - Distinct colors for each MEP system type
   - sanitary_drain (Brown), sanitary_vent (Gray)
   - dhw (Red), dcw (Blue), power (Yellow)
   - data (Orange), lighting (White)

3. DataTree Output
   - One branch per route for curves and points
   - Enables per-route selection and analysis
   - Compatible with downstream visualization tools

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry creation (via RhinoCommonFactory)
    - Grasshopper: DataTree and component framework
    - System.Drawing: Color definitions for visualization
    - json: Parsing route data from upstream components
    - timber_framing_generator: RhinoCommonFactory for assembly-safe geometry

Performance Considerations:
    - Linear scaling with number of routes and segments
    - Geometry creation via factory adds minimal overhead
    - For >100 routes, consider filtering by system type

Usage:
    1. Connect routes_json from MEP Router component
    2. Optionally toggle color_by_system for system-type coloring
    3. Optionally toggle show_junctions to display junction points
    4. Set run=True to execute visualization
    5. Connect curves output to Preview or other display components

Input Requirements:
    Routes JSON (routes_json) - str:
        JSON string containing computed routes from OAHS router.
        Must have "routes" array with route objects containing
        "segments" (with start/end coords) and optional "junctions".
        Required: Yes
        Access: Item

    Color by System (color_by_system) - bool:
        Enable system-type based color coding for route curves.
        Required: No (defaults to True)
        Access: Item

    Show Junctions (show_junctions) - bool:
        Display junction/Steiner points as Point3d geometry.
        Required: No (defaults to True)
        Access: Item

    Run (run) - bool:
        Trigger to execute visualization. Set True to process.
        Required: Yes
        Access: Item

Outputs:
    Curves (curves) - DataTree[Curve]:
        Route curves as LineCurves, one branch per route.
        Connect to Preview component for visualization.

    Colors (colors) - List[System.Drawing.Color]:
        Color list matching curves for system-type visualization.
        Use with Custom Preview for colored display.

    Points (points) - DataTree[Point3d]:
        Junction/Steiner points, one branch per route.
        Useful for debugging routing decisions.

    Info (info) - str:
        Diagnostic information string with processing summary.

Technical Details:
    - Uses RhinoCommonFactory for all geometry creation
    - Colors use System.Drawing.Color for GH compatibility
    - DataTrees preserve route-level grouping for selection
    - Empty/invalid JSON returns empty outputs gracefully

Error Handling:
    - Invalid JSON logs warning and returns empty outputs
    - Missing fields in route data are skipped with warning
    - Geometry creation failures logged but don't halt processing
    - run=False returns immediately with "Disabled" info message

Author: Fernando Maytorena
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
clr.AddReference("System.Drawing")

from System import Array
from System.Collections.Generic import List
from System.Drawing import Color

# Rhino / Grasshopper
import Rhino
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Route Visualizer"
COMPONENT_NICKNAME = "MEP-Viz"
COMPONENT_MESSAGE = "v1.0.0"
COMPONENT_CATEGORY = "TimberFraming"
COMPONENT_SUBCATEGORY = "MEP"

# System color mapping: system_type (lowercase) -> (R, G, B)
# Includes both Revit PascalCase names (lowered) and shorthand aliases.
SYSTEM_COLORS = {
    # Revit system types (lowercase)
    "sanitary": (139, 90, 43),             # Brown
    "domesticcoldwater": (0, 100, 255),    # Blue
    "domestichotwater": (255, 50, 50),     # Red
    "vent": (128, 128, 128),               # Gray
    # Shorthand aliases (legacy / OAHS format)
    "sanitary_drain": (139, 90, 43),       # Brown
    "sanitary_vent": (128, 128, 128),      # Gray
    "dhw": (255, 50, 50),                  # Red
    "dcw": (0, 100, 255),                  # Blue
    # Other trades
    "power": (255, 255, 0),                # Yellow
    "data": (255, 165, 0),                 # Orange
    "lighting": (255, 255, 255),           # White
    "default": (0, 255, 0),                # Green
}

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log
        level: One of "info", "debug", "warning", "error", "remark"
    """
    # Always print to console (captured by 'out' parameter and log files)
    print(f"[{level.upper()}] {message}")

    # Add to GH component UI for warnings and errors
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
    2. Configuring input parameter names, descriptions, and access
    3. Configuring output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # IMPORTANT: In GHPython, the NickName becomes the Python variable name!
    # Format: (DisplayName, variable_name, Description, Access)
    # - Name: Human-readable display name (shown in tooltips)
    # - NickName: MUST be valid Python identifier - this IS the variable name in code
    # - Access: item, list, or tree
    #
    # NOTE: Type Hints must be set via GH UI (right-click -> Type hint)
    # They cannot be set programmatically from within the script.
    inputs = ghenv.Component.Params.Input

    input_config = [
        # (DisplayName, variable_name, Description, Access)
        ("Routes JSON", "routes_json", "JSON string with computed routes from OAHS router",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Color by System", "color_by_system", "Enable system-type color coding (default True)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Show Junctions", "show_junctions", "Display junction/Steiner points (default True)",
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

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    # IMPORTANT: NickName becomes the Python variable name - must match code!
    outputs = ghenv.Component.Params.Output

    output_config = [
        # (DisplayName, variable_name, Description) - indices start at 1
        ("Curves", "curves", "Route curves as LineCurves (DataTree, one branch per route)"),
        ("Colors", "colors", "System.Drawing.Color list matching curves"),
        ("Points", "points", "Junction/Steiner points (DataTree, one branch per route)"),
        ("Info", "info", "Diagnostic information string"),
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

def get_factory():
    """Get RhinoCommonFactory instance for geometry creation.

    Returns:
        RhinoCommonFactory instance

    Raises:
        ImportError: If timber_framing_generator is not installed
    """
    from src.timber_framing_generator.utils.geometry_factory import get_factory as _get_factory
    return _get_factory()


def get_system_color(system_type, color_by_system=True):
    """Get System.Drawing.Color for a system type.

    Args:
        system_type: MEP system type string (e.g., "sanitary_drain", "dhw")
        color_by_system: If False, return default green for all systems

    Returns:
        System.Drawing.Color instance
    """
    if not color_by_system:
        rgb = SYSTEM_COLORS["default"]
    else:
        # Normalize system type (lowercase, strip whitespace)
        system_key = system_type.lower().strip() if system_type else "default"
        rgb = SYSTEM_COLORS.get(system_key, SYSTEM_COLORS["default"])

    return Color.FromArgb(255, rgb[0], rgb[1], rgb[2])


def validate_inputs(routes_json_input, run_input):
    """Validate component inputs.

    Args:
        routes_json_input: Routes JSON string to validate
        run_input: Run boolean input

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_input:
        return False, "Set run=True to execute visualization"

    if not routes_json_input:
        return False, "Missing routes_json input"

    # Validate JSON parsing
    try:
        data = json.loads(routes_json_input)
        if not isinstance(data, dict):
            return False, "routes_json must be a JSON object"
        # Accept either "routes" (old OAHS format) or "wall_routes" (Phase 2)
        if "routes" not in data and "wall_routes" not in data:
            return False, "routes_json missing 'routes' or 'wall_routes' key"
    except json.JSONDecodeError as e:
        return False, f"Invalid routes_json: {e}"

    return True, None


def parse_routes(routes_json_str):
    """Parse routes from JSON string.

    Supports two formats:
    - Old OAHS format: {"routes": [{"route_id", "system_type", "segments", ...}]}
    - Phase 2 wall_routes format: {"wall_routes": [{"connector_id", "system_type",
      "world_segments", ...}]}

    Args:
        routes_json_str: JSON string with routes data

    Returns:
        List of route dictionaries in visualizer format
    """
    data = json.loads(routes_json_str)

    # Old format: routes key with 3D segments
    if "routes" in data:
        return data["routes"]

    # Phase 2 format: wall_routes with world_segments
    if "wall_routes" in data:
        adapted = []
        for wr in data["wall_routes"]:
            adapted.append({
                "route_id": wr.get("connector_id", "unknown"),
                "system_type": wr.get("system_type", "default"),
                "segments": wr.get("world_segments", []),
                "junctions": [],
            })
        return adapted

    return []


def create_route_curves(route, factory):
    """Create LineCurve geometry for route segments.

    Args:
        route: Route dictionary with "segments" list
        factory: RhinoCommonFactory instance

    Returns:
        List of LineCurve objects from RhinoCommon assembly
    """
    curves = []
    segments = route.get("segments", [])

    for seg in segments:
        start_coords = seg.get("start")
        end_coords = seg.get("end")

        if not start_coords or not end_coords:
            log_debug(f"Skipping segment with missing start/end in route {route.get('route_id', 'unknown')}")
            continue

        if len(start_coords) < 3 or len(end_coords) < 3:
            log_debug(f"Skipping segment with incomplete coordinates")
            continue

        try:
            # Use factory to create LineCurve (ensures RhinoCommon assembly)
            line_curve = factory.create_line_curve(
                tuple(start_coords[:3]),
                tuple(end_coords[:3])
            )
            if line_curve is not None:
                curves.append(line_curve)
        except Exception as e:
            log_debug(f"Error creating line curve: {e}")
            continue

    return curves


def create_junction_points(route, factory):
    """Create Point3d geometry for route junctions.

    Args:
        route: Route dictionary with "junctions" list
        factory: RhinoCommonFactory instance

    Returns:
        List of Point3d objects from RhinoCommon assembly
    """
    points = []
    junctions = route.get("junctions", [])

    for junction in junctions:
        if not junction or len(junction) < 3:
            log_debug(f"Skipping junction with incomplete coordinates")
            continue

        try:
            # Use factory to create Point3d (ensures RhinoCommon assembly)
            pt = factory.create_point3d(
                float(junction[0]),
                float(junction[1]),
                float(junction[2])
            )
            if pt is not None:
                points.append(pt)
        except Exception as e:
            log_debug(f"Error creating junction point: {e}")
            continue

    return points


def process_routes(routes_json_str, color_by_system, show_junctions):
    """Process route data and generate visualization geometry.

    Args:
        routes_json_str: JSON string with routes data
        color_by_system: Enable system-type color coding
        show_junctions: Include junction points in output

    Returns:
        tuple: (curves_tree, colors_list, points_tree, info_string)
    """
    log_info("Starting route visualization processing")

    # Get geometry factory
    try:
        factory = get_factory()
    except ImportError as e:
        log_error(f"Could not import geometry factory: {e}")
        return DataTree[object](), [], DataTree[object](), f"Import error: {e}"

    # Parse routes
    routes = parse_routes(routes_json_str)
    log_info(f"Parsed {len(routes)} routes")

    # Initialize output structures
    curves_tree = DataTree[object]()
    points_tree = DataTree[object]()
    colors_list = []

    # Track statistics
    total_curves = 0
    total_points = 0
    system_counts = {}

    # Process each route
    for route_idx, route in enumerate(routes):
        route_id = route.get("route_id", f"route_{route_idx}")
        system_type = route.get("system_type", "default")

        log_debug(f"Processing route {route_id} (system: {system_type})")

        # Track system counts
        system_counts[system_type] = system_counts.get(system_type, 0) + 1

        # Create path for this route
        path = GH_Path(route_idx)

        # Create route curves
        route_curves = create_route_curves(route, factory)
        for curve in route_curves:
            curves_tree.Add(curve, path)
            # Add color for each curve
            colors_list.append(get_system_color(system_type, color_by_system))
        total_curves += len(route_curves)

        # Create junction points if requested
        if show_junctions:
            route_points = create_junction_points(route, factory)
            for pt in route_points:
                points_tree.Add(pt, path)
            total_points += len(route_points)

    # Build info string
    info_lines = [
        f"Routes processed: {len(routes)}",
        f"Total curve segments: {total_curves}",
        f"Total junction points: {total_points}",
        "System breakdown:",
    ]
    for sys_type, count in sorted(system_counts.items()):
        info_lines.append(f"  - {sys_type}: {count} routes")

    info_string = "\n".join(info_lines)
    log_info(f"Visualization complete: {total_curves} curves, {total_points} points")

    return curves_tree, colors_list, points_tree, info_string

# =============================================================================
# Main Function
# =============================================================================

def main(routes_json_input, color_by_system_input, show_junctions_input, run_input):
    """Main entry point for the component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Process route data
    4. Return visualization geometry

    Args:
        routes_json_input: JSON string with route data.
        color_by_system_input: Enable system-type color coding.
        show_junctions_input: Display junction points.
        run_input: Boolean trigger.

    Returns:
        tuple: (curves, colors, points, info) or empty outputs on failure
    """
    # Setup component (display only, AFTER inputs captured)
    setup_component()

    # Initialize empty outputs
    empty_curves = DataTree[object]()
    empty_colors = []
    empty_points = DataTree[object]()

    try:
        # Handle None/unset boolean inputs with defaults
        if color_by_system_input is None:
            color_by_system_input = True
        if show_junctions_input is None:
            show_junctions_input = True

        # Validate inputs
        is_valid, error_msg = validate_inputs(routes_json_input, run_input)
        if not is_valid:
            if error_msg and "run=True" not in error_msg:
                log_warning(error_msg)
            return empty_curves, empty_colors, empty_points, error_msg or "Disabled"

        # Process routes
        curves_tree, colors_list, points_tree, info_string = process_routes(
            routes_json_input,
            color_by_system_input,
            show_junctions_input
        )

        return curves_tree, colors_list, points_tree, info_string

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_debug(traceback.format_exc())
        return empty_curves, empty_colors, empty_points, f"Error: {str(e)}"

# =============================================================================
# Execution
# =============================================================================

# Capture GH globals at module level (BEFORE main() is called)
# dir() inside a function only sees local scope -- GH injects at module level.
try:
    _routes_json = routes_json
except NameError:
    _routes_json = None

try:
    _color_by_system = color_by_system
except NameError:
    _color_by_system = True

try:
    _show_junctions = show_junctions
except NameError:
    _show_junctions = True

try:
    _run = run
except NameError:
    _run = False

if __name__ == "__main__":
    curves, colors, points, info = main(
        _routes_json, _color_by_system, _show_junctions, _run
    )
