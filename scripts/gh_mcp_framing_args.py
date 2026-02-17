# File: scripts/gh_mcp_framing_args.py
"""MCP Framing Args Extractor for Grasshopper.

Extracts arguments from the MCP ``generate_framing`` tool call and converts
them into the inputs expected by the real framing pipeline (Panel Decomposer,
Cell Decomposer, Framing Generator). Acts as the upstream adapter between
the Swiftlet MCP Deconstruct Tool Call and the existing pipeline components.

Key Features:
1. MCP Argument Parsing
   - Reads the Args JSON string from Deconstruct Tool Call
   - Extracts ``stud_spacing`` (inches) and converts to feet
   - Validates that walls_json is available before enabling pipeline

2. Pipeline Gating
   - Outputs ``run_pipeline = True`` only when both args and walls_json are valid
   - Prevents pipeline from running when analyze_walls hasn't been called yet
   - Prevents pipeline from running when generate_framing args are missing

3. Config Generation
   - Builds a config_json compatible with Framing Generator's config input
   - Includes framing_system, stud_spacing, and stage fields

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Argument parsing and config serialization

Performance Considerations:
    - Lightweight JSON parsing only; negligible execution time
    - No geometry or heavy computation involved

Usage:
    1. Connect Deconstruct Tool Call "Args" output to input 0 (MCP Args)
    2. Connect Wall Analyzer "walls_json" output to input 1 (Walls JSON)
    3. Wire output 1 (walls_json_out) to Panel Decomposer, Cell Decomposer,
       and Framing Generator walls_json inputs
    4. Wire output 2 (stud_space_ft) to Panel Decomposer stud_space input
    5. Wire output 3 (run_pipeline) to Panel Decomposer, Cell Decomposer,
       and Framing Generator run inputs
    6. Wire output 4 (config_json) to Framing Generator config_json input
    7. Monitor output 5 (info) for debug messages

Input Requirements:
    MCP Args (mcp_args) - str:
        JSON string from Deconstruct Tool Call "Args" output.
        Expected fields: {"stud_spacing": <number in inches>}
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer "walls_json" output.
        Must be a valid JSON array of wall objects.
        Required: Yes (pipeline won't run without it)
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Walls JSON Out (walls_json_out) - str:
        Pass-through of the walls_json input for downstream components.

    Stud Spacing (stud_space_ft) - float:
        Stud spacing in feet, converted from inches in MCP args.
        Defaults to 1.333 ft (16" OC) if not specified.

    Run Pipeline (run_pipeline) - bool:
        True when both MCP args and walls_json are valid.
        Wire to Panel Decomposer, Cell Decomposer, Framing Generator run inputs.

    Config JSON (config_json) - str:
        Pipeline configuration JSON for Framing Generator config input.
        Contains framing_system, stud_spacing, stage fields.

    Info (info) - str:
        Human-readable summary of parsed arguments and pipeline readiness.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes to prevent wire disconnection
    - No RhinoCommonFactory needed (no geometry output)
    - stud_spacing conversion: inches / 12.0 = feet
    - Default stud_spacing: 16" OC = 1.333 ft

Error Handling:
    - Missing MCP args: run_pipeline=False, info shows error
    - Missing walls_json: run_pipeline=False, info shows "call analyze_walls first"
    - Invalid JSON in args: run_pipeline=False, warning logged
    - Invalid stud_spacing value: defaults to 16" OC with warning

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

COMPONENT_NAME = "MCP Framing Args"
COMPONENT_NICKNAME = "MCPArgs"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Config"

DEFAULT_STUD_SPACING_IN = 16.0
DEFAULT_MATERIAL = "timber"

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
        ("MCP Args", "mcp_args",
         "JSON string from Deconstruct Tool Call Args output",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 1
        ("Walls JSON", "walls_json",
         "JSON string from Wall Analyzer walls_json output",
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
        ("Walls JSON Out", "walls_json_out",
         "Pass-through walls_json for downstream pipeline components"),
        ("Stud Spacing", "stud_space_ft",
         "Stud spacing in feet (converted from inches)"),
        ("Run Pipeline", "run_pipeline",
         "True when args and walls_json are valid"),
        ("Config JSON", "config_json",
         "Pipeline configuration JSON for Framing Generator"),
        ("Info", "info",
         "Debug information about parsed arguments"),
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


def _parse_mcp_args(args_raw) -> tuple:
    """Parse the MCP tool call arguments JSON.

    Args:
        args_raw: Raw string from Deconstruct Tool Call Args output.

    Returns:
        tuple: (is_valid, args_dict, error_message)
    """
    if args_raw is None:
        return False, {}, "No MCP args received (tool not called yet)"

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
        return False, {}, f"MCP args must be a JSON object, got {type(parsed).__name__}"

    return True, parsed, None


def _extract_stud_spacing(args: dict) -> float:
    """Extract and validate stud_spacing from MCP args.

    Args:
        args: Parsed MCP args dict.

    Returns:
        float: Stud spacing in inches.
    """
    stud_spacing = args.get("stud_spacing", DEFAULT_STUD_SPACING_IN)
    try:
        stud_spacing = float(stud_spacing)
        if stud_spacing <= 0:
            raise ValueError("Must be positive")
    except (TypeError, ValueError):
        log_warning(
            f"Invalid stud_spacing: {stud_spacing}, "
            f"defaulting to {DEFAULT_STUD_SPACING_IN} inches"
        )
        stud_spacing = DEFAULT_STUD_SPACING_IN
    return stud_spacing


def _validate_walls_json(walls_json_raw) -> tuple:
    """Validate the walls_json input.

    Args:
        walls_json_raw: Raw string from Wall Analyzer.

    Returns:
        tuple: (is_valid, error_message)
    """
    if walls_json_raw is None:
        return False, "No walls_json available -- call analyze_walls first"

    if not isinstance(walls_json_raw, str):
        walls_json_raw = str(walls_json_raw)

    walls_json_raw = walls_json_raw.strip()
    if not walls_json_raw:
        return False, "Empty walls_json -- call analyze_walls first"

    try:
        parsed = json.loads(walls_json_raw)
        if not isinstance(parsed, list):
            return False, "walls_json must be a JSON array of wall objects"
        if len(parsed) == 0:
            return False, "walls_json contains no walls"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the MCP Framing Args Extractor.

    Workflow:
    1. Setup component metadata
    2. Read MCP args and walls_json inputs
    3. Parse and validate MCP args
    4. Validate walls_json availability
    5. Extract stud_spacing and build config
    6. Output pipeline inputs

    Returns:
        tuple: (walls_json_out, stud_space_ft, run_pipeline, config_json, info)
    """
    setup_component()

    # Defaults (pipeline off)
    walls_json_out = ""
    stud_space_ft = 1.333  # 16" OC default
    run_pipeline = False
    config_json = ""
    info_lines = []

    try:
        # Read inputs by index
        mcp_args_raw = _read_input(0)
        walls_json_raw = _read_input(1)

        # Parse MCP args
        args_valid, args_dict, args_error = _parse_mcp_args(mcp_args_raw)
        if not args_valid:
            info_lines.append(f"MCP Args: {args_error}")
            info = "\n".join(info_lines)
            log_info(info)
            return walls_json_out, stud_space_ft, run_pipeline, config_json, info

        # Validate walls_json
        walls_valid, walls_error = _validate_walls_json(walls_json_raw)
        if not walls_valid:
            info_lines.append(f"Walls JSON: {walls_error}")
            info = "\n".join(info_lines)
            log_warning(walls_error)
            return walls_json_out, stud_space_ft, run_pipeline, config_json, info

        # Extract stud_spacing (inches -> feet)
        stud_spacing_in = _extract_stud_spacing(args_dict)
        stud_space_ft = stud_spacing_in / 12.0

        # Pass through walls_json
        walls_json_out = walls_json_raw.strip()

        # Build config_json for Framing Generator
        config = {
            "framing_system": DEFAULT_MATERIAL,
            "stud_spacing": stud_space_ft,
            "stage": "frame",
        }
        config_json = json.dumps(config, indent=2)

        # Pipeline is ready
        run_pipeline = True

        # Build info summary
        walls_data = json.loads(walls_json_out)
        wall_count = len(walls_data) if isinstance(walls_data, list) else 1

        info_lines.append("MCP Framing Args: Pipeline READY")
        info_lines.append(f"  stud_spacing: {stud_spacing_in:.1f} in -> {stud_space_ft:.4f} ft")
        info_lines.append(f"  walls: {wall_count}")
        info_lines.append(f"  run_pipeline: True")

        info = "\n".join(info_lines)
        log_info(info)

        return walls_json_out, stud_space_ft, run_pipeline, config_json, info

    except Exception as e:
        error_msg = f"Unexpected error in MCP Args Extractor: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        info_lines.append(f"ERROR: {error_msg}")
        return walls_json_out, stud_space_ft, False, config_json, "\n".join(info_lines)


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    walls_json_out, stud_space_ft, run_pipeline, config_json, info = main()
