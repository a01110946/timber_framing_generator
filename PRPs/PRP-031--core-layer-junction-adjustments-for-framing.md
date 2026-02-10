# PRP-031: Core Layer Junction Adjustments for Framing

> **Version:** 2.0
> **Created:** 2026-02-10
> **Status:** Draft
> **Branch:** feature/sheathing-junctions

---

## Goal

Enrich `walls_json` with per-wall `framing_segments` immediately after
junction analysis, so that ALL downstream components (Cell Decomposer,
Panel Decomposer, Framing Generator, MEP Router) operate on the correct
adjusted framing boundaries.

Primary walls extend through corners; secondary walls trim to stop at
the primary wall's framing face. At X-crossings, the secondary wall's
framing splits into two segments around the primary wall's core.

## Why

- **No nailing surface**: Sheathing already extends/trims at junctions
  (PRP-029/030), but the framing underneath does NOT. Extended sheathing
  hangs past the last stud with nothing to nail to.
- **Overlap/gaps**: Both walls' plates currently occupy the same space
  at the corner, or leave a gap. Physically impossible.
- **Cascading correctness**: Core adjustments change the wall's
  *framing length*. Every downstream consumer — cell decomposition,
  panel decomposition, framing element generation, MEP cavity routing —
  must see the adjusted boundaries. A late-stage fix in the Framing
  Generator alone would leave Cell Decomposer, Panel Decomposer, and
  MEP Router blind to the real framing geometry.
- **The data already exists**: The junction resolver emits core
  EXTEND/TRIM adjustments. They are currently dead data — never consumed
  by the framing pipeline.

## What

The Junction Analyzer computes `framing_segments` per wall and injects
them into an enriched `walls_json` output. Original wall fields
(`wall_length`, `base_curve_start/end`, etc.) are preserved unchanged.

### `framing_segments` Field

A list of `[u_start, u_end]` pairs defining the effective framing runs
for each wall. Always in the wall's original U coordinate system.

**L-corner** (primary EXTENDS at end, secondary TRIMS at start):
```json
{"wall_id": "wall_1", "wall_length": 10.0,
 "framing_segments": [[0.0, 10.146]]}

{"wall_id": "wall_2", "wall_length": 12.0,
 "framing_segments": [[0.146, 12.0]]}
```

**T-intersection** (terminating wall TRIMS at its terminating endpoint):
```json
{"wall_id": "wall_term", "wall_length": 8.0,
 "framing_segments": [[0.0, 7.854]]}

{"wall_id": "wall_cont", "wall_length": 20.0,
 "framing_segments": [[0.0, 20.0]]}
```
Continuous wall is unaffected — its plates run straight through.

**X-crossing** (secondary wall SPLITS, primary runs through):
```json
{"wall_id": "wall_pri", "wall_length": 15.0,
 "framing_segments": [[0.0, 15.0]]}

{"wall_id": "wall_sec", "wall_length": 15.0,
 "framing_segments": [[-0.146, 7.354], [7.646, 15.146]]}
```
Secondary splits into two independent framing runs with a gap where
the primary wall's core passes through.

**Default** (no junctions, or `framing_segments` absent):
```
[[0.0, wall_length]]
```

### How Core Adjustments Map to Segments

| Junction Type | Wall Role | Endpoint | Adjustment | Segment Effect |
|---|---|---|---|---|
| L-corner | Primary | end | EXTEND by X | End boundary → `wall_length + X` |
| L-corner | Secondary | start | TRIM by X | Start boundary → `+X` |
| T-intersection | Terminating | end | TRIM by X | End boundary → `wall_length - X` |
| T-intersection | Continuous | midspan | TRIM (ignored) | Unaffected — plates run through |
| X-crossing | Primary | midspan | — | Unaffected — runs through |
| X-crossing | Secondary | midspan | TRIM by X at U | Split: `[..., U-X], [U+X, ...]` |

### Success Criteria

