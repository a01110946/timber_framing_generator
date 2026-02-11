# PRP-023: Wall Junction Analyzer

> **Version:** 1.0
> **Created:** 2026-02-05
> **Status:** Draft
> **Branch:** feature/wall-junction-analyzer

---

## Goal

Create a Wall Junction Analyzer component that builds a wall centerline graph, classifies junction types (L-corner, T-intersection, X-crossing, free end), resolves join strategies (butt/miter), and outputs **per-wall, per-end, per-layer extension/trim adjustments** so downstream components (framing, sheathing, finishes) generate geometry that meets cleanly at wall intersections.

---

## Why

### Business Value
- **Eliminates geometry collisions**: Currently, framing and sheathing extend to wall centerline endpoints and overlap/collide at corners (visible in Rhino viewport as red/green clashes)
- **Accurate material takeoffs**: Extension and trimming adjustments affect panel counts, stud counts, and waste calculations
- **Construction-ready output**: Real framing requires junction-aware details — corner posts, ladder blocking, sheathing wraps — none of which exist today

### Technical Requirements
- **Layer-aware**: Different wall layers (framing core, exterior sheathing, interior finish) need different extension amounts at the same junction
- **User-overridable**: Auto-detect join type with confidence, but allow user to override any junction
- **Pipeline integration**: Output `junctions_json` consumed by Cell Decomposer, Sheathing Generator, Framing Generator, and future Finish Generator

### Problems Solved
1. Framing geometry overlaps at wall corners and T-intersections
2. Sheathing panels extend into adjacent wall volumes
3. No awareness of which wall "wraps" vs "butts" at corners
4. Corner handler exists in `panels/corner_handler.py` but is isolated from framing/sheathing pipeline
5. Each wall processed independently — no neighbor awareness

---

## What

### User-Visible Behavior

**Input**: `walls_json` from Wall Analyzer + optional `junction_overrides` JSON
**Output**:
- `junctions_json` — graph + per-layer adjustments for every wall end at every junction
- `graph_pts` — junction node positions for visual debugging
- `graph_lines` — wall edges for visual debugging
- `summary` — junction counts by type, adjustment statistics

### Pipeline Integration

```
Wall Analyzer → walls_json
                    ↓
           Junction Analyzer (NEW)  ←  junction_overrides (optional)
                    ↓
              junctions_json
                    ↓
    ┌───────────────┼───────────────────────┐
    ↓               ↓                       ↓
Cell Decomposer  Sheathing Generator    Future: Finish Generator
(corner studs,   (extend/trim panels    (extend/trim gypsum
 ladder blocking) per junction)          per junction)
```

### Success Criteria

- [ ] Detects all junction nodes where wall endpoints meet within tolerance
- [ ] Correctly classifies L-corner, T-intersection, X-crossing, free-end junctions
- [ ] Resolves butt join direction (which wall extends, which trims) with configurable priority
- [ ] Resolves miter joins at non-orthogonal angles
- [ ] Calculates per-layer adjustments (framing core, exterior sheathing, interior finish)
- [ ] Supports user override of join type and priority at any junction
- [ ] Outputs valid `junctions_json` consumed by downstream components
- [ ] Graph visualization outputs (points + lines) for Grasshopper debugging
- [ ] Handles T-intersections (wall ending mid-span of another wall)
- [ ] Unit tests pass for all junction types and edge cases
- [ ] Reuses existing endpoint-matching logic from `corner_handler.py`

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-modular-architecture-plan.md
    why: Overall system architecture and component pipeline

  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system — junctions operate in 2D plan (U-axis along wall)

  - file: docs/ai/ai-development-guidelines.md
    why: Coding standards, type hints, docstrings format

Core Implementations:
  - file: src/timber_framing_generator/panels/corner_handler.py
    why: >
      CRITICAL - Contains existing corner detection algorithm (endpoint matching,
      angle calculation, extend/recede logic). Reuse and extend, don't duplicate.
      Key functions: detect_wall_corners(), calculate_corner_adjustments(),
      _points_close(), _calculate_angle_between_walls()

  - file: src/timber_framing_generator/core/json_schemas.py
    why: >
      WallData schema (all fields), WallCornerInfo, WallCornerAdjustment dataclasses.
      New junction dataclasses should follow these patterns.

  - file: src/timber_framing_generator/config/assembly.py
    why: >
      WallAssembly with hardcoded layer thicknesses:
      exterior=0.75", core=3.5", interior=0.5".
      Used as defaults until Revit compound wall extraction is implemented.

  - file: scripts/gh_sheathing_generator.py
    why: Pattern for GHPython component with JSON I/O, config parsing, setup_component()

  - file: scripts/gh_wall_analyzer.py
    why: Upstream component — understand walls_json output format

  - file: src/timber_framing_generator/wall_data/revit_data_extractor.py
    why: >
      Currently extracts wall_thickness as single float. Does NOT extract
      Revit CompoundStructure. Layer data comes from config/assembly.py defaults.

Prior PRPs:
  - file: PRPs/PRP-009-wall-panelization.md
    why: Panel decomposition uses corner adjustments — junction analyzer replaces this
  - file: PRPs/PRP-010-sheathing-geometry-converter.md
    why: Pattern for geometry pipeline component PRP
```

### Current Codebase Structure

```
src/timber_framing_generator/
├── panels/
│   ├── corner_handler.py        # REUSE - Corner detection & adjustment algorithm
│   ├── panel_decomposer.py      # REFERENCE - Uses corner adjustments
│   └── __init__.py
├── core/
│   ├── json_schemas.py          # MODIFY - Add junction dataclasses
│   └── material_system.py       # REFERENCE
├── config/
│   ├── assembly.py              # REFERENCE - WallAssembly layer thicknesses
│   └── config.py                # REFERENCE - Default config values
├── wall_data/
│   └── revit_data_extractor.py  # REFERENCE - Wall data extraction
├── sheathing/
│   └── sheathing_generator.py   # MODIFY (later) - Consume junctions_json
├── cell_decomposition/
│   └── cell_segmentation.py     # MODIFY (later) - Consume junctions_json
└── framing_elements/
    └── framing_generator.py     # MODIFY (later) - Consume junctions_json

