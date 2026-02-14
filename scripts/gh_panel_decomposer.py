# File: scripts/gh_panel_decomposer.py
"""Panel Decomposer for Grasshopper.

Decomposes framed walls into manufacturable panels with optimized joint placement.
Handles wall corner geometry adjustments for accurate panel dimensions suitable
for offsite construction and prefabrication workflows.

Reads ``framing_segments`` from enriched walls_json (output by Junction
Analyzer) so that panels are created within junction-adjusted framing bounds
rather than the raw ``[0, wall_length]`` range. Walls with adjusted segments
are panelized per-segment; multi-segment walls (e.g., X-crossing splits)
produce independent panel runs that are merged into a single result.

Key Features:
1. Panel Decomposition
   - Splits walls into panels respecting max length constraints
   - Optimizes joint locations using dynamic programming
   - Aligns joints with stud locations for structural support

2. Framing-Segment-Aware Panelization
   - Reads ``framing_segments`` per wall (list of [u_start, u_end] pairs)
   - Panels created within segment bounds (extended, trimmed, split)
   - Multi-segment walls produce one panel run per segment
   - Openings filtered and shifted to segment-local coords for optimizer
   - Panel U coords shifted back to wall-absolute space after optimization
   - Backward compatible: absent framing_segments defaults to full wall

3. Corner Adjustment Calculation
   - Detects wall corners from endpoint proximity
   - Calculates extend/recede adjustments for face-to-face dimensions
   - Applies adjustments to panel geometry output (not Revit walls)
   - Segment-aware walls skip this step (junctions already handled)

4. Exclusion Zone Handling
   - Avoids joints near openings (12" per GA-216)
   - Avoids joints near wall corners (24" default)
   - Respects shear panel boundaries

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Curve and point creation for visualization
    - Grasshopper: DataTree for multi-wall output organization
    - timber_framing_generator.panels: Core panelization logic

Performance Considerations:
    - DP algorithm is O(n^2) where n = number of stud positions
    - Typical walls process in < 100ms
    - Corner detection is O(w^2) where w = number of walls
    - Multi-segment walls add one panelization pass per segment

Usage:
    1. Connect 'walls_json' from Junction Analyzer (enriched with framing_segments)
       or from Wall Analyzer (backward compatible without segments)
    2. Optionally connect 'framing_json' from Framing Generator (for stud-aligned joints)
    3. Configure panel constraints (max_length, joint offsets, etc.)
    4. Set 'run' to True to execute
    5. Use 'panels_json' for downstream processing or shop drawings

    Note: In the new pipeline (panelization-before-framing), this component
    typically receives walls_json directly without framing_json. The stud
    alignment is calculated from stud_spacing parameter instead.

Input Requirements:
    walls_json (walls_json) - str:
        JSON string from Junction Analyzer (enriched with framing_segments)
        or from Wall Analyzer (backward compatible without segments).
        Required: Yes
        Access: Item

    framing_json (framing_json) - str:
        JSON string from Framing Generator with framing elements
        Required: No (enhances joint stud detection when available)
        Access: Item

    max_panel_length (max_length) - float:
        Maximum panel length in feet
        Required: No (defaults to 24.0)
        Access: Item

    min_joint_to_opening (joint_opening) - float:
        Minimum distance from joint to opening edge in feet
        Required: No (defaults to 1.0 per GA-216)
        Access: Item

    min_joint_to_corner (joint_corner) - float:
        Minimum distance from joint to wall corner in feet
        Required: No (defaults to 2.0)
        Access: Item

    stud_spacing (stud_space) - float:
        Stud spacing in feet for joint alignment
        Required: No (defaults to 1.333 = 16" OC)
        Access: Item

    run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    panels_json (panels_json) - str:
        JSON string containing panel data for all walls

    panel_curves (panel_curves) - DataTree[Curve]:
        Panel boundary curves for visualization (closed polylines)

    joint_points (joint_points) - DataTree[Point3d]:
        Joint location points at mid-wall height

    debug_info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Panel geometry uses adjusted dimensions (not Revit centerlines)
    - Corner adjustments stored in results but don't modify Revit
    - Segment-aware walls use junction bounds directly (no extra corner detection)
    - Multi-segment panel U coords are in wall-absolute space after shift-back
    - Use gh_wall_corner_adjuster.py to apply changes to Revit walls

Error Handling:
    - Invalid JSON returns empty outputs with error in debug_info
    - Missing optional inputs use sensible defaults
    - Missing framing_segments falls back to full wall range
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

_modules_to_clear = [k for k in sys.modules.keys()
                     if 'timber_framing_generator' in k
                     or k == 'src']
for mod in _modules_to_clear:
    del sys.modules[mod]

# =============================================================================
# Project Setup
# =============================================================================

# Primary: worktree / feature-branch path
# Fallback: main repo path (for modules not yet in the worktree)
_WORKTREE_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\tfg-sheathing-junctions"
_MAIN_REPO_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

for _p in (_WORKTREE_PATH, _MAIN_REPO_PATH):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _MAIN_REPO_PATH)
sys.path.insert(0, _WORKTREE_PATH)

from src.timber_framing_generator.panels import (
    PanelConfig,
    decompose_all_walls,
    decompose_wall_to_panels,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Panel Decomposer"
COMPONENT_NICKNAME = "PanelDecomp"
COMPONENT_MESSAGE = "v1.1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Panels"

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log
        level: One of "info", "debug", "warning", "error", "remark"
    """
    print(f"[{level.upper()}] {message}")

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


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

    This function handles:
    1. Setting component metadata (name, category, etc.)
    2. Configuring input parameter names, descriptions, and access
    3. Configuring output parameter names and descriptions

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
        ("Walls JSON", "walls_json", "JSON string from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Framing JSON", "framing_json", "JSON string from Framing Generator (optional, for stud alignment)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Max Panel Length", "max_length", "Maximum panel length in feet (default 24.0)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Joint to Opening", "joint_opening", "Min distance from joint to opening in feet (default 1.0)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Joint to Corner", "joint_corner", "Min distance from joint to corner in feet (default 2.0)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Stud Spacing", "stud_space", "Stud spacing in feet (default 1.333 = 16\" OC)",
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

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output
    output_config = [
        ("Panels JSON", "panels_json", "JSON string containing panel data"),
        ("Panel Curves", "panel_curves", "Panel boundary curves for visualization"),
        ("Joint Points", "joint_points", "Joint location points"),
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

def validate_inputs(walls_json, run):
    """Validate component inputs.

    Args:
        walls_json: JSON string with wall data
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not walls_json:
        return False, "No walls_json input provided"

    try:
        json.loads(walls_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


def parse_walls_json(walls_json):
    """Parse walls JSON to list of wall dictionaries.

    Args:
        walls_json: JSON string

    Returns:
        List of wall dictionaries
    """
    data = json.loads(walls_json)
    return data if isinstance(data, list) else [data]


def parse_framing_json(framing_json):
    """Parse framing JSON to list of framing element dictionaries.

    Args:
        framing_json: JSON string or None

    Returns:
        List of framing dictionaries or None
    """
    if not framing_json:
        return None
    data = json.loads(framing_json)
    return data if isinstance(data, list) else [data]


def create_panel_boundary_curve(corners):
    """Create boundary curve from panel corners.

    Args:
        corners: Dictionary with bottom_left, bottom_right, top_right, top_left

    Returns:
        Closed polyline curve or None on failure
    """
    try:
        factory = get_factory()
        bl, br, tr, tl = corners["bottom_left"], corners["bottom_right"], corners["top_right"], corners["top_left"]

        points = [
            factory.create_point3d(bl["x"], bl["y"], bl["z"]),
            factory.create_point3d(br["x"], br["y"], br["z"]),
            factory.create_point3d(tr["x"], tr["y"], tr["z"]),
            factory.create_point3d(tl["x"], tl["y"], tl["z"]),
            factory.create_point3d(bl["x"], bl["y"], bl["z"]),  # Close loop
        ]
        return factory.create_polyline_curve(points)
    except Exception as e:
        log_debug(f"Error creating panel curve: {e}")
        return None


def create_joint_point(u_coord, wall_data):
    """Create point at joint location.

    Args:
        u_coord: U coordinate of joint
        wall_data: Wall data dictionary

    Returns:
        Point3d at joint location or None on failure
    """
    try:
        factory = get_factory()
        base_plane = wall_data.get("base_plane", {})
        origin = base_plane.get("origin", {})
        x_axis = base_plane.get("x_axis", {})
        height = wall_data.get("wall_height", wall_data.get("height", 8.0))
        base_elev = wall_data.get("base_elevation", 0.0)

        ox, oy = origin.get("x", 0), origin.get("y", 0)
        xx, xy = x_axis.get("x", 1), x_axis.get("y", 0)

        return factory.create_point3d(
            ox + u_coord * xx,
            oy + u_coord * xy,
            base_elev + height / 2
        )
    except Exception as e:
        log_debug(f"Error creating joint point: {e}")
        return None


def _has_adjusted_segments(wall_data):
    """Check if a wall has non-default framing segments.

    Returns True when ``framing_segments`` is present and differs from
    the default ``[[0, wall_length]]``.
    """
    segments = wall_data.get("framing_segments")
    if not segments:
        return False
    wall_length = wall_data.get("wall_length", 0)
    if len(segments) == 1:
        seg = segments[0]
        if abs(seg[0]) < 1e-6 and abs(seg[1] - wall_length) < 1e-6:
            return False
    return True


def _panelize_segment(wall_data, seg_start, seg_end, seg_idx, config):
    """Panelize a single framing segment of a wall.

    Creates a working copy of *wall_data* with ``wall_length`` set to
    the segment length and openings shifted into segment-local coords.
    Calls ``decompose_wall_to_panels()`` in ``[0, seg_length]`` space,
    then shifts resulting panel U coords back to wall-absolute coords.

    Corner adjustments are skipped because the junction system has
    already computed the correct segment bounds.

    Args:
        wall_data: Original wall dict (not mutated).
        seg_start: Segment start U in wall-absolute feet.
        seg_end: Segment end U in wall-absolute feet.
        seg_idx: Segment index (for panel IDs).
        config: PanelConfig instance.

    Returns:
        PanelResults dict with U coords in wall-absolute space.
    """
    seg_length = seg_end - seg_start
    wall_id = wall_data.get("wall_id", "unknown")

    # Build segment-local wall data
    working = dict(wall_data)
    working["wall_length"] = seg_length

    # Prefix wall_id for multi-segment to get unique panel IDs
    if seg_idx is not None:
        working["wall_id"] = f"{wall_id}_seg{seg_idx}"

    # Filter and shift openings into segment-local coords
    local_openings = []
    for o in wall_data.get("openings", []):
        o_start = o.get("u_start", 0)
        o_end = o.get("u_end", 0)
        # Opening must overlap segment
        if o_end > seg_start and o_start < seg_end:
            shifted = dict(o)
            shifted["u_start"] = max(o_start - seg_start, 0)
            shifted["u_end"] = min(o_end - seg_start, seg_length)
            local_openings.append(shifted)
    working["openings"] = local_openings

    # Panelize in [0, seg_length] space (no extra corner_adjustments)
    result = decompose_wall_to_panels(working, None, config)

    # Shift U coords back to wall-absolute space
    for panel in result.get("panels", []):
        panel["u_start"] += seg_start
        panel["u_end"] += seg_start
        # Shift corner geometry
        corners = panel.get("corners", {})
        _shift_corners_u(corners, seg_start, wall_data)

    for joint in result.get("joints", []):
        joint["u_coord"] += seg_start

    # Restore original wall_id in result
    result["wall_id"] = wall_id

    return result


def _shift_corners_u(corners, u_offset, wall_data):
    """Shift panel corner positions by a U offset along the wall X axis.

    Recalculates corner XY from the wall's base_plane to ensure correct
    world coordinates after the segment-local → absolute shift.

    Args:
        corners: Panel corners dict (bottom_left, bottom_right, etc.).
            **Modified in place.**
        u_offset: U offset to add (feet).
        wall_data: Original wall data with base_plane for direction.
    """
    base_plane = wall_data.get("base_plane", {})
    x_axis = base_plane.get("x_axis", {"x": 1, "y": 0, "z": 0})
    dx = x_axis.get("x", 1) * u_offset
    dy = x_axis.get("y", 0) * u_offset

    for key in ("bottom_left", "bottom_right", "top_right", "top_left"):
        pt = corners.get(key, {})
        if isinstance(pt, dict):
            pt["x"] = pt.get("x", 0) + dx
            pt["y"] = pt.get("y", 0) + dy


def process_panelization(walls_data, framing_data, config):
    """Process walls through panelization pipeline.

    Reads ``framing_segments`` per wall (injected by Junction Analyzer).
    Walls with adjusted segments are panelized per-segment; walls without
    segments (or with default ``[[0, wall_length]]``) go through the
    standard ``decompose_all_walls()`` path.

    Args:
        walls_data: List of wall dictionaries
        framing_data: List of framing dictionaries or None (from Framing Generator)
        config: PanelConfig instance

    Returns:
        tuple: (all_results, panel_curves_tree, joint_points_tree, info_lines)
    """
    log_info(f"Processing {len(walls_data)} walls")

    # Separate walls into segment-aware and default groups
    default_walls = []
    default_indices = []
    segment_walls = []
    segment_indices = []

    for idx, wd in enumerate(walls_data):
        if _has_adjusted_segments(wd):
            segment_walls.append(wd)
            segment_indices.append(idx)
        else:
            default_walls.append(wd)
            default_indices.append(idx)

    # Process default walls through standard pipeline (with corner detection)
    default_framing = None
    if framing_data and default_walls:
        default_framing = [
            framing_data[i] if i < len(framing_data) else None
            for i in default_indices
        ]
    default_results = (
        decompose_all_walls(default_walls, default_framing, config)
        if default_walls else []
    )

    # Process segment-aware walls per-segment
    segment_results = []
    for wd in segment_walls:
        segments = wd.get("framing_segments", [])
        wall_id = wd.get("wall_id", "unknown")
        wall_seg_results = []

        for si, (seg_s, seg_e) in enumerate(segments):
            seg_idx = si if len(segments) > 1 else None
            result = _panelize_segment(wd, seg_s, seg_e, seg_idx, config)
            wall_seg_results.append(result)

        if len(wall_seg_results) == 1:
            segment_results.append(wall_seg_results[0])
        else:
            # Merge multi-segment results into one entry per wall
            merged_panels = []
            merged_joints = []
            for r in wall_seg_results:
                merged_panels.extend(r.get("panels", []))
                merged_joints.extend(r.get("joints", []))
            segment_results.append({
                "wall_id": wall_id,
                "panels": merged_panels,
                "joints": merged_joints,
                "corner_adjustments": [],
                "total_panel_count": len(merged_panels),
                "original_wall_length": wd.get("wall_length", 0),
                "adjusted_wall_length": sum(s[1] - s[0] for s in segments),
                "metadata": {"framing_segments": segments},
            })

    # Rebuild results in original wall order
    all_results = [None] * len(walls_data)
    for i, idx in enumerate(default_indices):
        all_results[idx] = default_results[i]
    for i, idx in enumerate(segment_indices):
        all_results[idx] = segment_results[i]

    # Build visualization trees
    panel_curves = DataTree[object]()
    joint_points = DataTree[object]()
    info_lines = []
    total_panels = 0
    total_joints = 0

    for wall_idx, result in enumerate(all_results):
        wall_id = result["wall_id"]
        panels = result["panels"]
        joints = result["joints"]
        wall_data = walls_data[wall_idx] if wall_idx < len(walls_data) else {}

        seg_tag = ""
        if wall_idx in segment_indices:
            n_segs = len(walls_data[wall_idx].get("framing_segments", []))
            seg_tag = f" ({n_segs} segment{'s' if n_segs > 1 else ''})"

        info_lines.append(
            f"Wall {wall_id}{seg_tag}: {len(panels)} panels, {len(joints)} joints"
        )

        for panel_idx, panel in enumerate(panels):
            curve = create_panel_boundary_curve(panel["corners"])
            if curve:
                panel_curves.Add(curve, GH_Path(wall_idx, panel_idx))

        for joint_idx, joint in enumerate(joints):
            point = create_joint_point(joint["u_coord"], wall_data)
            if point:
                joint_points.Add(point, GH_Path(wall_idx, joint_idx))

        total_panels += len(panels)
        total_joints += len(joints)

    info_lines.append(f"Total: {total_panels} panels, {total_joints} joints")
    log_info(f"Completed: {total_panels} panels, {total_joints} joints")

    return all_results, panel_curves, joint_points, info_lines

# =============================================================================
# Main Function
# =============================================================================

def main(walls_json_in, framing_json_in, max_length_in, joint_opening_in,
         joint_corner_in, stud_space_in, run_in):
    """Main entry point for the component.

    Args:
        walls_json_in: JSON string with wall data.
        framing_json_in: JSON string with framing data (optional).
        max_length_in: Max panel length in feet (optional).
        joint_opening_in: Min joint-to-opening distance (optional).
        joint_corner_in: Min joint-to-corner distance (optional).
        stud_space_in: Stud spacing in feet (optional).
        run_in: Boolean trigger.

    Returns:
        tuple: (panels_json, panel_curves, joint_points, debug_info)
            - panels_json: JSON string with panel data for all walls.
            - panel_curves: DataTree of panel boundary curves.
            - joint_points: DataTree of joint location points.
            - debug_info: Debug information string.
    """
    setup_component()

    # Initialize outputs
    panels_json = ""
    panel_curves = DataTree[object]()
    joint_points = DataTree[object]()
    debug_lines = []

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs(walls_json_in, run_in)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            debug_lines.append(error_msg)
            return panels_json, panel_curves, joint_points, "\n".join(debug_lines)

        # Parse inputs
        walls_data = parse_walls_json(walls_json_in)
        framing_data = parse_framing_json(framing_json_in) if framing_json_in else None
        debug_lines.append(f"Parsed {len(walls_data)} walls")

        # Build configuration
        config = PanelConfig(
            max_panel_length=max_length_in if max_length_in else 24.0,
            min_joint_to_opening=joint_opening_in if joint_opening_in else 1.0,
            min_joint_to_corner=joint_corner_in if joint_corner_in else 2.0,
            stud_spacing=stud_space_in if stud_space_in else 1.333,
        )
        debug_lines.append(f"Config: max={config.max_panel_length}ft, stud={config.stud_spacing}ft")

        # Process panelization
        all_results, panel_curves, joint_points, info_lines = process_panelization(
            walls_data, framing_data, config
        )
        debug_lines.extend(info_lines)

        # Serialize results
        panels_json = json.dumps(all_results, indent=2)

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return panels_json, panel_curves, joint_points, "\n".join(debug_lines)

# =============================================================================
# Execution
# =============================================================================

# Set default values for optional inputs
try:
    walls_json
except NameError:
    walls_json = None

try:
    framing_json
except NameError:
    framing_json = None

try:
    max_length
except NameError:
    max_length = None

try:
    joint_opening
except NameError:
    joint_opening = None

try:
    joint_corner
except NameError:
    joint_corner = None

try:
    stud_space
except NameError:
    stud_space = None

try:
    run
except NameError:
    run = False

# Execute main — pass inputs explicitly to avoid CPython 3 exec() scope issues
if __name__ == "__main__":
    panels_json, panel_curves, joint_points, debug_info = main(
        walls_json, framing_json, max_length, joint_opening,
        joint_corner, stud_space, run
    )
