# File: timber_framing_generator/framing_elements/header_parameters.py

from dataclasses import dataclass
from typing import Optional, Dict, Any
from timber_framing_generator.config.framing import (
    FRAMING_PARAMS,
    PROFILES,
    get_profile_for_wall_type,
)


@dataclass
class HeaderParameters:
    """
    Manages parameters for header framing elements.

    This class handles both dimensional data and positioning information for headers,
    supporting customization and profile selection.
    """

    thickness: float  # Depth along wall length
    width: float  # Width through wall thickness
    height: float  # Vertical height
    profile_name: str  # Name of the lumber profile used

    # Optional parameters with defaults
    header_height_above_opening: float = None  # Vertical position above opening

    @classmethod
    def from_wall_type(
        cls,
        wall_type: str,
        rough_opening_height: float,
        profile_override: Optional[str] = None,
    ) -> "HeaderParameters":
        """
        Create header parameters based on wall type and opening height.

        This factory method handles the complexity of:
        1. Determining the appropriate profile based on wall type
        2. Getting the correct dimensions for that profile
        3. Setting default positioning relative to the opening

        Args:
            wall_type: The type of wall (e.g., '2x4EXT', '2x6EXT')
            rough_opening_height: Height of the rough opening
            profile_override: Optional override for the profile name

        Returns:
            HeaderParameters instance configured for the wall type
        """
        # Get profile dimensions using our configuration system
        if profile_override:
            profile = PROFILES.get(profile_override)
            if not profile:
                raise KeyError(f"Override profile not found: {profile_override}")
        else:
            profile = get_profile_for_wall_type(wall_type)

        # Get default header parameters from config
        header_height = FRAMING_PARAMS.get(
            "header_height", profile.width * 2
        )  # TEMPORARILY NOT USING HEADER HEIGHT

        # For headers, typical orientation is:
        # - thickness = profile.thickness (depth along wall)
        # - width = profile.width (through wall)
        # - height = header_height (vertical dimension)

        return cls(
            thickness=profile.thickness,
            width=profile.width,
            height=header_height,
            profile_name=profile.name,
            header_height_above_opening=0.0,  # Default to aligning with top of opening
        )
