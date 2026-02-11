# File: src/timber_framing_generator/assemblies/assembly_creator.py
"""Core logic for grouping elements by panel and creating Revit Assemblies.

This module provides:
1. Pure Python grouping logic (group_elements_by_panel) - no Revit dependency
2. Revit API assembly creation (create_assemblies) - behind REVIT_AVAILABLE guard

The grouping logic correlates baking_data_json (element -> geometry_index mapping)
with panels_json (panel -> element_ids mapping) and the actual Revit ElementIds
from upstream RiR baking components.

CRITICAL: AssemblyInstance.Create requires two separate transactions:
  Transaction 1: Create the assembly instance (commit immediately)
  Transaction 2: Rename type, set parameters, create views
  The assembly type is only assigned AFTER Transaction 1 commits.

CPython3 Gotcha:
    ICollection<ElementId> must be System.Collections.Generic.List[ElementId],
    NOT a Python list. Python lists do not auto-convert.

Usage:
    from src.timber_framing_generator.assemblies.assembly_creator import (
        group_elements_by_panel, create_assemblies,
    )

    groups = group_elements_by_panel(
        baking_data_json, panels_json, column_ids, beam_ids,
    )
    result = create_assemblies(doc, groups, naming_prefix="W")
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Conditional Revit Imports
# =============================================================================

REVIT_AVAILABLE = False
REVIT_ERROR: Optional[str] = None

try:
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        AssemblyInstance,
        BuiltInCategory,
        ElementId,
        FilteredElementCollector,
        Transaction,
        Transform,
        XYZ,
    )
    from System.Collections.Generic import List as NetList
    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_ERROR = str(e)
except Exception as e:
    REVIT_ERROR = str(e)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PanelElementGroup:
    """Groups Revit ElementIds belonging to a single panel.

    Attributes:
        panel_id: Panel identifier (e.g., "wall_1_panel_0")
        wall_id: Parent wall identifier
        panel_index: Zero-based panel position along wall
        column_element_ids: Revit ElementIds for vertical framing (studs, etc.)
        beam_element_ids: Revit ElementIds for horizontal framing (plates, etc.)
        sheathing_element_ids: Revit ElementIds for sheathing layers
    """
    panel_id: str
    wall_id: str
    panel_index: int
    column_element_ids: List[Any] = field(default_factory=list)
    beam_element_ids: List[Any] = field(default_factory=list)
    sheathing_element_ids: List[Any] = field(default_factory=list)

    @property
    def all_element_ids(self) -> List[Any]:
        """All ElementIds for this panel (framing + sheathing)."""
        return (
            self.column_element_ids
            + self.beam_element_ids
            + self.sheathing_element_ids
        )

    @property
    def element_count(self) -> int:
        """Total number of elements in this panel group."""
        return len(self.all_element_ids)

    @property
    def is_empty(self) -> bool:
        """True if no elements are assigned to this panel."""
        return self.element_count == 0


@dataclass
class AssemblyResult:
    """Result of creating a single Revit assembly.

    Attributes:
        panel_id: Source panel identifier
        wall_id: Parent wall identifier
        assembly_name: Generated name (e.g., "W1-P01")
        assembly_id: Revit ElementId as integer (None if not created)
        element_count: Number of elements in the assembly
        views_created: Names of assembly views created
        view_ids: ElementId integers for created views
        sheet_id: ElementId integer for created sheet (None if no sheet)
        status: "pending", "created", or "failed"
        error: Error message if status is "failed"
    """
    panel_id: str
    wall_id: str
    assembly_name: str
    assembly_id: Optional[int] = None
    element_count: int = 0
    views_created: List[str] = field(default_factory=list)
    view_ids: List[int] = field(default_factory=list)
    sheet_id: Optional[int] = None
    status: str = "pending"
    error: Optional[str] = None


@dataclass
class AssemblyBatchResult:
    """Aggregated result of creating all assemblies in a batch.

    Attributes:
        results: Individual AssemblyResult per panel
        total_assemblies: Total number of assemblies attempted
        successful: Count of successfully created assemblies
        failed: Count of failed assembly creations
    """
    results: List[AssemblyResult] = field(default_factory=list)
    total_assemblies: int = 0
    successful: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON output."""
        return {
            "assemblies": [
                {
                    "panel_id": r.panel_id,
                    "wall_id": r.wall_id,
                    "assembly_name": r.assembly_name,
                    "assembly_id": r.assembly_id,
                    "element_count": r.element_count,
                    "views_created": r.views_created,
                    "view_ids": r.view_ids,
                    "sheet_id": r.sheet_id,
                    "status": r.status,
                    "error": r.error,
                }
                for r in self.results
            ],
            "summary": {
                "total": self.total_assemblies,
                "successful": self.successful,
                "failed": self.failed,
            },
        }


