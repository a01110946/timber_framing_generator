# File: src/framing_elements/plate_parameters.py

from typing import Dict, Optional
from dataclasses import dataclass
from config import FRAMING_PARAMS, PROFILES

@dataclass
class PlateParameters:
    """Contains all parameters needed to define a plate's properties."""
    thickness: float
    width: float
    vertical_offset: float
    profile_name: str
    framing_type: str
    
    @classmethod
    def from_wall_type(
        cls,
        wall_type: str,
        framing_type: str = "bottom_plate",
        representation_type: str = "structural",
        profile_override: Optional[str] = None,
        thickness_override: Optional[float] = None,
        width_override: Optional[float] = None
    ) -> "PlateParameters":
        """
        Creates plate parameters based on wall type and overrides.
        
        This factory method encapsulates all the logic for determining
        plate dimensions and offsets based on wall type and representation.
        """
        # Determine profile from wall type or override
        profile_name = profile_override or cls._get_profile_from_wall_type(wall_type)
        dimensions = PROFILES.get(profile_name, {})
        
        # Get dimensions with override capability
        thickness = thickness_override or dimensions.get(
            "thickness", 
            FRAMING_PARAMS.get("plate_thickness")
        )
        width = width_override or dimensions.get(
            "width",
            FRAMING_PARAMS.get("plate_width")
        )
        
        # Calculate vertical offset based on type and representation
        vertical_offset = cls._calculate_vertical_offset(
            thickness,
            framing_type,
            representation_type
        )
        
        return cls(
            thickness=thickness,
            width=width,
            vertical_offset=vertical_offset,
            profile_name=profile_name,
            framing_type=framing_type
        )
    
    @staticmethod
    def _get_profile_from_wall_type(wall_type: str) -> str:
        """Maps wall types to default profiles."""
        # This could be expanded with more sophisticated mapping
        if "2x4" in wall_type:
            return "2x4"
        if "2x6" in wall_type:
            return "2x6"
        return "2x4"  # Default
    
    @staticmethod
    def _calculate_vertical_offset(
        thickness: float,
        framing_type: str,
        representation_type: str
    ) -> float:
        """Calculates vertical offset based on type and representation."""
        if framing_type in ["bottom_plate", "sole_plate"]:
            return thickness / 2.0 if representation_type == "structural" else -thickness / 2.0
        else:  # top_plate or cap_plate
            base_offset = -thickness / 2.0
            if framing_type == "cap_plate":
                base_offset -= thickness  # Additional offset for cap plate
            return base_offset