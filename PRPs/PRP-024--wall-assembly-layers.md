# PRP-024: Wall Assembly Layer System

> **Version:** 1.0
> **Created:** 2026-02-05
> **Status:** Draft
> **Branch:** feature/wall-assembly-layers
> **Depends on:** PRP-023 (Wall Junction Analyzer)

---

## Goal

Replace the hardcoded 3-layer wall model (`exterior`, `core`, `interior`) with an ordered multi-layer wall assembly system where each layer has a function, side, priority, and thickness. Fix the junction resolver to implement the **crossed pattern** at butt joints (exterior layers follow the primary wall, interior layers follow the secondary wall), and produce per-layer adjustments that any downstream generator (sheathing, insulation, drywall, cladding) can consume.

---

## Why

### Business Value
- **Correct sheathing at corners**: Currently, sheathing overlaps at L-corners because both exterior and interior layers of the primary wall extend identically. In reality, exterior layers extend on the outside corner while interior layers extend on the inside corner (the **crossed pattern**).
- **Multi-layer material takeoffs**: Real wall assemblies have 5-10 layers (siding, WRB, sheathing, insulation, vapor retarder, drywall). Each layer needs its own junction geometry.
- **Manufacturer adaptability**: Prefab manufacturers have specific rules for sheathing placement (edge alignment to studs, 24" return at corners, 1/16" panel gaps). A rule engine per layer type enables this.
- **Foundation for future generators**: Insulation, drywall, and cladding generators need the same layer-aware adjustment system.

### Technical Requirements
- **Per-layer junction resolution**: Each layer in the assembly gets its own extend/trim amount based on its side and function
- **Backward compatible**: Existing 3-layer code paths continue working; new multi-layer is opt-in
- **Pluggable layer source**: Layers come from defaults today, Revit CompoundStructure tomorrow, user overrides anytime

### Problems Solved
1. **Sheathing overlap at L-corners**: Primary wall's exterior AND interior both extend -> exterior overlaps secondary's exterior
2. **Sheathing overlap at T-intersections**: Terminating wall's sheathing extends into continuous wall volume
3. **Gap at inside corners**: Neither wall's interior finish covers the corner junction
4. **No support for multiple layers per side**: Can't model `siding | WRB | sheathing | core | insulation | drywall` as distinct layers
5. **No per-layer rules engine**: Can't apply manufacturer-specific placement rules per layer type

---

## What

### The Crossed Pattern (Core Insight)

At an L-corner butt joint between a primary wall (extends) and secondary wall (trims):

```
    EXTERIOR SIDE (outside of building)
                    |
         Secondary  |  Secondary ext. layers TRIM
         wall       |  (butt against primary)
                    |
    ================+==================  Primary wall
                    |                    Primary ext. layers EXTEND
         Secondary  |                    (wrap the corner)
         int. layers|
         EXTEND     |
         (wrap the  |
          inside    |
          corner)   |
                    |
    INTERIOR SIDE (inside of building)
```

**Rule**: At butt joints, layers on the **same side as the primary wall's extending direction** EXTEND. Layers on the **opposite side** follow the secondary wall pattern (extend to cover the inside corner).

