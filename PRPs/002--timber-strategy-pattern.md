# PRP: Timber Strategy Pattern Implementation (Phase 2)

> **Version:** 1.0
> **Created:** 2026-01-21
> **Status:** Ready
> **Branch:** feature/phase2-timber-strategy

---

## Goal
Implement `TimberFramingStrategy` that wraps the existing timber framing generation logic, conforming to the `FramingStrategy` abstract base class defined in Phase 1. This enables multi-material support while preserving all existing functionality.

## Why
- **Multi-Material Architecture**: Foundation for supporting both Timber and CFS framing
- **Strategy Pattern**: Allows swapping material implementations without changing core pipeline
- **Backward Compatibility**: Existing framing logic is wrapped, not rewritten
- **Testability**: Strategy can be unit tested independently of GH/Rhino environment

## What
Create `materials/timber/` module with:
1. `timber_profiles.py` - Standard lumber profiles (2x4, 2x6, etc.)
2. `timber_strategy.py` - `TimberFramingStrategy` implementing `FramingStrategy` ABC

### Success Criteria
- [ ] `TimberFramingStrategy` implements all abstract methods from `FramingStrategy`
- [ ] Strategy can be retrieved via `get_framing_strategy(MaterialSystem.TIMBER)`
- [ ] All existing framing element types are mapped to `ElementType` enum
- [ ] Lumber profiles are defined using `ElementProfile` dataclass
- [ ] Unit tests pass for strategy instantiation and profile lookup
- [ ] Syntax check passes: `python -c "import ast; ast.parse(open('file.py').read())"`

---

## All Needed Context

### Documentation & References
```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-modular-architecture-plan.md
    why: Overall modularization plan and Phase 2 requirements

  - file: docs/ai/ai-architecture-document.md
    why: Existing pipeline: wall data → cell decomposition → framing

  - file: CLAUDE.md
    why: Project conventions and critical gotchas

Core Abstractions (Phase 1):
  - file: src/timber_framing_generator/core/material_system.py
    why: FramingStrategy ABC, ElementType enum, ElementProfile dataclass
    key_classes:
      - FramingStrategy (ABC to implement)
      - MaterialSystem (enum: TIMBER, CFS)
      - ElementType (enum for all element types)
      - ElementProfile (dataclass for profiles)
      - FramingElement (dataclass for elements)
      - register_strategy() (function to register)

  - file: src/timber_framing_generator/core/__init__.py
    why: Exports to use in imports

Existing Framing Logic:
  - file: src/timber_framing_generator/framing_elements/framing_generator.py
    why: Current FramingGenerator class to delegate to
    key_methods:
      - _generate_plates()
      - _generate_king_studs()
      - _generate_headers_and_sills()
      - _generate_trimmers()
      - _generate_header_cripples()
      - _generate_sill_cripples()
      - _generate_studs()
      - _generate_row_blocking()

  - file: src/timber_framing_generator/config/framing.py
    why: Existing PROFILES dict, FRAMING_PARAMS, ProfileDimensions class
```

### Current Codebase Structure
```
src/timber_framing_generator/
├── core/                           # ✅ Phase 1 (done)
│   ├── __init__.py
│   ├── material_system.py          # FramingStrategy ABC
│   └── json_schemas.py             # JSON serialization
│
├── materials/                      # 🔄 Phase 2 (this PRP)
│   └── timber/
│       ├── __init__.py             # CREATE
│       ├── timber_profiles.py      # CREATE
│       └── timber_strategy.py      # CREATE
│
├── config/
│   └── framing.py                  # REFERENCE (PROFILES, FRAMING_PARAMS)
│
├── framing_elements/
│   └── framing_generator.py        # DELEGATE TO (existing logic)
```

