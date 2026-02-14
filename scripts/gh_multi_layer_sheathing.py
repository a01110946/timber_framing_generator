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
    1. Connect 'walls_json' from Wall Analyzer component
    2. Optionally connect 'junctions_json' from Junction Analyzer
    3. Connect 'config_json' from Config Builder (or manual JSON)
    4. Optionally connect 'framing_json' from Framing Generator
    5. Set 'run' (last input) to True to execute
    6. Collect 'multi_layer_json' for downstream geometry conversion
    7. View 'layer_summary' for per-layer panel counts

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
        Configuration JSON from Config Builder component. Contains:
        - assembly_mode: "auto" or "revit" (default: "auto")
        - framing_system: "timber" or "cfs" (default: "timber")
        - assembly_overrides: Per-Wall-Type assembly mappings (optional)
        - faces: List of faces to process (default ["exterior", "interior"])
        - panel_size: Default panel size (default "4x8")
        - include_functions: Layer function filter (optional)
        - layer_configs: Per-layer config overrides (optional)
        Required: No
        Access: Item

    Framing JSON (framing_json) - str:
        Optional JSON from Framing Generator. When connected, extracts
        per-wall stud profile depth to prevent sheathing overlap with
        CFS or oversized framing.
        Required: No
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
Version: 0.2.3
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
# Project Setup
# =============================================================================

# Primary: worktree / feature-branch path (contains wall_junctions, etc.)
# Fallback: main repo path (for when this file is used from the main checkout)
_WORKTREE_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\tfg-sheathing-junctions"
_MAIN_REPO_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Ensure worktree path has highest priority (index 0) in sys.path.
# Other GH components may have already added the main repo path, so we
# remove both and re-insert in correct priority order.
for _p in (_WORKTREE_PATH, _MAIN_REPO_PATH):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _MAIN_REPO_PATH)
sys.path.insert(0, _WORKTREE_PATH)

# =============================================================================
# Module Reload (Development Only)
# =============================================================================

# Force reload of project modules during development
# Set to False in production for better performance
FORCE_RELOAD = True

if FORCE_RELOAD:
    # Clear timber_framing_generator modules AND the 'src' package itself.
    # Other GH components may have already imported 'src', caching its
    # __path__ to the main repo.  Clearing it forces Python to re-resolve
    # 'src' from the updated sys.path (worktree at index 0).
    modules_to_reload = [key for key in sys.modules.keys()
                         if 'timber_framing_generator' in key
                         or key == 'src']
    for mod_name in modules_to_reload:
        del sys.modules[mod_name]

# =============================================================================
# Project Imports (after reload)
# =============================================================================

