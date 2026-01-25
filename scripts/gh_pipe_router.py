# File: scripts/gh_pipe_router.py
"""Pipe Router for Grasshopper.

Calculates pipe routes from plumbing connectors to wall entry points.
This is the second step in the MEP integration pipeline.

Key Features:
1. Wall Finding
   - Finds nearest wall using ray-plane intersection
   - Respects max search distance parameter

2. Route Calculation
   - From fixture connector to wall face (entry point)
   - Then to first vertical connection inside wall

3. Geometry Output
   - Creates polyline curves showing pipe paths
   - Uses RhinoCommonFactory for proper assembly compatibility

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry creation
    - Grasshopper: Component framework
    - timber_framing_generator.mep.plumbing: Pipe routing logic
    - timber_framing_generator.utils.geometry_factory: RhinoCommon geometry

Input Requirements:
    connectors_json (conn_json) - str:
        JSON from MEP Connector Extractor
        Required: Yes
        Access: Item

    walls_json (walls_json) - str:
        JSON with wall geometry data (from Wall Analyzer)
        Required: Yes
        Access: Item

    max_search_distance (max_dist) - float:
        Maximum distance to search for walls (in feet)
        Required: No (defaults to 10 ft)
        Access: Item

    run (run) - bool:
        Execute toggle
        Required: Yes
        Access: Item

Outputs:
    routes_json (json) - str:
        JSON with calculated routes for downstream components

    route_curves (curves) - list of Curves:
        Polyline curves showing pipe paths

    route_points (pts) - list of Point3d:
        All route path points for visualization

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

COMPONENT_NAME = "Pipe Router"
COMPONENT_NICKNAME = "PipeRte"
COMPONENT_MESSAGE = "v1.1"

# Project path
PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# =============================================================================
# Project Imports
# =============================================================================

try:
    from src.timber_framing_generator.mep.plumbing import calculate_pipe_routes
    from src.timber_framing_generator.core import MEPConnector, MEPRoute
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

    if not connectors_json:
        return False, "No connectors_json provided"

    if not walls_json:
        return False, "No walls_json provided"

    return True, None


def parse_connectors(connectors_json_str):
    """Parse connectors from JSON string.

    Returns:
        tuple: (connectors list, error message or None)
    """
    try:
        data = json.loads(connectors_json_str)
        connector_list = data.get("connectors", [])

        connectors = []
        for conn_dict in connector_list:
            conn = MEPConnector.from_dict(conn_dict)
            connectors.append(conn)

        return connectors, None
    except json.JSONDecodeError as e:
        return [], f"JSON parse error: {e}"
    except Exception as e:
        return [], f"Error parsing connectors: {e}"


def extract_walls_list(walls_data):
    """Extract list of walls from various JSON structures."""
    if isinstance(walls_data, list):
        return walls_data

    if isinstance(walls_data, dict):
        if "walls" in walls_data:
            return walls_data["walls"]
        if "wall_id" in walls_data or "base_plane" in walls_data:
            return [walls_data]
        if "results" in walls_data:
            return extract_walls_list(walls_data["results"])

    return []


def create_route_geometry(routes, factory):
    """Create route curves and points using RhinoCommonFactory.

    Args:
        routes: List of MEPRoute objects
        factory: RhinoCommonFactory instance

    Returns:
        tuple: (curves, points) lists
    """
    curves = []
    points = []

    for route in routes:
        if len(route.path_points) >= 2:
            # Create polyline curve using factory
            curve = factory.create_polyline_curve(route.path_points)
            if curve is not None:
                curves.append(curve)

            # Create points for visualization
            for p in route.path_points:
                pt = factory.create_point3d(p[0], p[1], p[2])
                points.append(pt)

    return curves, points

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component."""
    # Setup component
    setup_component()

    # Initialize outputs
    routes_json = "{}"
    route_curves = []
    route_points = []
    debug_lines = []

    debug_lines.append("=" * 50)
    debug_lines.append("PIPE ROUTER")
    debug_lines.append("=" * 50)

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs()
        if not is_valid:
            debug_lines.append(error_msg)
            return routes_json, route_curves, route_points, "\n".join(debug_lines)

        # Parse connectors
        connectors, parse_error = parse_connectors(connectors_json)
        if parse_error:
            debug_lines.append(parse_error)
            return routes_json, route_curves, route_points, "\n".join(debug_lines)

        debug_lines.append(f"Input connectors: {len(connectors)}")

        if not connectors:
            debug_lines.append("No connectors in JSON data")
            return routes_json, route_curves, route_points, "\n".join(debug_lines)

        # Parse walls
        try:
            walls_data = json.loads(walls_json)
            walls_list = extract_walls_list(walls_data)
            debug_lines.append(f"Input walls: {len(walls_list)}")
        except json.JSONDecodeError as e:
            debug_lines.append(f"ERROR parsing walls_json: {e}")
            return routes_json, route_curves, route_points, "\n".join(debug_lines)

        # Build routing config
        search_dist = max_search_distance if max_search_distance else 10.0
        config = {
            "max_search_distance": search_dist,
            "wall_thickness": 0.333,  # Default 4" wall
        }
        debug_lines.append(f"Max search distance: {search_dist} ft")

        # Calculate routes
        debug_lines.append("")
        debug_lines.append("Calculating routes...")

        framing_data = {"walls": walls_list}
        routes = calculate_pipe_routes(connectors, framing_data, [], config)
        debug_lines.append(f"Calculated {len(routes)} routes")

        if not routes:
            debug_lines.append("No routes could be calculated")
            debug_lines.append("Check that fixtures are within search distance of walls")
            return routes_json, route_curves, route_points, "\n".join(debug_lines)

        # Analyze routes
        total_length = sum(route.get_length() for route in routes)
        end_types = {}
        for route in routes:
            et = route.end_point_type
            end_types[et] = end_types.get(et, 0) + 1

        debug_lines.append("")
        debug_lines.append("Route summary:")
        debug_lines.append(f"  Total routes: {len(routes)}")
        debug_lines.append(f"  Total length: {total_length:.2f} ft")
        for et, count in end_types.items():
            debug_lines.append(f"  {et}: {count}")

        # Build JSON output
        output_data = {
            "routes": [route.to_dict() for route in routes],
            "count": len(routes),
            "total_length": total_length,
            "source": "gh_pipe_router",
        }
        routes_json = json.dumps(output_data, indent=2)

        # Create geometry using RhinoCommonFactory
        factory = get_factory()
        route_curves, route_points = create_route_geometry(routes, factory)

        debug_lines.append("")
        debug_lines.append(f"Created {len(route_curves)} route curves")
        debug_lines.append(f"Created {len(route_points)} route points")

        # Summary
        debug_lines.append("")
        debug_lines.append("=" * 50)
        debug_lines.append("ROUTING COMPLETE")
        debug_lines.append(f"Total routes: {len(routes)}")
        debug_lines.append(f"Total length: {total_length:.2f} ft")
        debug_lines.append("=" * 50)

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return routes_json, route_curves, route_points, "\n".join(debug_lines)

# =============================================================================
# Execution
# =============================================================================

# Define default input values if not provided by Grasshopper
if 'run' not in dir():
    run = False

if 'connectors_json' not in dir():
    connectors_json = ""

if 'walls_json' not in dir():
    walls_json = ""

if 'max_search_distance' not in dir():
    max_search_distance = 10.0

# Execute main and assign to output variables
routes_json, route_curves, route_points, debug_info = main()
