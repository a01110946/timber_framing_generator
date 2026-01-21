# Geometry Assembly Mismatch Solution

## Problem Summary

The timber framing generator creates geometry using the `rhino3dm` Python package, which internally uses the **Rhino3dmIO** .NET assembly. However, when running in Grasshopper, the environment expects geometry from the **RhinoCommon** assembly. Despite having identical type names (`Rhino.Geometry.Brep`, `Rhino.Geometry.Point3d`, etc.), these assemblies are incompatible at the CLR/.NET level.

**Result**: Geometry objects appear valid (correct type names) but Grasshopper rejects them with "Data conversion failed from Goo to Brep" because the assembly doesn't match.

---

## Research Findings

### 1. Where Geometry is Created

All framing elements are created through a common pattern:
- **Input**: Numerical data (UV coordinates, dimensions, base plane)
- **Process**: Calculate centerlines and profiles from coordinates
- **Output**: `rg.Brep` via extrusion or sweep operations

**Key files**:
- `framing_elements/plate_geometry.py` - Plate extrusions
- `framing_elements/studs.py` - Stud sweeps
- `framing_elements/headers.py`, `king_studs.py`, etc.
- `utils/safe_rhino.py` - Safe geometry creation helpers

### 2. Environment Detection

The codebase already detects environment:
```python
# framing_generator.py lines 32-46
is_rhino_environment = 'rhinoscriptsyntax' in sys.modules or 'scriptcontext' in sys.modules
if not is_rhino_environment:
    import rhinoinside
    rhinoinside.load()
```

### 3. Existing Data Patterns

The codebase already has numerical geometry representation:
- **Cell system**: UV coordinates (`u_start`, `u_end`, `v_start`, `v_end`)
- **API models**: `Point3D(x, y, z)`, `Plane(origin, x_axis, y_axis, z_axis)`
- **Framing elements**: Created from centerlines (start/end points) + dimensions (width/depth)

---

## Environment Comparison

| Aspect | API Environment | Grasshopper Environment |
|--------|-----------------|------------------------|
| **Rhino Assembly** | rhino3dm (Rhino3dmIO) or rhinoinside | RhinoCommon (native) |
| **Input** | JSON via HTTP | Revit walls via RhinoInside.Revit |
| **Geometry Needed** | Optional (can return JSON) | Required (Brep outputs) |
| **Serialization** | JSON/Pydantic | Native GH datatree |
| **Module Conflicts** | None (isolated process) | Yes (sys.path conflicts) |

---

## Solution: Environment-Aware Geometry Factory

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Core Framing Logic                        │
│  (Environment-agnostic, works with numerical data only)     │
│                                                              │
│  Input: wall_data dict (coordinates, dimensions)            │
│  Output: FramingElementData (numerical representation)      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Geometry Factory Interface                      │
│                                                              │
│  create_brep_from_centerline(start, end, width, depth)      │
│  create_point3d(x, y, z)                                     │
│  create_plane(origin, x_axis, y_axis)                        │
└─────────────────────────────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
┌─────────────────────────┐   ┌─────────────────────────────┐
│   API/rhino3dm Factory  │   │  Grasshopper/RhinoCommon    │
│                         │   │        Factory               │
│  Uses: rhino3dm         │   │  Uses: CLR reflection       │
│  Assembly: Rhino3dmIO   │   │  Assembly: RhinoCommon      │
│  For: Standalone/API    │   │  For: GH Python component   │
└─────────────────────────┘   └─────────────────────────────┘
```

### What Stays the Same (Both Environments)

1. **Core framing generation logic** in `framing_generator.py`
2. **Cell decomposition** with UV coordinates
3. **Wall data extraction** patterns
4. **Framing element calculations** (positions, dimensions)

### What Differs (Environment-Specific)

| Step | API Environment | Grasshopper Environment |
|------|-----------------|------------------------|
| **Import Rhino** | `import rhino3dm` or `rhinoinside.load()` | CLR + RhinoCommon reference |
| **Create Point3d** | `rhino3dm.Point3d(x, y, z)` | `Activator.CreateInstance(RC_Point3d, [x, y, z])` |
| **Create Brep** | `rhino3dm` extrusion methods | RhinoCommon via CLR reflection |
| **Output Format** | JSON serializable or Brep | Native RhinoCommon Brep |

---

## Implementation Plan: Hybrid Approach

**Strategy**: Start with minimal changes to prove the solution works, then refactor incrementally.

---

### Stage 1: Minimal Working Solution (Do First)

**Goal**: Get Grasshopper outputs working with RhinoCommon geometry

#### Step 1.1: Complete RhinoCommonFactory in gh-main.py

**File**: `scripts/gh-main.py`

The factory is partially implemented. Complete these methods:

```python
class RhinoCommonFactory:
    # Already have: create_point3d, create_vector3d, create_box_brep_from_centerline

    # ADD: Method to convert Rhino3dmIO geometry to RhinoCommon
    def convert_brep(self, source_brep) -> Brep:
        """Convert any Brep to RhinoCommon by extracting bbox and recreating."""
        bbox = source_brep.GetBoundingBox(True)
        # Extract coordinates as floats
        min_pt = (float(bbox.Min.X), float(bbox.Min.Y), float(bbox.Min.Z))
        max_pt = (float(bbox.Max.X), float(bbox.Max.Y), float(bbox.Max.Z))
        # Create RhinoCommon geometry
        rc_bbox = self.create_bounding_box(min_pt, max_pt)
        rc_box = self.create_box(rc_bbox)
        return rc_box.ToBrep()
