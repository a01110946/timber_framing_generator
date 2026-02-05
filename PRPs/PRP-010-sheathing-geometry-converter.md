# PRP-010: Sheathing Geometry Converter

> **Version:** 1.0
> **Created:** 2026-02-04
> **Status:** Draft
> **Branch:** feature/sheathing-geometry-converter

---

## Goal

Create a Grasshopper component that converts sheathing JSON data into 3D Brep geometry, completing the sheathing pipeline and enabling visualization/baking of sheathing panels.

---

## Why

### Business Value
- **Visual Verification**: Designers can see sheathing layout before fabrication
- **Clash Detection**: Identify conflicts between sheathing and other building elements
- **Material Takeoff**: Export geometry for BIM coordination and quantity verification
- **Complete Pipeline**: Sheathing generator exists but has no geometry output

### Technical Requirements
- **Assembly Compatibility**: Must use RhinoCommonFactory for Grasshopper-compatible Breps
- **Cutout Support**: Sheathing panels have window/door cutouts that must be represented
- **Face Offset**: Panels positioned on exterior or interior face (offset from wall centerline)

### Problems Solved
1. Sheathing generator outputs JSON only - no visualization
2. No way to verify sheathing layout in Rhino/Grasshopper
3. Missing final step in sheathing pipeline

---

## What

### User-Visible Behavior

**Input**: `sheathing_json` from Sheathing Generator
**Output**:
- 3D Breps for each sheathing panel
- Cutouts subtracted for openings
- Panels positioned on correct wall face
- Summary statistics

### Pipeline Integration

```
Wall Analyzer → walls_json → Sheathing Generator → sheathing_json
    → [NEW] Sheathing Geometry Converter → Breps
```

### Success Criteria

- [ ] Converts sheathing_json to Breps
- [ ] Cutouts correctly subtracted from panels
- [ ] Panels positioned at correct face offset (exterior/interior)
- [ ] Uses RhinoCommonFactory for assembly compatibility
- [ ] DataTree output organized by wall ID
- [ ] Summary output with panel counts and areas
- [ ] Follows existing gh_geometry_converter.py patterns

---

## Research Findings

### Existing Sheathing Data Structure

From `sheathing_generator.py`, the output JSON structure:

```json
{
  "wall_id": "wall_123",
  "sheathing_panels": [
    {
      "id": "wall_123_sheath_exterior_0_0",
      "wall_id": "wall_123",
      "face": "exterior",
      "material": "structural_plywood_7_16",
      "thickness_inches": 0.4375,
      "u_start": 0.0,
      "u_end": 4.0,
      "v_start": 0.0,
      "v_end": 8.0,
      "row": 0,
      "column": 0,
      "is_full_sheet": true,
      "area_gross_sqft": 32.0,
      "area_net_sqft": 32.0,
      "cutouts": [
        {
          "opening_type": "window",
          "u_start": 2.0,
          "u_end": 4.0,
          "v_start": 3.0,
          "v_end": 7.0
        }
      ]
    }
  ]
}
```

### Geometry Creation Approach

1. **Panel Rectangle**: Create from u_start/u_end, v_start/v_end in UVW coordinates
2. **Cutout Subtraction**: Boolean difference for each cutout
3. **Thickness Extrusion**: Extrude by `thickness_inches` (convert to feet)
4. **Face Positioning**: Offset from wall centerline based on `face` (exterior/interior)

### Face Offset Calculation

```python
# Exterior face: offset outward (positive W direction)
# Interior face: offset inward (negative W direction)
wall_thickness = wall_data.get("thickness", 0.5)  # feet
half_thickness = wall_thickness / 2

if face == "exterior":
    w_offset = half_thickness  # Panel on exterior face
else:
    w_offset = -half_thickness - panel_thickness  # Panel on interior face
```

---

## All Needed Context

### Documentation & References

```yaml
Project Docs:
  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for panel positioning

  - file: docs/ai/ai-geometry-assembly-solution.md
    why: RhinoCommonFactory patterns for Brep creation

Core Implementations:
  - file: src/timber_framing_generator/sheathing/sheathing_generator.py
    why: Understand sheathing JSON structure

  - file: src/timber_framing_generator/sheathing/sheathing_profiles.py
    why: Material properties (thickness)

  - file: scripts/gh_geometry_converter.py
    why: Pattern for geometry conversion component

  - file: src/timber_framing_generator/utils/geometry_factory.py
    why: RhinoCommonFactory API
```

