# Wall Panelization System

> **Module**: `src/timber_framing_generator/panels/`
> **Status**: Implemented
> **Version**: 1.0

## Overview

The wall panelization system decomposes framed walls into manufacturable, transportable panels with optimized joint placement. It handles Revit wall corner geometry adjustments to produce accurate panel dimensions for offsite construction.

## Key Concepts

### Panel Decomposition
Walls are split into panels based on:
- **Maximum panel length** (typically 24ft for manufacturing, 40ft for transport)
- **Joint exclusion zones** around openings, corners, and shear panels
- **Stud alignment** for structural support at joints

### Corner Handling
Revit walls join at centerlines, but panels require face-to-face dimensions:
- **Primary wall** (usually longer): Extends by connecting wall's half-thickness
- **Secondary wall**: Recedes by primary wall's half-thickness

```
BEFORE (Revit centerline join):
        ┌─────────┐
        │  Wall B │
        │         │
────────┼─────────┘
Wall A  │

AFTER (Corner adjustment):
        ┌─────────┐
        │  Wall B │ (receded)
        │         │
────────┴─────────┘
Wall A (extended)
```

### Joint Optimization
Uses dynamic programming to find optimal joint locations:
1. Generate candidate positions at stud locations
2. Filter out candidates in exclusion zones
3. Find minimum panels while respecting max length constraint

## Module Structure

```
src/timber_framing_generator/panels/
├── __init__.py            # Module exports
├── panel_config.py        # PanelConfig, ExclusionZone, CornerPriority
├── corner_handler.py      # Corner detection and adjustment
├── joint_optimizer.py     # DP-based joint placement
└── panel_decomposer.py    # Main orchestration
```

## Configuration

```python
from src.timber_framing_generator.panels import PanelConfig, CornerPriority

config = PanelConfig(
    # Size constraints (feet)
    max_panel_length=24.0,     # Manufacturing limit
    min_panel_length=4.0,      # Minimum practical size
    max_panel_height=12.0,     # Single-story typical

    # Joint rules (feet)
    min_joint_to_opening=1.0,  # 12" from openings (GA-216)
    min_joint_to_corner=2.0,   # 24" from wall corners
    min_joint_to_shear=0.0,    # Joints OK at shear panel edges

    # Corner handling
    corner_priority=CornerPriority.LONGER_WALL,

    # Stud alignment
    stud_spacing=1.333,        # 16" OC
    snap_to_studs=True,
)
```

### Presets

```python
# Residential (8-9ft ceilings, 16" OC)
config = PanelConfig.for_residential()

# Commercial (taller ceilings, larger panels)
config = PanelConfig.for_commercial()

# 24" OC stud spacing
config = PanelConfig.for_24_oc()
```

## Usage

### Single Wall Panelization

```python
from src.timber_framing_generator.panels import (
    PanelConfig,
    decompose_wall_to_panels,
)

config = PanelConfig(max_panel_length=20.0)

result = decompose_wall_to_panels(
    wall_data,      # WallData dictionary
    framing_data,   # FramingResults dictionary (optional)
    config,
)

print(f"Created {result['total_panel_count']} panels")
for panel in result['panels']:
    print(f"  Panel {panel['id']}: {panel['length']:.1f}ft")
```

### Multi-Wall with Corner Handling

```python
from src.timber_framing_generator.panels import decompose_all_walls

# Process all walls together for corner detection
results = decompose_all_walls(
    walls_data,      # List of WallData dictionaries
    framing_results, # List of FramingResults (optional)
    config,
)

for result in results:
    # Corner adjustments applied automatically
    print(f"Wall {result['wall_id']}:")
    print(f"  Original length: {result['original_wall_length']:.2f}ft")
    print(f"  Adjusted length: {result['adjusted_wall_length']:.2f}ft")
    print(f"  Panels: {result['total_panel_count']}")
```

## Data Schemas

### PanelResults
```python
{
    "wall_id": str,
    "panels": [PanelData, ...],
    "joints": [PanelJoint, ...],
    "corner_adjustments": [WallCornerAdjustment, ...],
    "total_panel_count": int,
    "original_wall_length": float,
    "adjusted_wall_length": float,
    "metadata": {...}
}
```

### PanelData
```python
{
    "id": "wall_1_panel_0",
    "wall_id": "wall_1",
    "panel_index": 0,
    "u_start": 0.0,
    "u_end": 20.0,
    "length": 20.0,
    "height": 8.0,
    "corners": {
        "bottom_left": {"x": 0, "y": 0, "z": 0},
        "bottom_right": {"x": 20, "y": 0, "z": 0},
        "top_right": {"x": 20, "y": 0, "z": 8},
        "top_left": {"x": 0, "y": 0, "z": 8}
    },
    "element_ids": ["stud_0", "stud_1", ...],
    "estimated_weight": 800.0,
    "assembly_sequence": 0
}
```

### PanelJoint
```python
{
    "u_coord": 20.0,
    "joint_type": "field",  # or "corner_adjacent", "opening_adjacent"
    "left_panel_id": "wall_1_panel_0",
    "right_panel_id": "wall_1_panel_1",
    "stud_u_coords": [19.998, 20.125]  # Double stud at joint
}
```

## Grasshopper Integration

The panelization system uses two GHPython components:
1. **Panel Decomposer** - Calculates panels and adjusted geometry (no Revit modification)
2. **Wall Corner Adjuster** - Optionally applies corner adjustments to Revit walls

