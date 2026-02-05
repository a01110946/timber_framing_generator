# PRP-019: MEP Route Visualization Component

## Overview

**Feature**: Route Visualization GHPython Component
**Branch**: `feature/mep-routing-phase9-visualizer`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 9)

## Problem Statement

Routes computed by OAHS need to be visualized in Rhino:

1. **Curve Generation**: Convert route segments to RhinoCommon curves
2. **Color Coding**: Distinguish system types visually
3. **Junction Markers**: Show Steiner/junction points
4. **Debug Visualization**: Display graph edges and occupancy

## Solution Design

### 1. GHPython Component: gh_mep_route_visualizer.py

**Inputs:**
- `routes_json`: JSON string with computed routes
- `color_by_system`: Boolean to enable system-type coloring
- `show_junctions`: Boolean to show junction points
- `show_occupancy`: Boolean to visualize reserved space

**Outputs:**
- `curves`: Route curves (colored by system)
- `colors`: Color list matching curves
- `points`: Junction/Steiner points
- `info`: Diagnostic information

### 2. System Color Scheme

| System Type | Color | RGB |
|-------------|-------|-----|
| Sanitary Drain | Brown | (139, 90, 43) |
| Sanitary Vent | Gray | (128, 128, 128) |
| DHW | Red | (255, 0, 0) |
| DCW | Blue | (0, 0, 255) |
| Power | Yellow | (255, 255, 0) |
| Data | Orange | (255, 165, 0) |
| Lighting | White | (255, 255, 255) |

### 3. Coordinate Transformation

Routes use 2D plane coordinates (U, V). Need to transform to 3D world:

```python
def transform_to_world(segment, domain_info):
    """Transform 2D route segment to 3D world coordinates."""
    if domain_info["type"] == "wall":
        # Wall plane: U along wall, V vertical
        plane = domain_info["base_plane"]
        start_3d = plane.PointAt(segment.start[0], segment.start[1])
        end_3d = plane.PointAt(segment.end[0], segment.end[1])
    elif domain_info["type"] == "floor":
        # Floor plane: X, Y horizontal
        z = domain_info["elevation"]
        start_3d = Point3d(segment.start[0], segment.start[1], z)
        end_3d = Point3d(segment.end[0], segment.end[1], z)
    return start_3d, end_3d
```

### 4. Assembly-Safe Geometry

Must use RhinoCommonFactory for correct assembly:

```python
from src.timber_framing_generator.utils.geometry_factory import get_factory

factory = get_factory()
line = factory.create_line(start_3d, end_3d)
curve = factory.create_polyline_curve(points)
```

## Implementation Steps

### Step 1: Basic Curve Generation
- Parse routes_json
- Create line curves for each segment
- Return as DataTree

### Step 2: Color Coding
- System type color mapping
- Apply colors to curves
- Return color list

### Step 3: Junction Points
- Extract Steiner points from routes
- Create point markers
- Optional display

### Step 4: Debug Visualization
- Graph edge display
- Occupancy region display
- Node labels

## File Structure

```
scripts/
    gh_mep_route_visualizer.py  # Main visualization component
```

## Test Cases

1. Single route → single colored curve
2. Multiple routes → correct colors per system
3. Route with junctions → points displayed
4. Empty routes_json → graceful handling

## Exit Criteria

- [ ] gh_mep_route_visualizer.py component created
- [ ] Routes display as curves in Rhino
- [ ] System types color-coded correctly
- [ ] Works with RhinoCommonFactory
- [ ] Junction points optionally shown
- [ ] Component documented
