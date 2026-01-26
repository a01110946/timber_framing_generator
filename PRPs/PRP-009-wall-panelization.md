# PRP-009: Wall Panelization System

> **Version:** 1.0
> **Created:** 2026-01-25
> **Status:** Draft
> **Branch:** feature/wall-panelization

---

## Goal

Implement a wall panelization system that decomposes framed walls into manufacturable, transportable panels with optimized joint placement, while handling Revit wall corner adjustments for accurate geometry.

---

## Why

### Business Value
- **Offsite Manufacturing**: Panels are the unit of prefab production; without panelization, walls can't be manufactured offsite
- **Transport Optimization**: Panels must fit on trucks (typically 8'×40' max without permits)
- **Field Assembly**: Proper joint placement enables efficient crane lifts and connections
- **Quality Control**: Panel-based production improves quality vs. stick-built

### Technical Requirements
- **Joint Placement Rules**: Industry standards require joints to be offset from openings, corners, and shear walls
- **Corner Geometry**: Revit walls join at centerlines, causing overlaps that must be resolved for accurate panel dimensions
- **Structural Continuity**: Sheathing must maintain structural integrity across panels

### Problems Solved
1. Currently no way to split walls into manufacturable panels
2. Revit corner joins create geometry conflicts for offsite construction
3. No automated joint optimization based on structural/manufacturing rules

---

## What

### User-Visible Behavior

**Input**: Framed walls (from existing pipeline) + panel configuration
**Output**:
- Walls split into panels with joint locations
- Corner-adjusted wall geometry (extended/receded based on joining walls)
- Panel metadata (dimensions, weight estimates, assembly sequence)

### Configuration Parameters

```python
@dataclass
class PanelConfig:
    # Size Constraints
    max_panel_length: float = 24.0       # feet (typical manufacturing limit)
    min_panel_length: float = 4.0        # feet (minimum practical size)
    max_panel_height: float = 12.0       # feet (single-story typical)

    # Joint Exclusion Zones
    min_joint_to_opening: float = 1.0    # feet from window/door edges
    min_joint_to_corner: float = 2.0     # feet from wall corners
    min_joint_to_shear_panel: float = 0.0  # feet (joints allowed at shear panel edges)

    # Corner Handling
    corner_priority: str = "longer_wall"  # "longer_wall" | "specified" | "alternate"

    # Transport Constraints
    max_transport_length: float = 40.0   # feet (standard flatbed)
    max_transport_weight: float = 10000  # lbs (crane/forklift limit)
```

### Success Criteria

- [ ] Walls decompose into panels respecting max_panel_length
- [ ] No panel joints within exclusion zones (openings, corners, shear walls)
- [ ] Corner geometry correctly adjusted (one wall extends, other recedes)
- [ ] Panel joints align with stud locations (structural requirement)
- [ ] Panel metadata includes dimensions, weight, and assembly order
- [ ] Integration with existing framing pipeline (JSON-based)

---

## Research Findings

### Panel Length Constraints

| Constraint Source | Typical Limit | Notes |
|------------------|---------------|-------|
| Manufacturing table | 24-32 ft | Most panel lines limited to ~24ft |
| Standard truck | 40 ft | Without oversize permits |
| Oversize load | 53 ft | Requires permits, escort vehicles |
| Crane capacity | Site-specific | Weight more limiting than length |

