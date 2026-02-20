# File: scripts/gh_mcp_create_walls_args.py
"""MCP Create Walls Args Extractor for Grasshopper.

Extracts arguments from the MCP ``create_walls`` tool call and prepares
inputs for the gh_kreo_to_revit.py component. Supports both MCP-provided
JSON and pre-wired default JSON from GH Panels.

Key Features:
1. MCP Argument Parsing
   - Reads Args JSON from Deconstruct Tool Call
   - Extracts walls_json, doors_json, windows_json from MCP args
   - Extracts optional wall_height config

2. Default Fallback
   - If MCP args don't contain JSON data, falls back to pre-wired
     Panel inputs (default_walls_json, etc.)
   - Allows the component to work both via MCP and manual GH triggers

3. Pipeline Gating
   - Outputs run=True only when valid walls data is available
   - Builds config_json from MCP args or defaults

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Argument parsing

Performance Considerations:
    - Lightweight JSON parsing only

Usage:
    1. Connect Deconstruct Tool Call "Args" output to input 0
    2. Connect pre-wired Panel with walls JSON to input 1
    3. Connect pre-wired Panel with doors JSON to input 2
    4. Connect pre-wired Panel with windows JSON to input 3
    5. Wire outputs to gh_kreo_to_revit.py inputs

Input Requirements:
    MCP Args (mcp_args) - str:
        JSON string from Deconstruct Tool Call "Args" output.
        May contain walls_json, doors_json, windows_json, wall_height.
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Default Walls JSON (default_walls_json) - str:
        Pre-wired Kreo walls JSON from a GH Panel (fallback).
        Required: No (used when MCP args don't contain walls_json)
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
        Kreo walls JSON (from MCP or default).

    Doors JSON (doors_json) - str:
        Kreo doors JSON (from MCP or default).

    Windows JSON (windows_json) - str:
        Kreo windows JSON (from MCP or default).

    Config JSON (config_json) - str:
        Configuration for gh_kreo_to_revit: wall_height_ft, level_name.

    Run (run) - bool:
        True when valid walls data is available.

    Info (info) - str:
        Debug information about input sources.

Author: ConstructAI Demo
Version: 1.0.0
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
COMPONENT_MESSAGE = "v1.0"
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
         "Kreo walls JSON for gh_kreo_to_revit"),
        ("Doors JSON", "doors_json",
         "Kreo doors JSON for gh_kreo_to_revit"),
        ("Windows JSON", "windows_json",
         "Kreo windows JSON for gh_kreo_to_revit"),
        ("Config JSON", "config_json",
         "Configuration JSON for gh_kreo_to_revit"),
        ("Run", "run",
         "True when valid walls data is available"),
        ("Info", "info",
         "Debug information about input sources"),
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
        tuple: (walls_json, doors_json, windows_json, config_json, run, info)
    """
    setup_component()

    walls_json = ""
    doors_json = ""
    windows_json = ""
    config_json = ""
    run = False
    info_lines = []

    try:
        # Read inputs by index
        mcp_args_raw = _read_input(0)
        default_walls = _read_input(1)
        default_doors = _read_input(2)
        default_windows = _read_input(3)

        # Parse MCP args
        args_valid, args_dict, args_error = _parse_mcp_args(mcp_args_raw)

        # Resolve walls_json: MCP args take priority, then default Panel
        walls_source = "none"
        if args_valid and _has_content(args_dict.get("walls_json")):
            walls_json = str(args_dict["walls_json"]).strip()
            walls_source = "mcp"
        elif _has_content(default_walls):
            walls_json = str(default_walls).strip()
            walls_source = "default"

        # Resolve doors_json
        doors_source = "none"
        if args_valid and _has_content(args_dict.get("doors_json")):
            doors_json = str(args_dict["doors_json"]).strip()
            doors_source = "mcp"
        elif _has_content(default_doors):
            doors_json = str(default_doors).strip()
            doors_source = "default"

        # Resolve windows_json
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

            # Pass door_schedule through to config for door creator
            door_schedule = args_dict.get("door_schedule")
            if isinstance(door_schedule, list) and door_schedule:
                config["door_schedule"] = door_schedule

            # Pass window_schedule through to config for window creator
            window_schedule = args_dict.get("window_schedule")
            if isinstance(window_schedule, list) and window_schedule:
                config["window_schedule"] = window_schedule
        else:
            config["wall_height_ft"] = DEFAULT_WALL_HEIGHT_FT

        config_json = json.dumps(config, indent=2)

        # Determine run gate
        run = bool(walls_json)

        # Build info
        info_lines.append(f"MCP Args: {'valid' if args_valid else args_error}")
        info_lines.append(f"  walls_json: {walls_source} ({len(walls_json)} chars)")
        info_lines.append(f"  doors_json: {doors_source} ({len(doors_json)} chars)")
        info_lines.append(f"  windows_json: {windows_source} ({len(windows_json)} chars)")
        info_lines.append(f"  run: {run}")

        info = "\n".join(info_lines)
        log_info(info)

        return walls_json, doors_json, windows_json, config_json, run, info

    except Exception as e:
        error_msg = f"Error in MCP Create Walls Args: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return walls_json, doors_json, windows_json, config_json, False, error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    walls_json, doors_json, windows_json, config_json, run, info = main()
