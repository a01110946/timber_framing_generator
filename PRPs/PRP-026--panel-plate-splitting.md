# PRP-026: Panel-Aware Plate Splitting & Element-to-Panel Assignment

> **Version:** 1.0
> **Created:** 2026-02-09
> **Status:** Draft
> **Branch:** feature/panel-plate-splitting

---

## Goal

When walls are panelized (split into panels for offsite manufacturing and transport), all framing elements -- particularly plates -- must be bounded by panel boundaries. Currently, a long wall split into four panels still produces a single continuous top plate and single continuous bottom plate. This PRP adds:

1. **Plate splitting at panel joints**: Top and bottom plates are split into per-panel segments, one plate per panel per layer.
2. **Panel ID on every framing element**: Every framing element (`FramingElementData`) gets a `panel_id` property that identifies which panel it belongs to, enabling downstream Revit Assembly creation.

---

## Why

### Business Value
- **Revit Assemblies**: Each panel becomes a Revit Assembly containing only its own framing elements. Without `panel_id`, there is no way to group elements into assemblies.
- **Manufacturing**: Offsite panel lines need cut lists per panel. A continuous plate spanning multiple panels cannot be manufactured or shipped as separate units.
- **Transport**: Panels are the unit of transport. Elements that cross panel boundaries cannot be loaded onto trucks independently.
- **Field Assembly**: Crane lifts entire panels into place. Each panel must be self-contained with its own plates.

### Problems Solved
1. Plates currently span the entire wall regardless of panelization
2. No `panel_id` property exists on framing elements, making Revit Assembly grouping impossible
3. Panel decomposer tracks `element_ids` but the framing pipeline doesn't consume panel data

---

## What

### User-Visible Behavior

**Input**: Existing framing pipeline outputs + `panels_json` from panel decomposer
**Output**:
- Plates split at panel joint U-coordinates (one plate segment per panel per layer)
- Every framing element tagged with `panel_id`
- Updated `framing_json` with per-element `panel_id` field

### Success Criteria

- [ ] When a wall has N panels, there are N bottom plates (per layer) and N top plates (per layer)
- [ ] Plate segments are bounded exactly by panel `u_start` and `u_end`
- [ ] Bottom plate door splits still work correctly within panels (door + panel boundary splits compose)
- [ ] Every `FramingElementData` in `framing_json` has a `panel_id` field (nullable for non-panelized walls)
- [ ] Panel ID assignment is based on the element's U-coordinate falling within the panel's `[u_start, u_end]` range
- [ ] Elements at panel boundaries (e.g., king studs at a joint) are assigned to the panel where their center falls
- [ ] Existing non-panelized workflow is unaffected (panel_id is null/None when no panels_json is provided)
- [ ] Unit tests cover: single panel (no split), multi-panel split, panel + door split composition, panel_id assignment

---

## All Needed Context

### Documentation & References

```yaml
Project Docs:
  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for plate positioning along wall

  - file: docs/ai/ai-modular-architecture-plan.md
    why: Modular component architecture and JSON communication pattern

Feature-Specific:
  - file: src/timber_framing_generator/framing_elements/plates.py
    why: Current plate generation with door-split logic (pattern to extend for panel splits)

  - file: src/timber_framing_generator/panels/panel_decomposer.py
    why: Panel decomposition output format (panels with u_start/u_end)

  - file: src/timber_framing_generator/panels/panel_config.py
    why: Panel configuration and exclusion zones

  - file: src/timber_framing_generator/core/json_schemas.py
    why: FramingElementData schema (needs panel_id field), PanelData schema

  - file: src/timber_framing_generator/framing_elements/framing_generator.py
    why: Framing orchestrator that calls create_plates() and assembles all elements

  - file: src/timber_framing_generator/framing_elements/plate_geometry.py
    why: PlateGeometry class used for plate representation

  - file: src/timber_framing_generator/framing_elements/plate_parameters.py
    why: PlateParameters used for plate configuration
```

### Current Codebase Structure

```
src/timber_framing_generator/
├── core/
│   └── json_schemas.py          # FramingElementData (needs panel_id), PanelData
├── panels/
│   ├── panel_config.py          # PanelConfig, ExclusionZone
│   ├── panel_decomposer.py      # decompose_wall_to_panels() -> panels with u_start/u_end
│   ├── corner_handler.py        # Corner adjustments
│   └── joint_optimizer.py       # Joint placement
├── framing_elements/
│   ├── framing_generator.py     # FramingGenerator._generate_plates() orchestrator
│   ├── plates.py                # create_plates() with door-split logic
│   ├── plate_geometry.py        # PlateGeometry class
│   └── plate_parameters.py      # PlateParameters class
└── config/
    └── framing.py               # FRAMING_PARAMS
```

