# File: src/timber_framing_generator/core/json_schemas.py
"""
JSON schema definitions for inter-component communication.

This module defines the JSON structures used to pass data between
modular GHPython components. All data is serialized as JSON strings
to enable inspection, caching, and API integration.

Schemas:
    - WallDataSchema: Wall geometry and properties
    - CellDataSchema: Cell decomposition results
    - FramingElementsSchema: Generated framing elements
    - ConfigSchema: Configuration parameters

Usage:
    from src.timber_framing_generator.core.json_schemas import (
        WallData, CellData, serialize_wall_data, deserialize_wall_data
    )

    # Serialize wall data
    json_str = serialize_wall_data(wall_data)

    # Deserialize
    wall_data = deserialize_wall_data(json_str)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, Union
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class CellType(Enum):
    """Cell types from cell decomposition."""
    WBC = "WBC"   # Wall Boundary Cell
    OC = "OC"     # Opening Cell
    SC = "SC"     # Stud Cell
    SCC = "SCC"   # Sill Cripple Cell
    HCC = "HCC"   # Header Cripple Cell


class OpeningType(Enum):
    """Types of wall openings."""
    WINDOW = "window"
    DOOR = "door"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Point3D:
    """3D point representation."""
    x: float
    y: float
    z: float

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @classmethod
    def from_tuple(cls, t: Tuple[float, float, float]) -> "Point3D":
        return cls(x=t[0], y=t[1], z=t[2])

    @classmethod
    def from_rhino(cls, point) -> "Point3D":
        """Create from Rhino Point3d."""
        return cls(x=float(point.X), y=float(point.Y), z=float(point.Z))


@dataclass
class Vector3D:
    """3D vector representation."""
    x: float
    y: float
    z: float

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @classmethod
    def from_tuple(cls, t: Tuple[float, float, float]) -> "Vector3D":
        return cls(x=t[0], y=t[1], z=t[2])

    @classmethod
    def from_rhino(cls, vector) -> "Vector3D":
        """Create from Rhino Vector3d."""
        return cls(x=float(vector.X), y=float(vector.Y), z=float(vector.Z))


@dataclass
class PlaneData:
    """Plane representation for JSON serialization."""
    origin: Point3D
    x_axis: Vector3D
    y_axis: Vector3D
    z_axis: Vector3D

    @classmethod
    def from_rhino(cls, plane) -> "PlaneData":
        """Create from Rhino Plane."""
        return cls(
            origin=Point3D.from_rhino(plane.Origin),
            x_axis=Vector3D.from_rhino(plane.XAxis),
            y_axis=Vector3D.from_rhino(plane.YAxis),
            z_axis=Vector3D.from_rhino(plane.ZAxis),
        )


@dataclass
class OpeningData:
    """Wall opening data."""
    id: str
    opening_type: str  # "window" or "door"
    u_start: float     # Start position along wall (U coordinate)
    u_end: float       # End position along wall
    v_start: float     # Bottom of opening (V coordinate)
    v_end: float       # Top of opening
    width: float       # Opening width
    height: float      # Opening height
    sill_height: Optional[float] = None  # Height of sill above floor (windows)


@dataclass
class WallData:
    """
    Complete wall data for JSON serialization.

    This is the output of the Wall Analyzer component and input
    to the Cell Decomposer component.
    """
    wall_id: str
    wall_length: float
    wall_height: float
    wall_thickness: float
    base_elevation: float
    top_elevation: float
    base_plane: PlaneData
    base_curve_start: Point3D
    base_curve_end: Point3D
    openings: List[OpeningData] = field(default_factory=list)
    is_exterior: bool = False
    wall_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CellCorners:
    """Cell corner points in world coordinates."""
    bottom_left: Point3D
    bottom_right: Point3D
    top_right: Point3D
    top_left: Point3D

    def to_list(self) -> List[Tuple[float, float, float]]:
        return [
            self.bottom_left.to_tuple(),
            self.bottom_right.to_tuple(),
            self.top_right.to_tuple(),
            self.top_left.to_tuple(),
        ]


@dataclass
class CellInfo:
    """
    Single cell from wall decomposition.
    """
    id: str
    cell_type: str  # CellType enum value
    u_start: float
    u_end: float
    v_start: float
    v_end: float
    corners: CellCorners
    opening_id: Optional[str] = None  # For OC cells, links to OpeningData
    opening_type: Optional[str] = None  # "window" or "door" for OC cells
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> float:
        """Cell width (U dimension)."""
        return self.u_end - self.u_start

    @property
    def height(self) -> float:
        """Cell height (V dimension)."""
        return self.v_end - self.v_start


@dataclass
class CellData:
    """
    Complete cell decomposition data.

    This is the output of the Cell Decomposer component and input
    to the Framing Generator component.
    """
    wall_id: str
    cells: List[CellInfo]
    wall_data_ref: Optional[WallData] = None  # Optional reference to source wall
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfileData:
    """Profile data for a framing element."""
    name: str
    width: float
    depth: float
    material_system: str  # "timber" or "cfs"
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FramingElementData:
    """
    Single framing element data for JSON serialization.
    """
    id: str
    element_type: str  # ElementType enum value
    profile: ProfileData
    centerline_start: Point3D
    centerline_end: Point3D
    u_coord: float
    v_start: float
    v_end: float
    cell_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> float:
        """Calculate element length."""
        dx = self.centerline_end.x - self.centerline_start.x
        dy = self.centerline_end.y - self.centerline_start.y
        dz = self.centerline_end.z - self.centerline_start.z
        return (dx**2 + dy**2 + dz**2) ** 0.5


@dataclass
class FramingResults:
    """
    Complete framing generation results.

    This is the output of the Framing Generator component and input
    to the Geometry Converter component.
    """
    wall_id: str
    material_system: str  # "timber" or "cfs"
    elements: List[FramingElementData]
    element_counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Custom JSON Encoder
# =============================================================================

class FramingJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for framing data classes."""

    def default(self, obj):
        if hasattr(obj, '__dataclass_fields__'):
            return asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