### Desired Structure

```
src/timber_framing_generator/
└── sheathing/
    ├── __init__.py              # Already exists
    ├── sheathing_generator.py   # Already exists
    ├── sheathing_profiles.py    # Already exists
    └── sheathing_geometry.py    # NEW: Geometry conversion logic

scripts/
└── gh_sheathing_geometry_converter.py  # NEW: GHPython component

tests/
└── sheathing/
    ├── test_sheathing_generator.py     # Already exists
    └── test_sheathing_geometry.py      # NEW: Geometry tests
```

### Known Gotchas

```yaml
CRITICAL - Assembly Mismatch:
  issue: rhino3dm creates Rhino3dmIO geometry, GH needs RhinoCommon
  solution: Use RhinoCommonFactory for ALL geometry creation

CRITICAL - Boolean Operations:
  issue: BooleanDifference can fail on degenerate geometry
  solution: Validate cutout dimensions, handle failures gracefully

IMPORTANT - Coordinate Transform:
  issue: Sheathing uses UVW coordinates, geometry needs world XYZ
  solution: Transform using wall base_plane
  pattern: |
    world_point = base_plane.Origin +
                  base_plane.XAxis * u +
                  base_plane.YAxis * v +
                  base_plane.ZAxis * w

IMPORTANT - Thickness Units:
  issue: sheathing_profiles uses inches, geometry uses feet
  solution: Convert thickness_inches to feet (÷ 12)
```

---

## Implementation Blueprint

### Phase 1: Core Geometry Module