# =============================================================================
# Element Grouping (Pure Python - No Revit Dependency)
# =============================================================================

def _extract_panels_list(
    panels_raw: Any,
) -> Optional[List[Dict[str, Any]]]:
    """Extract a flat list of panel dicts from various panels_json formats.

    The panel decomposer outputs either:
    - A single wall result: {"wall_id": ..., "panels": [{...}, ...], ...}
    - A list of wall results: [{"wall_id": ..., "panels": [...]}, ...]

    This function normalizes both into a flat list of panel dicts.

    Args:
        panels_raw: Parsed JSON data (dict, list, or None)

    Returns:
        Flat list of panel dicts, or None if no panels found
    """
    if panels_raw is None:
        return None

    # Single wall result dict: {"wall_id": ..., "panels": [...]}
    if isinstance(panels_raw, dict) and "panels" in panels_raw:
        panels = panels_raw["panels"]
        if panels:
            return panels
        return None

    # List of items
    if isinstance(panels_raw, list):
        if not panels_raw:
            return None

        # Check if first item is a wall result (has "panels" key)
        if isinstance(panels_raw[0], dict) and "panels" in panels_raw[0]:
            # List of wall results: flatten all panels
            flat: List[Dict[str, Any]] = []
            for wall_result in panels_raw:
                flat.extend(wall_result.get("panels", []))
            return flat if flat else None

        # Already a flat list of panel dicts (has "id" key)
        if isinstance(panels_raw[0], dict) and "id" in panels_raw[0]:
            return panels_raw

    logger.warning("Unrecognized panels_json format: %s", type(panels_raw))
    return None


def group_elements_by_panel(
    baking_data_json: str,
    panels_json: Optional[str],
    column_ids: List[Any],
    beam_ids: List[Any],
    sheathing_ids: Optional[List[Any]] = None,
    sheathing_data_json: Optional[str] = None,
) -> List[PanelElementGroup]:
    """Group Revit ElementIds by panel_id.

    Correlates three data sources:
    1. baking_data_json: maps element IDs to geometry_index and classification
    2. panels_json: maps panel_id to element_ids
    3. column_ids/beam_ids: actual Revit ElementIds in geometry_index order

    If panels_json is None or empty, creates one group per wall with all
    elements from that wall.

    Args:
        baking_data_json: JSON from gh_revit_baker.py with geometry_index per member
        panels_json: JSON from panel decomposer with panel boundaries and element lists.
            If None, falls back to one assembly per wall.
        column_ids: Revit ElementIds from RiR "Add Structural Column" (ordered by geometry_index)
        beam_ids: Revit ElementIds from RiR "Add Structural Framing" (ordered by geometry_index)
        sheathing_ids: Optional Revit ElementIds from sheathing baking
        sheathing_data_json: Optional JSON mapping sheathing panels to panel_ids

    Returns:
        List of PanelElementGroup, one per panel (or one per wall if no panels)
    """
    baking_data = json.loads(baking_data_json)
    panels_raw = json.loads(panels_json) if panels_json else None

    # Flatten panels_json into a list of panel dicts.
    # panels_json can be:
    #   - A flat list of panel dicts: [{"id": ..., "wall_id": ...}, ...]
    #   - A single wall result: {"wall_id": ..., "panels": [...]}
    #   - A list of wall results: [{"wall_id": ..., "panels": [...]}, ...]
    panels_data = _extract_panels_list(panels_raw)

    # If panels provided, group by panel
    if panels_data:
        return _group_by_panels(
            baking_data, panels_data, column_ids, beam_ids,
            sheathing_ids, sheathing_data_json,
        )

    # Fallback: one group per wall
    return _group_by_walls(
        baking_data, column_ids, beam_ids,
        sheathing_ids, sheathing_data_json,
    )


