# File: src/timber_framing_generator/cavity/cavity_decomposer.py
"""
Cavity decomposer for wall framing.

Computes rectangular voids (cavities) between framing members in a wall.
Supports two modes:

1. **Framing mode**: Uses actual framing element positions from framing_json.
   Produces exact cavity boundaries matching real stud/plate/header placement.

2. **Derived mode**: Computes cavity positions from wall geometry and configured
   stud spacing. Used when framing data is not yet available.

Algorithm (framing mode):
    For each cell (SC, SCC, HCC):
    1. Filter framing elements to those intersecting the cell's UV bounds
    2. Classify into vertical_members and horizontal_members
    3. Extract vertical boundary edges sorted by U
    4. For each adjacent pair of vertical boundaries (column strip):
       a. Collect horizontal members overlapping the strip
       b. Add cell v_min/v_max as bottom/top boundaries
       c. Sort horizontal boundaries by V
       d. For each adjacent pair of horizontal boundaries -> one Cavity
    5. Filter: skip cavities below min_clear_width or min_clear_height
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple, Any

from .cavity import Cavity, CavityConfig, serialize_cavities, deserialize_cavities

logger = logging.getLogger(__name__)

# Element types classified as vertical members (create left/right cavity bounds)
VERTICAL_MEMBER_TYPES = {
    "stud", "king_stud", "trimmer",
    "header_cripple", "sill_cripple",
}

# Element types classified as horizontal members (create top/bottom cavity bounds)
HORIZONTAL_MEMBER_TYPES = {
    "bottom_plate", "top_plate",
    "bottom_track", "top_track",
    "header", "sill",
    "row_blocking",
}


def decompose_wall_cavities(
    wall_data: Dict[str, Any],
    cell_data: Optional[Dict[str, Any]] = None,
    framing_data: Optional[Dict[str, Any]] = None,
    config: Optional[CavityConfig] = None,
) -> List[Cavity]:
    """Decompose a wall into rectangular cavities.

    Dispatches to framing mode (if framing_data provided) or derived mode.

    Args:
        wall_data: Wall data dict with wall_id, wall_length, wall_height,
            wall_thickness, openings.
        cell_data: Optional cell decomposition dict with cells list.
            Each cell has id, cell_type, u_start, u_end, v_start, v_end.
        framing_data: Optional framing results dict with elements list.
            Each element has element_type, u_coord, v_start, v_end,
            profile.width, cell_id.
        config: Cavity decomposition configuration.

    Returns:
        List of Cavity objects sorted by (u_min, v_min).
    """
    config = config or CavityConfig()
    wall_id = wall_data.get("wall_id", "wall_0")
    wall_length = float(wall_data.get("wall_length", 10.0))
    wall_height = float(wall_data.get("wall_height", 8.0))
    wall_thickness = float(wall_data.get("wall_thickness", 0.292))

    if framing_data and cell_data:
        logger.info(
            "Cavity decomposition: framing mode for %s", wall_id
        )
        cavities = _decompose_from_framing(
            wall_id, wall_length, wall_height, wall_thickness,
            cell_data, framing_data, config
        )
    else:
        logger.info(
            "Cavity decomposition: derived mode for %s", wall_id
        )
        cavities = _decompose_derived(
            wall_id, wall_length, wall_height, wall_thickness,
            wall_data.get("openings", []), config
        )

    logger.info(
        "Wall %s: %d cavities produced", wall_id, len(cavities)
    )
    return cavities


# ---------------------------------------------------------------------------
# Framing mode
# ---------------------------------------------------------------------------

def _decompose_from_framing(
    wall_id: str,
    wall_length: float,
    wall_height: float,
    wall_thickness: float,
    cell_data: Dict[str, Any],
    framing_data: Dict[str, Any],
    config: CavityConfig,
) -> List[Cavity]:
    """Decompose cavities from actual framing element positions."""
    cells = cell_data.get("cells", [])
    elements = framing_data.get("elements", [])
    cavities: List[Cavity] = []
    cavity_index = 0

    for cell in cells:
        cell_type = cell.get("cell_type", "")
        # Only decompose SC, SCC, and HCC cells into cavities
        if cell_type not in ("SC", "SCC", "HCC"):
            continue

        cell_id = cell.get("id", "unknown")
        cell_u_min = float(cell.get("u_start", 0))
        cell_u_max = float(cell.get("u_end", wall_length))
        cell_v_min = float(cell.get("v_start", 0))
        cell_v_max = float(cell.get("v_end", wall_height))

        # Filter elements that belong to or overlap this cell
        cell_elements = _filter_elements_for_cell(
            elements, cell_id, cell_u_min, cell_u_max,
            cell_v_min, cell_v_max, config.tolerance
        )

        cell_cavities = _decompose_cell_from_framing(
            wall_id, cell_id, cell_type,
            cell_u_min, cell_u_max, cell_v_min, cell_v_max,
            wall_thickness, cell_elements, config, cavity_index
        )
        cavity_index += len(cell_cavities)
        cavities.extend(cell_cavities)

    cavities.sort(key=lambda c: (c.u_min, c.v_min))
    return cavities


def _filter_elements_for_cell(
    elements: List[Dict[str, Any]],
    cell_id: str,
    cell_u_min: float,
    cell_u_max: float,
    cell_v_min: float,
    cell_v_max: float,
    tolerance: float,
) -> List[Dict[str, Any]]:
    """Filter framing elements to those relevant to a cell.

    Matches by cell_id first, then falls back to geometric overlap.
    """
    matched = []
    for elem in elements:
        # Match by cell_id if available
        if elem.get("cell_id") == cell_id:
            matched.append(elem)
            continue

        # Geometric overlap check
        u = float(elem.get("u_coord", 0))
        v_start = float(elem.get("v_start", 0))
        v_end = float(elem.get("v_end", 0))
        width = float(elem.get("profile", {}).get("width", 0.125))
        half_w = width / 2.0

        elem_u_min = u - half_w
        elem_u_max = u + half_w

        # Check U overlap
        u_overlaps = (
            elem_u_max > cell_u_min - tolerance
            and elem_u_min < cell_u_max + tolerance
        )
        # Check V overlap
        v_overlaps = (
            v_end > cell_v_min - tolerance
            and v_start < cell_v_max + tolerance
        )
        if u_overlaps and v_overlaps:
            matched.append(elem)

    return matched


def _decompose_cell_from_framing(
    wall_id: str,
    cell_id: str,
    cell_type: str,
    cell_u_min: float,
    cell_u_max: float,
    cell_v_min: float,
    cell_v_max: float,
    wall_thickness: float,
    elements: List[Dict[str, Any]],
    config: CavityConfig,
    start_index: int,
) -> List[Cavity]:
    """Decompose a single cell into cavities using framing elements.

    Algorithm:
    1. Collect vertical boundary edges (stud inside faces) sorted by U
    2. For each adjacent pair of vertical edges (column strip):
       a. Collect horizontal members within the strip
       b. Add cell v_min/v_max as outer boundaries
       c. Sort by V and create cavities between each adjacent pair
    """
    tol = config.tolerance

    # --- Collect vertical boundary edges ---
    # Each entry: (u_position, member_type, side)
    # "side" is "left" (right face of member) or "right" (left face of member)
    vertical_edges: List[Tuple[float, str, float, float]] = []
    # Also: (u_edge, member_type, v_start, v_end)

    for elem in elements:
        etype = elem.get("element_type", "")
        if etype not in VERTICAL_MEMBER_TYPES:
            continue

        u = float(elem.get("u_coord", 0))
        width = float(elem.get("profile", {}).get("width", 0.125))
        half_w = width / 2.0
        v_start = float(elem.get("v_start", cell_v_min))
        v_end = float(elem.get("v_end", cell_v_max))

        # Right face of this member = left boundary of cavity to its right
        right_face = u + half_w
        # Left face of this member = right boundary of cavity to its left
        left_face = u - half_w

        vertical_edges.append((right_face, etype, v_start, v_end))
        vertical_edges.append((left_face, etype, v_start, v_end))

    # Add cell boundaries as virtual edges
    vertical_edges.append((cell_u_min, "wall_edge", cell_v_min, cell_v_max))
    vertical_edges.append((cell_u_max, "wall_edge", cell_v_min, cell_v_max))

    # Deduplicate and sort by U
    unique_u = sorted(set(e[0] for e in vertical_edges))

    # Build a lookup: u -> member_type (use the first non-wall_edge match)
    u_member_type: Dict[float, str] = {}
    for u_val, mtype, _, _ in vertical_edges:
        if u_val not in u_member_type or u_member_type[u_val] == "wall_edge":
            u_member_type[u_val] = mtype

    # --- Collect horizontal boundary edges ---
    horiz_members: List[Tuple[float, str, float, float]] = []
    # (v_position, member_type, u_start, u_end)

    for elem in elements:
        etype = elem.get("element_type", "")
        if etype not in HORIZONTAL_MEMBER_TYPES:
            continue

        u_coord = float(elem.get("u_coord", 0))
        v_start = float(elem.get("v_start", 0))
        v_end = float(elem.get("v_end", 0))
        width = float(elem.get("profile", {}).get("width", 0.125))
        half_w = width / 2.0

        # Horizontal members span a U range
        # For plates/tracks: they span the cell width
        # For headers/sills: they span between trimmers
        # Use u_coord +/- half profile depth as approximate U span
        # but for simplicity, get length from v_start/v_end (which for
        # horizontal members represent the start/end along the wall)
        depth = float(elem.get("profile", {}).get("depth", 0.292))

        if etype in ("bottom_plate", "top_plate", "bottom_track", "top_track"):
            # Plates span the full cell
            u_min_h = cell_u_min
            u_max_h = cell_u_max
            if etype in ("bottom_plate", "bottom_track"):
                # Top face of bottom plate
                horiz_members.append((v_end, etype, u_min_h, u_max_h))
            else:
                # Bottom face of top plate
                horiz_members.append((v_start, etype, u_min_h, u_max_h))
        elif etype == "header":
            u_min_h = cell_u_min
            u_max_h = cell_u_max
            # Bottom face of header (above opening)
            horiz_members.append((v_start, etype, u_min_h, u_max_h))
        elif etype == "sill":
            u_min_h = cell_u_min
            u_max_h = cell_u_max
            # Top face of sill (below window)
            horiz_members.append((v_end, etype, u_min_h, u_max_h))
        elif etype == "row_blocking":
            u_min_h = u_coord - half_w
            u_max_h = u_coord + half_w
            # Top face of blocking
            horiz_members.append((v_end, etype, u_min_h, u_max_h))
            # Bottom face of blocking
            horiz_members.append((v_start, etype, u_min_h, u_max_h))

    # --- Build cavities between each pair of vertical columns ---
    cavities: List[Cavity] = []
    cavity_idx = start_index

    for col_i in range(len(unique_u) - 1):
        left_u = unique_u[col_i]
        right_u = unique_u[col_i + 1]
        strip_width = right_u - left_u

        # Skip zero-width or sub-threshold strips
        if strip_width < config.min_clear_width:
            continue

        left_type = u_member_type.get(left_u, "wall_edge")
        right_type = u_member_type.get(right_u, "wall_edge")

        # Collect V boundaries within this column strip
        v_boundaries: List[Tuple[float, str]] = []
        v_boundaries.append((cell_v_min, _bottom_member_label(cell_type)))
        v_boundaries.append((cell_v_max, _top_member_label(cell_type)))

        strip_mid_u = (left_u + right_u) / 2.0
        for v_pos, h_type, h_u_min, h_u_max in horiz_members:
            # Check if this horizontal member overlaps the column strip
            if h_u_max > strip_mid_u - tol and h_u_min < strip_mid_u + tol:
                if cell_v_min + tol < v_pos < cell_v_max - tol:
                    v_boundaries.append((v_pos, h_type))

        # Deduplicate and sort by V
        seen_v: Dict[float, str] = {}
        for v_val, v_type in v_boundaries:
            rounded_v = round(v_val, 6)
            if rounded_v not in seen_v or seen_v[rounded_v] == "wall_edge":
                seen_v[rounded_v] = v_type
        sorted_v = sorted(seen_v.keys())

        for row_i in range(len(sorted_v) - 1):
            bot_v = sorted_v[row_i]
            top_v = sorted_v[row_i + 1]
            strip_height = top_v - bot_v

            if strip_height < config.min_clear_height:
                continue

            bot_type = seen_v[bot_v]
            top_type = seen_v[top_v]

            cavity = Cavity(
                id=f"{wall_id}_cav_{cavity_idx}",
                wall_id=wall_id,
                cell_id=cell_id,
                u_min=left_u,
                u_max=right_u,
                v_min=bot_v,
                v_max=top_v,
                depth=wall_thickness,
                left_member=left_type,
                right_member=right_type,
                top_member=top_type,
                bottom_member=bot_type,
            )
            cavities.append(cavity)
            cavity_idx += 1

    return cavities


def _bottom_member_label(cell_type: str) -> str:
    """Default bottom member label based on cell type."""
    if cell_type == "SCC":
        return "bottom_plate"
    if cell_type == "HCC":
        return "header"
    return "bottom_plate"


def _top_member_label(cell_type: str) -> str:
    """Default top member label based on cell type."""
    if cell_type == "SCC":
        return "sill"
    if cell_type == "HCC":
        return "top_plate"
    return "top_plate"


# ---------------------------------------------------------------------------
# Derived mode
# ---------------------------------------------------------------------------

def _decompose_derived(
    wall_id: str,
    wall_length: float,
    wall_height: float,
    wall_thickness: float,
    openings: List[Dict[str, Any]],
    config: CavityConfig,
) -> List[Cavity]:
    """Decompose cavities using configured spacing (no framing data needed).

    Computes stud positions from config.stud_spacing, then generates
    full-height cavities between each pair of adjacent studs (minus plates).
    Openings (doors/windows) split or remove cavities as needed.
    """
    stud_width = config.stud_width
    half_stud = stud_width / 2.0
    spacing = config.stud_spacing
    plate_t = config.plate_thickness

    # Compute stud U positions (centerlines)
    stud_positions: List[float] = []
    u = half_stud  # First stud at left edge
    while u < wall_length - half_stud + config.tolerance:
        stud_positions.append(u)
        u += spacing

    # Ensure end stud
    end_stud = wall_length - half_stud
    if not stud_positions or abs(stud_positions[-1] - end_stud) > config.tolerance:
        stud_positions.append(end_stud)

    # Compute vertical boundaries (inside faces of studs)
    # Each stud produces a left face and a right face
    # Cavity boundaries are: right face of left stud, left face of right stud
    v_boundaries: List[Tuple[float, str]] = []
    for pos in stud_positions:
        right_face = pos + half_stud
        left_face = pos - half_stud
        v_boundaries.append((right_face, "stud"))
        v_boundaries.append((left_face, "stud"))

    # Add wall edges
    v_boundaries.append((0.0, "wall_edge"))
    v_boundaries.append((wall_length, "wall_edge"))

    # Deduplicate and sort
    unique_u = sorted(set(b[0] for b in v_boundaries))
    u_type: Dict[float, str] = {}
    for u_val, mtype in v_boundaries:
        if u_val not in u_type or u_type[u_val] == "wall_edge":
            u_type[u_val] = mtype

    # Default V range: above bottom plate, below top plate
    base_v_min = plate_t
    base_v_max = wall_height - plate_t

    # Build opening zones for exclusion/splitting
    opening_zones = _parse_opening_zones(openings)

    cavities: List[Cavity] = []
    cavity_idx = 0

    for col_i in range(len(unique_u) - 1):
        left_u = unique_u[col_i]
        right_u = unique_u[col_i + 1]
        strip_width = right_u - left_u

        if strip_width < config.min_clear_width:
            continue

        left_type = u_type.get(left_u, "wall_edge")
        right_type = u_type.get(right_u, "wall_edge")

        # Check which openings overlap this column strip
        strip_mid_u = (left_u + right_u) / 2.0
        overlapping_openings = [
            oz for oz in opening_zones
            if oz["u_start"] < right_u - config.tolerance
            and oz["u_end"] > left_u + config.tolerance
        ]

        if not overlapping_openings:
            # Full-height cavity
            if base_v_max - base_v_min >= config.min_clear_height:
                cavity = Cavity(
                    id=f"{wall_id}_cav_{cavity_idx}",
                    wall_id=wall_id,
                    cell_id=f"{wall_id}_SC",
                    u_min=left_u,
                    u_max=right_u,
                    v_min=base_v_min,
                    v_max=base_v_max,
                    depth=wall_thickness,
                    left_member=left_type,
                    right_member=right_type,
                    top_member="top_plate",
                    bottom_member="bottom_plate",
                )
                cavities.append(cavity)
                cavity_idx += 1
        else:
            # Split cavity around openings
            for oz in overlapping_openings:
                if oz["type"] == "door":
                    # Door: full-height no-go zone -- skip this column
                    pass
                else:
                    # Window: create SCC below and HCC above
                    # SCC: bottom plate to sill
                    scc_v_max = oz["v_start"]
                    if scc_v_max - base_v_min >= config.min_clear_height:
                        cavity = Cavity(
                            id=f"{wall_id}_cav_{cavity_idx}",
                            wall_id=wall_id,
                            cell_id=f"{wall_id}_SCC",
                            u_min=left_u,
                            u_max=right_u,
                            v_min=base_v_min,
                            v_max=scc_v_max,
                            depth=wall_thickness,
                            left_member=left_type,
                            right_member=right_type,
                            top_member="sill",
                            bottom_member="bottom_plate",
                        )
                        cavities.append(cavity)
                        cavity_idx += 1

                    # HCC: header to top plate
                    hcc_v_min = oz["v_end"]
                    if base_v_max - hcc_v_min >= config.min_clear_height:
                        cavity = Cavity(
                            id=f"{wall_id}_cav_{cavity_idx}",
                            wall_id=wall_id,
                            cell_id=f"{wall_id}_HCC",
                            u_min=left_u,
                            u_max=right_u,
                            v_min=hcc_v_min,
                            v_max=base_v_max,
                            depth=wall_thickness,
                            left_member=left_type,
                            right_member=right_type,
                            top_member="top_plate",
                            bottom_member="header",
                        )
                        cavities.append(cavity)
                        cavity_idx += 1

    cavities.sort(key=lambda c: (c.u_min, c.v_min))
    return cavities


def _parse_opening_zones(
    openings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Parse opening data into zone dictionaries."""
    zones = []
    for op in openings:
        zones.append({
            "id": op.get("id", "unknown"),
            "type": op.get("opening_type", "window"),
            "u_start": float(op.get("u_start", 0)),
            "u_end": float(op.get("u_end", 0)),
            "v_start": float(op.get("v_start", 0)),
            "v_end": float(op.get("v_end", 0)),
        })
    return zones


