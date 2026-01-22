# PRP: CFS Strategy Pattern (Phase 4)

> **Version:** 1.0
> **Created:** 2026-01-21
> **Status:** Ready
> **Branch:** feature/phase4-cfs-support

---

## Goal
Create CFS (Cold-Formed Steel) framing strategy and profiles that implement the FramingStrategy ABC, enabling steel stud framing as an alternative to timber.

## Why
- **Multi-Material Support**: Complete the strategy pattern implementation for a second material system
- **Industry Coverage**: CFS framing is common in commercial and multi-family construction
- **Code Validation**: Validates the material-agnostic architecture works for different material systems
- **Future Extensibility**: Demonstrates how to add new materials to the system

## What
Create CFS material modules:
1. `materials/cfs/__init__.py` - Package init with exports
2. `materials/cfs/cfs_profiles.py` - Steel stud profiles (C-sections, tracks)
3. `materials/cfs/cfs_strategy.py` - CFSFramingStrategy implementing FramingStrategy ABC
4. `tests/unit/test_cfs_strategy.py` - Unit tests for CFS profiles and strategy

### Success Criteria
- [ ] CFSFramingStrategy correctly implements FramingStrategy ABC
- [ ] CFS_PROFILES dict contains standard steel stud sizes (600S162-54, etc.)
- [ ] Strategy registers via `register_strategy()` at module import
- [ ] `get_framing_strategy(MaterialSystem.CFS)` returns CFSFramingStrategy
- [ ] CFS generation sequence matches steel stud assembly order
- [ ] All unit tests pass
- [ ] Syntax check passes for all new files

---

## All Needed Context

### Documentation & References
```yaml
# MUST READ - Include these in your context window
Core Architecture:
  - file: src/timber_framing_generator/core/material_system.py
    why: FramingStrategy ABC, MaterialSystem enum, register_strategy()

  - file: docs/ai/ai-modular-architecture-plan.md
    why: CFS vs Timber differences, architecture overview

Reference Implementation:
  - file: src/timber_framing_generator/materials/timber/timber_profiles.py
    why: Pattern for profile definitions

  - file: src/timber_framing_generator/materials/timber/timber_strategy.py
    why: Pattern for strategy implementation

Existing Tests:
  - file: tests/unit/test_timber_strategy.py
    why: Test patterns to follow
```

### CFS vs Timber Key Differences

| Aspect | Timber | CFS |
|--------|--------|-----|
| Horizontal members | Plates (2x4, 2x6) | Tracks (C-section, no lips) |
| Vertical members | Studs (2x4, 2x6) | Studs (C-section with lips) |
| Profile shape | Rectangular | C-section |
| Naming convention | 2x4, 2x6 | 600S162-54 (depth-S-flange-gauge) |
| Additional elements | Blocking | Web stiffeners, bridging |
| Load transfer | Direct bearing | Through flanges |

### CFS Profile Naming Convention
```
600S162-54
│   │   │
│   │   └── Gauge (54 mil = 0.054")
│   └────── Flange width (1.62")
└────────── Web depth (6.00")

S = Stud (with lips)
T = Track (no lips)
```

### Standard CFS Profiles
```
Studs (with lips):
  - 350S162-33  (3.5" web, 1.62" flange, 33 mil)
  - 350S162-54  (3.5" web, 1.62" flange, 54 mil)
  - 600S162-33  (6.0" web, 1.62" flange, 33 mil)
  - 600S162-54  (6.0" web, 1.62" flange, 54 mil)
  - 800S162-54  (8.0" web, 1.62" flange, 54 mil)

Tracks (no lips):
  - 350T125-33  (3.5" web, 1.25" flange, 33 mil)
  - 350T125-54  (3.5" web, 1.25" flange, 54 mil)
  - 600T125-33  (6.0" web, 1.25" flange, 33 mil)
  - 600T125-54  (6.0" web, 1.25" flange, 54 mil)
```