def _group_by_panels(
    baking_data: Dict[str, Any],
    panels_data: List[Dict[str, Any]],
    column_ids: List[Any],
    beam_ids: List[Any],
    sheathing_ids: Optional[List[Any]],
    sheathing_data_json: Optional[str],
) -> List[PanelElementGroup]:
    """Group elements using panel definitions.

    Uses two strategies:
    1. If panels have element_ids populated, match by element ID
    2. Otherwise, compute U-coordinates from member centerlines and
       match against panel u_start/u_end ranges (geometry-based fallback)
    """
    sheathing_panel_map: Dict[str, List[int]] = {}
    if sheathing_ids and sheathing_data_json:
        sheathing_panel_map = _build_sheathing_panel_map(sheathing_data_json)

    # Check if any panel has element_ids populated
    has_element_ids = any(
        panel.get("element_ids") for panel in panels_data
    )

    if has_element_ids:
        logger.info("Using element_ids from panels for grouping")
        return _group_by_element_ids(
            baking_data, panels_data, column_ids, beam_ids,
            sheathing_ids, sheathing_panel_map,
        )

    logger.info("Panels have no element_ids -- using geometry-based assignment")
    return _group_by_geometry(
        baking_data, panels_data, column_ids, beam_ids,
        sheathing_ids, sheathing_panel_map,
    )


def _group_by_element_ids(
    baking_data: Dict[str, Any],
    panels_data: List[Dict[str, Any]],
    column_ids: List[Any],
    beam_ids: List[Any],
    sheathing_ids: Optional[List[Any]],
    sheathing_panel_map: Dict[str, List[int]],
) -> List[PanelElementGroup]:
    """Group elements by matching panel element_ids to baking data member IDs."""
    # Build element index: member_id -> {classification, geometry_index}
    element_index: Dict[str, Dict[str, Any]] = {}
    for wall_id, wall_data in baking_data.get("walls", {}).items():
        for member in wall_data.get("members", []):
            element_index[member["id"]] = {
                "classification": member["classification"],
                "geometry_index": member["geometry_index"],
            }

    groups: List[PanelElementGroup] = []

    for panel in panels_data:
        panel_id = panel["id"]
        group = PanelElementGroup(
            panel_id=panel_id,
            wall_id=panel["wall_id"],
            panel_index=panel.get("panel_index", 0),
        )

        for elem_id_str in panel.get("element_ids", []):
            info = element_index.get(elem_id_str)
            if not info:
                continue
            idx = info["geometry_index"]
            if info["classification"] == "column" and idx < len(column_ids):
                group.column_element_ids.append(column_ids[idx])
            elif info["classification"] == "beam" and idx < len(beam_ids):
                group.beam_element_ids.append(beam_ids[idx])

        if sheathing_ids and panel_id in sheathing_panel_map:
            for sheath_idx in sheathing_panel_map[panel_id]:
                if sheath_idx < len(sheathing_ids):
                    group.sheathing_element_ids.append(sheathing_ids[sheath_idx])

        if not group.is_empty:
            groups.append(group)

    logger.info(
        "Grouped %d elements into %d panels (by element_ids)",
        sum(g.element_count for g in groups), len(groups),
    )
    return groups


