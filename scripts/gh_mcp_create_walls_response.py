# File: scripts/gh_mcp_create_walls_response.py
"""MCP Create Walls Response Formatter for Grasshopper.

Combines result JSONs from the three-step Kreo-to-Revit pipeline (walls,
doors, windows) into a single MCP response body for the Swiftlet MCP Tool
Response component.

Key Features:
1. Combines three result JSONs into one MCP response
   - walls_result_json from gh_kreo_create_walls
   - doors_result_json from gh_kreo_create_doors (optional)
   - windows_result_json from gh_kreo_create_windows (optional)

2. Error handling for missing/invalid input
   - Returns error response when walls_result_json is missing
   - Handles non-JSON input gracefully
   - Optional door/window results default to zero counts

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Response validation and formatting

Usage:
    1. Connect gh_kreo_create_walls "walls_result_json" to input 0
    2. Connect gh_kreo_create_doors "doors_result_json" to input 1 (optional)
    3. Connect gh_kreo_create_windows "windows_result_json" to input 2 (optional)
    4. Wire output 1 (response_body) to MCP Tool Response "body" input
    5. Wire Deconstruct Tool Call "R" directly to MCP Tool Response "R"
    6. Monitor output 2 (info) for debug

Input Requirements:
    Walls Result JSON (walls_result_json) - str:
        JSON output from gh_kreo_create_walls component.
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Doors Result JSON (doors_result_json) - str:
        JSON output from gh_kreo_create_doors component.
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Windows Result JSON (windows_result_json) - str:
        JSON output from gh_kreo_create_windows component.
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Response Body (response_body) - str:
        Combined JSON string for MCP Tool Response "body" input.

    Info (info) - str:
        Summary of the response.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes
    - Merges wall_ids, door_ids, window_ids into single response
    - Reports combined counts for all element types

Error Handling:
    - Missing walls_result_json: error response
    - Missing doors/windows: zero counts in response
    - Invalid JSON: error with parse details

Author: ConstructAI Demo
Version: 2.0.0
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

COMPONENT_NAME = "MCP Create Walls Response"
COMPONENT_NICKNAME = "MCPWallResp"
COMPONENT_MESSAGE = "v2.0"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

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
        ("Walls Result JSON", "walls_result_json",
         "JSON from gh_kreo_create_walls (all-in-one mode)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls Result Passthrough", "walls_result_passthrough",
         "JSON from MCPWallArgs passthrough (staged mode)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Doors Result JSON", "doors_result_json",
         "JSON output from gh_kreo_create_doors (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Windows Result JSON", "windows_result_json",
         "JSON output from gh_kreo_create_windows (optional)",
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
        ("Response Body", "response_body",
         "Combined JSON string for MCP Tool Response body input"),
        ("Info", "info",
         "Summary of the response"),
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


def _safe_parse_json(raw, label: str) -> dict:
    """Parse a JSON input, returning empty dict on failure.

    Args:
        raw: Raw input value (may be None or non-string).
        label: Human-readable label for error messages.

    Returns:
        Parsed dict, or empty dict if input is missing/invalid.
    """
    if raw is None:
        return {}
    s = str(raw).strip()
    if not s:
        return {}
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError as e:
        log_warning(f"Invalid JSON for {label}: {e}")
        return {}


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point.

    Returns:
        tuple: (response_body, info)
    """
    setup_component()

    try:
        input_count = ghenv.Component.Params.Input.Count
        if input_count >= 4:
            # New layout: walls(0), passthrough(1), doors(2), windows(3)
            walls_raw = _read_input(0)
            passthrough_raw = _read_input(1)
            doors_raw = _read_input(2)
            windows_raw = _read_input(3)
        else:
            # Legacy 3-input layout: walls(0), doors(1), windows(2)
            walls_raw = _read_input(0)
            passthrough_raw = None
            doors_raw = _read_input(1)
            windows_raw = _read_input(2)
        log_info(f"Input layout: {input_count} inputs ({'4-input' if input_count >= 4 else '3-input legacy'})")

        # Merge: all-in-one (input 0) takes priority; staged fallback (input 1)
        def _has_data(val) -> bool:
            if val is None:
                return False
            s = str(val).strip()
            return s not in ("", "null", "None", "[]", "{}")

        effective_walls_raw = walls_raw if _has_data(walls_raw) else passthrough_raw
        source = "all-in-one" if _has_data(walls_raw) else ("passthrough" if _has_data(passthrough_raw) else "none")
        log_info(f"Walls source: {source}")

        # Parse walls result (required)
        walls_result = _safe_parse_json(effective_walls_raw, "walls_result_json")
        if not walls_result:
            error_response = {
                "status": "error",
                "message": "No walls result data. Run wall creator first.",
            }
            response_body = json.dumps(error_response, indent=2)
            info = "MCP Response: No walls result data (pipeline idle)"
            log_info(info)
            return response_body, info

        # Parse optional door/window results
        doors_result = _safe_parse_json(doors_raw, "doors_result_json")
        windows_result = _safe_parse_json(windows_raw, "windows_result_json")

        # Extract counts and IDs from each result
        walls_created = walls_result.get("walls_created", 0)
        wall_ids = walls_result.get("wall_ids", [])
        classification = walls_result.get("classification", {})
        wall_status = walls_result.get("status", "unknown")

        doors_placed = doors_result.get("doors_placed", 0)
        door_ids = doors_result.get("door_ids", [])
        doors_unmatched = doors_result.get("unmatched", 0)
        door_fallbacks = doors_result.get("fallbacks", [])

        windows_placed = windows_result.get("windows_placed", 0)
        window_ids = windows_result.get("window_ids", [])
        windows_unmatched = windows_result.get("unmatched", 0)
        window_fallbacks = windows_result.get("fallbacks", [])

        # Determine overall status
        if wall_status != "success":
            overall_status = wall_status
        else:
            overall_status = "success"

        # Merge fallback lists
        all_fallbacks = door_fallbacks + window_fallbacks

        # Build combined response
        combined = {
            "status": overall_status,
            "walls_created": walls_created,
            "doors_placed": doors_placed,
            "windows_placed": windows_placed,
            "unmatched_openings": doors_unmatched + windows_unmatched,
            "wall_classification": classification,
            "wall_ids": wall_ids,
            "door_ids": door_ids,
            "window_ids": window_ids,
            "scale_m_per_px": walls_result.get("scale_m_per_px", 0.0),
            "wall_height_ft": walls_result.get("wall_height_ft", 8.0),
            "level": walls_result.get("level_name", ""),
            "message": (
                f"Created {walls_created} walls, "
                f"placed {doors_placed} doors and {windows_placed} windows"
            ),
        }
        if all_fallbacks:
            combined["fallbacks"] = all_fallbacks
            combined["message"] += (
                f" ({len(all_fallbacks)} family type fallbacks - "
                "check Revit model for substituted types)"
            )
        response_body = json.dumps(combined, indent=2)

        # Build info summary
        info = (
            f"MCP Response: status={overall_status}, "
            f"{walls_created} walls, {doors_placed} doors, {windows_placed} windows"
        )
        if doors_unmatched + windows_unmatched > 0:
            info += f"\n  Unmatched: {doors_unmatched + windows_unmatched} openings"
        if all_fallbacks:
            info += f"\n  Fallbacks: {len(all_fallbacks)} family type substitutions"

        log_info(info)
        return response_body, info

    except Exception as e:
        error_msg = f"Error formatting MCP response: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        error_response = {"status": "error", "message": error_msg}
        return json.dumps(error_response, indent=2), error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    response_body, info = main()
