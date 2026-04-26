# File: scripts/gh_format_response.py
"""Format HTTP Response for Grasshopper — Stage-Aware.

Collects output stats from the framing pipeline and formats them into a JSON
response string for the Swiftlet Server Response component. Only includes
sections relevant to the current pipeline stage, so responses match what
was actually requested.

Key Features:
1. Stage-Aware Response Building
   - Reads config_json to determine the active pipeline stage
   - Only includes stats for stages that actually ran
   - "analyze" -> walls_processed only
   - "frame"   -> + framing element counts
   - "bake"    -> + baking confirmation
   - "sheathing" -> + sheathing panel counts
   - "assemble"  -> + assembly IDs and counts
   - "all"     -> everything (backward compatible)

2. Pipeline Stats Extraction
   - Parses framing_json for element counts by type
   - Parses assembly_json for assembly creation results
   - Parses sheathing_json for layer and panel counts

3. Error Handling
   - Accepts an optional error input for pipeline failures
   - Always produces valid JSON regardless of input state
   - Gracefully handles missing or malformed inputs

4. Structured Response
   - Outputs JSON matching the HTTP response contract
   - Compatible with Swiftlet's Create Text Body Custom component

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
    2. Connect Assembly Creator "assembly_json" output to input 1
    3. Optionally connect Multi-Layer Sheathing "multi_layer_json" to input 2
    4. Optionally connect error string to input 3 (for pipeline failures)
    5. Connect gh_http_trigger "config_json" output to input 4 (for stage)
    6. Wire "Response JSON" output to Swiftlet Create Text Body Custom
    7. Monitor "Info" output for debug messages

Input Requirements:
    Framing JSON (framing_json) - str:
        JSON output from Framing Generator component.
        Required: No (response will show zero elements)
        Access: Item
        Type Hint: str (set via GH UI)

    Assembly JSON (assembly_json) - str:
        JSON output from Assembly Creator component.
        Required: No (response will show zero assemblies)
        Access: Item
        Type Hint: str (set via GH UI)

    Sheathing JSON (sheathing_json) - str:
        JSON output from Multi-Layer Sheathing component.
        Required: No (sheathing section omitted if not connected)
        Access: Item
        Type Hint: str (set via GH UI)

    Error (error) - str:
        Optional error message from pipeline failure.
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Config JSON (config_json) - str:
        Config JSON from gh_http_trigger (contains "stage" field).
        Required: No (defaults to "all" if missing)
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Response JSON (response_json) - str:
        Formatted JSON response body for Swiftlet Server Response.
        Always valid JSON with status, counts, and message.
        Only includes sections relevant to the active stage.

    Info (info) - str:
        Human-readable summary of the response contents.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes to prevent wire disconnection
    - No RhinoCommonFactory needed (no geometry output)
    - Error input takes priority: if set, response status is "error"
    - Stage levels match gh_http_trigger.py STAGE_LEVELS

Error Handling:
    - Missing inputs: zero counts reported, status still "success"
    - Invalid JSON in inputs: warning logged, section shows zero counts
    - Error input provided: status="error" with error message
    - Missing config_json: defaults to stage="all"
    - Unexpected exception: status="error" with traceback

Author: Timber Framing Generator
Version: 2.0.0
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

COMPONENT_NAME = "Format HTTP Response"
COMPONENT_NICKNAME = "HTTPResp"
COMPONENT_MESSAGE = "v2.0 staged"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Config"

# Must match gh_http_trigger.py STAGE_LEVELS
STAGE_LEVELS = {
    "analyze": 1,
    "frame": 2,
    "bake": 3,
    "sheathing": 4,
    "assemble": 5,
    "all": 99,
}

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
        ("Assembly JSON", "assembly_json",
         "JSON output from Assembly Creator",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 2
        ("Sheathing JSON", "sheathing_json",
         "JSON output from Multi-Layer Sheathing (optional)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 3
        ("Error", "error",
         "Optional error message from pipeline failure",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 4 (NEW v2.0)
        ("Config JSON", "config_json",
         "Config JSON from gh_http_trigger (contains stage field)",
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
        ("Response JSON", "response_json",
         "Formatted JSON response body for Swiftlet Server Response"),
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


def _safe_parse_json(json_str: str, input_name: str) -> dict:
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

    Args:
        framing_data: Parsed framing_json dict.

    Returns:
        dict: Framing statistics with total and by-type counts.
    """
    stats = {"total_elements": 0, "by_type": {}}

    # framing_json has a "walls" key with per-wall elements
    walls = framing_data.get("walls", [])
    if isinstance(walls, list):
        for wall in walls:
            elements = wall.get("elements", [])
            if isinstance(elements, list):
                stats["total_elements"] += len(elements)
                for elem in elements:
                    elem_type = elem.get("element_type", "unknown")
                    stats["by_type"][elem_type] = stats["by_type"].get(elem_type, 0) + 1

    # Count walls processed
    stats["walls_processed"] = len(walls) if isinstance(walls, list) else 0

    return stats


