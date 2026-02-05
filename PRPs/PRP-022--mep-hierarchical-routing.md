# PRP-022: MEP Hierarchical Routing Architecture

> **Version:** 1.1
> **Created:** 2026-02-05
> **Updated:** 2026-02-05
> **Status:** Draft
> **Branch:** `feature/mep-hierarchical-routing`
> **Parent Issue:** [#37 - Building Spatial Understanding Layer](https://github.com/a01110946/timber_framing_generator/issues/37)

---

## Goal

Re-architect the monolithic MEP routing pipeline into a **5-phase hierarchical workflow** where each phase solves routing at a specific spatial scale, passing results downstream. Each phase becomes an independent, testable, and visualizable Grasshopper component.

## Why

- **Current system fails all routes** (0/23 successful) because the monolithic graph places nodes in abstract 2D space with zero domain transitions — the graph has no edges to traverse
- **Debugging is impossible**: a single component that tries to solve fixture-to-stack in one shot produces opaque failures with no intermediate state to inspect
- **Missing spatial scale**: there is no horizontal distribution phase — pipes must route through ceiling/floor plenums to reach corridors (multi-family) or cluster rooms (single-family) before reaching stacks
- **Offsite construction**: wall-to-wall routing is a distinct concern for prefab panels shipped independently
- **Each phase has different constraints**: gravity for sanitary (in-wall), slope for drainage (horizontal), clearance for fire-rated shafts (to-stack)
- **Testability**: each phase can be unit-tested with mock data at its own spatial scale

## What

Replace `gh_mep_router.py` (single component) with 5 sequential components:

| # | Component | Spatial Scale | Domain |
|---|-----------|---------------|--------|
| 1 | **Fixture-to-Penetration** | Room → Wall/Floor surface | Point-to-surface |
| 2 | **In-Wall Router** | Within a single wall cavity | 2D UV grid |
| 3 | **Wall-to-Wall Connector** | Panel boundary crossings | Edge-to-edge |
| 4 | **Horizontal Distribution** | Ceiling/floor plenum across rooms | 2D XY grid |
| 5 | **To-Riser Router** | Distribution point → vertical pathway | 2D XY + vertical |

Data flows as JSON between components, following the existing pipeline pattern (`walls_json → cells_json → framing_json → ...`).

### Design Philosophy (Issue #37)

These principles apply to ALL phases:

**1. Abstract Topology, Not Building Types**

No `building_type` parameter. Topology elements are abstract and scale-independent:

| Abstract Concept | Definition | Possible Physical Forms |
|-----------------|------------|------------------------|
| **Service Wall** | Wall carrying MEP routes (any trade) | Chase wall, partition with conduits, stud bay with pipes, exterior surface-mount |
| **Riser** | Vertical MEP pathway (any trade) | Dedicated shaft room, pipe in wall cavity, conduit sleeve, exterior riser |
| **Distribution Path** | Horizontal MEP pathway | Ceiling plenum, attic, crawlspace, floor joist cavity, exposed run |
| **Convergence Point** | Where branches merge | Wall intersection, mechanical closet, ceiling junction, or nonexistent |

**2. User-in-the-Loop Interaction Model**

Every phase component follows this pattern:
- **Auto-detection succeeds** → Proceed with defaults
- **Auto-detection uncertain** → Output candidates with confidence scores; user accepts or overrides
- **Auto-detection fails** → Report what's missing + guidance; user provides via optional inputs; re-run succeeds

Every phase component has three input categories:
- **Required inputs**: Data from upstream (`connectors_json`, `walls_json`, etc.) + `run` toggle
- **Optional user-override inputs**: Take precedence over auto-detection (`service_walls`, `riser_locations`, etc.)
- **Status outputs**: `status` ("ready"/"needs_input"/"error"), `needs` (human-readable guidance), `candidates` (auto-detected with scores)

**No silent failures.** If a phase cannot proceed, it tells the user exactly what it needs and in what form.

**3. Trade-Agnostic Terminology**

| Old Term (Wrong) | New Term (Correct) |
|---|---|
| Wet Wall | **Service Wall** |
| Wet Stack | **Service Riser** |
| Shaft | **Riser Location** (abstract) |
| Corridor Chase | **Distribution Path** |
| Collection Point | **Convergence Point** |

**4. Phases Can Be Trivial or Skipped**

- Phase 4 may produce **direct routes** (fixture room → riser, no horizontal distribution needed)
- Phase 5 may target a **wall position** instead of a room (single-family riser in wall cavity)
- Back-to-back bathroom/kitchen sharing a service wall may skip Phases 3-4 entirely

### Success Criteria

- [ ] Phase 1 (Fixture-to-Penetration) routes fixtures to nearest wall/floor entry point with 100% success on test data
- [ ] Phase 2 (In-Wall) routes within wall cavities respecting stud obstacles, with visualization of wall graph
- [ ] Phase 3 (Wall-to-Wall) connects adjacent panels at their shared edges
- [ ] Phase 4 (Horizontal Distribution) routes through ceiling/floor plenums between rooms/units and corridor
- [ ] Phase 5 (To-Riser) connects distribution branches to vertical pathways (any riser type)
- [ ] Each phase outputs debug geometry (graph_pts, graph_lines) for viewport inspection
- [ ] Each phase outputs status/needs/candidates for user-in-the-loop interaction
- [ ] Each phase outputs stats_json and info for diagnostics
- [ ] End-to-end pipeline routes ≥80% of connectors on test bathroom + kitchen scenario
- [ ] Existing test suite continues to pass
- [ ] No `building_type` parameter anywhere — topology adapts via abstract concepts

---

## All Needed Context

### Documentation & References
```yaml
Project Docs:
  - file: docs/ai/ai-modular-architecture-plan.md
    why: Existing 5-component architecture pattern to mirror

  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for wall-relative positioning

  - file: docs/ai/ai-geometry-assembly-solution.md
    why: RhinoCommon vs Rhino3dmIO assembly mismatch for GH outputs

  - file: docs/ai/ai-mep-connectors-reference.md
    why: MEP connector data format from Revit extraction

  - file: docs/ai/ai-grasshopper-rhino-patterns.md
    why: GHPython component patterns, DataTrees, module reloading

Prior PRPs (routing domain knowledge):
  - file: PRPs/PRP-011--mep-routing-core-structures.md
    why: RoutingDomain, Obstacle, Point2D definitions

  - file: PRPs/PRP-013--mep-routing-graph-construction.md
    why: Graph building approach, grid resolution, edge costs

  - file: PRPs/PRP-016--mep-routing-oahs-core.md
    why: OAHS algorithm, ConnectorSequencer, ConflictResolver

  - file: PRPs/PRP-017--mep-routing-orchestrator.md
    why: SequentialOrchestrator, TradeConfig, zone strategies
```

### Current Architecture (What Exists)

```
scripts/gh_mep_router.py          ← Single GH component (REPLACE)

src/timber_framing_generator/mep/routing/
├── __init__.py                   ← Module exports
├── domains.py                    ← RoutingDomain, Obstacle, Point2D (KEEP)
├── graph.py                      ← MultiDomainGraph, TransitionEdge (REFACTOR)
├── graph_builder.py              ← UnifiedGraphBuilder, TransitionGenerator (REFACTOR)
├── wall_graph.py                 ← WallGraphBuilder (KEEP, enhance)
├── floor_graph.py                ← FloorGraphBuilder (KEEP, enhance)
├── occupancy.py                  ← OccupancyMap (KEEP)
├── targets.py                    ← RoutingTarget, TargetType (KEEP)
├── pathfinding.py                ← AStarPathfinder (KEEP)
├── multi_domain_pathfinder.py    ← MultiDomainPathfinder (KEEP)
├── oahs_router.py                ← OAHSRouter, ConnectorSequencer (KEEP, scope down)
├── orchestrator.py               ← SequentialOrchestrator (REPLACE)
├── trade_config.py               ← TradeConfig, Trade enum (KEEP)
├── target_generator.py           ← Target generation (KEEP)
├── route_segment.py              ← RouteSegment (KEEP)
├── routing_result.py             ← RoutingResult (KEEP)
├── heuristics/                   ← Trade-specific heuristics (KEEP)
├── postprocess/                  ← Sanitary slope, elbow optimization (KEEP)
└── penetration_integration.py    ← Penetration coordination (KEEP)
```

### Current Data Flow (Broken)

```
connectors_json + walls_json + targets_json
          ↓
  gh_mep_router.py
          ↓
  build_routing_graph()  ← Creates graph in abstract 2D space
          ↓                  34 wall domains, 0 transitions, 0 edges
  SequentialOrchestrator.route_building()
          ↓
  OAHSRouter.route_all()  ← All routes fail (NO_PATH)
          ↓
  routes_json (empty)
```

### Proposed Data Flow (Hierarchical)

```
connectors_json + walls_json + targets_json
          ↓
  ┌─ Phase 1: gh_mep_fixture_router.py ─────────────────┐
  │  For each fixture connector:                          │
  │    Find nearest wall/floor surface → penetration pt   │
  │  Output: penetrations_json (fixture→wall assignments) │
  └───────────────────────────────────────────────────────┘
          ↓
  ┌─ Phase 2: gh_mep_wall_router.py ────────────────────┐
  │  For each wall with assigned penetrations:            │
  │    Build UV grid graph within wall cavity             │
  │    Route from penetration to wall exit point          │
  │  Output: wall_routes_json (in-wall path segments)     │
  └──────────────────────────────────────────────────────┘
          ↓
  ┌─ Phase 3: gh_mep_wall_connector.py ─────────────────┐
  │  For each pair of adjacent wall panels:               │
  │    Match exit points across panel boundary            │
  │    Generate crossing specs (sleeve, fire-stop)        │
  │  Output: panel_crossings_json (boundary connections)  │
  └──────────────────────────────────────────────────────┘
          ↓
  ┌─ Phase 4: gh_mep_distribution_router.py ────────────┐
  │  For each ceiling/floor plenum zone:                  │
  │    Build XY grid graph in plenum space                │
  │    Route from wall exits to corridor/collection pts   │
  │    Single-family: room cluster → common area          │
  │    Multi-family: unit → corridor chase                │
  │  Output: distribution_routes_json (horizontal runs)   │
  └──────────────────────────────────────────────────────┘
          ↓
  ┌─ Phase 5: gh_mep_stack_router.py ───────────────────┐
  │  For each collection point:                           │
  │    Route to nearest vertical shaft/stack              │
  │    Apply shaft-specific constraints (fire rating,     │
  │    sizing, shared-chase rules)                        │
  │  Output: stack_routes_json (vertical connections)     │
  └──────────────────────────────────────────────────────┘
          ↓
  Final assembly: routes_json (all phases combined)
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: Assembly mismatch
# All geometry output from GH components MUST use RhinoCommonFactory
# Never use rg.Point3d() directly — use factory.create_point3d(x, y, z)

# CRITICAL: Graph nodes must exist in REAL geometry space
# Current bug: nodes at abstract (u, v) coords, not world XY
# Fix: Each domain must carry a transform to convert local→world coords

# CRITICAL: Transitions need real geometry
# Wall-to-wall transitions must match at physical corner locations
# Wall-to-floor transitions must match at base plate / top plate Z elevations

# CRITICAL: Sanitary gravity constraint
# Horizontal distribution for sanitary lines needs 1/4" per foot slope
# This means horizontal runs have a maximum practical length before
# the pipe drops too low — constrains Phase 4 routing for sanitary

# CRITICAL: Trade sequencing still applies per-phase
# Within each phase, plumbing routes first (most constrained)
# Then HVAC, then electrical (most flexible)

# GOTCHA: # r: networkx directive required in ALL GH components using networkx
# Must be on line 1 of the script

# GOTCHA: Module reloading — each component needs sys.modules clearing
# for development, but this should be removable in production
```

---

## Implementation Blueprint

### Phase 1: Fixture-to-Penetration Router

**Purpose**: For each MEP fixture connector, find the nearest wall or floor surface and compute a penetration point. This is purely geometric — no graph traversal needed.

**Algorithm**:
1. For each connector, get its 3D world location
2. Find all walls within search radius (e.g., 5 ft)
3. For each candidate wall:
   - Project connector location onto wall plane
   - Check if projection falls within wall bounds (U: 0 to wall_length, V: 0 to wall_height)
   - Compute perpendicular distance (W component)
4. Select closest wall where projection is in-bounds
5. Output: penetration point in both world coords and wall-local UVW coords

**Input/Output Contract**:
```yaml
Inputs:
  connectors_json: str  # MEP connectors with 3D locations, system types
  walls_json: str       # Wall geometry with base planes, dimensions
  search_radius: float  # Max distance to search for wall (default: 5.0 ft)
  run: bool

Outputs:
  penetrations_json: str  # Fixture-to-wall assignments
    # Schema:
    # {
    #   "penetrations": [
    #     {
    #       "connector_id": "conn_0",
    #       "system_type": "DomesticColdWater",
    #       "wall_id": "wall_15",
    #       "world_location": [x, y, z],
    #       "wall_uv": [u, v],
    #       "distance": 1.23,
    #       "side": "interior" | "exterior"
    #     }
    #   ],
    #   "unassigned": ["conn_5", "conn_12"],
    #   "status": "ready" | "needs_input",
    #   "needs": []  # e.g. ["conn_5 has no wall within 5.0 ft. Increase search_radius or add wall."]
    # }
  graph_pts: List[Point3d]   # Connector + penetration points for debug
  graph_lines: List[LineCurve]  # Connector→penetration lines for debug
  stats_json: str
  info: list
```

**Key Files**:
```yaml
CREATE: scripts/gh_mep_fixture_router.py        # GH component
CREATE: src/timber_framing_generator/mep/routing/fixture_router.py  # Core logic
CREATE: tests/mep/routing/test_fixture_router.py # Tests
```

### Phase 2: In-Wall Router

**Purpose**: For each wall that has assigned penetrations, build a 2D UV grid graph and route from penetration point to a wall exit point (top plate, bottom plate, or wall end).

**Algorithm**:
1. Group penetrations by wall_id
2. For each wall:
   - Build UV grid using existing WallGraphBuilder (already works)
   - Add penetration points as source terminals
   - Determine exit points: top-of-wall (to ceiling plenum), bottom-of-wall (to floor), wall-end (to adjacent panel)
   - Add exit points as target terminals
   - Run A* pathfinding for each source→nearest-valid-exit
3. Track occupancy to prevent conflicts between routes in same wall

**Input/Output Contract**:
```yaml
Inputs:
  penetrations_json: str   # From Phase 1
  walls_json: str          # Wall geometry
  trade_filter: str        # Optional
  grid_resolution: float   # Default: 0.333 ft (~4")
  run: bool

Outputs:
  wall_routes_json: str  # In-wall path segments
    # Schema:
    # {
    #   "wall_routes": [
    #     {
    #       "connector_id": "conn_0",
    #       "wall_id": "wall_15",
    #       "system_type": "DomesticColdWater",
    #       "path_uv": [[u0,v0], [u1,v1], ...],
    #       "path_world": [[x0,y0,z0], [x1,y1,z1], ...],
    #       "exit_type": "top" | "bottom" | "end_left" | "end_right",
    #       "exit_uv": [u, v],
    #       "exit_world": [x, y, z],
    #       "penetrations_count": 2,
    #       "cost": 12.5
    #     }
    #   ],
    #   "failed": [...]
    # }
  graph_pts: List[Point3d]     # Wall graph nodes in world coords
  graph_lines: List[LineCurve] # Wall graph edges in world coords
  stats_json: str
  info: list
```

**Key Files**:
```yaml
CREATE: scripts/gh_mep_wall_router.py
CREATE: src/timber_framing_generator/mep/routing/wall_router.py
CREATE: tests/mep/routing/test_wall_router.py
REUSE:  src/timber_framing_generator/mep/routing/wall_graph.py  # Existing
REUSE:  src/timber_framing_generator/mep/routing/pathfinding.py  # Existing
```

**Critical Detail — UV to World Transform**:
```python
# Every wall has a base_plane that maps (U, V) → World (X, Y, Z)
# U = along wall, V = vertical
# World point = base_plane.Origin + base_plane.XAxis * u + base_plane.YAxis * v
#
# For graph visualization, nodes MUST be converted to world coords:
def uv_to_world(u: float, v: float, wall: dict) -> Tuple[float, float, float]:
    origin = wall["base_plane"]["origin"]  # [x, y, z]
    x_axis = wall["base_plane"]["x_axis"]  # [dx, dy, dz]
    y_axis = wall["base_plane"]["y_axis"]  # [0, 0, 1] typically
    return (
        origin[0] + x_axis[0] * u + y_axis[0] * v,
        origin[1] + x_axis[1] * u + y_axis[1] * v,
        origin[2] + x_axis[2] * u + y_axis[2] * v,
    )
```

### Phase 3: Wall-to-Wall Connector

**Purpose**: For prefab panel boundaries, match wall route exit points that meet at shared edges. Generate crossing specifications (sleeve sizes, fire-stop requirements).

**Algorithm**:
1. Identify adjacent wall pairs from walls_json (shared edge within tolerance)
2. For each pair, match exit points from wall_routes_json:
   - Wall A's `exit_type="end_right"` ↔ Wall B's `exit_type="end_left"` (or vice versa)
   - Match by proximity (UV elevation should be close)
   - Match by system_type (same system must connect)
3. Generate crossing spec: sleeve diameter = pipe diameter + clearance

**Input/Output Contract**:
```yaml
Inputs:
  wall_routes_json: str   # From Phase 2
  walls_json: str         # Wall geometry (for adjacency detection)
  panels_json: str        # Optional panel decomposition (if available)
  tolerance: float        # Edge matching tolerance (default: 0.25 ft)
  run: bool

Outputs:
  panel_crossings_json: str
    # Schema:
    # {
    #   "crossings": [
    #     {
    #       "id": "cross_0",
    #       "wall_a_id": "wall_15",
    #       "wall_b_id": "wall_16",
    #       "connector_id": "conn_0",
    #       "system_type": "DomesticColdWater",
    #       "location_world": [x, y, z],
    #       "sleeve_diameter": 0.125,
    #       "fire_rating_required": false
    #     }
    #   ],
    #   "unmatched_exits": [...]  # Exits that go to Phase 4 instead
    # }
  graph_pts: List[Point3d]
  graph_lines: List[LineCurve]
  stats_json: str
  info: list
```

**Key Files**:
```yaml
CREATE: scripts/gh_mep_wall_connector.py
CREATE: src/timber_framing_generator/mep/routing/wall_connector.py
CREATE: tests/mep/routing/test_wall_connector.py
```

### Phase 4: Horizontal Distribution Router

**Purpose**: Route through ceiling plenums, floor joist cavities, attics, crawlspaces, or exposed runs to connect wall exit points to convergence points or directly to risers. This is the phase that bridges individual rooms to distribution paths. **May be trivial or skipped** when fixtures are directly adjacent to a riser (e.g., back-to-back bathroom/kitchen sharing a service wall).

**Use Cases** (abstract — no building_type parameter):

| Scenario | Source | Distribution Path Domain | Destination |
|----------|--------|--------------------------|-------------|
| Riser in adjacent room | Wall exit (top) | Ceiling plenum | Convergence point near riser |
| Riser in same wall | Wall exit (end) | *Direct route — skip Phase 4* | Riser location |
| Remote riser | Wall exit (top) | Attic / crawlspace / exposed | Distribution path → riser |
| Shared riser corridor | Wall exit (top/bottom) | Ceiling plenum / floor joist | Corridor convergence point |

**Algorithm**:
1. Collect all "unmatched exits" from Phase 3 + all top/bottom exits from Phase 2
2. Check for **direct routes**: if exit point is adjacent to a riser, produce a direct route (skip grid)
3. For remaining exits, build a 2D XY grid graph in the distribution path region:
   - Use auto-detected or user-provided distribution path boundaries (from zones_json Phase 3)
   - Domain type (ceiling_plenum, floor_joist, attic, crawlspace, exposed) from zones_json
4. Route each exit point to nearest convergence point or riser
5. Apply trade sequencing (plumbing first, then HVAC, then electrical)
6. Track occupancy to prevent conflicts

**User-in-the-Loop**: If no distribution path region is available and exits cannot reach a riser directly, output `status: "needs_input"` with guidance to provide `distribution_regions` (Brep boundary).

**Input/Output Contract**:
```yaml
Inputs:
  # Required
  wall_routes_json: str       # From Phase 2 (for exit points)
  panel_crossings_json: str   # From Phase 3 (for unmatched exits)
  walls_json: str             # Wall geometry (defines room boundaries)
  zones_json: str             # From Phase 3 of Issue #37 (distribution paths, risers)
  run: bool

  # Optional user overrides
  distribution_regions: List[Brep]  # User-drawn plenum/attic boundaries
  convergence_points: List[Point3d] # User-placed merge locations
  trade_filter: str                 # Optional
  grid_resolution: float            # Default: 1.0 ft

Outputs:
  distribution_routes_json: str
    # Schema:
    # {
    #   "distribution_routes": [
    #     {
    #       "connector_id": "conn_0",
    #       "system_type": "DomesticColdWater",
    #       "source_exit": {"wall_id": "wall_15", "location": [x,y,z]},
    #       "destination": {
    #         "type": "convergence_point" | "riser" | "direct",
    #         "id": "conv_1",
    #         "location": [x,y,z],
    #         "source": "auto" | "user"
    #       },
    #       "domain": "ceiling_plenum" | "floor_joist" | "attic" | "crawlspace" | "exposed" | "direct",
    #       "path_world": [[x0,y0,z0], [x1,y1,z1], ...],
    #       "slope": 0.0208,  # ft/ft for sanitary (1/4" per foot)
    #       "length": 15.3,
    #       "cost": 23.7
    #     }
    #   ],
    #   "direct_routes": [...],  # Exits that skip distribution (adjacent to riser)
    #   "status": "ready" | "needs_input",
    #   "needs": [],
    #   "failed": [...]
    # }
  graph_pts: List[Point3d]
  graph_lines: List[LineCurve]
  stats_json: str
  info: list
```

**Key Files**:
```yaml
CREATE: scripts/gh_mep_distribution_router.py
CREATE: src/timber_framing_generator/mep/routing/distribution_router.py
CREATE: tests/mep/routing/test_distribution_router.py
REUSE:  src/timber_framing_generator/mep/routing/floor_graph.py  # Existing
REUSE:  src/timber_framing_generator/mep/routing/pathfinding.py  # Existing
```

**Critical Detail — Sanitary Slope Constraint**:
```python
# Sanitary drain lines MUST slope at 1/4" per foot (0.0208 ft/ft)
# This means for a 20-ft horizontal run, the pipe drops 5" (0.417 ft)
# If ceiling height is 9 ft and pipe starts at 8.5 ft:
#   Max run before hitting 8 ft soffit = (8.5 - 8.0) / 0.0208 = 24 ft
#
# This constrains the maximum horizontal distribution distance for sanitary.
# Pressure systems (water supply, gas) have no slope constraint.
# HVAC ducts may need slope for condensate.
```

### Phase 5: To-Riser Router (renamed from "To-Stack")

**Purpose**: Connect distribution convergence points to vertical risers. Accepts **any riser type** — the component does not distinguish between shaft rooms, wall-cavity stacks, or exterior risers internally. A riser is a riser: it has a location, a capacity, and compatible systems.

**Riser Types** (abstract, from zones_json):

| Riser Type | Physical Form | Routing Target |
|------------|---------------|----------------|
| `shaft_room` | Dedicated mechanical shaft room | Room entry point |
| `wall_stack` | Pipe/conduit in wall cavity | U-position within wall |
| `exterior` | Exterior riser/penetration | Exterior wall penetration point |

**Algorithm**:
1. Collect all convergence points from Phase 4 + direct routes
2. Get riser locations from zones_json (auto-detected or user-provided)
3. For each convergence point:
   - Find compatible riser (correct trade, sufficient capacity)
   - Route from convergence point to riser entry
   - Specify vertical connection (riser tie-in elevation, direction)
4. Apply riser capacity constraints (shared risers have limited space)

**User-in-the-Loop**: If no riser is found for a trade/system, output `status: "needs_input"` with guidance to provide `riser_locations` (Point3d, Box, or Plane).

**Input/Output Contract**:
```yaml
Inputs:
  # Required
  distribution_routes_json: str  # From Phase 4
  zones_json: str                # Riser locations from Phase 3 of Issue #37
  walls_json: str                # For riser-wall association
  run: bool

  # Optional user overrides
  riser_locations: List[Point3d/Box/Plane]  # User-placed riser positions
  trade_filter: str                         # Optional

Outputs:
  riser_routes_json: str  # (renamed from stack_routes_json)
    # Schema:
    # {
    #   "riser_routes": [
    #     {
    #       "connector_id": "conn_0",
    #       "system_type": "DomesticColdWater",
    #       "convergence_point": [x, y, z],
    #       "riser_id": "riser_1",
    #       "riser_type": "wall_stack" | "shaft_room" | "exterior",
    #       "riser_location": [x, y, z],
    #       "source": "auto" | "user",
    #       "entry_elevation": 8.0,
    #       "path_world": [[x0,y0,z0], ...],
    #       "vertical_run": 9.0,
    #       "cost": 5.2
    #     }
    #   ],
    #   "riser_utilization": {
    #     "riser_1": {"capacity": 1.0, "used": 0.65, "systems": ["DCW", "DHW", "SAN"]}
    #   },
    #   "status": "ready" | "needs_input",
    #   "needs": [],
    #   "failed": [...]
    # }
  graph_pts: List[Point3d]
  graph_lines: List[LineCurve]
  stats_json: str
  info: list
```

**Key Files**:
```yaml
CREATE: scripts/gh_mep_riser_router.py     # (renamed from gh_mep_stack_router.py)
CREATE: src/timber_framing_generator/mep/routing/riser_router.py  # (renamed from stack_router.py)
CREATE: tests/mep/routing/test_riser_router.py
```

---

### Implementation Order

```yaml
Sprint 1 - Foundation (Phase 1 + Phase 2):
  Task 1: Create fixture_router.py with wall-projection logic
  Task 2: Create gh_mep_fixture_router.py GH component
  Task 3: Write test_fixture_router.py
  Task 4: Create wall_router.py wrapping existing WallGraphBuilder + pathfinding
  Task 5: Create gh_mep_wall_router.py with UV→World debug visualization
  Task 6: Write test_wall_router.py
  Task 7: Integration test: fixture→in-wall on single bathroom wall

Sprint 2 - Connectivity (Phase 3 + Phase 4):
  Task 8: Create wall_connector.py for panel boundary matching
  Task 9: Create gh_mep_wall_connector.py GH component
  Task 10: Write test_wall_connector.py
  Task 11: Create distribution_router.py for ceiling/floor plenum routing
  Task 12: Create gh_mep_distribution_router.py GH component
  Task 13: Write test_distribution_router.py
  Task 14: Integration test: bathroom cluster → corridor chase

Sprint 3 - Completion (Phase 5 + Assembly):
  Task 15: Create riser_router.py for vertical riser connections (any riser type)
  Task 16: Create gh_mep_riser_router.py GH component
  Task 17: Write test_riser_router.py
  Task 18: Create gh_mep_route_assembler.py (optional) to merge all phase outputs
  Task 19: End-to-end integration test: full bathroom + kitchen scenario
  Task 20: Deprecate/archive gh_mep_router.py (old monolithic component)
```

### File Structure

```
scripts/
├── gh_mep_router.py              # DEPRECATED (keep for reference)
├── gh_mep_fixture_router.py      # Phase 1: Fixture → Penetration
├── gh_mep_wall_router.py         # Phase 2: In-Wall Routing
├── gh_mep_wall_connector.py      # Phase 3: Panel Boundary Crossing
├── gh_mep_distribution_router.py # Phase 4: Horizontal Distribution
├── gh_mep_riser_router.py        # Phase 5: To-Riser Connection
└── gh_mep_route_assembler.py     # Optional: Merge all phases

src/timber_framing_generator/mep/routing/
├── fixture_router.py             # Phase 1 core logic
├── wall_router.py                # Phase 2 core logic (wraps WallGraphBuilder)
├── wall_connector.py             # Phase 3 core logic
├── distribution_router.py        # Phase 4 core logic (wraps FloorGraphBuilder)
├── riser_router.py               # Phase 5 core logic
├── route_assembler.py            # Optional: merge results
│
│   # Existing modules (KEEP):
├── domains.py                    # RoutingDomain, Obstacle
├── graph.py                      # MultiDomainGraph (used per-phase, not globally)
├── wall_graph.py                 # WallGraphBuilder (reused by Phase 2)
├── floor_graph.py                # FloorGraphBuilder (reused by Phase 4)
├── pathfinding.py                # AStarPathfinder (reused by Phase 2, 4, 5)
├── occupancy.py                  # OccupancyMap (reused per-phase)
├── targets.py                    # RoutingTarget
├── trade_config.py               # TradeConfig
├── oahs_router.py                # OAHSRouter (may be reused in Phase 2)
├── heuristics/                   # Trade heuristics (reused)
└── postprocess/                  # Sanitary post-processing (reused in Phase 4)

tests/mep/routing/
├── test_fixture_router.py        # Phase 1 tests
├── test_wall_router.py           # Phase 2 tests
├── test_wall_connector.py        # Phase 3 tests
├── test_distribution_router.py   # Phase 4 tests
├── test_riser_router.py          # Phase 5 tests
│
│   # Existing tests (KEEP):
├── test_domains.py
├── test_graph.py
├── test_graph_builder.py
├── test_pathfinding.py
├── test_oahs_router.py
└── test_orchestrator.py          # Update to test new orchestration
```

### Code Patterns & Examples

**GH Component Pattern** (all 5 phases follow this):
```python
# r: networkx
# File: scripts/gh_mep_fixture_router.py
"""Phase 1: Fixture-to-Penetration Router...

Outputs:
    Penetrations JSON (penetrations_json) - str: ...
    Graph Nodes (graph_pts) - List[Point3d]: ...
    Graph Edges (graph_lines) - List[LineCurve]: ...
    Stats JSON (stats_json) - str: ...
    Info (info) - list: ...
"""
import sys
import json

# Force module reload (development)
for mod_name in list(sys.modules.keys()):
    if 'timber_framing_generator' in mod_name:
        del sys.modules[mod_name]

import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")
import Grasshopper

# ... setup_component(), validate_inputs(), main() pattern ...

if __name__ == "__main__":
    penetrations_json, graph_pts, graph_lines, stats_json, info = main()
```

**Fixture-to-Wall Projection** (Phase 1 core algorithm):
```python
def find_nearest_wall(
    connector_location: Tuple[float, float, float],
    walls: List[dict],
    search_radius: float = 5.0,
) -> Optional[dict]:
    """Project connector onto nearest wall surface.

    Args:
        connector_location: World XYZ of fixture connector
        walls: Wall data dicts with base_plane, length, height
        search_radius: Maximum search distance in feet

    Returns:
        Dict with wall_id, uv coords, distance, side — or None
    """
    cx, cy, cz = connector_location
    best = None
    best_dist = search_radius

    for wall in walls:
        origin = wall["base_plane"]["origin"]
        x_axis = wall["base_plane"]["x_axis"]
        z_axis = wall["base_plane"]["z_axis"]  # wall normal
        length = wall["length"]
        height = wall["height"]

        # Vector from wall origin to connector
        dx = cx - origin[0]
        dy = cy - origin[1]
        dz = cz - origin[2]

        # Project onto wall axes
        u = dx * x_axis[0] + dy * x_axis[1] + dz * x_axis[2]
        v = dz  # V is vertical (world Z relative to wall base)
        w = dx * z_axis[0] + dy * z_axis[1] + dz * z_axis[2]  # Through-wall

        # Check if projection is within wall bounds
        if 0 <= u <= length and 0 <= v <= height:
            dist = abs(w)
            if dist < best_dist:
                best_dist = dist
                best = {
                    "wall_id": wall["id"],
                    "wall_uv": [u, v],
                    "world_location": [
                        origin[0] + x_axis[0] * u,
                        origin[1] + x_axis[1] * u,
                        origin[2] + v,
                    ],
                    "distance": dist,
                    "side": "interior" if w > 0 else "exterior",
                }

    return best
```

**UV→World Graph Visualization** (Phase 2 — fixes the current bug):
```python
def extract_wall_graph_geometry(
    wall_graph: nx.Graph,
    wall_data: dict,
    factory,
) -> Tuple[list, list]:
    """Convert wall UV graph to world-space geometry for visualization.

    This is the critical fix: current system outputs nodes in abstract UV space.
    This function transforms them to real-world coordinates.
    """
    origin = wall_data["base_plane"]["origin"]
    x_axis = wall_data["base_plane"]["x_axis"]

    points = []
    lines = []

    for node_id, data in wall_graph.nodes(data=True):
        u, v = data.get("pos", (0, 0))
        wx = origin[0] + x_axis[0] * u
        wy = origin[1] + x_axis[1] * u
        wz = origin[2] + v  # V = vertical

        pt = factory.create_point3d(wx, wy, wz)
        if pt:
            points.append(pt)

    for u_node, v_node in wall_graph.edges():
        u_pos = wall_graph.nodes[u_node].get("pos", (0, 0))
        v_pos = wall_graph.nodes[v_node].get("pos", (0, 0))

        p1 = (
            origin[0] + x_axis[0] * u_pos[0],
            origin[1] + x_axis[1] * u_pos[0],
            origin[2] + u_pos[1],
        )
        p2 = (
            origin[0] + x_axis[0] * v_pos[0],
            origin[1] + x_axis[1] * v_pos[0],
            origin[2] + v_pos[1],
        )
        line = factory.create_line_curve(p1, p2)
        if line:
            lines.append(line)

    return points, lines
```

### Testing Strategy

**Unit Tests (no Rhino required)**:
```python
# Test Phase 1: Fixture-to-Penetration
def test_find_nearest_wall_direct_projection():
    """Connector directly in front of wall projects correctly."""
    wall = make_wall(origin=(0,0,0), direction=(1,0,0), length=10, height=9)
    result = find_nearest_wall((5, 2, 4), [wall])
    assert result["wall_id"] == wall["id"]
    assert abs(result["wall_uv"][0] - 5.0) < 0.01  # U along wall
    assert abs(result["wall_uv"][1] - 4.0) < 0.01  # V = height

def test_find_nearest_wall_out_of_range():
    """Connector too far from any wall returns None."""
    wall = make_wall(origin=(0,0,0), direction=(1,0,0), length=10, height=9)
    result = find_nearest_wall((0, 50, 0), [wall], search_radius=5.0)
    assert result is None

# Test Phase 2: In-Wall Routing
def test_wall_route_simple():
    """Route from penetration to top-of-wall exit in simple wall."""
    wall = make_wall_with_studs(length=4, height=9, stud_spacing=1.333)
    route = route_in_wall(
        wall=wall,
        entry_uv=(2.0, 3.0),
        exit_type="top",
    )
    assert route is not None
    assert route["exit_uv"][1] == pytest.approx(9.0, abs=0.5)

# Test Phase 4: Horizontal Distribution
def test_distribution_sanitary_slope():
    """Sanitary distribution respects 1/4 inch per foot slope."""
    route = route_distribution(
        source=(5, 10, 8.5),
        destination=(20, 10, 8.5),
        system_type="SanitaryDrain",
    )
    # 15 ft run at 1/4"/ft = 3.75" drop = 0.3125 ft
    end_z = route["path_world"][-1][2]
    assert end_z < 8.5  # Must drop
    assert abs(end_z - (8.5 - 0.3125)) < 0.05
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Lint new modules
python -m flake8 src/timber_framing_generator/mep/routing/fixture_router.py --max-line-length=88
python -m flake8 src/timber_framing_generator/mep/routing/wall_router.py --max-line-length=88
python -m flake8 src/timber_framing_generator/mep/routing/wall_connector.py --max-line-length=88
python -m flake8 src/timber_framing_generator/mep/routing/distribution_router.py --max-line-length=88
python -m flake8 src/timber_framing_generator/mep/routing/riser_router.py --max-line-length=88

# Type check
python -m mypy src/timber_framing_generator/mep/routing/
```

### Level 2: Unit Tests
```bash
# Per-phase tests
python -m pytest tests/mep/routing/test_fixture_router.py -v
python -m pytest tests/mep/routing/test_wall_router.py -v
python -m pytest tests/mep/routing/test_wall_connector.py -v
python -m pytest tests/mep/routing/test_distribution_router.py -v
python -m pytest tests/mep/routing/test_riser_router.py -v

# Full routing test suite
python -m pytest tests/mep/routing/ -v

# All project tests (regression)
python -m pytest tests/ -v
```

### Level 3: Integration Test (Grasshopper)
```
1. Open Rhino 8 with Grasshopper
2. Create new GH definition with 5 phase components in series
3. Connect: Wall Analyzer → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
4. Select test walls (bathroom + kitchen)
5. Toggle run=True on Phase 1, inspect penetrations_json + debug geometry
6. Toggle run=True on Phase 2, inspect wall graph in viewport (should overlay on walls)
7. Continue through phases, verifying each intermediate JSON is valid
8. Final: verify routes visible from fixture to stack
```

---

## Final Checklist

- [ ] Phase 1: fixture_router.py + GH component + tests passing
- [ ] Phase 2: wall_router.py + GH component + tests passing (graph visible on walls)
- [ ] Phase 3: wall_connector.py + GH component + tests passing
- [ ] Phase 4: distribution_router.py + GH component + tests passing
- [ ] Phase 5: riser_router.py + GH component + tests passing (any riser type)
- [ ] All existing tests still pass: `python -m pytest tests/ -v`
- [ ] No linting errors: `python -m flake8 src/timber_framing_generator/mep/routing/`
- [ ] Each GH component outputs debug geometry visible in Rhino viewport
- [ ] JSON contracts between phases are documented and validated
- [ ] Every phase reports status/needs when auto-detection fails (no silent failures)
- [ ] End-to-end: fixture → penetration → wall route → distribution → riser works
- [ ] Old gh_mep_router.py archived/deprecated

---

## Anti-Patterns to Avoid

- **Don't build a single global graph** — each phase builds its own scoped graph
- **Don't mix spatial scales** — wall routing (inches) and distribution routing (feet) are separate domains
- **Don't skip UV→World transform** — all debug geometry must be in world coordinates
- **Don't route sanitary without slope** — gravity lines need 1/4" per foot minimum
- **Don't ignore phase boundaries** — each phase's output JSON is the contract; don't leak internal state
- **Don't try to solve everything in one pass** — the whole point is incremental, debuggable phases
- **Don't use a `building_type` parameter** — topology adapts via abstract concepts (Service Wall, Riser, Distribution Path), not hardcoded building categories
- **Don't fail silently** — every phase must report `status`, `needs`, and `candidates` when auto-detection is uncertain
- **Don't assume all service walls are "wet"** — service walls carry any trade (plumbing, electrical, HVAC, data)
- **Don't create new graph libraries** — reuse existing WallGraphBuilder, FloorGraphBuilder, AStarPathfinder
- **Don't forget `# r: networkx`** — every GH component using networkx needs this on line 1
- **Don't use `rg.Point3d()` directly** — use RhinoCommonFactory for all geometry output

---

## Notes

### Migration Strategy

The old `gh_mep_router.py` can remain in the codebase during development. The new components are additive — they don't modify existing files. Once the 5-phase pipeline is validated:
1. Mark `gh_mep_router.py` as deprecated (add `# DEPRECATED` header)
2. Update CLAUDE.md project structure to reflect new components
3. Remove old orchestrator imports from `__init__.py` if no longer needed

### Future Extensions

- **Phase 2.5 — Stud Penetration Scheduler**: After in-wall routing, generate actual penetration schedules (hole sizes, reinforcement requirements) per IRC/IBC code
- **Phase 4.5 — HVAC Duct Sizer**: After distribution routing, size ducts based on CFM requirements and available plenum space
- **Multi-story**: Phase 5 connects floors; vertical routing through floor assemblies becomes its own sub-phase
- **Clash Detection**: Post-assembly, run clash detection across all phase outputs to find trade conflicts
