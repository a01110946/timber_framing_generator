# PRP: [Feature Name]

> **Version:** 1.0
> **Created:** [Date]
> **Status:** Draft | Ready | In Progress | Completed
> **Branch:** [branch-name]

---

## Goal
[What needs to be built - be specific about the end state]

## Why
- [Business value and user impact]
- [Integration with existing features]
- [Problems this solves and for whom]

## What
[User-visible behavior and technical requirements]

### Success Criteria
- [ ] [Specific measurable outcome 1]
- [ ] [Specific measurable outcome 2]
- [ ] [Specific measurable outcome 3]

---

## All Needed Context

### Documentation & References
```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-architecture-document.md
    why: Overall system architecture and component interactions

  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for wall-relative positioning

  - file: docs/ai/ai-development-guidelines.md
    why: Coding standards, type hints, docstrings format

  - file: docs/ai/ai-timber-framing-technical-stack.md
    why: Technology stack and integration details

Feature-Specific:
  - file: [path/to/relevant/module.py]
    why: [Pattern to follow, gotchas to avoid]

  - url: [Library documentation URL]
    why: [Specific sections/methods needed]
```

### Current Codebase Structure
```
src/timber_framing_generator/
├── __init__.py
├── cell_decomposition/          # Wall decomposition into cells
│   ├── cell_segmentation.py     # Decomposition algorithm
│   ├── cell_types.py            # Cell type definitions (WBC, OC, SC, SCC, HCC)
│   └── cell_visualizer.py       # Visualization helpers
├── config/                      # Configuration and parameters
│   ├── framing.py               # FRAMING_PARAMS, PROFILES
│   ├── assembly.py              # Wall assembly configurations
│   └── units.py                 # Unit conversion utilities
├── framing_elements/            # Framing component generators
│   ├── framing_generator.py     # Main orchestrator (FramingGenerator class)
│   ├── timber_element.py        # Base element creation
│   ├── plates.py                # Plate generation
│   ├── plate_geometry.py        # Plate geometry helpers
│   ├── studs.py                 # Stud generation
│   ├── king_studs.py            # King stud generation
│   ├── headers.py               # Header generation
│   ├── sills.py                 # Sill generation
│   ├── trimmers.py              # Trimmer generation
│   ├── header_cripples.py       # Header cripple studs
│   ├── sill_cripples.py         # Sill cripple studs
│   ├── row_blocking.py          # Row blocking generation
│   └── location_data.py         # Location information
├── utils/                       # Utility functions
│   ├── coordinate_systems.py    # UVW ↔ World transformations
│   ├── geometry_helpers.py      # Common geometry utilities
│   ├── safe_rhino.py            # Safe Rhino API wrappers
│   ├── logging_config.py        # Custom logging system
│   └── serialization.py         # Data serialization
├── wall_data/                   # Wall data extraction
│   ├── revit_data_extractor.py  # Extract from Revit
│   ├── wall_helpers.py          # Wall processing helpers
│   └── wall_selector.py         # Wall selection interface
└── dev_utils/                   # Development utilities
    └── reload_modules.py        # Module reloading for GH dev
```

### Desired Structure (files to add/modify)
```bash
# Show new/modified files with comments
src/timber_framing_generator/
├── [module]/
│   └── [file.py]      # [Description of changes]
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: Rhino.Geometry specifics
# - Extrusion.ToBrep() only works on actual Extrusion objects, not Breps
# - Box constructor requires (Plane, Interval, Interval, Interval), NOT 8 Point3d
# - Always check .IsValid before using geometry objects
# - Use safe_rhino.py wrappers for defensive geometry creation

# CRITICAL: Grasshopper integration
# - Outputs must be valid Rhino geometry or they show as null
# - Use ghpythonlib.treehelpers for DataTree conversion
# - Module reloading requires clearing sys.modules cache

# CRITICAL: Coordinate system
# - All framing uses UVW (wall-relative) coordinates
# - U = along wall length, V = vertical, W = through thickness
# - base_plane.PointAt(u, v, w) converts UVW to world coords

# CRITICAL: Units
# - All internal calculations in FEET
# - Lumber sizes: 2x4 = 1.5" x 3.5" = 0.125' x 0.292'
```

---

## Implementation Blueprint

