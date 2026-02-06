# File: scripts/gh_multi_layer_sheathing.py
"""Multi-Layer Sheathing Generator for Grasshopper.

Generates panels for ALL panelizable layers in a wall assembly (substrate,
finish, thermal) using the multi-layer generator. Each layer is positioned
at its correct W offset and configured with per-layer material defaults,
panel sizes, and optional user overrides.

Key Features:
1. Full Assembly Coverage
   - Processes every panelizable layer (substrate, finish, thermal)
   - Skips structural and membrane layers automatically
   - Configurable layer function filtering via include_functions

2. Per-Layer Configuration
   - Each layer receives material and panel size defaults based on function
   - Per-layer overrides via layer_configs in config_json
   - Base config applied to all layers unless overridden

3. Junction Integration
   - Computes per-face U-axis bounds from Junction Analyzer adjustments
   - Panels extend or trim at wall ends for proper junction coverage
   - Handles flipped walls by swapping exterior/interior face labels

4. JSON Pipeline
   - Accepts walls_json from Wall Analyzer
   - Outputs multi_layer_json for downstream geometry conversion
   - Inspectable intermediate data with Panel or jSwan

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework
    - json: Serialization
    - timber_framing_generator.sheathing.multi_layer_generator: Core generation logic

Performance Considerations:
    - Processing time scales with wall count and layer count per wall
    - Each layer runs a full SheathingGenerator pass (panel layout + cutouts)
    - Walls without wall_assembly are skipped with a warning

Usage:
    1. Connect 'walls_json' from Wall Analyzer component (must contain wall_assembly)
    2. Optionally connect 'junctions_json' from Junction Analyzer
    3. Optionally configure per-layer overrides via 'config_json'
    4. Optionally set 'assembly_mode' (auto/revit_only/catalog/custom)
    5. Optionally connect 'custom_map' JSON for per-Wall-Type mappings
    6. Set 'run' (last input) to True to execute
    7. Collect 'multi_layer_json' for downstream geometry conversion
    8. View 'layer_summary' for per-layer panel counts

Input Requirements:
    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer with wall geometry data.
        Must contain wall_assembly with layers list.
        Required: Yes
        Access: Item

    Junctions JSON (junctions_json) - str:
        Optional JSON from Junction Analyzer for per-layer adjustments.
        When connected, panels are extended or trimmed at wall ends
        to account for wall intersections (L-corners, T-junctions).
        Required: No
        Access: Item

    Config JSON (config_json) - str:
        Optional JSON with configuration overrides:
        - include_functions: List of layer functions to generate
          (default: ["substrate", "finish", "thermal"])
        - layer_configs: Per-layer config overrides keyed by layer name
          (e.g., {"OSB Sheathing": {"panel_size": "4x10"}})
        - panel_size: Default panel size for all layers (default "4x8")
        - faces: List of faces to process (default ["exterior", "interior"])
        - Other keys become base config for all layers
        Required: No
        Access: Item

    Assembly Mode (assembly_mode) - str:
        Assembly resolution mode controlling how wall assemblies are determined:
        - "auto" (default): Best available (Revit > catalog > inferred > default)
        - "revit_only": Only use explicit Revit CompoundStructure data
        - "catalog": Ignore Revit layers, match Wall Type name to catalog
        - "custom": Use per-Wall-Type mappings from Custom Map input
        Required: No (defaults to "auto")
        Access: Item

    Custom Map (custom_map) - str:
        Per-Wall-Type assembly mapping JSON for "custom" mode. Keys are
        Revit Wall Type names, values are catalog keys or inline assembly dicts.
        Example: {"Basic Wall - 2x6 Exterior": "2x6_exterior"}
        Unmapped Wall Types fall back to "auto" behavior.
        Required: No (only used in "custom" mode)
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution. Always the last input.
        Required: Yes
        Access: Item

Outputs:
    Multi-Layer JSON (multi_layer_json) - str:
        JSON string with all layer results per wall, including panel positions,
        W offsets, material summaries, and placement rules applied.

    Layer Summary (layer_summary) - str:
        Per-layer material summary showing panel counts per wall and layer.

    Stats (stats) - str:
        Quick stats: total panels, layers processed, walls processed.

    Log (log) - str:
        Processing log with debug information.

Technical Details:
    - Uses generate_assembly_layers() from multi_layer_generator module
    - Each layer is matched to a default material based on function + side
    - W offsets computed from assembly layer stack for correct 3D placement
    - Flipped walls swap exterior/interior face labels before processing

Error Handling:
    - Invalid JSON returns empty results with error in log
    - Walls without wall_assembly are skipped with warning
    - Per-layer errors are caught and logged without stopping other layers
    - Empty results return valid JSON structure with zero counts

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

from src.timber_framing_generator.sheathing.multi_layer_generator import (
    generate_assembly_layers,
)
from src.timber_framing_generator.config.assembly import get_assembly_for_wall
from src.timber_framing_generator.config.assembly_resolver import (
    resolve_all_walls,
    summarize_resolutions,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Multi-Layer Sheathing Generator"
COMPONENT_NICKNAME = "MLSheath"
COMPONENT_MESSAGE = "v1.1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "4-Sheathing"

# Default configuration
DEFAULT_CONFIG = {
    "panel_size": "4x8",
    "faces": ["exterior", "interior"],
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
    """Initialize and configure the Grasshopper component.

    Sets component metadata, input names/descriptions/access, and
    output names/descriptions. Output[0] is reserved for GH's internal
    'out' -- outputs start from index 1.

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Walls JSON", "walls_json",
         "JSON string from Wall Analyzer (must contain wall_assembly)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Junctions JSON", "junctions_json",
         "Optional JSON from Junction Analyzer for per-layer adjustments",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional configuration JSON with per-layer overrides",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Assembly Mode", "assembly_mode",
         "Assembly resolution mode: auto, revit_only, catalog, custom (default: auto)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Custom Map", "custom_map",
         'Per-Wall-Type assembly mapping JSON (e.g., {"My Wall Type": "2x6_exterior"})',
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
        ("Multi-Layer JSON", "multi_layer_json",
         "JSON with all layer results per wall"),
        ("Layer Summary", "layer_summary",
         "Per-layer material summary"),
        ("Stats", "stats",
         "Quick stats: total panels, layers, walls"),
        ("Log", "log",
         "Processing log"),
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
        walls_json: JSON string with wall data.
        run: Boolean run trigger.

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

    Extracts include_functions, layer_configs, and base config from
    the user-provided JSON. Keys not recognized as top-level control
    keys are passed through as base config for all layers.

    Args:
        config_json: Optional JSON string with config overrides.

    Returns:
        tuple: (base_config, layer_configs, include_functions)
            - base_config: Dict of settings applied to all layers.
            - layer_configs: Dict of per-layer overrides keyed by layer name.
            - include_functions: List of layer functions to generate, or None.
    """
    base_config = dict(DEFAULT_CONFIG)
    layer_configs = {}
    include_functions = None

    if config_json and config_json.strip():
        try:
            user_config = json.loads(config_json)
            log_info(f"Applied user config: {list(user_config.keys())}")

            # Extract top-level control keys
            if "include_functions" in user_config:
                include_functions = user_config.pop("include_functions")
                log_info(f"Filtering to functions: {include_functions}")

            if "layer_configs" in user_config:
                layer_configs = user_config.pop("layer_configs")
                log_info(f"Per-layer overrides for: {list(layer_configs.keys())}")

            # Remaining keys become the base config
            base_config.update(user_config)

        except json.JSONDecodeError as e:
            log_warning(f"Invalid config_json, using defaults: {e}")

    return base_config, layer_configs, include_functions


def compute_sheathing_bounds(wall_id, wall_length, face, junctions_data):
    """Compute U-axis panel bounds from junction adjustments.

    Looks up the junction adjustments for a specific wall and face,
    and returns the adjusted u_start_bound and u_end_bound.

    Args:
        wall_id: Wall identifier.
        wall_length: Original wall length in feet.
        face: "exterior" or "interior" -- determines which layer to use.
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


