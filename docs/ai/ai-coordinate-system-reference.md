# Coordinate System Reference - Timber Framing Generator

## Introduction

The Timber Framing Generator uses a specialized coordinate system approach to handle the transformation between different reference frames. This document provides a comprehensive explanation of the coordinate systems used, transformations between them, and best practices for working with geometric operations in the project.

## Core Coordinate Systems

The project works with three primary coordinate systems:

1. **World Coordinates** - The absolute Revit/Rhino coordinate system
2. **Wall-Local Coordinates (UVW)** - Coordinates relative to the wall's orientation and dimensions
3. **Element-Local Coordinates** - Coordinates relative to individual framing elements

Understanding the relationships between these systems is crucial for correctly positioning and orienting framing elements.

## UVW Coordinate System

### Concept

The UVW coordinate system is a wall-relative coordinate system where:

- **U-Axis**: Runs horizontally along the wall length (follows wall_base_curve)
- **V-Axis**: Runs vertically upward (perpendicular to base plane)
- **W-Axis**: Passes through the wall thickness (normal to wall face)

This creates a right-handed coordinate system where:

- U=0 is at the start of the wall's base curve
- V=0 is at the wall's base elevation
- W=0 is typically at the wall's centerline (through thickness)

### Visual Representation

```
                  V
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  │
                  └─────────────────────────► U
                 /
                /
               /
              /
             /
            /
           /
          /
         W
```

### Mathematical Definition

The UVW system is defined by the wall's base plane, where:

- U-Axis corresponds to the base_plane.XAxis
- V-Axis corresponds to the base_plane.YAxis
- W-Axis corresponds to the base_plane.ZAxis

```python
def define_wall_uvw_system(wall_data):
    """Define the UVW coordinate system for a wall."""
    # Extract base curve and wall data
    base_curve = wall_data["wall_base_curve"]
    base_elevation = wall_data["wall_base_elevation"]
    
    # Create origin point at start of wall base curve
    start_point = base_curve.PointAtStart
    origin = rg.Point3d(start_point.X, start_point.Y, base_elevation)
    
    # Create X-Axis (U-direction) along wall length
    start = base_curve.PointAtStart
    end = base_curve.PointAtEnd
    x_axis = rg.Vector3d(end - start)
    x_axis.Unitize()
    
    # Y-Axis (V-direction) is vertical
    y_axis = rg.Vector3d(0, 0, 1)
    
    # Z-Axis (W-direction) is perpendicular to wall face
    z_axis = rg.Vector3d.CrossProduct(x_axis, y_axis)
    z_axis.Unitize()
    
    # Force Y-Axis to be perpendicular to both X and Z
    y_axis = rg.Vector3d.CrossProduct(z_axis, x_axis)
    y_axis.Unitize()
    
    # Create and return the wall's base plane
    base_plane = rg.Plane(origin, x_axis, y_axis)
    return base_plane
```

## UVW to World Transformation

### Core Concept

Transforming from UVW to world coordinates involves:

1. Starting with UVW coordinates (u, v, w)
2. Using the wall's base plane to map these to 3D space
3. Returning a point in world coordinates

### Implementation

```python
def uvw_to_world(u, v, w, base_plane):
    """
    Convert UVW coordinates to world coordinates.
    
    Args:
        u: Position along wall length
        v: Height from wall base
        w: Depth through wall thickness
        base_plane: Wall's base plane defining the coordinate system
        
    Returns:
        Point3d in world coordinates
    """
    # Use the base plane's PointAt method for direct transformation
    return base_plane.PointAt(u, v, w)
```

### Alternative Vector-Based Approach

For clarity and explicit control, you can also use vector operations:

```python
def uvw_to_world_vector(u, v, w, base_plane):
    """Convert UVW coordinates to world using vector operations."""
    # Start at the origin
    point = rg.Point3d(base_plane.Origin)
    
    # Add displacement along each axis
    point += base_plane.XAxis * u  # U displacement
    point += base_plane.YAxis * v  # V displacement
    point += base_plane.ZAxis * w  # W displacement
    
    return point
```

## World to UVW Transformation

### Core Concept

Transforming from world coordinates to UVW involves:

1. Starting with a world point
2. Creating a vector from the wall's origin to this point
3. Projecting this vector onto the UVW axes to get coordinates

