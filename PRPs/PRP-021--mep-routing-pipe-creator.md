# PRP-021: MEP Pipe/Conduit Creator Component

## Overview

**Feature**: Pipe/Conduit Creator for Rhino.Inside.Revit Integration
**Branch**: `feature/mep-routing-phase11-creator`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 11)

## Problem Statement

Routes computed by OAHS need to become Revit pipes/conduits:

1. **System Mapping**: Map route system types to Revit pipe types
2. **Pipe Creation**: Generate Revit pipes from route segments
3. **Fitting Insertion**: Add fittings at direction changes
4. **Junction Fittings**: Add T-fittings at merge points

## Solution Design

### 1. Revit Pipe Type Mapping

**File**: `src/timber_framing_generator/mep/routing/revit_pipe_mapper.py`

```python
# System type to Revit pipe type family mapping
REVIT_PIPE_TYPES = {
    "sanitary_drain": {
        "category": "Pipe",
        "system_type": "Sanitary",
        "pipe_type": "Cast Iron - No Hub"
    },
    "sanitary_vent": {
        "category": "Pipe",
        "system_type": "Sanitary",
        "pipe_type": "PVC - Schedule 40"
    },
    "dhw": {
        "category": "Pipe",
        "system_type": "Domestic Hot Water",
        "pipe_type": "Copper Type L"
    },
    "dcw": {
        "category": "Pipe",
        "system_type": "Domestic Cold Water",
        "pipe_type": "PEX"
    },
    "power": {
        "category": "Conduit",
        "system_type": "Power",
        "conduit_type": "EMT"
    },
    "data": {
        "category": "Conduit",
        "system_type": "Communications",
        "conduit_type": "EMT"
    },
}
```

### 2. GHPython Component: gh_mep_pipe_creator.py

**Inputs**:
- `routes_json`: From MEP Router
- `doc`: Revit document (from RiR)
- `pipe_type_overrides`: Optional JSON for custom type mappings
- `create_fittings`: Boolean to enable fitting creation
- `run`: Boolean trigger

**Outputs**:
- `pipe_specs_json`: Pipe specifications for Revit creation
- `fitting_specs_json`: Fitting specifications
- `curves`: Visualization curves for review
- `info`: Diagnostic summary

### 3. Pipe Specification Schema

```json
{
  "pipes": [
    {
      "id": "pipe_001",
      "route_id": "route_001",
      "system_type": "sanitary_drain",
      "start_point": [0.0, 0.0, 4.0],
      "end_point": [5.0, 0.0, 4.0],
      "diameter": 0.125,
      "revit_config": {
        "system_type": "Sanitary",
        "pipe_type": "Cast Iron - No Hub",
        "level": "Level 1"
      }
    }
  ],
  "fittings": [
    {
      "id": "fitting_001",
      "type": "elbow_90",
      "location": [5.0, 0.0, 4.0],
      "connected_pipes": ["pipe_001", "pipe_002"],
      "angle": 90
    }
  ]
}
```

### 4. Fitting Detection Logic

**Direction Changes**:
- Calculate angle between consecutive segments
- 85-95°: Insert 90° elbow
- 40-50°: Insert 45° elbow
- Other angles: Flag for manual review

**Junction Points**:
- Detect where multiple routes merge
- Insert tee fitting
- Determine main vs branch connections

## Implementation Steps

### Step 1: Pipe Mapper Module
- System type to Revit type mapping
- Default and override configuration
- Size mapping (nominal to actual)

### Step 2: Fitting Detector
- Angle calculation between segments
- Junction detection
- Fitting type selection

### Step 3: GHPython Component
- Parse routes_json
- Generate pipe specs with Revit config
- Generate fitting specs
- Output visualization curves

### Step 4: Tests
- Pipe type mapping tests
- Fitting detection tests
- JSON serialization tests

## Exit Criteria

- [ ] revit_pipe_mapper.py module created
- [ ] gh_mep_pipe_creator.py component created
- [ ] System types map to correct Revit pipe types
- [ ] Fittings detected at direction changes
- [ ] T-fittings detected at junctions
- [ ] Tests passing
- [ ] Component documented

## Notes

The actual Revit pipe creation via API will be handled by a downstream
component using Rhino.Inside.Revit's Python API. This component produces
the specifications needed for that creation step.
