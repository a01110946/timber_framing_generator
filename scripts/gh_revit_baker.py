# File: scripts/gh_revit_baker.py
"""
GHPython Component: Revit Baker

Transforms framing elements into outputs suitable for Rhino.Inside.Revit's
Add Structural Column and Add Structural Beam components.

This component classifies elements as vertical (columns) vs horizontal (beams),
maps profile names to Revit family types, and outputs parallel DataTrees for
RiR component inputs.

Inputs:
    elements_json: JSON string from Framing Generator component
    wall_json: JSON string from Wall Analyzer (for level information)
    revit_column_types: List of available Revit Structural Column family types
    revit_beam_types: List of available Revit Structural Framing family types
    type_mapping: Optional dict mapping profile names to Revit type names
    run: Boolean to trigger execution

Outputs:
    column_curves: DataTree of centerlines for vertical elements (studs, etc.)
    column_types: DataTree of matched Revit types (parallel to column_curves)
    column_base_levels: DataTree of base levels (parallel to column_curves)
    column_top_levels: DataTree of top levels (parallel to column_curves)
    beam_curves: DataTree of centerlines for horizontal elements (plates, etc.)
    beam_types: DataTree of matched Revit types (parallel to beam_curves)
    beam_ref_levels: DataTree of reference levels (parallel to beam_curves)
    unmapped: List of elements with no matching Revit type
    debug_info: Processing summary

Usage:
    1. Connect 'elements_json' from Framing Generator
    2. Connect 'wall_json' from Wall Analyzer
    3. Connect Revit family types (use RiR type pickers)
    4. Optionally provide 'type_mapping' for custom profile-to-type mapping
    5. Set 'run' to True
    6. Connect outputs to RiR Add Structural Column/Beam components
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


def parse_wall_json(wall_json_input):
    """
    Parse wall JSON and extract level information.

    Args:
        wall_json_input: JSON string or list from Wall Analyzer

    Returns:
        Dict mapping wall_id to {base_level_id, top_level_id}
    """
    # Handle Grasshopper wrapping in list
    json_str = wall_json_input
    if isinstance(wall_json_input, (list, tuple)):
        json_str = wall_json_input[0] if wall_json_input else "[]"

    try:
        walls = json.loads(json_str)
        if not isinstance(walls, list):
            walls = [walls]

        wall_levels = {}
        for wall in walls:
            wall_id = wall.get('wall_id', 'unknown')
            wall_levels[wall_id] = {
                'base_level_id': wall.get('base_level_id'),
                'top_level_id': wall.get('top_level_id'),
            }
        return wall_levels
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
column_curves = DataTree[object]()
column_types = DataTree[object]()
column_base_levels = DataTree[object]()
column_top_levels = DataTree[object]()
beam_curves = DataTree[object]()
beam_types = DataTree[object]()
beam_ref_levels = DataTree[object]()
unmapped = []
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
            "Revit Baker v2.0 (with diagnostics)",
            "=" * 40,
            f"Material System: {results.material_system}",
            f"Total Elements: {len(results.elements)}",
            f"Walls with Level Info: {len(wall_levels)}",
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

        # Track counts
        column_count = 0
        beam_count = 0
        skipped_count = 0
        null_level_count = 0
        type_match_stats = {'exact': 0, 'contains': 0, 'default': 0, 'fallback': 0, 'user_mapping': 0, 'default_contains': 0}

        # DEBUG: Track first few elements for detailed output
        debug_element_count = 0
        max_debug_elements = 3
        wall_ids_from_elements = set()

        # Process each element
        for element in results.elements:
            elem_type = element.element_type.lower()
            classification = classify_element(elem_type)

            # Get wall ID for this element
            wall_id = extract_wall_id_from_element(element)
            wall_ids_from_elements.add(wall_id)

            # Get level info from wall data
            wall_level_info = wall_levels.get(wall_id, {})
            base_level_id = wall_level_info.get('base_level_id')
            top_level_id = wall_level_info.get('top_level_id')

            # DEBUG: Track level resolution for first few elements
            if debug_element_count < max_debug_elements:
                print(f"\n[LEVEL DEBUG] Element: {element.id}")
                print(f"  Wall ID from element: '{wall_id}'")
                print(f"  Wall ID in wall_levels: {wall_id in wall_levels}")
                print(f"  base_level_id: {base_level_id}, top_level_id: {top_level_id}")

            # Get Revit level objects
            base_level = get_revit_level_by_id(doc, base_level_id) if doc else None
            top_level = get_revit_level_by_id(doc, top_level_id) if doc else None

            # Track null levels
            if base_level is None or top_level is None:
                null_level_count += 1

            if debug_element_count < max_debug_elements:
                print(f"  Resolved base_level: {base_level}, top_level: {top_level}")
                debug_element_count += 1

            # Create centerline curve
            curve = create_centerline_curve(element, factory)
            if not curve:
                skipped_count += 1
                continue

            # Profile name for type matching
            profile_name = element.profile.name

            # Enable debug for first few type matches
            debug_type_match = (column_count + beam_count) < 3

            if classification == "column":
                # Match to column type
                matched_type, match_quality = find_matching_revit_type(
                    profile_name, column_type_list, user_type_mapping,
                    debug_first_n=1 if debug_type_match else 0
                )

                if matched_type is None:
                    unmapped.append(f"Column: {element.id} ({profile_name})")
                    skipped_count += 1
                    continue

                if match_quality:
                    type_match_stats[match_quality] = type_match_stats.get(match_quality, 0) + 1

                # Add to DataTrees using element index as path
                path = GH_Path(column_count)
                column_curves.Add(curve, path)
                column_types.Add(matched_type, path)
                column_base_levels.Add(base_level, path)
                column_top_levels.Add(top_level, path)
                column_count += 1

            elif classification == "beam":
                # Match to beam type
                matched_type, match_quality = find_matching_revit_type(
                    profile_name, beam_type_list, user_type_mapping,
                    debug_first_n=1 if debug_type_match else 0
                )

                if matched_type is None:
                    unmapped.append(f"Beam: {element.id} ({profile_name})")
                    skipped_count += 1
                    continue

                if match_quality:
                    type_match_stats[match_quality] = type_match_stats.get(match_quality, 0) + 1

                # Add to DataTrees using element index as path
                path = GH_Path(beam_count)
                beam_curves.Add(curve, path)
                beam_types.Add(matched_type, path)
                # For beams, reference level is typically the base level
                beam_ref_levels.Add(base_level, path)
                beam_count += 1

            else:
                # Unknown classification
                unmapped.append(f"Unknown: {element.id} ({elem_type})")
                skipped_count += 1

        # Build debug summary
        debug_lines.append("Classification Summary:")
        debug_lines.append(f"  Columns: {column_count}")
        debug_lines.append(f"  Beams: {beam_count}")
        debug_lines.append(f"  Skipped/Unmapped: {skipped_count}")
        debug_lines.append("")

        # Wall ID matching summary
        wall_ids_in_json = set(wall_levels.keys())
        matched_wall_ids = wall_ids_from_elements & wall_ids_in_json
        unmatched_element_wall_ids = wall_ids_from_elements - wall_ids_in_json
        debug_lines.append("Wall ID Matching:")
        debug_lines.append(f"  Wall IDs from elements: {len(wall_ids_from_elements)}")
        debug_lines.append(f"  Wall IDs in wall_json: {len(wall_ids_in_json)}")
        debug_lines.append(f"  Matched: {len(matched_wall_ids)}")
        if unmatched_element_wall_ids:
            debug_lines.append(f"  UNMATCHED element wall IDs: {sorted(unmatched_element_wall_ids)[:5]}")
        debug_lines.append("")

        # Level resolution summary
        debug_lines.append("Level Resolution:")
        debug_lines.append(f"  Elements with null levels: {null_level_count}")
        if null_level_count > 0:
            debug_lines.append("  Possible causes:")
            debug_lines.append("    - wall_json not connected or missing level IDs")
            debug_lines.append("    - Wall IDs don't match between elements_json and wall_json")
            debug_lines.append("    - Revit document not available")
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
    except Exception as e:
        import traceback
        debug_info = f"ERROR: {str(e)}\n{traceback.format_exc()}"

elif not run:
    debug_info = "Set 'run' to True to execute"
elif not elements_json:
    debug_info = "No elements_json input provided"

# Print debug_info so it appears in the 'out' output
print(debug_info)
