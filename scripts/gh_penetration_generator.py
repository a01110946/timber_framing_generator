# File: scripts/gh_penetration_generator.py
"""Penetration Generator for Grasshopper.

Generates penetration specifications for pipes passing through framing.
This is the third step in the MEP integration pipeline.

Key Features:
1. Penetration Detection
   - Finds where pipe routes cross framing members (studs)
   - Calculates intersection points

2. Code Compliance
   - Checks penetration size against member depth limits
   - Flags oversized penetrations with warnings
   - Identifies where reinforcement is required

3. Geometry Output
   - Creates circles representing hole locations
   - Uses RhinoCommonFactory for proper assembly compatibility

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry creation
    - Grasshopper: Component framework
    - timber_framing_generator.mep.plumbing: Penetration generation logic
    - timber_framing_generator.utils.geometry_factory: RhinoCommon geometry

Input Requirements:
    routes_json (routes_json) - str:
        JSON from Pipe Router
        Required: Yes
        Access: Item

    elements_json (elements_json) - str:
        JSON with framing elements (from Framing Generator)
        Required: Yes
        Access: Item

    run (run) - bool:
        Execute toggle
        Required: Yes
        Access: Item

Outputs:
    penetrations_json (json) - str:
        JSON with penetration specifications

    penetration_points (pts) - list of Point3d:
        Point3d at each penetration center

    penetration_circles (circles) - list of Curves:
        Circle curves representing holes

    warnings (warnings) - list of str:
        List of warning messages for problematic penetrations

    debug_info (info) - str:
        Processing summary and diagnostics

Author: Claude AI Assistant
Version: 1.1.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import sys
import json
import math
import traceback

# Force reload of project modules (development only)
FORCE_RELOAD = True
if FORCE_RELOAD:
    modules_to_reload = [k for k in sys.modules.keys()
                         if 'timber_framing_generator' in k]
    for mod_name in modules_to_reload:
        del sys.modules[mod_name]

# .NET / CLR
import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

# Rhino / Grasshopper
import Rhino
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Penetration Generator"
COMPONENT_NICKNAME = "PenGen"
COMPONENT_MESSAGE = "v1.1"

# Project path
PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# =============================================================================
# Project Imports
# =============================================================================

try:
    from src.timber_framing_generator.mep.plumbing import generate_plumbing_penetrations
    from src.timber_framing_generator.core import MEPRoute
    from src.timber_framing_generator.utils.geometry_factory import get_factory
    PROJECT_AVAILABLE = True
    PROJECT_ERROR = None
except ImportError as e:
    PROJECT_AVAILABLE = False
    PROJECT_ERROR = str(e)

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
    print(f"[INFO] {message}")


def log_warning(message):
    log_message(message, "warning")


def log_error(message):
    log_message(message, "error")

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component."""
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE

# =============================================================================
# Helper Functions
# =============================================================================

def validate_inputs():
    """Validate component inputs."""
    if not PROJECT_AVAILABLE:
        return False, f"Project import error: {PROJECT_ERROR}"

    if not run:
        return False, "Toggle 'run' to True to execute"

    if not routes_json:
        return False, "No routes_json provided (connect from Pipe Router)"

    if not elements_json:
        return False, "No elements_json provided (connect from Framing Generator)"

    return True, None


def parse_routes(routes_json_str):
    """Parse routes from JSON string.

    Returns:
        tuple: (routes list, error message or None)
    """
    try:
        data = json.loads(routes_json_str)
        route_list = data.get("routes", [])

        routes = []
        for route_dict in route_list:
            route = MEPRoute.from_dict(route_dict)
            routes.append(route)

        return routes, None
    except json.JSONDecodeError as e:
        return [], f"JSON parse error: {e}"
    except Exception as e:
        return [], f"Error parsing routes: {e}"


def extract_framing_elements(framing_data):
    """Extract framing elements from various JSON structures."""
    if isinstance(framing_data, list):
        return framing_data

    if isinstance(framing_data, dict):
        if "elements" in framing_data:
            return framing_data["elements"]
        if "results" in framing_data:
            results = framing_data["results"]
            if isinstance(results, dict) and "elements" in results:
                return results["elements"]
        if "framing_elements" in framing_data:
            return framing_data["framing_elements"]

    return []


def create_penetration_geometry(penetrations, factory):
    """Create penetration points and circles using RhinoCommonFactory.

    Args:
        penetrations: List of penetration dictionaries
        factory: RhinoCommonFactory instance

    Returns:
        tuple: (points, circles) lists
    """
    points = []
    circles = []

    for pen in penetrations:
        loc = pen.get("location", {})
        diameter = pen.get("diameter", 0.0833)

        # Create point at penetration center
        pt = factory.create_point3d(
            loc.get("x", 0),
            loc.get("y", 0),
            loc.get("z", 0)
        )
        points.append(pt)

        # Create circle representing hole
        # Circle in vertical plane (XZ plane, facing along Y)
        radius = diameter / 2
        circle = factory.create_circle(
            center=(loc.get("x", 0), loc.get("y", 0), loc.get("z", 0)),
            radius=radius,
            normal=(0, 1, 0)  # Facing along Y axis
        )
        if circle is not None:
            circles.append(circle)

    return points, circles


