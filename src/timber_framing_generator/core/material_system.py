# File: src/timber_framing_generator/core/material_system.py
"""
Material system abstractions for multi-material framing support.

This module defines the core abstractions that allow the framing generator
to support different material systems (Timber, Cold-Formed Steel, etc.)
through a strategy pattern.

Usage:
    from src.timber_framing_generator.core import MaterialSystem, FramingStrategy

    # Get the appropriate strategy for a material
    strategy = get_framing_strategy(MaterialSystem.TIMBER)
    elements = strategy.generate_framing(wall_data, cell_data, config)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple


class MaterialSystem(Enum):
    """
    Enumeration of supported framing material systems.

    Each material system has different element types, profiles,
    and generation sequences.
    """
    TIMBER = "timber"
    CFS = "cfs"  # Cold-Formed Steel


class ElementType(Enum):
    """
    Base enumeration of framing element types.

    Some types are shared across material systems (studs, headers),
    while others are material-specific (plates vs tracks).
    """
    # Horizontal members
    BOTTOM_PLATE = "bottom_plate"       # Timber: bottom plate
    TOP_PLATE = "top_plate"             # Timber: top plate(s)
    BOTTOM_TRACK = "bottom_track"       # CFS: bottom track
    TOP_TRACK = "top_track"             # CFS: top track

    # Vertical members
    STUD = "stud"
    KING_STUD = "king_stud"
    TRIMMER = "trimmer"

    # Opening components
    HEADER = "header"
    SILL = "sill"
    HEADER_CRIPPLE = "header_cripple"
    SILL_CRIPPLE = "sill_cripple"

    # Bracing/blocking
    ROW_BLOCKING = "row_blocking"       # Timber: solid blocking
    BRIDGING = "bridging"               # CFS: bridging
    WEB_STIFFENER = "web_stiffener"     # CFS: web stiffeners


@dataclass
class ElementProfile:
    """
    Profile definition for a framing element.

    Profiles define the cross-sectional dimensions and shape
    of framing members. Different material systems use different
    profile conventions.

    Attributes:
        name: Profile designation (e.g., "2x4", "600S162-54")
        width: Width of the profile (perpendicular to wall, W direction)
        depth: Depth of the profile (along wall, U direction for studs)
        material_system: Which material system this profile belongs to
        properties: Additional material-specific properties
    """
    name: str
    width: float  # W direction (wall thickness)
    depth: float  # U direction (along wall face)
    material_system: MaterialSystem
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate profile dimensions are positive."""
        if self.width <= 0 or self.depth <= 0:
            raise ValueError(f"Profile dimensions must be positive: width={self.width}, depth={self.depth}")


@dataclass
class FramingElement:
    """
    Data representation of a single framing element.

    This is a material-agnostic representation containing all information
    needed to create geometry. Geometry is NOT stored here - only the
    parameters needed to create it.

    Attributes:
        id: Unique identifier for this element
        element_type: Type of framing element
        profile: Profile definition for this element
        centerline_start: Start point of centerline (x, y, z) in world coords
        centerline_end: End point of centerline (x, y, z) in world coords
        u_coord: U coordinate in wall-local system (for sorting/grouping)
        v_start: V start coordinate in wall-local system
        v_end: V end coordinate in wall-local system
        cell_id: ID of the cell this element belongs to (if applicable)
        metadata: Additional element-specific data
    """
    id: str
    element_type: ElementType
    profile: ElementProfile
    centerline_start: Tuple[float, float, float]
    centerline_end: Tuple[float, float, float]
    u_coord: float
    v_start: float
    v_end: float
    cell_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> float:
        """Calculate element length from centerline."""
        dx = self.centerline_end[0] - self.centerline_start[0]
        dy = self.centerline_end[1] - self.centerline_start[1]
        dz = self.centerline_end[2] - self.centerline_start[2]
        return (dx**2 + dy**2 + dz**2) ** 0.5

    @property
    def is_vertical(self) -> bool:
        """Check if element is vertical (V direction dominant)."""
        dx = abs(self.centerline_end[0] - self.centerline_start[0])
        dy = abs(self.centerline_end[1] - self.centerline_start[1])
        dz = abs(self.centerline_end[2] - self.centerline_start[2])
        return dz > max(dx, dy)


