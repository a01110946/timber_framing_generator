# Modular Multi-Material Framing Architecture

> **Status**: ✅ COMPLETE
> **Created**: 2026-01-21
> **Completed**: 2026-01-21
> **Phase**: 5 of 5 (All Complete)

## Overview

This document describes the modular architecture that supports multiple material systems (Timber and CFS) with modular GHPython components communicating via JSON. All phases have been implemented and tested.

---

## Architecture Diagram

### Recommended Pipeline (Panelization Before Framing)

For offsite/prefab construction, panelization should happen BEFORE cell decomposition:

```
┌────────────────────────────────────────────────────────────────────────────┐
│              GRASSHOPPER COMPONENT PIPELINE (PANELIZED)                    │
└────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 1. Wall Analyzer │───>│ 2. Panel Decomp  │───>│ 3. Cell Decomp   │
│  (GHPython #1)   │JSON│  (GHPython #2)   │JSON│  (GHPython #3)   │
├──────────────────┤    ├──────────────────┤    ├──────────────────┤
│ IN:              │    │ IN:              │    │ IN:              │
│  - revit_walls   │    │  - walls_json    │    │  - wall_json     │
│                  │    │  - max_length    │    │  - panels_json   │ <─ NEW
│ OUT:             │    │  - stud_spacing  │    │                  │
│  - wall_json     │    │ OUT:             │    │ OUT:             │
│  - wall_viz      │    │  - panels_json   │    │  - cell_json     │
│ (Material-Agnostic)   │  - panel_curves  │    │  - cell_viz      │
└──────────────────┘    └──────────────────┘    └──────────────────┘
                                                         │
       ┌─────────────────────────────────────────────────┘
       ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 4. Framing Gen   │───>│ 5. Geo Converter │───>│ 6. Optional Bake │
│  (GHPython #4)   │JSON│  (GHPython #5)   │Brep│  (GHPython #6)   │
├──────────────────┤    ├──────────────────┤    ├──────────────────┤
│ IN:              │    │ IN:              │    │ IN:              │
│  - cell_json     │    │  - elements_json │    │  - geometry      │
│  - wall_json     │    │  - filter_types  │    │  - layers        │
│  - material_type │    │ OUT:             │    │ OUT:             │
│ OUT:             │    │  - breps         │    │  - baked_ids     │
│  - elements_json │    │  - curves        │    │                  │
│  (panel_id in    │    │  - metadata      │    │                  │
│   metadata)      │    │ (Material-Agnostic)   │                  │
│ (Material-Specific)   └──────────────────┘    └──────────────────┘
└──────────────────┘
```

**Key Changes in Panelized Pipeline:**
- Panel Decomposer runs BEFORE Cell Decomposer
- Cell Decomposer accepts optional `panels_json` input
- Cells are decomposed per-panel (not per-wall)
- Cell IDs include panel info: `wall_1_panel_0_SC_0`
- Framing elements include `panel_id` in metadata
- End studs automatically placed at panel boundaries

### Legacy Pipeline (Whole-Wall Mode)

For non-panelized workflows, leave Panel Decomposer disconnected:

```
┌────────────────────────────────────────────────────────────────────────────┐
│              GRASSHOPPER COMPONENT PIPELINE (LEGACY)                       │
└────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 1. Wall Analyzer │───>│ 2. Cell Decomp   │───>│ 3. Framing Gen   │
│  (GHPython #1)   │JSON│  (GHPython #2)   │JSON│  (GHPython #3)   │
├──────────────────┤    ├──────────────────┤    ├──────────────────┤
│ IN:              │    │ IN:              │    │ IN:              │
│  - revit_walls   │    │  - wall_json     │    │  - cell_json     │
│                  │    │                  │    │  - material_type │
│ OUT:             │    │ OUT:             │    │  - config        │
│  - wall_json     │    │  - cell_json     │    │ OUT:             │
│  - wall_viz      │    │  - cell_viz      │    │  - elements_json │
│ (Material-Agnostic)   │ (Material-Agnostic)   │ (Material-Specific)
└──────────────────┘    └──────────────────┘    └──────────────────┘
                                                         │
                        ┌────────────────────────────────┘
                        ▼
┌──────────────────┐    ┌──────────────────┐
│ 4. Geo Converter │───>│ 5. Optional Bake │
│  (GHPython #4)   │Brep│  (GHPython #5)   │
├──────────────────┤    ├──────────────────┤
│ IN:              │    │ IN:              │
│  - elements_json │    │  - geometry      │
│  - filter_types  │    │  - layers        │
│ OUT:             │    │ OUT:             │
│  - breps         │    │  - baked_ids     │
│  - curves        │    │                  │
│  - metadata      │    │                  │
│ (Material-Agnostic)   │                  │
└──────────────────┘    └──────────────────┘
```