def process_walls(walls_json, base_config, layer_configs, include_functions,
                  junctions_data=None, assembly_mode="auto", custom_map=None):
    """Process walls and generate multi-layer sheathing panels.

    For each wall, resolves the assembly (using the assembly resolver),
    determines faces from config, computes junction bounds per face,
    handles wall flip state, and calls generate_assembly_layers() to
    produce panels for all panelizable layers.

    Args:
        walls_json: JSON string with wall data.
        base_config: Base configuration dict for all layers.
        layer_configs: Per-layer config overrides keyed by layer name.
        include_functions: List of layer functions to generate, or None for all.
        junctions_data: Optional parsed junctions_json dict.
        assembly_mode: Assembly resolution mode (auto/revit_only/catalog/custom).
        custom_map: Per-Wall-Type assembly mapping dict for custom mode.

    Returns:
        tuple: (all_results, summary_lines, stats_text, log_lines)
    """
    log_lines = []
    all_results = []
    summary_lines = []

    try:
        walls_data = json.loads(walls_json)
    except json.JSONDecodeError as e:
        log_error(f"Failed to parse walls_json: {e}")
        return [], [], "Error: Invalid JSON", [f"JSON parse error: {e}"]

    # Handle single wall or list of walls
    if isinstance(walls_data, dict):
        walls_list = [walls_data]
    elif isinstance(walls_data, list):
        walls_list = walls_data
    else:
        log_error("walls_json must be a dict or list")
        return [], [], "Error: Invalid format", ["Invalid walls_json format"]

    # Resolve assemblies for all walls
    walls_list = resolve_all_walls(walls_list, mode=assembly_mode, custom_map=custom_map)
    resolution_summary = summarize_resolutions(walls_list)

    log_info(f"Processing {len(walls_list)} walls for multi-layer sheathing")
    log_info(f"Assembly mode: {assembly_mode}")
    log_lines.append(f"Processing {len(walls_list)} walls")
    log_lines.append(f"Assembly mode: {assembly_mode}")
    log_lines.append(
        f"Assembly quality: {resolution_summary['by_source']} "
        f"(avg conf {resolution_summary['average_confidence']:.2f})"
    )
    log_lines.append(f"Base config: panel_size={base_config.get('panel_size', '4x8')}")
    if include_functions:
        log_lines.append(f"Layer filter: {include_functions}")
    if layer_configs:
        log_lines.append(f"Per-layer overrides: {list(layer_configs.keys())}")

    total_panels = 0
    total_layers_processed = 0
    walls_processed = 0

    summary_lines.append("=== Multi-Layer Sheathing ===")
    summary_lines.append(
        f"Assembly mode: {assembly_mode} | "
        f"Quality: {resolution_summary['by_source']}"
    )

    for i, wall_data in enumerate(walls_list):
        wall_id = wall_data.get("wall_id", f"wall_{i}")

        # Check if assembly was resolved (skipped walls have no assembly)
        wall_assembly = wall_data.get("wall_assembly")
        assembly_source = wall_data.get("assembly_source", "unknown")
        if not wall_assembly:
            if assembly_source == "skipped":
                log_info(f"Wall {wall_id}: skipped ({wall_data.get('assembly_notes', '')})")
            else:
                log_warning(f"Wall {wall_id}: no assembly resolved - skipping")
            log_lines.append(f"  Wall {wall_id}: SKIPPED ({assembly_source})")
            continue

        log_info(
            f"Processing wall {wall_id} "
            f"(assembly: {wall_data.get('assembly_name', '?')}, "
            f"source: {assembly_source}, "
            f"conf: {wall_data.get('assembly_confidence', 0):.2f})"
        )

        try:
            # Determine actual face labels, accounting for wall flip state.
            # When is_flipped=True, the wall's Z-axis (positive normal) points
            # to the interior instead of the exterior. We swap face labels so
            # panels are placed on the actual building exterior/interior.
            faces = base_config.get("faces", ["exterior", "interior"])
            is_flipped = wall_data.get("is_flipped", False)
            if is_flipped:
                faces = [
                    "interior" if f == "exterior" else "exterior"
                    for f in faces
                ]
                log_info(f"  Wall {wall_id} is flipped - swapped faces to {faces}")

            wall_length = wall_data.get("wall_length", 0)

            # Compute junction bounds for each face
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

            # Call multi-layer generator with per-face junction bounds.
            # Each layer uses the bounds matching its face (exterior or
            # interior), which may differ at wall corners.
            result = generate_assembly_layers(
                wall_data,
                config=base_config,
                layer_configs=layer_configs if layer_configs else None,
                face_bounds=face_bounds if face_bounds else None,
                include_functions=include_functions,
            )

            all_results.append(result)
            walls_processed += 1

            # Accumulate stats
            wall_panel_count = result.get("total_panel_count", 0)
            wall_layers_count = result.get("layers_processed", 0)
            total_panels += wall_panel_count
            total_layers_processed += wall_layers_count

            # Build per-wall summary
            layer_results = result.get("layer_results", [])
            if layer_results:
                summary_lines.append(f"Wall {wall_id}:")
                for lr in layer_results:
                    layer_name = lr.get("layer_name", "unknown")
                    layer_func = lr.get("layer_function", "")
                    layer_side = lr.get("layer_side", "")
                    panel_count = lr.get("panel_count", 0)
                    w_off = lr.get("w_offset")
                    w_str = f"w={w_off:.4f}" if w_off is not None else "w=None"
                    summary_lines.append(
                        f"  {layer_name} ({layer_func}/{layer_side}): "
                        f"{panel_count} panels, {w_str}"
                    )
                log_lines.append(
                    f"  Wall {wall_id}: {wall_panel_count} panels "
                    f"across {wall_layers_count} layers"
                )
            else:
                summary_lines.append(
                    f"Wall {wall_id}: no panelizable layers found"
                )
                log_lines.append(
                    f"  Wall {wall_id}: 0 panels (no panelizable layers)"
                )

        except Exception as e:
            log_warning(f"Error processing wall {wall_id}: {e}")
            log_lines.append(f"  Wall {wall_id}: ERROR - {e}")
            continue

    # Build stats text
    unique_layers = set()
    for result in all_results:
        for lr in result.get("layer_results", []):
            unique_layers.add(lr.get("layer_name", "unknown"))

    stats_text = (
        f"Total Panels: {total_panels}\n"
        f"Layers Processed: {total_layers_processed} "
        f"({len(unique_layers)} unique)\n"
        f"Walls Processed: {walls_processed}/{len(walls_list)}"
    )

    # Append total to summary
    summary_lines.append(
        f"Total: {total_panels} panels across "
        f"{len(unique_layers)} layers, {walls_processed} walls"
    )

    log_info(
        f"Total: {total_panels} panels, {total_layers_processed} layers, "
        f"{walls_processed} walls"
    )

    return all_results, summary_lines, stats_text, log_lines


