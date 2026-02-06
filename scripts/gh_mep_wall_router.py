# File: scripts/gh_mep_wall_router.py
"""MEP In-Wall Router for Grasshopper.

Routes MEP pipes/conduits through wall cavities from penetration points
(Phase 1 output) to wall exit points (top or bottom plate). This is Phase 2
of the hierarchical MEP routing pipeline -- uses cavity-based routing where
pipes drop vertically within rectangular voids between framing members.

Key Features:
1. Cavity-Based Routing
   - Decomposes walls into rectangular cavities (voids between studs/plates)
   - Pipes route vertically within cavities -- no A* grid needed
   - Prefer straight vertical drops; only jog horizontally when necessary
   - Multi-pipe support via occupancy-aware collision detection

2. Progressive Refinement
   - walls_json alone: derives cavities from configured stud spacing
   - walls_json + framing_json: uses exact framing element positions
   - walls_json + framing_json + cell_json: full precision with cell data
   - Reports obstacle_source in stats ("derived" or "framing")

3. System-Type-Aware Exit Selection
   - Sanitary/supply pipes exit through bottom plate (gravity/riser below)
   - Vent pipes exit through top plate (vent stack above)
   - Each route selects the appropriate wall exit edge

4. User-in-the-Loop Design
   - Reports unrouted penetrations with actionable guidance
   - Floor penetrations passed through unchanged (not routed in wall)
   - Status output: "ready" if all routed, "needs_input" if some failed

5. Debug Visualization
   - Route segment endpoints for Rhino viewport inspection
   - Route segment lines (vertical drops within cavities)
   - Uses RhinoCommonFactory for correct assembly output

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Point3d and LineCurve for debug visualization
    - Grasshopper: Component framework and data structures
    - json: Serialization of routing data
    - timber_framing_generator.mep.routing.wall_router: Core routing logic
    - timber_framing_generator.cavity: Cavity decomposition module
    - timber_framing_generator.utils.geometry_factory: RhinoCommonFactory

Performance Considerations:
    - O(walls * penetrations) per run -- no graph search needed
    - Cavity decomposition is lightweight (sorted member lists)
    - Typical residential wall routes all pipes in < 5ms

Usage:
    1. Connect penetrations_json from MEP Fixture Router (Phase 1)
    2. Connect walls_json from Wall Analyzer
    3. Optionally connect framing_json from Framing Generator for exact cavities
    4. Optionally connect cell_json from Cell Decomposer for cell-aware cavities
    5. Set run to True to execute
    5. Check status output: "ready" means all penetrations routed
    6. If "needs_input", review info output for guidance

Input Requirements:
    Penetrations JSON (penetrations_json) - str:
        JSON string with Phase 1 output from MEP Fixture Router.
        Format: {"penetrations": [...], "unassigned": [...], "status": "..."}
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Walls JSON (walls_json) - str:
        JSON string with wall geometry from Wall Analyzer.
        Format: {"walls": [{"wall_id", "wall_length", "wall_height", "openings", ...}]}
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Framing JSON (framing_json) - str:
        JSON string with framing elements from Framing Generator.
        Format: {"wall_id", "elements": [...]} or {"walls": [{...}, ...]}
        Required: No (progressive refinement - derives cavities without it)
        Access: Item
        Type hint: str (set via GH UI)

    Cell JSON (cell_json) - str:
        JSON string with cell decomposition from Cell Decomposer.
        Format: {"walls": [{"wall_id", "cells": [...]}]}
        Required: No (used with framing_json for cell-aware cavity decomposition)
        Access: Item
        Type hint: str (set via GH UI)

    Run (run) - bool:
        Boolean to trigger execution.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

Outputs:
    Wall Routes JSON (wall_routes_json) - str:
        JSON with in-wall routes, exit points, floor passthroughs, and status.

    Graph Points (graph_pts) - List[Point3d]:
        Route segment endpoint positions for debug visualization.

    Graph Lines (graph_lines) - List[LineCurve]:
        Route segment lines for debug visualization.

    Stats JSON (stats_json) - str:
        Routing statistics (routes per wall, stud crossings, success rate).

    Status (status) - str:
        "ready" or "needs_input" - user-in-the-loop status.

    Info (info) - List[str]:
        Diagnostic messages and processing log.

Technical Details:
    - Decomposes each wall into rectangular cavities between framing members
    - Pipe drops vertically at entry U when possible (no horizontal jog)
    - Only shifts horizontally when collision with existing pipe detected
    - Stud crossing only when penetration falls on a stud (horizontal snap)
    - Exit selection: system_type determines top vs bottom plate exit
    - Floor penetrations (target="floor") bypass wall routing entirely

Error Handling:
    - Invalid JSON returns empty outputs with error in info
    - Missing required inputs logged as warnings
    - Individual penetration routing failures do not halt processing
    - Failed routes reported in unrouted list with reasons

Author: Fernando Maytorena
Version: 2.0.0
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

from src.timber_framing_generator.mep.routing.wall_router import (
    route_all_walls,
    generate_stats,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Wall Router"
COMPONENT_NICKNAME = "WallRouter"
COMPONENT_MESSAGE = "v2.0 | Phase 2 (cavity)"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "MEP"

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log.
        level: One of "info", "debug", "warning", "error", "remark".
    """
    print("[{}] {}".format(level.upper(), message))

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
    print("[DEBUG] {}".format(message))


