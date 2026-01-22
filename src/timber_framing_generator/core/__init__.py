# File: src/timber_framing_generator/core/__init__.py
"""
Core abstractions for the timber framing generator.

This module provides material-agnostic base classes and enums
for supporting multiple framing material systems (Timber, CFS, etc.).
"""

from .material_system import (
    MaterialSystem,
    ElementType,
    FramingStrategy,
    ElementProfile,
    FramingElement,
    StrategyFactory,
    get_framing_strategy,
    register_strategy,
    list_available_materials,
)

from .json_schemas import (
    # Data classes
    Point3D,
    Vector3D,
    PlaneData,
    OpeningData,
    WallData,
    CellCorners,
    CellInfo,
    CellData,
    ProfileData,
    FramingElementData,
    FramingResults,
    # Enums
    CellType,
    OpeningType,
    # Serialization
    serialize_wall_data,
    deserialize_wall_data,
    serialize_cell_data,
    deserialize_cell_data,
    serialize_framing_results,
    deserialize_framing_results,
    # Validation
    validate_wall_data,
    validate_cell_data,
)

__all__ = [
    # Material system
    "MaterialSystem",
    "ElementType",
    "FramingStrategy",
    "ElementProfile",
    "FramingElement",
    "StrategyFactory",
    "get_framing_strategy",
    "register_strategy",
    "list_available_materials",
    # JSON schemas
    "Point3D",
    "Vector3D",
    "PlaneData",
    "OpeningData",
    "WallData",
    "CellCorners",
    "CellInfo",
    "CellData",
    "ProfileData",
    "FramingElementData",
    "FramingResults",
    "CellType",
    "OpeningType",
    "serialize_wall_data",
    "deserialize_wall_data",
    "serialize_cell_data",
    "deserialize_cell_data",
    "serialize_framing_results",
    "deserialize_framing_results",
    "validate_wall_data",
    "validate_cell_data",
]
