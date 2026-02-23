# File: scripts/gh_mcp_framing_args.py
"""MCP Framing Args Extractor for Grasshopper.

Extracts arguments from the MCP ``generate_framing`` tool call and converts
them into the inputs expected by the full baking pipeline (Panel Decomposer,
Cell Decomposer, Framing Generator, Geometry Converter, Revit Baker,
Multi-Layer Sheathing, Sheathing Baker, Assembly Creator). Acts as the
upstream adapter between the Swiftlet MCP Deconstruct Tool Call and the
existing pipeline components.

Key Features:
1. MCP Argument Parsing
   - Reads the Args JSON string from Deconstruct Tool Call
   - Extracts ``stud_spacing`` (inches) and converts to feet
   - Extracts boolean stage flags: ``bake``, ``sheathing``, ``assemblies``,
     ``sheathing_in_assemblies``
   - Validates that walls_json is available before enabling pipeline

2. Pipeline Gating
   - Outputs independent boolean gates for each pipeline stage
   - ``run_frame``: True when args + walls_json valid (always needed)
   - ``run_bake``: run_frame AND bake (default True)
   - ``run_sheathing``: run_frame AND sheathing (default False)
   - ``run_assemble``: run_bake AND assemblies (must bake before assembling)
   - ``sheathing_gate``: run_sheathing AND run_assemble AND
     sheathing_in_assemblies (Stream Filter gate)

3. Config Generation
   - Builds a config_json compatible with Framing Generator + downstream
   - Includes framing_system, stud_spacing, stage, assembly, and sheathing
     settings (matching gh_http_trigger.py pattern)

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
    3. Wire output 1 (walls_json_out) to Junction Analyzer in 0,
       ML Sheathing in 0
    4. Wire output 2 (stud_space_ft) to Panel Decomposer stud_space input
    5. Wire output 3 (run_frame) to Panel Decomposer, Cell Decomposer,
       Framing Generator, Geometry Converter run inputs
    6. Wire output 4 (run_bake) to Revit Baker run input
    7. Wire output 5 (run_sheathing) to ML Sheathing run, Sheathing Baker run
    8. Wire output 6 (run_assemble) to Assembly Creator run input
    9. Wire output 7 (sheathing_gate) to Stream Filter G inputs
       (for sheathing_ids and sheathing_data_json into Assembly Creator)
    10. Wire output 8 (config_json) to Junction Analyzer in 1,
        Framing Generator in 3
    11. Monitor output 9 (info) for debug messages

Input Requirements:
    MCP Args (mcp_args) - str:
        JSON string from Deconstruct Tool Call "Args" output.
        Expected fields:
        {
            "stud_spacing": <number in inches, default 16>,
            "bake": <bool, default true>,
            "sheathing": <bool, default false>,
            "assemblies": <bool, default false>,
            "sheathing_in_assemblies": <bool, default true>
        }
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer "walls_json" output.
        Must be a valid JSON array of wall objects.
        Optional when walls_json is provided in MCP args dict (preferred)
        or when Revit is available for inline fallback query.
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Walls JSON Out (walls_json_out) - str:
        Pass-through of the walls_json input for downstream components.

    Stud Spacing (stud_space_ft) - float:
        Stud spacing in feet, converted from inches in MCP args.
        Defaults to 1.333 ft (16" OC) if not specified.

    Run Frame (run_frame) - bool:
        True when both MCP args and walls_json are valid.
        Wire to Panel Decomposer, Cell Decomposer, Framing Generator,
        Geometry Converter run inputs.

    Run Bake (run_bake) - bool:
        True when run_frame AND bake=true.
        Wire to Revit Baker run input.

    Run Sheathing (run_sheathing) - bool:
        True when run_frame AND sheathing=true.
        Wire to ML Sheathing and Sheathing Baker run inputs.

    Run Assemble (run_assemble) - bool:
        True when run_bake AND assemblies=true.
        Wire to Assembly Creator run input.

    Sheathing Gate (sheathing_gate) - bool:
        True when run_sheathing AND run_assemble AND sheathing_in_assemblies.
        Wire to Stream Filter G input (gates sheathing into assemblies).

    Config JSON (config_json) - str:
        Pipeline configuration JSON for Framing Generator and downstream.
        Contains framing_system, stud_spacing, stage, assembly, and
        sheathing settings.

    Info (info) - str:
        Human-readable summary of parsed arguments and pipeline readiness.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes to prevent wire disconnection
    - No RhinoCommonFactory needed (no geometry output)
    - stud_spacing conversion: inches / 12.0 = feet
    - Default stud_spacing: 16" OC = 1.333 ft
    - bake defaults True (demo purpose: see results in Revit)
    - sheathing and assemblies default False (opt-in for heavier ops)

walls_json Resolution Order (four-tier):
    1. MCP args dict ``walls_json`` key -- agent passes analyze_walls output directly
       (preferred: no canvas Data Recorder dependency, always fresh)
    1.5 MCP args dict ``wall_ids`` key -- agent passes ids from create_walls response
       (preferred when analyze_walls was not called; queries walls by ElementId with
       full opening data extraction, so framing correctly skips doors/windows)
    2. GH input 1 (walls_json panel/Data Recorder) -- legacy canvas wiring
    3. Inline Revit fallback -- queries all walls from current Revit document
       (used when wall analyzer run=False and no cached data; requires Revit)

Error Handling:
    - Missing MCP args: all run flags=False, info shows error
    - No walls_json from any source: all run flags=False, info shows guidance
    - Invalid JSON in args: all run flags=False, warning logged
    - Invalid stud_spacing value: defaults to 16" OC with warning

Author: Timber Framing Generator
Version: 2.1.0
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
COMPONENT_MESSAGE = "v2.1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "0-Config"

DEFAULT_STUD_SPACING_IN = 16.0
DEFAULT_MATERIAL = "timber"
DEFAULT_BAKE = True
DEFAULT_SHEATHING = False
DEFAULT_ASSEMBLIES = False
DEFAULT_SHEATHING_IN_ASSEMBLIES = True
DEFAULT_PANEL_MAX_LENGTH_FT = 24.0
DEFAULT_ASSEMBLY_NAMING_PREFIX = "W"

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
        # Index 1
        ("Walls JSON Out", "walls_json_out",
         "Pass-through walls_json for downstream pipeline components"),
        # Index 2
        ("Stud Spacing", "stud_space_ft",
         "Stud spacing in feet (converted from inches)"),
        # Index 3
        ("Run Frame", "run_frame",
         "True when args and walls_json are valid. Wire to Decomposers + Framing Gen + Geom Converter."),
        # Index 4
        ("Run Bake", "run_bake",
         "True when run_frame AND bake=true. Wire to Revit Baker."),
        # Index 5
        ("Run Sheathing", "run_sheathing",
         "True when run_frame AND sheathing=true. Wire to ML Sheathing + Sheathing Baker."),
        # Index 6
        ("Run Assemble", "run_assemble",
         "True when run_bake AND assemblies=true. Wire to Assembly Creator."),
        # Index 7
        ("Sheathing Gate", "sheathing_gate",
         "True when sheathing should be included in assemblies. Wire to Stream Filter G."),
        # Index 8
        ("Config JSON", "config_json",
         "Pipeline configuration JSON for Framing Generator and downstream"),
        # Index 9
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


def _extract_bool(args: dict, key: str, default: bool) -> bool:
    """Extract a boolean value from MCP args with a default.

    Handles string "true"/"false" from JSON as well as actual booleans.

    Args:
        args: Parsed MCP args dict.
        key: Key to look up.
        default: Default value if key is missing.

    Returns:
        bool: Extracted boolean value.
    """
    val = args.get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def _validate_walls_json(walls_json_raw) -> tuple:
    """Validate the walls_json input.

    Args:
        walls_json_raw: Raw string from Wall Analyzer.

    Returns:
        tuple: (is_valid, error_message)
    """
    if walls_json_raw is None:
        return False, "walls_json is None"

    if not isinstance(walls_json_raw, str):
        walls_json_raw = str(walls_json_raw)

    walls_json_raw = walls_json_raw.strip()
    if not walls_json_raw:
        return False, "walls_json is empty"

    try:
        parsed = json.loads(walls_json_raw)
        if not isinstance(parsed, list):
            return False, "walls_json must be a JSON array of wall objects"
        if len(parsed) == 0:
            return False, "walls_json contains no walls"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


def _query_all_walls_from_revit() -> tuple:
    """Tier-3 fallback: query all walls from the active Revit document.

    Called when both MCP args walls_json and GH input 1 are empty/invalid
    (e.g. Wall Analyzer run=False and no cached Data Recorder value).
    Produces the same walls_json format as Wall Analyzer.

    Returns:
        tuple: (walls_json_str or None, info_message)
    """
    try:
        import clr as _clr
        _clr.AddReference("RhinoInside.Revit")
        _clr.AddReference("RevitAPI")
        from RhinoInside.Revit import Revit
        doc = Revit.ActiveDBDocument
        if doc is None:
            return None, "Revit fallback: no active Revit document"

        from Autodesk.Revit.DB import (
            FilteredElementCollector, Wall, BuiltInCategory,
        )
        wall_elements = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Walls)
            .OfClass(Wall)
            .ToElements()
        )
        if not wall_elements:
            return None, "Revit fallback: no walls in Revit document"

        # Import wall extraction (same modules as gh_wall_analyzer.py)
        PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
        if PROJECT_PATH not in sys.path:
            sys.path.insert(0, PROJECT_PATH)

        from src.timber_framing_generator.wall_data.revit_data_extractor import (
            extract_wall_data_from_revit,
        )
        from src.timber_framing_generator.core.json_schemas import (
            WallData, Point3D, Vector3D, PlaneData, OpeningData,
            serialize_wall_data, FramingJSONEncoder,
        )

        walls_out = []
        for wall_elem in wall_elements:
            try:
                wall_data = extract_wall_data_from_revit(wall_elem, doc)
                if wall_data is None:
                    continue
                # Build wall_id from ElementId
                eid = wall_elem.Id
                wall_id = str(int(eid.Value) if hasattr(eid, "Value") else int(eid.IntegerValue))

                # Minimal WallData dict (same format as Wall Analyzer)
                base_plane = wall_data.get("base_plane")
                if base_plane:
                    plane_dict = {
                        "origin": {"x": base_plane.Origin.X, "y": base_plane.Origin.Y, "z": base_plane.Origin.Z},
                        "x_axis": {"x": base_plane.XAxis.X, "y": base_plane.XAxis.Y, "z": base_plane.XAxis.Z},
                        "y_axis": {"x": base_plane.YAxis.X, "y": base_plane.YAxis.Y, "z": base_plane.YAxis.Z},
                        "z_axis": {"x": base_plane.ZAxis.X, "y": base_plane.ZAxis.Y, "z": base_plane.ZAxis.Z},
                    }
                else:
                    plane_dict = {
                        "origin": {"x": 0, "y": 0, "z": 0},
                        "x_axis": {"x": 1, "y": 0, "z": 0},
                        "y_axis": {"x": 0, "y": 1, "z": 0},
                        "z_axis": {"x": 0, "y": 0, "z": 1},
                    }

                # Override z_axis with exterior normal if available
                en = wall_data.get("exterior_normal")
                if isinstance(en, dict):
                    plane_dict["z_axis"] = {"x": float(en.get("x", 0)), "y": float(en.get("y", 0)), "z": float(en.get("z", 0))}

                base_curve = wall_data.get("wall_base_curve")
                curve_start = {"x": base_curve.PointAtStart.X, "y": base_curve.PointAtStart.Y, "z": base_curve.PointAtStart.Z} if base_curve else {"x": 0, "y": 0, "z": 0}
                curve_end = {"x": base_curve.PointAtEnd.X, "y": base_curve.PointAtEnd.Y, "z": base_curve.PointAtEnd.Z} if base_curve else {"x": 1, "y": 0, "z": 0}

                base_level = wall_data.get("base_level")
                top_level = wall_data.get("top_level")

                def _eid_int_local(eid_obj):
                    if hasattr(eid_obj, "Value"):
                        return int(eid_obj.Value)
                    return int(eid_obj.IntegerValue)

                wall_dict = {
                    "wall_id": wall_id,
                    "wall_length": float(wall_data.get("wall_length", 0)),
                    "wall_height": float(wall_data.get("wall_height", 0)),
                    "wall_thickness": float(wall_data.get("wall_thickness", 0)),
                    "base_elevation": float(wall_data.get("base_elevation", 0)),
                    "base_plane": plane_dict,
                    "curve_start": curve_start,
                    "curve_end": curve_end,
                    "base_level_id": _eid_int_local(base_level.Id) if base_level else None,
                    "top_level_id": _eid_int_local(top_level.Id) if top_level else None,
                    "openings": [
                        {k: v for k, v in op.items() if k != "opening_location_point"}
                        for op in wall_data.get("openings", [])
                    ],
                    "is_flipped": bool(wall_data.get("is_flipped", False)),
                    "wall_type": str(wall_data.get("wall_type", "")),
                    "metadata": wall_data.get("metadata", {}),
                }
                walls_out.append(wall_dict)
            except Exception as wall_err:
                log_info("Revit fallback: skipped wall %s: %s" % (wall_id, wall_err))
                continue

        if not walls_out:
            return None, "Revit fallback: all walls failed extraction"

        walls_json_str = json.dumps(walls_out)
        return walls_json_str, "Revit fallback: queried %d walls from document" % len(walls_out)

    except Exception as e:
        return None, "Revit fallback failed: %s" % str(e)


def _query_walls_by_id(wall_ids: list) -> tuple:
    """Tier-1.5: Query specific walls from Revit by ElementId.

    Called when wall_ids are provided in MCP args (e.g., from a prior
    create_walls call). Extracts full wall data including openings so that
    the framing generator can skip doors/windows correctly.

    This bypasses the need for a separate analyze_walls call — the agent
    passes the wall_ids it received from create_walls directly.

    Args:
        wall_ids: List of Revit ElementId integers from create_walls response.

    Returns:
        tuple: (walls_json_str or None, info_message)
    """
    if not wall_ids:
        return None, "wall_ids Tier-1.5: empty list"

    try:
        import clr as _clr
        _clr.AddReference("RhinoInside.Revit")
        _clr.AddReference("RevitAPI")
        from RhinoInside.Revit import Revit
        doc = Revit.ActiveDBDocument
        if doc is None:
            return None, "wall_ids Tier-1.5: no active Revit document"

        from Autodesk.Revit.DB import ElementId as _ElemId, Wall as _Wall

        PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
        if PROJECT_PATH not in sys.path:
            sys.path.insert(0, PROJECT_PATH)

        from src.timber_framing_generator.wall_data.revit_data_extractor import (
            extract_wall_data_from_revit,
        )

        walls_out = []
        skipped = 0
        for raw_id in wall_ids:
            try:
                eid = _ElemId(int(raw_id))
                elem = doc.GetElement(eid)
                if elem is None or not isinstance(elem, _Wall):
                    skipped += 1
                    continue

                wall_data = extract_wall_data_from_revit(elem, doc)
                if wall_data is None:
                    skipped += 1
                    continue

                wall_id_str = str(raw_id)
                base_plane = wall_data.get("base_plane")
                if base_plane:
                    plane_dict = {
                        "origin": {"x": base_plane.Origin.X, "y": base_plane.Origin.Y, "z": base_plane.Origin.Z},
                        "x_axis": {"x": base_plane.XAxis.X, "y": base_plane.XAxis.Y, "z": base_plane.XAxis.Z},
                        "y_axis": {"x": base_plane.YAxis.X, "y": base_plane.YAxis.Y, "z": base_plane.YAxis.Z},
                        "z_axis": {"x": base_plane.ZAxis.X, "y": base_plane.ZAxis.Y, "z": base_plane.ZAxis.Z},
                    }
                else:
                    plane_dict = {
                        "origin": {"x": 0, "y": 0, "z": 0},
                        "x_axis": {"x": 1, "y": 0, "z": 0},
                        "y_axis": {"x": 0, "y": 1, "z": 0},
                        "z_axis": {"x": 0, "y": 0, "z": 1},
                    }

                en = wall_data.get("exterior_normal")
                if isinstance(en, dict):
                    plane_dict["z_axis"] = {"x": float(en.get("x", 0)), "y": float(en.get("y", 0)), "z": float(en.get("z", 0))}

                base_curve = wall_data.get("wall_base_curve")
                curve_start = {"x": base_curve.PointAtStart.X, "y": base_curve.PointAtStart.Y, "z": base_curve.PointAtStart.Z} if base_curve else {"x": 0, "y": 0, "z": 0}
                curve_end = {"x": base_curve.PointAtEnd.X, "y": base_curve.PointAtEnd.Y, "z": base_curve.PointAtEnd.Z} if base_curve else {"x": 1, "y": 0, "z": 0}

                base_level = wall_data.get("base_level")
                top_level = wall_data.get("top_level")

                def _eid_int_local(eid_obj):
                    if hasattr(eid_obj, "Value"):
                        return int(eid_obj.Value)
                    return int(eid_obj.IntegerValue)

                wall_dict = {
                    "wall_id": wall_id_str,
                    "wall_length": float(wall_data.get("wall_length", 0)),
                    "wall_height": float(wall_data.get("wall_height", 0)),
                    "wall_thickness": float(wall_data.get("wall_thickness", 0)),
                    "base_elevation": float(wall_data.get("base_elevation", 0)),
                    "base_plane": plane_dict,
                    "curve_start": curve_start,
                    "curve_end": curve_end,
                    "base_level_id": _eid_int_local(base_level.Id) if base_level else None,
                    "top_level_id": _eid_int_local(top_level.Id) if top_level else None,
                    "openings": [
                        {k: v for k, v in op.items() if k != "opening_location_point"}
                        for op in wall_data.get("openings", [])
                    ],
                    "is_flipped": bool(wall_data.get("is_flipped", False)),
                    "wall_type": str(wall_data.get("wall_type", "")),
                    "metadata": wall_data.get("metadata", {}),
                }
                walls_out.append(wall_dict)
            except Exception as wall_err:
                log_info("wall_ids Tier-1.5: skipped id %s: %s" % (raw_id, wall_err))
                skipped += 1
                continue

        if not walls_out:
            return None, "wall_ids Tier-1.5: all %d walls failed extraction" % len(wall_ids)

        walls_json_str = json.dumps(walls_out)
        return walls_json_str, "wall_ids Tier-1.5: queried %d/%d walls (skipped %d)" % (
            len(walls_out), len(wall_ids), skipped
        )

    except Exception as e:
        return None, "wall_ids Tier-1.5 failed: %s" % str(e)


def _build_config(args: dict, stud_space_ft: float, stage: str) -> dict:
    """Build a config dict from MCP args for downstream pipeline components.

    Matches the config schema used by gh_http_trigger.py so that downstream
    components (Junction Analyzer, Framing Generator, Assembly Creator) see
    the same fields regardless of whether the pipeline was triggered via
    HTTP or MCP.

    Args:
        args: Parsed MCP args dict.
        stud_space_ft: Stud spacing already converted to feet.
        stage: Resolved pipeline stage string.

    Returns:
        dict: Config dict for serialization to config_json.
    """
    config = {
        "stage": stage,
        "framing_system": DEFAULT_MATERIAL,
        "stud_spacing": stud_space_ft,
        "panel_max_length": DEFAULT_PANEL_MAX_LENGTH_FT,
        "generate_assemblies": _extract_bool(args, "assemblies", DEFAULT_ASSEMBLIES),
        "generate_sheets": _extract_bool(args, "assemblies", DEFAULT_ASSEMBLIES),
        "assembly_naming_prefix": DEFAULT_ASSEMBLY_NAMING_PREFIX,
        "assembly_mode": "auto",
    }
    return config


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
    5. Extract stud_spacing and boolean stage flags
    6. Compute run gates for each pipeline stage
    7. Build config_json with full pipeline settings
    8. Output all pipeline inputs and gate signals

    Returns:
        tuple: (walls_json_out, stud_space_ft, run_frame, run_bake,
                run_sheathing, run_assemble, sheathing_gate, config_json, info)
    """
    setup_component()

    # Defaults (all stages off)
    walls_json_out = ""
    stud_space_ft = 1.333  # 16" OC default
    run_frame = False
    run_bake = False
    run_sheathing = False
    run_assemble = False
    sheathing_gate = False
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
            return (walls_json_out, stud_space_ft, run_frame, run_bake,
                    run_sheathing, run_assemble, sheathing_gate,
                    config_json, info)

        # ---------------------------------------------------------------
        # Three-tier walls_json resolution (prevents stale Data Recorder)
        # ---------------------------------------------------------------
        walls_source = "none"

        # Tier 1: walls_json key in MCP args (agent passes analyze_walls output)
        mcp_walls = args_dict.get("walls_json")
        if mcp_walls and isinstance(mcp_walls, str) and mcp_walls.strip():
            walls_json_raw = mcp_walls.strip()
            walls_source = "mcp_args"
            info_lines.append("walls_json: from MCP args (tier 1)")

        # Tier 1.5: wall_ids key in MCP args (agent passes ids from create_walls)
        # Preferred over tier 2/3: ensures openings are included from specific walls
        if walls_source == "none":
            raw_wall_ids = args_dict.get("wall_ids")
            if raw_wall_ids:
                # Accept JSON string or list
                if isinstance(raw_wall_ids, str):
                    try:
                        raw_wall_ids = json.loads(raw_wall_ids)
                    except Exception:
                        raw_wall_ids = []
                if isinstance(raw_wall_ids, list) and raw_wall_ids:
                    ids_walls_json, ids_msg = _query_walls_by_id(raw_wall_ids)
                    info_lines.append(ids_msg)
                    if ids_walls_json:
                        walls_json_raw = ids_walls_json
                        walls_source = "wall_ids"
                        log_info("walls_json: %s" % ids_msg)

        # Tier 2: GH input 1 (Wall Analyzer / Data Recorder on canvas)
        walls_valid, walls_error = _validate_walls_json(walls_json_raw)
        if walls_valid and walls_source == "none":
            walls_source = "canvas_input"
            info_lines.append("walls_json: from canvas input 1 (tier 2)")
        elif not walls_valid and walls_source == "none":
            info_lines.append(f"walls_json input 1 empty ({walls_error}); trying tier 3")

            # Tier 3: inline Revit query (Wall Analyzer run=False fallback)
            revit_walls_json, revit_msg = _query_all_walls_from_revit()
            info_lines.append(revit_msg)
            if revit_walls_json:
                walls_json_raw = revit_walls_json
                walls_valid, walls_error = _validate_walls_json(walls_json_raw)
                if walls_valid:
                    walls_source = "revit_fallback"
                    log_info("walls_json: %s" % revit_msg)

        # Re-validate after tier-1 / tier-1.5 (from MCP args) assignment
        if walls_source in ("mcp_args", "wall_ids"):
            walls_valid, walls_error = _validate_walls_json(walls_json_raw)

        if not walls_valid:
            err = (
                "No valid walls_json from any source. "
                "Call analyze_walls first, or pass walls_json in generate_framing args."
            )
            info_lines.append(err)
            info = "\n".join(info_lines)
            log_warning(err)
            return (walls_json_out, stud_space_ft, run_frame, run_bake,
                    run_sheathing, run_assemble, sheathing_gate,
                    config_json, info)

        # Extract stud_spacing (inches -> feet)
        stud_spacing_in = _extract_stud_spacing(args_dict)
        stud_space_ft = stud_spacing_in / 12.0

        # Extract boolean stage flags from MCP args
        do_bake = _extract_bool(args_dict, "bake", DEFAULT_BAKE)
        do_sheathing = _extract_bool(args_dict, "sheathing", DEFAULT_SHEATHING)
        do_assemblies = _extract_bool(args_dict, "assemblies", DEFAULT_ASSEMBLIES)
        do_sheathing_in_assemblies = _extract_bool(
            args_dict, "sheathing_in_assemblies", DEFAULT_SHEATHING_IN_ASSEMBLIES)

        # Pass through walls_json
        walls_json_out = walls_json_raw.strip()

        # Compute run gates
        run_frame = True  # Args valid + walls valid = always run framing
        run_bake = run_frame and do_bake
        run_sheathing = run_frame and do_sheathing
        run_assemble = run_bake and do_assemblies  # Must bake before assembling
        sheathing_gate = run_sheathing and run_assemble and do_sheathing_in_assemblies

        # Determine effective stage for config_json
        if run_assemble:
            stage = "assemble"
        elif run_sheathing:
            stage = "sheathing"
        elif run_bake:
            stage = "bake"
        else:
            stage = "frame"

        # Build config_json for downstream components
        config = _build_config(args_dict, stud_space_ft, stage)
        config_json = json.dumps(config, indent=2)

        # Build info summary
        walls_data = json.loads(walls_json_out)
        wall_count = len(walls_data) if isinstance(walls_data, list) else 1

        info_lines.append("MCP Framing Args: Pipeline READY")
        info_lines.append(f"  stud_spacing: {stud_spacing_in:.1f} in -> {stud_space_ft:.4f} ft")
        info_lines.append(f"  walls: {wall_count} (source: {walls_source})")
        info_lines.append(f"  stage: {stage}")
        info_lines.append(f"  run_frame:    {run_frame}")
        info_lines.append(f"  run_bake:     {run_bake}")
        info_lines.append(f"  run_sheathing:{run_sheathing}")
        info_lines.append(f"  run_assemble: {run_assemble}")
        info_lines.append(f"  sheathing_gate:{sheathing_gate}")

        info = "\n".join(info_lines)
        log_info(info)

        return (walls_json_out, stud_space_ft, run_frame, run_bake,
                run_sheathing, run_assemble, sheathing_gate,
                config_json, info)

    except Exception as e:
        error_msg = f"Unexpected error in MCP Args Extractor: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        info_lines.append(f"ERROR: {error_msg}")
        return (walls_json_out, stud_space_ft, False, False,
                False, False, False,
                config_json, "\n".join(info_lines))


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    (walls_json_out, stud_space_ft, run_frame, run_bake,
     run_sheathing, run_assemble, sheathing_gate,
     config_json, info) = main()
