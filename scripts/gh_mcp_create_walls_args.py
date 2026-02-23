# File: scripts/gh_mcp_create_walls_args.py
"""MCP Create Walls Args Extractor for Grasshopper.

Extracts arguments from the MCP ``create_walls`` tool call and prepares
inputs for the Kreo-to-Revit pipeline. Supports two execution modes:

Modes:
  All-in-one:
    Agent calls create_walls with just wall_height (+ optional door/window
    schedules). All requested elements are created in one pass.

  Staged:
    Step 1 - Walls only: agent calls create_walls(wall_height=8)
             -> gh_kreo_create_walls creates walls, outputs walls_result_json
    Step 2 - Doors: agent calls create_walls(walls_result_json=..., door_schedule=[...])
             -> run_walls=False, walls_result_passthrough feeds door creator
    Step 3 - Windows: agent calls create_walls(walls_result_json=..., window_schedule=[...])
             -> run_walls=False, walls_result_passthrough feeds window creator

Key Features:
1. MCP Argument Parsing
   - Reads Args JSON from Deconstruct Tool Call
   - Extracts walls_result_json (staged mode), door/window schedules, wall_height

2. Staged vs All-in-one Gate
   - walls_result_json in args -> staged mode: skip wall creation, pass through IDs
   - No walls_result_json -> all-in-one mode: create walls + requested elements

3. Separate Run Gates
   - run_walls: True only in all-in-one mode
   - run_doors: True when agent sends door_schedule or doors_json
   - run_windows: True when agent sends window_schedule or windows_json
   - In manual mode (no MCP args): all three gates active if default Panels have data

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Argument parsing

Usage:
    1. Connect Deconstruct Tool Call "Args" output to input 0
    2. Connect pre-wired Panel with walls JSON to input 1
    3. Connect pre-wired Panel with doors JSON to input 2
    4. Connect pre-wired Panel with windows JSON to input 3
    5. Wire walls_result_passthrough (output 7) + gh_kreo_create_walls output
       to a merge, then to door/window creators
    6. Wire run_walls to gh_kreo_create_walls trigger
    7. Wire run_doors / run_windows to door/window creator triggers

Input Requirements:
    MCP Args (mcp_args) - str:
        JSON string from Deconstruct Tool Call "Args" output.
        May contain: walls_result_json, door_schedule, window_schedule,
        wall_height, level_name.
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Default Walls JSON (default_walls_json) - str:
        Pre-wired Kreo walls JSON from a GH Panel (fallback).
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Default Doors JSON (default_doors_json) - str:
        Pre-wired Kreo doors JSON from a GH Panel (fallback).
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Default Windows JSON (default_windows_json) - str:
        Pre-wired Kreo windows JSON from a GH Panel (fallback).
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Walls JSON (walls_json) - str:
        Kreo walls JSON (from MCP or default). Used by gh_kreo_to_walls_json.

    Doors JSON (doors_json) - str:
        Kreo doors JSON (from MCP or default). Empty if agent didn't request doors.

    Windows JSON (windows_json) - str:
        Kreo windows JSON (from MCP or default). Empty if agent didn't request windows.

    Config JSON (config_json) - str:
        Configuration: wall_height_ft, level_name, door_schedule, window_schedule.

    Run Walls (run_walls) - bool:
        True in all-in-one mode (wall data available, no prior walls_result_json).
        False in staged mode (walls already exist).

    Run Doors (run_doors) - bool:
        True when agent requests doors (door_schedule or doors_json present).
        In manual mode: True if default doors Panel has data.

    Run Windows (run_windows) - bool:
        True when agent requests windows (window_schedule or windows_json present).
        In manual mode: True if default windows Panel has data.

    Walls Result Passthrough (walls_result_passthrough) - str:
        In staged mode: the walls_result_json from the previous create_walls call.
        In all-in-one mode: empty string (gh_kreo_create_walls provides it instead).
        Wire this + gh_kreo_create_walls.walls_result_json into a merge; use
        whichever is non-empty as the walls_result_json for door/window creators.

    Info (info) - str:
        Debug information about mode, input sources, and run gates.

Author: ConstructAI Demo
Version: 1.1.0
"""

# =============================================================================
# Imports
# =============================================================================

import sys
import json
import traceback

import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

import Grasshopper

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MCP Create Walls Args"
COMPONENT_NICKNAME = "MCPWallArgs"
COMPONENT_MESSAGE = "v1.1"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

