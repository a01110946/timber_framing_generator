# Junction Adjustment Math: Extend & Trim Distances

## Reference Point: Where Do Adjustments Start?

All extend/trim distances are measured from each wall's **centerline endpoint** — the point where Revit's `wall.Location.Curve` ends (or starts).

In Revit, every wall has a Location Curve that runs along its **centerline**, not along either face. When two walls meet at a corner, their centerline endpoints are what the junction detector sees. These endpoints may or may not coincide exactly (due to Revit's join behavior), but the junction detector groups them within a thickness-aware tolerance.

The adjustment `amount` for a given layer tells the sheathing generator how much to **extend** (add length) or **trim** (subtract length) from that centerline endpoint along the wall's U-axis direction.

```
                    Secondary wall (Wall B)
                         |
                         |  centerline
                         |
         ________________|________________
        |       |  core  |  core  |       |
 ext    | ext   |  B     |  B     | ext   |    ext
 face   | layer |________|________| layer |    face
        |       |        |        |       |
 -------|-------|--------*--------|-------|------- Wall A centerline
        |       |  core  |  core  |       |
 int    | int   |  A     |  A     | int   |    int
 face   | layer |________|________| layer |    face
        |_______|________|________|_______|

                         * = junction point (where centerlines meet)
```

## The Physical Problem

At an L-corner butt joint, the **primary wall** (longer or exterior wall) extends past the junction to wrap around the secondary wall. The **secondary wall** trims back to butt against the primary wall's face.

Each layer (exterior sheathing, core framing, interior gypsum) occupies a different position in the wall cross-section. Therefore, each layer needs to extend or trim by a **different amount** to meet the correct face of the opposing wall.

## The Formula

### Setup

Given two walls at a butt joint:
- **Primary wall** (P): extends at the junction
- **Secondary wall** (S): trims at the junction

Each wall has assembly layers ordered from outside to inside:
- Exterior layers: `ext[0]` (closest to core), `ext[1]`, ..., `ext[n]` (outermost)
- Core layer
- Interior layers: `int[0]` (closest to core), `int[1]`, ..., `int[m]` (innermost)

All layer thicknesses are **scaled** to match the Revit `wall_thickness`:
```
scale_factor = wall_thickness / sum(all_catalog_layer_thicknesses)
scaled_thickness = catalog_thickness * scale_factor
```

### Primary Wall Adjustments

The primary wall's layers extend or trim from its centerline endpoint:

| Layer | Direction | Amount | Physical Meaning |
|-------|-----------|--------|-----------------|
| **Core** | EXTEND | `half_S_core` | Reaches from centerline to secondary's core face |
| **Ext[0]** (e.g., OSB) | EXTEND | `half_S_core + S_ext[0] * scale` | Reaches past core to first secondary ext layer face |
| **Ext[1]** (e.g., siding) | EXTEND | `half_S_core + (S_ext[0] + S_ext[1]) * scale` | Reaches to second secondary ext layer face |
| **Int[0]** (e.g., gypsum) | **TRIM** | `half_S_core + S_int[0] * scale` | Stops before secondary's first int layer |

Where:
- `half_S_core` = secondary wall's scaled core thickness / 2
- `S_ext[i]` = secondary wall's i-th exterior layer thickness (core-outward order)
- `scale` = secondary wall's scale factor

### Secondary Wall Adjustments

The secondary wall uses **crossed/interlocking** directions (v2.3):
exterior and core TRIM; interior **EXTENDS** to cover the interior face
of the corner.

| Layer | Direction | Amount | Physical Meaning |
|-------|-----------|--------|-----------------|
| **Core** | TRIM | `half_P_core` | Stops at primary's core face |
| **Ext[0]** (e.g., OSB) | TRIM | `half_P_core + P_ext[0] * scale` | Stops at primary's first ext layer face |
| **Ext[1]** (e.g., siding) | TRIM | `half_P_core + (P_ext[0] + P_ext[1]) * scale` | Stops at primary's second ext layer face |
| **Int[0]** (e.g., gypsum) | **EXTEND** | `half_P_core + P_int[0] * scale` | Wraps past primary's first int layer face |

Where:
- `half_P_core` = primary wall's scaled core thickness / 2
- `P_ext[i]` = primary wall's i-th exterior layer thickness
- `P_int[i]` = primary wall's i-th interior layer thickness
- `scale` = primary wall's scale factor

### T-Intersection Adjustments

For T-intersections, the **continuous wall** (passes through) gets no adjustments. The **terminating wall** trims all layers using the same formula as "secondary" above, with the continuous wall as the opposing wall.

## Worked Example

### Walls

- **Wall A** (primary, 20 ft long): 2x6 exterior wall
  - Siding: 0.5" (ext, outermost)
  - OSB Sheathing: 7/16" (ext, closest to core)
  - 2x6 Framing: 5.5" (core)
  - Gypsum Board: 0.5" (int)
  - **Revit wall_thickness**: 0.573 ft (6.875")
  - **Catalog total**: 0.5" + 7/16" + 5.5" + 0.5" = 6.9375" = 0.578 ft
  - **Scale factor**: 0.573 / 0.578 = 0.991

- **Wall B** (secondary, 10 ft long): 2x4 interior wall
  - OSB Sheathing: 7/16" (ext)
  - 2x4 Framing: 3.5" (core)
  - Gypsum Board: 0.5" (int)
  - **Revit wall_thickness**: 0.370 ft (4.4375")
  - **Catalog total**: 7/16" + 3.5" + 0.5" = 4.4375" = 0.370 ft
  - **Scale factor**: 1.0 (matches exactly)

### Primary (Wall A) Adjustments

```
half_B_core = (3.5" / 12) * 1.0 / 2 = 0.1458 ft

OSB Sheathing (ext[0]):
  EXTEND by 0.1458 + (7/16" / 12) * 1.0 = 0.1458 + 0.0365 = 0.1823 ft (2.19")

Siding (ext[1]):
  EXTEND by 0.1458 + (7/16" / 12 + 0) * 1.0 = 0.1458 + 0.0365 = 0.1823 ft
  (Wall B has only 1 ext layer, so cumulative stops growing)

Core:
  EXTEND by 0.1458 ft (1.75")

Gypsum Board (int[0]):
  TRIM by 0.1458 + (0.5" / 12) * 1.0 = 0.1458 + 0.0417 = 0.1875 ft (2.25")
```

Notice the primary's **OSB barely extends** past the core — just 0.0365 ft (0.44") for the secondary's OSB layer thickness. The siding gets the same amount because Wall B has no second exterior layer.

### Secondary (Wall B) Adjustments

```
half_A_core = (5.5" / 12) * 0.991 / 2 = 0.2271 ft

All TRIM:

OSB Sheathing (ext[0]):
  TRIM by 0.2271 + (7/16" / 12) * 0.991 = 0.2271 + 0.0362 = 0.2633 ft

Core:
  TRIM by 0.2271 ft (2.72")

Gypsum Board (int[0]):
  TRIM by 0.2271 + (0.5" / 12) * 0.991 = 0.2271 + 0.0413 = 0.2684 ft
```

The secondary wall's **exterior layers trim by a LOT** — almost the full primary core thickness — because they need to clear the entire primary wall's framing zone.

## Why This Makes Physical Sense

Think about what happens at a corner when you look at it from above:

1. **Primary wall's exterior layer** (e.g., OSB) wraps around the corner. It extends past the centerline by `half_secondary_core + secondary_exterior_layer_thickness`. This is a small extension (just past the secondary wall's framing + sheathing) — typically about 2" for a 2x4 wall.

2. **Primary wall's interior layer** (e.g., gypsum) does NOT wrap around. It TRIMS — it stops short of the centerline by `half_secondary_core + secondary_interior_thickness` because the secondary wall's framing and gypsum occupy that space on the inside of the corner.

3. **Secondary wall's exterior layer** trims by `half_primary_core + primary_exterior_thickness`. This is a larger amount because the primary wall is typically thicker (it's the dominant wall), and the secondary's panels need to stop at the primary wall's outer face.

4. **Core layers** extend/trim by just `half_opposing_core` — the minimum distance from the centerline to the opposing wall's framing face.

## Fallback (No Assembly Data)

When a wall has no `wall_assembly` (no individual layer breakdown), the resolver uses 3 aggregate adjustments per wall:

| Wall | Layer | Direction | Amount |
|------|-------|-----------|--------|
| Primary | exterior | EXTEND | `half_S_core + S_ext_total` |
| Primary | core | EXTEND | `half_S_core` |
| Primary | interior | **TRIM** | `half_S_core + S_int_total` |
| Secondary | exterior | TRIM | `half_P_core + P_ext_total` |
| Secondary | core | TRIM | `half_P_core` |
| Secondary | interior | **EXTEND** | `half_P_core + P_int_total` |

The aggregate `WallLayerInfo` thicknesses are already scaled to match `wall_thickness`.

> **Note (v2.3)**: The crossed/interlocking pattern ensures continuous coverage
> on both exterior and interior faces of the corner. Primary exterior extends
> → continuous exterior face. Secondary interior extends → continuous interior
> face. The secondary's exterior TRIM creates a visible recess at the corner
> that is physically correct — covered by the primary wall's body in
> construction.

## Key Implementation Files

- `junction_resolver.py`: `_calculate_butt_adjustments()`, `_calculate_t_intersection_adjustments()`, `_assembly_scale_factor()`
- `junction_types.py`: `LayerAdjustment`, `WallLayerInfo` data classes
- `gh_multi_layer_sheathing.py`: Applies adjustments to panel U-bounds