---

## Key Design Decisions

### 1. JSON as Intermediate Format
- All data between GHPython components passes as JSON strings
- Enables inspection with jSwan or Panel components
- Supports caching and API integration
- Geometry serialized as coordinate data, not live Rhino objects

### 2. Material Strategy Pattern
```python
class FramingStrategy(ABC):
    @abstractmethod
    def get_generation_sequence(self) -> List[str]: pass
    @abstractmethod
    def create_plates(self, wall_data, cell_data, config): pass
    @abstractmethod
    def create_studs(self, wall_data, cell_data, plates, config): pass
    # ... etc

class TimberStrategy(FramingStrategy):
    # Uses: plates, studs, king_studs, headers, sills, cripples, blocking

class CFSStrategy(FramingStrategy):
    # Uses: tracks, studs, king_studs, web_stiffeners, headers, bridging
```

### 3. Shared vs Material-Specific Logic

| Component | Shared (Material-Agnostic) | Material-Specific |
|-----------|---------------------------|-------------------|
| Wall Data Extraction | ✓ | |
| Cell Decomposition | ✓ | |
| Element Positioning (UV coords) | ✓ | |
| Profile Dimensions | | ✓ (lumber vs C-section) |
| Element Types | | ✓ (plates vs tracks) |
| Generation Sequence | | ✓ (different dependencies) |
| Geometry Creation | ✓ (from centerline+profile) | |

---

## JSON Schemas (Simplified)

### Wall Data (Stage 1 Output)
```json
{
  "wall_id": "string",
  "wall_length": 12.5,
  "wall_height": 8.0,
  "base_plane": { "origin": [x,y,z], "x_axis": [...], "y_axis": [...] },
  "openings": [
    { "type": "window", "u_start": 3.0, "width": 3.0, "height": 4.0, "sill_height": 2.5 }
  ]
}
```

### Cell Data (Stage 2 Output)
```json
{
  "wall_id": "string",
  "cells": [
    { "type": "SC", "u_start": 0, "u_end": 3, "v_start": 0, "v_end": 8, "corners": [[x,y,z], ...] },
    { "type": "OC", "u_start": 3, "u_end": 6, "v_start": 2.5, "v_end": 6.5, "opening_type": "window" }
  ]
}
```

### Framing Elements (Stage 3 Output)
```json
{
  "material_system": "timber",
  "elements": [
    {
      "id": "stud_001",
      "type": "stud",
      "profile": { "name": "2x4", "width": 0.292, "depth": 0.125 },
      "centerline": { "start": [1.33, 0, 0], "end": [1.33, 0, 8] },
      "u_coord": 1.33
    }
  ]
}
```

---

## Package Structure

```
src/timber_framing_generator/
├── core/                           # ✅ COMPLETE (Phase 1)
│   ├── __init__.py                 # Exports core components
│   ├── material_system.py          # MaterialSystem enum, FramingStrategy ABC, ElementType
│   └── json_schemas.py             # WallData, CellData, FramingResults dataclasses
│
├── materials/                      # ✅ COMPLETE (Phases 2 & 4)
│   ├── __init__.py                 # Imports both material modules for registration
│   ├── timber/
│   │   ├── __init__.py             # Exports TimberFramingStrategy, profiles
│   │   ├── timber_strategy.py      # TimberFramingStrategy
│   │   └── timber_profiles.py      # 2x4, 2x6, 2x8, 2x10, 2x12
│   └── cfs/
│       ├── __init__.py             # Exports CFSFramingStrategy, profiles
│       ├── cfs_strategy.py         # CFSFramingStrategy
│       └── cfs_profiles.py         # 350S/600S/800S studs, tracks
│
├── cell_decomposition/             # UNCHANGED (material-agnostic)
├── wall_data/                      # UNCHANGED (material-agnostic)
├── framing_elements/               # Existing generation logic (to be integrated)
└── utils/
    └── geometry_factory.py         # ✅ COMPLETE - RhinoCommonFactory

scripts/                            # ✅ COMPLETE (Phase 3+)
├── gh_wall_analyzer.py             # Component 1: Revit → walls_json
├── gh_panel_decomposer.py          # Component 2: walls_json → panels_json (optional)
├── gh_cell_decomposer.py           # Component 3: walls_json + panels_json → cell_json
├── gh_framing_generator.py         # Component 4: cell_json → elements_json
└── gh_geometry_converter.py        # Component 5: elements_json → RhinoCommon Breps
```

---

## GHPython Components

