# File: scripts/gh_kreo_create_windows.py
"""Kreo Window Creator for Grasshopper.

Places Revit windows from Kreo AI detection JSON. This is Component 3 of the
three-step Kreo-to-Revit pipeline (walls -> doors -> windows). Reads
walls_result_json from the wall creator to match windows to host walls and
looks up walls fresh from the Revit document using ElementIds.

Key Features:
1. Kreo JSON Parsing
   - Reads filtered Kreo window JSON
   - Validates input format and required fields

2. Wall Matching via walls_result_json
   - Reconstructs lightweight wall geometry from walls_ft coordinates
   - Converts window pixel coords to feet using scale/max_y_px from walls
   - Matches each window to its nearest host wall

3. Window Placement
   - Looks up host walls fresh from Revit using ElementId integers
   - Places windows as hosted family instances in a single transaction
   - Sets sill height parameter (default 3.0 ft)
   - Avoids stale DB.Wall reference issue

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit

Dependencies:
    - Grasshopper: Component framework and parameter access
    - Autodesk.Revit.DB: Family instance placement
    - src.constructai_demo: Parsing, conversion, matching, placement

Performance Considerations:
    - Single pass through window list for matching
    - One Revit transaction for all window placements

Usage:
    1. Connect filtered Kreo windows JSON to input 0
    2. Connect walls_result_json from gh_kreo_create_walls to input 1
    3. Optionally set sill height in config (input 2)
    4. Set input 3 (run) to True to execute
    5. Wire output 1 (windows_result_json) downstream
    6. Monitor output 2 (info) for status

Input Requirements:
    Windows JSON (windows_json) - str:
        Filtered Kreo JSON with window line segments. Format:
        {"status": "Ready", "lines": [{"p1": [x,y], "p2": [x,y],
         "length": m, "thickness": m}, ...]}
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Walls Result JSON (walls_result_json) - str:
        Output from gh_kreo_create_walls with wall_ids, walls_ft,
        scale_m_per_px, max_y_px.
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Config JSON (config_json) - str:
        Optional config: {"sill_height_ft": 3.0}
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Run (run) - bool:
        Trigger flag. Set to True to execute.
        Required: Yes
        Access: Item
        Type Hint: bool (set via GH UI)

Outputs:
    Windows Result JSON (windows_result_json) - str:
        JSON with window_ids, windows_placed count, and unmatched count.

    Info (info) - str:
        Human-readable status message.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes
    - Uses constructai_demo package (NOT timber_framing_generator)
    - match_openings_to_walls returns wall LIST indices, mapped to
      wall_ids via array position
    - Uses place_openings_by_id() for fresh DB.Wall lookup
    - Sets sill height on placed window instances

Error Handling:
    - Missing windows_json or walls_result_json: error status
    - run=False: idle status, no Revit operations
    - Invalid JSON: error with parse details
    - Revit API errors: transaction rollback, error in result_json
    - Unmatched windows: warning in info, not fatal

Author: ConstructAI Demo
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
import Grasshopper

# Force fresh imports of constructai_demo modules
for mod_name in list(sys.modules.keys()):
    if "constructai_demo" in mod_name:
        del sys.modules[mod_name]

# ConstructAI Demo modules
from src.constructai_demo.kreo_parser import parse_windows
from src.constructai_demo.coordinate_converter import (
    ConvertedOpening,
    ConvertedPoint,
    ConvertedWall,
    convert_point,
    METERS_TO_FEET,
)
from src.constructai_demo.opening_matcher import (
    match_openings_to_walls,
    get_unmatched_openings,
)
from src.constructai_demo.revit_creator import (
    place_openings_by_id,
    find_level,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Kreo Create Windows"
COMPONENT_NICKNAME = "KreoWindows"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

MATCH_TOLERANCE_FT = 1.5
DEFAULT_SILL_HEIGHT_FT = 3.0

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message: str, level: str = "info") -> None:
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


def log_info(message: str) -> None:
    print(f"[INFO] {message}")


def log_warning(message: str) -> None:
    log_message(message, "warning")


def log_error(message: str) -> None:
    log_message(message, "error")


# =============================================================================
# Component Setup
# =============================================================================

def setup_component() -> None:
    """Initialize and configure the Grasshopper component."""
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Windows JSON", "windows_json",
         "Filtered Kreo JSON with window line segments",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls Result JSON", "walls_result_json",
         "Output from gh_kreo_create_walls with wall_ids and walls_ft",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional config: sill_height_ft (default 3.0)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Set True to execute (places windows in Revit)",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            p = inputs[i]
            if p.Name != name:
                p.Name = name
            if p.NickName != nick:
                p.NickName = nick
            if p.Description != desc:
                p.Description = desc
            if p.Access != access:
                p.Access = access

    # Configure outputs (start from index 1)
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Windows Result JSON", "windows_result_json",
         "JSON with window_ids and placement counts"),
        ("Info", "info",
         "Human-readable status message"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1
        if idx < outputs.Count:
            p = outputs[idx]
            if p.Name != name:
                p.Name = name
            if p.NickName != nick:
                p.NickName = nick
            if p.Description != desc:
                p.Description = desc


# =============================================================================
# Helper Functions
# =============================================================================

def _read_input(index: int, default=None):
    """Read a GH input value by parameter index via VolatileData."""
    inputs = ghenv.Component.Params.Input
    if index >= inputs.Count:
        return default
    param = inputs[index]
    if param.VolatileDataCount == 0:
        return default
    all_data = list(param.VolatileData.AllData(True))
    if not all_data:
        return default
    goo = all_data[0]
    if hasattr(goo, "Value"):
        return goo.Value
    if hasattr(goo, "ScriptVariable"):
        return goo.ScriptVariable()
    return default


def _get_revit_doc():
    """Get the active Revit document via RhinoInside."""
    import clr as _clr
    _clr.AddReference("RhinoInside.Revit")
    from RhinoInside.Revit import Revit
    return Revit.ActiveDBDocument


def _parse_config(config_raw) -> dict:
    """Parse optional config JSON."""
    if config_raw is None:
        return {}
    if not isinstance(config_raw, str):
        config_raw = str(config_raw)
    config_raw = config_raw.strip()
    if not config_raw:
        return {}
    try:
        parsed = json.loads(config_raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _reconstruct_walls(walls_ft: list) -> list:
    """Reconstruct lightweight ConvertedWall list from walls_ft coordinates.

    Only p1/p2 are needed for opening matching. Other fields are set
    to placeholder values since they aren't used by match_openings_to_walls.

    Args:
        walls_ft: List of dicts with p1_x, p1_y, p2_x, p2_y (in feet).

    Returns:
        List of ConvertedWall objects for matching.
    """
    walls = []
    for i, wf in enumerate(walls_ft):
        walls.append(ConvertedWall(
            p1=ConvertedPoint(x=wf["p1_x"], y=wf["p1_y"]),
            p2=ConvertedPoint(x=wf["p2_x"], y=wf["p2_y"]),
            length_ft=0.0,
            thickness_ft=0.0,
            thickness_m=0.0,
            original_index=i,
        ))
    return walls


def _convert_openings(kreo_openings, scale, max_y_px, opening_type):
    """Convert parsed Kreo openings to ConvertedOpening using scale from walls.

    Args:
        kreo_openings: List of KreoOpening from parser.
        scale: Meters per pixel (from walls_result_json).
        max_y_px: Maximum Y pixel (from walls_result_json).
        opening_type: "door" or "window".

    Returns:
        List of ConvertedOpening in Revit feet.
    """
    converted = []
    for op in kreo_openings:
        p1 = convert_point(op.p1.x, op.p1.y, scale, max_y_px)
        p2 = convert_point(op.p2.x, op.p2.y, scale, max_y_px)
        converted.append(ConvertedOpening(
            p1=p1,
            p2=p2,
            width_ft=op.length * METERS_TO_FEET,
            opening_type=opening_type,
            original_index=op.index,
            revit_type=op.revit_type,
            sill_height_in=op.sill_height_in,
        ))
    return converted


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for Kreo window creator.

    Returns:
        tuple: (windows_result_json, info)
    """
    setup_component()

    windows_result_json = ""
    info = "Idle (run=False)"

    try:
        # Read inputs by index
        windows_json_raw = _read_input(0)
        walls_result_raw = _read_input(1)
        config_raw = _read_input(2)
        run_raw = _read_input(3, False)

        # Check run flag
        run = False
        if isinstance(run_raw, bool):
            run = run_raw
        elif isinstance(run_raw, str):
            run = run_raw.strip().lower() in ("true", "1", "yes")
        elif run_raw is not None:
            run = bool(run_raw)

        if not run:
            log_info("Idle (run=False)")
            return windows_result_json, info

        # Validate windows_json
        if windows_json_raw is None or not str(windows_json_raw).strip():
            error = "No windows_json provided"
            log_error(error)
            windows_result_json = json.dumps({"status": "error", "message": error})
            return windows_result_json, error

        # Validate walls_result_json
        if walls_result_raw is None or not str(walls_result_raw).strip():
            error = "No walls_result_json provided (run wall creator first)"
            log_error(error)
            windows_result_json = json.dumps({"status": "error", "message": error})
            return windows_result_json, error

        # Parse walls_result_json
        walls_result = json.loads(str(walls_result_raw).strip())
        if walls_result.get("status") != "success":
            error = f"Wall creator reported: {walls_result.get('message', 'unknown error')}"
            log_error(error)
            windows_result_json = json.dumps({"status": "error", "message": error})
            return windows_result_json, error

        wall_ids = walls_result["wall_ids"]
        walls_ft = walls_result["walls_ft"]
        scale = walls_result["scale_m_per_px"]
        max_y_px = walls_result["max_y_px"]
        level_name = walls_result.get("level_name")

        # Parse config for sill height
        config = _parse_config(config_raw)
        sill_height_ft = float(config.get("sill_height_ft", DEFAULT_SILL_HEIGHT_FT))

        # ---------------------------------------------------------------
        # Step 1: Parse Kreo windows JSON
        # ---------------------------------------------------------------
        log_info("Parsing Kreo windows JSON...")
        windows_json_str = str(windows_json_raw).strip()
        kreo_windows = parse_windows(windows_json_str)
        log_info(f"  Parsed {len(kreo_windows)} windows")

        if not kreo_windows:
            result = {
                "status": "success",
                "windows_placed": 0,
                "window_ids": [],
                "unmatched": 0,
                "message": "No windows in input JSON",
            }
            windows_result_json = json.dumps(result, indent=2)
            info = "Kreo Create Windows: 0 windows in input"
            log_info(info)
            return windows_result_json, info

        # ---------------------------------------------------------------
        # Step 2: Convert window coordinates using wall scale
        # ---------------------------------------------------------------
        log_info("Converting window coordinates...")
        converted_windows = _convert_openings(
            kreo_windows, scale, max_y_px, "window")
        log_info(f"  Converted {len(converted_windows)} windows to feet")

        # ---------------------------------------------------------------
        # Step 3: Reconstruct wall geometry and match windows
        # ---------------------------------------------------------------
        log_info("Matching windows to host walls...")
        reconstructed_walls = _reconstruct_walls(walls_ft)
        matched = match_openings_to_walls(
            reconstructed_walls, converted_windows, tolerance_ft=MATCH_TOLERANCE_FT)

        unmatched = get_unmatched_openings(converted_windows, matched)
        unmatched_count = len(unmatched)
        matched_count = sum(len(v) for v in matched.values())
        log_info(f"  Matched {matched_count} windows to {len(matched)} walls")
        if unmatched_count > 0:
            log_warning(f"  {unmatched_count} windows could not be matched to walls")

        # ---------------------------------------------------------------
        # Step 4: Get Revit doc and level, place windows
        # ---------------------------------------------------------------
        doc = _get_revit_doc()

        level = find_level(doc, level_name)
        if level is None:
            error = "No levels found in Revit document"
            log_error(error)
            windows_result_json = json.dumps({"status": "error", "message": error})
            return windows_result_json, error

        log_info(
            f"Placing {matched_count} windows in Revit "
            f"(sill={sill_height_ft} ft)..."
        )
        placed = place_openings_by_id(
            doc,
            matched_openings=matched,
            wall_ids=wall_ids,
            level=level,
            opening_type="window",
            sill_height_ft=sill_height_ft,
        )
        log_info(f"  Placed {len(placed)} windows")

        # ---------------------------------------------------------------
        # Step 5: Build result
        # ---------------------------------------------------------------
        window_ids = [eid for _, eid in placed]

        result = {
            "status": "success",
            "windows_placed": len(placed),
            "window_ids": window_ids,
            "unmatched": unmatched_count,
            "sill_height_ft": sill_height_ft,
            "message": (
                f"Placed {len(placed)} windows "
                f"({unmatched_count} unmatched, sill={sill_height_ft} ft)"
            ),
        }
        windows_result_json = json.dumps(result, indent=2)

        info_lines = [
            "Kreo Create Windows: SUCCESS",
            f"  Windows: {len(placed)} placed (sill={sill_height_ft} ft)",
        ]
        if unmatched_count > 0:
            info_lines.append(f"  Unmatched: {unmatched_count} windows")
        info = "\n".join(info_lines)
        log_info(info)

        return windows_result_json, info

    except Exception as e:
        error_msg = f"Error in Kreo Create Windows: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        result = {"status": "error", "message": error_msg}
        windows_result_json = json.dumps(result, indent=2)
        return windows_result_json, error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    windows_result_json, info = main()
