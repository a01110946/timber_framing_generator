# File: scripts/gh_geometry_converter.py
"""
GHPython Component: Geometry Converter

Converts framing elements JSON to RhinoCommon geometry (Breps and Curves).
This is the final stage of the modular pipeline, handling the assembly
mismatch issue by using the RhinoCommonFactory.

Inputs:
    elements_json: JSON string from Framing Generator component
    filter_types: Optional list of element types to include (e.g., ["stud", "plate"])
    run: Boolean to trigger execution

Outputs:
    breps: All framing elements as Breps
    by_type: DataTree of Breps organized by element type
    centerlines: Centerline curves for each element
    element_ids: Element IDs for selection feedback

Usage:
    1. Connect 'elements_json' from Framing Generator
    2. Optionally set 'filter_types' to filter specific element types
    3. Set 'run' to True to execute
    4. Connect 'breps' to display or bake geometry
"""

import sys
import json

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

from src.timber_framing_generator.utils.geometry_factory import get_factory
from src.timber_framing_generator.core.json_schemas import (
    deserialize_framing_results, FramingElementData, Point3D
)

# =============================================================================
# Helper Functions
# =============================================================================

def create_brep_from_element(element: FramingElementData, factory):
    """
    Create a Brep from a framing element.

    Args:
        element: FramingElementData with centerline and profile info
        factory: RhinoCommonFactory instance

    Returns:
        Brep geometry or None if creation fails
    """
    start = element.centerline_start
    end = element.centerline_end

    # Calculate direction and length
    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z
    length = (dx*dx + dy*dy + dz*dz) ** 0.5

    if length < 0.001:
        return None

    direction = (dx/length, dy/length, dz/length)

    return factory.create_box_brep_from_centerline(
        start_point=(start.x, start.y, start.z),
        direction=direction,
        length=length,
        width=element.profile.width,
        depth=element.profile.depth,
    )


def create_centerline_from_element(element: FramingElementData, factory):
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


def element_type_to_branch_index(element_type: str) -> int:
    """
    Map element type to a consistent branch index for DataTree organization.

    Args:
        element_type: Element type string (e.g., "stud", "bottom_plate")

    Returns:
        Integer index for GH_Path
    """
    type_order = [
        "bottom_plate",
        "top_plate",
        "stud",
        "king_stud",
        "trimmer",
        "header",
        "sill",
        "header_cripple",
        "sill_cripple",
        "blocking",
        "track",  # CFS
        "web_stiffener",  # CFS
        "bridging",  # CFS
    ]

    if element_type.lower() in type_order:
        return type_order.index(element_type.lower())
    else:
        # Unknown types go to end
        return len(type_order) + hash(element_type) % 100


# =============================================================================
# Main Execution
# =============================================================================

# Initialize outputs
breps = []
by_type = DataTree[object]()
centerlines = []
element_ids = []
debug_info = ""

if run and elements_json:
    try:
        # Handle Grasshopper wrapping string in list
        json_input = elements_json
        if isinstance(elements_json, (list, tuple)):
            json_input = elements_json[0] if elements_json else ""

        # Get geometry factory
        factory = get_factory()

        # Parse JSON
        results = deserialize_framing_results(json_input)

        debug_lines = [
            f"Geometry Converter",
            f"Material System: {results.material_system}",
            f"Total Elements: {len(results.elements)}",
            "",
        ]

        # Parse filter_types if provided
        active_filters = None
        if filter_types:
            if isinstance(filter_types, str):
                active_filters = [f.strip().lower() for f in filter_types.split(',')]
            elif isinstance(filter_types, list):
                active_filters = [f.lower() for f in filter_types]
            debug_lines.append(f"Filter: {active_filters}")

        # Group elements by type for DataTree organization
        type_groups = {}
        type_names = {}  # Maps index to type name for debug

        for element in results.elements:
            elem_type = element.element_type.lower()

            # Apply filter if provided
            if active_filters and elem_type not in active_filters:
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

                # Create centerline
                centerline = create_centerline_from_element(element, factory)
                if centerline:
                    centerlines.append(centerline)

                # Track element ID
                element_ids.append(element.id)

        # Build by_type DataTree
        for branch_idx in sorted(type_groups.keys()):
            path = GH_Path(branch_idx)
            for brep in type_groups[branch_idx]:
                by_type.Add(brep, path)

        # Summary
        debug_lines.append("")
        debug_lines.append("Elements by Type:")
        for branch_idx in sorted(type_groups.keys()):
            elem_type = type_names[branch_idx]
            count = len(type_groups[branch_idx])
            debug_lines.append(f"  [{branch_idx}] {elem_type}: {count}")

        debug_lines.append("")
        debug_lines.append(f"Total Breps: {len(breps)}")
        debug_lines.append(f"Total Centerlines: {len(centerlines)}")

        # Note if no elements
        if len(breps) == 0:
            debug_lines.append("")
            debug_lines.append("NOTE: No geometry created.")
            debug_lines.append("This is expected if:")
            debug_lines.append("  - elements_json contains no elements")
            debug_lines.append("  - filter_types excluded all elements")
            debug_lines.append("  - Strategy returns empty list (Phase 2/3)")

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

# =============================================================================
# Assign Outputs
# =============================================================================

a = breps         # breps output
b = by_type       # by_type output (DataTree)
c = centerlines   # centerlines output
d = element_ids   # element_ids output
e = debug_info    # debug_info output
