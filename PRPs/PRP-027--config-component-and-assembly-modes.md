# PRP-027: Config Component & Assembly Mode Consolidation

> **Version:** 1.0
> **Created:** 2026-02-08
> **Status:** Draft
> **Branch:** feature/sheathing-junctions
> **Depends on:** PRP-025 (Assembly Resolution Strategy)

---

## Goal

Create a dedicated **GHPython Config Component** that provides a user-friendly interface for configuring the sheathing and framing pipeline. This component replaces manual JSON authoring with named inputs, outputs a shared `config_json` consumed by both the **Framing Generator** and **Multi-Layer Sheathing** components, and introduces a `framing_system` parameter (`"timber"` / `"cfs"`) so the tool correctly interprets wall thickness for any building system.

---

## Why

### Business Value
- **User-friendly**: Most users don't understand JSON. Named inputs with descriptions are discoverable and self-documenting in Grasshopper.
- **Single source of truth**: One config component feeds both Framing Generator and MLSheath, eliminating the risk of mismatched settings between the two.
- **Material-system-aware**: The tool currently assumes timber framing. CFS studs have different depths for the same nominal wall thickness. Without `framing_system`, CFS walls get wrong assemblies and wrong framing depths.
- **Schematic design support**: Architects model walls at varying levels of detail. The `assembly_mode` setting lets users tell the tool how to interpret their model ("trust Revit exactly" vs "propose assemblies for me").

### Technical Requirements
- **Backward compatible**: All new inputs have sensible defaults. Existing GH definitions that don't use the Config Component still work — Framing Generator and MLSheath fall back to their current defaults when `config_json` is absent or empty.
- **Two assembly modes**: `"auto"` (tool proposes from catalog, current default behavior) and `"revit"` (trust Revit CompoundStructure, user overrides only).
- **Framing system mapping**: Wall thickness → nominal framing depth via material-specific lookup tables (timber midpoints differ from CFS midpoints).
- **Assembly overrides**: Per-Wall-Type custom assembly mapping, usable in both modes to override individual wall types.

