# Timber Framing Generator - Claude Code Instructions

## Project Overview

A Python-based tool that automates timber framing element generation from Revit wall data via Rhino.Inside.Revit. Supports both standalone API mode and Grasshopper visual programming mode.

**Key Technologies**: Python 3.9+, Grasshopper, Rhino.Inside.Revit, FastAPI, rhino3dm

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

## Project Structure

```
src/timber_framing_generator/
├── cell_decomposition/     # Wall → cell decomposition
├── framing_elements/       # Element generators (studs, plates, headers)
├── wall_data/              # Revit data extraction
├── utils/                  # Helpers, serialization, logging
└── config/                 # Configuration settings

scripts/
├── gh-main.py              # Main Grasshopper integration script
└── *.py                    # Other utility scripts

docs/ai/                    # AI-friendly documentation (READ THESE)
tests/                      # Unit and integration tests
api/                        # FastAPI endpoints
```

## AI Documentation Files

Before making changes, read relevant docs in `docs/ai/`:

| File | When to Read |
|------|--------------|
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

1. **Modularization**: Breaking monolithic `gh-main.py` into JSON-based GHPython components
2. **Multi-Material Support**: Adding Cold-Formed Steel (CFS) alongside Timber
3. **Geometry Pipeline**: Reliable RhinoCommon geometry output

See `PRPs/` folder for active implementation plans.

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
