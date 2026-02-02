# File: scripts/gh_framing_generator.py
"""Framing Generator for Grasshopper.

Generates framing elements using the strategy pattern based on material type.
Outputs JSON data (no geometry) for downstream geometry conversion. Supports
multiple material systems through a modular strategy architecture.

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

3. Panel-Aware Framing
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
    2. Connect 'walls_json' from Wall Analyzer
    3. Set 'material_type' to "timber" or "cfs"
    4. Set 'run' to True to execute
    5. Connect 'framing_json' to Geometry Converter component

Input Requirements:
    Cell JSON (cell_json) - str:
        JSON string from Cell Decomposer with cell decomposition data
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

Error Handling:
    - Invalid JSON returns empty results with error in log
    - Unknown material type defaults to timber with warning
    - Missing cells logged but don't halt execution

Author: Timber Framing Generator
Version: 1.1.0
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

_modules_to_clear = [k for k in sys.modules.keys() if 'timber_framing_generator' in k]
for mod in _modules_to_clear:
    del sys.modules[mod]

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Import materials module to trigger strategy registration
from src.timber_framing_generator.materials import timber  # noqa: F401

from src.timber_framing_generator.core.material_system import (
    MaterialSystem, get_framing_strategy, list_available_materials
)
from src.timber_framing_generator.core.json_schemas import (
    FramingResults, FramingElementData, ProfileData, Point3D, Vector3D,
    deserialize_cell_data, FramingJSONEncoder
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Framing Generator"
COMPONENT_NICKNAME = "FrameGen"
COMPONENT_MESSAGE = "v1.1"
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


def generate_framing_for_wall(cell_data_dict, wall_data_dict, strategy, config):
    """Generate framing elements for a single wall using the strategy.

    Args:
        cell_data_dict: Cell decomposition data for this wall
        wall_data_dict: Wall data for this wall
        strategy: FramingStrategy instance
        config: Configuration parameters

    Returns:
        Tuple of (list of FramingElementData, generation log lines)
    """
    log_lines = []
    elements = []

    wall_id = cell_data_dict.get('wall_id', 'unknown')
    log_lines.append(f"Generating framing for wall {wall_id}")
    log_lines.append(f"  Material: {strategy.material_system.value}")
    log_lines.append(f"  Cells: {len(cell_data_dict.get('cells', []))}")

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

        # Extract panel_id from cell_data metadata (if panel-aware decomposition)
        panel_id = cell_data_dict.get('metadata', {}).get('panel_id')

        for elem in framing_elements:
            # Build element metadata with wall_id, panel_id, and wall direction
            elem_metadata = dict(elem.metadata) if elem.metadata else {}
            elem_metadata['wall_id'] = wall_id
            if panel_id:
                elem_metadata['panel_id'] = panel_id
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
                metadata=elem_metadata,
            )
            elements.append(elem_data)

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


def process_framing(cell_list, wall_lookup, strategy, config):
    """Process all walls through the framing generator.

    Args:
        cell_list: List of cell data dictionaries
        wall_lookup: Dictionary mapping wall_id to wall data
        strategy: FramingStrategy instance
        config: Configuration parameters

    Returns:
        Tuple of (all_elements, type_counts, log_lines)
    """
    log_lines = []
    all_elements = []
    type_counts = {}

    for i, cell_data_dict in enumerate(cell_list):
        wall_id = cell_data_dict.get('wall_id', f'wall_{i}')
        wall_data_dict = wall_lookup.get(wall_id, {})

        elements, wall_log = generate_framing_for_wall(
            cell_data_dict, wall_data_dict, strategy, config
        )

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
    setup_component()

    # Initialize outputs
    framing_json = "{}"
    element_count = {}
    log_lines = []

    try:
        # Unwrap Grasshopper list wrappers
        cell_json_input = cell_json
        while isinstance(cell_json_input, (list, tuple)) and len(cell_json_input) > 0:
            cell_json_input = cell_json_input[0]

        walls_json_input = walls_json
        if isinstance(walls_json, (list, tuple)):
            walls_json_input = walls_json[0] if walls_json else None

        config_json_input = config_json if config_json else None
        if isinstance(config_json, (list, tuple)):
            config_json_input = config_json[0] if config_json else None

        # Validate inputs
        is_valid, error_msg = validate_inputs(cell_json_input, walls_json_input, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            return framing_json, element_count, error_msg

        # Get material system and strategy
        material_type_val = material_type if material_type else "timber"
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

        # Parse inputs
        cell_list = json.loads(cell_json_input)
        wall_list = json.loads(walls_json_input)
        wall_lookup = {w.get('wall_id'): w for w in wall_list}
        config = json.loads(config_json_input) if config_json_input else {}

        log_lines.append(f"Framing Generator v1.1")
        log_lines.append(f"Material System: {material_type_val}")
        log_lines.append(f"Walls to process: {len(cell_list)}")
        log_lines.append(f"Strategy: {strategy.__class__.__name__}")
        log_lines.append("")

        # Process framing
        all_elements, type_counts, process_log = process_framing(
            cell_list, wall_lookup, strategy, config
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

# Set default values for optional inputs
try:
    cell_json
except NameError:
    cell_json = None

try:
    walls_json
except NameError:
    walls_json = None

try:
    material_type
except NameError:
    material_type = "timber"

try:
    config_json
except NameError:
    config_json = None

try:
    run
except NameError:
    run = False

# Execute main
if __name__ == "__main__":
    framing_json, element_count, generation_log = main()