### Implementation

```python
def world_to_uvw(point, base_plane):
    """
    Convert world coordinates to UVW coordinates.
    
    Args:
        point: Point3d in world coordinates
        base_plane: Wall's base plane defining the coordinate system
        
    Returns:
        Tuple of (u, v, w) coordinates
    """
    # Vector from origin to point
    vector = point - base_plane.Origin
    
    # Project onto each axis
    u = vector * base_plane.XAxis  # Dot product gives U coordinate
    v = vector * base_plane.YAxis  # Dot product gives V coordinate
    w = vector * base_plane.ZAxis  # Dot product gives W coordinate
    
    return (u, v, w)
```

### Matrix-Based Transformation

For higher performance with many points, use transformation matrices:

```python
def create_transformation_matrices(base_plane):
    """Create transformation matrices for a wall coordinate system."""
    # World to UVW transformation
    to_uvw = rg.Transform.PlaneToPlane(
        base_plane,  # Source plane (world coordinates)
        rg.Plane.WorldXY  # Target plane (UVW coordinates)
    )
    
    # UVW to World transformation
    to_world = rg.Transform.PlaneToPlane(
        rg.Plane.WorldXY,  # Source plane (UVW coordinates)
        base_plane  # Target plane (world coordinates)
    )
    
    return to_uvw, to_world

def transform_point_to_uvw(point, to_uvw_transform):
    """Transform a point from world to UVW using a matrix."""
    # Make a copy to avoid modifying the original
    transformed = rg.Point3d(point)
    # Apply the transformation
    transformed.Transform(to_uvw_transform)
    return (transformed.X, transformed.Y, transformed.Z)
```

## Creating Element Geometries in UVW Space

### Working with Centerlines

Creating element centerlines in UVW space:

```python
def create_horizontal_element_centerline(u_start, u_end, v_position, base_plane):
    """Create a centerline for a horizontal element (e.g., plate, header)."""
    # Create start and end points
    start_point = base_plane.PointAt(u_start, v_position, 0)
    end_point = base_plane.PointAt(u_end, v_position, 0)
    
    # Create the centerline
    return rg.LineCurve(start_point, end_point)

def create_vertical_element_centerline(u_position, v_start, v_end, base_plane):
    """Create a centerline for a vertical element (e.g., stud)."""
    # Create start and end points
    start_point = base_plane.PointAt(u_position, v_start, 0)
    end_point = base_plane.PointAt(u_position, v_end, 0)
    
    # Create the centerline
    return rg.LineCurve(start_point, end_point)
```

### Creating Profile Planes

Profiles need to be perpendicular to the centerline and correctly oriented:

```python
def create_stud_profile_plane(centerline, base_plane):
    """Create a profile plane for a stud (perpendicular to centerline)."""
    # Get the start point of the centerline
    origin = centerline.PointAtStart
    
    # For a vertical stud:
    # - X axis should be the wall thickness direction (W)
    # - Y axis should be along the wall length (U)
    x_axis = base_plane.ZAxis
    y_axis = base_plane.XAxis
    
    return rg.Plane(origin, x_axis, y_axis)

def create_plate_profile_plane(centerline, base_plane):
    """Create a profile plane for a plate (perpendicular to centerline)."""
    # Get the start point of the centerline
    origin = centerline.PointAtStart
    
    # For a horizontal plate:
    # - X axis should be the wall thickness direction (W)
    # - Y axis should be vertical (V)
    x_axis = base_plane.ZAxis
    y_axis = base_plane.YAxis
    
    return rg.Plane(origin, x_axis, y_axis)
```

## WallCoordinateSystem Class

The project uses a `WallCoordinateSystem` class to manage transformations:

```python
class WallCoordinateSystem:
    """
    Manages transformations between wall-local coordinates and world coordinates.
    
    The wall coordinate system uses these axes:
    - U-axis: Along the wall length (wall_base_curve direction)
    - V-axis: Vertical direction (perpendicular to base plane)
    - W-axis: Through wall thickness (normal to wall face)
    """
    
    def __init__(self, wall_data):
        """Initialize with wall data."""
        self.base_plane = wall_data["base_plane"]
        self.wall_curve = wall_data["wall_base_curve"]
        self.base_elevation = wall_data["wall_base_elevation"]
        self.top_elevation = wall_data["wall_top_elevation"]
        
        # Create transformations
        self._to_world_transform = self._compute_to_world_transform()
        self._to_wall_transform = self._compute_to_wall_transform()
    
    def wall_to_world(self, u, v, w=0.0):
        """Convert wall coordinates (u,v,w) to world coordinates."""
        wall_point = rg.Point3d(u, v, w)
        world_point = rg.Point3d(wall_point)
        
        if world_point.Transform(self._to_world_transform):
            return world_point
        
        # Fallback direct method if transform fails
        return self.point_at(u, v, w)
    
    def world_to_wall(self, point):
        """Convert world coordinates to wall coordinates (u,v,w)."""
        wall_point = rg.Point3d(point)
        
        if wall_point.Transform(self._to_wall_transform):
            return (wall_point.X, wall_point.Y, wall_point.Z)
        
        return None
    
    def point_at(self, u, v, w=0.0):
        """Get a point in world coordinates using direct base plane evaluation."""
        return self.base_plane.PointAt(u, v, w)
```

## Coordinate System for Framing Elements

### Framing Element Local Coordinates

Each framing element has its own local coordinate system:

```python
def create_element_coordinate_system(centerline, profile_plane, element_type):
    """Create a coordinate system for a framing element."""
    # Origin at the element's center
    origin = centerline.PointAt(centerline.GetLength() / 2)
    
    if element_type == "stud":
        # For studs, X is along length, Y is across width, Z is through depth
        x_axis = rg.Vector3d(centerline.PointAtEnd - centerline.PointAtStart)
        y_axis = profile_plane.XAxis
        z_axis = profile_plane.YAxis
    else:  # Plates, headers, etc.
        # For horizontal elements, X is along length, Y is through depth, Z is across height
        x_axis = rg.Vector3d(centerline.PointAtEnd - centerline.PointAtStart)
        y_axis = profile_plane.XAxis
        z_axis = profile_plane.YAxis
    
    # Ensure unit vectors
    x_axis.Unitize()
    y_axis.Unitize()
    z_axis.Unitize()
    
    return rg.Plane(origin, x_axis, y_axis)
```

## Common Geometric Operations in UVW Space

### Creating Rectangular Profiles

```python
def create_centered_rectangle(plane, width, height):
    """Create a rectangle centered on a plane."""
    return rg.Rectangle3d(
        plane,
        rg.Interval(-width/2, width/2),
        rg.Interval(-height/2, height/2)
    )

def create_stud_profile(origin, base_plane, stud_width, stud_depth):
    """Create a profile rectangle for a stud element."""
    # Create profile plane
    profile_plane = rg.Plane(
        origin,
        base_plane.ZAxis,  # Width direction (through wall)
        base_plane.XAxis   # Depth direction (along wall)
    )
    
    # Create centered rectangle
    return rg.Rectangle3d(
        profile_plane,
        rg.Interval(-stud_depth/2, stud_depth/2),
        rg.Interval(-stud_width/2, stud_width/2)
    )
```

### Generating Framing Element Geometry

```python
def create_extrusion(profile, path_vector):
    """Create an extrusion from a profile along a vector."""
    # Convert profile to a curve
    profile_curve = profile.ToNurbsCurve()
    
    # Create extrusion
    extrusion = rg.Extrusion.CreateExtrusion(profile_curve, path_vector)
    
    # Convert to Brep and cap the ends
    if extrusion and extrusion.IsValid:
        return extrusion.ToBrep(True)
    
    return None

def create_framing_element(centerline, profile):
    """Create a framing element from centerline and profile."""
    # Get vector for extrusion
    start = centerline.PointAtStart
    end = centerline.PointAtEnd
    path_vector = rg.Vector3d(end - start)
    
    # Create the extrusion
    return create_extrusion(profile, path_vector)
```

## Cell Coordinate System

The cell decomposition system provides a simplified 2D coordinate system:

```python
def calculate_corner_points(u_start, u_end, v_start, v_end, base_plane):
    """
    Calculate corner points for a cell in world coordinates.
    
    Points are in order:
    [0] = bottom-left
    [1] = bottom-right
    [2] = top-right
    [3] = top-left
    """
    return [
        base_plane.PointAt(u_start, v_start),  # bottom-left
        base_plane.PointAt(u_end, v_start),    # bottom-right
        base_plane.PointAt(u_end, v_end),      # top-right
        base_plane.PointAt(u_start, v_end)     # top-left
    ]
```

