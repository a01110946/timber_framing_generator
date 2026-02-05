# File: scripts/gh_mep_fixture_router.py
"""MEP Fixture-to-Penetration Router for Grasshopper.

Projects MEP fixture connectors onto the nearest wall surface to compute
wall penetration points. This is Phase 1 of the hierarchical MEP routing
pipeline -- purely geometric, no graph traversal needed.

Key Features:
1. Fixture-to-Wall Projection
   - Projects each connector onto all walls within search_radius
   - Selects the closest valid projection (within wall bounds)
   - Outputs both world coordinates and wall-local UV coordinates

2. User-in-the-Loop Design
   - Reports unassigned connectors with actionable guidance
   - Status output: "ready" if all assigned, "needs_input" if some unassigned
   - Needs list describes exactly what the user must fix

3. Debug Visualization
   - Connector origin points and penetration points for Rhino viewport
   - Lines from connector to penetration for visual validation
   - Uses RhinoCommonFactory for correct assembly output

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Point3d and LineCurve for debug visualization
    - Grasshopper: Component framework and data structures
    - json: Serialization of connector and wall data
    - timber_framing_generator.mep.routing.fixture_router: Core routing logic
    - timber_framing_generator.utils.geometry_factory: RhinoCommonFactory

Performance Considerations:
    - O(connectors * walls) projection checks per run
    - Typical residential models (< 100 connectors, < 50 walls) process in < 50ms
    - For large models, reduce search_radius to limit comparisons

Usage:
    1. Connect connectors_json from MEP Connector Extractor
    2. Connect walls_json from Wall Analyzer
    3. Optionally adjust search_radius (default 5.0 ft)
    4. Set run to True to execute
    5. Check status output: "ready" means all connectors assigned
    6. If "needs_input", review info output for guidance

Input Requirements:
    Connectors JSON (connectors_json) - str:
        JSON string with MEP connectors from connector extractor.
        Format: {"connectors": [{"id", "origin": {"x","y","z"}, "system_type", ...}]}
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Walls JSON (walls_json) - str:
        JSON string with wall geometry from Wall Analyzer.
        Format: [{"wall_id", "wall_length", "wall_height", "base_plane": {...}}]
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Search Radius (search_radius) - float:
        Maximum perpendicular distance to search for wall (feet).
        Required: No (defaults to 5.0)
        Access: Item
        Type hint: float (set via GH UI)

    Run (run) - bool:
        Boolean to trigger execution.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

Outputs:
    Penetrations JSON (penetrations_json) - str:
        JSON string with fixture-to-wall assignments, unassigned list, and status.

    Graph Points (graph_pts) - List[Point3d]:
        Connector origins and penetration points for debug visualization.

    Graph Lines (graph_lines) - List[LineCurve]:
        Lines from connector origin to penetration point on wall.

    Stats JSON (stats_json) - str:
        Routing statistics (counts, distances, per-wall/per-system breakdowns).

    Status (status) - str:
        "ready" if all connectors assigned, "needs_input" if some unassigned.

    Info (info) - List[str]:
        Diagnostic messages and processing log.

Technical Details:
    - Projection uses wall base_plane dot products (U along wall, V vertical, W normal)
    - Penetration point is clamped to wall bounds (0 <= U <= wall_length, 0 <= V <= wall_height)
    - Side classification: "interior" if connector is on z_axis side, "exterior" otherwise
    - All geometry output uses RhinoCommonFactory to avoid assembly mismatch

Error Handling:
    - Invalid JSON returns empty outputs with error in info
    - Missing required inputs logged as warnings
    - Individual connector failures do not halt processing
    - Empty connector/wall lists produce valid but empty results

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
import time

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

from src.timber_framing_generator.mep.routing.fixture_router import (
    route_fixtures_to_walls,
    generate_stats,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Fixture Router"
COMPONENT_NICKNAME = "FixRouter"
COMPONENT_MESSAGE = "v1.0 | Phase 1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "MEP"

DEFAULT_SEARCH_RADIUS = 5.0  # feet

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message: str, level: str = "info") -> None:
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log.
        level: One of "info", "debug", "warning", "error", "remark".
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


def log_debug(message: str) -> None:
    """Log debug message (console only)."""
    print(f"[DEBUG] {message}")


def log_info(message: str) -> None:
    """Log info message (console only)."""
    print(f"[INFO] {message}")


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

    Configures:
    1. Component metadata (name, category, etc.)
    2. Input parameter names, descriptions, and access
    3. Output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    Required type hints:
        - connectors_json: str
        - walls_json: str
        - search_radius: float
        - run: bool
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # IMPORTANT: NickName becomes the Python variable name
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Connectors JSON", "connectors_json",
         "JSON string with MEP connectors from connector extractor",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls JSON", "walls_json",
         "JSON string with wall geometry from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Search Radius", "search_radius",
         "Max distance to search for wall (feet, default 5.0)",
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
        ("Penetrations JSON", "penetrations_json",
         "JSON with fixture-to-wall assignments and status"),
        ("Graph Points", "graph_pts",
         "Connector + penetration points for debug visualization"),
        ("Graph Lines", "graph_lines",
         "Lines from connector to penetration point"),
        ("Stats JSON", "stats_json",
         "Routing statistics (counts, distances, breakdowns)"),
        ("Status", "status",
         "'ready' or 'needs_input' - user-in-the-loop status"),
        ("Info", "info",
         "Diagnostic messages and processing log"),
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

def validate_inputs(connectors_json_input, walls_json_input, run_input):
    """Validate component inputs.

    Args:
        connectors_json_input: JSON string with connector data.
        walls_json_input: JSON string with wall data.
        run_input: Boolean trigger.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_input:
        return False, "Component not running. Set 'run' to True."

    if not connectors_json_input:
        return False, "Missing connectors_json input"

    if not walls_json_input:
        return False, "Missing walls_json input"

    # Validate JSON parsing
    try:
        parsed = json.loads(connectors_json_input)
        if isinstance(parsed, dict):
            connectors = parsed.get("connectors", [])
        elif isinstance(parsed, list):
            connectors = parsed
        else:
            return False, "connectors_json must be a dict or list"

        if not connectors:
            return False, "connectors_json contains no connectors"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in connectors_json: {e}"

    try:
        parsed_walls = json.loads(walls_json_input)
        if isinstance(parsed_walls, dict):
            walls = parsed_walls.get("walls", [])
        elif isinstance(parsed_walls, list):
            walls = parsed_walls
        else:
            return False, "walls_json must be a dict or list"

        if not walls:
            return False, "walls_json contains no walls"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


