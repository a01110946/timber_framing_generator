# File: scripts/gh_sheathing_generator.py
"""Sheathing Generator for Grasshopper.

Generates sheathing panel layouts for walls with proper panel sizing,
joint staggering, and opening cutouts. Outputs JSON data with panel
positions and a material summary for takeoff calculations.

Key Features:
1. Material Selection
   - Structural plywood (7/16", 15/32", 1/2", 19/32")
   - OSB (7/16", 1/2")
   - Gypsum board (1/2", 5/8")
   - DensGlass exterior sheathing

2. Panel Layout
   - Standard panel sizes (4x8, 4x9, 4x10, 4x12)
   - Automatic joint staggering between rows
   - Configurable minimum piece width

3. Opening Handling
   - Automatic cutouts for windows and doors
   - Cutout bounds clipped to panel edges
   - Waste calculation including cutouts

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework
    - json: Serialization
    - timber_framing_generator.sheathing: Sheathing generation logic

Performance Considerations:
    - Processing time scales with wall count and panel density
    - Large walls with many openings may have more cutout calculations
    - JSON output size proportional to panel count

Usage:
    1. Connect 'walls_json' from Wall Analyzer component
    2. Optionally configure material and panel size via 'config_json'
    3. Set 'run' to True to execute
    4. Collect 'sheathing_json' for downstream processing
    5. View 'summary' for material quantities

Input Requirements:
    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer with wall geometry data
        Required: Yes
        Access: Item

    Junctions JSON (junctions_json) - str:
        Optional JSON from Junction Analyzer with per-layer adjustments.
        When connected, sheathing panels are extended or trimmed at wall
        ends to account for wall intersections (L-corners, T-junctions).
        Required: No
        Access: Item

    Config JSON (config_json) - str:
        Optional JSON configuration with:
        - panel_size: "4x8", "4x9", "4x10", "4x12" (default "4x8")
        - material: Material name (default "structural_plywood_7_16")
        - stagger_offset: Feet between row joints (default 2.0)
        - min_piece_width: Minimum panel width in feet (default 0.5)
        - faces: List of faces to sheathe (default ["exterior"])
        Required: No
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Sheathing JSON (sheathing_json) - str:
        JSON string containing all sheathing panels with positions and cutouts

    Summary (summary) - str:
        Material summary with panel counts, areas, and waste percentage

    Log (log) - str:
        Processing log with debug information

Technical Details:
    - Panels laid out left-to-right, bottom-to-top
    - Stagger offset applied to alternating rows
    - Cutouts calculated as intersection of opening and panel bounds
    - Full sheets identified for material ordering optimization

Error Handling:
    - Invalid JSON returns empty results with error in log
    - Invalid material name falls back to default with warning
    - Empty walls return empty panel list (no error)

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
import Grasshopper

# =============================================================================
# Module Reload (Development Only)
# =============================================================================

# Force reload of project modules during development
# Set to False in production for better performance
FORCE_RELOAD = True

if FORCE_RELOAD:
    modules_to_reload = [key for key in sys.modules.keys()
                         if 'timber_framing_generator' in key]
    for mod_name in modules_to_reload:
        del sys.modules[mod_name]

# =============================================================================
# Project Imports (after reload)
# =============================================================================

from src.timber_framing_generator.sheathing import (
    generate_wall_sheathing,
    SHEATHING_MATERIALS,
    PANEL_SIZES,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Sheathing Generator"
COMPONENT_NICKNAME = "Sheath"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "4-Sheathing"

# Default configuration
DEFAULT_CONFIG = {
    "panel_size": "4x8",
    "material": "structural_plywood_7_16",
    "stagger_offset": 2.0,
    "min_piece_width": 0.5,
    "faces": ["exterior"],
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
        ("Junctions JSON", "junctions_json",
         "Optional JSON from Junction Analyzer for per-layer adjustments",
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
        ("Sheathing JSON", "sheathing_json", "JSON with sheathing panel data"),
        ("Summary", "summary", "Material summary string"),
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
    """Validate component inputs.

    Args:
        walls_json: JSON string with wall data
        run: Boolean run trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Run is False - component disabled"

    if walls_json is None or not walls_json.strip():
        return False, "walls_json is required"

    return True, None


def parse_config(config_json):
    """Parse configuration JSON with defaults.

    Args:
        config_json: Optional JSON string with config overrides

    Returns:
        dict: Merged configuration with defaults
    """
    config = dict(DEFAULT_CONFIG)

    if config_json and config_json.strip():
        try:
            user_config = json.loads(config_json)
            config.update(user_config)
            log_info(f"Applied user config: {list(user_config.keys())}")
        except json.JSONDecodeError as e:
            log_warning(f"Invalid config_json, using defaults: {e}")

    # Validate material
    if config["material"] not in SHEATHING_MATERIALS:
        log_warning(f"Unknown material '{config['material']}', using default")
        config["material"] = DEFAULT_CONFIG["material"]

    # Validate panel size
    if config["panel_size"] not in PANEL_SIZES:
        log_warning(f"Unknown panel size '{config['panel_size']}', using default")
        config["panel_size"] = DEFAULT_CONFIG["panel_size"]

    return config