scripts/
├── gh_wall_analyzer.py          # REFERENCE - Upstream component
├── gh_sheathing_generator.py    # REFERENCE - Pattern for component structure
└── gh_cell_decomposer.py        # REFERENCE - Pattern for component structure
```

### Desired Structure (files to add/modify)

```
src/timber_framing_generator/
└── wall_junctions/              # NEW MODULE
    ├── __init__.py              # Exports: analyze_junctions, JunctionGraph, etc.
    ├── junction_types.py        # Data models: JunctionNode, WallConnection, LayerAdjustment
    ├── junction_detector.py     # Graph construction + junction classification
    └── junction_resolver.py     # Join resolution + per-layer adjustment calculation

src/timber_framing_generator/
└── core/
    └── json_schemas.py          # MODIFY - Add junction-related dataclasses

scripts/
└── gh_junction_analyzer.py      # NEW - GHPython component

tests/
└── wall_junctions/
    ├── __init__.py
    ├── test_junction_detector.py
    ├── test_junction_resolver.py
    └── conftest.py              # Shared fixtures (mock walls at various junction types)
```

### Known Gotchas & Library Quirks

```yaml
CRITICAL - Endpoint Tolerance:
  issue: >
    Wall endpoints from Revit may not be exactly coincident. Centerlines
    join at the intersection point, but floating-point precision means
    endpoints may differ by up to 0.01-0.1 feet.
  solution: Use tolerance-based matching (default 0.1 ft = ~1.2 inches)
  reference: corner_handler.py uses 0.1 ft default

CRITICAL - T-Intersection Detection:
  issue: >
    T-intersections have one wall's endpoint meeting another wall's
    MID-SPAN, not its endpoint. The current corner_handler only detects
    endpoint-to-endpoint connections. T-intersections require
    point-to-line proximity testing.
  solution: >
    For each wall endpoint, check proximity to all other wall centerline
    SEGMENTS (not just endpoints). Use point-to-line-segment distance.

