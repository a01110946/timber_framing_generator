# PRP: Modular GHPython Components (Phase 3)

> **Version:** 1.0
> **Created:** 2026-01-21
> **Status:** Ready
> **Branch:** feature/phase3-modular-ghpython

---

## Goal
Create four modular GHPython component scripts that communicate via JSON strings, enabling inspection of intermediate data and supporting both Timber and CFS framing through the strategy pattern.

## Why
- **Debuggability**: JSON outputs can be inspected with Panel or jSwan components
- **Modularity**: Each component is independently testable and replaceable
- **Multi-Material**: Strategy pattern enables material switching via input parameter
- **API Integration**: JSON format enables future web API integration

## What
Create four GHPython scripts in `scripts/`:
1. `gh_wall_analyzer.py` - Extracts wall data from Revit, outputs JSON
2. `gh_cell_decomposer.py` - Decomposes walls into cells, outputs JSON
3. `gh_framing_generator.py` - Generates framing elements as JSON (no geometry)
4. `gh_geometry_converter.py` - Converts JSON elements to RhinoCommon Breps

### Success Criteria
- [ ] Each component can be loaded in a GHPython node
- [ ] Components communicate via JSON strings
- [ ] JSON outputs can be parsed by jSwan or Panel components
- [ ] `gh_geometry_converter` produces valid RhinoCommon Breps
- [ ] Pipeline produces same results as current `gh-main.py`
- [ ] Syntax check passes for all new files

---

## All Needed Context

### Documentation & References
```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-modular-architecture-plan.md
    why: Pipeline architecture diagram and component specs

  - file: docs/ai/ai-grasshopper-rhino-patterns.md
    why: CLR reflection, DataTree usage, RhinoCommon patterns

  - file: CLAUDE.md
    why: Project conventions and critical gotchas

Core Modules:
  - file: src/timber_framing_generator/core/json_schemas.py
    why: WallData, CellData, FramingResults dataclasses and serialization

  - file: src/timber_framing_generator/core/material_system.py
    why: FramingStrategy, get_framing_strategy(), MaterialSystem enum

  - file: src/timber_framing_generator/utils/geometry_factory.py
    why: RhinoCommonFactory for creating GH-compatible geometry

Existing Scripts:
  - file: scripts/gh-main.py
    why: Current monolithic implementation - patterns to extract
    key_sections:
      - lines 1-100: RhinoCommon setup and imports
      - lines 134-730: RhinoCommonFactory class
      - lines 800-900: convert_breps_for_output()

  - file: src/timber_framing_generator/wall_data/revit_data_extractor.py
    why: extract_wall_data_from_revit() function to call

  - file: src/timber_framing_generator/cell_decomposition/cell_segmentation.py
    why: decompose_wall_to_cells() function to call
```

### Pipeline Architecture
```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 1. Wall Analyzer │───>│ 2. Cell Decomp   │───>│ 3. Framing Gen   │
│                  │JSON│                  │JSON│                  │
│ IN: revit_walls  │    │ IN: wall_json    │    │ IN: cell_json    │
│ OUT: wall_json   │    │ OUT: cell_json   │    │     wall_json    │
│      wall_curves │    │      cell_srf    │    │     material     │
│                  │    │      cell_types  │    │ OUT: elements_json
└──────────────────┘    └──────────────────┘    └──────────────────┘
                                                         │
                        ┌────────────────────────────────┘
                        ▼
                ┌──────────────────┐
                │ 4. Geo Converter │
                │                  │
                │ IN: elements_json│
                │ OUT: breps       │
                │      by_type     │
                │      centerlines │
                └──────────────────┘
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: RhinoCommon Setup (same as gh-main.py)
# - Must remove rhino3dm from sys.path BEFORE importing Rhino
# - Must add CLR references before importing Rhino.Geometry
# - Each GHPython component needs this setup at top

# CRITICAL: JSON Serialization
# - All geometry must be serialized as coordinates, not Rhino objects
# - Use Point3D.from_rhino() to extract coordinates
# - Use PlaneData.from_rhino() for planes

# CRITICAL: Strategy Registration
# - Must import materials.timber module to trigger registration
# - get_framing_strategy() will fail if not imported

# CRITICAL: DataTree for Multiple Walls
# - Use DataTree[object]() for grafted outputs
# - One wall = one branch (GH_Path(wall_index))
```

---

## Implementation Blueprint

### Tasks (in execution order)