def parse_connectors(connectors_json_str: str):
    """Parse connectors from JSON string.

    Args:
        connectors_json_str: JSON string with connector data.

    Returns:
        List of connector dicts.
    """
    data = json.loads(connectors_json_str)
    if isinstance(data, dict):
        return data.get("connectors", [])
    elif isinstance(data, list):
        return data
    return []


def parse_walls(walls_json_str: str):
    """Parse walls from JSON string.

    Args:
        walls_json_str: JSON string with wall data.

    Returns:
        List of wall dicts.
    """
    data = json.loads(walls_json_str)
    if isinstance(data, dict):
        return data.get("walls", [])
    elif isinstance(data, list):
        return data
    return []


def create_debug_geometry(result):
    """Create debug visualization geometry from routing result.

    For each penetration, creates:
    - A point at the connector origin (source)
    - A point at the penetration location on the wall (target)
    - A line from connector to penetration

    All geometry is created via RhinoCommonFactory to avoid assembly mismatch.

    Args:
        result: FixtureRoutingResult with penetrations list.

    Returns:
        tuple: (graph_pts, graph_lines) - lists of Point3d and LineCurve.
    """
    factory = get_factory()
    graph_pts = []
    graph_lines = []

    for pen in result.penetrations:
        try:
            # Connector origin point
            co = pen.connector_origin
            connector_pt = factory.create_point3d(
                float(co[0]), float(co[1]), float(co[2])
            )
            graph_pts.append(connector_pt)

            # Penetration point on wall
            wl = pen.world_location
            penetration_pt = factory.create_point3d(
                float(wl[0]), float(wl[1]), float(wl[2])
            )
            graph_pts.append(penetration_pt)

            # Line from connector to penetration
            line_curve = factory.create_line_curve(
                (float(co[0]), float(co[1]), float(co[2])),
                (float(wl[0]), float(wl[1]), float(wl[2])),
            )
            if line_curve is not None:
                graph_lines.append(line_curve)

        except Exception as e:
            log_warning(f"Failed to create debug geometry for {pen.connector_id}: {e}")
            continue

    # Also add points for unassigned connectors (so user can see them)
    for ua in result.unassigned:
        try:
            origin = ua.origin
            ua_pt = factory.create_point3d(
                float(origin[0]), float(origin[1]), float(origin[2])
            )
            graph_pts.append(ua_pt)
        except Exception as e:
            log_debug(f"Failed to create point for unassigned {ua.connector_id}: {e}")

    return graph_pts, graph_lines

# =============================================================================
# Main Function
# =============================================================================

