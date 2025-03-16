# Development Guidelines - Timber Framing Generator

## Introduction

This document outlines the development standards and best practices for contributing to the Timber Framing Generator project. Following these guidelines ensures code consistency, maintainability, and compatibility with the project's architecture.

## Python Standards

### Python Version

The project uses Python 3.9+ for compatibility with Rhino.Inside.Revit and required libraries.

```python
# In pyproject.toml
requires-python = ">=3.9"
```

### Dependencies Management

We're transitioning to using `uv` instead of `pip` for dependency management:

```bash
# Install uv if you haven't already
curl -sSf https://install.ultraviolet.dev | sh

# Install project dependencies
uv pip install -e .
```

### Type Annotations

All code must use strict type hints:

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

Use forward references (in quotes) for types not yet defined or circular references.

### Docstrings

Every module, class, method, and function must have comprehensive docstrings following this format:

```python
def create_stud_profile(
    base_point: rg.Point3d, 
    base_plane: rg.Plane, 
    stud_width: float, 
    stud_depth: float
) -> rg.Rectangle3d:
    """
    Creates a rectangular profile for a stud element, centered on its reference point.

    This function creates a profile that:
    1. Is centered on the base_point
    2. Is oriented according to the base_plane
    3. Has dimensions specified by stud_width and stud_depth

    Args:
        base_point: Center point for the profile
        base_plane: Reference plane for orientation
        stud_width: Width of the stud (across the wall thickness)
        stud_depth: Depth of the stud (along the wall direction)

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

### Code Formatting

Use `black` for code formatting with a line length of 88 characters:

```bash
black src/ tests/
```

### Import Order

Follow this import order convention:

```python
# Standard library imports
import os
import sys
from typing import Dict, List, Optional

# Third-party imports
import Rhino.Geometry as rg
from Autodesk.Revit import DB
import rhinoscriptsyntax as rs

# Local application imports
from timber_framing_generator.utils.coordinate_systems import WallCoordinateSystem
from timber_framing_generator.config.framing import FRAMING_PARAMS
```

## Error Handling

### Exception Hierarchy

Use specific exceptions following this hierarchy:

```python
class TimberFramingError(Exception):
    """Base exception for all Timber Framing Generator errors."""
    pass

class GeometryError(TimberFramingError):
    """Raised when a geometric operation fails."""
    pass

class ValidationError(TimberFramingError):
    """Raised when input validation fails."""
    pass

class RevitIntegrationError(TimberFramingError):
    """Raised when Revit integration operations fail."""
    pass
```

### Try-Except Pattern

Use this pattern for error handling:

```python
try:
    # Operation that might fail
    result = some_operation()
    
    # Validate result
    if result is None or not result.IsValid:
        raise GeometryError("Operation returned invalid result")
        
    return result
except Exception as e:
    logger.error(f"Error performing operation: {str(e)}")
    # Optionally include traceback for dev environments
    if os.environ.get("DEBUG"):
        import traceback
        logger.debug(traceback.format_exc())
    raise TimberFramingError(f"Operation failed: {str(e)}") from e
```

## Logging

Use Python's built-in logging module with this configuration:

```python
import logging

# Configure module-level logger
logger = logging.getLogger(__name__)

def process_wall(wall):
    """Process wall function."""
    logger.info(f"Processing wall ID: {wall.Id}")
    
    try:
        # Processing logic
        logger.debug(f"Wall parameters: {wall.parameters}")
        
        # Success
        logger.info(f"Wall {wall.Id} processed successfully")
    except Exception as e:
        logger.error(f"Failed to process wall {wall.Id}: {str(e)}")
        raise
```

## Model Context Protocol (MCP)

### Implementation Pattern

For classes supporting the Model Context Protocol:

```python
class FramingElement:
    """Represents a framing element with MCP support."""
    
    def __enter__(self):
        """Enter the model context."""
        self.original_state = self._capture_state()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the model context."""
        if exc_type is not None:
            # Restore original state on exception
            self._restore_state(self.original_state)
            return False  # Propagate exception
        return True
        
    def _capture_state(self):
        """Capture current state."""
        pass
        
    def _restore_state(self, state):
        """Restore to previous state."""
        pass
```

### MCP Usage Example

```python
def process_wall_with_mcp(wall):
    """Process wall using MCP."""
    with FramingElement() as element:
        # Operations that modify the element
        element.add_property(key, value)
        element.generate_geometry()
        
        # If an exception occurs inside this block,
        # the element will be restored to its original state
```

## Testing Standards

### Unit Test Requirements

All code should have unit tests:

```python
import unittest

class TestStudGeneration(unittest.TestCase):
    """Test case for stud generation."""
    
    def setUp(self):
        """Set up test resources."""
        self.wall_data = create_test_wall_data()
        self.generator = StudGenerator(self.wall_data)
        
    def test_stud_creation(self):
        """Test creating a stud."""
        stud = self.generator.create_stud(0.5, 0.0, 8.0)
        self.assertIsNotNone(stud)
        self.assertTrue(stud.IsValid)
        
    def test_stud_dimensions(self):
        """Test stud has correct dimensions."""
        stud = self.generator.create_stud(0.5, 0.0, 8.0)
        bbox = stud.GetBoundingBox(True)
        self.assertAlmostEqual(bbox.Max.Z - bbox.Min.Z, 8.0)
```

### Mock Objects

Use mock objects for testing code that depends on Rhino or Revit:

```python
class MockPoint3d:
    """Mock for rg.Point3d."""
    
    def __init__(self, x=0, y=0, z=0):
        self.X = x
        self.Y = y
        self.Z = z
        
    def DistanceTo(self, other):
        """Calculate distance to another point."""
        dx = self.X - other.X
        dy = self.Y - other.Y
        dz = self.Z - other.Z
        return (dx*dx + dy*dy + dz*dz) ** 0.5
```

## Code Organization

### Module Structure

Follow this module structure pattern:

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

Structure classes with this pattern:

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
        
    def _preprocess_data(self):
        """Preprocessing step (private method)."""
        pass
        
    def _generate_elements(self):
        """Element generation (private method)."""
        pass
```

## Code Review Checklist

When submitting code for review, ensure:

1. All functions have docstrings and type hints
2. Unit tests cover the new functionality
3. Code passes linting (black, flake8)
4. Error handling follows project standards
5. Logging is implemented appropriately
6. No hardcoded values (use constants or config)
7. Comments explain "why", not just "what"
8. Changes are compatible with API stability requirements

## Documentation Updates

When making code changes:

1. Update affected docstrings
2. Add code examples for new functionality
3. Document any changes to API behavior
4. Update architecture documentation if design changes

## Commit Message Standards

Use this format for commit messages:

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

By following these guidelines, you'll help maintain code quality and consistency across the Timber Framing Generator project.