def compute_sheathing_bounds(wall_id, wall_length, face, junctions_data):
    """Compute U-axis panel bounds from junction adjustments.

    Looks up the junction adjustments for a specific wall and face,
    and returns the adjusted u_start_bound and u_end_bound.

    Args:
        wall_id: Wall identifier.
        wall_length: Original wall length in feet.
        face: "exterior" or "interior" — determines which layer to use.
        junctions_data: Parsed junctions_json dict, or None.

    Returns:
        tuple: (u_start_bound, u_end_bound) in feet.
    """
    u_start_bound = 0.0
    u_end_bound = wall_length

    if not junctions_data:
        return u_start_bound, u_end_bound

    # Map face to layer name
    layer_name = "exterior" if face == "exterior" else "interior"

    # Get adjustments for this wall
    wall_adjustments = junctions_data.get("wall_adjustments", {}).get(wall_id, [])

    for adj in wall_adjustments:
        if adj.get("layer_name") != layer_name:
            continue

        end = adj.get("end")
        adj_type = adj.get("adjustment_type")
        amount = adj.get("amount", 0.0)

        if end == "start":
            if adj_type == "extend":
                u_start_bound = -amount  # Extend before wall start
            elif adj_type == "trim":
                u_start_bound = amount   # Trim after wall start
        elif end == "end":
            if adj_type == "extend":
                u_end_bound = wall_length + amount  # Extend past wall end
            elif adj_type == "trim":
                u_end_bound = wall_length - amount  # Trim before wall end

    return u_start_bound, u_end_bound


def process_walls(walls_json, config, junctions_data=None):
    """Process walls and generate sheathing panels.

    Args:
        walls_json: JSON string with wall data
        config: Configuration dictionary
        junctions_data: Optional parsed junctions_json dict

    Returns:
        tuple: (all_results, summary_text, log_lines)
    """
    log_lines = []
    all_results = []

    try:
        walls_data = json.loads(walls_json)
    except json.JSONDecodeError as e:
        log_error(f"Failed to parse walls_json: {e}")
        return [], "Error: Invalid JSON", [f"JSON parse error: {e}"]

    # Handle single wall or list of walls
    if isinstance(walls_data, dict):
        walls_list = [walls_data]
    elif isinstance(walls_data, list):
        walls_list = walls_data
    else:
        log_error("walls_json must be a dict or list")
        return [], "Error: Invalid format", ["Invalid walls_json format"]

    log_info(f"Processing {len(walls_list)} walls")
    log_lines.append(f"Processing {len(walls_list)} walls")
    log_lines.append(f"Config: panel_size={config['panel_size']}, material={config['material']}")

    total_panels = 0
    total_gross_area = 0
    total_net_area = 0

    for i, wall_data in enumerate(walls_list):
        wall_id = wall_data.get("wall_id", f"wall_{i}")
        log_info(f"Processing wall {wall_id}")

        try:
            # Determine actual face labels, accounting for wall flip state.
            # When is_flipped=True, the wall's Z-axis (positive normal) points
            # to the interior instead of the exterior. We swap face labels so
            # "exterior" sheathing is placed on the actual building exterior.
            faces = config.get("faces", ["exterior"])
            is_flipped = wall_data.get("is_flipped", False)
            if is_flipped:
                faces = [
                    "interior" if f == "exterior" else "exterior"
                    for f in faces
                ]
                log_info(f"  Wall {wall_id} is flipped - swapped faces to {faces}")

            wall_length = wall_data.get("wall_length", 0)
            face_bounds = {}
            for face in faces:
                u_start, u_end = compute_sheathing_bounds(
                    wall_id, wall_length, face, junctions_data
                )
                face_bounds[face] = (u_start, u_end)
                if u_start != 0.0 or u_end != wall_length:
                    log_info(
                        f"  {face} bounds: u=[{u_start:.4f}, {u_end:.4f}] "
                        f"(wall_length={wall_length:.4f})"
                    )

            # Generate sheathing for this wall
            # Use first face bounds for the generator (each face will be
            # generated separately if bounds differ per face)
            first_face = faces[0] if faces else "exterior"
            u_start_bound, u_end_bound = face_bounds.get(
                first_face, (0.0, wall_length)
            )

            result = generate_wall_sheathing(
                wall_data,
                config=config,
                faces=faces,
                u_start_bound=u_start_bound,
                u_end_bound=u_end_bound,
            )

            all_results.append(result)

            # Accumulate stats
            wall_summary = result.get("summary", {})
            total_panels += wall_summary.get("total_panels", 0)
            total_gross_area += wall_summary.get("gross_area_sqft", 0)
            total_net_area += wall_summary.get("net_area_sqft", 0)

            log_lines.append(f"  Wall {wall_id}: {wall_summary.get('total_panels', 0)} panels")

        except Exception as e:
            log_warning(f"Error processing wall {wall_id}: {e}")
            log_lines.append(f"  Wall {wall_id}: ERROR - {e}")
            continue

    # Build summary text
    waste_area = total_gross_area - total_net_area
    waste_pct = (waste_area / total_gross_area * 100) if total_gross_area > 0 else 0

    summary_text = (
        f"Total Panels: {total_panels}\n"
        f"Gross Area: {total_gross_area:.1f} sq ft\n"
        f"Net Area: {total_net_area:.1f} sq ft\n"
        f"Waste: {waste_area:.1f} sq ft ({waste_pct:.1f}%)\n"
        f"Material: {config['material']}\n"
        f"Panel Size: {config['panel_size']}"
    )

    log_info(f"Total: {total_panels} panels, {total_gross_area:.1f} sq ft")

    return all_results, summary_text, log_lines