class FramingStrategy(ABC):
    """
    Abstract base class for material-specific framing strategies.

    Each material system (Timber, CFS) implements this interface
    to provide its specific element types, profiles, and generation logic.

    The strategy pattern allows the core framing pipeline to remain
    material-agnostic while delegating material-specific decisions
    to the appropriate strategy implementation.
    """

    @property
    @abstractmethod
    def material_system(self) -> MaterialSystem:
        """Return the material system this strategy handles."""
        pass

    @property
    @abstractmethod
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        """Return default profiles for each element type."""
        pass

    @abstractmethod
    def get_generation_sequence(self) -> List[ElementType]:
        """
        Return the order in which element types should be generated.

        Different materials may have different dependency chains.
        For example, timber generates plates first, then studs.
        CFS may generate tracks, then studs, then bridging.

        Returns:
            Ordered list of ElementType values
        """
        pass

    @abstractmethod
    def get_element_types(self) -> List[ElementType]:
        """
        Return all element types used by this material system.

        Returns:
            List of ElementType values this strategy generates
        """
        pass

    @abstractmethod
    def create_horizontal_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate horizontal members (plates/tracks).

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            config: Configuration parameters

        Returns:
            List of FramingElement for horizontal members
        """
        pass

    @abstractmethod
    def create_vertical_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        horizontal_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate vertical members (studs, king studs, trimmers).

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            horizontal_members: Previously generated horizontal members
            config: Configuration parameters

        Returns:
            List of FramingElement for vertical members
        """
        pass

    @abstractmethod
    def create_opening_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate opening-related members (headers, sills, cripples).

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for opening members
        """
        pass

    @abstractmethod
    def create_bracing_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate bracing/blocking members.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for bracing members
        """
        pass

    def generate_framing(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None
    ) -> List[FramingElement]:
        """
        Generate all framing elements for a wall.

        This is the main entry point that orchestrates element generation
        in the correct order based on get_generation_sequence().

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            config: Optional configuration overrides

        Returns:
            List of all FramingElement objects for this wall
        """
        config = config or {}
        all_elements: List[FramingElement] = []

        # Generate in sequence to respect dependencies
        horizontal = self.create_horizontal_members(wall_data, cell_data, config)
        all_elements.extend(horizontal)

        vertical = self.create_vertical_members(
            wall_data, cell_data, horizontal, config
        )
        all_elements.extend(vertical)

        existing = horizontal + vertical
        opening = self.create_opening_members(
            wall_data, cell_data, existing, config
        )
        all_elements.extend(opening)

        existing.extend(opening)
        bracing = self.create_bracing_members(
            wall_data, cell_data, existing, config
        )
        all_elements.extend(bracing)

        return all_elements


class StrategyFactory:
    """
    Factory for creating material-specific framing strategies.

    Usage:
        factory = StrategyFactory()
        factory.register(TimberStrategy())
        factory.register(CFSStrategy())

        strategy = factory.get_strategy(MaterialSystem.TIMBER)
    """

    def __init__(self):
        self._strategies: Dict[MaterialSystem, FramingStrategy] = {}

    def register(self, strategy: FramingStrategy) -> None:
        """Register a strategy for its material system."""
        self._strategies[strategy.material_system] = strategy

    def get_strategy(self, material_system: MaterialSystem) -> FramingStrategy:
        """Get the strategy for a material system."""
        if material_system not in self._strategies:
            available = [m.value for m in self._strategies.keys()]
            raise ValueError(
                f"No strategy registered for {material_system.value}. "
                f"Available: {available}"
            )
        return self._strategies[material_system]

    def list_available(self) -> List[MaterialSystem]:
        """List all registered material systems."""
        return list(self._strategies.keys())


# Global factory instance (populated by material implementations)
_strategy_factory = StrategyFactory()


def get_framing_strategy(material_system: MaterialSystem) -> FramingStrategy:
    """
    Get the framing strategy for a material system.

    Args:
        material_system: The material system to get a strategy for

    Returns:
        FramingStrategy implementation for the requested material

    Raises:
        ValueError: If no strategy is registered for the material
    """
    return _strategy_factory.get_strategy(material_system)


def register_strategy(strategy: FramingStrategy) -> None:
    """
    Register a framing strategy.

    Called by material implementations to register themselves.

    Args:
        strategy: The strategy to register
    """
    _strategy_factory.register(strategy)


def list_available_materials() -> List[MaterialSystem]:
    """
    List all available material systems.

    Returns:
        List of MaterialSystem values that have registered strategies
    """
    return _strategy_factory.list_available()
