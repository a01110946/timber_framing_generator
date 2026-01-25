# File: src/timber_framing_generator/core/__init__.py
"""
Core abstractions for the offsite framing generator.

This module provides material-agnostic and component-agnostic base classes
and enums for supporting:
- Multiple framing material systems (Timber, CFS, etc.)
- Multiple building component types (Walls, Floors, Roofs)
- MEP system integration (Plumbing, HVAC, Electrical)
"""

# Material system (existing)
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

# Component types (NEW)
from .component_types import ComponentType

# Building component abstraction (NEW)
from .building_component import BuildingComponent

# MEP system abstractions (NEW)
from .mep_system import (
    MEPDomain,
    MEPConnector,
    MEPRoute,
    MEPSystem,
)

# JSON schemas (existing)
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
    # Component types (NEW)
    "ComponentType",
    # Building component (NEW)
    "BuildingComponent",
    # MEP system (NEW)
    "MEPDomain",
    "MEPConnector",
    "MEPRoute",
    "MEPSystem",
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