CRITICAL - Layer Thickness Source:
  issue: >
    Revit compound wall structure (GetCompoundStructure) is NOT extracted.
    wall_thickness is a single float. Layer breakdown must come from
    config/assembly.py defaults.
  solution: >
    Phase 1: Use WallAssembly defaults (ext=0.75", core=3.5", int=0.5").
    Phase 2 (future PRP): Extract Revit CompoundStructure in wall analyzer.
    Design the system so layer source is pluggable.

IMPORTANT - Wall Direction Consistency:
  issue: >
    Wall direction (base_curve_start → base_curve_end) is arbitrary from
    Revit. Two walls meeting at a corner may have start→end pointing
    TOWARD or AWAY from the junction. The adjustment sign (extend vs trim)
    depends on which end of the wall is at the junction.
  solution: >
    Always track which end ("start" or "end") is at each junction.
    Extend = move endpoint AWAY from wall center (increase length).
    Trim = move endpoint TOWARD wall center (decrease length).

IMPORTANT - Angle Calculation:
  issue: >
    Walls meeting at 180° (collinear/inline) are NOT junctions — they're
    wall continuations. Must filter these out during classification.
  solution: Use angle threshold (e.g., 170°-180° = inline, skip)

IMPORTANT - Multiple Walls at One Node:
  issue: >
    3+ walls can meet at a single junction (Y, X, or complex multi-way).
    Binary extend/recede logic doesn't apply. Must handle pairwise.
  solution: >
    Process multi-wall junctions as sets of pairwise relationships.
    Each pair gets its own resolution. For Phase 1, warn on 3+ wall
    junctions and apply best-effort resolution.
```

---

## Implementation Blueprint

### Data Models

```python
# File: src/timber_framing_generator/wall_junctions/junction_types.py

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum


class JunctionType(Enum):
    """Classification of wall junction geometry."""
    FREE_END = "free_end"              # Wall endpoint connects to nothing
    L_CORNER = "l_corner"              # Two walls meeting at angle (typically 90°)
    T_INTERSECTION = "t_intersection"  # One wall ending mid-span of another
    X_CROSSING = "x_crossing"          # Two walls crossing through each other
    INLINE = "inline"                  # Two collinear walls (continuation)
    MULTI_WAY = "multi_way"            # 3+ walls meeting at one point


class JoinType(Enum):
    """How two walls connect at a junction."""
    BUTT = "butt"    # One wall extends, other trims square
    MITER = "miter"  # Both walls cut at bisector angle
    NONE = "none"    # Free end, no join needed


class AdjustmentType(Enum):
    """Direction of wall length adjustment."""
    EXTEND = "extend"  # Wall gets longer (endpoint moves away from center)
    TRIM = "trim"      # Wall gets shorter (endpoint moves toward center)
    MITER = "miter"    # Wall is cut at an angle
    NONE = "none"      # No adjustment (free end)


@dataclass
class WallConnection:
    """A wall's participation in a junction."""
    wall_id: str
    end: str                      # "start" or "end"
    direction: Tuple[float, float, float]  # Wall direction vector at this end
    angle_at_junction: float      # Angle relative to reference (degrees)
    wall_thickness: float         # Total wall thickness (feet)
    wall_length: float            # Wall length (feet)
    is_midspan: bool = False      # True if junction is at wall's mid-span (T-int)
    midspan_u: Optional[float] = None  # U-coordinate along wall where T meets


@dataclass
class JunctionNode:
    """A point where walls meet."""
    id: str
    position: Tuple[float, float, float]  # World XYZ
    junction_type: JunctionType
    connections: List[WallConnection]
    resolved: bool = False  # True after join resolution


@dataclass
class WallLayerInfo:
    """Thickness breakdown for a wall's layers."""
    wall_id: str
    total_thickness: float        # feet
    exterior_thickness: float     # feet (sheathing/cladding)
    core_thickness: float         # feet (framing structural layer)
    interior_thickness: float     # feet (gypsum/finish)
    source: str = "default"       # "default" | "revit" | "override"


@dataclass
class LayerAdjustment:
    """Per-layer extension/trim at one end of one wall."""
    wall_id: str
    end: str                      # "start" or "end"
    junction_id: str              # Which junction this applies to
    layer_name: str               # "core", "exterior", "interior"
    adjustment_type: AdjustmentType
    amount: float                 # Distance in feet (always positive)
    miter_angle: Optional[float] = None  # Degrees, for miter joins
    connecting_wall_id: str = ""  # The other wall at this junction


@dataclass
class JunctionResolution:
    """Resolved join strategy for a pair of walls at a junction."""
    junction_id: str
    join_type: JoinType           # butt or miter
    primary_wall_id: str          # Wall that extends (butt) or both (miter)
    secondary_wall_id: str        # Wall that trims (butt) or both (miter)
    confidence: float             # 0.0-1.0, how confident the auto-detection is
    reason: str                   # Human-readable explanation
    layer_adjustments: List[LayerAdjustment] = field(default_factory=list)
    is_user_override: bool = False


@dataclass
class JunctionGraph:
    """Complete wall junction graph with resolutions."""
    nodes: Dict[str, JunctionNode]        # junction_id → node
    wall_layers: Dict[str, WallLayerInfo] # wall_id → layer info
    resolutions: List[JunctionResolution] # All resolved junctions
    wall_adjustments: Dict[str, List[LayerAdjustment]]  # wall_id → adjustments

    def get_adjustments_for_wall(self, wall_id: str) -> List[LayerAdjustment]:
        """Get all layer adjustments for a specific wall."""
        return self.wall_adjustments.get(wall_id, [])

    def get_adjustments_for_wall_end(
        self, wall_id: str, end: str
    ) -> List[LayerAdjustment]:
        """Get layer adjustments for a specific wall end."""
        return [
            adj for adj in self.wall_adjustments.get(wall_id, [])
            if adj.end == end
        ]
```

### Algorithm Overview

```
Phase 1: Graph Construction
  Input:  walls_json (list of WallData dicts)
  Output: Dict[str, JunctionNode] (nodes with connections)

  1. Extract all wall endpoints (start, end) with wall metadata
  2. For each endpoint, find nearby endpoints (tolerance matching)     → L-corners, X-crossings
  3. For each endpoint, find nearby wall SEGMENTS (point-to-line)      → T-intersections
  4. Group matched points into junction nodes
  5. Build JunctionNode for each group with WallConnection list

Phase 2: Junction Classification
  Input:  Dict[str, JunctionNode]
  Output: Same, with junction_type set on each node

  For each node, based on connection count and angles:
    1 connection  → FREE_END
    2 connections, angle ~180° → INLINE
    2 connections, angle < 170° → L_CORNER
    3 connections, one pair ~180° → T_INTERSECTION
    3 connections, no pair ~180° → MULTI_WAY (Y-junction)
    4+ connections → X_CROSSING or MULTI_WAY

Phase 3: Join Resolution
  Input:  Classified nodes + optional user overrides
  Output: List[JunctionResolution]

  For each non-free-end junction:
    1. Determine default join type (butt for L/T, configurable for miter)
    2. Determine priority (which wall extends):
       - Exterior wall > interior wall
       - Longer wall > shorter wall
       - Continuous wall in T > terminating wall in T
       - User override > all
    3. Apply join type and priority → JunctionResolution

Phase 4: Per-Layer Adjustment Calculation
  Input:  JunctionResolutions + WallLayerInfo for each wall
  Output: Dict[str, List[LayerAdjustment]] (wall_id → adjustments)

  For each resolution:
    For BUTT join:
      Primary wall (extends):
        core:     extend by secondary.core_thickness / 2
        exterior: extend by secondary.total_thickness / 2
        interior: extend by secondary.total_thickness / 2
      Secondary wall (trims):
        core:     trim by primary.core_thickness / 2
        exterior: trim by primary.core_thickness / 2 (butts against primary's sheathing)
        interior: trim by primary.core_thickness / 2

    For MITER join:
      Both walls:
        All layers: miter at bisector angle, extend amount depends on
                    layer offset from centerline and junction angle
```

---

### Tasks (in execution order)

```yaml
Task 1: Create junction_types.py data models
  - CREATE: src/timber_framing_generator/wall_junctions/__init__.py
  - CREATE: src/timber_framing_generator/wall_junctions/junction_types.py
  - Content: All dataclasses and enums from Data Models section above
  - MIRROR pattern from: src/timber_framing_generator/core/json_schemas.py (dataclass style)

Task 2: Create junction_detector.py (graph construction + classification)
  - CREATE: src/timber_framing_generator/wall_junctions/junction_detector.py
  - REUSE logic from: src/timber_framing_generator/panels/corner_handler.py
    - _points_close() → reuse for endpoint matching
    - _calculate_angle_between_walls() → reuse for angle computation
    - detect_wall_corners() → extend for T-intersection detection
  - NEW: point_to_segment_distance() for T-intersection detection
  - NEW: classify_junction() based on connection count + angles
  - NEW: build_junction_graph() orchestrator function

Task 3: Create junction_resolver.py (join resolution + layer adjustments)
  - CREATE: src/timber_framing_generator/wall_junctions/junction_resolver.py
  - REUSE logic from: corner_handler.calculate_corner_adjustments() (priority strategies)
  - NEW: resolve_junction() for single junction
  - NEW: calculate_layer_adjustments() for per-layer math
  - NEW: apply_user_overrides() for junction_overrides input
  - REFERENCE: config/assembly.py for default layer thicknesses

Task 4: Update json_schemas.py with junction serialization
  - MODIFY: src/timber_framing_generator/core/json_schemas.py
  - ADD: Serialization/deserialization functions for JunctionGraph
  - ADD: junctions_json format specification
  - PRESERVE: All existing dataclasses and functions

Task 5: Update wall_junctions __init__.py exports
  - MODIFY: src/timber_framing_generator/wall_junctions/__init__.py
  - EXPORT: analyze_junctions (main entry point), JunctionGraph, JunctionType, etc.

Task 6: Create GHPython component
  - CREATE: scripts/gh_junction_analyzer.py
  - MIRROR pattern from: scripts/gh_sheathing_generator.py
  - Inputs: walls_json (str), junction_overrides (str, optional), run (bool)
  - Outputs: junctions_json (str), graph_pts (list), graph_lines (list), summary (str), log (str)
  - Follow grasshopper-python-assistant skill template

Task 7: Write unit tests
  - CREATE: tests/wall_junctions/__init__.py
  - CREATE: tests/wall_junctions/conftest.py (mock wall fixtures)
  - CREATE: tests/wall_junctions/test_junction_detector.py
  - CREATE: tests/wall_junctions/test_junction_resolver.py
  - MIRROR pattern from: tests/panels/test_panel_decomposer.py (mock wall creation)
```

### Pseudocode (with CRITICAL details)

```python
# =============================================================================
# Task 2: junction_detector.py
# =============================================================================

import math
from typing import List, Dict, Tuple, Optional
from .junction_types import (
    JunctionNode, WallConnection, JunctionType, WallLayerInfo
)


# Reuse from corner_handler.py
def _points_close(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    tolerance: float
) -> bool:
    """Euclidean distance check between two 3D points."""
    dx, dy, dz = p1[0] - p2[0], p1[1] - p2[1], p1[2] - p2[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz) <= tolerance


def _point_to_segment_distance(
    point: Tuple[float, float, float],
    seg_start: Tuple[float, float, float],
    seg_end: Tuple[float, float, float],
) -> Tuple[float, float]:
    """Distance from point to line segment, and parameter t along segment.

    Returns:
        (distance, t) where t is 0.0 at seg_start, 1.0 at seg_end.
        t is clamped to [0, 1].
    """
    # PATTERN: Project point onto segment, clamp t to [0, 1]
    dx = seg_end[0] - seg_start[0]
    dy = seg_end[1] - seg_start[1]
    dz = seg_end[2] - seg_start[2]
    seg_len_sq = dx * dx + dy * dy + dz * dz

    if seg_len_sq < 1e-12:
        # Degenerate segment
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, seg_start)))
        return dist, 0.0

    # Parameter t along segment
    t = (
        (point[0] - seg_start[0]) * dx +
        (point[1] - seg_start[1]) * dy +
        (point[2] - seg_start[2]) * dz
    ) / seg_len_sq

    t = max(0.0, min(1.0, t))

    # Closest point on segment
    closest = (
        seg_start[0] + t * dx,
        seg_start[1] + t * dy,
        seg_start[2] + t * dz,
    )

    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, closest)))
    return dist, t


