# File: scripts/gh_revit_baker.py
"""
GHPython Component: Revit Baker

Transforms framing elements into outputs suitable for Rhino.Inside.Revit's
Add Structural Column and Add Structural Beam components.

This component classifies elements as vertical (columns) vs horizontal (beams),
maps profile names to Revit family types, computes Cross-Section Rotation (CSR)
for CFS beams, and creates placement planes for vertical columns.

CRITICAL: Vertical columns use PLANE-BASED placement to avoid centerline offset.
See docs/ai/ai-rir-revit-patterns.md for details on why curves cause offset issues.

Inputs:
    elements_json: JSON string from Framing Generator component
    wall_json: JSON string from Wall Analyzer (for level information)
    revit_column_types: List of available Revit Structural Column family types
    revit_beam_types: List of available Revit Structural Framing family types
    type_mapping: Optional dict mapping profile names to Revit type names
    mirror_opening_studs: Boolean - if True, king studs/trimmers on opposite
                          sides of openings face each other (default: False)
    run: Boolean to trigger execution

Outputs:
    baking_data_json: JSON string with all member data organized by wall.
                      For columns: includes plane_origin and plane_x_axis for
                      orientation control. For beams: includes csr_angle.
    column_curves: DataTree of centerlines for vertical columns.
                   Connect to RiR "Add Structural Column" Curve input.
    beam_curves: DataTree of centerlines for horizontal elements (plates, etc.)
                 These use CSR parameter for orientation.
    debug_info: Processing summary

Note on Column Orientation:
    Column orientation data (plane_origin, plane_x_axis) is in baking_data_json.
    Use the Baking Data Parser to extract and create Rhino Planes for updating
    column Location after creation. This follows the JSON-based pattern.

JSON Output Structure:
    {
      "walls": {
        "<wall_id>": {
          "base_level_id": <int>,
          "top_level_id": <int>,
          "members": [
            {
              "id": "<element_id>",
              "element_type": "<type>",
              "classification": "column"|"beam",
              "profile_name": "<profile>",
              "revit_type_name": "<matched_type>",
              "csr_angle": <float>,  // For beams only; columns use plane orientation
              "centerline_start": {"x": <float>, "y": <float>, "z": <float>},
              "centerline_end": {"x": <float>, "y": <float>, "z": <float>},
              "plane_origin": {"x": <float>, "y": <float>, "z": <float>},  // Columns only
              "plane_x_axis": {"x": <float>, "y": <float>, "z": <float>},  // Columns only
              "geometry_index": <int>
            },
            ...
          ]
        },
        ...
      },
      "summary": {
        "total_walls": <int>,
        "total_columns": <int>,
        "total_beams": <int>,
        "material_system": "<system>"
      }
    }

Usage:
    1. Connect 'elements_json' from Framing Generator
    2. Connect 'wall_json' from Wall Analyzer
    3. Connect Revit family types (use RiR type pickers)
    4. Optionally provide 'type_mapping' for custom profile-to-type mapping
    5. Set 'mirror_opening_studs' to True for mirrored king stud orientation
    6. Set 'run' to True
    7. Connect column_planes to RiR "Add Structural Column" (Plane input)
    8. Connect beam_curves + CSR to RiR "Add Structural Framing"
"""

import sys
import json

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
clr.AddReference('RhinoInside.Revit')

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path
from RhinoInside.Revit import Revit

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
from src.timber_framing_generator.core.material_system import ElementType

# =============================================================================
# Element Classification
# =============================================================================

# Vertical members -> Structural Columns
COLUMN_ELEMENT_TYPES = {
    ElementType.STUD.value,
    ElementType.KING_STUD.value,
    ElementType.TRIMMER.value,
    ElementType.HEADER_CRIPPLE.value,
    ElementType.SILL_CRIPPLE.value,
}

# Horizontal members -> Structural Beams/Framing
BEAM_ELEMENT_TYPES = {
    # Timber
    ElementType.BOTTOM_PLATE.value,
    ElementType.TOP_PLATE.value,
    ElementType.ROW_BLOCKING.value,
    # CFS
    ElementType.BOTTOM_TRACK.value,
    ElementType.TOP_TRACK.value,
    ElementType.BRIDGING.value,
    # Shared
    ElementType.HEADER.value,
    ElementType.SILL.value,
}

# Default type mapping for common profiles
# Maps framing generator profile names to Revit family type names
DEFAULT_TYPE_MAPPING = {
    # Timber profiles
    "2x4": "2x4",
    "2x6": "2x6",
    "2x8": "2x8",
    "2x10": "2x10",
    "2x12": "2x12",
    # CFS profiles - map to Clark Dietrich naming with (50) yield strength suffix
    # 350-series (3.5" web)
    "350S162-33": "350S162-33(50)",
    "350S162-43": "350S162-43(50)",
    "350S162-54": "350S162-54(50)",
    "350T125-33": "350T125-33(50)",
    "350T125-43": "350T125-43(50)",
    "350T125-54": "350T125-54(50)",
    # 362-series (3.625" web) - Clark Dietrich standard
    "362S162-33": "362S162-33(50)",
    "362S162-43": "362S162-43(50)",
    "362S162-54": "362S162-54(50)",
    "362T125-33": "362T125-33(50)",
    "362T125-43": "362T125-43(50)",
    "362T125-54": "362T125-54(50)",
    # 600-series (6" web)
    "600S162-33": "600S162-33(50)",
    "600S162-43": "600S162-43(50)",
    "600S162-54": "600S162-54(50)",
    "600S162-68": "600S162-68(50)",
    "600T125-33": "600T125-33(50)",
    "600T125-43": "600T125-43(50)",
    "600T125-54": "600T125-54(50)",
    # 800-series (8" web)
    "800S162-54": "800S162-54(50)",
    "800S162-68": "800S162-68(50)",
    "800T125-54": "800T125-54(50)",
    "800T125-68": "800T125-68(50)",
}


