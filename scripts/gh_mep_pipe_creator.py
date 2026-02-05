# File: scripts/gh_mep_pipe_creator.py
"""MEP Pipe Creator for Grasshopper.

Converts MEP route JSON from the OAHS routing algorithm into pipe and conduit
specifications for Revit creation via Rhino.Inside.Revit. This component bridges
the routing results to Revit element creation, generating both pipe segments
and fitting specifications.

Key Features:
1. Route to Pipe Conversion
   - Converts route segments to pipe specifications
   - Maps system types to Revit pipe/conduit types
   - Includes nominal size and diameter information

2. Fitting Detection
   - Detects direction changes for elbow fittings
   - Identifies 90-degree and 45-degree bends
   - Generates fitting specifications with angles

3. Type Override Support
   - Custom pipe type mappings via JSON input
   - Override default Revit type assignments
   - Per-system-type configuration

4. Visual Output
   - LineCurve geometry for pipe path visualization
   - Point3d markers at fitting locations
   - DataTree output for per-route organization

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry creation (via RhinoCommonFactory)
    - Grasshopper: DataTree and component framework
    - json: Parsing route and override data
    - timber_framing_generator: RhinoCommonFactory and revit_pipe_mapper module

Performance Considerations:
    - Linear scaling with number of routes and segments
    - Fitting detection adds minimal overhead per route
    - For >100 routes, consider filtering by system type first

Usage:
    1. Connect routes_json from MEP Router component
    2. Optionally provide type_overrides_json for custom mappings
    3. Toggle create_fittings to enable/disable fitting detection
    4. Set run=True to execute pipe creation
    5. Connect pipe_specs_json to Revit creation component

Input Requirements:
    Routes JSON (routes_json) - str:
        JSON string containing computed routes from OAHS router.
        Must have "routes" array with route objects containing
        "segments" (with start/end coords) and "system_type".
        Required: Yes
        Access: Item

    Type Overrides JSON (type_overrides_json) - str:
        Optional JSON string with custom pipe type mappings.
        Format: {"system_type": {"pipe_type": "...", ...}}
        Required: No (empty string uses defaults)
        Access: Item

    Create Fittings (create_fittings) - bool:
        Enable fitting detection at direction changes.
        Required: No (defaults to True)
        Access: Item

    Run (run) - bool:
        Trigger to execute pipe creation. Set True to process.
        Required: Yes
        Access: Item

Outputs:
    Pipe Specs JSON (pipe_specs_json) - str:
        JSON string with pipe specifications for Revit creation.
        Contains array of pipe objects with endpoints, diameter,
        system type, and Revit configuration.

    Fitting Specs JSON (fitting_specs_json) - str:
        JSON string with fitting specifications.
        Contains array of fitting objects with type, location,
        angle, and connected pipe IDs.

    Curves (curves) - DataTree[Curve]:
        LineCurve visualization of pipe paths.
        One branch per route for selection/filtering.

    Fitting Points (fitting_pts) - List[Point3d]:
        Point3d markers at fitting locations.
        Use for visualization of direction changes.

    Info (info) - str:
        Diagnostic summary string with pipe/fitting counts.

Technical Details:
    - Uses RhinoCommonFactory for all geometry creation
    - Pipe specs include Revit type mapping from revit_pipe_mapper
    - Fittings detected by angle calculation at vertices
    - Empty/invalid JSON returns empty outputs gracefully

Error Handling:
    - Invalid routes_json logs warning and returns empty outputs
    - Invalid type_overrides_json uses defaults with warning
    - Missing fields in route data are skipped with warning
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

from System import Array
from System.Collections.Generic import List

# Rhino / Grasshopper
import Rhino
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Pipe Creator"
COMPONENT_NICKNAME = "MEP-Pipes"
COMPONENT_MESSAGE = "v1.0.0"
COMPONENT_CATEGORY = "TimberFraming"
COMPONENT_SUBCATEGORY = "MEP"

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
        ("Type Overrides JSON", "type_overrides_json", "Optional JSON with custom pipe type mappings",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Create Fittings", "create_fittings", "Enable fitting detection at direction changes (default True)",
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
        ("Pipe Specs JSON", "pipe_specs_json", "JSON string with pipe specifications for Revit"),
        ("Fitting Specs JSON", "fitting_specs_json", "JSON string with fitting specifications"),
        ("Curves", "curves", "LineCurve visualization of pipe paths (DataTree, one branch per route)"),
        ("Fitting Points", "fitting_pts", "Point3d markers at fitting locations"),
        ("Info", "info", "Diagnostic summary string"),
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


def validate_inputs(routes_json_input, run_input):
    """Validate component inputs.

    Args:
        routes_json_input: Routes JSON string to validate
        run_input: Run boolean input

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_input:
        return False, "Set run=True to execute pipe creation"

    if not routes_json_input:
        return False, "Missing routes_json input"

    # Validate JSON parsing
    try:
        data = json.loads(routes_json_input)
        if not isinstance(data, dict):
            return False, "routes_json must be a JSON object"
        if "routes" not in data:
            return False, "routes_json missing 'routes' key"
    except json.JSONDecodeError as e:
        return False, f"Invalid routes_json: {e}"

    return True, None


