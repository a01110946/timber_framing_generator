# File: timber_framing_generator/framing_elements/timber_element.py

from typing import Dict, Union, List, Optional
import Rhino.Geometry as rg

# --- Default Framing Parameters (Move to config.py later) ---
FRAMING_PARAMS = {
    "stud_width": 3.5,  # Example default
    "stud_depth": 1.5,  # Example default
    "plate_thickness": 3.5,  # Example default
    "top_plate_layers": 1,
    "bottom_plate_layers": 1,
    "header_width": 5.5,
    "header_depth": 1.5,
    "sill_width": 3.5,
    "sill_depth": 1.5,
    "trimmer_offset": 0.5,  # Offset for trimmer from opening.  Adjust as needed.
    "king_stud_offset": 0.5,  # Offset for king stud from trimmer. Adjust.
}

# --- Helper functions ---
def _create_line_curve(start_point: rg.Point3d, end_point: rg.Point3d) -> rg.LineCurve:
    """Creates a LineCurve from two points (helper function)."""
    return rg.LineCurve(rg.Line(start_point, end_point))


def _get_point_at_uv(
    cell_data: Dict, u_fraction: float, v_fraction: float
) -> rg.Point3d:
    """Gets a 3D point within a cell based on UV fractions (helper)."""
    corner_points = cell_data["corner_points"]
    # Assuming corner_points are in order: [bottom-left, bottom-right, top-right, top-left]
    pt_bl = corner_points[0]
    pt_br = corner_points[1]
    pt_tr = corner_points[2]
    pt_tl = corner_points[3]

    # Interpolate along the bottom edge (U direction)
    bottom_point = pt_bl + (pt_br - pt_bl) * u_fraction

    # Interpolate along the top edge (U direction)
    top_point = pt_tl + (pt_tr - pt_tl) * u_fraction

    # Interpolate between bottom and top (V direction)
    interpolated_point = bottom_point + (top_point - bottom_point) * v_fraction

    return interpolated_point


