# File: scripts/gh_cell_decomposer.py
"""Cell Decomposer for Grasshopper.

Decomposes wall data into cells (stud regions, opening regions, cripple regions)
and serializes to JSON format. Supports both whole-wall and panel-aware
decomposition for offsite construction workflows.

Key Features:
1. Cell Decomposition
   - Splits walls into stud cells (SC), opening cells (OC)
   - Creates header cripple cells (HCC) above openings
   - Creates sill cripple cells (SCC) below windows

2. Panel-Aware Mode
   - Integrates with Panel Decomposer output
   - Decomposes cells within panel boundaries
   - Generates panel-aware cell IDs (wall_1_panel_0_SC_0)

3. Legacy Mode
   - Works without Panel Decomposer
   - Decomposes entire walls as single units
   - Backward compatible with existing workflows

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry types
    - Grasshopper: DataTree for output organization
    - timber_framing_generator.core: JSON schemas
    - timber_framing_generator.cell_decomposition: Panel-aware functions

Performance Considerations:
    - Processing time scales linearly with wall count
    - Panel-aware mode adds overhead per panel
    - Typical walls process in < 50ms

Usage:
    Option A - Without panelization (legacy mode):
        1. Connect 'wall_json' from Wall Analyzer
        2. Leave 'panels_json' empty
        3. Set 'run' to True to execute

    Option B - With panelization (recommended for offsite construction):
        1. Connect 'wall_json' from Wall Analyzer
        2. Connect 'panels_json' from Panel Decomposer
        3. Set 'run' to True to execute

Input Requirements:
    Walls JSON (wall_json) - str:
        JSON string from Wall Analyzer component
        Required: Yes
        Access: Item

    Panels JSON (panels_json) - str:
        JSON string from Panel Decomposer (optional)
        Required: No
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Cell JSON (cell_json) - str:
        JSON string containing cell data for all walls/panels

    Cell Surfaces (cell_srf) - DataTree[Surface]:
        Cell boundary surfaces for visualization

    Cell Types (cell_types) - DataTree[str]:
        Cell type labels (SC, OC, HCC, SCC)

    Debug Info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Cell IDs without panels: wall_1_SC_0
    - Cell IDs with panels: wall_1_panel_0_SC_0
    - Openings clipped to panel boundaries

Error Handling:
    - Invalid JSON returns empty outputs with error in debug_info
    - Missing panels falls back to legacy mode
    - Processing errors logged but don't halt execution

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

from src.timber_framing_generator.core.json_schemas import (
    CellData, CellInfo, CellCorners, Point3D,
    deserialize_wall_data, FramingJSONEncoder
)
from src.timber_framing_generator.utils.geometry_factory import get_factory
from src.timber_framing_generator.cell_decomposition import (
    get_openings_in_range,
    clip_opening_to_range,
    check_opening_spans_panel_joint,
    generate_panel_cell_id,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Cell Decomposer"
COMPONENT_NICKNAME = "CellDecomp"
COMPONENT_MESSAGE = "v1.1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Analysis"

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
    They must be configured via UI: Right-click input -> Type hint -> Select type
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Walls JSON", "wall_json", "JSON string from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Panels JSON", "panels_json", "JSON string from Panel Decomposer (optional)",
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
        ("Cell JSON", "cell_json", "JSON string containing cell data"),
        ("Cell Surfaces", "cell_srf", "Cell boundary surfaces for visualization"),
        ("Cell Types", "cell_types", "Cell type labels (SC, OC, HCC, SCC)"),
        ("Debug Info", "debug_info", "Debug information and status"),
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

def validate_inputs(wall_json, panels_json, run):
    """Validate component inputs.

    Args:
        wall_json: JSON string with wall data
        panels_json: JSON string with panel data (optional)
        run: Boolean trigger

    Returns:
        tuple: (is_valid, panels_valid, error_message)
    """
    if not run:
        return False, False, "Component not running. Set 'run' to True."

    if not wall_json:
        return False, False, "No wall_json input provided"

    try:
        json.loads(wall_json)
    except json.JSONDecodeError as e:
        return False, False, f"Invalid JSON in wall_json: {e}"

    # Validate panels_json (optional input)
    panels_valid = False
    if panels_json:
        log_info(f"panels_json received: type={type(panels_json).__name__}, len={len(panels_json)}")
        try:
            parsed = json.loads(panels_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                panels_valid = True
                log_info(f"panels_json parsed: {len(parsed)} wall entries")
            else:
                log_warning(f"panels_json parsed but empty or not a list: {type(parsed)}")
        except json.JSONDecodeError as e:
            log_warning(f"Invalid JSON in panels_json: {e}")
    else:
        log_info(f"panels_json not provided or empty: {repr(panels_json)}")

    return True, panels_valid, None


def create_cell_surface(corners):
    """Create a visualization surface from cell corners using RhinoCommonFactory.

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
        log_debug(f"Error creating cell surface: {e}")
        return None


