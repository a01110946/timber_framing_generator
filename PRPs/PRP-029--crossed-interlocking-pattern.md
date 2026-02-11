# PRP-029: Crossed/Interlocking Junction Pattern

## Status: In Progress
## Date: 2026-02-09

## Problem Statement

The current "primary dominates all faces" butt joint pattern produces visually
incorrect junction geometry in Grasshopper. Despite numerically correct
adjustment amounts, the sheathing layers show gaps on one face and overlaps
on the other at L-corners.

### Root Cause

The current logic assigns EXTEND/TRIM directions based on a "primary dominates
all faces" model where the primary wall wraps ALL faces of the corner:

**Current pattern (WRONG):**

```
Exterior corner:
  Primary:   ext EXTEND, core EXTEND, int EXTEND  (wraps everything)
  Secondary: ext TRIM,   core TRIM,   int TRIM    (fully subordinate)

Interior corner:
  Primary:   ext EXTEND, core EXTEND, int TRIM
  Secondary: ext TRIM,   core TRIM,   int TRIM    (fully subordinate)
```

This creates a problem because at any L-corner, the primary wall's layers
extend on BOTH faces of the corner. On the exterior face, this is correct —
the primary wall should wrap past the secondary wall's end. But on the
interior face, this creates a gap where the secondary wall's interior
layers have been trimmed back, and the primary wall's interior layers
extend into empty space that should be covered by the secondary wall.

### Visual Explanation

Consider two walls at an exterior L-corner, viewed from above:

```
PRIMARY DOMINATES ALL (wrong):
                                    Primary wraps both faces
                                    ┌──────────────────────┐
                    Primary ext  →  │ ==================== │ ← Primary ext extends
                    Primary core →  │ ==================== │ ← Primary core extends
                    Primary int  →  │ ==================== │ ← Primary int extends (WRONG!)
                                    └──────────────────────┘
                                                ▲
                                    ┌───────────┼──────────┐
           Secondary int  → TRIMS   │  ←←←←←←← │          │
           Secondary core → TRIMS   │  ←←←←←←← │          │
           Secondary ext  → TRIMS   │  ←←←←←←← │          │
                                    └───────────┴──────────┘

Result: Primary int extends into the room → gap visible from inside
        Secondary int trims back → gap visible from inside
```

### Correct Pattern: Crossed/Interlocking

In real construction (and in Revit's wall join behavior), each wall
dominates its OWN exterior face at L-corners. The walls interlock:

```
CROSSED/INTERLOCKING (correct):
                                    Primary covers exterior face only
                                    ┌──────────────────────┐
                    Primary ext  →  │ ==================== │ ← EXTENDS (covers ext face)
                    Primary core →  │ ==================== │ ← EXTENDS
                    Primary int  →  │ ============ │       │ ← TRIMS (stops at secondary)
                                    └──────────────┼───────┘
                                                   │
                                    ┌──────────────┼───────┐
           Secondary int  → EXTENDS │  →→→→→→→→→→→ │       │ ← EXTENDS (covers int face)
           Secondary core → TRIMS   │  ←←←←←←← │          │
           Secondary ext  → TRIMS   │  ←←←←←←← │          │
                                    └───────────┴──────────┘

Result: Primary ext covers exterior face continuously
        Secondary int covers interior face continuously
        No gaps on either face
```

### Key Insight

The crossed pattern creates two continuous coverage lines:
1. **Exterior face**: Primary exterior layers extend past, creating a
   continuous exterior surface at the corner
2. **Interior face**: Secondary interior layers extend past, creating a
   continuous interior surface at the corner

This is identical to how Revit resolves wall joins — each wall "wins"
on its own exterior face.

## New Rules

The direction pattern is the **same for ALL L-corner types** (both
exterior and interior corners):

| Wall | Layer Side | Direction | Reason |
|------|-----------|-----------|--------|
| Primary | exterior | EXTEND | Covers exterior face continuously |
| Primary | core | EXTEND | Structural continuity |
| Primary | interior | **TRIM** | Stops at secondary wall body |
| Secondary | exterior | TRIM | Stops at primary wall body |
| Secondary | core | TRIM | Subordinate at junction |
| Secondary | interior | **EXTEND** | Covers interior face continuously |

### Amounts (unchanged)

The adjustment amounts remain the same — only the directions change:

- **Primary ext[i]**: `half_sec_core + cumulative(sec_ext[0..i])` → EXTEND
- **Primary core**: `half_sec_core` → EXTEND
- **Primary int[i]**: `half_sec_core + cumulative(sec_int[0..i])` → **TRIM**
- **Secondary ext[i]**: `half_pri_core + cumulative(pri_ext[0..i])` → TRIM
- **Secondary core**: `half_pri_core` → TRIM
- **Secondary int[i]**: `half_pri_core + cumulative(pri_int[0..i])` → **EXTEND**

### Corner Type Detection

`_is_exterior_corner()` is preserved for diagnostic logging but **no
longer affects** the EXTEND/TRIM direction assignment. The junction
report will still label corners as EXTERIOR or INTERIOR for debugging.

### Secondary Interior Opposing Layers

Previously, the opposing layers used for secondary interior cumulative
amounts were conditional on corner type:
```python
# OLD (wrong): conditional opposing
sec_int_opposing = pri_int if exterior_corner else pri_ext
```

With the crossed pattern, secondary interior always extends past the
primary wall's interior face, so it always uses `pri_int`:
```python
# NEW (correct): always pri_int
sec_int_opposing = pri_int
```

## Implementation Changes

### junction_resolver.py

1. `pri_int_type = AdjustmentType.TRIM` (unconditional)
2. Secondary interior: `AdjustmentType.EXTEND` (unconditional)
3. `sec_int_opposing = pri_int` (unconditional)
4. Fallback path: same changes for aggregate adjustments
5. Version bump to `"2.3-crossed-pattern"`

### test_junction_resolver.py

1. Update `TestButtJoinDirections`: primary int → TRIM at exterior corners,
   secondary int → EXTEND at all corners
2. Update `TestPerLayerCumulativeAdjustments`: primary int → TRIM,
   secondary int → EXTEND
3. Update `TestRecomputeAdjustments`: secondary int → EXTEND
4. Update `test_directions_with_four_room_layout`: primary int TRIM,
   secondary int EXTEND

### scripts/gh_multi_layer_sheathing.py

1. Version bump to v2.6

## Verification

1. `pytest tests/wall_junctions/ -v` — all tests pass
2. `pytest tests/sheathing/ -v` — no regressions
3. User re-pastes updated MLSheath component into GH
4. Visual check: exterior face continuous (primary ext), interior face
   continuous (secondary int), no gaps at corners

## Previous Attempts (for reference)

| Version | Pattern | Result |
|---------|---------|--------|
| v2.1-corner-fix | Primary dominates all + corner detection | Gaps on interior face |
| v2.2-cumulative-fix | Same + cumulative timing fix | Same gaps (amounts correct, pattern wrong) |
| **v2.3-crossed-pattern** | **Crossed/interlocking** | **Expected: correct** |