### Desired Structure (files to add/modify)

```bash
src/timber_framing_generator/
├── core/
│   └── json_schemas.py          # MODIFY: Add panel_id to FramingElementData
├── panels/
│   └── panel_decomposer.py      # MODIFY: Add panel-aware element assignment helper
├── framing_elements/
│   ├── framing_generator.py     # MODIFY: Accept panels_json, pass to plate creation, assign panel_ids
│   └── plates.py                # MODIFY: Add panel boundary splitting (compose with door splits)

tests/
├── test_panel_plate_splitting.py  # NEW: Panel-aware plate splitting tests
└── test_panel_id_assignment.py    # NEW: Panel ID assignment tests
```

### Known Gotchas & Library Quirks

```yaml
CRITICAL - Plate door splitting already exists:
  issue: Bottom plates already split at door openings via _split_reference_line_at_doors()
  impact: Panel splits must compose with door splits, not replace them
  solution: |
    Apply panel splits FIRST (split reference line at panel boundaries),
    then apply door splits WITHIN each panel segment.
    Order matters: panel boundaries -> door boundaries -> final segments.

CRITICAL - Plate types and layers:
  issue: Bottom plates can be [sole_plate, bottom_plate] (2 layers), top plates can be [top_plate, cap_plate]
  impact: Each layer needs its own set of panel-split segments
  solution: |
    The panel boundary splitting happens at the reference_line level,
    which is per-layer. Each layer's reference line gets split at the same
    panel U-coordinates.

CRITICAL - Elements at panel boundaries:
  issue: A king stud or trimmer may sit exactly at a panel joint U-coordinate
  impact: It must belong to exactly one panel, not both
  solution: |
    Use the element's center U-coordinate for assignment.
    If center is exactly at boundary, assign to the LEFT panel (u_start <= u < u_end for all panels
    except the last, which uses u_start <= u <= u_end).

CRITICAL - Non-panelized workflow must not break:
  issue: Many walls will not be panelized (single panel = entire wall)
  impact: panel_id should be None/null when no panels_json is provided
  solution: |
    Make panels_json an optional input. When absent, plates are generated
    as today (full wall length) and panel_id is None on all elements.
```

---

## Implementation Blueprint

### Data Model Changes

```python
# File: src/timber_framing_generator/core/json_schemas.py

@dataclass
class FramingElementData:
    """Single framing element data for JSON serialization."""
    id: str
    element_type: str
    profile: ProfileData
    centerline_start: Point3D
    centerline_end: Point3D
    u_coord: float
    v_start: float
    v_end: float
    cell_id: Optional[str] = None
    panel_id: Optional[str] = None  # NEW: Links element to its panel for Revit Assembly
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Panel-Aware Plate Splitting Logic

```python
# File: src/timber_framing_generator/framing_elements/plates.py

def _split_reference_line_at_panel_boundaries(
    reference_line,
    panel_boundaries: List[Tuple[float, float]],
    base_plane
) -> List[Tuple[Any, str]]:
    """
    Split a reference line into segments at panel boundaries.

    Args:
        reference_line: The original plate centerline (rg.Curve)
        panel_boundaries: List of (u_start, u_end, panel_id) tuples
        base_plane: Wall's base plane for coordinate transformation

    Returns:
        List of (LineCurve_segment, panel_id) tuples
    """
    # Similar pattern to _split_reference_line_at_doors()
    # For each panel, create a segment from panel.u_start to panel.u_end
    # The result is one reference line segment per panel
    ...


def create_plates(
    wall_data: Dict,
    plate_type: str = "bottom_plate",
    representation_type: str = "structural",
    profile_override: Optional[str] = None,
    layers: Optional[int] = None,
    openings: Optional[List[Dict[str, Any]]] = None,
    panel_boundaries: Optional[List[Dict[str, Any]]] = None,  # NEW
) -> List[PlateGeometry]:
    """
    Creates plate geometry objects for a wall.

    NEW: When panel_boundaries is provided, plates are split at panel
    joint locations. Each resulting plate segment carries a panel_id.
    Door splits (bottom plate only) compose with panel splits:
    panel split first, then door split within each panel segment.
    """
    ...
