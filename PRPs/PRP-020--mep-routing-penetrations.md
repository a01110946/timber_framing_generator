# PRP-020: MEP Routing Penetration Generator Integration

## Overview

**Feature**: Penetration Generator Integration for MEP Routes
**Branch**: `feature/mep-routing-phase10-penetrations`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 10)

## Problem Statement

Routes computed by OAHS need to produce penetration specifications:

1. **Route-to-Penetration**: Convert route segments to penetration specs
2. **Code Compliance**: Validate against 40% member depth limit
3. **Reinforcement**: Flag penetrations needing structural reinforcement
4. **GHPython Component**: Visual feedback in Grasshopper

## Existing Code

### penetration_rules.py
- `generate_plumbing_penetrations(routes, framing_elements)` - Main function
- `MAX_PENETRATION_RATIO = 0.40` - Code limit
- `REINFORCEMENT_THRESHOLD = 0.33` - Above this, reinforcement required
- `PLUMBING_PENETRATION_CLEARANCE = 0.0208` (1/4" clearance)

### base.py
- `calculate_penetration_size(pipe_diameter, clearance)` - Hole diameter calc
- `check_penetration_allowed(hole_diameter, member_depth, max_ratio)` - Validation

## Solution Design

### 1. Penetration Integration Module

**File**: `src/timber_framing_generator/mep/routing/penetration_integration.py`

Bridge between OAHS routes_json and existing penetration_rules:

```python
def integrate_routes_to_penetrations(
    routes_json: str,
    framing_json: str
) -> Dict[str, Any]:
    """
    Convert OAHS routes to penetration specifications.

    Args:
        routes_json: JSON from gh_mep_router
        framing_json: JSON from gh_framing_generator

    Returns:
        Penetrations JSON with validation results
    """
```

### 2. GHPython Component

**File**: `scripts/gh_mep_penetration_generator.py`

**Inputs**:
- `routes_json`: From MEP Router
- `framing_json`: From Framing Generator
- `clearance`: Pipe clearance (default 0.25")
- `run`: Boolean trigger

**Outputs**:
- `penetrations_json`: Full penetration specs
- `allowed_pts`: Point3d for allowed penetrations
- `blocked_pts`: Point3d for blocked penetrations
- `reinforce_pts`: Point3d needing reinforcement
- `info`: Diagnostic summary

### 3. Output JSON Schema

```json
{
  "penetrations": [
    {
      "id": "pen_route_001_stud_123",
      "route_id": "route_001",
      "element_id": "stud_123",
      "element_type": "stud",
      "location": {"x": 10.5, "y": 2.0, "z": 4.5},
      "diameter": 0.125,
      "pipe_size": 0.0625,
      "system_type": "sanitary_drain",
      "is_allowed": true,
      "reinforcement_required": false,
      "penetration_ratio": 0.28,
      "warning": null
    }
  ],
  "summary": {
    "total": 15,
    "allowed": 12,
    "blocked": 3,
    "reinforcement_required": 2
  }
}
```

## Implementation Steps

### Step 1: Penetration Integration Module
- Parse routes_json and framing_json
- Convert route segments to MEPRoute format
- Call existing `generate_plumbing_penetrations`
- Return structured JSON

### Step 2: GHPython Component
- Follow grasshopper-python-assistant template
- Use RhinoCommonFactory for points
- Color code by status (green/red/orange)
- DataTree for route-grouped output

### Step 3: Integration Tests
- Test route → penetration conversion
- Test code compliance validation
- Test reinforcement flagging

## Exit Criteria

- [ ] penetration_integration.py module created
- [ ] gh_mep_penetration_generator.py component created
- [ ] Routes produce valid penetration specs
- [ ] Penetrations respect code limits (40% max)
- [ ] Reinforcement flagged when ratio > 33%
- [ ] Integration tests passing
- [ ] Component documented
