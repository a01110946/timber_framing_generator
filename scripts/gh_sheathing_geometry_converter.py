# File: scripts/gh_sheathing_geometry_converter.py
"""Sheathing Geometry Converter for Grasshopper.

Converts sheathing JSON data to RhinoCommon geometry (Breps). This component
is the final stage of the sheathing pipeline, transforming panel definitions
with UVW coordinates into 3D geometry using the wall's base plane.

Supports both single-layer sheathing (from Sheathing Generator) and
multi-layer assemblies (from Multi-Layer Sheathing Generator). Multi-layer
JSON is automatically flattened so all layer panels are converted uniformly.

Key Features:
1. Assembly-Safe Geometry Creation
   - Uses RhinoCommonFactory for correct RhinoCommon assembly
   - Avoids Rhino3dmIO/RhinoCommon mismatch issues
   - Geometry verified for Grasshopper compatibility

2. Wall-Aware Panel Placement
   - Uses wall base_plane for UVW to world coordinate transformation
   - Supports both exterior and interior face placement
   - Handles panels with opening cutouts (boolean difference)

3. Multi-Layer Support
   - Accepts multi_layer_json from Multi-Layer Sheathing Generator
   - Automatically flattens layer_results into single panel list per wall
   - Preserves layer_name and w_offset metadata on each panel

4. Flexible Filtering and Organization
   - Filter by wall ID for single-wall visualization
   - Multiple output formats (flat list, by-wall DataTree)
   - Panel IDs and summary statistics

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Rhino.Geometry: Core geometry types
    - Grasshopper: DataTree for organized output
    - timber_framing_generator.utils.geometry_factory: RhinoCommonFactory
    - timber_framing_generator.sheathing.sheathing_geometry: create_sheathing_breps

Performance Considerations:
    - Processing time scales linearly with panel count
    - Boolean difference for cutouts adds processing time
    - Large walls with many openings may take several seconds

Usage:
    1. Connect 'sheathing_json' from Sheathing Generator
    2. Connect 'walls_json' from Wall Analyzer (provides base planes)
    3. Optionally set 'filter_wall' to show only one wall's sheathing
    4. Set 'run' to True to execute
    5. Connect 'breps' to display or bake geometry

Input Requirements:
    Sheathing JSON (sheathing_json) - str:
        JSON string from Sheathing Generator or Multi-Layer Sheathing Generator.
        Accepts both single-layer and multi-layer formats.
        Required: Yes
        Access: Item

    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer with base_plane for each wall
        Required: Yes
        Access: Item

    Filter Wall (filter_wall) - str:
        Wall ID to filter (e.g., "1234567" for single wall view)
        Required: No (shows all walls)
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Breps (breps) - list[Brep]:
        All sheathing panels as Brep geometry

    By Wall (by_wall) - DataTree[Brep]:
        Breps organized by wall ID in branches

    Panel IDs (panel_ids) - list[str]:
        Panel IDs for selection feedback

    Summary (summary) - str:
        Text summary with panel counts and areas

    Debug Info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Uses RhinoCommonFactory for correct assembly
    - Panel geometry created from UVW corners and extrusion vector
    - Wall base_plane provides coordinate transformation
    - Cutouts use boolean difference operations

Error Handling:
    - Invalid JSON returns empty outputs with error in debug_info
    - Missing wall data logged but doesn't halt execution
    - Invalid geometry creation logged and skipped

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
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================

_modules_to_clear = [k for k in sys.modules.keys() if 'timber_framing_generator' in k]
for mod in _modules_to_clear:
    del sys.modules[mod]

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.utils.geometry_factory import get_factory
from src.timber_framing_generator.sheathing.sheathing_geometry import (
    create_sheathing_breps,
    create_sheathing_breps_batch,
    SheathingPanelGeometry,
)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Sheathing Geometry Converter"
COMPONENT_NICKNAME = "SheathGeo"
COMPONENT_MESSAGE = "v1.1"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "Geometry"

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message."""
    print(f"[{level.upper()}] {message}")

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)


def log_debug(message):
    """Log debug message (console only)."""
    print(f"[DEBUG] {message}")


def log_info(message):
    """Log info message (console only)."""
    print(f"[INFO] {message}")