### Component 1: Wall Analyzer
**File**: `scripts/gh_wall_analyzer.py`
```
Inputs:
  - walls (Revit wall elements)
  - run (bool)

Outputs:
  - wall_json (str) - JSON array of wall data
  - wall_curves (Curve[]) - Visualization of wall base curves
  - debug_info (str)

Logic:
  - Calls existing revit_data_extractor
  - Serializes to JSON
  - Creates visualization geometry
```

### Component 2: Panel Decomposer (Optional)
**File**: `scripts/gh_panel_decomposer.py`
```
Inputs:
  - walls_json (str) - JSON from Wall Analyzer
  - elements_json (str) - Optional, for stud alignment
  - max_length (float) - Maximum panel length in feet
  - stud_space (float) - Stud spacing for joint alignment
  - run (bool)

Outputs:
  - panels_json (str) - JSON with panel data and joints
  - panel_curves (Curve[]) - Panel boundary curves
  - joint_points (Point3d[]) - Joint location points
  - debug_info (str)

Logic:
  - Decomposes walls into transportable panels
  - Calculates optimal joint positions
  - Handles corner adjustments for face-to-face dimensions
```

### Component 3: Cell Decomposer
**File**: `scripts/gh_cell_decomposer.py`
```
Inputs:
  - wall_json (str) - JSON from Wall Analyzer
  - panels_json (str) - Optional, JSON from Panel Decomposer
  - run (bool)

Outputs:
  - cell_json (str) - JSON with all cell data
  - cell_rectangles (Surface[]) - Cell boundaries for visualization
  - cell_types (str[]) - Cell type labels

Logic:
  - If panels_json provided: Decompose per-panel (panel-aware mode)
  - If panels_json empty: Decompose per-wall (legacy mode)
  - Panel-aware cell IDs: wall_1_panel_0_SC_0
  - Legacy cell IDs: wall_1_SC_0
```

### Component 4: Framing Generator
**File**: `scripts/gh_framing_generator.py`
```
Inputs:
  - cell_json (str)
  - wall_json (str)
  - material_type (str) - "timber" or "cfs"
  - config_json (str) - Optional configuration overrides

Outputs:
  - elements_json (str) - All framing elements as JSON
  - element_count (int) - Summary count
  - generation_log (str) - Debug info

Logic:
  - Selects strategy based on material_type
  - Generates elements using strategy
  - Passes panel_id to element metadata (if from panel-aware decomposition)
  - Serializes to JSON (no geometry yet!)
```

### Component 5: Geometry Converter
**File**: `scripts/gh_geometry_converter.py`
```
Inputs:
  - elements_json (str)
  - filter_types (str[]) - Optional: only convert certain element types

Outputs:
  - breps (Brep[]) - All framing geometry
  - by_type (DataTree<Brep>) - Geometry organized by element type
  - centerlines (Curve[]) - Element centerlines
  - metadata (str[]) - Element IDs for selection

Logic:
  - Uses RhinoCommonFactory pattern
  - Creates geometry from centerline + profile data
  - Handles assembly mismatch issue here only
```

---

## Migration Plan

### Phase 1: Extract Core Abstractions ✅ COMPLETE
1. ✅ Created `core/material_system.py` with FramingStrategy ABC, ElementType enum
2. ✅ Created `core/json_schemas.py` with WallData, CellData, FramingResults
3. ✅ Extracted `RhinoCommonFactory` to `utils/geometry_factory.py`

### Phase 2: Wrap Timber in Strategy ✅ COMPLETE
1. ✅ Created `materials/timber/timber_strategy.py` - TimberFramingStrategy
2. ✅ Created `materials/timber/timber_profiles.py` - 2x4 through 2x12
3. ✅ Strategy registers via `register_strategy()` at module import
4. ✅ 21 unit tests passing

### Phase 3: Create Modular GHPython Components ✅ COMPLETE
1. ✅ Created `scripts/gh_wall_analyzer.py` - Revit → wall_json
2. ✅ Created `scripts/gh_cell_decomposer.py` - wall_json → cell_json
3. ✅ Created `scripts/gh_framing_generator.py` - cell_json → elements_json
4. ✅ Created `scripts/gh_geometry_converter.py` - elements_json → Breps

### Phase 4: Add CFS Support ✅ COMPLETE
1. ✅ Created `materials/cfs/cfs_strategy.py` - CFSFramingStrategy
2. ✅ Created `materials/cfs/cfs_profiles.py` - studs (350S/600S/800S) and tracks
3. ✅ Added CFS profile catalog with gauge information
4. ✅ 41 unit tests passing, both strategies coexist

### Phase 5: Documentation & Polish ✅ COMPLETE
1. ✅ Updated AI documentation files
2. ✅ All PRPs documented in PRPs/ directory
3. ✅ All 62 unit tests passing (21 timber + 41 CFS)

---

## CFS vs Timber: Key Differences