# =============================================================================
# Main Function
# =============================================================================

def main(walls_json_in, junctions_json_in, config_json_in, run_in,
         assembly_mode_in=None, custom_map_in=None):
    """Main entry point for the component.

    Orchestrates the multi-layer sheathing generation workflow:
    1. Sets up component metadata
    2. Validates inputs
    3. Parses configuration (base config, layer overrides, function filter)
    4. Parses optional junction data
    5. Resolves assemblies for all walls (auto/revit_only/catalog/custom)
    6. Processes all walls
    7. Returns JSON results, summary, stats, and log

    Args:
        walls_json_in: JSON string from Wall Analyzer.
        junctions_json_in: Optional JSON from Junction Analyzer.
        config_json_in: Optional configuration JSON.
        run_in: Boolean to trigger execution.
        assembly_mode_in: Optional assembly resolution mode
            ("auto", "revit_only", "catalog", "custom"). Default: "auto".
        custom_map_in: Optional JSON string with per-Wall-Type assembly
            mappings for custom mode.

    Returns:
        tuple: (multi_layer_json, layer_summary, stats, log)
    """
    # Set component metadata and NickNames (for display, after inputs are read)
    setup_component()

    try:
        # Use inputs passed as arguments
        walls_json_input = walls_json_in
        junctions_json_input = junctions_json_in
        config_json_input = config_json_in
        run_input = run_in

        # Parse assembly mode (default: "auto")
        assembly_mode = "auto"
        if assembly_mode_in and str(assembly_mode_in).strip():
            assembly_mode = str(assembly_mode_in).strip().lower()

        # Parse custom map JSON (optional)
        custom_map = None
        if custom_map_in and str(custom_map_in).strip():
            try:
                custom_map = json.loads(custom_map_in)
                log_info(f"Custom map loaded: {len(custom_map)} Wall Type mappings")
            except (json.JSONDecodeError, TypeError) as e:
                log_warning(f"Invalid custom_map JSON, ignoring: {e}")

        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json_input, run_input)
        if not is_valid:
            log_info(error_msg)
            return "", error_msg, "", error_msg

        # Parse configuration
        base_config, layer_configs, include_functions = parse_config(
            config_json_input
        )

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
        results, summary_lines, stats_text, log_lines = process_walls(
            walls_json_input, base_config, layer_configs, include_functions,
            junctions_data, assembly_mode=assembly_mode, custom_map=custom_map,
        )

        # Serialize results to JSON
        multi_layer_json_output = json.dumps(results, indent=2)
        layer_summary_output = "\n".join(summary_lines)
        log_output = "\n".join(log_lines)

        return multi_layer_json_output, layer_summary_output, stats_text, log_output

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return "", error_msg, "", traceback.format_exc()


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
        "ERROR: Component has %d inputs but needs at least 4. "
        "Right-click component zoomable UI (ZUI) -> add inputs, "
        "then reconnect: walls_json, junctions_json, config_json, "
        "[assembly_mode], [custom_map], run"
        % _input_count
    )
    print(_msg)
    multi_layer_json = ""
    layer_summary = _msg
    stats = ""
    log = _msg
else:
    # Input order: data inputs first, run toggle last.
    # Indices 3-4 (assembly_mode, custom_map) are optional -- _read_input
    # returns None when the ZUI slot doesn't exist.
    _walls_json = _read_input(0)       # walls_json
    _junctions_json = _read_input(1)   # junctions_json
    _config_json = _read_input(2)      # config_json
    _assembly_mode = _read_input(3)    # assembly_mode (optional)
    _custom_map = _read_input(4)       # custom_map (optional)
    _run_index = _input_count - 1      # run is always last
    _run = bool(_read_input(_run_index, False))

    multi_layer_json, layer_summary, stats, log = main(
        _walls_json, _junctions_json, _config_json, _run,
        _assembly_mode, _custom_map,
    )