- [ ] Junction Analyzer outputs enriched `walls_json` with `framing_segments`
- [ ] Cell Decomposer uses `framing_segments` for cell boundaries
- [ ] `reconstruct_wall_data()` uses `framing_segments` for WBC creation
- [ ] Multi-segment walls (X-crossings) produce independent framing runs
- [ ] Plates extend/trim to match core junction adjustments
- [ ] End studs placed at adjusted wall boundaries
- [ ] Original `wall_length` and `base_curve_*` fields untouched
- [ ] Backward compatible: absent `framing_segments` → `[[0, wall_length]]`
- [ ] No regressions in existing framing/sheathing/junction tests
- [ ] Unit tests for `compute_framing_segments()`

---

## All Needed Context

### Documentation & References
```yaml
Feature-Specific:
  - file: src/timber_framing_generator/wall_junctions/junction_types.py
    why: LayerAdjustment dataclass — fields wall_id, end, layer_name,
         adjustment_type, amount, midspan_u. Serialized via
         _serialize_adjustment().

  - file: src/timber_framing_generator/wall_junctions/junction_resolver.py
    why: Emits core adjustments:
         - L-corner primary EXTEND: lines 502-508
         - L-corner secondary TRIM: lines 568-574
         - T-int terminating TRIM: lines 839-846
         - T-int continuous midspan TRIM: lines 989-996
         - X-crossing: bidirectional midspan via midspan_only=True

  - file: scripts/gh_junction_analyzer.py
    why: GH component that runs analyze_junctions() and serializes
         the graph. THIS IS WHERE framing_segments enrichment happens.
         Currently outputs junctions_json — needs new walls_json output.

  - file: scripts/gh_cell_decomposer.py
    why: Creates cells from 0 to wall_length (line 591-625).
         MUST BE MODIFIED to read framing_segments and use adjusted
         boundaries for SC cells and WBC corner points.

  - file: src/timber_framing_generator/materials/timber/element_adapters.py
    why: reconstruct_wall_data() creates WBC from wall_length (lines
         150-180). MUST BE MODIFIED to read framing_segments from
         wall_data dict for WBC corner point creation.

  - file: src/timber_framing_generator/framing_elements/location_data.py
    why: get_plate_location_data() builds reference_line from WBC corners
         (lines 110-135). No changes needed — reads WBC automatically.

  - file: src/timber_framing_generator/framing_elements/plates.py
    why: create_plates() uses reference_line from location_data.
         Downstream of WBC — adjusts automatically when WBC changes.

  - file: scripts/gh_framing_generator.py
    why: Processes cells per wall. For multi-segment walls (X-crossings),
         needs to process each segment independently.
```

### Serialized Adjustment Format (from junctions_json)

```json
{
  "wall_adjustments": {
    "wall_1": [
      {
        "end": "end",
        "junction_id": "jn_0",
        "layer_name": "core",
        "adjustment_type": "extend",
        "amount": 0.145833,
        "connecting_wall_id": "wall_2"
      }
    ],
    "wall_2": [
      {
        "end": "start",
        "junction_id": "jn_0",
        "layer_name": "core",
        "adjustment_type": "trim",
        "amount": 0.145833,
        "connecting_wall_id": "wall_1"
      }
    ],
    "wall_sec": [
      {
        "end": "midspan",
        "junction_id": "jn_x",
        "layer_name": "core",
        "adjustment_type": "trim",
        "amount": 0.145833,
        "connecting_wall_id": "wall_pri",
        "midspan_u": 7.5
      }
    ]
  }
}
```

The `compute_framing_segments()` function reads:
- `layer_name == "core"` adjustments only
- `end in ("start", "end")` for endpoint shifts (L-corners, T-intersections)
- `end == "midspan"` with `midspan_u` for X-crossing splits

### Known Gotchas

