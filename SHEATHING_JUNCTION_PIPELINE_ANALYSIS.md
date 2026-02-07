# Sheathing-Junction Pipeline Analysis

## Date: 2026-02-07
## Status: 3 bugs identified, pre-fix analysis

---

## Pipeline Overview

```
STEP 1: Wall Analyzer (GH)         -> walls_json (wall geometry + is_flipped + base_curve_start/end)
STEP 2: Junction Analyzer (GH)     -> junctions_json (topology + resolutions + per-layer adjustments)
STEP 3: MLSheath Phase 2 recompute -> replaces adjustments with assembly-aware amounts
STEP 4: MLSheath compute_bounds    -> face_bounds dict {layer_name: (u_start, u_end)}
STEP 5: MLSheath generate_layers   -> multi_layer_json (panel dicts with u_start/u_end/w_offset)
STEP 6: Geometry Converter (GH)    -> Breps (world-space geometry from UVW coordinates)
```

---

## Step-by-Step Data Flow

### Step 1: Wall Analyzer -> walls_json

The Wall Analyzer reads Revit wall data and outputs per-wall dicts containing:
- `wall_id`, `wall_length`, `wall_thickness` (Revit total wall thickness in feet)
- `base_plane` with `origin`, `x_axis` (U = along wall), `y_axis` (V = vertical), `z_axis` (W = wall normal)
- `base_curve_start`, `base_curve_end` (wall centerline endpoints)
- `is_flipped` (True when z_axis points toward building interior instead of exterior)
- `is_exterior` (True for exterior walls)
- `wall_assembly` (None for generic Revit walls, filled for detailed compound walls)

**Key conventions:**
- U axis = along wall length (x_axis direction)
- V axis = vertical (y_axis = world Z)
- W axis = through wall thickness (z_axis = wall normal)
- `+W` = `+z_axis` direction. For non-flipped walls, this is toward building exterior.
- For `is_flipped=true`, `+z_axis` points toward building **interior** (opposite of expected).

**Revit wall join behavior:**
When two walls meet at a corner, Revit positions the centerline endpoint of one wall at the **face** of the other wall, NOT at the other wall's centerline. This means the distance between the two base_curve endpoints is approximately `sqrt((t1/2)^2 + (t2/2)^2)`, not zero.

### Step 2: Junction Analyzer -> junctions_json

The Junction Analyzer receives `walls_json` and:
1. Resolves assemblies for all walls (auto mode)
2. Calls `analyze_junctions(walls_data, ...)` which runs:
   - `build_junction_graph()`: groups close endpoints using thickness-aware tolerance
   - `_detect_t_intersections()`: checks for mid-span intersections
   - `_classify_junction()`: L_CORNER, T_INTERSECTION, X_CROSSING, FREE_END
   - `resolve_all_junctions()`: determines primary/secondary, computes per-layer adjustments

**Output format (junctions_json):**
```json
{
  "version": "1.1",
  "junction_count": 3,
  "junctions": [ ... ],
  "resolutions": [
    {
      "junction_id": "junction_0",
      "join_type": "butt",
      "primary_wall_id": "529396",
      "secondary_wall_id": "529397",
      "confidence": 0.70
    }
  ],
  "wall_adjustments": {
    "529396": [
      {"layer_name": "core", "end": "start", "adjustment_type": "extend", "amount": 0.229167},
      {"layer_name": "structural_sheathing", "end": "start", "adjustment_type": "extend", "amount": 0.270833},
      ...
    ]
  }
}
```

**`is_flipped` handling: NONE.** The junction analyzer does not read or use `is_flipped`. Detection uses only `base_curve_start/end` positions and `base_plane.x_axis` directions. Adjustments are computed based on assembly layer `side` properties (exterior/core/interior) without spatial awareness of which side faces toward or away from the other wall.

### Step 3: MLSheath Phase 2 Recompute

When `junctions_json` contains `resolutions`, MLSheath:
1. Re-parses `walls_json` and resolves assemblies
2. Calls `recompute_adjustments(junctions_data, walls_for_recompute)`
3. Replaces `junctions_data["wall_adjustments"]` with assembly-aware amounts

**`is_flipped` handling: NONE.** Recompute uses the same resolver logic as Phase 1.

### Step 4: MLSheath compute_sheathing_bounds

For each wall and each assembly layer:
1. Calls `compute_sheathing_bounds(wall_id, wall_length, layer_name, junctions_data)`
2. This function matches adjustments by `layer_name` (exact string match)
3. For `end="start"`: extends -> `u_start = -amount`, trims -> `u_start = +amount`
4. For `end="end"`: extends -> `u_end = wall_length + amount`, trims -> `u_end = wall_length - amount`

**face_bounds dict** ends up with keys for both individual layer names and aggregate face names:
```python
face_bounds = {
    "exterior_finish": (-0.323, 55.106),      # per-layer (from junction adjustments)
    "structural_sheathing": (-0.271, 55.106),  # per-layer
    "interior_finish": (0.271, 55.106),        # per-layer (trimmed)
    "exterior": (0.0, 55.106),                 # aggregate (fallback, no matching adjustments)
    "interior": (0.0, 55.106),                 # aggregate
    "core": (-0.229, 55.106),                  # aggregate
}
```

