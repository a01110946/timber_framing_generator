# File: scripts/gh_http_trigger.py
"""HTTP Trigger for Grasshopper — Staged Pipeline Execution.

Converts raw HTTP request body from Swiftlet into per-stage boolean triggers
and validated config JSON for downstream pipeline components. Supports staged
execution to avoid Revit crashes from simultaneous heavy operations.

Key Features:
1. Staged Execution
   - Request body includes a "stage" field controlling which pipeline steps run
   - Stages are cumulative: "bake" = analyze + compute + bake
   - Default stage is "all" for backward compatibility
   - Each stage has its own boolean output for GH wiring

2. Request Validation
   - Parses incoming JSON body from Swiftlet Deconstruct Body Tx output
   - Validates structure and field types
   - Outputs all triggers=False until a valid request arrives

3. Config Extraction
   - Extracts pipeline configuration from request body
   - Applies sensible defaults for missing fields
   - Outputs a config_json string compatible with existing pipeline components

4. Safe Gating
   - Prevents pipeline auto-run on GH definition load
   - Only outputs triggers when Content is non-empty valid JSON

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Request body parsing

Performance Considerations:
    - Lightweight JSON parsing only; negligible execution time
    - No geometry or heavy computation involved

Usage:
    1. Connect Swiftlet Deconstruct Body "Tx" output to this component's
       "HTTP Content" input
    2. Wire per-stage outputs to corresponding component "run" inputs:
       - run_analyze   -> Wall Analyzer
       - run_frame     -> Panel Decomposer, Cell Decomposer, Framing Generator,
                          Geometry Converter
       - run_bake      -> RiR Baker
       - run_sheathing -> Multi-Layer Sheathing, Sheathing Baker
       - run_assemble  -> Assembly Creator (after sheathing, so panels are complete)
    3. Wire "Config JSON" output to Framing Generator / Panel Decomposer
       config_json inputs
    4. Optionally monitor "Info" output for debug messages

Input Requirements:
    HTTP Content (content) - str:
        Raw request body string from Swiftlet Deconstruct Body Tx output.
        Expected to be a JSON string (or empty when no request received).
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Run Analyze (run_analyze) - bool:
        True when stage >= "analyze". Wire to Wall Analyzer "run" input.

    Config JSON (config_json) - str:
        Validated pipeline configuration as JSON string.
        Contains material, stud_spacing, panel settings, assembly flags, stage.
        Empty string when no valid request.

    Info (info) - str:
        Human-readable debug information about the request and active stage.

    Run Frame (run_frame) - bool:
        True when stage >= "frame". Wire to Panel Decomposer, Cell Decomposer,
        Framing Generator, and Geometry Converter "run" inputs.

    Run Bake (run_bake) - bool:
        True when stage >= "bake". Wire to RiR Baker "run" input.

    Run Sheathing (run_sheathing) - bool:
        True when stage >= "sheathing". Wire to Multi-Layer Sheathing and
        Sheathing Baker "run" inputs.

    Run Assemble (run_assemble) - bool:
        True when stage >= "assemble". Wire to Assembly Creator "run" input.
        Comes after sheathing so panels include sheathing in assemblies.

Technical Details:
    - Reads input by parameter index (not NickName globals) for Rhino 8 reliability
    - Guards setup_component() property changes to prevent wire disconnection
    - No RhinoCommonFactory needed (no geometry output)
    - Defaults: material=timber, stud_spacing=16in, panel_max_length=24ft, stage=all
    - Output indices 1-3 (run_analyze, config_json, info) are unchanged from v1.0
      to preserve existing wiring; new outputs added at indices 4-7

Error Handling:
    - Empty/None content: all triggers=False, empty config
    - Invalid JSON: all triggers=False, warning logged
    - Missing fields in JSON: defaults applied, triggers based on stage
    - Unknown stage value: warning logged, defaults to "all"
    - Unexpected error: all triggers=False, error logged

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

COMPONENT_NAME = "HTTP Trigger"
COMPONENT_NICKNAME = "HTTPTrig"
COMPONENT_MESSAGE = "v2.0 staged"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Config"

# Default config values (applied when request body omits fields)
DEFAULT_MATERIAL = "timber"
DEFAULT_STUD_SPACING_IN = 16.0
DEFAULT_PANEL_MAX_LENGTH_FT = 24.0
DEFAULT_GENERATE_ASSEMBLIES = True
DEFAULT_GENERATE_SHEETS = True
DEFAULT_ASSEMBLY_NAMING_PREFIX = "W"
DEFAULT_STAGE = "all"

# Pipeline stages (cumulative). Higher level includes all lower levels.
# "analyze"   -> Wall Analyzer only (Revit read, fast)
# "frame"     -> + Panel/Cell Decomposer + Framing Generator + Geometry Converter (computation, fast)
# "bake"      -> + RiR Baker (Revit write, slow)
# "sheathing" -> + Multi-Layer Sheathing + Sheathing Baker (computation + Revit write)
# "assemble"  -> + Assembly Creator (Revit write, slow) — AFTER sheathing so panels are complete
# "all"       -> Everything (backward compatible default)
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
    # ASCII only -- Rhino 8 console uses cp1252 encoding
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
    value hasn't actually changed (see MEMORY.md: setup_component() pattern).

    Output layout preserves v1.0 indices 1-3 for backward compatibility:
      [0] out           (GH default)
      [1] run_analyze   (was: trigger)
      [2] config_json   (unchanged)
      [3] info          (unchanged)
      [4] run_frame     (NEW)
      [5] run_bake      (NEW)
      [6] run_sheathing (NEW)
      [7] run_assemble  (NEW)
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
        ("HTTP Content", "content",
         "Raw request body from Swiftlet Deconstruct Body Tx output",
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
        # Index 1 (was: Trigger)
        ("Run Analyze", "run_analyze",
         "True when stage >= analyze. Wire to Wall Analyzer run input."),
        # Index 2 (unchanged)
        ("Config JSON", "config_json",
         "Validated pipeline config for downstream components"),
        # Index 3 (unchanged)
        ("Info", "info",
         "Debug information about the request and active stage"),
        # Index 4 (NEW)
        ("Run Frame", "run_frame",
         "True when stage >= frame. Wire to Decomposers + Framing Generator + Geometry Converter."),
        # Index 5 (NEW)
        ("Run Bake", "run_bake",
         "True when stage >= bake. Wire to RiR Baker."),
        # Index 6 (NEW)
        ("Run Sheathing", "run_sheathing",
         "True when stage >= sheathing. Wire to Sheathing components."),
        # Index 7 (NEW)
        ("Run Assemble", "run_assemble",
         "True when stage >= assemble. Wire to Assembly Creator (after sheathing)."),
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


def _unwrap_body_content(raw_obj) -> str:
    """Extract the raw text content from a Swiftlet RequestBody object.

    Swiftlet's Deconstruct Request "B" output is a RequestBody object,
    not a plain string. This function tries multiple ways to extract the
    actual JSON text from inside it.

    Args:
        raw_obj: The object received from the GH input (may be a string,
                 a Swiftlet RequestBody, or a GH_ObjectWrapper).

    Returns:
        str: The extracted text content, or empty string on failure.
    """
    if raw_obj is None:
        return ""

    # If it's already a plain string, use it directly
    if isinstance(raw_obj, str):
        return raw_obj.strip()

    # Try common .NET / Swiftlet properties to get the text content
    # The actual property name depends on Swiftlet's implementation
    for attr in ("Content", "Text", "RawContent", "Data", "Value",
                 "StringContent", "Body", "Payload"):
        if hasattr(raw_obj, attr):
            try:
                val = getattr(raw_obj, attr)
                if val is not None and isinstance(val, str) and val.strip():
                    log_info(f"Extracted body via .{attr}: {len(val)} chars")
                    return val.strip()
            except Exception:
                continue

    # Try calling it as a method (some Swiftlet types use methods)
    for method in ("GetContent", "GetText", "ToString", "ReadAsString"):
        if hasattr(raw_obj, method) and callable(getattr(raw_obj, method)):
            try:
                val = getattr(raw_obj, method)()
                if val is not None and isinstance(val, str) and val.strip():
                    # Filter out the type label (e.g., "REQUEST BODY\n[ application/json ]")
                    if not val.strip().startswith("REQUEST BODY"):
                        log_info(f"Extracted body via .{method}(): {len(val)} chars")
                        return val.strip()
            except Exception:
                continue

    # Last resort: str() conversion, but filter out Swiftlet type labels
    fallback = str(raw_obj).strip()
    if fallback and not fallback.startswith("REQUEST BODY"):
        return fallback

    # Log what we found for debugging
    obj_type = type(raw_obj).__name__
    obj_attrs = [a for a in dir(raw_obj) if not a.startswith("_")]
    log_info(f"RequestBody unwrap failed. Type: {obj_type}")
    log_info(f"Available attributes: {obj_attrs[:20]}")
    return ""


def _parse_request_body(content) -> tuple:
    """Parse and validate the HTTP request body.

    Args:
        content: Raw object from Swiftlet Deconstruct Body Tx output.
                 May be a string, a Swiftlet RequestBody, or None.

    Returns:
        tuple: (is_valid, parsed_dict, error_message)
    """
    if content is None:
        return False, {}, "No content received (Listener idle)"

    # Unwrap the Swiftlet RequestBody object to get the raw text
    text = _unwrap_body_content(content)

    if not text:
        return False, {}, "Empty request body (could not extract text from RequestBody object)"

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return False, {}, f"Invalid JSON in request body: {e} (raw: {text[:100]})"

    if not isinstance(parsed, dict):
        return False, {}, f"Request body must be a JSON object, got {type(parsed).__name__}"

    return True, parsed, None


def _resolve_stage(request_data: dict) -> tuple:
    """Resolve the pipeline stage from the request data.

    Args:
        request_data: Parsed JSON dict from the HTTP request body.

    Returns:
        tuple: (stage_name, stage_level) where stage_level is an int
               used for cumulative comparison.
    """
    stage = request_data.get("stage", DEFAULT_STAGE)
    stage = str(stage).strip().lower()

    if stage not in STAGE_LEVELS:
        valid = ", ".join(sorted(STAGE_LEVELS.keys(), key=lambda s: STAGE_LEVELS[s]))
        log_warning(f'Unknown stage "{stage}", defaulting to "{DEFAULT_STAGE}". Valid: {valid}')
        stage = DEFAULT_STAGE

    return stage, STAGE_LEVELS[stage]


def _build_config(request_data: dict, stage: str) -> dict:
    """Build a validated config dict from the HTTP request data.

    Extracts known fields, applies defaults for missing ones, and
    builds a config_json compatible with the existing pipeline.

    Args:
        request_data: Parsed JSON dict from the HTTP request body.
        stage: Resolved stage name.

    Returns:
        dict: Validated config for downstream pipeline components.
    """
    config = {}

    # Stage (included so downstream components can read it if needed)
    config["stage"] = stage

    # Material / framing system
    material = request_data.get("material", DEFAULT_MATERIAL)
    if material not in ("timber", "cfs"):
        log_warning(f'Unknown material "{material}", defaulting to "{DEFAULT_MATERIAL}"')
        material = DEFAULT_MATERIAL
    config["framing_system"] = material

    # Stud spacing (input in inches, output in feet for pipeline)
    stud_spacing_in = request_data.get("stud_spacing_in", DEFAULT_STUD_SPACING_IN)
    try:
        stud_spacing_in = float(stud_spacing_in)
        if stud_spacing_in <= 0:
            raise ValueError("Must be positive")
    except (TypeError, ValueError):
        log_warning(f"Invalid stud_spacing_in: {stud_spacing_in}, defaulting to {DEFAULT_STUD_SPACING_IN}")
        stud_spacing_in = DEFAULT_STUD_SPACING_IN
    config["stud_spacing"] = stud_spacing_in / 12.0  # Convert inches -> feet

    # Panel max length (feet)
    panel_max_length = request_data.get("panel_max_length_ft", DEFAULT_PANEL_MAX_LENGTH_FT)
    try:
        panel_max_length = float(panel_max_length)
        if panel_max_length <= 0:
            raise ValueError("Must be positive")
    except (TypeError, ValueError):
        log_warning(f"Invalid panel_max_length_ft: {panel_max_length}, defaulting to {DEFAULT_PANEL_MAX_LENGTH_FT}")
        panel_max_length = DEFAULT_PANEL_MAX_LENGTH_FT
    config["panel_max_length"] = panel_max_length

    # Assembly flags
    config["generate_assemblies"] = bool(
        request_data.get("generate_assemblies", DEFAULT_GENERATE_ASSEMBLIES)
    )
    config["generate_sheets"] = bool(
        request_data.get("generate_sheets", DEFAULT_GENERATE_SHEETS)
    )

    # Assembly naming prefix
    prefix = request_data.get("assembly_naming_prefix", DEFAULT_ASSEMBLY_NAMING_PREFIX)
    config["assembly_naming_prefix"] = str(prefix).strip() or DEFAULT_ASSEMBLY_NAMING_PREFIX

    # Pass through assembly_mode (default: auto)
    config["assembly_mode"] = request_data.get("assembly_mode", "auto")

    return config


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the HTTP Trigger component.

    Workflow:
    1. Setup component metadata
    2. Read Content input from Swiftlet Deconstruct Body Tx
    3. Parse and validate as JSON
    4. Resolve stage and compute per-stage booleans
    5. Extract config with defaults
    6. Output per-stage triggers + config JSON

    Returns:
        tuple: (run_analyze, config_json, info, run_frame, run_bake,
                run_sheathing, run_assemble)
    """
    setup_component()

    # Default: all False, empty config
    # Order: run_analyze, config_json, info, run_frame, run_bake, run_sheathing, run_assemble
    false_result = (False, "", "No request", False, False, False, False)

    try:
        # Read input by index
        content = _read_input(0)

        # Parse request body
        is_valid, request_data, error_msg = _parse_request_body(content)

        if not is_valid:
            log_info(f"HTTP Trigger: {error_msg}")
            # Order: run_analyze, config_json, info, run_frame, run_bake, run_sheathing, run_assemble
            return (False, "", error_msg, False, False, False, False)

        # Resolve stage
        stage, stage_level = _resolve_stage(request_data)

        # Compute per-stage booleans (cumulative)
        run_analyze = stage_level >= STAGE_LEVELS["analyze"]
        run_frame = stage_level >= STAGE_LEVELS["frame"]
        run_bake = stage_level >= STAGE_LEVELS["bake"]
        run_assemble = stage_level >= STAGE_LEVELS["assemble"]
        run_sheathing = stage_level >= STAGE_LEVELS["sheathing"]

        # Build validated config
        config = _build_config(request_data, stage)
        config_json = json.dumps(config, indent=2)

        # Build info summary
        active_stages = []
        if run_analyze:
            active_stages.append("analyze")
        if run_frame:
            active_stages.append("frame")
        if run_bake:
            active_stages.append("bake")
        if run_sheathing:
            active_stages.append("sheathing")
        if run_assemble:
            active_stages.append("assemble")

        info_lines = [
            f"HTTP Trigger: Request received (stage={stage})",
            f"  active: {' -> '.join(active_stages)}",
            f"  material: {config['framing_system']}",
            f"  stud_spacing: {config['stud_spacing']:.4f} ft ({config['stud_spacing'] * 12:.1f} in OC)",
            f"  panel_max_length: {config['panel_max_length']:.1f} ft",
            f"  generate_assemblies: {config['generate_assemblies']}",
            f"  generate_sheets: {config['generate_sheets']}",
            f"  assembly_prefix: {config['assembly_naming_prefix']}",
        ]
        info = "\n".join(info_lines)
        log_info(info)

        return (run_analyze, config_json, info,
                run_frame, run_bake, run_sheathing, run_assemble)

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return false_result


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    result = main()
    run_analyze, config_json, info, run_frame, run_bake, run_sheathing, run_assemble = result