def _calculate_angle(
    dir1: Tuple[float, float, float],
    dir2: Tuple[float, float, float],
) -> float:
    """Angle between two direction vectors in degrees (0-180)."""
    dot = dir1[0] * dir2[0] + dir1[1] * dir2[1] + dir1[2] * dir2[2]
    mag1 = math.sqrt(sum(d * d for d in dir1))
    mag2 = math.sqrt(sum(d * d for d in dir2))

    if mag1 < 1e-12 or mag2 < 1e-12:
        return 0.0

    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def build_junction_graph(
    walls_data: List[Dict],
    tolerance: float = 0.1,
    t_intersection_tolerance: float = 0.1,
    inline_angle_threshold: float = 170.0,
) -> Dict[str, JunctionNode]:
    """Build junction graph from wall data.

    Algorithm:
    1. Extract endpoints from all walls
    2. Match endpoints within tolerance (L-corners, continuations)
    3. Match endpoints to mid-span segments (T-intersections)
    4. Group into junction nodes
    5. Classify each node

    Args:
        walls_data: List of wall dicts from walls_json
        tolerance: Max distance for endpoint matching (feet)
        t_intersection_tolerance: Max distance for point-to-segment (feet)
        inline_angle_threshold: Angles above this are "inline" (degrees)

    Returns:
        Dict mapping junction_id to JunctionNode
    """
    # Step 1: Extract all wall endpoints
    endpoints = []  # List of (wall_id, "start"/"end", position, direction, metadata)
    for wall in walls_data:
        wall_id = wall["wall_id"]
        start = _extract_point(wall, "start")
        end = _extract_point(wall, "end")
        direction = _extract_direction(wall)
        thickness = wall["wall_thickness"]
        length = wall["wall_length"]

        endpoints.append({
            "wall_id": wall_id, "end": "start", "position": start,
            "direction": direction, "thickness": thickness, "length": length
        })
        endpoints.append({
            "wall_id": wall_id, "end": "end", "position": end,
            "direction": direction, "thickness": thickness, "length": length
        })

    # Step 2: Match endpoints to each other (L-corners, X-crossings)
    # PATTERN: Union-Find for grouping close endpoints
    groups = _group_close_endpoints(endpoints, tolerance)

    # Step 3: Match unmatched endpoints to wall mid-spans (T-intersections)
    unmatched = [ep for ep in endpoints if ep not in any group > 1]
    for ep in unmatched:
        for wall in walls_data:
            if wall["wall_id"] == ep["wall_id"]:
                continue  # Skip self
            seg_start = _extract_point(wall, "start")
            seg_end = _extract_point(wall, "end")
            dist, t = _point_to_segment_distance(ep["position"], seg_start, seg_end)

            # GOTCHA: Exclude matches near segment endpoints (those are L-corners)
            if dist <= t_intersection_tolerance and 0.05 < t < 0.95:
                # This is a T-intersection!
                midspan_u = t * wall["wall_length"]
                # Add to group with a mid-span WallConnection
                _add_t_intersection(groups, ep, wall, midspan_u)

    # Step 4: Create JunctionNode for each group
    nodes = {}
    for group_id, group_endpoints in groups.items():
        connections = [
            WallConnection(
                wall_id=ep["wall_id"],
                end=ep["end"],
                direction=ep["direction"],
                angle_at_junction=0.0,  # Computed in classification
                wall_thickness=ep["thickness"],
                wall_length=ep["length"],
                is_midspan=ep.get("is_midspan", False),
                midspan_u=ep.get("midspan_u", None),
            )
            for ep in group_endpoints
        ]

        # Average position of group
        avg_pos = _average_positions([ep["position"] for ep in group_endpoints])

        node = JunctionNode(
            id=f"junction_{group_id}",
            position=avg_pos,
            junction_type=JunctionType.FREE_END,  # Classified next
            connections=connections,
        )
        nodes[node.id] = node

    # Step 5: Classify each node
    for node in nodes.values():
        node.junction_type = _classify_junction(
            node.connections, inline_angle_threshold
        )

    return nodes


