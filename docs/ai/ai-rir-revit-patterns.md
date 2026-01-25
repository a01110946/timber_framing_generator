# Rhino.Inside.Revit Patterns

Learnings from working with Rhino.Inside.Revit (RiR) for baking geometry to Revit.

---

## Beam Cross-Section Rotation (CSR)

**Problem**: CFS (Cold-Formed Steel) C-shaped profiles need specific orientation when baked to Revit. The CSR parameter controls how the cross-section is rotated around the beam's centerline.

### CSR Coordinate System

For a horizontal beam, CSR rotates the cross-section around the centerline axis:

```
local_Y = world_Z × centerline_direction
```

Where `centerline_direction` is the normalized vector from beam start to end.

### CSR Angle Reference

| CSR Angle | C-Opening Faces |
|-----------|-----------------|
| **0°**    | -local_Y (opposite of horizontal perpendicular) |
| **90°**   | +Z (up) |
| **180°**  | +local_Y (horizontal perpendicular) |
| **270°**  | -Z (down) |

### Computing CSR for Target Direction

To orient a beam's cross-section toward a target direction:

```python
# Compute local_Y (horizontal perpendicular to centerline)
# local_Y = world_Z × centerline = (0,0,1) × (vec_x, vec_y, 0)
local_y = (-centerline_y, centerline_x, 0)  # Cross product result

# Determine CSR based on target direction
if target == UP:
    csr = 90.0
elif target == DOWN:
    csr = 270.0
elif dot(target, local_y) > 0:  # Target aligns with local_Y
    csr = 180.0
else:  # Target aligns with -local_Y
    csr = 0.0
```

### Example: Blocking Facing Inward

For wall blocking that should face inward (opposite of wall normal):

```python
def compute_blocking_csr(centerline_vector, wall_normal):
    vec_x, vec_y, vec_z = centerline_vector
    norm_x, norm_y, _ = wall_normal

    # local_Y = world_Z × centerline
    local_y_x = -vec_y
    local_y_y = vec_x

    # Check if local_Y points inward (opposite of wall normal)
    dot_local_y_normal = local_y_x * norm_x + local_y_y * norm_y
    local_y_points_inward = dot_local_y_normal < 0

    if local_y_points_inward:
        # local_Y points inward, CSR 180° faces local_Y direction
        return 180.0
    else:
        # local_Y points outward, CSR 0° faces -local_Y (inward)
        return 0.0
```

### Key Insight

> **CSR 0° and 180° control horizontal orientation (perpendicular to beam), while CSR 90° and 270° control vertical orientation (up/down). The local_Y vector (world_Z × centerline) is the reference for horizontal rotation.**

---

## CFS Framing Element Orientation Rules

Standard orientation for CFS framing elements:

| Element Type | C-Opening Faces | CSR Angle |
|--------------|-----------------|-----------|
| Bottom plate/track | UP | 90° |
| Top plate/track | DOWN | 270° |
| Sill | DOWN | 270° |
| Header | UP | 90° |
| Blocking/Bridging | DOWN | 270° |

**Rationale**:
- Bottom track opens UP to receive studs from above
- Top track opens DOWN to receive studs from below
- Sills open DOWN (like top track, receives cripples from below)
- Headers open UP (like bottom track, receives cripples from above)
- Blocking opens DOWN for consistent orientation

```python
# Simple CSR assignment for horizontal CFS elements
CSR_BY_ELEMENT_TYPE = {
    "bottom_plate": 90.0,   # UP
    "bottom_track": 90.0,   # UP
    "top_plate": 270.0,     # DOWN
    "top_track": 270.0,     # DOWN
    "sill": 270.0,          # DOWN
    "header": 90.0,         # UP
    "row_blocking": 270.0,  # DOWN
    "bridging": 270.0,      # DOWN
}
```

---

## Column Cross-Section Rotation (CSR)

For vertical columns (studs, king studs, trimmers, cripples), CSR rotates around the Z-axis.

### Column CSR Reference

| CSR Angle | C-Opening Faces |
|-----------|-----------------|
| **0°**    | +X |
| **90°**   | -Y |
| **180°**  | -X |
| **270°**  | +Y |

**Note**: 90° and 270° are swapped compared to beams. This was determined empirically through Revit testing.

### CFS Column Orientation Rules

**Base rule**: All columns face toward wall's U vector (wall_x_axis)