# --- Stud Creation ---
def create_stud(
    cell_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a stud (centerline) from a Stud Cell (SC)."""
    # Parameter handling (use provided values, defaults, or profile)
    if profile:
        stud_width = profile.Width
        stud_depth = profile.Height  # Assuming profile is oriented correctly
    else:
        stud_width = (
            stud_width if stud_width is not None else FRAMING_PARAMS["stud_width"]
        )
        stud_depth = (
            stud_depth if stud_depth is not None else FRAMING_PARAMS["stud_depth"]
        )

    # Get the center point of the cell (U=0.5, V=0.5)
    center_point = _get_point_at_uv(cell_data, 0.5, 0.5)
    pt1 = _get_point_at_uv(cell_data, 0.5, 0)  # Bottom center
    pt2 = _get_point_at_uv(cell_data, 0.5, 1)  # Top center

    return _create_line_curve(pt1, pt2)


# --- Sill Cripple Creation ---
def create_sill_cripple(
    cell_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a sill cripple (centerline) from a Sill Cripple Cell (SCC)."""
    return create_stud(
        cell_data, stud_width, stud_depth, profile
    )  # Reuse stud creation


# --- Header Cripple Creation ---
def create_header_cripple(
    cell_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a header cripple (centerline) from a Header Cripple Cell (HCC)."""
    return create_stud(cell_data, stud_width, stud_depth, profile)


# --- King Stud Creation ---
def create_king_stud(
    opening_cell_data: Dict,
    wall_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> List[rg.Curve]:
    """Creates king studs on either side of an opening."""
    if profile:
        stud_width = profile.Width
        stud_depth = profile.Height
    else:
        stud_width = (
            stud_width if stud_width is not None else FRAMING_PARAMS["stud_width"]
        )
        stud_depth = (
            stud_depth if stud_depth is not None else FRAMING_PARAMS["stud_depth"]
        )

    base_plane = wall_data["base_plane"]
    king_studs = []

    # Left King Stud
    u_left = (
        opening_cell_data["u_start"]
        - FRAMING_PARAMS["trimmer_offset"]
        - FRAMING_PARAMS["king_stud_offset"]
        - stud_width
    )  # Offset to the *left*
    v_start = opening_cell_data["v_start"]
    v_end = opening_cell_data["v_end"]

    pt_start_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_start
    )
    pt_end_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    king_studs.append(_create_line_curve(pt_start_left, pt_end_left))

    # Right King Stud
    u_right = (
        opening_cell_data["u_end"]
        + FRAMING_PARAMS["trimmer_offset"]
        + FRAMING_PARAMS["king_stud_offset"]
    )  # Offset to the *right*
    pt_start_right = rg.Point3d(
        base_plane.Origin.X + u_right,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start,
    )
    pt_end_right = rg.Point3d(
        base_plane.Origin.X + u_right, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    king_studs.append(_create_line_curve(pt_start_right, pt_end_right))

    return king_studs


# --- Trimmer Stud Creation ---
def create_trimmer_stud(
    opening_cell_data: Dict,
    wall_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> List[rg.Curve]:
    """Creates trimmer studs on either side of an opening."""
    if profile:
        stud_width = profile.Width
        stud_depth = profile.Height
    else:
        stud_width = (
            stud_width if stud_width is not None else FRAMING_PARAMS["stud_width"]
        )
        stud_depth = (
            stud_depth if stud_depth is not None else FRAMING_PARAMS["stud_depth"]
        )

    base_plane = wall_data["base_plane"]
    trimmer_studs = []

    # Left trimmer Stud
    u_left = (
        opening_cell_data["u_start"] - FRAMING_PARAMS["trimmer_offset"] - stud_width / 2
    )  # Offset to the *left*
    v_start = opening_cell_data["v_start"]
    v_end = opening_cell_data["v_end"]
    pt_start_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_start
    )
    pt_end_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    trimmer_studs.append(_create_line_curve(pt_start_left, pt_end_left))

    # Right trimmer Stud
    u_right = (
        opening_cell_data["u_end"] + FRAMING_PARAMS["trimmer_offset"] + stud_width / 2
    )  # Offset to the *right*
    pt_start_right = rg.Point3d(
        base_plane.Origin.X + u_right,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start,
    )
    pt_end_right = rg.Point3d(
        base_plane.Origin.X + u_right, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    trimmer_studs.append(_create_line_curve(pt_start_right, pt_end_right))

    return trimmer_studs


# --- Header Creation ---
def create_header(
    opening_data: Dict,
    wall_data: Dict,
    header_width: Optional[float] = None,
    header_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a header (centerline) above an opening."""
    if profile:
        header_width = profile.Width
        header_depth = profile.Height
    else:
        header_width = (
            header_width if header_width is not None else FRAMING_PARAMS["header_width"]
        )
        header_depth = (
            header_depth if header_depth is not None else FRAMING_PARAMS["header_depth"]
        )

    base_plane = wall_data["base_plane"]
    start_u = opening_data["start_u_coordinate"]
    rough_width = opening_data["rough_width"]
    end_u = start_u + rough_width
    v_start = (
        opening_data["base_elevation_relative_to_wall_base"]
        + opening_data["rough_height"]
    )  # Top of opening

    # For now, simple header along the U direction at the opening's top.
    pt_start = rg.Point3d(
        base_plane.Origin.X + start_u,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start,
    )
    pt_end = rg.Point3d(
        base_plane.Origin.X + end_u, base_plane.Origin.Y, base_plane.Origin.Z + v_start
    )

    return _create_line_curve(pt_start, pt_end)


# --- Sill Creation ---
def create_sill(
    opening_data: Dict,
    wall_data: Dict,
    sill_width: Optional[float] = None,
    sill_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a sill (centerline) below an opening."""
    if profile:
        sill_width = profile.Width
        sill_depth = profile.Height
    else:
        sill_width = (
            sill_width if sill_width is not None else FRAMING_PARAMS["sill_width"]
        )
        sill_depth = (
            sill_depth if sill_depth is not None else FRAMING_PARAMS["sill_depth"]
        )

    base_plane = wall_data["base_plane"]
    start_u = opening_data["start_u_coordinate"]
    rough_width = opening_data["rough_width"]
    end_u = start_u + rough_width
    v_start = opening_data["base_elevation_relative_to_wall_base"]  # Bottom of opening

    pt_start = rg.Point3d(
        base_plane.Origin.X + start_u,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start,
    )
    pt_end = rg.Point3d(
        base_plane.Origin.X + end_u, base_plane.Origin.Y, base_plane.Origin.Z + v_start
    )

    return _create_line_curve(pt_start, pt_end)


# --- Top Plate Creation ---
def create_top_plate(
    wall_data: Dict,
    top_plate_layers: Optional[int] = None,
    plate_width: Optional[float] = None,
    plate_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> List[rg.Curve]:
    """
    Create top plate curves from the wall's base curve at a given elevation.
    """
    if profile:
        plate_width = profile.Width
        plate_depth = profile.Height
    else:
        plate_width = (
            plate_width if plate_width is not None else FRAMING_PARAMS["stud_width"]
        )
        plate_depth = (
            plate_depth
            if plate_depth is not None
            else FRAMING_PARAMS["plate_thickness"]
        )

    top_plate_layers = (
        top_plate_layers
        if top_plate_layers is not None
        else FRAMING_PARAMS["top_plate_layers"]
    )
    base_curve = wall_data["wall_base_curve"]
    elevation = wall_data["wall_top_elevation"]

    plates = []
    if top_plate_layers == 1:
        # Single top plate: offset downward by half the plate thickness
        translation = rg.Vector3d(0, 0, elevation - plate_depth / 2)
        plate = base_curve.DuplicateCurve()
        plate.Translate(translation)
        plates.append(plate)
    elif top_plate_layers == 2:
        # Two layers: cap plate centered at elevation - plate_thickness/2,
        # and top plate centered at elevation - 3*plate_thickness/2.
        translation1 = rg.Vector3d(0, 0, elevation - plate_depth / 2)
        plate1 = base_curve.DuplicateCurve()
        plate1.Translate(translation1)

        translation2 = rg.Vector3d(0, 0, elevation - 3 * plate_depth / 2)
        plate2 = base_curve.DuplicateCurve()
        plate2.Translate(translation2)

        plates.extend([plate1, plate2])
    else:
        raise ValueError(
            "Unsupported number of top plate layers: {}".format(top_plate_layers)
        )
    return plates


# --- Bottom Plate Creation ---
def create_bottom_plate(
    wall_data: Dict,
    bottom_plate_layers: Optional[int] = None,
    plate_width: Optional[float] = None,
    plate_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> List[rg.Curve]:
    """
    Create bottom plate curves from the wall's base curve at a given elevation.
    """
    if profile:
        plate_width = profile.Width
        plate_depth = profile.Height
    else:
        plate_width = (
            plate_width if plate_width is not None else FRAMING_PARAMS["stud_width"]
        )
        plate_depth = (
            plate_depth
            if plate_depth is not None
            else FRAMING_PARAMS["plate_thickness"]
        )

    bottom_plate_layers = (
        bottom_plate_layers
        if bottom_plate_layers is not None
        else FRAMING_PARAMS["bottom_plate_layers"]
    )
    base_curve = wall_data["wall_base_curve"]
    elevation = wall_data["wall_base_elevation"]

    plates = []
    if bottom_plate_layers == 1:
        # Single bottom plate: offset upward by half the plate thickness.
        translation = rg.Vector3d(0, 0, elevation + plate_depth / 2)
        plate = base_curve.DuplicateCurve()
        plate.Translate(translation)
        plates.append(plate)
    elif bottom_plate_layers == 2:
        # Two layers: first plate offset by half the plate thickness,
        # second (cap) plate offset by 1.5 times the plate thickness upward.
        translation1 = rg.Vector3d(0, 0, elevation + plate_depth / 2)
        plate1 = base_curve.DuplicateCurve()
        plate1.Translate(translation1)

        translation2 = rg.Vector3d(0, 0, elevation + 3 * plate_depth / 2)
        plate2 = base_curve.DuplicateCurve()
        plate2.Translate(translation2)

        plates.extend([plate1, plate2])
    else:
        raise ValueError(
            "Unsupported number of bottom plate layers: {}".format(bottom_plate_layers)
        )
    return plates
