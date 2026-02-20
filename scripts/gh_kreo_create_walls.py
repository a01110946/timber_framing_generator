# File: scripts/gh_kreo_create_walls.py
"""Kreo Wall Creator for Grasshopper (Junction Analyzer-enriched).

Creates Revit walls from Junction Analyzer-enriched walls_json. Uses
framing_segments to compute clean wall endpoints with proper butt joints
at corners. This is the wall creation step in the Kreo-to-Revit pipeline.

Data Flow:
    [Kreo JSON] -> [gh_kreo_to_walls_json] -> [Junction Analyzer]
        -> [gh_kreo_create_walls] -> [door/window creators]

Key Features:
1. JA-Enriched Input
   - Reads wall dicts with framing_segments from Junction Analyzer
   - Falls back to base_curve_start/end when JA is bypassed

2. Clean Endpoint Computation
   - Uses framing_segments (extend/trim adjustments) for clean corners
   - Computes world-space endpoints from U-parameter + wall direction

3. Wall Classification and Creation
   - Classifies walls by thickness (2x4 interior / 2x6 exterior)
   - Finds matching Revit WallTypes
   - Creates walls in a single Revit transaction

4. Result Output
   - Outputs walls_result_json with wall_ids, walls_ft (clean), scale, max_y_px
   - Downstream door/window creators consume this to match openings

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit

Dependencies:
    - Grasshopper: Component framework and parameter access
    - Autodesk.Revit.DB: Wall creation
    - src.constructai_demo: Coordinate types, classification, Revit creator

Performance Considerations:
    - Single pass through wall list
    - One Revit transaction for all walls
    - framing_segments computation is O(1) per wall

Usage:
    1. Connect JA-enriched walls_json to input 0
    2. Connect metadata_json from converter to input 1
    3. Connect optional config JSON to input 2
    4. Set input 3 (run) to True to execute
    5. Wire output 1 (walls_result_json) to door/window creators
    6. Monitor output 2 (info) for status

Input Requirements:
    Walls JSON (walls_json) - str:
        JA-enriched wall dicts (list or {"walls": [...]}) with
        framing_segments, base_plane, base_curve_start/end, wall_thickness.
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Metadata JSON (metadata_json) - str:
        From converter: {"scale_m_per_px": ..., "max_y_px": ...,
        "classification": {...}}
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Config JSON (config_json) - str:
        Optional config: {"wall_height_ft": 8.0, "level_name": "Level 1"}
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

    Run (run) - bool:
        Trigger flag. Set to True to execute.
        Required: Yes
        Access: Item
        Type Hint: bool (set via GH UI)

Outputs:
    Walls Result JSON (walls_result_json) - str:
        JSON with wall_ids, walls_ft (clean endpoints), scale_m_per_px,
        max_y_px, wall_height_ft, level_name, classification for downstream.

    Info (info) - str:
        Human-readable status message.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes
    - framing_segments: list of [u_start, u_end] pairs along wall U axis
    - Clean endpoints: origin + x_axis * u_start/u_end from first/last segment
    - Falls back to base_curve_start/end if framing_segments missing
    - Single Revit transaction for wall creation
    - wall_ids list order matches walls_ft list order

Error Handling:
    - Missing walls_json: error status, no Revit operations
    - Missing metadata_json: error status
    - run=False: idle status, no Revit operations
    - Invalid JSON: error with parse details
    - Revit API errors: transaction rollback, error in result_json
    - Walls without framing_segments: fallback to base_curve endpoints

Author: ConstructAI Demo
Version: 2.0.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import sys
import json
import math
import traceback

# .NET / CLR
import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

# Rhino / Grasshopper
import Grasshopper

# =============================================================================
# Project Setup
# =============================================================================

_MAIN_REPO_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Force fresh imports of constructai_demo modules
for mod_name in list(sys.modules.keys()):
    if "constructai_demo" in mod_name or mod_name == "src":
        del sys.modules[mod_name]

# Ensure project root is on sys.path
if _MAIN_REPO_PATH not in sys.path:
    sys.path.insert(0, _MAIN_REPO_PATH)

# ConstructAI Demo modules
from src.constructai_demo.coordinate_converter import (
    ConvertedWall,
    ConvertedPoint,
    METERS_TO_FEET,
)
from src.constructai_demo.revit_creator import (
    create_walls as revit_create_walls,
    find_level,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Kreo Create Walls"
COMPONENT_NICKNAME = "KreoWalls"
COMPONENT_MESSAGE = "v2.1-JA"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

DEFAULT_WALL_HEIGHT_FT = 8.0

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
    """Initialize and configure the Grasshopper component."""
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Walls JSON", "walls_json",
         "JA-enriched walls (with framing_segments)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Metadata JSON", "metadata_json",
         "From converter: scale, max_y, classification",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional config: wall_height_ft, level_name",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Set True to execute (creates Revit walls)",
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

    # Configure outputs (start from index 1)
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Walls Result JSON", "walls_result_json",
         "JSON with wall_ids, walls_ft, scale, max_y_px for downstream"),
        ("Info", "info",
         "Human-readable status message"),
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


def _element_id_int(element_id) -> int:
    """Convert a Revit ElementId to integer."""
    if hasattr(element_id, "IntegerValue"):
        return element_id.IntegerValue
    if hasattr(element_id, "Value"):
        return element_id.Value
    return int(str(element_id))


def _get_revit_doc():
    """Get the active Revit document via RhinoInside."""
    import clr as _clr
    _clr.AddReference("RhinoInside.Revit")
    from RhinoInside.Revit import Revit
    return Revit.ActiveDBDocument


def _parse_config(config_raw) -> dict:
    """Parse optional config JSON."""
    if config_raw is None:
        return {}
    if not isinstance(config_raw, str):
        config_raw = str(config_raw)
    config_raw = config_raw.strip()
    if not config_raw:
        return {}
    try:
        parsed = json.loads(config_raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_walls_json(walls_json_str: str) -> list:
    """Parse walls from JA output JSON.

    Handles both bare list (JA output) and dict with "walls" key.

    Args:
        walls_json_str: JSON string with wall data.

    Returns:
        List of wall dicts.
    """
    data = json.loads(walls_json_str)
    if isinstance(data, dict):
        return data.get("walls", [])
    if isinstance(data, list):
        return data
    return []


def _get_clean_endpoints(wall_dict: dict) -> tuple:
    """Extract clean endpoints from wall dict.

    Uses base_curve_start/end directly. These are already snapped to
    proper intersections by the converter's endpoint snapping step.
    framing_segments are for the framing pipeline (studs/plates),
    not for Revit wall geometry.

    Args:
        wall_dict: Wall dict (from JA output or converter).

    Returns:
        ((p1_x, p1_y), (p2_x, p2_y)) tuple of clean endpoint coordinates.
    """
    start = wall_dict.get("base_curve_start", {})
    end = wall_dict.get("base_curve_end", {})
    return (
        (float(start.get("x", 0.0)), float(start.get("y", 0.0))),
        (float(end.get("x", 0.0)), float(end.get("y", 0.0))),
    )


def _wall_dicts_to_converted(wall_dicts: list) -> list:
    """Convert JA wall dicts to ConvertedWall objects for Revit creation.

    Computes clean endpoints from framing_segments and builds ConvertedWall
    objects that revit_create_walls() can consume.

    Args:
        wall_dicts: List of wall dicts from JA output.

    Returns:
        List of (ConvertedWall, clean_p1, clean_p2) tuples.
    """
    results = []

    for i, wd in enumerate(wall_dicts):
        p1, p2 = _get_clean_endpoints(wd)

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length_ft = math.sqrt(dx * dx + dy * dy)

        if length_ft < 0.01:
            log_warning(f"  Skipping degenerate wall {wd.get('wall_id', i)}")
            continue

        thickness_ft = float(wd.get("wall_thickness", 0.2917))
        thickness_m = float(wd.get("thickness_m", thickness_ft / METERS_TO_FEET))

        cw = ConvertedWall(
            p1=ConvertedPoint(x=p1[0], y=p1[1]),
            p2=ConvertedPoint(x=p2[0], y=p2[1]),
            length_ft=length_ft,
            thickness_ft=thickness_ft,
            thickness_m=thickness_m,
            original_index=i,
        )
        results.append((cw, p1, p2))

    return results


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for Kreo wall creator.

    Returns:
        tuple: (walls_result_json, info)
    """
    setup_component()

    walls_result_json = ""
    info = "Idle (run=False)"

    try:
        # Read inputs by index
        walls_json_raw = _read_input(0)
        metadata_json_raw = _read_input(1)
        config_raw = _read_input(2)
        run_raw = _read_input(3, False)

        # Check run flag
        run = False
        if isinstance(run_raw, bool):
            run = run_raw
        elif isinstance(run_raw, str):
            run = run_raw.strip().lower() in ("true", "1", "yes")
        elif run_raw is not None:
            run = bool(run_raw)

        if not run:
            log_info("Idle (run=False)")
            return walls_result_json, info

        # Validate walls_json (required)
        if walls_json_raw is None or not str(walls_json_raw).strip():
            error = "No walls_json provided"
            log_error(error)
            walls_result_json = json.dumps({"status": "error", "message": error})
            return walls_result_json, error

        # Validate metadata_json (required)
        if metadata_json_raw is None or not str(metadata_json_raw).strip():
            error = "No metadata_json provided"
            log_error(error)
            walls_result_json = json.dumps({"status": "error", "message": error})
            return walls_result_json, error

        # ---------------------------------------------------------------
        # Step 1: Parse inputs
        # ---------------------------------------------------------------
        log_info("Parsing JA-enriched walls_json...")
        walls_json_str = str(walls_json_raw).strip()
        wall_dicts = _parse_walls_json(walls_json_str)
        log_info(f"  Parsed {len(wall_dicts)} wall dicts")

        # Count walls with framing_segments
        ja_count = sum(
            1 for wd in wall_dicts if wd.get("framing_segments")
        )
        log_info(f"  Walls with framing_segments: {ja_count}/{len(wall_dicts)}")

        # Parse metadata
        metadata_str = str(metadata_json_raw).strip()
        metadata = json.loads(metadata_str)
        scale_m_per_px = float(metadata.get("scale_m_per_px", 0.0))
        max_y_px = float(metadata.get("max_y_px", 0.0))
        classification = metadata.get("classification", {})
        log_info(f"  Scale: {scale_m_per_px:.6f} m/px, Max Y: {max_y_px:.1f} px")

        # Parse config (direct input overrides metadata.config)
        config = {}
        metadata_config = metadata.get("config", {})
        if isinstance(metadata_config, dict):
            config.update(metadata_config)
        direct_config = _parse_config(config_raw)
        if direct_config:
            config.update(direct_config)

        wall_height_ft = float(config.get("wall_height_ft", DEFAULT_WALL_HEIGHT_FT))
        level_name = config.get("level_name", None)

        # ---------------------------------------------------------------
        # Step 2: Build ConvertedWall objects with clean endpoints
        # ---------------------------------------------------------------
        log_info("Computing clean endpoints from framing_segments...")
        wall_entries = _wall_dicts_to_converted(wall_dicts)
        log_info(f"  {len(wall_entries)} walls ready for Revit creation")

        converted_walls = [entry[0] for entry in wall_entries]

        # ---------------------------------------------------------------
        # Step 3: Get Revit document and level
        # ---------------------------------------------------------------
        doc = _get_revit_doc()
        level = find_level(doc, level_name)
        if level is None:
            error = "No levels found in Revit document"
            log_error(error)
            walls_result_json = json.dumps({"status": "error", "message": error})
            return walls_result_json, error
        log_info(f"  Using level: {level.Name} (elevation: {level.Elevation:.2f} ft)")

        # ---------------------------------------------------------------
        # Step 4: Create walls in Revit
        # ---------------------------------------------------------------
        log_info(f"Creating {len(converted_walls)} walls (height={wall_height_ft} ft)...")
        created_walls = revit_create_walls(
            doc, converted_walls, level, wall_height_ft)
        log_info(f"  Created {len(created_walls)} walls in Revit")

        # ---------------------------------------------------------------
        # Step 5: Build walls_result_json with clean endpoints
        # ---------------------------------------------------------------
        wall_ids = []
        walls_ft = []
        for idx, wall_obj in created_walls:
            wall_ids.append(_element_id_int(wall_obj.Id))
            # Find the ConvertedWall by original_index
            cw = next(
                (w for w in converted_walls if w.original_index == idx),
                None,
            )
            if cw is not None:
                walls_ft.append({
                    "p1_x": round(cw.p1.x, 4),
                    "p1_y": round(cw.p1.y, 4),
                    "p2_x": round(cw.p2.x, 4),
                    "p2_y": round(cw.p2.y, 4),
                })

        result = {
            "status": "success",
            "walls_created": len(created_walls),
            "wall_ids": wall_ids,
            "walls_ft": walls_ft,
            "scale_m_per_px": scale_m_per_px,
            "max_y_px": max_y_px,
            "wall_height_ft": wall_height_ft,
            "level_name": level.Name,
            "classification": classification,
            "ja_enriched": ja_count,
        }
        walls_result_json = json.dumps(result, indent=2)

        info_lines = [
            "Kreo Create Walls: SUCCESS",
            f"  Walls: {len(created_walls)} created ({classification})",
            f"  JA-enriched: {ja_count}/{len(wall_dicts)}",
            f"  Level: {level.Name}",
            f"  Scale: {scale_m_per_px:.6f} m/px",
        ]
        info = "\n".join(info_lines)
        log_info(info)

        return walls_result_json, info

    except Exception as e:
        error_msg = f"Error in Kreo Create Walls: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        result = {"status": "error", "message": error_msg}
        walls_result_json = json.dumps(result, indent=2)
        return walls_result_json, error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    walls_result_json, info = main()