## Common Visualization Operations

```python
def create_cell_visualization(cells, base_plane):
    """Create visualization geometry for cells."""
    rectangles = []
    colors = []
    
    for cell in cells:
        # Only visualize non-WBC cells
        if cell["cell_type"] != "WBC":
            u_start = cell["u_start"]
            u_end = cell["u_end"]
            v_start = cell["v_start"]
            v_end = cell["v_end"]
            
            # Create rectangle in world coordinates
            rect = rg.Rectangle3d(
                base_plane,
                rg.Interval(u_start, u_end),
                rg.Interval(v_start, v_end)
            )
            
            rectangles.append(rect)
            
            # Set color based on cell type
            if cell["cell_type"] == "OC":
                colors.append(System.Drawing.Color.Red)
            elif cell["cell_type"] == "SC":
                colors.append(System.Drawing.Color.Blue)
            elif cell["cell_type"] == "SCC":
                colors.append(System.Drawing.Color.Green)
            elif cell["cell_type"] == "HCC":
                colors.append(System.Drawing.Color.Yellow)
            else:
                colors.append(System.Drawing.Color.Gray)
    
    return rectangles, colors
```

## Best Practices

### General Guidelines

1. **Maintain Consistent Coordinate Systems**
   - Always use the same coordinate system conventions
   - Document any deviations from standard UVW orientation
   - Use helper methods to centralize transformation logic

2. **Ensure Proper Vector Direction**
   - Always check vector directions, especially when computing cross products
   - Ensure cross products maintain proper right-hand rule orientation
   - Use `.Unitize()` for direction vectors to prevent scaling issues

3. **Handle Numerical Precision**
   - Be aware of floating-point precision issues
   - Use tolerances for point equality and other geometric operations
   - Consider using `PointAtParameter` instead of explicit coordinates for curves

4. **Debug Visualization**
   - Create debug visualization for coordinate systems
   - Include axis indicators for troubleshooting
   - Visualize intermediate geometric constructions

### Example Debug Visualization

```python
def visualize_coordinate_system(base_plane, scale=1.0):
    """Create debug visualization for a coordinate system."""
    origin = base_plane.Origin
    
    # Create axis lines
    u_axis = rg.LineCurve(origin, origin + base_plane.XAxis * scale)
    v_axis = rg.LineCurve(origin, origin + base_plane.YAxis * scale)
    w_axis = rg.LineCurve(origin, origin + base_plane.ZAxis * scale)
    
    # Return visualization elements
    return {
        "origin": origin,
        "axes": [u_axis, v_axis, w_axis],
        "labels": ["U-Axis", "V-Axis", "W-Axis"]
    }
```

### Performance Optimization

1. **Cache Transformation Matrices**
   - Compute transformation matrices once and reuse them
   - Store matrix inversions for bidirectional transformations
   - Update matrices only when the coordinate system changes

2. **Use Bulk Transformations**
   - Transform multiple points at once when possible
   - Use batched geometric operations
   - Consider using parallel processing for large transformation sets

3. **Minimize Coordinate System Switches**
   - Complete all operations in one coordinate system before switching
   - Group operations by coordinate system
   - Pass coordinate system objects rather than recreating them

## Troubleshooting

### Common Issues and Solutions

#### Issue: Incorrect Element Orientation

**Symptoms:**
- Framing elements are rotated incorrectly
- Elements have wrong dimensions

**Solutions:**
- Check profile plane orientation:
  ```python
  # Check orientation by visualizing profile axes
  def visualize_profile_plane(profile_plane, scale=1.0):
      """Create visualization to check profile plane orientation."""
      origin = profile_plane.Origin
      x_line = rg.LineCurve(origin, origin + profile_plane.XAxis * scale)
      y_line = rg.LineCurve(origin, origin + profile_plane.YAxis * scale)
      return [x_line, y_line]
  ```
- Verify base plane axes are orthogonal and properly oriented
- Check the order of dimensions in profile creation (width vs. height)

#### Issue: Offset or Displacement Problems

**Symptoms:**
- Elements are in wrong position
- Elements don't align with each other

