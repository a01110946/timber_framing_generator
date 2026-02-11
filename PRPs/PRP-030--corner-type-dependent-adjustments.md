# PRP-030: Corner-Type-Dependent Junction Adjustments

## Status: Implemented
## Date: 2026-02-09

## Problem Statement

The v2.3 "crossed/interlocking" pattern (PRP-029) applies identical
EXTEND/TRIM directions to ALL L-corner types. In reality, the correct
directions depend on whether the corner is an **exterior** or **interior**
corner. Additionally, the cumulative amount calculation uses two patterns
("full" and "shifted") that must be assigned differently based on corner
type, wall role, and layer side.

### Root Cause

The current code unconditionally sets:
```python
pri_int_type = AdjustmentType.TRIM
sec_ext_type = AdjustmentType.TRIM
sec_int_type = AdjustmentType.EXTEND
```

And uses the same "add-then-compute" (full) cumulative pattern for all
layer loops. This produces incorrect geometry at both exterior and interior
corners.

### Correct Rules

The direction pattern depends on corner type:

**EXTERIOR corner** (dot < 0): Both walls' exterior layers EXTEND to
create a continuous exterior surface. Both walls' interior layers TRIM.

**INTERIOR corner** (dot >= 0): Both walls' exterior layers TRIM. Both
walls' interior layers EXTEND to create a continuous interior surface.

Primary core always EXTENDS, secondary core always TRIMS (unchanged).

### Direction Table

| Corner   | Wall      | Side     | Direction |
|----------|-----------|----------|-----------|
| EXTERIOR | Primary   | ext      | EXTEND    |
| EXTERIOR | Primary   | core     | EXTEND    |
| EXTERIOR | Primary   | int      | **TRIM**  |
| EXTERIOR | Secondary | ext      | **EXTEND**|
| EXTERIOR | Secondary | core     | TRIM      |
| EXTERIOR | Secondary | int      | **TRIM**  |
| INTERIOR | Primary   | ext      | **TRIM**  |
| INTERIOR | Primary   | core     | EXTEND    |
| INTERIOR | Primary   | int      | **EXTEND**|
| INTERIOR | Secondary | ext      | **TRIM**  |
| INTERIOR | Secondary | core     | TRIM      |
| INTERIOR | Secondary | int      | **EXTEND**|

### Cumulative Pattern Table

Two patterns for per-layer cumulative amounts:
- **Full** (add-then-compute): `cumul += opp[i]; amount = half_core + cumul`
  Layer reaches to the OUTER face of the opposing layer at index i.
- **Shifted** (compute-then-add): `amount = half_core + cumul; cumul += opp[i]`
  Layer reaches to the INNER face of the opposing layer at index i.

| Corner   | Wall      | Side | Cumulative |
|----------|-----------|------|------------|
| EXTERIOR | Primary   | ext  | full       |
| EXTERIOR | Primary   | int  | shifted    |
| EXTERIOR | Secondary | ext  | shifted    |
| EXTERIOR | Secondary | int  | full       |
| INTERIOR | Primary   | ext  | shifted    |
| INTERIOR | Primary   | int  | full       |
| INTERIOR | Secondary | ext  | full       |
| INTERIOR | Secondary | int  | full       |

The cumulative pattern only applies to the per-layer path (when individual
assembly layers are available). The fallback (aggregate) path always uses
total opposing-side thickness (equivalent to outermost "full" amount).

### Fixture Corner Classification

Important: `_is_exterior_corner()` classifies based on
`dot(primary.z_axis, secondary_outward_direction)`:

| Fixture                   | dot  | Classification |
|---------------------------|------|----------------|
| `l_corner_walls`          | -1   | **EXTERIOR**   |
| `l_corner_interior_walls` | +1   | **INTERIOR**   |
| `four_room_layout`        | -1   | **EXTERIOR** (all 4 corners) |

The fixture names match their corner types correctly:
`_outward_direction_at_junction` returns the wall direction as-is for
"start" endpoints (pointing AWAY from junction).

