# PRP-025: Assembly Resolution Strategy

> **Version:** 1.0
> **Created:** 2026-02-05
> **Status:** Draft
> **Branch:** feature/assembly-resolution
> **Depends on:** PRP-024 (Wall Assembly Layers)

---

## Goal

Create a flexible assembly resolution system that handles the full spectrum of Revit wall model quality — from schematic single-layer walls to correctly modeled multi-layer CompoundStructures — by auto-detecting assembly quality, offering user-configurable override modes (including per-Wall-Type custom mappings), and reporting confidence levels so users always know which walls have reliable assemblies.

---

## Why

### Business Value
- **Works with any Revit model**: Users shouldn't need a perfectly modeled Revit file to get useful output. The system should gracefully handle schematic, single-layer, and incomplete wall models.
- **Per-Wall-Type customization**: Users organize Revit models by Wall Type. A "2x6 Exterior Insulated" type should map to the same assembly across all instances. This matches industry workflow.
- **Transparency builds trust**: When the system guesses an assembly, users need to know. Confidence scores and source annotations prevent silent incorrect output.
- **Scales from quick studies to production**: Schematic design uses "auto" mode with defaults. Production uses "revit_only" or "custom" mode with verified assemblies.

### Technical Requirements
- **Backward compatible**: Existing pipeline (Revit assembly -> catalog fallback -> default) continues working unchanged in "auto" mode
- **Per-Wall-Type mappings**: "custom" mode maps Revit Wall Type names to assembly definitions, not a single assembly for all walls
- **Assembly source tracking**: Every wall's output includes where its assembly came from and how confident the match is
- **GH-native UX**: Override mode is a Value List dropdown; custom mappings are a JSON input or panel

### Problems Solved
1. **Framing-only walls (scenario A)**: Wall width = stud depth only. No assembly info. Currently gets a default that may be wrong.
2. **Generic full-thickness walls (scenario B)**: Full width modeled but as single Core layer. Currently matched by `is_exterior` flag only.
3. **Schematic architect walls (scenario D)**: Arbitrary thickness, no meaningful assembly. Currently gets a random default.
4. **No user override path**: Users can't correct wrong assembly guesses without editing the Revit model.
5. **No visibility into assembly source**: Users can't tell which walls used Revit data vs. catalog guesses vs. defaults.

---

## What

### Assembly Quality Levels

When a wall enters the pipeline, classify its assembly data:

| Quality | Source | Description | Confidence |
|---------|--------|-------------|------------|
| `explicit` | Revit CompoundStructure | Real multi-layer assembly extracted from Revit API. Has function, side, material per layer. | 1.0 |
| `catalog` | Wall Type name match | Wall Type name matched against assembly catalog. May not be exact. | 0.6-0.9 |
| `inferred` | Thickness + is_exterior | No type match. Assembly guessed from wall thickness and exterior/interior flag. | 0.3-0.5 |
| `default` | Hardcoded fallback | No useful data. Used generic 2x4 exterior or interior default. | 0.1-0.2 |
| `custom` | User-provided | User explicitly mapped this Wall Type to an assembly. | 1.0 (user intent) |

### Assembly Override Modes

New dropdown input on Multi-Layer Sheathing component:

| Mode | Behavior | Best For |
|------|----------|----------|
| **`auto`** (default) | Use best available: explicit > catalog > inferred > default | Quick explorations, well-modeled files |
| **`revit_only`** | Only use Revit CompoundStructure. Skip walls without one. | Production runs with verified Revit models |
| **`catalog`** | Ignore Revit layers. Match Wall Type name to catalog. | Revit models with good type names but wrong/missing layers |
| **`custom`** | User provides per-Wall-Type assembly mapping. Unmapped types fall back to `auto`. | Full control, mixed-quality models |

### Custom Mode: Per-Wall-Type Mapping

The **`custom`** mode accepts a JSON dictionary mapping Revit Wall Type names to assembly definitions:

```json
{
    "Basic Wall - 2x6 Exterior": "2x6_exterior",
    "Basic Wall - 2x4 Interior": "2x4_interior",
    "CW 102-50-100p": {
        "name": "custom_cavity",
        "layers": [
            {"name": "Brick", "function": "finish", "side": "exterior", "thickness": 0.333},
            {"name": "Cavity Insulation", "function": "thermal", "side": "exterior", "thickness": 0.167},
            {"name": "Sheathing", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "Steel Studs", "function": "structure", "side": "core", "thickness": 0.5},
            {"name": "Gypsum", "function": "finish", "side": "interior", "thickness": 0.042}
        ]
    }
}
```

Values can be:
- **String**: Catalog assembly key (e.g., `"2x6_exterior"`) for quick mapping
- **Dict**: Full inline assembly definition for types not in the catalog

Unmapped Wall Types fall back to `auto` mode behavior.

### Catalog Matching Enhancement

Currently `WALL_ASSEMBLIES` has only 3 entries with rigid keys (`"2x4_exterior"`, `"2x6_exterior"`, `"2x4_interior"`). Revit Wall Type names look like `"Basic Wall - 2x6 Exterior"` or `"Generic - 6\" Interior"`. The catalog matching needs fuzzy lookup:

```
Revit Wall Type: "Basic Wall - 2x6 Exterior Insulated"
  -> Extract keywords: ["2x6", "exterior"]
  -> Match catalog: "2x6_exterior" (confidence: 0.8)

Revit Wall Type: "Generic - 4\" Interior Partition"
  -> Extract keywords: ["4", "interior", "partition"]
  -> Match catalog: "2x4_interior" (confidence: 0.7)

Revit Wall Type: "CW 102-50-100p"
  -> No keywords match
  -> Fall back to thickness + is_exterior inference (confidence: 0.3)
```

### Output Enrichment

Every wall's result includes assembly metadata:

```json
{
    "wall_id": "529398",
    "wall_type": "Basic Wall - 2x6 Exterior",
    "assembly_source": "catalog",
    "assembly_name": "2x6_exterior",
    "assembly_confidence": 0.8,
    "assembly_notes": "Matched by wall type keywords: 2x6, exterior",
    "layer_results": [...]
}
```

### Pipeline Diagram

```
                     walls_json (from Wall Analyzer)
                              |
                              v
                  +------------------------+
                  | Assembly Resolver      |
                  |                        |
  assembly_mode --+-> resolve_assembly()   |
  custom_map_json-+   per wall:            |
                  |   1. Check override mode|
                  |   2. Apply resolution   |
                  |   3. Set quality+conf   |
                  +------------------------+
                              |
                              v
                     enriched walls_json
                    (wall_assembly + metadata)
                              |
                              v
                  +------------------------+
                  | generate_assembly_layers|
                  | (existing, unchanged)  |
                  +------------------------+
                              |
                              v
                     multi_layer_json
                   (with assembly_source,
                    confidence per wall)
```

### Success Criteria

- [ ] `resolve_assembly()` function handles all 4 modes (auto, revit_only, catalog, custom)
- [ ] Custom mode accepts per-Wall-Type mappings (both string keys and inline dicts)
- [ ] Catalog matching uses keyword extraction for fuzzy Wall Type name matching
- [ ] Every wall result includes `assembly_source`, `assembly_confidence`, `assembly_notes`
- [ ] "auto" mode is backward-compatible with current `get_assembly_for_wall()` behavior
- [ ] "revit_only" mode skips walls without explicit CompoundStructure
- [ ] GH component has `assembly_mode` Value List input and `custom_map` JSON input
- [ ] Summary output shows assembly quality breakdown (e.g., "3 explicit, 2 catalog, 1 default")
- [ ] All existing tests continue passing

---

## All Needed Context

### Documentation & References

```yaml
- docs/ai/ai-modular-architecture-plan.md  # why: overall architecture
- docs/ai/ai-coordinate-system-reference.md  # why: UVW system for panel placement
- PRPs/PRP-024--wall-assembly-layers.md  # why: layer system this builds on
```

