# File: scripts/gh_baking_data_parser.py
"""
GHPython Component: Baking Data Parser

Flattens the nested baking_data_json structure into parallel lists suitable
for Grasshopper's data matching requirements.

Inputs:
    baking_data_json (JSON) - str:
        JSON string from Revit Baker component
        Required: Yes
        Access: Item

    filter_classification (Filter) - str:
        Optional filter: "column", "beam", or empty for all
        Required: No (defaults to all)
        Access: Item

    run (Run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    wall_ids (WID) - list[str]:
        Wall IDs (one per member, for grouping/data matching)

    element_ids (EID) - list[str]:
        Element IDs

    element_types (Type) - list[str]:
        Element types (stud, bottom_plate, etc.)

    classifications (Class) - list[str]:
        Classifications (column or beam)

    profile_names (Prof) - list[str]:
        Profile names (350S162-54, 2x4, etc.)

    revit_type_names (RType) - list[str]:
        Matched Revit type names

    csr_angles (CSR) - list[float]:
        Cross-Section Rotation angles in degrees (beams only, 0.0 for columns)

    geometry_indices (GIdx) - list[int]:
        Indices linking to column_curves/beam_curves DataTrees

    column_planes (ColPln) - list[Plane]:
        Orientation planes for columns (use to update Location after creation).
        For beams, this will be None/invalid plane.

    base_level_ids (BLvl) - list[int]:
        Base level IDs (from wall, per member)

    top_level_ids (TLvl) - list[int]:
        Top level IDs (from wall, per member)

    centerline_starts (PtS) - list[Point3d]:
        Centerline start points

    centerline_ends (PtE) - list[Point3d]:
        Centerline end points

    debug_info (Info) - str:
        Processing summary

Usage:
    1. Connect 'baking_data_json' from Revit Baker
    2. Optionally set 'filter_classification' to "column" or "beam"
    3. Set 'run' to True
    4. Connect outputs to downstream components

Notes:
    - All outputs are parallel lists with the same length
    - base_level_id and top_level_id are inherited from the wall for each member
    - Use filter_classification to get only columns or beams for RiR components
    - geometry_index links to the corresponding curve in column_curves or beam_curves
    - column_planes contains valid Plane objects for columns (for Location update)
    - column_planes contains Plane.Unset for beams (use csr_angles instead)

Column Orientation Workflow:
    1. Create columns using column_curves from Revit Baker
    2. After creation, update column Location using column_planes to set orientation
    3. The plane's X-axis controls where the C-section lips face

Extending This Component (Adding New Fields):
    To add a new output field, follow these steps:

    IMPORTANT: In GHPython, the NickName becomes the Python variable name!
    Format: (DisplayName, variable_name, Description)

    1. Add to OUTPUT_CONFIG in setup_component():
       ```
       ("My New Field", "my_new_field", "Description of my new field"),
       ```

    2. Initialize the output list at the top of Main Execution section:
       ```
       my_new_field = []
       ```

    3. Append to it inside the member processing loop (after "# Extract all
       member properties" comment):
       ```
       # For member-level properties:
       my_new_field.append(member.get("my_json_key", default_value))

       # For wall-level properties (inherited per member):
       my_new_field.append(wall_data.get("my_wall_key", default_value))
       ```

    4. (Optional) Add to debug output counts for verification:
       ```
       f"  my_new_field: {len(my_new_field)}",
       ```

    Example - Adding a "cell_id" output:
       Step 1: ("Cell IDs", "cell_ids", "Cell IDs for each member"),
       Step 2: cell_ids = []
       Step 3: cell_ids.append(member.get("cell_id", ""))
       Step 4: f"  cell_ids: {len(cell_ids)}",

Environment:
    Rhino 8, Grasshopper, Python component (CPython 3)

Author: Timber Framing Generator Project
Version: 1.0.0
"""

import sys
import json

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================
_modules_to_clear = [k for k in sys.modules.keys() if 'timber_framing_generator' in k]
for mod in _modules_to_clear:
    del sys.modules[mod]
print(f"[RELOAD] Cleared {len(_modules_to_clear)} cached timber_framing_generator modules")

# =============================================================================
# RhinoCommon / Grasshopper Setup
# =============================================================================

import clr
clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')

import Rhino.Geometry as rg
import Grasshopper

# =============================================================================
# Project Setup (for RhinoCommonFactory)
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Component Constants
# =============================================================================

COMPONENT_NAME = "Baking Data Parser"
COMPONENT_NICKNAME = "BakeParser"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Revit"

