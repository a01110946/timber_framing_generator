# File: tests/core/test_component_types.py
"""Tests for ComponentType enum."""

import pytest
from src.timber_framing_generator.core.component_types import ComponentType


class TestComponentType:
    """Test cases for ComponentType enum."""

    def test_all_types_defined(self):
        """All expected component types are defined."""
        assert hasattr(ComponentType, "WALL")
        assert hasattr(ComponentType, "FLOOR")
        assert hasattr(ComponentType, "ROOF")
        assert hasattr(ComponentType, "CEILING")

    def test_values(self):
        """Component types have correct string values."""
        assert ComponentType.WALL.value == "wall"
        assert ComponentType.FLOOR.value == "floor"
        assert ComponentType.ROOF.value == "roof"
        assert ComponentType.CEILING.value == "ceiling"

    def test_str(self):
        """String representation returns value."""
        assert str(ComponentType.WALL) == "wall"
        assert str(ComponentType.FLOOR) == "floor"

    def test_from_string_valid(self):
        """from_string creates correct type from valid string."""
        assert ComponentType.from_string("wall") == ComponentType.WALL
        assert ComponentType.from_string("FLOOR") == ComponentType.FLOOR
        assert ComponentType.from_string("Roof") == ComponentType.ROOF

    def test_from_string_invalid(self):
        """from_string raises ValueError for invalid string."""
        with pytest.raises(ValueError, match="Unknown component type"):
            ComponentType.from_string("invalid")

    def test_iteration(self):
        """Can iterate over all component types."""
        types = list(ComponentType)
        assert len(types) == 4
        assert ComponentType.WALL in types
        assert ComponentType.FLOOR in types


class TestComponentTypeImport:
    """Test that ComponentType can be imported from various paths."""

    def test_import_from_core(self):
        """Can import from core module."""
        from src.timber_framing_generator.core import ComponentType as CT
        assert CT.WALL.value == "wall"

    def test_import_from_component_types(self):
        """Can import directly from component_types module."""
        from src.timber_framing_generator.core.component_types import ComponentType as CT
        assert CT.FLOOR.value == "floor"