def log_info(message):
    """Log info message (console only)."""
    print("[INFO] {}".format(message))


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

    Configures:
    1. Component metadata (name, category, etc.)
    2. Input parameter names, descriptions, and access
    3. Output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    Required type hints:
        - penetrations_json: str
        - walls_json: str
        - framing_json: str
        - run: bool
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Penetrations JSON", "penetrations_json",
         "JSON string with Phase 1 penetrations from MEP Fixture Router",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls JSON", "walls_json",
         "JSON string with wall geometry from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Framing JSON", "framing_json",
         "Optional JSON with framing elements (improves cavity accuracy)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Cell JSON", "cell_json",
         "Optional JSON with cell decomposition (used with framing_json)",
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
        ("Wall Routes JSON", "wall_routes_json",
         "JSON with in-wall routes, exit points, and status"),
        ("Graph Points", "graph_pts",
         "Graph node points for debug visualization"),
        ("Graph Lines", "graph_lines",
         "Graph edge lines for debug visualization"),
        ("Stats JSON", "stats_json",
         "Routing statistics (routes, stud crossings, success rate)"),
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

def validate_inputs(pen_json_input, walls_json_input, run_input):
    """Validate component inputs.

    Args:
        pen_json_input: JSON string with penetration data.
        walls_json_input: JSON string with wall data.
        run_input: Boolean trigger.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_input:
        return False, "Component not running. Set 'run' to True."

    if not pen_json_input:
        return False, "Missing penetrations_json input"

    if not walls_json_input:
        return False, "Missing walls_json input"

    # Validate JSON parsing
    try:
        parsed = json.loads(pen_json_input)
        pens = parsed.get("penetrations", []) if isinstance(parsed, dict) else []
        if not pens:
            return False, "penetrations_json contains no penetrations"
    except json.JSONDecodeError as e:
        return False, "Invalid JSON in penetrations_json: {}".format(e)

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
        return False, "Invalid JSON in walls_json: {}".format(e)

    return True, None


def parse_walls_json(walls_json_str):
    """Parse walls_json into the format expected by route_all_walls.

    Args:
        walls_json_str: JSON string with wall data.

    Returns:
        Dict with "walls" key containing list of wall dicts.
    """
    data = json.loads(walls_json_str)
    if isinstance(data, dict):
        if "walls" in data:
            return data
        else:
            return {"walls": [data]}
    elif isinstance(data, list):
        return {"walls": data}
    return {"walls": []}


def parse_framing_json(framing_json_str):
    """Parse optional framing_json.

    Args:
        framing_json_str: JSON string with framing data, or None.

    Returns:
        Dict with framing data, or None.
    """
    if not framing_json_str:
        return None

    try:
        data = json.loads(framing_json_str)
        return data
    except (json.JSONDecodeError, TypeError):
        return None


def create_debug_geometry(result, walls_json):
    """Create debug visualization geometry from wall routing result.

    For each wall route, creates:
    - Points at entry and exit positions
    - Line segments following the route path

    All geometry is created via RhinoCommonFactory to avoid assembly mismatch.

    Args:
        result: WallRoutingResult with wall_routes and exit_points.
        walls_json: Parsed walls dict for UV-to-world conversion.

    Returns:
        tuple: (graph_pts, graph_lines) - lists of Point3d and LineCurve.
    """
    factory = get_factory()
    graph_pts = []
    graph_lines = []

    # Build wall lookup for UV-to-world conversion
    wall_lookup = {}
    for w in walls_json.get("walls", []):
        wall_lookup[w["wall_id"]] = w

    for wr in result.wall_routes:
        try:
            wall = wall_lookup.get(wr.wall_id)
            if wall is None:
                continue

            bp = wall["base_plane"]
            origin = bp["origin"]
            x_axis = bp["x_axis"]
            base_elev = float(wall.get("base_elevation", origin.get("z", 0.0)))

            # Convert route segments to world coordinates and create geometry
            for seg in wr.route.segments:
                su, sv = seg.start
                eu, ev = seg.end

                # UV to world
                ox = float(origin["x"])
                oy = float(origin["y"])
                xx = float(x_axis["x"])
                xy = float(x_axis["y"])

                sx = ox + xx * su
                sy = oy + xy * su
                sz = base_elev + sv

                ex = ox + xx * eu
                ey = oy + xy * eu
                ez = base_elev + ev

                # Create points
                start_pt = factory.create_point3d(sx, sy, sz)
                end_pt = factory.create_point3d(ex, ey, ez)
                if start_pt is not None:
                    graph_pts.append(start_pt)
                if end_pt is not None:
                    graph_pts.append(end_pt)

                # Create line
                line = factory.create_line_curve(
                    (sx, sy, sz), (ex, ey, ez),
                )
                if line is not None:
                    graph_lines.append(line)

        except Exception as e:
            log_debug("Failed to create debug geometry for {}: {}".format(
                wr.connector_id, e))

    # Add exit points
    for ep in result.exit_points:
        try:
            wl = ep.world_location
            pt = factory.create_point3d(float(wl[0]), float(wl[1]), float(wl[2]))
            if pt is not None:
                graph_pts.append(pt)
        except Exception as e:
            log_debug("Failed to create exit point geometry: {}".format(e))

    return graph_pts, graph_lines

# =============================================================================
# Main Function
# =============================================================================

def parse_cell_json(cell_json_str):
    """Parse optional cell_json.

    Args:
        cell_json_str: JSON string with cell decomposition data, or None.

    Returns:
        Dict with cell data, or None.
    """
    if not cell_json_str:
        return None

    try:
        data = json.loads(cell_json_str)
        return data
    except (json.JSONDecodeError, TypeError):
        return None


def main(pen_json_input, walls_json_input, framing_json_input, cell_json_input, run_input):
    """Main entry point for the component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Route penetrations through wall cavities via core library
    4. Create debug visualization geometry
    5. Return results

    Args:
        pen_json_input: JSON string with penetration data (from Phase 1).
        walls_json_input: JSON string with wall data.
        framing_json_input: Optional JSON string with framing data.
        cell_json_input: Optional JSON string with cell decomposition data.
        run_input: Boolean trigger.

    Returns:
        tuple: (wall_routes_json, graph_pts, graph_lines, stats_json, status, info)
    """
    setup_component()

    # Initialize outputs with safe defaults
    wall_routes_json = ""
    graph_pts = []
    graph_lines = []
    stats_json = ""
    status = ""
    info_lines = []

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs(
            pen_json_input, walls_json_input, run_input
        )
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            info_lines.append(error_msg or "Validation failed")
            return wall_routes_json, graph_pts, graph_lines, stats_json, status, info_lines

        info_lines.append("Inputs validated successfully")

        # Parse inputs
        start_time = time.time()

        penetrations_json = json.loads(pen_json_input)
        walls_json = parse_walls_json(walls_json_input)
        framing_json = parse_framing_json(framing_json_input)
        cell_json = parse_cell_json(cell_json_input)

        wall_count = len(walls_json.get("walls", []))
        pen_count = len(penetrations_json.get("penetrations", []))
        info_lines.append("Parsed {} penetrations across {} walls".format(
            pen_count, wall_count))

        if framing_json and cell_json:
            info_lines.append("Framing + cell data provided -> exact cavity decomposition")
        elif framing_json:
            info_lines.append("Framing data provided -> framing-based cavities (no cell data)")
        else:
            info_lines.append("No framing data -> derived cavities from wall geometry")

        # Run in-wall routing (core logic)
        result = route_all_walls(penetrations_json, walls_json, framing_json, cell_json)

        elapsed_ms = (time.time() - start_time) * 1000
        info_lines.append("Routing completed in {:.1f}ms".format(elapsed_ms))

        # Serialize result to JSON
        wall_routes_json = json.dumps(result.to_dict(), indent=2)

        # Generate stats
        stats = generate_stats(result)
        stats_json = json.dumps(stats, indent=2)

        # Set status
        status = result.status

        # Create debug visualization geometry
        graph_pts, graph_lines = create_debug_geometry(result, walls_json)
        info_lines.append("Debug geometry: {} points, {} lines".format(
            len(graph_pts), len(graph_lines)))

        # Summary
        info_lines.append("")
        info_lines.append("=== SUMMARY ===")
        info_lines.append("Wall routes: {}".format(len(result.wall_routes)))
        info_lines.append("Exit points: {}".format(len(result.exit_points)))
        info_lines.append("Unrouted: {}".format(len(result.unrouted)))
        info_lines.append("Floor passthroughs: {}".format(len(result.floor_passthroughs)))
        info_lines.append("Obstacle source: {}".format(result.obstacle_source))
        info_lines.append("Status: {}".format(status))

        if result.unrouted:
            info_lines.append("")
            info_lines.append("=== UNROUTED PENETRATIONS ===")
            for ur in result.unrouted:
                info_lines.append(
                    "  {} ({}) in wall {}: {}".format(
                        ur.connector_id, ur.system_type,
                        ur.wall_id, ur.reason))
            info_lines.append("")
            info_lines.append("ACTION: Check wall geometry and opening placement.")

        if result.wall_routes:
            info_lines.append("")
            info_lines.append("=== ROUTED ===")
            for wr in result.wall_routes:
                info_lines.append(
                    "  {} ({}) in wall {} -> {} "
                    "(entry=({:.2f},{:.2f}), exit=({:.2f},{:.2f}), "
                    "{} stud crossings)".format(
                        wr.connector_id, wr.system_type,
                        wr.wall_id, wr.exit_edge,
                        wr.entry_uv[0], wr.entry_uv[1],
                        wr.exit_uv[0], wr.exit_uv[1],
                        wr.stud_crossings))

        if result.floor_passthroughs:
            info_lines.append("")
            info_lines.append("=== FLOOR PASSTHROUGHS ===")
            for fp in result.floor_passthroughs:
                info_lines.append(
                    "  {} ({}) -> floor (passed through)".format(
                        fp.get("connector_id", "?"),
                        fp.get("system_type", "?")))

        # Add remark if status needs input
        if status == "needs_input":
            log_message(
                "{} penetration(s) could not be routed through wall cavities. "
                "Check the info output for details.".format(len(result.unrouted)),
                "remark",
            )

    except ImportError as e:
        log_error("Import error: {}".format(e))
        info_lines.append("Import error: {}".format(e))
        info_lines.append("Ensure timber_framing_generator package is installed")
        info_lines.append(traceback.format_exc())
    except json.JSONDecodeError as e:
        log_error("JSON parse error: {}".format(e))
        info_lines.append("JSON parse error: {}".format(e))
    except Exception as e:
        log_error("Unexpected error: {}".format(str(e)))
        info_lines.append("Error: {}: {}".format(type(e).__name__, e))
        info_lines.append(traceback.format_exc())

    return wall_routes_json, graph_pts, graph_lines, stats_json, status, info_lines

# =============================================================================
# Execution
# =============================================================================

# Resolve GH global inputs with safe defaults
try:
    _penetrations_json = penetrations_json
except NameError:
    _penetrations_json = None

try:
    _walls_json = walls_json
except NameError:
    _walls_json = None

try:
    _framing_json = framing_json
except NameError:
    _framing_json = None

try:
    _cell_json = cell_json
except NameError:
    _cell_json = None

try:
    _run = run
except NameError:
    _run = False

if __name__ == "__main__":
    wall_routes_json, graph_pts, graph_lines, stats_json, status, info = main(
        _penetrations_json, _walls_json, _framing_json, _cell_json, _run
    )
