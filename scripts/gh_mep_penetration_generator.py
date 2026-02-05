# File: scripts/gh_mep_penetration_generator.py
"""MEP Penetration Generator for Grasshopper.

Converts MEP routes to penetration specifications with code compliance validation.
This component bridges the OAHS routing output to existing penetration rules,
producing validated penetration specs with code compliance and reinforcement flags.

Key Features:
1. Route-to-Penetration Conversion
   - Parses routes_json from MEP Router
   - Intersects routes with framing elements
   - Generates penetration specifications

2. Code Compliance Validation
   - Checks penetration size vs member depth
   - Flags blocked penetrations exceeding limits
   - Identifies penetrations requiring reinforcement

3. Visual Status Feedback
   - Allowed penetrations (green points)
   - Blocked penetrations (red points)
   - Reinforcement required (orange points)

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry creation (via RhinoCommonFactory)
    - Grasshopper: DataTree and component framework
    - json: Parsing route and framing data
    - timber_framing_generator: RhinoCommonFactory for assembly-safe geometry
    - penetration_integration: Route-to-penetration logic with code compliance

Performance Considerations:
    - Linear scaling with number of routes and framing elements
    - Geometry creation via factory adds minimal overhead
    - For >100 routes, ensure framing_json is well-structured

Usage:
    1. Connect routes_json from MEP Router component
    2. Connect framing_json from Framing Generator component
    3. Optionally adjust clearance (default 0.0208 ft = 1/4")
    4. Set run=True to execute penetration analysis
    5. Connect point outputs to Preview with appropriate colors

Input Requirements:
    Routes JSON (routes_json) - str:
        JSON string containing computed routes from OAHS router.
        Must have "routes" array with route objects containing
        "segments" (with start/end coords) and system_type.
        Required: Yes
        Access: Item

    Framing JSON (framing_json) - str:
        JSON string containing framing elements from Framing Generator.
        Elements need centerlines and profile information for
        penetration validation.
        Required: Yes
        Access: Item

    Clearance (clearance) - float:
        Pipe clearance in feet added around penetrations.
        Required: No (defaults to 0.0208 = 1/4")
        Access: Item

    Run (run) - bool:
        Trigger to execute penetration analysis. Set True to process.
        Required: Yes
        Access: Item

Outputs:
    Penetrations JSON (penetrations_json) - str:
        Full penetration specifications as JSON string with
        location, size, is_allowed, reinforcement_required flags.

    Allowed Points (allowed_pts) - List[Point3d]:
        Point3d for allowed penetrations (display green).
        No code violations.

    Blocked Points (blocked_pts) - List[Point3d]:
        Point3d for blocked penetrations (display red).
        Exceed code limits - require rerouting.

    Reinforce Points (reinforce_pts) - List[Point3d]:
        Point3d needing reinforcement (display orange).
        Allowed but require structural reinforcement.

    Info (info) - str:
        Diagnostic summary string with processing statistics.

Technical Details:
    - Uses RhinoCommonFactory for all geometry creation
    - Code limits based on IRC/building code penetration rules
    - Penetration ratio checked against member depth
    - JSON output compatible with downstream components

Error Handling:
    - Invalid JSON logs warning and returns empty outputs
    - Missing fields in route/framing data are skipped with warning
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

COMPONENT_NAME = "MEP Penetration Generator"
COMPONENT_NICKNAME = "MEP-Pen"
COMPONENT_MESSAGE = "v1.0.0"
COMPONENT_CATEGORY = "TimberFraming"
COMPONENT_SUBCATEGORY = "MEP"

DEFAULT_CLEARANCE = 0.0208  # 1/4" in feet

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
        ("Framing JSON", "framing_json", "JSON string with framing elements from Framing Generator",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Clearance", "clearance", "Pipe clearance in feet (default 0.0208 = 1/4\")",
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
        ("Penetrations JSON", "penetrations_json", "Full penetration specs as JSON string"),
        ("Allowed Points", "allowed_pts", "Point3d for allowed penetrations (green)"),
        ("Blocked Points", "blocked_pts", "Point3d for blocked penetrations (red)"),
        ("Reinforce Points", "reinforce_pts", "Point3d needing reinforcement (orange)"),
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


def validate_inputs(routes_json_input, framing_json_input, run_input):
    """Validate component inputs.

    Args:
        routes_json_input: Routes JSON string to validate
        framing_json_input: Framing JSON string to validate
        run_input: Run boolean input

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_input:
        return False, "Set run=True to execute penetration analysis"

    if not routes_json_input:
        return False, "Missing routes_json input"

    if not framing_json_input:
        return False, "Missing framing_json input"

    # Validate routes JSON parsing
    try:
        data = json.loads(routes_json_input)
        if not isinstance(data, dict):
            return False, "routes_json must be a JSON object"
        if "routes" not in data:
            return False, "routes_json missing 'routes' key"
    except json.JSONDecodeError as e:
        return False, f"Invalid routes_json: {e}"

    # Validate framing JSON parsing
    try:
        framing_data = json.loads(framing_json_input)
        # Framing JSON can be a list or dict - just check it parses
    except json.JSONDecodeError as e:
        return False, f"Invalid framing_json: {e}"

    return True, None