### Data Models
```python
# Core data models if applicable
```

### Tasks (in execution order)
```yaml
Task 1: [Description]
  - MODIFY: src/timber_framing_generator/[module]/[file.py]
  - FIND pattern: "[existing code to locate]"
  - CHANGE: [what to change]
  - PRESERVE: [what must stay the same]

Task 2: [Description]
  - CREATE: src/timber_framing_generator/[module]/[file.py]
  - MIRROR pattern from: src/timber_framing_generator/[similar_file.py]
  - MODIFY: [specific changes]

Task N: Write tests
  - CREATE: tests/[module]/test_[feature].py
  - MIRROR pattern from: tests/conftest.py (fixture patterns)
```

### Pseudocode (with CRITICAL details)
```python
# Task 1: [Description]
def new_function(param: Type) -> ReturnType:
    """
    Docstring following Google style.

    Args:
        param: Description

    Returns:
        Description of return value
    """
    # PATTERN: Validate geometry first
    if not is_valid_geometry(param):
        logger.warning("Invalid geometry provided")
        return None

    # GOTCHA: Use safe wrappers for Rhino operations
    result = safe_create_extrusion(profile, direction)

    # PATTERN: Always check result validity
    if result is None or not result.IsValid:
        return None

    return result
```

### Integration Points
```yaml
CONFIG:
  - file: src/timber_framing_generator/config/framing.py
  - pattern: "Add new parameters to FRAMING_PARAMS dict"

IMPORTS:
  - file: src/timber_framing_generator/framing_elements/__init__.py
  - pattern: "Export new classes/functions"

GRASSHOPPER:
  - file: scripts/gh-main.py
  - pattern: "Import and use new functionality"
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
# Run FIRST - fix errors before proceeding
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Linting (using flake8 as configured in pyproject.toml)
python -m flake8 src/timber_framing_generator/[module]/ --max-line-length=88

# Type checking
python -m mypy src/timber_framing_generator/[module]/
```

### Level 2: Unit Tests
```python
# Test cases to create - follow existing patterns from tests/conftest.py
import pytest

def test_happy_path(wall_data):
    """Basic functionality works with valid input."""
    result = function_under_test(wall_data)
    assert result is not None
    assert result.IsValid  # For Rhino geometry

def test_invalid_input():
    """Invalid input returns None or raises appropriate error."""
    result = function_under_test(None)
    assert result is None

def test_edge_case():
    """Edge cases are handled correctly."""
    # Test with minimal/extreme values
```

```bash
# Run and iterate until passing
python -m pytest tests/[module]/test_[feature].py -v

# Run all tests
python -m pytest tests/ -v
```

### Level 3: Integration Test (Grasshopper)
```bash
# Manual test in Grasshopper:
# 1. Open Rhino with Grasshopper
# 2. Load the test Grasshopper definition
# 3. Connect to Revit via Rhino.Inside.Revit
# 4. Select test walls
# 5. Toggle 'run' to True
# 6. Verify outputs are not null
# 7. Check geometry in Rhino viewport

# Expected outcomes:
# - All geometry outputs show valid Brep objects
# - No error messages in Python output
# - Framing elements visible in viewport
```

---

## Final Checklist

- [ ] All unit tests pass: `python -m pytest tests/ -v`
- [ ] No linting errors: `python -m flake8 src/timber_framing_generator/`
- [ ] No type errors: `python -m mypy src/timber_framing_generator/`
- [ ] Grasshopper integration test successful (outputs not null)
- [ ] Error cases handled gracefully (return None, log warning)
- [ ] Logs are informative but not verbose
- [ ] Code follows project conventions (type hints, docstrings)
- [ ] No breaking changes to existing API

---

## Anti-Patterns to Avoid

- ❌ Don't call .ToBrep() on objects that are already Breps
- ❌ Don't use Rhino constructors without checking valid overloads
- ❌ Don't skip geometry validity checks
- ❌ Don't hardcode paths or values that should be config
- ❌ Don't ignore None returns from safe_* wrapper functions
- ❌ Don't create new patterns when existing ones work
- ❌ Don't catch all exceptions - be specific
- ❌ Don't skip the validation loop steps

---

## Notes

[Additional context, decisions made, or future considerations]
