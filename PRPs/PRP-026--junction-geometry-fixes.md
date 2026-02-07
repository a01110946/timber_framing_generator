# PRP-026: Junction Geometry Fixes — Flip Handling, Extension Offset, Thickness Scaling

## Problem Statement

Three bugs prevent correct sheathing panel placement at wall junctions:

1. **Bug 1 — `is_flipped` not handled**: When a Revit wall is flipped (`is_flipped=true`), the wall's `z_axis` points toward the building interior instead of exterior. No component in the pipeline accounts for this, causing W-offsets to place exterior layers on the interior side, junction adjustments to extend/trim the wrong side, and geometry to extrude in the wrong direction.

2. **Bug 2 — Extension offset from centerline**: `_calculate_butt_adjustments()` measures extensions from the secondary wall's centerline (`half_sec_core + cumulative`). But the primary wall's `u=0` is at the secondary wall's **face** (Revit join behavior), not its centerline. Extensions fall short by ~`half_sec_wall_thickness` (~2" for a 4" wall, ~3" for a 6" wall).

3. **Bug 3 — Catalog vs Revit thickness mismatch**: The assembly catalog's total thickness (e.g., 2x6_exterior = 0.594 ft) differs from the Revit wall_thickness (0.500 ft). Layer thicknesses used in calculations don't match the physical wall geometry.

## Analysis Reference

See `SHEATHING_JUNCTION_PIPELINE_ANALYSIS.md` in the repo root for the full pipeline trace, data flow diagrams, and per-step debugging checklist.

## Solution Design

### Fix 1: Normalize z_axis for flipped walls

**Approach**: At the entry point of each GH component, negate `z_axis` in the wall data when `is_flipped=true`. This makes `+z_axis = physical exterior` consistently, so all downstream code works without individual changes.

**Implementation**:

Create a shared helper `_normalize_flip(wall_data)` that:
```python
def _normalize_flip(wall_data):
    """Negate z_axis for flipped walls so +z = physical exterior."""
    if not wall_data.get("is_flipped", False):
        return wall_data
    wall = dict(wall_data)
    bp = dict(wall.get("base_plane", {}))
    z = bp.get("z_axis", {})
    bp["z_axis"] = {"x": -z.get("x", 0), "y": -z.get("y", 0), "z": -z.get("z", 0)}
    wall["base_plane"] = bp
    return wall
```

Apply in:
- `gh_junction_analyzer.py`: Before `analyze_junctions()`, normalize all wall dicts
- `gh_multi_layer_sheathing.py`: Before Phase 2 recompute and before `process_walls()`
- `gh_sheathing_geometry_converter.py`: Before `create_sheathing_breps()`

Remove the ineffective `faces` swap in `gh_multi_layer_sheathing.py:582-589`.

**Tests**:
- `TestFlipNormalization`: Verify z_axis negated when is_flipped=true, unchanged when false
- `TestFlippedWallWOffsets`: Verify exterior layers at positive W after normalization
- `TestFlippedWallAdjustments`: Verify exterior extends and interior trims correctly for a flipped primary wall

### Fix 2: Account for endpoint-to-centerline offset in extensions

**Approach**: Add `half_sec_wall_thickness` (from Revit `wall_thickness`, not catalog) to all extension amounts. This compensates for the fact that the primary wall's endpoint is at the secondary wall's face.

For trims on the primary wall's interior side, subtract the offset instead (the secondary wall occupies space on that side too, but the trim amount was also measured from centerline).

**Implementation** in `_calculate_butt_adjustments()`:

```python
# Compute offset: distance from primary endpoint to secondary centerline
# In Revit, the primary wall endpoint is at the secondary wall's face,
# so the offset ≈ half the secondary's Revit wall_thickness.
sec_half_thickness = secondary.wall_thickness / 2.0
pri_half_thickness = primary.wall_thickness / 2.0

# Primary core: extends from endpoint through to secondary core far edge
# = offset (face to center) + half_sec_core
adjustments.append(LayerAdjustment(
    ..., amount=sec_half_thickness + half_sec_core, ...
))

# Primary exterior layers: extend further (wrapping secondary exterior layers)
amount = sec_half_thickness + half_sec_core + cumulative_sec_ext

# Primary interior layers: trim by offset + cumulative
amount = sec_half_thickness + half_sec_core + cumulative_sec_int
```

Similarly for secondary wall trims, add `pri_half_thickness` offset.

Same pattern for `_calculate_t_intersection_adjustments()`.

**Tests**:
- `TestExtensionOffset`: Verify extension amounts include half_sec_wall_thickness
- `TestExtensionReachesSecondaryFace`: With known geometry, verify the panel u_start reaches the secondary wall's far face
- `TestTrimOffset`: Verify trim amounts also account for offset

### Fix 3: Scale catalog layers to match Revit wall_thickness

**Approach**: After assembly resolution, if the catalog assembly total differs from the Revit `wall_thickness`, scale all layer thicknesses proportionally.

**Implementation** in `junction_resolver.py` `build_wall_layers_map()` or in `_build_layers_from_assembly()`:

```python
assembly_total = sum(l["thickness"] for l in assembly["layers"])
revit_thickness = wall_data.get("wall_thickness", 0)
if assembly_total > 0 and revit_thickness > 0 and abs(assembly_total - revit_thickness) > 0.01:
    scale = revit_thickness / assembly_total
    for layer in assembly["layers"]:
        layer["thickness"] *= scale
```

**Tests**:
- `TestThicknessScaling`: Verify layers are scaled when catalog != Revit thickness
- `TestNoScalingWhenClose`: Verify no scaling when difference < 0.01 ft
- `TestScaledExtensions`: Verify extension amounts use scaled thicknesses

## Implementation Order

1. **Fix 1** (is_flipped) — Highest impact, fixes layer placement AND adjustment direction
2. **Fix 2** (extension offset) — Fixes extension/trim distances
3. **Fix 3** (thickness scaling) — Fixes subtle misalignment, lowest priority

## Files Modified

| File | Fix | Change |
|------|-----|--------|
| `junction_resolver.py` | 2, 3 | Add offset to extension formula; scale layers |
| `gh_junction_analyzer.py` | 1 | Normalize z_axis before analyze_junctions |
| `gh_multi_layer_sheathing.py` | 1 | Normalize z_axis; remove ineffective face swap |
| `gh_sheathing_geometry_converter.py` | 1 | Normalize z_axis before geometry creation |
| `sheathing_geometry.py` | — | No changes needed (z_axis normalization upstream) |
| `multi_layer_generator.py` | — | No changes needed |
| `tests/wall_junctions/test_junction_resolver.py` | 2, 3 | New test classes |
| `tests/sheathing/test_multi_layer_generator.py` | 1 | Flipped wall W-offset tests |

## Verification

1. Run `pytest tests/config/ tests/sheathing/ tests/wall_junctions/ -v` — all tests pass
2. In Grasshopper with 2-wall L-corner test case:
   - Verify panels appear on correct building side for flipped wall
   - Verify panel edges align with secondary wall's far face at junction
   - Verify flipping wall in Revit swaps which side gets exterior/interior panels