| Wall Direction | wall_x_axis | Base CSR |
|----------------|-------------|----------|
| Along +X | (1, 0, 0) | 0° |
| Along -X | (-1, 0, 0) | 180° |
| Along +Y | (0, 1, 0) | 270° |
| Along -Y | (0, -1, 0) | 90° |

**Flip rules** (add 180° to base CSR):
- **End stud**: Last stud at wall end (always flip)
- **With `mirror_opening_studs=True`**:
  - Trimmer BEFORE opening (side 0 / left): flip
  - King stud AFTER opening (side 1 / right): flip

```python
# Column CSR computation
def compute_column_csr(wall_x_axis, is_end_stud, mirror_opening_studs, element_type, element_id):
    wall_ax, wall_ay = wall_x_axis[0], wall_x_axis[1]

    # Base CSR: face toward wall_x_axis
    # Note: For Y-aligned walls, 90°=-Y, 270°=+Y (empirically determined)
    if abs(wall_ax) >= abs(wall_ay):
        # Wall runs along X
        base_csr = 0.0 if wall_ax >= 0 else 180.0
    else:
        # Wall runs along Y
        base_csr = 270.0 if wall_ay >= 0 else 90.0

    # Flip conditions
    should_flip = False
    if is_end_stud and element_type == "stud":
        should_flip = True
    if mirror_opening_studs:
        if element_type == "trimmer" and element_id.endswith("_0"):
            should_flip = True
        elif element_type == "king_stud" and element_id.endswith("_1"):
            should_flip = True

    return (base_csr + 180.0) % 360.0 if should_flip else base_csr
```

### End Stud Detection

End studs are identified by position: `u_coord > wall_length - tolerance`

```python
stud_width = 0.125  # 1.5" in feet
tolerance = stud_width * 1.5
is_end_stud = element.u_coord > wall_length - tolerance
```

---

## Vertical Column Placement with Planes (RECOMMENDED)

**CRITICAL DISCOVERY**: Using "Slanted - End Point Driven" column style causes an offset between the input centerline and the actual column location. The solution is to use **Vertical** column style with **plane-based placement**.

### The Problem with Slanted Columns

When using RiR's `Add Structural Column` component with curves:
- Revit places the column using a reference line that is offset from the profile centroid
- The offset is consistent (~0.023 ft in X, ~0.035 ft in Y for typical CFS profiles)
- This offset varies with CSR angle (flipped studs have different offset direction)
- The offset comes from how Revit handles "End Point Driven" column placement

### The Solution: Vertical Columns with Planes

Vertical columns in Revit:
1. **Use a LocationPoint** (not LocationCurve) for placement
2. **Have NO offset** - the location point is exactly the column centerline
3. **Control orientation via the placement plane's X-axis**, not a CSR parameter

### Plane Construction for Column Orientation

For a vertical column, construct the placement plane as:

```python
# Plane for vertical column placement
# Origin: Column base point (bottom of stud)
# X-axis: Direction where C-section lips should face
# Z-axis: World Z (vertical = column direction)

def create_column_plane(element, wall_x_axis, should_flip=False):
    """
    Create placement plane for a vertical column.

    Args:
        element: FramingElementData with centerline info
        wall_x_axis: Tuple (x, y, z) of wall's X-axis direction
        should_flip: If True, flip X-axis 180° (for end studs, etc.)

    Returns:
        Plane with origin at column base, X-axis controlling orientation
    """
    # Origin at column base (centerline start)
    origin = rg.Point3d(
        element.centerline_start.x,
        element.centerline_start.y,
        element.centerline_start.z
    )

    # X-axis controls where C-section lips face
    # Standard: face toward wall's X-axis direction
    x_axis = rg.Vector3d(wall_x_axis[0], wall_x_axis[1], 0)
    x_axis.Unitize()

    # Flip for end studs, mirrored opening elements, etc.
    if should_flip:
        x_axis = -x_axis

    # Z-axis is always World Z (column goes vertical)
    z_axis = rg.Vector3d(0, 0, 1)

    # Y-axis = Z × X (right-hand rule)
    y_axis = rg.Vector3d.CrossProduct(z_axis, x_axis)
    y_axis.Unitize()

    return rg.Plane(origin, x_axis, y_axis)
```

### Orientation Control via Plane X-Axis

The plane's X-axis determines the column's rotation around its centerline:

| Desired C-Opening Direction | Plane X-Axis |
|----------------------------|--------------|
| Face +X | (1, 0, 0) |
| Face -X | (-1, 0, 0) |
| Face +Y | (0, 1, 0) |
| Face -Y | (0, -1, 0) |

**For wall-aligned studs**: X-axis = wall_x_axis (lips face along wall direction)