from src.timber_framing_generator.sheathing.multi_layer_generator import (
    generate_assembly_layers,
    extract_max_framing_depth,
)
from src.timber_framing_generator.config.assembly import get_assembly_for_wall
from src.timber_framing_generator.config.assembly_resolver import (
    resolve_all_walls,
    summarize_resolutions,
)
from src.timber_framing_generator.wall_junctions.junction_resolver import (
    recompute_adjustments,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Multi-Layer Sheathing Generator"
COMPONENT_NICKNAME = "MLSheath"
COMPONENT_MESSAGE = "v2.8-embedded-panels"

# Version marker — confirms the updated script is running in GH
print("[MLSheath] Script version v2.8 loaded (embedded panels fallback + diagnostics)")
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

    # Input layout depends on component input count:
    # 5 inputs (legacy): walls, junctions, config, framing, run
    # 6 inputs (new):    walls, junctions, config, framing, panels_json, run
    input_config = [
        ("Walls JSON", "walls_json",
         "JSON string from Wall Analyzer (must contain wall_assembly)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Junctions JSON", "junctions_json",
         "Optional JSON from Junction Analyzer for per-layer adjustments",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Configuration JSON from Config Builder (assembly_mode, framing_system, "
         "faces, panel_size, include_functions, assembly_overrides, layer_configs)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Framing JSON", "framing_json",
         "Optional JSON from Framing Generator — auto-detects framing profile depth "
         "to prevent sheathing overlap with CFS or oversized framing",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    if inputs.Count >= 6:
        # 6-input layout: panels_json at 4, run at 5
        input_config.append(
            ("Panels JSON", "panels_json",
             "Optional JSON from Panel Decomposer for panel-bounded sheathing",
             Grasshopper.Kernel.GH_ParamAccess.item))
        input_config.append(
            ("Run", "run", "Boolean to trigger execution",
             Grasshopper.Kernel.GH_ParamAccess.item))
    else:
        # 5-input layout (legacy): run at 4
        input_config.append(
            ("Run", "run", "Boolean to trigger execution",
             Grasshopper.Kernel.GH_ParamAccess.item))

    # Guard: only set properties that actually differ from current values.
    # Setting Access unconditionally can trigger GH parameter reconstruction
    # which silently disconnects wires (even if the value doesn't change).
    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            p = inputs[i]
            if p.Name != name:
                p.Name = name
            if p.NickName != nick:
                p.NickName = nick
            if p.Description != desc:
                p.Description = desc
            if p.Access != access:
                p.Access = access

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

    Extracts control keys (assembly_mode, framing_system, assembly_overrides,
    include_functions, layer_configs, framing_depth) and passes remaining
    keys through as base config for all layers.

    Args:
        config_json: Optional JSON string with config overrides.

    Returns:
        tuple: (base_config, layer_configs, include_functions, framing_depth,
                assembly_mode, framing_system, assembly_overrides)
            - base_config: Dict of settings applied to all layers.
            - layer_configs: Dict of per-layer overrides keyed by layer name.
            - include_functions: List of layer functions to generate, or None.
            - framing_depth: Explicit framing profile depth in feet, or None.
            - assembly_mode: "auto" or "revit" (default "auto").
            - framing_system: "timber" or "cfs" (default "timber").
            - assembly_overrides: Dict of per-Wall-Type mappings, or None.
    """
    base_config = dict(DEFAULT_CONFIG)
    layer_configs = {}
    include_functions = None
    framing_depth = None
    assembly_mode = "auto"
    framing_system = "timber"
    assembly_overrides = None

    if config_json and config_json.strip():
        try:
            user_config = json.loads(config_json)
            log_info(f"Applied user config: {list(user_config.keys())}")

            # Extract top-level control keys (not passed to base_config)
            if "include_functions" in user_config:
                include_functions = user_config.pop("include_functions")
                log_info(f"Filtering to functions: {include_functions}")

            if "layer_configs" in user_config:
                layer_configs = user_config.pop("layer_configs")
                log_info(f"Per-layer overrides for: {list(layer_configs.keys())}")

            if "framing_depth" in user_config:
                framing_depth = float(user_config.pop("framing_depth"))
                log_info(f"Explicit framing_depth: {framing_depth:.4f} ft")

            if "assembly_mode" in user_config:
                assembly_mode = str(user_config.pop("assembly_mode")).strip().lower()
                log_info(f"Assembly mode: {assembly_mode}")

            if "framing_system" in user_config:
                framing_system = str(user_config.pop("framing_system")).strip().lower()
                log_info(f"Framing system: {framing_system}")

            if "assembly_overrides" in user_config:
                assembly_overrides = user_config.pop("assembly_overrides")
                if assembly_overrides and isinstance(assembly_overrides, dict):
                    log_info(f"Assembly overrides: {len(assembly_overrides)} Wall Type mappings")
                else:
                    assembly_overrides = None

            # Remove stud_spacing — not used by MLSheath (consumed by Framing Generator)
            user_config.pop("stud_spacing", None)

            # Remaining keys become the base config
            base_config.update(user_config)

        except json.JSONDecodeError as e:
            log_warning(f"Invalid config_json, using defaults: {e}")

    return (base_config, layer_configs, include_functions, framing_depth,
            assembly_mode, framing_system, assembly_overrides)


def compute_sheathing_bounds(wall_id, wall_length, face, junctions_data, layer_side=None):
    """Compute U-axis panel bounds from junction adjustments.

    Looks up the junction adjustments for a specific wall and face,
    and returns a list of (u_start, u_end) segments. For walls with no
    midspan gaps, returns a single segment. For walls with midspan gaps
    (T-intersections, X-crossings), returns multiple segments.

    ASSUMPTION: Adjustment 'amount' is measured from the wall's Revit
    centerline endpoint along the U-axis.
    ASSUMPTION: u=0 is the wall's centerline start, u=wall_length is
    the wall's centerline end.

    Args:
        wall_id: Wall identifier.
        wall_length: Original wall length in feet.
        face: Layer side — "exterior", "interior", or "core".
            Must match the ``layer_name`` values emitted by the
            junction resolver.
        junctions_data: Parsed junctions_json dict, or None.
        layer_side: Optional layer side ("exterior", "interior", "core")
            for disambiguating same-named layers on different sides.
            When provided, adjustments that carry a ``layer_side`` field
            must match this value in addition to ``layer_name``.

    Returns:
        list: List of (u_start, u_end) segment tuples in feet.
            Usually a single segment; multiple when midspan gaps exist.
    """
    u_start_bound = 0.0
    u_end_bound = wall_length
    midspan_gaps = []  # List of (gap_center_u, amount_pos, amount_neg)

    if not junctions_data:
        return [(u_start_bound, u_end_bound)]

    # Use face directly as layer_name — the junction resolver emits
    # adjustments keyed by individual layer names OR aggregate face names.
    layer_name = face

    # Get adjustments for this wall
    wall_adjustments = junctions_data.get("wall_adjustments", {}).get(wall_id, [])

    matched_any = False
    for adj in wall_adjustments:
        if adj.get("layer_name") != layer_name:
            continue
        # When both the adjustment and the query carry a layer_side,
        # require them to match.  This disambiguates same-named layers
        # on different sides (e.g., "Gypsum Board" on ext vs int).
        adj_side = adj.get("layer_side")
        if layer_side and adj_side and adj_side != layer_side:
            continue

        matched_any = True
        end = adj.get("end")
        adj_type = adj.get("adjustment_type")
        amount = adj.get("amount", 0.0)

        if end == "midspan":
            # Midspan gap: asymmetric amounts for +U and -U edges.
            # amount = positive-U edge, amount_neg = negative-U edge (defaults to amount).
            gap_u = adj.get("midspan_u", 0.0)
            amount_neg = adj.get("amount_neg")
            if amount_neg is None:
                amount_neg = amount
            midspan_gaps.append((gap_u, amount, amount_neg))
            log_info(
                f"    BOUNDS-APPLY wall={wall_id} layer='{layer_name}' "
                f"end=midspan {adj_type} amount_pos={amount:.6f} amount_neg={amount_neg:.6f} ft "
                f"midspan_u={gap_u:.6f} -> gap at [{gap_u - amount_neg:.6f}, {gap_u + amount:.6f}]"
            )
        elif end == "start":
            if adj_type == "extend":
                u_start_bound = -amount  # Extend before wall start
            elif adj_type == "trim":
                u_start_bound = amount   # Trim after wall start
            log_info(
                f"    BOUNDS-APPLY wall={wall_id} layer='{layer_name}' "
                f"end={end} {adj_type} amount={amount:.6f} ft ({amount*12:.4f} in) "
                f"-> u_start={u_start_bound:.6f} u_end={u_end_bound:.6f} "
                f"(wall_length={wall_length:.6f})"
            )
        elif end == "end":
            if adj_type == "extend":
                u_end_bound = wall_length + amount  # Extend past wall end
            elif adj_type == "trim":
                u_end_bound = wall_length - amount  # Trim before wall end
            log_info(
                f"    BOUNDS-APPLY wall={wall_id} layer='{layer_name}' "
                f"end={end} {adj_type} amount={amount:.6f} ft ({amount*12:.4f} in) "
                f"-> u_start={u_start_bound:.6f} u_end={u_end_bound:.6f} "
                f"(wall_length={wall_length:.6f})"
            )

    if not matched_any and wall_adjustments:
        log_info(
            f"    BOUNDS-APPLY wall={wall_id} layer='{layer_name}': "
            f"NO matching adjustment found among {len(wall_adjustments)} adjustments. "
            f"Available layer_names: {sorted(set(a.get('layer_name') for a in wall_adjustments))}"
        )

    # If no midspan gaps, return the single segment
    if not midspan_gaps:
        return [(u_start_bound, u_end_bound)]

    # Split the single segment into sub-segments around midspan gaps.
    # Sort gaps by U-coordinate.
    midspan_gaps.sort(key=lambda g: g[0])

    segments = []
    current_start = u_start_bound
    for gap_u, gap_amount_pos, gap_amount_neg in midspan_gaps:
        gap_left = gap_u - gap_amount_neg
        gap_right = gap_u + gap_amount_pos
        # Add segment from current_start to gap_left (if positive length)
        if gap_left > current_start + 0.001:
            segments.append((current_start, gap_left))
        current_start = gap_right

    # Add final segment from last gap to u_end_bound
    if u_end_bound > current_start + 0.001:
        segments.append((current_start, u_end_bound))

    log_info(
        f"    BOUNDS-SPLIT wall={wall_id} layer='{layer_name}': "
        f"{len(midspan_gaps)} midspan gaps -> {len(segments)} segments"
    )
    for i, (seg_s, seg_e) in enumerate(segments):
        log_info(
            f"      segment[{i}]: u=[{seg_s:.6f}, {seg_e:.6f}] "
            f"length={seg_e - seg_s:.6f} ft"
        )

    return segments if segments else [(u_start_bound, u_end_bound)]


def parse_panels_json(panels_json_str):
    """Parse panels JSON into wall_id -> panel list mapping.

    Args:
        panels_json_str: JSON string from Panel Decomposer.

    Returns:
        dict: {wall_id: [panel_dict, ...]} sorted by u_start, or empty dict.
    """
    if not panels_json_str or not str(panels_json_str).strip():
        return {}

    try:
        data = json.loads(str(panels_json_str))
    except (json.JSONDecodeError, TypeError):
        log_warning("Invalid panels_json, ignoring")
        return {}

    if not isinstance(data, list):
        return {}

    result = {}
    for wall_result in data:
        if not isinstance(wall_result, dict):
            continue
        wall_id = str(wall_result.get("wall_id", ""))
        panels = wall_result.get("panels", [])
        if wall_id and panels:
            result[wall_id] = sorted(
                panels, key=lambda p: p.get("u_start", 0)
            )

    return result


def _clip_face_bounds(face_bounds, panel_u_start, panel_u_end):
    """Clip face_bounds segments to panel boundaries.

    Args:
        face_bounds: Dict mapping face/layer key -> list of (u_start, u_end) segments.
        panel_u_start: Panel start U coordinate.
        panel_u_end: Panel end U coordinate.

    Returns:
        Clipped face_bounds dict, or None if empty after clipping.
    """
    if not face_bounds:
        return None

    clipped = {}
    for key, segments in face_bounds.items():
        clipped_segs = []
        for seg_start, seg_end in segments:
            clip_start = max(seg_start, panel_u_start)
            clip_end = min(seg_end, panel_u_end)
            if clip_end > clip_start + 0.001:
                clipped_segs.append((clip_start, clip_end))
        if clipped_segs:
            clipped[key] = clipped_segs

    return clipped if clipped else None


def generate_panelized_assembly_layers(
    wall_data, wall_panels, base_config, layer_configs, include_functions,
    face_bounds, framing_depth,
):
    """Generate multi-layer sheathing bounded to framing panel boundaries.

    For each framing panel, calls generate_assembly_layers() with the
    panel's u_start/u_end as bounds and the panel_id set on wall_data.
    Results are merged per-layer so the output structure matches the
    non-panelized path (one layer_result per layer, not per panel).

    Args:
        wall_data: Wall data dict (with wall_assembly).
        wall_panels: List of panel dicts sorted by u_start.
        base_config: Base config for all layers.
        layer_configs: Per-layer config overrides.
        include_functions: Layer function filter, or None.
        face_bounds: Dict of face/layer key -> segments from junction analysis.
        framing_depth: Framing profile depth in feet, or None.

    Returns:
        dict: Same format as generate_assembly_layers() output.
    """
    wall_id = wall_data.get("wall_id", "unknown")
    wall_length = wall_data.get("wall_length", 0)
    num_panels = len(wall_panels)

    # Merged layer_results keyed by "layer_name|layer_side"
    merged = {}
    total_panels = 0

    for panel_idx, panel in enumerate(wall_panels):
        panel_id = panel.get("id", "%s_panel_%d" % (wall_id, panel_idx))
        panel_u_start = panel.get("u_start", 0)
        panel_u_end = panel.get("u_end", wall_length)
        log_info(
            "    Panel %d/%d: id=%s, u=[%.3f, %.3f], length=%.3f ft"
            % (panel_idx + 1, num_panels, panel_id,
               panel_u_start, panel_u_end, panel_u_end - panel_u_start)
        )

        is_first = (panel_idx == 0)
        is_last = (panel_idx == num_panels - 1)

        # Start with panel boundaries
        effective_u_start = panel_u_start
        effective_u_end = panel_u_end

        # Apply junction extensions only at wall edges
        if is_first and face_bounds:
            for segs in face_bounds.values():
                for seg_start, _ in segs:
                    if seg_start < effective_u_start:
                        effective_u_start = seg_start

        if is_last and face_bounds:
            for segs in face_bounds.values():
                for _, seg_end in segs:
                    if seg_end > effective_u_end:
                        effective_u_end = seg_end

        # Clip face_bounds to this panel's range
        panel_face_bounds = _clip_face_bounds(
            face_bounds, effective_u_start, effective_u_end
        )

        # Set panel_id on wall_data copy
        panel_wall_data = dict(wall_data)
        panel_wall_data["panel_id"] = panel_id

        try:
            result = generate_assembly_layers(
                panel_wall_data,
                config=base_config,
                layer_configs=layer_configs if layer_configs else None,
                u_start_bound=effective_u_start,
                u_end_bound=effective_u_end,
                face_bounds=panel_face_bounds,
                include_functions=include_functions,
                framing_depth=framing_depth,
            )
        except TypeError as _te:
            if "framing_depth" in str(_te):
                result = generate_assembly_layers(
                    panel_wall_data,
                    config=base_config,
                    layer_configs=layer_configs if layer_configs else None,
                    u_start_bound=effective_u_start,
                    u_end_bound=effective_u_end,
                    face_bounds=panel_face_bounds,
                    include_functions=include_functions,
                )
            else:
                raise

        # Merge layer_results: concatenate panels per layer
        for lr in result.get("layer_results", []):
            layer_key = "%s|%s" % (
                lr.get("layer_name", "unknown"),
                lr.get("layer_side", "unknown"),
            )
            if layer_key not in merged:
                merged[layer_key] = dict(lr)
                merged[layer_key]["panels"] = list(lr.get("panels", []))
                merged[layer_key]["panel_count"] = lr.get("panel_count", 0)
            else:
                merged[layer_key]["panels"].extend(lr.get("panels", []))
                merged[layer_key]["panel_count"] += lr.get("panel_count", 0)

        total_panels += result.get("total_panel_count", 0)

    log_info(
        "  Wall %s: panelized -> %d framing panels -> %d sheathing panels"
        % (wall_id, num_panels, total_panels)
    )

    out = {
        "wall_id": wall_id,
        "layer_results": list(merged.values()),
        "total_panel_count": total_panels,
        "layers_processed": len(merged),
    }

    # Copy assembly metadata from wall_data
    for key in ("assembly_source", "assembly_confidence", "assembly_notes",
                "assembly_name", "wall_type"):
        if key in wall_data:
            out[key] = wall_data[key]

    return out


def process_walls(walls_json, base_config, layer_configs, include_functions,
                  junctions_data=None, assembly_mode="auto",
                  assembly_overrides=None, framing_system="timber",
                  framing_depth=None, framing_data=None,
                  custom_map=None, panels_by_wall=None):
    """Process walls and generate multi-layer sheathing panels.

    For each wall, resolves the assembly (using the assembly resolver),
    determines faces from config, computes junction bounds per face,
    and calls generate_assembly_layers() to produce panels for all
    panelizable layers.

    Args:
        walls_json: JSON string with wall data.
        base_config: Base configuration dict for all layers.
        layer_configs: Per-layer config overrides keyed by layer name.
        include_functions: List of layer functions to generate, or None for all.
        junctions_data: Optional parsed junctions_json dict.
        assembly_mode: Assembly resolution mode (auto/revit/revit_only/catalog/custom).
        assembly_overrides: Per-Wall-Type assembly mapping dict, applied in ALL modes.
        framing_system: "timber" or "cfs" — determines thickness-to-depth mapping.
        framing_depth: Optional explicit framing profile depth in feet.
            When set, overrides per-wall detection and applies to ALL walls.
        framing_data: Optional parsed framing_json for per-wall depth
            extraction. When provided and framing_depth is None, each wall
            gets its own framing depth from the framing elements matching
            its wall_id.
        custom_map: Deprecated — use assembly_overrides. Kept for backward compat.

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

    # Inject framing_hint into wall dicts for assembly resolution (Option B).
    # When framing_json is connected, each wall gets a hint with its stud
    # profile depth, enabling the resolver to pick the correct assembly
    # (e.g., 2x6_exterior for a 6" wall instead of defaulting to 2x4).
    if framing_data is not None:
        for wall in walls_list:
            wid = str(wall.get("wall_id", ""))
            depth = extract_max_framing_depth(framing_data, wall_id=wid)
            if depth:
                wall["framing_hint"] = {"depth_ft": depth}
                log_info(f"  Injected framing_hint for wall {wid}: depth_ft={depth:.4f}")

    # Resolve assemblies for all walls
    walls_list = resolve_all_walls(
        walls_list, mode=assembly_mode,
        assembly_overrides=assembly_overrides,
        custom_map=custom_map,
        framing_system=framing_system,
    )
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
    panelized_count = 0
    standard_count = 0

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
            # Log wall geometry diagnostic for all walls
            bp = wall_data.get("base_plane", {})
            zax = bp.get("z_axis", {})
            xax = bp.get("x_axis", {})
            log_info(
                f"  base_plane x_axis=({xax.get('x',0):.3f}, "
                f"{xax.get('y',0):.3f}, {xax.get('z',0):.3f}), "
                f"z_axis=({zax.get('x',0):.3f}, "
                f"{zax.get('y',0):.3f}, {zax.get('z',0):.3f})"
            )
            log_info(
                f"  wall_thickness={wall_data.get('wall_thickness', '?')}, "
                f"is_flipped={wall_data.get('is_flipped', '?')}, "
                f"wall_type='{wall_data.get('wall_type', '?')}'"
            )
            log_info(
                f"  +z_axis = 'exterior' face, -z_axis = 'interior' face"
            )

            # Face labels from config. z_axis is set by the Wall Analyzer
            # using Revit's wall.Orientation, so +z = exterior regardless
            # of the wall's is_flipped state.
            faces = base_config.get("faces", ["exterior", "interior"])

            wall_length = wall_data.get("wall_length", 0)

            # Compute junction bounds per individual layer name.
            # The junction resolver now emits per-layer adjustments keyed
            # by the actual layer name (e.g., "OSB Sheathing") when wall
            # assemblies are available, with fallback "exterior"/"core"/
            # "interior" for walls without assemblies.  We compute bounds
            # for every individual layer name AND the aggregate face keys
            # so that generate_assembly_layers() can look up by either.
            face_bounds = {}

            # Diagnostic: show what adjustments exist for this wall
            wall_adjs = (junctions_data or {}).get(
                "wall_adjustments", {}
            ).get(wall_id, [])
            adj_layer_names = set()
            if wall_adjs:
                adj_layer_names = set(a.get("layer_name") for a in wall_adjs)
                log_info(
                    f"  BOUNDS-DIAG wall {wall_id}: {len(wall_adjs)} adjustments, "
                    f"layer_names={sorted(adj_layer_names)}"
                )
            else:
                log_info(f"  BOUNDS-DIAG wall {wall_id}: NO adjustments found")

            # Per-individual-layer bounds (from assembly).
            # Only add when the junction resolver emitted adjustments keyed
            # by that specific layer name (per-layer cumulative path).
            # If only aggregate names (exterior/core/interior) exist, skip
            # individual names so generate_assembly_layers() falls through
            # to the aggregate face keys instead of getting shadowed.
            assembly_layers = (wall_assembly or {}).get("layers", [])
            log_info(
                f"  BOUNDS-DIAG assembly layers: "
                f"{[al.get('name') for al in assembly_layers]}"
            )
            for al in assembly_layers:
                lname = al.get("name")
                lside = al.get("side", "exterior")
                lkey = f"{lname}|{lside}"
                if lname and lname in adj_layer_names:
                    segments = compute_sheathing_bounds(
                        wall_id, wall_length, lname, junctions_data,
                        layer_side=lside,
                    )
                    face_bounds[lkey] = segments
                    log_info(
                        f"  layer '{lname}' (side={lside}, key='{lkey}') bounds: "
                        f"{len(segments)} segment(s) "
                        f"(ADJUSTED, wall_length={wall_length:.4f})"
                    )
                elif lname:
                    log_info(
                        f"  layer '{lname}' (side={lside}): no matching adjustment "
                        f"(will use face fallback)"
                    )

            # Aggregate face-level bounds (fallback for layers not matched by name)
            for bf in set(faces) | {"core"}:
                segments = compute_sheathing_bounds(
                    wall_id, wall_length, bf, junctions_data
                )
                face_bounds[bf] = segments
                seg0 = segments[0] if segments else (0.0, wall_length)
                matched = "ADJUSTED" if (len(segments) != 1 or abs(seg0[0]) > 0.0001 or abs(seg0[1] - wall_length) > 0.0001) else "unchanged"
                log_info(
                    f"  face '{bf}' bounds: {len(segments)} segment(s) "
                    f"({matched}, wall_length={wall_length:.4f})"
                )

            log_info(f"  BOUNDS-DIAG final face_bounds keys: {sorted(face_bounds.keys())}")
            log_info(f"  BOUNDS-DIAG final face_bounds values:")
            for bk, bv in sorted(face_bounds.items()):
                for si, (u_s, u_e) in enumerate(bv):
                    changed_start = "ADJUSTED" if abs(u_s) > 0.0001 else "default"
                    changed_end = "ADJUSTED" if abs(u_e - wall_length) > 0.0001 else "default"
                    seg_label = f"[{si}]" if len(bv) > 1 else ""
                    log_info(
                        f"    '{bk}'{seg_label}: u_start={u_s:.6f} ({changed_start}), "
                        f"u_end={u_e:.6f} ({changed_end}), "
                        f"effective_length={u_e - u_s:.6f} ft ({(u_e - u_s)*12:.4f} in)"
                    )

            # Resolve per-wall framing depth.
            # Explicit framing_depth (from config) overrides per-wall detection.
            # Otherwise, extract from framing_json filtered by this wall's ID.
            wall_framing_depth = framing_depth
            if wall_framing_depth is None and framing_data is not None:
                wall_framing_depth = extract_max_framing_depth(
                    framing_data, wall_id=wall_id,
                )
                if wall_framing_depth is not None:
                    log_info(
                        f"  framing_depth={wall_framing_depth:.4f} ft "
                        f"({wall_framing_depth * 12:.2f} in) for wall {wall_id}"
                    )

            # Check if this wall has framing panels for panel-bounded sheathing
            wall_panels = panels_by_wall.get(str(wall_id)) if panels_by_wall else None

            # Fallback: embedded panels in wall_data (from enriched walls_json)
            if not wall_panels:
                embedded = wall_data.get("panels")
                if embedded and isinstance(embedded, list) and len(embedded) > 0:
                    wall_panels = sorted(embedded, key=lambda p: p.get("u_start", 0))
                    log_info("  Wall %s: using EMBEDDED panels (%d panels)" % (wall_id, len(wall_panels)))

            if wall_panels:
                # Panel-aware path: generate sheathing bounded to each
                # framing panel so sheets don't cross panel joints.
                panelized_count += 1
                log_info(
                    f"  Wall {wall_id}: PANELIZED path "
                    f"({len(wall_panels)} framing panels)"
                )
                result = generate_panelized_assembly_layers(
                    wall_data, wall_panels, base_config, layer_configs,
                    include_functions, face_bounds, wall_framing_depth,
                )
            else:
                standard_count += 1
                if panels_by_wall:
                    log_info(
                        "  Wall %s: STANDARD path (no panel match; "
                        "available panel wall_ids: %s)"
                        % (wall_id, sorted(panels_by_wall.keys()))
                    )
                else:
                    log_info("  Wall %s: STANDARD path (no panels data)" % wall_id)
                # Standard path: generate sheathing for the full wall
                try:
                    result = generate_assembly_layers(
                        wall_data,
                        config=base_config,
                        layer_configs=layer_configs if layer_configs else None,
                        face_bounds=face_bounds if face_bounds else None,
                        include_functions=include_functions,
                        framing_depth=wall_framing_depth,
                    )
                except TypeError as _te:
                    # Fallback: if an older version of multi_layer_generator is
                    # loaded (missing framing_depth param), retry without it.
                    if "framing_depth" in str(_te):
                        log_warning(
                            f"Wall {wall_id}: stale module lacks framing_depth "
                            f"param -- falling back (restart Rhino to fix)"
                        )
                        result = generate_assembly_layers(
                            wall_data,
                            config=base_config,
                            layer_configs=layer_configs if layer_configs else None,
                            face_bounds=face_bounds if face_bounds else None,
                            include_functions=include_functions,
                        )
                    else:
                        raise

            all_results.append(result)
            walls_processed += 1

            # W offset diagnostic: log per-layer W positions for first 2 walls
            if walls_processed <= 2:
                layer_results_diag = result.get("layer_results", [])
                core_t = sum(
                    l.get("thickness", 0)
                    for l in wall_assembly.get("layers", [])
                    if l.get("side") == "core"
                )
                log_info(
                    f"  W-DIAG wall {wall_id}: core_t={core_t:.4f}, "
                    f"core_half={core_t/2:.4f}"
                )
                for lr in layer_results_diag:
                    w_off = lr.get("w_offset")
                    panels_list = lr.get("panels", [])
                    first_u = panels_list[0].get("u_start", "?") if panels_list else "N/A"
                    last_u = panels_list[-1].get("u_end", "?") if panels_list else "N/A"
                    log_info(
                        f"    {lr.get('layer_name')}: w_offset={w_off}, "
                        f"side={lr.get('layer_side')}, "
                        f"panels={lr.get('panel_count', 0)}, "
                        f"first_u_start={first_u}, last_u_end={last_u}"
                    )

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
        f"Walls Processed: {walls_processed}/{len(walls_list)}\n"
        f"Panelization: {panelized_count}/{walls_processed} walls panel-bounded, "
        f"{standard_count} standard"
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
         framing_json_in=None, panels_json_in=None):
    """Main entry point for the component.

    Orchestrates the multi-layer sheathing generation workflow:
    1. Sets up component metadata
    2. Validates inputs
    3. Parses configuration (assembly_mode, framing_system, assembly_overrides,
       base config, layer overrides, function filter)
    4. Parses optional junction data
    5. Auto-detects framing depth from framing_json (if connected)
    6. Parses optional panels_json for panel-bounded sheathing
    7. Resolves assemblies for all walls
    8. Processes all walls
    9. Returns JSON results, summary, stats, and log

    Args:
        walls_json_in: JSON string from Wall Analyzer.
        junctions_json_in: Optional JSON from Junction Analyzer.
        config_json_in: Configuration JSON from Config Builder (or manual).
            Contains assembly_mode, framing_system, assembly_overrides,
            faces, panel_size, include_functions, layer_configs, etc.
        run_in: Boolean to trigger execution.
        framing_json_in: Optional JSON from Framing Generator. When
            connected, the maximum profile depth is extracted and used
            as framing_depth to prevent sheathing from overlapping
            oversized framing (e.g., CFS profiles on a timber wall type).
        panels_json_in: Optional JSON from Panel Decomposer. When
            connected, sheathing is generated per framing panel so
            sheets don't cross panel joints.

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

        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json_input, run_input)
        if not is_valid:
            log_info(error_msg)
            return "", error_msg, "", error_msg

        # Parse configuration (now includes assembly_mode, framing_system, overrides)
        (base_config, layer_configs, include_functions, framing_depth,
         assembly_mode, framing_system, assembly_overrides) = parse_config(
            config_json_input
        )

        # Parse framing_json for per-wall framing depth extraction.
        # When an explicit framing_depth is set via config_json, it overrides
        # per-wall detection and applies to ALL walls uniformly.
        framing_data = None
        if framing_json_in and str(framing_json_in).strip():
            try:
                framing_data = json.loads(framing_json_in)
                if framing_depth is not None:
                    log_info(
                        f"Explicit framing_depth={framing_depth:.4f} ft from config "
                        f"(overrides per-wall detection from framing_json)"
                    )
                else:
                    # Quick log: show global max for reference
                    global_max = extract_max_framing_depth(framing_data)
                    log_info(
                        f"framing_json loaded — per-wall depth extraction active "
                        f"(global max={global_max:.4f} ft / {global_max * 12:.2f} in)"
                        if global_max else "framing_json loaded (no elements found)"
                    )
            except (json.JSONDecodeError, TypeError) as e:
                log_warning(f"Invalid framing_json, ignoring: {e}")

        # Parse junctions data (optional)
        junctions_data = None
        if junctions_json_input and str(junctions_json_input).strip():
            try:
                junctions_data = json.loads(junctions_json_input)
                junc_count = junctions_data.get("junction_count", 0)
                wall_adj_map = junctions_data.get("wall_adjustments", {})
                adj_count = sum(len(adjs) for adjs in wall_adj_map.values())
                log_info(
                    f"Loaded junction data (Phase 1): {junc_count} junctions, "
                    f"{adj_count} best-effort adjustments across {len(wall_adj_map)} walls"
                )
            except (json.JSONDecodeError, TypeError) as e:
                log_warning(f"Invalid junctions_json, ignoring: {e}")

        # Phase 2: Recompute junction adjustments with resolved assemblies.
        # The Junction Analyzer runs on raw Revit walls (Phase 1) and may
        # only have single-core-layer data. After assembly resolution,
        # we recompute adjustments with the real multi-layer assemblies.
        phase2_log = []  # Captured for visible log output
        if junctions_data and junctions_data.get("resolutions"):
            try:
                # Parse walls for assembly resolution
                walls_for_recompute = json.loads(walls_json_input)
                if isinstance(walls_for_recompute, dict):
                    walls_for_recompute = [walls_for_recompute]

                # z_axis already set by Wall Analyzer (wall.Orientation),
                # no flip correction needed for Phase 2 recompute.

                # Inject framing_hint for correct assembly resolution
                if framing_data is not None:
                    for wall in walls_for_recompute:
                        wid = str(wall.get("wall_id", ""))
                        depth = extract_max_framing_depth(framing_data, wall_id=wid)
                        if depth:
                            wall["framing_hint"] = {"depth_ft": depth}

                # Resolve assemblies on a copy for recompute
                walls_for_recompute = resolve_all_walls(
                    walls_for_recompute, mode=assembly_mode,
                    assembly_overrides=assembly_overrides,
                    framing_system=framing_system,
                )

                recomputed = recompute_adjustments(junctions_data, walls_for_recompute)

                old_count = sum(
                    len(v) for v in junctions_data.get("wall_adjustments", {}).values()
                )
                new_count = sum(len(v) for v in recomputed.values())
                junctions_data["wall_adjustments"] = recomputed

                phase2_msg = (
                    f"Phase 2 recompute: {old_count} -> {new_count} adjustments"
                )
                log_info(phase2_msg)
                phase2_log.append(f"=== PHASE 2 RECOMPUTE (resolver v2.3-crossed-pattern) ===")
                phase2_log.append(phase2_msg)

                # Diagnostic: dump recomputed adjustments (console + log)
                for wid, adjs in recomputed.items():
                    log_info(f"  RECOMPUTED wall {wid}: {len(adjs)} adjustments")
                    phase2_log.append(f"  Wall {wid}: {len(adjs)} adjustments")
                    for adj in adjs:
                        adj_line = (
                            f"    {adj.get('layer_name')} "
                            f"[{adj.get('end')}] "
                            f"{adj.get('adjustment_type').upper()} "
                            f"{adj.get('amount', 0):.6f} ft "
                            f"({adj.get('amount', 0) * 12:.4f} in) "
                            f"vs {adj.get('connecting_wall_id')}"
                        )
                        log_info(adj_line)
                        phase2_log.append(adj_line)
            except Exception as e:
                log_warning(
                    f"Phase 2 recompute failed, using Phase 1 adjustments: {e}"
                )
                phase2_log.append(f"Phase 2 FAILED: {e}")
                import traceback as _tb
                print(_tb.format_exc())
        elif junctions_data:
            phase2_log.append(
                "No resolutions in junctions_json (old format?) — "
                "using Phase 1 adjustments as-is"
            )
            log_info(phase2_log[-1])

        # Parse panels_json for panel-bounded sheathing (optional)
        panels_by_wall = parse_panels_json(panels_json_in)
        if panels_by_wall:
            total_fpanels = sum(len(v) for v in panels_by_wall.values())
            log_info(
                f"Panel-bounded mode: {total_fpanels} framing panels "
                f"across {len(panels_by_wall)} walls"
            )
            # Check wall_id match between panels_json and walls_json
            try:
                _walls_tmp = json.loads(walls_json_input)
                if isinstance(_walls_tmp, dict):
                    _walls_tmp = [_walls_tmp]
                _wall_ids = set(str(w.get("wall_id", "")) for w in _walls_tmp)
                _panel_ids = set(panels_by_wall.keys())
                _matched = _wall_ids & _panel_ids
                log_info("  Panel wall_ids: %s" % sorted(_panel_ids))
                log_info("  Walls wall_ids: %s" % sorted(_wall_ids))
                log_info("  Matched: %d/%d walls" % (len(_matched), len(_wall_ids)))
                _unmatched = _panel_ids - _wall_ids
                if _unmatched:
                    log_warning(
                        "  panels_json has %d wall_ids not in walls_json: %s"
                        % (len(_unmatched), sorted(_unmatched)))
            except Exception:
                pass
        elif panels_json_in and str(panels_json_in).strip():
            log_info(
                "panels_json was provided but parse_panels_json returned empty "
                "- check JSON format (expected list of {wall_id, panels: [...]})")
        else:
            log_info("No panels_json provided - standard full-wall mode")

        # Process walls
        results, summary_lines, stats_text, log_lines = process_walls(
            walls_json_input, base_config, layer_configs, include_functions,
            junctions_data, assembly_mode=assembly_mode,
            assembly_overrides=assembly_overrides,
            framing_system=framing_system,
            framing_depth=framing_depth, framing_data=framing_data,
            panels_by_wall=panels_by_wall if panels_by_wall else None,
        )

        # Prepend Phase 2 recompute log to visible output
        if phase2_log:
            log_lines = phase2_log + [""] + log_lines

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
        "[framing_json], [panels_json], run"
        % _input_count
    )
    print(_msg)
    multi_layer_json = ""
    layer_summary = _msg
    stats = ""
    log = _msg
else:
    # Input order: data inputs first, run toggle last.
    # v2.2: assembly_mode and custom_map removed as standalone inputs;
    # now read from config_json (via Config Builder component).
    _walls_json = _read_input(0)       # walls_json
    _junctions_json = _read_input(1)   # junctions_json
    _config_json = _read_input(2)      # config_json
    _framing_json = _read_input(3)     # framing_json (optional)
    # panels_json is at index 4 only when component has 6+ inputs.
    # If component has 5 inputs, panels_json slot doesn't exist.
    # To enable panel-bounded sheathing, user must add a 6th input via
    # ZUI (right-click component -> + icon) and reconnect panels_json.
    _panels_json = _read_input(4) if _input_count >= 6 else None
    if _input_count < 6:
        print(
            "[MLSheath] NOTE: Component has %d inputs (no panels_json slot). "
            "Panel-bounded sheathing is DISABLED. To enable: "
            "right-click component ZUI -> add input for panels_json "
            "at index 4 (before run), then reconnect from Panel Decomposer."
            % _input_count
        )
    _run_index = _input_count - 1      # run is always last
    _run = bool(_read_input(_run_index, False))

    # Panelization diagnostics
    print("[MLSheath] PANELIZATION DIAGNOSTICS:")
    print("  Input count: %d (need 6+ for panels_json input)" % _input_count)
    print("  panels_json received: %s" % ("YES (%d chars)" % len(str(_panels_json)) if _panels_json else "NO"))

    multi_layer_json, layer_summary, stats, log = main(
        _walls_json, _junctions_json, _config_json, _run,
        _framing_json, _panels_json,
    )