# ---------------------------------------------------------------------------
# Utility functions for consumers (MEP router, etc.)
# ---------------------------------------------------------------------------

def find_cavity_for_uv(
    cavities: List[Cavity],
    u: float,
    v: float,
    tolerance: float = 1e-4,
) -> Optional[Cavity]:
    """Find the cavity containing a UV point.

    Args:
        cavities: List of cavities to search.
        u: U-coordinate.
        v: V-coordinate.
        tolerance: Boundary tolerance.

    Returns:
        The containing Cavity, or None if the point is on a member.
    """
    for cavity in cavities:
        if cavity.contains_uv(u, v, tolerance):
            return cavity
    return None


def find_nearest_cavity(
    cavities: List[Cavity],
    u: float,
    v: float,
) -> Optional[Cavity]:
    """Find the nearest cavity to a UV point (by U distance, matching V range).

    Used when a point falls on a stud and needs to be assigned to an
    adjacent cavity. Prefers cavities whose V range contains the point's V.

    Args:
        cavities: List of cavities to search.
        u: U-coordinate.
        v: V-coordinate.

    Returns:
        The nearest Cavity, or None if no cavities exist.
    """
    if not cavities:
        return None

    best: Optional[Cavity] = None
    best_dist = float("inf")

    for cavity in cavities:
        # Prefer cavities whose V range contains this V
        if cavity.v_min <= v <= cavity.v_max:
            # Distance = how far u is from the cavity's U range
            if u < cavity.u_min:
                dist = cavity.u_min - u
            elif u > cavity.u_max:
                dist = u - cavity.u_max
            else:
                dist = 0.0
            if dist < best_dist:
                best_dist = dist
                best = cavity

    # If no cavity contains the V, fall back to closest by center distance
    if best is None:
        for cavity in cavities:
            dist = abs(u - cavity.center_u) + abs(v - cavity.center_v)
            if dist < best_dist:
                best_dist = dist
                best = cavity

    return best


