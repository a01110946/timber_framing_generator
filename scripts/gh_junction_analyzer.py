# File: scripts/gh_junction_analyzer.py
"""Junction Analyzer for Grasshopper.

Analyzes wall junctions (L-corners, T-intersections, X-crossings) from wall
geometry data and outputs per-layer extension/trim adjustments. This component
sits between the Wall Analyzer and downstream framing/sheathing generators,
providing each with the exact adjustment amounts needed at every wall end.

Key Features:
1. Junction Detection and Classification
   - L-corners (two walls meeting at an angle)
   - T-intersections (wall ending mid-span of another)
   - X-crossings (two walls crossing through each other)
   - Free ends and inline continuations

2. Per-Layer Resolution
   - Butt and miter join strategies
   - Configurable priority: longer_wall, exterior_first, alternate
   - Per-wall layer thickness overrides (exterior, core, interior)
   - User overrides for individual junction resolutions

3. Debug Visualization
   - Junction node points at intersection locations
   - Wall edge lines from start to end point
   - Uses RhinoCommonFactory for correct assembly output

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Point3d and LineCurve for debug visualization
    - Grasshopper: Component framework and data structures
    - json: Serialization of wall and junction data
    - timber_framing_generator.wall_junctions: Junction analysis pipeline
    - timber_framing_generator.utils.geometry_factory: RhinoCommonFactory

Performance Considerations:
    - O(walls^2) for endpoint-matching during detection
    - Typical residential models (< 50 walls) process in < 100ms
    - JSON output size proportional to junction and adjustment count

Usage:
    1. Connect 'walls_json' from Wall Analyzer component
    2. Optionally configure tolerance, join type, priority via 'config_json'
    3. Set 'run' to True to execute
    4. Connect 'junctions_json' to downstream framing/sheathing components
    5. View 'summary' for junction counts and resolution statistics

Input Requirements:
    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer with wall geometry data.
        Format: list of wall dicts with wall_id, wall_length, wall_thickness,
        base_plane, base_curve_start, base_curve_end, is_exterior, etc.
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Config JSON (config_json) - str:
        Optional JSON configuration overrides:
        - tolerance: float (default 0.1) endpoint matching tolerance in feet
        - t_intersection_tolerance: float (default 0.15)
        - default_join_type: "butt" or "miter" (default "butt")
        - priority_strategy: "longer_wall", "exterior_first", "alternate"
        - junction_overrides: dict of junction_id -> {join_type, primary_wall_id}
        - layer_overrides: dict of wall_id -> {exterior_thickness, core_thickness, interior_thickness}
        Required: No
        Access: Item
        Type hint: str (set via GH UI)

    Run (run) - bool:
        Boolean to trigger execution.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

Outputs:
    Junctions JSON (junctions_json) - str:
        JSON string with junction graph, resolutions, and per-wall adjustments.

    Graph Points (graph_pts) - List[Point3d]:
        Junction node positions for debug visualization.

    Graph Lines (graph_lines) - List[LineCurve]:
        Wall edges (start to end) for debug visualization.

    Summary (summary) - str:
        Human-readable junction summary with counts and statistics.

    Log (log) - str:
        Processing log with debug information.

Technical Details:
    - Junction detection uses endpoint proximity matching within tolerance
    - T-intersections detected via perpendicular projection onto wall midspans
    - Priority strategy determines which wall extends vs trims at butt joins
    - All geometry output uses RhinoCommonFactory to avoid assembly mismatch

Error Handling:
    - Invalid walls_json returns empty outputs with error in log
    - Invalid config_json falls back to defaults with warning
    - Individual wall processing failures do not halt the pipeline
    - Empty wall list produces valid but empty junction graph

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

from src.timber_framing_generator.wall_junctions import analyze_junctions
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Junction Analyzer"
COMPONENT_NICKNAME = "JnxAnl"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Analysis"

DEFAULT_CONFIG = {
    "tolerance": 0.1,
    "t_intersection_tolerance": 0.15,
    "default_join_type": "butt",
    "priority_strategy": "longer_wall",
    "junction_overrides": {},
    "layer_overrides": {},
}

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
        - walls_json: str
        - config_json: str
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
        ("Walls JSON", "walls_json",
         "JSON string from Wall Analyzer with wall geometry data",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional JSON configuration (tolerance, join type, priority, overrides)",
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
        ("Junctions JSON", "junctions_json",
         "JSON with junction graph, resolutions, and per-wall adjustments"),
        ("Graph Points", "graph_pts",
         "Junction node positions for debug visualization"),
        ("Graph Lines", "graph_lines",
         "Wall edges (start to end) for debug visualization"),
        ("Summary", "summary",
         "Human-readable junction summary"),
        ("Log", "log",
         "Processing log with debug information"),
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

def validate_inputs(
    walls_json_input: str,
    run_input: bool,
) -> tuple:
    """Validate component inputs.

    Args:
        walls_json_input: JSON string with wall data.
        run_input: Boolean trigger.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_input:
        return False, "Component not running. Set 'run' to True."

    if not walls_json_input or not isinstance(walls_json_input, str):
        return False, "walls_json is required"

    if not walls_json_input.strip():
        return False, "walls_json is empty"

    # Validate JSON is parsable
    try:
        data = json.loads(walls_json_input)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    # Validate we have walls
    if isinstance(data, dict):
        walls = data.get("walls", [])
    elif isinstance(data, list):
        walls = data
    else:
        return False, "walls_json must be a dict or list"

    if not walls:
        return False, "walls_json contains no walls"

    return True, None