def _group_by_geometry(
    baking_data: Dict[str, Any],
    panels_data: List[Dict[str, Any]],
    column_ids: List[Any],
    beam_ids: List[Any],
    sheathing_ids: Optional[List[Any]],
    sheathing_panel_map: Dict[str, List[int]],
) -> List[PanelElementGroup]:
    """Group elements by computing U-coordinates from centerlines.

    For each wall:
    1. Derive wall direction from the longest horizontal member (plate/beam)
    2. Use that member's start point as the wall origin
    3. For each member, compute U = dot(midpoint - origin, direction)
    4. Assign to panel whose [u_start, u_end] range contains U
    """
    # Index panels by wall_id for lookup
    wall_panels: Dict[str, List[Dict[str, Any]]] = {}
    for panel in panels_data:
        wid = panel["wall_id"]
        wall_panels.setdefault(wid, []).append(panel)

    # Sort each wall's panels by u_start
    for wid in wall_panels:
        wall_panels[wid].sort(key=lambda p: p.get("u_start", 0))

    # Initialize groups for each panel
    panel_groups: Dict[str, PanelElementGroup] = {}
    for panel in panels_data:
        pid = panel["id"]
        panel_groups[pid] = PanelElementGroup(
            panel_id=pid,
            wall_id=panel["wall_id"],
            panel_index=panel.get("panel_index", 0),
        )

    for wall_id, wall_data in baking_data.get("walls", {}).items():
        panels_for_wall = wall_panels.get(wall_id, [])
        if not panels_for_wall:
            logger.debug("Wall '%s' has no panels, skipping", wall_id)
            continue

        members = wall_data.get("members", [])
        if not members:
            continue

        # Derive wall direction from the longest horizontal member
        origin, direction = _derive_wall_axis(members)
        if origin is None or direction is None:
            logger.warning(
                "Could not derive wall axis for '%s', skipping", wall_id,
            )
            continue

        # Assign each member to a panel by U-coordinate
        for member in members:
            u = _compute_member_u(member, origin, direction)
            if u is None:
                continue

            # Find matching panel
            matched_panel_id = _find_panel_for_u(u, panels_for_wall)
            if matched_panel_id is None:
                continue

            idx = member["geometry_index"]
            cls = member["classification"]
            group = panel_groups[matched_panel_id]

            if cls == "column" and idx < len(column_ids):
                group.column_element_ids.append(column_ids[idx])
            elif cls == "beam" and idx < len(beam_ids):
                group.beam_element_ids.append(beam_ids[idx])

    # Add sheathing
    if sheathing_ids:
        for pid, indices in sheathing_panel_map.items():
            if pid in panel_groups:
                for sheath_idx in indices:
                    if sheath_idx < len(sheathing_ids):
                        panel_groups[pid].sheathing_element_ids.append(
                            sheathing_ids[sheath_idx],
                        )

    # Filter to non-empty groups, preserve panel order
    groups = [g for g in panel_groups.values() if not g.is_empty]

    logger.info(
        "Grouped %d elements into %d panels (by geometry)",
        sum(g.element_count for g in groups), len(groups),
    )
    return groups


def _derive_wall_axis(
    members: List[Dict[str, Any]],
) -> tuple:
    """Derive wall origin and direction from the longest horizontal member.

    Horizontal members (beams/plates) run along the wall length.
    The longest one gives the most reliable direction estimate.

    Args:
        members: List of baking data member dicts

    Returns:
        (origin_xyz, direction_xyz) tuple, or (None, None) if no beams found.
        Each is a dict with x, y, z keys.
    """
    best_length_sq = 0.0
    best_start = None
    best_end = None

    for m in members:
        if m.get("classification") != "beam":
            continue
        s = m.get("centerline_start", {})
        e = m.get("centerline_end", {})
        dx = e.get("x", 0) - s.get("x", 0)
        dy = e.get("y", 0) - s.get("y", 0)
        dz = e.get("z", 0) - s.get("z", 0)
        length_sq = dx * dx + dy * dy + dz * dz
        if length_sq > best_length_sq:
            best_length_sq = length_sq
            best_start = s
            best_end = e

    if best_start is None or best_length_sq < 1e-10:
        return None, None

    length = best_length_sq ** 0.5
    direction = {
        "x": (best_end["x"] - best_start["x"]) / length,
        "y": (best_end["y"] - best_start["y"]) / length,
        "z": (best_end["z"] - best_start["z"]) / length,
    }

    # Origin is the start of this plate (approximates wall start)
    # Project to get the minimum U across all members for better origin
    origin = {"x": best_start["x"], "y": best_start["y"], "z": best_start["z"]}

    return origin, direction


def _compute_member_u(
    member: Dict[str, Any],
    origin: Dict[str, float],
    direction: Dict[str, float],
) -> Optional[float]:
    """Compute U-coordinate of a member along the wall axis.

    For beams (horizontal): use midpoint of centerline
    For columns (vertical): use centerline start (bottom point)

    Args:
        member: Baking data member dict with centerline_start/end
        origin: Wall origin point {x, y, z}
        direction: Wall direction unit vector {x, y, z}

    Returns:
        U-coordinate (distance from origin along wall), or None
    """
    s = member.get("centerline_start", {})
    e = member.get("centerline_end", {})

    if not s or not e:
        return None

    # Reference point: midpoint for beams, start for columns
    if member.get("classification") == "beam":
        ref = {
            "x": (s.get("x", 0) + e.get("x", 0)) / 2.0,
            "y": (s.get("y", 0) + e.get("y", 0)) / 2.0,
            "z": (s.get("z", 0) + e.get("z", 0)) / 2.0,
        }
    else:
        ref = {"x": s.get("x", 0), "y": s.get("y", 0), "z": s.get("z", 0)}

    # Project: u = dot(ref - origin, direction)
    dx = ref["x"] - origin["x"]
    dy = ref["y"] - origin["y"]
    dz = ref["z"] - origin["z"]
    u = dx * direction["x"] + dy * direction["y"] + dz * direction["z"]

    return u


