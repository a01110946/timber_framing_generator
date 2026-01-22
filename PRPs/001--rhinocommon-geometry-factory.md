# PRP: RhinoCommon Geometry Factory (Stage 1)

> **Version:** 1.0
> **Created:** 2026-01-21
> **Status:** In Progress
> **Branch:** fix/geometry-conversion-bugs

---

## Goal
Complete and verify the RhinoCommon geometry factory that converts Rhino3dmIO geometry to RhinoCommon assembly types, enabling Grasshopper to accept framing geometry outputs without "Data conversion failed from Goo to Brep" errors.

## Why
- **Critical Bug**: Grasshopper rejects all framing geometry due to assembly mismatch
- **Root Cause**: `rhino3dm` Python package creates Rhino3dmIO types, but Grasshopper expects RhinoCommon types
- **Impact**: Without this fix, no framing elements are visible in Grasshopper outputs

## What
The `RhinoCommonFactory` class in `scripts/gh-main.py` uses CLR reflection to:
1. Find the RhinoCommon assembly via `System.AppDomain`
2. Create geometry types directly using `System.Activator.CreateInstance()`
3. Convert Rhino3dmIO geometry to RhinoCommon by extracting coordinates and recreating

### Success Criteria
- [ ] All framing outputs (studs, plates, headers, etc.) connect to Brep components without errors
- [ ] `test_clr_box` diagnostic output shows Assembly: `RhinoCommon` and IsValid: `True`
- [ ] Geometry appears in Rhino viewport when connected to Preview component
- [ ] No "Data conversion failed from Goo to Brep" errors in Grasshopper

---

## All Needed Context

### Documentation & References
```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-geometry-assembly-solution.md
    why: Full problem analysis and solution architecture

  - file: docs/ai/ai-architecture-document.md
    why: Overall system architecture

  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for wall-relative positioning

Feature-Specific:
  - file: scripts/gh-main.py
    why: Contains RhinoCommonFactory implementation (lines 134-523)

  - file: scripts/gh-main.py
    why: Contains convert_breps_for_output() (lines 809-890)

  - file: scripts/gh-main.py
    why: Contains diagnostic test section (lines 1486-1769)
```

### Current Implementation Status

**Already Implemented (in `scripts/gh-main.py`):**

| Component | Status | Lines |
|-----------|--------|-------|
| `RhinoCommonFactory` class | ✅ Complete | 134-523 |
| `create_point3d()` | ✅ Complete | 221-223 |
| `create_vector3d()` | ✅ Complete | 225-227 |
| `create_plane()` | ✅ Complete | 229-262 |
| `create_line()` | ✅ Complete | 264-282 |
| `create_bounding_box()` | ✅ Complete | 322-340 |
| `create_box()` | ✅ Complete | 342-344 |
| `create_box_brep_from_centerline()` | ✅ Complete | 400-488 |
| `convert_geometry_from_rhino3dm()` | ✅ Complete | 490-523 |
| `convert_breps_for_output()` | ✅ Complete | 809-890 |
| Diagnostic test section | ✅ Complete | 1486-1769 |
| Factory instantiation (`rc_factory`) | ✅ Complete | 526-530 |

### Known Gotchas & Library Quirks
```python
# CRITICAL: Assembly mismatch details
# - rhino3dm creates types from "Rhino3dmIO" assembly
# - Grasshopper expects types from "RhinoCommon" assembly
# - Type names are IDENTICAL but CLR treats them as different types
# - GH_Brep(rhino3dm_brep) fails with "value cannot be converted"

# CRITICAL: CLR reflection pattern
# - Use System.AppDomain.CurrentDomain.GetAssemblies() to find RhinoCommon
# - Use assembly.GetType("Rhino.Geometry.Point3d") to get types
# - Use System.Activator.CreateInstance(type, Array[object]([args])) to instantiate

# CRITICAL: Coordinate extraction
# - Extract floats from Rhino3dmIO geometry: float(point.X)
# - Pass floats to RhinoCommon constructors
# - This "launders" coordinates through the assembly boundary

# LIMITATION: Stage 1 uses bounding box approximation
# - Exact geometry shape is lost (studs become axis-aligned boxes)
# - Acceptable for initial verification
# - Stage 2 will improve fidelity using centerline+profile recreation
```

---

## Implementation Blueprint

### Tasks (in execution order)