def parse_config(config_json_input: str) -> dict:
    """Parse configuration JSON with defaults.

    Args:
        config_json_input: Optional JSON string with config overrides.

    Returns:
        dict: Merged configuration with defaults.
    """
    config = dict(DEFAULT_CONFIG)

    if config_json_input and isinstance(config_json_input, str) and config_json_input.strip():
        try:
            user_config = json.loads(config_json_input)
            if isinstance(user_config, dict):
                config.update(user_config)
                log_info(f"Applied user config: {list(user_config.keys())}")
            else:
                log_warning("config_json must be a JSON object, using defaults")
        except json.JSONDecodeError as e:
            log_warning(f"Invalid config_json, using defaults: {e}")

    # Validate join type
    valid_join_types = ("butt", "miter")
    if config["default_join_type"] not in valid_join_types:
        log_warning(
            f"Unknown default_join_type '{config['default_join_type']}', "
            f"using 'butt'. Valid: {valid_join_types}"
        )
        config["default_join_type"] = "butt"

    # Validate priority strategy
    valid_strategies = ("longer_wall", "exterior_first", "alternate")
    if config["priority_strategy"] not in valid_strategies:
        log_warning(
            f"Unknown priority_strategy '{config['priority_strategy']}', "
            f"using 'longer_wall'. Valid: {valid_strategies}"
        )
        config["priority_strategy"] = "longer_wall"

    # Validate tolerance values are positive
    for key in ("tolerance", "t_intersection_tolerance"):
        if not isinstance(config.get(key), (int, float)) or config[key] <= 0:
            log_warning(f"Invalid {key}={config.get(key)}, using default")
            config[key] = DEFAULT_CONFIG[key]

    return config


