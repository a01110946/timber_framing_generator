# File: src/config/framing.py

"""
Framing-specific configurations for the Timber Framing Generator.
This module contains all parameters, profiles, and settings related to
timber framing elements.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, Any

from .units import ProjectUnits, convert_from_feet

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
    All dimensions are stored internally in feet and converted as needed.
    """
    thickness: float  # In feet
    width: float     # In feet
    name: str
    description: str
    
    def get_dimensions(self, units: ProjectUnits = ProjectUnits.FEET) -> Dict[str, float]:
        """
        Gets the profile dimensions in the requested units.
        
        Args:
            units: The desired output units (defaults to feet)
            
        Returns:
            Dictionary with thickness and width in requested units
        """
        return {
            "thickness": convert_from_feet(self.thickness, units),
            "width": convert_from_feet(self.width, units)
        }

# Standard framing profiles (dimensions in feet)
PROFILES: Dict[str, ProfileDimensions] = {
    "2x4": ProfileDimensions(
        thickness=3.5/12,  # 3.5 inches in feet
        width=1.5/12,      # 1.5 inches in feet
        name="2x4",
        description="Standard 2x4 dimensional lumber"
    ),
    "2x6": ProfileDimensions(
        thickness=5.5/12,  # 5.5 inches in feet
        width=1.5/12,      # 1.5 inches in feet
        name="2x6",
        description="Standard 2x6 dimensional lumber"
    )
}

# Framing parameters (all dimensions in feet)
FRAMING_PARAMS: Dict[str, Any] = {
    # Plate configuration
    "bottom_plate_layers": 1,
    "top_plate_layers": 2,
    
    # Default dimensions if not specified by profile
    "plate_thickness": 3.5/12,  # 3.5 inches in feet
    "plate_width": 1.5/12,      # 1.5 inches in feet
    
    # Offsets and tolerances
    "minimum_stud_spacing": 16.0/12,  # 16 inches in feet
    "trimmer_offset": 0.5/12,         # 0.5 inches in feet
    "king_stud_offset": 0.5/12,       # 0.5 inches in feet
    
    # Validation thresholds
    "minimum_cell_width": 1.5/12,     # 1.5 inches in feet
    "minimum_cell_height": 1.5/12      # 1.5 inches in feet
}

# Wall type to profile mapping
WALL_TYPE_PROFILES: Dict[str, str] = {
    "2x4EXT": "2x4",
    "2x6EXT": "2x6"
}

def get_profile_for_wall_type(wall_type: str) -> ProfileDimensions:
    """
    Gets the appropriate profile dimensions for a wall type.
    
    Args:
        wall_type: The wall type identifier
        
    Returns:
        ProfileDimensions object with the appropriate dimensions
        
    Raises:
        KeyError: If wall type is not recognized or mapped profile not found
    """
    profile_name = WALL_TYPE_PROFILES.get(wall_type)
    if not profile_name:
        raise KeyError(f"No profile mapping found for wall type: {wall_type}")
        
    profile = PROFILES.get(profile_name)
    if not profile:
        raise KeyError(f"Profile not found: {profile_name}")
        
    return profile