```

### Panel ID Assignment

```python
# File: src/timber_framing_generator/panels/panel_decomposer.py (or new utility)

def assign_panel_ids(
    elements: List[Dict],
    panels: List[Dict],
) -> List[Dict]:
    """
    Assign panel_id to each framing element based on U-coordinate.

    For each element, find which panel's [u_start, u_end] range
    contains the element's u_coord. Elements exactly at a boundary
    are assigned to the left panel.

    Args:
        elements: List of FramingElementData dicts with 'u_coord'
        panels: List of PanelData dicts with 'id', 'u_start', 'u_end'

    Returns:
        Same elements list with 'panel_id' field populated
    """
    for element in elements:
        u = element.get("u_coord", 0)
        for i, panel in enumerate(panels):
            u_start = panel["u_start"]
            u_end = panel["u_end"]
            # Last panel includes right boundary
            if i == len(panels) - 1:
                if u_start <= u <= u_end:
                    element["panel_id"] = panel["id"]
                    break
            else:
                if u_start <= u < u_end:
                    element["panel_id"] = panel["id"]
                    break
    return elements
```

### Integration in FramingGenerator

```python
# File: src/timber_framing_generator/framing_elements/framing_generator.py

class FramingGenerator:
    def __init__(self, wall_data, framing_config=None, panels_data=None):
        # ... existing init ...
        self.panels_data = panels_data  # List of panel dicts from panels_json

    def _generate_plates(self):
        # Build panel_boundaries from self.panels_data if available
        panel_boundaries = None
        if self.panels_data:
            panel_boundaries = [
                {"u_start": p["u_start"], "u_end": p["u_end"], "panel_id": p["id"]}
                for p in self.panels_data
            ]

        self.framing_elements["bottom_plates"] = create_plates(
            wall_data=self.wall_data,
            plate_type="bottom_plate",
            # ... existing params ...
            panel_boundaries=panel_boundaries,  # NEW
        )
        # Same for top plates

    def generate_framing(self):
        # ... existing generation ...
        # After all elements are generated, assign panel_ids
        if self.panels_data:
            self._assign_panel_ids_to_elements()

    def _assign_panel_ids_to_elements(self):
        """Tag all framing elements with their panel_id."""
        # For plates: already tagged during creation
        # For studs, king studs, trimmers, etc.: assign by U-coordinate
        ...
```

---

## Tasks (Execution Order)

### Task 1: Add `panel_id` to FramingElementData
```yaml
action: MODIFY
file: src/timber_framing_generator/core/json_schemas.py
find: "cell_id: Optional[str] = None"
add_after: "panel_id: Optional[str] = None  # Links element to panel for Revit Assembly"
preserve: All existing fields, serialization/deserialization functions
also_update:
  - deserialize_framing_results() to handle panel_id
```

### Task 2: Add panel boundary splitting to plates.py
```yaml
action: MODIFY
file: src/timber_framing_generator/framing_elements/plates.py
add:
  - _split_reference_line_at_panel_boundaries() function
  - panel_boundaries parameter to create_plates()
  - Composition logic: panel splits first, then door splits within each panel segment
  - panel_id attribute on resulting PlateGeometry objects
preserve:
  - Existing door-splitting logic (_split_reference_line_at_doors)
  - Existing non-panelized behavior (panel_boundaries=None -> no split)
  - All existing parameters and return types
```

### Task 3: Add panel_id to PlateGeometry
```yaml
action: MODIFY
file: src/timber_framing_generator/framing_elements/plate_geometry.py
add: panel_id attribute (Optional[str], default None) to PlateGeometry class
preserve: All existing attributes and methods
```

### Task 4: Create panel ID assignment utility
```yaml
action: MODIFY
file: src/timber_framing_generator/panels/panel_decomposer.py
add:
  - assign_panel_ids_to_elements() function
  - Assigns panel_id based on element u_coord falling within panel [u_start, u_end]
  - Handles boundary elements (center-based assignment)
preserve: All existing functions
```

### Task 5: Integrate into FramingGenerator
```yaml
action: MODIFY
file: src/timber_framing_generator/framing_elements/framing_generator.py
add:
  - panels_data parameter to __init__()
  - Pass panel_boundaries to create_plates() calls in _generate_plates()
  - _assign_panel_ids_to_elements() method called after all elements are generated
  - Panel ID assignment for all element types (studs, king studs, trimmers, cripples, blocking)
