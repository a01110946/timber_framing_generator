# File: src/timber_framing_generator/components/__init__.py
"""
Building components module.

This module contains component-specific implementations for walls, floors,
and roofs. Each component type has its own submodule with:
- Data extraction from Revit
- Cell decomposition logic
- Component-specific framing patterns

Submodules:
    walls: Wall component handling
    floors: Floor component handling (future)
    roofs: Roof component handling (future)
"""

from src.timber_framing_generator.core.component_types import ComponentType

__all__ = [
    "ComponentType",
]
