# File: scripts/gh_config_builder.py
"""Config Builder for Grasshopper.

Builds a config_json string from user-friendly Grasshopper inputs. This
component acts as the single source of truth for pipeline configuration,
producing a JSON string consumed by downstream components (Multi-Layer
Sheathing Generator, Framing Generator, etc.).

Key Features:
1. User-Friendly Configuration
   - Exposes common settings as individual GH inputs (sliders, panels, toggles)
   - No need to hand-craft JSON strings
   - Always produces valid JSON even with zero inputs connected

2. Validation and Defaults
   - Validates assembly_mode ("auto" or "revit")
   - Validates framing_system ("timber" or "cfs")
   - Parses and validates JSON sub-objects (assembly_overrides, layer_configs)
   - Provides sensible defaults for all settings

3. Selective Output
   - Only includes optional keys when they carry non-default values
   - Keeps output JSON minimal and readable
   - Downstream components apply their own defaults for missing keys

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - json: Serialization of config dictionary

Performance Considerations:
    - Lightweight string processing only; negligible execution time
    - No geometry or heavy computation involved

Usage:
    1. Place component on canvas; it outputs default config immediately
    2. Optionally connect a Panel with "auto" or "revit" to Assembly Mode
    3. Optionally connect a Panel with "timber" or "cfs" to Framing System
    4. Optionally connect assembly_overrides or layer_configs as JSON strings
    5. Optionally wire a Number Slider to Stud Spacing (inches OC)
    6. Connect config_json output to downstream components

Input Requirements:
    Assembly Mode (assembly_mode) - str:
        Assembly resolution mode: "auto" or "revit".
        Required: No (defaults to "auto")
        Access: Item
        Type Hint: str (set via GH UI)

    Framing System (framing_system) - str:
        Material system: "timber" or "cfs".
        Required: No (defaults to "timber")
        Access: Item
        Type Hint: str (set via GH UI)

    Assembly Overrides (assembly_overrides) - str:
        Optional JSON string for per-Wall-Type assembly mappings.
        Example: {"Basic Wall - 2x6 Exterior": "2x6_exterior"}
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Faces (faces) - str:
        Wall faces to process. Provide one or more of:
        "exterior", "interior". Each face as a separate list item.
        Required: No (defaults to ["exterior", "interior"])
        Access: List
        Type Hint: str (set via GH UI)

    Panel Size (panel_size) - str:
        Default panel size for all layers (e.g., "4x8", "4x10", "4x12").
        Required: No (defaults to "4x8")
        Access: Item
        Type Hint: str (set via GH UI)

    Stud Spacing (stud_spacing) - float:
        Stud spacing in inches on-center (e.g., 16.0, 24.0).
        Required: No (defaults to 16.0)
        Access: Item
        Type Hint: float (set via GH UI)

    Include Functions (include_functions) - str:
        Layer function filter. Provide one or more of:
        "substrate", "finish", "thermal". Each as a separate list item.
        Required: No (defaults to all panelizable functions)
        Access: List
        Type Hint: str (set via GH UI)

    Layer Configs (layer_configs) - str:
        Optional JSON string with per-layer configuration overrides.
        Keys are layer names, values are config dicts.
        Example: {"OSB Sheathing": {"panel_size": "4x10"}}
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Config JSON (config_json) - str:
        Serialized JSON configuration string for downstream components.
        Always valid JSON. Minimal keys — only includes non-default values.

Technical Details:
    - No geometry output; RhinoCommonFactory not required
    - No module reloading needed (no project imports)
    - Always-active component (no run toggle)
    - Stud spacing is converted from inches to feet in the output JSON

Error Handling:
    - Invalid assembly_mode: warns and falls back to "auto"
    - Invalid framing_system: warns and falls back to "timber"
    - Invalid JSON in assembly_overrides: warns and skips key
    - Invalid JSON in layer_configs: warns and skips key
    - Empty/None inputs: silently use defaults
    - Always outputs valid JSON regardless of input errors

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

COMPONENT_NAME = "Config Builder"
COMPONENT_NICKNAME = "ConfBuild"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Config"

# Allowed values for validated inputs
VALID_ASSEMBLY_MODES = {"auto", "revit"}
VALID_FRAMING_SYSTEMS = {"timber", "cfs"}
VALID_FACES = {"exterior", "interior"}
VALID_INCLUDE_FUNCTIONS = {"substrate", "finish", "thermal"}

# Defaults
DEFAULT_ASSEMBLY_MODE = "auto"
DEFAULT_FRAMING_SYSTEM = "timber"
DEFAULT_PANEL_SIZE = "4x8"
DEFAULT_STUD_SPACING_INCHES = 16.0

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message: str, level: str = "info") -> None:
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log.
        level: One of "info", "debug", "warning", "error", "remark".
    """
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
    """Log info message (console only)."""
    print(f"[INFO] {message}")