# =============================================================================
# Serialization Functions
# =============================================================================

def serialize_wall_data(wall_data: WallData) -> str:
    """Serialize WallData to JSON string."""
    return json.dumps(asdict(wall_data), cls=FramingJSONEncoder, indent=2)


def deserialize_wall_data(json_str: str) -> WallData:
    """Deserialize JSON string to WallData."""
    data = json.loads(json_str)

    # Reconstruct nested objects
    base_plane = PlaneData(
        origin=Point3D(**data['base_plane']['origin']),
        x_axis=Vector3D(**data['base_plane']['x_axis']),
        y_axis=Vector3D(**data['base_plane']['y_axis']),
        z_axis=Vector3D(**data['base_plane']['z_axis']),
    )

    openings = [OpeningData(**o) for o in data.get('openings', [])]

    return WallData(
        wall_id=data['wall_id'],
        wall_length=data['wall_length'],
        wall_height=data['wall_height'],
        wall_thickness=data['wall_thickness'],
        base_elevation=data['base_elevation'],
        top_elevation=data['top_elevation'],
        base_plane=base_plane,
        base_curve_start=Point3D(**data['base_curve_start']),
        base_curve_end=Point3D(**data['base_curve_end']),
        openings=openings,
        is_exterior=data.get('is_exterior', False),
        wall_type=data.get('wall_type'),
        metadata=data.get('metadata', {}),
    )


def serialize_cell_data(cell_data: CellData) -> str:
    """Serialize CellData to JSON string."""
    return json.dumps(asdict(cell_data), cls=FramingJSONEncoder, indent=2)


