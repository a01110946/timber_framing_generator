# File: scripts/gh_wall_orientation_debug.py
"""
GHPython Component: Wall Orientation Diagnostic

Simple diagnostic tool to output wall orientation data in a clear format.
Use this to verify your test walls have all 4 unique orientations.

Inputs:
    elements_json (JSON) - str:
        JSON string from Framing Generator component
        Required: Yes
        Access: Item

    run (Run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    orientation_report (Report) - str:
        Clear report of wall orientations and blocking CSR values

Expected Wall Orientations for Complete Test:
    North wall: x_axis = +X (1,0,0), z_axis = +Y (0,1,0)  → facing outward to +Y
    South wall: x_axis = +X (1,0,0), z_axis = -Y (0,-1,0) → facing outward to -Y
    East wall:  x_axis = +Y (0,1,0), z_axis = +X (1,0,0)  → facing outward to +X
    West wall:  x_axis = +Y (0,1,0), z_axis = -X (-1,0,0) → facing outward to -X

Environment:
    Rhino 8, Grasshopper, Python component (CPython 3)
"""

import sys
import json
from collections import defaultdict

# =============================================================================
# Force Module Reload
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

from src.timber_framing_generator.core.json_schemas import deserialize_framing_results

# =============================================================================
# Helper Functions
# =============================================================================

def classify_wall_orientation(z_axis):
    """
    Classify wall facing direction based on wall_z_axis (normal).

    Returns:
        String like "EAST (+X)", "WEST (-X)", "NORTH (+Y)", "SOUTH (-Y)"
    """
    if z_axis is None:
        return "UNKNOWN (no z_axis)"

    x, y, z = z_axis

    # Determine dominant axis
    if abs(x) >= abs(y):
        if x >= 0:
            return "EAST (+X facing)"
        else:
            return "WEST (-X facing)"
    else:
        if y >= 0:
            return "NORTH (+Y facing)"
        else:
            return "SOUTH (-Y facing)"


def get_direction_category(vector):
    """Get simple direction category for a vector."""
    if vector is None:
        return "UNKNOWN"

    x, y, z = vector

    # Check if vertical
    if abs(z) > max(abs(x), abs(y)):
        return "VERTICAL"

    # Horizontal direction
    if abs(x) >= abs(y):
        return "+X" if x >= 0 else "-X"
    else:
        return "+Y" if y >= 0 else "-Y"


# =============================================================================
# Main Execution
# =============================================================================

orientation_report = ""

