# Data Structure Specification - Timber Framing Generator

## Introduction

This document provides detailed specifications for all data structures used in the Timber Framing Generator project. Understanding these structures is crucial for developing new features, debugging issues, and ensuring proper data flow through the system.

## Type Definitions

The project uses TypedDict, dataclasses, and type aliases for strong typing. Here are the core type definitions:

```python
from typing import Dict, List, Tuple, Union, Optional, Any, TypedDict
from dataclasses import dataclass
import Rhino.Geometry as rg
from Autodesk.Revit import DB

# Type aliases for common types
Point3D = rg.Point3d
Curve3D = rg.Curve
Plane3D = rg.Plane
Brep3D = rg.Brep

# Basic coordinate type
Coordinates = Tuple[float, float, float]
```

## Wall Data Structure

### WallDataInput (API Model)

```python
class WallDataInput(BaseModel):
    """Input data model for wall analysis."""
    wall_type: str
    wall_base_elevation: float
    wall_top_elevation: float
    wall_length: float
    wall_height: float
    is_exterior_wall: bool
    openings: List[OpeningModel] = []
```

### Wall Data Dictionary

The core internal representation of wall data:

```python
class WallData(TypedDict):
    """Internal representation of wall data."""
    wall_type: str                 # Wall type identifier (e.g., "2x4 EXT")
    wall_base_curve: Curve3D       # Base curve of the wall
    wall_length: float             # Length of wall along base curve
    base_plane: Plane3D            # Wall's base plane (origin at start of wall)
    wall_base_elevation: float     # Z-coordinate of wall base
    wall_top_elevation: float      # Z-coordinate of wall top
    wall_height: float             # Height of wall (top_elevation - base_elevation)
    is_exterior_wall: bool         # Whether wall is exterior
    openings: List['OpeningData']  # List of openings in the wall
    cells: List['CellData']        # List of decomposed cells
```

Example wall data:
```python
wall_data = {
    "wall_type": "2x4 EXT",
    "wall_base_curve": wall_curve,  # rg.Curve instance
    "wall_length": 10.0,
    "base_plane": base_plane,       # rg.Plane instance
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_height": 8.0,
    "is_exterior_wall": True,
    "openings": [...],  # List of opening dictionaries
    "cells": [...],     # List of cell dictionaries
}
```

## Opening Data Structure

### OpeningModel (API Model)

```python
class OpeningModel(BaseModel):
    """Data model for wall openings like doors and windows."""
    opening_type: Literal["door", "window"]
    start_u_coordinate: float      # Position along wall length
    rough_width: float             # Width of rough opening
    rough_height: float            # Height of rough opening
    base_elevation_relative_to_wall_base: float  # Height from wall base
```

### OpeningData (Internal)

```python
class OpeningData(TypedDict):
    """Internal representation of wall opening."""
    opening_type: str              # "door" or "window"
    start_u_coordinate: float      # Position along wall (U-coordinate)
    rough_width: float             # Width of rough opening
    rough_height: float            # Height of rough opening
    base_elevation_relative_to_wall_base: float  # Height from wall base
    opening_location_point: Optional[Point3D]    # 3D location point
```

Example opening data:
```python
opening_data = {
    "opening_type": "window",
    "start_u_coordinate": 3.0,        # 3 feet from wall start
    "rough_width": 3.0,               # 3 feet wide
    "rough_height": 4.0,              # 4 feet tall
    "base_elevation_relative_to_wall_base": 3.0,  # 3 feet up from wall base
    "opening_location_point": rg.Point3d(3.0, 0.0, 3.0)
}
```

## Cell Data Structures

### CellData Base Structure

```python
class CellData(TypedDict):
    """Base type for all cell types."""
    cell_type: str           # Cell type code (e.g., "WBC", "OC", "SC")
    u_start: float           # Start position along wall length
    u_end: float             # End position along wall length
    v_start: float           # Start height position
    v_end: float             # End height position
    corner_points: List[Point3D]  # 3D corner points [bl, br, tr, tl]
```

### Specialized Cell Types