# =============================================================================
# Main Function
# =============================================================================

def main(walls_json_in, junctions_json_in, config_json_in, run_in):
    """Main entry point for the component.

    Args:
        walls_json_in: JSON string from Wall Analyzer
        junctions_json_in: Optional JSON from Junction Analyzer
        config_json_in: Optional configuration JSON
        run_in: Boolean to trigger execution
    """
    # Set component metadata and NickNames (for display, after inputs are read)
    setup_component()

    try:
        # Use inputs passed as arguments
        walls_json_input = walls_json_in
        junctions_json_input = junctions_json_in
        config_json_input = config_json_in
        run_input = run_in

        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json_input, run_input)
        if not is_valid:
            log_info(error_msg)
            return "", error_msg, error_msg

        # Parse configuration
        config = parse_config(config_json_input)

        # Parse junctions data (optional)
        junctions_data = None
        if junctions_json_input and str(junctions_json_input).strip():
            try:
                junctions_data = json.loads(junctions_json_input)
                junc_count = junctions_data.get("junction_count", 0)
                adj_count = sum(
                    len(adjs)
                    for adjs in junctions_data.get("wall_adjustments", {}).values()
                )
                log_info(
                    f"Loaded junction data: {junc_count} junctions, "
                    f"{adj_count} adjustments"
                )
            except (json.JSONDecodeError, TypeError) as e:
                log_warning(f"Invalid junctions_json, ignoring: {e}")

        # Process walls
        results, summary_text, log_lines = process_walls(
            walls_json_input, config, junctions_data
        )

        # Serialize results to JSON
        sheathing_json_output = json.dumps(results, indent=2)
        log_output = "\n".join(log_lines)

        return sheathing_json_output, summary_text, log_output

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return "", error_msg, traceback.format_exc()


# =============================================================================
# Execution
# =============================================================================

# Read inputs by parameter index via VolatileData.AllData(True).
# NickName-based global injection is unreliable in Rhino 8 CPython --
# setup_component() renames NickNames but GH injects globals based on the
# NickName at solve-start, causing mismatches. AllData(True) always works.

def _read_input(index, default=None):
    """Read a GH input value by parameter index via VolatileData."""
    inputs = ghenv.Component.Params.Input
    if index >= inputs.Count:
        return default
    param = inputs[index]
    if param.VolatileDataCount == 0:
        return default
    all_data = list(param.VolatileData.AllData(True))
    if not all_data:
        return default
    goo = all_data[0]
    if hasattr(goo, "Value"):
        return goo.Value
    if hasattr(goo, "ScriptVariable"):
        return goo.ScriptVariable()
    return default

_input_count = ghenv.Component.Params.Input.Count
if _input_count < 4:
    _msg = (
        "ERROR: Component has %d inputs but needs 4. "
        "Right-click component zoomable UI (ZUI) -> add input until you have 4, "
        "then reconnect: walls_json, junctions_json, config_json, run"
        % _input_count
    )
    print(_msg)
    sheathing_json = ""
    summary = _msg
    log = _msg
else:
    _walls_json = _read_input(0)       # walls_json
    _junctions_json = _read_input(1)   # junctions_json
    _config_json = _read_input(2)      # config_json
    _run = bool(_read_input(3, False)) # run

    sheathing_json, summary, log = main(
        _walls_json, _junctions_json, _config_json, _run
    )