### gh_panel_decomposer.py

Calculates panel decomposition and corner adjustments. Outputs adjusted geometry for manufacturing but does NOT modify Revit walls.

**Inputs:**
| Input | NickName | Description | Default |
|-------|----------|-------------|---------|
| Walls JSON | `walls_json` | JSON from Wall Analyzer | Required |
| Framing JSON | `framing_json` | JSON from Framing Generator | Optional |
| Max Panel Length | `max_length` | Maximum panel length (ft) | 24.0 |
| Joint to Opening | `joint_opening` | Joint offset from openings (ft) | 1.0 |
| Joint to Corner | `joint_corner` | Joint offset from corners (ft) | 2.0 |
| Stud Spacing | `stud_space` | Stud spacing for alignment (ft) | 1.333 |
| Run | `run` | Boolean trigger | False |

**Outputs:**
| Output | NickName | Description |
|--------|----------|-------------|
| Panels JSON | `panels_json` | JSON with panels, joints, and corner_adjustments |
| Panel Curves | `panel_curves` | DataTree of panel boundary curves |
| Joint Points | `joint_points` | DataTree of joint location points |
| Debug Info | `debug_info` | Status messages |

### gh_wall_corner_adjuster.py

Applies corner adjustments to Revit walls using Rhino.Inside.Revit API. Use this component when you want the Revit model to reflect the adjusted wall geometry.

**Inputs:**
| Input | NickName | Description | Default |
|-------|----------|-------------|---------|
| Panels JSON | `panels_json` | JSON from Panel Decomposer | Required* |
| Adjustments JSON | `adj_json` | Direct adjustments JSON | Optional* |
| Dry Run | `dry_run` | Preview mode (no Revit changes) | True |
| Run | `run` | Boolean trigger | False |

*Either `panels_json` or `adj_json` required

**Outputs:**
| Output | NickName | Description |
|--------|----------|-------------|
| Modified Walls | `modified` | List of modified wall element IDs |
| Preview Lines | `preview` | Original and adjusted wall extent lines |
| Debug Info | `debug_info` | Status messages |

**Revit API Operations:**
1. `WallUtils.DisallowWallJoinAtEnd()` - Prevents auto-rejoining
2. `Wall.Location.Curve` modification - Extends/shortens wall

### Workflow Options

**Option A: Manufacturing Only (No Revit Changes)**
```
Wall Analyzer → Panel Decomposer → panels_json → Shop Drawings
                      ↓
              panel_curves → Visualization
```
- Revit model unchanged (centerline joins preserved)
- Panel geometry output uses adjusted dimensions
- Suitable when Revit is for coordination only

**Option B: Full Revit Integration**
```
Wall Analyzer → Panel Decomposer → panels_json → Wall Corner Adjuster
                      ↓                                  ↓
              panel_curves                    Modified Revit Walls
```
- Revit walls physically modified at corners
- Model reflects manufacturing dimensions
- Use dry_run=True first to preview changes

## Joint Placement Algorithm

The joint optimizer uses dynamic programming:

```python
# Simplified algorithm
def find_optimal_joints(wall_length, exclusion_zones, config):
    # Generate candidates at stud locations
    candidates = [i * stud_spacing for i in range(1, wall_length // stud_spacing)]

    # Filter out candidates in exclusion zones
    valid = [c for c in candidates if not in_any_zone(c, exclusion_zones)]

    # DP: find minimum panels
    dp[0] = 0  # Starting position
    for i in range(1, len(valid)):
        for j in range(i):
            panel_length = valid[i] - valid[j]
            if min_length <= panel_length <= max_length:
                dp[i] = min(dp[i], dp[j] + 1)

    # Backtrack to find joint positions
    return backtrack(dp, valid)
```

## Exclusion Zones

Joints cannot be placed:
- Within 12" (1ft) of opening edges (GA-216 standard)
- Within 24" (2ft) of wall corners
- At shear panel boundaries (configurable)

```python
# Example: wall with window
wall_length = 30.0
window = {"u_start": 10.0, "u_end": 14.0}
min_joint_to_opening = 1.0

# Creates exclusion zone from 9.0 to 15.0
# Joints at 16" OC: 1.333, 2.666, ... 9.331 (excluded), ... 14.664 (excluded), 15.997 (OK)
```

## Industry Standards Referenced

| Standard | Requirement | Config Parameter |
|----------|-------------|------------------|
| GA-216 | 12" min from gypsum joints to openings | `min_joint_to_opening` |
| APA E30 | 1/2" minimum bearing on framing | (implicit in stud alignment) |
| IRC Wall Bracing | 48" min braced wall panel | `min_panel_length` |

## Testing

```bash
# Run panel tests
pytest tests/panels/ -v

# Run specific test class
pytest tests/panels/test_joint_optimizer.py::TestFindOptimalJoints -v
```

## Common Issues

### Panel Too Long Error
If the DP algorithm can't find a valid solution, check:
1. Exclusion zones don't cover entire wall
2. `max_panel_length` > `min_panel_length`
3. Wall has room for at least one panel

### Corner Adjustments Not Applied
Ensure walls have matching endpoints within tolerance:
```python
corners = detect_wall_corners(walls_data, tolerance=0.1)  # 0.1ft = 1.2"
```

### Joints Not Aligned to Studs
Check that `snap_to_studs=True` and `stud_spacing` matches framing:
```python
config = PanelConfig(stud_spacing=1.333, snap_to_studs=True)  # 16" OC
```