### Problems Solved
1. **CFS thickness mismatch**: A 4" wall with CFS framing should get 400S studs (4.0" depth), not 2x4 lumber (3.5" depth). Currently the system always assumes timber.
2. **No centralized config**: `assembly_mode` and `custom_map` live as separate inputs on MLSheath but are absent from Framing Generator. The framing system has no way to receive these settings.
3. **JSON authoring friction**: Users must hand-write `config_json` to set panel sizes, faces, include_functions. A visual component with named inputs removes this barrier.
4. **Framing Generator blind to assembly mode**: The mode affects framing depth (e.g., "revit" mode should read actual stud depth from Revit's CompoundStructure, not guess from wall thickness). Currently Framing Generator has no access to this setting.

---

## What

### New Component: Config Builder (`ConfBuild`)

A GHPython component in the **Timber Framing** > **0-Config** subcategory.

#### Inputs

| Index | Name | NickName | Type | Default | Description |
|-------|------|----------|------|---------|-------------|
| 0 | Assembly Mode | assembly_mode | str | `"auto"` | `"auto"` = tool proposes assemblies from catalog; `"revit"` = trust Revit CompoundStructure |
| 1 | Framing System | framing_system | str | `"timber"` | `"timber"` or `"cfs"` — determines thickness-to-depth mapping tables |
| 2 | Assembly Overrides | assembly_overrides | str | `None` | Optional JSON: per-Wall-Type assembly mapping. Keys = Revit Wall Type names, values = catalog keys or inline assembly dicts |
| 3 | Faces | faces | str list | `["exterior", "interior"]` | Which wall faces to generate sheathing for. Access: List |
| 4 | Panel Size | panel_size | str | `"4x8"` | Default panel size for all layers (e.g., "4x8", "4x10", "4x12") |
| 5 | Stud Spacing | stud_spacing | float | `16.0` | Stud spacing in inches on-center (16 or 24 typical) |
| 6 | Include Functions | include_functions | str list | `None` | Optional filter: which layer functions to generate (e.g., ["substrate", "finish"]). `None` = all panelizable. Access: List |
| 7 | Layer Configs | layer_configs | str | `None` | Optional JSON with per-layer config overrides keyed by layer name |

#### Outputs

| Index | Name | NickName | Description |
|-------|------|----------|-------------|
| 0 | out | out | GH internal console output |
| 1 | Config JSON | config_json | Serialized JSON string for downstream components |

#### Behavior

The component collects all inputs, builds a Python dict, and serializes to JSON:

```python
config = {
    "assembly_mode": assembly_mode or "auto",
    "framing_system": framing_system or "timber",
    "panel_size": panel_size or "4x8",
    "faces": faces or ["exterior", "interior"],
    "stud_spacing": stud_spacing or 16.0,
}

# Only include optional keys when provided
if assembly_overrides:
    config["assembly_overrides"] = json.loads(assembly_overrides)
if include_functions:
    config["include_functions"] = include_functions
if layer_configs:
    config["layer_configs"] = json.loads(layer_configs)

config_json = json.dumps(config, indent=2)
```

### Assembly Modes (Simplified from PRP-025)

PRP-025 proposed 4 modes (`auto`, `revit_only`, `catalog`, `custom`). This PRP simplifies to **2 modes** + overrides:

| Mode | Behavior | When to Use |
|------|----------|-------------|
| **`auto`** (default) | Tool proposes assembly from catalog using: wall type name match > framing hint > thickness inference > default | Schematic design, undeveloped models, quick explorations |
| **`revit`** | Trust Revit CompoundStructure as-is. Walls without CompoundStructure get a warning and fall back to `auto` behavior | Developed models with verified assemblies |

Both modes support `assembly_overrides` — a per-Wall-Type mapping that takes priority over the mode's default behavior. This replaces PRP-025's separate `"custom"` mode.

**Resolution priority (both modes)**:
1. `assembly_overrides[wall_type_name]` (if present) — confidence 1.0
2. Mode-specific resolution (see below)

**`"auto"` resolution chain** (unchanged from current):
1. Revit CompoundStructure (if valid multi-layer) — confidence 1.0
2. Catalog name match (wall type keywords) — confidence 0.6-0.9
3. Framing hint (from framing_json depth) — confidence 0.85
4. Thickness inference (nearest lumber/CFS size) — confidence 0.3-0.5
5. Default fallback (2x4_exterior or 2x4_interior) — confidence 0.1-0.2

**`"revit"` resolution chain**:
1. Revit CompoundStructure — confidence 1.0
2. Warning + fallback to `auto` chain if no CompoundStructure

### Framing System: Thickness → Depth Mapping

Wall thickness (in schematic models) is interpreted as the **nominal framing size**. The mapping from thickness to actual framing depth depends on the framing system.

#### Timber Mapping Table

Uses midpoint boundaries between consecutive lumber depths:

| Revit Thickness | Nearest Nominal | Actual Depth | Boundary |
|-----------------|-----------------|--------------|----------|
| < 3.0" | 2x3 | 2.5" | — |
| 3.0" – 4.49" | 2x4 | 3.5" | midpoint(2.5, 3.5) = 3.0 |
| 4.5" – 6.49" | 2x6 | 5.5" | midpoint(3.5, 5.5) = 4.5 |
| 6.5" – 8.74" | 2x8 | 7.25" | midpoint(5.5, 7.25) = 6.375 → round to 6.5 |
| 8.75" – 10.49" | 2x10 | 9.25" | midpoint(7.25, 9.25) = 8.25 → round to 8.75 |
| 10.5" – 12.49" | 2x12 | 11.25" | midpoint(9.25, 11.25) = 10.25 → round to 10.5 |
| >= 12.5" | 2x12 (cap) | 11.25" | — |

This logic already exists in `assembly_resolver.py` as `_nearest_lumber_size()` (implemented in PRP-025). No changes needed for timber.

#### CFS Mapping Table

CFS studs use nominal web depth = actual web depth (no undersizing like timber):

| Revit Thickness | Nearest CFS | Actual Depth |
|-----------------|-------------|--------------|
| < 3.0" | 250S | 2.5" |
| 3.0" – 3.74" | 350S | 3.5" |
| 3.75" – 4.99" | 400S | 4.0" |
| 5.0" – 5.49" | 550S | 5.5" |
| 5.5" – 6.99" | 600S | 6.0" |
| 7.0" – 7.99" | 800S | 8.0" |
| >= 8.0" | 1000S | 10.0" |

**Key difference**: A 4" wall → 3.5" framing depth (timber) vs 4.0" framing depth (CFS). This affects:
- **Assembly resolution**: Which catalog assembly is selected
- **W-offset computation**: Sheathing layer positioning depends on framing depth
- **Framing element generation**: Profile dimensions in framing_json

#### Implementation Location

New function in `assembly_resolver.py`:

```python
def _nearest_framing_depth(thickness_inches: float, framing_system: str = "timber") -> float:
    """Map wall thickness to nearest actual framing depth.

    Args:
        thickness_inches: Wall thickness in inches.
        framing_system: "timber" or "cfs".

    Returns:
        Actual framing depth in inches.
    """
    if framing_system == "cfs":
        return _nearest_cfs_depth(thickness_inches)
    else:
        return _nearest_lumber_size(thickness_inches)  # existing function
```

### Pipeline Diagram

```
                    +-----------------------+
                    |   Config Builder      |
                    |   (NEW component)     |
                    |                       |
  assembly_mode  -->|                       |
  framing_system -->|   Builds config_json  |--> config_json
  assembly_overrides>|                      |
  faces          -->|                       |
  panel_size     -->|                       |
  stud_spacing   -->|                       |
  include_funcs  -->|                       |
  layer_configs  -->|                       |
                    +-----------------------+
                              |
                    +---------+---------+
                    |                   |
                    v                   v
        +-------------------+   +-------------------+
        | Framing Generator |   | ML Sheathing      |
        | (gh_framing_      |   | (gh_multi_layer_  |
        |  generator.py)    |   |  sheathing.py)    |
        |                   |   |                   |
        | Reads:            |   | Reads:            |
        | - framing_system  |   | - assembly_mode   |
        | - stud_spacing    |   | - framing_system  |
        | - assembly_mode   |   | - assembly_overrides |
        |                   |   | - faces           |
        +-------------------+   | - panel_size      |
                |               | - include_functions|
                v               | - layer_configs   |
          framing_json          +-------------------+
                |                       |
                +--------->  MLSheath   |
                (existing    also reads |
                 connection) framing_json
                             for depth  |
                                        v
                                multi_layer_json
```

### Changes to Existing Components

#### 1. Multi-Layer Sheathing (`gh_multi_layer_sheathing.py`)

**Remove** the standalone `assembly_mode` (index 3) and `custom_map` (index 4) inputs. These move into `config_json` via the Config Builder.

**New input layout** (reduces from 7 to 5 inputs):

| Index | Name | NickName | Description |
|-------|------|----------|-------------|
| 0 | Walls JSON | walls_json | Wall data from Wall Analyzer |
| 1 | Junctions JSON | junctions_json | Optional junction adjustments |
| 2 | Config JSON | config_json | From Config Builder (or manual JSON) |
| 3 | Framing JSON | framing_json | Optional framing data for depth detection |
| 4 | Run | run | Execution trigger |

**`parse_config()` changes**:
- Read `assembly_mode` from config dict (default `"auto"`)
- Read `framing_system` from config dict (default `"timber"`)
- Read `assembly_overrides` from config dict (replaces `custom_map`)
- Existing keys (`faces`, `panel_size`, `include_functions`, `layer_configs`, `framing_depth`) remain unchanged

**`process_walls()` changes**:
- Replace `custom_map` parameter with `assembly_overrides`
- Pass `framing_system` to `resolve_all_walls()` and `_nearest_framing_depth()`
- When `assembly_mode="revit"` and a wall lacks CompoundStructure, log warning and fall back to auto

#### 2. Framing Generator (`gh_framing_generator.py`)

**Current inputs** (no change to count):

| Index | Name | NickName | Description |
|-------|------|----------|-------------|
| 0 | Cell JSON | cell_json | Cell decomposition data |
| 1 | Walls JSON | walls_json | Wall geometry data |
| 2 | Material Type | material_type | "timber" or "cfs" |
| 3 | Config JSON | config_json | Configuration overrides |
| 4 | Run | run | Execution trigger |

**Changes in `main()`**:
- Parse `framing_system` from `config_json` — if present, **override** the `material_type` input with it. This ensures the Config Builder's `framing_system` takes precedence while keeping `material_type` as a fallback for users who don't use Config Builder.
- Parse `stud_spacing` from `config_json` — pass to strategy as config param.
- Parse `assembly_mode` from `config_json` — when `"revit"`, use wall's CompoundStructure to determine framing depth rather than inferring from thickness.

#### 3. Assembly Resolver (`assembly_resolver.py`)

**Add `framing_system` parameter** to:
- `resolve_all_walls(walls_data, mode, custom_map, framing_system)`
- `_resolve_auto(wall_data, framing_system)` — calls `_nearest_framing_depth()` with correct system
- `_infer_assembly_from_thickness(wall_data, framing_system)` — uses system-specific mapping

**Add `_nearest_cfs_depth(thickness_inches)`** — CFS midpoint mapping table.

**Rename `custom_map` → `assembly_overrides`** throughout — aligns with new naming.

### Scenario D Documentation (Future)

> **Not implemented in this PRP.** Documented for future reference.
>
> **Problem**: When the same wall thickness can be framed with either timber or CFS, the tool needs a way to know which system to use. Currently `framing_system` is set globally. A future enhancement could support per-wall or per-wall-type framing system selection.
>
> **Example**: A 4" wall could be 2x4 timber (3.5" actual) or 400S CFS (4.0" actual). Different framing depths mean different sheathing W-offsets.
>
> **Possible future solution**: Extend `assembly_overrides` to include a `framing_system` key per wall type:
> ```json
> {
>     "Basic Wall - 4\" Exterior": {
>         "framing_system": "cfs",
>         "assembly": "cfs_400s_exterior"
>     }
> }
> ```
>
> This is deferred until CFS assembly catalogs and strategies are fully developed.

### Success Criteria

- [ ] New `gh_config_builder.py` component with 8 inputs and 1 JSON output
- [ ] Config JSON consumed by both Framing Generator and MLSheath
- [ ] `assembly_mode` and `custom_map` removed as standalone MLSheath inputs
- [ ] `framing_system` parameter propagates through assembly resolution
- [ ] `_nearest_cfs_depth()` mapping table implemented in `assembly_resolver.py`
- [ ] Framing Generator reads `framing_system` and `stud_spacing` from config_json
- [ ] Both `"auto"` and `"revit"` modes work correctly
- [ ] `assembly_overrides` works in both modes
- [ ] Existing tests pass (backward compatible when config_json is absent)
- [ ] New tests for CFS mapping, config builder serialization, and mode behavior

---

## All Needed Context

### Documentation & References

```yaml
- PRPs/PRP-025--assembly-resolution-strategy.md  # why: original assembly mode design (being simplified)
- docs/ai/ai-modular-architecture-plan.md        # why: overall component architecture
- docs/ai/ai-coordinate-system-reference.md      # why: UVW system for W-offset computation
```

### Current Codebase Structure

```
scripts/
  gh_framing_generator.py       # Inputs: cell_json, walls_json, material_type, config_json, run
  gh_multi_layer_sheathing.py   # Inputs: walls_json, junctions_json, config_json, assembly_mode, custom_map, framing_json, run
  gh_sheathing_geometry_converter.py  # Downstream: reads multi_layer_json
  gh_junction_analyzer.py       # Upstream: produces junctions_json
  gh_config_builder.py          # NEW: produces config_json

src/timber_framing_generator/
  config/
    assembly.py                 # WALL_ASSEMBLIES catalog, get_assembly_for_wall()
    assembly_resolver.py        # resolve_all_walls(), _nearest_lumber_size()
  sheathing/
    multi_layer_generator.py    # generate_assembly_layers(), extract_max_framing_depth()
    sheathing_geometry.py       # calculate_layer_w_offsets()
  core/
    material_system.py          # MaterialSystem enum, get_framing_strategy()
  materials/
    timber/                     # Timber strategy + profiles
    cfs/                        # CFS strategy + profiles
```

### Known Gotchas

1. **GH input index stability**: Removing `assembly_mode` (index 3) and `custom_map` (index 4) from MLSheath shifts `framing_json` from index 5 to 3 and `run` from index 6 to 4. Existing GH definitions referencing old indices will break. Users must reconnect wires after updating.

2. **`material_type` vs `framing_system`**: Framing Generator currently has a standalone `material_type` input. The Config Builder's `framing_system` should override it when present in config_json, but `material_type` remains as a direct fallback for backward compatibility.

3. **CFS strategy registration**: The CFS strategy module must be imported before use. Currently only timber is imported in `gh_framing_generator.py`. When `framing_system="cfs"`, the component must import `from src.timber_framing_generator.materials import cfs`.

4. **Assembly overrides JSON format**: The overrides dict values can be either string catalog keys or inline assembly dicts (same as PRP-025's custom mode). The Config Builder passes this through as-is; validation happens in `assembly_resolver.py`.

---

## Implementation Blueprint

### Phase 1: CFS Depth Mapping

**File**: `src/timber_framing_generator/config/assembly_resolver.py`

Add CFS-specific mapping alongside existing `_nearest_lumber_size()`:

```python
# CFS standard web depths (inches)
_CFS_DEPTHS = [2.5, 3.5, 4.0, 5.5, 6.0, 8.0, 10.0]

def _nearest_cfs_depth(thickness_inches: float) -> float:
    """Map wall thickness to nearest CFS stud web depth using midpoints."""
    if thickness_inches <= 0:
        return 3.5  # default
    best = _CFS_DEPTHS[0]
    for i in range(1, len(_CFS_DEPTHS)):
        midpoint = (_CFS_DEPTHS[i - 1] + _CFS_DEPTHS[i]) / 2
        if thickness_inches >= midpoint:
            best = _CFS_DEPTHS[i]
        else:
            break
    return best


def _nearest_framing_depth(thickness_inches: float, framing_system: str = "timber") -> float:
    """Map wall thickness to actual framing depth for the given system."""
    if framing_system == "cfs":
        return _nearest_cfs_depth(thickness_inches)
    return _nearest_lumber_size(thickness_inches)
```

Add `framing_system` parameter to `resolve_all_walls()` and its callees.

### Phase 2: Config Builder Component

**New file**: `scripts/gh_config_builder.py`

Follows the standard GHPython template:

```python
def setup_component():
    # 8 inputs: assembly_mode, framing_system, assembly_overrides,
    #           faces, panel_size, stud_spacing, include_functions, layer_configs
    # 1 output: config_json (index 1)
    ...

def build_config(assembly_mode, framing_system, assembly_overrides,
                 faces, panel_size, stud_spacing, include_functions, layer_configs):
    """Build config dict from individual inputs."""
    config = {
        "assembly_mode": (assembly_mode or "auto").strip().lower(),
        "framing_system": (framing_system or "timber").strip().lower(),
        "panel_size": panel_size or "4x8",
        "stud_spacing": float(stud_spacing) if stud_spacing else 16.0,
    }

    # Faces: accept list input or default
    if faces:
        config["faces"] = list(faces) if not isinstance(faces, list) else faces
    else:
        config["faces"] = ["exterior", "interior"]

    # Optional keys
    if assembly_overrides and str(assembly_overrides).strip():
        config["assembly_overrides"] = json.loads(str(assembly_overrides))

    if include_functions:
        funcs = list(include_functions) if not isinstance(include_functions, list) else include_functions
        if funcs:
            config["include_functions"] = funcs

    if layer_configs and str(layer_configs).strip():
        config["layer_configs"] = json.loads(str(layer_configs))

    return config

def main():
    setup_component()
    config = build_config(...)
    config_json = json.dumps(config, indent=2)
    return config_json
```

### Phase 3: MLSheath Input Consolidation

**File**: `scripts/gh_multi_layer_sheathing.py`

1. Remove `assembly_mode` and `custom_map` from `input_config` (indices 3-4)
2. Shift `framing_json` to index 3, `run` to index 4
3. Update `parse_config()` to extract new keys:

```python
def parse_config(config_json):
    # ... existing logic ...
    assembly_mode = "auto"
    framing_system = "timber"
    assembly_overrides = None

    if user_config:
        if "assembly_mode" in user_config:
            assembly_mode = user_config.pop("assembly_mode")
        if "framing_system" in user_config:
            framing_system = user_config.pop("framing_system")
        if "assembly_overrides" in user_config:
            assembly_overrides = user_config.pop("assembly_overrides")
        if "stud_spacing" in user_config:
            user_config.pop("stud_spacing")  # Not used by MLSheath, remove to avoid pass-through noise

    return base_config, layer_configs, include_functions, framing_depth, assembly_mode, framing_system, assembly_overrides
```

4. Update `process_walls()` signature and pass `framing_system` to resolver
5. Update `main()` to read from config instead of separate inputs

### Phase 4: Framing Generator Config Integration

**File**: `scripts/gh_framing_generator.py`

1. In `main()`, after parsing `config_json`:

```python
config = json.loads(config_json_input) if config_json_input else {}

# Config Builder overrides for material type
framing_system = config.get("framing_system")
if framing_system:
    material_type_val = framing_system  # Override material_type input
else:
    material_type_val = material_type if material_type else "timber"

# Stud spacing from config
stud_spacing = config.get("stud_spacing", 16.0)
config["stud_spacing"] = stud_spacing  # Ensure it's in the config dict passed to strategy
```

2. Import CFS strategy when needed:

```python
if material_type_val == "cfs":
    from src.timber_framing_generator.materials import cfs  # noqa: F401
```

### Phase 5: Tests

**New tests in** `tests/config/test_assembly_resolver.py`:

```yaml
- TestNearestCfsDepth:
    - test_4_inch_wall_cfs: 4.0" → 4.0" (400S)
    - test_4_inch_wall_timber: 4.0" → 3.5" (2x4)
    - test_6_inch_wall_cfs: 6.0" → 6.0" (600S)
    - test_6_inch_wall_timber: 6.0" → 5.5" (2x6)
    - test_3_5_inch_wall_cfs: 3.5" → 3.5" (350S)
    - test_8_inch_wall_cfs: 8.0" → 8.0" (800S)
    - test_boundary_cfs_3_75: 3.75" → 4.0" (above 350S-400S midpoint)
    - test_below_minimum: 1.0" → 2.5" (smallest available)

- TestFramingSystemInPipeline:
    - test_auto_mode_timber_default: No framing_system → timber mapping
    - test_auto_mode_cfs_explicit: framing_system="cfs" → CFS mapping
    - test_revit_mode_ignores_system: "revit" mode uses CompoundStructure regardless
    - test_assembly_overrides_both_modes: Overrides take priority in both modes
```

**New tests in** `tests/sheathing/test_config_builder.py`:

```yaml
- TestConfigBuilder:
    - test_default_config: No inputs → sensible defaults
    - test_all_inputs: All inputs provided → correct JSON
    - test_assembly_overrides_json: Valid JSON string parsed correctly
    - test_invalid_overrides_json: Invalid JSON → error handling
    - test_faces_list: List input → list in JSON
    - test_optional_keys_absent: Absent optional keys not in output
```

### Tasks (Execution Order)

```yaml
tasks:
  - id: 1
    title: "Add _nearest_cfs_depth() and _nearest_framing_depth() to assembly_resolver.py"
    details: "CFS mapping table + unified dispatch function + framing_system param on resolve_all_walls()"
    files:
      - src/timber_framing_generator/config/assembly_resolver.py

  - id: 2
    title: "Write tests for CFS depth mapping"
    details: "TestNearestCfsDepth and TestFramingSystemInPipeline test classes"
    files:
      - tests/config/test_assembly_resolver.py

  - id: 3
    title: "Create gh_config_builder.py component"
    details: "New GHPython component with 8 inputs, 1 JSON output, follows template"
    files:
      - scripts/gh_config_builder.py (new)

  - id: 4
    title: "Update MLSheath to read config keys instead of standalone inputs"
    details: "Remove assembly_mode/custom_map inputs, read from config_json, add framing_system support"
    files:
      - scripts/gh_multi_layer_sheathing.py

  - id: 5
    title: "Update Framing Generator to read framing_system from config_json"
    details: "Override material_type with framing_system when present, import CFS strategy dynamically"
    files:
      - scripts/gh_framing_generator.py

  - id: 6
    title: "Rename custom_map → assembly_overrides in assembly_resolver.py"
    details: "Consistent naming across the codebase"
    files:
      - src/timber_framing_generator/config/assembly_resolver.py

  - id: 7
    title: "Write Config Builder unit tests"
    details: "TestConfigBuilder class — serialization, defaults, validation"
    files:
      - tests/sheathing/test_config_builder.py (new)

  - id: 8
    title: "Update MLSheath and resolver tests for new signatures"
    details: "Existing tests must pass with updated function signatures"
    files:
      - tests/sheathing/test_multi_layer_generator.py
      - tests/config/test_assembly_resolver.py
```

---

## Validation Loop

### Level 1: Unit Tests

```bash
# CFS mapping + framing_system
pytest tests/config/test_assembly_resolver.py -v -k "cfs or framing_system"

# Config builder
pytest tests/sheathing/test_config_builder.py -v

# Existing tests (regression)
pytest tests/ -v --ignore=tests/api --ignore=tests/integration
```

### Level 2: Integration Check

- Verify `resolve_all_walls()` with `framing_system="cfs"` produces different depths than `"timber"` for the same wall thickness
- Verify `parse_config()` in MLSheath correctly extracts all new keys
- Verify Framing Generator overrides `material_type` when `framing_system` is in config

### Level 3: Grasshopper Validation

1. Place Config Builder component on canvas
2. Set `assembly_mode` = "auto", `framing_system` = "timber"
3. Connect `config_json` output to both Framing Generator and MLSheath
4. Run pipeline — verify same behavior as before (backward compatible)
5. Change `framing_system` to "cfs" — verify framing depths change
6. Change `assembly_mode` to "revit" — verify Revit assemblies are trusted
7. Add `assembly_overrides` JSON — verify specific wall types are overridden

---

## Final Checklist

- [ ] Config Builder component follows GHPython template from skill
- [ ] Config Builder outputs valid JSON with all provided settings
- [ ] MLSheath reads `assembly_mode`, `framing_system`, `assembly_overrides` from config_json
- [ ] MLSheath standalone `assembly_mode`/`custom_map` inputs removed
- [ ] Framing Generator reads `framing_system` from config_json
- [ ] `framing_system` propagates through assembly resolver
- [ ] CFS mapping table produces correct depths
- [ ] Timber mapping unchanged
- [ ] `assembly_overrides` works in both "auto" and "revit" modes
- [ ] All existing tests pass
- [ ] New tests cover CFS mapping, config builder, and mode behavior
- [ ] GH component versions incremented

---

## Anti-Patterns to Avoid

- **Don't break existing workflows**: Users without the Config Builder must still get sensible defaults. All new config keys have defaults.
- **Don't duplicate mode logic in GH scripts**: Assembly resolution lives in `assembly_resolver.py`. GH scripts pass parameters; they don't implement resolution logic.
- **Don't over-engineer the Config Builder**: It's a simple dict-to-JSON serializer. No validation beyond JSON parsing. Complex validation lives in the consuming components.
- **Don't add CFS assemblies to the catalog yet**: This PRP only adds the CFS depth mapping. Full CFS assembly definitions (layer stacks) are future work.
- **Don't remove `material_type` from Framing Generator**: Keep it as a backward-compatible fallback. `framing_system` from config_json overrides it when present.

---

## Notes

- **Scope boundary**: This PRP covers the Config Component, mode consolidation, and CFS depth mapping. It does NOT implement CFS-specific assembly catalog entries, CFS framing strategies, or per-wall-type framing system selection (Scenario D).
- **MLSheath input count change**: Reducing from 7 to 5 inputs is a breaking change for existing GH definitions. The GH file must be updated after deploying this change.
- **Version bumps**: Config Builder v1.0, MLSheath v2.2, Framing Generator v1.2.

---

## References

- `PRPs/PRP-025--assembly-resolution-strategy.md` — Original 4-mode design (simplified here to 2 modes + overrides)
- `src/timber_framing_generator/config/assembly_resolver.py` — Assembly resolution logic
- `src/timber_framing_generator/config/assembly.py` — Assembly catalog
- `scripts/gh_multi_layer_sheathing.py` — Current MLSheath with standalone assembly_mode/custom_map
- `scripts/gh_framing_generator.py` — Current Framing Generator with material_type input
