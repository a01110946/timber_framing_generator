# File: timber_framing_generator/framing_elements/plates.py

from typing import List, Dict, Optional, Any
from src.timber_framing_generator.config.framing import (
    FRAMING_PARAMS,
    PlatePosition,
)

from src.timber_framing_generator.framing_elements.location_data import (
    get_plate_location_data,
)
from src.timber_framing_generator.framing_elements.plate_parameters import (
    PlateParameters,
    PlateLayerConfig,
)
from src.timber_framing_generator.framing_elements.plate_geometry import PlateGeometry

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


def _get_door_openings(openings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter openings to get only door openings.

    Args:
        openings: List of opening dictionaries

    Returns:
        List of door opening dictionaries
    """
    doors = []
    for opening in openings:
        opening_type = opening.get("opening_type", "").lower()
        if opening_type == "door":
            doors.append(opening)
    return doors


def _split_reference_line_at_doors(
    reference_line,
    doors: List[Dict[str, Any]],
    base_plane
) -> List:
    """
    Split a reference line into segments that skip door openings.

    Args:
        reference_line: The original plate centerline (rg.Curve)
        doors: List of door opening dictionaries with 'start_u_coordinate' and 'rough_width'
        base_plane: Wall's base plane for coordinate transformation

    Returns:
        List of LineCurve segments that skip door areas
    """
    import Rhino.Geometry as rg

    if not doors:
        return [reference_line]

    # Get line start and end in U coordinates
    line_start = reference_line.PointAtStart
    line_end = reference_line.PointAtEnd

    # Calculate wall direction vector
    wall_direction = rg.Vector3d(line_end - line_start)
    wall_length = wall_direction.Length
    wall_direction.Unitize()

    # Collect door intervals in U coordinates
    # Sort doors by their start position
    door_intervals = []
    for door in doors:
        u_start = door.get("start_u_coordinate", 0)
        rough_width = door.get("rough_width", 0)
        u_end = u_start + rough_width
        door_intervals.append((u_start, u_end))

    # Sort by start position
    door_intervals.sort(key=lambda x: x[0])

    # Merge overlapping intervals
    merged = []
    for start, end in door_intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Create line segments between door intervals
    segments = []
    current_u = 0.0

    for door_start, door_end in merged:
        # Create segment from current position to door start
        if door_start > current_u + 0.01:  # Small tolerance
            seg_start = rg.Point3d.Add(line_start, rg.Vector3d.Multiply(wall_direction, current_u))
            seg_end = rg.Point3d.Add(line_start, rg.Vector3d.Multiply(wall_direction, door_start))
            segments.append(rg.LineCurve(seg_start, seg_end))
            logger.debug(f"Created plate segment from U={current_u:.3f} to U={door_start:.3f}")

        # Move current position past the door
        current_u = door_end

    # Create final segment from last door to wall end
    if current_u < wall_length - 0.01:  # Small tolerance
        seg_start = rg.Point3d.Add(line_start, rg.Vector3d.Multiply(wall_direction, current_u))
        seg_end = line_end
        segments.append(rg.LineCurve(seg_start, seg_end))
        logger.debug(f"Created plate segment from U={current_u:.3f} to wall end")

    logger.info(f"Split bottom plate into {len(segments)} segments (skipping {len(merged)} door openings)")
    return segments


def create_plates(
    wall_data: Dict,
    plate_type: str = "bottom_plate",
    representation_type: str = "structural",
    profile_override: Optional[str] = None,
    layers: Optional[int] = None,
    openings: Optional[List[Dict[str, Any]]] = None,
) -> List[PlateGeometry]:
    """
    Creates plate geometry objects for a wall with full configuration options.

    This function serves as the main entry point for plate creation, supporting:
    1. Different plate types (bottom, top, or both)
    2. Different representation methods (structural or schematic)
    3. Custom profile overrides
    4. Single or multiple plate layers

    The representation_type parameter controls plate positioning:
    - "structural": Places plates in their actual construction position
                   (e.g., bottom plate centered below wall base)
    - "schematic": Places plates for clear visualization
                   (e.g., bottom plate centered above wall base)

    Args:
        wall_data: Dictionary containing wall information including:
                  - wall_type: String identifying the wall construction
                  - base_plane: Rhino plane defining wall orientation
                  - wall_base_elevation: Float for wall's base height
                  - wall_top_elevation: Float for wall's top height
        plate_type: Type of plate to create ("bottom_plate", "top_plate")
                   Default is "bottom_plate"
        representation_type: How to represent the plate ("structural" or "schematic")
                           Default is "structural"
        profile_override: Optional override for the plate profile
                        If None, uses wall type's default profile
        layers: Number of plate layers (1 or 2)
               If None, uses default from FRAMING_PARAMS
        openings: Optional list of wall openings. For bottom plates, door openings
                 will cause the plate to be split into segments.

    Returns:
        List[PlateGeometry]: A list of PlateGeometry objects representing the plates

    Example:
        # Create structural bottom plates
        bottom_plates = create_plates(
            wall_data,
            plate_type="bottom_plate",
            representation_type="structural"
        )

        # Create schematic double top plates
        top_plates = create_plates(
            wall_data,
            plate_type="top_plate",
            representation_type="schematic",
            layers=2
        )
    """
    logger.info(f"Creating plates with configuration:")
    logger.info(f"- Plate type: {plate_type}")
    logger.info(f"- Representation: {representation_type}")
    logger.info(f"- Profile override: {profile_override}")
    logger.info(f"- Layers: {layers}")
    logger.trace(f"Wall data: {wall_data}")

    plates = []

    # Determine plate types to create based on input
    plate_types = []
    if plate_type == "bottom_plate":
        if layers == 2:
            plate_types.extend(["sole_plate", "bottom_plate"])
            logger.debug(f"Creating double bottom plates (sole plate + bottom plate)")
        else:
            plate_types.append("bottom_plate")
            logger.debug(f"Creating single bottom plate")
    elif plate_type == "top_plate":
        if layers == 2:
            plate_types.extend(["top_plate", "cap_plate"])
            logger.debug(f"Creating double top plates (top plate + cap plate)")
        else:
            plate_types.append("top_plate")
            logger.debug(f"Creating single top plate")
    else:
        error_msg = f"Unsupported plate type: {plate_type}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Create plates for each type
    for idx, current_plate_type in enumerate(plate_types):
        logger.debug(f"Processing {current_plate_type}:")

        # Get location data for this plate type
        logger.debug(f"- Getting location data with {representation_type} representation")
        try:
            location_data = get_plate_location_data(
                wall_data,
                plate_type=current_plate_type,
                representation_type=representation_type,
            )
            logger.debug(f"  Reference elevation: {location_data['reference_elevation']:.3f}")
            logger.trace(f"  Complete location data: {location_data}")
        except Exception as e:
            logger.error(f"Failed to get location data for {current_plate_type}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

        # Create parameters with optional profile override
        logger.debug(f"- Creating plate parameters")
        try:
            # Determine position based on plate_type parameter, not loop index
            # All bottom plates (sole_plate, bottom_plate) use BOTTOM position
            # All top plates (top_plate, cap_plate) use TOP position
            plate_position = PlatePosition.BOTTOM if plate_type == "bottom_plate" else PlatePosition.TOP
            parameters = PlateParameters.from_wall_type(
                wall_data["wall_type"],
                framing_type=current_plate_type,
                layer_config=PlateLayerConfig(
                    position=plate_position,
                    num_layers=len(plate_types),
                ),
                layer_idx=idx,
                representation_type=representation_type,
                profile_override=profile_override,
            )
            logger.debug(f"  Profile: {parameters.profile_name}")
            logger.debug(f"  Dimensions: {parameters.thickness:.3f} x {parameters.width:.3f}")
            logger.debug(f"  Vertical offset: {parameters.vertical_offset:.3f}")
            logger.trace(f"  Complete parameters: {parameters}")
        except Exception as e:
            logger.error(f"Failed to create parameters for {current_plate_type}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

        # Create and append the plate geometry object(s)
        logger.debug(f"- Creating plate geometry")
        try:
            # Check if this is a bottom plate and if there are door openings
            # If so, split the plate into segments that skip door areas
            if plate_type == "bottom_plate" and openings:
                doors = _get_door_openings(openings)
                if doors:
                    logger.info(f"Found {len(doors)} door openings - splitting bottom plate")
                    reference_line = location_data["reference_line"]
                    base_plane = location_data["base_plane"]
                    segments = _split_reference_line_at_doors(reference_line, doors, base_plane)

                    for seg_idx, segment in enumerate(segments):
                        # Create modified location data with the segment as reference line
                        segment_location_data = dict(location_data)
                        segment_location_data["reference_line"] = segment
                        plate = PlateGeometry(segment_location_data, parameters)
                        plates.append(plate)
                        logger.debug(f"  Created {current_plate_type} segment {seg_idx + 1}/{len(segments)}")
                else:
                    # No doors, create single plate
                    plate = PlateGeometry(location_data, parameters)
                    plates.append(plate)
                    logger.info(f"  Successfully created {current_plate_type} geometry")
            else:
                # Top plates or bottom plates without openings - create single plate
                plate = PlateGeometry(location_data, parameters)
                plates.append(plate)
                logger.info(f"  Successfully created {current_plate_type} geometry")
        except Exception as e:
            logger.error(f"Failed to create geometry for {current_plate_type}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    logger.info(f"Created {len(plates)} plate elements total")
    return plates