def create_pipe_curves(pipe_result, factory):
    """Create LineCurve geometry for pipe segments.

    Args:
        pipe_result: PipeCreatorResult with pipes list
        factory: RhinoCommonFactory instance

    Returns:
        tuple: (DataTree of curves organized by route, route_to_index mapping)
    """
    curves_tree = DataTree[object]()
    route_indices = {}  # route_id -> branch index

    for pipe in pipe_result.pipes:
        route_id = pipe.route_id

        # Get or create branch index for this route
        if route_id not in route_indices:
            route_indices[route_id] = len(route_indices)
        branch_idx = route_indices[route_id]
        path = GH_Path(branch_idx)

        # Create LineCurve from pipe endpoints
        try:
            start = pipe.start_point
            end = pipe.end_point

            line_curve = factory.create_line_curve(
                (float(start[0]), float(start[1]), float(start[2])),
                (float(end[0]), float(end[1]), float(end[2]))
            )
            if line_curve is not None:
                curves_tree.Add(line_curve, path)
        except Exception as e:
            log_debug(f"Error creating pipe curve for {pipe.id}: {e}")
            continue

    return curves_tree, route_indices


def create_fitting_points(pipe_result, factory):
    """Create Point3d geometry for fitting locations.

    Args:
        pipe_result: PipeCreatorResult with fittings list
        factory: RhinoCommonFactory instance

    Returns:
        List of Point3d objects at fitting locations
    """
    points = []

    for fitting in pipe_result.fittings:
        try:
            loc = fitting.location
            pt = factory.create_point3d(
                float(loc[0]),
                float(loc[1]),
                float(loc[2])
            )
            if pt is not None:
                points.append(pt)
        except Exception as e:
            log_debug(f"Error creating fitting point for {fitting.id}: {e}")
            continue

    return points