| Aspect | Timber | CFS |
|--------|--------|-----|
| Horizontal members | Plates (2x4, 2x6) | Tracks (C-section, no lips) |
| Vertical members | Studs (2x4, 2x6) | Studs (C-section with lips) |
| Profile shape | Rectangular | C-section |
| Additional elements | Blocking | Web stiffeners, bridging |
| Connections | Nails | Screws, clip angles |
| Headers | Solid lumber or built-up | Box headers or back-to-back |

---

## Verification Plan

### Unit Tests
- JSON serialization/deserialization for each schema
- Strategy selection based on material type
- Profile catalog lookups

### Integration Tests
- Full pipeline: Revit wall → JSON → Geometry
- Both material systems produce valid output
- Assembly mismatch resolved in geometry stage

### Grasshopper Tests
- Each component works standalone
- Pipeline produces same results as current monolithic script
- jSwan can parse all JSON outputs

---

## Files Created

### Core Infrastructure (Phase 1)
- ✅ `src/timber_framing_generator/core/__init__.py`
- ✅ `src/timber_framing_generator/core/material_system.py`
- ✅ `src/timber_framing_generator/core/json_schemas.py`
- ✅ `src/timber_framing_generator/utils/geometry_factory.py`

### Timber Materials (Phase 2)
- ✅ `src/timber_framing_generator/materials/__init__.py`
- ✅ `src/timber_framing_generator/materials/timber/__init__.py`
- ✅ `src/timber_framing_generator/materials/timber/timber_strategy.py`
- ✅ `src/timber_framing_generator/materials/timber/timber_profiles.py`

### GHPython Components (Phase 3)
- ✅ `scripts/gh_wall_analyzer.py`
- ✅ `scripts/gh_cell_decomposer.py`
- ✅ `scripts/gh_framing_generator.py`
- ✅ `scripts/gh_geometry_converter.py`

### CFS Materials (Phase 4)
- ✅ `src/timber_framing_generator/materials/cfs/__init__.py`
- ✅ `src/timber_framing_generator/materials/cfs/cfs_strategy.py`
- ✅ `src/timber_framing_generator/materials/cfs/cfs_profiles.py`

### Unit Tests
- ✅ `tests/unit/test_timber_strategy.py` (21 tests)
- ✅ `tests/unit/test_cfs_strategy.py` (41 tests)

### PRPs
- ✅ `PRPs/002--timber-strategy-pattern.md`
- ✅ `PRPs/003--modular-ghpython-components.md`
- ✅ `PRPs/004--cfs-strategy-pattern.md`
- ✅ `PRPs/005--documentation-polish.md`

---

## Notes

- **JSON vs Geometry**: Geometry creation happens in the LAST stage only. All intermediate stages work with JSON data.
- **RhinoCommon Issue**: Only `gh_geometry_converter.py` handles assembly mismatch via RhinoCommonFactory
- **Backward Compatibility**: `gh-main.py` preserved as reference implementation
- **jSwan Integration**: JSON outputs can connect directly to jSwan for inspection

## Usage Examples

### Material Selection
```python
from src.timber_framing_generator.core import get_framing_strategy, MaterialSystem
from src.timber_framing_generator.materials import timber, cfs  # Triggers registration

# Get strategy for specific material
timber_strategy = get_framing_strategy(MaterialSystem.TIMBER)
cfs_strategy = get_framing_strategy(MaterialSystem.CFS)

# Use strategy
elements = timber_strategy.generate_framing(wall_data, cell_data, config)
```

### Grasshopper Pipeline (Panelized - Recommended)
```
[Revit Walls] → [Wall Analyzer] → walls_json
                                      ↓
              [Panel Decomposer] ← walls_json → panels_json
                                                    ↓
[Cell Decomposer] ← walls_json + panels_json → cell_json (per-panel cells)
                                                    ↓
[Framing Generator] ← cell_json + material_type → elements_json (with panel_id)
                                                       ↓
[Geometry Converter] ← elements_json → breps, centerlines
```

### Grasshopper Pipeline (Legacy - Without Panels)
```
[Revit Walls] → [Wall Analyzer] → wall_json
                                      ↓
[Cell Decomposer] ← wall_json  → cell_json
                                      ↓
[Framing Generator] ← cell_json + material_type → elements_json
                                                       ↓
[Geometry Converter] ← elements_json → breps, centerlines
```

### Profile Lookup
```python
from src.timber_framing_generator.materials.timber import get_timber_profile
from src.timber_framing_generator.materials.cfs import get_cfs_profile
from src.timber_framing_generator.core.material_system import ElementType

# Timber profile
stud_profile = get_timber_profile(ElementType.STUD)  # Returns 2x4

# CFS profile
track_profile = get_cfs_profile(ElementType.BOTTOM_PLATE)  # Returns 350T125-54
```