def parse_panels_json(panels_json_str):
    """Parse panels JSON to extract panel data.

    Args:
        panels_json_str: JSON string containing panels data

    Returns:
        List of panel result dictionaries
    """
    if not panels_json_str:
        return []
    data = json.loads(panels_json_str)
    return data if isinstance(data, list) else [data]


def get_panels_for_wall(panels_data, wall_id):
    """Get panels for a specific wall from the panels data.

    Args:
        panels_data: List of panel result dictionaries
        wall_id: Wall ID to look up

    Returns:
        List of panel dictionaries for this wall
    """
    # Convert to string for comparison (handles int vs str mismatch)
    wall_id_str = str(wall_id)
    for result in panels_data:
        if str(result.get('wall_id', '')) == wall_id_str:
            return result.get('panels', [])
    return []


def decompose_panel_to_cells(wall_dict, panel, wall_index, panel_index):
    """Decompose a single panel (wall segment) to cells.

    Args:
        wall_dict: Wall data dictionary from JSON
        panel: Panel dictionary with id, u_start, u_end, etc.
        wall_index: Index for this wall
        panel_index: Index for this panel within the wall

    Returns:
        Tuple of (CellData, list of surfaces, list of type labels)
    """
    wall_id = wall_dict.get('wall_id', f'wall_{wall_index}')
    panel_id = panel.get('id', f'{wall_id}_panel_{panel_index}')
    panel_u_start = panel.get('u_start', 0)
    panel_u_end = panel.get('u_end', wall_dict.get('wall_length', 0))
    panel_length = panel_u_end - panel_u_start

    wall_height = wall_dict.get('wall_height', 0)
    base_elevation = wall_dict.get('base_elevation', 0)

    base_plane = wall_dict.get('base_plane', {})
    origin = base_plane.get('origin', {'x': 0, 'y': 0, 'z': 0})
    x_axis = base_plane.get('x_axis', {'x': 1, 'y': 0, 'z': 0})

    cells = []
    surfaces = []
    type_labels = []

    all_openings = wall_dict.get('openings', [])
    panel_openings = get_openings_in_range(all_openings, panel_u_start, panel_u_end)

    log_debug(f"Panel {panel_id}: range u={panel_u_start:.2f} to {panel_u_end:.2f}, {len(panel_openings)} openings")

    def world_point(u_coord, v_coord):
        return Point3D(
            origin['x'] + x_axis['x'] * u_coord,
            origin['y'] + x_axis['y'] * u_coord,
            base_elevation + v_coord
        )

    cell_idx = 0

    if not panel_openings:
        corners = CellCorners(
            bottom_left=world_point(panel_u_start, 0),
            bottom_right=world_point(panel_u_end, 0),
            top_right=world_point(panel_u_end, wall_height),
            top_left=world_point(panel_u_start, wall_height),
        )
        cell = CellInfo(
            id=generate_panel_cell_id(wall_id, panel_index, "SC", cell_idx),
            cell_type="SC",
            u_start=panel_u_start,
            u_end=panel_u_end,
            v_start=0,
            v_end=wall_height,
            corners=corners,
            panel_id=panel_id,
        )
        cells.append(cell)
        srf = create_cell_surface(corners)
        if srf:
            surfaces.append(srf)
        type_labels.append("SC")
    else:
        sorted_openings = sorted(panel_openings, key=lambda o: o.get('u_start', 0))
        current_u = panel_u_start

        for opening in sorted_openings:
            clipped = clip_opening_to_range(opening, panel_u_start, panel_u_end)
            if not clipped:
                continue

            o_u_start = clipped.get('u_start', 0)
            o_u_end = clipped.get('u_end', 0)
            o_v_start = clipped.get('v_start', 0)
            o_v_end = clipped.get('v_end', 0)
            o_type = clipped.get('opening_type', 'window')
            o_id = clipped.get('id', f'opening_{cell_idx}')

            # Stud cell before opening
            if current_u < o_u_start:
                corners = CellCorners(
                    bottom_left=world_point(current_u, 0),
                    bottom_right=world_point(o_u_start, 0),
                    top_right=world_point(o_u_start, wall_height),
                    top_left=world_point(current_u, wall_height),
                )
                cell = CellInfo(
                    id=generate_panel_cell_id(wall_id, panel_index, "SC", cell_idx),
                    cell_type="SC",
                    u_start=current_u,
                    u_end=o_u_start,
                    v_start=0,
                    v_end=wall_height,
                    corners=corners,
                    panel_id=panel_id,
                )
                cells.append(cell)
                srf = create_cell_surface(corners)
                if srf:
                    surfaces.append(srf)
                type_labels.append("SC")
                cell_idx += 1

            # Header cripple cell (above opening)
            if o_v_end < wall_height:
                corners = CellCorners(
                    bottom_left=world_point(o_u_start, o_v_end),
                    bottom_right=world_point(o_u_end, o_v_end),
                    top_right=world_point(o_u_end, wall_height),
                    top_left=world_point(o_u_start, wall_height),
                )
                cell = CellInfo(
                    id=generate_panel_cell_id(wall_id, panel_index, "HCC", cell_idx),
                    cell_type="HCC",
                    u_start=o_u_start,
                    u_end=o_u_end,
                    v_start=o_v_end,
                    v_end=wall_height,
                    corners=corners,
                    opening_id=o_id,
                    panel_id=panel_id,
                )
                cells.append(cell)
                srf = create_cell_surface(corners)
                if srf:
                    surfaces.append(srf)
                type_labels.append("HCC")
                cell_idx += 1

            # Opening cell
            corners = CellCorners(
                bottom_left=world_point(o_u_start, o_v_start),
                bottom_right=world_point(o_u_end, o_v_start),
                top_right=world_point(o_u_end, o_v_end),
                top_left=world_point(o_u_start, o_v_end),
            )
            cell = CellInfo(
                id=generate_panel_cell_id(wall_id, panel_index, "OC", cell_idx),
                cell_type="OC",
                u_start=o_u_start,
                u_end=o_u_end,
                v_start=o_v_start,
                v_end=o_v_end,
                corners=corners,
                opening_id=o_id,
                opening_type=o_type,
                panel_id=panel_id,
            )
            cells.append(cell)
            srf = create_cell_surface(corners)
            if srf:
                surfaces.append(srf)
            type_labels.append("OC")
            cell_idx += 1

            # Sill cripple cell (below window)
            if o_v_start > 0 and o_type == 'window':
                corners = CellCorners(
                    bottom_left=world_point(o_u_start, 0),
                    bottom_right=world_point(o_u_end, 0),
                    top_right=world_point(o_u_end, o_v_start),
                    top_left=world_point(o_u_start, o_v_start),
                )
                cell = CellInfo(
                    id=generate_panel_cell_id(wall_id, panel_index, "SCC", cell_idx),
                    cell_type="SCC",
                    u_start=o_u_start,
                    u_end=o_u_end,
                    v_start=0,
                    v_end=o_v_start,
                    corners=corners,
                    opening_id=o_id,
                    panel_id=panel_id,
                )
                cells.append(cell)
                srf = create_cell_surface(corners)
                if srf:
                    surfaces.append(srf)
                type_labels.append("SCC")
                cell_idx += 1

            current_u = o_u_end

        # Final stud cell after last opening
        if current_u < panel_u_end:
            corners = CellCorners(
                bottom_left=world_point(current_u, 0),
                bottom_right=world_point(panel_u_end, 0),
                top_right=world_point(panel_u_end, wall_height),
                top_left=world_point(current_u, wall_height),
            )
            cell = CellInfo(
                id=generate_panel_cell_id(wall_id, panel_index, "SC", cell_idx),
                cell_type="SC",
                u_start=current_u,
                u_end=panel_u_end,
                v_start=0,
                v_end=wall_height,
                corners=corners,
                panel_id=panel_id,
            )
            cells.append(cell)
            srf = create_cell_surface(corners)
            if srf:
                surfaces.append(srf)
            type_labels.append("SC")

    cell_data = CellData(
        wall_id=wall_id,
        cells=cells,
        metadata={
            'wall_length': wall_dict.get('wall_length', 0),
            'wall_height': wall_height,
            'panel_id': panel_id,
            'panel_u_start': panel_u_start,
            'panel_u_end': panel_u_end,
        }
    )

    return cell_data, surfaces, type_labels