### Desired Structure (files to add)
```bash
src/timber_framing_generator/
├── materials/                      # NEW directory
│   ├── __init__.py                 # Package init, export materials
│   └── timber/
│       ├── __init__.py             # Export TimberFramingStrategy
│       ├── timber_profiles.py      # TIMBER_PROFILES dict using ElementProfile
│       └── timber_strategy.py      # TimberFramingStrategy class
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: Strategy Registration
# - Call register_strategy() at module import time
# - This allows get_framing_strategy(MaterialSystem.TIMBER) to work
# - Import materials module in __init__.py to trigger registration

# CRITICAL: ElementType Mapping
# Existing framing elements → ElementType enum:
#   "bottom_plates" → ElementType.BOTTOM_PLATE
#   "top_plates" → ElementType.TOP_PLATE
#   "studs" → ElementType.STUD
#   "king_studs" → ElementType.KING_STUD
#   "trimmers" → ElementType.TRIMMER
#   "headers" → ElementType.HEADER
#   "sills" → ElementType.SILL
#   "header_cripples" → ElementType.HEADER_CRIPPLE
#   "sill_cripples" → ElementType.SILL_CRIPPLE
#   "row_blocking" → ElementType.ROW_BLOCKING

# CRITICAL: Profile Convention
# - Existing: ProfileDimensions(thickness=1.5/12, width=3.5/12, ...)
# - New: ElementProfile(name="2x4", width=1.5/12, depth=3.5/12, ...)
# - width = through wall (W direction)
# - depth = along wall face (U direction for studs)

# CRITICAL: Units
# - All dimensions in FEET internally
# - 2x4: 1.5" x 3.5" = 0.125' x 0.292'
# - 2x6: 1.5" x 5.5" = 0.125' x 0.458'
```

---

## Implementation Blueprint

### Data Models

```python
# From core/material_system.py (already exists):
@dataclass
class ElementProfile:
    name: str
    width: float   # W direction (wall thickness)
    depth: float   # U direction (along wall face)
    material_system: MaterialSystem
    properties: Dict[str, Any] = field(default_factory=dict)
```

### Tasks (in execution order)

```yaml
Task 1: Create materials package structure
  - CREATE: src/timber_framing_generator/materials/__init__.py
  - CREATE: src/timber_framing_generator/materials/timber/__init__.py
  - PURPOSE: Package initialization and exports

Task 2: Create timber_profiles.py
  - CREATE: src/timber_framing_generator/materials/timber/timber_profiles.py
  - DEFINE: TIMBER_PROFILES dict with standard lumber sizes
  - PATTERN: Use ElementProfile from core.material_system
  - INCLUDE: 2x4, 2x6, 2x8, 2x10, 2x12

Task 3: Create timber_strategy.py
  - CREATE: src/timber_framing_generator/materials/timber/timber_strategy.py
  - IMPLEMENT: TimberFramingStrategy(FramingStrategy)
  - DELEGATE: To existing FramingGenerator for actual generation
  - REGISTER: Call register_strategy() at module load

Task 4: Update core __init__ to import materials
  - MODIFY: src/timber_framing_generator/__init__.py (if exists)
  - OR: Ensure materials is importable

Task 5: Write unit tests
  - CREATE: tests/unit/test_timber_strategy.py
  - TEST: Strategy instantiation, profile lookup, element type listing
```

### Pseudocode (with CRITICAL details)

```python
# Task 2: timber_profiles.py
# File: src/timber_framing_generator/materials/timber/timber_profiles.py

from src.timber_framing_generator.core import (
    MaterialSystem, ElementProfile, ElementType
)

# Standard lumber profiles (dimensions in FEET)
# width = through wall thickness (W direction)
# depth = along wall face (U direction for studs)
TIMBER_PROFILES: Dict[str, ElementProfile] = {
    "2x4": ElementProfile(
        name="2x4",
        width=1.5 / 12,    # 1.5 inches in feet
        depth=3.5 / 12,    # 3.5 inches in feet
        material_system=MaterialSystem.TIMBER,
        properties={"nominal": "2x4", "actual_inches": (1.5, 3.5)}
    ),
    "2x6": ElementProfile(
        name="2x6",
        width=1.5 / 12,
        depth=5.5 / 12,
        material_system=MaterialSystem.TIMBER,
        properties={"nominal": "2x6", "actual_inches": (1.5, 5.5)}
    ),
    # ... more profiles
}

# Default profile assignments for element types
DEFAULT_TIMBER_PROFILES: Dict[ElementType, str] = {
    ElementType.BOTTOM_PLATE: "2x4",
    ElementType.TOP_PLATE: "2x4",
    ElementType.STUD: "2x4",
    ElementType.KING_STUD: "2x4",
    ElementType.TRIMMER: "2x4",
    ElementType.HEADER: "2x6",  # Headers often larger
    ElementType.SILL: "2x4",
    ElementType.HEADER_CRIPPLE: "2x4",
    ElementType.SILL_CRIPPLE: "2x4",
    ElementType.ROW_BLOCKING: "2x4",
}

def get_timber_profile(element_type: ElementType) -> ElementProfile:
    """Get the default profile for an element type."""
    profile_name = DEFAULT_TIMBER_PROFILES.get(element_type, "2x4")
    return TIMBER_PROFILES[profile_name]
```