def _find_panel_for_u(
    u: float,
    panels: List[Dict[str, Any]],
) -> Optional[str]:
    """Find which panel a U-coordinate belongs to.

    Uses the same boundary logic as assign_panel_ids_to_elements:
    - Non-last panels: u_start <= u < u_end
    - Last panel: u_start <= u <= u_end

    Also applies a small tolerance for elements near boundaries.

    Args:
        u: U-coordinate along wall
        panels: Sorted list of panel dicts with u_start, u_end, id

    Returns:
        panel_id string, or None if no match
    """
    tolerance = 0.01  # ~0.12 inches tolerance for boundary elements

    last_idx = len(panels) - 1
    for i, panel in enumerate(panels):
        u_start = panel.get("u_start", 0)
        u_end = panel.get("u_end", 0)

        if i == last_idx:
            # Last panel: inclusive on both ends + tolerance
            if u_start - tolerance <= u <= u_end + tolerance:
                return panel["id"]
        else:
            if u_start - tolerance <= u < u_end + tolerance:
                return panel["id"]

    return None


def _group_by_walls(
    baking_data: Dict[str, Any],
    column_ids: List[Any],
    beam_ids: List[Any],
    sheathing_ids: Optional[List[Any]],
    sheathing_data_json: Optional[str],
) -> List[PanelElementGroup]:
    """Fallback: one group per wall when no panels are defined."""
    sheathing_wall_map: Dict[str, List[int]] = {}
    if sheathing_ids and sheathing_data_json:
        sheathing_wall_map = _build_sheathing_wall_map(sheathing_data_json)

    groups: List[PanelElementGroup] = []

    for wall_id, wall_data in baking_data.get("walls", {}).items():
        group = PanelElementGroup(
            panel_id=wall_id,
            wall_id=wall_id,
            panel_index=0,
        )

        for member in wall_data.get("members", []):
            idx = member["geometry_index"]
            if member["classification"] == "column" and idx < len(column_ids):
                group.column_element_ids.append(column_ids[idx])
            elif member["classification"] == "beam" and idx < len(beam_ids):
                group.beam_element_ids.append(beam_ids[idx])

        if sheathing_ids and wall_id in sheathing_wall_map:
            for sheath_idx in sheathing_wall_map[wall_id]:
                if sheath_idx < len(sheathing_ids):
                    group.sheathing_element_ids.append(sheathing_ids[sheath_idx])

        if not group.is_empty:
            groups.append(group)

    logger.info(
        "Grouped %d elements into %d wall-level assemblies (no panels)",
        sum(g.element_count for g in groups), len(groups),
    )
    return groups


def _build_sheathing_panel_map(
    sheathing_data_json: str,
) -> Dict[str, List[int]]:
    """Build mapping: panel_id -> list of sheathing indices."""
    sheathing_data = json.loads(sheathing_data_json)
    panel_map: Dict[str, List[int]] = {}

    for i, spanel in enumerate(sheathing_data.get("panels", [])):
        pid = spanel.get("panel_id")
        if pid:
            panel_map.setdefault(pid, []).append(i)

    return panel_map


def _build_sheathing_wall_map(
    sheathing_data_json: str,
) -> Dict[str, List[int]]:
    """Build mapping: wall_id -> list of sheathing indices."""
    sheathing_data = json.loads(sheathing_data_json)
    wall_map: Dict[str, List[int]] = {}

    for i, spanel in enumerate(sheathing_data.get("panels", [])):
        wid = spanel.get("wall_id")
        if wid:
            wall_map.setdefault(wid, []).append(i)

    return wall_map


# =============================================================================
# Assembly Naming
# =============================================================================