# =============================================================================
# Helper Functions
# =============================================================================

def classify_element(element_type: str) -> str:
    """
    Classify an element as 'column' or 'beam' based on its type.

    Args:
        element_type: Element type string from elements_json

    Returns:
        'column' for vertical members, 'beam' for horizontal members,
        'unknown' for unrecognized types
    """
    elem_type_lower = element_type.lower()

    if elem_type_lower in COLUMN_ELEMENT_TYPES:
        return "column"
    elif elem_type_lower in BEAM_ELEMENT_TYPES:
        return "beam"
    else:
        # Check by naming convention for unknown types
        if any(x in elem_type_lower for x in ['stud', 'cripple', 'trimmer']):
            return "column"
        elif any(x in elem_type_lower for x in ['plate', 'track', 'header', 'sill', 'blocking', 'bridging']):
            return "beam"
        return "unknown"


def find_matching_revit_type(profile_name: str, revit_types: list,
                              user_mapping: dict = None,
                              debug_first_n: int = 0) -> tuple:
    """
    Find a matching Revit type for a profile name.

    Matching strategy (in order):
    1. User-provided mapping (exact match)
    2. Exact match with Revit type name
    3. Profile name contained in Revit type name
    4. Default mapping
    5. Fallback to first available type

    Args:
        profile_name: Profile name from framing element (e.g., "2x4")
        revit_types: List of available Revit family types
        user_mapping: Optional dict of profile_name -> revit_type_name
        debug_first_n: If > 0, print debug info for first N calls

    Returns:
        Tuple of (matched_type, match_quality) where match_quality is:
        'exact', 'contains', 'default', 'fallback', or None
    """
    if not revit_types:
        return None, None

    profile_lower = profile_name.lower().strip()

    # Build mapping of revit type names to types
    type_name_map = {}
    type_name_list = []  # For debug output
    for rt in revit_types:
        try:
            # Get type name - handle both Revit API objects and strings
            if hasattr(rt, 'Name'):
                name = rt.Name
            elif hasattr(rt, 'get_Name'):
                name = rt.get_Name()
            else:
                name = str(rt)
            type_name_map[name.lower()] = rt
            type_name_list.append(name)
        except Exception as e:
            type_name_list.append(f"ERROR: {e}")
            continue

    # Debug output for first few calls
    if debug_first_n > 0:
        print(f"\n[TYPE MATCH DEBUG] Profile: '{profile_name}' -> '{profile_lower}'")
        print(f"  Available types ({len(type_name_list)}): {type_name_list[:5]}...")

    # 1. User-provided mapping
    if user_mapping and profile_name in user_mapping:
        target_name = user_mapping[profile_name].lower()
        if target_name in type_name_map:
            return type_name_map[target_name], 'user_mapping'
        if debug_first_n > 0:
            print(f"  User mapping '{profile_name}' -> '{user_mapping[profile_name]}' NOT FOUND in types")

    # 2. Exact match
    if profile_lower in type_name_map:
        return type_name_map[profile_lower], 'exact'

    # 3. Profile name contained in type name (e.g., "2x4" in "Stud - 2x4")
    for type_name, rt in type_name_map.items():
        if profile_lower in type_name:
            if debug_first_n > 0:
                print(f"  Contains match: '{profile_lower}' in '{type_name}'")
            return rt, 'contains'

    if debug_first_n > 0:
        print(f"  No contains match found for '{profile_lower}'")

    # 4. Default mapping
    if profile_name in DEFAULT_TYPE_MAPPING:
        default_target = DEFAULT_TYPE_MAPPING[profile_name].lower()
        if default_target in type_name_map:
            return type_name_map[default_target], 'default'
        # Also try pattern matching with default
        for type_name, rt in type_name_map.items():
            if default_target in type_name:
                return rt, 'default_contains'

    # 5. Fallback to first available type
    if revit_types:
        return revit_types[0], 'fallback'

    return None, None