```python
class WallBoundaryCell(CellData):
    """Wall Boundary Cell representing the entire wall."""
    pass  # Uses base CellData structure

class OpeningCell(CellData):
    """Opening Cell representing a door or window."""
    opening_type: str        # "door" or "window"

class StudCell(CellData):
    """Stud Cell representing area for standard studs."""
    pass  # Uses base CellData structure

class SillCrippleCell(CellData):
    """Sill Cripple Cell below window openings."""
    pass  # Uses base CellData structure

class HeaderCrippleCell(CellData):
    """Header Cripple Cell above openings."""
    pass  # Uses base CellData structure
```

Example cell data:
```python
wall_boundary_cell = {
    "cell_type": "WBC",
    "u_start": 0.0,
    "u_end": 10.0,
    "v_start": 0.0,
    "v_end": 8.0,
    "corner_points": [
        rg.Point3d(0, 0, 0),      # bottom-left
        rg.Point3d(10, 0, 0),     # bottom-right
        rg.Point3d(10, 0, 8),     # top-right
        rg.Point3d(0, 0, 8)       # top-left
    ]
}

opening_cell = {
    "cell_type": "OC",
    "opening_type": "window",
    "u_start": 3.0,
    "u_end": 6.0,
    "v_start": 3.0,
    "v_end": 7.0,
    "corner_points": [
        rg.Point3d(3, 0, 3),      # bottom-left
        rg.Point3d(6, 0, 3),      # bottom-right
        rg.Point3d(6, 0, 7),      # top-right
        rg.Point3d(3, 0, 7)       # top-left
    ]
}
```

## Framing Element Data Structures

### FramingElement Base Interface

```python
@dataclass
class FramingElementData:
    """Base class for all framing elements."""
    # Core properties
    element_type: str        # Type of framing element
    thickness: float         # Thickness in feet
    width: float             # Width in feet
    length: float            # Length in feet
    
    # Location data
    centerline: Curve3D      # Centerline curve
    profile: rg.Rectangle3d  # Profile rectangle
    
    # Geometric representation
    geometry: Optional[Brep3D] = None  # Solid geometric representation
```

### PlateData Structure

```python
@dataclass
class PlateData(FramingElementData):
    """Data for plate elements."""
    plate_type: str          # "bottom_plate", "top_plate", etc.
    layer_index: int         # Layer index (0 for first layer, 1 for second)
    reference_elevation: float  # Reference elevation
    boundary_elevation: float   # Connection boundary elevation
```

Example plate data:
```python
bottom_plate = PlateData(
    element_type="plate",
    plate_type="bottom_plate",
    thickness=1.5/12,        # 1.5 inches in feet
    width=3.5/12,            # 3.5 inches in feet
    length=10.0,             # 10 feet long
    layer_index=0,
    centerline=centerline_curve,
    profile=profile_rect,
    reference_elevation=0.0,
    boundary_elevation=1.5/12,  # Top of plate
    geometry=plate_brep
)
```

### StudData Structure

```python
@dataclass
class StudData(FramingElementData):
    """Data for stud elements."""
    stud_type: str           # "standard", "king", "trimmer", "cripple", etc.
    u_position: float        # U-coordinate position along wall
    v_start: float           # Bottom V-coordinate
    v_end: float             # Top V-coordinate
```

Example stud data:
```python
king_stud = StudData(
    element_type="stud",
    stud_type="king",
    thickness=1.5/12,        # 1.5 inches in feet
    width=3.5/12,            # 3.5 inches in feet
    length=8.0,              # 8 feet tall
    u_position=3.0,          # 3 feet from wall start
    v_start=0.0,             # Bottom of wall
    v_end=8.0,               # Top of wall
    centerline=centerline_curve,
    profile=profile_rect,
    geometry=stud_brep
)
```

### HeaderData Structure

```python
@dataclass
class HeaderData(FramingElementData):
    """Data for header elements."""
    u_start: float           # Start U-coordinate
    u_end: float             # End U-coordinate
    v_position: float        # V-coordinate height position
    header_height: float     # Vertical height of header
```

Example header data:
```python
header = HeaderData(
    element_type="header",
    thickness=1.5/12,        # 1.5 inches in feet
    width=5.5/12,            # 5.5 inches in feet
    length=3.0,              # 3 feet long
    u_start=3.0,             # 3 feet from wall start
    u_end=6.0,               # 6 feet from wall start
    v_position=7.0,          # 7 feet from wall base
    header_height=7.0/12,    # 7 inches height
    centerline=centerline_curve,
    profile=profile_rect,
    geometry=header_brep
)
```

### SillData Structure