In concrete terms:
- Primary exterior layers: **EXTEND** by `secondary.total / 2`
- Primary interior layers: **TRIM** by `secondary.core / 2` (secondary's interior covers this corner)
- Secondary exterior layers: **TRIM** by `primary.core / 2`
- Secondary interior layers: **EXTEND** by `primary.total / 2` (covers the inside corner)
- Primary core: **EXTEND** by `secondary.core / 2`
- Secondary core: **TRIM** by `primary.core / 2`

### Layer Function Hierarchy

Following Revit/IFC conventions, layers are classified by function:

| Priority | Function | Typical Materials | Side |
|----------|----------|-------------------|------|
| 1 (Highest) | **Structure** | Wood studs, steel studs | Core |
| 2 | **Substrate** | OSB, plywood (structural sheathing) | Exterior or Interior |
| 3 | **Thermal/Air** | Cavity insulation, rigid foam, air gap | Either |
| 4 | **Membrane** | WRB (Tyvek), vapor retarder | Either |
| 5 (Lowest) | **Finish** | Siding, gypsum board, stucco | Exterior or Interior |

Higher-priority layers can extend through lower-priority layers at junctions. The **core boundary** separates exterior-side layers from interior-side layers.

### User-Visible Behavior

**Inputs** (no change to Junction Analyzer GH component interface):
- `walls_json` with optional `wall_assembly` per wall
- `junction_overrides` (unchanged)

**Outputs** (enhanced `junctions_json`):
- `wall_adjustments` now contain **per-layer adjustments with layer index**, not just "exterior"/"core"/"interior"
- Backward-compatible: old 3-name format still works for downstream consumers that don't know about multi-layer

### Success Criteria

- [ ] `WallAssembly` dataclass with ordered `WallLayer` list replaces simple 3-thickness model
- [ ] Each `WallLayer` has: name, function, side, thickness, priority, material, wraps_at_ends, wraps_at_inserts
- [ ] Junction resolver implements crossed pattern at L-corners
- [ ] Junction resolver handles T-intersections with per-layer trimming
- [ ] `LayerAdjustment.layer_name` supports both legacy names ("exterior", "core", "interior") and specific layer names ("structural_sheathing", "drywall")
- [ ] Default assembly factory creates standard 2x4 and 2x6 assemblies from `config/assembly.py`
- [ ] Revit CompoundStructure extraction stub (returns defaults for now, ready for Phase 2)
- [ ] Sheathing generator consumes new per-layer adjustments correctly
- [ ] All existing tests pass (backward compatibility)
- [ ] New tests cover crossed pattern at L-corners, T-intersections, and multi-layer assemblies
- [ ] L-corner sheathing no longer overlaps (visual verification in Grasshopper)

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-modular-architecture-plan.md
    why: Overall system architecture and pipeline flow

  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for wall-relative layer positioning

Core Implementations:
  - file: src/timber_framing_generator/wall_junctions/junction_types.py
    why: >
      CRITICAL - Current WallLayerInfo with 3 hardcoded layers.
      LayerAdjustment with layer_name field. Must be extended.

  - file: src/timber_framing_generator/wall_junctions/junction_resolver.py
    why: >
      CRITICAL - _calculate_butt_adjustments() is WRONG. Currently extends
      ALL primary layers (including interior) by the same amount.
      Must implement the crossed pattern.

  - file: src/timber_framing_generator/config/assembly.py
    why: >
      Current WallAssembly with 3 thicknesses. WALL_ASSEMBLY singleton.
      Will be replaced by multi-layer WallAssembly.

  - file: scripts/gh_sheathing_generator.py
    why: >
      compute_sheathing_bounds() maps face -> layer_name and consumes
      junction adjustments. Must be updated for multi-layer.

  - file: src/timber_framing_generator/sheathing/sheathing_geometry.py
    why: >
      calculate_w_offset() positions panels relative to wall centerline.
      Must support arbitrary layer stacking.

  - file: src/timber_framing_generator/core/json_schemas.py
    why: WallData dataclass. Will gain optional wall_assembly field.

Standards:
  - reference: "Revit Layer Functions: Structure [1], Substrate [2], Thermal [3], Membrane [4], Finish 1/2 [5/6]"
  - reference: "IFC IfcMaterialLayerSet / IfcMaterialLayer with Priority [0-100]"
  - reference: "IRC R602.10 - 24-inch minimum return corner for braced wall lines"
  - reference: "APA E30 - 1/2 inch minimum bearing on framing, 3/8 inch edge distance, 1/16 inch panel gap"
```

### Current Codebase Structure

```
src/timber_framing_generator/
├── wall_junctions/
│   ├── junction_types.py        # MODIFY - WallLayerInfo -> WallAssembly + WallLayer
│   ├── junction_resolver.py     # MODIFY - Fix crossed pattern, per-layer resolution
│   ├── junction_detector.py     # NO CHANGE
│   └── __init__.py              # MODIFY - Export new types
├── config/
│   └── assembly.py              # MODIFY - Multi-layer WallAssembly definitions
├── core/
│   └── json_schemas.py          # MODIFY - Optional wall_assembly on WallData
├── sheathing/
│   └── sheathing_geometry.py    # MODIFY (Phase 3) - Layer-aware W offset
└── wall_data/
    └── revit_data_extractor.py  # STUB (Phase 2) - CompoundStructure extraction

scripts/
├── gh_sheathing_generator.py    # MODIFY - Update compute_sheathing_bounds
└── gh_junction_analyzer.py      # MINOR MODIFY - Pass assembly data through
```

### Desired Structure (files to add/modify)

```
src/timber_framing_generator/
├── wall_junctions/
│   ├── junction_types.py        # MODIFY: Add WallLayer, LayerFunction, LayerSide enums
│   │                            #         Replace WallLayerInfo internals
│   │                            #         Keep WallLayerInfo as backward-compatible wrapper
│   ├── junction_resolver.py     # MODIFY: Fix _calculate_butt_adjustments (crossed pattern)
│   │                            #         Add _calculate_per_layer_butt_adjustments
│   │                            #         Update build_wall_layers_map for multi-layer
│   └── __init__.py              # MODIFY: Export new types
├── config/
│   └── assembly.py              # MODIFY: Multi-layer WALL_ASSEMBLIES catalog
│   │                            #         Keep backward-compatible WALL_ASSEMBLY
└── core/
    └── json_schemas.py          # MODIFY: Optional wall_assembly field on WallData

tests/
├── wall_junctions/
│   ├── test_junction_resolver.py  # MODIFY: Add crossed pattern tests
│   └── test_wall_assembly.py      # CREATE: Assembly creation and layer resolution tests
```

### Known Gotchas & Library Quirks

```yaml
CRITICAL - Crossed Pattern Direction:
  issue: >
    The "primary wall extends" description is ambiguous for layers.
    The primary wall's CORE extends (into the secondary wall's volume).
    But the primary wall's INTERIOR layers actually TRIM, because the
    secondary wall's interior layers are the ones that extend to cover
    the inside corner.
  solution: >
    Determine layer adjustment based on layer.side + wall role:
      primary + exterior_side -> EXTEND
      primary + interior_side -> TRIM
      secondary + exterior_side -> TRIM
      secondary + interior_side -> EXTEND
      core layers always follow the wall role (primary=extend, secondary=trim)

