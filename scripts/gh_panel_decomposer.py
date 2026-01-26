# File: scripts/gh_panel_decomposer.py
"""
GHPython Component: Panel Decomposer

Decomposes framed walls into manufacturable panels with optimized joint placement.
Handles Revit wall corner adjustments for accurate panel geometry.

Inputs:
    walls_json: JSON string from Wall Analyzer component
    framing_json: JSON string from Framing Generator component (optional)
    max_panel_length: Maximum panel length in feet (default 24.0)
    min_joint_to_opening: Minimum distance from joint to opening edge in feet (default 1.0)
    min_joint_to_corner: Minimum distance from joint to wall corner in feet (default 2.0)
    stud_spacing: Stud spacing in feet for joint alignment (default 1.333 = 16" OC)
    run: Boolean to trigger execution

Outputs:
    panels_json: JSON string containing panel data for all walls
    panel_curves: DataTree of panel boundary curves for visualization
    joint_points: DataTree of joint location points
    debug_info: Debug information and status messages

Usage:
    1. Connect 'walls_json' from Wall Analyzer
    2. Optionally connect 'framing_json' from Framing Generator
    3. Set configuration parameters as needed
    4. Set 'run' to True to execute
    5. Use 'panels_json' for downstream processing
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

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.panels import (
    PanelConfig,
    decompose_wall_to_panels,
    decompose_all_walls,
    serialize_panel_results,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Helper Functions
# =============================================================================

def create_panel_boundary_curve(corners: dict):
    """
    Create a boundary curve from panel corners using RhinoCommonFactory.

    Args:
        corners: Dictionary with bottom_left, bottom_right, top_right, top_left

    Returns:
        Polyline curve for visualization, or None if creation fails
    """
    try:
        factory = get_factory()

        bl = corners["bottom_left"]
        br = corners["bottom_right"]
        tr = corners["top_right"]
        tl = corners["top_left"]

        points = [
            factory.create_point3d(bl["x"], bl["y"], bl["z"]),
            factory.create_point3d(br["x"], br["y"], br["z"]),
            factory.create_point3d(tr["x"], tr["y"], tr["z"]),
            factory.create_point3d(tl["x"], tl["y"], tl["z"]),
            factory.create_point3d(bl["x"], bl["y"], bl["z"]),  # Close the loop
        ]

        return factory.create_polyline_curve(points)
    except Exception as e:
        print(f"Error creating panel curve: {e}")
        return None


def create_joint_point(u_coord: float, wall_data: dict):
    """
    Create a point at a joint location.

    Args:
        u_coord: U coordinate of the joint
        wall_data: Wall data dictionary with base_plane

    Returns:
        Point3d at joint location, or None if creation fails
    """
    try:
        factory = get_factory()

        base_plane = wall_data.get("base_plane", {})
        origin = base_plane.get("origin", {})
        x_axis = base_plane.get("x_axis", {})
        height = wall_data.get("wall_height", wall_data.get("height", 8.0))
        base_elev = wall_data.get("base_elevation", 0.0)

        # Calculate joint point at mid-height of wall
        ox = origin.get("x", 0)
        oy = origin.get("y", 0)
        oz = base_elev

        xx = x_axis.get("x", 1)
        xy = x_axis.get("y", 0)

        point_x = ox + u_coord * xx
        point_y = oy + u_coord * xy
        point_z = oz + height / 2  # Mid-height

        return factory.create_point3d(point_x, point_y, point_z)
    except Exception as e:
        print(f"Error creating joint point: {e}")
        return None


def parse_walls_json(walls_json: str) -> list:
    """
    Parse walls JSON which can be a single wall or a list of walls.

    Args:
        walls_json: JSON string

    Returns:
        List of wall dictionaries
    """
    data = json.loads(walls_json)

    # Handle single wall or list of walls
    if isinstance(data, list):
        return data
    else:
        return [data]


def parse_framing_json(framing_json: str) -> list:
    """
    Parse framing JSON which can be a single result or a list.

    Args:
        framing_json: JSON string

    Returns:
        List of framing result dictionaries
    """
    if not framing_json:
        return None

    data = json.loads(framing_json)

    if isinstance(data, list):
        return data
    else:
        return [data]


# =============================================================================
# Main Component Logic
# =============================================================================

def main():
    """Main component execution."""
    debug = []

    # Initialize outputs
    panels_json = ""
    panel_curves = DataTree[object]()
    joint_points = DataTree[object]()

    # Check run input
    if not run:
        debug.append("Component not running. Set 'run' to True to execute.")
        return panels_json, panel_curves, joint_points, "\n".join(debug)

    # Validate inputs
    if not walls_json:
        debug.append("ERROR: No walls_json input provided")
        return panels_json, panel_curves, joint_points, "\n".join(debug)

    try:
        # Parse walls
        walls_data = parse_walls_json(walls_json)
        debug.append(f"Parsed {len(walls_data)} walls from JSON")

        # Parse framing data if provided
        framing_data = None
        if framing_json:
            framing_data = parse_framing_json(framing_json)
            debug.append(f"Parsed {len(framing_data)} framing results")

        # Build configuration
        config = PanelConfig(
            max_panel_length=max_panel_length if max_panel_length else 24.0,
            min_joint_to_opening=min_joint_to_opening if min_joint_to_opening else 1.0,
            min_joint_to_corner=min_joint_to_corner if min_joint_to_corner else 2.0,
            stud_spacing=stud_spacing if stud_spacing else 1.333,
        )
        debug.append(f"Config: max_length={config.max_panel_length}ft, stud_spacing={config.stud_spacing}ft")

        # Decompose walls to panels
        all_results = decompose_all_walls(walls_data, framing_data, config)
        debug.append(f"Decomposed {len(all_results)} walls into panels")

        # Process results for output
        total_panels = 0
        total_joints = 0

        for wall_idx, result in enumerate(all_results):
            wall_id = result["wall_id"]
            panels = result["panels"]
            joints = result["joints"]

            debug.append(f"  Wall {wall_id}: {len(panels)} panels, {len(joints)} joints")

            # Get corresponding wall data for geometry creation
            wall_data = walls_data[wall_idx] if wall_idx < len(walls_data) else {}

            # Create panel curves
            for panel_idx, panel in enumerate(panels):
                curve = create_panel_boundary_curve(panel["corners"])
                if curve:
                    path = GH_Path(wall_idx, panel_idx)
                    panel_curves.Add(curve, path)

            # Create joint points
            for joint_idx, joint in enumerate(joints):
                point = create_joint_point(joint["u_coord"], wall_data)
                if point:
                    path = GH_Path(wall_idx, joint_idx)
                    joint_points.Add(point, path)

            total_panels += len(panels)
            total_joints += len(joints)

        debug.append(f"Total: {total_panels} panels, {total_joints} joints")

        # Serialize results to JSON
        panels_json = json.dumps(all_results, indent=2)

    except Exception as e:
        import traceback
        debug.append(f"ERROR: {str(e)}")
        debug.append(traceback.format_exc())

    debug_info = "\n".join(debug)
    return panels_json, panel_curves, joint_points, debug_info


# =============================================================================
# Component Execution
# =============================================================================

# Set default values for optional inputs if not defined
try:
    max_panel_length
except NameError:
    max_panel_length = 24.0

try:
    min_joint_to_opening
except NameError:
    min_joint_to_opening = 1.0

try:
    min_joint_to_corner
except NameError:
    min_joint_to_corner = 2.0

try:
    stud_spacing
except NameError:
    stud_spacing = 1.333

try:
    walls_json
except NameError:
    walls_json = None

try:
    framing_json
except NameError:
    framing_json = None

try:
    run
except NameError:
    run = False

# Execute main
panels_json, panel_curves, joint_points, debug_info = main()
