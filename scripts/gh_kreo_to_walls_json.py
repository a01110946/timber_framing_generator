# File: scripts/gh_kreo_to_walls_json.py
"""Kreo to Walls JSON Converter for Grasshopper.

Converts Kreo AI detection wall JSON into Junction Analyzer-compatible
walls_json format. This is the first step in the Kreo-to-Revit pipeline
when using the Junction Analyzer for clean wall intersections.

Key Features:
1. Kreo JSON Parsing
   - Reads filtered Kreo wall JSON via kreo_parser
   - Handles both raw API and filtered formats

2. Coordinate Conversion
   - Derives meters-per-pixel scale from wall data
   - Flips Y-axis (top-left origin to bottom-left)
   - Converts to Revit internal units (feet)

3. JA-Compatible Output
   - Builds wall dicts with base_plane, base_curve_start/end
   - Computes x_axis (wall direction) and z_axis (left normal)
   - Classifies walls as exterior/interior by thickness

4. Metadata Output
   - Outputs scale, max_y, classification for downstream use
   - Bypasses Junction Analyzer (metadata is not modified by JA)

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and parameter access
    - src.constructai_demo: Parsing, conversion, classification

Performance Considerations:
    - Single pass through wall list
    - No Revit API calls (pure data transformation)

Usage:
    1. Connect filtered Kreo walls JSON to input 0
    2. Optionally connect config JSON to input 1
    3. Wire output 1 (walls_json_out) to Junction Analyzer walls_json input
    4. Wire output 2 (ja_config_json) to Junction Analyzer config_json input
    5. Wire output 3 (metadata_json) to Kreo Create Walls metadata input
    6. Monitor output 4 (info) for status

Input Requirements:
    Walls JSON (walls_json) - str:
        Filtered Kreo JSON with walls. Format:
        {"status": "Ready", "lines": [{"p1": [x,y], "p2": [x,y],
         "length": m, "thickness": m}, ...]}
        Required: Yes
        Access: Item
        Type Hint: str (set via GH UI)

    Config JSON (config_json) - str:
        Optional config: {"wall_height_ft": 8.0, "level_name": "Level 1"}
        Passed through in metadata_json for downstream use.
        Required: No
        Access: Item
        Type Hint: str (set via GH UI)

Outputs:
    Walls JSON (walls_json_out) - str:
        Junction Analyzer-compatible JSON: {"walls": [{wall_id, wall_length,
        wall_thickness, base_plane, base_curve_start, base_curve_end,
        is_exterior, is_flipped, thickness_m}, ...]}

    JA Config JSON (ja_config_json) - str:
        Junction Analyzer config with Kreo-appropriate tolerances.
        Wire directly to JA config_json input. Kreo AI detection has
        approximate endpoints (~6-12 inches gaps), so tolerances are
        higher than the JA defaults (0.1 ft / 0.15 ft).

    Metadata JSON (metadata_json) - str:
        JSON with scale_m_per_px, max_y_px, classification, config.
        Bypasses JA and goes directly to Kreo Create Walls.

    Info (info) - str:
        Human-readable status message.

Technical Details:
    - Reads inputs by parameter index (not NickName globals)
    - Guards setup_component() property changes
    - Uses constructai_demo package for parsing/conversion
    - z_axis = left normal (perpendicular, CCW rotation of x_axis)
    - No Revit API interaction (safe to run without RiR)

Error Handling:
    - Missing walls_json: empty outputs, status message
    - Invalid JSON: error with parse details
    - Degenerate walls (zero length): skipped with warning
    - Empty wall list: warning in info

Author: ConstructAI Demo
Version: 1.0.0
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
from src.constructai_demo.kreo_parser import parse_walls
from src.constructai_demo.coordinate_converter import (
    compute_scale,
    find_max_y,
    convert_point,
    METERS_TO_FEET,
)
from src.constructai_demo.wall_classifier import classify_wall, WallClass

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Kreo to Walls JSON"
COMPONENT_NICKNAME = "KreoToJA"
COMPONENT_MESSAGE = "v1.2"
COMPONENT_CATEGORY = "ConstructAI"
COMPONENT_SUBCATEGORY = "0-Demo"

# Kreo AI detection has approximate wall endpoints — gaps of ~6-12 inches
# are typical. These tolerances are much higher than the JA defaults
# (0.1 ft / 0.15 ft) to catch the imprecise intersections.
KREO_SNAP_TOLERANCE_FT = 1.0        # 12 inches for endpoint snapping
KREO_JA_TOLERANCE_FT = 0.5          # 6 inches for JA L-corners (post-snap)
KREO_JA_T_TOLERANCE_FT = 1.0        # 12 inches for JA T-intersections

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
         "Filtered Kreo JSON with wall line segments",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config JSON", "config_json",
         "Optional config: wall_height_ft, level_name (passed through)",
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
        ("Walls JSON", "walls_json_out",
         "Junction Analyzer-compatible walls JSON"),
        ("JA Config JSON", "ja_config_json",
         "JA config with Kreo-appropriate tolerances (wire to JA config_json)"),
        ("Metadata JSON", "metadata_json",
         "Scale, max_y, classification for downstream"),
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


# =============================================================================
# Endpoint Snapping
# =============================================================================

def _line_line_intersection(
    ax: float, ay: float, adx: float, ady: float,
    bx: float, by: float, bdx: float, bdy: float,
) -> tuple:
    """Find intersection of two infinite lines in 2D.

    Line A: (ax, ay) + t * (adx, ady)
    Line B: (bx, by) + s * (bdx, bdy)

    Returns:
        (x, y, t, s) if lines intersect, or None if parallel.
        t = parameter along line A, s = parameter along line B.
    """
    denom = adx * bdy - ady * bdx
    if abs(denom) < 1e-10:
        return None  # Parallel or coincident

    dx = bx - ax
    dy = by - ay
    t = (dx * bdy - dy * bdx) / denom
    s = (dx * ady - dy * adx) / denom

    ix = ax + t * adx
    iy = ay + t * ady
    return (ix, iy, t, s)


def _point_to_line_closest(
    px: float, py: float,
    lx: float, ly: float, ldx: float, ldy: float,
) -> tuple:
    """Find closest point on infinite line to a point.

    Returns:
        (closest_x, closest_y, t) where t is parameter along line.
    """
    line_len_sq = ldx * ldx + ldy * ldy
    if line_len_sq < 1e-12:
        return (lx, ly, 0.0)
    t = ((px - lx) * ldx + (py - ly) * ldy) / line_len_sq
    return (lx + t * ldx, ly + t * ldy, t)


def _would_shorten(
    starts: list, ends: list,
    wall_idx: int, is_start: bool,
    snap_x: float, snap_y: float,
    max_trim: float = 0.1,
) -> bool:
    """Check if snapping an endpoint would shorten the wall.

    Snapping should only extend walls (or make tiny adjustments).
    If the snap would shorten the wall by more than max_trim, reject it.

    Args:
        starts: Mutable list of [x, y] start points.
        ends: Mutable list of [x, y] end points.
        wall_idx: Index of the wall being snapped.
        is_start: True if snapping the start endpoint, False for end.
        snap_x, snap_y: Proposed snap coordinates.
        max_trim: Maximum allowed shortening in feet (default 0.1 = ~1 inch).

    Returns:
        True if the snap would shorten the wall beyond max_trim.
    """
    s = starts[wall_idx]
    e = ends[wall_idx]
    old_dx = e[0] - s[0]
    old_dy = e[1] - s[1]
    old_len = math.sqrt(old_dx * old_dx + old_dy * old_dy)

    if is_start:
        new_dx = e[0] - snap_x
        new_dy = e[1] - snap_y
    else:
        new_dx = snap_x - s[0]
        new_dy = snap_y - s[1]

    new_len = math.sqrt(new_dx * new_dx + new_dy * new_dy)
    return new_len < old_len - max_trim


def _project_onto_wall(
    px: float, py: float,
    orig_start: list, direction: list,
) -> tuple:
    """Project a point onto a wall's original centerline.

    Ensures snap points only move endpoints along the wall direction,
    never perpendicular (which would make walls crooked).

    Args:
        px, py: Point to project.
        orig_start: Original wall start [x, y] (never modified).
        direction: Wall direction [dx, dy] (normalized).

    Returns:
        (proj_x, proj_y) on the wall's centerline.
    """
    t = (px - orig_start[0]) * direction[0] + (py - orig_start[1]) * direction[1]
    return (
        orig_start[0] + t * direction[0],
        orig_start[1] + t * direction[1],
    )


def _snap_endpoints(wall_dicts: list, tolerance: float) -> tuple:
    """Snap wall endpoints to form clean intersections.

    For each wall endpoint, checks if it's near another wall's endpoint
    (L-corner) or body (T-intersection). If so, computes the geometric
    intersection and snaps the endpoint there.

    Safety: never shortens a wall by more than 0.1 ft (~1 inch). This
    prevents the T-intersection pass from pulling endpoints back when
    walls already extend past a neighbor.

    Updates base_curve_start/end, base_plane.origin, x_axis, z_axis,
    and wall_length for affected walls.

    Args:
        wall_dicts: List of wall dicts (modified in place).
        tolerance: Max distance in feet for endpoint snapping.

    Returns:
        (l_snaps, t_snaps) counts of L-corner and T-intersection snaps.
    """
    n = len(wall_dicts)
    l_snaps = 0
    t_snaps = 0

    # Extract mutable endpoint arrays for fast access
    starts = []
    ends = []
    dirs = []
    for wd in wall_dicts:
        s = wd["base_curve_start"]
        e = wd["base_curve_end"]
        starts.append([float(s["x"]), float(s["y"])])
        ends.append([float(e["x"]), float(e["y"])])
        xa = wd["base_plane"]["x_axis"]
        dirs.append([float(xa["x"]), float(xa["y"])])

    # Original centerline origins — never modified. Used to project snap
    # points back onto the wall's line so walls stay straight.
    orig_starts = [[s[0], s[1]] for s in starts]

    # Track which endpoints have been snapped (to avoid double-snapping)
    snapped_start = [False] * n
    snapped_end = [False] * n

    # --- Pass 1: L-corners (endpoint-to-endpoint) ---
    for i in range(n):
        for j in range(i + 1, n):
            # Check all 4 endpoint pair combos
            pairs = [
                (ends[i], "end_i", starts[j], "start_j"),
                (ends[i], "end_i", ends[j], "end_j"),
                (starts[i], "start_i", starts[j], "start_j"),
                (starts[i], "start_i", ends[j], "end_j"),
            ]
            for pt_a, label_a, pt_b, label_b in pairs:
                dx = pt_a[0] - pt_b[0]
                dy = pt_a[1] - pt_b[1]
                dist = math.sqrt(dx * dx + dy * dy)
                # Use tolerance * 1.5 for endpoint pairs -- at 90-degree
                # corners the diagonal gap is sqrt(2) * individual gap
                if dist > tolerance * 1.5 or dist < 1e-6:
                    continue

                # Skip if both already snapped
                a_is_start = "start" in label_a
                b_is_start = "start" in label_b
                if a_is_start and snapped_start[i]:
                    continue
                if not a_is_start and snapped_end[i]:
                    continue
                if b_is_start and snapped_start[j]:
                    continue
                if not b_is_start and snapped_end[j]:
                    continue

                # Compute line-line intersection
                result = _line_line_intersection(
                    starts[i][0], starts[i][1], dirs[i][0], dirs[i][1],
                    starts[j][0], starts[j][1], dirs[j][0], dirs[j][1],
                )
                if result is None:
                    # Parallel walls - use midpoint as fallback
                    ix = (pt_a[0] + pt_b[0]) / 2.0
                    iy = (pt_a[1] + pt_b[1]) / 2.0
                else:
                    ix, iy = result[0], result[1]

                # Verify intersection is close to both endpoints
                da = math.sqrt((ix - pt_a[0])**2 + (iy - pt_a[1])**2)
                db = math.sqrt((ix - pt_b[0])**2 + (iy - pt_b[1])**2)
                if da > tolerance * 2.0 or db > tolerance * 2.0:
                    continue

                # Project onto each wall's original centerline to stay straight
                pi_x, pi_y = _project_onto_wall(
                    ix, iy, orig_starts[i], dirs[i])
                pj_x, pj_y = _project_onto_wall(
                    ix, iy, orig_starts[j], dirs[j])

                # Guard: don't shorten either wall
                if _would_shorten(starts, ends, i, a_is_start, pi_x, pi_y):
                    continue
                if _would_shorten(starts, ends, j, b_is_start, pj_x, pj_y):
                    continue

                # Snap both endpoints (projected onto their own centerlines)
                if a_is_start:
                    starts[i] = [pi_x, pi_y]
                    snapped_start[i] = True
                else:
                    ends[i] = [pi_x, pi_y]
                    snapped_end[i] = True

                if b_is_start:
                    starts[j] = [pj_x, pj_y]
                    snapped_start[j] = True
                else:
                    ends[j] = [pj_x, pj_y]
                    snapped_end[j] = True

                l_snaps += 1

    # --- Pass 2: T-intersections (endpoint-to-body) ---
    for i in range(n):
        for end_label in ("start", "end"):
            if end_label == "start" and snapped_start[i]:
                continue
            if end_label == "end" and snapped_end[i]:
                continue

            pt = starts[i] if end_label == "start" else ends[i]

            best_dist = tolerance
            best_point = None
            best_j = -1

            for j in range(n):
                if i == j:
                    continue
                # Project pt onto wall j's centerline
                cx, cy, t = _point_to_line_closest(
                    pt[0], pt[1],
                    starts[j][0], starts[j][1],
                    dirs[j][0], dirs[j][1],
                )
                # t should be within wall j's length (not just near endpoints)
                wl_j = float(wall_dicts[j]["wall_length"])
                if t < -0.1 or t > wl_j + 0.1:
                    continue
                dist = math.sqrt((pt[0] - cx)**2 + (pt[1] - cy)**2)
                if dist < best_dist:
                    best_dist = dist
                    best_point = (cx, cy)
                    best_j = j

            if best_point is not None:
                is_start = (end_label == "start")
                # Project onto wall's own centerline to stay straight
                proj_x, proj_y = _project_onto_wall(
                    best_point[0], best_point[1],
                    orig_starts[i], dirs[i])

                # Guard: don't shorten the wall
                if _would_shorten(starts, ends, i, is_start,
                                  proj_x, proj_y):
                    continue

                if is_start:
                    starts[i] = [proj_x, proj_y]
                    snapped_start[i] = True
                else:
                    ends[i] = [proj_x, proj_y]
                    snapped_end[i] = True
                t_snaps += 1

    # --- Apply snapped endpoints back to wall dicts ---
    for i, wd in enumerate(wall_dicts):
        p1x, p1y = starts[i]
        p2x, p2y = ends[i]

        dx = p2x - p1x
        dy = p2y - p1y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            continue

        nx = dx / length
        ny = dy / length
        perp_x = -ny
        perp_y = nx

        wd["wall_length"] = round(length, 6)
        wd["base_curve_start"] = {"x": round(p1x, 6), "y": round(p1y, 6), "z": 0.0}
        wd["base_curve_end"] = {"x": round(p2x, 6), "y": round(p2y, 6), "z": 0.0}
        wd["base_plane"]["origin"] = {"x": round(p1x, 6), "y": round(p1y, 6), "z": 0.0}
        wd["base_plane"]["x_axis"] = {"x": round(nx, 6), "y": round(ny, 6), "z": 0.0}
        wd["base_plane"]["z_axis"] = {"x": round(perp_x, 6), "y": round(perp_y, 6), "z": 0.0}

    return l_snaps, t_snaps


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for Kreo to Walls JSON converter.

    Returns:
        tuple: (walls_json_out, ja_config_json, metadata_json, info)
    """
    setup_component()

    walls_json_out = ""
    ja_config_json = ""
    metadata_json = ""
    info = "No input"

    try:
        # Read inputs by index
        walls_json_raw = _read_input(0)
        config_raw = _read_input(1)

        # Validate walls_json (required)
        if walls_json_raw is None or not str(walls_json_raw).strip():
            return walls_json_out, ja_config_json, metadata_json, info

        # Parse config (passed through to metadata)
        config = _parse_config(config_raw)

        # ---------------------------------------------------------------
        # Step 1: Parse Kreo JSON
        # ---------------------------------------------------------------
        log_info("Parsing Kreo walls JSON...")
        walls_json_str = str(walls_json_raw).strip()
        kreo_walls = parse_walls(walls_json_str)
        log_info(f"  Parsed {len(kreo_walls)} walls")

        if not kreo_walls:
            info = "No walls in Kreo JSON"
            log_warning(info)
            return walls_json_out, ja_config_json, metadata_json, info

        # ---------------------------------------------------------------
        # Step 2: Compute scale and max_y
        # ---------------------------------------------------------------
        scale = compute_scale(kreo_walls)
        max_y = find_max_y(kreo_walls)
        log_info(f"  Scale: {scale:.6f} m/px, Max Y: {max_y:.1f} px")

        # ---------------------------------------------------------------
        # Step 3: Convert each wall to JA-compatible format
        # ---------------------------------------------------------------
        wall_dicts = []
        classification_counts = {}
        skipped = 0

        for i, kw in enumerate(kreo_walls):
            # Convert pixel -> feet
            p1_ft = convert_point(kw.p1.x, kw.p1.y, scale, max_y)
            p2_ft = convert_point(kw.p2.x, kw.p2.y, scale, max_y)

            # Compute direction vector
            dx = p2_ft.x - p1_ft.x
            dy = p2_ft.y - p1_ft.y
            length = math.sqrt(dx * dx + dy * dy)

            if length < 1e-6:
                log_warning(f"  Skipping degenerate wall {i} (zero length)")
                skipped += 1
                continue

            # Normalize direction (x_axis)
            nx = dx / length
            ny = dy / length

            # Perpendicular left normal (z_axis): rotate x_axis 90 CCW
            perp_x = -ny
            perp_y = nx

            # Determine exterior/interior: use explicit flag if present,
            # otherwise fall back to thickness-based classification
            wall_class = classify_wall(kw.thickness)
            if kw.is_exterior is not None:
                is_exterior = kw.is_exterior
            else:
                is_exterior = wall_class in (WallClass.EXTERIOR_2X4, WallClass.EXTERIOR_2X6)

            key = wall_class.value
            classification_counts[key] = classification_counts.get(key, 0) + 1

            thickness_ft = kw.thickness * METERS_TO_FEET

            wall_dict = {
                "wall_id": f"kreo_{i}",
                "wall_length": round(length, 6),
                "wall_thickness": round(thickness_ft, 6),
                "base_plane": {
                    "origin": {
                        "x": round(p1_ft.x, 6),
                        "y": round(p1_ft.y, 6),
                        "z": 0.0,
                    },
                    "x_axis": {
                        "x": round(nx, 6),
                        "y": round(ny, 6),
                        "z": 0.0,
                    },
                    "z_axis": {
                        "x": round(perp_x, 6),
                        "y": round(perp_y, 6),
                        "z": 0.0,
                    },
                },
                "base_curve_start": {
                    "x": round(p1_ft.x, 6),
                    "y": round(p1_ft.y, 6),
                    "z": 0.0,
                },
                "base_curve_end": {
                    "x": round(p2_ft.x, 6),
                    "y": round(p2_ft.y, 6),
                    "z": 0.0,
                },
                "is_exterior": is_exterior,
                "is_flipped": False,
                "thickness_m": kw.thickness,
            }
            wall_dicts.append(wall_dict)

        # ---------------------------------------------------------------
        # Step 3.5: Snap endpoints so walls meet at intersections
        # ---------------------------------------------------------------
        log_info("Snapping wall endpoints...")
        l_snaps, t_snaps = _snap_endpoints(wall_dicts, KREO_SNAP_TOLERANCE_FT)
        log_info(f"  Snapped: {l_snaps} L-corners, {t_snaps} T-intersections")

        # ---------------------------------------------------------------
        # Step 4: Build outputs
        # ---------------------------------------------------------------
        walls_json_out = json.dumps({"walls": wall_dicts}, indent=2)

        # JA config with Kreo-appropriate tolerances
        ja_config = {
            "tolerance": KREO_JA_TOLERANCE_FT,
            "t_intersection_tolerance": KREO_JA_T_TOLERANCE_FT,
        }
        ja_config_json = json.dumps(ja_config, indent=2)

        metadata = {
            "scale_m_per_px": scale,
            "max_y_px": max_y,
            "classification": classification_counts,
        }
        if config:
            metadata["config"] = config
        metadata_json = json.dumps(metadata, indent=2)

        info_lines = [
            f"Kreo -> JA: {len(wall_dicts)} walls converted",
            f"  Scale: {scale:.6f} m/px",
            f"  Classification: {classification_counts}",
            f"  Snapped (tol={KREO_SNAP_TOLERANCE_FT} ft): {l_snaps} L-corners, {t_snaps} T-intersections",
            f"  JA tolerances: L={KREO_JA_TOLERANCE_FT} ft, T={KREO_JA_T_TOLERANCE_FT} ft",
        ]
        if skipped > 0:
            info_lines.append(f"  Skipped: {skipped} degenerate walls")
        info = "\n".join(info_lines)
        log_info(info)

        return walls_json_out, ja_config_json, metadata_json, info

    except Exception as e:
        error_msg = f"Error in Kreo to Walls JSON: {str(e)}"
        log_error(error_msg)
        print(traceback.format_exc())
        return walls_json_out, ja_config_json, metadata_json, error_msg


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    walls_json_out, ja_config_json, metadata_json, info = main()