def deserialize_cell_data(json_str: str) -> CellData:
    """Deserialize JSON string to CellData."""
    data = json.loads(json_str)

    cells = []
    for c in data.get('cells', []):
        corners = CellCorners(
            bottom_left=Point3D(**c['corners']['bottom_left']),
            bottom_right=Point3D(**c['corners']['bottom_right']),
            top_right=Point3D(**c['corners']['top_right']),
            top_left=Point3D(**c['corners']['top_left']),
        )
        cell = CellInfo(
            id=c['id'],
            cell_type=c['cell_type'],
            u_start=c['u_start'],
            u_end=c['u_end'],
            v_start=c['v_start'],
            v_end=c['v_end'],
            corners=corners,
            opening_id=c.get('opening_id'),
            opening_type=c.get('opening_type'),
            metadata=c.get('metadata', {}),
        )
        cells.append(cell)

    return CellData(
        wall_id=data['wall_id'],
        cells=cells,
        wall_data_ref=None,  # Not deserialized to avoid duplication
        metadata=data.get('metadata', {}),
    )


def serialize_framing_results(results: FramingResults) -> str:
    """Serialize FramingResults to JSON string."""
    return json.dumps(asdict(results), cls=FramingJSONEncoder, indent=2)


def deserialize_framing_results(json_str: str) -> FramingResults:
    """Deserialize JSON string to FramingResults."""
    data = json.loads(json_str)

    elements = []
    for e in data.get('elements', []):
        profile = ProfileData(**e['profile'])
        element = FramingElementData(
            id=e['id'],
            element_type=e['element_type'],
            profile=profile,
            centerline_start=Point3D(**e['centerline_start']),
            centerline_end=Point3D(**e['centerline_end']),
            u_coord=e['u_coord'],
            v_start=e['v_start'],
            v_end=e['v_end'],
            cell_id=e.get('cell_id'),
            metadata=e.get('metadata', {}),
        )
        elements.append(element)

    return FramingResults(
        wall_id=data['wall_id'],
        material_system=data['material_system'],
        elements=elements,
        element_counts=data.get('element_counts', {}),
        metadata=data.get('metadata', {}),
    )


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_wall_data(data: Union[str, Dict, WallData]) -> Tuple[bool, List[str]]:
    """
    Validate wall data structure.

    Args:
        data: JSON string, dict, or WallData object

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    try:
        if isinstance(data, str):
            data = json.loads(data)

        if isinstance(data, WallData):
            data = asdict(data)

        # Required fields
        required = ['wall_id', 'wall_length', 'wall_height', 'base_plane']
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Dimension validation
        if data.get('wall_length', 0) <= 0:
            errors.append("wall_length must be positive")
        if data.get('wall_height', 0) <= 0:
            errors.append("wall_height must be positive")

        # Base plane validation
        if 'base_plane' in data:
            plane = data['base_plane']
            if 'origin' not in plane:
                errors.append("base_plane missing origin")

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {str(e)}")
    except Exception as e:
        errors.append(f"Validation error: {str(e)}")

    return len(errors) == 0, errors


def validate_cell_data(data: Union[str, Dict, CellData]) -> Tuple[bool, List[str]]:
    """
    Validate cell data structure.

    Args:
        data: JSON string, dict, or CellData object

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    try:
        if isinstance(data, str):
            data = json.loads(data)

        if isinstance(data, CellData):
            data = asdict(data)

        # Required fields
        if 'wall_id' not in data:
            errors.append("Missing required field: wall_id")
        if 'cells' not in data:
            errors.append("Missing required field: cells")

        # Cell validation
        for i, cell in enumerate(data.get('cells', [])):
            if 'cell_type' not in cell:
                errors.append(f"Cell {i} missing cell_type")
            if 'u_start' not in cell or 'u_end' not in cell:
                errors.append(f"Cell {i} missing U coordinates")
            if 'v_start' not in cell or 'v_end' not in cell:
                errors.append(f"Cell {i} missing V coordinates")

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {str(e)}")
    except Exception as e:
        errors.append(f"Validation error: {str(e)}")

    return len(errors) == 0, errors