```python
@dataclass
class SillData(FramingElementData):
    """Data for sill elements."""
    u_start: float           # Start U-coordinate
    u_end: float             # End U-coordinate
    v_position: float        # V-coordinate height position
    sill_height: float       # Vertical height of sill
```

Example sill data:
```python
sill = SillData(
    element_type="sill",
    thickness=1.5/12,        # 1.5 inches in feet
    width=5.5/12,            # 5.5 inches in feet
    length=3.0,              # 3 feet long
    u_start=3.0,             # 3 feet from wall start
    u_end=6.0,               # 6 feet from wall start
    v_position=3.0,          # 3 feet from wall base
    sill_height=1.5/12,      # 1.5 inches height
    centerline=centerline_curve,
    profile=profile_rect,
    geometry=sill_brep
)
```

## Location Data Structure

Structure for managing element positioning:

```python
@dataclass
class LocationData:
    """Manages location information for framing elements."""
    reference_line: Curve3D          # Reference line from wall geometry
    base_plane: Plane3D              # Wall's base plane for orientation
    reference_elevation: float       # Elevation for positioning
    wall_type: str                   # Original wall type for reference
    representation_type: str         # "structural" or "schematic"
```

Example location data:
```python
location_data = {
    "reference_line": wall_curve,     # rg.Curve
    "base_plane": base_plane,         # rg.Plane
    "reference_elevation": 0.0,       # Base elevation
    "wall_type": "2x4 EXT",
    "representation_type": "structural"
}
```

## Framing Configuration Structures

```python
@dataclass
class ProfileDimensions:
    """Stores dimensions for a framing profile."""
    thickness: float     # Thickness in feet
    width: float         # Width in feet
    name: str            # Profile name (e.g., "2x4") 
    description: str     # Human-readable description
```

```python
@dataclass
class WallAssembly:
    """Defines wall assembly configuration."""
    exterior_layer_thickness: float
    core_layer_thickness: float
    interior_layer_thickness: float
    
    @property
    def total_wall_thickness(self) -> float:
        """Calculate total wall thickness."""
        return (
            self.exterior_layer_thickness
            + self.core_layer_thickness
            + self.interior_layer_thickness
        )
```

## API Data Structures

### WallAnalysisJob

```python
class WallAnalysisJob(BaseModel):
    """Model for wall analysis job data."""
    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    wall_data: WallDataInput
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
```

## Serialization Format

For API communication and storage, data structures are serialized to JSON:

```python
def serialize_point3d(point: Point3D) -> Dict[str, float]:
    """Serialize a Point3d to a dictionary."""
    return {
        "x": point.X,
        "y": point.Y,
        "z": point.Z
    }

def serialize_plane(plane: Plane3D) -> Dict[str, Any]:
    """Serialize a Plane to a dictionary."""
    return {
        "origin": serialize_point3d(plane.Origin),
        "x_axis": serialize_point3d(plane.XAxis),
        "y_axis": serialize_point3d(plane.YAxis),
        "z_axis": serialize_point3d(plane.ZAxis)
    }
```

Example serialized data:
```json
{
  "wall_data": {
    "wall_type": "2x4 EXT",
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_length": 10.0,
    "wall_height": 8.0,
    "is_exterior_wall": true,
    "openings": [
      {
        "opening_type": "window",
        "start_u_coordinate": 3.0,
        "rough_width": 3.0,
        "rough_height": 4.0,
        "base_elevation_relative_to_wall_base": 3.0
      }
    ]
  },
  "base_plane": {
    "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
    "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
    "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
    "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0}
  },
  "cells": [
    {
      "cell_type": "WBC",
      "u_start": 0.0,
      "u_end": 10.0,
      "v_start": 0.0,
      "v_end": 8.0,
      "corner_points": [
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"x": 10.0, "y": 0.0, "z": 0.0},
        {"x": 10.0, "y": 0.0, "z": 8.0},
        {"x": 0.0, "y": 0.0, "z": 8.0}
      ]
    }
  ]
}
```

## Data Validation

### Validation Rules

Each data structure has specific validation requirements:

1. **Wall Data**:
   - Wall length must be positive
   - Wall height must be positive and match (top_elevation - base_elevation)
   - Wall must have a valid base curve and base plane

2. **Opening Data**:
   - Opening must fit within wall dimensions
   - Window openings must not start at wall base (door openings should)
   - Openings must not overlap with each other

