# File: scripts/gh_framing_generator.py
"""
GHPython Component: Framing Generator

Generates framing elements using the strategy pattern based on material type.
Outputs JSON data (no geometry) for downstream geometry conversion.

Inputs:
    cell_json: JSON string from Cell Decomposer component
    wall_json: JSON string from Wall Analyzer component (for reference data)
    material_type: Material system - "timber" or "cfs" (default: "timber")
    config_json: Optional JSON string with configuration overrides
    run: Boolean to trigger execution

Outputs:
    elements_json: JSON string containing all framing elements
    element_count: Dictionary of element counts by type
    generation_log: Detailed generation log

Usage:
    1. Connect 'cell_json' from Cell Decomposer
    2. Connect 'wall_json' from Wall Analyzer
    3. Set 'material_type' to "timber" or "cfs"
    4. Set 'run' to True to execute
    5. Connect 'elements_json' to Geometry Converter component
"""

import sys
import json
from dataclasses import asdict
from io import StringIO

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================
# Clear cached modules to ensure fresh imports when script changes
_modules_to_clear = [k for k in sys.modules.keys() if 'timber_framing_generator' in k]
for mod in _modules_to_clear:
    del sys.modules[mod]
print(f"[RELOAD] Cleared {len(_modules_to_clear)} cached timber_framing_generator modules")

# =============================================================================
# RhinoCommon Setup
# =============================================================================

import clr

clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')

import Rhino.Geometry as rg

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
# Helper Functions
# =============================================================================

def get_material_system(material_type: str) -> MaterialSystem:
    """
    Convert material type string to MaterialSystem enum.

    Args:
        material_type: "timber" or "cfs"

    Returns:
        MaterialSystem enum value

    Raises:
        ValueError: If material type is not recognized
    """
    material_map = {
        "timber": MaterialSystem.TIMBER,
        "cfs": MaterialSystem.CFS,
    }

    material_lower = material_type.lower().strip()
    if material_lower not in material_map:
        available = list(material_map.keys())
        raise ValueError(f"Unknown material type: {material_type}. Available: {available}")

    return material_map[material_lower]