### Current Codebase Structure

```
src/timber_framing_generator/
  config/
    assembly.py                    # WALL_ASSEMBLIES catalog, get_assembly_for_wall()
  wall_junctions/
    junction_types.py              # WallAssemblyDef, WallLayer, LayerFunction, LayerSide
  wall_data/
    assembly_extractor.py          # assembly_dict_to_def() for Revit data
  sheathing/
    multi_layer_generator.py       # generate_assembly_layers() - layer panel generation
    sheathing_generator.py         # SheathingGenerator - core panel layout
    sheathing_geometry.py          # W offset calculation, brep creation

scripts/
  gh_wall_analyzer.py              # Extracts wall_type, wall_assembly from Revit
  gh_multi_layer_sheathing.py      # Multi-layer GH component (main consumer)
  gh_sheathing_geometry_converter.py  # Converts panels to Breps
```

### Known Gotchas

1. **Revit Wall Type names are inconsistent**: Users name them anything. "Basic Wall - 2x4 Exterior", "EXT-2x6-R21", "Type 3A". Fuzzy matching must be robust but not over-eager.

2. **wall_assembly dict vs WallAssemblyDef object**: In `walls_json`, the assembly is a plain dict. `get_assembly_for_wall()` tries to deserialize it via `assembly_dict_to_def()`. The resolver must work at the dict level (pre-deserialization).

3. **is_exterior flag**: Currently the primary fallback signal. Some Revit walls may not have this flag, or it may be wrong. The resolver should use it as a hint, not a guarantee.

4. **GH NickName injection unreliability**: Per MEMORY.md, always read inputs by parameter index, not by NickName-based globals. The new `assembly_mode` and `custom_map` inputs must follow this pattern.

---

## Implementation Blueprint

### Phase 1: Assembly Resolver Module

**New file**: `src/timber_framing_generator/config/assembly_resolver.py`

```python
@dataclass
class AssemblyResolution:
    """Result of resolving an assembly for a wall."""
    assembly: Optional[Dict[str, Any]]  # WallAssemblyDef as dict (or None)
    source: str                          # "explicit", "catalog", "inferred", "default", "custom"
    confidence: float                    # 0.0 - 1.0
    notes: str                           # Human-readable explanation
    assembly_name: str                   # Catalog key or custom name


def resolve_assembly(
    wall_data: Dict[str, Any],
    mode: str = "auto",
    custom_map: Optional[Dict[str, Any]] = None,
) -> AssemblyResolution:
    """Resolve the assembly for a single wall.

    Args:
        wall_data: Wall dict from walls_json with wall_type, wall_assembly, is_exterior.
        mode: Resolution mode ("auto", "revit_only", "catalog", "custom").
        custom_map: Per-Wall-Type assembly mappings for "custom" mode.
            Keys are Revit Wall Type names.
            Values are catalog key strings or inline assembly dicts.

    Returns:
        AssemblyResolution with the chosen assembly and metadata.
    """
    ...


def resolve_all_walls(
    walls_data: List[Dict[str, Any]],
    mode: str = "auto",
    custom_map: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Resolve assemblies for all walls, enriching each with metadata.

    Returns walls_data with added keys:
        wall_assembly (if resolved), assembly_source, assembly_confidence,
        assembly_notes, assembly_name.
    """
    ...


def match_wall_type_to_catalog(
    wall_type: str,
) -> Optional[Tuple[str, float]]:
    """Fuzzy match a Revit Wall Type name to the assembly catalog.

    Returns (catalog_key, confidence) or None if no match.
    """
    ...
```

### Phase 2: Catalog Matching Keywords

