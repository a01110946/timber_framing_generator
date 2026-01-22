# File: src/timber_framing_generator/materials/cfs/cfs_strategy.py
"""
CFS (Cold-Formed Steel) framing strategy implementation.

This module provides CFSFramingStrategy which implements the FramingStrategy
interface for light-gauge steel stud wall framing. It provides the same
material-agnostic interface as TimberFramingStrategy, enabling material
switching at runtime.

Usage:
    from src.timber_framing_generator.core import (
        get_framing_strategy, MaterialSystem
    )

    # Get CFS strategy via factory
    strategy = get_framing_strategy(MaterialSystem.CFS)

    # Generate framing elements
    elements = strategy.generate_framing(wall_data, cell_data, config)
"""

from typing import Dict, List, Any

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    FramingStrategy,
    ElementType,
    ElementProfile,
    FramingElement,
    register_strategy,
)
from .cfs_profiles import (
    CFS_PROFILES,
    DEFAULT_CFS_PROFILES,
    get_cfs_profile,
)


class CFSFramingStrategy(FramingStrategy):
    """
    CFS framing strategy implementing the FramingStrategy interface.

    This strategy generates cold-formed steel wall framing elements including:
    - Tracks (bottom and top - equivalent to plates)
    - Studs (standard, king, trimmer)
    - Opening components (headers, sills, cripples)
    - Bracing (bridging)

    The strategy provides a material-agnostic interface that allows for
    seamless switching between timber and CFS framing systems.

    Key CFS Differences from Timber:
        - Uses tracks (no lips) instead of plates for top/bottom
        - Uses C-section studs with lips for vertical members
        - Headers typically made from back-to-back studs
        - Bridging/blocking uses stud sections
        - All connections via screws (not nails)

    Attributes:
        material_system: Always returns MaterialSystem.CFS
        default_profiles: Maps element types to default CFS profiles

    Example:
        >>> strategy = CFSFramingStrategy()
        >>> sequence = strategy.get_generation_sequence()
        >>> print(sequence[0])
        ElementType.BOTTOM_PLATE
    """

    @property
    def material_system(self) -> MaterialSystem:
        """Return the material system this strategy handles."""
        return MaterialSystem.CFS

    @property
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        """
        Return default CFS profiles for each element type.

        Returns:
            Dict mapping ElementType to ElementProfile
        """
        return {
            element_type: CFS_PROFILES[profile_name]
            for element_type, profile_name in DEFAULT_CFS_PROFILES.items()
        }

    def get_generation_sequence(self) -> List[ElementType]:
        """
        Return the order in which element types should be generated.

        CFS framing follows a similar sequence to timber framing:
        1. Tracks (define top/bottom boundaries)
        2. King studs (frame openings)
        3. Headers and sills (span openings)
        4. Trimmers (support headers)
        5. Cripples (fill above/below openings)
        6. Standard studs (fill remaining space)
        7. Bridging (lateral bracing)

        Returns:
            Ordered list of ElementType values
        """
        return [
            ElementType.BOTTOM_PLATE,   # Bottom track
            ElementType.TOP_PLATE,      # Top track
            ElementType.KING_STUD,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.TRIMMER,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.STUD,
            ElementType.ROW_BLOCKING,   # Bridging in CFS terminology
        ]

    def get_element_types(self) -> List[ElementType]:
        """
        Return all element types used in CFS framing.

        Returns:
            List of ElementType values this strategy generates
        """
        return list(DEFAULT_CFS_PROFILES.keys())

    def get_profile(
        self,
        element_type: ElementType,
        config: Dict[str, Any] = None
    ) -> ElementProfile:
        """
        Get the profile for a specific element type.

        Checks config for profile overrides, otherwise uses default.

        Args:
            element_type: The type of framing element
            config: Optional configuration with profile overrides

        Returns:
            ElementProfile for the element type
        """
        config = config or {}
        profile_overrides = config.get("profile_overrides", {})

        # Check for override in config
        override_name = profile_overrides.get(element_type.value)
        if override_name:
            return get_cfs_profile(element_type, override_name)

        return get_cfs_profile(element_type)

    def create_horizontal_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate tracks (horizontal members) for CFS framing.

        In CFS framing, tracks (C-sections without lips) are used
        instead of plates for the top and bottom horizontal members.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            config: Configuration parameters

        Returns:
            List of FramingElement for tracks

        Note:
            Phase 4 returns empty list - full integration in Phase 5.
        """
        # Phase 4: Placeholder - actual integration in Phase 5
        # Will delegate to track generation logic
        return []

    def create_vertical_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        horizontal_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate vertical members (studs, king studs, trimmers).

        In CFS framing, C-section studs with lips are used for
        vertical members. Studs fit inside tracks (flanges overlap).

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            horizontal_members: Previously generated tracks
            config: Configuration parameters

        Returns:
            List of FramingElement for vertical members

        Note:
            Phase 4 returns empty list - full integration in Phase 5.
        """
        # Phase 4: Placeholder - actual integration in Phase 5
        # Will delegate to CFS stud generation logic
        return []

    def create_opening_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate opening-related members (headers, sills, cripples).

        CFS headers are typically made from:
        - Back-to-back studs
        - Box headers (4 pieces)
        - L-headers for light loads

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for opening members

        Note:
            Phase 4 returns empty list - full integration in Phase 5.
        """
        # Phase 4: Placeholder - actual integration in Phase 5
        # Will delegate to CFS header/sill generation logic
        return []

    def create_bracing_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate bracing members (bridging for CFS).

        CFS bridging provides lateral bracing and typically consists of:
        - Flat strap bridging
        - Cold-rolled channel bridging
        - Stud sections as blocking

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for bracing members

        Note:
            Phase 4 returns empty list - full integration in Phase 5.
        """
        # Phase 4: Placeholder - actual integration in Phase 5
        # Will delegate to CFS bridging generation logic
        return []


# =============================================================================
# Strategy Registration
# =============================================================================

# Register the CFS strategy when this module is imported
# This allows get_framing_strategy(MaterialSystem.CFS) to work
_cfs_strategy = CFSFramingStrategy()
register_strategy(_cfs_strategy)