```python
# File: src/timber_framing_generator/sheathing/sheathing_geometry.py

"""
Sheathing panel geometry creation.

Converts sheathing panel data (UVW coordinates) to 3D Brep geometry
with cutouts for openings.
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

@dataclass
class SheathingPanelGeometry:
    """Geometry data for a sheathing panel."""
    panel_id: str
    wall_id: str
    face: str
    brep: Any  # RhinoCommon Brep
    area_gross: float
    area_net: float
    has_cutouts: bool


def create_panel_brep(
    panel_data: Dict,
    wall_base_plane: Dict,
    wall_thickness: float,
    factory: Any
) -> Optional[Any]:
    """
    Create a Brep for a sheathing panel.

    Args:
        panel_data: Sheathing panel dictionary from sheathing_json
        wall_base_plane: Wall's base plane (origin, x_axis, y_axis, z_axis)
        wall_thickness: Wall thickness in feet
        factory: RhinoCommonFactory instance

    Returns:
        RhinoCommon Brep or None if creation fails
    """
    # Extract panel bounds (UVW coordinates, in feet)
    u_start = panel_data["u_start"]
    u_end = panel_data["u_end"]
    v_start = panel_data["v_start"]
    v_end = panel_data["v_end"]

    # Panel thickness (convert inches to feet)
    thickness_ft = panel_data["thickness_inches"] / 12.0

    # Calculate W offset based on face
    half_wall = wall_thickness / 2.0
    face = panel_data.get("face", "exterior")

    if face == "exterior":
        w_offset = half_wall  # On exterior face
    else:
        w_offset = -half_wall - thickness_ft  # On interior face

    # Create panel corners in UVW
    corners_uvw = [
        (u_start, v_start, w_offset),                    # Bottom-left
        (u_end, v_start, w_offset),                      # Bottom-right
        (u_end, v_end, w_offset),                        # Top-right
        (u_start, v_end, w_offset),                      # Top-left
    ]

    # Transform to world coordinates
    corners_world = [
        uvw_to_world(u, v, w, wall_base_plane)
        for u, v, w in corners_uvw
    ]

    # Create rectangle surface
    panel_surface = factory.create_planar_surface_from_corners(corners_world)

    if panel_surface is None:
        return None

    # Extrude by thickness (in wall normal direction)
    extrusion_vector = get_extrusion_vector(face, wall_base_plane, thickness_ft)
    panel_brep = factory.extrude_surface(panel_surface, extrusion_vector)

    if panel_brep is None:
        return None

    # Subtract cutouts
    cutouts = panel_data.get("cutouts", [])
    if cutouts:
        panel_brep = subtract_cutouts(
            panel_brep, cutouts, wall_base_plane,
            w_offset, thickness_ft, factory
        )

    return panel_brep


def subtract_cutouts(
    panel_brep: Any,
    cutouts: List[Dict],
    wall_base_plane: Dict,
    w_offset: float,
    thickness: float,
    factory: Any
) -> Any:
    """
    Subtract cutout regions from panel brep.

    Args:
        panel_brep: Base panel Brep
        cutouts: List of cutout dictionaries
        wall_base_plane: Wall's base plane
        w_offset: W offset of panel face
        thickness: Panel thickness in feet
        factory: RhinoCommonFactory instance

    Returns:
        Panel Brep with cutouts subtracted
    """
    result = panel_brep

    for cutout in cutouts:
        # Create cutout box (slightly oversized to ensure clean cut)
        cutout_brep = create_cutout_brep(
            cutout, wall_base_plane, w_offset, thickness, factory
        )

        if cutout_brep is None:
            continue

        # Boolean difference
        new_result = factory.boolean_difference(result, cutout_brep)

        if new_result is not None:
            result = new_result
        # If boolean fails, keep original (log warning)

    return result


def create_cutout_brep(
    cutout: Dict,
    wall_base_plane: Dict,
    w_offset: float,
    thickness: float,
    factory: Any
) -> Optional[Any]:
    """Create a Brep for a cutout region."""
    u_start = cutout["u_start"]
    u_end = cutout["u_end"]
    v_start = cutout["v_start"]
    v_end = cutout["v_end"]

    # Validate dimensions
    if u_end <= u_start or v_end <= v_start:
        return None

    # Create cutout box corners (extend slightly beyond panel thickness)
    tolerance = 0.01  # 0.01 feet = ~1/8 inch
    corners_uvw = [
        (u_start, v_start, w_offset - tolerance),
        (u_end, v_start, w_offset - tolerance),
        (u_end, v_end, w_offset - tolerance),
        (u_start, v_end, w_offset - tolerance),
    ]

    corners_world = [
        uvw_to_world(u, v, w, wall_base_plane)
        for u, v, w in corners_uvw
    ]

    # Create and extrude
    cutout_surface = factory.create_planar_surface_from_corners(corners_world)
    if cutout_surface is None:
        return None

    extrusion_depth = thickness + 2 * tolerance
    # Extrude in wall normal direction
    normal = (
        wall_base_plane["z_axis"]["x"],
        wall_base_plane["z_axis"]["y"],
        wall_base_plane["z_axis"]["z"]
    )
    extrusion_vector = (
        normal[0] * extrusion_depth,
        normal[1] * extrusion_depth,
        normal[2] * extrusion_depth
    )

    return factory.extrude_surface(cutout_surface, extrusion_vector)


def uvw_to_world(
    u: float, v: float, w: float,
    base_plane: Dict
) -> Tuple[float, float, float]:
    """
    Transform UVW coordinates to world XYZ.

    Args:
        u: Along wall length
        v: Vertical (up)
        w: Through wall (normal direction)
        base_plane: Wall base plane dictionary

    Returns:
        (x, y, z) world coordinates
    """
    origin = base_plane["origin"]
    x_axis = base_plane["x_axis"]
    y_axis = base_plane["y_axis"]
    z_axis = base_plane["z_axis"]

    x = origin["x"] + x_axis["x"] * u + y_axis["x"] * v + z_axis["x"] * w
    y = origin["y"] + x_axis["y"] * u + y_axis["y"] * v + z_axis["y"] * w
    z = origin["z"] + x_axis["z"] * u + y_axis["z"] * v + z_axis["z"] * w

    return (x, y, z)


def get_extrusion_vector(
    face: str,
    wall_base_plane: Dict,
    thickness: float
) -> Tuple[float, float, float]:
    """Get extrusion vector for panel thickness."""
    z_axis = wall_base_plane["z_axis"]

    # Exterior: extrude outward (positive normal)
    # Interior: extrude inward (negative normal)
    direction = 1.0 if face == "exterior" else -1.0

    return (
        z_axis["x"] * thickness * direction,
        z_axis["y"] * thickness * direction,
        z_axis["z"] * thickness * direction
    )
```

### Phase 2: Extend RhinoCommonFactory