CRITICAL - Backward Compatibility:
  issue: >
    Downstream code (gh_sheathing_generator.py) looks up adjustments by
    layer_name in ["exterior", "core", "interior"]. New multi-layer
    adjustments use specific names like "structural_sheathing".
  solution: >
    Emit BOTH formats: legacy 3-name adjustments (aggregated) AND
    per-layer adjustments with specific names. Downstream consumers
    can choose which to read. The legacy format computes the maximum
    extend/trim for all layers on each side.

CRITICAL - Layer Stacking Order:
  issue: >
    W-offset calculation must account for ALL layers between centerline
    and the target layer, not just "half wall thickness".
  solution: >
    Each layer knows its W-offset range: w_start to w_end.
    Computed by stacking from core boundary outward on each side.
    Phase 1 keeps simple half-thickness offset; Phase 3 updates
    sheathing_geometry.py with proper stacking.

IMPORTANT - Revit CompoundStructure Not Yet Extracted:
  issue: >
    revit_data_extractor.py extracts wall_thickness as a single float.
    Revit's WallType.GetCompoundStructure() provides per-layer data
    but is not yet implemented.
  solution: >
    Phase 1: Default assemblies from config/assembly.py.
    Phase 2 (future PRP): Extract CompoundStructure in wall analyzer.
    Design the system so layer source is pluggable.

IMPORTANT - T-Intersection Layer Behavior:
  issue: >
    At T-intersections, the terminating wall's ALL layers trim.
    The continuous wall is unmodified. This is simpler than L-corners
    (no crossed pattern for T-intersections).
  solution: >
    T-intersection: all terminating layers trim by continuous.core/2.
    No change from current logic for T-intersections.
```

---

## Implementation Blueprint

### Data Models

```python
# File: src/timber_framing_generator/wall_junctions/junction_types.py
# NEW enums and dataclasses (additions to existing file)

class LayerFunction(Enum):
    """Wall layer function classification (Revit/IFC convention)."""
    STRUCTURE = "structure"        # Priority 1 - Studs, structural sheathing
    SUBSTRATE = "substrate"        # Priority 2 - Sheathing, backer board
    THERMAL = "thermal"            # Priority 3 - Insulation, air gaps
    MEMBRANE = "membrane"          # Priority 4 - WRB, vapor retarder
    FINISH = "finish"              # Priority 5 - Siding, drywall


class LayerSide(Enum):
    """Which side of the core boundary a layer is on."""
    EXTERIOR = "exterior"   # Outside the core boundary (toward building exterior)
    CORE = "core"           # The structural core itself
    INTERIOR = "interior"   # Inside the core boundary (toward building interior)


@dataclass
class WallLayer:
    """A single layer in a wall assembly.

    Attributes:
        name: Human-readable layer name (e.g., "structural_sheathing").
        function: Layer function classification.
        side: Which side of core boundary.
        thickness: Layer thickness in feet.
        material: Material name (e.g., "OSB 7/16").
        priority: Junction priority [1-100]. Higher priority layers extend
                  through lower priority layers at junctions.
        wraps_at_ends: Whether this layer wraps at free wall ends.
        wraps_at_inserts: Whether this layer wraps at openings.
    """
    name: str
    function: LayerFunction
    side: LayerSide
    thickness: float
    material: str = ""
    priority: int = 50
    wraps_at_ends: bool = False
    wraps_at_inserts: bool = False