```python
# CRITICAL: Preserve original wall data.
# walls_json fields (wall_length, base_curve_start/end) are Revit truth.
# framing_segments is an ADDITION, not a replacement.
# Downstream components read framing_segments; when absent, default to
# [[0, wall_length]].

# CRITICAL: A wall can have adjustments at BOTH ends.
# e.g., wall_1 is primary at its "end" (EXTEND) and secondary
# at its "start" (TRIM). Each end is independent.

# CRITICAL: T-intersection continuous wall is UNAFFECTED for framing.
# The continuous wall's midspan core TRIM (end="midspan") exists in
# junctions_json for sheathing gaps. For framing, the continuous wall's
# plates run straight through — its midspan adjustment is ignored.

# CRITICAL: X-crossing secondary wall SPLITS for framing.
# The midspan core TRIM (end="midspan") with midspan_u creates a gap.
# The secondary wall becomes two framing segments. The primary wall
# runs through unaffected.

# CRITICAL: Multi-segment walls need independent framing runs.
# Each segment in framing_segments produces its own set of plates,
# studs, and all framing elements. The Cell Decomposer creates
# separate cell groups per segment. The Framing Generator processes
# each segment as an independent mini-wall.

# CRITICAL: Openings stay in original U coordinates.
# framing_segments shifts the outer edges. Interior openings (OC, HCC,
# SCC) keep their original u_start/u_end positions. Only outermost SC
# cells shift to match segment boundaries.

# Units: All amounts in FEET (consistent with rest of system).
```

---

## Implementation Blueprint

### Data Flow

```
Wall Analyzer
  │
  ▼ walls_json (raw Revit data)
  │
Junction Analyzer
  │  1. analyze_junctions() → junction graph
  │  2. compute_framing_segments(graph, walls) → per-wall segments
  │  3. Inject framing_segments into each wall dict
  │
  ├──▶ junctions_json (unchanged — for sheathing)
  │
  ▼ walls_json (enriched — with framing_segments)
  │
  ├──▶ Panel Decomposer (reads framing_segments for panelization bounds)
  ├──▶ Cell Decomposer  (reads framing_segments for cell boundaries)
  │       │
  │       ▼ cell_json (cells within adjusted boundaries)
  │       │
  │       ├──▶ Framing Generator (processes per segment, plates+studs correct)
  │       └──▶ MEP Router (sees adjusted cavities)
  │
  └──▶ Multi-Layer Sheathing (uses junctions_json directly, unchanged)
```

### Desired Structure (files to add/modify)
```bash
src/timber_framing_generator/
├── wall_junctions/
│   └── core_adjustment.py          # NEW: compute_framing_segments()
├── materials/timber/
│   └── element_adapters.py         # MODIFY: read framing_segments for WBC
scripts/
├── gh_junction_analyzer.py         # MODIFY: new walls_json output, enrichment
├── gh_cell_decomposer.py           # MODIFY: read framing_segments for cell bounds
├── gh_framing_generator.py         # MODIFY: multi-segment processing
tests/
├── wall_junctions/
│   └── test_core_adjustment.py     # NEW: unit tests
```

### Tasks (in execution order)

```yaml
Task 1: Create core_adjustment.py utility module
  - CREATE: src/timber_framing_generator/wall_junctions/core_adjustment.py
  - Main function: compute_framing_segments(junctions_data, walls_data)
  - Returns enriched walls list with framing_segments on each wall
  - Pure Python, no Rhino dependency — fully testable standalone
  - Handles L-corners, T-intersections, and X-crossing splits

Task 2: Modify Junction Analyzer to output enriched walls_json
  - MODIFY: scripts/gh_junction_analyzer.py
  - After analyze_junctions(), call compute_framing_segments()
  - Add new output: "Walls JSON" (enriched walls_json with framing_segments)
  - Existing outputs remain unchanged (junctions_json, graph_pts, etc.)
  - PRESERVE: junctions_json format and content unchanged

Task 3: Modify Cell Decomposer to read framing_segments
  - MODIFY: scripts/gh_cell_decomposer.py
  - Read framing_segments from each wall dict (default [[0, wall_length]])
  - For single-segment: adjust first SC u_start and last SC u_end
  - For multi-segment: create separate cell groups per segment,
    each with its own SC cells and opening cells within that range
  - PRESERVE: Works without framing_segments (backward compat)

Task 4: Modify reconstruct_wall_data() for framing_segments
  - MODIFY: src/timber_framing_generator/materials/timber/element_adapters.py
  - Read framing_segments from wall_data dict
  - Use segment bounds for WBC corner points (BL/BR/TL/TR)
  - Default to [[0, wall_length]] when absent
  - PRESERVE: Existing behavior for walls without framing_segments

Task 5: Modify Framing Generator for multi-segment walls
  - MODIFY: scripts/gh_framing_generator.py
  - For multi-segment walls (X-crossings), process each segment as
    an independent framing run with its own plates and studs
  - Single-segment walls: no change from current behavior
  - cell_json entries for multi-segment walls carry segment metadata
    (segment_u_start, segment_u_end) set by Cell Decomposer

Task 6: Write unit tests
  - CREATE: tests/wall_junctions/test_core_adjustment.py
  - Test compute_framing_segments() with:
    - L-corner (primary extends, secondary trims)
    - T-intersection (terminating trims, continuous unaffected)
    - X-crossing (secondary splits, primary unaffected)
    - Wall with adjustments at both ends
    - Wall with no adjustments (default [[0, wall_length]])
    - Multiple junctions on same wall

Task 7: Run full test suite, verify no regressions
  - RUN: pytest tests/ -v
```

