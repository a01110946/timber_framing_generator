# File: timber_framing_generator/framing_elements/plate_parameters.py

from dataclasses import dataclass
from typing import List, Optional
from src.timber_framing_generator.config.framing import (
    PlatePosition,
    FRAMING_PARAMS,
    PROFILES,
    ProfileDimensions,
    get_profile_for_wall_type,
    WALL_TYPE_PROFILES,
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
            return (
                ["sole_plate", "bottom_plate"]
                if self.num_layers == 2
                else ["bottom_plate"]
            )
        else:  # TOP position
            return ["top_plate", "cap_plate"] if self.num_layers == 2 else ["top_plate"]

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
            raise ValueError(
                f"Layer index {layer_idx} exceeds configured layers {self.num_layers}"
            )

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
        representation_type: str = "structural",
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

        # Calculate vertical offset based on layer position and stacking
        self.vertical_offset = self._calculate_vertical_offset(
            self.thickness,
            self.plate_type,
            self.representation_type,
            self.layer_idx,
            self.layer_config.num_layers,
            self.layer_config.position
        )

    @classmethod
    def from_wall_type(
        cls,
        wall_type: str,
        layer_config: PlateLayerConfig,
        layer_idx: int,
        representation_type: str = "schematic",
        framing_type: Optional[str] = None,
        profile_override: Optional[str] = None,
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
            profile: ProfileDimensions = PlateParameters.get_profile_for_wall_type(
                wall_type
            )

        return cls(
            thickness=profile.thickness,
            width=profile.width,
            profile_name=profile.name,
            layer_config=layer_config,
            layer_idx=layer_idx,
            representation_type=representation_type,
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
        representation_type: str,
        layer_idx: int = 0,
        num_layers: int = 1,
        position: PlatePosition = None
    ) -> float:
        """
        Calculates vertical offset based on type, representation, and stacking.

        For bottom plates (single or double):
        - The reference line is at wall base elevation
        - All plates should be INSIDE the wall (above the reference line)
        - Single plate: offset = +thickness/2 (bottom face at wall base)
        - Double plates: stack upward from wall base
          - sole_plate (idx=0): +thickness/2
          - bottom_plate (idx=1): +1.5*thickness

        For top plates (single or double):
        - The reference line is at wall top elevation
        - All plates should be INSIDE the wall (below the reference line)
        - Single plate: offset = -thickness/2 (top face at wall top)
        - Double plates: stack downward from wall top
          - top_plate (idx=0): -1.5*thickness (lower plate)
          - cap_plate (idx=1): -thickness/2 (upper plate, top face at wall top)

        Args:
            thickness: The plate thickness
            framing_type: Type of plate ('bottom_plate', 'top_plate', etc.)
            representation_type: How to represent the plate ('structural' or 'schematic')
            layer_idx: Index of this plate in the layer stack (0-based)
            num_layers: Total number of plate layers (1 or 2)
            position: PlatePosition.BOTTOM or PlatePosition.TOP

        Returns:
            float: The calculated vertical offset
        """
        # Determine position from framing_type if not provided
        if position is None:
            if framing_type in ["bottom_plate", "sole_plate"]:
                position = PlatePosition.BOTTOM
            else:
                position = PlatePosition.TOP

        if position == PlatePosition.BOTTOM:
            # Bottom plates: stack upward from wall base (all inside wall)
            if num_layers == 1:
                # Single plate: bottom face at wall base
                offset = thickness / 2.0
            else:
                # Double plates: stack upward
                # layer_idx=0: sole_plate, bottom face at wall base -> +thickness/2
                # layer_idx=1: bottom_plate, bottom face at top of sole -> +1.5*thickness
                offset = thickness / 2.0 + (layer_idx * thickness)
            print(f"Bottom plate offset for {framing_type} (idx={layer_idx}, layers={num_layers}): +{offset}")
            return offset
        else:
            # Top plates: stack downward from wall top (all inside wall)
            if num_layers == 1:
                # Single plate: top face at wall top
                offset = -thickness / 2.0
            else:
                # Double plates: both inside wall, stacking downward from wall top
                # layer_idx=0: top_plate (lower), below cap_plate -> -1.5*thickness
                # layer_idx=1: cap_plate (upper), top face at wall top -> -thickness/2
                # Calculate: the upper plate (idx=1) is at -thickness/2
                # The lower plate (idx=0) is at -(1.5*thickness)
                offset = -thickness / 2.0 - ((num_layers - 1 - layer_idx) * thickness)
            print(f"Top plate offset for {framing_type} (idx={layer_idx}, layers={num_layers}): {offset}")
            return offset
