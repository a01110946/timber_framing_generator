# File: timber_framing_generator/framing_elements/timber_element.py

from typing import Dict, Union, List, Optional
import Rhino.Geometry as rg
from src.timber_framing_generator.utils.safe_rhino import safe_get_length

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)

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
    logger.trace(f"Creating line curve from ({start_point.X}, {start_point.Y}, {start_point.Z}) to ({end_point.X}, {end_point.Y}, {end_point.Z})")
    return rg.LineCurve(rg.Line(start_point, end_point))


def _get_point_at_uv(
    cell_data: Dict, u_fraction: float, v_fraction: float
) -> rg.Point3d:
    """Gets a 3D point within a cell based on UV fractions (helper)."""
    logger.trace(f"Getting point at UV: ({u_fraction}, {v_fraction})")
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

    logger.trace(f"Calculated point: ({interpolated_point.X}, {interpolated_point.Y}, {interpolated_point.Z})")
    return interpolated_point


# --- Stud Creation ---
def create_stud(
    cell_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a stud (centerline) from a Stud Cell (SC)."""
    logger.debug("Creating stud from cell data")
    
    # Parameter handling (use provided values, defaults, or profile)
    if profile:
        logger.debug("Using provided profile for stud dimensions")
        stud_width = profile.Width
        stud_depth = profile.Height  # Assuming profile is oriented correctly
        logger.trace(f"Profile dimensions: width={stud_width}, height={stud_depth}")
    else:
        stud_width = (
            stud_width if stud_width is not None else FRAMING_PARAMS["stud_width"]
        )
        stud_depth = (
            stud_depth if stud_depth is not None else FRAMING_PARAMS["stud_depth"]
        )
        logger.trace(f"Using stud dimensions: width={stud_width}, depth={stud_depth}")

    # Get the center point of the cell (U=0.5, V=0.5)
    logger.trace("Calculating stud centerline points")
    center_point = _get_point_at_uv(cell_data, 0.5, 0.5)
    pt1 = _get_point_at_uv(cell_data, 0.5, 0)  # Bottom center
    pt2 = _get_point_at_uv(cell_data, 0.5, 1)  # Top center
    
    logger.trace(f"Stud bottom point: ({pt1.X}, {pt1.Y}, {pt1.Z})")
    logger.trace(f"Stud top point: ({pt2.X}, {pt2.Y}, {pt2.Z})")
    logger.trace(f"Stud height: {pt2.DistanceTo(pt1)}")

    return _create_line_curve(pt1, pt2)


# --- Sill Cripple Creation ---
def create_sill_cripple(
    cell_data: Dict,
    stud_width: Optional[float] = None,
    stud_depth: Optional[float] = None,
    profile: Optional[rg.Rectangle3d] = None,
) -> rg.Curve:
    """Creates a sill cripple (centerline) from a Sill Cripple Cell (SCC)."""
    logger.debug("Creating sill cripple from cell data")
    logger.trace(f"Cell data UV range: {cell_data.get('u_start', 'N/A')}-{cell_data.get('u_end', 'N/A')}, {cell_data.get('v_start', 'N/A')}-{cell_data.get('v_end', 'N/A')}")
    
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
    logger.debug("Creating header cripple from cell data")
    logger.trace(f"Cell data UV range: {cell_data.get('u_start', 'N/A')}-{cell_data.get('u_end', 'N/A')}, {cell_data.get('v_start', 'N/A')}-{cell_data.get('v_end', 'N/A')}")
    
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
    logger.debug("Creating king studs for opening")
    logger.trace(f"Opening cell data: {opening_cell_data}")
    
    if profile:
        logger.debug("Using provided profile for king stud dimensions")
        stud_width = profile.Width
        stud_depth = profile.Height
        logger.trace(f"Profile dimensions: width={stud_width}, height={stud_depth}")
    else:
        stud_width = (
            stud_width if stud_width is not None else FRAMING_PARAMS["stud_width"]
        )
        stud_depth = (
            stud_depth if stud_depth is not None else FRAMING_PARAMS["stud_depth"]
        )
        logger.trace(f"Using king stud dimensions: width={stud_width}, depth={stud_depth}")

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
    
    logger.trace(f"Left king stud position: u={u_left}, v_range={v_start}-{v_end}")

    pt_start_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_start
    )
    pt_end_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    logger.trace(f"Left king stud start: ({pt_start_left.X}, {pt_start_left.Y}, {pt_start_left.Z})")
    logger.trace(f"Left king stud end: ({pt_end_left.X}, {pt_end_left.Y}, {pt_end_left.Z})")
    
    king_studs.append(_create_line_curve(pt_start_left, pt_end_left))

    # Right King Stud
    u_right = (
        opening_cell_data["u_end"]
        + FRAMING_PARAMS["trimmer_offset"]
        + FRAMING_PARAMS["king_stud_offset"]
    )  # Offset to the *right*
    
    logger.trace(f"Right king stud position: u={u_right}, v_range={v_start}-{v_end}")
    
    pt_start_right = rg.Point3d(
        base_plane.Origin.X + u_right,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start,
    )
    pt_end_right = rg.Point3d(
        base_plane.Origin.X + u_right, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    logger.trace(f"Right king stud start: ({pt_start_right.X}, {pt_start_right.Y}, {pt_start_right.Z})")
    logger.trace(f"Right king stud end: ({pt_end_right.X}, {pt_end_right.Y}, {pt_end_right.Z})")
    
    king_studs.append(_create_line_curve(pt_start_right, pt_end_right))
    
    logger.debug(f"Created {len(king_studs)} king studs")
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
    logger.debug("Creating trimmer studs for opening")
    logger.trace(f"Opening cell data: {opening_cell_data}")
    
    if profile:
        logger.debug("Using provided profile for trimmer dimensions")
        stud_width = profile.Width
        stud_depth = profile.Height
        logger.trace(f"Profile dimensions: width={stud_width}, height={stud_depth}")
    else:
        stud_width = (
            stud_width if stud_width is not None else FRAMING_PARAMS["stud_width"]
        )
        stud_depth = (
            stud_depth if stud_depth is not None else FRAMING_PARAMS["stud_depth"]
        )
        logger.trace(f"Using trimmer dimensions: width={stud_width}, depth={stud_depth}")

    base_plane = wall_data["base_plane"]
    trimmer_studs = []

    # Left trimmer Stud
    u_left = (
        opening_cell_data["u_start"] - FRAMING_PARAMS["trimmer_offset"] - stud_width / 2
    )  # Offset to the *left*
    v_start = opening_cell_data["v_start"]
    v_end = opening_cell_data["v_end"]
    
    logger.trace(f"Left trimmer position: u={u_left}, v_range={v_start}-{v_end}")
    
    pt_start_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_start
    )
    pt_end_left = rg.Point3d(
        base_plane.Origin.X + u_left, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    logger.trace(f"Left trimmer start: ({pt_start_left.X}, {pt_start_left.Y}, {pt_start_left.Z})")
    logger.trace(f"Left trimmer end: ({pt_end_left.X}, {pt_end_left.Y}, {pt_end_left.Z})")
    
    trimmer_studs.append(_create_line_curve(pt_start_left, pt_end_left))

    # Right trimmer Stud
    u_right = (
        opening_cell_data["u_end"] + FRAMING_PARAMS["trimmer_offset"] + stud_width / 2
    )  # Offset to the *right*
    
    logger.trace(f"Right trimmer position: u={u_right}, v_range={v_start}-{v_end}")
    
    pt_start_right = rg.Point3d(
        base_plane.Origin.X + u_right,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start,
    )
    pt_end_right = rg.Point3d(
        base_plane.Origin.X + u_right, base_plane.Origin.Y, base_plane.Origin.Z + v_end
    )
    logger.trace(f"Right trimmer start: ({pt_start_right.X}, {pt_start_right.Y}, {pt_start_right.Z})")
    logger.trace(f"Right trimmer end: ({pt_end_right.X}, {pt_end_right.Y}, {pt_end_right.Z})")
    
    trimmer_studs.append(_create_line_curve(pt_start_right, pt_end_right))
    
    logger.debug(f"Created {len(trimmer_studs)} trimmer studs")
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
    logger.debug("Creating header for opening")
    logger.trace(f"Opening data: {opening_data}")
    
    if profile:
        logger.debug("Using provided profile for header dimensions")
        header_width = profile.Width
        header_depth = profile.Height
        logger.trace(f"Profile dimensions: width={header_width}, height={header_depth}")
    else:
        header_width = (
            header_width
            if header_width is not None
            else FRAMING_PARAMS["header_width"]
        )
        header_depth = (
            header_depth
            if header_depth is not None
            else FRAMING_PARAMS["header_depth"]
        )
        logger.trace(f"Using header dimensions: width={header_width}, depth={header_depth}")

    base_plane = wall_data["base_plane"]
    
    # Extract opening information
    u_start = opening_data["u_start"]
    u_end = opening_data["u_end"]
    v_end = opening_data["v_end"]  # Top of opening
    
    logger.trace(f"Header horizontal range: u={u_start}-{u_end}")
    logger.trace(f"Header vertical position: v={v_end + header_width/2}")

    # Create centerline for the header at the top of the opening
    pt_start = rg.Point3d(
        base_plane.Origin.X + u_start,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_end + header_width / 2,  # Centered at top of opening
    )
    pt_end = rg.Point3d(
        base_plane.Origin.X + u_end,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_end + header_width / 2,
    )
    logger.trace(f"Header start point: ({pt_start.X}, {pt_start.Y}, {pt_start.Z})")
    logger.trace(f"Header end point: ({pt_end.X}, {pt_end.Y}, {pt_end.Z})")
    logger.trace(f"Header length: {pt_end.DistanceTo(pt_start)}")

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
    logger.debug("Creating sill for opening")
    logger.trace(f"Opening data: {opening_data}")
    
    if profile:
        logger.debug("Using provided profile for sill dimensions")
        sill_width = profile.Width
        sill_depth = profile.Height
        logger.trace(f"Profile dimensions: width={sill_width}, height={sill_depth}")
    else:
        sill_width = (
            sill_width if sill_width is not None else FRAMING_PARAMS["sill_width"]
        )
        sill_depth = (
            sill_depth if sill_depth is not None else FRAMING_PARAMS["sill_depth"]
        )
        logger.trace(f"Using sill dimensions: width={sill_width}, depth={sill_depth}")

    base_plane = wall_data["base_plane"]
    
    # Extract opening information
    u_start = opening_data["u_start"]
    u_end = opening_data["u_end"]
    v_start = opening_data["v_start"]  # Bottom of opening
    
    logger.trace(f"Sill horizontal range: u={u_start}-{u_end}")
    logger.trace(f"Sill vertical position: v={v_start - sill_width/2}")

    # Create centerline for the sill at the bottom of the opening
    pt_start = rg.Point3d(
        base_plane.Origin.X + u_start,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start - sill_width / 2,  # Centered at bottom of opening
    )
    pt_end = rg.Point3d(
        base_plane.Origin.X + u_end,
        base_plane.Origin.Y,
        base_plane.Origin.Z + v_start - sill_width / 2,
    )
    logger.trace(f"Sill start point: ({pt_start.X}, {pt_start.Y}, {pt_start.Z})")
    logger.trace(f"Sill end point: ({pt_end.X}, {pt_end.Y}, {pt_end.Z})")
    logger.trace(f"Sill length: {pt_end.DistanceTo(pt_start)}")

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
    
    Args:
        wall_data: Dictionary containing wall information including base curve and height
        top_plate_layers: Number of top plate layers (default from FRAMING_PARAMS)
        plate_width: Width of the plate (default from FRAMING_PARAMS)
        plate_depth: Depth of the plate (default from FRAMING_PARAMS)
        profile: Optional Rectangle3d profile to use instead of width/depth
    
    Returns:
        List of LineCurves representing the top plates
    """
    logger.debug("Creating top plates")
    
    if profile:
        logger.debug("Using provided profile for top plate dimensions")
        plate_width = profile.Width
        plate_depth = profile.Height
        logger.trace(f"Profile dimensions: width={plate_width}, height={plate_depth}")
    else:
        plate_width = (
            plate_width if plate_width is not None else FRAMING_PARAMS["plate_thickness"]
        )
        plate_depth = (
            plate_depth if plate_depth is not None else FRAMING_PARAMS["stud_depth"]
        )
        logger.trace(f"Using top plate dimensions: width={plate_width}, depth={plate_depth}")

    # Get number of layers for top plate
    top_plate_layers = (
        top_plate_layers
        if top_plate_layers is not None
        else FRAMING_PARAMS["top_plate_layers"]
    )
    logger.debug(f"Creating {top_plate_layers} top plate layers")

    # Extract required data
    base_curve = wall_data["wall_base_curve"]
    wall_height = wall_data["wall_height"]
    wall_length = wall_data.get("wall_length")
    if wall_length is None and hasattr(base_curve, "GetLength"):
        wall_length = safe_get_length(base_curve)
        logger.trace(f"Extracted wall length: {wall_length}")
    
    # Create top plates for each layer
    top_plates = []
    
    for layer in range(top_plate_layers):
        # Calculate elevation for this layer
        elevation = wall_height - plate_width * (top_plate_layers - layer)
        logger.trace(f"Top plate layer {layer+1} elevation: {elevation}")
        
        # Create a copy of the base curve at the top plate elevation
        top_plate_start = rg.Point3d(0, 0, elevation)
        top_plate_end = rg.Point3d(wall_length, 0, elevation) if wall_length else None
        
        if top_plate_end:
            logger.trace(f"Top plate layer {layer+1} endpoints: ({top_plate_start.X}, {top_plate_start.Y}, {top_plate_start.Z}) - ({top_plate_end.X}, {top_plate_end.Y}, {top_plate_end.Z})")
            top_plate = _create_line_curve(top_plate_start, top_plate_end)
            top_plates.append(top_plate)
        else:
            logger.warning("Could not determine wall length for top plate creation")
    
    logger.debug(f"Created {len(top_plates)} top plate curves")
    return top_plates


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
    
    Args:
        wall_data: Dictionary containing wall information including base curve
        bottom_plate_layers: Number of bottom plate layers (default from FRAMING_PARAMS)
        plate_width: Width of the plate (default from FRAMING_PARAMS)
        plate_depth: Depth of the plate (default from FRAMING_PARAMS)
        profile: Optional Rectangle3d profile to use instead of width/depth
    
    Returns:
        List of LineCurves representing the bottom plates
    """
    logger.debug("Creating bottom plates")
    
    if profile:
        logger.debug("Using provided profile for bottom plate dimensions")
        plate_width = profile.Width
        plate_depth = profile.Height
        logger.trace(f"Profile dimensions: width={plate_width}, height={plate_depth}")
    else:
        plate_width = (
            plate_width if plate_width is not None else FRAMING_PARAMS["plate_thickness"]
        )
        plate_depth = (
            plate_depth if plate_depth is not None else FRAMING_PARAMS["stud_depth"]
        )
        logger.trace(f"Using bottom plate dimensions: width={plate_width}, depth={plate_depth}")

    # Get number of layers for bottom plate
    bottom_plate_layers = (
        bottom_plate_layers
        if bottom_plate_layers is not None
        else FRAMING_PARAMS["bottom_plate_layers"]
    )
    logger.debug(f"Creating {bottom_plate_layers} bottom plate layers")

    # Extract required data
    base_curve = wall_data["wall_base_curve"]
    wall_length = wall_data.get("wall_length")
    if wall_length is None and hasattr(base_curve, "GetLength"):
        wall_length = safe_get_length(base_curve)
        logger.trace(f"Extracted wall length: {wall_length}")
    
    # Create bottom plates for each layer
    bottom_plates = []
    
    for layer in range(bottom_plate_layers):
        # Calculate elevation for this layer
        elevation = layer * plate_width
        logger.trace(f"Bottom plate layer {layer+1} elevation: {elevation}")
        
        # Create a copy of the base curve at the bottom plate elevation
        bottom_plate_start = rg.Point3d(0, 0, elevation)
        bottom_plate_end = rg.Point3d(wall_length, 0, elevation) if wall_length else None
        
        if bottom_plate_end:
            logger.trace(f"Bottom plate layer {layer+1} endpoints: ({bottom_plate_start.X}, {bottom_plate_start.Y}, {bottom_plate_start.Z}) - ({bottom_plate_end.X}, {bottom_plate_end.Y}, {bottom_plate_end.Z})")
            bottom_plate = _create_line_curve(bottom_plate_start, bottom_plate_end)
            bottom_plates.append(bottom_plate)
        else:
            logger.warning("Could not determine wall length for bottom plate creation")
    
    logger.debug(f"Created {len(bottom_plates)} bottom plate curves")
    return bottom_plates