def parse_walls(walls_json_str: str) -> list:
    """Parse walls from JSON string.

    Handles both dict-with-key and bare-list formats.

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


def create_debug_geometry(graph, walls_data: list) -> tuple:
    """Create debug visualization geometry from junction graph and wall data.

    For each junction node, creates a Point3d at the node position.
    For each wall, creates a LineCurve from start to end point.

    All geometry is created via RhinoCommonFactory to avoid assembly mismatch.

    Args:
        graph: JunctionGraph with nodes and resolutions.
        walls_data: List of wall dicts for wall edge geometry.

    Returns:
        tuple: (graph_pts, graph_lines) - lists of Point3d and LineCurve.
    """
    factory = get_factory()
    graph_pts = []
    graph_lines = []

    # Junction node points
    for node in graph.nodes.values():
        try:
            pos = node.position
            pt = factory.create_point3d(
                float(pos[0]), float(pos[1]), float(pos[2])
            )
            if pt is not None:
                graph_pts.append(pt)
        except Exception as e:
            log_debug(f"Failed to create point for junction {node.id}: {e}")

    # Wall edge lines (start to end)
    for wall in walls_data:
        try:
            # Extract start/end points from wall data
            start = _extract_point(wall, "base_curve_start")
            end = _extract_point(wall, "base_curve_end")

            if start is not None and end is not None:
                line_curve = factory.create_line_curve(start, end)
                if line_curve is not None:
                    graph_lines.append(line_curve)
        except Exception as e:
            wall_id = wall.get("wall_id", "unknown")
            log_debug(f"Failed to create line for wall {wall_id}: {e}")

    return graph_pts, graph_lines


def _extract_point(wall: dict, key: str) -> tuple:
    """Extract a (x, y, z) tuple from wall data for a given key.

    Handles both flat dict format {"x": ..., "y": ..., "z": ...} and
    the WallData schema format.

    Args:
        wall: Wall dict from walls_json.
        key: Key name (e.g., "base_curve_start", "base_curve_end").

    Returns:
        (x, y, z) tuple of floats, or None if not found.
    """
    pt_data = wall.get(key)
    if pt_data is None:
        return None

    if isinstance(pt_data, dict):
        x = float(pt_data.get("x", 0))
        y = float(pt_data.get("y", 0))
        z = float(pt_data.get("z", 0))
        return (x, y, z)

    if isinstance(pt_data, (list, tuple)) and len(pt_data) >= 3:
        return (float(pt_data[0]), float(pt_data[1]), float(pt_data[2]))

    return None


def build_summary_text(graph) -> str:
    """Build a human-readable summary string from the junction graph.

    Args:
        graph: JunctionGraph with nodes, resolutions, and adjustments.

    Returns:
        Formatted summary string.
    """
    stats = graph._build_summary()

    lines = [
        "=== Junction Analysis Summary ===",
        "",
        f"Total Junctions: {stats['total_junctions']}",
        f"  L-Corners:        {stats['l_corners']}",
        f"  T-Intersections:  {stats['t_intersections']}",
        f"  X-Crossings:      {stats['x_crossings']}",
        f"  Free Ends:        {stats['free_ends']}",
        f"  Inline:           {stats['inline']}",
        f"  Multi-Way:        {stats['multi_way']}",
        "",
        f"Resolutions: {stats['total_resolutions']}",
        f"User Overrides Applied: {stats['user_overrides_applied']}",
        "",
        f"Walls with Adjustments: {len(graph.wall_adjustments)}",
    ]

    # Per-wall adjustment summary
    if graph.wall_adjustments:
        lines.append("")
        lines.append("--- Per-Wall Adjustments ---")
        for wall_id, adjs in sorted(graph.wall_adjustments.items()):
            adj_strs = []
            for adj in adjs:
                adj_strs.append(
                    f"{adj.layer_name}/{adj.end}: "
                    f"{adj.adjustment_type.value} {adj.amount:.4f}'"
                )
            lines.append(f"  Wall {wall_id}: {len(adjs)} adjustments")
            for s in adj_strs:
                lines.append(f"    {s}")

    return "\n".join(lines)

# =============================================================================
# Main Function
# =============================================================================

def main(
    walls_json_input: str,
    config_json_input: str,
    run_input: bool,
) -> tuple:
    """Main entry point for the component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Parse configuration and walls
    4. Run junction analysis pipeline
    5. Create debug visualization geometry
    6. Return results

    Args:
        walls_json_input: JSON string from Wall Analyzer.
        config_json_input: Optional configuration JSON.
        run_input: Boolean trigger.

    Returns:
        tuple: (junctions_json, graph_pts, graph_lines, summary, log)
    """
    setup_component()

    # Initialize outputs with safe defaults
    junctions_json = ""
    graph_pts = []
    graph_lines = []
    summary_text = ""
    log_lines = []

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json_input, run_input)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            log_lines.append(error_msg or "Validation failed")
            return junctions_json, graph_pts, graph_lines, summary_text, "\n".join(log_lines)

        log_lines.append("Junction Analyzer v1.0")
        log_lines.append("Inputs validated successfully")

        # Parse configuration
        config = parse_config(config_json_input)
        log_lines.append(
            f"Config: join_type={config['default_join_type']}, "
            f"priority={config['priority_strategy']}, "
            f"tolerance={config['tolerance']}"
        )

        # Parse walls
        start_time = time.time()
        walls_data = parse_walls(walls_json_input)
        log_lines.append(f"Parsed {len(walls_data)} walls")

        # Run junction analysis pipeline
        graph = analyze_junctions(
            walls_data,
            tolerance=config["tolerance"],
            t_intersection_tolerance=config["t_intersection_tolerance"],
            default_join_type=config["default_join_type"],
            priority_strategy=config["priority_strategy"],
            user_overrides=config.get("junction_overrides") or None,
            layer_overrides=config.get("layer_overrides") or None,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        log_lines.append(f"Analysis completed in {elapsed_ms:.1f}ms")

        # Serialize result to JSON
        graph_dict = graph.to_dict()
        junctions_json = json.dumps(graph_dict, indent=2)

        # Build summary
        summary_text = build_summary_text(graph)

        # Create debug visualization geometry
        graph_pts, graph_lines = create_debug_geometry(graph, walls_data)
        log_lines.append(
            f"Debug geometry: {len(graph_pts)} junction points, "
            f"{len(graph_lines)} wall lines"
        )

        # Log summary stats
        stats = graph_dict.get("summary", {})
        log_lines.append("")
        log_lines.append("=== RESULTS ===")
        log_lines.append(f"Junctions found: {stats.get('total_junctions', 0)}")
        log_lines.append(f"  L-Corners: {stats.get('l_corners', 0)}")
        log_lines.append(f"  T-Intersections: {stats.get('t_intersections', 0)}")
        log_lines.append(f"  X-Crossings: {stats.get('x_crossings', 0)}")
        log_lines.append(f"  Free Ends: {stats.get('free_ends', 0)}")
        log_lines.append(f"Resolutions: {stats.get('total_resolutions', 0)}")
        log_lines.append(f"Walls with adjustments: {len(graph.wall_adjustments)}")

        total_adjustments = sum(
            len(adjs) for adjs in graph.wall_adjustments.values()
        )
        log_lines.append(f"Total layer adjustments: {total_adjustments}")

        if stats.get("user_overrides_applied", 0) > 0:
            log_lines.append(
                f"User overrides applied: {stats['user_overrides_applied']}"
            )

    except ImportError as e:
        log_error(f"Import error: {e}")
        log_lines.append(f"Import error: {e}")
        log_lines.append("Ensure timber_framing_generator is installed and on sys.path")
        log_lines.append(traceback.format_exc())
    except json.JSONDecodeError as e:
        log_error(f"JSON parse error: {e}")
        log_lines.append(f"JSON parse error: {e}")
    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_lines.append(f"Error: {type(e).__name__}: {e}")
        log_lines.append(traceback.format_exc())

    return junctions_json, graph_pts, graph_lines, summary_text, "\n".join(log_lines)

# =============================================================================
# Execution
# =============================================================================

# Resolve GH global inputs with safe defaults.
# In GHPython, input variables are injected as globals based on NickName.
# NOTE: After pasting this script, you may need to:
#   1. Set the correct number of inputs (3) and outputs (6, including 'out')
#   2. Right-click each input and set type hints:
#      Input 0 (walls_json): str
#      Input 1 (config_json): str
#      Input 2 (run): bool

try:
    _walls_json = walls_json
except NameError:
    _walls_json = None

try:
    _config_json = config_json
except NameError:
    _config_json = None

try:
    _run = run
except NameError:
    _run = False

if __name__ == "__main__":
    junctions_json, graph_pts, graph_lines, summary, log = main(
        _walls_json, _config_json, _run
    )
