# File: scripts/gh_wall_analyzer.py
"""
GHPython Component: Wall Analyzer

Extracts wall data from Revit walls and serializes to JSON format
for use by downstream components in the modular framing pipeline.

Inputs:
    walls: List of Revit wall elements
    run: Boolean to trigger execution

Outputs:
    wall_json: JSON string containing wall data for all walls
    wall_curves: DataTree of wall base curves for visualization
    debug_info: Debug information and status messages

Usage:
    1. Place this script in a GHPython component
    2. Connect Revit walls to 'walls' input
    3. Set 'run' to True to execute
    4. Connect 'wall_json' to Cell Decomposer component
"""

import sys
import os
import json
from dataclasses import asdict

# =============================================================================
# RhinoCommon Setup (CRITICAL - must be at top)
# =============================================================================

import clr

# Add CLR references before importing Rhino
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

from src.timber_framing_generator.wall_data.revit_data_extractor import (
    extract_wall_data_from_revit
)
from src.timber_framing_generator.core.json_schemas import (
    WallData, Point3D, Vector3D, PlaneData, OpeningData,
    serialize_wall_data, FramingJSONEncoder
)

# =============================================================================
# Helper Functions
# =============================================================================

def convert_wall_data_to_schema(wall_data: dict, wall_id: str) -> WallData:
    """
    Convert extracted wall data dict to WallData schema.

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
        # Default plane if not available
        plane_data = PlaneData(
            origin=Point3D(0, 0, 0),
            x_axis=Vector3D(1, 0, 0),
            y_axis=Vector3D(0, 1, 0),
            z_axis=Vector3D(0, 0, 1),
        )

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
    for opening in wall_data.get('openings', []):
        opening_data = OpeningData(
            id=str(opening.get('id', '')),
            opening_type=opening.get('type', 'window'),
            u_start=float(opening.get('u_start', 0)),
            u_end=float(opening.get('u_end', 0)),
            v_start=float(opening.get('v_start', 0)),
            v_end=float(opening.get('v_end', 0)),
            width=float(opening.get('width', 0)),
            height=float(opening.get('height', 0)),
            sill_height=opening.get('sill_height'),
        )
        openings.append(opening_data)

    # Create WallData
    return WallData(
        wall_id=wall_id,
        wall_length=float(wall_data.get('wall_length', 0)),
        wall_height=float(wall_data.get('wall_height', 0)),
        wall_thickness=float(wall_data.get('wall_thickness', 0.5)),  # Default 6"
        base_elevation=float(wall_data.get('wall_base_elevation', 0)),
        top_elevation=float(wall_data.get('wall_top_elevation', 0)),
        base_plane=plane_data,
        base_curve_start=curve_start,
        base_curve_end=curve_end,
        openings=openings,
        is_exterior=wall_data.get('is_exterior_wall', False),
        wall_type=wall_data.get('wall_type'),
        metadata={
            'revit_id': wall_id,
            'has_cells': 'cells' in wall_data,
        }
    )


# =============================================================================
# Main Execution
# =============================================================================

# Initialize outputs
wall_json = "[]"
wall_curves = DataTree[object]()
debug_info = ""

# Check if we should run
if run and walls:
    try:
        # Ensure walls is a list (handle single wall input)
        if not isinstance(walls, (list, tuple)):
            walls = [walls]

        # Get Revit document
        doc = Revit.ActiveDBDocument
        if doc is None:
            debug_info = "ERROR: No active Revit document"
        else:
            wall_data_list = []
            debug_lines = [f"Processing {len(walls)} walls..."]

            for i, wall in enumerate(walls):
                try:
                    # Get wall ID
                    wall_id = str(wall.Id.IntegerValue)

                    # Extract wall data using existing function
                    data = extract_wall_data_from_revit(wall, doc)

                    if data:
                        # Convert to JSON-serializable schema
                        wall_data = convert_wall_data_to_schema(data, wall_id)
                        wall_data_list.append(wall_data)

                        # Add base curve for visualization
                        base_curve = data.get('wall_base_curve')
                        if base_curve:
                            wall_curves.Add(base_curve, GH_Path(i))

                        debug_lines.append(
                            f"Wall {i} (ID:{wall_id}): L={wall_data.wall_length:.2f}', "
                            f"H={wall_data.wall_height:.2f}', "
                            f"Openings={len(wall_data.openings)}"
                        )
                    else:
                        debug_lines.append(f"Wall {i}: FAILED - No data extracted")

                except Exception as e:
                    debug_lines.append(f"Wall {i}: ERROR - {str(e)}")

            # Serialize all walls to JSON
            if wall_data_list:
                # Convert to list of dicts for JSON
                wall_dicts = [asdict(w) for w in wall_data_list]
                wall_json = json.dumps(wall_dicts, cls=FramingJSONEncoder, indent=2)
                debug_lines.append(f"\nSuccess: Serialized {len(wall_data_list)} walls to JSON")
            else:
                debug_lines.append("\nWarning: No walls were successfully processed")

            debug_info = "\n".join(debug_lines)

    except Exception as e:
        import traceback
        debug_info = f"ERROR: {str(e)}\n{traceback.format_exc()}"
        wall_json = "[]"

elif not run:
    debug_info = "Set 'run' to True to execute"
elif not walls:
    debug_info = "No walls provided"

# =============================================================================
# Assign Outputs (GHPython component outputs)
# =============================================================================

a = wall_json      # wall_json output
b = wall_curves    # wall_curves output
c = debug_info     # debug_info output