DEFAULT_WALL_HEIGHT_FT = 8.0

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message: str, level: str = "info") -> None:
    print(f"[{level.upper()}] {message}")
    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)


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

    inputs = ghenv.Component.Params.Input

    input_config = [
        ("MCP Args", "mcp_args",
         "JSON string from Deconstruct Tool Call Args output",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Default Walls JSON", "default_walls_json",
         "Pre-wired Kreo walls JSON from Panel (fallback)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Default Doors JSON", "default_doors_json",
         "Pre-wired Kreo doors JSON from Panel (fallback)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Default Windows JSON", "default_windows_json",
         "Pre-wired Kreo windows JSON from Panel (fallback)",
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

    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Walls JSON", "walls_json",
         "Kreo walls JSON for gh_kreo_to_walls_json"),
        ("Doors JSON", "doors_json",
         "Kreo doors JSON. Empty if agent didn't request doors"),
        ("Windows JSON", "windows_json",
         "Kreo windows JSON. Empty if agent didn't request windows"),
        ("Config JSON", "config_json",
         "Configuration: wall_height_ft, level_name, door/window schedules"),
        ("Run Walls", "run_walls",
         "True in all-in-one mode. False in staged mode (walls already exist)"),
        ("Run Doors", "run_doors",
         "True when agent requests doors"),
        ("Run Windows", "run_windows",
         "True when agent requests windows"),
        ("Walls Result Passthrough", "walls_result_passthrough",
         "Staged mode: prior walls_result_json. Merge with create_walls output"),
        ("Info", "info",
         "Debug information about mode, sources, and run gates"),
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


def _has_content(val) -> bool:
    """Check if a value has meaningful string content."""
    if val is None:
        return False
    s = str(val).strip()
    if s in ("", "null", "None", "[]", "{}"):
        return False
    return True


def _parse_mcp_args(args_raw) -> tuple:
    """Parse MCP tool call arguments.

    Returns:
        tuple: (is_valid, args_dict, error_message)
    """
    if args_raw is None:
        return False, {}, "No MCP args received"

    if not isinstance(args_raw, str):
        args_raw = str(args_raw)

    args_raw = args_raw.strip()
    if not args_raw:
        return False, {}, "Empty MCP args"

    try:
        parsed = json.loads(args_raw)
    except json.JSONDecodeError as e:
        return False, {}, f"Invalid JSON in MCP args: {e}"

    if not isinstance(parsed, dict):
        return False, {}, "MCP args must be a JSON object"

    return True, parsed, None


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point.

    Returns:
        tuple: (walls_json, doors_json, windows_json, config_json,
                run_walls, run_doors, run_windows, walls_result_passthrough, info)
    """
    setup_component()

    walls_json = ""
    doors_json = ""
    windows_json = ""
    config_json = ""
    run_walls = False
    run_doors = False
    run_windows = False
    walls_result_passthrough = ""
    info_lines = []

    try:
        # Read inputs by index
        mcp_args_raw = _read_input(0)
        default_walls = _read_input(1)
        default_doors = _read_input(2)
        default_windows = _read_input(3)

        # Parse MCP args
        args_valid, args_dict, args_error = _parse_mcp_args(mcp_args_raw)

        # ---------------------------------------------------------------
        # Detect execution mode
        # Staged: agent passes walls_result_json from a prior call
        # All-in-one: no prior walls_result_json, create everything fresh
        # ---------------------------------------------------------------
        prior_walls_result = None
        if args_valid:
            raw_wres = args_dict.get("walls_result_json")
            if _has_content(raw_wres):
                prior_walls_result = str(raw_wres).strip()

        staged_mode = prior_walls_result is not None
        if staged_mode:
            walls_result_passthrough = prior_walls_result
            info_lines.append("Mode: STAGED (walls_result_json provided, skipping wall creation)")
        else:
            info_lines.append("Mode: ALL-IN-ONE (creating walls fresh)")

        # run_all: agent can pass run_all=true to request all element types
        run_all = False
        if args_valid:
            raw_run_all = args_dict.get("run_all")
            if raw_run_all is not None:
                if isinstance(raw_run_all, bool):
                    run_all = raw_run_all
                else:
                    run_all = str(raw_run_all).strip().lower() in ("true", "1", "yes")

        # Detect what the agent explicitly requested.
        # Intent signals (any of these = "I want this element type"):
        #   - run_all=true
        #   - Key present in args at all (even if value is empty string)
        #   - Non-empty doors_json / windows_json value
        #   - Non-empty door_schedule / window_schedule list
        agent_wants_doors = False
        agent_wants_windows = False
        if args_valid:
            agent_wants_doors = (
                run_all
                or "doors_json" in args_dict
                or _has_content(args_dict.get("doors_json"))
                or bool(args_dict.get("door_schedule"))
            )
            agent_wants_windows = (
                run_all
                or "windows_json" in args_dict
                or _has_content(args_dict.get("windows_json"))
                or bool(args_dict.get("window_schedule"))
            )

        # Resolve walls_json: only needed in all-in-one mode
        walls_source = "none"
        if not staged_mode:
            if args_valid and _has_content(args_dict.get("walls_json")):
                walls_json = str(args_dict["walls_json"]).strip()
                walls_source = "mcp"
            elif _has_content(default_walls):
                walls_json = str(default_walls).strip()
                walls_source = "default"

        # Resolve doors_json: MCP args take priority; fall back to default
        # panel unconditionally (pre-wired Kreo JSON = always use it).
        doors_source = "none"
        if args_valid and _has_content(args_dict.get("doors_json")):
            doors_json = str(args_dict["doors_json"]).strip()
            doors_source = "mcp"
        elif _has_content(default_doors):
            doors_json = str(default_doors).strip()
            doors_source = "default"

        # Resolve windows_json (same logic)
        windows_source = "none"
        if args_valid and _has_content(args_dict.get("windows_json")):
            windows_json = str(args_dict["windows_json"]).strip()
            windows_source = "mcp"
        elif _has_content(default_windows):
            windows_json = str(default_windows).strip()
            windows_source = "default"

        # Build config from MCP args
        config = {}
        if args_valid:
            wall_height = args_dict.get("wall_height", DEFAULT_WALL_HEIGHT_FT)
            try:
                config["wall_height_ft"] = float(wall_height)
            except (TypeError, ValueError):
                config["wall_height_ft"] = DEFAULT_WALL_HEIGHT_FT

            level_name = args_dict.get("level_name")
            if level_name:
                config["level_name"] = str(level_name)

            door_schedule = args_dict.get("door_schedule")
            if isinstance(door_schedule, list) and door_schedule:
                config["door_schedule"] = door_schedule

            window_schedule = args_dict.get("window_schedule")
            if isinstance(window_schedule, list) and window_schedule:
                config["window_schedule"] = window_schedule
        else:
            config["wall_height_ft"] = DEFAULT_WALL_HEIGHT_FT

        config_json = json.dumps(config, indent=2)

        # ---------------------------------------------------------------
        # Run gates
        # ---------------------------------------------------------------
        if staged_mode:
            # Staged: walls already exist, only run what agent requested
            run_walls = False
            run_doors = agent_wants_doors and bool(doors_json)
            run_windows = agent_wants_windows and bool(windows_json)
        elif args_valid:
            # All-in-one MCP: run whatever we have data for.
            # Default panels provide doors/windows even when the agent doesn't
            # explicitly pass door/window keys — this is the expected all-in-one
            # behavior (Kreo JSON pre-wired = always create all elements).
            # Staged mode (walls_result_json in args) handles "add to existing walls".
            run_walls = bool(walls_json)
            run_doors = bool(doors_json)
            run_windows = bool(windows_json)
        else:
            # Manual mode (no MCP args): all gates OFF.
            # Use Boolean Toggles wired directly to each creator for manual runs.
            run_walls = False
            run_doors = False
            run_windows = False

        # Build info
        info_lines.append(f"MCP Args: {'valid' if args_valid else args_error}")
        info_lines.append(f"  walls_json: {walls_source} ({len(walls_json)} chars)")
        info_lines.append(f"  doors_json: {doors_source} ({len(doors_json)} chars)")
        info_lines.append(f"  windows_json: {windows_source} ({len(windows_json)} chars)")
        info_lines.append(f"  walls_result_passthrough: {len(walls_result_passthrough)} chars")
        info_lines.append(f"  run_walls={run_walls}, run_doors={run_doors} (wants={agent_wants_doors}), run_windows={run_windows} (wants={agent_wants_windows})")

        info = "\n".join(info_lines)
        log_info(info)

        return (walls_json, doors_json, windows_json, config_json,
                run_walls, run_doors, run_windows, walls_result_passthrough, info)

    except Exception as e:
        error_msg = f"Error in MCP Create Walls Args: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return (walls_json, doors_json, windows_json, config_json,
                False, False, False, "", error_msg)


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    (walls_json, doors_json, windows_json, config_json,
     run_walls, run_doors, run_windows, walls_result_passthrough, info) = main()
