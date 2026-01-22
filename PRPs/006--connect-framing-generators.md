# PRP 006: Connect Framing Generators to Strategy Pattern

> **Status**: ✅ COMPLETE
> **Created**: 2026-01-21
> **Completed**: 2026-01-21
> **Branch**: feature/phase6-connect-generators

## Overview

Connect the existing framing generators (`plates.py`, `studs.py`, `king_studs.py`, etc.) to the `TimberFramingStrategy` methods so that actual `FramingElement` objects are generated instead of empty lists.

## Problem Statement

The `TimberFramingStrategy` currently returns empty lists from all its `create_*` methods. This means the Grasshopper pipeline produces 0 framing elements. We need to:

1. Wire up the existing generators to the strategy methods
2. Convert the Rhino geometry (Breps) from existing generators to `FramingElement` data objects
3. Ensure centerline data is properly extracted for JSON serialization

## Architecture Decision

### Approach: Adapter Pattern

Rather than rewriting the generators, we'll create adapter functions that:
1. Call existing generators to get Rhino geometry (Breps)
2. Extract centerline/positional data from the Breps
3. Return `FramingElement` objects that can be serialized to JSON

This approach:
- Reuses existing tested logic
- Minimizes risk of bugs
- Maintains backward compatibility

### Data Flow

```
JSON wall_data → Reconstruct Rhino geometry → Existing generators → Breps
                                                                       ↓
JSON FramingElement ← Extract centerline data ← Brep bounding boxes ←──┘
```

## Implementation Tasks

### Task 1: Create Element Adapter Utilities

Create `src/timber_framing_generator/materials/timber/element_adapters.py`:

```python
"""
Adapter functions to convert existing Brep-based framing elements
to FramingElement data objects.
"""

def brep_to_framing_element(
    brep: rg.Brep,
    element_type: ElementType,
    profile: ElementProfile,
    base_plane: rg.Plane,
    element_id: str,
    cell_id: str = None
) -> FramingElement:
    """
    Extract centerline and positional data from a Brep.
    """
    # Get bounding box
    bbox = brep.GetBoundingBox(True)

    # For vertical elements (studs):
    # - centerline runs from bottom center to top center
    # - u_coord is horizontal position along wall

    # For horizontal elements (plates, headers):
    # - centerline runs along the length
    # - v is vertical position

    ...
```

### Task 2: Implement create_horizontal_members()

Connect to `plates.py`:

```python
def create_horizontal_members(self, wall_data, cell_data, config):
    # Reconstruct wall_data dict with Rhino geometry
    rhino_wall_data = self._prepare_wall_data(wall_data)

    # Call existing plate generator
    bottom_plates = create_plates(
        rhino_wall_data,
        plate_type="bottom_plate",
        representation_type="schematic",
        layers=config.get("bottom_plate_layers", 1)
    )

    top_plates = create_plates(
        rhino_wall_data,
        plate_type="top_plate",
        representation_type="schematic",
        layers=config.get("top_plate_layers", 2)
    )

    # Convert PlateGeometry objects to FramingElement
    elements = []
    for i, plate in enumerate(bottom_plates):
        elem = self._plate_to_framing_element(plate, i, ElementType.BOTTOM_PLATE)
        elements.append(elem)

    for i, plate in enumerate(top_plates):
        elem = self._plate_to_framing_element(plate, i, ElementType.TOP_PLATE)
        elements.append(elem)

    return elements
```

### Task 3: Implement create_vertical_members()

Connect to `king_studs.py`, `studs.py`, `trimmers.py`:

```python
def create_vertical_members(self, wall_data, cell_data, horizontal_members, config):
    rhino_wall_data = self._prepare_wall_data(wall_data)

    # Need plates for generator initialization
    bottom_plate, top_plate = self._get_plate_geometry(horizontal_members, rhino_wall_data)

    elements = []

    # King studs for each opening
    openings = wall_data.get("openings", [])
    king_gen = KingStudGenerator(rhino_wall_data, bottom_plate, top_plate)
    for opening in openings:
        king_studs = king_gen.generate_king_studs(opening)
        for brep in king_studs:
            elem = self._brep_to_framing_element(brep, ElementType.KING_STUD, ...)
            elements.append(elem)

    # Standard studs
    stud_gen = StudGenerator(rhino_wall_data, bottom_plate, top_plate, king_studs)
    studs = stud_gen.generate_studs()
    for brep in studs:
        elem = self._brep_to_framing_element(brep, ElementType.STUD, ...)
        elements.append(elem)

    # Trimmers
    ...

    return elements
```

### Task 4: Implement create_opening_members()

Connect to `headers.py`, `sills.py`, `header_cripples.py`, `sill_cripples.py`:

```python
def create_opening_members(self, wall_data, cell_data, existing_members, config):
    # Headers
    # Sills (windows only)
    # Header cripples
    # Sill cripples (windows only)
    ...
```

### Task 5: Implement create_bracing_members()

Connect to `row_blocking.py`:

```python
def create_bracing_members(self, wall_data, cell_data, existing_members, config):
    # Row blocking between studs
    ...
```

### Task 6: Add Wall Data Reconstruction Helper

The JSON wall_data needs Rhino geometry reconstructed:

```python
def _prepare_wall_data(self, wall_data: Dict) -> Dict:
    """
    Reconstruct Rhino geometry from JSON wall_data.

    JSON has:
      - base_plane: {origin: {x,y,z}, x_axis: {...}, ...}
      - base_curve_start: {x, y, z}
      - base_curve_end: {x, y, z}

    Need to create:
      - base_plane: rg.Plane
      - wall_base_curve: rg.LineCurve
    """
    import Rhino.Geometry as rg

    # Reconstruct base plane
    plane_data = wall_data.get("base_plane", {})
    origin = plane_data.get("origin", {})
    x_axis = plane_data.get("x_axis", {})
    y_axis = plane_data.get("y_axis", {})

    origin_pt = rg.Point3d(origin["x"], origin["y"], origin["z"])
    x_vec = rg.Vector3d(x_axis["x"], x_axis["y"], x_axis["z"])
    y_vec = rg.Vector3d(y_axis["x"], y_axis["y"], y_axis["z"])

    base_plane = rg.Plane(origin_pt, x_vec, y_vec)

    # Reconstruct base curve
    start = wall_data.get("base_curve_start", {})
    end = wall_data.get("base_curve_end", {})

    start_pt = rg.Point3d(start["x"], start["y"], start["z"])
    end_pt = rg.Point3d(end["x"], end["y"], end["z"])
    base_curve = rg.LineCurve(start_pt, end_pt)

    # Build complete wall_data dict
    result = dict(wall_data)  # Copy
    result["base_plane"] = base_plane
    result["wall_base_curve"] = base_curve
    result["wall_base_elevation"] = wall_data.get("base_elevation", 0)
    result["wall_top_elevation"] = wall_data.get("top_elevation", 0)
    result["wall_type"] = wall_data.get("wall_type", "2x4")

    return result
```

## Validation

### Lint Check
```bash
ruff check src/timber_framing_generator/materials/timber/
```

### Type Check
```bash
mypy src/timber_framing_generator/materials/timber/
```

### Unit Tests
```bash
pytest tests/unit/test_timber_strategy.py -v
```

### Integration Test
Run the Grasshopper pipeline and verify:
1. Elements JSON contains non-empty `elements` array
2. Element types include plates, studs, king_studs
3. Geometry Converter produces Breps from the elements

## Files to Modify

- `src/timber_framing_generator/materials/timber/timber_strategy.py` - Main implementation
- `src/timber_framing_generator/materials/timber/element_adapters.py` - NEW: Adapter utilities

## Files to Reference

- `src/timber_framing_generator/framing_elements/framing_generator.py` - Existing orchestrator
- `src/timber_framing_generator/framing_elements/plates.py` - Plate generation
- `src/timber_framing_generator/framing_elements/studs.py` - Stud generation
- `src/timber_framing_generator/framing_elements/king_studs.py` - King stud generation
- `src/timber_framing_generator/core/material_system.py` - FramingElement definition

## Gotchas

1. **PlateGeometry vs Brep**: `create_plates()` returns `PlateGeometry` objects, not Breps. Use `plate.centerline` and `plate.parameters` for data extraction.

2. **Coordinate System**: Wall data uses UVW coordinates:
   - U = along wall length (X direction)
   - V = vertical (Z direction)
   - W = wall thickness (Y direction)

3. **Opening Data Format**: Existing generators expect specific keys:
   - `start_u_coordinate` (not `u_start`)
   - `rough_width` / `rough_height`
   - `base_elevation_relative_to_wall_base` (not `v_start`)

4. **Rhino Dependency**: The adapter code runs inside Grasshopper and has access to `Rhino.Geometry`. The strategy needs to handle both JSON input and live Rhino objects.

## Success Criteria

- [ ] `TimberFramingStrategy.generate_framing()` returns non-empty list
- [ ] Elements include: bottom_plate, top_plate, stud, king_stud (at minimum)
- [ ] Geometry Converter produces valid Breps from the elements
- [ ] All existing unit tests still pass
- [ ] No regression in existing Grasshopper workflow

## Estimated Complexity

Medium-High: Requires careful integration of existing generators with new data format while handling coordinate system conversions and geometry reconstruction.
