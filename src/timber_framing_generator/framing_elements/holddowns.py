# File: src/timber_framing_generator/framing_elements/holddowns.py
"""
Holddown location generation for shear walls.

Generates point locations where holddown anchors should be placed at shear
wall ends and panel splice points. Holddowns resist overturning forces by
connecting the wall framing to the foundation or floor structure below.

Holddown placement rules:
- Required at both ends of every shear wall
- Required at panel splice points (for panelized walls)
- Centered on end studs (typically offset by half stud width from wall end)

Usage:
    from src.timber_framing_generator.framing_elements.holddowns import (
        generate_holddown_locations,
        HolddownLocation,
    )

    # Generate holddown locations for a wall
    holddowns = generate_holddown_locations(wall_data, config)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum

# Handle Rhino import
try:
    import Rhino.Geometry as rg
    RHINO_AVAILABLE = True
except ImportError:
    RHINO_AVAILABLE = False
    rg = None


class HolddownPosition(Enum):
    """Position of holddown relative to wall or panel."""
    LEFT = "left"           # Left end of wall/panel
    RIGHT = "right"         # Right end of wall/panel
    SPLICE = "splice"       # Panel splice point (interior connection)


@dataclass
class HolddownLocation:
    """
    Represents a holddown anchor location.

    Attributes:
        id: Unique identifier for this holddown
        wall_id: Parent wall ID
        panel_id: Panel ID (if panelized wall)
        position: Position type (left, right, splice)
        point: 3D point location for the holddown
        u_coordinate: Position along wall in U-coordinate (feet)
        elevation: Vertical position (typically at bottom plate)
        stud_width: Width of associated end stud (for centerline offset)
        is_load_bearing: Whether this is on a load-bearing wall
        capacity_required: Optional capacity requirement (lbs)
    """
    id: str
    wall_id: str
    panel_id: Optional[str]
    position: HolddownPosition
    point: Any  # rg.Point3d when Rhino available
    u_coordinate: float
    elevation: float
    stud_width: float = 0.125  # Default 1.5" = 0.125 ft
    is_load_bearing: bool = False
    capacity_required: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        point_dict = None
        if self.point is not None:
            if hasattr(self.point, 'X'):
                point_dict = {
                    "x": float(self.point.X),
                    "y": float(self.point.Y),
                    "z": float(self.point.Z),
                }
            elif isinstance(self.point, (list, tuple)) and len(self.point) >= 3:
                point_dict = {
                    "x": float(self.point[0]),
                    "y": float(self.point[1]),
                    "z": float(self.point[2]),
                }

        return {
            "id": self.id,
            "wall_id": self.wall_id,
            "panel_id": self.panel_id,
            "position": self.position.value,
            "point": point_dict,
            "u_coordinate": self.u_coordinate,
            "elevation": self.elevation,
            "stud_width": self.stud_width,
            "is_load_bearing": self.is_load_bearing,
            "capacity_required": self.capacity_required,
        }


def generate_holddown_locations(
    wall_data: Dict[str, Any],
    config: Dict[str, Any] = None,
    panels_data: List[Dict[str, Any]] = None
) -> List[HolddownLocation]:
    """
    Generate holddown locations for a wall.

    For non-panelized walls: generates holddowns at wall ends.
    For panelized walls: generates holddowns at panel ends and splice points.

    Args:
        wall_data: Wall geometry and properties including:
            - wall_id: Wall identifier
            - wall_length: Length in feet
            - wall_base_elevation: Base elevation
            - base_plane: Wall's base plane for positioning
            - is_load_bearing: Whether wall is structural
            - framing_config: Optional framing dimensions
        config: Optional configuration with:
            - stud_width: End stud width (default 0.125 ft = 1.5")
            - offset_from_end: Distance from wall end to holddown (default half stud)
            - include_splices: Whether to add holddowns at panel splices (default True)
        panels_data: Optional list of panel dictionaries for panelized walls

    Returns:
        List of HolddownLocation objects
    """
    config = config or {}
    holddowns = []

    # Get wall properties
    wall_id = str(wall_data.get("wall_id", "unknown"))
    wall_length = wall_data.get("wall_length", 0)
    base_elevation = wall_data.get("wall_base_elevation", 0)
    base_plane = wall_data.get("base_plane")
    is_load_bearing = wall_data.get("is_load_bearing", False)

    # Get configuration
    framing_config = wall_data.get("framing_config", {})
    stud_width = config.get("stud_width", framing_config.get("stud_width", 0.125))
    offset_from_end = config.get("offset_from_end", stud_width / 2)
    include_splices = config.get("include_splices", True)

    if wall_length <= 0:
        return holddowns

    # Generate holddowns based on whether wall is panelized
    if panels_data and len(panels_data) > 0:
        # Panelized wall: holddowns at panel boundaries
        holddowns = _generate_panelized_holddowns(
            wall_id=wall_id,
            wall_length=wall_length,
            base_elevation=base_elevation,
            base_plane=base_plane,
            is_load_bearing=is_load_bearing,
            stud_width=stud_width,
            offset_from_end=offset_from_end,
            include_splices=include_splices,
            panels_data=panels_data,
        )
    else:
        # Non-panelized wall: holddowns at wall ends only
        holddowns = _generate_wall_end_holddowns(
            wall_id=wall_id,
            wall_length=wall_length,
            base_elevation=base_elevation,
            base_plane=base_plane,
            is_load_bearing=is_load_bearing,
            stud_width=stud_width,
            offset_from_end=offset_from_end,
        )

    return holddowns


def _generate_wall_end_holddowns(
    wall_id: str,
    wall_length: float,
    base_elevation: float,
    base_plane: Any,
    is_load_bearing: bool,
    stud_width: float,
    offset_from_end: float,
) -> List[HolddownLocation]:
    """Generate holddowns at wall ends."""
    holddowns = []

    # Left end holddown (at u = offset_from_end)
    left_u = offset_from_end
    left_point = _calculate_point(base_plane, left_u, base_elevation)
    holddowns.append(HolddownLocation(
        id=f"{wall_id}_holddown_left",
        wall_id=wall_id,
        panel_id=None,
        position=HolddownPosition.LEFT,
        point=left_point,
        u_coordinate=left_u,
        elevation=base_elevation,
        stud_width=stud_width,
        is_load_bearing=is_load_bearing,
    ))

    # Right end holddown (at u = wall_length - offset_from_end)
    right_u = wall_length - offset_from_end
    right_point = _calculate_point(base_plane, right_u, base_elevation)
    holddowns.append(HolddownLocation(
        id=f"{wall_id}_holddown_right",
        wall_id=wall_id,
        panel_id=None,
        position=HolddownPosition.RIGHT,
        point=right_point,
        u_coordinate=right_u,
        elevation=base_elevation,
        stud_width=stud_width,
        is_load_bearing=is_load_bearing,
    ))

    return holddowns


def _generate_panelized_holddowns(
    wall_id: str,
    wall_length: float,
    base_elevation: float,
    base_plane: Any,
    is_load_bearing: bool,
    stud_width: float,
    offset_from_end: float,
    include_splices: bool,
    panels_data: List[Dict[str, Any]],
) -> List[HolddownLocation]:
    """Generate holddowns at panel boundaries."""
    holddowns = []

    # Sort panels by u_start position
    sorted_panels = sorted(panels_data, key=lambda p: p.get("u_start", 0))

    for i, panel in enumerate(sorted_panels):
        panel_id = panel.get("panel_id", f"panel_{i}")
        panel_u_start = panel.get("u_start", 0)
        panel_u_end = panel.get("u_end", wall_length)

        # Left holddown for this panel
        if i == 0:
            # First panel: left end of wall
            left_u = panel_u_start + offset_from_end
            position = HolddownPosition.LEFT
        else:
            # Interior panel: splice point
            if not include_splices:
                continue
            left_u = panel_u_start + offset_from_end
            position = HolddownPosition.SPLICE

        left_point = _calculate_point(base_plane, left_u, base_elevation)
        holddowns.append(HolddownLocation(
            id=f"{wall_id}_{panel_id}_holddown_left",
            wall_id=wall_id,
            panel_id=panel_id,
            position=position,
            point=left_point,
            u_coordinate=left_u,
            elevation=base_elevation,
            stud_width=stud_width,
            is_load_bearing=is_load_bearing,
        ))

        # Right holddown for last panel only (to avoid duplicates at splices)
        if i == len(sorted_panels) - 1:
            right_u = panel_u_end - offset_from_end
            right_point = _calculate_point(base_plane, right_u, base_elevation)
            holddowns.append(HolddownLocation(
                id=f"{wall_id}_{panel_id}_holddown_right",
                wall_id=wall_id,
                panel_id=panel_id,
                position=HolddownPosition.RIGHT,
                point=right_point,
                u_coordinate=right_u,
                elevation=base_elevation,
                stud_width=stud_width,
                is_load_bearing=is_load_bearing,
            ))

    return holddowns


def _calculate_point(base_plane: Any, u_coordinate: float, elevation: float) -> Any:
    """
    Calculate 3D point from base plane and coordinates.

    Args:
        base_plane: Wall's base plane
        u_coordinate: Position along wall (feet)
        elevation: Vertical position (feet)

    Returns:
        Point3d if Rhino available, tuple otherwise
    """
    if base_plane is None:
        # No plane available, return simple tuple
        return (u_coordinate, 0, elevation)

    if RHINO_AVAILABLE and hasattr(base_plane, 'PointAt'):
        # Use Plane.PointAt(u, v, w) where:
        # u = along wall (XAxis)
        # v = vertical (YAxis = World Z in our convention)
        # w = through wall (ZAxis = wall normal)
        # For holddowns, we want the point at wall centerline (w=0)
        # and at the bottom plate level (v from elevation)

        # Note: elevation is absolute, origin.Z is also absolute
        # We need v relative to the origin
        v_relative = elevation - base_plane.Origin.Z
        return base_plane.PointAt(u_coordinate, v_relative, 0)
    else:
        # Fallback for non-Rhino environment
        return (u_coordinate, 0, elevation)


def get_holddown_summary(holddowns: List[HolddownLocation]) -> Dict[str, Any]:
    """
    Generate summary statistics for holddown locations.

    Args:
        holddowns: List of HolddownLocation objects

    Returns:
        Dictionary with summary statistics
    """
    if not holddowns:
        return {
            "total_holddowns": 0,
            "wall_end_holddowns": 0,
            "splice_holddowns": 0,
            "load_bearing_count": 0,
        }

    wall_end_count = sum(
        1 for h in holddowns
        if h.position in (HolddownPosition.LEFT, HolddownPosition.RIGHT)
    )
    splice_count = sum(1 for h in holddowns if h.position == HolddownPosition.SPLICE)
    load_bearing_count = sum(1 for h in holddowns if h.is_load_bearing)

    return {
        "total_holddowns": len(holddowns),
        "wall_end_holddowns": wall_end_count,
        "splice_holddowns": splice_count,
        "load_bearing_count": load_bearing_count,
        "walls_with_holddowns": len(set(h.wall_id for h in holddowns)),
    }