def _extract_assembly_stats(assembly_data: dict) -> dict:
    """Extract assembly statistics from assembly_json.

    Args:
        assembly_data: Parsed assembly_json dict.

    Returns:
        dict: Assembly statistics with count and IDs.
    """
    stats = {"count": 0, "ids": []}

    # assembly_json may have "assemblies" list or "assembly_count"
    assemblies = assembly_data.get("assemblies", [])
    if isinstance(assemblies, list):
        stats["count"] = len(assemblies)
        for asm in assemblies:
            asm_id = asm.get("assembly_id") or asm.get("id")
            if asm_id is not None:
                stats["ids"].append(str(asm_id))
    elif "assembly_count" in assembly_data:
        stats["count"] = int(assembly_data["assembly_count"])

    return stats


def _extract_sheathing_stats(sheathing_data: dict) -> dict:
    """Extract sheathing statistics from multi_layer_json.

    Args:
        sheathing_data: Parsed multi_layer_json dict.

    Returns:
        dict: Sheathing statistics with layer and panel counts.
    """
    stats = {"layers": 0, "total_panels": 0}

    layers = sheathing_data.get("layers", [])
    if isinstance(layers, list):
        stats["layers"] = len(layers)
        for layer in layers:
            panels = layer.get("panels", [])
            if isinstance(panels, list):
                stats["total_panels"] += len(panels)

    return stats


def _resolve_stage(config_json_raw) -> tuple:
    """Resolve the pipeline stage from config_json input.

    Args:
        config_json_raw: Raw config JSON string from gh_http_trigger, or None.

    Returns:
        tuple: (stage_name, stage_level)
    """
    if config_json_raw is None:
        return "all", STAGE_LEVELS["all"]

    config = _safe_parse_json(config_json_raw, "config_json")
    stage = str(config.get("stage", "all")).strip().lower()

    if stage not in STAGE_LEVELS:
        return "all", STAGE_LEVELS["all"]

    return stage, STAGE_LEVELS[stage]


