# File: src/timber_framing_generator/materials/timber/timber_strategy.py
"""
Timber framing strategy implementation.

This module provides TimberFramingStrategy which implements the FramingStrategy
interface for standard timber/lumber wall framing. It wraps the existing
framing generation logic while conforming to the material-agnostic interface.

Usage:
    from src.timber_framing_generator.core import (
        get_framing_strategy, MaterialSystem
    )

    # Get timber strategy via factory
    strategy = get_framing_strategy(MaterialSystem.TIMBER)

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
from .timber_profiles import (
    TIMBER_PROFILES,
    DEFAULT_TIMBER_PROFILES,
    get_timber_profile,
)


class TimberFramingStrategy(FramingStrategy):
    """
    Timber framing strategy implementing the FramingStrategy interface.

    This strategy generates standard timber wall framing elements including:
    - Plates (bottom and top)
    - Studs (standard, king, trimmer)
    - Opening components (headers, sills, cripples)
    - Bracing (row blocking)

    The strategy wraps existing framing generation logic while providing
    a material-agnostic interface that allows for future multi-material
    support (e.g., CFS framing).

    Attributes:
        material_system: Always returns MaterialSystem.TIMBER
        default_profiles: Maps element types to default lumber profiles

    Example:
        >>> strategy = TimberFramingStrategy()
        >>> sequence = strategy.get_generation_sequence()
        >>> print(sequence[0])
        ElementType.BOTTOM_PLATE
    """

    @property
    def material_system(self) -> MaterialSystem:
        """Return the material system this strategy handles."""
        return MaterialSystem.TIMBER

    @property
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        """
        Return default lumber profiles for each element type.

        Returns:
            Dict mapping ElementType to ElementProfile
        """
        return {
            element_type: TIMBER_PROFILES[profile_name]
            for element_type, profile_name in DEFAULT_TIMBER_PROFILES.items()
        }

    def get_generation_sequence(self) -> List[ElementType]:
        """
        Return the order in which element types should be generated.

        Timber framing follows a specific sequence where certain elements
        must be generated before others due to dependencies:
        1. Plates (define top/bottom boundaries)
        2. King studs (frame openings)
        3. Headers and sills (span openings)
        4. Trimmers (support headers)
        5. Cripples (fill above/below openings)
        6. Standard studs (fill remaining space)
        7. Row blocking (lateral bracing)

        Returns:
            Ordered list of ElementType values
        """
        return [
            ElementType.BOTTOM_PLATE,
            ElementType.TOP_PLATE,
            ElementType.KING_STUD,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.TRIMMER,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.STUD,
            ElementType.ROW_BLOCKING,
        ]

    def get_element_types(self) -> List[ElementType]:
        """
        Return all element types used in timber framing.

        Returns:
            List of ElementType values this strategy generates
        """
        return list(DEFAULT_TIMBER_PROFILES.keys())

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
            return get_timber_profile(element_type, override_name)

        return get_timber_profile(element_type)

    def create_horizontal_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate plates (horizontal members) for timber framing.

        This method will delegate to the existing plate generation logic
        and convert the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            config: Configuration parameters

        Returns:
            List of FramingElement for plates

        Note:
            Phase 2 returns empty list - full integration in Phase 3.
        """
        # Phase 2: Placeholder - actual integration in Phase 3
        # Will delegate to existing:
        #   from ..framing_elements.plates import create_plates
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

        This method will delegate to the existing stud generation logic
        and convert the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            horizontal_members: Previously generated plates
            config: Configuration parameters

        Returns:
            List of FramingElement for vertical members

        Note:
            Phase 2 returns empty list - full integration in Phase 3.
        """
        # Phase 2: Placeholder - actual integration in Phase 3
        # Will delegate to existing:
        #   from ..framing_elements.studs import StudGenerator
        #   from ..framing_elements.king_studs import KingStudGenerator
        #   from ..framing_elements.trimmers import TrimmerGenerator
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

        This method will delegate to the existing opening component
        generation logic and convert the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for opening members

        Note:
            Phase 2 returns empty list - full integration in Phase 3.
        """
        # Phase 2: Placeholder - actual integration in Phase 3
        # Will delegate to existing:
        #   from ..framing_elements.headers import HeaderGenerator
        #   from ..framing_elements.sills import SillGenerator
        #   from ..framing_elements.header_cripples import HeaderCrippleGenerator
        #   from ..framing_elements.sill_cripples import SillCrippleGenerator
        return []

    def create_bracing_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate bracing members (row blocking for timber).

        This method will delegate to the existing row blocking generation
        logic and convert the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for bracing members

        Note:
            Phase 2 returns empty list - full integration in Phase 3.
        """
        # Phase 2: Placeholder - actual integration in Phase 3
        # Will delegate to existing:
        #   from ..framing_elements.row_blocking import RowBlockingGenerator
        return []


# =============================================================================
# Strategy Registration
# =============================================================================

# Register the timber strategy when this module is imported
# This allows get_framing_strategy(MaterialSystem.TIMBER) to work
_timber_strategy = TimberFramingStrategy()
register_strategy(_timber_strategy)