### Known Gotchas
```python
# CRITICAL: Strategy Registration
# - Must call register_strategy() at module level
# - Import triggers registration: from materials import cfs  # noqa: F401

# CRITICAL: Profile Dimensions
# - All dimensions in FEET (consistent with timber)
# - width = through wall thickness (flange + lip for studs)
# - depth = web depth (similar to plate depth in timber)

# CRITICAL: CFS-Specific ElementTypes
# - CFS uses TRACK instead of plates but maps to same ElementType
# - WEB_STIFFENER and BRIDGING may need future ElementType additions
```

---

## Implementation Blueprint

### Tasks (in execution order)

```yaml
Task 1: Create cfs/__init__.py
  - CREATE: src/timber_framing_generator/materials/cfs/__init__.py
  - PURPOSE: Package initialization with strategy import trigger
  - PATTERN: Copy from timber/__init__.py

Task 2: Create cfs_profiles.py
  - CREATE: src/timber_framing_generator/materials/cfs/cfs_profiles.py
  - PURPOSE: Define standard CFS profiles (studs and tracks)
  - CONTENT:
    - CFS_PROFILES dict with standard sizes
    - DEFAULT_CFS_PROFILES mapping ElementType to profile name
    - get_cfs_profile() helper function
    - list_available_profiles() function

Task 3: Create cfs_strategy.py
  - CREATE: src/timber_framing_generator/materials/cfs/cfs_strategy.py
  - PURPOSE: CFSFramingStrategy implementing FramingStrategy ABC
  - METHODS:
    - material_system property → MaterialSystem.CFS
    - default_profiles property → returns CFS profiles
    - get_generation_sequence() → CFS assembly order
    - get_element_types() → CFS element types
    - get_profile() → profile lookup with config override
    - create_horizontal_members() → placeholder (returns [])
    - create_vertical_members() → placeholder (returns [])
    - create_opening_members() → placeholder (returns [])
    - create_bracing_members() → placeholder (returns [])
  - REGISTER: Call register_strategy() at module level

Task 4: Update materials/__init__.py
  - MODIFY: src/timber_framing_generator/materials/__init__.py
  - ADD: Import cfs module for strategy registration

Task 5: Create unit tests
  - CREATE: tests/unit/test_cfs_strategy.py
  - CONTENT:
    - Test CFS profile definitions (dimensions, names)
    - Test DEFAULT_CFS_PROFILES mapping
    - Test get_cfs_profile() function
    - Test CFSFramingStrategy properties
    - Test strategy registration
    - Test get_framing_strategy(MaterialSystem.CFS)
    - Test generation sequence
```

### Pseudocode