### Pseudocode (with CRITICAL details)

```python
# =================================================================
# Task 1: core_adjustment.py
# =================================================================

from typing import Dict, List, Any


def compute_framing_segments(
    junctions_data: Dict[str, Any],
    walls_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Enrich walls with framing_segments derived from core adjustments.

    Reads core LayerAdjustment records from junctions_data and computes
    the effective framing segment boundaries for each wall.

    - Endpoint adjustments (end="start"/"end") shift segment edges.
    - Midspan adjustments (end="midspan") split into multiple segments.
    - Continuous walls at T-intersections are unaffected.
    - Primary walls at X-crossings are unaffected.

    Args:
        junctions_data: Parsed junctions_json dict with wall_adjustments.
        walls_data: List of wall dicts (will NOT be mutated).

    Returns:
        New list of wall dicts, each with framing_segments added.
        Original fields are preserved unchanged.
    """
    enriched = []

    for wall in walls_data:
        wall_id = wall.get("wall_id", "")
        wall_length = wall.get("wall_length", 0.0)
        new_wall = dict(wall)  # Shallow copy — don't mutate original

        adjs = junctions_data.get("wall_adjustments", {}).get(wall_id, [])
        core_adjs = [a for a in adjs if a.get("layer_name") == "core"]

        # --- Step 1: Compute endpoint shifts ---
        u_start = 0.0
        u_end = wall_length

        for adj in core_adjs:
            end = adj.get("end")
            adj_type = adj.get("adjustment_type", "")
            amount = adj.get("amount", 0.0)

            if end == "start":
                if adj_type == "trim":
                    u_start = max(u_start, amount)
                elif adj_type == "extend":
                    u_start = min(u_start, -amount)
            elif end == "end":
                if adj_type == "trim":
                    u_end = min(u_end, wall_length - amount)
                elif adj_type == "extend":
                    u_end = max(u_end, wall_length + amount)
            # end == "midspan" handled in Step 2

        # --- Step 2: Collect midspan splits (X-crossings) ---
        midspan_gaps = []
        for adj in core_adjs:
            if adj.get("end") != "midspan":
                continue
            mid_u = adj.get("midspan_u")
            amount = adj.get("amount", 0.0)
            if mid_u is not None and amount > 0:
                midspan_gaps.append((mid_u - amount, mid_u + amount))

        # --- Step 3: Build segments ---
        if not midspan_gaps:
            # Single segment (L-corner, T-intersection, or no adjustment)
            segments = [[u_start, u_end]]
        else:
            # Multi-segment: sort gaps and split
            midspan_gaps.sort(key=lambda g: g[0])
            segments = []
            seg_start = u_start
            for gap_start, gap_end in midspan_gaps:
                if gap_start > seg_start:
                    segments.append([seg_start, gap_start])
                seg_start = gap_end
            if seg_start < u_end:
                segments.append([seg_start, u_end])

        new_wall["framing_segments"] = segments
        enriched.append(new_wall)

    return enriched
```

```python
# =================================================================
# Task 2: gh_junction_analyzer.py changes
# =================================================================

# Add to output_config (new output after existing ones):
("Walls JSON", "walls_json_out",
 "Enriched walls_json with framing_segments per wall"),

# In main(), after graph serialization:
from src.timber_framing_generator.wall_junctions.core_adjustment import (
    compute_framing_segments,
)

enriched_walls = compute_framing_segments(graph_dict, walls_data)
walls_json_out = json.dumps(enriched_walls, indent=2)

# Return updated tuple (add walls_json_out):
return junctions_json, graph_pts, graph_lines, summary_text, \
       "\n".join(log_lines), walls_json_out
```

