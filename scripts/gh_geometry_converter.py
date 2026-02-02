# File: scripts/gh_geometry_converter.py
"""Geometry Converter for Grasshopper.

Converts framing elements JSON to RhinoCommon geometry (Breps and Curves).
This is the final stage of the modular pipeline, handling the assembly
mismatch issue by using the RhinoCommonFactory.

Key Features:
1. Assembly-Safe Geometry Creation
   - Uses RhinoCommonFactory for correct RhinoCommon assembly
   - Avoids Rhino3dmIO/RhinoCommon mismatch issues
   - Geometry verified for Grasshopper compatibility

2. Flexible Filtering
   - Filter by element type (stud, plate, header, etc.)
   - Filter by wall ID for single-wall visualization
   - Multiple output organizations (flat, by-type, by-wall)

3. Multiple Output Formats
   - Flat list of all Breps
   - DataTree organized by element type
   - DataTree organized by wall ID
   - Centerline curves for visualization

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry types
    - Grasshopper: DataTree for organized output
    - timber_framing_generator.utils.geometry_factory: RhinoCommonFactory
    - timber_framing_generator.core.json_schemas: JSON deserialization

Performance Considerations:
    - Processing time scales linearly with element count
    - Memory usage proportional to geometry complexity
    - Large walls (>1000 elements) may take several seconds

Usage:
    1. Connect 'framing_json' from Framing Generator
    2. Optionally set 'filter_types' to filter specific element types
    3. Optionally set 'filter_wall' to show only one wall's framing
    4. Set 'run' to True to execute
    5. Connect 'breps' to display or bake geometry

Input Requirements:
    Framing JSON (framing_json) - str:
        JSON string from Framing Generator containing framing elements
        Required: Yes
        Access: Item

    Filter Types (filter_types) - str:
        Comma-separated element types to include (e.g., "stud,plate")
        Required: No (shows all types)
        Access: Item

    Filter Wall (filter_wall) - str:
        Wall ID to filter (e.g., "1234567" for single wall)
        Required: No (shows all walls)
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Breps (breps) - list[Brep]:
        All framing elements as Brep geometry

    By Type (by_type) - DataTree[Brep]:
        Breps organized by element type in branches

    By Wall (by_wall) - DataTree[Brep]:
        Breps organized by wall ID in branches

    Centerlines (centerlines) - list[Curve]:
        Centerline curves for each element

    Element IDs (element_ids) - list[str]:
        Element IDs for selection feedback

    Wall IDs (wall_ids) - list[str]:
        List of unique wall IDs found in data

    Debug Info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Uses RhinoCommonFactory to ensure correct assembly
    - Box geometry created from centerline + profile dimensions
    - Wall direction from element metadata for correct orientation

Error Handling:
    - Invalid JSON returns empty outputs with error in debug_info
    - Missing elements logged but don't halt execution
    - Invalid geometry creation logged and skipped

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

from src.timber_framing_generator.utils.geometry_factory import get_factory
from src.timber_framing_generator.core.json_schemas import (
    deserialize_framing_results, FramingElementData, Point3D
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Geometry Converter"
COMPONENT_NICKNAME = "GeoConv"
COMPONENT_MESSAGE = "v1.1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Geometry"

# Element type to branch index mapping
TYPE_ORDER = [
    "bottom_plate", "top_plate", "stud", "king_stud", "trimmer",
    "header", "sill", "header_cripple", "sill_cripple", "blocking",
    "track", "web_stiffener", "bridging",
]

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
        ("Framing JSON", "framing_json", "JSON string from Framing Generator",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Filter Types", "filter_types", "Comma-separated element types to include",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Filter Wall", "filter_wall", "Wall ID to filter (single wall view)",
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
        ("Breps", "breps", "All framing elements as Breps"),
        ("By Type", "by_type", "DataTree of Breps by element type"),
        ("By Wall", "by_wall", "DataTree of Breps by wall ID"),
        ("Centerlines", "centerlines", "Centerline curves for each element"),
        ("Element IDs", "element_ids", "Element IDs for selection"),
        ("Wall IDs", "wall_ids", "Unique wall IDs found in data"),
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

def validate_inputs(framing_json, run):
    """Validate component inputs.

    Args:
        framing_json: JSON string with framing data
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not framing_json:
        return False, "No framing_json input provided"

    try:
        json.loads(framing_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in framing_json: {e}"

    return True, None


def element_type_to_branch_index(element_type):
    """Map element type to a consistent branch index.

    Args:
        element_type: Element type string (e.g., "stud", "bottom_plate")

    Returns:
        Integer index for GH_Path
    """
    elem_lower = element_type.lower()
    if elem_lower in TYPE_ORDER:
        return TYPE_ORDER.index(elem_lower)
    else:
        return len(TYPE_ORDER) + hash(element_type) % 100


def create_brep_from_element(element, factory):
    """Create a Brep from a framing element.

    Args:
        element: FramingElementData with centerline and profile info
        factory: RhinoCommonFactory instance

    Returns:
        Brep geometry or None if creation fails
    """
    start = element.centerline_start
    end = element.centerline_end

    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z
    length = (dx*dx + dy*dy + dz*dz) ** 0.5

    if length < 0.001:
        return None

    direction = (dx/length, dy/length, dz/length)

    # Extract wall direction from element metadata
    wall_x_axis = None
    wall_z_axis = None
    if element.metadata:
        wall_x_axis = element.metadata.get('wall_x_axis')
        wall_z_axis = element.metadata.get('wall_z_axis')

    return factory.create_box_brep_from_centerline(
        start_point=(start.x, start.y, start.z),
        direction=direction,
        length=length,
        width=element.profile.width,
        depth=element.profile.depth,
        wall_x_axis=wall_x_axis,
        wall_z_axis=wall_z_axis,
    )


def create_centerline_from_element(element, factory):
    """Create a LineCurve centerline from a framing element.

    Args:
        element: FramingElementData with centerline info
        factory: RhinoCommonFactory instance

    Returns:
        LineCurve geometry or None if creation fails
    """
    start = element.centerline_start
    end = element.centerline_end

    return factory.create_line_curve(
        (start.x, start.y, start.z),
        (end.x, end.y, end.z)
    )


def get_element_wall_id(element):
    """Extract wall ID from element metadata or cell_id.

    Args:
        element: FramingElementData instance

    Returns:
        Wall ID string
    """
    if element.metadata and element.metadata.get('wall_id'):
        return element.metadata['wall_id']
    elif element.cell_id:
        parts = element.cell_id.split('_')
        if len(parts) >= 2:
            return parts[0]
    elif '_' in element.id:
        parts = element.id.split('_')
        if len(parts) >= 1 and parts[0].isdigit():
            return parts[0]
    return 'unknown'


def process_geometry(results, filter_types_list, wall_filter, factory):
    """Process all elements to geometry.

    Args:
        results: Deserialized FramingResults
        filter_types_list: List of element types to include (or None)
        wall_filter: Wall ID to filter (or None)
        factory: RhinoCommonFactory instance

    Returns:
        Tuple of (breps, type_groups, wall_groups, centerlines, element_ids, unique_walls)
    """
    breps = []
    type_groups = {}
    type_names = {}
    wall_groups = {}
    centerlines = []
    element_ids = []
    unique_walls = set()

    for element in results.elements:
        elem_type = element.element_type.lower()
        elem_wall_id = get_element_wall_id(element)
        unique_walls.add(elem_wall_id)

        # Apply filters
        if filter_types_list and elem_type not in filter_types_list:
            continue
        if wall_filter and elem_wall_id != wall_filter:
            continue

        # Create Brep
        brep = create_brep_from_element(element, factory)
        if brep:
            breps.append(brep)

            # Group by type
            branch_idx = element_type_to_branch_index(elem_type)
            if branch_idx not in type_groups:
                type_groups[branch_idx] = []
                type_names[branch_idx] = elem_type
            type_groups[branch_idx].append(brep)

            # Group by wall
            if elem_wall_id not in wall_groups:
                wall_groups[elem_wall_id] = []
            wall_groups[elem_wall_id].append(brep)

            # Create centerline
            centerline = create_centerline_from_element(element, factory)
            if centerline:
                centerlines.append(centerline)

            element_ids.append(element.id)

    return breps, type_groups, type_names, wall_groups, centerlines, element_ids, unique_walls

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Returns:
        tuple: (breps, by_type, by_wall, centerlines, element_ids, wall_ids, debug_info)
    """
    setup_component()

    # Initialize outputs
    breps = []
    by_type = DataTree[object]()
    by_wall = DataTree[object]()
    centerlines = []
    element_ids = []
    wall_ids = []
    log_lines = []

    try:
        # Unwrap Grasshopper list wrappers
        framing_json_input = framing_json
        if isinstance(framing_json, (list, tuple)):
            framing_json_input = framing_json[0] if framing_json else None

        filter_types_input = filter_types if filter_types else None
        if isinstance(filter_types, (list, tuple)):
            filter_types_input = filter_types[0] if filter_types else None

        filter_wall_input = filter_wall if filter_wall else None
        if isinstance(filter_wall, (list, tuple)):
            filter_wall_input = filter_wall[0] if filter_wall else None

        # Validate inputs
        is_valid, error_msg = validate_inputs(framing_json_input, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            return breps, by_type, by_wall, centerlines, element_ids, wall_ids, error_msg

        # Get geometry factory
        factory = get_factory()

        # Parse JSON
        results = deserialize_framing_results(framing_json_input)

        log_lines.append(f"Geometry Converter v1.1")
        log_lines.append(f"Material System: {results.material_system}")
        log_lines.append(f"Total Elements: {len(results.elements)}")
        log_lines.append("")

        # Parse filter_types
        filter_types_list = None
        if filter_types_input:
            filter_types_list = [f.strip().lower() for f in filter_types_input.split(',')]
            log_lines.append(f"Type Filter: {filter_types_list}")

        # Parse filter_wall
        wall_filter = str(filter_wall_input).strip() if filter_wall_input else None
        if wall_filter:
            log_lines.append(f"Wall Filter: {wall_filter}")

        # Process geometry
        breps, type_groups, type_names, wall_groups, centerlines, element_ids, unique_walls = \
            process_geometry(results, filter_types_list, wall_filter, factory)

        # Build by_type DataTree
        for branch_idx in sorted(type_groups.keys()):
            path = GH_Path(branch_idx)
            for brep in type_groups[branch_idx]:
                by_type.Add(brep, path)

        # Build by_wall DataTree
        sorted_walls = sorted(wall_groups.keys())
        wall_id_to_branch = {wid: idx for idx, wid in enumerate(sorted_walls)}
        for wall_id_key in sorted_walls:
            path = GH_Path(wall_id_to_branch[wall_id_key])
            for brep in wall_groups[wall_id_key]:
                by_wall.Add(brep, path)

        # Set wall_ids output
        wall_ids = sorted(unique_walls)

        # Summary
        log_lines.append("")
        log_lines.append(f"Unique Walls: {len(unique_walls)}")
        log_lines.append(f"Wall IDs: {sorted(unique_walls)}")
        log_lines.append("")
        log_lines.append("Elements by Type:")
        for branch_idx in sorted(type_groups.keys()):
            elem_type = type_names[branch_idx]
            count = len(type_groups[branch_idx])
            log_lines.append(f"  [{branch_idx}] {elem_type}: {count}")

        log_lines.append("")
        log_lines.append(f"Total Breps: {len(breps)}")
        log_lines.append(f"Total Centerlines: {len(centerlines)}")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_lines.append(f"ERROR: {str(e)}")
        log_lines.append(traceback.format_exc())

    return breps, by_type, by_wall, centerlines, element_ids, wall_ids, "\n".join(log_lines)

# =============================================================================
# Execution
# =============================================================================

# Set default values for optional inputs
try:
    framing_json
except NameError:
    framing_json = None

try:
    filter_types
except NameError:
    filter_types = None

try:
    filter_wall
except NameError:
    filter_wall = None

try:
    run
except NameError:
    run = False

# Execute main
if __name__ == "__main__":
    breps, by_type, by_wall, centerlines, element_ids, wall_ids, debug_info = main()
