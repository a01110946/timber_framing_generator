# Session Reflection: MEP Routing, Cavity Module, Junctions & Wall Assemblies

**Date:** 2026-02-05
**Branch:** `mep-adjustments`
**Scope:** Issue #33 (MEP Routing) + Wall Junction System + Multi-Layer Assembly Pipeline

---

## 1. The Journey: From Issue #33 to a Working Pipeline

### Phase 1: The OAHS Monolithic Router (PRP-011)

The journey started with **Issue #33** and **PRP-011** -- the Obstacle-Aware Hanan Steiner (OAHS) monolithic MEP router. This was an academically-elegant approach: build a multi-domain graph, compute Hanan grids, find Steiner trees via MST, then route with A*. We implemented it across 11 phases, from core data structures all the way to pipe geometry creation.

**It routed 0 out of 23 connections.** Zero.

The fundamental problem was not the algorithm -- it was the abstraction level. The monolithic router tried to solve the entire building at once, placing graph nodes in abstract 2D space with no understanding of what "inside a wall" or "between studs" actually means physically. Domain transitions were theoretical, not geometric.

### Phase 2: Hierarchical Decomposition (PRP-022)

Rather than patching a broken architecture, we decomposed the problem hierarchically:

| Phase | Scale | Question |
|-------|-------|----------|
| 1. Fixture Router | Room -> Wall | "Which wall does this pipe hit?" |
| 2. Wall Router | Within wall | "How does the pipe drop through studs?" |
| 3. Wall-to-Wall | Panel boundary | "How does the pipe cross between panels?" |
| 4. Distribution | Floor/ceiling | "How does the pipe reach the stack?" |
| 5. To-Riser | Vertical | "How does the pipe reach the main?" |

Each phase solves a constrained, well-defined problem and passes results downstream. This is the same decomposition principle we use for framing (Wall -> Panel -> Cell -> Element) -- now applied to routing.

### Phase 3: The Cavity Breakthrough

The wall router went through two iterations:

1. **Grid-based A* (v1):** Created a 2D UV grid per wall with stud penetration costs. Produced U-shaped routes, stud collisions, and diagonal segments. Required patching with L-shaped rectilinear connections.

2. **Cavity-based routing (v2):** Inverted the problem. Instead of navigating around obstacles, we defined the acceptable spaces (cavities -- rectangular voids between framing members) and routed within them. Routes became trivially vertical drops. Zero stud crossings by construction.

The cavity abstraction also required refinement of the edge-packing heuristic. The initial approach snapped all pipes to the nearest cavity edge, creating unnecessary horizontal jogs and pipe crossings. The correct heuristic was simpler: keep the pipe at its entry position, only shift when forced by collision with another pipe.

---

## 2. What We Built

### 2.1 Cavity Module (New Foundational Layer)

**Hierarchy:** Wall -> Panel -> Cell -> **Cavity**

| File | Lines | Purpose |
|------|-------|---------|
| `cavity/cavity.py` | 175 | `Cavity` and `CavityConfig` dataclasses |
| `cavity/cavity_decomposer.py` | 692 | Two-mode decomposition + spatial queries |
| `cavity/__init__.py` | 29 | Public API exports |