def _classify_junction(
    connections: List[WallConnection],
    inline_threshold: float = 170.0,
) -> JunctionType:
    """Classify junction based on connection count and angles.

    Rules:
      1 connection → FREE_END
      2 connections:
        - Has T mid-span connection → T_INTERSECTION
        - Angle ≥ inline_threshold → INLINE
        - Angle < inline_threshold → L_CORNER
      3 connections:
        - Has one pair ~180° → T_INTERSECTION
        - Otherwise → MULTI_WAY
      4+ connections → X_CROSSING or MULTI_WAY
    """
    n = len(connections)

    if n <= 1:
        return JunctionType.FREE_END

    # Check for mid-span connections (definitive T-intersection marker)
    has_midspan = any(c.is_midspan for c in connections)

    if n == 2:
        if has_midspan:
            return JunctionType.T_INTERSECTION

        angle = _calculate_angle(connections[0].direction, connections[1].direction)
        # GOTCHA: If both walls point AWAY from junction, angle is ~0°
        # If they point TOWARD, angle is ~180°. Need to handle both cases.
        # Normalize: flip direction if wall "end" is at junction (pointing away)
        adjusted_angle = _adjusted_angle_at_junction(connections[0], connections[1])

        if adjusted_angle >= inline_threshold:
            return JunctionType.INLINE
        return JunctionType.L_CORNER

    if n == 3:
        if has_midspan:
            return JunctionType.T_INTERSECTION
        # Check if any pair is ~inline
        for i in range(n):
            for j in range(i + 1, n):
                angle = _adjusted_angle_at_junction(connections[i], connections[j])
                if angle >= inline_threshold:
                    return JunctionType.T_INTERSECTION
        return JunctionType.MULTI_WAY

    if n == 4:
        return JunctionType.X_CROSSING

    return JunctionType.MULTI_WAY


# =============================================================================
# Task 3: junction_resolver.py
# =============================================================================

from .junction_types import (
    JunctionNode, JunctionResolution, JoinType, JunctionType,
    LayerAdjustment, AdjustmentType, WallLayerInfo
)
from ..config.assembly import WallAssembly


def resolve_all_junctions(
    nodes: Dict[str, JunctionNode],
    wall_layers: Dict[str, WallLayerInfo],
    default_join_type: str = "butt",
    priority_strategy: str = "longer_wall",
    user_overrides: Optional[Dict] = None,
) -> List[JunctionResolution]:
    """Resolve join type and priority for every junction.

    Args:
        nodes: Junction graph nodes
        wall_layers: Layer info per wall
        default_join_type: "butt" or "miter"
        priority_strategy: "longer_wall", "exterior_first", or "alternate"
        user_overrides: Optional dict of junction_id → override settings

    Returns:
        List of JunctionResolution with layer adjustments
    """
    resolutions = []

    for node in nodes.values():
        if node.junction_type == JunctionType.FREE_END:
            continue
        if node.junction_type == JunctionType.INLINE:
            continue  # Wall continuation, no junction to resolve

        # Check for user override first
        override = (user_overrides or {}).get(node.id)

        if node.junction_type in (JunctionType.L_CORNER, JunctionType.T_INTERSECTION):
            resolution = _resolve_two_wall_junction(
                node, wall_layers, default_join_type, priority_strategy, override
            )
            resolutions.append(resolution)

        elif node.junction_type in (JunctionType.X_CROSSING, JunctionType.MULTI_WAY):
            # Process pairwise
            pair_resolutions = _resolve_multi_wall_junction(
                node, wall_layers, default_join_type, priority_strategy, override
            )
            resolutions.extend(pair_resolutions)

    return resolutions


