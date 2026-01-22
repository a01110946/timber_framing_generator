# File: scripts/gh_cell_decomposer.py
"""
GHPython Component: Cell Decomposer

Decomposes wall data into cells (stud regions, opening regions, etc.)
and serializes to JSON format.

Inputs:
    wall_json: JSON string from Wall Analyzer component
    run: Boolean to trigger execution

Outputs:
    cell_json: JSON string containing cell data for all walls
    cell_srf: DataTree of cell boundary surfaces for visualization
    cell_types: DataTree of cell type labels (SC, OC, HCC, SCC)
    debug_info: Debug information and status messages

Usage:
    1. Connect 'wall_json' from Wall Analyzer
    2. Set 'run' to True to execute
    3. Connect 'cell_json' to Framing Generator component
"""

import sys
import json
from dataclasses import asdict

# =============================================================================
# RhinoCommon Setup
# =============================================================================

import clr

clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.core.json_schemas import (
    CellData, CellInfo, CellCorners, Point3D,
    deserialize_wall_data, FramingJSONEncoder
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Helper Functions
# =============================================================================

def create_cell_surface(corners: CellCorners):
    """
    Create a visualization surface from cell corners using RhinoCommonFactory.

    Args:
        corners: CellCorners with bottom_left, bottom_right, top_right, top_left

    Returns:
        NurbsSurface for visualization, or None if creation fails
    """
    try:
        factory = get_factory()
        return factory.create_surface_from_corners(
            (corners.bottom_left.x, corners.bottom_left.y, corners.bottom_left.z),
            (corners.bottom_right.x, corners.bottom_right.y, corners.bottom_right.z),
            (corners.top_right.x, corners.top_right.y, corners.top_right.z),
            (corners.top_left.x, corners.top_left.y, corners.top_left.z),
        )
    except Exception as e:
        print(f"Error creating cell surface: {e}")
        return None


def decompose_wall_json_to_cells(wall_dict: dict, wall_index: int) -> tuple:
    """
    Decompose a single wall from JSON to cells.

    This is a simplified version - in full implementation would call
    the cell_segmentation module with reconstructed Rhino geometry.

    Args:
        wall_dict: Wall data dictionary from JSON
        wall_index: Index for this wall

    Returns:
        Tuple of (CellData, list of surfaces, list of type labels)
    """
    wall_id = wall_dict.get('wall_id', f'wall_{wall_index}')
    wall_length = wall_dict.get('wall_length', 0)
    wall_height = wall_dict.get('wall_height', 0)
    base_elevation = wall_dict.get('base_elevation', 0)

    # Get base plane origin for positioning
    base_plane = wall_dict.get('base_plane', {})
    origin = base_plane.get('origin', {'x': 0, 'y': 0, 'z': 0})
    x_axis = base_plane.get('x_axis', {'x': 1, 'y': 0, 'z': 0})
    y_axis = base_plane.get('y_axis', {'x': 0, 'y': 1, 'z': 0})

    cells = []
    surfaces = []
    type_labels = []

    openings = wall_dict.get('openings', [])

    # Simple cell decomposition algorithm:
    # 1. Create stud cells for regions without openings
    # 2. Create opening cells, header cripple cells, sill cripple cells

    if not openings:
        # No openings - single stud cell spanning entire wall
        corners = CellCorners(
            bottom_left=Point3D(origin['x'], origin['y'], base_elevation),
            bottom_right=Point3D(
                origin['x'] + x_axis['x'] * wall_length,
                origin['y'] + x_axis['y'] * wall_length,
                base_elevation
            ),
            top_right=Point3D(
                origin['x'] + x_axis['x'] * wall_length,
                origin['y'] + x_axis['y'] * wall_length,
                base_elevation + wall_height
            ),
            top_left=Point3D(origin['x'], origin['y'], base_elevation + wall_height),
        )

        cell = CellInfo(
            id=f"{wall_id}_SC_0",
            cell_type="SC",
            u_start=0,
            u_end=wall_length,
            v_start=0,
            v_end=wall_height,
            corners=corners,
        )
        cells.append(cell)

        srf = create_cell_surface(corners)
        if srf:
            surfaces.append(srf)
        type_labels.append("SC")
    else:
        # Sort openings by u_start
        sorted_openings = sorted(openings, key=lambda o: o.get('u_start', 0))

        current_u = 0
        cell_idx = 0

        for opening in sorted_openings:
            o_u_start = opening.get('u_start', 0)
            o_u_end = opening.get('u_end', 0)
            o_v_start = opening.get('v_start', 0)
            o_v_end = opening.get('v_end', 0)
            o_type = opening.get('opening_type', 'window')
            o_id = opening.get('id', f'opening_{cell_idx}')

            # Stud cell before opening (if space exists)
            if current_u < o_u_start:
                corners = CellCorners(
                    bottom_left=Point3D(
                        origin['x'] + x_axis['x'] * current_u,
                        origin['y'] + x_axis['y'] * current_u,
                        base_elevation
                    ),
                    bottom_right=Point3D(
                        origin['x'] + x_axis['x'] * o_u_start,
                        origin['y'] + x_axis['y'] * o_u_start,
                        base_elevation
                    ),
                    top_right=Point3D(
                        origin['x'] + x_axis['x'] * o_u_start,
                        origin['y'] + x_axis['y'] * o_u_start,
                        base_elevation + wall_height
                    ),
                    top_left=Point3D(
                        origin['x'] + x_axis['x'] * current_u,
                        origin['y'] + x_axis['y'] * current_u,
                        base_elevation + wall_height
                    ),
                )
                cell = CellInfo(
                    id=f"{wall_id}_SC_{cell_idx}",
                    cell_type="SC",
                    u_start=current_u,
                    u_end=o_u_start,
                    v_start=0,
                    v_end=wall_height,
                    corners=corners,
                )
                cells.append(cell)
                srf = create_cell_surface(corners)
                if srf:
                    surfaces.append(srf)
                type_labels.append("SC")
                cell_idx += 1

            # Header cripple cell (above opening) if not a door
            if o_v_end < wall_height:
                corners = CellCorners(
                    bottom_left=Point3D(
                        origin['x'] + x_axis['x'] * o_u_start,
                        origin['y'] + x_axis['y'] * o_u_start,
                        base_elevation + o_v_end
                    ),
                    bottom_right=Point3D(
                        origin['x'] + x_axis['x'] * o_u_end,
                        origin['y'] + x_axis['y'] * o_u_end,
                        base_elevation + o_v_end
                    ),
                    top_right=Point3D(
                        origin['x'] + x_axis['x'] * o_u_end,
                        origin['y'] + x_axis['y'] * o_u_end,
                        base_elevation + wall_height
                    ),
                    top_left=Point3D(
                        origin['x'] + x_axis['x'] * o_u_start,
                        origin['y'] + x_axis['y'] * o_u_start,
                        base_elevation + wall_height
                    ),
                )
                cell = CellInfo(
                    id=f"{wall_id}_HCC_{cell_idx}",
                    cell_type="HCC",
                    u_start=o_u_start,
                    u_end=o_u_end,
                    v_start=o_v_end,
                    v_end=wall_height,
                    corners=corners,
                    opening_id=o_id,
                )
                cells.append(cell)
                srf = create_cell_surface(corners)
                if srf:
                    surfaces.append(srf)
                type_labels.append("HCC")
                cell_idx += 1

            # Opening cell
            corners = CellCorners(
                bottom_left=Point3D(
                    origin['x'] + x_axis['x'] * o_u_start,
                    origin['y'] + x_axis['y'] * o_u_start,
                    base_elevation + o_v_start
                ),
                bottom_right=Point3D(
                    origin['x'] + x_axis['x'] * o_u_end,
                    origin['y'] + x_axis['y'] * o_u_end,
                    base_elevation + o_v_start
                ),
                top_right=Point3D(
                    origin['x'] + x_axis['x'] * o_u_end,
                    origin['y'] + x_axis['y'] * o_u_end,
                    base_elevation + o_v_end
                ),
                top_left=Point3D(
                    origin['x'] + x_axis['x'] * o_u_start,
                    origin['y'] + x_axis['y'] * o_u_start,
                    base_elevation + o_v_end
                ),
            )
            cell = CellInfo(
                id=f"{wall_id}_OC_{cell_idx}",
                cell_type="OC",
                u_start=o_u_start,
                u_end=o_u_end,
                v_start=o_v_start,
                v_end=o_v_end,
                corners=corners,
                opening_id=o_id,
                opening_type=o_type,
            )
            cells.append(cell)
            srf = create_cell_surface(corners)
            if srf:
                surfaces.append(srf)
            type_labels.append("OC")
            cell_idx += 1

            # Sill cripple cell (below opening) - windows only
            if o_v_start > 0 and o_type == 'window':
                corners = CellCorners(
                    bottom_left=Point3D(
                        origin['x'] + x_axis['x'] * o_u_start,
                        origin['y'] + x_axis['y'] * o_u_start,
                        base_elevation
                    ),
                    bottom_right=Point3D(
                        origin['x'] + x_axis['x'] * o_u_end,
                        origin['y'] + x_axis['y'] * o_u_end,
                        base_elevation
                    ),
                    top_right=Point3D(
                        origin['x'] + x_axis['x'] * o_u_end,
                        origin['y'] + x_axis['y'] * o_u_end,
                        base_elevation + o_v_start
                    ),
                    top_left=Point3D(
                        origin['x'] + x_axis['x'] * o_u_start,
                        origin['y'] + x_axis['y'] * o_u_start,
                        base_elevation + o_v_start
                    ),
                )
                cell = CellInfo(
                    id=f"{wall_id}_SCC_{cell_idx}",
                    cell_type="SCC",
                    u_start=o_u_start,
                    u_end=o_u_end,
                    v_start=0,
                    v_end=o_v_start,
                    corners=corners,
                    opening_id=o_id,
                )
                cells.append(cell)
                srf = create_cell_surface(corners)
                if srf:
                    surfaces.append(srf)
                type_labels.append("SCC")
                cell_idx += 1

            current_u = o_u_end

        # Final stud cell after last opening
        if current_u < wall_length:
            corners = CellCorners(
                bottom_left=Point3D(
                    origin['x'] + x_axis['x'] * current_u,
                    origin['y'] + x_axis['y'] * current_u,
                    base_elevation
                ),
                bottom_right=Point3D(
                    origin['x'] + x_axis['x'] * wall_length,
                    origin['y'] + x_axis['y'] * wall_length,
                    base_elevation
                ),
                top_right=Point3D(
                    origin['x'] + x_axis['x'] * wall_length,
                    origin['y'] + x_axis['y'] * wall_length,
                    base_elevation + wall_height
                ),
                top_left=Point3D(
                    origin['x'] + x_axis['x'] * current_u,
                    origin['y'] + x_axis['y'] * current_u,
                    base_elevation + wall_height
                ),
            )
            cell = CellInfo(
                id=f"{wall_id}_SC_{cell_idx}",
                cell_type="SC",
                u_start=current_u,
                u_end=wall_length,
                v_start=0,
                v_end=wall_height,
                corners=corners,
            )
            cells.append(cell)
            srf = create_cell_surface(corners)
            if srf:
                surfaces.append(srf)
            type_labels.append("SC")

    cell_data = CellData(
        wall_id=wall_id,
        cells=cells,
        metadata={'wall_length': wall_length, 'wall_height': wall_height}
    )

    return cell_data, surfaces, type_labels


# =============================================================================
# Main Execution
# =============================================================================

# Initialize outputs
cell_json = "[]"
cell_srf = DataTree[object]()
cell_types = DataTree[object]()
debug_info = ""

if run and wall_json:
    try:
        # Parse wall JSON
        wall_list = json.loads(wall_json)

        if not wall_list:
            debug_info = "No walls in JSON input"
        else:
            all_cell_data = []
            debug_lines = [f"Processing {len(wall_list)} walls..."]

            for i, wall_dict in enumerate(wall_list):
                try:
                    cell_data, surfaces, type_labels = decompose_wall_json_to_cells(
                        wall_dict, i
                    )
                    all_cell_data.append(cell_data)

                    # Add surfaces and labels to DataTrees
                    wall_path = GH_Path(i)
                    for j, srf in enumerate(surfaces):
                        cell_srf.Add(srf, GH_Path(i, j))
                    for j, label in enumerate(type_labels):
                        cell_types.Add(label, GH_Path(i, j))

                    debug_lines.append(
                        f"Wall {i}: {len(cell_data.cells)} cells "
                        f"(SC:{type_labels.count('SC')}, OC:{type_labels.count('OC')}, "
                        f"HCC:{type_labels.count('HCC')}, SCC:{type_labels.count('SCC')})"
                    )

                except Exception as e:
                    debug_lines.append(f"Wall {i}: ERROR - {str(e)}")

            # Serialize all cells to JSON
            if all_cell_data:
                cell_dicts = [asdict(cd) for cd in all_cell_data]
                cell_json = json.dumps(cell_dicts, cls=FramingJSONEncoder, indent=2)
                debug_lines.append(f"\nSuccess: Serialized cells for {len(all_cell_data)} walls")

            debug_info = "\n".join(debug_lines)

    except json.JSONDecodeError as e:
        debug_info = f"JSON Parse Error: {str(e)}"
    except Exception as e:
        import traceback
        debug_info = f"ERROR: {str(e)}\n{traceback.format_exc()}"

elif not run:
    debug_info = "Set 'run' to True to execute"
elif not wall_json:
    debug_info = "No wall_json input provided"

# =============================================================================
# Assign Outputs
# =============================================================================

a = cell_json      # cell_json output
b = cell_srf       # cell_srf output
c = cell_types     # cell_types output
d = debug_info     # debug_info output