def _build_response(framing_stats: dict, assembly_stats: dict,
                    sheathing_stats: dict, stage: str, stage_level: int,
                    error_msg: str = None) -> dict:
    """Build the final HTTP response dict, filtered by stage.

    Only includes sections for stages that actually ran (cumulative).

    Args:
        framing_stats: Extracted framing statistics.
        assembly_stats: Extracted assembly statistics.
        sheathing_stats: Extracted sheathing statistics.
        stage: Active stage name (e.g. "analyze", "frame", "all").
        stage_level: Numeric stage level for cumulative comparison.
        error_msg: Optional error message.

    Returns:
        dict: Complete response body.
    """
    walls_processed = framing_stats.get("walls_processed", 0)

    if error_msg:
        return {
            "status": "error",
            "stage": stage,
            "message": str(error_msg),
            "walls_processed": walls_processed,
        }

    response = {
        "status": "success",
        "stage": stage,
        "walls_processed": walls_processed,
    }

    parts = [f"{walls_processed} walls analyzed"]

    # Include framing stats if stage >= frame
    if stage_level >= STAGE_LEVELS["frame"]:
        response["framing"] = {
            "total_elements": framing_stats.get("total_elements", 0),
            "by_type": framing_stats.get("by_type", {}),
        }
        parts.append(f"{framing_stats.get('total_elements', 0)} framing elements")

    # Include sheathing stats if stage >= sheathing
    if stage_level >= STAGE_LEVELS["sheathing"]:
        if sheathing_stats.get("layers", 0) > 0:
            response["sheathing"] = {
                "layers": sheathing_stats["layers"],
                "total_panels": sheathing_stats["total_panels"],
            }
            parts.append(f"{sheathing_stats['total_panels']} sheathing panels")

    # Include assembly stats if stage >= assemble
    if stage_level >= STAGE_LEVELS["assemble"]:
        response["assemblies"] = {
            "count": assembly_stats.get("count", 0),
            "ids": assembly_stats.get("ids", []),
        }
        parts.append(f"{assembly_stats.get('count', 0)} assemblies")

    # Build summary message
    stage_label = "complete" if stage == "all" else f"stage '{stage}' complete"
    response["message"] = f"Pipeline {stage_label}: " + ", ".join(parts)

    return response


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the Format HTTP Response component.

    Workflow:
    1. Setup component metadata
    2. Read all inputs by index
    3. Parse JSON inputs
    4. Extract statistics from each pipeline stage
    5. Build and serialize response

    Returns:
        tuple: (response_json, info)
    """
    setup_component()

    try:
        # Read inputs by index
        framing_json_raw = _read_input(0)
        assembly_json_raw = _read_input(1)
        sheathing_json_raw = _read_input(2)
        error_raw = _read_input(3)
        config_json_raw = _read_input(4)

        # Resolve stage from config
        stage, stage_level = _resolve_stage(config_json_raw)

        # Parse JSON inputs
        framing_data = _safe_parse_json(framing_json_raw, "framing_json")
        assembly_data = _safe_parse_json(assembly_json_raw, "assembly_json")
        sheathing_data = _safe_parse_json(sheathing_json_raw, "sheathing_json")

        # Extract error if provided
        error_msg = None
        if error_raw is not None:
            error_str = str(error_raw).strip()
            if error_str:
                error_msg = error_str

        # Extract statistics
        framing_stats = _extract_framing_stats(framing_data)
        assembly_stats = _extract_assembly_stats(assembly_data)
        sheathing_stats = _extract_sheathing_stats(sheathing_data)

        # Build stage-aware response
        response = _build_response(
            framing_stats, assembly_stats, sheathing_stats,
            stage, stage_level, error_msg
        )
        response_json = json.dumps(response, indent=2)

        # Build info summary
        info_lines = [
            f"HTTP Response: status={response['status']}, stage={stage}",
            f"  walls: {framing_stats.get('walls_processed', 0)}",
        ]
        if stage_level >= STAGE_LEVELS["frame"]:
            info_lines.append(
                f"  elements: {framing_stats.get('total_elements', 0)}")
        if stage_level >= STAGE_LEVELS["sheathing"]:
            if sheathing_stats.get("layers", 0) > 0:
                info_lines.append(
                    f"  sheathing: {sheathing_stats['layers']} layers, "
                    f"{sheathing_stats['total_panels']} panels")
        if stage_level >= STAGE_LEVELS["assemble"]:
            info_lines.append(
                f"  assemblies: {assembly_stats.get('count', 0)}")
        if error_msg:
            info_lines.append(f"  ERROR: {error_msg}")

        info = "\n".join(info_lines)
        log_info(info)

        return response_json, info

    except Exception as e:
        error_msg = f"Unexpected error formatting response: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        # Always return valid JSON even on failure
        fallback = {
            "status": "error",
            "message": error_msg,
            "walls_processed": 0,
        }
        return json.dumps(fallback, indent=2), error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    response_json, info = main()
