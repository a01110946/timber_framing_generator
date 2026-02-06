# File: src/timber_framing_generator/sheathing/sheathing_geometry.py
"""
Sheathing panel geometry creation.

Converts sheathing panel data (UVW coordinates) to 3D Brep geometry
with cutouts for openings. Uses RhinoCommonFactory for Grasshopper-compatible
geometry output.

Usage:
    from src.timber_framing_generator.sheathing.sheathing_geometry import (
        create_sheathing_breps,
        SheathingPanelGeometry
    )

    geometries = create_sheathing_breps(
        sheathing_data=parsed_sheathing_json,
        wall_data=parsed_wall_json,
        factory=get_factory()
    )
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class SheathingPanelGeometry:
    """
    Geometry data for a sheathing panel.

    Attributes:
        panel_id: Unique panel identifier
        wall_id: Parent wall ID
        face: Wall face ("exterior" or "interior")
        brep: RhinoCommon Brep geometry
        area_gross: Gross panel area (sq ft)
        area_net: Net area after cutouts (sq ft)
        has_cutouts: Whether panel has opening cutouts
    """
    panel_id: str
    wall_id: str
    face: str
    brep: Any  # RhinoCommon Brep
    area_gross: float
    area_net: float
    has_cutouts: bool


def uvw_to_world(
    u: float,
    v: float,
    w: float,
    base_plane: Dict[str, Any]
) -> Tuple[float, float, float]:
    """
    Transform UVW coordinates to world XYZ.

    The wall coordinate system:
    - U: Along wall length (wall's XAxis direction)
    - V: Vertical direction (world Z, up)
    - W: Through wall thickness (wall's ZAxis/normal direction)

    Args:
        u: Position along wall length (feet)
        v: Vertical position from wall base (feet)
        w: Offset through wall thickness (feet)
        base_plane: Wall base plane dictionary with origin, x_axis, y_axis, z_axis

    Returns:
        (x, y, z) world coordinates
    """
    origin = base_plane["origin"]
    x_axis = base_plane["x_axis"]
    y_axis = base_plane["y_axis"]
    z_axis = base_plane["z_axis"]

    # Transform: world = origin + u*X + v*Y + w*Z
    x = origin["x"] + x_axis["x"] * u + y_axis["x"] * v + z_axis["x"] * w
    y = origin["y"] + x_axis["y"] * u + y_axis["y"] * v + z_axis["y"] * w
    z = origin["z"] + x_axis["z"] * u + y_axis["z"] * v + z_axis["z"] * w

    return (x, y, z)


def get_extrusion_vector(
    face: str,
    base_plane: Dict[str, Any],
    thickness: float
) -> Tuple[float, float, float]:
    """
    Get the extrusion vector for panel thickness.

    Args:
        face: "exterior" or "interior"
        base_plane: Wall base plane dictionary
        thickness: Panel thickness in feet

    Returns:
        (dx, dy, dz) extrusion vector
    """
    z_axis = base_plane["z_axis"]

    # Exterior: extrude outward (positive normal direction)
    # Interior: extrude inward (negative normal direction)
    direction = 1.0 if face == "exterior" else -1.0

    return (
        z_axis["x"] * thickness * direction,
        z_axis["y"] * thickness * direction,
        z_axis["z"] * thickness * direction
    )


def calculate_w_offset(
    face: str,
    wall_thickness: float,
    panel_thickness: float,
    wall_assembly: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Calculate the W offset for panel placement.

    Panels are placed on the exterior or interior face of the wall,
    offset from the wall centerline. When assembly data is available,
    the offset is computed from the actual layer stack (core + exterior
    or core + interior thicknesses), which is more accurate for
    asymmetric assemblies.

    Args:
        face: "exterior" or "interior"
        wall_thickness: Wall thickness in feet (fallback)
        panel_thickness: Sheathing panel thickness in feet
        wall_assembly: Optional assembly dict from wall_data. When present,
            layer stack thicknesses are used instead of wall_thickness/2.

    Returns:
        W offset from wall centerline in feet
    """
    if wall_assembly:
        return _calculate_w_offset_from_assembly(
            face, wall_assembly, panel_thickness
        )

    # Fallback: simple half-thickness (symmetric assumption)
    half_wall = wall_thickness / 2.0

    if face == "exterior":
        # Exterior face: panel core-facing surface at wall outer face
        return half_wall
    else:
        # Interior face: panel core-facing surface at wall inner face
        # (mirrors exterior: extrusion in -Z places panel against wall)
        return -half_wall


def _calculate_w_offset_from_assembly(
    face: str,
    wall_assembly: Dict[str, Any],
    panel_thickness: float,
) -> float:
    """
    Calculate W offset from assembly layer stack.

    Uses the actual cumulative layer thicknesses from the wall assembly
    instead of dividing total thickness by 2. This produces correct
    positioning for asymmetric assemblies where exterior and interior
    layer thicknesses differ.

    The centerline (W=0) is at the center of the structural core.

    Args:
        face: "exterior" or "interior"
        wall_assembly: Assembly dictionary with "layers" list.
        panel_thickness: Sheathing panel thickness in feet.

    Returns:
        W offset from wall centerline in feet.
    """
    try:
        from src.timber_framing_generator.wall_data.assembly_extractor import (
            assembly_dict_to_def,
        )
        assembly_def = assembly_dict_to_def(wall_assembly)
    except Exception:
        # If conversion fails, fall back to total thickness
        total = sum(l.get("thickness", 0) for l in wall_assembly.get("layers", []))
        half = total / 2.0
        if face == "exterior":
            return half
        return -half

    core_half = assembly_def.core_thickness / 2.0

    if face == "exterior":
        # Panel starts at the wall's exterior face
        # = core center + half core + all exterior layers
        return core_half + assembly_def.exterior_thickness
    else:
        # Panel core-facing surface at wall's interior face
        # (mirrors exterior: extrusion in -Z places panel against wall)
        return -(core_half + assembly_def.interior_thickness)


def calculate_layer_w_offsets(
    wall_assembly: Dict[str, Any],
) -> Dict[str, float]:
    """
    Compute W offset for each layer's core-facing surface.

    Returns a dictionary mapping layer name to its W position where
    the layer starts (the face closest to the structural core).

    Useful for Phase 5 when placing individual layers (insulation,
    drywall, cladding) at their precise positions.

    Args:
        wall_assembly: Assembly dictionary with "layers" list.

    Returns:
        Dict mapping layer name to W offset (feet from centerline).
    """
    from src.timber_framing_generator.wall_data.assembly_extractor import (
        assembly_dict_to_def,
    )
    from src.timber_framing_generator.wall_junctions.junction_types import LayerSide

    assembly_def = assembly_dict_to_def(wall_assembly)
    offsets: Dict[str, float] = {}
    core_half = assembly_def.core_thickness / 2.0

    # Exterior layers: stack outward from core exterior face
    ext_layers = assembly_def.get_layers_by_side(LayerSide.EXTERIOR)
    cumulative = core_half
    for layer in reversed(ext_layers):  # closest to core first
        offsets[layer.name] = cumulative
        cumulative += layer.thickness

    # Interior layers: stack inward from core interior face
    int_layers = assembly_def.get_layers_by_side(LayerSide.INTERIOR)
    cumulative = -core_half
    for layer in int_layers:  # order from assembly (closest to core first)
        cumulative -= layer.thickness
        offsets[layer.name] = cumulative

    # Core layer
    core_layers = assembly_def.get_layers_by_side(LayerSide.CORE)
    for layer in core_layers:
        offsets[layer.name] = -core_half

    return offsets


def create_panel_brep(
    panel_data: Dict[str, Any],
    base_plane: Dict[str, Any],
    wall_thickness: float,
    factory: Any,
    wall_assembly: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """
    Create a Brep for a sheathing panel.

    Args:
        panel_data: Sheathing panel dictionary from sheathing_json
        base_plane: Wall's base plane (origin, x_axis, y_axis, z_axis)
        wall_thickness: Wall thickness in feet
        factory: RhinoCommonFactory instance
        wall_assembly: Optional assembly dict for layer-aware W offset

    Returns:
        RhinoCommon Brep or None if creation fails
    """
    # Extract panel bounds (UVW coordinates, in feet)
    u_start = panel_data["u_start"]
    u_end = panel_data["u_end"]
    v_start = panel_data["v_start"]
    v_end = panel_data["v_end"]

    # Panel thickness (convert inches to feet)
    thickness_ft = panel_data["thickness_inches"] / 12.0

    # Calculate W offset based on face (uses assembly when available)
    face = panel_data.get("face", "exterior")
    w_offset = calculate_w_offset(face, wall_thickness, thickness_ft, wall_assembly)

    # Create panel corners in world coordinates
    # Order: bottom-left, bottom-right, top-right, top-left (counter-clockwise)
    corners = [
        uvw_to_world(u_start, v_start, w_offset, base_plane),  # BL
        uvw_to_world(u_end, v_start, w_offset, base_plane),    # BR
        uvw_to_world(u_end, v_end, w_offset, base_plane),      # TR
        uvw_to_world(u_start, v_end, w_offset, base_plane),    # TL
    ]

    # Get extrusion vector (panel thickness direction)
    extrusion_vector = get_extrusion_vector(face, base_plane, thickness_ft)

    # Create box from corners and extrusion
    panel_brep = factory.create_box_from_corners_and_thickness(
        corners, extrusion_vector
    )

    if panel_brep is None:
        return None

    # Subtract cutouts if any
    cutouts = panel_data.get("cutouts", [])
    if cutouts:
        panel_brep = subtract_cutouts(
            panel_brep, cutouts, base_plane,
            w_offset, thickness_ft, face, factory
        )

    return panel_brep


def subtract_cutouts(
    panel_brep: Any,
    cutouts: List[Dict[str, Any]],
    base_plane: Dict[str, Any],
    w_offset: float,
    panel_thickness: float,
    face: str,
    factory: Any
) -> Any:
    """
    Subtract cutout regions from panel brep.

    Args:
        panel_brep: Base panel Brep
        cutouts: List of cutout dictionaries
        base_plane: Wall's base plane
        w_offset: W offset of panel face
        panel_thickness: Panel thickness in feet
        face: "exterior" or "interior"
        factory: RhinoCommonFactory instance

    Returns:
        Panel Brep with cutouts subtracted
    """
    cutout_breps = []

    for cutout in cutouts:
        cutout_brep = create_cutout_brep(
            cutout, base_plane, w_offset, panel_thickness, face, factory
        )
        if cutout_brep is not None:
            cutout_breps.append(cutout_brep)

    if cutout_breps:
        return factory.boolean_difference_multiple(panel_brep, cutout_breps)

    return panel_brep


def create_cutout_brep(
    cutout: Dict[str, Any],
    base_plane: Dict[str, Any],
    w_offset: float,
    panel_thickness: float,
    face: str,
    factory: Any
) -> Optional[Any]:
    """
    Create a Brep for a cutout region.

    The cutout extends slightly beyond the panel thickness to ensure
    a clean boolean difference.

    Args:
        cutout: Cutout dictionary with u_start, u_end, v_start, v_end
        base_plane: Wall's base plane
        w_offset: W offset of panel face
        panel_thickness: Panel thickness in feet
        face: "exterior" or "interior"
        factory: RhinoCommonFactory instance

    Returns:
        RhinoCommon Brep for cutout or None
    """
    u_start = cutout["u_start"]
    u_end = cutout["u_end"]
    v_start = cutout["v_start"]
    v_end = cutout["v_end"]

    # Validate dimensions
    if u_end <= u_start or v_end <= v_start:
        return None

    # Extend cutout slightly beyond panel surface for clean boolean
    tolerance = 0.01  # ~1/8 inch
    w_start = w_offset - tolerance
    w_end = w_offset + panel_thickness + tolerance
    if face == "interior":
        w_start = w_offset - panel_thickness - tolerance
        w_end = w_offset + tolerance

    # Create cutout corners
    corners = [
        uvw_to_world(u_start, v_start, w_start, base_plane),
        uvw_to_world(u_end, v_start, w_start, base_plane),
        uvw_to_world(u_end, v_end, w_start, base_plane),
        uvw_to_world(u_start, v_end, w_start, base_plane),
    ]

    # Extrusion vector through panel: always from w_start toward w_end (+Z).
    # Corners are placed at w_start (the more-negative W boundary), so the
    # extrusion must go in the +Z direction to reach w_end and fully
    # encompass the panel for both exterior and interior faces.
    extrusion_depth = abs(w_end - w_start)
    z_axis = base_plane["z_axis"]
    extrusion_vector = (
        z_axis["x"] * extrusion_depth,
        z_axis["y"] * extrusion_depth,
        z_axis["z"] * extrusion_depth,
    )

    return factory.create_box_from_corners_and_thickness(corners, extrusion_vector)


def create_sheathing_breps(
    sheathing_data: Dict[str, Any],
    wall_data: Dict[str, Any],
    factory: Any
) -> List[SheathingPanelGeometry]:
    """
    Create Brep geometry for all sheathing panels.

    Args:
        sheathing_data: Parsed sheathing JSON for a single wall
        wall_data: Parsed wall JSON with base_plane and thickness
        factory: RhinoCommonFactory instance

    Returns:
        List of SheathingPanelGeometry objects
    """
    results = []

    # Get wall properties
    base_plane = wall_data.get("base_plane", {})
    wall_thickness = wall_data.get("thickness", wall_data.get("wall_thickness", 0.5))

    # Handle different thickness keys (may be in inches or feet)
    if wall_thickness > 2.0:  # Likely in inches
        wall_thickness = wall_thickness / 12.0

    # Get assembly data for layer-aware W offset (Phase 3)
    wall_assembly = wall_data.get("wall_assembly")

    panels = sheathing_data.get("sheathing_panels", [])

    for panel_data in panels:
        brep = create_panel_brep(
            panel_data, base_plane, wall_thickness, factory, wall_assembly
        )

        if brep is not None:
            geometry = SheathingPanelGeometry(
                panel_id=panel_data.get("id", "unknown"),
                wall_id=panel_data.get("wall_id", "unknown"),
                face=panel_data.get("face", "exterior"),
                brep=brep,
                area_gross=panel_data.get("area_gross_sqft", 0),
                area_net=panel_data.get("area_net_sqft", 0),
                has_cutouts=len(panel_data.get("cutouts", [])) > 0
            )
            results.append(geometry)

    return results


def create_sheathing_breps_batch(
    sheathing_results: List[Dict[str, Any]],
    walls_data: List[Dict[str, Any]],
    factory: Any
) -> Dict[str, List[SheathingPanelGeometry]]:
    """
    Create Brep geometry for sheathing panels across multiple walls.

    Args:
        sheathing_results: List of sheathing JSON results (one per wall)
        walls_data: List of wall JSON data (one per wall)
        factory: RhinoCommonFactory instance

    Returns:
        Dictionary mapping wall_id to list of SheathingPanelGeometry
    """
    # Index walls by ID
    walls_by_id = {}
    for wall in walls_data:
        wall_id = str(wall.get("wall_id", wall.get("id", "unknown")))
        walls_by_id[wall_id] = wall

    results = {}

    for sheathing_data in sheathing_results:
        wall_id = str(sheathing_data.get("wall_id", "unknown"))
        wall_data = walls_by_id.get(wall_id, {})

        # Provide default base plane if not present
        if "base_plane" not in wall_data:
            wall_data["base_plane"] = _create_default_base_plane()

        geometries = create_sheathing_breps(sheathing_data, wall_data, factory)

        if wall_id not in results:
            results[wall_id] = []
        results[wall_id].extend(geometries)

    return results


def _create_default_base_plane() -> Dict[str, Any]:
    """Create a default world-aligned base plane."""
    return {
        "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
        "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
        "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},  # V = World Z
        "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},  # W = World Y (into wall)
    }