### Flip Rules for Plane-Based Orientation

Same as CSR flip rules, but applied by reversing the plane's X-axis:

```python
should_flip = False

# End stud (last stud at wall end)
if is_end_stud and element_type == "stud":
    should_flip = True

# mirror_opening_studs option
if mirror_opening_studs:
    # Trimmer before opening (left side)
    if element_type == "trimmer" and element_id.endswith("_0"):
        should_flip = True
    # King stud after opening (right side)
    elif element_type == "king_stud" and element_id.endswith("_1"):
        should_flip = True
```

### Key Advantages

1. **No centerline offset** - columns placed exactly at input location
2. **Simpler orientation control** - X-axis direction is intuitive
3. **No CSR parameter needed** - rotation handled by plane
4. **Works for all wall orientations** - just align X-axis with wall direction

### RiR Component Connection (Two-Step Workflow)

Columns require a two-step process in Grasshopper:

**Step 1: Create Columns** (Add Structural Column)
- **Curve**: `column_curves` output (centerlines)
- **Type**: Matched Revit Structural Column family type
- **Base Level / Top Level**: From wall data

**Step 2: Update Location for Orientation**
- Parse `baking_data_json` to extract `plane_origin` and `plane_x_axis` for each column
- Create Rhino Planes from this data (in Baking Data Parser or similar component)
- Use RiR Element Location component to update the column's Location

**JSON Structure for Columns:**
```json
{
  "plane_origin": {"x": 10.5, "y": 0.0, "z": 0.0},
  "plane_x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
  "geometry_index": 0
}
```

**Plane Creation in Parser:**
```python
# Create plane from JSON data
origin = rg.Point3d(plane_origin["x"], plane_origin["y"], plane_origin["z"])
x_axis = rg.Vector3d(plane_x_axis["x"], plane_x_axis["y"], 0)
x_axis.Unitize()
z_axis = rg.Vector3d(0, 0, 1)
y_axis = rg.Vector3d.CrossProduct(z_axis, x_axis)
plane = rg.Plane(origin, x_axis, y_axis)
```

> **Note**: The plane-based Location update sets the column to "Vertical" style automatically, avoiding the centerline offset issue that occurs with "Slanted - End Point Driven" style.

---

## Comparison: Curve-Only vs Curve+Plane Workflow

| Aspect | Curve Only (Slanted) | Curve + Plane (Vertical) |
|--------|---------------------|--------------------------|
| Location accuracy | Offset from centroid | Exact centerline |
| Orientation control | CSR parameter | Plane X-axis |
| Revit column style | End Point Driven | Vertical |
| Location type | LocationCurve | LocationPoint |
| Complexity | Single step | Two steps (create + update) |
| Offset issue | Present | Eliminated |

**Recommendation**: Use the two-step curve+plane workflow for all vertical CFS columns to avoid offset issues and gain precise orientation control.

---

---

## Assembly Mismatch: Planes (and All Geometry)

**CRITICAL**: When creating Rhino geometry in GHPython for Grasshopper output, you must use `RhinoCommonFactory` - not direct `rg.Plane()`, `rg.Point3d()`, etc.

### The Problem

```python
# WRONG - creates plane from Rhino3dmIO assembly
import Rhino.Geometry as rg
plane = rg.Plane(origin, x_axis, y_axis)  # Grasshopper can't use this!
```

Grasshopper displays it as a string like:
```
Origin=43.30894346739535, 6.815078908658708, 0.125 XAxis=1,-3.256654...
```

### The Solution

```python
# CORRECT - creates plane from RhinoCommon assembly
from src.timber_framing_generator.utils.geometry_factory import get_factory

rc_factory = get_factory()
plane = rc_factory.create_plane(
    (ox, oy, oz),  # origin as tuple
    (ax, ay, az),  # x_axis as tuple
    (yx, yy, yz)   # y_axis as tuple
)
```

### Applies To All Geometry Types

This assembly mismatch affects ALL geometry creation:
- `Point3d` → use `rc_factory.create_point3d(x, y, z)`
- `Vector3d` → use `rc_factory.create_vector3d(x, y, z)`
- `Plane` → use `rc_factory.create_plane(origin, x_axis, y_axis)`
- `LineCurve` → use `rc_factory.create_line_curve(start, end)`
- `Brep` → use `rc_factory.create_box_brep_from_centerline(...)`

### Key Insight

