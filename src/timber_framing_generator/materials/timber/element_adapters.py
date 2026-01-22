# File: src/timber_framing_generator/materials/timber/element_adapters.py
"""
Adapter functions to convert existing Brep-based framing elements
to FramingElement data objects for JSON serialization.

This module bridges the gap between the existing generators that produce
Rhino geometry (Breps) and the new strategy pattern that requires
FramingElement data objects.

Usage:
    from src.timber_framing_generator.materials.timber.element_adapters import (
        plate_geometry_to_framing_element,
        brep_to_framing_element,
        reconstruct_wall_data,
    )

Note:
    Rhino.Geometry is imported conditionally to allow unit testing
    outside of the Rhino/Grasshopper environment.
"""

from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING

from src.timber_framing_generator.core.material_system import (
    ElementType,
    ElementProfile,
    FramingElement,
)

# Conditional import for Rhino geometry - allows testing outside Grasshopper
try:
    import Rhino.Geometry as rg
    from src.timber_framing_generator.utils.safe_rhino import safe_get_bounding_box
    RHINO_AVAILABLE = True
except ImportError:
    RHINO_AVAILABLE = False
    rg = None  # type: ignore


def reconstruct_wall_data(wall_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct Rhino geometry from JSON wall_data.

    The JSON wall_data contains serialized geometry that needs to be
    converted back to live Rhino objects for use with existing generators.

    Args:
        wall_data: Dictionary from JSON with serialized geometry

    Returns:
        Dictionary with reconstructed Rhino geometry objects

    Raises:
        RuntimeError: If Rhino is not available (running outside Grasshopper)

    Example:
        JSON input has:
            base_plane: {origin: {x,y,z}, x_axis: {...}, y_axis: {...}, z_axis: {...}}
            base_curve_start: {x, y, z}
            base_curve_end: {x, y, z}

        Output has:
            base_plane: rg.Plane
            wall_base_curve: rg.LineCurve
    """
    if not RHINO_AVAILABLE:
        raise RuntimeError(
            "Rhino.Geometry is not available. "
            "This function must be called from within Grasshopper/Rhino."
        )

    result = dict(wall_data)  # Copy original data

    # Reconstruct base plane
    plane_data = wall_data.get("base_plane", {})
    if isinstance(plane_data, dict):
        origin = plane_data.get("origin", {})
        x_axis = plane_data.get("x_axis", {})
        y_axis = plane_data.get("y_axis", {})

        # Handle nested dict format or direct values
        if isinstance(origin, dict):
            origin_pt = rg.Point3d(
                origin.get("x", 0),
                origin.get("y", 0),
                origin.get("z", 0)
            )
            x_vec = rg.Vector3d(
                x_axis.get("x", 1),
                x_axis.get("y", 0),
                x_axis.get("z", 0)
            )
            y_vec = rg.Vector3d(
                y_axis.get("x", 0),
                y_axis.get("y", 1),
                y_axis.get("z", 0)
            )
            result["base_plane"] = rg.Plane(origin_pt, x_vec, y_vec)
    elif isinstance(plane_data, rg.Plane):
        # Already a Plane object
        result["base_plane"] = plane_data

    # Reconstruct base curve from start/end points
    curve_start = wall_data.get("base_curve_start", {})
    curve_end = wall_data.get("base_curve_end", {})

    if isinstance(curve_start, dict) and isinstance(curve_end, dict):
        start_pt = rg.Point3d(
            curve_start.get("x", 0),
            curve_start.get("y", 0),
            curve_start.get("z", 0)
        )
        end_pt = rg.Point3d(
            curve_end.get("x", 0),
            curve_end.get("y", wall_data.get("wall_length", 10)),
            curve_end.get("z", 0)
        )
        result["wall_base_curve"] = rg.LineCurve(start_pt, end_pt)
    elif "wall_base_curve" not in result:
        # Create default curve along X axis
        base_plane = result.get("base_plane", rg.Plane.WorldXY)
        wall_length = wall_data.get("wall_length", 10)
        start_pt = base_plane.Origin
        end_pt = rg.Point3d.Add(
            start_pt,
            rg.Vector3d.Multiply(base_plane.XAxis, wall_length)
        )
        result["wall_base_curve"] = rg.LineCurve(start_pt, end_pt)

    # Map JSON keys to expected keys for existing generators
    result["wall_base_elevation"] = wall_data.get("base_elevation", 0)
    result["wall_top_elevation"] = wall_data.get("top_elevation",
                                                  wall_data.get("base_elevation", 0) +
                                                  wall_data.get("wall_height", 8))
    result["wall_type"] = wall_data.get("wall_type", "2x4")
    result["wall_length"] = wall_data.get("wall_length", 10)
    result["wall_height"] = wall_data.get("wall_height", 8)

    # Create WBC (Wall Boundary Cell) with corner_points - required by plate generator
    # The WBC defines the full wall boundary as 4 corner points
    base_plane = result.get("base_plane", rg.Plane.WorldXY)
    wall_length = result["wall_length"]
    wall_height = result["wall_height"]
    base_elevation = result["wall_base_elevation"]

    # Calculate corner points in world coordinates
    # The wall lies along the base_plane's X axis
    origin = base_plane.Origin

    # Bottom-left: origin
    bl = rg.Point3d(origin.X, origin.Y, base_elevation)
    # Bottom-right: origin + wall_length along X axis
    br = rg.Point3d.Add(
        rg.Point3d(origin.X, origin.Y, base_elevation),
        rg.Vector3d.Multiply(base_plane.XAxis, wall_length)
    )
    # Top-right: bottom-right + wall_height in Z
    tr = rg.Point3d(br.X, br.Y, base_elevation + wall_height)
    # Top-left: bottom-left + wall_height in Z
    tl = rg.Point3d(bl.X, bl.Y, base_elevation + wall_height)

    wbc_cell = {
        "cell_type": "WBC",
        "corner_points": [bl, br, tr, tl],
        "u_start": 0,
        "u_end": wall_length,
        "v_start": 0,
        "v_end": wall_height,
    }

    # Ensure cells list exists and contains WBC
    existing_cells = result.get("cells", [])

    # Normalize cell data format - existing generators expect "type" but JSON has "cell_type"
    normalized_cells = []
    for cell in existing_cells:
        if isinstance(cell, dict):
            normalized_cell = dict(cell)
            # Map "cell_type" to "type" for backward compatibility with generators
            if "cell_type" in normalized_cell and "type" not in normalized_cell:
                normalized_cell["type"] = normalized_cell["cell_type"]
            normalized_cells.append(normalized_cell)
        else:
            normalized_cells.append(cell)

    # Check if WBC already exists
    has_wbc = any(c.get("cell_type") == "WBC" or c.get("type") == "WBC"
                  for c in normalized_cells if isinstance(c, dict))
    if not has_wbc:
        result["cells"] = [wbc_cell] + normalized_cells
    else:
        result["cells"] = normalized_cells

    # Convert openings to expected format if needed
    openings = wall_data.get("openings", [])
    converted_openings = []
    for opening in openings:
        converted = dict(opening)
        # Map JSON schema keys to generator-expected keys
        if "u_start" in opening and "start_u_coordinate" not in opening:
            converted["start_u_coordinate"] = opening["u_start"]
        if "u_end" in opening and "rough_width" not in opening:
            converted["rough_width"] = opening["u_end"] - opening["u_start"]
        if "v_start" in opening and "base_elevation_relative_to_wall_base" not in opening:
            converted["base_elevation_relative_to_wall_base"] = opening["v_start"]
        if "v_end" in opening and "rough_height" not in opening:
            converted["rough_height"] = opening["v_end"] - opening.get("v_start", 0)
        if "opening_type" not in converted:
            converted["opening_type"] = opening.get("type", "window")
        converted_openings.append(converted)
    result["openings"] = converted_openings

    return result


def plate_geometry_to_framing_element(
    plate,  # PlateGeometry object
    element_id: str,
    element_type: ElementType,
    profile: ElementProfile,
    base_plane: rg.Plane,
    cell_id: str = None
) -> FramingElement:
    """
    Convert a PlateGeometry object to a FramingElement.

    Args:
        plate: PlateGeometry object from create_plates()
        element_id: Unique identifier for this element
        element_type: BOTTOM_PLATE or TOP_PLATE
        profile: ElementProfile for this plate
        base_plane: Wall's base plane for coordinate calculations
        cell_id: Optional cell identifier

    Returns:
        FramingElement with centerline and positional data
    """
    # Get centerline from plate geometry
    centerline = plate.centerline
    start_pt = centerline.PointAtStart
    end_pt = centerline.PointAtEnd

    # Calculate u_coord (position along wall) - for plates, typically 0 or wall_length/2
    # Plates run the full length, so u_coord is at the center
    u_start = _project_to_u(start_pt, base_plane)
    u_end = _project_to_u(end_pt, base_plane)
    u_coord = (u_start + u_end) / 2

    # Get v_start and v_end from elevation data
    boundary_data = plate.get_boundary_data()
    # For plates, v is the vertical position
    v_center = start_pt.Z
    half_thickness = plate.parameters.thickness / 2

    return FramingElement(
        id=element_id,
        element_type=element_type,
        profile=profile,
        centerline_start=(start_pt.X, start_pt.Y, start_pt.Z),
        centerline_end=(end_pt.X, end_pt.Y, end_pt.Z),
        u_coord=u_coord,
        v_start=v_center - half_thickness,
        v_end=v_center + half_thickness,
        cell_id=cell_id,
        metadata={
            "plate_type": plate.parameters.plate_type,
            "boundary_elevation": boundary_data["boundary_elevation"],
            "reference_elevation": boundary_data["reference_elevation"],
        }
    )


def brep_to_framing_element(
    brep: rg.Brep,
    element_id: str,
    element_type: ElementType,
    profile: ElementProfile,
    base_plane: rg.Plane,
    is_vertical: bool = True,
    cell_id: str = None
) -> Optional[FramingElement]:
    """
    Convert a Brep geometry to a FramingElement by extracting centerline.

    Args:
        brep: Rhino Brep geometry
        element_id: Unique identifier for this element
        element_type: Type of framing element
        profile: ElementProfile for this element
        base_plane: Wall's base plane for coordinate calculations
        is_vertical: True for studs (vertical), False for horizontal members
        cell_id: Optional cell identifier

    Returns:
        FramingElement with centerline data, or None if extraction fails
    """
    if brep is None or not brep.IsValid:
        return None

    bbox = safe_get_bounding_box(brep, True)
    if not bbox.IsValid:
        return None

    # Calculate centerline based on orientation
    if is_vertical:
        # Vertical members: centerline runs from bottom center to top center
        center_x = (bbox.Min.X + bbox.Max.X) / 2
        center_y = (bbox.Min.Y + bbox.Max.Y) / 2

        start_pt = rg.Point3d(center_x, center_y, bbox.Min.Z)
        end_pt = rg.Point3d(center_x, center_y, bbox.Max.Z)

        # u_coord is horizontal position along wall
        u_coord = _project_to_u(start_pt, base_plane)
        v_start = bbox.Min.Z
        v_end = bbox.Max.Z
    else:
        # Horizontal members: centerline runs along length
        # Determine which axis is the length direction
        dx = bbox.Max.X - bbox.Min.X
        dy = bbox.Max.Y - bbox.Min.Y
        dz = bbox.Max.Z - bbox.Min.Z

        center_z = (bbox.Min.Z + bbox.Max.Z) / 2

        if dx >= dy and dx >= dz:
            # Length along X
            start_pt = rg.Point3d(bbox.Min.X, (bbox.Min.Y + bbox.Max.Y) / 2, center_z)
            end_pt = rg.Point3d(bbox.Max.X, (bbox.Min.Y + bbox.Max.Y) / 2, center_z)
        elif dy >= dx and dy >= dz:
            # Length along Y
            start_pt = rg.Point3d((bbox.Min.X + bbox.Max.X) / 2, bbox.Min.Y, center_z)
            end_pt = rg.Point3d((bbox.Min.X + bbox.Max.X) / 2, bbox.Max.Y, center_z)
        else:
            # Length along Z (unusual for horizontal, but handle it)
            start_pt = rg.Point3d((bbox.Min.X + bbox.Max.X) / 2, (bbox.Min.Y + bbox.Max.Y) / 2, bbox.Min.Z)
            end_pt = rg.Point3d((bbox.Min.X + bbox.Max.X) / 2, (bbox.Min.Y + bbox.Max.Y) / 2, bbox.Max.Z)

        # For horizontal members, u_coord is typically at center
        u_start = _project_to_u(start_pt, base_plane)
        u_end = _project_to_u(end_pt, base_plane)
        u_coord = (u_start + u_end) / 2
        v_start = center_z - profile.width / 2
        v_end = center_z + profile.width / 2

    return FramingElement(
        id=element_id,
        element_type=element_type,
        profile=profile,
        centerline_start=(start_pt.X, start_pt.Y, start_pt.Z),
        centerline_end=(end_pt.X, end_pt.Y, end_pt.Z),
        u_coord=u_coord,
        v_start=v_start,
        v_end=v_end,
        cell_id=cell_id,
        metadata={}
    )


def normalize_cells(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize cell data format for compatibility with existing generators.

    The JSON cell data uses "cell_type" key but existing generators expect "type".
    This function normalizes the cell data by adding the "type" key.

    Args:
        cells: List of cell dictionaries from JSON

    Returns:
        List of normalized cell dictionaries with both "type" and "cell_type" keys
    """
    print(f"\n=== normalize_cells DEBUG ===")
    print(f"Input cells count: {len(cells)}")

    normalized_cells = []
    for i, cell in enumerate(cells):
        print(f"  Cell {i}: type={type(cell).__name__}")
        if isinstance(cell, dict):
            normalized_cell = dict(cell)
            original_cell_type = normalized_cell.get("cell_type", "N/A")
            original_type = normalized_cell.get("type", "N/A")
            print(f"    Before: cell_type='{original_cell_type}', type='{original_type}'")

            # Map "cell_type" to "type" for backward compatibility with generators
            if "cell_type" in normalized_cell and "type" not in normalized_cell:
                normalized_cell["type"] = normalized_cell["cell_type"]
                print(f"    After: Added type='{normalized_cell['type']}'")
            else:
                print(f"    After: No change needed (already has 'type' or no 'cell_type')")

            normalized_cells.append(normalized_cell)
        else:
            print(f"    WARNING: Cell is not a dict, skipping normalization")
            normalized_cells.append(cell)

    print(f"Output cells count: {len(normalized_cells)}")
    print(f"=== END normalize_cells DEBUG ===\n")
    return normalized_cells


def _project_to_u(point: rg.Point3d, base_plane: rg.Plane) -> float:
    """
    Project a 3D point onto the wall's u-axis to get its u-coordinate.

    Args:
        point: The 3D point to project
        base_plane: The wall's base plane

    Returns:
        The u-coordinate (distance along wall from origin)
    """
    vec = point - base_plane.Origin
    return vec * base_plane.XAxis
