# File: timber_framing_generator/framing_elements/sill_parameters.py

from dataclasses import dataclass
from typing import Optional, Dict, Any
from timber_framing_generator.config.framing import FRAMING_PARAMS, PROFILES, get_profile_for_wall_type

@dataclass
class SillParameters:
    """
    Manages parameters for sill framing elements.
    
    Sills are the horizontal members below windows, providing support and load transfer.
    This class handles both dimensional data and positioning information for sills.
    """
    thickness: float  # Depth along wall length
    width: float      # Width through wall thickness
    height: float     # Vertical height
    profile_name: str  # Name of the lumber profile used
    
    @classmethod
    def from_wall_type(
        cls,
        wall_type: str,
        rough_opening_width: float,
        profile_override: Optional[str] = None
    ) -> "SillParameters":
        """
        Create sill parameters based on wall type and opening width.
        
        Args:
            wall_type: The type of wall (e.g., '2x4EXT', '2x6EXT')
            rough_opening_width: Width of the rough opening
            profile_override: Optional override for the profile name
            
        Returns:
            SillParameters instance configured for the wall type
        """
        # Get profile dimensions using our configuration system
        if profile_override:
            profile = PROFILES.get(profile_override)
            if not profile:
                raise KeyError(f"Override profile not found: {profile_override}")
        else:
            profile = get_profile_for_wall_type(wall_type)
            
        # Get default sill parameters from config
        sill_height = FRAMING_PARAMS.get("sill_height", profile.width)
        
        # For sills, typical orientation is:
        # - thickness = profile.thickness (depth along wall)
        # - width = profile.width (through wall)
        # - height = sill_height (vertical dimension)
        
        return cls(
            thickness=profile.thickness,
            width=profile.width,
            height=sill_height,
            profile_name=profile.name
        )