def _resolve_two_wall_junction(
    node: JunctionNode,
    wall_layers: Dict[str, WallLayerInfo],
    default_join_type: str,
    priority_strategy: str,
    override: Optional[Dict],
) -> JunctionResolution:
    """Resolve a junction between exactly two walls (L-corner or T-intersection)."""

    conn_a = node.connections[0]
    conn_b = node.connections[1]

    # For T-intersections, the continuous wall always wins
    if node.junction_type == JunctionType.T_INTERSECTION:
        if conn_a.is_midspan:
            # conn_a is the continuous wall, conn_b terminates
            primary, secondary = conn_a, conn_b
        elif conn_b.is_midspan:
            primary, secondary = conn_b, conn_a
        else:
            # Detected by angle — the pair with ~180° angle is continuous
            primary, secondary = _determine_t_priority(node.connections)
        join_type = JoinType.BUTT
        confidence = 0.95
        reason = "T-intersection: continuous wall extends, terminating wall trims"

    else:
        # L-Corner: determine priority
        join_type = JoinType(override.get("join_type", default_join_type)) if override else JoinType(default_join_type)

        if override and "primary_wall_id" in override:
            # User specified which wall wins
            if override["primary_wall_id"] == conn_a.wall_id:
                primary, secondary = conn_a, conn_b
            else:
                primary, secondary = conn_b, conn_a
            confidence = 1.0
            reason = "User override"
        else:
            primary, secondary = _determine_priority(
                conn_a, conn_b, priority_strategy
            )
            confidence = 0.7
            reason = f"Auto-detected: {priority_strategy} strategy"

    # Calculate per-layer adjustments
    layers_a = wall_layers.get(primary.wall_id)
    layers_b = wall_layers.get(secondary.wall_id)

    if join_type == JoinType.BUTT:
        adjustments = _calculate_butt_adjustments(
            node.id, primary, secondary, layers_a, layers_b
        )
    elif join_type == JoinType.MITER:
        angle = _adjusted_angle_at_junction(primary, secondary)
        adjustments = _calculate_miter_adjustments(
            node.id, primary, secondary, layers_a, layers_b, angle
        )
    else:
        adjustments = []

    return JunctionResolution(
        junction_id=node.id,
        join_type=join_type,
        primary_wall_id=primary.wall_id,
        secondary_wall_id=secondary.wall_id,
        confidence=confidence,
        reason=reason,
        layer_adjustments=adjustments,
        is_user_override=override is not None,
    )


def _determine_priority(
    conn_a: WallConnection,
    conn_b: WallConnection,
    strategy: str,
) -> Tuple[WallConnection, WallConnection]:
    """Determine which wall is primary (extends) in a butt join.

    Strategies:
      - "longer_wall": Longer wall extends
      - "exterior_first": Exterior wall extends (requires metadata)
      - "alternate": Consistent alternation by wall_id comparison
    """
    if strategy == "longer_wall":
        if conn_a.wall_length >= conn_b.wall_length:
            return conn_a, conn_b
        return conn_b, conn_a

    elif strategy == "alternate":
        if conn_a.wall_id < conn_b.wall_id:
            return conn_a, conn_b
        return conn_b, conn_a

    # Default: a is primary
    return conn_a, conn_b


