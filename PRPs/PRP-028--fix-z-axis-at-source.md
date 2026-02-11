# PRP-028: Fix z_axis at Source — Eliminate exterior_normal Workaround

## Problem Statement

The `base_plane.z_axis` in `walls_json` can be **opposite** to Revit's `wall.Orientation` for certain wall directions due to the Y-axis safety guard in `wall_helpers.py`. This forces every downstream consumer (MLSheath, SheathGeoConverter, Junction Detector) to work around the unreliable z_axis by reading a separate `exterior_normal` field instead.

**Root cause**: `wall_helpers.py:157-165` ensures Y-axis always points up `(0,0,1)` for framing element placement. When `cross(wall.Orientation, x_dir)` produces a Y with Z < 0, the guard recomputes `Z = cross(X, Y)`, which can be the **opposite** of `wall.Orientation`.

Example for a wall going east `X=(1,0,0)` facing north `wall.Orientation=(0,1,0)`:
- `Y = cross(Z, X) = (0, 0, -1)` — points DOWN, triggers guard
- Guard: `Y = (0,0,1)`, then `Z = cross(X, Y) = (0, -1, 0)` — **opposite** of `wall.Orientation`

**Current workarounds**:
- `exterior_normal` field added to `WallData` schema to carry `wall.Orientation` alongside the unreliable `base_plane.z_axis`
- MLSheath overrides `base_plane.z_axis` with `exterior_normal` at runtime (lines 536-560)
- SheathGeoConverter overrides `base_plane.z_axis` with `exterior_normal` at runtime (lines 425-432)
- `junction_detector.py` has `_extract_z_axis()` that prefers `exterior_normal` over `base_plane.z_axis`

This is fragile: every new consumer of `walls_json` must remember to use `exterior_normal` instead of `base_plane.z_axis`. A single missed consumer causes silent bugs (layers on wrong face, wrong corner-type detection).

## Solution Design

**Fix z_axis at the source** so it always equals `wall.Orientation` in the serialized `walls_json`. Then remove `exterior_normal` and all downstream workarounds.

### Step 1: Override z_axis in Wall Analyzer (`gh_wall_analyzer.py`)

In `convert_wall_data_to_schema()`, after building `plane_data` from `wall_helpers.py` output, override `z_axis` with the value from `exterior_normal` (which is `wall.Orientation`):

```python
# Override z_axis with wall.Orientation (authoritative exterior direction).
# wall_helpers.py may compute a z_axis that disagrees with wall.Orientation
# due to the Y-axis safety guard. Fix it here so walls_json is correct.
en = _parse_exterior_normal(wall_data)
if en is not None:
    plane_data.z_axis = en
```

Then remove `exterior_normal` from the `WallData()` constructor call.

### Step 2: Remove `exterior_normal` from `WallData` schema (`json_schemas.py`)

Delete the `exterior_normal: Optional[Vector3D] = None` field from the `WallData` dataclass. This eliminates the redundant field from the data model.

### Step 3: Remove `_parse_exterior_normal()` from Wall Analyzer

Delete the helper function and its call site — no longer needed.

### Step 4: Remove `exterior_normal` from `revit_data_extractor.py`

Remove the `exterior_normal` key from the returned wall dict. The Wall Analyzer still needs `wall.Orientation` to override z_axis, so keep reading it but use it directly for the z_axis override instead of storing it as a separate field.

**Wait** — the Wall Analyzer needs the raw `wall.Orientation` value from the extractor to override z_axis. The extractor already provides it as `exterior_normal`. We have two choices:
- (A) Keep `exterior_normal` in the extractor output dict (internal, not serialized to JSON) — used only by Wall Analyzer to override z_axis
- (B) Rename it to something clearer in the extractor dict

**Decision**: Option A — keep `exterior_normal` in the extractor's return dict as an internal implementation detail. It just won't appear in the final `walls_json` or `WallData` schema.

### Step 5: Remove override blocks from MLSheath (`gh_multi_layer_sheathing.py`)

Delete lines 536-560 (the `exterior_normal → z_axis` override loop). `walls_json` now has the correct z_axis from the source.

### Step 6: Remove override block from SheathGeoConverter (`gh_sheathing_geometry_converter.py`)

Delete lines 425-432 (the `exterior_normal → z_axis` override loop).

### Step 7: Simplify `_extract_z_axis()` in Junction Detector (`junction_detector.py`)

Remove the `exterior_normal` preference — just read `base_plane.z_axis` directly, since it's now authoritative.

### Step 8: Fix wrong docstring in `wall_helpers.py`

Update the docstring at lines 95-100 to reflect reality:
- `wall.Orientation` **does** change when the wall is flipped in Revit (proven empirically)
- The Y-axis safety guard can make `z_axis ≠ wall.Orientation`
- Downstream code (Wall Analyzer) overrides z_axis with `wall.Orientation` before serializing

## Files Changed

| File | Change |
|------|--------|
| `scripts/gh_wall_analyzer.py` | Override z_axis with exterior_normal in `convert_wall_data_to_schema()`, remove `_parse_exterior_normal()`, remove `exterior_normal` from WallData constructor |
| `src/.../core/json_schemas.py` | Remove `exterior_normal` field from `WallData` |
| `scripts/gh_multi_layer_sheathing.py` | Remove exterior_normal → z_axis override block (lines 536-560) |
| `scripts/gh_sheathing_geometry_converter.py` | Remove exterior_normal → z_axis override block (lines 425-432) |
| `src/.../wall_junctions/junction_detector.py` | Simplify `_extract_z_axis()` to only read `base_plane.z_axis` |
| `src/.../wall_data/wall_helpers.py` | Fix wrong docstring about wall.Orientation and flip behavior |

## Implications

1. **base_plane is no longer a strict orthonormal frame** for some wall directions: `X × Y ≠ Z`. This is acceptable because downstream code reads individual axes from JSON, not the frame as a whole (X for U-direction, Y for vertical, Z for wall normal).

2. **Cell Decomposer and Framing Generator** use X and Y axes only (for U/V decomposition). They don't depend on Z being the cross product of X × Y.

3. **No test changes needed** — tests don't reference `exterior_normal` (zero occurrences in `tests/`). The junction detector tests mock wall dicts with `base_plane.z_axis` directly.

## Verification

1. `pytest tests/wall_junctions/ tests/sheathing/ -v` — all 305 tests pass
2. User re-pastes updated Wall Analyzer, MLSheath, and SheathGeoConverter into GH
3. Sheathing layers appear on correct (exterior) face for both flipped and unflipped walls
4. Junction corner-type detection uses correct z_axis (now reliable in walls_json)
