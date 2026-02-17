# File: scripts/gh_mcp_framing_response.py
"""MCP Framing Response Formatter for Grasshopper.

Reads the output of the real framing pipeline (Framing Generator) and formats
it into a JSON response body suitable for the Swiftlet MCP Tool Response
component. Acts as the downstream adapter between the pipeline and the MCP
response flow.

Key Features:
1. Framing Statistics Extraction
   - Parses framing_json to count elements by type
   - Counts walls processed and total framing elements
   - Reuses the same extraction logic as gh_format_response.py

2. Wall-Level Summary
   - Reports per-wall element counts
   - Includes wall IDs for traceability

3. MCP Response Formatting
   - Outputs a JSON string ready for MCP Tool Response "body" input
   - Includes status, element counts, and a human-readable message
   - Error responses when framing_json is missing or invalid

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Response serialization and input parsing

Performance Considerations:
    - Lightweight JSON parsing and aggregation; negligible execution time
    - No geometry or heavy computation involved

Usage:
    1. Connect Framing Generator "framing_json" output to input 0
    2. Connect Script A "walls_json_out" (or Wall Analyzer) to input 1
    3. Wire output 1 (response_body) to MCP Tool Response "body" input
    4. Monitor output 2 (info) for debug messages
    5. Wire Deconstruct Tool Call "R" directly to MCP Tool Response "R"
       (R does NOT pass through this component)

Input Requirements:
    Framing JSON (framing_json) - str:
        JSON output from Framing Generator component.
        Expected structure: {"walls": [...], "elements": [...], ...}
        or FramingResults format with top-level "elements" list.
        Required: Yes (response will show error if missing)
        Access: Item
        Type Hint: str (set via GH UI)

    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer or Script A pass-through.
        Used for wall count in the response summary.
        Required: No (wall count will be inferred from framing_json)
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Response Body (response_body) - str:
        JSON string for MCP Tool Response "body" input.
        Contains status, element counts by type, wall stats, and message.

    Info (info) - str:
        Human-readable summary of the response contents.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes to prevent wire disconnection
    - No RhinoCommonFactory needed (no geometry output)
    - Handles both FramingResults format (top-level "elements") and
      legacy format (nested "walls[].elements")
    - Always returns valid JSON even on error

Error Handling:
    - Missing framing_json: status="error", message explains the issue
    - Invalid JSON in framing_json: status="error" with parse error
    - Empty elements: status="success" with zero counts (valid result)
    - Unexpected exception: status="error" with traceback

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
import Grasshopper

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MCP Framing Response"
COMPONENT_NICKNAME = "MCPResp"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Config"

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
    """Initialize and configure the Grasshopper component.

    Guards all property setters to prevent wire disconnection when the
    value hasn't actually changed.
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        # Index 0
        ("Framing JSON", "framing_json",
         "JSON output from Framing Generator",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 1
        ("Walls JSON", "walls_json",
         "JSON string from Wall Analyzer or MCP Args pass-through",
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

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Response Body", "response_body",
         "JSON string for MCP Tool Response body input"),
        ("Info", "info",
         "Summary of the response contents"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1  # Skip Output[0]
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
    """Read a GH input value by parameter index via VolatileData.

    Args:
        index: Zero-based input parameter index.
        default: Value to return when the input is empty or missing.

    Returns:
        The input value, or default if not connected / empty.
    """
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


def _safe_parse_json(json_str, input_name: str) -> dict:
    """Safely parse a JSON string input.

    Args:
        json_str: Raw JSON string, or None.
        input_name: Human-readable name for log messages.

    Returns:
        Parsed dict, or empty dict on failure.
    """
    if json_str is None:
        return {}
    if not isinstance(json_str, str):
        json_str = str(json_str)
    json_str = json_str.strip()
    if not json_str:
        return {}

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
        return {}
    except json.JSONDecodeError as e:
        log_warning(f"Failed to parse {input_name}: {e}")
        return {}


def _extract_framing_stats(framing_data: dict) -> dict:
    """Extract element count statistics from framing_json.

    Handles both FramingResults format (top-level "elements" list with
    nested wall_id in metadata) and the legacy format ("walls" list with
    per-wall "elements").

    Args:
        framing_data: Parsed framing_json dict.

    Returns:
        dict: Framing statistics with total, by-type counts, and per-wall info.
    """
    stats = {
        "total_elements": 0,
        "by_type": {},
        "walls_processed": 0,
        "per_wall": {},
    }

    # FramingResults format: top-level "elements" list
    elements = framing_data.get("elements", [])
    if isinstance(elements, list) and elements:
        stats["total_elements"] = len(elements)
        wall_ids_seen = set()
        for elem in elements:
            elem_type = elem.get("element_type", "unknown")
            stats["by_type"][elem_type] = stats["by_type"].get(elem_type, 0) + 1

            # Track per-wall counts via metadata.wall_id
            meta = elem.get("metadata", {})
            wall_id = meta.get("wall_id", "unknown")
            wall_ids_seen.add(wall_id)
            if wall_id not in stats["per_wall"]:
                stats["per_wall"][wall_id] = 0
            stats["per_wall"][wall_id] += 1

        stats["walls_processed"] = len(wall_ids_seen)
        return stats

    # Legacy format: "walls" list with per-wall "elements"
    walls = framing_data.get("walls", [])
    if isinstance(walls, list):
        for wall in walls:
            wall_elements = wall.get("elements", [])
            if isinstance(wall_elements, list):
                wall_id = wall.get("wall_id", f"wall_{stats['walls_processed']}")
                stats["total_elements"] += len(wall_elements)
                stats["per_wall"][wall_id] = len(wall_elements)
                for elem in wall_elements:
                    elem_type = elem.get("element_type", "unknown")
                    stats["by_type"][elem_type] = stats["by_type"].get(elem_type, 0) + 1
        stats["walls_processed"] = len(walls) if isinstance(walls, list) else 0

    return stats


def _get_wall_count_from_walls_json(walls_json_raw) -> int:
    """Get wall count from walls_json input.

    Args:
        walls_json_raw: Raw walls_json string.

    Returns:
        int: Number of walls, or 0 if unavailable.
    """
    if not walls_json_raw:
        return 0
    try:
        parsed = json.loads(walls_json_raw)
        if isinstance(parsed, list):
            return len(parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    return 0


def _build_response(framing_stats: dict, wall_count: int) -> dict:
    """Build the MCP response dict.

    Args:
        framing_stats: Extracted framing statistics.
        wall_count: Number of walls from walls_json (for cross-reference).

    Returns:
        dict: Complete response body for MCP Tool Response.
    """
    total = framing_stats["total_elements"]
    walls_processed = framing_stats["walls_processed"]
    by_type = framing_stats["by_type"]

    # Use walls_json count if framing didn't report walls
    if walls_processed == 0 and wall_count > 0:
        walls_processed = wall_count

    response = {
        "status": "success",
        "walls_processed": walls_processed,
        "framing": {
            "total_elements": total,
            "by_type": by_type,
        },
    }

    # Add per-wall summary if available
    per_wall = framing_stats.get("per_wall", {})
    if per_wall:
        response["wall_details"] = [
            {"wall_id": wid, "element_count": count}
            for wid, count in sorted(per_wall.items())
        ]

    # Build human-readable message
    type_parts = [f"{count} {etype}" for etype, count in sorted(by_type.items())]
    type_summary = ", ".join(type_parts) if type_parts else "no elements"
    response["message"] = (
        f"Generated {total} framing elements across {walls_processed} walls: "
        f"{type_summary}"
    )

    return response


def _build_error_response(error_msg: str) -> dict:
    """Build an error response dict.

    Args:
        error_msg: Error description.

    Returns:
        dict: Error response body.
    """
    return {
        "status": "error",
        "message": error_msg,
        "walls_processed": 0,
        "framing": {
            "total_elements": 0,
            "by_type": {},
        },
    }


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the MCP Framing Response Formatter.

    Workflow:
    1. Setup component metadata
    2. Read framing_json and walls_json inputs
    3. Parse framing_json and extract statistics
    4. Build response JSON
    5. Output response body and info

    Returns:
        tuple: (response_body, info)
    """
    setup_component()

    try:
        # Read inputs by index
        framing_json_raw = _read_input(0)
        walls_json_raw = _read_input(1)

        # Check if framing_json is available
        if framing_json_raw is None or str(framing_json_raw).strip() in ("", "{}"):
            response = _build_error_response(
                "No framing data available. Pipeline may not have run yet."
            )
            response_body = json.dumps(response, indent=2)
            info = "MCP Response: No framing data (pipeline idle)"
            log_info(info)
            return response_body, info

        # Parse framing_json
        framing_data = _safe_parse_json(framing_json_raw, "framing_json")
        if not framing_data:
            response = _build_error_response(
                "Failed to parse framing_json output"
            )
            response_body = json.dumps(response, indent=2)
            info = "MCP Response: ERROR - invalid framing_json"
            log_warning(info)
            return response_body, info

        # Extract statistics
        framing_stats = _extract_framing_stats(framing_data)

        # Get wall count from walls_json for cross-reference
        wall_count = _get_wall_count_from_walls_json(walls_json_raw)

        # Build response
        response = _build_response(framing_stats, wall_count)
        response_body = json.dumps(response, indent=2)

        # Build info summary
        total = framing_stats["total_elements"]
        walls = framing_stats["walls_processed"] or wall_count
        info_lines = [
            f"MCP Response: status=success",
            f"  walls: {walls}",
            f"  elements: {total}",
        ]
        for etype, count in sorted(framing_stats["by_type"].items()):
            info_lines.append(f"    {etype}: {count}")
        info = "\n".join(info_lines)
        log_info(info)

        return response_body, info

    except Exception as e:
        error_msg = f"Unexpected error formatting MCP response: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        response = _build_error_response(error_msg)
        return json.dumps(response, indent=2), error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    response_body, info = main()