```

#### Step 1.2: Update convert_breps_for_output()

**File**: `scripts/gh-main.py`

Modify to use factory as primary conversion method:

```python
def convert_breps_for_output(brep_list, debug=False):
    # Check assembly of each item
    # If Rhino3dmIO → use rc_factory.convert_brep()
    # If RhinoCommon → pass through directly
```

#### Step 1.3: Test in Grasshopper

- Load GH definition
- Run with test wall
- Verify outputs connect to Brep component without errors
- Check geometry is correct (bounding box approximation)

---

### Stage 2: Improve Geometry Fidelity (After Stage 1 Works)

**Goal**: Preserve actual geometry shape, not just bounding box

#### Step 2.1: Extract Centerline Data from Framing Elements

**File**: `src/timber_framing_generator/utils/serialization.py` (ADD methods)

```python
def extract_element_data(element) -> Dict:
    """Extract numerical data from a framing element."""
    if hasattr(element, 'centerline') and hasattr(element, 'profile'):
        return {
            'start': (element.centerline.PointAtStart.X, ...),
            'end': (element.centerline.PointAtEnd.X, ...),
            'width': element.profile.Width,
            'depth': element.profile.Height,
        }
    # Fallback to bounding box
    bbox = element.GetBoundingBox(True)
    return {'bbox_min': ..., 'bbox_max': ...}
```

#### Step 2.2: Enhance RhinoCommonFactory

**File**: `scripts/gh-main.py`

```python
def create_brep_from_centerline(self, start, end, width, depth):
    """Create proper extrusion from centerline and profile dimensions."""
    # Create profile plane at start point
    # Create rectangle profile
    # Extrude along direction to end point
    # Return proper RhinoCommon Brep
```

#### Step 2.3: Update Conversion Pipeline

Use `extract_element_data()` to get numerical data, then `create_brep_from_centerline()` to recreate geometry with proper shape.

---

### Stage 3: Full Architecture Refactor (Optional, Future)

**Goal**: Clean separation of data and geometry throughout codebase

Only pursue if Stage 2 proves insufficient or if we need better testability/maintainability.

1. **NEW**: `framing_element_data.py` - Pure numerical data classes
2. **NEW**: `geometry_factory.py` - Abstract factory + implementations
3. **MODIFY**: Framing modules to return data instead of Breps
4. **MODIFY**: gh-main.py to use factory at final output stage

---

## Critical Files to Modify (Hybrid Approach)

### Stage 1 (Minimal - Do First)
| File | Action | Purpose |
|------|--------|---------|
| `scripts/gh-main.py` | COMPLETE | Finish RhinoCommonFactory, fix convert_breps_for_output() |

### Stage 2 (Improved Fidelity - After Stage 1 Works)
| File | Action | Purpose |
|------|--------|---------|
| `scripts/gh-main.py` | ENHANCE | Add `create_brep_from_centerline()` method |
| `src/.../utils/serialization.py` | ADD | Add `extract_element_data()` helper |

### Stage 3 (Full Refactor - Optional Future)
| File | Action | Purpose |
|------|--------|---------|
| `src/.../framing_element_data.py` | NEW | Pure numerical data classes |
| `src/.../geometry_factory.py` | NEW | Abstract factory pattern |
| `src/.../framing_generator.py` | MODIFY | Return data instead of Breps |

---

## Verification Plan

### Stage 1 Verification
1. **Assembly Check**: In gh-main.py diagnostic section, verify `test_clr_box` output shows:
   - Assembly: `RhinoCommon` (not Rhino3dmIO)
   - IsValid: `True`

2. **Grasshopper Output Test**:
   - Connect `studs` output to a Brep parameter component
   - Expected: No "Data conversion failed from Goo to Brep" error
   - Connect to Preview component to visualize

3. **Quick Visual Check**:
   - Geometry appears in Rhino viewport
   - Shapes are box-like (bounding box approximation is acceptable for Stage 1)

### Stage 2 Verification
1. **Geometry Fidelity Test**:
   - Compare output geometry to expected framing dimensions
   - Verify studs have correct width/depth (not stretched bbox)
   - Headers should be horizontal, studs should be vertical

2. **API Regression Test**:
   ```bash
   pytest tests/api/ -v
   ```
   - Ensure API still works (uses rhino3dm, unaffected by changes)

### Stage 3 Verification (if pursued)
1. **Unit Tests**: Test data class creation
2. **Integration Tests**: Full pipeline with both API and GH outputs

---

## Alternative Approaches Considered

### Option A: Convert at Output (Current partial implementation)
- Convert Rhino3dmIO Breps to RhinoCommon at the final step
- **Limitation**: Loses geometry fidelity (bounding box only)

### Option B: Environment-aware imports in modules
- Patch sys.modules before importing framing modules
- **Limitation**: Complex, fragile, affects global state

### Option C: Remove rhino3dm entirely from GH environment
- Modify sys.path to exclude rhino3dm
- **Limitation**: May break other dependencies, not reliable

**Chosen: Environment-Aware Factory Pattern** - Clean separation, full geometry fidelity, testable.
