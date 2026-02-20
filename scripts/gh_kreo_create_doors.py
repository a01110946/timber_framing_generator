# File: scripts/gh_kreo_create_doors.py
"""Kreo Door Creator for Grasshopper.

Places Revit doors from Kreo AI detection JSON. This is Component 2 of the
three-step Kreo-to-Revit pipeline (walls -> doors -> windows). Reads
walls_result_json from the wall creator to match doors to host walls and
looks up walls fresh from the Revit document using ElementIds.

Key Features:
1. Kreo JSON Parsing
   - Reads filtered Kreo door JSON
   - Validates input format and required fields

2. Wall Matching via walls_result_json
   - Reconstructs lightweight wall geometry from walls_ft coordinates
   - Converts door pixel coords to feet using scale/max_y_px from walls
   - Matches each door to its nearest host wall

3. Door Placement
   - Looks up host walls fresh from Revit using ElementId integers
   - Places doors as hosted family instances in a single transaction
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
    - Single pass through door list for matching
    - One Revit transaction for all door placements

Usage:
    1. Connect filtered Kreo doors JSON to input 0
    2. Connect walls_result_json from gh_kreo_create_walls to input 1
    3. Optionally connect config JSON to input 2
    4. Set input 3 (run) to True to execute
    5. Wire output 1 (doors_result_json) downstream
    6. Monitor output 2 (info) for status

Input Requirements:
    Doors JSON (doors_json) - str:
        Filtered Kreo JSON with door line segments. Format:
        {"status": "Ready", "lines": [{"p1": [x,y], "p2": [x,y],
         "length": m, "thickness": m, "revit_type": "Family : Type"}, ...]}
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
        Optional config: {"sill_height_ft": 0.0}
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Run (run) - bool:
        Trigger flag. Set to True to execute.
        Required: Yes
        Access: Item
        Type Hint: bool (set via GH UI)

Outputs:
    Doors Result JSON (doors_result_json) - str:
        JSON with door_ids, doors_placed count, and unmatched count.

    Info (info) - str:
        Human-readable status message.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes
    - Uses constructai_demo package (NOT timber_framing_generator)
    - match_openings_to_walls returns wall LIST indices, mapped to
      wall_ids via array position
    - Uses place_openings_by_id() for fresh DB.Wall lookup

Error Handling:
    - Missing doors_json or walls_result_json: error status
    - run=False: idle status, no Revit operations
    - Invalid JSON: error with parse details
    - Revit API errors: transaction rollback, error in result_json
    - Unmatched doors: warning in info, not fatal

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
from src.constructai_demo.kreo_parser import parse_doors
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
    find_door_family,
    ensure_door_types,
    match_door_to_schedule,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Kreo Create Doors"
COMPONENT_NICKNAME = "KreoDoors"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

MATCH_TOLERANCE_FT = 1.5

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
        ("Doors JSON", "doors_json",
         "Filtered Kreo JSON with door line segments",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls Result JSON", "walls_result_json",
         "Output from gh_kreo_create_walls with wall_ids and walls_ft",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional config: sill_height_ft (default 0.0)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Set True to execute (places doors in Revit)",
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
        ("Doors Result JSON", "doors_result_json",
         "JSON with door_ids and placement counts"),
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
            length_ft=0.0,  # not needed for matching
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
        ))
    return converted


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


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for Kreo door creator.

    Returns:
        tuple: (doors_result_json, info)
    """
    setup_component()

    doors_result_json = ""
    info = "Idle (run=False)"

    try:
        # Read inputs by index
        doors_json_raw = _read_input(0)
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
            return doors_result_json, info

        # Validate doors_json
        if doors_json_raw is None or not str(doors_json_raw).strip():
            error = "No doors_json provided"
            log_error(error)
            doors_result_json = json.dumps({"status": "error", "message": error})
            return doors_result_json, error

        # Validate walls_result_json
        if walls_result_raw is None or not str(walls_result_raw).strip():
            error = "No walls_result_json provided (run wall creator first)"
            log_error(error)
            doors_result_json = json.dumps({"status": "error", "message": error})
            return doors_result_json, error

        # Parse walls_result_json
        walls_result = json.loads(str(walls_result_raw).strip())
        if walls_result.get("status") != "success":
            error = f"Wall creator reported: {walls_result.get('message', 'unknown error')}"
            log_error(error)
            doors_result_json = json.dumps({"status": "error", "message": error})
            return doors_result_json, error

        wall_ids = walls_result["wall_ids"]
        walls_ft = walls_result["walls_ft"]
        scale = walls_result["scale_m_per_px"]
        max_y_px = walls_result["max_y_px"]
        level_name = walls_result.get("level_name")

        # Parse config for sill height and door schedule
        config = _parse_config(config_raw)
        sill_height_ft = float(config.get("sill_height_ft", 0.0))
        door_schedule = config.get("door_schedule")  # List[dict] or None

        # ---------------------------------------------------------------
        # Step 1: Parse Kreo doors JSON
        # ---------------------------------------------------------------
        log_info("Parsing Kreo doors JSON...")
        doors_json_str = str(doors_json_raw).strip()
        kreo_doors = parse_doors(doors_json_str)
        log_info(f"  Parsed {len(kreo_doors)} doors")

        if not kreo_doors:
            result = {
                "status": "success",
                "doors_placed": 0,
                "door_ids": [],
                "unmatched": 0,
                "fallbacks": [],
                "message": "No doors in input JSON",
            }
            doors_result_json = json.dumps(result, indent=2)
            info = "Kreo Create Doors: 0 doors in input"
            log_info(info)
            return doors_result_json, info

        # ---------------------------------------------------------------
        # Step 2: Convert door coordinates using wall scale
        # ---------------------------------------------------------------
        log_info("Converting door coordinates...")
        converted_doors = _convert_openings(kreo_doors, scale, max_y_px, "door")
        log_info(f"  Converted {len(converted_doors)} doors to feet")

        # Diagnostic: log revit_type for each converted door
        for cd in converted_doors:
            log_info(
                f"  Door {cd.original_index}: revit_type={cd.revit_type!r}"
            )

        # ---------------------------------------------------------------
        # Step 2b: Door schedule matching (if schedule provided)
        # ---------------------------------------------------------------
        schedule_fallbacks = []
        type_map = {}

        doc = _get_revit_doc()

        if isinstance(door_schedule, list) and door_schedule:
            log_info(f"Door schedule: {len(door_schedule)} entries, ensuring types...")
            type_map, schedule_fallbacks = ensure_door_types(doc, door_schedule)
            log_info(f"  Type map: {len(type_map)} entries, {len(schedule_fallbacks)} fallbacks")

            # Match each converted door to a schedule entry by width
            matched_to_schedule = 0
            for cd in converted_doors:
                # Skip doors that already have a revit_type from the JSON
                if cd.revit_type:
                    continue
                schedule_id = match_door_to_schedule(
                    cd.width_ft, door_schedule, tolerance_in=2.0
                )
                if schedule_id and schedule_id in type_map:
                    cd.revit_type = type_map[schedule_id]
                    matched_to_schedule += 1
            log_info(f"  Matched {matched_to_schedule} doors to schedule entries")
        else:
            log_info("No door_schedule in config, using revit_type from JSON")

        # ---------------------------------------------------------------
        # Step 2c: Track doors with null/missing revit_type (fallbacks)
        # ---------------------------------------------------------------
        default_symbol = find_door_family(doc)
        default_type_name = None
        if default_symbol:
            default_type_name = f"{default_symbol.Family.Name} : {default_symbol.Name}"

        # Parse raw lines once to get door_type metadata
        raw_parsed = json.loads(doors_json_str)
        if isinstance(raw_parsed, dict):
            raw_lines = raw_parsed.get("lines", [])
        elif isinstance(raw_parsed, list):
            raw_lines = raw_parsed
        else:
            raw_lines = []

        for i, cd in enumerate(converted_doors):
            if not cd.revit_type:
                door_type_mark = ""
                if i < len(raw_lines) and isinstance(raw_lines[i], dict):
                    door_type_mark = raw_lines[i].get("door_type", "")

                reason = "No revit_type specified (unknown door type)"
                if door_type_mark:
                    reason = (
                        f"Door type '{door_type_mark}' not in schedule, "
                        f"using default family"
                    )

                fb_entry = {
                    "door_index": cd.original_index,
                    "requested": None,
                    "resolved": default_type_name,
                    "reason": reason,
                }
                if door_type_mark:
                    fb_entry["door_type"] = door_type_mark

                schedule_fallbacks.append(fb_entry)
                log_warning(
                    f"  Door {cd.original_index}: no revit_type, "
                    f"fallback -> {default_type_name}"
                )

        # ---------------------------------------------------------------
        # Step 3: Reconstruct wall geometry and match doors
        # ---------------------------------------------------------------
        log_info("Matching doors to host walls...")
        reconstructed_walls = _reconstruct_walls(walls_ft)
        matched = match_openings_to_walls(
            reconstructed_walls, converted_doors, tolerance_ft=MATCH_TOLERANCE_FT)

        unmatched = get_unmatched_openings(converted_doors, matched)
        unmatched_count = len(unmatched)
        matched_count = sum(len(v) for v in matched.values())
        log_info(f"  Matched {matched_count} doors to {len(matched)} walls")
        if unmatched_count > 0:
            log_warning(f"  {unmatched_count} doors could not be matched to walls")

        # ---------------------------------------------------------------
        # Step 4: Get Revit level, place doors
        # ---------------------------------------------------------------
        level = find_level(doc, level_name)
        if level is None:
            error = "No levels found in Revit document"
            log_error(error)
            doors_result_json = json.dumps({"status": "error", "message": error})
            return doors_result_json, error

        log_info(f"Placing {matched_count} doors in Revit (sill={sill_height_ft} ft)...")
        placed = place_openings_by_id(
            doc,
            matched_openings=matched,
            wall_ids=wall_ids,
            level=level,
            opening_type="door",
            sill_height_ft=sill_height_ft,
        )
        log_info(f"  Placed {len(placed)} doors")

        # ---------------------------------------------------------------
        # Step 5: Build result
        # ---------------------------------------------------------------
        door_ids = [eid for _, eid in placed]

        result = {
            "status": "success",
            "doors_placed": len(placed),
            "door_ids": door_ids,
            "unmatched": unmatched_count,
            "fallbacks": schedule_fallbacks,
            "message": f"Placed {len(placed)} doors ({unmatched_count} unmatched)",
        }
        if schedule_fallbacks:
            result["message"] += f", {len(schedule_fallbacks)} type fallbacks"

        doors_result_json = json.dumps(result, indent=2)

        info_lines = [
            "Kreo Create Doors: SUCCESS",
            f"  Doors: {len(placed)} placed",
        ]
        if unmatched_count > 0:
            info_lines.append(f"  Unmatched: {unmatched_count} doors")
        if schedule_fallbacks:
            info_lines.append(f"  Type fallbacks: {len(schedule_fallbacks)}")
            for fb in schedule_fallbacks:
                fb_id = fb.get("schedule_id", fb.get("door_index", "?"))
                info_lines.append(
                    f"    {fb_id}: {fb.get('requested')} -> {fb.get('resolved')}"
                )
        info = "\n".join(info_lines)
        log_info(info)

        return doors_result_json, info

    except Exception as e:
        error_msg = f"Error in Kreo Create Doors: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        result = {"status": "error", "message": error_msg}
        doors_result_json = json.dumps(result, indent=2)
        return doors_result_json, error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    doors_result_json, info = main()