```yaml
Task 1: Verify Factory Initialization
  - CHECK: scripts/gh-main.py lines 526-530
  - VERIFY: rc_factory is created without errors
  - VERIFY: print statement shows "RhinoCommonFactory initialized successfully"

Task 2: Test in Grasshopper - Basic Verification
  - MANUAL: Open Rhino with Grasshopper via Rhino.Inside.Revit
  - MANUAL: Load the timber framing GH definition
  - MANUAL: Select a test wall in Revit
  - MANUAL: Toggle 'run' and 'reload' inputs
  - CHECK: Console output for "RhinoCommonFactory: Found RhinoCommon assembly"
  - CHECK: No Python errors in component output

Task 3: Verify Diagnostic Test Section
  - CHECK: test_clr_box output should show:
    - Type: Rhino.Geometry.Brep
    - Assembly: RhinoCommon
    - IsValid: True
  - MANUAL: Connect test_clr_box to a Brep parameter component
  - VERIFY: No "Data conversion failed from Goo to Brep" error

Task 4: Verify Framing Outputs
  - MANUAL: Connect each output (studs, plates, headers, etc.) to Brep components
  - VERIFY: All outputs connect without conversion errors
  - MANUAL: Connect to Preview component to visualize
  - VERIFY: Geometry appears in Rhino viewport

Task 5: Check Conversion Statistics
  - CHECK: Console output shows conversion summary
  - VERIFY: "factory_successes" count matches expected geometry count
  - VERIFY: "conversion_errors" is 0
```

### Integration Points
```yaml
FACTORY INSTANTIATION:
  - file: scripts/gh-main.py
  - lines: 526-530
  - pattern: "rc_factory = RhinoCommonFactory()"

CONVERSION USAGE:
  - file: scripts/gh-main.py
  - lines: 854-861
  - pattern: "rc_factory.convert_geometry_from_rhino3dm(item)"

DIAGNOSTIC TEST:
  - file: scripts/gh-main.py
  - lines: 1688-1755
  - pattern: "Method 9 - CLR Box creation test"
```

---

## Validation Loop

### Level 1: Syntax Check (Already Passing)
```bash
# The factory is already implemented - just verify no syntax errors
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
python -c "import ast; ast.parse(open('scripts/gh-main.py').read())"
```

### Level 2: Grasshopper Integration Test
```
# Manual test in Grasshopper:

1. Start Revit 2024+
2. Launch Rhino.Inside.Revit
3. Open Grasshopper
4. Load the timber framing definition
5. Select a test wall in Revit viewport
6. Set component inputs:
   - walls: [selected wall]
   - run: True
   - reload: True

7. Check Python output panel for:
   ✓ "RhinoCommonFactory: Found RhinoCommon assembly"
   ✓ "RhinoCommonFactory initialized successfully"
   ✓ No error messages

8. Check diagnostic outputs:
   ✓ test_clr_box shows valid Brep
   ✓ test_info shows "CLR Box: SUCCESS - Assembly: RhinoCommon"

9. Check framing outputs:
   ✓ Connect studs to Brep parameter → No error
   ✓ Connect plates to Brep parameter → No error
   ✓ Connect headers to Brep parameter → No error

10. Visual verification:
    ✓ Connect any output to Preview component
    ✓ Geometry visible in Rhino viewport
    ✓ Shapes are approximately correct (box approximations)
```

### Level 3: Output Completeness
```
# Verify all framing categories have geometry:

Expected outputs (check count > 0 for test wall with opening):
- bottom_plates: ≥ 1
- top_plates: ≥ 2 (double top plate)
- studs: ≥ 3
- king_studs: ≥ 2 (for opening)
- headers: ≥ 1 (for opening)
- trimmers: ≥ 2 (for opening)

Optional (may be 0 depending on wall):
- sills, sill_cripples, header_cripples, row_blocking
```

---

## Final Checklist

- [ ] RhinoCommonFactory initializes without errors
- [ ] test_clr_box diagnostic shows Assembly: RhinoCommon
- [ ] No "Data conversion failed from Goo to Brep" errors
- [ ] Framing geometry visible in Rhino viewport
- [ ] All outputs have expected element counts
- [ ] Conversion summary shows 0 errors

---

## Anti-Patterns to Avoid

- ❌ Don't try to cast Rhino3dmIO types directly to GH_Brep
- ❌ Don't use `isinstance()` checks across assembly boundaries
- ❌ Don't assume type names mean same assembly
- ❌ Don't skip the coordinate extraction step (must pass through floats)
- ❌ Don't cache geometry objects across runs (assembly may change)

---

## Stage 2 Preview (After Stage 1 Verification)

Once Stage 1 is verified working, Stage 2 will improve geometry fidelity:

1. Extract centerline + profile data from framing elements (not just bbox)
2. Use `create_extrusion_brep()` to recreate proper shapes
3. Add `extract_element_data()` helper to serialization.py

This will produce accurate framing geometry instead of bounding box approximations.

---

## Notes

- Factory was implemented in previous session
- This PRP focuses on verification and testing
- Stage 1 uses bounding box approximation (acceptable for initial verification)
- Full geometry fidelity will be addressed in Stage 2 PRP
