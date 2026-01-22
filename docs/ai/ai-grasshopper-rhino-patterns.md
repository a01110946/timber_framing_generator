# Grasshopper, Rhino.Inside.Revit & Python Best Patterns

## Overview

This document captures proven patterns for working with Grasshopper, Rhino.Inside.Revit, and CPython in this project. These patterns address real issues encountered during development.

---

## Python Environment: CPython vs IronPython

### Environment Detection

```python
# Detect if running in Grasshopper (CPython via GH_CPython component)
import sys

is_grasshopper = 'Grasshopper' in sys.modules or 'ghpythonlib' in sys.modules
is_rhino_environment = 'rhinoscriptsyntax' in sys.modules or 'scriptcontext' in sys.modules

# In GH_CPython, we use CPython with access to both worlds:
# - Standard Python packages (rhino3dm, numpy, etc.)
# - .NET assemblies via pythonnet (clr module)
```

### Import Patterns

```python
# Standard imports for GH_CPython component
import sys
import clr

# Add .NET references
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

# Import Grasshopper types
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path
from Grasshopper.Kernel.Types import GH_Brep, GH_Point, GH_Curve

# Import Rhino geometry
import Rhino.Geometry as rg
```

---

## The Assembly Mismatch Problem (Critical)

### The Issue

When using `rhino3dm` Python package:
- Creates geometry from **Rhino3dmIO** assembly
- Grasshopper expects **RhinoCommon** assembly
- Type names are IDENTICAL but CLR treats them as different types
- Results in: `"Data conversion failed from Goo to Brep"`

### The Solution: RhinoCommonFactory

Use CLR reflection to create geometry from the correct assembly:

```python
import clr
from System import Activator, Array, Type
from System.Reflection import BindingFlags

class RhinoCommonFactory:
    """Factory for creating RhinoCommon geometry via CLR reflection."""

    def __init__(self):
        self.rc_assembly = None
        self._type_cache = {}
        self._find_rhinocommon_assembly()

    def _find_rhinocommon_assembly(self):
        """Find RhinoCommon assembly from loaded assemblies."""
        from System import AppDomain
        for assembly in AppDomain.CurrentDomain.GetAssemblies():
            name = assembly.GetName().Name
            if name == "RhinoCommon":
                self.rc_assembly = assembly
                print("RhinoCommonFactory: Found RhinoCommon assembly")
                return

    def _get_type(self, type_name):
        """Get a RhinoCommon type by name, with caching."""
        if type_name not in self._type_cache:
            full_name = f"Rhino.Geometry.{type_name}"
            self._type_cache[type_name] = self.rc_assembly.GetType(full_name)
        return self._type_cache[type_name]

    def create_point3d(self, x, y, z):
        """Create a RhinoCommon Point3d."""
        RC_Point3d = self._get_type("Point3d")
        args = Array[object]([float(x), float(y), float(z)])
        return Activator.CreateInstance(RC_Point3d, args)

    def create_vector3d(self, x, y, z):
        """Create a RhinoCommon Vector3d."""
        RC_Vector3d = self._get_type("Vector3d")
        args = Array[object]([float(x), float(y), float(z)])
        return Activator.CreateInstance(RC_Vector3d, args)
```

### Key Principle: Launder Through Floats

Always extract raw coordinates as Python floats, then recreate:

```python
# WRONG: Direct conversion (preserves wrong assembly)
rc_point = some_point  # Still Rhino3dmIO!

# RIGHT: Extract floats, recreate from RhinoCommon
x, y, z = float(some_point.X), float(some_point.Y), float(some_point.Z)
rc_point = rc_factory.create_point3d(x, y, z)
```

---

## Invoking Static Methods via Reflection

Some RhinoCommon operations require static method calls. Use MethodInfo.Invoke:

```python
def create_surface_from_corners(self, p1, p2, p3, p4):
    """Create NurbsSurface from 4 corner points."""
    # Convert points to RhinoCommon Point3d
    corners = []
    for pt in [p1, p2, p3, p4]:
        if isinstance(pt, (tuple, list)):
            corners.append(self.create_point3d(*pt))
        elif hasattr(pt, 'X'):
            corners.append(self.create_point3d(
                float(pt.X), float(pt.Y), float(pt.Z)
            ))

    # Get static method via reflection
    RC_NurbsSurface = self._get_type("NurbsSurface")
    RC_Point3d = self._get_type("Point3d")

    method_info = RC_NurbsSurface.GetMethod(
        "CreateFromCorners",
        BindingFlags.Public | BindingFlags.Static,
        None,
        Array[Type]([RC_Point3d, RC_Point3d, RC_Point3d, RC_Point3d]),
        None
    )

    if method_info is not None:
        result = method_info.Invoke(None, Array[object](corners))
        return result
    return None
```

---

## DataTree Usage for Grasshopper Outputs

### When to Use DataTrees

Use DataTree when:
- One input produces multiple outputs (e.g., one wall → many studs)
- You need grafted/branched data structure
- Outputs should maintain association with inputs

### Basic Pattern

```python
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# Create tree
studs_tree = DataTree[object]()

# For each wall (with index i)
for i, wall in enumerate(walls):
    wall_path = GH_Path(i)

    # Generate studs for this wall
    studs = generate_studs(wall)

    # Add each stud to the tree under this wall's path
    for stud in studs:
        studs_tree.Add(stud, wall_path)

# Assign to output
a = studs_tree  # 'a' is GH component output
```

### Nested Paths

For hierarchical data (wall → cell → element):