def log_warning(message: str) -> None:
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message: str) -> None:
    """Log error message (console + GH UI)."""
    log_message(message, "error")


# =============================================================================
# Component Setup
# =============================================================================

def setup_component() -> None:
    """Initialize and configure the Grasshopper component.

    Configures:
    1. Component metadata (name, category, etc.)
    2. Input parameter names, descriptions, and access
    3. Output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1].

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # NickName becomes the Python variable name — must be valid Python identifier
    inputs = ghenv.Component.Params.Input

    input_config = [
        # Index 0
        ("Assembly Mode", "assembly_mode",
         'Assembly resolution mode: "auto" or "revit" (default: "auto")',
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 1
        ("Framing System", "framing_system",
         'Material system: "timber" or "cfs" (default: "timber")',
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 2
        ("Assembly Overrides", "assembly_overrides",
         "Optional JSON for per-Wall-Type assembly mappings",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 3
        ("Faces", "faces",
         'Wall faces to process (default: exterior + interior)',
         Grasshopper.Kernel.GH_ParamAccess.list),
        # Index 4
        ("Panel Size", "panel_size",
         'Default panel size, e.g. "4x8", "4x10" (default: "4x8")',
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 5
        ("Stud Spacing", "stud_spacing",
         "Stud spacing in inches OC (default: 16.0)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        # Index 6
        ("Include Functions", "include_functions",
         'Layer function filter: "substrate", "finish", "thermal"',
         Grasshopper.Kernel.GH_ParamAccess.list),
        # Index 7
        ("Layer Configs", "layer_configs",
         'Optional per-layer config JSON (e.g. {"OSB Sheathing": {"panel_size": "4x10"}})',
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Config JSON", "config_json",
         "Serialized JSON config for downstream components"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1  # Skip Output[0]
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc


# =============================================================================
# Helper Functions
# =============================================================================

def _read_input(index: int, default=None):
    """Read a GH input value by parameter index via VolatileData.

    This approach is more reliable than NickName-based global injection
    in Rhino 8 CPython, because setup_component() renames NickNames but
    GH injects globals based on the NickName at solve-start.

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
    # For list-access params, return full list
    if param.Access == Grasshopper.Kernel.GH_ParamAccess.list:
        values = []
        for goo in all_data:
            if hasattr(goo, "Value"):
                values.append(goo.Value)
            elif hasattr(goo, "ScriptVariable"):
                values.append(goo.ScriptVariable())
        return values if values else default
    # For item-access params, return single value
    goo = all_data[0]
    if hasattr(goo, "Value"):
        return goo.Value
    if hasattr(goo, "ScriptVariable"):
        return goo.ScriptVariable()
    return default


def _read_input_list(index: int, default=None):
    """Read a GH list input by parameter index.

    Convenience wrapper around _read_input that always returns a list.

    Args:
        index: Zero-based input parameter index.
        default: Value to return when the input is empty or missing.

    Returns:
        List of input values, or default if not connected / empty.
    """
    result = _read_input(index, default)
    if result is None:
        return default
    if isinstance(result, (list, tuple)):
        return list(result)
    return [result]