> **Always extract coordinates as Python floats and pass tuples to `RhinoCommonFactory` methods. This "launders" the data through the assembly boundary, ensuring the output geometry is from the correct RhinoCommon assembly that Grasshopper expects.**

---

---

## MEP Connector Direction Patterns

**Discovery Date**: January 2026

### Understanding Connector.CoordinateSystem.BasisZ

The `BasisZ` vector from a Revit MEP connector does NOT universally indicate "pipe routing direction." Its meaning varies by **system type**:

| System Type | BasisZ Behavior | Routing Implication |
|-------------|-----------------|---------------------|
| **Sanitary (drains)** | Always (0, 0, -1) DOWN | Reliable - route pipes DOWN |
| **Supply (water)** | Points toward pipe source | Varies by fixture design |

### Empirical Findings by Fixture Type

**Kitchen Sink (Double):**
```
Sanitary:         BasisZ = (0, 0, -1)  → DOWN (drain)
DomesticColdWater: BasisZ = (0, 0, -1)  → DOWN (supply from below cabinet)
DomesticHotWater:  BasisZ = (0, 0, -1)  → DOWN (supply from below cabinet)
```
All connectors point DOWN - pipes come from below the cabinet.

**Lavatory (Vanity Sink):**
```
Sanitary:         BasisZ = (0, 0, -1)  → DOWN (drain through P-trap)
DomesticColdWater: BasisZ = (0, -1, 0) or (1, 0, 0)  → Horizontal to wall
DomesticHotWater:  BasisZ = (0, -1, 0) or (1, 0, 0)  → Horizontal to wall
```
Drains go down; supply comes horizontally from wall valves.

**Bathtub:**
```
Sanitary:         BasisZ = (0, 0, -1)  → DOWN (drain)
DomesticColdWater: BasisZ = (0, -1, 0) or (1, 0, 0)  → Horizontal
DomesticHotWater:  BasisZ = (0, -1, 0) or (1, 0, 0)  → Horizontal
```
Similar to lavatory - drains down, supply horizontal.

**Toilet (Water Closet):**
```
Sanitary:         BasisZ = (0, 0, -1)  → DOWN (waste line)
DomesticColdWater: BasisZ = (0, -1, 0) or (1, 0, 0)  → Horizontal to wall
```
Drain down to floor; supply horizontal from wall valve.

### Key Insight

> **For Sanitary connectors, BasisZ is reliable and always points DOWN (gravity flow). For Supply connectors, BasisZ points toward where the pipe comes FROM - this varies based on fixture design and orientation.**

### Routing Strategy

```python
def get_initial_routing_direction(connector):
    """
    Get the initial pipe routing direction from a connector.

    Returns:
        Tuple (x, y, z) - direction to route pipe initially
    """
    system_type = connector.system_type.lower()
    basis_z = connector.direction  # This is BasisZ from extraction

    # Sanitary: ALWAYS route DOWN initially (gravity)
    if 'sanitary' in system_type:
        return (0.0, 0.0, -1.0)

    # Vent: ALWAYS route UP initially
    if 'vent' in system_type:
        return (0.0, 0.0, 1.0)

    # Supply (cold/hot water): Use BasisZ as it points toward source
    # If pointing down → supply comes from below (route down)
    # If pointing horizontal → supply comes from wall (route horizontal)
    if basis_z[2] < -0.5:  # Mostly pointing down
        return (0.0, 0.0, -1.0)
    else:
        # Horizontal - normalize to pure horizontal
        x, y = basis_z[0], basis_z[1]
        mag = (x*x + y*y) ** 0.5
        if mag > 0.01:
            return (x/mag, y/mag, 0.0)
        else:
            return (0.0, 0.0, -1.0)  # Fallback to down
```

### Route Path Construction

For plumbing fixtures, the typical route is:

1. **From connector** → follow initial direction
2. **Drop/rise to routing elevation** (usually near floor level)
3. **Horizontal run** → to nearest wall
4. **Wall entry** → penetrate wall face
5. **First vertical connection** → inside wall cavity

```
Fixture
   │
   │ (initial direction from BasisZ)
   ▼
   ● Routing point (below fixture)
   │
   │ (horizontal to wall)
   ─────────────●───────────● Wall entry + vertical connection
              Wall face   Inside wall
```

### FlowDirection Property

The `FlowDirection` property was `None` for all tested fixtures. This appears to only be set when connectors are actually connected to pipes in Revit. It's not useful for routing unconnected fixtures.

---

## Future Topics

- Level assignment from Revit walls
- Type matching strategies
- Structural framing vs structural column classification
- MEP system routing optimization
