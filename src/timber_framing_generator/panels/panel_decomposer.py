# File: src/timber_framing_generator/panels/panel_decomposer.py
"""
Main panel decomposition module.

Orchestrates the panelization process:
1. Detect and apply corner adjustments
2. Find optimal joint locations
3. Create panel objects with geometry and contents

This module provides the main entry points for wall panelization,
suitable for both single-wall and multi-wall scenarios.

Example:
    >>> from timber_framing_generator.panels import (
    ...     PanelConfig, decompose_wall_to_panels, decompose_all_walls
    ... )
    >>> config = PanelConfig(max_panel_length=24.0)
    >>> results = decompose_wall_to_panels(wall_data, framing_data, config)
    >>> print(f"Created {results['total_panel_count']} panels")
"""

from typing import List, Dict, Any, Optional, Tuple
import json

from .panel_config import PanelConfig, ExclusionZone
from .corner_handler import (
    detect_wall_corners,
    calculate_corner_adjustments,
    apply_corner_adjustments,
    get_adjusted_wall_length,
)
from .joint_optimizer import (
    find_exclusion_zones,
    find_optimal_joints,
    get_panel_boundaries,
)


def decompose_wall_to_panels(
    wall_data: Dict,
    framing_data: Optional[Dict] = None,
    config: Optional[PanelConfig] = None,
    corner_adjustments: Optional[List[Dict]] = None,
) -> Dict:
    """Decompose a single wall into panels.

    This is the main entry point for panelizing a single wall.
    It handles corner adjustments, finds optimal joints, and creates
    panel objects with geometry.

    Args:
        wall_data: WallData dictionary
        framing_data: FramingResults dictionary with elements (optional)
        config: Panel configuration (uses defaults if not provided)
        corner_adjustments: Pre-calculated corner adjustments (optional)

    Returns:
        PanelResults dictionary with panels, joints, and metadata
    """
    if config is None:
        config = PanelConfig()

    wall_id = wall_data.get("wall_id", wall_data.get("id", "unknown"))
    original_length = wall_data.get("wall_length", wall_data.get("length", 0))
    wall_height = wall_data.get("wall_height", wall_data.get("height", 8.0))

    # Apply corner adjustments if provided
    working_wall_data = wall_data
    if corner_adjustments:
        working_wall_data = apply_corner_adjustments(wall_data, corner_adjustments)

    adjusted_length = working_wall_data.get(
        "wall_length",
        working_wall_data.get("length", original_length)
    )

    # Find exclusion zones
    exclusion_zones = find_exclusion_zones(working_wall_data, config)

    # Find optimal joint locations
    joint_u_coords = find_optimal_joints(
        adjusted_length,
        exclusion_zones,
        config
    )

    # Get panel boundaries
    boundaries = get_panel_boundaries(joint_u_coords, adjusted_length)

    # Create panels
    panels = []
    joints = []

    for i, (u_start, u_end) in enumerate(boundaries):
        panel = _create_panel(
            wall_id=wall_id,
            panel_index=i,
            u_start=u_start,
            u_end=u_end,
            wall_data=working_wall_data,
            framing_data=framing_data,
            config=config,
        )
        panels.append(panel)

        # Create joint (except for last panel)
        if i < len(boundaries) - 1:
            joint = _create_joint(
                u_coord=u_end,
                left_panel_id=panel["id"],
                right_panel_id=f"{wall_id}_panel_{i+1}",
                wall_data=working_wall_data,
                framing_data=framing_data,
                config=config,
            )
            joints.append(joint)

    return {
        "wall_id": wall_id,
        "panels": panels,
        "joints": joints,
        "corner_adjustments": corner_adjustments or [],
        "total_panel_count": len(panels),
        "original_wall_length": original_length,
        "adjusted_wall_length": adjusted_length,
        "metadata": {
            "config": config.to_dict(),
            "exclusion_zones": [
                {"u_start": z.u_start, "u_end": z.u_end, "type": z.zone_type}
                for z in exclusion_zones
            ],
        },
    }