```python
# Keyword extraction patterns for wall type names
CATALOG_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "2x4_exterior": {
        "required": ["exterior"],
        "size_hint": ["2x4", "4\"", "3.5\"", "3-1/2"],
        "negative": ["2x6", "2x8"],
    },
    "2x6_exterior": {
        "required": ["exterior"],
        "size_hint": ["2x6", "6\"", "5.5\"", "5-1/2"],
        "negative": ["2x4", "2x8"],
    },
    "2x4_interior": {
        "required_any": ["interior", "partition"],
        "size_hint": ["2x4", "4\"", "3.5\""],
        "negative": ["exterior"],
    },
}
```

### Phase 3: GH Component Updates

Update `gh_multi_layer_sheathing.py`:

1. Add two new inputs:
   - `assembly_mode` (index 4): Value List with options ["auto", "revit_only", "catalog", "custom"]
   - `custom_map` (index 5): JSON string with per-Wall-Type mappings

2. Before the per-wall loop, call `resolve_all_walls()`:
   ```python
   from src.timber_framing_generator.config.assembly_resolver import resolve_all_walls

   enriched_walls = resolve_all_walls(walls_list, mode=assembly_mode, custom_map=custom_map)
   ```

3. Add assembly quality summary to output log:
   ```
   Assembly Quality: 3 explicit, 2 catalog (avg conf 0.75), 1 default
   ```

### Phase 4: Output Enrichment

In `generate_assembly_layers()`, pass through any assembly metadata from the enriched wall_data:

```python
return {
    "wall_id": ...,
    "wall_type": wall_data.get("wall_type"),
    "assembly_source": wall_data.get("assembly_source", "unknown"),
    "assembly_confidence": wall_data.get("assembly_confidence", 0.0),
    "assembly_notes": wall_data.get("assembly_notes", ""),
    "assembly_name": wall_data.get("assembly_name", ""),
    "layer_results": layer_results,
    ...
}
```

### Tasks (Execution Order)

```yaml
tasks:
  - id: 1
    title: "Create assembly_resolver.py with resolve_assembly()"
    details: "Core resolution logic for all 4 modes"
    files:
      - src/timber_framing_generator/config/assembly_resolver.py (new)

  - id: 2
    title: "Implement catalog keyword matching"
    details: "Fuzzy match Wall Type names to catalog entries"
    files:
      - src/timber_framing_generator/config/assembly_resolver.py

  - id: 3
    title: "Add per-Wall-Type custom map support"
    details: "Handle string catalog keys and inline assembly dicts"
    files:
      - src/timber_framing_generator/config/assembly_resolver.py

  - id: 4
    title: "Unit tests for assembly resolver"
    details: "Test all 4 modes, fuzzy matching, custom maps, edge cases"
    files:
      - tests/config/test_assembly_resolver.py (new)

  - id: 5
    title: "Enrich output with assembly metadata"
    details: "Add source, confidence, notes to multi-layer output"
    files:
      - src/timber_framing_generator/sheathing/multi_layer_generator.py

  - id: 6
    title: "Update GH component with new inputs"
    details: "Add assembly_mode dropdown and custom_map JSON input"
    files:
      - scripts/gh_multi_layer_sheathing.py

  - id: 7
    title: "Integration tests with real-world Wall Type names"
    details: "Test with typical Revit naming patterns"
    files:
      - tests/config/test_assembly_resolver.py
```

---

## Validation Loop

### Level 1: Unit Tests

```bash
pytest tests/config/test_assembly_resolver.py -v
```

Test cases:
- `test_auto_mode_uses_explicit_assembly` — wall with CompoundStructure returns quality="explicit"
- `test_auto_mode_catalog_fallback` — wall type "2x6 Exterior" matches catalog
- `test_auto_mode_default_fallback` — unknown wall type defaults by is_exterior
- `test_revit_only_skips_no_assembly` — returns None for walls without CompoundStructure
- `test_catalog_mode_ignores_revit_layers` — even if wall has assembly, uses catalog match
- `test_custom_mode_string_value` — `{"My Wall Type": "2x6_exterior"}` resolves correctly
- `test_custom_mode_inline_dict` — inline assembly definition is used
- `test_custom_mode_unmapped_falls_back` — unmapped types use auto behavior
- `test_fuzzy_match_basic_wall_2x6` — "Basic Wall - 2x6 Exterior" matches "2x6_exterior"
- `test_fuzzy_match_generic_interior` — "Generic - 4\" Interior" matches "2x4_interior"
- `test_fuzzy_match_no_match` — "CW 102-50-100p" returns None
- `test_confidence_scores` — explicit=1.0, catalog>0.6, inferred>0.3, default<0.3