3. **Cell Data**:
   - Cell must have non-zero width (u_end > u_start)
   - Cell must have non-zero height (v_end > v_start)
   - Cell coordinates must be within wall boundaries
   - Corner points must form a valid rectangular boundary

4. **Framing Element Data**:
   - Element dimensions must be positive
   - Element must have valid centerline and profile
   - Geometry must be a valid solid

### Validation Implementation

Validation can be implemented at multiple levels:

```python
# Parameter validation
def validate_wall_data(wall_data: WallData) -> bool:
    """Validate wall data structure."""
    # Check required fields
    if not all(key in wall_data for key in [
        "wall_type", "wall_base_curve", "wall_length", "base_plane",
        "wall_base_elevation", "wall_top_elevation", "wall_height"
    ]):
        raise ValidationError("Missing required wall data fields")
        
    # Check value constraints
    if wall_data["wall_length"] <= 0:
        raise ValidationError("Wall length must be positive")
        
    if wall_data["wall_height"] <= 0:
        raise ValidationError("Wall height must be positive")
        
    # Check geometric validity
    if not wall_data["wall_base_curve"].IsValid:
        raise ValidationError("Wall base curve is not valid")
        
    # Validate openings
    for opening in wall_data.get("openings", []):
        validate_opening_data(opening, wall_data)
        
    return True
```

## Data Flow Diagrams

### Wall Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Revit Wall     │────▶│  Wall Data Dict │────▶│  Cell Dict      │
│  Element        │     │                 │     │                 │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Plate Data     │◀────│  Location Data  │◀────│  Framing        │
│                 │     │                 │     │  Parameters     │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │
         │
         ▼
┌─────────────────┐
│                 │
│  Geometry       │
│  (Brep)         │
│                 │
└─────────────────┘
```

## Best Practices

### Working with Data Structures

1. **Type Checking**:
   - Always use type hints for parameters and return values
   - Validate input data before processing
   - Check for None values and provide reasonable defaults

2. **Dictionary Access**:
   - Use .get() with default values when accessing dictionaries
   - Check for key existence before accessing nested structures
   - Use meaningful exception messages when key lookup fails

3. **Immutability**:
   - Treat input data structures as immutable when possible
   - Create new data structures instead of modifying existing ones
   - Document when functions modify input data

4. **Serialization**:
   - Handle None values gracefully during serialization
   - Use explicit type conversion for numeric values
   - Implement proper error handling for serialization failures

## Appendix: Type Conversion Reference

### Revit to Rhino Type Conversion

```python
# Convert Revit XYZ to Rhino Point3d
def revit_xyz_to_rhino_point3d(xyz: DB.XYZ) -> rg.Point3d:
    """Convert Revit XYZ to Rhino Point3d."""
    return rg.Point3d(xyz.X, xyz.Y, xyz.Z)

# Convert Revit Curve to Rhino Curve
def revit_curve_to_rhino_curve(curve: DB.Curve) -> rg.Curve:
    """Convert Revit Curve to Rhino Curve."""
    # Implementation depends on curve type
    if isinstance(curve, DB.Line):
        start = revit_xyz_to_rhino_point3d(curve.GetEndPoint(0))
        end = revit_xyz_to_rhino_point3d(curve.GetEndPoint(1))
        return rg.LineCurve(start, end)
    # Handle other curve types...
```

### Rhino to Revit Type Conversion

```python
# Convert Rhino Point3d to Revit XYZ
def rhino_point3d_to_revit_xyz(point: rg.Point3d) -> DB.XYZ:
    """Convert Rhino Point3d to Revit XYZ."""
    return DB.XYZ(point.X, point.Y, point.Z)

# Convert Rhino Curve to Revit Curve
def rhino_curve_to_revit_curve(curve: rg.Curve) -> DB.Curve:
    """Convert Rhino Curve to Revit Curve."""
    # Implementation depends on curve type
    if isinstance(curve, rg.LineCurve):
        start = rhino_point3d_to_revit_xyz(curve.PointAtStart)
        end = rhino_point3d_to_revit_xyz(curve.PointAtEnd)
        return DB.Line.CreateBound(start, end)
    # Handle other curve types...
```

These data structures form the foundation of the Timber Framing Generator, enabling consistent data representation and processing across the system.