**Key abstractions:**
- `Cavity`: Smallest rectangular void between framing members, bounded by studs (left/right) and plates/headers/sills/blocking (top/bottom)
- `CavityConfig`: Configurable stud spacing (not hardcoded 16" OC), minimum clear dimensions, tolerance
- Two decomposition modes: **Derived** (from wall geometry + configured spacing) and **Framing** (from exact framing element positions + cell data)
- Spatial queries: `find_cavity_for_uv()`, `find_nearest_cavity()`, `find_adjacent_cavities()`

**Design principle:** The cavity is a universal coordination layer. MEP routing uses it to find pipe paths. Insulation fills cavities. Electrical runs through cavities. Nailing schedules reference cavity edges (which are stud faces). One abstraction, many consumers.

### 2.2 MEP Phase 1: Fixture Router

| File | Lines | Purpose |
|------|-------|---------|
| `mep/routing/fixture_router.py` | 504 | Projects MEP connectors onto walls |
| `scripts/gh_mep_fixture_router.py` | 598 | GH component wrapper |

**Key capabilities:**
- Fixture-type-aware penetration placement (toilet drain at floor, sink connections at specific heights, shower supply from above)
- Search radius-based wall assignment
- UV coordinate computation on assigned wall face
- System-type preservation for downstream exit selection

### 2.3 MEP Phase 2: Wall Router (Cavity-Based)

| File | Lines | Purpose |
|------|-------|---------|
| `mep/routing/wall_router.py` | 863 | Cavity-based in-wall routing |
| `scripts/gh_mep_wall_router.py` | 693 | GH component wrapper |

**Key capabilities:**
- Cavity decomposition per wall (derived or framing mode)
- Prefer-straight-drop heuristic: pipes drop vertically at entry position, only jog when collision detected
- Occupancy-aware multi-pipe support: pipes from the same fixture take different positions without crossing
- System-type exit selection: sanitary/supply -> bottom plate, vent -> top plate
- Progressive refinement: works with walls_json alone, improves with framing_json + cell_json
- World coordinate embedding in output (`world_segments`) for downstream visualization

### 2.4 Route Visualizer (Fixed)

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/gh_mep_route_visualizer.py` | 567 | Route visualization with system-type colors |

**Fixes applied:**
- `dir()` scope bug: GH globals captured at module level with `try/except NameError` pattern
- Format compatibility: accepts both `"routes"` (old OAHS) and `"wall_routes"` (Phase 2) keys
- Color mapping: added Revit PascalCase system type names (`Sanitary`, `DomesticColdWater`, `DomesticHotWater`, `Vent`) alongside shorthand aliases

### 2.5 Wall Junction System

| File | Lines | Purpose |
|------|-------|---------|
| `wall_junctions/junction_types.py` | 479 | 9 dataclasses, 5 enums -- the type system |
| `wall_junctions/junction_detector.py` | 539 | Geometric detection of wall junctions |
| `wall_junctions/junction_resolver.py` | 838 | Join strategy resolution + per-layer adjustments |
| `scripts/gh_junction_analyzer.py` | 677 | GH component wrapper |

**Key abstractions:**

- `JunctionType`: FREE_END, L_CORNER, T_INTERSECTION, X_CROSSING, INLINE, MULTI_WAY
- `JoinType`: BUTT (one wall extends, one trims) or MITER (both cut at bisector angle)
- `LayerFunction`: STRUCTURE > SUBSTRATE > THERMAL > MEMBRANE > FINISH (5-level priority hierarchy)
- `LayerAdjustment`: Per-layer extend/trim amount at a wall end for a specific junction

**Detection algorithm:**
1. Extract all wall start/end points
2. Group nearby endpoints by proximity (configurable tolerance)
3. Detect T-intersections (endpoint hitting wall mid-span)
4. Classify by connection count and angles

**Resolution algorithm:**
1. Determine priority (which wall extends): longer_wall, exterior_first, or alternate strategies
2. For T-junctions: continuous wall always takes priority over terminating wall
3. Calculate per-layer adjustments: primary wall extends by secondary wall's layer thickness, secondary wall trims
4. Support for user overrides and confidence scoring

**Design principle:** The junction system solves a problem that is invisible in schematic design (LOD 100) but critical for fabrication (LOD 400). At an L-corner, the exterior sheathing of Wall A must extend to cover the end grain of Wall B, while Wall B's interior gypsum must trim to avoid double-thickness. These adjustments are per-layer, per-junction, per-wall-end -- and they must be computed automatically.

### 2.6 Wall Assembly Pipeline

| File | Lines | Purpose |
|------|-------|---------|
| `wall_data/assembly_extractor.py` | 304 | Revit CompoundStructure -> WallAssemblyDef |
| `materials/layer_rules.py` | 252 | Per-material placement rules (stagger, orientation, fastening) |
| `sheathing/multi_layer_generator.py` | 372 | Multi-layer panel generation |
| `scripts/gh_multi_layer_sheathing.py` | 701 | GH component wrapper |

**Assembly extraction:**
- Parses Revit's `CompoundStructure` with function assignment (Structure, Substrate, Thermal, Membrane, Finish)
- Maps layer index to side (Exterior/Core/Interior) using core boundary indices
- Produces `WallAssemblyDef` with ordered `WallLayer` list
- JSON serializable for inter-component communication

**Layer rules engine:**
- Pre-built rule sets per material: OSB, plywood, gypsum board, continuous insulation, WRB membrane, exterior finish
- Each rule defines: stagger pattern, stagger offset, minimum piece width, panel orientation, blocking requirements, fastener spacing
- Extensible: custom rules can override defaults per project or manufacturer

**Multi-layer generator:**
- Iterates panelizable layers (substrate, finish, thermal -- skips structure and membrane)
- Computes W-offset for each layer from assembly geometry (exterior layers stack outward, interior layers stack inward)
- Applies junction adjustments (U-axis extend/trim per layer)
- Runs `SheathingGenerator` with per-layer configuration from rules engine
- Outputs `multi_layer_json` for geometry conversion

**Architectural flow:**
```
Revit Wall Type (CompoundStructure)
        |
        v
assembly_extractor.extract_compound_structure()
        |
        v
WallAssemblyDef (in walls_json.wall_assembly)
        |
        v
walls_json -> [Junction Analyzer] -> junctions_json
        |                                   |
        |                                   v
        +----> [Multi-Layer Sheathing] <- layer_rules.get_rules_for_layer()
                      |
                      v
              multi_layer_json -> [Geometry Converter] -> Breps
```

---

## 3. By the Numbers

| Metric | Value |
|--------|-------|
| Files changed (vs main) | 52 |
| Lines added | ~16,900 |
| Lines removed | ~91 |
| New source modules | 12 |
| New test files | 13 |
| Tests passing | 853 |
| GH components added/updated | 6 |
| PRPs created | 3 (PRP-022, 023, 024) |

### Module breakdown (source code)

| Module | Lines | Files |
|--------|-------|-------|
| Cavity | 896 | 3 |
| MEP Routing (fixture + wall) | 1,367 | 2 |
| Wall Junctions | 1,856 | 3 |
| Assembly + Layer Rules | 556 | 2 |
| Multi-Layer Sheathing | 372 | 1 |
| GH Components | 3,269 | 5 |
| **Total source** | **~8,316** | **16** |

### Test coverage

| Test Module | Lines | Tests |
|-------------|-------|-------|
| Cavity | 400+ | 31 |
| MEP Fixture Router | 690 | ~25 |
| MEP Wall Router | 910 | 43 |
| Junction Detector | 268 | ~15 |
| Junction Resolver | 757 | ~30 |
| Wall Assembly | 217 | ~10 |
| Assembly Extractor | 472 | ~20 |
| Layer Rules | 538 | ~25 |
| Multi-Layer Generator | 714 | ~30 |
| Sheathing | 346 | ~15 |
| **Total tests** | **~5,300 lines** | **853 passing** |

---

## 4. Key Insights

### 4.1 The cavity abstraction was the breakthrough

Once we stopped thinking about routing as "navigating a grid" and started thinking about it as "picking which void to drop through," the problem became almost trivially solvable. Most residential plumbing routes are just vertical drops within stud bays. The cavity module made this geometric reality explicit.

### 4.2 Progressive refinement matches BIM workflow

The wall router works with just `walls_json` (derives cavities from stud spacing), improves with `framing_json` (exact element positions), and reaches full precision with `framing_json + cell_json`. This means it works at LOD 100 and gets better as the model matures -- exactly matching the BIM workflow from schematic to fabrication.

### 4.3 Decomposition scales across domains

The same hierarchy pattern (Wall -> Panel -> Cell -> Cavity) that works for framing also works for routing, junctions, sheathing, and will work for insulation, nailing, and electrical. The junction system's per-layer adjustment model similarly applies to framing, sheathing, cladding, and trim. One abstraction pattern, many consumers.

### 4.4 Simple heuristics beat complex algorithms

- Edge-packing (snap to cavity edge) was wrong; prefer-entry-position (keep pipe where it enters) was right
- Grid-based A* produced pathological routes; vertical-drop-within-cavity produced correct routes
- Layer priority hierarchy (5 levels) resolved junction strategies that would otherwise require case-by-case rules

### 4.5 GHPython scope is a recurring trap

The `dir()` inside functions bug was hit twice (fixture router, route visualizer). The `try/except NameError` at module level is the only reliable pattern. Also: NickName-based globals are unreliable (globals use OLD names if `setup_component()` renames them), and reading inputs by parameter index is the only safe approach.

### 4.6 The junction system enables offsite construction

Wall junctions are invisible in traditional construction (carpenters handle them implicitly on-site). In panelized offsite construction, every wall is fabricated independently and assembled on-site. Per-layer adjustments at junctions must be pre-computed during design: the exterior sheathing of Panel A extends by 5.5" to cover Panel B's end grain, but Panel A's interior gypsum trims by 0.625" to avoid double-thickness. This level of detail is what separates LOD 100 from LOD 400.

---

## 5. Evaluation

### What works well

- **Cavity-based routing** produces geometrically correct, structurally sound routes with zero stud crossings
- **Fixture-type awareness** generates realistic penetration points that match actual plumbing practice
- **Multi-pipe collision avoidance** works without crossing, using an occupancy-aware prefer-entry heuristic
- **Junction detection** handles L-corners, T-intersections, X-crossings, and free ends correctly
- **Per-layer resolution** produces extend/trim amounts that are structurally and thermally correct
- **Assembly extraction** bridges Revit's CompoundStructure data into pure Python types that work outside Rhino
- **Layer rules engine** encodes industry-standard panel placement rules (stagger, orientation, fastening)
- **JSON inter-component communication** enables inspection and debugging at every pipeline stage
- **All 853 tests pass** with comprehensive coverage of edge cases

### What needs iteration

- **Cross-cavity routing** (pipe on a stud needing to jog to adjacent bay) is functional but has not been stress-tested with complex wall configurations (double studs, built-up headers, etc.)
- **Horizontal blocking penetration** is not yet handled -- pipes that need to cross blocking (horizontal framing members within a cavity) are not modeled
- **Occupancy map** checks vertical columns only -- does not account for horizontal segment collisions between different pipes
- **Junction resolver** uses a 3-layer legacy model (`WallLayerInfo`) by default; full `WallAssemblyDef` support is implemented but needs more real-world testing
- **Multi-layer sheathing** material resolution relies on string matching with aliases, which can break with unexpected Revit material names
- **No validation against building codes** yet (e.g., max hole diameter as fraction of stud depth, notch rules, fire-stopping requirements)

---

## 6. Recommendations

### Short-term (next sessions)

1. **Phase 3: Wall-to-Wall Connector.** Use the cavity module's `find_adjacent_cavities()` and the junction graph to route across panel boundaries. The junction analyzer already knows which walls share edges. This should be a relatively straightforward extension of the cavity-based approach.

2. **Phase 4: Horizontal Distribution.** This is where the building spatial understanding layer (Issue #37, Phases 1-4 of the larger plan) becomes critical. Room-level Dijkstra routing requires the topology graph and MEP zone classification planned in PRP-023/024/025.

3. **Fabrication Data Export.** Each `WallRoute` already carries `entry_uv`, `exit_uv`, `pipe_radius`, and the cavity boundaries. From these, compute:
   - Stud penetration locations (U position + height) for CNC drilling
   - Plate penetration locations for floor/ceiling pass-throughs
   - Hole diameters (pipe OD + clearance per code)
   - Per-panel BOM with penetration schedules
   - Machine-readable formats (DSTV, BTL, or custom CSV for CNC routers)

4. **Junction integration with framing.** The junction resolver produces per-layer adjustments, but these need to flow into the framing generator to adjust stud lengths, plate extents, and corner post configurations. The data is ready; the integration path needs building.

### Medium-term (architecture)

5. **Cavity as universal coordination layer.** Make the cavity module the single source of truth for "available space within a wall." Insulation fills cavities. Electrical runs through cavities. Nailing schedules reference cavity boundaries. Sheathing fastener patterns align with cavity edges. This prevents every downstream module from independently computing stud positions.

6. **Assembly-aware routing.** The assembly extractor already parses multi-layer walls. Pipes need to know which layer they are in (structural stud layer vs furring vs service cavity). The cavity decomposer could accept layer-specific framing data to produce layer-aware cavities.

7. **Validation and code compliance.** Pipe penetration through studs has code requirements (IRC R602.6): max hole diameter = 40% of stud depth for bored holes, max notch depth = 25% of stud depth, minimum 5/8" from stud edge. The cavity-based system provides the perfect hook for these checks: validate at the point where a route crosses from one cavity to another.

8. **Feedback loop to framing.** Currently, framing is generated independently and routing works around it. The ideal workflow would allow routing constraints to influence framing decisions: "this wall needs a service cavity," "move this stud 2 inches to accommodate a drain stack," "add blocking at 4'-0" for horizontal distribution."

### Long-term (product vision)

9. **LOD 100 -> LOD 400 automated pipeline.** The progressive refinement pattern means a schematic Revit model can immediately show approximate MEP routing. As the model develops (framing generated, cells decomposed, assemblies defined), routing automatically improves in fidelity. The fabrication data export is the final LOD 400 step -- from "a pipe goes here" to "drill a 1.5" hole at (x, y) on stud #7 of panel W-A3."

10. **Digital twin integration.** Each cavity, each route, each penetration has a unique ID and full geometric data. This is the foundation for a digital twin where the manufacturer can track: "Panel W-A3, Cavity 5: 1" DHW pipe at U=2.35, penetrates bottom plate at (x, y, z), connects to Panel W-B1 Cavity 3 below."

11. **Manufacturer-specific profiles.** Different panelized wall manufacturers have different constraints: maximum panel width, transport limits, crane capacity, fastening preferences, layer stacking order. The layer rules engine is designed for extensibility -- per-manufacturer rule sets would allow the same Revit model to produce fabrication data for different factories.

12. **Multi-trade coordination.** The cavity module can serve as the shared spatial model for all trades: plumbing routes in lower cavities, electrical runs in upper cavities, HVAC penetrates at specific heights. Trade priority rules (plumbing first, then electrical, then HVAC) can be enforced through the occupancy map.

---

## 7. Architecture Summary

```
Revit Model (LOD 100)
    |
    v
[Wall Analyzer] -----------> walls_json (geometry, openings, assembly)
    |                              |
    |                              v
    |                    [Junction Analyzer] --> junctions_json
    |                              |
    v                              v
[Cell Decomposer] --> cell_json   [Multi-Layer Sheathing] --> multi_layer_json
    |                                                              |
    v                                                              v
[Framing Generator] --> framing_json                    [Geometry Converter]
    |                                                              |
    v                                                              v
[Cavity Decomposer] --> cavities                            Sheathing Breps
    |
    v
[MEP Connector Extractor] --> connectors_json
    |
    v
[MEP Fixture Router] --> penetrations_json (Phase 1)
    |
    v
[MEP Wall Router] --> wall_routes_json (Phase 2)
    |
    v
[MEP Route Visualizer] --> curves, colors (debug)
    |
    v
[Phase 3: Wall-to-Wall] --> (future)
    |
    v
[Phase 4: Distribution] --> (future)
    |
    v
[Phase 5: To-Riser] --> (future)
    |
    v
[Fabrication Export] --> CNC files, BOMs, shop drawings (future)
    |
    v
Revit Model (LOD 400)
```

---

## 8. Files Changed (vs main branch)

### New Source Files
- `src/timber_framing_generator/cavity/cavity.py`
- `src/timber_framing_generator/cavity/cavity_decomposer.py`
- `src/timber_framing_generator/cavity/__init__.py`
- `src/timber_framing_generator/mep/routing/fixture_router.py`
- `src/timber_framing_generator/mep/routing/wall_router.py` (rewritten)
- `src/timber_framing_generator/mep/routing/domains.py`
- `src/timber_framing_generator/wall_junctions/__init__.py`
- `src/timber_framing_generator/wall_junctions/junction_types.py`
- `src/timber_framing_generator/wall_junctions/junction_detector.py`
- `src/timber_framing_generator/wall_junctions/junction_resolver.py`
- `src/timber_framing_generator/wall_data/assembly_extractor.py`
- `src/timber_framing_generator/materials/layer_rules.py`
- `src/timber_framing_generator/sheathing/multi_layer_generator.py`

### New GH Components
- `scripts/gh_mep_fixture_router.py`
- `scripts/gh_mep_wall_router.py`
- `scripts/gh_junction_analyzer.py`
- `scripts/gh_multi_layer_sheathing.py`

### Updated Files
- `scripts/gh_mep_route_visualizer.py` (scope fix, format compat, color mapping)
- `scripts/gh_sheathing_generator.py`
- `scripts/gh_sheathing_geometry_converter.py`
- `scripts/gh_wall_analyzer.py`
- `src/timber_framing_generator/mep/routing/wall_graph.py` (L-shaped connections)
- `src/timber_framing_generator/sheathing/sheathing_generator.py`
- `src/timber_framing_generator/sheathing/sheathing_geometry.py`
- `src/timber_framing_generator/config/assembly.py`
- `src/timber_framing_generator/core/mep_system.py`
- `src/timber_framing_generator/mep/plumbing/connector_extractor.py`

### New Test Files (13)
- `tests/cavity/test_cavity_decomposer.py`
- `tests/mep/routing/test_fixture_router.py`
- `tests/mep/routing/test_wall_router.py`
- `tests/wall_junctions/test_junction_detector.py`
- `tests/wall_junctions/test_junction_resolver.py`
- `tests/wall_junctions/test_wall_assembly.py`
- `tests/wall_data/test_assembly_extractor.py`
- `tests/materials/test_layer_rules.py`
- `tests/sheathing/test_multi_layer_generator.py`
- `tests/sheathing/test_sheathing_generator.py`
- `tests/sheathing/test_sheathing_geometry.py`
- `tests/mep/plumbing/test_connector_extractor.py`
- `tests/wall_junctions/conftest.py`

### New PRPs
- `PRPs/PRP-022--mep-hierarchical-routing.md`
- `PRPs/PRP-023--wall-junction-analyzer.md`
- `PRPs/PRP-024--wall-assembly-layers.md`

---

*This document captures the state of the system as of 2026-02-05. It is intended as a reference for future development sessions and for onboarding new contributors to the MEP routing and wall assembly pipeline.*