def _safe_str(value, default: str = "") -> str:
    """Safely convert a value to a stripped string.

    Args:
        value: Input value (may be None, str, or other type).
        default: Fallback when value is None or empty.

    Returns:
        Stripped lowercase string, or default.
    """
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _parse_json_input(value, input_name: str) -> dict | None:
    """Parse a JSON string input, logging warnings on failure.

    Args:
        value: Raw input value (str or None).
        input_name: Human-readable name for log messages.

    Returns:
        Parsed dict, or None if input is empty or invalid.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        parsed = json.loads(s)
        if not isinstance(parsed, dict):
            log_warning(
                f"{input_name} must be a JSON object (dict), "
                f"got {type(parsed).__name__}. Ignoring."
            )
            return None
        return parsed
    except json.JSONDecodeError as e:
        log_warning(f"Invalid JSON in {input_name}: {e}")
        return None


def validate_inputs(assembly_mode_raw, framing_system_raw):
    """Validate user inputs and return cleaned values.

    Checks assembly_mode and framing_system against allowed values.
    Warns on invalid values and falls back to defaults.

    Args:
        assembly_mode_raw: Raw assembly mode string from input.
        framing_system_raw: Raw framing system string from input.

    Returns:
        tuple: (assembly_mode, framing_system) with validated values.
    """
    # Validate assembly_mode
    assembly_mode = _safe_str(assembly_mode_raw, DEFAULT_ASSEMBLY_MODE).lower()
    if assembly_mode not in VALID_ASSEMBLY_MODES:
        log_warning(
            f'Invalid assembly_mode "{assembly_mode}". '
            f"Expected one of {sorted(VALID_ASSEMBLY_MODES)}. "
            f'Falling back to "{DEFAULT_ASSEMBLY_MODE}".'
        )
        assembly_mode = DEFAULT_ASSEMBLY_MODE

    # Validate framing_system
    framing_system = _safe_str(framing_system_raw, DEFAULT_FRAMING_SYSTEM).lower()
    if framing_system not in VALID_FRAMING_SYSTEMS:
        log_warning(
            f'Invalid framing_system "{framing_system}". '
            f"Expected one of {sorted(VALID_FRAMING_SYSTEMS)}. "
            f'Falling back to "{DEFAULT_FRAMING_SYSTEM}".'
        )
        framing_system = DEFAULT_FRAMING_SYSTEM

    return assembly_mode, framing_system


def _clean_faces_list(raw_faces) -> list[str] | None:
    """Clean and validate a faces list input.

    Filters to valid face names and deduplicates. Returns None if
    the input is empty (so downstream components use their defaults).

    Args:
        raw_faces: List of face name strings from GH input, or None.

    Returns:
        Deduplicated list of valid face names, or None if empty.
    """
    if not raw_faces:
        return None

    cleaned = []
    seen = set()
    for item in raw_faces:
        face = _safe_str(item).lower()
        if not face:
            continue
        if face not in VALID_FACES:
            log_warning(
                f'Ignoring unknown face "{face}". '
                f"Valid faces: {sorted(VALID_FACES)}"
            )
            continue
        if face not in seen:
            cleaned.append(face)
            seen.add(face)

    return cleaned if cleaned else None


def _clean_include_functions_list(raw_functions) -> list[str] | None:
    """Clean and validate an include_functions list input.

    Filters to valid function names and deduplicates. Returns None if
    the input is empty (so downstream components process all functions).

    Args:
        raw_functions: List of function name strings from GH input, or None.

    Returns:
        Deduplicated list of valid function names, or None if empty.
    """
    if not raw_functions:
        return None

    cleaned = []
    seen = set()
    for item in raw_functions:
        func = _safe_str(item).lower()
        if not func:
            continue
        if func not in VALID_INCLUDE_FUNCTIONS:
            log_warning(
                f'Ignoring unknown include_function "{func}". '
                f"Valid functions: {sorted(VALID_INCLUDE_FUNCTIONS)}"
            )
            continue
        if func not in seen:
            cleaned.append(func)
            seen.add(func)

    return cleaned if cleaned else None


def _parse_stud_spacing(raw_value) -> float | None:
    """Parse and validate stud spacing input.

    Args:
        raw_value: Raw stud spacing value from GH input (float or None).

    Returns:
        Stud spacing in inches, or None if input is empty / default.
    """
    if raw_value is None:
        return None

    try:
        spacing = float(raw_value)
    except (TypeError, ValueError):
        log_warning(
            f"Invalid stud_spacing value: {raw_value!r}. "
            f"Expected a number (inches OC). Ignoring."
        )
        return None

    if spacing <= 0:
        log_warning(
            f"stud_spacing must be positive, got {spacing}. Ignoring."
        )
        return None

    return spacing


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the Config Builder component.

    Orchestrates the config building workflow:
    1. Sets up component metadata
    2. Reads all inputs by index
    3. Validates constrained inputs (assembly_mode, framing_system)
    4. Parses JSON sub-inputs (assembly_overrides, layer_configs)
    5. Builds config dict with only non-default values
    6. Serializes to JSON string

    Returns:
        str: Serialized JSON config string. Always valid JSON.
    """
    setup_component()

    try:
        # Read all inputs by index (reliable in Rhino 8 CPython)
        assembly_mode_raw = _read_input(0)       # assembly_mode
        framing_system_raw = _read_input(1)       # framing_system
        assembly_overrides_raw = _read_input(2)   # assembly_overrides
        faces_raw = _read_input_list(3)           # faces (list)
        panel_size_raw = _read_input(4)           # panel_size
        stud_spacing_raw = _read_input(5)         # stud_spacing
        include_functions_raw = _read_input_list(6)  # include_functions (list)
        layer_configs_raw = _read_input(7)        # layer_configs

        # Validate constrained inputs
        assembly_mode, framing_system = validate_inputs(
            assembly_mode_raw, framing_system_raw
        )

        # Parse JSON sub-inputs
        assembly_overrides = _parse_json_input(
            assembly_overrides_raw, "assembly_overrides"
        )
        layer_configs = _parse_json_input(layer_configs_raw, "layer_configs")

        # Clean list inputs
        faces = _clean_faces_list(faces_raw)
        include_functions = _clean_include_functions_list(include_functions_raw)

        # Parse scalar inputs
        panel_size = _safe_str(panel_size_raw) or None
        stud_spacing = _parse_stud_spacing(stud_spacing_raw)

        # Build config dict — only include keys with non-default / non-None values
        config = {}

        # Always include assembly_mode and framing_system
        config["assembly_mode"] = assembly_mode
        config["framing_system"] = framing_system

        # Optional keys — only included when explicitly provided
        if assembly_overrides is not None:
            config["assembly_overrides"] = assembly_overrides

        if faces is not None:
            config["faces"] = faces

        if panel_size is not None:
            config["panel_size"] = panel_size

        if stud_spacing is not None:
            # Convert inches to feet for downstream components
            config["stud_spacing"] = stud_spacing / 12.0

        if include_functions is not None:
            config["include_functions"] = include_functions

        if layer_configs is not None:
            config["layer_configs"] = layer_configs

        # Log summary of what was built
        log_info(f"Config Builder {COMPONENT_MESSAGE}")
        log_info(f"  assembly_mode: {assembly_mode}")
        log_info(f"  framing_system: {framing_system}")
        if faces is not None:
            log_info(f"  faces: {faces}")
        if panel_size is not None:
            log_info(f"  panel_size: {panel_size}")
        if stud_spacing is not None:
            log_info(f"  stud_spacing: {stud_spacing} in ({stud_spacing / 12.0:.4f} ft)")
        if include_functions is not None:
            log_info(f"  include_functions: {include_functions}")
        if assembly_overrides is not None:
            log_info(f"  assembly_overrides: {len(assembly_overrides)} mappings")
        if layer_configs is not None:
            log_info(f"  layer_configs: {list(layer_configs.keys())}")

        config_json_output = json.dumps(config, indent=2)
        log_info(f"  Output keys: {list(config.keys())}")

        return config_json_output

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        print(traceback.format_exc())
        # Return minimal valid JSON even on error
        fallback = {
            "assembly_mode": DEFAULT_ASSEMBLY_MODE,
            "framing_system": DEFAULT_FRAMING_SYSTEM,
        }
        return json.dumps(fallback, indent=2)


# =============================================================================
# Execution
# =============================================================================

# No run toggle — this component is always active.
# No module reload — no project imports to cache.
# Inputs are read inside main() via _read_input() by index.

if __name__ == "__main__":
    config_json = main()