def find_adjacent_cavities(
    cavities: List[Cavity],
    cavity: Cavity,
    tolerance: float = 1e-4,
) -> Tuple[Optional[Cavity], Optional[Cavity]]:
    """Find the cavities immediately to the left and right of a given cavity.

    Adjacent cavities share the same V range and have touching U boundaries.

    Args:
        cavities: All cavities in the wall.
        cavity: The reference cavity.
        tolerance: Boundary matching tolerance.

    Returns:
        Tuple of (left_neighbor, right_neighbor). Either may be None.
    """
    left: Optional[Cavity] = None
    right: Optional[Cavity] = None
    left_dist = float("inf")
    right_dist = float("inf")

    for other in cavities:
        if other.id == cavity.id:
            continue

        # Must overlap in V range
        v_overlap = (
            other.v_max > cavity.v_min + tolerance
            and other.v_min < cavity.v_max - tolerance
        )
        if not v_overlap:
            continue

        # Left neighbor: other.u_max near cavity.u_min
        gap_left = cavity.u_min - other.u_max
        if -tolerance < gap_left < left_dist:
            left_dist = gap_left
            left = other

        # Right neighbor: other.u_min near cavity.u_max
        gap_right = other.u_min - cavity.u_max
        if -tolerance < gap_right < right_dist:
            right_dist = gap_right
            right = other

    return left, right