def create_centerline_curve(element: FramingElementData, factory):
    """
    Create a LineCurve centerline from a framing element.

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


def create_column_plane(element: FramingElementData, wall_x_axis: tuple,
                        should_flip: bool = False) -> tuple:
    """
    Create a placement plane for a vertical column.

    CRITICAL: Vertical columns use plane-based placement to avoid the
    centerline offset issue that occurs with curve-based "Slanted" columns.
    The plane's X-axis controls the column's orientation (where C-section
    lips face).

    Args:
        element: FramingElementData with centerline info
        wall_x_axis: Tuple (x, y, z) of wall's X-axis direction
        should_flip: If True, flip X-axis 180° (for end studs, mirrored elements)

    Returns:
        Tuple of (rg.Plane, x_axis_tuple) or (None, None) if creation fails
    """
    try:
        # Origin at column base (centerline start)
        origin = rg.Point3d(
            element.centerline_start.x,
            element.centerline_start.y,
            element.centerline_start.z
        )

        # X-axis controls where C-section lips face
        # Standard: face toward wall's X-axis direction
        wall_ax = wall_x_axis[0] if wall_x_axis else 1.0
        wall_ay = wall_x_axis[1] if wall_x_axis else 0.0

        x_axis = rg.Vector3d(wall_ax, wall_ay, 0)
        x_axis.Unitize()

        # Flip for end studs, mirrored opening elements, etc.
        if should_flip:
            x_axis = -x_axis

        # Z-axis is always World Z (column goes vertical)
        z_axis = rg.Vector3d(0, 0, 1)

        # Y-axis = Z × X (right-hand rule)
        y_axis = rg.Vector3d.CrossProduct(z_axis, x_axis)
        y_axis.Unitize()

        plane = rg.Plane(origin, x_axis, y_axis)

        # Return plane and the x_axis as tuple for JSON serialization
        x_axis_tuple = (float(x_axis.X), float(x_axis.Y), float(x_axis.Z))
        return plane, x_axis_tuple

    except Exception as e:
        print(f"Error creating column plane: {e}")
        return None, None


def compute_csr_angle(element_type: str, material_system: str,
                      centerline_vector: tuple = None,
                      wall_normal: tuple = None,
                      wall_x_axis: tuple = None,
                      element_id: str = None,
                      mirror_opening_studs: bool = False,
                      is_end_stud: bool = False) -> float:
    """
    Compute Cross-Section Rotation angle for CFS elements.

    CFS (Cold-Formed Steel) profiles are C-shaped and require specific
    orientation when baked to Revit. This function returns the CSR angle
    based on element type, wall normal, and wall x_axis.

    CRITICAL INSIGHT:
    CSR rotates around the beam's centerline axis. The "local Y" direction
    (perpendicular to centerline in horizontal plane) determines where CSR 90°
    points. For blocking to face INWARD:
    - local Y = world_Z × centerline_direction
    - If local Y points opposite to wall_normal → CSR 90° = INWARD
    - If local Y points same as wall_normal → CSR 270° = INWARD

    Args:
        element_type: Element type string (e.g., "stud", "bottom_plate")
        material_system: "timber" or "cfs"
        centerline_vector: Tuple (x, y, z) of the centerline direction vector.
        wall_normal: Tuple (x, y, z) of the wall's Z-axis (outward normal).
        wall_x_axis: Tuple (x, y, z) of the wall's X-axis (run direction).
        element_id: Element ID string. Used to detect opening side for mirroring.
        mirror_opening_studs: If True, flip trimmer_0 and king_stud_1 by 180°.
        is_end_stud: If True, this is the last stud at the wall end (flip 180°).

    Returns:
        CSR angle in degrees (0, 90, 180, or 270)
    """
    # Timber elements don't need rotation
    if material_system.lower() != "cfs":
        return 0.0

    elem_lower = element_type.lower()

    # Get vector components with defaults
    vec_x, vec_y, vec_z = centerline_vector if centerline_vector else (1, 0, 0)
    norm_x, norm_y, norm_z = wall_normal if wall_normal else (0, 0, 0)
    wall_ax, wall_ay, wall_az = wall_x_axis if wall_x_axis else (1, 0, 0)

    # For vertical members, the vector is primarily Z
    is_vertical = abs(vec_z) > max(abs(vec_x), abs(vec_y))

    if is_vertical:
        # Vertical members (studs, cripples, etc.)
        VERTICAL_TYPES = {"stud", "king_stud", "trimmer",
                          "header_cripple", "sill_cripple"}

        if elem_lower in VERTICAL_TYPES:
            # =========================================================
            # Column CSR: All columns face toward wall's U vector (wall_x_axis)
            # =========================================================
            # For vertical columns, CSR rotates around the Z-axis.
            # Empirically determined from Revit testing:
            #   CSR 0°   = C-opening faces +X
            #   CSR 90°  = C-opening faces -Y (not +Y!)
            #   CSR 180° = C-opening faces -X
            #   CSR 270° = C-opening faces +Y (not -Y!)
            #
            # To face wall_x_axis direction:
            if abs(wall_ax) >= abs(wall_ay):
                # Wall runs along X
                base_csr = 0.0 if wall_ax >= 0 else 180.0
            else:
                # Wall runs along Y (note: 90°=-Y, 270°=+Y)
                base_csr = 270.0 if wall_ay >= 0 else 90.0

            # =========================================================
            # Flip logic for special studs
            # =========================================================
            should_flip = False

            # 1. End stud (last stud at wall end) - always flip
            if is_end_stud and elem_lower == "stud":
                should_flip = True

            # 2. mirror_opening_studs logic:
            #    - Flip trimmer BEFORE opening (side 0 / left): trimmer_X_0
            #    - Flip king stud AFTER opening (side 1 / right): king_stud_X_1
            if mirror_opening_studs and element_id:
                if elem_lower == "trimmer" and element_id.endswith("_0"):
                    # Trimmer before opening (left side) - flip
                    should_flip = True
                elif elem_lower == "king_stud" and element_id.endswith("_1"):
                    # King stud after opening (right side) - flip
                    should_flip = True

            if should_flip:
                return (base_csr + 180.0) % 360.0

            return base_csr

    # Horizontal members
    HORIZONTAL_TYPES = {
        "bottom_plate", "bottom_track",
        "top_plate", "top_track",
        "sill", "header",
        "row_blocking", "bridging"
    }

    if elem_lower not in HORIZONTAL_TYPES:
        return 0.0

    # =========================================================================
    # Determine if centerline matches wall x_axis direction
    # =========================================================================
    # Compute dot product to see if they point same direction
    # dot > 0 means same direction, dot < 0 means opposite
    dot_product = vec_x * wall_ax + vec_y * wall_ay + vec_z * wall_az
    centerline_matches_wall_axis = dot_product >= 0

    # =========================================================================
    # Compute local Y direction (perpendicular to centerline in horizontal plane)
    # local_Y = world_Z × centerline = (0,0,1) × (vec_x, vec_y, 0)
    #         = (-vec_y, vec_x, 0) [normalized direction]
    # =========================================================================
    # For CSR 90°, the C-opening faces local Y direction
    # We want C-opening to face INWARD (opposite of wall_normal)
    #
    # Check if local_Y points opposite to wall_normal (inward):
    # local_Y · wall_normal < 0 means local_Y points inward
    local_y_x = -vec_y  # Cross product of (0,0,1) × (vec_x, vec_y, 0)
    local_y_y = vec_x
    dot_local_y_normal = local_y_x * norm_x + local_y_y * norm_y
    local_y_points_inward = dot_local_y_normal < 0

    # =========================================================================
    # Determine CSR based on element type
    # =========================================================================
    # CSR reference (empirically determined from Revit testing):
    #   CSR 0°   = C-opening faces -local_Y (opposite of horizontal perpendicular)
    #   CSR 90°  = C-opening faces UP (+Z)
    #   CSR 180° = C-opening faces +local_Y (horizontal perpendicular)
    #   CSR 270° = C-opening faces DOWN (-Z)
    #
    # CFS Framing Orientation Rules:
    #   - Bottom plates/tracks: face UP (CSR 90°)
    #   - Top plates/tracks: face DOWN (CSR 270°)
    #   - Sills: face DOWN (CSR 270°)
    #   - Headers: face UP (CSR 90°)
    #   - Blocking/Bridging: face DOWN (CSR 270°)

    if elem_lower in {"bottom_plate", "bottom_track"}:
        return 90.0  # Face UP

    elif elem_lower in {"top_plate", "top_track"}:
        return 270.0  # Face DOWN

    elif elem_lower == "sill":
        return 270.0  # Face DOWN

    elif elem_lower == "header":
        return 90.0  # Face UP

    elif elem_lower in {"row_blocking", "bridging"}:
        return 270.0  # Face DOWN

    return 0.0


def parse_wall_json(wall_json_input):
    """
    Parse wall JSON and extract level and geometry information.

    Args:
        wall_json_input: JSON string or list from Wall Analyzer

    Returns:
        Dict mapping wall_id to {base_level_id, top_level_id, wall_length}
    """
    # Handle Grasshopper wrapping in list
    json_str = wall_json_input
    if isinstance(wall_json_input, (list, tuple)):
        json_str = wall_json_input[0] if wall_json_input else "[]"

    try:
        walls = json.loads(json_str)
        if not isinstance(walls, list):
            walls = [walls]

        wall_data = {}
        for wall in walls:
            wall_id = wall.get('wall_id', 'unknown')
            wall_data[wall_id] = {
                'base_level_id': wall.get('base_level_id'),
                'top_level_id': wall.get('top_level_id'),
                'wall_length': wall.get('wall_length', 0),
            }
        return wall_data
    except Exception as e:
        print(f"Error parsing wall_json: {e}")
        return {}


def get_revit_level_by_id(doc, level_id: int):
    """
    Get a Revit Level element by its integer ID.

    Args:
        doc: Revit Document
        level_id: Integer element ID

    Returns:
        Revit Level element or None
    """
    if level_id is None:
        return None

    try:
        from Autodesk.Revit import DB
        element_id = DB.ElementId(level_id)
        level = doc.GetElement(element_id)
        return level
    except Exception as e:
        print(f"Error getting level {level_id}: {e}")
        return None


def extract_wall_id_from_element(element: FramingElementData) -> str:
    """
    Extract wall ID from element metadata or cell_id.

    Args:
        element: FramingElementData instance

    Returns:
        Wall ID string or 'unknown'
    """
    # Try metadata first
    if element.metadata and element.metadata.get('wall_id'):
        return element.metadata['wall_id']

    # Try cell_id (format: "1361779_SC_0")
    if element.cell_id:
        parts = element.cell_id.split('_')
        if len(parts) >= 1:
            return parts[0]

    # Try element id
    if '_' in element.id:
        parts = element.id.split('_')
        if len(parts) >= 1 and parts[0].isdigit():
            return parts[0]

    return 'unknown'


# =============================================================================
# Main Execution
# =============================================================================

# Initialize outputs
baking_data_json = ""
column_curves = DataTree[object]()   # Curves for column creation
beam_curves = DataTree[object]()     # Curves for beam placement (with CSR)
debug_info = ""

if run and elements_json:
    try:
        # Handle Grasshopper wrapping
        json_input = elements_json
        if isinstance(elements_json, (list, tuple)):
            json_input = elements_json[0] if elements_json else ""

        # Get geometry factory
        factory = get_factory()

        # Get Revit document for level lookup
        doc = Revit.ActiveDBDocument

        # Parse elements JSON
        results = deserialize_framing_results(json_input)

        # Parse wall JSON for level information
        wall_levels = {}
        if wall_json:
            wall_levels = parse_wall_json(wall_json)

        # Parse mirror_opening_studs input (default False)
        do_mirror = False
        if mirror_opening_studs:
            if isinstance(mirror_opening_studs, (list, tuple)):
                do_mirror = bool(mirror_opening_studs[0]) if mirror_opening_studs else False
            else:
                do_mirror = bool(mirror_opening_studs)

        # Parse user type mapping if provided
        user_type_mapping = None
        if type_mapping:
            if isinstance(type_mapping, str):
                try:
                    user_type_mapping = json.loads(type_mapping)
                except:
                    pass
            elif isinstance(type_mapping, dict):
                user_type_mapping = type_mapping

        debug_lines = [
            "Revit Baker v3.0 (with CSR support)",
            "=" * 40,
            f"Material System: {results.material_system}",
            f"Total Elements: {len(results.elements)}",
            f"Walls with Level Info: {len(wall_levels)}",
            f"Mirror Opening Studs: {do_mirror}",
            f"Revit Document: {'Available' if doc else 'NOT AVAILABLE'}",
            "",
        ]

        # DEBUG: Show wall level info
        if wall_levels:
            debug_lines.append("Wall Level Data (first 5):")
            for i, (wid, levels) in enumerate(list(wall_levels.items())[:5]):
                debug_lines.append(f"  Wall {wid}: base_level_id={levels.get('base_level_id')}, top_level_id={levels.get('top_level_id')}")
            if len(wall_levels) > 5:
                debug_lines.append(f"  ... and {len(wall_levels) - 5} more walls")
            debug_lines.append("")
        else:
            debug_lines.append("WARNING: No wall level data parsed!")
            debug_lines.append("  - Is wall_json connected?")
            debug_lines.append("  - Does wall_json contain base_level_id/top_level_id fields?")
            debug_lines.append("")

        # Convert revit type inputs to lists
        column_type_list = []
        beam_type_list = []

        if revit_column_types:
            if isinstance(revit_column_types, (list, tuple)):
                column_type_list = list(revit_column_types)
            else:
                column_type_list = [revit_column_types]

        if revit_beam_types:
            if isinstance(revit_beam_types, (list, tuple)):
                beam_type_list = list(revit_beam_types)
            else:
                beam_type_list = [revit_beam_types]

        # DEBUG: Extract and show Revit type names
        def get_type_name(rt):
            try:
                if hasattr(rt, 'Name'):
                    return rt.Name
                elif hasattr(rt, 'get_Name'):
                    return rt.get_Name()
                else:
                    return str(rt)
            except:
                return "ERROR"

        column_type_names = [get_type_name(rt) for rt in column_type_list[:5]]
        beam_type_names = [get_type_name(rt) for rt in beam_type_list[:5]]

        debug_lines.append(f"Available Column Types: {len(column_type_list)}")
        debug_lines.append(f"  First 5 names: {column_type_names}")
        debug_lines.append(f"Available Beam Types: {len(beam_type_list)}")
        debug_lines.append(f"  First 5 names: {beam_type_names}")
        debug_lines.append("")

        # DEBUG: Show first few element profile names
        profile_names_seen = set()
        for elem in results.elements[:20]:
            profile_names_seen.add(elem.profile.name)
        debug_lines.append(f"Profile names in elements (sample): {sorted(profile_names_seen)}")
        debug_lines.append("")

        # =================================================================
        # Group elements by wall for structured JSON output
        # =================================================================
        wall_elements = {}  # wall_id -> list of elements
        for element in results.elements:
            wall_id = extract_wall_id_from_element(element)
            if wall_id not in wall_elements:
                wall_elements[wall_id] = []
            wall_elements[wall_id].append(element)

        # Initialize baking data structure
        baking_data = {
            "walls": {},
            "summary": {
                "total_walls": 0,
                "total_columns": 0,
                "total_beams": 0,
                "material_system": results.material_system
            }
        }

        # Track counts and statistics
        column_count = 0
        beam_count = 0
        skipped_count = 0
        unmapped = []
        type_match_stats = {'exact': 0, 'contains': 0, 'default': 0, 'fallback': 0, 'user_mapping': 0, 'default_contains': 0}

        # CSR statistics for debug output
        csr_stats = {}  # element_type -> {csr_angle -> count}

        # Centerline vector debug tracking
        vector_debug = {}  # element_type -> list of (vector, csr) for first few

        # DEBUG: Track first few elements for detailed output
        debug_element_count = 0
        max_debug_elements = 3

        # =================================================================
        # Process each wall's elements
        # =================================================================
        for wall_id, elements in wall_elements.items():
            # Get level info from wall data
            wall_level_info = wall_levels.get(wall_id, {})
            base_level_id = wall_level_info.get('base_level_id')
            top_level_id = wall_level_info.get('top_level_id')

            # Initialize wall data in baking structure
            wall_data = {
                "base_level_id": base_level_id,
                "top_level_id": top_level_id,
                "members": []
            }

            for element in elements:
                elem_type = element.element_type.lower()
                classification = classify_element(elem_type)

                # DEBUG: Track level resolution for first few elements
                if debug_element_count < max_debug_elements:
                    print(f"\n[LEVEL DEBUG] Element: {element.id}")
                    print(f"  Wall ID from element: '{wall_id}'")
                    print(f"  Wall ID in wall_levels: {wall_id in wall_levels}")
                    print(f"  base_level_id: {base_level_id}, top_level_id: {top_level_id}")
                    # DEBUG: Show centerline coordinates for alignment verification
                    print(f"  [CENTERLINE] start=({element.centerline_start.x:.4f}, {element.centerline_start.y:.4f}, {element.centerline_start.z:.4f})")
                    print(f"  [CENTERLINE] end=({element.centerline_end.x:.4f}, {element.centerline_end.y:.4f}, {element.centerline_end.z:.4f})")
                    debug_element_count += 1

                # Profile name for type matching
                profile_name = element.profile.name

                # Enable debug for first few type matches
                debug_type_match = (column_count + beam_count) < 3

                # Determine which type list to use based on classification
                if classification == "column":
                    type_list = column_type_list
                elif classification == "beam":
                    type_list = beam_type_list
                else:
                    unmapped.append(f"Unknown: {element.id} ({elem_type})")
                    skipped_count += 1
                    continue

                # Match to Revit type
                matched_type, match_quality = find_matching_revit_type(
                    profile_name, type_list, user_type_mapping,
                    debug_first_n=1 if debug_type_match else 0
                )

                if matched_type is None:
                    unmapped.append(f"{classification.title()}: {element.id} ({profile_name})")
                    skipped_count += 1
                    continue

                if match_quality:
                    type_match_stats[match_quality] = type_match_stats.get(match_quality, 0) + 1

                # =========================================================
                # Compute CSR angle for CFS elements
                # =========================================================
                # Use the ACTUAL centerline vector (end - start) as rotation axis
                # This is what Revit uses to determine CSR rotation direction
                centerline_vector = (
                    element.centerline_end.x - element.centerline_start.x,
                    element.centerline_end.y - element.centerline_start.y,
                    element.centerline_end.z - element.centerline_start.z
                )

                # Extract wall normal (wall_z_axis) and wall x_axis from element metadata
                wall_normal = None
                wall_x_axis = None
                if element.metadata:
                    if 'wall_z_axis' in element.metadata:
                        axis = element.metadata['wall_z_axis']
                        if isinstance(axis, dict):
                            wall_normal = (axis.get('x', 0), axis.get('y', 0), axis.get('z', 0))
                        elif isinstance(axis, (list, tuple)):
                            wall_normal = tuple(axis)

                    if 'wall_x_axis' in element.metadata:
                        axis = element.metadata['wall_x_axis']
                        if isinstance(axis, dict):
                            wall_x_axis = (axis.get('x', 0), axis.get('y', 0), axis.get('z', 0))
                        elif isinstance(axis, (list, tuple)):
                            wall_x_axis = tuple(axis)

                # Detect if this is the end stud (last stud at wall end)
                is_end_stud = False
                if elem_type == "stud":
                    wall_length = wall_level_info.get('wall_length', 0)
                    u_coord = getattr(element, 'u_coord', None)
                    if wall_length > 0 and u_coord is not None:
                        # End stud is near wall_length (within stud width tolerance)
                        stud_width = 0.125  # 1.5" in feet (approximate)
                        tolerance = stud_width * 1.5
                        if u_coord > wall_length - tolerance:
                            is_end_stud = True
                    # DEBUG: Track end stud detection for first wall
                    if wall_id == list(wall_elements.keys())[0] and elem_type == "stud":
                        if 'end_stud_debug' not in vector_debug:
                            vector_debug['end_stud_debug'] = []
                        vector_debug['end_stud_debug'].append({
                            'id': element.id,
                            'u_coord': u_coord,
                            'wall_length': wall_length,
                            'is_end_stud': is_end_stud
                        })

                csr_angle = compute_csr_angle(
                    elem_type,
                    results.material_system,
                    centerline_vector,
                    wall_normal,
                    wall_x_axis,
                    element.id,
                    do_mirror,
                    is_end_stud
                )

                # =========================================================
                # Create geometry based on classification
                # =========================================================
                # COLUMNS: Curve for creation, plane data in JSON for orientation
                # BEAMS: Curves with CSR for orientation

                column_curve = None
                column_x_axis_tuple = None
                beam_curve = None

                if classification == "column":
                    # Create centerline curve for column creation
                    column_curve = create_centerline_curve(element, factory)
                    if not column_curve:
                        skipped_count += 1
                        continue

                    # Determine if column orientation should be flipped
                    should_flip = False

                    # End stud (last stud at wall end) - always flip
                    if is_end_stud and elem_type == "stud":
                        should_flip = True

                    # mirror_opening_studs: flip trimmer_0 and king_stud_1
                    if do_mirror and element.id:
                        if elem_type == "trimmer" and element.id.endswith("_0"):
                            should_flip = True
                        elif elem_type == "king_stud" and element.id.endswith("_1"):
                            should_flip = True

                    # Compute orientation X-axis for JSON output
                    # (Baking Data Parser will create actual Plane from this)
                    wall_ax = wall_x_axis[0] if wall_x_axis else 1.0
                    wall_ay = wall_x_axis[1] if wall_x_axis else 0.0
                    if should_flip:
                        column_x_axis_tuple = (-wall_ax, -wall_ay, 0.0)
                    else:
                        column_x_axis_tuple = (wall_ax, wall_ay, 0.0)
                else:
                    # Beams use centerline curves with CSR for orientation
                    beam_curve = create_centerline_curve(element, factory)
                    if not beam_curve:
                        skipped_count += 1
                        continue

                # DEBUG: Track opening element CSR details
                if elem_type in ('king_stud', 'trimmer'):
                    if 'opening_elements_debug' not in vector_debug:
                        vector_debug['opening_elements_debug'] = []
                    # Compute base CSR (without flip) for comparison
                    wall_ax = wall_x_axis[0] if wall_x_axis else 1
                    wall_ay = wall_x_axis[1] if wall_x_axis else 0
                    if abs(wall_ax) >= abs(wall_ay):
                        base_csr = 0.0 if wall_ax >= 0 else 180.0
                    else:
                        base_csr = 90.0 if wall_ay >= 0 else 270.0
                    is_flipped = abs(csr_angle - base_csr) > 1.0  # Check if different from base
                    vector_debug['opening_elements_debug'].append({
                        'wall_id': wall_id,
                        'id': element.id,
                        'csr': csr_angle,
                        'base_csr': base_csr,
                        'flipped': is_flipped
                    })

                # Track CSR statistics for debug
                if elem_type not in csr_stats:
                    csr_stats[elem_type] = {}
                csr_stats[elem_type][csr_angle] = csr_stats[elem_type].get(csr_angle, 0) + 1

                # Get Revit type name for JSON output
                revit_type_name = get_type_name(matched_type)

                # Determine geometry index based on classification (compute BEFORE debug tracking)
                if classification == "column":
                    geometry_index = column_count
                else:
                    geometry_index = beam_count

                # Track ALL blocking elements for comprehensive debug
                if elem_type == "row_blocking":
                    if elem_type not in vector_debug:
                        vector_debug[elem_type] = []
                    vec_x, vec_y, vec_z = centerline_vector
                    local_y = (-vec_y, vec_x)  # Cross product with Z
                    norm_x, norm_y = (wall_normal[0], wall_normal[1]) if wall_normal else (0, 0)
                    dot_local_y_normal = local_y[0] * norm_x + local_y[1] * norm_y
                    local_y_inward = dot_local_y_normal < 0
                    vector_debug[elem_type].append({
                        'id': element.id,
                        'start': (element.centerline_start.x, element.centerline_start.y, element.centerline_start.z),
                        'end': (element.centerline_end.x, element.centerline_end.y, element.centerline_end.z),
                        'vector': centerline_vector,
                        'normal': wall_normal,
                        'csr': csr_angle,
                        'local_y': local_y,
                        'local_y_inward': local_y_inward,
                        'wall_id': wall_id,
                        'geometry_index': geometry_index
                    })

                # Build member data for JSON
                member_data = {
                    "id": element.id,
                    "element_type": element.element_type,
                    "classification": classification,
                    "profile_name": profile_name,
                    "revit_type_name": revit_type_name,
                    "centerline_start": {
                        "x": element.centerline_start.x,
                        "y": element.centerline_start.y,
                        "z": element.centerline_start.z
                    },
                    "centerline_end": {
                        "x": element.centerline_end.x,
                        "y": element.centerline_end.y,
                        "z": element.centerline_end.z
                    },
                    "geometry_index": geometry_index
                }

                # Add classification-specific data
                if classification == "column":
                    # Columns use plane-based placement (no CSR)
                    member_data["plane_origin"] = {
                        "x": element.centerline_start.x,
                        "y": element.centerline_start.y,
                        "z": element.centerline_start.z
                    }
                    if column_x_axis_tuple:
                        member_data["plane_x_axis"] = {
                            "x": column_x_axis_tuple[0],
                            "y": column_x_axis_tuple[1],
                            "z": column_x_axis_tuple[2]
                        }
                else:
                    # Beams use CSR for orientation
                    member_data["csr_angle"] = csr_angle

                wall_data["members"].append(member_data)

                # Add geometry to appropriate DataTree
                # Note: Column plane data (for orientation) is in baking_data_json
                if classification == "column":
                    path = GH_Path(column_count)
                    column_curves.Add(column_curve, path)
                    column_count += 1
                elif classification == "beam":
                    path = GH_Path(beam_count)
                    beam_curves.Add(beam_curve, path)
                    beam_count += 1

            # Add wall data to baking structure
            baking_data["walls"][wall_id] = wall_data

        # Update summary
        baking_data["summary"]["total_walls"] = len(wall_elements)
        baking_data["summary"]["total_columns"] = column_count
        baking_data["summary"]["total_beams"] = beam_count

        # Serialize to JSON output
        baking_data_json = json.dumps(baking_data, indent=2)

        # =================================================================
        # Build debug summary
        # =================================================================
        debug_lines.append("Classification Summary:")
        debug_lines.append(f"  Walls: {len(wall_elements)}")
        debug_lines.append(f"  Columns: {column_count}")
        debug_lines.append(f"  Beams: {beam_count}")
        debug_lines.append(f"  Skipped/Unmapped: {skipped_count}")
        debug_lines.append("")

        # Wall ID matching summary
        wall_ids_in_json = set(wall_levels.keys())
        wall_ids_from_elements = set(wall_elements.keys())
        matched_wall_ids = wall_ids_from_elements & wall_ids_in_json
        unmatched_element_wall_ids = wall_ids_from_elements - wall_ids_in_json
        debug_lines.append("Wall ID Matching:")
        debug_lines.append(f"  Wall IDs from elements: {len(wall_ids_from_elements)}")
        debug_lines.append(f"  Wall IDs in wall_json: {len(wall_ids_in_json)}")
        debug_lines.append(f"  Matched: {len(matched_wall_ids)}")
        if unmatched_element_wall_ids:
            debug_lines.append(f"  UNMATCHED element wall IDs: {sorted(unmatched_element_wall_ids)[:5]}")
        debug_lines.append("")

        # Orientation summary (CFS only)
        debug_lines.append("Orientation Control (CFS):")
        debug_lines.append(f"  Material System: {results.material_system}")
        debug_lines.append(f"  Mirror Opening Studs: {do_mirror}")
        debug_lines.append(f"  Columns: Plane-based (X-axis controls orientation)")
        debug_lines.append(f"  Beams: CSR parameter (Cross-Section Rotation)")
        if results.material_system.lower() == "cfs":
            debug_lines.append("  Beam CSR Values by Element Type:")
            for elem_type in sorted(csr_stats.keys()):
                # Skip column types in CSR stats (they use plane orientation)
                if elem_type in {"stud", "king_stud", "trimmer", "header_cripple", "sill_cripple"}:
                    continue
                angles = csr_stats[elem_type]
                angle_summary = ", ".join([f"{angle}°: {count}" for angle, count in sorted(angles.items())])
                debug_lines.append(f"    {elem_type}: {angle_summary}")

            # Show ALL blocking elements grouped by wall
            debug_lines.append("")
            debug_lines.append("  ALL Blocking Elements (grouped by wall):")
            if "row_blocking" in vector_debug:
                # Group by wall
                by_wall = {}
                for sample in vector_debug["row_blocking"]:
                    wid = sample.get('wall_id', '?')
                    if wid not in by_wall:
                        by_wall[wid] = []
                    by_wall[wid].append(sample)

                for wid in sorted(by_wall.keys()):
                    samples = by_wall[wid]
                    # Get wall normal from first sample
                    norm = samples[0]['normal'] if samples else None
                    norm_str = f"({norm[0]:.2f}, {norm[1]:.2f})" if norm else "None"
                    debug_lines.append(f"    Wall {wid} (norm={norm_str}): {len(samples)} blocking")
                    for i, sample in enumerate(samples):
                        start = sample.get('start', (0, 0, 0))
                        end = sample.get('end', (0, 0, 0))
                        vec = sample['vector']
                        csr = sample['csr']
                        gidx = sample.get('geometry_index', '?')
                        # Determine direction
                        if abs(vec[0]) >= abs(vec[1]):
                            direction = "+X" if vec[0] >= 0 else "-X"
                        else:
                            direction = "+Y" if vec[1] >= 0 else "-Y"
                        # Show Z coordinate to identify upper vs lower row
                        z_height = start[2] if len(start) > 2 else 0
                        debug_lines.append(f"      [{i}] {sample['id']}: X({start[0]:.1f}->{end[0]:.1f}) Y({start[1]:.1f}) Z={z_height:.1f} dir={direction} CSR={csr}° idx={gidx}")
            # Show end stud detection debug
            if 'end_stud_debug' in vector_debug:
                debug_lines.append("")
                debug_lines.append("  End Stud Detection (first wall):")
                for stud in vector_debug['end_stud_debug']:
                    debug_lines.append(f"    {stud['id']}: u_coord={stud['u_coord']}, wall_length={stud['wall_length']}, is_end={stud['is_end_stud']}")

            # Show detailed king stud and trimmer CSR values for mirror debug
            debug_lines.append("")
            debug_lines.append("  Opening Elements CSR (mirror_opening_studs debug):")
            debug_lines.append(f"    mirror_opening_studs = {do_mirror}")
            # Collect CSR values we computed for opening elements
            if 'opening_elements_debug' in vector_debug:
                for item in vector_debug['opening_elements_debug']:
                    debug_lines.append(f"    {item['wall_id']}: {item['id']} -> CSR={item['csr']}° (base={item['base_csr']}°, flipped={item['flipped']})")
        else:
            debug_lines.append("  (Timber - all CSR angles are 0°)")
        debug_lines.append("")

        debug_lines.append("Type Matching Stats:")
        for quality, count in type_match_stats.items():
            if count > 0:
                debug_lines.append(f"  {quality}: {count}")
        debug_lines.append("")

        if unmapped:
            debug_lines.append(f"Unmapped Elements ({len(unmapped)}):")
            for item in unmapped[:10]:  # Show first 10
                debug_lines.append(f"  - {item}")
            if len(unmapped) > 10:
                debug_lines.append(f"  ... and {len(unmapped) - 10} more")

        debug_info = "\n".join(debug_lines)

    except json.JSONDecodeError as e:
        debug_info = f"JSON Parse Error: {str(e)}"
        baking_data_json = json.dumps({"error": str(e)})
    except Exception as e:
        import traceback
        debug_info = f"ERROR: {str(e)}\n{traceback.format_exc()}"
        baking_data_json = json.dumps({"error": str(e)})

elif not run:
    debug_info = "Set 'run' to True to execute"
    baking_data_json = json.dumps({"error": "Not running"})
elif not elements_json:
    debug_info = "No elements_json input provided"
    baking_data_json = json.dumps({"error": "No input"})

# Print debug_info so it appears in the 'out' output
print(debug_info)