def generate_assembly_name(
    wall_id: str,
    panel_index: int,
    prefix: str = "W",
) -> str:
    """Generate assembly name like W1-P01, W2-P03.

    Extracts the numeric part from wall_id (e.g., "wall_1" -> 1).

    Args:
        wall_id: Wall identifier string
        panel_index: Zero-based panel index along wall
        prefix: Naming prefix (default "W")

    Returns:
        Formatted assembly name string
    """
    match = re.search(r"(\d+)", wall_id)
    wall_num = int(match.group(1)) if match else 0
    return f"{prefix}{wall_num}-P{panel_index + 1:02d}"


# =============================================================================
# Revit Assembly Creation
# =============================================================================

def _to_element_id(value: Any) -> Any:
    """Convert a value to a Revit ElementId.

    GH untyped parameters often unwrap ElementIds as strings (via .Value).
    This converts str/int back to ElementId for the .NET List<ElementId>.

    Args:
        value: An ElementId, int, or str (integer representation)

    Returns:
        Revit ElementId object

    Raises:
        ValueError: If value cannot be converted
    """
    if isinstance(value, ElementId):
        return value
    if isinstance(value, int):
        return ElementId(value)
    if isinstance(value, str):
        try:
            return ElementId(int(value))
        except ValueError:
            raise ValueError(
                "Cannot convert string '%s' to ElementId (not an integer)" % value
            )
    # Fallback: try int() conversion for other numeric types
    try:
        return ElementId(int(value))
    except (ValueError, TypeError):
        raise ValueError("Cannot convert %r (type %s) to ElementId" % (value, type(value).__name__))


def _fix_assembly_orientation(
    doc: Any,
    assembly: Any,
    wall_direction: Optional[Dict[str, float]],
) -> bool:
    """Rotate assembly transform so BasisX aligns with wall direction.

    The Revit assembly's local coordinate system determines how
    ElevationFront/Top views are oriented. If BasisX doesn't align with
    the wall direction, the "Front Elevation" view shows a side view instead.

    This rotates the assembly transform around the Z axis to correct the
    alignment. Must be called inside an active transaction.

    Args:
        doc: Revit Document object
        assembly: AssemblyInstance object
        wall_direction: Wall direction unit vector {x, y, z}, or None to skip

    Returns:
        True if rotation was applied, False if skipped or failed
    """
    if wall_direction is None:
        return False

    if not REVIT_AVAILABLE:
        return False

    try:
        transform = assembly.GetTransform()
        basis_x = transform.BasisX

        # Wall direction in XY plane (ignore Z for rotation)
        wd_x = wall_direction.get("x", 0.0)
        wd_y = wall_direction.get("y", 0.0)
        wd_len = math.sqrt(wd_x * wd_x + wd_y * wd_y)
        if wd_len < 1e-10:
            return False

        wd_x /= wd_len
        wd_y /= wd_len

        # Compute angle between assembly BasisX and wall direction (XY plane)
        dot = basis_x.X * wd_x + basis_x.Y * wd_y
        cross_z = basis_x.X * wd_y - basis_x.Y * wd_x
        angle = math.atan2(cross_z, dot)

        # Skip if already aligned (within ~5 degrees)
        if abs(angle) < 0.09:
            return False

        # Rotate around Z axis at assembly origin
        origin = transform.Origin
        rotation = Transform.CreateRotationAtPoint(
            XYZ.BasisZ, -angle, origin,
        )

        new_transform = rotation.Multiply(transform)
        assembly.SetTransform(new_transform)

        print(
            "[assembly_creator] Rotated assembly by %.1f deg to align with wall"
            % math.degrees(angle)
        )
        return True

    except Exception as e:
        print("[assembly_creator] Orientation fix failed: %s" % e)
        return False