def generate_framing_for_wall(
    cell_data_dict: dict,
    wall_data_dict: dict,
    strategy,
    config: dict
) -> tuple:
    """
    Generate framing elements for a single wall using the strategy.

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
    log_lines.append(f"  wall_id from cell_data_dict: '{wall_id}'")
    log_lines.append(f"  cell_data_dict keys: {list(cell_data_dict.keys())}")
    log_lines.append(f"  Material: {strategy.material_system.value}")
    log_lines.append(f"  Cells: {len(cell_data_dict.get('cells', []))}")

    # Use strategy to generate elements
    # Capture stdout to include debug output in logs
    old_stdout = sys.stdout
    captured_output = StringIO()
    try:
        # Capture print statements from the strategy modules
        sys.stdout = captured_output

        framing_elements = strategy.generate_framing(
            wall_data=wall_data_dict,
            cell_data=cell_data_dict,
            config=config
        )

        # Convert FramingElement objects to FramingElementData for JSON
        # DEBUG: Print wall_id being added to elements
        print(f"DEBUG: Adding wall_id='{wall_id}' to {len(framing_elements)} elements")

        # Extract wall direction from wall_data_dict's base_plane for geometry reconstruction
        wall_x_axis = None
        wall_z_axis = None
        # DEBUG: Show wall_data_dict content for troubleshooting
        print(f"DEBUG: wall_data_dict keys: {list(wall_data_dict.keys()) if wall_data_dict else 'EMPTY'}")
        if wall_data_dict and 'base_plane' in wall_data_dict:
            print(f"DEBUG: base_plane keys: {list(wall_data_dict['base_plane'].keys())}")
            base_plane = wall_data_dict['base_plane']
            if 'x_axis' in base_plane:
                x_axis = base_plane['x_axis']
                wall_x_axis = (x_axis['x'], x_axis['y'], x_axis['z'])
                print(f"DEBUG: wall_x_axis from base_plane: {wall_x_axis}")
            if 'z_axis' in base_plane:
                z_axis = base_plane['z_axis']
                wall_z_axis = (z_axis['x'], z_axis['y'], z_axis['z'])
                print(f"DEBUG: wall_z_axis from base_plane: {wall_z_axis}")

        for elem in framing_elements:
            # Add wall_id and wall direction to element metadata for filtering and geometry
            elem_metadata = dict(elem.metadata) if elem.metadata else {}
            elem_metadata['wall_id'] = wall_id
            # Add wall direction for geometry reconstruction
            if wall_x_axis:
                elem_metadata['wall_x_axis'] = wall_x_axis
            if wall_z_axis:
                elem_metadata['wall_z_axis'] = wall_z_axis
            # Only print full metadata for first element to avoid log spam
            if len(elements) == 0:
                print(f"DEBUG: First element {elem.id} metadata: wall_id={elem_metadata.get('wall_id')}, wall_x_axis={elem_metadata.get('wall_x_axis')}, wall_z_axis={elem_metadata.get('wall_z_axis')}")

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

    finally:
        # Always restore stdout and capture debug output
        sys.stdout = old_stdout
        debug_output = captured_output.getvalue()
        if debug_output.strip():
            log_lines.append("")
            log_lines.append("--- DEBUG OUTPUT ---")
            log_lines.append(debug_output.strip())
            log_lines.append("--- END DEBUG ---")

    return elements, log_lines


# =============================================================================
# Main Execution
# =============================================================================

# Initialize outputs
elements_json = "{}"
element_count = {}
generation_log = ""

# Default material type
if not material_type:
    material_type = "timber"

if run and cell_json:
    try:
        # Handle Grasshopper wrapping strings in lists (can be nested)
        cell_json_input = cell_json
        unwrap_count = 0
        while isinstance(cell_json_input, (list, tuple)) and len(cell_json_input) > 0:
            cell_json_input = cell_json_input[0]
            unwrap_count += 1
        print(f"DEBUG: Unwrapped cell_json {unwrap_count} times")
        print(f"DEBUG: cell_json_input type after unwrap: {type(cell_json_input)}")
        wall_json_input = wall_json
        if isinstance(wall_json, (list, tuple)):
            wall_json_input = wall_json[0] if wall_json else None
        config_json_input = config_json
        if isinstance(config_json, (list, tuple)):
            config_json_input = config_json[0] if config_json else None

        # Get material system and strategy
        material_system = get_material_system(material_type)

        # Check if strategy is available
        available = list_available_materials()
        if material_system not in available:
            generation_log = (
                f"ERROR: Strategy for {material_type} not available.\n"
                f"Available materials: {[m.value for m in available]}\n"
                f"Make sure to import the materials module."
            )
        else:
            strategy = get_framing_strategy(material_system)

            # Parse inputs
            cell_list = json.loads(cell_json_input)
            wall_list = json.loads(wall_json_input) if wall_json_input else []

            # DEBUG: Print raw JSON length and first few chars
            print(f"\n{'='*60}")
            print(f"FRAMING GENERATOR DEBUG - JSON PARSING")
            print(f"{'='*60}")
            print(f"cell_json_input type: {type(cell_json_input)}")
            print(f"cell_json_input length: {len(cell_json_input) if cell_json_input else 0} chars")
            if cell_json_input:
                print(f"cell_json_input first 500 chars: {cell_json_input[:500]}...")
            print(f"cell_list type: {type(cell_list)}")
            print(f"cell_list length: {len(cell_list)} items")
            print(f"{'='*60}\n")

            # Create wall lookup by ID
            wall_lookup = {w.get('wall_id'): w for w in wall_list}

            # Parse config
            config = json.loads(config_json_input) if config_json_input else {}

            log_lines = [
                f"Framing Generator",
                f"Material System: {material_type}",
                f"Walls to process: {len(cell_list)}",
                f"Walls in wall_lookup: {len(wall_lookup)}",
                f"Strategy: {strategy.__class__.__name__}",
                f"Generation sequence: {[e.value for e in strategy.get_generation_sequence()]}",
                "",
            ]

            # Add wall_lookup debug info to log
            if wall_lookup:
                log_lines.append("Wall lookup info:")
                for wid in list(wall_lookup.keys())[:3]:  # Show first 3
                    wd = wall_lookup[wid]
                    has_bp = 'base_plane' in wd
                    log_lines.append(f"  {wid}: has_base_plane={has_bp}")
                if len(wall_lookup) > 3:
                    log_lines.append(f"  ... and {len(wall_lookup) - 3} more")
                log_lines.append("")
            else:
                log_lines.append("WARNING: wall_lookup is EMPTY - wall_json may not be connected!")
                log_lines.append("")

            # DEBUG: Print detailed cell structure
            print(f"\n{'='*60}")
            print(f"FRAMING GENERATOR DEBUG - CELL DATA ANALYSIS")
            print(f"{'='*60}")
            print(f"Total walls in cell_list: {len(cell_list)}")
            for idx, cell_data_item in enumerate(cell_list):
                wall_id = cell_data_item.get('wall_id', 'UNKNOWN')
                cells_in_wall = cell_data_item.get('cells', [])
                print(f"\n--- Wall {idx}: {wall_id} ---")
                print(f"  Keys in cell_data_item: {list(cell_data_item.keys())}")
                print(f"  Number of cells: {len(cells_in_wall)}")
                for cidx, cell in enumerate(cells_in_wall[:5]):  # Show first 5 cells
                    if isinstance(cell, dict):
                        cell_type = cell.get('cell_type', cell.get('type', 'MISSING'))
                        cell_id = cell.get('id', 'no-id')
                        u_start = cell.get('u_start', 'N/A')
                        u_end = cell.get('u_end', 'N/A')
                        print(f"    Cell {cidx}: type={cell_type}, id={cell_id}, u=({u_start}-{u_end})")
                    else:
                        print(f"    Cell {cidx}: NOT A DICT - type={type(cell)}")
                if len(cells_in_wall) > 5:
                    print(f"    ... and {len(cells_in_wall) - 5} more cells")
            print(f"{'='*60}\n")

            all_elements = []
            type_counts = {}

            # DEBUG: Print wall_lookup info
            print(f"\n{'='*60}")
            print(f"DEBUG: wall_lookup has {len(wall_lookup)} walls")
            for wid in list(wall_lookup.keys())[:5]:
                wd = wall_lookup[wid]
                has_base_plane = 'base_plane' in wd
                bp_keys = list(wd.get('base_plane', {}).keys()) if has_base_plane else []
                print(f"  Wall {wid}: has_base_plane={has_base_plane}, base_plane keys={bp_keys}")
            print(f"{'='*60}\n")

            for i, cell_data_dict in enumerate(cell_list):
                wall_id = cell_data_dict.get('wall_id', f'wall_{i}')
                wall_data_dict = wall_lookup.get(wall_id, {})

                # DEBUG: Check if wall_data_dict has base_plane
                if i < 3:  # Only print for first 3 walls
                    has_bp = 'base_plane' in wall_data_dict
                    print(f"DEBUG: Wall {wall_id}: wall_data_dict has_base_plane={has_bp}")

                elements, wall_log = generate_framing_for_wall(
                    cell_data_dict, wall_data_dict, strategy, config
                )

                all_elements.extend(elements)
                log_lines.extend(wall_log)

                # Count by type
                for elem in elements:
                    elem_type = elem.element_type
                    type_counts[elem_type] = type_counts.get(elem_type, 0) + 1

            # Create results object
            results = FramingResults(
                wall_id="all_walls",  # Combined results
                material_system=material_type,
                elements=all_elements,
                element_counts=type_counts,
                metadata={
                    'total_walls': len(cell_list),
                    'total_elements': len(all_elements),
                }
            )

            # Serialize to JSON
            elements_json = json.dumps(asdict(results), cls=FramingJSONEncoder, indent=2)
            element_count = type_counts

            log_lines.append("")
            log_lines.append(f"Summary:")
            log_lines.append(f"  Total elements: {len(all_elements)}")
            for elem_type, count in sorted(type_counts.items()):
                log_lines.append(f"  {elem_type}: {count}")

            # Note about Phase 2/3
            if len(all_elements) == 0:
                log_lines.append("")
                log_lines.append("NOTE: No elements generated.")
                log_lines.append("This is expected in Phase 2/3 - strategies return empty lists.")
                log_lines.append("Full generation will be implemented when strategies are complete.")

            generation_log = "\n".join(log_lines)

    except json.JSONDecodeError as e:
        generation_log = f"JSON Parse Error: {str(e)}"
    except ValueError as e:
        generation_log = f"Value Error: {str(e)}"
    except Exception as e:
        import traceback
        generation_log = f"ERROR: {str(e)}\n{traceback.format_exc()}"

elif not run:
    generation_log = "Set 'run' to True to execute"
elif not cell_json:
    generation_log = "No cell_json input provided"
