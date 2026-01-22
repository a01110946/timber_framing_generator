# File: timber_framing_generator/framing_elements/plates.py

from typing import List, Dict, Optional
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


def create_plates(
    wall_data: Dict,
    plate_type: str = "bottom_plate",
    representation_type: str = "structural",
    profile_override: Optional[str] = None,
    layers: Optional[int] = None,
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
            parameters = PlateParameters.from_wall_type(
                wall_data["wall_type"],
                framing_type=current_plate_type,
                layer_config=PlateLayerConfig(
                    position=PlatePosition.BOTTOM if idx == 0 else PlatePosition.TOP,
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

        # Create and append the plate geometry object
        logger.debug(f"- Creating plate geometry")
        try:
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