def create_assemblies(
    doc: Any,
    groups: List[PanelElementGroup],
    naming_prefix: str = "W",
    naming_category_id: Any = None,
    create_views: bool = False,
    view_config: Any = None,
    wall_directions: Optional[Dict[str, Dict[str, float]]] = None,
) -> AssemblyBatchResult:
    """Create Revit AssemblyInstances from grouped elements.

    Uses the two-transaction pattern required by the Revit API:
    - Transaction 1: AssemblyInstance.Create() + commit
    - Transaction 2: Rename assembly type, fix orientation, create views

    Args:
        doc: Revit Document object
        groups: Element groups from group_elements_by_panel()
        naming_prefix: Prefix for assembly names (default "W")
        naming_category_id: Revit ElementId for naming category.
            Defaults to OST_StructuralFraming.
        create_views: If True, creates assembly views using view_config settings
        view_config: Optional AssemblyViewConfig controlling view types and settings.
            If None with create_views=True, uses AssemblyViewConfig defaults.
        wall_directions: Optional mapping of wall_id -> direction dict {x, y, z}.
            Used to fix assembly orientation before creating views.

    Returns:
        AssemblyBatchResult with per-panel results and summary
    """
    if not REVIT_AVAILABLE:
        logger.error("Revit API not available: %s", REVIT_ERROR)
        return AssemblyBatchResult()

    # Import here to avoid issues when REVIT_AVAILABLE is False
    from src.timber_framing_generator.assemblies.assembly_views import (
        AssemblyViewConfig,
        create_assembly_views,
    )
    from src.timber_framing_generator.assemblies.assembly_sheets import (
        create_assembly_sheet,
    )

    # Default naming category: Structural Framing
    if naming_category_id is None:
        naming_category_id = ElementId(BuiltInCategory.OST_StructuralFraming)

    # Resolve view config
    resolved_config: Optional[AssemblyViewConfig] = None
    if create_views:
        if view_config is not None:
            resolved_config = view_config
        else:
            resolved_config = AssemblyViewConfig()

    batch = AssemblyBatchResult()
    batch.total_assemblies = len(groups)

    for group in groups:
        assembly_name = generate_assembly_name(
            group.wall_id, group.panel_index, naming_prefix,
        )
        result = AssemblyResult(
            panel_id=group.panel_id,
            wall_id=group.wall_id,
            assembly_name=assembly_name,
            element_count=group.element_count,
        )

        try:
            # Build .NET List<ElementId>
            # ElementIds may arrive as actual ElementId, int, or str
            # (GH untyped params often unwrap to str via .Value)
            id_list = NetList[ElementId]()
            for eid in group.all_element_ids:
                id_list.Add(_to_element_id(eid))

            # Transaction 1: Create assembly instance
            t1 = Transaction(doc, "Create Assembly: %s" % assembly_name)
            t1.Start()
            try:
                assembly = AssemblyInstance.Create(
                    doc, id_list, naming_category_id,
                )
                t1.Commit()
            except Exception as e:
                if t1.HasStarted():
                    t1.RollBack()
                raise

            # Transaction 2: Rename, fix orientation, and configure
            # (type exists only after T1 commit)
            t2 = Transaction(doc, "Configure Assembly: %s" % assembly_name)
            t2.Start()
            try:
                # Rename assembly type
                assembly_type_id = assembly.GetTypeId()
                assembly_type = doc.GetElement(assembly_type_id)
                if assembly_type:
                    assembly_type.Name = assembly_name

                # Fix orientation BEFORE creating views
                if wall_directions:
                    wall_dir = wall_directions.get(group.wall_id)
                    _fix_assembly_orientation(doc, assembly, wall_dir)

                # Create views if requested
                if create_views and resolved_config is not None:
                    view_infos = create_assembly_views(
                        doc, assembly.Id, config=resolved_config,
                    )
                    result.views_created = [vi.view_name for vi in view_infos]
                    result.view_ids = [
                        vi.view_id.IntegerValue
                        for vi in view_infos
                        if vi.view_id is not None
                    ]

                    # Create sheet if requested
                    if resolved_config.include_sheet and view_infos:
                        sheet_result = create_assembly_sheet(
                            doc, assembly.Id, view_infos,
                            titleblock_name=resolved_config.titleblock_name,
                            assembly_name=assembly_name,
                        )
                        if sheet_result:
                            result.sheet_id = sheet_result.sheet_id
                            result.views_created.append(
                                "Sheet: %s" % sheet_result.sheet_name,
                            )

                t2.Commit()
            except Exception as e:
                if t2.HasStarted():
                    t2.RollBack()
                # Assembly was created but configuration failed
                logger.warning(
                    "Assembly '%s' created but configuration failed: %s",
                    assembly_name, e,
                )

            result.assembly_id = assembly.Id.IntegerValue
            result.status = "created"
            batch.successful += 1
            logger.info(
                "Created assembly '%s' with %d elements",
                assembly_name, group.element_count,
            )

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            batch.failed += 1
            logger.error(
                "Failed to create assembly '%s': %s", assembly_name, e,
            )

        batch.results.append(result)

    logger.info(
        "Assembly batch complete: %d/%d successful",
        batch.successful, batch.total_assemblies,
    )
    return batch
