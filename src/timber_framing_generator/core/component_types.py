# File: src/timber_framing_generator/core/component_types.py
"""
Building component type definitions.

This module defines the types of building components that can be framed
by the offsite construction system. Each component type has its own
data extraction, cell decomposition, and framing generation logic.
"""

from enum import Enum


class ComponentType(Enum):
    """
    Types of building components that can be framed.

    Each component type has its own:
    - Data extraction logic (from Revit)
    - Cell decomposition strategy
    - Framing element types
    - MEP penetration patterns

    Attributes:
        WALL: Vertical wall assemblies (studs, plates, headers, etc.)
        FLOOR: Horizontal floor assemblies (joists, rim boards, blocking)
        ROOF: Sloped roof assemblies (rafters, ridge, collar ties)
        CEILING: Horizontal ceiling assemblies (ceiling joists)
    """
    WALL = "wall"
    FLOOR = "floor"
    ROOF = "roof"
    CEILING = "ceiling"

    def __str__(self) -> str:
        """Return the string value for display."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "ComponentType":
        """
        Create ComponentType from string value.

        Args:
            value: String value (e.g., "wall", "floor")

        Returns:
            Corresponding ComponentType enum member

        Raises:
            ValueError: If value doesn't match any component type
        """
        value_lower = value.lower()
        for member in cls:
            if member.value == value_lower:
                return member
        raise ValueError(
            f"Unknown component type: {value}. "
            f"Valid types: {[m.value for m in cls]}"
        )