```yaml
Task 1: Create gh_wall_analyzer.py
  - CREATE: scripts/gh_wall_analyzer.py
  - PURPOSE: Extract wall data from Revit, serialize to JSON
  - INPUTS: walls (Revit walls), run (bool)
  - OUTPUTS: wall_json (str), wall_curves (Curve[]), debug_info (str)
  - DELEGATES TO: extract_wall_data_from_revit()

Task 2: Create gh_cell_decomposer.py
  - CREATE: scripts/gh_cell_decomposer.py
  - PURPOSE: Decompose walls into cells, serialize to JSON
  - INPUTS: wall_json (str)
  - OUTPUTS: cell_json (str), cell_srf (Surface[]), cell_types (str[])
  - DELEGATES TO: decompose_wall_to_cells()

Task 3: Create gh_framing_generator.py
  - CREATE: scripts/gh_framing_generator.py
  - PURPOSE: Generate framing elements as JSON data (no geometry)
  - INPUTS: cell_json (str), wall_json (str), material_type (str), config_json (str)
  - OUTPUTS: elements_json (str), element_count (int), generation_log (str)
  - USES: get_framing_strategy(MaterialSystem.TIMBER)

Task 4: Create gh_geometry_converter.py
  - CREATE: scripts/gh_geometry_converter.py
  - PURPOSE: Convert JSON elements to RhinoCommon Breps
  - INPUTS: elements_json (str), filter_types (str[])
  - OUTPUTS: breps (Brep[]), by_type (DataTree), centerlines (Curve[])
  - USES: RhinoCommonFactory from geometry_factory.py
```

### Pseudocode

```python
# Task 1: gh_wall_analyzer.py
# ============================================================================
"""
GHPython Component: Wall Analyzer

Inputs:
    walls: Revit wall elements (list)
    run: Boolean to trigger execution

Outputs:
    wall_json: JSON string with wall data for all walls
    wall_curves: Wall base curves for visualization
    debug_info: Debug information string
"""

import sys
import clr
import json

# RhinoCommon setup (simplified - see gh-main.py for full version)
clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')
clr.AddReference('RhinoInside.Revit')

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path
from RhinoInside.Revit import Revit

# Add project path
PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.wall_data.revit_data_extractor import (
    extract_wall_data_from_revit
)
from src.timber_framing_generator.core.json_schemas import (
    WallData, Point3D, PlaneData, OpeningData, serialize_wall_data
)

# Initialize outputs
wall_json = "[]"
wall_curves = DataTree[object]()
debug_info = ""

if run and walls:
    doc = Revit.ActiveDBDocument
    wall_data_list = []
    debug_lines = []

    for i, wall in enumerate(walls):
        try:
            # Extract wall data using existing function
            data = extract_wall_data_from_revit(wall, doc)
            if data:
                # Convert to JSON-serializable format
                wall_data = WallData(
                    wall_id=str(wall.Id.IntegerValue),
                    wall_length=float(data.get('wall_length', 0)),
                    wall_height=float(data.get('wall_height', 0)),
                    # ... more fields
                )
                wall_data_list.append(wall_data)

                # Add base curve for visualization
                base_curve = data.get('wall_base_curve')
                if base_curve:
                    wall_curves.Add(base_curve, GH_Path(i))

                debug_lines.append(f"Wall {i}: OK")
        except Exception as e:
            debug_lines.append(f"Wall {i}: ERROR - {e}")

    # Serialize all walls to JSON
    wall_json = json.dumps([asdict(w) for w in wall_data_list], indent=2)
    debug_info = "\n".join(debug_lines)

# Assign outputs (GH component outputs)
a = wall_json
b = wall_curves
c = debug_info
```

