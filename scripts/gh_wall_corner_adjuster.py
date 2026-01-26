# File: scripts/gh_wall_corner_adjuster.py
"""Wall Corner Adjuster for Grasshopper (Rhino.Inside.Revit).

Modifies Revit wall geometry at corners to convert from centerline joins to
face-to-face dimensions for accurate panel manufacturing. This component
applies the corner adjustments calculated by the Panel Decomposer to the
actual Revit wall elements.

Key Features:
1. Wall Corner Unjoining
   - Disallows wall joins at specified ends using WallUtils
   - Prevents Revit from automatically re-joining walls

2. Wall Location Curve Modification
   - Extends or shortens wall location curves
   - Maintains wall properties while adjusting geometry

3. Transaction Management
   - All modifications wrapped in Revit transaction
   - Supports dry-run mode for preview without changes

Environment:
    Rhino 8
    Grasshopper
    Rhino.Inside.Revit
    Python component (CPython 3)

Dependencies:
    - Autodesk.Revit.DB: Wall manipulation, transactions
    - RhinoInside.Revit: Revit document access
    - timber_framing_generator.panels: Corner adjustment data

Performance Considerations:
    - Transaction overhead ~50ms per wall
    - Batch processing recommended for many walls
    - Undo available via Revit's undo stack

Usage:
    1. Connect 'panels_json' from Panel Decomposer (contains corner_adjustments)
    2. Or connect 'adjustments_json' directly with adjustment data
    3. Set 'dry_run' to True to preview without changes
    4. Set 'run' to True to execute

Input Requirements:
    panels_json (panels_json) - str:
        JSON string from Panel Decomposer containing corner_adjustments
        Required: Yes (or adjustments_json)
        Access: Item

    adjustments_json (adj_json) - str:
        Direct corner adjustments JSON (alternative to panels_json)
        Required: No
        Access: Item

    dry_run (dry_run) - bool:
        Preview mode - calculates but doesn't modify Revit
        Required: No (defaults to True for safety)
        Access: Item

    run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    modified_walls (modified) - list:
        List of modified wall element IDs

    preview_lines (preview) - DataTree[Line]:
        Preview lines showing original and adjusted wall extents

    debug_info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Uses WallUtils.DisallowWallJoinAtEnd to prevent auto-rejoining
    - Modifies Wall.Location.Curve to extend/shorten walls
    - All changes in single transaction for undo support

Error Handling:
    - Invalid wall IDs logged and skipped
    - Failed modifications don't halt other walls
    - Dry run mode prevents accidental changes

Author: Timber Framing Generator
Version: 1.0.0
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
# Revit API Setup (Rhino.Inside.Revit)
# =============================================================================

try:
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    clr.AddReference("RhinoInside.Revit")

    from Autodesk.Revit.DB import (
        Transaction,
        Wall,
        WallUtils,
        Line as RevitLine,
        XYZ,
        ElementId,
        BuiltInParameter,
    )
    from RhinoInside.Revit import Revit

    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_AVAILABLE = False
    REVIT_IMPORT_ERROR = str(e)

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

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Wall Corner Adjuster"
COMPONENT_NICKNAME = "CornerAdj"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Panels"

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
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


def log_debug(message):
    print(f"[DEBUG] {message}")


def log_info(message):
    print(f"[INFO] {message}")


def log_warning(message):
    log_message(message, "warning")


def log_error(message):
    log_message(message, "error")

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component."""
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Panels JSON", "panels_json", "JSON from Panel Decomposer with corner_adjustments", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Adjustments JSON", "adj_json", "Direct adjustments JSON (alternative)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Dry Run", "dry_run", "Preview mode - no Revit changes (default True)", Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run", "Boolean to trigger execution", Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    outputs = ghenv.Component.Params.Output
    output_config = [
        ("Modified Walls", "modified", "List of modified wall element IDs"),
        ("Preview Lines", "preview", "Original and adjusted wall extent lines"),
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

def validate_inputs(panels_json, adj_json, run):
    """Validate component inputs."""
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not panels_json and not adj_json:
        return False, "No panels_json or adj_json input provided"

    if not REVIT_AVAILABLE:
        return False, f"Revit API not available: {REVIT_IMPORT_ERROR}"

    return True, None


def extract_adjustments(panels_json, adj_json):
    """Extract corner adjustments from inputs.

    Args:
        panels_json: JSON from Panel Decomposer
        adj_json: Direct adjustments JSON

    Returns:
        List of adjustment dictionaries
    """
    all_adjustments = []

    # From panels_json (Panel Decomposer output)
    if panels_json:
        data = json.loads(panels_json)
        panels_list = data if isinstance(data, list) else [data]

        for panel_result in panels_list:
            adjustments = panel_result.get("corner_adjustments", [])
            all_adjustments.extend(adjustments)

    # From direct adjustments
    if adj_json:
        adj_data = json.loads(adj_json)
        adj_list = adj_data if isinstance(adj_data, list) else [adj_data]
        all_adjustments.extend(adj_list)

    return all_adjustments


def get_wall_by_id(doc, wall_id):
    """Get Revit wall element by ID string.

    Args:
        doc: Revit document
        wall_id: Wall ID as string (may include prefix like "wall_")

    Returns:
        Wall element or None
    """
    try:
        # Extract numeric ID if prefixed
        if isinstance(wall_id, str):
            # Handle formats like "wall_12345" or just "12345"
            numeric_part = ''.join(filter(str.isdigit, wall_id))
            if numeric_part:
                element_id = ElementId(int(numeric_part))
            else:
                log_warning(f"Could not parse wall ID: {wall_id}")
                return None
        else:
            element_id = ElementId(int(wall_id))

        element = doc.GetElement(element_id)
        if isinstance(element, Wall):
            return element
        else:
            log_warning(f"Element {wall_id} is not a Wall")
            return None

    except Exception as e:
        log_warning(f"Error getting wall {wall_id}: {e}")
        return None


def adjust_wall_at_corner(doc, wall, corner_type, adjustment_type, amount, dry_run):
    """Adjust a wall's location curve at one end.

    Args:
        doc: Revit document
        wall: Wall element
        corner_type: "start" or "end"
        adjustment_type: "extend" or "recede"
        amount: Adjustment amount in feet
        dry_run: If True, don't modify

    Returns:
        tuple: (success, original_line, new_line)
    """
    try:
        location = wall.Location
        if not hasattr(location, 'Curve'):
            log_warning(f"Wall {wall.Id.IntegerValue} has no location curve")
            return False, None, None

        curve = location.Curve
        if not isinstance(curve, RevitLine):
            log_warning(f"Wall {wall.Id.IntegerValue} curve is not a line")
            return False, None, None

        # Get current endpoints
        start_pt = curve.GetEndPoint(0)
        end_pt = curve.GetEndPoint(1)

        # Calculate direction
        direction = (end_pt - start_pt).Normalize()

        # Calculate new endpoints
        new_start = start_pt
        new_end = end_pt

        if corner_type == "start":
            if adjustment_type == "extend":
                # Extend start backwards (opposite direction)
                new_start = start_pt - direction * amount
            else:  # recede
                # Recede start forwards
                new_start = start_pt + direction * amount
        else:  # "end"
            if adjustment_type == "extend":
                # Extend end forwards
                new_end = end_pt + direction * amount
            else:  # recede
                # Recede end backwards
                new_end = end_pt - direction * amount

        # Create preview lines
        factory = get_factory()
        original_line = factory.create_line(
            (start_pt.X, start_pt.Y, start_pt.Z),
            (end_pt.X, end_pt.Y, end_pt.Z)
        )
        new_line = factory.create_line(
            (new_start.X, new_start.Y, new_start.Z),
            (new_end.X, new_end.Y, new_end.Z)
        )

        if dry_run:
            log_info(f"  [DRY RUN] Would {adjustment_type} wall at {corner_type} by {amount:.3f}ft")
            return True, original_line, new_line

        # Actually modify the wall
        # First, disallow wall join at this end
        end_index = 0 if corner_type == "start" else 1
        WallUtils.DisallowWallJoinAtEnd(wall, end_index)

        # Create new line and set it
        new_curve = RevitLine.CreateBound(new_start, new_end)
        location.Curve = new_curve

        log_info(f"  Modified wall at {corner_type}: {adjustment_type} by {amount:.3f}ft")
        return True, original_line, new_line

    except Exception as e:
        log_error(f"Error adjusting wall: {e}")
        return False, None, None


def process_adjustments(doc, adjustments, dry_run):
    """Process all corner adjustments.

    Args:
        doc: Revit document
        adjustments: List of adjustment dictionaries
        dry_run: If True, preview only

    Returns:
        tuple: (modified_ids, preview_lines, info_lines)
    """
    modified_ids = []
    preview_lines = DataTree[object]()
    info_lines = []

    # Group adjustments by wall
    adjustments_by_wall = {}
    for adj in adjustments:
        wall_id = adj.get("wall_id", "")
        if wall_id not in adjustments_by_wall:
            adjustments_by_wall[wall_id] = []
        adjustments_by_wall[wall_id].append(adj)

    log_info(f"Processing {len(adjustments)} adjustments for {len(adjustments_by_wall)} walls")
    info_lines.append(f"Processing {len(adjustments)} adjustments")

    wall_idx = 0
    for wall_id, wall_adjs in adjustments_by_wall.items():
        wall = get_wall_by_id(doc, wall_id)
        if wall is None:
            info_lines.append(f"  Wall {wall_id}: NOT FOUND")
            continue

        info_lines.append(f"  Wall {wall_id} (Revit ID: {wall.Id.IntegerValue}):")

        for adj in wall_adjs:
            corner_type = adj.get("corner_type", "end")
            adjustment_type = adj.get("adjustment_type", "extend")
            amount = adj.get("adjustment_amount", 0)
            connecting_wall = adj.get("connecting_wall_id", "?")

            info_lines.append(f"    {corner_type}: {adjustment_type} by {amount:.3f}ft (connects to {connecting_wall})")

            success, orig_line, new_line = adjust_wall_at_corner(
                doc, wall, corner_type, adjustment_type, amount, dry_run
            )

            if success:
                if orig_line:
                    preview_lines.Add(orig_line, GH_Path(wall_idx, 0))  # Original
                if new_line:
                    preview_lines.Add(new_line, GH_Path(wall_idx, 1))  # Adjusted

        if not dry_run:
            modified_ids.append(wall.Id.IntegerValue)

        wall_idx += 1

    return modified_ids, preview_lines, info_lines

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component."""
    setup_component()

    # Initialize outputs
    modified_walls = []
    preview_lines = DataTree[object]()
    debug_lines = []

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs(panels_json, adj_json, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            debug_lines.append(error_msg)
            return modified_walls, preview_lines, "\n".join(debug_lines)

        # Get Revit document
        doc = Revit.ActiveDBDocument
        if doc is None:
            log_error("No active Revit document")
            debug_lines.append("ERROR: No active Revit document")
            return modified_walls, preview_lines, "\n".join(debug_lines)

        # Extract adjustments
        adjustments = extract_adjustments(panels_json, adj_json)
        debug_lines.append(f"Found {len(adjustments)} corner adjustments")

        if not adjustments:
            debug_lines.append("No adjustments to apply")
            return modified_walls, preview_lines, "\n".join(debug_lines)

        # Check dry_run mode
        is_dry_run = dry_run if dry_run is not None else True
        debug_lines.append(f"Mode: {'DRY RUN (preview only)' if is_dry_run else 'LIVE (modifying Revit)'}")

        if is_dry_run:
            # Process without transaction
            modified_walls, preview_lines, info_lines = process_adjustments(
                doc, adjustments, dry_run=True
            )
            debug_lines.extend(info_lines)
        else:
            # Process within transaction
            with Transaction(doc, "Adjust Wall Corners for Panelization") as t:
                t.Start()
                try:
                    modified_walls, preview_lines, info_lines = process_adjustments(
                        doc, adjustments, dry_run=False
                    )
                    debug_lines.extend(info_lines)
                    t.Commit()
                    debug_lines.append(f"Transaction committed: {len(modified_walls)} walls modified")
                except Exception as e:
                    t.RollBack()
                    log_error(f"Transaction rolled back: {e}")
                    debug_lines.append(f"ERROR: Transaction rolled back - {e}")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return modified_walls, preview_lines, "\n".join(debug_lines)

# =============================================================================
# Execution
# =============================================================================

# Set default values for optional inputs
try:
    panels_json
except NameError:
    panels_json = None

try:
    adj_json
except NameError:
    adj_json = None

try:
    dry_run
except NameError:
    dry_run = True  # Safe default

try:
    run
except NameError:
    run = False

# Execute main
if __name__ == "__main__":
    modified, preview, debug_info = main()
