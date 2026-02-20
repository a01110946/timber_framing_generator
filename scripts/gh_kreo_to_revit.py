# File: scripts/gh_kreo_to_revit.py
"""Kreo JSON to Revit Elements Creator for Grasshopper.

Orchestrates the full pipeline from Kreo AI detection JSON to Revit walls,
doors, and windows. This is part of the ConstructAI demo and is completely
separate from the Timber Framing Generator pipeline.

Key Features:
1. JSON Parsing
   - Reads filtered Kreo JSON for walls, doors, and windows
   - Validates input format and required fields

2. Coordinate Conversion
   - Derives meters-per-pixel scale from wall data
   - Flips Y-axis (top-left origin to bottom-left)
   - Converts to Revit internal units (feet)

3. Wall Classification
   - Classifies walls by thickness (2x4 interior / 2x6 exterior)
   - Finds matching Revit WallTypes

4. Opening Matching
   - Assigns doors and windows to nearest host wall
   - Computes insertion points on wall lines

5. Revit Element Creation
   - Creates walls via DB.Wall.Create with appropriate WallTypes
   - Places doors and windows as hosted family instances
   - Two transactions: walls first, then openings

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit

Dependencies:
    - Grasshopper: Component framework and parameter access
    - Autodesk.Revit.DB: Wall creation and family placement
    - src.constructai_demo: Parsing, conversion, classification, matching

Performance Considerations:
    - Single pass through each element list
    - Two Revit transactions (walls, then openings)
    - Scale computation is O(n) over walls

Usage:
    1. Connect filtered Kreo walls JSON to input 0
    2. Connect filtered Kreo doors JSON to input 1 (optional)
    3. Connect filtered Kreo windows JSON to input 2 (optional)
    4. Connect optional config JSON to input 3
    5. Set input 4 (run) to True to execute
    6. Wire output 1 (result_json) downstream
    7. Monitor output 2 (info) for status

Input Requirements:
    Walls JSON (walls_json) - str:
        Filtered Kreo JSON with walls. Format:
        {"status": "Ready", "lines": [{"p1": [x,y], "p2": [x,y],
         "length": m, "thickness": m}, ...]}
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Doors JSON (doors_json) - str:
        Filtered Kreo JSON with doors. Same format as walls.
        Required: No (skip door placement if missing)
        Access: Item
        Type Hint: str (set via GH UI)

    Windows JSON (windows_json) - str:
        Filtered Kreo JSON with windows. Same format as walls.
        Required: No (skip window placement if missing)
        Access: Item
        Type Hint: str (set via GH UI)

    Config JSON (config_json) - str:
        Optional config: {"wall_height_ft": 8.0, "level_name": "Level 1"}
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Run (run) - bool:
        Trigger flag. Set to True to execute.
        Required: Yes
        Access: Item
        Type Hint: bool (set via GH UI)

Outputs:
    Result JSON (result_json) - str:
        Summary with counts and element IDs:
        {"status": "success", "walls_created": N, "doors_placed": N,
         "windows_placed": N, "wall_ids": [...], ...}

    Info (info) - str:
        Human-readable status message.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes
    - Uses constructai_demo package (NOT timber_framing_generator)
    - Two separate Revit transactions for walls and openings
    - Opening placement requires host walls to exist first

Error Handling:
    - Missing walls_json: error status, no Revit operations
    - run=False: idle status, no Revit operations
    - Invalid JSON: error with parse details
    - Revit API errors: transaction rollback, error in result_json
    - Unmatched openings: warning in info, not fatal

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
from src.constructai_demo.kreo_parser import parse_walls, parse_doors, parse_windows
from src.constructai_demo.coordinate_converter import convert_all_elements
from src.constructai_demo.wall_classifier import classify_wall, get_classification_summary
from src.constructai_demo.opening_matcher import (
    match_openings_to_walls,
    get_unmatched_openings,
)
from src.constructai_demo.revit_creator import (
    create_walls as revit_create_walls,
    place_openings as revit_place_openings,
    find_level,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Kreo to Revit"
COMPONENT_NICKNAME = "KreoRevit"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

DEFAULT_WALL_HEIGHT_FT = 8.0

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
        ("Walls JSON", "walls_json",
         "Filtered Kreo JSON with wall line segments",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Doors JSON", "doors_json",
         "Filtered Kreo JSON with door line segments (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Windows JSON", "windows_json",
         "Filtered Kreo JSON with window line segments (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional config: wall_height_ft, level_name",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Set True to execute (creates Revit elements)",
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
        ("Result JSON", "result_json",
         "Summary JSON with counts and element IDs"),
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


def _element_id_str(element_id) -> str:
    """Convert a Revit ElementId to string (works on 2023 and 2024+)."""
    if hasattr(element_id, "IntegerValue"):
        return str(element_id.IntegerValue)
    if hasattr(element_id, "Value"):
        return str(element_id.Value)
    return str(element_id)


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


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for Kreo to Revit creator.

    Returns:
        tuple: (result_json, info)
    """
    setup_component()

    result_json = ""
    info = "Idle (run=False)"

    try:
        # Read inputs by index
        walls_json_raw = _read_input(0)
        doors_json_raw = _read_input(1)
        windows_json_raw = _read_input(2)
        config_raw = _read_input(3)
        run_raw = _read_input(4, False)

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
            return result_json, info

        # Validate walls_json (required)
        if walls_json_raw is None or not str(walls_json_raw).strip():
            error = "No walls_json provided"
            log_error(error)
            result_json = json.dumps({"status": "error", "message": error})
            return result_json, error

        # Parse config
        config = _parse_config(config_raw)
        wall_height_ft = float(config.get("wall_height_ft", DEFAULT_WALL_HEIGHT_FT))
        level_name = config.get("level_name", None)

        # ---------------------------------------------------------------
        # Step 1: Parse Kreo JSON
        # ---------------------------------------------------------------
        log_info("Parsing Kreo JSON...")
        walls_json_str = str(walls_json_raw).strip()
        log_info(f"  walls_json type={type(walls_json_raw).__name__}, len={len(walls_json_str)}")
        log_info(f"  walls_json[:200] = {walls_json_str[:200]}")
        kreo_walls = parse_walls(walls_json_str)
        log_info(f"  Parsed {len(kreo_walls)} walls")

        kreo_doors = []
        if doors_json_raw and str(doors_json_raw).strip():
            kreo_doors = parse_doors(str(doors_json_raw).strip())
            log_info(f"  Parsed {len(kreo_doors)} doors")

        kreo_windows = []
        if windows_json_raw and str(windows_json_raw).strip():
            kreo_windows = parse_windows(str(windows_json_raw).strip())
            log_info(f"  Parsed {len(kreo_windows)} windows")

        # ---------------------------------------------------------------
        # Step 2: Convert coordinates
        # ---------------------------------------------------------------
        log_info("Converting coordinates (pixel -> feet)...")
        converted = convert_all_elements(kreo_walls, kreo_doors, kreo_windows)
        log_info(f"  Scale: {converted.scale_m_per_px:.6f} m/px")
        log_info(f"  Max Y: {converted.max_y_px:.1f} px")

        # ---------------------------------------------------------------
        # Step 3: Classify walls
        # ---------------------------------------------------------------
        classification = get_classification_summary(converted.walls)
        log_info(f"  Classification: {classification}")

        # ---------------------------------------------------------------
        # Step 4: Get Revit document and level
        # ---------------------------------------------------------------
        doc = _get_revit_doc()
        level = find_level(doc, level_name)
        if level is None:
            error = "No levels found in Revit document"
            log_error(error)
            result_json = json.dumps({"status": "error", "message": error})
            return result_json, error
        log_info(f"  Using level: {level.Name} (elevation: {level.Elevation:.2f} ft)")

        # ---------------------------------------------------------------
        # Step 5: Create walls in Revit
        # ---------------------------------------------------------------
        log_info(f"Creating {len(converted.walls)} walls (height={wall_height_ft} ft)...")
        created_walls = revit_create_walls(
            doc, converted.walls, level, wall_height_ft)
        log_info(f"  Created {len(created_walls)} walls in Revit")

        # Build wall index -> DB.Wall map for opening placement
        host_walls = {idx: wall for idx, wall in created_walls}

        # Collect wall element IDs
        wall_ids = []
        for idx, wall in created_walls:
            wall_ids.append(_element_id_str(wall.Id))

        # ---------------------------------------------------------------
        # Step 6: Match and place openings
        # ---------------------------------------------------------------
        doors_placed = 0
        windows_placed = 0
        door_ids = []
        window_ids = []
        unmatched_count = 0

        all_openings = converted.doors + converted.windows
        if all_openings and host_walls:
            log_info("Matching openings to host walls...")
            matched = match_openings_to_walls(
                converted.walls, all_openings, tolerance_ft=1.5)

            unmatched = get_unmatched_openings(all_openings, matched)
            unmatched_count = len(unmatched)
            if unmatched_count > 0:
                log_warning(f"  {unmatched_count} openings could not be matched to walls")

            matched_count = sum(len(v) for v in matched.values())
            log_info(f"  Matched {matched_count} openings to {len(matched)} walls")

            if matched:
                log_info("Placing openings in Revit...")
                placed = revit_place_openings(
                    doc, matched, host_walls, level,
                    default_sill_height_ft=3.0)

                for opening_type, instance in placed:
                    eid = _element_id_str(instance.Id)
                    if opening_type == "door":
                        doors_placed += 1
                        door_ids.append(eid)
                    elif opening_type == "window":
                        windows_placed += 1
                        window_ids.append(eid)

        # ---------------------------------------------------------------
        # Step 7: Build result
        # ---------------------------------------------------------------
        result = {
            "status": "success",
            "walls_created": len(created_walls),
            "doors_placed": doors_placed,
            "windows_placed": windows_placed,
            "unmatched_openings": unmatched_count,
            "wall_classification": classification,
            "wall_ids": wall_ids,
            "door_ids": door_ids,
            "window_ids": window_ids,
            "scale_m_per_px": converted.scale_m_per_px,
            "wall_height_ft": wall_height_ft,
            "level": level.Name,
            "message": (
                f"Created {len(created_walls)} walls, "
                f"placed {doors_placed} doors and {windows_placed} windows"
            ),
        }
        result_json = json.dumps(result, indent=2)

        info_lines = [
            "Kreo to Revit: SUCCESS",
            f"  Walls: {len(created_walls)} created ({classification})",
            f"  Doors: {doors_placed} placed",
            f"  Windows: {windows_placed} placed",
        ]
        if unmatched_count > 0:
            info_lines.append(f"  Unmatched: {unmatched_count} openings")
        info = "\n".join(info_lines)
        log_info(info)

        return result_json, info

    except Exception as e:
        error_msg = f"Error in Kreo to Revit: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        result = {"status": "error", "message": error_msg}
        result_json = json.dumps(result, indent=2)
        return result_json, error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    result_json, info = main()