```python
# Task 4: gh_geometry_converter.py (most complex)
# ============================================================================
"""
GHPython Component: Geometry Converter

Inputs:
    elements_json: JSON string with framing elements
    filter_types: Optional list of element types to include (e.g., ["stud", "plate"])

Outputs:
    breps: All framing geometry as Breps
    by_type: DataTree organized by element type
    centerlines: Element centerlines as curves
    metadata: Element IDs for selection feedback
"""

import sys
import clr
import json

# RhinoCommon setup
clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# Project imports
PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.utils.geometry_factory import get_factory
from src.timber_framing_generator.core.json_schemas import (
    deserialize_framing_results, FramingElementData
)

# Initialize outputs
breps = []
by_type = DataTree[object]()
centerlines = []
metadata = []

if elements_json:
    try:
        # Get geometry factory
        factory = get_factory()

        # Parse JSON
        results = deserialize_framing_results(elements_json)

        # Group elements by type for by_type output
        type_groups = {}

        for element in results.elements:
            # Apply filter if provided
            if filter_types and element.element_type not in filter_types:
                continue

            # Create Brep from centerline + profile
            start = element.centerline_start
            end = element.centerline_end

            # Calculate direction and length
            dx = end.x - start.x
            dy = end.y - start.y
            dz = end.z - start.z
            length = (dx*dx + dy*dy + dz*dz) ** 0.5

            if length > 0.001:
                direction = (dx/length, dy/length, dz/length)

                brep = factory.create_box_brep_from_centerline(
                    start_point=(start.x, start.y, start.z),
                    direction=direction,
                    length=length,
                    width=element.profile.width,
                    depth=element.profile.depth
                )

                if brep:
                    breps.append(brep)

                    # Group by type
                    if element.element_type not in type_groups:
                        type_groups[element.element_type] = []
                    type_groups[element.element_type].append(brep)

                    # Create centerline
                    line = factory.create_line_curve(
                        (start.x, start.y, start.z),
                        (end.x, end.y, end.z)
                    )
                    if line:
                        centerlines.append(line)

                    metadata.append(element.id)

        # Build by_type DataTree
        for i, (elem_type, type_breps) in enumerate(type_groups.items()):
            path = GH_Path(i)
            for brep in type_breps:
                by_type.Add(brep, path)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

# Assign outputs
a = breps
b = by_type
c = centerlines
d = metadata
```

### Integration Points
```yaml
WALL_ANALYZER:
  - Calls: extract_wall_data_from_revit() from wall_data/revit_data_extractor.py
  - Outputs: JSON using core/json_schemas.py

CELL_DECOMPOSER:
  - Calls: decompose_wall_to_cells() from cell_decomposition/cell_segmentation.py
  - Outputs: JSON using core/json_schemas.py

FRAMING_GENERATOR:
  - Calls: get_framing_strategy(MaterialSystem.TIMBER) from core/material_system.py
  - NOTE: Phase 2 strategies return empty lists - this component will need update when strategies are fully implemented

GEOMETRY_CONVERTER:
  - Uses: RhinoCommonFactory from utils/geometry_factory.py
  - Handles: Assembly mismatch (Rhino3dmIO vs RhinoCommon)
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
# Run FIRST - fix errors before proceeding
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Syntax check all new files
python -c "import ast; ast.parse(open('scripts/gh_wall_analyzer.py').read())"
python -c "import ast; ast.parse(open('scripts/gh_cell_decomposer.py').read())"
python -c "import ast; ast.parse(open('scripts/gh_framing_generator.py').read())"
python -c "import ast; ast.parse(open('scripts/gh_geometry_converter.py').read())"

echo "All syntax checks passed!"
```

### Level 2: Grasshopper Integration Test
```
# Manual test in Grasshopper:

1. Open Revit 2024+ and launch Rhino.Inside.Revit
2. Open Grasshopper
3. Create 4 Python components connected in series:
   - Wall Analyzer → Cell Decomposer → Framing Generator → Geometry Converter

4. Connect inputs:
   - Wall Analyzer: walls=selected Revit walls, run=True
   - Material type: "timber"

5. Expected outcomes:
   - wall_json output shows valid JSON with wall data
   - cell_json output shows cells with u_start, u_end, etc.
   - elements_json shows framing elements (empty for Phase 2/3)
   - breps output shows valid geometry (if elements exist)

6. Connect JSON outputs to Panel components:
   - Should display readable JSON text
   - Can parse with jSwan for structured view
```

---

## Final Checklist

- [ ] All 4 GHPython scripts created in scripts/
- [ ] Syntax checks pass for all scripts
- [ ] Components can be loaded in GHPython nodes
- [ ] wall_json output is valid JSON
- [ ] cell_json output is valid JSON
- [ ] elements_json output is valid JSON
- [ ] JSON can be displayed in Panel component
- [ ] Geometry converter produces valid Breps (when elements exist)
- [ ] No breaking changes to existing gh-main.py

---

## Anti-Patterns to Avoid

- ❌ Don't create Rhino geometry before the geometry converter stage
- ❌ Don't serialize Rhino objects directly - extract coordinates first
- ❌ Don't skip the RhinoCommon setup at script start
- ❌ Don't forget to import materials module for strategy registration
- ❌ Don't use bare except - catch specific exceptions
- ❌ Don't hardcode paths - use consistent PROJECT_PATH variable

---

## Notes

- **Phase 3 Scope**: Components are created but framing generation returns empty (Phase 2 strategies are placeholders). Full integration happens when strategies are implemented.
- **Backward Compatibility**: `gh-main.py` continues to work - these are new parallel components.
- **Testing**: Until strategies generate elements, geometry converter will output empty lists.
- **Future Enhancement**: Phase 4 will implement CFS strategy, then both materials can use this pipeline.