```python
# wall_idx=0, cell_idx=2, element_idx varies
path = GH_Path(wall_idx, cell_idx)
tree.Add(element, path)
```

---

## Error Handling in GHPython

### Silent Failures are Common

GHPython swallows many exceptions. Always wrap operations:

```python
def safe_create_geometry(data):
    """Create geometry with explicit error handling."""
    try:
        result = some_operation(data)
        if result is None:
            print("WARNING: some_operation returned None")
            return None
        if hasattr(result, 'IsValid') and not result.IsValid:
            print("WARNING: Result geometry is invalid")
            return None
        return result
    except Exception as e:
        print(f"ERROR in safe_create_geometry: {e}")
        import traceback
        traceback.print_exc()
        return None
```

### Debug Output Pattern

```python
# Use print() - it goes to GH Python output panel
print(f"Processing wall {wall_id}")
print(f"  Generated {len(studs)} studs")
print(f"  First stud type: {type(studs[0]).__name__}")

# Check assembly (critical for debugging)
if hasattr(studs[0], 'GetType'):
    assembly = studs[0].GetType().Assembly.GetName().Name
    print(f"  Assembly: {assembly}")  # Should be "RhinoCommon"
```

---

## Geometry Conversion Pattern

### Convert rhino3dm to RhinoCommon

```python
def convert_breps_for_output(brep_list, rc_factory):
    """Convert all breps to RhinoCommon before GH output."""
    converted = []

    for item in brep_list:
        if item is None:
            continue

        # Check if already RhinoCommon
        if hasattr(item, 'GetType'):
            assembly = item.GetType().Assembly.GetName().Name
            if assembly == "RhinoCommon":
                converted.append(item)
                continue

        # Convert via bounding box recreation
        rc_brep = rc_factory.convert_geometry_from_rhino3dm(item)
        if rc_brep is not None:
            converted.append(rc_brep)

    return converted
```

### Surface → Boundary Curve Extraction

When direct PolylineCurve creation fails (common CLR issue), create surface first:

```python
# Step 1: Create surface from corners (this works reliably)
surface = rc_factory.create_surface_from_corners(p1, p2, p3, p4)

# Step 2: Extract boundary curve from surface
if surface is not None:
    brep = surface.ToBrep()
    if brep is not None:
        edges = brep.Edges
        # Collect edge curves
        edge_curves = [edges[i].DuplicateCurve() for i in range(edges.Count)]
        # Join into single curve if needed
        boundary = Curve.JoinCurves(edge_curves)[0]
```

---

## Common Pitfalls

### 1. Activator.CreateInstance Overload Issues

```python
# WRONG: Can pick wrong constructor overload
result = Activator.CreateInstance(SomeType, my_array)

# RIGHT: Be explicit about argument types
args = Array[object]([arg1, arg2, arg3])
result = Activator.CreateInstance(SomeType, args)

# Or use GetConstructor for exact signature
constructor = SomeType.GetConstructor(Array[Type]([...]))
result = constructor.Invoke(Array[object]([...]))
```

### 2. List vs Array Confusion

```python
# .NET methods expect System.Array, not Python list
from System import Array

# WRONG
points = [p1, p2, p3]
method.Invoke(None, points)

# RIGHT
points = Array[object]([p1, p2, p3])
method.Invoke(None, points)
```

### 3. Type Checking Across Assemblies

```python
# WRONG: isinstance fails across assemblies
if isinstance(geom, rg.Brep):  # May fail!

# RIGHT: Check type name string
if type(geom).__name__ == "Brep":
    pass

# Or check via GetType
if hasattr(geom, 'GetType') and 'Brep' in geom.GetType().FullName:
    pass
```

---

## Diagnostic Test Pattern

Include diagnostic outputs for debugging:

```python
# In main script, add test outputs
def create_diagnostic_outputs(rc_factory):
    """Create test geometry to verify factory works."""
    # Create simple test box
    test_box = rc_factory.create_box_brep_from_centerline(
        start=(0, 0, 0),
        end=(0, 0, 1),
        width=0.125,
        depth=0.292
    )

    # Build info string
    info = []
    if test_box is not None:
        info.append(f"Type: {type(test_box).__name__}")
        if hasattr(test_box, 'GetType'):
            info.append(f"Assembly: {test_box.GetType().Assembly.GetName().Name}")
        if hasattr(test_box, 'IsValid'):
            info.append(f"IsValid: {test_box.IsValid}")
    else:
        info.append("FAILED: test_box is None")

    return test_box, "\n".join(info)

# Assign to GH outputs
test_clr_box, test_info = create_diagnostic_outputs(rc_factory)
```

---

## Performance Tips

1. **Cache type lookups**: Store `_get_type()` results
2. **Batch DataTree additions**: Add multiple items at once if possible
3. **Minimize reflection calls**: Reuse MethodInfo objects
4. **Use lists over DataTrees for simple outputs**: DataTrees have overhead

---

## Quick Reference

| Task | Pattern |
|------|---------|
| Create Point3d | `rc_factory.create_point3d(x, y, z)` |
| Create Vector3d | `rc_factory.create_vector3d(x, y, z)` |
| Create Brep from bbox | `rc_factory.create_box_brep_from_centerline(...)` |
| Create Surface | `rc_factory.create_surface_from_corners(p1, p2, p3, p4)` |
| Grafted output | `DataTree[object]()` with `GH_Path(index)` |
| Check assembly | `obj.GetType().Assembly.GetName().Name` |
| Static method call | `MethodInfo.Invoke(None, args)` |
| Convert rhino3dm→RC | `rc_factory.convert_geometry_from_rhino3dm(geom)` |