def main(connectors_json_input, walls_json_input, radius_input, run_input):
    """Main entry point for the component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Route fixtures to walls via core library
    4. Create debug visualization geometry
    5. Return results

    Args:
        connectors_json_input: JSON string with connector data (from GH global).
        walls_json_input: JSON string with wall data (from GH global).
        radius_input: Search radius in feet.
        run_input: Boolean trigger.

    Returns:
        tuple: (penetrations_json, graph_pts, graph_lines, stats_json, status, info)
    """
    setup_component()

    # Initialize outputs with safe defaults
    penetrations_json = ""
    graph_pts = []
    graph_lines = []
    stats_json = ""
    status = ""
    info_lines = []

    try:
        # Apply default for search_radius
        if radius_input is None or (isinstance(radius_input, (int, float)) and radius_input <= 0):
            radius_input = DEFAULT_SEARCH_RADIUS

        # Validate inputs
        is_valid, error_msg = validate_inputs(
            connectors_json_input, walls_json_input, run_input
        )
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            info_lines.append(error_msg or "Validation failed")
            return penetrations_json, graph_pts, graph_lines, stats_json, status, info_lines

        info_lines.append("Inputs validated successfully")
        info_lines.append(f"Search radius: {radius_input:.1f} ft")

        # Parse inputs
        start_time = time.time()

        connectors = parse_connectors(connectors_json_input)
        info_lines.append(f"Parsed {len(connectors)} connectors")

        walls = parse_walls(walls_json_input)
        info_lines.append(f"Parsed {len(walls)} walls")

        # Run fixture-to-wall routing (core logic)
        result = route_fixtures_to_walls(connectors, walls, radius_input)

        elapsed_ms = (time.time() - start_time) * 1000
        info_lines.append(f"Routing completed in {elapsed_ms:.1f}ms")

        # Serialize result to JSON
        penetrations_json = json.dumps(result.to_dict(), indent=2)

        # Generate stats
        stats = generate_stats(result)
        stats_json = json.dumps(stats, indent=2)

        # Set status
        status = result.status

        # Create debug visualization geometry
        graph_pts, graph_lines = create_debug_geometry(result)
        info_lines.append(f"Debug geometry: {len(graph_pts)} points, {len(graph_lines)} lines")

        # Summary
        info_lines.append("")
        info_lines.append("=== SUMMARY ===")
        info_lines.append(f"Penetrations: {len(result.penetrations)}")
        info_lines.append(f"Unassigned: {len(result.unassigned)}")
        info_lines.append(f"Status: {status}")

        if result.unassigned:
            info_lines.append("")
            info_lines.append("=== UNASSIGNED CONNECTORS ===")
            for ua in result.unassigned:
                info_lines.append(
                    f"  {ua.connector_id} ({ua.system_type}) at "
                    f"({ua.origin[0]:.1f}, {ua.origin[1]:.1f}, {ua.origin[2]:.1f}): "
                    f"{ua.reason}"
                )
            info_lines.append("")
            info_lines.append("ACTION: Increase search_radius or add walls near these fixtures.")

        if result.penetrations:
            info_lines.append("")
            info_lines.append("=== ASSIGNED CONNECTORS ===")
            for pen in result.penetrations:
                info_lines.append(
                    f"  {pen.connector_id} ({pen.system_type}) -> "
                    f"wall {pen.wall_id} (dist={pen.distance:.2f} ft, "
                    f"uv=({pen.wall_uv[0]:.2f}, {pen.wall_uv[1]:.2f}), "
                    f"side={pen.side})"
                )

        # Add remark if status needs input
        if status == "needs_input":
            log_message(
                f"{len(result.unassigned)} connector(s) could not be assigned to a wall. "
                "Check the info output for details.",
                "remark",
            )

    except ImportError as e:
        log_error(f"Import error: {e}")
        info_lines.append(f"Import error: {e}")
        info_lines.append("Ensure timber_framing_generator is installed and on sys.path")
        info_lines.append(traceback.format_exc())
    except json.JSONDecodeError as e:
        log_error(f"JSON parse error: {e}")
        info_lines.append(f"JSON parse error: {e}")
    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        info_lines.append(f"Error: {type(e).__name__}: {e}")
        info_lines.append(traceback.format_exc())

    return penetrations_json, graph_pts, graph_lines, stats_json, status, info_lines

# =============================================================================
# Execution
# =============================================================================

# Resolve GH global inputs with safe defaults
try:
    _connectors_json = connectors_json
except NameError:
    _connectors_json = None

try:
    _walls_json = walls_json
except NameError:
    _walls_json = None

try:
    _search_radius = search_radius
except NameError:
    _search_radius = DEFAULT_SEARCH_RADIUS

try:
    _run = run
except NameError:
    _run = False

if __name__ == "__main__":
    penetrations_json, graph_pts, graph_lines, stats_json, status, info = main(
        _connectors_json, _walls_json, _search_radius, _run
    )