def process_routes(routes_json_str, type_overrides_str, create_fittings_flag):
    """Process route data and generate pipe/fitting specifications.

    Args:
        routes_json_str: JSON string with routes data
        type_overrides_str: Optional JSON string with type overrides
        create_fittings_flag: Boolean to enable fitting detection

    Returns:
        tuple: (pipe_specs_json, fitting_specs_json, curves_tree, fitting_pts, info_string)
    """
    log_info("Starting pipe creation processing")

    # Import the revit_pipe_mapper module
    try:
        from src.timber_framing_generator.mep.routing.revit_pipe_mapper import (
            process_routes_to_pipes,
            detect_junctions,
        )
    except ImportError as e:
        log_error(f"Could not import revit_pipe_mapper: {e}")
        return "", "", DataTree[object](), [], f"Import error: {e}"

    # Get geometry factory
    try:
        factory = get_factory()
    except ImportError as e:
        log_error(f"Could not import geometry factory: {e}")
        return "", "", DataTree[object](), [], f"Import error: {e}"

    # Process routes to pipe specifications
    pipe_result = process_routes_to_pipes(
        routes_json_str,
        type_overrides_str if type_overrides_str else None,
        create_fittings_flag
    )

    log_info(f"Generated {len(pipe_result.pipes)} pipes, {len(pipe_result.fittings)} fittings")

    # Create output JSON strings
    pipe_specs_dict = {
        "pipes": [p.to_dict() for p in pipe_result.pipes],
        "summary": {
            "total_pipes": len(pipe_result.pipes),
        }
    }
    pipe_specs_json = json.dumps(pipe_specs_dict, indent=2)

    fitting_specs_dict = {
        "fittings": [f.to_dict() for f in pipe_result.fittings],
        "summary": {
            "total_fittings": len(pipe_result.fittings),
        }
    }
    fitting_specs_json = json.dumps(fitting_specs_dict, indent=2)

    # Create visualization geometry
    curves_tree, route_indices = create_pipe_curves(pipe_result, factory)
    fitting_pts = create_fitting_points(pipe_result, factory)

    # Detect inter-route junctions
    junctions = detect_junctions(routes_json_str)

    # Build info string
    info_lines = [
        f"Pipes generated: {len(pipe_result.pipes)}",
        f"Fittings detected: {len(pipe_result.fittings)}",
        f"Inter-route junctions: {len(junctions)}",
        f"Routes processed: {len(route_indices)}",
    ]

    if pipe_result.warnings:
        info_lines.append(f"Warnings: {len(pipe_result.warnings)}")
        for warning in pipe_result.warnings[:5]:  # Show first 5 warnings
            info_lines.append(f"  - {warning}")
        if len(pipe_result.warnings) > 5:
            info_lines.append(f"  ... and {len(pipe_result.warnings) - 5} more")

    info_string = "\n".join(info_lines)
    log_info(f"Pipe creation complete: {len(pipe_result.pipes)} pipes, {len(pipe_result.fittings)} fittings")

    return pipe_specs_json, fitting_specs_json, curves_tree, fitting_pts, info_string

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Process route data
    4. Return pipe specifications and visualization geometry

    Returns:
        tuple: (pipe_specs_json, fitting_specs_json, curves, fitting_pts, info) or empty outputs on failure
    """
    # Setup component
    setup_component()

    # Initialize empty outputs
    empty_curves = DataTree[object]()
    empty_points = []

    try:
        # Get inputs (these come from GH component inputs)
        # Use globals() to check if variables are defined
        routes_json_input = routes_json if 'routes_json' in dir() else None
        type_overrides_input = type_overrides_json if 'type_overrides_json' in dir() else ""
        create_fittings_input = create_fittings if 'create_fittings' in dir() else True
        run_input = run if 'run' in dir() else False

        # Handle None/unset boolean inputs with defaults
        if create_fittings_input is None:
            create_fittings_input = True

        # Handle None type overrides as empty string
        if type_overrides_input is None:
            type_overrides_input = ""

        # Validate inputs
        is_valid, error_msg = validate_inputs(routes_json_input, run_input)
        if not is_valid:
            if error_msg and "run=True" not in error_msg:
                log_warning(error_msg)
            return "", "", empty_curves, empty_points, error_msg or "Disabled"

        # Process routes
        pipe_specs_json, fitting_specs_json, curves_tree, fitting_pts, info_string = process_routes(
            routes_json_input,
            type_overrides_input,
            create_fittings_input
        )

        return pipe_specs_json, fitting_specs_json, curves_tree, fitting_pts, info_string

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_debug(traceback.format_exc())
        return "", "", empty_curves, empty_points, f"Error: {str(e)}"

# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    # Execute main and assign to output variables
    # These variable names must match your GH component outputs
    pipe_specs_json, fitting_specs_json, curves, fitting_pts, info = main()