def create_status_points(penetrations, factory):
    """Create Point3d geometry grouped by penetration status.

    Args:
        penetrations: List of penetration specification dictionaries
        factory: RhinoCommonFactory instance

    Returns:
        tuple: (allowed_points, blocked_points, reinforcement_points)
    """
    from src.timber_framing_generator.mep.routing.penetration_integration import (
        extract_penetration_points,
    )

    # Get coordinate tuples grouped by status
    allowed_coords, blocked_coords, reinforce_coords = extract_penetration_points(penetrations)

    # Convert to Point3d using factory
    allowed_pts = []
    for coord in allowed_coords:
        try:
            pt = factory.create_point3d(
                float(coord[0]),
                float(coord[1]),
                float(coord[2])
            )
            if pt is not None:
                allowed_pts.append(pt)
        except Exception as e:
            log_debug(f"Error creating allowed point: {e}")

    blocked_pts = []
    for coord in blocked_coords:
        try:
            pt = factory.create_point3d(
                float(coord[0]),
                float(coord[1]),
                float(coord[2])
            )
            if pt is not None:
                blocked_pts.append(pt)
        except Exception as e:
            log_debug(f"Error creating blocked point: {e}")

    reinforce_pts = []
    for coord in reinforce_coords:
        try:
            pt = factory.create_point3d(
                float(coord[0]),
                float(coord[1]),
                float(coord[2])
            )
            if pt is not None:
                reinforce_pts.append(pt)
        except Exception as e:
            log_debug(f"Error creating reinforcement point: {e}")

    return allowed_pts, blocked_pts, reinforce_pts


def process_penetrations(routes_json_str, framing_json_str, clearance_value):
    """Process route data and generate penetration specifications.

    Args:
        routes_json_str: JSON string with routes data
        framing_json_str: JSON string with framing data
        clearance_value: Pipe clearance in feet

    Returns:
        tuple: (penetrations_json, allowed_pts, blocked_pts, reinforce_pts, info_string)
    """
    log_info("Starting penetration analysis")

    # Import penetration integration functions
    try:
        from src.timber_framing_generator.mep.routing.penetration_integration import (
            integrate_routes_to_penetrations,
            penetrations_to_json,
            get_penetration_info_string,
        )
    except ImportError as e:
        log_error(f"Could not import penetration_integration: {e}")
        return "", [], [], [], f"Import error: {e}"

    # Get geometry factory
    try:
        factory = get_factory()
    except ImportError as e:
        log_error(f"Could not import geometry factory: {e}")
        return "", [], [], [], f"Import error: {e}"

    # Run penetration integration
    try:
        result = integrate_routes_to_penetrations(
            routes_json=routes_json_str,
            framing_json=framing_json_str,
            clearance=clearance_value,
        )
    except ValueError as e:
        log_error(f"Penetration analysis failed: {e}")
        return "", [], [], [], f"Analysis error: {e}"
    except Exception as e:
        log_error(f"Unexpected error in penetration analysis: {e}")
        log_debug(traceback.format_exc())
        return "", [], [], [], f"Unexpected error: {e}"

    # Convert result to JSON
    penetrations_json_out = penetrations_to_json(result)

    # Get info string
    info_string = get_penetration_info_string(result)

    # Extract penetrations for point creation
    penetrations = result.get("penetrations", [])

    # Create status-grouped points
    allowed_pts, blocked_pts, reinforce_pts = create_status_points(penetrations, factory)

    log_info(f"Penetration analysis complete: {len(allowed_pts)} allowed, {len(blocked_pts)} blocked, {len(reinforce_pts)} need reinforcement")

    return penetrations_json_out, allowed_pts, blocked_pts, reinforce_pts, info_string

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Process penetration analysis
    4. Return results

    Returns:
        tuple: (penetrations_json, allowed_pts, blocked_pts, reinforce_pts, info)
               or empty outputs on failure
    """
    # Setup component
    setup_component()

    # Initialize empty outputs
    empty_json = ""
    empty_pts = []

    try:
        # Get inputs (these come from GH component inputs)
        # Use globals() to check if variables are defined
        routes_json_input = routes_json if 'routes_json' in dir() else None
        framing_json_input = framing_json if 'framing_json' in dir() else None
        clearance_input = clearance if 'clearance' in dir() else None
        run_input = run if 'run' in dir() else False

        # Handle None/unset clearance with default
        if clearance_input is None:
            clearance_input = DEFAULT_CLEARANCE

        # Validate inputs
        is_valid, error_msg = validate_inputs(routes_json_input, framing_json_input, run_input)
        if not is_valid:
            if error_msg and "run=True" not in error_msg:
                log_warning(error_msg)
            return empty_json, empty_pts, empty_pts, empty_pts, error_msg or "Disabled"

        # Process penetrations
        penetrations_json_out, allowed_pts, blocked_pts, reinforce_pts, info_string = process_penetrations(
            routes_json_input,
            framing_json_input,
            clearance_input
        )

        return penetrations_json_out, allowed_pts, blocked_pts, reinforce_pts, info_string

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_debug(traceback.format_exc())
        return empty_json, empty_pts, empty_pts, empty_pts, f"Error: {str(e)}"

# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    # Execute main and assign to output variables
    # These variable names must match your GH component outputs
    penetrations_json, allowed_pts, blocked_pts, reinforce_pts, info = main()