def decompose_wall_json_to_cells(wall_dict, wall_index):
    """Decompose a single wall from JSON to cells (legacy mode).

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

    base_plane = wall_dict.get('base_plane', {})
    origin = base_plane.get('origin', {'x': 0, 'y': 0, 'z': 0})
    x_axis = base_plane.get('x_axis', {'x': 1, 'y': 0, 'z': 0})

    cells = []
    surfaces = []
    type_labels = []
    openings = wall_dict.get('openings', [])

    log_debug(f"Wall {wall_id}: L={wall_length:.2f}, H={wall_height:.2f}, {len(openings)} openings")

    if not openings:
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

            # Stud cell before opening
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

            # Header cripple cell (above opening)
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

            # Sill cripple cell (below window)
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


def process_decomposition(wall_list, panels_data):
    """Process all walls/panels through decomposition.

    Args:
        wall_list: List of wall dictionaries
        panels_data: List of panel result dictionaries or None

    Returns:
        Tuple of (all_cell_data, cell_srf_tree, cell_types_tree, log_lines)
    """
    all_cell_data = []
    cell_srf = DataTree[object]()
    cell_types = DataTree[object]()
    log_lines = []
    tree_idx = 0

    if panels_data:
        log_lines.append("=== PANEL-AWARE MODE ===")
        log_lines.append(f"Processing {len(wall_list)} walls with panel decomposition")
    else:
        log_lines.append("=== LEGACY MODE (no panels) ===")
        log_lines.append(f"Processing {len(wall_list)} walls")

    for wall_idx, wall_dict in enumerate(wall_list):
        wall_id = wall_dict.get('wall_id', f'wall_{wall_idx}')

        try:
            if panels_data:
                wall_panels = get_panels_for_wall(panels_data, wall_id)

                if not wall_panels:
                    log_lines.append(f"Wall {wall_idx} ({wall_id}): No panels, using whole-wall mode")
                    cell_data, surfaces, type_labels = decompose_wall_json_to_cells(wall_dict, wall_idx)
                    all_cell_data.append(cell_data)

                    for j, srf in enumerate(surfaces):
                        cell_srf.Add(srf, GH_Path(tree_idx, j))
                    for j, label in enumerate(type_labels):
                        cell_types.Add(label, GH_Path(tree_idx, j))

                    log_lines.append(f"  Cells: {len(cell_data.cells)}")
                    tree_idx += 1
                else:
                    log_lines.append(f"Wall {wall_idx} ({wall_id}): {len(wall_panels)} panels")

                    for panel_idx, panel in enumerate(wall_panels):
                        panel_id = panel.get('id', f'{wall_id}_panel_{panel_idx}')
                        cell_data, surfaces, type_labels = decompose_panel_to_cells(
                            wall_dict, panel, wall_idx, panel_idx
                        )
                        all_cell_data.append(cell_data)

                        for j, srf in enumerate(surfaces):
                            cell_srf.Add(srf, GH_Path(tree_idx, j))
                        for j, label in enumerate(type_labels):
                            cell_types.Add(label, GH_Path(tree_idx, j))

                        log_lines.append(f"  Panel {panel_idx}: {len(cell_data.cells)} cells")
                        tree_idx += 1
            else:
                cell_data, surfaces, type_labels = decompose_wall_json_to_cells(wall_dict, wall_idx)
                all_cell_data.append(cell_data)

                for j, srf in enumerate(surfaces):
                    cell_srf.Add(srf, GH_Path(tree_idx, j))
                for j, label in enumerate(type_labels):
                    cell_types.Add(label, GH_Path(tree_idx, j))

                log_lines.append(f"Wall {wall_idx} ({wall_id}): {len(cell_data.cells)} cells")
                tree_idx += 1

        except Exception as e:
            log_lines.append(f"Wall {wall_idx}: ERROR - {str(e)}")
            log_lines.append(traceback.format_exc())

    return all_cell_data, cell_srf, cell_types, log_lines

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Returns:
        tuple: (cell_json, cell_srf, cell_types, debug_info)
    """
    setup_component()

    # Initialize outputs
    cell_json = "[]"
    cell_srf = DataTree[object]()
    cell_types = DataTree[object]()
    log_lines = []

    try:
        # Unwrap Grasshopper list wrappers
        wall_json_input = wall_json
        if isinstance(wall_json, (list, tuple)):
            wall_json_input = wall_json[0] if wall_json else None

        panels_json_input = panels_json if panels_json else None
        if isinstance(panels_json, (list, tuple)):
            panels_json_input = panels_json[0] if panels_json else None

        # Validate inputs
        is_valid, panels_valid, error_msg = validate_inputs(wall_json_input, panels_json_input, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            return cell_json, cell_srf, cell_types, error_msg

        log_info(f"Validation complete: walls_valid={is_valid}, panels_valid={panels_valid}")

        # Parse inputs
        wall_list = json.loads(wall_json_input)
        panels_data = parse_panels_json(panels_json_input) if panels_json_input else None

        log_lines.append(f"Cell Decomposer v1.1")
        log_lines.append(f"Walls: {len(wall_list)}")

        # Debug: Show what panels_json contains
        log_lines.append(f"DEBUG panels_json type: {type(panels_json)}")
        log_lines.append(f"DEBUG panels_json_input type: {type(panels_json_input)}")
        if panels_json_input:
            log_lines.append(f"DEBUG panels_json_input length: {len(panels_json_input)}")
            log_lines.append(f"DEBUG panels_json_input first 200 chars: {str(panels_json_input)[:200]}")
        else:
            log_lines.append(f"DEBUG panels_json_input is None or empty")
        log_lines.append(f"DEBUG panels_data: {type(panels_data)}, len={len(panels_data) if panels_data else 0}")
        log_lines.append("")

        # Process decomposition
        all_cell_data, cell_srf, cell_types, process_log = process_decomposition(
            wall_list, panels_data
        )
        log_lines.extend(process_log)

        # Serialize to JSON
        if all_cell_data:
            cell_dicts = [asdict(cd) for cd in all_cell_data]
            cell_json = json.dumps(cell_dicts, cls=FramingJSONEncoder, indent=2)

            total_cells = sum(len(cd.cells) for cd in all_cell_data)
            log_lines.append("")
            log_lines.append(f"=== SUMMARY ===")
            log_lines.append(f"Total entries: {len(all_cell_data)}")
            log_lines.append(f"Total cells: {total_cells}")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_lines.append(f"ERROR: {str(e)}")
        log_lines.append(traceback.format_exc())

    return cell_json, cell_srf, cell_types, "\n".join(log_lines)

# =============================================================================
# Execution
# =============================================================================

# Debug: Print actual input NickNames
print("[PARAM DEBUG] Input parameter NickNames:")
for i, param in enumerate(ghenv.Component.Params.Input):
    print(f"  Input {i}: NickName='{param.NickName}', Name='{param.Name}'")

# Debug: Check globals vs locals for panels_json
print("[SCOPE DEBUG] Checking globals() for input variables:")
print(f"  'panels_json' in globals(): {'panels_json' in globals()}")
print(f"  'wall_json' in globals(): {'wall_json' in globals()}")
print(f"  'run' in globals(): {'run' in globals()}")
if 'panels_json' in globals():
    print(f"  globals()['panels_json'] type: {type(globals()['panels_json'])}")
    print(f"  globals()['panels_json'] value: {repr(globals()['panels_json'])[:200]}")

# Set default values for optional inputs
# Track whether variables were defined by GH or set by fallback
_panels_json_from_gh = False

try:
    wall_json
except NameError:
    wall_json = None

# WORKAROUND: panels_json not being injected into globals - read directly from component
try:
    panels_json
    _panels_json_from_gh = True
except NameError:
    panels_json = None
    _panels_json_from_gh = False

# If panels_json is still None, try reading directly from the component parameter
if panels_json is None:
    try:
        panels_param = ghenv.Component.Params.Input[1]  # Index 1 = panels_json
        if panels_param.VolatileDataCount > 0:
            # Get the first item from the volatile data
            branch = panels_param.VolatileData.Branch(0)
            if branch and len(branch) > 0:
                raw_value = branch[0]
                # Extract the actual value (might be wrapped in GH_String or similar)
                if hasattr(raw_value, 'Value'):
                    panels_json = raw_value.Value
                else:
                    panels_json = str(raw_value)
                print(f"[WORKAROUND] Read panels_json directly from param: {type(panels_json)}, len={len(panels_json) if panels_json else 0}")
    except Exception as e:
        print(f"[WORKAROUND] Failed to read panels_json from param: {e}")

try:
    run
except NameError:
    run = False

# Debug: Print immediately to see what GH passed
print(f"[INIT DEBUG] panels_json defined by GH: {_panels_json_from_gh}")
print(f"[INIT DEBUG] panels_json value type: {type(panels_json)}")
print(f"[INIT DEBUG] panels_json is None: {panels_json is None}")
if panels_json is not None:
    print(f"[INIT DEBUG] panels_json length: {len(panels_json) if hasattr(panels_json, '__len__') else 'N/A'}")

# Execute main
if __name__ == "__main__":
    cell_json, cell_srf, cell_types, debug_info = main()