```python
# Task 3: timber_strategy.py
# File: src/timber_framing_generator/materials/timber/timber_strategy.py

from typing import Dict, List, Any
from src.timber_framing_generator.core import (
    MaterialSystem, FramingStrategy, ElementType, ElementProfile,
    FramingElement, register_strategy
)
from .timber_profiles import TIMBER_PROFILES, DEFAULT_TIMBER_PROFILES, get_timber_profile


class TimberFramingStrategy(FramingStrategy):
    """
    Timber framing strategy implementing the FramingStrategy interface.

    This wraps the existing FramingGenerator logic while conforming
    to the new material-agnostic interface.
    """

    @property
    def material_system(self) -> MaterialSystem:
        return MaterialSystem.TIMBER

    @property
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        """Return default profiles for each element type."""
        return {
            element_type: TIMBER_PROFILES[profile_name]
            for element_type, profile_name in DEFAULT_TIMBER_PROFILES.items()
        }

    def get_generation_sequence(self) -> List[ElementType]:
        """Timber generation order: plates → king studs → headers/sills → etc."""
        return [
            ElementType.BOTTOM_PLATE,
            ElementType.TOP_PLATE,
            ElementType.KING_STUD,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.TRIMMER,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.STUD,
            ElementType.ROW_BLOCKING,
        ]

    def get_element_types(self) -> List[ElementType]:
        """All element types used in timber framing."""
        return list(DEFAULT_TIMBER_PROFILES.keys())

    def create_horizontal_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """Generate plates using existing logic."""
        # PHASE 2: Returns empty list - actual integration in Phase 3
        # This is a placeholder that allows the strategy to be registered
        # Full integration will delegate to existing FramingGenerator
        return []

    def create_vertical_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        horizontal_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """Generate studs, king studs, trimmers using existing logic."""
        # PHASE 2: Placeholder
        return []

    def create_opening_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """Generate headers, sills, cripples using existing logic."""
        # PHASE 2: Placeholder
        return []

    def create_bracing_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """Generate row blocking using existing logic."""
        # PHASE 2: Placeholder
        return []


# Register the strategy when this module is imported
register_strategy(TimberFramingStrategy())
```

### Integration Points
```yaml
REGISTRATION:
  - file: src/timber_framing_generator/materials/timber/timber_strategy.py
  - pattern: "register_strategy(TimberFramingStrategy())" at module level
  - effect: Enables get_framing_strategy(MaterialSystem.TIMBER)

IMPORTS:
  - file: src/timber_framing_generator/materials/__init__.py
  - pattern: "from .timber import TimberFramingStrategy"
  - effect: Makes strategy available at package level

FUTURE INTEGRATION (Phase 3):
  - file: scripts/gh_framing_generator.py
  - pattern: "strategy = get_framing_strategy(MaterialSystem.TIMBER)"
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
# Run FIRST - fix errors before proceeding
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Syntax check all new files
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/__init__.py').read())"
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/timber/__init__.py').read())"
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/timber/timber_profiles.py').read())"
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/timber/timber_strategy.py').read())"

echo "All syntax checks passed!"
```

