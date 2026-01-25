# File: src/timber_framing_generator/core/building_component.py
"""
Abstract base class for building components.

This module defines the BuildingComponent ABC which provides a unified
interface for handling different building component types (walls, floors,
roofs). Each component type implements this interface with component-specific
logic for data extraction, cell decomposition, and MEP zone identification.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any

from .component_types import ComponentType


class BuildingComponent(ABC):
    """
    Abstract base class for building components.

    Building components represent the major structural assemblies of a building
    that can be framed (walls, floors, roofs). Each component type has:
    - Unique data extraction logic from Revit elements
    - Specific cell decomposition strategies
    - Different framing element types
    - Distinct MEP penetration patterns

    Subclasses must implement all abstract methods to provide
    component-specific behavior while conforming to the common interface.

    Example:
        >>> class WallComponent(BuildingComponent):
        ...     @property
        ...     def component_type(self) -> ComponentType:
        ...         return ComponentType.WALL
        ...
        ...     def extract_data(self, revit_element):
        ...         # Wall-specific extraction logic
        ...         pass
    """

    @property
    @abstractmethod
    def component_type(self) -> ComponentType:
        """
        Return the type of this component.

        Returns:
            ComponentType enum value identifying this component
        """
        pass

    @abstractmethod
    def extract_data(self, revit_element: Any) -> Dict[str, Any]:
        """
        Extract component data from a Revit element.

        This method converts a Revit element (Wall, Floor, RoofBase, etc.)
        into a standardized dictionary format that can be used by the
        framing generation system.

        Args:
            revit_element: Revit element (Wall, Floor, RoofBase, etc.)

        Returns:
            Dictionary containing standardized component data:
            - geometry: Boundary curves, openings, etc.
            - properties: Type, materials, dimensions
            - levels: Base and top level information
            - metadata: Element ID, category, etc.
        """
        pass

    @abstractmethod
    def decompose_to_cells(
        self,
        component_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Decompose component into cells for framing.

        Cells are regions within a component where framing members are placed.
        Each component type has its own cell decomposition strategy:
        - Walls: WBC, OC, SC, SCC, HCC cells
        - Floors: Joist bays, opening cells
        - Roofs: Rafter bays, valley/hip cells

        Args:
            component_data: Extracted component data from extract_data()
            config: Decomposition configuration (spacing, tolerances, etc.)

        Returns:
            List of cell dictionaries, each containing:
            - id: Unique cell identifier
            - cell_type: Type of cell (component-specific)
            - bounds: Cell boundary geometry
            - metadata: Additional cell information
        """
        pass

    @abstractmethod
    def get_framing_element_types(self) -> List[str]:
        """
        Return list of framing element types for this component.

        Each component type uses different framing elements:
        - Walls: bottom_plate, top_plate, stud, king_stud, header, sill, etc.
        - Floors: rim_board, joist, blocking, bridging, etc.
        - Roofs: rafter, ridge_board, collar_tie, etc.

        Returns:
            List of element type strings used by this component
        """
        pass

    def get_mep_zones(
        self,
        component_data: Dict[str, Any],
        framing_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Identify zones where MEP can be routed.

        MEP zones are regions between framing members where pipes, ducts,
        or conduits can pass through. This method analyzes the framing
        layout to identify valid routing zones.

        This method has a default implementation that returns an empty list.
        Subclasses can override to provide component-specific MEP zone logic.

        Args:
            component_data: Extracted component data
            framing_data: Generated framing element data

        Returns:
            List of MEP zone dictionaries, each containing:
            - id: Unique zone identifier
            - zone_type: Type of zone (stud_bay, joist_bay, etc.)
            - bounds: Zone boundary geometry
            - max_penetration_size: Maximum allowed penetration diameter
        """
        # Default implementation - subclasses should override
        return []

    def validate_component_data(self, component_data: Dict[str, Any]) -> bool:
        """
        Validate extracted component data.

        Checks that the component data contains all required fields
        and that values are within acceptable ranges.

        Args:
            component_data: Data to validate

        Returns:
            True if data is valid, False otherwise
        """
        # Basic validation - subclasses can extend
        required_keys = ["id", "geometry", "properties"]
        return all(key in component_data for key in required_keys)