# Input configuration: (Name, NickName, Description, Access)
# IMPORTANT: NickName becomes the Python variable name in GHPython!
INPUT_CONFIG = [
    ("Baking Data JSON", "baking_data_json", "JSON string from Revit Baker component",
     Grasshopper.Kernel.GH_ParamAccess.item),
    ("Filter Classification", "filter_classification", "Optional: 'column', 'beam', or empty for all",
     Grasshopper.Kernel.GH_ParamAccess.item),
    ("Run", "run", "Set to True to execute",
     Grasshopper.Kernel.GH_ParamAccess.item),
]

# Output configuration: (Name, NickName, Description)
# IMPORTANT: NickName becomes the Python variable name in GHPython!
# Note: Output[0] is reserved for 'out' - these start at index 1
OUTPUT_CONFIG = [
    ("Wall IDs", "wall_ids", "Wall IDs (one per member)"),
    ("Element IDs", "element_ids", "Element IDs"),
    ("Element Types", "element_types", "Element types (stud, bottom_plate, etc.)"),
    ("Classifications", "classifications", "Classifications (column or beam)"),
    ("Profile Names", "profile_names", "Profile names"),
    ("Revit Type Names", "revit_type_names", "Matched Revit type names"),
    ("CSR Angles", "csr_angles", "Cross-Section Rotation angles (beams only)"),
    ("Geometry Indices", "geometry_indices", "Indices into column_curves/beam_curves"),
    ("Base Level IDs", "base_level_ids", "Base level IDs (from wall)"),
    ("Top Level IDs", "top_level_ids", "Top level IDs (from wall)"),
    ("Centerline Starts", "centerline_starts", "Centerline start points (Point3d)"),
    ("Centerline Ends", "centerline_ends", "Centerline end points (Point3d)"),
    ("Column Planes", "column_planes", "Orientation planes for columns (Plane)"),
    ("Debug Info", "debug_info", "Processing summary"),
]

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component.

    This function handles:
    1. Setting component metadata (name, category, etc.)
    2. Configuring input parameters
    3. Configuring output parameters

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input
    for i, (name, nick, desc, access) in enumerate(INPUT_CONFIG):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output
    for i, (name, nick, desc) in enumerate(OUTPUT_CONFIG):
        idx = i + 1  # Skip Output[0] which is 'out'
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc


# Run setup on component load
setup_component()

# =============================================================================
# Main Execution
# =============================================================================

# Initialize all outputs as empty lists
wall_ids = []
element_ids = []
element_types = []
classifications = []
profile_names = []
revit_type_names = []
csr_angles = []
geometry_indices = []
base_level_ids = []
top_level_ids = []
centerline_starts = []
centerline_ends = []
column_planes = []
debug_info = ""

