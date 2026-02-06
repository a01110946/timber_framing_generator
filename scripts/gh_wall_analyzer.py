# File: scripts/gh_wall_analyzer.py
"""Wall Analyzer for Grasshopper.

Extracts wall data from Revit walls via Rhino.Inside.Revit and serializes
to JSON format for use by downstream components in the modular framing pipeline.

Key Features:
1. Revit Data Extraction
   - Wall geometry (length, height, thickness)
   - Base plane and orientation
   - Opening information (doors, windows)

2. JSON Serialization
   - Converts to standardized WallData schema
   - Includes level references for RiR baking
   - Opening data with UVW coordinates

3. Visualization
   - Wall base curves for preview
   - Uses RhinoCommonFactory for correct assembly

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit

Dependencies:
    - Rhino.Geometry: Core geometry types
    - Grasshopper: DataTree for output organization
    - RhinoInside.Revit: Revit API access
    - timber_framing_generator.wall_data: Revit extraction

Performance Considerations:
    - Processing time scales with wall complexity
    - Opening extraction adds overhead
    - Typical wall processes in < 100ms

Usage:
    1. Connect Revit walls to 'walls' input
    2. Set 'run' to True to execute
    3. Connect 'walls_json' to Panel Decomposer component

Input Requirements:
    Walls (walls) - list[Revit.Wall]:
        List of Revit wall elements
        Required: Yes
        Access: List

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Walls JSON (walls_json) - str:
        JSON string containing wall data for all walls

    Wall Curves (wall_curves) - DataTree[Curve]:
        Wall base curves for visualization

    Debug Info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Uses RhinoInside.Revit for Revit API access
    - Converts Revit coordinates to Rhino world space
    - Opening positions in UVW wall-relative coordinates

Error Handling:
    - No Revit document returns error in debug_info
    - Failed wall extraction logged but doesn't halt
    - Invalid walls skipped with warning

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
clr.AddReference("RhinoInside.Revit")

# Rhino / Grasshopper
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path
from RhinoInside.Revit import Revit

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

from src.timber_framing_generator.wall_data.revit_data_extractor import (
    extract_wall_data_from_revit
)
from src.timber_framing_generator.core.json_schemas import (
    WallData, Point3D, Vector3D, PlaneData, OpeningData,
    serialize_wall_data, FramingJSONEncoder
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Wall Analyzer"
COMPONENT_NICKNAME = "WallAnalyze"
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
        ("Walls", "walls", "List of Revit wall elements",
         Grasshopper.Kernel.GH_ParamAccess.list),
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
        ("Walls JSON", "walls_json", "JSON string containing wall data"),
        ("Wall Curves", "wall_curves", "Wall base curves for visualization"),
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

def validate_inputs(walls, run):
    """Validate component inputs.

    Args:
        walls: List of Revit wall elements
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not walls:
        return False, "No walls provided"

    return True, None


def convert_wall_data_to_schema(wall_data, wall_id):
    """Convert extracted wall data dict to WallData schema.

    Args:
        wall_data: Dictionary from extract_wall_data_from_revit()
        wall_id: Unique wall identifier

    Returns:
        WallData instance ready for JSON serialization
    """
    # Extract base plane
    base_plane = wall_data.get('base_plane')
    if base_plane:
        plane_data = PlaneData(
            origin=Point3D.from_rhino(base_plane.Origin),
            x_axis=Vector3D.from_rhino(base_plane.XAxis),
            y_axis=Vector3D.from_rhino(base_plane.YAxis),
            z_axis=Vector3D.from_rhino(base_plane.ZAxis),
        )
    else:
        plane_data = PlaneData(
            origin=Point3D(0, 0, 0),
            x_axis=Vector3D(1, 0, 0),
            y_axis=Vector3D(0, 1, 0),
            z_axis=Vector3D(0, 0, 1),
        )

    # Extract Revit level IDs for RiR baking
    base_level = wall_data.get('base_level')
    top_level = wall_data.get('top_level')
    base_level_id = base_level.Id.IntegerValue if base_level else None
    top_level_id = top_level.Id.IntegerValue if top_level else None

    # Extract base curve endpoints
    base_curve = wall_data.get('wall_base_curve')
    if base_curve:
        curve_start = Point3D.from_rhino(base_curve.PointAtStart)
        curve_end = Point3D.from_rhino(base_curve.PointAtEnd)
    else:
        curve_start = Point3D(0, 0, 0)
        curve_end = Point3D(1, 0, 0)

    # Convert openings
    openings = []
    wall_length = float(wall_data.get('wall_length', 0))  # NEW CODE: Get wall length for validation
    for opening in wall_data.get('openings', []):
        o_type = opening.get('opening_type', opening.get('type', 'window'))
        u_start = float(opening.get('start_u_coordinate', opening.get('u_start', 0)))
        width = float(opening.get('rough_width', opening.get('width', 0)))
        height = float(opening.get('rough_height', opening.get('height', 0)))
        u_end = float(opening.get('u_end', u_start + width))

        # NEW CODE: Validate opening is within wall bounds
        if u_start < 0 or u_end > wall_length:
            print(f"WARNING: Skipping opening - outside wall bounds "
                  f"(u={u_start:.2f} to {u_end:.2f}, wall_length={wall_length:.2f})")
            continue

        sill_height = opening.get('base_elevation_relative_to_wall_base',
                                  opening.get('sill_height', 0))
        if sill_height is None:
            sill_height = 0
        v_start = float(sill_height)
        v_end = float(opening.get('v_end', v_start + height))

        opening_data = OpeningData(
            id=str(opening.get('id', '')),
            opening_type=o_type,
            u_start=u_start,
            u_end=u_end,
            v_start=v_start,
            v_end=v_end,
            width=width,
            height=height,
            sill_height=sill_height,
        )
        openings.append(opening_data)

    return WallData(
        wall_id=wall_id,
        wall_length=float(wall_data.get('wall_length', 0)),
        wall_height=float(wall_data.get('wall_height', 0)),
        wall_thickness=float(wall_data.get('wall_thickness', 0.5)),
        base_elevation=float(wall_data.get('wall_base_elevation', 0)),
        top_elevation=float(wall_data.get('wall_top_elevation', 0)),
        base_plane=plane_data,
        base_curve_start=curve_start,
        base_curve_end=curve_end,
        openings=openings,
        is_exterior=wall_data.get('is_exterior_wall', False),
        is_flipped=wall_data.get('is_flipped', False),
        wall_type=wall_data.get('wall_type'),
        wall_assembly=wall_data.get('wall_assembly'),
        base_level_id=base_level_id,
        top_level_id=top_level_id,
        metadata={
            'revit_id': wall_id,
            'has_cells': 'cells' in wall_data,
        }
    )