```python
# Add to: src/timber_framing_generator/utils/geometry_factory.py

def create_planar_surface_from_corners(
    self,
    corners: List[Tuple[float, float, float]]
) -> Optional[Any]:
    """
    Create a planar surface from 4 corner points.

    Args:
        corners: List of 4 (x, y, z) tuples in order

    Returns:
        RhinoCommon Surface or None
    """
    if len(corners) != 4:
        return None

    # Create corner points
    pts = [self.create_point3d(*c) for c in corners]

    # Create polyline curve (closed)
    pts_closed = pts + [pts[0]]
    polyline = self.create_polyline_curve(pts_closed)

    if polyline is None:
        return None

    # Create planar surface from boundary
    breps = self.rg_brep.CreatePlanarBreps(polyline, 0.001)

    if breps and len(breps) > 0:
        return breps[0]
    return None


def extrude_surface(
    self,
    surface: Any,
    direction: Tuple[float, float, float]
) -> Optional[Any]:
    """
    Extrude a surface along a direction vector.

    Args:
        surface: RhinoCommon Brep (planar surface)
        direction: (x, y, z) extrusion vector

    Returns:
        RhinoCommon Brep or None
    """
    vec = self.create_vector3d(*direction)

    # Get faces from brep
    if hasattr(surface, 'Faces') and surface.Faces.Count > 0:
        face = surface.Faces[0]
        extruded = face.CreateExtrusion(vec, True)
        if extruded:
            return extruded.ToBrep()

    return None


def boolean_difference(
    self,
    brep_a: Any,
    brep_b: Any
) -> Optional[Any]:
    """
    Boolean difference: brep_a - brep_b.

    Args:
        brep_a: Base Brep
        brep_b: Brep to subtract

    Returns:
        Result Brep or None if operation fails
    """
    results = self.rg_brep.CreateBooleanDifference(brep_a, brep_b, 0.001)

    if results and len(results) > 0:
        return results[0]
    return None
```

### Phase 3: GHPython Component

```python
# File: scripts/gh_sheathing_geometry_converter.py
# See full implementation in Tasks section
```

---

## Tasks (Execution Order)

### Task 1: Extend RhinoCommonFactory
```yaml
action: MODIFY
file: src/timber_framing_generator/utils/geometry_factory.py
add:
  - create_planar_surface_from_corners()
  - extrude_surface()
  - boolean_difference()
preserve: All existing methods
```

### Task 2: Create Sheathing Geometry Module
```yaml
action: CREATE
file: src/timber_framing_generator/sheathing/sheathing_geometry.py
content: Core geometry conversion logic (uvw_to_world, create_panel_brep, etc.)
```

### Task 3: Update Sheathing __init__.py
```yaml
action: MODIFY
file: src/timber_framing_generator/sheathing/__init__.py
add: Export sheathing_geometry functions
```

### Task 4: Create GHPython Component
```yaml
action: CREATE
file: scripts/gh_sheathing_geometry_converter.py
content: |
  - Follow gh_geometry_converter.py patterns
  - Inputs: sheathing_json, walls_json (for base_plane), run
  - Outputs: breps, by_wall DataTree, summary, debug_info
```

### Task 5: Add Unit Tests
```yaml
action: CREATE
file: tests/sheathing/test_sheathing_geometry.py
content: |
  - Test uvw_to_world transformation
  - Test panel brep creation
  - Test cutout subtraction
  - Test face offset calculation
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
python -m py_compile src/timber_framing_generator/sheathing/sheathing_geometry.py
ruff check src/timber_framing_generator/sheathing/
mypy src/timber_framing_generator/sheathing/
```

### Level 2: Unit Tests
```bash
pytest tests/sheathing/test_sheathing_geometry.py -v
```

### Level 3: Integration Tests
```bash
pytest tests/sheathing/ -v
```

### Level 4: Grasshopper Validation
1. Load GH definition
2. Connect Wall Analyzer → Sheathing Generator → Sheathing Geometry Converter
3. Verify panels appear on correct wall face
4. Verify cutouts are present at openings
5. Check panel dimensions match expected values

---

## References

- `scripts/gh_geometry_converter.py` - Pattern for geometry conversion
- `src/timber_framing_generator/sheathing/sheathing_generator.py` - Sheathing JSON format
- `docs/ai/ai-geometry-assembly-solution.md` - RhinoCommonFactory usage
- `docs/ai/ai-coordinate-system-reference.md` - UVW coordinate system