**Sources**: [Wells Prefabrication Guide](https://www.wellsconcrete.com/about/news-insights/what-is-prefabrication/), [JDM Wall Panels](https://jdmwallpanels.com/)

### Joint Placement Rules

| Rule | Requirement | Source |
|------|-------------|--------|
| Distance from openings | 12" minimum (GA-216 for gypsum) | [National Gypsum Guidelines](https://www.nationalgypsum.com/ngconnects/blog/building-knowledge/guidelines-best-practices-installing-drywall-control-joints) |
| Panel joint support | 1/2" minimum bearing on framing | [APA Wall Construction Guide](https://www.buildgp.com/wp-content/uploads/2022/06/2020-APA-Engineered-Wood-Construction-guide-Walls-E30.pdf) |
| Braced wall panel length | 48" minimum (3 studs at 16" OC) | [IRC Wall Bracing Guide](https://www.appliedbuildingtech.com/sites/default/files/abtg_irc_2024_wall_bracing_guide_final_secured.pdf) |
| Shear wall joints | Must occur over common framing | [Eng-Tips Discussion](https://www.eng-tips.com/threads/wood-shear-wall-prefab-panels-common-framing-members.501988/) |

### Corner Handling Strategies

**Problem**: Revit walls join at centerlines, causing:
1. Overlap in the corner region
2. Gap at exterior corner
3. Incorrect panel lengths if measured from centerlines

**Solution**:
- **Wall A (Primary)**: Extends to outer face of Wall B
- **Wall B (Secondary)**: Recedes by Wall A's thickness

```
BEFORE (Revit centerline join):
        ┌─────────┐
        │  Wall B │ (centerline)
        │         │
────────┼─────────┘
Wall A  │
(centerline meets at corner)

AFTER (Corner adjustment):
        ┌─────────┐
        │  Wall B │ (receded)
        │         │
────────┴─────────┘
Wall A (extended)│
                 └── Wall A extends by Wall B thickness
```

**Reference**: [BIMPure Wall Joins Guide](https://www.bimpure.com/blog/8-tips-to-understand-revit-wall-joins), [Revit API Location Line](https://adndevblog.typepad.com/aec/2012/07/location-line-of-a-new-wall-using-revit-api.html)

---

## All Needed Context

### Documentation & References

```yaml
Project Docs:
  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for wall-relative calculations

  - file: docs/ai/ai-modular-architecture-plan.md
    why: Understand modular component patterns

  - file: docs/ai/ai-rir-revit-patterns.md
    why: Revit API patterns for wall manipulation

Core Implementations:
  - file: src/timber_framing_generator/core/json_schemas.py
    why: Understand existing data schemas (WallData, FramingResults)

  - file: src/timber_framing_generator/cell_decomposition/cell_segmentation.py
    why: Pattern for decomposing walls into regions

  - file: src/timber_framing_generator/wall_data/wall_data_extractor.py
    why: How wall data is extracted from Revit
```

### Current Codebase Structure

```
src/timber_framing_generator/
├── core/
│   ├── json_schemas.py          # WallData, CellData, FramingResults
│   ├── building_component.py    # BuildingComponent ABC
│   └── component_types.py       # ComponentType enum
├── wall_data/
│   └── wall_data_extractor.py   # Revit wall data extraction
├── cell_decomposition/
│   ├── cell_segmentation.py     # Wall → cells decomposition
│   └── cell_types.py            # Cell type definitions
├── framing_elements/
│   └── framing_generator.py     # Framing element generation
└── config/
    └── framing.py               # Framing configuration

scripts/
├── gh_wall_analyzer.py          # GH Component 1
├── gh_cell_decomposer.py        # GH Component 2
├── gh_framing_generator.py      # GH Component 3
└── gh_geometry_converter.py     # GH Component 4
```

### Desired Structure (files to add/modify)

```
src/timber_framing_generator/
├── core/
│   └── json_schemas.py          # MODIFY: Add PanelData, PanelResults
├── panels/                       # NEW directory
│   ├── __init__.py
│   ├── panel_config.py          # Panel configuration dataclass
│   ├── panel_decomposer.py      # Wall → panels decomposition
│   ├── joint_optimizer.py       # Optimal joint placement algorithm
│   └── corner_handler.py        # Wall corner adjustment logic
├── wall_data/
│   └── wall_data_extractor.py   # MODIFY: Add corner detection
└── config/
    └── panel_standards.py       # NEW: Industry standard panel sizes

scripts/
├── gh_wall_corner_adjuster.py   # NEW: GH Component for corner handling
└── gh_panel_decomposer.py       # NEW: GH Component for panelization

tests/
└── panels/
    ├── test_panel_decomposer.py
    ├── test_joint_optimizer.py
    └── test_corner_handler.py
```

### Known Gotchas & Library Quirks

```yaml
CRITICAL - Revit Wall Joins:
  issue: Walls join at centerlines in Revit, not faces
  impact: Panel lengths incorrect if measured from centerline joins
  solution: Detect corners, unjoin via API, extend/recede based on thickness
  pattern: |
    # Use WALL_KEY_REF_PARAM to get wall reference line
    # Wall thickness from wall.Width property
    # Extend/recede using wall location curve manipulation

CRITICAL - Stud Alignment:
  issue: Panel joints must occur at stud locations
  impact: Joints between studs have no framing support
  solution: Snap joint locations to nearest stud U-coordinate
  pattern: |
    stud_spacing = 1.333  # 16" OC in feet
    snapped_joint = round(proposed_joint / stud_spacing) * stud_spacing

CRITICAL - Sheathing Continuity:
  issue: Structural sheathing panels have specific joint rules
  impact: Incorrect joints compromise shear capacity
  solution: |
    - Panel joints at double studs (SDPWS requirement)
    - Offset joints on opposite faces
    - Minimum 1/2" bearing on framing
```

---

## Implementation Blueprint

### Phase 1: Data Models

```python
# File: src/timber_framing_generator/panels/panel_config.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class CornerPriority(Enum):
    LONGER_WALL = "longer_wall"      # Longer wall extends
    SPECIFIED = "specified"          # User specifies which extends
    ALTERNATE = "alternate"          # Alternate pattern for consistency

@dataclass
class ExclusionZone:
    """Region where panel joints are not allowed."""
    u_start: float
    u_end: float
    zone_type: str  # "opening", "corner", "shear_panel"
    element_id: Optional[str] = None

@dataclass
class PanelConfig:
    """Configuration for wall panelization."""
    # Size constraints
    max_panel_length: float = 24.0
    min_panel_length: float = 4.0
    max_panel_height: float = 12.0

    # Joint rules
    min_joint_to_opening: float = 1.0
    min_joint_to_corner: float = 2.0
    min_joint_to_shear: float = 0.0

    # Corner handling
    corner_priority: CornerPriority = CornerPriority.LONGER_WALL

    # Transport
    max_transport_length: float = 40.0
    max_transport_weight: float = 10000.0

    # Stud alignment
    stud_spacing: float = 1.333  # 16" OC in feet
    snap_to_studs: bool = True

# File: src/timber_framing_generator/core/json_schemas.py (additions)

@dataclass
class PanelJoint:
    """A joint between two panels."""
    u_coord: float              # Position along wall in U
    joint_type: str             # "field", "corner", "opening_adjacent"
    left_panel_id: str
    right_panel_id: str
    stud_u_coords: List[float]  # U positions of studs at joint (double stud)

@dataclass
class PanelData:
    """A single wall panel."""
    id: str
    wall_id: str
    panel_index: int            # Order along wall (0, 1, 2...)
    u_start: float
    u_end: float
    length: float               # u_end - u_start
    height: float

    # Geometry (world coordinates)
    corners: Dict[str, Dict[str, float]]  # "bl", "br", "tl", "tr"

    # Contents
    cell_ids: List[str]         # Cells contained in this panel
    element_ids: List[str]      # Framing elements in this panel

    # Metadata
    estimated_weight: float
    assembly_sequence: int
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class WallCornerAdjustment:
    """Adjustment to apply to a wall at a corner."""
    wall_id: str
    corner_type: str            # "start" or "end"
    adjustment_type: str        # "extend" or "recede"
    adjustment_amount: float    # In feet
    connecting_wall_id: str
    connecting_wall_thickness: float

@dataclass
class PanelResults:
    """Complete panelization results for a wall."""
    wall_id: str
    panels: List[PanelData]
    joints: List[PanelJoint]
    corner_adjustments: List[WallCornerAdjustment]
    total_panel_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Phase 2: Corner Handler

```python
# File: src/timber_framing_generator/panels/corner_handler.py

"""
Wall corner adjustment for accurate panel geometry.

Revit walls join at centerlines, but for panelization we need
face-to-face dimensions. This module detects corners and calculates
the extend/recede adjustments needed.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math

@dataclass
class WallCornerInfo:
    """Information about a wall corner connection."""
    wall_id: str
    corner_position: str          # "start" or "end"
    corner_point: Tuple[float, float, float]  # World XYZ
    connecting_wall_id: str
    connecting_wall_thickness: float
    angle: float                  # Angle between walls (degrees)
    is_primary: bool              # True if this wall extends

def detect_wall_corners(
    walls_data: List[Dict],
    tolerance: float = 0.1
) -> List[WallCornerInfo]:
    """
    Detect corners where walls meet.

    Args:
        walls_data: List of WallData dictionaries
        tolerance: Distance tolerance for corner detection (feet)

    Returns:
        List of WallCornerInfo for each detected corner
    """
    corners = []

    for i, wall_a in enumerate(walls_data):
        a_start = _get_wall_endpoint(wall_a, "start")
        a_end = _get_wall_endpoint(wall_a, "end")

        for j, wall_b in enumerate(walls_data):
            if i >= j:  # Avoid duplicates
                continue

            b_start = _get_wall_endpoint(wall_b, "start")
            b_end = _get_wall_endpoint(wall_b, "end")

            # Check all endpoint combinations
            for a_pos, a_pt in [("start", a_start), ("end", a_end)]:
                for b_pos, b_pt in [("start", b_start), ("end", b_end)]:
                    if _points_close(a_pt, b_pt, tolerance):
                        # Found a corner
                        corner_info = _create_corner_info(
                            wall_a, a_pos,
                            wall_b, b_pos,
                            a_pt
                        )
                        corners.extend(corner_info)

    return corners

def calculate_corner_adjustments(
    corners: List[WallCornerInfo],
    priority: str = "longer_wall"
) -> List[WallCornerAdjustment]:
    """
    Calculate extend/recede adjustments for each wall at corners.

    Args:
        corners: Detected corner information
        priority: How to determine which wall extends
                  "longer_wall" - longer wall extends
                  "specified" - based on corner_info.is_primary

    Returns:
        List of adjustments to apply to walls
    """
    adjustments = []

    # Group corners by location
    corner_groups = _group_corners_by_location(corners)

    for corner_point, corner_walls in corner_groups.items():
        if len(corner_walls) != 2:
            continue  # Skip complex intersections for now

        wall_a, wall_b = corner_walls

        # Determine which wall extends based on priority
        if priority == "longer_wall":
            primary = wall_a if wall_a["length"] >= wall_b["length"] else wall_b
            secondary = wall_b if primary == wall_a else wall_a
        else:
            primary = wall_a if wall_a["is_primary"] else wall_b
            secondary = wall_b if primary == wall_a else wall_a

        # Primary wall extends by secondary wall's half-thickness
        # (to reach the outer face of secondary)
        adjustments.append(WallCornerAdjustment(
            wall_id=primary["wall_id"],
            corner_type=primary["corner_position"],
            adjustment_type="extend",
            adjustment_amount=secondary["thickness"] / 2,
            connecting_wall_id=secondary["wall_id"],
            connecting_wall_thickness=secondary["thickness"]
        ))

        # Secondary wall recedes by primary wall's half-thickness
        adjustments.append(WallCornerAdjustment(
            wall_id=secondary["wall_id"],
            corner_type=secondary["corner_position"],
            adjustment_type="recede",
            adjustment_amount=primary["thickness"] / 2,
            connecting_wall_id=primary["wall_id"],
            connecting_wall_thickness=primary["thickness"]
        ))

    return adjustments

def apply_corner_adjustments(
    wall_data: Dict,
    adjustments: List[WallCornerAdjustment]
) -> Dict:
    """
    Apply corner adjustments to wall data.

    Creates a new wall_data dict with adjusted length and endpoints.

    Args:
        wall_data: Original WallData dictionary
        adjustments: Adjustments for this wall

    Returns:
        Modified wall_data with adjusted geometry
    """
    adjusted = wall_data.copy()

    for adj in adjustments:
        if adj.wall_id != wall_data["id"]:
            continue

        if adj.corner_type == "start":
            if adj.adjustment_type == "extend":
                # Move start point backward along wall direction
                adjusted["length"] += adj.adjustment_amount
                # Update base_plane origin
                adjusted = _shift_wall_start(adjusted, -adj.adjustment_amount)
            else:  # recede
                adjusted["length"] -= adj.adjustment_amount
                adjusted = _shift_wall_start(adjusted, adj.adjustment_amount)

        else:  # "end"
            if adj.adjustment_type == "extend":
                adjusted["length"] += adj.adjustment_amount
            else:  # recede
                adjusted["length"] -= adj.adjustment_amount

    return adjusted
```

### Phase 3: Joint Optimizer

```python
# File: src/timber_framing_generator/panels/joint_optimizer.py

"""
Optimal panel joint placement algorithm.

Places panel joints to:
1. Respect maximum panel length
2. Avoid exclusion zones (openings, corners, shear panels)
3. Align with stud locations
4. Minimize total number of panels
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import math

def find_exclusion_zones(
    wall_data: Dict,
    config: PanelConfig
) -> List[ExclusionZone]:
    """
    Identify regions where panel joints cannot be placed.

    Args:
        wall_data: WallData dictionary with openings
        config: Panel configuration with offset rules

    Returns:
        List of exclusion zones sorted by u_start
    """
    zones = []

    # Exclusion zones around openings
    for opening in wall_data.get("openings", []):
        zones.append(ExclusionZone(
            u_start=opening["u_start"] - config.min_joint_to_opening,
            u_end=opening["u_end"] + config.min_joint_to_opening,
            zone_type="opening",
            element_id=opening.get("id")
        ))

    # Exclusion zones at wall corners (start and end)
    zones.append(ExclusionZone(
        u_start=0,
        u_end=config.min_joint_to_corner,
        zone_type="corner_start"
    ))
    zones.append(ExclusionZone(
        u_start=wall_data["length"] - config.min_joint_to_corner,
        u_end=wall_data["length"],
        zone_type="corner_end"
    ))

    # TODO: Add shear panel exclusion zones from structural data

    # Merge overlapping zones
    return _merge_overlapping_zones(sorted(zones, key=lambda z: z.u_start))

def find_optimal_joints(
    wall_length: float,
    exclusion_zones: List[ExclusionZone],
    config: PanelConfig
) -> List[float]:
    """
    Find optimal joint locations using dynamic programming.

    Algorithm:
    1. Generate candidate joint positions (at stud locations)
    2. Filter out candidates in exclusion zones
    3. Use DP to find minimum panels while respecting max length

    Args:
        wall_length: Total wall length in feet
        exclusion_zones: Regions where joints not allowed
        config: Panel configuration

    Returns:
        List of joint U-coordinates (not including 0 and wall_length)
    """
    # Generate candidate positions at stud locations
    candidates = _generate_stud_aligned_candidates(
        wall_length,
        config.stud_spacing
    )

    # Filter out candidates in exclusion zones
    valid_candidates = [
        c for c in candidates
        if not _in_exclusion_zone(c, exclusion_zones)
    ]

    # Add wall boundaries
    valid_candidates = [0.0] + valid_candidates + [wall_length]
    valid_candidates = sorted(set(valid_candidates))

    # DP to find minimum joints
    n = len(valid_candidates)

    # dp[i] = minimum number of panels to reach position i
    # parent[i] = previous position for backtracking
    dp = [float('inf')] * n
    parent = [-1] * n
    dp[0] = 0

    for i in range(1, n):
        for j in range(i):
            panel_length = valid_candidates[i] - valid_candidates[j]

            # Check constraints
            if panel_length > config.max_panel_length:
                continue
            if panel_length < config.min_panel_length and i < n - 1:
                continue  # Allow short final panel

            if dp[j] + 1 < dp[i]:
                dp[i] = dp[j] + 1
                parent[i] = j

    # Backtrack to find joint positions
    joints = []
    current = n - 1
    while parent[current] != -1:
        if parent[current] != 0:  # Don't include start position
            joints.append(valid_candidates[parent[current]])
        current = parent[current]

    return sorted(joints)

def _generate_stud_aligned_candidates(
    wall_length: float,
    stud_spacing: float
) -> List[float]:
    """Generate candidate positions aligned with studs."""
    candidates = []
    pos = stud_spacing
    while pos < wall_length:
        candidates.append(pos)
        pos += stud_spacing
    return candidates

def _in_exclusion_zone(u: float, zones: List[ExclusionZone]) -> bool:
    """Check if a U coordinate is in any exclusion zone."""
    for zone in zones:
        if zone.u_start <= u <= zone.u_end:
            return True
    return False

def _merge_overlapping_zones(zones: List[ExclusionZone]) -> List[ExclusionZone]:
    """Merge overlapping exclusion zones."""
    if not zones:
        return []

    merged = [zones[0]]
    for zone in zones[1:]:
        if zone.u_start <= merged[-1].u_end:
            # Overlapping - extend previous zone
            merged[-1] = ExclusionZone(
                u_start=merged[-1].u_start,
                u_end=max(merged[-1].u_end, zone.u_end),
                zone_type="merged"
            )
        else:
            merged.append(zone)

    return merged
```

### Phase 4: Panel Decomposer

```python
# File: src/timber_framing_generator/panels/panel_decomposer.py

"""
Main panel decomposition module.

Orchestrates the panelization process:
1. Apply corner adjustments
2. Find optimal joint locations
3. Create panel objects with geometry and contents
"""

from typing import List, Dict, Any
import json

from .panel_config import PanelConfig
from .corner_handler import (
    detect_wall_corners,
    calculate_corner_adjustments,
    apply_corner_adjustments
)
from .joint_optimizer import find_exclusion_zones, find_optimal_joints

def decompose_wall_to_panels(
    wall_data: Dict,
    framing_data: Dict,
    config: PanelConfig,
    corner_adjustments: List[Dict] = None
) -> Dict:
    """
    Decompose a single wall into panels.

    Args:
        wall_data: WallData dictionary
        framing_data: FramingResults dictionary with elements
        config: Panel configuration
        corner_adjustments: Pre-calculated corner adjustments (optional)

    Returns:
        PanelResults dictionary
    """
    # Apply corner adjustments if provided
    if corner_adjustments:
        wall_data = apply_corner_adjustments(wall_data, corner_adjustments)

    # Find exclusion zones
    exclusion_zones = find_exclusion_zones(wall_data, config)

    # Find optimal joint locations
    joint_u_coords = find_optimal_joints(
        wall_data["length"],
        exclusion_zones,
        config
    )

    # Create panel boundaries
    boundaries = [0.0] + joint_u_coords + [wall_data["length"]]

    # Create panels
    panels = []
    joints = []

    for i in range(len(boundaries) - 1):
        u_start = boundaries[i]
        u_end = boundaries[i + 1]

        panel = _create_panel(
            wall_id=wall_data["id"],
            panel_index=i,
            u_start=u_start,
            u_end=u_end,
            wall_data=wall_data,
            framing_data=framing_data
        )
        panels.append(panel)

        # Create joint (except for last panel)
        if i < len(boundaries) - 2:
            joint = _create_joint(
                u_coord=u_end,
                left_panel_id=panel["id"],
                right_panel_id=f"{wall_data['id']}_panel_{i+1}",
                framing_data=framing_data,
                config=config
            )
            joints.append(joint)

    return {
        "wall_id": wall_data["id"],
        "panels": panels,
        "joints": joints,
        "corner_adjustments": corner_adjustments or [],
        "total_panel_count": len(panels),
        "metadata": {
            "config": _config_to_dict(config),
            "original_wall_length": wall_data["length"]
        }
    }

def decompose_all_walls(
    walls_data: List[Dict],
    framing_results: List[Dict],
    config: PanelConfig
) -> List[Dict]:
    """
    Decompose multiple walls with corner handling.

    Args:
        walls_data: List of WallData dictionaries
        framing_results: List of FramingResults dictionaries
        config: Panel configuration

    Returns:
        List of PanelResults dictionaries
    """
    # Detect and calculate corner adjustments
    corners = detect_wall_corners(walls_data)
    all_adjustments = calculate_corner_adjustments(corners, config.corner_priority.value)

    # Group adjustments by wall
    adjustments_by_wall = {}
    for adj in all_adjustments:
        if adj.wall_id not in adjustments_by_wall:
            adjustments_by_wall[adj.wall_id] = []
        adjustments_by_wall[adj.wall_id].append(adj)

    # Decompose each wall
    results = []
    for wall_data, framing_data in zip(walls_data, framing_results):
        wall_adjustments = adjustments_by_wall.get(wall_data["id"], [])

        result = decompose_wall_to_panels(
            wall_data,
            framing_data,
            config,
            corner_adjustments=wall_adjustments
        )
        results.append(result)

    return results

def _create_panel(
    wall_id: str,
    panel_index: int,
    u_start: float,
    u_end: float,
    wall_data: Dict,
    framing_data: Dict
) -> Dict:
    """Create a panel dictionary."""
    panel_id = f"{wall_id}_panel_{panel_index}"
    length = u_end - u_start
    height = wall_data["height"]

    # Calculate corners in world coordinates
    base_plane = wall_data["base_plane"]
    corners = _calculate_panel_corners(base_plane, u_start, u_end, height)

    # Find elements within this panel
    element_ids = _find_elements_in_range(
        framing_data.get("elements", []),
        u_start, u_end
    )

    # Estimate weight (rough: 5 lbs/sqft for framed wall)
    area = length * height
    estimated_weight = area * 5.0

    return {
        "id": panel_id,
        "wall_id": wall_id,
        "panel_index": panel_index,
        "u_start": u_start,
        "u_end": u_end,
        "length": length,
        "height": height,
        "corners": corners,
        "element_ids": element_ids,
        "estimated_weight": estimated_weight,
        "assembly_sequence": panel_index,
        "metadata": {}
    }
```

### Phase 5: GHPython Components

**Component 1: Wall Corner Adjuster** (`scripts/gh_wall_corner_adjuster.py`)
- Input: `walls_json` (from wall analyzer)
- Output: `adjusted_walls_json`, `corner_info`, `debug_info`

**Component 2: Panel Decomposer** (`scripts/gh_panel_decomposer.py`)
- Input: `walls_json`, `framing_json`, `config` (optional)
- Output: `panels_json`, `panel_curves` (visualization), `debug_info`

---

## Tasks (Execution Order)

### Task 1: Create Panel Configuration Module
```yaml
action: CREATE
file: src/timber_framing_generator/panels/__init__.py
file: src/timber_framing_generator/panels/panel_config.py
content: PanelConfig dataclass with defaults and validation
```

### Task 2: Add Panel Data Schemas
```yaml
action: MODIFY
file: src/timber_framing_generator/core/json_schemas.py
add: PanelJoint, PanelData, WallCornerAdjustment, PanelResults dataclasses
preserve: Existing WallData, CellData, FramingResults
```

### Task 3: Implement Corner Handler
```yaml
action: CREATE
file: src/timber_framing_generator/panels/corner_handler.py
content: |
  - detect_wall_corners(): Find where walls meet
  - calculate_corner_adjustments(): Determine extend/recede
  - apply_corner_adjustments(): Modify wall geometry
```

### Task 4: Implement Joint Optimizer
```yaml
action: CREATE
file: src/timber_framing_generator/panels/joint_optimizer.py
content: |
  - find_exclusion_zones(): Identify no-joint regions
  - find_optimal_joints(): DP algorithm for minimal panels
  - Helper functions for stud alignment
```

### Task 5: Implement Panel Decomposer
```yaml
action: CREATE
file: src/timber_framing_generator/panels/panel_decomposer.py
content: |
  - decompose_wall_to_panels(): Single wall panelization
  - decompose_all_walls(): Multi-wall with corner handling
  - Helper functions for panel creation
```

### Task 6: Create GHPython Components
```yaml
action: CREATE
file: scripts/gh_wall_corner_adjuster.py
file: scripts/gh_panel_decomposer.py
content: Grasshopper components following existing patterns
```

### Task 7: Add Unit Tests
```yaml
action: CREATE
file: tests/panels/test_panel_config.py
file: tests/panels/test_corner_handler.py
file: tests/panels/test_joint_optimizer.py
file: tests/panels/test_panel_decomposer.py
```

### Task 8: Documentation
```yaml
action: CREATE
file: docs/ai/ai-panelization-system.md
content: |
  - Panelization algorithm overview
  - Corner handling logic
  - Configuration options
  - Integration with framing pipeline
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
python -m py_compile src/timber_framing_generator/panels/*.py
ruff check src/timber_framing_generator/panels/
mypy src/timber_framing_generator/panels/
```

### Level 2: Unit Tests
```bash
pytest tests/panels/ -v
```

### Level 3: Integration Tests
```bash
# Test with sample wall data
pytest tests/panels/test_panel_decomposer.py -v -m integration
```

### Level 4: Grasshopper Validation
1. Load GH definition with new components
2. Connect to wall analyzer output
3. Verify panel visualization shows correct boundaries
4. Check corner adjustments in debug output
5. Validate joint positions avoid exclusion zones

---

## References

- [National Gypsum Drywall Joint Guidelines](https://www.nationalgypsum.com/ngconnects/blog/building-knowledge/guidelines-best-practices-installing-drywall-control-joints)
- [APA Wall Construction Guide](https://www.buildgp.com/wp-content/uploads/2022/06/2020-APA-Engineered-Wood-Construction-guide-Walls-E30.pdf)
- [IRC Wall Bracing Guide 2024](https://www.appliedbuildingtech.com/sites/default/files/abtg_irc_2024_wall_bracing_guide_final_secured.pdf)
- [BIMPure Wall Joins Guide](https://www.bimpure.com/blog/8-tips-to-understand-revit-wall-joins)
- [Revit API Wall Location Line](https://adndevblog.typepad.com/aec/2012/07/location-line-of-a-new-wall-using-revit-api.html)
