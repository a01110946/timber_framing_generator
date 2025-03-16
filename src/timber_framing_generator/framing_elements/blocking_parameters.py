# File: timber_framing_generator/framing_elements/blocking_parameters.py

"""
Parameters for row blocking configurations in timber framing.

This module contains dataclasses and parameter configurations for
row blocking elements, including positioning data and geometric
specifications.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Union, Tuple
import Rhino.Geometry as rg

from src.timber_framing_generator.config.framing import (
    FRAMING_PARAMS,
    BlockingPattern,
    PROFILES,
)


@dataclass
class BlockingLayerConfig:
    """
    Defines positioning and configuration for a row of blocking.
    
    Attributes:
        height: Height from bottom plate to this row of blocking (in feet)
        pattern: BlockingPattern enum indicating the pattern to use
        profile_override: Optional override for the profile to use (default is wall profile)
    """
    height: float
    pattern: BlockingPattern = BlockingPattern.INLINE
    profile_override: Optional[str] = None


class BlockingParameters:
    """
    Parameters for row blocking configuration.
    
    Attributes:
        include_blocking: Whether to include blocking
        block_spacing: Vertical spacing between blocks in feet
        first_block_height: Height of first row of blocking from bottom of wall in feet
        pattern: Pattern of blocking arrangement (inline or staggered)
    """
    
    def __init__(
        self,
        include_blocking: bool = FRAMING_PARAMS.get("include_blocking", True),
        block_spacing: float = FRAMING_PARAMS.get("block_spacing", 48.0/12.0),  # 4ft default
        first_block_height: float = FRAMING_PARAMS.get("first_block_height", 24.0/12.0),  # 2ft default
        pattern: Union[BlockingPattern, str] = None
    ):
        """
        Initialize blocking parameters.
        
        Args:
            include_blocking: Whether to include blocking in the wall
            block_spacing: Vertical spacing between rows of blocking in feet
            first_block_height: Height of first row of blocking in feet from wall base
            pattern: Block pattern arrangement (inline or staggered)
        """
        self.include_blocking = include_blocking
        self.block_spacing = block_spacing
        self.first_block_height = first_block_height
        
        # Handle string or enum pattern value
        if pattern is None:
            pattern_value = FRAMING_PARAMS.get("blocking_pattern", "inline")
            if isinstance(pattern_value, str):
                pattern_str = pattern_value.lower().strip()
                if pattern_str == "staggered":
                    self.pattern = BlockingPattern.STAGGERED
                else:
                    self.pattern = BlockingPattern.INLINE
            else:
                self.pattern = pattern_value
        elif isinstance(pattern, str):
            pattern_str = pattern.lower().strip()
            if pattern_str == "staggered":
                self.pattern = BlockingPattern.STAGGERED
            else:
                self.pattern = BlockingPattern.INLINE
        else:
            self.pattern = pattern
    
    def get_block_profile(self, wall_profile_name: str) -> str:
        """
        Get the block profile name based on the wall profile.
        
        Args:
            wall_profile_name: Name of the wall profile
            
        Returns:
            Name of profile to use for blocking elements
        """
        # For most wall types, blocks use the same profile as the wall
        return wall_profile_name
    
    def calculate_block_heights(self, wall_height: float) -> List[float]:
        """
        Calculate blocking heights for a wall of a given height.
        
        Args:
            wall_height: Total height of the wall in feet
            
        Returns:
            List of heights from wall base to blocking center
        """
        # Validate input
        if wall_height <= 0:
            return []
            
        # If blocking is disabled, return empty list
        if not self.include_blocking:
            return []
            
        # Start with the first block height
        heights = [self.first_block_height]
        
        # Add additional heights based on spacing
        current_height = self.first_block_height
        
        # Keep adding heights until we exceed the wall height
        while current_height + self.block_spacing < wall_height:
            current_height += self.block_spacing
            heights.append(current_height)
            
        return heights
        
    def __str__(self) -> str:
        """Return string representation of blocking parameters."""
        return (f"BlockingParameters(include={self.include_blocking}, "
                f"spacing={self.block_spacing}, "
                f"first_height={self.first_block_height}, "
                f"pattern={self.pattern})")
                
    def __repr__(self) -> str:
        """Return representation of blocking parameters."""
        return self.__str__()