```python
# =================================================================
# Task 3: gh_cell_decomposer.py changes
# =================================================================

# In decompose_wall_json_to_cells():
def decompose_wall_json_to_cells(wall_dict, wall_index):
    wall_length = wall_dict.get('wall_length', 0)
    segments = wall_dict.get('framing_segments', [[0, wall_length]])

    all_cells = []
    all_surfaces = []
    all_labels = []

    for seg_idx, (seg_start, seg_end) in enumerate(segments):
        # For each framing segment, create cells within [seg_start, seg_end]
        # Use seg_start/seg_end instead of 0/wall_length for:
        #   - First SC cell u_start
        #   - Last SC cell u_end
        #   - WBC corner points (if emitted)
        # Openings within the segment keep their original u-positions.
        # Openings outside the segment are excluded.
        #
        # For multi-segment, add segment metadata to cells:
        #   cell["metadata"]["segment_index"] = seg_idx
        #   cell["metadata"]["segment_u_start"] = seg_start
        #   cell["metadata"]["segment_u_end"] = seg_end
        ...
```

```python
# =================================================================
# Task 4: element_adapters.py changes
# =================================================================

# In reconstruct_wall_data(), replace hardcoded 0/wall_length:
def reconstruct_wall_data(wall_data):
    ...
    wall_length = result["wall_length"]

    # Read framing_segments — use first (or only) segment for WBC
    segments = wall_data.get("framing_segments", [[0, wall_length]])
    # For multi-segment, this function is called per segment with
    # the segment bounds passed via metadata
    seg_start, seg_end = segments[0][0], segments[0][1]

    # If cell metadata carries segment bounds (multi-segment case),
    # prefer those over wall-level segments
    seg_meta = wall_data.get("_segment_bounds")
    if seg_meta:
        seg_start, seg_end = seg_meta

    # Calculate corner points using segment bounds
    bl = rg.Point3d.Add(
        rg.Point3d(origin.X, origin.Y, base_elevation),
        rg.Vector3d.Multiply(base_plane.XAxis, seg_start)
    )
    br = rg.Point3d.Add(
        rg.Point3d(origin.X, origin.Y, base_elevation),
        rg.Vector3d.Multiply(base_plane.XAxis, seg_end)
    )
    tr = rg.Point3d(br.X, br.Y, base_elevation + wall_height)
    tl = rg.Point3d(bl.X, bl.Y, base_elevation + wall_height)

    wbc_cell = {
        "cell_type": "WBC",
        "corner_points": [bl, br, tr, tl],
        "u_start": seg_start,
        "u_end": seg_end,
        "v_start": 0,
        "v_end": wall_height,
    }
    ...
```

```python
# =================================================================
# Task 5: gh_framing_generator.py changes
# =================================================================

# In process_framing(), handle multi-segment:
for i, cell_data_dict in enumerate(cell_list):
    wall_id = cell_data_dict.get('wall_id', f'wall_{i}')
    wall_data_dict = wall_lookup.get(wall_id, {})

    # Check for segment metadata (multi-segment walls)
    seg_meta = cell_data_dict.get("metadata", {})
    seg_start = seg_meta.get("segment_u_start")
    seg_end = seg_meta.get("segment_u_end")

    if seg_start is not None and seg_end is not None:
        # Pass segment bounds to reconstruct_wall_data via wall_data
        wall_data_copy = dict(wall_data_dict)
        wall_data_copy["_segment_bounds"] = (seg_start, seg_end)
    else:
        wall_data_copy = wall_data_dict

    elements, wall_log = generate_framing_for_wall(
        cell_data_dict, wall_data_copy, strategy, config
    )
    ...
```