```python
# Task 2: cfs_profiles.py
# ============================================================================

CFS_PROFILES: Dict[str, ElementProfile] = {
    # Studs (with lips) - C-section profile
    "350S162-54": ElementProfile(
        name="350S162-54",
        width=1.62 / 12,     # Flange width: 1.62" = 0.135 feet
        depth=3.5 / 12,      # Web depth: 3.5" = 0.292 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.62,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
        }
    ),
    # ... more profiles

    # Tracks (no lips) - Used for top/bottom
    "350T125-54": ElementProfile(
        name="350T125-54",
        width=1.25 / 12,     # Flange width: 1.25" = 0.104 feet
        depth=3.5 / 12,      # Web depth: 3.5" = 0.292 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
        }
    ),
}

DEFAULT_CFS_PROFILES: Dict[ElementType, str] = {
    # Tracks for horizontal members
    ElementType.BOTTOM_PLATE: "350T125-54",  # Bottom track
    ElementType.TOP_PLATE: "350T125-54",     # Top track

    # Studs for vertical members
    ElementType.STUD: "350S162-54",
    ElementType.KING_STUD: "350S162-54",
    ElementType.TRIMMER: "350S162-54",

    # Opening components
    ElementType.HEADER: "600S162-54",        # Deeper for headers
    ElementType.SILL: "350S162-54",
    ElementType.HEADER_CRIPPLE: "350S162-54",
    ElementType.SILL_CRIPPLE: "350S162-54",

    # Bracing
    ElementType.ROW_BLOCKING: "350S162-54",  # Bridging in CFS terminology
}


# Task 3: cfs_strategy.py
# ============================================================================

class CFSFramingStrategy(FramingStrategy):
    """CFS framing strategy implementing the FramingStrategy interface."""

    @property
    def material_system(self) -> MaterialSystem:
        return MaterialSystem.CFS

    @property
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        return {
            element_type: CFS_PROFILES[profile_name]
            for element_type, profile_name in DEFAULT_CFS_PROFILES.items()
        }

    def get_generation_sequence(self) -> List[ElementType]:
        """CFS follows similar sequence to timber."""
        return [
            ElementType.BOTTOM_PLATE,  # Bottom track
            ElementType.TOP_PLATE,     # Top track
            ElementType.KING_STUD,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.TRIMMER,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.STUD,
            ElementType.ROW_BLOCKING,  # Bridging
        ]

    # ... other methods similar to timber

# Register at module level
register_strategy(CFSFramingStrategy())
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
# Run FIRST - fix errors before proceeding
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Syntax check all new files
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/cfs/__init__.py').read())"
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/cfs/cfs_profiles.py').read())"
python -c "import ast; ast.parse(open('src/timber_framing_generator/materials/cfs/cfs_strategy.py').read())"
python -c "import ast; ast.parse(open('tests/unit/test_cfs_strategy.py').read())"

echo "All syntax checks passed!"
```

### Level 2: Unit Tests
```bash
# Run unit tests
uv run pytest tests/unit/test_cfs_strategy.py -v

# Run all material strategy tests
uv run pytest tests/unit/test_timber_strategy.py tests/unit/test_cfs_strategy.py -v
```

### Level 3: Integration Test
```python
# Test both strategies can be retrieved
from src.timber_framing_generator.core.material_system import (
    get_framing_strategy, MaterialSystem, list_available_materials
)

# Import both materials to trigger registration
from src.timber_framing_generator.materials import timber  # noqa: F401
from src.timber_framing_generator.materials import cfs  # noqa: F401

# Test
available = list_available_materials()
assert MaterialSystem.TIMBER in available
assert MaterialSystem.CFS in available

timber_strategy = get_framing_strategy(MaterialSystem.TIMBER)
cfs_strategy = get_framing_strategy(MaterialSystem.CFS)

assert timber_strategy.material_system == MaterialSystem.TIMBER
assert cfs_strategy.material_system == MaterialSystem.CFS
```

---

## Final Checklist

- [ ] cfs/__init__.py created
- [ ] cfs_profiles.py created with standard CFS profiles
- [ ] cfs_strategy.py created implementing FramingStrategy ABC
- [ ] materials/__init__.py updated to import cfs
- [ ] Unit tests created and passing
- [ ] All syntax checks pass
- [ ] get_framing_strategy(MaterialSystem.CFS) returns CFSFramingStrategy
- [ ] Both timber and CFS strategies coexist without conflict
- [ ] No breaking changes to existing code

---

## Anti-Patterns to Avoid

- ❌ Don't forget to call register_strategy() at module level
- ❌ Don't use different units (always FEET for dimensions)
- ❌ Don't add new ElementTypes without modifying material_system.py
- ❌ Don't implement actual generation logic (Phase 4 is structure only)
- ❌ Don't import CFS-specific modules in timber strategy (keep isolated)

---

## Notes

- **Phase 4 Scope**: CFS strategy is structural only - generation methods return empty lists
- **Future Enhancement**: Actual CFS generation will need additional ElementTypes (WEB_STIFFENER, BRIDGING)
- **Testing**: Unit tests verify structure, not actual framing generation
- **Compatibility**: Both strategies registered in same factory, retrieved by MaterialSystem enum