## Implementation Changes

### junction_resolver.py

1. Replace unconditional crossed-pattern direction assignment with
   corner-type-dependent lookup:

```python
if exterior_corner:
    pri_ext_dir, pri_ext_cumul = AdjustmentType.EXTEND, "full"
    pri_int_dir, pri_int_cumul = AdjustmentType.TRIM, "shifted"
    sec_ext_dir, sec_ext_cumul = AdjustmentType.EXTEND, "shifted"
    sec_int_dir, sec_int_cumul = AdjustmentType.TRIM, "full"
else:  # interior
    pri_ext_dir, pri_ext_cumul = AdjustmentType.TRIM, "shifted"
    pri_int_dir, pri_int_cumul = AdjustmentType.EXTEND, "full"
    sec_ext_dir, sec_ext_cumul = AdjustmentType.TRIM, "full"
    sec_int_dir, sec_int_cumul = AdjustmentType.EXTEND, "full"
```

2. Update each per-layer loop to respect the cumulative pattern
   (full = add-then-compute, shifted = compute-then-add).

3. Update fallback (aggregate) path: only directions change based
   on corner type; amounts unchanged (half_core + side_total).

4. Version bump to `"2.4-corner-dependent"`.

### test_junction_resolver.py

Update all direction and amount tests to match new rules:

**`TestButtJoinDirections`** (uses `l_corner_walls` = INTERIOR):
- `test_primary_exterior_extends` → rename, expect **TRIM**
- `test_primary_interior_trims_at_exterior_corner` → rename, expect **EXTEND**
- `test_primary_core_extends` → unchanged
- `test_secondary_exterior_trims_at_exterior_corner` → rename, expect **TRIM** (same)
- `test_secondary_interior_extends` → expect **EXTEND** (same)
- `test_secondary_core_trims` → unchanged

**`TestButtJoinDirections`** (uses `l_corner_interior_walls` = EXTERIOR):
- `test_primary_interior_trims_at_interior_corner` → rename, expect **TRIM** (same)
- `test_secondary_exterior_trims_at_interior_corner` → rename, expect **EXTEND**
- `test_interior_corner_directions` → update pri_ext=EXTEND, sec_ext=EXTEND, sec_int=TRIM

**`TestButtJoinDirections`** (uses `four_room_layout` = all INTERIOR):
- `test_directions_with_four_room_layout` → update pri_ext=TRIM, pri_int=EXTEND

**`TestPerLayerCumulativeAdjustments`** (fixtures = INTERIOR corner):
- `test_primary_ext_cumulative_amounts` → direction TRIM, shifted cumulative
- `test_primary_int_cumulative_amounts_exterior_corner` → rename, direction EXTEND, full cumulative
- `test_secondary_directions_exterior_corner` → rename, sec_ext still TRIM, sec_int still EXTEND
- `test_secondary_ext_cumulative_amounts` → amounts use "full" cumul (same)
- `test_secondary_int_cumulative_amounts` → amounts use "full" cumul (same)

**`TestRecomputeAdjustments`**:
- `test_recompute_secondary_crossed_directions` → update for corner type

### junction-adjustment-math.md

Update the formula documentation to reflect corner-type-dependent rules.

## Verification

1. `pytest tests/wall_junctions/ -v` — all tests pass
2. `pytest tests/sheathing/ -v` — no regressions
3. User re-pastes updated MLSheath component into GH
4. Visual check: exterior corners have continuous exterior surface,
   interior corners have continuous interior surface

## Previous Attempts

| Version | Pattern | Result |
|---------|---------|--------|
| v2.1-corner-fix | Primary dominates all + corner detection | Gaps on interior face |
| v2.2-cumulative-fix | Same + cumulative timing fix | Same gaps |
| v2.3-crossed-pattern | Crossed/interlocking (same for all corners) | Wrong directions |
| **v2.4-corner-dependent** | **Corner-type-dependent directions + cumulative** | **Expected: correct** |