**`is_flipped` handling: INEFFECTIVE.** The code swaps `faces = ["exterior", "interior"]` -> `["interior", "exterior"]` but since the aggregate bounds loop uses `set(faces) | {"core"}` (which is always `{"exterior", "interior", "core"}`), the swap has no effect. The per-layer bounds use exact layer names, which are also flip-agnostic.

### Step 5: generate_assembly_layers (multi_layer_generator.py)

For each layer in the wall assembly:
1. Looks up bounds: `face_bounds[layer_name]` first, then `face_bounds[face]` fallback
2. Passes `u_start_bound` and `u_end_bound` to `SheathingGenerator`
3. SheathingGenerator generates panels within `[u_start_bound, u_end_bound]`
4. W offset computed from assembly stack: exterior at `+W`, interior at `-W`

**`is_flipped` handling: NONE.** `_determine_face(side)` returns `side` unchanged. W offsets always put exterior at `+W` (toward `+z_axis`).

### Step 6: Geometry Converter (gh_sheathing_geometry_converter.py)

For each panel dict:
1. Reads `u_start`, `u_end`, `v_start`, `v_end`, `layer_w_offset`, `face`
2. Creates 4 corner points via `uvw_to_world(u, v, w_offset, base_plane)`
3. Extrusion direction: `+z_axis` for `face="exterior"`, `-z_axis` for `face="interior"`

**`is_flipped` handling: NONE.** Extrusion uses `z_axis` as-is.

---

## Bugs Identified

### Bug 1: `is_flipped` Not Handled (Layers on Wrong Side)

**Symptom:** Vertical wall (529396, `is_flipped=true`) has exterior sheathing on the building interior and interior finish on the building exterior. Flipping the wall in Revit has no visual effect.

**Root cause:** `is_flipped` is read in only one place (`gh_multi_layer_sheathing.py:582-589`) where it swaps the `faces` list, but this swap has no practical effect because `set(faces)` is invariant. The flag is NOT consumed by:
- W-offset computation (exterior always at `+W` = `+z_axis`)
- Junction resolver (adjustments keyed by assembly `side`, not physical side)
- Geometry converter (extrusion direction based on `face` field = assembly `side`)

**Impact on junction adjustments:** For wall 529396 (flipped):
- Assembly "exterior" = `+z_axis` = east = toward secondary wall = should TRIM (butts against secondary)
- Assembly "interior" = `-z_axis` = west = away from secondary = should EXTEND (wraps corner)
- But resolver says: exterior EXTENDS, interior TRIMS -> **INVERTED**

**Which files handle `is_flipped`:**

| Component | Uses `is_flipped`? | Effect |
|---|---|---|
| Junction Analyzer (`gh_junction_analyzer.py`) | NO | Detection unaware of flip |
| Junction Detector (`junction_detector.py`) | NO | Uses only positions/directions |
| Junction Resolver (`junction_resolver.py`) | NO | Adjustments based on assembly `side` |
| `recompute_adjustments()` | NO | Same resolver logic |
| MLSheath (`gh_multi_layer_sheathing.py`) | YES, but **no-op** | Swaps faces list, but set() is invariant |
| Multi-layer Generator (`multi_layer_generator.py`) | NO | `_determine_face()` returns side unchanged |
| Geometry Converter (`gh_sheathing_geometry_converter.py`) | NO | Extrusion uses `z_axis` as-is |

### Bug 2: Extension Formula Uses Wrong Reference Point (Extensions Too Short)

**Symptom:** Primary wall's extending layers don't reach across the secondary wall's full thickness. The panels fall short by approximately `half_secondary_wall_thickness`.

**Root cause:** The `_calculate_butt_adjustments()` formula computes extensions relative to the **secondary wall's centerline**:

```
extension = half_sec_core + cumulative_sec_layers_on_extending_side
```

But the primary wall's `u=0` (base_curve_start) is at the secondary wall's **near face** (confirmed from data: primary start y=-25.718 = secondary center y=-25.968 + half_sec_thickness 0.250). The formula should account for this offset.

**Verified with actual data:**

| Primary Layer | Current Extension | Offset to Sec Center | Correct Extension | Shortfall |
|---|---|---|---|---|
| exterior_finish | 0.323 ft | +0.250 ft | ~0.500 ft | 0.177 ft |
| structural_sheathing | 0.271 ft | +0.250 ft | ~0.448 ft | 0.177 ft |
| core | 0.229 ft | +0.250 ft | ~0.406 ft | 0.177 ft |