def decompose_all_walls(
    walls_data: List[Dict],
    framing_results: Optional[List[Dict]] = None,
    config: Optional[PanelConfig] = None,
) -> List[Dict]:
    """Decompose multiple walls with corner handling.

    Processes all walls together to properly handle corners:
    1. Detect all corner connections between walls
    2. Calculate extend/recede adjustments
    3. Apply adjustments and decompose each wall

    Args:
        walls_data: List of WallData dictionaries
        framing_results: List of FramingResults dictionaries (optional)
        config: Panel configuration (uses defaults if not provided)

    Returns:
        List of PanelResults dictionaries, one per wall
    """
    # Guard: if caller passed (walls_data, config) without framing_results,
    # framing_results ends up as PanelConfig. Detect and fix argument shift.
    if isinstance(framing_results, PanelConfig):
        config = framing_results
        framing_results = None

    if config is None:
        config = PanelConfig()

    if framing_results is None:
        framing_results = [None] * len(walls_data)

    # Detect and calculate corner adjustments
    corners = detect_wall_corners(walls_data)
    all_adjustments = calculate_corner_adjustments(
        corners,
        config.corner_priority.value
    )

    # Group adjustments by wall
    adjustments_by_wall: Dict[str, List[Dict]] = {}
    for adj in all_adjustments:
        wall_id = adj["wall_id"]
        if wall_id not in adjustments_by_wall:
            adjustments_by_wall[wall_id] = []
        adjustments_by_wall[wall_id].append(adj)

    # Decompose each wall
    results = []
    for wall_data, framing_data in zip(walls_data, framing_results):
        wall_id = wall_data.get("wall_id", wall_data.get("id", ""))
        wall_adjustments = adjustments_by_wall.get(wall_id, [])

        result = decompose_wall_to_panels(
            wall_data,
            framing_data,
            config,
            corner_adjustments=wall_adjustments,
        )
        results.append(result)

    return results


def _create_panel(
    wall_id: str,
    panel_index: int,
    u_start: float,
    u_end: float,
    wall_data: Dict,
    framing_data: Optional[Dict],
    config: PanelConfig,
) -> Dict:
    """Create a panel dictionary.

    Args:
        wall_id: ID of the source wall
        panel_index: Index of this panel along the wall
        u_start: Start U coordinate
        u_end: End U coordinate
        wall_data: WallData dictionary
        framing_data: FramingResults dictionary (optional)
        config: Panel configuration

    Returns:
        Panel dictionary
    """
    panel_id = f"{wall_id}_panel_{panel_index}"
    length = u_end - u_start
    height = wall_data.get("wall_height", wall_data.get("height", 8.0))
    base_elevation = wall_data.get("base_elevation", 0.0)

    # Calculate corners in world coordinates
    corners = _calculate_panel_corners(
        wall_data,
        u_start,
        u_end,
        height,
        base_elevation,
    )

    # Find elements within this panel
    element_ids = []
    cell_ids = []
    if framing_data:
        element_ids = _find_elements_in_range(
            framing_data.get("elements", []),
            u_start,
            u_end,
        )

    # Estimate weight
    area = length * height
    estimated_weight = area * config.weight_per_sqft

    return {
        "id": panel_id,
        "wall_id": wall_id,
        "panel_index": panel_index,
        "u_start": u_start,
        "u_end": u_end,
        "length": length,
        "height": height,
        "corners": corners,
        "cell_ids": cell_ids,
        "element_ids": element_ids,
        "estimated_weight": estimated_weight,
        "assembly_sequence": panel_index,
        "metadata": {},
    }


