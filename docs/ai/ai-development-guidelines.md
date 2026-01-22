# Timber Framing Generator Development Guide

## Introduction

This guide documents development standards, practices, and the technical stack for the Timber Framing Generator project. It serves as the definitive reference for contributors to maintain consistency and quality across the codebase.

## Python Standards

### Python Version
- Python 3.9+ for compatibility with Rhino.Inside.Revit
- Use `uv` for dependency management: 
  ```bash
  uv pip install -e .
  ```

### Type Annotations
```python
from typing import Dict, List, Optional, Tuple, Union, Any

def process_wall_geometry(
    wall_element: "Revit.DB.Wall",
    base_plane: rg.Plane,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Union[rg.Curve, List[rg.Point3d], float]]:
    """Function documentation."""
    # Implementation
```

### Docstrings
```python
def create_stud_profile(
    base_point: rg.Point3d, 
    base_plane: rg.Plane, 
    stud_width: float, 
    stud_depth: float
) -> rg.Rectangle3d:
    """
    Creates a rectangular profile for a stud element, centered on its reference point.

    Args:
        base_point: Center point for the profile
        base_plane: Reference plane for orientation
        stud_width: Width of the stud (across wall thickness)
        stud_depth: Depth of the stud (along wall direction)

    Returns:
        A Rectangle3d representing the stud profile
        
    Example:
        profile = create_stud_profile(
            rg.Point3d(0, 0, 0),
            rg.Plane.WorldXY,
            1.5/12,  # 1.5 inches in feet
            3.5/12   # 3.5 inches in feet
        )
    """
```

## Technical Stack

### Core Backend Framework
- **FastAPI**: High-performance web framework with automatic OpenAPI docs
- **Pydantic**: Data validation and settings management
- **Uvicorn**: ASGI server for API endpoints

### CAD/BIM Integration
- **Rhino 3D**: Foundation for 3D modeling and geometric operations
- **Grasshopper**: Visual scripting platform for parametric modeling
- **Revit**: Building Information Modeling source and target
- **Rhino.Inside.Revit**: Technology bridge connecting Rhino and Revit

### Development Tools
- **uv**: Modern Python package manager replacing pip
- **Ruff**: Code formatter and linter
- **Git**: Version control with specific commit message standards
- **Type hints**: Enhanced IDE support and runtime validation

### Supporting Libraries
- **rhinoinside**: Python library for Rhino integration
- **rhino3dm**: Pure Python library for 3D geometry
- **Rhino Geometry (rg)**: Core geometry library
- **Revit.DB**: Revit API for BIM operations

### Testing Framework
- **pytest**: Primary testing framework
- **httpx**: Modern HTTP client for API testing

## Code Organization

### Module Structure
```
src/timber_framing_generator/
├── __init__.py
├── module_name/
│   ├── __init__.py
│   ├── core.py           # Core functionality
│   ├── helpers.py        # Helper functions 
│   └── exceptions.py     # Module-specific exceptions
```

### Class Organization
```python
class FramingGenerator:
    """Framing generator class docstring."""
    
    def __init__(self, wall_data):
        """Initialize with required data."""
        self.wall_data = wall_data
        self._initialize_state()
        
    def _initialize_state(self):
        """Initialize internal state (private method)."""
        self.framing_elements = []
        
    def generate_framing(self):
        """Main public API method."""
        self._preprocess_data()
        self._generate_elements()
        return self.framing_elements
```

## Error Handling

```python
def extract_wall_data(
    wall: "Revit.DB.Wall",
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Function docstring as specified above."""
    try:
        logger.info(f"Processing wall ID: {wall.Id}")
        
        # Validate input
        if not wall:
            raise ValueError("Wall element cannot be None")
            
        # Process wall
        result = process_wall_geometry(wall)
        
        # Validate output
        if not result.get('base_curve'):
            raise ValueError("Failed to extract wall base curve")
            
        return result
        
    except Exception as e:
        logger.error(f"Error processing wall: {str(e)}")
        raise RuntimeError(f"Wall processing failed: {str(e)}") from e
```

## Best Practices

1. **Always use proper type annotations** for all functions and classes
2. **Document code with comprehensive docstrings** following the guidelines
3. **Implement proper error handling** with appropriate exception classes
4. **Use the UVW coordinate system** for wall-relative positioning
5. **Maintain a clear separation** between data extraction and geometry generation
6. **Follow established naming conventions** for consistency
7. **Write tests for all critical functionality**
8. **Use environment variables for configuration**, not hardcoded values

## Commit Message Standards

```
component: Brief description of change

Detailed explanation of what changed and why.
Include any background context necessary to understand the change.

References #issue_number
```

Example:
```
framing_elements: Add support for double top plates

Extends the plate_generator module to support configurable
double top plates with proper vertical offsets.
Includes updated tests and documentation.

References #42
```

## Pull Request Process

1. Create a feature branch (`feature/your-feature-name`)
2. Make changes with appropriate tests
3. Update documentation
4. Submit PR with detailed description
5. Address review comments
6. Merge once approved and CI passes