# Timber Framing Generator - Claude Code Instructions

## Project Overview

A Python-based tool that automates framing element generation from Revit wall data via Rhino.Inside.Revit. Supports **multiple material systems** (Timber and CFS) through a modular architecture with JSON-based inter-component communication.

**Key Technologies**: Python 3.9+, Grasshopper, Rhino.Inside.Revit, FastAPI, rhino3dm

**Architecture**: Modular GHPython components using Strategy Pattern for material selection

## Critical Gotchas

### 1. RhinoCommon vs Rhino3dmIO Assembly Mismatch (MUST READ)

**Problem**: The `rhino3dm` Python package creates geometry from the **Rhino3dmIO** assembly, but Grasshopper expects geometry from the **RhinoCommon** assembly. Despite identical type names (`Rhino.Geometry.Brep`), they are incompatible at the CLR level.

**Symptom**: `"Data conversion failed from Goo to Brep"` errors in Grasshopper even though geometry appears valid.

**Solution**: Use `RhinoCommonFactory` class (in `scripts/gh-main.py`) which uses CLR reflection to create geometry from the correct assembly:
```python
# Extract coordinates as floats (launders through assembly boundary)
x, y, z = float(point.X), float(point.Y), float(point.Z)
# Create via RhinoCommon using Activator.CreateInstance
rc_point = rc_factory.create_point3d(x, y, z)
```

**Verify assembly**: `obj.GetType().Assembly.GetName().Name` should return `"RhinoCommon"`

**Full documentation**: `docs/ai/ai-geometry-assembly-solution.md`

### 2. UVW Coordinate System