def _create_joint(
    u_coord: float,
    left_panel_id: str,
    right_panel_id: str,
    wall_data: Dict,
    framing_data: Optional[Dict],
    config: PanelConfig,
) -> Dict:
    """Create a joint dictionary.

    Args:
        u_coord: U coordinate of the joint
        left_panel_id: ID of panel to the left
        right_panel_id: ID of panel to the right
        wall_data: WallData dictionary
        framing_data: FramingResults dictionary (optional)
        config: Panel configuration

    Returns:
        Joint dictionary
    """
    # Determine joint type based on location
    wall_length = wall_data.get("wall_length", wall_data.get("length", 0))

    if u_coord < config.min_joint_to_corner:
        joint_type = "corner_adjacent"
    elif u_coord > wall_length - config.min_joint_to_corner:
        joint_type = "corner_adjacent"
    else:
        # Check if near an opening
        is_near_opening = False
        for opening in wall_data.get("openings", []):
            opening_start = opening.get("u_start", 0)
            opening_end = opening.get("u_end", 0)
            if (abs(u_coord - opening_start) < config.min_joint_to_opening + 0.5 or
                abs(u_coord - opening_end) < config.min_joint_to_opening + 0.5):
                is_near_opening = True
                break

        joint_type = "opening_adjacent" if is_near_opening else "field"

    # Find studs at joint location
    stud_u_coords = []
    if framing_data and config.snap_to_studs:
        # Joint should be at a stud - find nearby studs
        for element in framing_data.get("elements", []):
            if element.get("element_type") in ["stud", "king_stud", "trimmer"]:
                elem_u = element.get("u_coord", 0)
                if abs(elem_u - u_coord) < config.stud_spacing / 2:
                    stud_u_coords.append(elem_u)

    return {
        "u_coord": u_coord,
        "joint_type": joint_type,
        "left_panel_id": left_panel_id,
        "right_panel_id": right_panel_id,
        "stud_u_coords": stud_u_coords,
    }


def _calculate_panel_corners(
    wall_data: Dict,
    u_start: float,
    u_end: float,
    height: float,
    base_elevation: float,
) -> Dict:
    """Calculate panel corner points in world coordinates.

    Uses the wall's base plane to transform U coordinates to world XYZ.

    Args:
        wall_data: WallData dictionary with base_plane
        u_start: Start U coordinate
        u_end: End U coordinate
        height: Panel height
        base_elevation: Base elevation

    Returns:
        Dictionary with corner points (bottom_left, bottom_right, top_right, top_left)
    """
    base_plane = wall_data.get("base_plane", {})

    # Get plane components
    origin = base_plane.get("origin", {})
    x_axis = base_plane.get("x_axis", {})

    # Extract coordinates
    if isinstance(origin, dict):
        ox, oy, oz = origin.get("x", 0), origin.get("y", 0), origin.get("z", 0)
    else:
        ox, oy, oz = 0, 0, 0

    if isinstance(x_axis, dict):
        xx, xy, xz = x_axis.get("x", 1), x_axis.get("y", 0), x_axis.get("z", 0)
    else:
        xx, xy, xz = 1, 0, 0

    # Calculate corner positions
    # Bottom left: origin + u_start * x_axis
    bl_x = ox + u_start * xx
    bl_y = oy + u_start * xy
    bl_z = base_elevation

    # Bottom right: origin + u_end * x_axis
    br_x = ox + u_end * xx
    br_y = oy + u_end * xy
    br_z = base_elevation

    # Top right: bottom right + height in Z
    tr_x = br_x
    tr_y = br_y
    tr_z = base_elevation + height

    # Top left: bottom left + height in Z
    tl_x = bl_x
    tl_y = bl_y
    tl_z = base_elevation + height

    return {
        "bottom_left": {"x": bl_x, "y": bl_y, "z": bl_z},
        "bottom_right": {"x": br_x, "y": br_y, "z": br_z},
        "top_right": {"x": tr_x, "y": tr_y, "z": tr_z},
        "top_left": {"x": tl_x, "y": tl_y, "z": tl_z},
    }


def _find_elements_in_range(
    elements: List[Dict],
    u_start: float,
    u_end: float,
) -> List[str]:
    """Find framing element IDs within a U coordinate range.

    Args:
        elements: List of FramingElementData dictionaries
        u_start: Start of range
        u_end: End of range

    Returns:
        List of element IDs within the range
    """
    element_ids = []

    for element in elements:
        elem_u = element.get("u_coord", 0)

        # Check if element is within panel bounds
        # For elements, we check if their centerline is within bounds
        if u_start <= elem_u <= u_end:
            element_ids.append(element.get("id", ""))

    return element_ids


def serialize_panel_results(results: Dict) -> str:
    """Serialize PanelResults to JSON string.

    Args:
        results: PanelResults dictionary

    Returns:
        JSON string
    """
    return json.dumps(results, indent=2)


def deserialize_panel_results(json_str: str) -> Dict:
    """Deserialize JSON string to PanelResults dictionary.

    Args:
        json_str: JSON string

    Returns:
        PanelResults dictionary
    """
    return json.loads(json_str)
