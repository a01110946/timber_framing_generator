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

**Full documentation**: `docs/ai/ai-geometry-assembly-solution.md`

### 2. UVW Coordinate System

All wall-relative positioning uses UVW coordinates:
- **U**: Along wall length (wall_base_curve direction)
- **V**: Vertical direction (height)
- **W**: Through wall thickness (normal to wall face)

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
├── gh_wall_analyzer.py     # Component 1: Revit → wall_json
├── gh_cell_decomposer.py   # Component 2: wall_json → cell_json
├── gh_framing_generator.py # Component 3: cell_json → elements_json
└── gh_geometry_converter.py# Component 4: elements_json → Breps

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

When modifying `scripts/gh-main.py`:

1. **Test in Grasshopper** - Load the GH definition, select a test wall, toggle run/reload
2. **Check diagnostic outputs** - `test_clr_box`, `test_info` verify assembly compatibility
3. **Use DataTree for grafted outputs** - One wall can have multiple elements
4. **Always convert geometry** - Use `rc_factory.convert_geometry_from_rhino3dm()` before output

See `docs/ai/ai-grasshopper-rhino-patterns.md` for detailed patterns.

## Current Focus Areas

**Completed**:
1. ✅ **Modularization**: Four JSON-based GHPython components (wall_analyzer, cell_decomposer, framing_generator, geometry_converter)
2. ✅ **Multi-Material Support**: Timber and CFS strategies with profile catalogs
3. ✅ **Geometry Pipeline**: RhinoCommonFactory handles assembly mismatch

**Next Steps**:
- Connect strategy methods to existing framing element generators
- Implement CFS-specific elements (web stiffeners, bridging)
- Full pipeline integration testing in Grasshopper

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

## Commit Message Format

```
component: Brief description

Detailed explanation of changes.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Do NOT

- Modify geometry creation without understanding assembly mismatch
- Skip coordinate system transformations (UVW ↔ World)
- Create new patterns when existing ones work
- Commit .env files or credentials
- Use bare `except:` clauses