### Integration Points
```yaml
UTILITY:
  - file: src/timber_framing_generator/wall_junctions/core_adjustment.py
  - pattern: "Pure function, no Rhino dependency, imported by GH components"

JUNCTION_ANALYZER:
  - file: scripts/gh_junction_analyzer.py
  - pattern: "Enrich walls_data after analyze_junctions(), output as walls_json"

CELL_DECOMPOSER:
  - file: scripts/gh_cell_decomposer.py
  - pattern: "Read framing_segments, use segment bounds for cell boundaries"

ELEMENT_ADAPTERS:
  - file: src/timber_framing_generator/materials/timber/element_adapters.py
  - pattern: "Read framing_segments or _segment_bounds for WBC creation"

FRAMING_GENERATOR:
  - file: scripts/gh_framing_generator.py
  - pattern: "Pass segment metadata through to reconstruct_wall_data()"
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\tfg-sheathing-junctions"

# Lint new file
python -m flake8 src/timber_framing_generator/wall_junctions/core_adjustment.py --max-line-length=88

# Type check
python -m mypy src/timber_framing_generator/wall_junctions/core_adjustment.py
```

### Level 2: Unit Tests
```bash
# New tests only
python -m pytest tests/wall_junctions/test_core_adjustment.py -v

# All junction tests
python -m pytest tests/wall_junctions/ -v

# All sheathing tests (regression check)
python -m pytest tests/sheathing/ -v

# Full suite
python -m pytest tests/ -v
```

### Level 3: Integration Test (Grasshopper)
```
1. Open Rhino with Grasshopper
2. Wire Junction Analyzer's enriched walls_json output to:
   - Cell Decomposer (instead of raw Wall Analyzer walls_json)
   - Any other downstream component that reads walls_json
3. Load test model with known L-corner + T-intersection
4. Toggle run=True
5. Verify:
   - Primary wall plates extend past corner (visible gap filled)
   - Secondary wall plates stop short of corner (no overlap)
   - T-intersection terminating wall plates trim (no overlap with
     continuous wall)
   - End studs placed at adjusted boundaries
   - Cell surfaces in Cell Decomposer match adjusted bounds
6. For X-crossing test (if available):
   - Secondary wall has two independent plate runs
   - Primary wall plates run continuously through crossing
   - Gap at crossing equals primary wall core thickness
```

---

## Final Checklist

- [ ] `core_adjustment.py` created with `compute_framing_segments()`
- [ ] `gh_junction_analyzer.py` outputs enriched walls_json
- [ ] `gh_cell_decomposer.py` reads framing_segments for cell boundaries
- [ ] `element_adapters.py` reads framing_segments for WBC creation
- [ ] `gh_framing_generator.py` handles multi-segment walls
- [ ] All unit tests pass: `python -m pytest tests/ -v`
- [ ] No regressions in existing junction/sheathing tests
- [ ] Backward compatible: absent framing_segments → `[[0, wall_length]]`
- [ ] Original `wall_length` and `base_curve_*` fields untouched
- [ ] Code follows project conventions (type hints, Google docstrings)

---

## Anti-Patterns to Avoid

- Do NOT modify `wall_length` or `base_curve_start/end` — `framing_segments` is an addition, not a replacement
- Do NOT ignore midspan core adjustments — X-crossing secondary walls MUST split
- Do NOT assume continuous walls at T-intersections need framing adjustment — only their midspan sheathing adjustments exist, which are irrelevant for framing
- Do NOT assume single-segment — always read `framing_segments` as a list and iterate
- Do NOT create Rhino-dependent code in `core_adjustment.py` — keep it pure Python
- Do NOT bypass the Cell Decomposer — it's the single source of truth for cell boundaries; don't re-adjust cells in the Framing Generator

---

## Notes

- **Upstream enrichment**: The Junction Analyzer is the earliest point where both `walls_json` and junction topology are known. Enriching here ensures all downstream components see correct boundaries.
- **Phase 2 compatibility**: The sheathing pipeline's Phase 2 `recompute_adjustments()` operates on individual sheathing layer adjustments, not core/framing. The `framing_segments` field is orthogonal and does not interfere.
- **CFS compatibility**: The CFS strategy will also benefit once its `create_horizontal_members()` reads the same WBC from `reconstruct_wall_data()`.
- **Panel Decomposer**: When panels are used, panelization bounds should respect `framing_segments`. A panel should not extend past a segment boundary. This is a natural constraint that the Panel Decomposer can enforce by reading the field.
- **MEP Router**: Cavity routing should use cell boundaries from the adjusted Cell Decomposer output. No direct MEP changes needed — it inherits correct cells automatically.