All wall-relative positioning uses UVW coordinates:
- **U**: Along wall length (wall's XAxis direction)
- **V**: Vertical direction (wall's YAxis = World Z)
- **W**: Through wall thickness (wall's ZAxis = wall normal)

**Wall Base Plane**:
- `Origin`: Wall start point at base elevation
- `XAxis`: Along wall direction (U)
- `YAxis`: World Z up (V)
- `ZAxis`: Wall normal, perpendicular to face (W)

**Converting U-coordinate to World Position**:
```python
point_along_wall = base_plane.Origin + base_plane.XAxis * u_coordinate
world_point = rg.Point3d(point_along_wall.X, point_along_wall.Y, v_elevation)
```

**Documentation**: `docs/ai/ai-coordinate-system-reference.md`

### 3. Cell Types

Walls are decomposed into cells for framing:
- **WBC**: Wall Boundary Cell (entire wall)
- **OC**: Opening Cell (doors/windows)
- **SC**: Stud Cell (regions for standard studs)
- **SCC**: Sill Cripple Cell (below windows)
- **HCC**: Header Cripple Cell (above openings)

### 4. Material Strategy Pattern

The framing generator supports multiple material systems via the Strategy Pattern:

```python
from src.timber_framing_generator.core import get_framing_strategy, MaterialSystem
from src.timber_framing_generator.materials import timber, cfs  # Triggers registration

# Get material-specific strategy
strategy = get_framing_strategy(MaterialSystem.TIMBER)  # or MaterialSystem.CFS

# Generate framing (material-agnostic interface)
elements = strategy.generate_framing(wall_data, cell_data, config)
```

**Available Materials**:
- **TIMBER**: Standard lumber (2x4, 2x6, etc.)
- **CFS**: Cold-Formed Steel (350S162-54, 600T125-54, etc.)

**Key Files**:
- `src/timber_framing_generator/core/material_system.py` - FramingStrategy ABC
- `src/timber_framing_generator/materials/timber/` - Timber implementation
- `src/timber_framing_generator/materials/cfs/` - CFS implementation

### 5. Box Z-Direction Gotcha (Geometry Creation)

**Problem**: When creating `rg.Box(plane, x_interval, y_interval, z_interval)`, the box's Z direction is determined by the cross product of `plane.XAxis × plane.YAxis`.

**Common mistake**: Using wall's ZAxis (normal) as the plane's Y axis results in the box Z pointing DOWN.

**Solution for upward extrusion**:
```python
# For vertical elements that should extrude UP
box_plane = rg.Plane(
    start_point,
    base_plane.XAxis,       # X = along wall
    rg.Vector3d(0, 0, 1)    # Y = World Z (vertical)
)
# Now box Z = XAxis × WorldZ = points into wall (correct)
# Y interval controls height (extrudes UP)
```

### 6. Normalized Parameters vs Absolute Coordinates

**Problem**: `Curve.ClosestPoint()` returns a **normalized parameter** (0-1), not an absolute distance.

**Common mistake**:
```python
# WRONG: t is 0-1, not feet!
success, t = curve.ClosestPoint(point)
start_u = t - half_width  # Produces nonsense like -1.2
```

**Solution**:
```python
success, t = curve.ClosestPoint(point)
curve_length = curve.GetLength()
absolute_position = t * curve_length  # Convert to absolute
start_u = absolute_position - half_width
```

### 7. Division by Zero in Spacing Calculations

**Problem**: When wall length < stud spacing, `int(length / spacing)` returns 0, causing division by zero.

**Solution**: Always handle edge cases:
```python
# Guard against division by zero
if num_studs == 0:
    # Place single stud at center or handle specially
    return [cell_width / 2]

# Safe division
actual_spacing = cell_width / num_studs  # Only if num_studs > 0
```

## Framing Domain Knowledge

### Lumber Profile Orientation

For vertical elements (studs, king studs, trimmers, cripples):
- **Width (1.5")**: Visible edge along wall face - what you see from exterior
- **Depth (3.5")**: Wall thickness direction - runs through wall

This is **standard residential framing convention**: narrow edge faces out.

### Critical Framing Rules

| Rule | Implementation |
|------|---------------|
| Every wall needs end studs | Place at `u=half_stud_width` and `u=wall_length-half_stud_width` |
| Bottom plates split at doors | Don't run through door openings |
| Header cripples go UP | From header top to bottom of top plate |
| Sill cripples go DOWN | From bottom plate top to sill bottom |
| King studs at openings | At opening's u_start and u_end boundaries |
| Trimmers inside king studs | Support header, inside of king studs |

### Standard Dimensions

- Stud spacing: 16" OC (1.333 ft) or 24" OC
- 2x4 actual: 1.5" × 3.5" (0.125' × 0.292')
- 2x6 actual: 1.5" × 5.5" (0.125' × 0.458')
- Plate thickness: 1.5" (0.125')

## Project Structure

```
src/timber_framing_generator/
├── core/                   # Core abstractions (Strategy, JSON schemas)
│   ├── material_system.py  # FramingStrategy ABC, ElementType enum
│   └── json_schemas.py     # WallData, CellData, FramingResults
├── materials/              # Material-specific implementations
│   ├── timber/             # Timber strategy and profiles
│   └── cfs/                # CFS strategy and profiles
├── cell_decomposition/     # Wall → cell decomposition
├── framing_elements/       # Element generators (studs, plates, headers)
├── wall_data/              # Revit data extraction
├── utils/                  # Helpers, geometry_factory
└── config/                 # Configuration settings

scripts/
├── gh-main.py              # Legacy monolithic Grasshopper script
├── gh_wall_analyzer.py     # Component 1: Revit → walls_json
├── gh_panel_decomposer.py  # Component 2: walls_json → panels_json (optional)
├── gh_cell_decomposer.py   # Component 3: walls_json + panels_json → cell_json
├── gh_framing_generator.py # Component 4: cell_json → framing_json
└── gh_geometry_converter.py# Component 5: framing_json → Breps

docs/ai/                    # AI-friendly documentation (READ THESE)
tests/                      # Unit and integration tests
PRPs/                       # Product Requirements Prompts
api/                        # FastAPI endpoints
```

## AI Documentation Files

Before making changes, read relevant docs in `docs/ai/`:

| File | When to Read |
|------|--------------|
| `ai-modular-architecture-plan.md` | **START HERE** - Complete architecture overview |
| `ai-architecture-document.md` | Understanding overall system |
| `ai-geometry-assembly-solution.md` | Working with Grasshopper outputs |
| `ai-coordinate-system-reference.md` | Positioning framing elements |
| `ai-blocking-system.md` | Row blocking implementation |
| `ai-grasshopper-rhino-patterns.md` | GH/CPython/CLR patterns |
| `ai-development-guidelines.md` | Code standards |

## Common Commands

```bash
# Install dependencies
uv pip install -e .

# Run tests
pytest tests/ -v

# Run API server (standalone mode)
python -m uvicorn api.main:app --reload

# Lint code
ruff check src/

# Type check
mypy src/
```

## Grasshopper Development

**Rhino 8 uses CPython 3** (not IronPython). This affects module imports, reloading, and some .NET interop patterns.

### CRITICAL: Before Writing ANY GHPython Script

**YOU MUST read the grasshopper-python-assistant skill EVERY TIME before writing or modifying any GHPython script.**

Location: `~/.claude/skills/grasshopper-python-assistant/`

**Required reading before ANY GH work:**
1. `SKILL.md` - Overview and quick reference
2. `templates/ghpython_component.py` - **MANDATORY template structure**
3. `templates/module_docstring.md` - **MANDATORY docstring format**
4. `references/common_patterns.md` - DataTrees, JSON, assembly patterns

**MANDATORY requirements for ALL GHPython components:**

1. **Follow the template structure exactly** - Every component MUST have:
   - Module docstring following `templates/module_docstring.md` format
   - `setup_component()` function that configures:
     - Component metadata (Name, NickName, Message, Category, SubCategory)
     - Input parameters with Name, NickName, Description, Access
     - Output parameters with Name, NickName, Description (starting from index 1)
   - `validate_inputs()` function
   - `main()` function as entry point
   - Execution block with `if __name__ == "__main__":`

2. **Use RhinoCommonFactory for ALL geometry output** (points, vectors, curves, breps)
   ```python
   from src.timber_framing_generator.utils.geometry_factory import get_factory
   factory = get_factory()
   pt = factory.create_point3d(x, y, z)  # NOT rg.Point3d(x, y, z)
   vec = factory.create_vector3d(x, y, z)  # NOT rg.Vector3d(x, y, z)
   curve = factory.create_polyline_curve(points)  # NOT rg.Polyline
   ```

3. **Match input/output names with existing components** - Check existing component outputs before defining inputs

4. **Type Hints must be set via Grasshopper UI, NOT programmatically**:
   - In Rhino 8, TypeHints CANNOT be set from within a GHPython script
   - They must be configured manually: Right-click input → Type hint → Select type
   - To read current type hint: `param.Converter.TypeName` (not `param.TypeHint`)
   - Configure parameters in `setup_component()` (without TypeHint):
   ```python
   inputs = ghenv.Component.Params.Input
   for i, (name, nick, desc, access) in enumerate(input_config):
       if i < inputs.Count:
           inputs[i].Name = name
           inputs[i].NickName = nick
           inputs[i].Description = desc
           inputs[i].Access = access
   ```

When modifying GHPython scripts:

1. **Test in Grasshopper** - Load the GH definition, select a test wall, toggle run/reload
2. **Check diagnostic outputs** - `test_clr_box`, `test_info` verify assembly compatibility
3. **Use DataTree for grafted outputs** - One wall can have multiple elements
4. **Always convert geometry** - Use RhinoCommonFactory methods, NOT direct rg.* constructors

### Force Module Reload (Without Restarting Rhino)

CPython caches imported modules. To force reload during development, add this near the top of your GHPython component:

```python
import sys

# Clear all project modules from cache (forces fresh import)
for mod_name in list(sys.modules.keys()):
    if 'timber_framing_generator' in mod_name:
        del sys.modules[mod_name]
```

Or reload a specific module:

```python
import importlib
import src.timber_framing_generator.framing_elements.studs as studs_module
importlib.reload(studs_module)
```

**Remove reload code after debugging** - it adds overhead to each run.

See `docs/ai/ai-grasshopper-rhino-patterns.md` for detailed patterns.

### Grasshopper Data Structures

| Python Structure | Grasshopper Result |
|-----------------|-------------------|
| `[a, b, c]` (flat list) | Flattened: all items in branch {0} |
| `[[a, b], [c, d]]` (nested) | Grafted: branch {0}=[a,b], branch {1}=[c,d] |
| `DataTree[object]()` | Full control over branch structure |

### JSON Communication Layer

Components communicate via JSON strings:
```
Wall Analyzer → walls_json → Panel Decomposer → panels_json → Cell Decomposer → cell_json → Framing Generator → framing_json → Geometry Converter → Breps
```

**Standard JSON variable names** (use these consistently):
- `walls_json` - Wall geometry from Wall Analyzer
- `panels_json` - Panel decomposition from Panel Decomposer
- `cell_json` - Cell decomposition from Cell Decomposer
- `framing_json` - Framing elements from Framing Generator

Benefits:
- Inspect data between components (jSwan, Panel)
- Decoupled, testable components
- Geometry as coordinates (no assembly issues until final stage)

## Current Focus Areas

**Completed**:
1. ✅ **Modularization**: Four JSON-based GHPython components
2. ✅ **Multi-Material Support**: Timber and CFS strategies with profile catalogs
3. ✅ **Geometry Pipeline**: RhinoCommonFactory handles assembly mismatch
4. ✅ **Framing Fixes**: Vertical element orientation, header cripple direction, bottom plate door splits, end studs on all walls

**Next Steps**:
- Implement CFS-specific elements (web stiffeners, bridging)
- Full pipeline integration testing in Grasshopper
- Documentation polish

See `PRPs/` folder for implementation documentation and `docs/ai/ai-modular-architecture-plan.md` for architecture details.

## Testing Patterns

```python
# Unit tests don't require Rhino environment
def test_cell_decomposition():
    wall_data = create_mock_wall_data()
    cells = decompose_wall(wall_data)
    assert len(cells) > 0

# Integration tests may need rhinoinside
@pytest.mark.integration
def test_full_pipeline():
    # Requires Rhino environment
    pass
```

## Debugging Strategies

### Logging Levels
- `DEBUG`: Variable values, intermediate states
- `INFO`: Start/end of operations, counts
- `WARNING`: Recoverable issues, fallbacks
- `ERROR`: Fatal errors with traceback

### Visual Debugging
- Output intermediate geometry for inspection
- Use color-coding by element type
- Check bounding boxes for dimension verification

### Log Analysis
- Review log files in `logs/` directory
- Check stud counts match expectations
- Verify elevations and dimensions

## Commit Message Format

```
component: Brief description

Detailed explanation of changes.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Available Skills

### grasshopper-python-assistant
Located at: `~/.claude/skills/grasshopper-python-assistant/`

Use this skill when:
- Creating new GHPython components
- Adding documentation to GH Python code
- Implementing error handling in GH components
- Working with DataTrees and Grasshopper data structures

The skill provides:
- **templates/ghpython_component.py**: Full component template with setup, logging, error handling
- **templates/module_docstring.md**: Module-level documentation template
- **templates/function_docstring.md**: Function docstring template
- **references/common_patterns.md**: DataTree, module reload, JSON, assembly patterns
- **references/error_handling.md**: Dual logging, graceful degradation, safe wrappers
- **references/performance_guidelines.md**: Performance documentation standards

## Do NOT

- Modify geometry creation without understanding assembly mismatch
- Skip coordinate system transformations (UVW ↔ World)
- Create new patterns when existing ones work
- Commit .env files or credentials
- Use bare `except:` clauses
- Assume `ClosestPoint()` returns absolute distance (it's normalized 0-1)
- Forget end studs on short walls
- Create boxes without verifying Z-direction
- Write GHPython scripts without reading the grasshopper-python-assistant skill first
- Use `rg.Point3d()`, `rg.Vector3d()`, etc. directly in GH components - use RhinoCommonFactory
- Define component inputs/outputs without checking existing component interfaces
