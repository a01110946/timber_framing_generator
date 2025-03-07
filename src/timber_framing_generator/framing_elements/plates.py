# File: timber_framing_generator/framing_elements/plates.py

from typing import List, Dict, Optional
from timber_framing_generator.config.framing import (
    FRAMING_PARAMS,
    PlatePosition,
)

from timber_framing_generator.framing_elements.location_data import (
    get_plate_location_data,
)
from timber_framing_generator.framing_elements.plate_parameters import (
    PlateParameters,
    PlateLayerConfig,
)
from timber_framing_generator.framing_elements.plate_geometry import PlateGeometry


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
    print(f"\nCreating plates with configuration:")
    print(f"- Plate type: {plate_type}")
    print(f"- Representation: {representation_type}")
    print(f"- Profile override: {profile_override}")
    print(f"- Layers: {layers}")

    plates = []

    # Determine plate types to create based on input
    plate_types = []
    if plate_type == "bottom_plate":
        if layers == 2:
            plate_types.extend(["sole_plate", "bottom_plate"])
            print(f"Creating double bottom plates (sole plate + bottom plate)")
        else:
            plate_types.append("bottom_plate")
            print(f"Creating single bottom plate")
    elif plate_type == "top_plate":
        if layers == 2:
            plate_types.extend(["top_plate", "cap_plate"])
            print(f"Creating double top plates (top plate + cap plate)")
        else:
            plate_types.append("top_plate")
            print(f"Creating single top plate")
    else:
        raise ValueError(f"Unsupported plate type: {plate_type}")

    # Create plates for each type
    for idx, current_plate_type in enumerate(plate_types):
        print(f"\nProcessing {current_plate_type}:")

        # Get location data for this plate type
        print(f"- Getting location data with {representation_type} representation")
        location_data = get_plate_location_data(
            wall_data,
            plate_type=current_plate_type,
            representation_type=representation_type,
        )
        print(f"  Reference elevation: {location_data['reference_elevation']:.3f}")

        # Create parameters with optional profile override
        print(f"- Creating plate parameters")
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
        print(f"  Profile: {parameters.profile_name}")
        print(f"  Dimensions: {parameters.thickness:.3f} x {parameters.width:.3f}")
        print(f"  Vertical offset: {parameters.vertical_offset:.3f}")

        # Create and append the plate geometry object
        print(f"- Creating plate geometry")
        plate = PlateGeometry(location_data, parameters)
        plates.append(plate)
        print(f"  Successfully created {current_plate_type} geometry")

    print(f"\nCreated {len(plates)} plate elements total")
    return plates