def process_walls(walls_input, doc):
    """Process all walls through extraction.

    Args:
        walls_input: List of Revit wall elements
        doc: Revit document

    Returns:
        Tuple of (wall_data_list, wall_curves_tree, log_lines)
    """
    wall_data_list = []
    wall_curves = DataTree[object]()
    log_lines = [f"Processing {len(walls_input)} walls..."]
    factory = get_factory()

    for i, wall in enumerate(walls_input):
        try:
            wall_id = str(wall.Id.IntegerValue)
            data = extract_wall_data_from_revit(wall, doc)

            if data:
                wall_data = convert_wall_data_to_schema(data, wall_id)
                wall_data_list.append(wall_data)

                # Add base curve for visualization
                base_curve = data.get('wall_base_curve')
                if base_curve:
                    start_pt = base_curve.PointAtStart
                    end_pt = base_curve.PointAtEnd
                    rc_curve = factory.create_line_curve(
                        (float(start_pt.X), float(start_pt.Y), float(start_pt.Z)),
                        (float(end_pt.X), float(end_pt.Y), float(end_pt.Z))
                    )
                    if rc_curve:
                        wall_curves.Add(rc_curve, GH_Path(i))

                log_lines.append(
                    f"Wall {i} (ID:{wall_id}): L={wall_data.wall_length:.2f}', "
                    f"H={wall_data.wall_height:.2f}', "
                    f"Openings={len(wall_data.openings)}"
                )
            else:
                log_lines.append(f"Wall {i}: FAILED - No data extracted")

        except Exception as e:
            log_lines.append(f"Wall {i}: ERROR - {str(e)}")

    return wall_data_list, wall_curves, log_lines

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Returns:
        tuple: (walls_json, wall_curves, debug_info)
    """
    setup_component()

    # Initialize outputs
    walls_json = "[]"
    wall_curves = DataTree[object]()
    log_lines = []

    try:
        # Ensure walls is a list
        walls_input = walls
        if not isinstance(walls, (list, tuple)):
            walls_input = [walls] if walls else []

        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_input, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            return walls_json, wall_curves, error_msg

        # Get Revit document
        doc = Revit.ActiveDBDocument
        if doc is None:
            log_error("No active Revit document")
            return walls_json, wall_curves, "ERROR: No active Revit document"

        log_lines.append(f"Wall Analyzer v1.1")
        log_lines.append(f"Walls: {len(walls_input)}")
        log_lines.append("")

        # Process walls
        wall_data_list, wall_curves, process_log = process_walls(walls_input, doc)
        log_lines.extend(process_log)

        # Serialize to JSON
        if wall_data_list:
            wall_dicts = [asdict(w) for w in wall_data_list]
            walls_json = json.dumps(wall_dicts, cls=FramingJSONEncoder, indent=2)
            log_lines.append("")
            log_lines.append(f"Success: Serialized {len(wall_data_list)} walls to JSON")
        else:
            log_lines.append("")
            log_lines.append("Warning: No walls were successfully processed")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_lines.append(f"ERROR: {str(e)}")
        log_lines.append(traceback.format_exc())

    return walls_json, wall_curves, "\n".join(log_lines)

# =============================================================================
# Execution
# =============================================================================

# Set default values for optional inputs
try:
    walls
except NameError:
    walls = None

try:
    run
except NameError:
    run = False

# Execute main
if __name__ == "__main__":
    walls_json, wall_curves, debug_info = main()