**Solutions:**
- Verify base plane origin matches the wall's base curve start
- Check UVW values provided to coordinate conversion methods
- Use explicit point construction to debug transformation issues:
  ```python
  # Debug point transformation
  def debug_point_transformation(u, v, w, base_plane):
      """Create step-by-step debug of point transformation."""
      origin = base_plane.Origin
      point = rg.Point3d(origin)
      
      # Add each component and print result
      print(f"Origin: {point}")
      
      point += base_plane.XAxis * u
      print(f"After U={u}: {point}")
      
      point += base_plane.YAxis * v
      print(f"After V={v}: {point}")
      
      point += base_plane.ZAxis * w
      print(f"After W={w}: {point}")
      
      # Compare with direct method
      direct = base_plane.PointAt(u, v, w)
      print(f"Direct method: {direct}")
      print(f"Difference: {point.DistanceTo(direct)}")
      
      return point
  ```

#### Issue: Transformation Matrix Problems

**Symptoms:**
- Transformation methods return None
- Transformed points are clearly incorrect

**Solutions:**
- Check if planes are valid before creating transformations
- Verify transformation matrices have valid determinants (non-zero)
- Try direct vector-based transformation methods as fallback:
  ```python
  def fallback_wall_to_world(u, v, w, base_plane):
      """Fallback method when matrix transformation fails."""
      return rg.Point3d(
          base_plane.Origin.X + base_plane.XAxis.X * u + base_plane.YAxis.X * v + base_plane.ZAxis.X * w,
          base_plane.Origin.Y + base_plane.XAxis.Y * u + base_plane.YAxis.Y * v + base_plane.ZAxis.Y * w,
          base_plane.Origin.Z + base_plane.XAxis.Z * u + base_plane.YAxis.Z * v + base_plane.ZAxis.Z * w
      )
  ```

## Reference Cases

### Standard Wall Configuration

```python
# Wall running along X-axis
wall_data = {
    "wall_base_curve": rg.LineCurve(rg.Point3d(0,0,0), rg.Point3d(10,0,0)),
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_height": 8.0,
    "base_plane": rg.Plane(
        rg.Point3d(0,0,0),      # Origin at start of wall
        rg.Vector3d(1,0,0),     # X-Axis along wall length (U)
        rg.Vector3d(0,0,1)      # Y-Axis vertical (V)
    )
}

# UVW interpretation:
# - U=0 is at (0,0,0), U=10 is at (10,0,0)
# - V=0 is at elevation 0, V=8 is at elevation 8
# - W=0 is at wall centerline, W=+1 is exterior face, W=-1 is interior face
```

### Rotated Wall Configuration

```python
# Wall running at 45 degrees
wall_data = {
    "wall_base_curve": rg.LineCurve(rg.Point3d(0,0,0), rg.Point3d(7.07,7.07,0)),
    "wall_base_elevation": 0.0,
    "wall_top_elevation": 8.0,
    "wall_height": 8.0,
    "base_plane": rg.Plane(
        rg.Point3d(0,0,0),             # Origin at start of wall
        rg.Vector3d(0.707,0.707,0),    # X-Axis along wall length (U)
        rg.Vector3d(0,0,1)             # Y-Axis vertical (V)
    )
}

# UVW interpretation:
# - U=0 is at (0,0,0), U=10 is at (7.07,7.07,0)
# - V=0 is at elevation 0, V=8 is at elevation 8
# - W=0 is at wall centerline, W=+1 is 45° from X and Y axes
```

## Practical Examples

### Placing a Stud at a Specific Position

```python
def place_stud_at_position(u_position, base_plane, stud_width, stud_depth, wall_height):
    """Place a stud at a specific U position in the wall."""
    # Create bottom point of stud centerline
    bottom_point = base_plane.PointAt(u_position, 0, 0)
    
    # Create top point of stud centerline
    top_point = base_plane.PointAt(u_position, wall_height, 0)
    
    # Create centerline
    centerline = rg.LineCurve(bottom_point, top_point)
    
    # Create profile at bottom point
    profile = create_stud_profile(bottom_point, base_plane, stud_width, stud_depth)
    
    # Create extrusion
    path_vector = rg.Vector3d(top_point - bottom_point)
    return create_extrusion(profile, path_vector)
```

