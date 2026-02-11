# File: scripts/gh_framing_generator.py
"""Framing Generator for Grasshopper.

Generates framing elements using the strategy pattern based on material type.
Outputs JSON data (no geometry) for downstream geometry conversion. Supports
multiple material systems through a modular strategy architecture.

Reads segment metadata from Cell Decomposer (``segment_u_start``,
``segment_u_end``) and injects ``_segment_bounds`` into wall data so that
the WBC (Wall Boundary Cell) is built at the correct junction-adjusted U
range. This propagates extend/trim/split adjustments into plates, studs,
and all framing elements.

Key Features:
1. Multi-Material Support
   - Timber framing (2x4, 2x6, etc.)
   - CFS (Cold-Formed Steel) framing
   - Extensible strategy pattern for new materials

2. Element Generation
   - Studs, plates, headers, sills
   - King studs and trimmers at openings
   - Cripple studs above/below openings
   - End studs at wall and panel boundaries

3. Junction-Aware Framing
   - Reads segment bounds from cell_data metadata
   - Injects _segment_bounds into wall data for WBC construction
   - Framing elements correctly extend/trim at L-corners and T-intersections
   - Multi-segment walls (X-crossings) produce independent framing runs

4. Panel-Aware Framing
   - Passes panel_id through element metadata
   - Supports panelization-before-framing workflow
   - Enables per-panel framing for prefab construction

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry types
    - Grasshopper: Component framework
    - timber_framing_generator.core: Strategy pattern, JSON schemas
    - timber_framing_generator.materials: Material strategies

Performance Considerations:
    - Processing time scales linearly with cell count
    - Memory usage proportional to element count
    - JSON serialization is the bottleneck for large walls

Usage:
    1. Connect 'cell_json' from Cell Decomposer
    2. Connect 'walls_json' from Wall Analyzer (or Junction Analyzer enriched)
    3. Set 'material_type' to "timber" or "cfs"
    4. Set 'run' to True to execute
    5. Connect 'framing_json' to Geometry Converter component

Input Requirements:
    Cell JSON (cell_json) - str:
        JSON string from Cell Decomposer with cell decomposition data.
        May include segment metadata (segment_u_start, segment_u_end) from
        junction-adjusted framing segments.
        Required: Yes
        Access: Item

    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer with wall geometry reference
        Required: Yes
        Access: Item

    Material Type (material_type) - str:
        Material system to use ("timber" or "cfs")
        Required: No (defaults to "timber")
        Access: Item

    Config JSON (config_json) - str:
        Optional JSON string with configuration overrides
        Required: No
        Access: Item

    Panels JSON (panels_json) - str:
        Optional JSON string from Panel Decomposer for panel-aware framing.
        When provided, elements get panel_id metadata for prefab workflows.
        Required: No
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Framing JSON (framing_json) - str:
        JSON string containing all framing elements for Geometry Converter

    Element Count (element_count) - dict:
        Dictionary of element counts by type

    Generation Log (generation_log) - str:
        Detailed generation log with debug information

Technical Details:
    - Uses Strategy Pattern for material-specific generation
    - Elements stored as centerline + profile (no geometry)
    - Geometry created in separate Geometry Converter component
    - Panel_id passed through metadata for traceability
    - Segment bounds from cell metadata override WBC [0, wall_length] range

Error Handling:
    - Invalid JSON returns empty results with error in log
    - Unknown material type defaults to timber with warning
    - Missing cells logged but don't halt execution
    - Missing segment metadata falls back to full wall range (backward compatible)

Author: Timber Framing Generator
Version: 1.2.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import sys
import json
import traceback
from dataclasses import asdict
from io import StringIO

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

# Clear timber_framing_generator modules AND the 'src' package itself.
# Other GH components may have already imported 'src', caching its
# __path__ to the main repo.  Clearing it forces Python to re-resolve
# 'src' from the updated sys.path (worktree at index 0).
_modules_to_clear = [k for k in sys.modules.keys()
                     if 'timber_framing_generator' in k
                     or k == 'src']
for mod in _modules_to_clear:
    del sys.modules[mod]

# =============================================================================
# Project Setup
# =============================================================================

# Primary: worktree / feature-branch path (contains element_adapters fixes, etc.)
# Fallback: main repo path (for modules not yet in the worktree)
_WORKTREE_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\tfg-sheathing-junctions"
_MAIN_REPO_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Ensure worktree path has highest priority (index 0) in sys.path.
for _p in (_WORKTREE_PATH, _MAIN_REPO_PATH):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _MAIN_REPO_PATH)
sys.path.insert(0, _WORKTREE_PATH)

# Import materials module to trigger strategy registration
# Import material strategies to trigger registration.
# Both timber and cfs are imported so the strategy is available
# regardless of which framing_system the Config Builder sets.
from src.timber_framing_generator.materials import timber  # noqa: F401
try:
    from src.timber_framing_generator.materials import cfs  # noqa: F401
except ImportError:
    pass  # CFS module may not exist yet

from src.timber_framing_generator.core.material_system import (
    MaterialSystem, get_framing_strategy, list_available_materials
)
from src.timber_framing_generator.core.json_schemas import (
    FramingResults, FramingElementData, ProfileData, Point3D, Vector3D,
    deserialize_cell_data, FramingJSONEncoder
)
from src.timber_framing_generator.panels.panel_decomposer import (
    assign_panel_ids_to_elements,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Framing Generator"
COMPONENT_NICKNAME = "FrameGen"
COMPONENT_MESSAGE = "v1.2"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Framing"

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

    Configures:
    1. Component metadata (name, category, etc.)
    2. Input parameter names, descriptions, and access
    3. Output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input → Type hint → Select type
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # NOTE: Type Hints must be set via GH UI (right-click → Type hint)
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Cell JSON", "cell_json", "JSON string from Cell Decomposer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls JSON", "walls_json", "JSON string from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Material Type", "material_type", "Material system: 'timber' or 'cfs' (default: timber)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json", "Optional configuration overrides",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Panels JSON", "panels_json", "Optional panels JSON from Panel Decomposer for panel-aware framing",
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
        ("Framing JSON", "framing_json", "JSON string containing all framing elements"),
        ("Element Count", "element_count", "Dictionary of element counts by type"),
        ("Generation Log", "generation_log", "Detailed generation log"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc

# =============================================================================
# Parameter Reading Helpers (read by index, not NickName globals)
# =============================================================================

def _get_first_branch(param):
    """Get the first branch of data from a GH parameter's VolatileData.

    Handles both typed (GH_Structure[GH_String]) and untyped
    (GH_Structure[IGH_Goo]) parameters.

    Args:
        param: A GH input parameter object

    Returns:
        List-like branch data, or None if empty
    """
    data = param.VolatileData

    # Try .Branch(0) first (works for typed parameters)
    if hasattr(data, 'Branch'):
        try:
            return data.Branch(0)
        except Exception:
            pass

    # Try get_Branch (pythonnet explicit getter)
    if hasattr(data, 'get_Branch'):
        try:
            return data.get_Branch(0)
        except Exception:
            pass

    # Fallback: iterate Branches property
    if hasattr(data, 'Branches'):
        try:
            branches = list(data.Branches)
            if branches:
                return branches[0]
        except Exception:
            pass

    # Last resort: AllData gives flat list of all items
    if hasattr(data, 'AllData'):
        try:
            return data.AllData(True)
        except Exception:
            pass

    return None


def _read_string_input(inputs, index):
    """Read a string value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index

    Returns:
        str or None if input is empty or missing
    """
    if index >= inputs.Count:
        return None
    if inputs[index].VolatileDataCount == 0:
        return None
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return None
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return None
    return str(val)


def _read_bool_input(inputs, index, default=False):
    """Read a boolean value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index
        default: Default value if input is empty

    Returns:
        bool
    """
    if index >= inputs.Count:
        return default
    if inputs[index].VolatileDataCount == 0:
        return default
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return default
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return default
    return bool(val)


# =============================================================================
# Helper Functions
# =============================================================================

def validate_inputs(cell_json, walls_json, run):
    """Validate component inputs.

    Args:
        cell_json: JSON string with cell data
        walls_json: JSON string with wall data
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not cell_json:
        return False, "No cell_json input provided"

    if not walls_json:
        return False, "No walls_json input provided"

    try:
        json.loads(cell_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in cell_json: {e}"

    try:
        json.loads(walls_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


def get_material_system(material_type_str):
    """Convert material type string to MaterialSystem enum.

    Args:
        material_type_str: "timber" or "cfs"

    Returns:
        MaterialSystem enum value

    Raises:
        ValueError: If material type is not recognized
    """
    material_map = {
        "timber": MaterialSystem.TIMBER,
        "cfs": MaterialSystem.CFS,
    }

    material_lower = material_type_str.lower().strip() if material_type_str else "timber"
    if material_lower not in material_map:
        available = list(material_map.keys())
        raise ValueError(f"Unknown material type: {material_type_str}. Available: {available}")

    return material_map[material_lower]


def generate_framing_for_wall(cell_data_dict, wall_data_dict, strategy, config,
                              panels=None):
    """Generate framing elements for a single wall using the strategy.

    Args:
        cell_data_dict: Cell decomposition data for this wall
        wall_data_dict: Wall data for this wall
        strategy: FramingStrategy instance
        config: Configuration parameters
        panels: Optional list of panel dicts (with 'id', 'u_start', 'u_end')
                for panel-aware framing and panel_id assignment

    Returns:
        Tuple of (list of FramingElementData, generation log lines)
    """
    log_lines = []
    elements = []

    wall_id = cell_data_dict.get('wall_id', 'unknown')
    log_lines.append(f"Generating framing for wall {wall_id}")
    log_lines.append(f"  Material: {strategy.material_system.value}")
    log_lines.append(f"  Cells: {len(cell_data_dict.get('cells', []))}")
    if panels:
        log_lines.append(f"  Panels: {len(panels)}")

    # Capture stdout to include debug output
    old_stdout = sys.stdout
    captured_output = StringIO()
    try:
        sys.stdout = captured_output

        framing_elements = strategy.generate_framing(
            wall_data=wall_data_dict,
            cell_data=cell_data_dict,
            config=config
        )

        # Extract wall direction from wall_data_dict for geometry reconstruction
        wall_x_axis = None
        wall_z_axis = None
        if wall_data_dict and 'base_plane' in wall_data_dict:
            base_plane = wall_data_dict['base_plane']
            if 'x_axis' in base_plane:
                x_axis = base_plane['x_axis']
                wall_x_axis = (x_axis['x'], x_axis['y'], x_axis['z'])
            if 'z_axis' in base_plane:
                z_axis = base_plane['z_axis']
                wall_z_axis = (z_axis['x'], z_axis['y'], z_axis['z'])

        for elem in framing_elements:
            # Build element metadata with wall_id and wall direction
            elem_metadata = dict(elem.metadata) if elem.metadata else {}
            elem_metadata['wall_id'] = wall_id
            if wall_x_axis:
                elem_metadata['wall_x_axis'] = wall_x_axis
            if wall_z_axis:
                elem_metadata['wall_z_axis'] = wall_z_axis

            elem_data = FramingElementData(
                id=elem.id,
                element_type=elem.element_type.value,
                profile=ProfileData(
                    name=elem.profile.name,
                    width=elem.profile.width,
                    depth=elem.profile.depth,
                    material_system=elem.profile.material_system.value,
                    properties=elem.profile.properties,
                ),
                centerline_start=Point3D(*elem.centerline_start),
                centerline_end=Point3D(*elem.centerline_end),
                u_coord=elem.u_coord,
                v_start=elem.v_start,
                v_end=elem.v_end,
                cell_id=elem.cell_id,
                panel_id=None,  # Assigned later by assign_panel_ids_to_elements
                metadata=elem_metadata,
            )
            elements.append(elem_data)

        # Assign panel_id to elements if panels are provided
        if panels:
            # Convert FramingElementData objects to dicts for assignment
            elem_dicts = [
                {"u_coord": e.u_coord, "index": i}
                for i, e in enumerate(elements)
            ]
            assign_panel_ids_to_elements(elem_dicts, panels)
            for ed in elem_dicts:
                elements[ed["index"]].panel_id = ed.get("panel_id")
            assigned_count = sum(1 for e in elements if e.panel_id is not None)
            log_lines.append(f"  Panel IDs assigned: {assigned_count}/{len(elements)}")

        log_lines.append(f"  Generated: {len(elements)} elements")

    except Exception as e:
        log_lines.append(f"  ERROR: {str(e)}")
        log_lines.append(traceback.format_exc())

    finally:
        sys.stdout = old_stdout
        debug_output = captured_output.getvalue()
        if debug_output.strip():
            log_lines.append("--- DEBUG OUTPUT ---")
            log_lines.append(debug_output.strip())
            log_lines.append("--- END DEBUG ---")

    return elements, log_lines


def compute_effective_segment_bounds(
    panel_start: "float | None",
    panel_end: "float | None",
    seg_start: "float | None",
    seg_end: "float | None",
    wall_length: float,
    tolerance: float = 0.01,
) -> "tuple[float, float] | None":
    """Compute effective _segment_bounds for a cell/panel.

    In **panel mode** (panel_start/panel_end present), plates are bounded by
    panel edges.  Junction adjustments (seg_start/seg_end) only apply at the
    wall's own endpoints — i.e. the first panel inherits seg_start if its
    panel_start is near 0, and the last panel inherits seg_end if its
    panel_end is near wall_length.

    In **segment mode** (no panel bounds), the raw junction-adjusted segment
    bounds are used directly.

    Args:
        panel_start: Panel U-start from metadata (None if not panel mode).
        panel_end: Panel U-end from metadata (None if not panel mode).
        seg_start: Junction-adjusted segment U-start from metadata.
        seg_end: Junction-adjusted segment U-end from metadata.
        wall_length: Full wall length for endpoint comparison.
        tolerance: How close to 0 / wall_length counts as "at wall endpoint".

    Returns:
        (eff_start, eff_end) tuple, or None if no bounds to inject.
    """
    if panel_start is not None and panel_end is not None:
        # Panel mode: plates bounded by panel edges
        eff_start = panel_start
        eff_end = panel_end
        # First panel inherits junction extension at wall start
        if seg_start is not None and panel_start <= tolerance:
            eff_start = seg_start
        # Last panel inherits junction extension at wall end
        if seg_end is not None and panel_end >= wall_length - tolerance:
            eff_end = seg_end
        return (eff_start, eff_end)
    elif seg_start is not None and seg_end is not None:
        # Segment mode (no panels): junction-adjusted bounds
        return (seg_start, seg_end)
    return None


def process_framing(cell_list, wall_lookup, strategy, config,
                    panels_by_wall=None):
    """Process all walls through the framing generator.

    Args:
        cell_list: List of cell data dictionaries
        wall_lookup: Dictionary mapping wall_id to wall data
        strategy: FramingStrategy instance
        config: Configuration parameters
        panels_by_wall: Optional dict mapping wall_id to list of panel dicts

    Returns:
        Tuple of (all_elements, type_counts, log_lines)
    """
    log_lines = []
    all_elements = []
    type_counts = {}

    # In panel mode, each wall produces multiple cell_data entries (one per
    # panel).  Each call to generate_framing_for_wall() starts element-ID
    # counters at 0, so "stud_0" would appear once per panel.  Prefix IDs
    # with "p{N}_" to make them unique per wall.
    # Pre-scan to find walls that appear more than once in cell_list.
    wall_entry_counts = {}
    for cd in cell_list:
        wid = cd.get('wall_id', '')
        wall_entry_counts[wid] = wall_entry_counts.get(wid, 0) + 1
    wall_call_counter = {}

    for i, cell_data_dict in enumerate(cell_list):
        wall_id = cell_data_dict.get('wall_id', f'wall_{i}')
        wall_data_dict = wall_lookup.get(wall_id, {})

        # Inject segment bounds from cell metadata so that
        # reconstruct_wall_data() builds the WBC at the correct
        # framing U range (junction-adjusted, not raw wall_length).
        # In panel mode, plates are bounded by panel edges with
        # junction adjustments only at the wall's own endpoints.
        meta = cell_data_dict.get('metadata', {})
        wall_length = wall_data_dict.get('wall_length', 0)
        bounds = compute_effective_segment_bounds(
            panel_start=meta.get('panel_u_start'),
            panel_end=meta.get('panel_u_end'),
            seg_start=meta.get('segment_u_start'),
            seg_end=meta.get('segment_u_end'),
            wall_length=wall_length,
        )
        if bounds is not None:
            wall_data_dict = dict(wall_data_dict)  # shallow copy
            wall_data_dict['_segment_bounds'] = list(bounds)

        # Get panels for this wall if available
        wall_panels = None
        if panels_by_wall:
            wall_panels = panels_by_wall.get(wall_id)

        elements, wall_log = generate_framing_for_wall(
            cell_data_dict, wall_data_dict, strategy, config,
            panels=wall_panels,
        )

        # Make element IDs unique when a wall has multiple cell_data entries
        # (panel mode).  Each call generates IDs from 0 (stud_0, top_plate_0,
        # etc.) so without a prefix the same ID appears in multiple panels,
        # causing the baking element_index to overwrite and multiple panels
        # to resolve to the same Revit ElementId.
        panel_idx = wall_call_counter.get(wall_id, 0)
        wall_call_counter[wall_id] = panel_idx + 1
        if wall_entry_counts.get(wall_id, 1) > 1:
            for elem in elements:
                elem.id = "p%d_%s" % (panel_idx, elem.id)

        all_elements.extend(elements)
        log_lines.extend(wall_log)

        # Count by type
        for elem in elements:
            elem_type = elem.element_type
            type_counts[elem_type] = type_counts.get(elem_type, 0) + 1

    return all_elements, type_counts, log_lines

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Returns:
        tuple: (framing_json, element_count, generation_log)
    """
    # -----------------------------------------------------------------
    # Read inputs by parameter index (CRITICAL: NickName injection is unreliable)
    # -----------------------------------------------------------------
    inputs = ghenv.Component.Params.Input

    cell_json_input = _read_string_input(inputs, 0)
    walls_json_input = _read_string_input(inputs, 1)
    material_type_input = _read_string_input(inputs, 2)
    config_json_input = _read_string_input(inputs, 3)
    panels_json_input = _read_string_input(inputs, 4)
    run_val = _read_bool_input(inputs, 5, default=False)

    # -----------------------------------------------------------------
    # Setup component metadata (display only, AFTER inputs are captured)
    # -----------------------------------------------------------------
    setup_component()

    # Initialize outputs
    framing_json = "{}"
    element_count = {}
    log_lines = []

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs(cell_json_input, walls_json_input, run_val)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            return framing_json, element_count, error_msg

        # Parse inputs (config must be parsed BEFORE framing_system extraction)
        cell_list = json.loads(cell_json_input)
        wall_list = json.loads(walls_json_input)
        wall_lookup = {w.get('wall_id'): w for w in wall_list}
        config = json.loads(config_json_input) if config_json_input else {}

        # Get material system -- framing_system from config_json overrides material_type input
        framing_system = config.get("framing_system")
        if framing_system and framing_system.strip():
            material_type_val = framing_system.strip().lower()
            log_info(f"Using framing_system from config_json: {material_type_val}")
        else:
            material_type_val = material_type_input if material_type_input else "timber"
        material_system = get_material_system(material_type_val)

        # Check if strategy is available
        available = list_available_materials()
        if material_system not in available:
            error_msg = (
                f"Strategy for {material_type_val} not available.\n"
                f"Available: {[m.value for m in available]}"
            )
            log_error(error_msg)
            return framing_json, element_count, error_msg

        strategy = get_framing_strategy(material_system)

        # Parse optional panels_json input
        panels_by_wall = None
        if panels_json_input:
            try:
                panels_list = json.loads(panels_json_input)
                # panels_list is a list of PanelResults dicts, one per wall
                # Build lookup: wall_id -> list of panel dicts
                panels_by_wall = {}
                for panel_result in panels_list:
                    wid = panel_result.get("wall_id", "")
                    panels_by_wall[wid] = panel_result.get("panels", [])
                log_lines.append(f"Panels loaded: {len(panels_by_wall)} walls with panels")
            except (json.JSONDecodeError, TypeError) as e:
                log_lines.append(f"WARNING: Could not parse panels_json: {e}")

        log_lines.append(f"Framing Generator v1.2")
        log_lines.append(f"Material System: {material_type_val}")
        log_lines.append(f"Walls to process: {len(cell_list)}")
        log_lines.append(f"Strategy: {strategy.__class__.__name__}")
        log_lines.append("")

        # Process framing
        all_elements, type_counts, process_log = process_framing(
            cell_list, wall_lookup, strategy, config,
            panels_by_wall=panels_by_wall,
        )
        log_lines.extend(process_log)

        # Create results object
        results = FramingResults(
            wall_id="all_walls",
            material_system=material_type_val,
            elements=all_elements,
            element_counts=type_counts,
            metadata={
                'total_walls': len(cell_list),
                'total_elements': len(all_elements),
            }
        )

        # Serialize to JSON
        framing_json = json.dumps(asdict(results), cls=FramingJSONEncoder, indent=2)
        element_count = type_counts

        log_lines.append("")
        log_lines.append(f"Summary:")
        log_lines.append(f"  Total elements: {len(all_elements)}")
        for elem_type, count in sorted(type_counts.items()):
            log_lines.append(f"  {elem_type}: {count}")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_lines.append(f"ERROR: {str(e)}")
        log_lines.append(traceback.format_exc())

    return framing_json, element_count, "\n".join(log_lines)

# =============================================================================
# Execution
# =============================================================================

# All inputs are read by parameter index inside main() — no NickName globals needed.
if __name__ == "__main__":
    framing_json, element_count, generation_log = main()