def collect_warnings(penetrations):
    """Collect warning messages from penetrations."""
    warnings = []

    for pen in penetrations:
        element_id = pen.get("element_id", "unknown")

        if not pen.get("is_allowed", True):
            warning_msg = pen.get("warning", "Penetration exceeds code limits")
            warnings.append(f"{element_id}: {warning_msg}")

        elif pen.get("reinforcement_required", False):
            ratio = pen.get("penetration_ratio", 0) * 100
            warnings.append(f"{element_id}: Reinforcement recommended ({ratio:.1f}% of depth)")

    return warnings

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component."""
    # Setup component
    setup_component()

    # Initialize outputs
    penetrations_json = "{}"
    penetration_points = []
    penetration_circles = []
    warnings_list = []
    debug_lines = []

    debug_lines.append("=" * 50)
    debug_lines.append("PENETRATION GENERATOR")
    debug_lines.append("=" * 50)

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs()
        if not is_valid:
            debug_lines.append(error_msg)
            return penetrations_json, penetration_points, penetration_circles, warnings_list, "\n".join(debug_lines)

        # Parse routes
        routes, parse_error = parse_routes(routes_json)
        if parse_error:
            debug_lines.append(parse_error)
            return penetrations_json, penetration_points, penetration_circles, warnings_list, "\n".join(debug_lines)

        debug_lines.append(f"Input routes: {len(routes)}")

        if not routes:
            debug_lines.append("No routes in JSON data")
            return penetrations_json, penetration_points, penetration_circles, warnings_list, "\n".join(debug_lines)

        # Parse framing elements
        try:
            framing_data = json.loads(elements_json)
            framing_elements = extract_framing_elements(framing_data)
            debug_lines.append(f"Input framing elements: {len(framing_elements)}")
        except json.JSONDecodeError as e:
            debug_lines.append(f"ERROR parsing elements_json: {e}")
            return penetrations_json, penetration_points, penetration_circles, warnings_list, "\n".join(debug_lines)

        # Generate penetrations
        debug_lines.append("")
        debug_lines.append("Generating penetrations...")

        penetrations = generate_plumbing_penetrations(routes, framing_elements)
        debug_lines.append(f"Generated {len(penetrations)} penetrations")

        if not penetrations:
            debug_lines.append("No penetrations generated")
            debug_lines.append("Routes may not cross any framing members")

        # Analyze penetrations
        allowed_count = sum(1 for p in penetrations if p.get("is_allowed", True))
        disallowed_count = len(penetrations) - allowed_count
        reinforcement_count = sum(1 for p in penetrations if p.get("reinforcement_required", False))

        debug_lines.append("")
        debug_lines.append("Penetration summary:")
        debug_lines.append(f"  Total penetrations: {len(penetrations)}")
        debug_lines.append(f"  Code-compliant: {allowed_count}")
        debug_lines.append(f"  Requires review: {disallowed_count}")
        debug_lines.append(f"  Reinforcement needed: {reinforcement_count}")

        # Collect warnings
        warnings_list = collect_warnings(penetrations)

        if warnings_list:
            debug_lines.append("")
            debug_lines.append(f"Warnings ({len(warnings_list)}):")
            for w in warnings_list[:5]:
                debug_lines.append(f"  - {w}")
            if len(warnings_list) > 5:
                debug_lines.append(f"  ... and {len(warnings_list) - 5} more")

        # Build JSON output
        output_data = {
            "penetrations": penetrations,
            "count": len(penetrations),
            "allowed_count": allowed_count,
            "disallowed_count": disallowed_count,
            "reinforcement_count": reinforcement_count,
            "source": "gh_penetration_generator",
        }
        penetrations_json = json.dumps(output_data, indent=2)

        # Create geometry using RhinoCommonFactory
        factory = get_factory()
        penetration_points, penetration_circles = create_penetration_geometry(penetrations, factory)

        debug_lines.append("")
        debug_lines.append(f"Created {len(penetration_points)} visualization points")
        debug_lines.append(f"Created {len(penetration_circles)} hole circles")

        # Summary
        debug_lines.append("")
        debug_lines.append("=" * 50)
        debug_lines.append("PENETRATION GENERATION COMPLETE")
        debug_lines.append(f"Total penetrations: {len(penetrations)}")
        debug_lines.append(f"Code-compliant: {allowed_count}")
        debug_lines.append(f"Warnings: {len(warnings_list)}")
        debug_lines.append("=" * 50)

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return penetrations_json, penetration_points, penetration_circles, warnings_list, "\n".join(debug_lines)

# =============================================================================
# Execution
# =============================================================================

# Define default input values if not provided by Grasshopper
if 'run' not in dir():
    run = False

if 'routes_json' not in dir():
    routes_json = ""

if 'elements_json' not in dir():
    elements_json = ""

# Execute main and assign to output variables
penetrations_json, penetration_points, penetration_circles, warnings, debug_info = main()