def log_warning(message):
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message):
    """Log error message (console + GH UI)."""
    log_message(message, "error")

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component.

    Configures:
    1. Component metadata (name, category, etc.)
    2. Input parameter names, descriptions, and access
    3. Output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # NOTE: Type Hints must be set via GH UI (right-click -> Type hint)
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Sheathing JSON", "sheathing_json", "JSON string from Sheathing Generator",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls JSON", "walls_json", "JSON string from Wall Analyzer (provides base_plane)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Filter Wall", "filter_wall", "Wall ID to filter (single wall view)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run", "Boolean to trigger execution",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1)
    outputs = ghenv.Component.Params.Output
    output_config = [
        ("Breps", "breps", "All sheathing panels as Breps"),
        ("By Wall", "by_wall", "DataTree of Breps by wall ID"),
        ("Panel IDs", "panel_ids", "Panel IDs for selection"),
        ("Summary", "summary", "Panel counts and area summary"),
        ("Debug Info", "debug_info", "Debug information and status"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc

# =============================================================================
# Helper Functions
# =============================================================================

def validate_inputs(sheathing_json, walls_json, run):
    """Validate component inputs.

    Args:
        sheathing_json: JSON string with sheathing data
        walls_json: JSON string with wall data
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not sheathing_json:
        return False, "No sheathing_json input provided"

    if not walls_json:
        return False, "No walls_json input provided"

    try:
        json.loads(sheathing_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in sheathing_json: {e}"

    try:
        json.loads(walls_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in walls_json: {e}"

    return True, None


def parse_sheathing_json(sheathing_json):
    """Parse sheathing JSON, handling single-layer, multi-layer, and multi-wall formats.

    Supports three formats:
    1. Single-layer (from Sheathing Generator):
       [{"wall_id": "...", "sheathing_panels": [...]}]
    2. Multi-layer (from Multi-Layer Sheathing Generator):
       [{"wall_id": "...", "layer_results": [{"panels": [...]}]}]
    3. Single wall dict (either format)

    Multi-layer results are flattened: per-layer panels are merged into a
    single "sheathing_panels" list per wall so the geometry converter can
    process them uniformly.

    Args:
        sheathing_json: JSON string with sheathing data

    Returns:
        list: List of sheathing data dictionaries (one per wall),
              each containing "sheathing_panels" list
    """
    data = json.loads(sheathing_json)

    # Normalize to list
    if isinstance(data, dict):
        if "wall_id" in data:
            data = [data]
        elif "walls" in data and isinstance(data["walls"], list):
            data = data["walls"]
        elif "results" in data and isinstance(data["results"], list):
            data = data["results"]
        else:
            data = [data]
    elif not isinstance(data, list):
        return []

    # Check each entry for multi-layer format and flatten if needed
    result = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        # Multi-layer format: has "layer_results" instead of "sheathing_panels"
        if "layer_results" in entry and "sheathing_panels" not in entry:
            flattened = _flatten_multi_layer_entry(entry)
            result.append(flattened)
        else:
            # Standard single-layer format or already has sheathing_panels
            result.append(entry)

    return result


def _flatten_multi_layer_entry(entry):
    """Flatten multi-layer result into standard sheathing format.

    Merges panels from all layer_results into a single sheathing_panels list,
    adding layer_name and w_offset metadata to each panel dict.

    Args:
        entry: Multi-layer result dict with "layer_results" list.

    Returns:
        Dict with "wall_id" and "sheathing_panels" in standard format.
    """
    wall_id = entry.get("wall_id", "unknown")
    all_panels = []

    for layer_result in entry.get("layer_results", []):
        layer_name = layer_result.get("layer_name", "unknown")
        w_offset = layer_result.get("w_offset")

        for panel in layer_result.get("panels", []):
            # Add layer metadata to each panel for downstream use
            enriched_panel = dict(panel)
            enriched_panel["layer_name"] = layer_name
            if w_offset is not None:
                enriched_panel["layer_w_offset"] = w_offset
            all_panels.append(enriched_panel)

    log_info(
        f"Flattened multi-layer wall {wall_id}: "
        f"{len(entry.get('layer_results', []))} layers -> "
        f"{len(all_panels)} panels"
    )

    return {
        "wall_id": wall_id,
        "sheathing_panels": all_panels,
    }


def parse_walls_json(walls_json):
    """Parse walls JSON and index by wall_id.

    Args:
        walls_json: JSON string with wall data

    Returns:
        dict: Dictionary mapping wall_id to wall data
    """
    data = json.loads(walls_json)

    walls_by_id = {}

    # If it's a list of walls
    if isinstance(data, list):
        for wall in data:
            wall_id = str(wall.get("wall_id", wall.get("id", "unknown")))
            walls_by_id[wall_id] = wall
    # If it's a single wall
    elif isinstance(data, dict):
        if "wall_id" in data or "id" in data:
            wall_id = str(data.get("wall_id", data.get("id", "unknown")))
            walls_by_id[wall_id] = data
        # Check if it has a "walls" key
        elif "walls" in data and isinstance(data["walls"], list):
            for wall in data["walls"]:
                wall_id = str(wall.get("wall_id", wall.get("id", "unknown")))
                walls_by_id[wall_id] = wall

    return walls_by_id


def process_sheathing_geometry(sheathing_list, walls_by_id, wall_filter, factory):
    """Process all sheathing panels to geometry.

    Args:
        sheathing_list: List of sheathing data dictionaries
        walls_by_id: Dictionary mapping wall_id to wall data
        wall_filter: Wall ID to filter (or None for all)
        factory: RhinoCommonFactory instance

    Returns:
        tuple: (breps, wall_groups, panel_ids, stats)
    """
    breps = []
    wall_groups = {}
    panel_ids = []
    stats = {
        "total_panels": 0,
        "panels_with_cutouts": 0,
        "total_area_gross": 0.0,
        "total_area_net": 0.0,
        "walls_processed": set(),
    }

    # W offset diagnostics: track which path panels use
    w_offset_diag = {"layer_w": 0, "fallback": 0, "sample": None}

    for sheathing_data in sheathing_list:
        wall_id = str(sheathing_data.get("wall_id", "unknown"))

        # Apply wall filter
        if wall_filter and wall_id != wall_filter:
            continue

        # Get wall data for base_plane
        wall_data = walls_by_id.get(wall_id, {})

        # Skip if no base_plane available
        if "base_plane" not in wall_data:
            log_warning(f"Wall {wall_id}: No base_plane found, skipping")
            continue

        # W offset diagnostics: check first few panels for layer_w_offset
        panels = sheathing_data.get("sheathing_panels", [])
        for p in panels[:3]:
            lw = p.get("layer_w_offset")
            if lw is not None:
                w_offset_diag["layer_w"] += 1
            else:
                w_offset_diag["fallback"] += 1
            if w_offset_diag["sample"] is None:
                wall_t = wall_data.get("thickness", wall_data.get("wall_thickness", 0.5))
                has_asm = "wall_assembly" in wall_data
                w_offset_diag["sample"] = (
                    f"wall={wall_id}, panel={p.get('id','?')}, "
                    f"layer_w_offset={lw}, face={p.get('face','?')}, "
                    f"wall_thickness={wall_t}, has_assembly={has_asm}"
                )
        # Count remaining panels (beyond first 3)
        for p in panels[3:]:
            if p.get("layer_w_offset") is not None:
                w_offset_diag["layer_w"] += 1
            else:
                w_offset_diag["fallback"] += 1

        # Create geometry for this wall's panels
        geometries = create_sheathing_breps(sheathing_data, wall_data, factory)

        for geom in geometries:
            if geom.brep is not None:
                breps.append(geom.brep)
                panel_ids.append(geom.panel_id)

                # Group by wall
                if wall_id not in wall_groups:
                    wall_groups[wall_id] = []
                wall_groups[wall_id].append(geom.brep)

                # Update stats
                stats["total_panels"] += 1
                if geom.has_cutouts:
                    stats["panels_with_cutouts"] += 1
                stats["total_area_gross"] += geom.area_gross
                stats["total_area_net"] += geom.area_net
                stats["walls_processed"].add(wall_id)

    # Append W offset diagnostics to stats
    stats["w_offset_diag"] = w_offset_diag

    return breps, wall_groups, panel_ids, stats


def format_summary(stats):
    """Format summary statistics as text.

    Args:
        stats: Statistics dictionary from process_sheathing_geometry

    Returns:
        str: Formatted summary text
    """
    lines = [
        "=== Sheathing Summary ===",
        f"Total Panels: {stats['total_panels']}",
        f"Panels with Cutouts: {stats['panels_with_cutouts']}",
        f"Walls Processed: {len(stats['walls_processed'])}",
        f"",
        f"Gross Area: {stats['total_area_gross']:.1f} sq ft",
        f"Net Area: {stats['total_area_net']:.1f} sq ft",
    ]

    if stats["total_area_gross"] > 0:
        waste_pct = (1 - stats["total_area_net"] / stats["total_area_gross"]) * 100
        lines.append(f"Waste: {waste_pct:.1f}%")

    return "\n".join(lines)

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component.

    Returns:
        tuple: (breps, by_wall, panel_ids, summary, debug_info)
    """
    setup_component()

    # Initialize outputs
    breps = []
    by_wall = DataTree[object]()
    panel_ids = []
    summary = ""
    log_lines = []

    try:
        # Unwrap Grasshopper list wrappers
        sheathing_json_input = sheathing_json
        if isinstance(sheathing_json, (list, tuple)):
            sheathing_json_input = sheathing_json[0] if sheathing_json else None

        walls_json_input = walls_json
        if isinstance(walls_json, (list, tuple)):
            walls_json_input = walls_json[0] if walls_json else None

        filter_wall_input = filter_wall if filter_wall else None
        if isinstance(filter_wall, (list, tuple)):
            filter_wall_input = filter_wall[0] if filter_wall else None

        # Validate inputs
        is_valid, error_msg = validate_inputs(sheathing_json_input, walls_json_input, run)
        if not is_valid:
            if error_msg and "not running" not in error_msg.lower():
                log_warning(error_msg)
            return breps, by_wall, panel_ids, summary, error_msg

        # Get geometry factory
        factory = get_factory()

        # Parse JSON inputs
        sheathing_list = parse_sheathing_json(sheathing_json_input)
        walls_by_id = parse_walls_json(walls_json_input)

        log_lines.append(f"Sheathing Geometry Converter v1.0")
        log_lines.append(f"Sheathing entries: {len(sheathing_list)}")
        log_lines.append(f"Walls available: {len(walls_by_id)}")
        log_lines.append("")

        # Parse filter_wall
        wall_filter = str(filter_wall_input).strip() if filter_wall_input else None
        if wall_filter:
            log_lines.append(f"Wall Filter: {wall_filter}")

        # Process geometry
        breps, wall_groups, panel_ids, stats = process_sheathing_geometry(
            sheathing_list, walls_by_id, wall_filter, factory
        )

        # Build by_wall DataTree
        sorted_walls = sorted(wall_groups.keys())
        for branch_idx, wall_id_key in enumerate(sorted_walls):
            path = GH_Path(branch_idx)
            for brep in wall_groups[wall_id_key]:
                by_wall.Add(brep, path)

        # Create summary
        summary = format_summary(stats)

        # Debug info
        log_lines.append("")
        log_lines.append(f"Walls Processed: {len(stats['walls_processed'])}")
        log_lines.append(f"Wall IDs: {sorted(stats['walls_processed'])}")
        log_lines.append("")
        log_lines.append(f"Total Breps: {len(breps)}")
        log_lines.append(f"Panels with Cutouts: {stats['panels_with_cutouts']}")

        # W offset diagnostics
        w_diag = stats.get("w_offset_diag", {})
        log_lines.append("")
        log_lines.append("=== W Offset Diagnostics ===")
        log_lines.append(
            f"Panels with layer_w_offset: {w_diag.get('layer_w', 0)}"
        )
        log_lines.append(
            f"Panels using fallback: {w_diag.get('fallback', 0)}"
        )
        if w_diag.get("sample"):
            log_lines.append(f"Sample: {w_diag['sample']}")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_lines.append(f"ERROR: {str(e)}")
        log_lines.append(traceback.format_exc())

    return breps, by_wall, panel_ids, summary, "\n".join(log_lines)

# =============================================================================
# Execution
# =============================================================================

# Set default values for optional inputs
try:
    sheathing_json
except NameError:
    sheathing_json = None

try:
    walls_json
except NameError:
    walls_json = None

try:
    filter_wall
except NameError:
    filter_wall = None

try:
    run
except NameError:
    run = False

# Execute main
if __name__ == "__main__":
    breps, by_wall, panel_ids, summary, debug_info = main()