@dataclass
class WallAssemblyDef:
    """Multi-layer wall assembly definition.

    Layers are ordered from exterior to interior (outside to inside).
    The core boundary is implicit: layers with side=CORE are the core.

    Attributes:
        name: Assembly name (e.g., "2x4_exterior").
        layers: Ordered list of layers from exterior to interior.
        source: Where this assembly came from.
    """
    name: str
    layers: List[WallLayer]
    source: str = "default"

    @property
    def total_thickness(self) -> float:
        return sum(layer.thickness for layer in self.layers)

    @property
    def core_thickness(self) -> float:
        return sum(l.thickness for l in self.layers if l.side == LayerSide.CORE)

    @property
    def exterior_thickness(self) -> float:
        return sum(l.thickness for l in self.layers if l.side == LayerSide.EXTERIOR)

    @property
    def interior_thickness(self) -> float:
        return sum(l.thickness for l in self.layers if l.side == LayerSide.INTERIOR)

    def get_layers_by_side(self, side: LayerSide) -> List[WallLayer]:
        return [l for l in self.layers if l.side == side]

    def to_legacy_layer_info(self, wall_id: str) -> "WallLayerInfo":
        """Convert to legacy 3-layer WallLayerInfo for backward compatibility."""
        return WallLayerInfo(
            wall_id=wall_id,
            total_thickness=self.total_thickness,
            exterior_thickness=self.exterior_thickness,
            core_thickness=self.core_thickness,
            interior_thickness=self.interior_thickness,
            source=self.source,
        )
