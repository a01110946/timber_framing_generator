# Modular Multi-Material Framing Architecture

> **Status**: In Progress
> **Created**: 2026-01-21
> **Phase**: 2 of 5

## Overview

Refactor the framing generator to support multiple material systems (Timber and CFS) with modular GHPython components communicating via JSON.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    GRASSHOPPER COMPONENT PIPELINE                          │
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
├── core/                           # ✅ DONE (Phase 1)
│   ├── material_system.py          # MaterialSystem enum, base classes
│   ├── strategy_factory.py         # FramingStrategyFactory
│   └── json_schemas.py             # Schema definitions + validation
│
├── materials/                      # 🔄 IN PROGRESS (Phase 2)
│   ├── timber/
│   │   ├── timber_strategy.py      # TimberFramingStrategy
│   │   └── timber_profiles.py      # Lumber profiles (2x4, 2x6, etc.)
│   └── cfs/
│       ├── cfs_strategy.py         # CFSFramingStrategy (Phase 4)
│       └── cfs_profiles.py         # Steel profiles (Phase 4)
│
├── cell_decomposition/             # UNCHANGED (material-agnostic)
├── wall_data/                      # UNCHANGED (material-agnostic)
├── framing_elements/               # REFACTOR: Use strategy pattern
└── utils/
    ├── serialization.py            # ENHANCE: Add JSON schema support
    └── geometry_factory.py         # ✅ DONE (Phase 1)
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

### Component 2: Cell Decomposer
**File**: `scripts/gh_cell_decomposer.py`
```
Inputs:
  - wall_json (str)

Outputs:
  - cell_json (str) - JSON with all cell data
  - cell_rectangles (Surface[]) - Cell boundaries for visualization
  - cell_types (str[]) - Cell type labels

Logic:
  - Calls existing cell_segmentation
  - Serializes cells to JSON
  - Creates cell visualization surfaces
```

### Component 3: Framing Generator
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
  - Serializes to JSON (no geometry yet!)
```

### Component 4: Geometry Converter
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
1. ✅ Create `core/material_system.py` with base classes
2. ✅ Create `core/json_schemas.py` with schema definitions
3. ✅ Extract `RhinoCommonFactory` to `utils/geometry_factory.py`

### Phase 2: Wrap Timber in Strategy 🔄 IN PROGRESS
1. Create `materials/timber/timber_strategy.py`
2. Create `materials/timber/timber_profiles.py`
3. Migrate existing framing logic to strategy methods
4. Ensure all existing tests pass

### Phase 3: Create Modular GHPython Components
1. Create `gh_wall_analyzer.py`
2. Create `gh_cell_decomposer.py`
3. Create `gh_framing_generator.py`
4. Create `gh_geometry_converter.py`
5. Test pipeline with timber

### Phase 4: Add CFS Support
1. Create `materials/cfs/cfs_strategy.py`
2. Implement CFS-specific elements (tracks, web stiffeners)
3. Add CFS profiles catalog
4. Test CFS pipeline

### Phase 5: Documentation & Polish
1. Update AI documentation files
2. Create example Grasshopper definitions
3. Add validation and error handling

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

## Files to Modify/Create

### New Files
- ✅ `src/timber_framing_generator/core/material_system.py`
- ✅ `src/timber_framing_generator/core/json_schemas.py`
- ✅ `src/timber_framing_generator/utils/geometry_factory.py`
- 🔄 `src/timber_framing_generator/materials/timber/timber_strategy.py`
- 🔄 `src/timber_framing_generator/materials/timber/timber_profiles.py`
- `src/timber_framing_generator/materials/cfs/cfs_strategy.py`
- `scripts/gh_wall_analyzer.py`
- `scripts/gh_cell_decomposer.py`
- `scripts/gh_framing_generator.py`
- `scripts/gh_geometry_converter.py`

### Refactored Files
- `src/timber_framing_generator/framing_elements/framing_generator.py` → Use strategy pattern
- `src/timber_framing_generator/utils/serialization.py` → Add JSON schema support
- `scripts/gh-main.py` → Extract RhinoCommonFactory, keep as reference

---

## Notes

- **JSON vs Geometry**: Keep geometry creation in the LAST stage only. All intermediate stages work with JSON data.
- **RhinoCommon Issue**: Only `gh_geometry_converter.py` needs to handle assembly mismatch
- **Backward Compatibility**: Keep `gh-main.py` working for now, migrate gradually
- **jSwan Integration**: JSON outputs can connect directly to jSwan for inspection
