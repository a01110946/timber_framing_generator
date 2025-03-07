# File: timber_framing_generator/config/framing.py

"""
Framing-specific configurations for the Timber Framing Generator.
This module contains all parameters, profiles, and settings related to
timber framing elements.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Union, Any

from timber_framing_generator.config.units import ProjectUnits, convert_from_feet


class PlatePosition(Enum):
    """
    Defines the basic position categories for plates in a wall assembly.
    These positions determine how plates stack and reference their elevations.
    """

    BOTTOM = "bottom"  # Plates that reference from wall base elevation
    TOP = "top"  # Plates that reference from wall top elevation


@dataclass
class PlateConfig:
    """
    Configuration for plate positioning relative to reference elevation.

    structural_multiplier: Multiplier for structural representation
    schematic_multiplier: Multiplier for schematic representation
    reference: 'base' or 'top' - which wall elevation to reference from
    """

    structural_multiplier: float
    schematic_multiplier: float
    reference: str


# Configuration map defining plate positioning rules
PLATE_CONFIGS = {
    # Bottom plates: offset direction varies by representation type
    ("bottom", 1): PlateConfig(
        structural_multiplier=0.5,  # Up from base in structural
        schematic_multiplier=-0.5,  # Down from base in schematic
        reference="base",
    ),
    ("bottom", 2): [
        # Bottom plate
        PlateConfig(
            structural_multiplier=0.5, schematic_multiplier=-0.5, reference="base"
        ),
        # Sole plate
        PlateConfig(
            structural_multiplier=1.5, schematic_multiplier=-1.5, reference="base"
        ),
    ],
    # Top plates: always offset down from top
    ("top", 1): PlateConfig(
        structural_multiplier=-0.5,  # Always down from top
        schematic_multiplier=-0.5,  # Same for both representations
        reference="top",
    ),
    ("top", 2): [
        # Cap plate
        PlateConfig(
            structural_multiplier=-0.5, schematic_multiplier=-0.5, reference="top"
        ),
        # Top plate
        PlateConfig(
            structural_multiplier=-1.5, schematic_multiplier=-1.5, reference="top"
        ),
    ],
}


class RepresentationType(Enum):
    """Defines valid representation types for framing elements."""

    STRUCTURAL = "structural"
    SCHEMATIC = "schematic"


class PlateType(Enum):
    """Defines valid plate types."""

    BOTTOM_PLATE = "bottom_plate"
    TOP_PLATE = "top_plate"
    CAP_PLATE = "cap_plate"
    SOLE_PLATE = "sole_plate"


@dataclass
class ProfileDimensions:
    """
    Stores dimensions for a framing profile.

    This class maintains the fundamental dimensions of lumber profiles used in framing.
    All dimensions are stored internally in feet but can be converted to other units
    as needed through the get_dimensions() method.

    Attributes:
        thickness: The profile's thickness in feet (e.g., 3.5/12 for a 2x4)
        width: The profile's width in feet (e.g., 1.5/12 for a 2x4)
        name: The profile's standard designation (e.g., "2x4")
        description: Human-readable description of the profile

    Example:
        A 2x4 lumber profile would be created as:
        >>> profile = ProfileDimensions(
        ...     thickness=3.5/12,  # 3.5 inches converted to feet
        ...     width=1.5/12,      # 1.5 inches converted to feet
        ...     name="2x4",
        ...     description="Standard 2x4 dimensional lumber"
        ... )
    """

    thickness: float  # In feet
    width: float  # In feet
    name: str
    description: str

    def get_dimensions(
        self, units: ProjectUnits = ProjectUnits.FEET
    ) -> Dict[str, float]:
        """
        Gets the profile dimensions in the requested units.

        This method converts the internally stored dimensions (which are in feet)
        to any supported unit system. This is crucial for interfacing with different
        parts of the system that might expect different units.

        Args:
            units: The desired output units (defaults to feet)
                  Uses ProjectUnits enum from our units configuration

        Returns:
            Dictionary with thickness and width in requested units

        Example:
            >>> profile = ProfileDimensions(3.5/12, 1.5/12, "2x4", "Standard 2x4")
            >>> dims = profile.get_dimensions(ProjectUnits.INCHES)
            >>> print(dims)
            {'thickness': 3.5, 'width': 1.5}
        """
        return {
            "thickness": convert_from_feet(self.thickness, units),
            "width": convert_from_feet(self.width, units),
        }


# Standard framing profiles (dimensions in feet)
PROFILES: Dict[str, ProfileDimensions] = {
    "2x4": ProfileDimensions(
        thickness=1.5 / 12,  # 3.5 inches in feet
        width=3.5 / 12,  # 1.5 inches in feet
        name="2x4",
        description="Standard 2x4 dimensional lumber",
    ),
    "2x6": ProfileDimensions(
        thickness=1.5 / 12,  # 5.5 inches in feet
        width=5.5 / 12,  # 1.5 inches in feet
        name="2x6",
        description="Standard 2x6 dimensional lumber",
    ),
}

# Framing parameters (all dimensions in feet)
FRAMING_PARAMS: Dict[str, Any] = {
    # Plate configuration
    "bottom_plate_layers": 1,
    "top_plate_layers": 2,
    # Default dimensions if not specified by profile
    "plate_thickness": 1.5 / 12,  # 3.5 inches in feet
    "plate_width": 3.5 / 12,  # 1.5 inches in feet
    # Stud parameters
    "stud_width": 1.5 / 12,  # 1.5 inches in feet
    "stud_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    "stud_spacing": 16.0 / 12,  # 16 inches in feet
    # King stud parameters
    "king_stud_width": 1.5 / 12,  # 1.5 inches in feet
    "king_stud_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    # Trimmer parameters
    "trimmer_width": 1.5 / 12,  # 1.5 inches in feet
    "trimmer_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    # Header parameters
    "header_height": 7 / 12,  # 1.5 inches in feet
    "header_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    "header_height_above_opening": 0.0,  # 0 inches in feet
    # Cripple parameters
    "cripple_width": 1.5 / 12,  # 1.5 inches in feet
    "cripple_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    "cripple_spacing": 16.0 / 12,  # 16 inches in feet
    # Sill parameters
    "sill_height": 1.5 / 12,  # 1.5 inches in feet
    "sill_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    # Offsets and tolerances
    "minimum_stud_spacing": 16.0 / 12,  # 16 inches in feet
    "trimmer_offset": 1.5 / 12 / 2,  # 0.5 inches in feet
    "king_stud_offset": 1.5 / 12 / 2,  # 0.5 inches in feet
    # Validation thresholds
    "minimum_cell_width": 1.5 / 12,  # 1.5 inches in feet
    "minimum_cell_height": 1.5 / 12,  # 1.5 inches in feet
}

# Wall type to profile mapping
WALL_TYPE_PROFILES: Dict[str, str] = {
    # Exterior walls
    "2x4 EXT": "2x4",
    "2x4EXT": "2x4",
    "2x6 EXT": "2x6",
    "2x6EXT": "2x6",
    # Interior walls
    "2x4 INT": "2x4",
    "2x6 INT": "2x6",
}


def get_profile_for_wall_type(wall_type: str) -> ProfileDimensions:
    """
    Gets the appropriate profile dimensions for a wall type.

    This function handles wall type string variations by:
    1. Trying the exact wall type string first
    2. Attempting to normalize the string if exact match fails

    Args:
        wall_type: The wall type identifier (e.g., "2x4 EXT", "2x6 INT")

    Returns:
        ProfileDimensions object with the appropriate dimensions

    Raises:
        KeyError: If wall type is not recognized or mapped profile not found
    """
    try:
        # First try exact match
        profile_name = WALL_TYPE_PROFILES.get(wall_type)

        if profile_name is None:
            # Try normalizing the string (remove extra spaces, convert to uppercase)
            normalized_type = wall_type.strip().upper().replace(" ", "")
            profile_name = WALL_TYPE_PROFILES.get(normalized_type)

            if profile_name is None:
                # If still not found, extract the base profile (2x4 or 2x6)
                base_profile = wall_type.split()[0]  # Get first part (e.g., "2x4")
                if base_profile in ("2x4", "2x6"):
                    profile_name = base_profile
                else:
                    raise KeyError(
                        f"No profile mapping found for wall type: {wall_type}"
                    )

        profile = PROFILES.get(profile_name)
        if not profile:
            raise KeyError(f"Profile not found: {profile_name}")

        return profile

    except Exception as e:
        print(f"Error processing wall type '{wall_type}': {str(e)}")
        raise


def calculate_plate_offset(
    thickness: float,
    position: PlatePosition,
    layer_count: int,
    layer_index: int,
    representation_type: str,
) -> float:
    """
    Calculate plate offset considering both position and representation type.

    Args:
        thickness: Plate thickness (typically 1.5 inches)
        position: PlatePosition.TOP or PlatePosition.BOTTOM
        layer_count: Number of plate layers (1 or 2)
        layer_index: Which layer in multi-layer system (0 = primary, 1 = secondary)
        representation_type: "structural" or "schematic"

    Returns:
        float: Offset distance from reference elevation
    """
    config = PLATE_CONFIGS[(position.value, layer_count)]

    # Get the appropriate config for single/multi-layer
    if isinstance(config, list):
        plate_config = config[layer_index]
    else:
        plate_config = config

    # Select multiplier based on representation type
    multiplier = (
        plate_config.structural_multiplier
        if representation_type == "structural"
        else plate_config.schematic_multiplier
    )

    return thickness * multiplier