if run and elements_json:
    try:
        # Handle Grasshopper wrapping
        json_input = elements_json
        if isinstance(elements_json, (list, tuple)):
            json_input = elements_json[0] if elements_json else ""

        results = deserialize_framing_results(json_input)

        # Group elements by wall and extract orientation
        wall_info = {}  # wall_id -> {x_axis, z_axis, blocking_count}

        for element in results.elements:
            # Extract wall_id
            wall_id = None
            if element.metadata and element.metadata.get('wall_id'):
                wall_id = element.metadata['wall_id']
            elif element.cell_id:
                wall_id = element.cell_id.split('_')[0]

            if wall_id is None:
                continue

            # Initialize wall info
            if wall_id not in wall_info:
                wall_info[wall_id] = {
                    'x_axis': None,
                    'z_axis': None,
                    'blocking_elements': [],
                    'element_count': 0
                }

            wall_info[wall_id]['element_count'] += 1

            # Extract axes from metadata (once per wall)
            if wall_info[wall_id]['x_axis'] is None and element.metadata:
                if 'wall_x_axis' in element.metadata:
                    axis = element.metadata['wall_x_axis']
                    if isinstance(axis, dict):
                        wall_info[wall_id]['x_axis'] = (axis.get('x', 0), axis.get('y', 0), axis.get('z', 0))
                    elif isinstance(axis, (list, tuple)):
                        wall_info[wall_id]['x_axis'] = tuple(axis)

                if 'wall_z_axis' in element.metadata:
                    axis = element.metadata['wall_z_axis']
                    if isinstance(axis, dict):
                        wall_info[wall_id]['z_axis'] = (axis.get('x', 0), axis.get('y', 0), axis.get('z', 0))
                    elif isinstance(axis, (list, tuple)):
                        wall_info[wall_id]['z_axis'] = tuple(axis)

            # Track blocking elements
            if element.element_type.lower() == 'row_blocking':
                centerline_vector = (
                    element.centerline_end.x - element.centerline_start.x,
                    element.centerline_end.y - element.centerline_start.y,
                    element.centerline_end.z - element.centerline_start.z
                )
                wall_info[wall_id]['blocking_elements'].append({
                    'id': element.id,
                    'vector': centerline_vector,
                    'start': (element.centerline_start.x, element.centerline_start.y, element.centerline_start.z),
                    'end': (element.centerline_end.x, element.centerline_end.y, element.centerline_end.z)
                })

        # Build report
        lines = [
            "=" * 60,
            "WALL ORIENTATION DIAGNOSTIC REPORT",
            "=" * 60,
            f"Total Walls: {len(wall_info)}",
            f"Material System: {results.material_system}",
            "",
        ]

        # Group walls by orientation
        orientation_groups = defaultdict(list)

        for wall_id in sorted(wall_info.keys()):
            info = wall_info[wall_id]
            orientation = classify_wall_orientation(info['z_axis'])
            orientation_groups[orientation].append(wall_id)

        # Summary of orientations
        lines.append("ORIENTATION SUMMARY:")
        lines.append("-" * 40)
        for orientation in sorted(orientation_groups.keys()):
            wall_ids = orientation_groups[orientation]
            lines.append(f"  {orientation}: {len(wall_ids)} walls {wall_ids}")
        lines.append("")

        # Check completeness
        expected = ["EAST (+X facing)", "WEST (-X facing)", "NORTH (+Y facing)", "SOUTH (-Y facing)"]
        missing = [o for o in expected if o not in orientation_groups]
        if missing:
            lines.append("WARNING: MISSING ORIENTATIONS FOR COMPLETE TEST:")
            for m in missing:
                lines.append(f"    - {m}")
            lines.append("")
        else:
            lines.append("All 4 orientations present!")
            lines.append("")

        # Detailed wall info
        lines.append("DETAILED WALL INFORMATION:")
        lines.append("-" * 40)

        for wall_id in sorted(wall_info.keys()):
            info = wall_info[wall_id]
            orientation = classify_wall_orientation(info['z_axis'])

            # Format axes nicely
            def fmt_vec(v):
                if v is None:
                    return "None"
                return f"({v[0]:.2f}, {v[1]:.2f}, {v[2]:.2f})"

            lines.append(f"\nWall {wall_id}:")
            lines.append(f"  Orientation: {orientation}")
            lines.append(f"  x_axis (run direction): {fmt_vec(info['x_axis'])}")
            lines.append(f"  z_axis (wall normal):   {fmt_vec(info['z_axis'])}")
            lines.append(f"  Total elements: {info['element_count']}")
            lines.append(f"  Blocking elements: {len(info['blocking_elements'])}")

            # Show blocking samples
            if info['blocking_elements']:
                lines.append("  Blocking samples:")
                for i, blk in enumerate(info['blocking_elements'][:3]):
                    vec = blk['vector']
                    dir_cat = get_direction_category(vec)
                    lines.append(f"    [{i}] {blk['id']}: vector={fmt_vec(vec)} -> {dir_cat}")

        # Add guidance for CSR testing
        lines.append("")
        lines.append("=" * 60)
        lines.append("NEXT STEPS FOR CSR TESTING:")
        lines.append("=" * 60)
        lines.append("""
1. Verify you have all 4 wall orientations (N, S, E, W)
2. If missing orientations, add walls with those directions
3. Once complete, bake to Revit and check blocking orientation
4. Report which walls have CORRECT vs INCORRECT blocking
   - Blocking should face INWARD (opposite of wall normal)
   - E.g., on East wall (normal +X), blocking should face -X (into building)
""")

        orientation_report = "\n".join(lines)

    except Exception as e:
        import traceback
        orientation_report = f"ERROR: {str(e)}\n{traceback.format_exc()}"

elif not run:
    orientation_report = "Set 'run' to True to execute"
elif not elements_json:
    orientation_report = "No elements_json input provided"

print(orientation_report)
