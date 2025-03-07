# File: timber_framing_generator/framing_elements/plate_parameters.py

from dataclasses import dataclass
from typing import List, Optional
from timber_framing_generator.config.framing import (
    PlatePosition,
    FRAMING_PARAMS,
    PROFILES,
    ProfileDimensions,
    get_profile_for_wall_type,
    WALL_TYPE_PROFILES
)

@dataclass
class PlateLayerConfig:
    """
    Configuration for plate layers in different positions.
    
    This class manages the complete plate stack configuration for both
    bottom and top plates. It determines not just the number of layers
    but also their relationships and specific roles.
    """
    position: PlatePosition
    num_layers: int
    
    @property
    def plate_types(self) -> List[str]:
        """
        Get the ordered list of plate types based on position and layer count.
        
        Returns:
            List of plate type identifiers in stacking order (bottom-up).
        """
        if self.position == PlatePosition.BOTTOM:
            return (["sole_plate", "bottom_plate"] 
                   if self.num_layers == 2 
                   else ["bottom_plate"])
        else:  # TOP position
            return (["top_plate", "cap_plate"] 
                   if self.num_layers == 2 
                   else ["top_plate"])
    
    def get_cumulative_offset(self, layer_idx: int, thickness: float) -> float:
        """
        Calculate the cumulative offset for a specific layer in the stack.
        
        Args:
            layer_idx: Index of the layer in the stack (0-based)
            thickness: Thickness of the current plate
            
        Returns:
            float: Cumulative offset from reference elevation
        """
        if layer_idx >= self.num_layers:
            raise ValueError(f"Layer index {layer_idx} exceeds configured layers {self.num_layers}")
            
        direction = -1 if self.position == PlatePosition.TOP else 1
        
        if layer_idx == 0:
            # First layer offset is half its thickness
            return (thickness / 2) * direction
        else:
            # Subsequent layers stack on previous layers
            return thickness * layer_idx * direction

class PlateParameters:
    """
    Manages parameters for individual plates within a layer stack.
    
    This class handles both:
    1. Basic dimensional data and positioning for a single plate
    2. Creation of appropriate parameters based on wall types and profiles
    """
    def __init__(
        self,
        thickness: float,
        width: float,
        profile_name: str,
        layer_config: PlateLayerConfig,
        layer_idx: int,
        representation_type: str = "structural"
    ):
        # Store all parameters as instance variables first
        self.thickness = thickness
        self.width = width
        self.profile_name = profile_name
        self.layer_config = layer_config
        self.layer_idx = layer_idx
        self.representation_type = representation_type

        # Determine specific plate type based on position in stack
        self.plate_type = self.layer_config.plate_types[layer_idx]
        
        # Calculate vertical offset based on layer position
        self.vertical_offset = self._calculate_vertical_offset(
            self.thickness,
            self.plate_type,
            self.representation_type
        )

    @classmethod
    def from_wall_type(
        cls,
        wall_type: str,
        layer_config: PlateLayerConfig,
        layer_idx: int,
        representation_type: str = "schematic",
        framing_type: Optional[str] = None,
        profile_override: Optional[str] = None
    ) -> "PlateParameters":
        """
        Create plate parameters based on wall type and layer configuration.
        
        This factory method handles the complexity of:
        1. Determining the appropriate profile based on wall type
        2. Getting the correct dimensions for that profile
        3. Creating properly configured parameters for the plate's position
        
        Args:
            wall_type: The type of wall (e.g., '2x4EXT', '2x6EXT')
            layer_config: Configuration for the plate stack
            layer_idx: Position of this plate in the stack
            representation_type: "structural" or "schematic"
            framing_type: Optional specification of the framing type
            profile_override: Optional override for the profile name
            
        Returns:
            PlateParameters instance configured for the wall type
            
        Example:
            >>> layer_config = PlateLayerConfig(PlatePosition.BOTTOM, 2)
            >>> params = PlateParameters.from_wall_type('2x4EXT', layer_config, 0)
        """
        # Get profile dimensions using our configuration system
        if profile_override:
            profile = PROFILES.get(profile_override)
            if not profile:
                raise KeyError(f"Override profile not found: {profile_override}")
        else:
            profile: ProfileDimensions = PlateParameters.get_profile_for_wall_type(wall_type)
                
        return cls(
            thickness=profile.thickness,
            width=profile.width,
            profile_name=profile.name,
            layer_config=layer_config,
            layer_idx=layer_idx,
            representation_type=representation_type
        )

    @staticmethod
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
    
    @staticmethod
    def _calculate_vertical_offset(
        thickness: float,
        framing_type: str,
        representation_type: str
    ) -> float:
        """
        Calculates vertical offset based on type and representation.
        
        Args:
            thickness: The plate thickness
            framing_type: Type of plate ('bottom_plate', 'top_plate', etc.)
            representation_type: How to represent the plate ('structural' or 'schematic')
            
        Returns:
            float: The calculated vertical offset
        """
        if framing_type in ["bottom_plate", "sole_plate"]:
        # Add debug print
            print(f"Calculating offset for {framing_type} with {representation_type}")
        # For bottom plates, reverse the offset based on representation
            return thickness / 2.0 if representation_type == "structural" else -thickness / 2.0
        else:  # top_plate or cap_plate
            base_offset = -thickness / 2.0
            if framing_type == "cap_plate":
                base_offset -= thickness  # Additional offset for cap plate
            return base_offset