preserve:
  - All existing generation logic
  - Non-panelized workflow (panels_data=None -> no changes)
  - Generation order and dependency tracking
```

### Task 6: Update GHPython components
```yaml
action: MODIFY
file: scripts/gh_framing_generator.py
add:
  - Optional panels_json input parameter
  - Parse panels_json and pass to FramingGenerator
  - Include panel_id in framing_json output
preserve:
  - All existing inputs/outputs
  - Backward compatibility (panels_json is optional)
```

### Task 7: Write unit tests
```yaml
action: CREATE
file: tests/panels/test_panel_plate_splitting.py
tests:
  - test_no_panels_produces_full_length_plates: Non-panelized walls unchanged
  - test_two_panels_produces_two_plates: Simple split into two
  - test_four_panels_produces_four_plates: Multiple panels
  - test_panel_split_with_door_opening: Door split composes with panel split
  - test_double_top_plate_split: Both layers split at same boundaries
  - test_panel_id_on_plates: Each plate segment has correct panel_id

action: CREATE
file: tests/panels/test_panel_id_assignment.py
tests:
  - test_assign_stud_to_correct_panel: Stud U-coord within panel range
  - test_boundary_element_assigned_to_left_panel: Element at boundary goes left
  - test_all_element_types_get_panel_id: Studs, king studs, trimmers, cripples, blocking
  - test_no_panels_leaves_panel_id_none: Non-panelized elements have null panel_id
  - test_panel_id_in_framing_json: Serialization includes panel_id
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
python -m py_compile src/timber_framing_generator/core/json_schemas.py
python -m py_compile src/timber_framing_generator/framing_elements/plates.py
python -m py_compile src/timber_framing_generator/panels/panel_decomposer.py
ruff check src/timber_framing_generator/
```

### Level 2: Unit Tests
```bash
pytest tests/panels/test_panel_plate_splitting.py -v
pytest tests/panels/test_panel_id_assignment.py -v
pytest tests/ -v  # Full test suite, ensure no regressions
```

### Level 3: Integration Test (Grasshopper)
```
1. Open Rhino with Grasshopper
2. Load test GH definition with wall analyzer + panel decomposer + framing generator
3. Select a long wall (>24 ft) that gets panelized into 2+ panels
4. Verify:
   a. Number of top plates = number of panels * layers
   b. Number of bottom plates = number of panels * layers (accounting for door splits)
   c. All plates terminate at panel boundaries
   d. framing_json contains panel_id on every element
   e. Elements can be grouped by panel_id into distinct sets
5. Select a short wall (<24 ft, single panel) and verify no splitting occurs
```

---

## Final Checklist

- [ ] All unit tests pass: `pytest tests/ -v`
- [ ] No linting errors: `ruff check src/timber_framing_generator/`
- [ ] Non-panelized workflow unchanged (backward compatible)
- [ ] panel_id serialized in framing_json
- [ ] Plate counts match panel counts (per layer)
- [ ] Door splits compose correctly with panel splits
- [ ] Boundary elements assigned to exactly one panel
- [ ] GHPython component accepts optional panels_json
- [ ] No breaking changes to existing component interfaces

---

## Anti-Patterns to Avoid

- Don't replace existing door-splitting logic -- compose with it
- Don't make panels_json a required input -- must remain optional
- Don't split plates by modifying PlateGeometry internals -- split the reference_line before construction
- Don't duplicate panel boundary detection -- reuse panel_decomposer output
- Don't hard-code panel counts -- derive from panels_json data
- Don't assign panel_id based on element index -- always use U-coordinate range matching

---

## Notes

### Composition Order for Bottom Plates
The bottom plate undergoes TWO types of splitting:
1. **Panel boundary splits**: At panel joint U-coordinates (new)
2. **Door opening splits**: At door opening U-ranges (existing)

These compose as: `wall_reference_line -> split_at_panels -> for_each_segment: split_at_doors -> final_segments`

This means a panel containing a door will have its bottom plate split into multiple segments (before door, after door), while its top plate remains a single piece within the panel.

### Downstream: Revit Assembly Creation
The `panel_id` field enables a downstream GHPython component to:
1. Group all framing elements by `panel_id`
2. Create a Revit Assembly for each group
3. Each assembly becomes a self-contained, schedulable, taggable unit in Revit

This PRP does NOT implement the Revit Assembly creation -- only the data preparation (panel_id tagging).