### Level 2: Unit Tests
```python
# tests/unit/test_timber_strategy.py
import pytest
from src.timber_framing_generator.core import (
    MaterialSystem, ElementType, get_framing_strategy, list_available_materials
)
from src.timber_framing_generator.materials.timber import TimberFramingStrategy
from src.timber_framing_generator.materials.timber.timber_profiles import (
    TIMBER_PROFILES, get_timber_profile
)


class TestTimberProfiles:
    """Test timber profile definitions."""

    def test_profiles_exist(self):
        """Standard lumber profiles are defined."""
        assert "2x4" in TIMBER_PROFILES
        assert "2x6" in TIMBER_PROFILES

    def test_profile_dimensions(self):
        """Profile dimensions are in feet and reasonable."""
        profile = TIMBER_PROFILES["2x4"]
        assert profile.width == pytest.approx(1.5 / 12, rel=0.01)
        assert profile.depth == pytest.approx(3.5 / 12, rel=0.01)
        assert profile.material_system == MaterialSystem.TIMBER

    def test_get_timber_profile(self):
        """Can get profile by element type."""
        profile = get_timber_profile(ElementType.STUD)
        assert profile.name == "2x4"


class TestTimberStrategy:
    """Test TimberFramingStrategy implementation."""

    def test_strategy_instantiation(self):
        """Strategy can be instantiated."""
        strategy = TimberFramingStrategy()
        assert strategy.material_system == MaterialSystem.TIMBER

    def test_strategy_registration(self):
        """Strategy is registered and retrievable."""
        # Import triggers registration
        from src.timber_framing_generator.materials.timber import timber_strategy

        available = list_available_materials()
        assert MaterialSystem.TIMBER in available

        strategy = get_framing_strategy(MaterialSystem.TIMBER)
        assert isinstance(strategy, TimberFramingStrategy)

    def test_generation_sequence(self):
        """Generation sequence includes all expected types."""
        strategy = TimberFramingStrategy()
        sequence = strategy.get_generation_sequence()

        assert ElementType.BOTTOM_PLATE in sequence
        assert ElementType.TOP_PLATE in sequence
        assert ElementType.STUD in sequence
        # Plates should come before studs
        assert sequence.index(ElementType.BOTTOM_PLATE) < sequence.index(ElementType.STUD)

    def test_default_profiles(self):
        """Default profiles are assigned for all element types."""
        strategy = TimberFramingStrategy()
        profiles = strategy.default_profiles

        assert ElementType.STUD in profiles
        assert profiles[ElementType.STUD].material_system == MaterialSystem.TIMBER

    def test_element_types(self):
        """Element types list is complete."""
        strategy = TimberFramingStrategy()
        types = strategy.get_element_types()

        # All timber element types should be present
        expected = [
            ElementType.BOTTOM_PLATE, ElementType.TOP_PLATE,
            ElementType.STUD, ElementType.KING_STUD, ElementType.TRIMMER,
            ElementType.HEADER, ElementType.SILL,
            ElementType.HEADER_CRIPPLE, ElementType.SILL_CRIPPLE,
            ElementType.ROW_BLOCKING
        ]
        for et in expected:
            assert et in types
```

```bash
# Run tests
python -m pytest tests/unit/test_timber_strategy.py -v

# Run all tests to ensure no regressions
python -m pytest tests/ -v --ignore=tests/api/
```

---

## Final Checklist

- [ ] `materials/` package structure created
- [ ] `timber_profiles.py` defines TIMBER_PROFILES with 2x4, 2x6, etc.
- [ ] `timber_strategy.py` implements all FramingStrategy abstract methods
- [ ] `register_strategy()` is called at module import
- [ ] `get_framing_strategy(MaterialSystem.TIMBER)` returns TimberFramingStrategy
- [ ] All syntax checks pass
- [ ] Unit tests pass: `pytest tests/unit/test_timber_strategy.py -v`
- [ ] No breaking changes to existing code

---

## Anti-Patterns to Avoid

- ❌ Don't duplicate existing framing logic - wrap/delegate instead
- ❌ Don't forget to call `register_strategy()` at module level
- ❌ Don't mix inches and feet - all internal dimensions in FEET
- ❌ Don't create dependencies on Rhino/Grasshopper in strategy (keep testable)
- ❌ Don't implement full generation logic yet - Phase 2 is structure only
- ❌ Don't modify existing `FramingGenerator` class yet

---

## Notes

- **Phase 2 Scope**: This phase creates the structure and registration. The strategy methods return empty lists as placeholders.
- **Phase 3 Integration**: The actual delegation to `FramingGenerator` happens in Phase 3 when we create the modular GHPython components.
- **Backward Compatibility**: The existing `gh-main.py` continues to work unchanged - this is additive.
- **Testing Without Rhino**: Unit tests can run without Rhino environment since the strategy doesn't create geometry directly.