```

### Algorithm: Crossed Pattern for Butt Joints

```python
def _calculate_butt_adjustments_v2(
    junction_id: str,
    primary: WallConnection,
    secondary: WallConnection,
    primary_assembly: WallAssemblyDef,
    secondary_assembly: WallAssemblyDef,
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments using the crossed pattern.

    At a butt joint:
    - Primary wall's exterior-side layers EXTEND (cover outside corner)
    - Primary wall's interior-side layers TRIM (secondary covers inside corner)
    - Secondary wall's exterior-side layers TRIM (butt against primary)
    - Secondary wall's interior-side layers EXTEND (cover inside corner)
    - Core layers follow wall role: primary extends, secondary trims
    """
    adjustments = []

    half_sec_core = secondary_assembly.core_thickness / 2.0
    half_sec_total = secondary_assembly.total_thickness / 2.0
    half_pri_core = primary_assembly.core_thickness / 2.0
    half_pri_total = primary_assembly.total_thickness / 2.0

    # --- PRIMARY WALL ---
    for layer in primary_assembly.layers:
        if layer.side == LayerSide.CORE:
            # Core extends into secondary wall's core
            adj_type = AdjustmentType.EXTEND
            amount = half_sec_core
        elif layer.side == LayerSide.EXTERIOR:
            # Exterior layers extend to wrap outside corner
            adj_type = AdjustmentType.EXTEND
            amount = half_sec_total
        else:  # INTERIOR
            # Interior layers TRIM — secondary's interior will cover this corner
            adj_type = AdjustmentType.TRIM
            amount = half_sec_core

        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer.name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # --- SECONDARY WALL ---
    for layer in secondary_assembly.layers:
        if layer.side == LayerSide.CORE:
            # Core trims to butt against primary's core
            adj_type = AdjustmentType.TRIM
            amount = half_pri_core
        elif layer.side == LayerSide.EXTERIOR:
            # Exterior layers trim — primary's exterior covers this corner
            adj_type = AdjustmentType.TRIM
            amount = half_pri_core
        else:  # INTERIOR
            # Interior layers EXTEND to wrap inside corner
            adj_type = AdjustmentType.EXTEND
            amount = half_pri_total

        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer.name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=primary.wall_id,
        ))

    # Also emit legacy 3-name adjustments for backward compatibility
    adjustments.extend(_emit_legacy_adjustments(
        junction_id, primary, secondary,
        primary_assembly, secondary_assembly
    ))

    return adjustments


def _emit_legacy_adjustments(
    junction_id, primary, secondary,
    primary_assembly, secondary_assembly,
):
    """Emit legacy "exterior"/"core"/"interior" adjustments.

    These are the aggregate adjustments that existing consumers
    (gh_sheathing_generator compute_sheathing_bounds) expect.
    """
    half_sec_core = secondary_assembly.core_thickness / 2.0
    half_sec_total = secondary_assembly.total_thickness / 2.0
    half_pri_core = primary_assembly.core_thickness / 2.0
    half_pri_total = primary_assembly.total_thickness / 2.0

    legacy = []

    # Primary wall: exterior extends, core extends, interior TRIMS
    for layer_name, adj_type, amount in [
        ("exterior", AdjustmentType.EXTEND, half_sec_total),
        ("core", AdjustmentType.EXTEND, half_sec_core),
        ("interior", AdjustmentType.TRIM, half_sec_core),
    ]:
        legacy.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # Secondary wall: exterior trims, core trims, interior EXTENDS
    for layer_name, adj_type, amount in [
        ("exterior", AdjustmentType.TRIM, half_pri_core),
        ("core", AdjustmentType.TRIM, half_pri_core),
        ("interior", AdjustmentType.EXTEND, half_pri_total),
    ]:
        legacy.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=primary.wall_id,
        ))

    return legacy
```

### Default Assembly Catalog

```python
# File: src/timber_framing_generator/config/assembly.py (additions)

# Standard 2x4 exterior wall assembly (outside to inside)
ASSEMBLY_2X4_EXTERIOR = WallAssemblyDef(
    name="2x4_exterior",
    layers=[
        WallLayer("exterior_finish", LayerFunction.FINISH, LayerSide.EXTERIOR,
                  thickness=convert_to_feet(0.5, "inches"),
                  material="Lap Siding", priority=10),
        WallLayer("wrb", LayerFunction.MEMBRANE, LayerSide.EXTERIOR,
                  thickness=0.0,  # negligible
                  material="Tyvek HomeWrap", priority=20),
        WallLayer("structural_sheathing", LayerFunction.SUBSTRATE, LayerSide.EXTERIOR,
                  thickness=convert_to_feet(0.4375, "inches"),
                  material="OSB 7/16", priority=80),
        WallLayer("framing_core", LayerFunction.STRUCTURE, LayerSide.CORE,
                  thickness=convert_to_feet(3.5, "inches"),
                  material="2x4 SPF @ 16\" OC", priority=100),
        WallLayer("interior_finish", LayerFunction.FINISH, LayerSide.INTERIOR,
                  thickness=convert_to_feet(0.5, "inches"),
                  material="1/2\" Gypsum Board", priority=10),
    ],
    source="default",
)

# Standard 2x6 exterior wall assembly
ASSEMBLY_2X6_EXTERIOR = WallAssemblyDef(
    name="2x6_exterior",
    layers=[
        WallLayer("exterior_finish", LayerFunction.FINISH, LayerSide.EXTERIOR,
                  thickness=convert_to_feet(0.625, "inches"),
                  material="Fiber Cement Siding", priority=10),
        WallLayer("wrb", LayerFunction.MEMBRANE, LayerSide.EXTERIOR,
                  thickness=0.0,
                  material="Tyvek HomeWrap", priority=20),
        WallLayer("structural_sheathing", LayerFunction.SUBSTRATE, LayerSide.EXTERIOR,
                  thickness=convert_to_feet(0.5, "inches"),
                  material="OSB 1/2", priority=80),
        WallLayer("framing_core", LayerFunction.STRUCTURE, LayerSide.CORE,
                  thickness=convert_to_feet(5.5, "inches"),
                  material="2x6 SPF @ 16\" OC", priority=100),
        WallLayer("interior_finish", LayerFunction.FINISH, LayerSide.INTERIOR,
                  thickness=convert_to_feet(0.5, "inches"),
                  material="1/2\" Gypsum Board", priority=10),
    ],
    source="default",
)

# Interior partition wall
ASSEMBLY_2X4_INTERIOR = WallAssemblyDef(
    name="2x4_interior",
    layers=[
        WallLayer("finish_a", LayerFunction.FINISH, LayerSide.EXTERIOR,
                  thickness=convert_to_feet(0.5, "inches"),
                  material="1/2\" Gypsum Board", priority=10),
        WallLayer("framing_core", LayerFunction.STRUCTURE, LayerSide.CORE,
                  thickness=convert_to_feet(3.5, "inches"),
                  material="2x4 SPF @ 16\" OC", priority=100),
        WallLayer("finish_b", LayerFunction.FINISH, LayerSide.INTERIOR,
                  thickness=convert_to_feet(0.5, "inches"),
                  material="1/2\" Gypsum Board", priority=10),
    ],
    source="default",
)

# Assembly catalog for lookup
WALL_ASSEMBLIES = {
    "2x4_exterior": ASSEMBLY_2X4_EXTERIOR,
    "2x6_exterior": ASSEMBLY_2X6_EXTERIOR,
    "2x4_interior": ASSEMBLY_2X4_INTERIOR,
}

def get_assembly_for_wall(wall_data: Dict) -> WallAssemblyDef:
    """Get the appropriate assembly for a wall.

    Lookup order:
    1. wall_data["wall_assembly"] if present (explicit override)
    2. WALL_ASSEMBLIES[wall_data["wall_type"]] if wall_type matches catalog
    3. ASSEMBLY_2X4_EXTERIOR if is_exterior
    4. ASSEMBLY_2X4_INTERIOR otherwise
    """
    # Check explicit assembly
    if "wall_assembly" in wall_data:
        return deserialize_assembly(wall_data["wall_assembly"])

    # Check wall type catalog
    wall_type = wall_data.get("wall_type", "")
    if wall_type in WALL_ASSEMBLIES:
        return WALL_ASSEMBLIES[wall_type]

    # Default by exterior/interior
    is_exterior = wall_data.get("is_exterior", False)
    return ASSEMBLY_2X4_EXTERIOR if is_exterior else ASSEMBLY_2X4_INTERIOR
```

---

### Tasks (in execution order)

```yaml
Task 1: Add new data models to junction_types.py
  - MODIFY: src/timber_framing_generator/wall_junctions/junction_types.py
  - ADD: LayerFunction enum, LayerSide enum, WallLayer dataclass, WallAssemblyDef dataclass
  - PRESERVE: All existing types (WallLayerInfo, LayerAdjustment, etc.)
  - ADD: WallAssemblyDef.to_legacy_layer_info() for backward compatibility
  - ADD: Serialization helpers for new types

Task 2: Add default assembly catalog to config/assembly.py
  - MODIFY: src/timber_framing_generator/config/assembly.py
  - ADD: ASSEMBLY_2X4_EXTERIOR, ASSEMBLY_2X6_EXTERIOR, ASSEMBLY_2X4_INTERIOR
  - ADD: WALL_ASSEMBLIES catalog dict
  - ADD: get_assembly_for_wall() lookup function
  - PRESERVE: Existing WALL_ASSEMBLY, SHEATHING_PARAMS, OPENING_DEFAULTS

Task 3: Fix junction_resolver.py crossed pattern
  - MODIFY: src/timber_framing_generator/wall_junctions/junction_resolver.py
  - CHANGE: _calculate_butt_adjustments() to implement crossed pattern:
    - Primary exterior: EXTEND by secondary.total/2
    - Primary interior: TRIM by secondary.core/2
    - Secondary exterior: TRIM by primary.core/2
    - Secondary interior: EXTEND by primary.total/2
  - ADD: _calculate_butt_adjustments_v2() for multi-layer assemblies
  - ADD: _emit_legacy_adjustments() for backward-compatible 3-name output
  - CHANGE: build_wall_layers_map() to support WallAssemblyDef
  - PRESERVE: _calculate_miter_adjustments, _calculate_t_intersection_adjustments
  - PRESERVE: resolve_all_junctions, analyze_junctions signatures

Task 4: Update sheathing generator for crossed pattern
  - MODIFY: scripts/gh_sheathing_generator.py
  - CHANGE: compute_sheathing_bounds() — no code change needed if legacy
    adjustments are emitted correctly (exterior EXTENDS for primary,
    TRIMS for secondary; interior TRIMS for primary, EXTENDS for secondary)
  - VERIFY: The existing face -> layer_name mapping works with corrected adjustments
  - TEST: L-corner sheathing no longer overlaps

Task 5: Update __init__.py exports
  - MODIFY: src/timber_framing_generator/wall_junctions/__init__.py
  - ADD: Export LayerFunction, LayerSide, WallLayer, WallAssemblyDef

Task 6: Write tests
  - MODIFY: tests/wall_junctions/test_junction_resolver.py
    - ADD: test_butt_adjustments_crossed_pattern_l_corner
    - ADD: test_butt_adjustments_primary_exterior_extends
    - ADD: test_butt_adjustments_primary_interior_trims
    - ADD: test_butt_adjustments_secondary_interior_extends
    - ADD: test_t_intersection_all_layers_trim (unchanged behavior)
  - CREATE: tests/wall_junctions/test_wall_assembly.py
    - ADD: test_assembly_total_thickness
    - ADD: test_assembly_layers_by_side
    - ADD: test_assembly_to_legacy_layer_info
    - ADD: test_get_assembly_for_wall_lookup
    - ADD: test_default_assemblies_match_expected_thicknesses
  - MIRROR pattern from: tests/wall_junctions/conftest.py (mock wall fixtures)
```

### Pseudocode (with CRITICAL details)

```python
# Task 3: Fixed _calculate_butt_adjustments (crossed pattern)
# This replaces the WRONG implementation in junction_resolver.py

def _calculate_butt_adjustments(
    junction_id: str,
    primary: WallConnection,
    secondary: WallConnection,
    primary_layers: WallLayerInfo,
    secondary_layers: WallLayerInfo,
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments for a butt join.

    CROSSED PATTERN:
      Primary wall:
        - core:     EXTEND by secondary.core / 2
        - exterior: EXTEND by secondary.total / 2 (wraps outside corner)
        - interior: TRIM by secondary.core / 2 (secondary's interior covers this)

      Secondary wall:
        - core:     TRIM by primary.core / 2
        - exterior: TRIM by primary.core / 2 (butts against primary exterior)
        - interior: EXTEND by primary.total / 2 (wraps inside corner)
    """
    adjustments = []

    half_sec_core = secondary_layers.core_thickness / 2.0
    half_sec_total = secondary_layers.total_thickness / 2.0
    half_pri_core = primary_layers.core_thickness / 2.0
    half_pri_total = primary_layers.total_thickness / 2.0

    # PRIMARY: exterior extends, core extends, interior TRIMS
    for layer_name, adj_type, amount in [
        ("core", AdjustmentType.EXTEND, half_sec_core),
        ("exterior", AdjustmentType.EXTEND, half_sec_total),
        ("interior", AdjustmentType.TRIM, half_sec_core),   # CHANGED: was EXTEND
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # SECONDARY: exterior trims, core trims, interior EXTENDS
    for layer_name, adj_type, amount in [
        ("core", AdjustmentType.TRIM, half_pri_core),
        ("exterior", AdjustmentType.TRIM, half_pri_core),
        ("interior", AdjustmentType.EXTEND, half_pri_total),  # CHANGED: was TRIM
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=primary.wall_id,
        ))

    return adjustments
```

### Integration Points

```yaml
CONFIG:
  - file: src/timber_framing_generator/config/assembly.py
    pattern: "Add WALL_ASSEMBLIES catalog alongside existing WALL_ASSEMBLY"
    effect: "Both old and new assembly formats coexist"

JUNCTION TYPES:
  - file: src/timber_framing_generator/wall_junctions/junction_types.py
    pattern: "Add new enums/dataclasses, preserve all existing types"
    effect: "WallLayerInfo still works for backward compatibility"

JUNCTION RESOLVER:
  - file: src/timber_framing_generator/wall_junctions/junction_resolver.py
    pattern: "Fix _calculate_butt_adjustments crossed pattern"
    effect: "Immediate fix for sheathing overlap at corners"

SHEATHING:
  - file: scripts/gh_sheathing_generator.py
    pattern: "compute_sheathing_bounds reads layer_name in ('exterior', 'interior')"
    effect: "Works immediately with corrected legacy adjustments"

DOWNSTREAM (future, NOT in this PRP):
  - Insulation Generator: Read thermal/air layer adjustments
  - Drywall Generator: Read finish/interior layer adjustments
  - Cladding Generator: Read finish/exterior layer adjustments
  - Revit Extraction: Populate WallAssemblyDef from CompoundStructure
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Compile check
python -m py_compile src/timber_framing_generator/wall_junctions/junction_types.py
python -m py_compile src/timber_framing_generator/wall_junctions/junction_resolver.py
python -m py_compile src/timber_framing_generator/config/assembly.py

# Linting
ruff check src/timber_framing_generator/wall_junctions/
ruff check src/timber_framing_generator/config/assembly.py

# Type checking
mypy src/timber_framing_generator/wall_junctions/
```

### Level 2: Unit Tests

```bash
# Run junction tests (includes new crossed pattern tests)
pytest tests/wall_junctions/ -v

# Run assembly tests
pytest tests/wall_junctions/test_wall_assembly.py -v

# Run ALL tests to verify no regressions
pytest tests/ -v
```

```python
# KEY TEST: Crossed pattern at L-corner
def test_butt_adjustments_crossed_pattern():
    """Primary exterior extends, primary interior TRIMS.
    Secondary exterior trims, secondary interior EXTENDS."""
    primary = WallConnection(
        wall_id="wall_A", end="end",
        direction=(1, 0, 0), angle_at_junction=0.0,
        wall_thickness=0.3958, wall_length=20.0
    )
    secondary = WallConnection(
        wall_id="wall_B", end="start",
        direction=(0, 1, 0), angle_at_junction=90.0,
        wall_thickness=0.3958, wall_length=15.0
    )
    layers = build_default_wall_layers("test", 0.3958)

    adjustments = _calculate_butt_adjustments(
        "j0", primary, secondary, layers, layers
    )

    # Primary wall adjustments
    pri_adjs = {a.layer_name: a for a in adjustments if a.wall_id == "wall_A"}
    assert pri_adjs["core"].adjustment_type == AdjustmentType.EXTEND
    assert pri_adjs["exterior"].adjustment_type == AdjustmentType.EXTEND
    assert pri_adjs["interior"].adjustment_type == AdjustmentType.TRIM   # KEY CHANGE

    # Secondary wall adjustments
    sec_adjs = {a.layer_name: a for a in adjustments if a.wall_id == "wall_B"}
    assert sec_adjs["core"].adjustment_type == AdjustmentType.TRIM
    assert sec_adjs["exterior"].adjustment_type == AdjustmentType.TRIM
    assert sec_adjs["interior"].adjustment_type == AdjustmentType.EXTEND  # KEY CHANGE
```

### Level 3: Integration Test (Grasshopper)

```
Manual test in Grasshopper:
1. Open Rhino with Grasshopper
2. Connect Wall Analyzer -> Junction Analyzer -> Sheathing Generator
3. Select walls forming an L-corner
4. VERIFY: Exterior sheathing of primary wall extends past corner (no overlap)
5. VERIFY: Interior sheathing of secondary wall extends to cover inside corner
6. VERIFY: No sheathing overlap at any junction
7. Select walls forming a T-intersection
8. VERIFY: Terminating wall sheathing trims cleanly
9. VERIFY: Continuous wall sheathing is unmodified
```

---

## Final Checklist

- [ ] `LayerFunction`, `LayerSide` enums added to junction_types.py
- [ ] `WallLayer`, `WallAssemblyDef` dataclasses added to junction_types.py
- [ ] `WallLayerInfo` preserved as backward-compatible type
- [ ] `WALL_ASSEMBLIES` catalog added to config/assembly.py
- [ ] `_calculate_butt_adjustments` fixed with crossed pattern
- [ ] Legacy 3-name adjustments emitted for backward compatibility
- [ ] `compute_sheathing_bounds` works correctly with corrected adjustments
- [ ] All existing tests pass: `pytest tests/ -v`
- [ ] New tests cover crossed pattern: primary ext extends, pri int trims
- [ ] New tests cover secondary: sec ext trims, sec int extends
- [ ] T-intersection unchanged: all terminating layers trim
- [ ] Assembly catalog has 2x4 exterior, 2x6 exterior, 2x4 interior defaults
- [ ] No breaking changes to downstream consumers

---

## Anti-Patterns to Avoid

- Do not remove `WallLayerInfo` -- it's used throughout the codebase and must remain as a backward-compatible wrapper
- Do not change the `LayerAdjustment.layer_name` field type -- it stays as `str` to support both legacy names and specific layer names
- Do not modify T-intersection logic -- it's correct (all terminating layers trim)
- Do not add Revit CompoundStructure extraction in this PRP -- that's Phase 2
- Do not change the `analyze_junctions()` function signature -- it's the public API
- Do not modify sheathing_geometry.py W-offset calculation -- that's Phase 3 (proper layer stacking)
- Do not add manufacturer rules engine in this PRP -- that's a future PRP

---

## Notes

### Implementation Phases

| Phase | PRP | Scope |
|-------|-----|-------|
| **Phase 1 (this PRP)** | PRP-024 | Multi-layer data models + fix crossed pattern + default assemblies |
| Phase 2 (future) | PRP-025 | Revit CompoundStructure extraction in wall analyzer |
| Phase 3 (future) | PRP-026 | Layer-aware W-offset stacking in sheathing_geometry.py |
| Phase 4 (future) | PRP-027 | Manufacturer rules engine for per-layer placement rules |
| Phase 5 (future) | PRP-028+ | Additional layer generators (insulation, drywall, cladding) |

### Why Fix Crossed Pattern First (Task 3)

The crossed pattern fix is the **highest-value, lowest-effort** change:
- It only modifies `_calculate_butt_adjustments` (one function, ~30 lines)
- It immediately fixes the sheathing overlap visible in Grasshopper
- It requires NO changes to downstream consumers (legacy 3-name format works)
- It can be done independently of the multi-layer assembly system

**Recommendation**: Implement Task 3 first and verify in Grasshopper before proceeding to Tasks 1-2.

### Research References

- **Revit Layer Functions**: Structure [1] > Substrate [2] > Thermal [3] > Membrane [4] > Finish [5]
- **IFC IfcMaterialLayer**: Priority [0-100], IfcRelConnectsPathElements for junction override
- **IRC R602.10**: 24" minimum return corner for continuous sheathing braced wall lines
- **APA E30**: 1/2" min bearing on framing, 3/8" edge distance, 1/16" panel gap
- **GA-216**: Gypsum board joints prohibited within 12" of opening corners
- **Revit 2026**: Custom layer priority (independent from function), optional core layer