def _calculate_butt_adjustments(
    junction_id: str,
    primary: WallConnection,
    secondary: WallConnection,
    primary_layers: Optional[WallLayerInfo],
    secondary_layers: Optional[WallLayerInfo],
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments for a butt join.

    Primary wall EXTENDS, secondary wall TRIMS.

    For the PRIMARY wall (extends):
      - core layer:     extend by secondary.core_thickness / 2
      - exterior layer: extend by secondary.total_thickness / 2
        (wraps around the corner, covering the secondary wall's edge)
      - interior layer: extend by secondary.total_thickness / 2
        (wraps around the corner on interior side)

    For the SECONDARY wall (trims):
      - core layer:     trim by primary.core_thickness / 2
      - exterior layer: trim by primary.core_thickness / 2
        (butts against primary wall's sheathing, not its centerline)
      - interior layer: trim by primary.core_thickness / 2
    """
    adjustments = []

    # Fallback to defaults if layer info missing
    if primary_layers is None:
        primary_layers = _default_wall_layers(primary.wall_id, primary.wall_thickness)
    if secondary_layers is None:
        secondary_layers = _default_wall_layers(secondary.wall_id, secondary.wall_thickness)

    # PRIMARY WALL: extends
    for layer_name, extend_amount in [
        ("core", secondary_layers.core_thickness / 2),
        ("exterior", secondary_layers.total_thickness / 2),
        ("interior", secondary_layers.total_thickness / 2),
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=AdjustmentType.EXTEND,
            amount=extend_amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # SECONDARY WALL: trims
    for layer_name, trim_amount in [
        ("core", primary_layers.core_thickness / 2),
        ("exterior", primary_layers.core_thickness / 2),
        ("interior", primary_layers.core_thickness / 2),
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=AdjustmentType.TRIM,
            amount=trim_amount,
            connecting_wall_id=primary.wall_id,
        ))

    return adjustments


def _default_wall_layers(wall_id: str, total_thickness: float) -> WallLayerInfo:
    """Create default layer info from config/assembly.py defaults.

    PATTERN: Use hardcoded defaults from WallAssembly config.
    Phase 2 will replace this with Revit CompoundStructure data.
    """
    # Default from config/assembly.py
    # exterior=0.75" (0.0625'), core=3.5" (0.2917'), interior=0.5" (0.0417')
    ext_default = 0.0625   # 0.75 inches in feet
    core_default = 0.2917  # 3.5 inches in feet
    int_default = 0.0417   # 0.5 inches in feet

    # Scale proportionally if total_thickness differs from default
    default_total = ext_default + core_default + int_default  # ~0.3958 ft
    if abs(total_thickness - default_total) > 0.01:
        # Scale all layers proportionally
        scale = total_thickness / default_total if default_total > 0 else 1.0
        ext_default *= scale
        core_default *= scale
        int_default *= scale

    return WallLayerInfo(
        wall_id=wall_id,
        total_thickness=total_thickness,
        exterior_thickness=ext_default,
        core_thickness=core_default,
        interior_thickness=int_default,
        source="default",
    )
```

### junctions_json Output Format

```json
{
  "version": "1.0",
  "tolerance": 0.1,
  "junction_count": 4,
  "junctions": [
    {
      "id": "junction_0",
      "position": {"x": 10.0, "y": 5.0, "z": 0.0},
      "junction_type": "l_corner",
      "connections": [
        {
          "wall_id": "wall_A",
          "end": "end",
          "is_midspan": false
        },
        {
          "wall_id": "wall_B",
          "end": "start",
          "is_midspan": false
        }
      ],
      "resolution": {
        "join_type": "butt",
        "primary_wall_id": "wall_A",
        "secondary_wall_id": "wall_B",
        "confidence": 0.7,
        "reason": "Auto-detected: longer_wall strategy",
        "is_user_override": false
      }
    }
  ],
  "wall_adjustments": {
    "wall_A": [
      {
        "end": "end",
        "junction_id": "junction_0",
        "layer_name": "core",
        "adjustment_type": "extend",
        "amount": 0.1458,
        "connecting_wall_id": "wall_B"
      },
      {
        "end": "end",
        "junction_id": "junction_0",
        "layer_name": "exterior",
        "adjustment_type": "extend",
        "amount": 0.1979,
        "connecting_wall_id": "wall_B"
      },
      {
        "end": "end",
        "junction_id": "junction_0",
        "layer_name": "interior",
        "adjustment_type": "extend",
        "amount": 0.1979,
        "connecting_wall_id": "wall_B"
      }
    ],
    "wall_B": [
      {
        "end": "start",
        "junction_id": "junction_0",
        "layer_name": "core",
        "adjustment_type": "trim",
        "amount": 0.1458,
        "connecting_wall_id": "wall_A"
      },
      {
        "end": "start",
        "junction_id": "junction_0",
        "layer_name": "exterior",
        "adjustment_type": "trim",
        "amount": 0.1458,
        "connecting_wall_id": "wall_A"
      },
      {
        "end": "start",
        "junction_id": "junction_0",
        "layer_name": "interior",
        "adjustment_type": "trim",
        "amount": 0.1458,
        "connecting_wall_id": "wall_A"
      }
    ]
  },
  "summary": {
    "l_corners": 2,
    "t_intersections": 1,
    "x_crossings": 0,
    "free_ends": 1,
    "total_junctions": 4,
    "user_overrides_applied": 0
  }
}
```

### Integration Points

```yaml
CONFIG:
  - file: src/timber_framing_generator/config/assembly.py
    pattern: "Read WallAssembly defaults for layer thicknesses"
    effect: "Provides fallback layer breakdown when Revit data unavailable"

IMPORTS:
  - file: src/timber_framing_generator/wall_junctions/__init__.py
    pattern: |
      from .junction_detector import build_junction_graph
      from .junction_resolver import resolve_all_junctions, build_junction_result
      from .junction_types import (
          JunctionGraph, JunctionNode, JunctionType, JoinType,
          LayerAdjustment, AdjustmentType, WallLayerInfo
      )

DOWNSTREAM (future integration, NOT in this PRP):
  - file: scripts/gh_sheathing_generator.py
    pattern: "Read junctions_json, apply exterior/interior layer adjustments to u_start/u_end"
  - file: scripts/gh_cell_decomposer.py
    pattern: "Read junctions_json, apply core layer adjustments to wall length"
  - file: scripts/gh_framing_generator.py
    pattern: "Read junctions_json, add corner posts / ladder blocking at junction ends"
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Type check new module
python -m py_compile src/timber_framing_generator/wall_junctions/junction_types.py
python -m py_compile src/timber_framing_generator/wall_junctions/junction_detector.py
python -m py_compile src/timber_framing_generator/wall_junctions/junction_resolver.py

# Linting
ruff check src/timber_framing_generator/wall_junctions/

# Type checking
mypy src/timber_framing_generator/wall_junctions/
```

### Level 2: Unit Tests

```bash
# Run junction tests
pytest tests/wall_junctions/ -v

# Key test cases:
# 1. L-corner: Two walls meeting at 90° — correct classification + adjustments
# 2. T-intersection: One wall ending mid-span of another
# 3. Free end: Isolated wall endpoint
# 4. X-crossing: Two walls crossing through each other
# 5. Inline: Two collinear walls (should NOT create junction)
# 6. User override: Override join type and priority
# 7. Different wall thicknesses: Verify asymmetric adjustments
# 8. Non-orthogonal angle: 45° corner
# 9. Multiple walls at one point: 3+ walls meeting
```

```python
# Test fixture examples:
def create_l_corner_walls():
    """Two walls meeting at 90° L-corner."""
    return [
        {
            "wall_id": "wall_A",
            "wall_length": 20.0,
            "wall_height": 8.0,
            "wall_thickness": 0.3958,  # ~4.75 inches
            "base_elevation": 0.0,
            "base_curve_start": {"x": 0.0, "y": 0.0, "z": 0.0},
            "base_curve_end": {"x": 20.0, "y": 0.0, "z": 0.0},
            "base_plane": {
                "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
                "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
                "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
            },
            "openings": [],
            "is_exterior": True,
        },
        {
            "wall_id": "wall_B",
            "wall_length": 15.0,
            "wall_height": 8.0,
            "wall_thickness": 0.3958,
            "base_elevation": 0.0,
            "base_curve_start": {"x": 20.0, "y": 0.0, "z": 0.0},
            "base_curve_end": {"x": 20.0, "y": 15.0, "z": 0.0},
            "base_plane": {
                "origin": {"x": 20.0, "y": 0.0, "z": 0.0},
                "x_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
                "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "z_axis": {"x": -1.0, "y": 0.0, "z": 0.0},
            },
            "openings": [],
            "is_exterior": True,
        },
    ]


def create_t_intersection_walls():
    """Wall B terminates mid-span of wall A."""
    return [
        {
            "wall_id": "wall_A",  # Continuous wall
            "wall_length": 30.0,
            "wall_height": 8.0,
            "wall_thickness": 0.3958,
            "base_elevation": 0.0,
            "base_curve_start": {"x": 0.0, "y": 0.0, "z": 0.0},
            "base_curve_end": {"x": 30.0, "y": 0.0, "z": 0.0},
            "base_plane": {
                "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
                "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
                "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
            },
            "openings": [],
            "is_exterior": True,
        },
        {
            "wall_id": "wall_B",  # Terminating wall
            "wall_length": 10.0,
            "wall_height": 8.0,
            "wall_thickness": 0.3958,
            "base_elevation": 0.0,
            "base_curve_start": {"x": 15.0, "y": 0.0, "z": 0.0},  # Meets wall_A mid-span
            "base_curve_end": {"x": 15.0, "y": 10.0, "z": 0.0},
            "base_plane": {
                "origin": {"x": 15.0, "y": 0.0, "z": 0.0},
                "x_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
                "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "z_axis": {"x": -1.0, "y": 0.0, "z": 0.0},
            },
            "openings": [],
            "is_exterior": False,
        },
    ]
```

### Level 3: Integration Test (Grasshopper)

```
Manual test in Grasshopper:
1. Open Rhino with Grasshopper
2. Connect Wall Analyzer → Junction Analyzer
3. Verify junctions_json is valid JSON
4. Verify graph_pts show junction points in viewport
5. Verify graph_lines show wall edges in viewport
6. Check summary output counts match expected junctions
7. Inspect junctions_json: verify L-corners have correct extend/trim amounts
8. Test with junction_overrides: override one corner to "miter"
9. Verify no runtime errors or warnings
```

---

## Final Checklist

- [ ] `junction_types.py` — All data models created with type hints and docstrings
- [ ] `junction_detector.py` — Graph construction handles L, T, X, free-end junctions
- [ ] `junction_resolver.py` — Butt and miter resolution with per-layer adjustments
- [ ] `json_schemas.py` — Junction serialization added (preserving existing schemas)
- [ ] `gh_junction_analyzer.py` — GHPython component follows template
- [ ] Unit tests pass: `pytest tests/wall_junctions/ -v`
- [ ] L-corner adjustments: primary extends, secondary trims, amounts correct
- [ ] T-intersection: continuous wall unmodified, terminating wall trims at core
- [ ] Free ends: no adjustments applied
- [ ] Different wall thicknesses: asymmetric adjustment amounts
- [ ] User overrides: can change join type and priority per junction
- [ ] No breaking changes to existing components
- [ ] `junctions_json` format documented and matches specification
- [ ] Grasshopper visualization outputs work (graph_pts, graph_lines)

---

## Anti-Patterns to Avoid

- ❌ Don't duplicate `corner_handler.py` logic — refactor shared functions into `wall_junctions/` and import, or call corner_handler functions directly
- ❌ Don't assume all walls are orthogonal — angles can be arbitrary (30°, 45°, 60°)
- ❌ Don't modify wall geometry in the junction analyzer — output adjustments only, let downstream components apply them
- ❌ Don't hardcode layer thicknesses in resolver — always read from `WallLayerInfo` which can come from defaults OR future Revit extraction
- ❌ Don't process walls independently — the entire point is cross-wall awareness
- ❌ Don't ignore the `end` field — a wall can have different adjustments at its start vs end
- ❌ Don't create geometry in this component — it outputs JSON only (geometry is downstream)
- ❌ Don't silently resolve uncertain junctions — use `confidence` field and let user override
- ❌ Don't use `rg.Point3d()` or any RhinoCommon in the core module — keep it pure Python for testability; only the GH component script uses Rhino

---

## Notes

### Scope Boundaries

**In scope (this PRP)**:
- Junction detection, classification, resolution
- Per-layer adjustment calculation
- junctions_json output format
- GH component for junction analysis
- Unit tests

**Out of scope (future PRPs)**:
- Revit CompoundStructure extraction (requires wall analyzer changes)
- Downstream integration: modifying sheathing/framing/cell-decomposer to consume junctions_json
- Corner stud framing details (3-stud corner, California corner, ladder blocking)
- Visual override UI in Grasshopper (junction editor)

### Relationship to Existing `corner_handler.py`

The junction analyzer **supersedes** `corner_handler.py` for junction detection but doesn't replace it immediately. Strategy:

1. **Phase 1 (this PRP)**: Build new `wall_junctions/` module. Can import shared utility functions from `corner_handler.py`.
2. **Phase 2 (future)**: Migrate `panel_decomposer.py` to use `junctions_json` instead of calling `corner_handler` directly.
3. **Phase 3 (future)**: Deprecate `corner_handler.py` once all consumers migrated.

### Layer Data Roadmap

| Phase | Layer Source | Accuracy |
|-------|-------------|----------|
| Phase 1 (this PRP) | `config/assembly.py` defaults, scaled by wall_thickness | Approximate |
| Phase 2 (future) | Revit `WallType.GetCompoundStructure()` via wall analyzer | Exact |
| Phase 3 (future) | User override per wall type via config_json | Exact + custom |

### Extension: Miter Join Geometry

Miter adjustment amounts are angle-dependent:

```
For a layer at offset d from centerline, at junction angle θ:
  miter_extension = d / tan(θ / 2)

Example: 90° corner, sheathing at d = total_thickness/2 = 0.198 ft
  extension = 0.198 / tan(45°) = 0.198 ft
```

This formula works for any angle, not just 90°.
