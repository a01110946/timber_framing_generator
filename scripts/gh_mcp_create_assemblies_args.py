# File: scripts/gh_mcp_create_assemblies_args.py
"""MCP Create Assemblies Args Extractor for Grasshopper.

Extracts arguments from the MCP ``create_assemblies`` tool call and gates
the assembly creator component. The agent calls this tool after
``create_walls`` has finished placing walls and framing.

Usage on GH Canvas:
    1. Wire Deconstruct Tool Call "Args" output to input 0
    2. Wire walls_result_json (output 1) to the assembly creator walls input
    3. Wire run (output 2) to the assembly creator run input
    4. Wire request passthrough (R from Deconstruct) to MCP Tool Response Request

Input Requirements:
    MCP Args (mcp_args) - str:
        JSON string from Deconstruct Tool Call "Args" output.
        May contain: walls_result_json (array of wall ElementId integers).
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Walls Result JSON (walls_result_json) - str:
        Passed through from MCP args to the assembly creator component.
        Contains the wall ElementId list needed to find the correct walls.

    Run (run) - bool:
        Always True when valid MCP args are received.
        False in manual mode (no MCP args). Use a Boolean Toggle to trigger
        manually.

    Info (info) - str:
        Debug information about input source and run gate.

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

COMPONENT_NAME = "MCP Create Assemblies Args"
COMPONENT_NICKNAME = "MCPAssemblyArgs"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

# =============================================================================
# Logging Utilities
# =============================================================================

def log_info(message: str) -> None:
    print("[INFO] %s" % message)


def log_warning(message: str) -> None:
    print("[WARNING] %s" % message)
    ghenv.Component.AddRuntimeMessage(
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)


def log_error(message: str) -> None:
    print("[ERROR] %s" % message)
    ghenv.Component.AddRuntimeMessage(
        Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)


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
        ("Walls Result JSON", "walls_result_json",
         "Wall ElementId list from prior create_walls response. Feed to assembly creator."),
        ("Run", "run",
         "True when valid MCP args received. Wire to assembly creator run input."),
        ("Info", "info",
         "Debug information about input source and run gate"),
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
        return False, {}, "Invalid JSON in MCP args: %s" % e

    if not isinstance(parsed, dict):
        return False, {}, "MCP args must be a JSON object"

    return True, parsed, None


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point.

    Returns:
        tuple: (walls_result_json, run, info)
    """
    setup_component()

    walls_result_json = ""
    run = False
    info_lines = []

    try:
        mcp_args_raw = _read_input(0)
        args_valid, args_dict, args_error = _parse_mcp_args(mcp_args_raw)

        if args_valid:
            # Extract walls_result_json — the list of ElementIds from create_walls
            raw_wres = args_dict.get("walls_result_json")
            if _has_content(raw_wres):
                walls_result_json = str(raw_wres).strip()
                info_lines.append("walls_result_json: %d chars from MCP args" % len(walls_result_json))
            else:
                info_lines.append("walls_result_json: not provided (assembly creator will use pre-wired data)")

            run = True
            info_lines.append("run=True (MCP trigger)")
        else:
            info_lines.append("MCP Args: %s" % args_error)
            info_lines.append("run=False (manual mode — use Boolean Toggle)")

        info = "\n".join(info_lines)
        log_info(info)

        return (walls_result_json, run, info)

    except Exception as e:
        error_msg = "Error in MCP Create Assemblies Args: %s" % str(e)
        log_error(error_msg)
        print(traceback.format_exc())
        return ("", False, error_msg)


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    (walls_result_json, run, info) = main()