### Placing a Header Above an Opening

```python
def place_header_above_opening(opening_data, base_plane, header_width, header_height):
    """Place a header above an opening."""
    # Extract opening data
    u_start = opening_data["start_u_coordinate"]
    u_end = u_start + opening_data["rough_width"]
    v_position = opening_data["base_elevation_relative_to_wall_base"] + opening_data["rough_height"]
    
    # Create header centerline start and end points
    start_point = base_plane.PointAt(u_start, v_position, 0)
    end_point = base_plane.PointAt(u_end, v_position, 0)
    
    # Create centerline
    centerline = rg.LineCurve(start_point, end_point)
    
    # Create profile plane at start point
    profile_plane = rg.Plane(
        start_point,
        base_plane.ZAxis,   # Into wall
        base_plane.YAxis    # Vertical
    )
    
    # Create profile
    profile = rg.Rectangle3d(
        profile_plane,
        rg.Interval(-header_width/2, header_width/2),
        rg.Interval(-header_height/2, header_height/2)
    )
    
    # Create extrusion
    path_vector = rg.Vector3d(end_point - start_point)
    return create_extrusion(profile, path_vector)
```

## Advanced Topics

### Non-Linear Wall Curves

For walls with curved base curves, utilize curve parametrization:

```python
def map_u_to_curve_parameter(u, wall_curve):
    """Map U coordinate to curve parameter."""
    # For a straight line, U directly maps to parameter
    if isinstance(wall_curve, rg.LineCurve):
        return u / wall_curve.GetLength()
    
    # For other curve types, find the parameter at the distance
    return wall_curve.NormalizedLengthParameter(u / wall_curve.GetLength())

def get_point_along_wall(u, v, w, wall_data):
    """Get point along potentially curved wall."""
    curve = wall_data["wall_base_curve"]
    base_elevation = wall_data["wall_base_elevation"]
    
    # Get parameter along curve
    t = map_u_to_curve_parameter(u, curve)
    
    # Get point on curve at parameter
    point_on_curve = curve.PointAt(t)
    
    # Get tangent, normal, and binormal at parameter
    tangent = curve.TangentAt(t)
    tangent.Unitize()
    
    # Normal is vertical
    normal = rg.Vector3d(0, 0, 1)
    
    # Binormal is cross product
    binormal = rg.Vector3d.CrossProduct(tangent, normal)
    binormal.Unitize()
    
    # Create point with offsets
    result = rg.Point3d(point_on_curve)
    result += normal * v
    result += binormal * w
    
    return result
```

### Multiple Coordinate System Contexts

For complex operations involving multiple coordinate systems:

```python
class CoordinateSystemContext:
    """Context manager for coordinate system operations."""
    
    def __init__(self, coordinate_system, point=None):
        """Initialize with a coordinate system and optional point."""
        self.system = coordinate_system
        self.original_point = point
        self.transformed_point = None
    
    def __enter__(self):
        """Transform point to local coordinates on entry."""
        if self.original_point:
            uvw = self.system.world_to_wall(self.original_point)
            self.transformed_point = rg.Point3d(uvw[0], uvw[1], uvw[2])
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Transform point back to world coordinates on exit."""
        if self.transformed_point:
            self.original_point = self.system.wall_to_world(
                self.transformed_point.X,
                self.transformed_point.Y,
                self.transformed_point.Z
            )
```

Usage example:
```python
def process_point_in_local_context(point, wall_data):
    """Process a point in wall-local coordinates."""
    system = WallCoordinateSystem(wall_data)
    
    with CoordinateSystemContext(system, point) as context:
        # Operations in local coordinates
        local_point = context.transformed_point
        
        # Modify local point
        local_point.X += 1.0  # Add 1 to U coordinate
        
        # Modifications are automatically transformed back
    
    # context.original_point now contains the transformed result
    return context.original_point
```

## Conclusion

Understanding the UVW coordinate system and transformations between coordinate systems is crucial for developing features for the Timber Framing Generator. This reference guide provides the necessary tools and techniques to work effectively with the geometric operations required for framing element generation.

Always ensure that coordinate systems are consistently defined and transformations are implemented correctly to avoid issues with positioning and orientation of framing elements. When in doubt, use visualization techniques to verify coordinate system behavior.