### Level 2: Integration Tests

```bash
pytest tests/sheathing/test_multi_layer_generator.py -v -k "assembly"
```

- Multi-layer output includes `assembly_source` field
- Custom map overrides produce correct layer panels
- Confidence propagates through to final output

### Level 3: Grasshopper Validation

1. Load test model with mixed wall types
2. Run in "auto" mode — verify all walls get assemblies, check confidence in summary
3. Switch to "catalog" mode — verify Revit assemblies are ignored
4. Create custom map JSON — verify per-Wall-Type overrides work
5. Switch to "revit_only" — verify walls without CompoundStructure are skipped

---

## Final Checklist

- [ ] `assembly_resolver.py` handles all 4 modes
- [ ] Custom mode uses per-Wall-Type mapping (not single-assembly-for-all)
- [ ] Fuzzy catalog matching handles common Revit naming patterns
- [ ] Confidence scores accurately reflect data quality
- [ ] Output includes `assembly_source`, `assembly_confidence`, `assembly_notes`
- [ ] GH component has `assembly_mode` and `custom_map` inputs
- [ ] Summary output shows quality breakdown
- [ ] Existing tests unaffected
- [ ] "auto" mode behavior matches current `get_assembly_for_wall()` exactly

---

## Anti-Patterns to Avoid

- **Don't make "auto" mode behave differently from current code**: It must be 100% backward-compatible. The current fallback chain (Revit -> catalog -> is_exterior -> default) must be preserved exactly.
- **Don't require custom map for basic usage**: The system must work out of the box with zero configuration. Custom maps are opt-in for users who want control.
- **Don't over-engineer fuzzy matching**: Simple keyword extraction is enough. Don't add NLP, regex explosion, or ML-based matching. Keep it deterministic and debuggable.
- **Don't silently drop walls**: If a wall can't be resolved (e.g., revit_only mode), include it in output with `assembly_source: "skipped"` and 0 panels, not silently omit it.
- **Don't put assembly resolution logic in the GH script**: Keep it in `assembly_resolver.py` so it's testable without Grasshopper.
- **Don't break the existing `get_assembly_for_wall()` function**: The resolver calls it internally for "auto" mode. Don't modify it; wrap it.

---

## Notes

- **Scope**: This PRP covers the resolution and matching logic only. It does NOT change how panels are generated once an assembly is resolved. `generate_assembly_layers()` continues working exactly as-is.
- **Catalog expansion**: The 3-entry catalog (`2x4_exterior`, `2x6_exterior`, `2x4_interior`) is intentionally small for now. Users who need more assemblies use "custom" mode. The catalog can grow incrementally as common patterns emerge.
- **Future: Revit-side assembly extraction**: When Rhino.Inside.Revit's CompoundStructure API improves, more walls will have `quality="explicit"`. The resolver is designed so that as Revit data quality improves, the system automatically benefits (explicit > catalog > default).

---

## References

- `src/timber_framing_generator/config/assembly.py` — Current assembly catalog and `get_assembly_for_wall()`
- `src/timber_framing_generator/wall_junctions/junction_types.py` — `WallAssemblyDef`, `WallLayer` dataclasses
- `src/timber_framing_generator/sheathing/multi_layer_generator.py` — Consumer of assembly data
- `scripts/gh_multi_layer_sheathing.py` — GH component that will get new inputs
- `scripts/gh_wall_analyzer.py` — Extracts `wall_type` and `wall_assembly` from Revit