The shortfall (0.177 ft = 2.1") is consistent across all layers — it equals the secondary wall's interior half-thickness (distance from near face to centerline = `sec_interior_finish + half_sec_core - half_sec_core` ... approximately `half_sec_wall_thickness = 0.250 ft`).

Wait, the shortfall is 0.177 ft, not 0.250 ft. This is because the catalog assembly's total (0.594 ft) differs from the Revit wall_thickness (0.500 ft). The formula uses catalog half-thicknesses (0.323 ft from center to exterior face), while the Revit half-thickness is 0.250 ft. So the offset from primary endpoint to secondary center is 0.250 ft (Revit), but the formula already "covers" 0.323 ft of catalog thickness. The net shortfall = `Revit_offset - (catalog_ext_half - Revit_half)` = 0.250 - (0.323 - 0.250) = 0.177 ft.

**Code location:** `junction_resolver.py:345-393`

### Bug 3: Catalog Assembly Thickness != Revit Wall Thickness

**Symptom:** The 2x6_exterior catalog assembly has total thickness 0.594 ft (7.125"), but the Revit wall is 0.500 ft (6"). Layer thicknesses used in calculations don't match the actual wall geometry.

**Root cause:** The catalog assembly includes finish layers (stucco 0.625", gypsum 0.5", OSB 0.5") on top of the 5.5" core = 7.125" total. Generic Revit walls only report the core-inclusive thickness.

**Impact:** Extension amounts are computed from catalog layer thicknesses that are thicker than reality. This partially compensates for Bug 2 (the formula undershoots by 0.177 ft instead of 0.250 ft because catalog thicknesses are inflated), but the compensation is inconsistent and geometry doesn't align with the Revit wall's physical face positions.

---

## Interaction Between Bugs

Bugs 1 and 2 compound:
- Bug 1 puts layers on the wrong side of the wall
- Bug 2 makes the extensions too short even if they were on the correct side
- Fixing Bug 1 alone would put layers on the right side but with incorrect extension lengths
- Fixing Bug 2 alone would give correct extension lengths but on the wrong side (for flipped walls)
- Both must be fixed together for correct visual results

Bug 3 is lower priority but causes subtle misalignment between computed adjustments and actual Revit wall geometry.

---

## Proposed Fix Strategy

### Fix for Bug 1: Normalize z_axis for flipped walls

**Approach:** At the entry point of each GH component, if `is_flipped=true`, negate `z_axis` in the wall data. This makes `+z_axis = physical exterior` consistently, so all downstream code (W offsets, junction resolver, geometry converter) works correctly without individual changes.

**Files to modify:**
- `gh_junction_analyzer.py`: Negate z_axis before `analyze_junctions()`
- `gh_multi_layer_sheathing.py`: Negate z_axis before Phase 2 recompute and before `process_walls()`
- `gh_sheathing_geometry_converter.py`: Negate z_axis before `create_sheathing_breps()`

**Alternative:** Swap assembly layer `side` labels when `is_flipped=true` (more invasive, requires changes in multiple modules).

### Fix for Bug 2: Account for endpoint-to-centerline offset

**Approach:** The resolver needs to add the distance from the primary wall's endpoint to the secondary wall's centerline. This distance can be computed from the wall data:

```
offset = secondary_wall.wall_thickness / 2.0  (Revit thickness, not catalog)
```

Then:
```
extension = offset + half_sec_core + cumulative_sec_layers
```

**Alternatively:** Use `wall_thickness / 2` (Revit) directly instead of `half_sec_core` (catalog) as the base for extensions. This sidesteps Bug 3 as well.

**Files to modify:**
- `junction_resolver.py`: `_calculate_butt_adjustments()` and `_calculate_t_intersection_adjustments()`

### Fix for Bug 3: Scale catalog layers to match Revit thickness

**Approach:** When the catalog assembly total differs from `wall_thickness`, scale layer thicknesses proportionally:

```
scale = wall_thickness / assembly_total_thickness
scaled_layer_thickness = layer.thickness * scale
```

**Files to modify:**
- `assembly_resolver.py` or `junction_resolver.py`: Scale after assembly resolution, before adjustment calculation.

---

## Debugging Checklist

To verify each step is working, check these values in the diagnostic output:

### Step 2 — Junction Detection
- [ ] `junction_count > 0`
- [ ] Junction type = `l_corner` (not `free_end`)
- [ ] Both walls present in connections
- [ ] `resolutions` list is non-empty

### Step 3 — Phase 2 Recompute
- [ ] Log shows: `Phase 2 recompute: X -> Y adjustments`
- [ ] Each adjustment has correct `layer_name` (individual layer names, not aggregate)
- [ ] Extension amounts are geometrically reasonable (`> half_sec_wall_thickness`)

### Step 4 — Bounds Computation
- [ ] Per-layer bounds differ from `(0, wall_length)` at junction ends
- [ ] Extension amounts match Step 3 adjustments

### Step 5 — Panel Generation
- [ ] `first_u_start` is negative (extended before wall start) for extending layers
- [ ] `last_u_end` > `wall_length` for extending layers at wall end
- [ ] W offsets: exterior positive, interior negative (for non-flipped walls)
- [ ] For flipped walls: verify W offsets place panels on correct physical side

### Step 6 — Geometry
- [ ] Panels appear on correct side of wall (exterior on building exterior)
- [ ] Panel edges align with other wall's face at junctions