if run and baking_data_json:
    try:
        # Get RhinoCommon factory for plane creation
        rc_factory = get_factory()

        # Handle Grasshopper wrapping
        json_input = baking_data_json
        if isinstance(baking_data_json, (list, tuple)):
            json_input = baking_data_json[0] if baking_data_json else ""

        # Parse JSON
        data = json.loads(json_input)

        # Check for error in JSON
        if "error" in data:
            debug_info = f"Error in baking_data_json: {data['error']}"
        else:
            # Get filter classification (normalize to lowercase)
            filter_class = None
            if filter_classification:
                if isinstance(filter_classification, (list, tuple)):
                    filter_class = str(filter_classification[0]).lower() if filter_classification else None
                else:
                    filter_class = str(filter_classification).lower()
                # Validate filter
                if filter_class not in ("column", "beam"):
                    filter_class = None

            # Process walls and members
            walls_data = data.get("walls", {})
            total_members = 0
            filtered_members = 0

            for wid, wall_data in walls_data.items():
                # Get wall-level properties
                wall_base_level = wall_data.get("base_level_id")
                wall_top_level = wall_data.get("top_level_id")

                # Process each member in this wall
                for member in wall_data.get("members", []):
                    total_members += 1

                    # Apply classification filter if specified
                    member_class = member.get("classification", "")
                    if filter_class and member_class != filter_class:
                        continue

                    filtered_members += 1

                    # Extract all member properties
                    wall_ids.append(wid)
                    element_ids.append(member.get("id", ""))
                    element_types.append(member.get("element_type", ""))
                    classifications.append(member_class)
                    profile_names.append(member.get("profile_name", ""))
                    revit_type_names.append(member.get("revit_type_name", ""))
                    csr_angles.append(member.get("csr_angle", 0.0))
                    geometry_indices.append(member.get("geometry_index", -1))

                    # Wall-level properties (inherited per member)
                    base_level_ids.append(wall_base_level)
                    top_level_ids.append(wall_top_level)

                    # Centerline points as Point3d
                    start = member.get("centerline_start", {})
                    end = member.get("centerline_end", {})
                    centerline_starts.append(rg.Point3d(
                        start.get("x", 0.0),
                        start.get("y", 0.0),
                        start.get("z", 0.0)
                    ))
                    centerline_ends.append(rg.Point3d(
                        end.get("x", 0.0),
                        end.get("y", 0.0),
                        end.get("z", 0.0)
                    ))

                    # Column orientation planes (for updating Location after creation)
                    # Only valid for columns; beams use CSR instead
                    # CRITICAL: Use RhinoCommonFactory to create planes from correct assembly
                    if member_class == "column":
                        plane_origin = member.get("plane_origin", {})
                        plane_x_axis = member.get("plane_x_axis", {})

                        # Extract coordinates as Python floats
                        ox = float(plane_origin.get("x", 0.0))
                        oy = float(plane_origin.get("y", 0.0))
                        oz = float(plane_origin.get("z", 0.0))

                        ax = float(plane_x_axis.get("x", 1.0))
                        ay = float(plane_x_axis.get("y", 0.0))
                        az = float(plane_x_axis.get("z", 0.0))

                        # Normalize x_axis
                        mag = (ax*ax + ay*ay + az*az) ** 0.5
                        if mag > 0:
                            ax, ay, az = ax/mag, ay/mag, az/mag

                        # Y-axis = Z × X (for vertical columns, Z = world Z)
                        # Cross product: (0,0,1) × (ax,ay,az) = (-ay, ax, 0)
                        yx, yy, yz = -ay, ax, 0.0
                        y_mag = (yx*yx + yy*yy + yz*yz) ** 0.5
                        if y_mag > 0:
                            yx, yy, yz = yx/y_mag, yy/y_mag, yz/y_mag

                        # Create plane using RhinoCommonFactory
                        rc_plane = rc_factory.create_plane(
                            (ox, oy, oz),  # origin
                            (ax, ay, az),  # x_axis
                            (yx, yy, yz)   # y_axis
                        )
                        column_planes.append(rc_plane)
                    else:
                        # Beams don't use planes - append None
                        column_planes.append(None)

            # Build debug summary
            summary = data.get("summary", {})
            # Count valid column planes (not None)
            valid_planes = sum(1 for p in column_planes if p is not None)
            debug_lines = [
                "Baking Data Parser",
                "=" * 40,
                f"Material System: {summary.get('material_system', 'unknown')}",
                f"Total Walls: {len(walls_data)}",
                f"Total Members in JSON: {total_members}",
                f"Filter: {filter_class if filter_class else 'None (all)'}",
                f"Output Members: {filtered_members}",
                "",
                "Output Counts:",
                f"  wall_ids: {len(wall_ids)}",
                f"  element_ids: {len(element_ids)}",
                f"  element_types: {len(element_types)}",
                f"  classifications: {len(classifications)}",
                f"  profile_names: {len(profile_names)}",
                f"  revit_type_names: {len(revit_type_names)}",
                f"  csr_angles: {len(csr_angles)}",
                f"  geometry_indices: {len(geometry_indices)}",
                f"  base_level_ids: {len(base_level_ids)}",
                f"  top_level_ids: {len(top_level_ids)}",
                f"  centerline_starts: {len(centerline_starts)}",
                f"  centerline_ends: {len(centerline_ends)}",
                f"  column_planes: {len(column_planes)} ({valid_planes} valid)",
            ]

            # Show sample data
            if filtered_members > 0:
                debug_lines.append("")
                debug_lines.append("Sample (first 3 members):")
                for i in range(min(3, filtered_members)):
                    debug_lines.append(f"  [{i}] {element_types[i]} | {revit_type_names[i]} | CSR={csr_angles[i]}°")

            debug_info = "\n".join(debug_lines)

    except json.JSONDecodeError as e:
        debug_info = f"JSON Parse Error: {str(e)}"
    except Exception as e:
        import traceback
        debug_info = f"ERROR: {str(e)}\n{traceback.format_exc()}"

elif not run:
    debug_info = "Set 'run' to True to execute"
elif not baking_data_json:
    debug_info = "No baking_data_json input provided"

# Print debug_info so it appears in the 'out' output
print(debug_info)
