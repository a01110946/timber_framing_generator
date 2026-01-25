# PRP: Architecture Refactor for Multi-Component Support

> **Version:** 1.0
> **Created:** 2025-01-24
> **Status:** In Progress
> **Branch:** feature/architecture-refactor

---

## Goal

Restructure the codebase to support multiple building components (walls, floors, roofs) and MEP integration while maintaining full backward compatibility with existing wall framing functionality.

## Why

- **Multi-component support**: Current architecture is wall-centric; need to support floors and roofs
- **MEP integration**: Need clean abstractions for MEP systems (plumbing, HVAC, electrical)
- **Scalability**: Prepare for offsite panel generation and fabrication outputs
- **Maintainability**: Clear separation of concerns with component-agnostic core

## What

Add new core abstractions and reorganize code structure without breaking existing functionality:
- Add `ComponentType` enum and `BuildingComponent` ABC
- Add `MEPDomain` enum and `MEPSystem` ABC
- Create `components/` directory for component-specific code
- Create `mep/` directory structure for MEP integration
- Ensure existing GH scripts continue to work unchanged

### Success Criteria

- [ ] All existing GH scripts work without modification
- [ ] New core abstractions are in place (ComponentType, MEPDomain, etc.)
- [ ] Directory structure supports multi-component architecture
- [ ] Existing tests pass
- [ ] New abstractions have basic tests

---

## All Needed Context

### Documentation & References
```yaml
Project Docs:
  - file: docs/ai/ai-offsite-construction-architecture.md
    why: Target architecture vision and decisions

  - file: docs/ai/ai-mep-connectors-reference.md
    why: MEP connector patterns for MEPSystem design

  - file: CLAUDE.md
    why: Project conventions and gotchas

Existing Patterns:
  - file: src/timber_framing_generator/core/material_system.py
    why: Pattern for Strategy ABC (FramingStrategy)

  - file: src/timber_framing_generator/materials/timber/timber_strategy.py
    why: Pattern for strategy implementation
```

### Current Codebase Structure
```
src/timber_framing_generator/
├── core/
│   ├── __init__.py
│   ├── material_system.py      # FramingStrategy ABC, MaterialSystem enum
│   └── json_schemas.py         # Data schemas
├── materials/
│   ├── timber/
│   │   ├── timber_strategy.py
│   │   ├── timber_profiles.py
│   │   └── element_adapters.py
│   └── cfs/
│       ├── cfs_strategy.py
│       └── cfs_profiles.py
├── cell_decomposition/         # Wall decomposition
├── framing_elements/           # Element generators
├── wall_data/                  # Wall extraction
├── config/
└── utils/
```

### Desired Structure (files to add)
```bash
src/timber_framing_generator/
├── core/
│   ├── __init__.py             # MODIFY: Export new types
│   ├── material_system.py      # PRESERVE: Existing FramingStrategy
│   ├── component_types.py      # CREATE: ComponentType enum
│   ├── building_component.py   # CREATE: BuildingComponent ABC
│   ├── mep_system.py           # CREATE: MEPSystem ABC, MEPDomain enum
│   └── json_schemas.py         # PRESERVE
├── components/                 # CREATE: Component-specific code
│   ├── __init__.py
│   └── walls/                  # Future: Move wall-specific code here
│       └── __init__.py
├── mep/                        # CREATE: MEP integration
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── base.py             # Base MEP classes
│   └── plumbing/
│       └── __init__.py
└── [existing directories preserved]
```

### Known Gotchas
```python
# CRITICAL: Backward compatibility
# - Existing imports must continue to work
# - FramingStrategy ABC signature must not change
# - GH scripts import from specific paths

# CRITICAL: Import paths
# - from src.timber_framing_generator.core import get_framing_strategy
# - from src.timber_framing_generator.materials import timber, cfs
# - These MUST continue to work

# PATTERN: Registration
# - Strategies register via register_strategy() at import time
# - New systems should follow same pattern
```

---

## Implementation Blueprint

### Data Models

```python
# core/component_types.py
from enum import Enum

class ComponentType(Enum):
    """Types of building components."""
    WALL = "wall"
    FLOOR = "floor"
    ROOF = "roof"
    CEILING = "ceiling"


# core/mep_system.py
from enum import Enum

class MEPDomain(Enum):
    """MEP system domains."""
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
```

### Tasks (in execution order)

```yaml
Task 1: Create ComponentType enum
  - CREATE: src/timber_framing_generator/core/component_types.py
  - Contains: ComponentType enum with WALL, FLOOR, ROOF, CEILING

Task 2: Create BuildingComponent ABC
  - CREATE: src/timber_framing_generator/core/building_component.py
  - Contains: Abstract base class for component handlers
  - Methods: extract_data, decompose_to_cells, get_framing_element_types

Task 3: Create MEP core types
  - CREATE: src/timber_framing_generator/core/mep_system.py
  - Contains: MEPDomain enum, MEPConnector dataclass, MEPRoute dataclass, MEPSystem ABC

Task 4: Create components directory structure
  - CREATE: src/timber_framing_generator/components/__init__.py
  - CREATE: src/timber_framing_generator/components/walls/__init__.py
  - Purpose: Prepare for future wall-specific code migration

Task 5: Create mep directory structure
  - CREATE: src/timber_framing_generator/mep/__init__.py
  - CREATE: src/timber_framing_generator/mep/core/__init__.py
  - CREATE: src/timber_framing_generator/mep/core/base.py
  - CREATE: src/timber_framing_generator/mep/plumbing/__init__.py
  - Purpose: Prepare for plumbing integration

Task 6: Update core __init__.py exports
  - MODIFY: src/timber_framing_generator/core/__init__.py
  - ADD: Export ComponentType, MEPDomain, BuildingComponent, MEPSystem
  - PRESERVE: All existing exports

Task 7: Create basic tests
  - CREATE: tests/core/test_component_types.py
  - CREATE: tests/core/test_mep_system.py
  - Verify enums and ABCs work correctly
```

### Pseudocode (with CRITICAL details)

```python
# Task 1: core/component_types.py
"""Building component type definitions."""

from enum import Enum


class ComponentType(Enum):
    """
    Types of building components that can be framed.

    Each component type has its own:
    - Data extraction logic
    - Cell decomposition strategy
    - Framing element types
    - MEP penetration patterns
    """
    WALL = "wall"
    FLOOR = "floor"
    ROOF = "roof"
    CEILING = "ceiling"


# Task 2: core/building_component.py
"""Abstract base class for building components."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any
from .component_types import ComponentType


class BuildingComponent(ABC):
    """
    Abstract base class for building components.

    Subclasses implement component-specific logic for:
    - Extracting data from Revit elements
    - Decomposing into cells for framing
    - Identifying MEP routing zones
    """

    @property
    @abstractmethod
    def component_type(self) -> ComponentType:
        """Return the type of this component."""
        pass

    @abstractmethod
    def extract_data(self, revit_element: Any) -> Dict[str, Any]:
        """Extract component data from a Revit element."""
        pass

    @abstractmethod
    def decompose_to_cells(
        self,
        component_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Decompose component into cells for framing."""
        pass

    @abstractmethod
    def get_framing_element_types(self) -> List[str]:
        """Return list of framing element types for this component."""
        pass


# Task 3: core/mep_system.py
"""MEP system abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Any, Tuple, Optional


class MEPDomain(Enum):
    """MEP system domains."""
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"


@dataclass
class MEPConnector:
    """Represents an MEP connector extracted from Revit."""
    id: str
    origin: Tuple[float, float, float]
    direction: Tuple[float, float, float]
    domain: MEPDomain
    system_type: str
    owner_element_id: int
    radius: Optional[float] = None
    flow_direction: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "origin": {"x": self.origin[0], "y": self.origin[1], "z": self.origin[2]},
            "direction": {"x": self.direction[0], "y": self.direction[1], "z": self.direction[2]},
            "domain": self.domain.value,
            "system_type": self.system_type,
            "owner_element_id": self.owner_element_id,
            "radius": self.radius,
            "flow_direction": self.flow_direction,
        }


@dataclass
class MEPRoute:
    """Represents a calculated route for MEP elements."""
    id: str
    domain: MEPDomain
    system_type: str
    path_points: List[Tuple[float, float, float]]
    start_connector_id: str
    end_point_type: str  # "wall_entry", "vertical_connection", "main_line", etc.
    pipe_size: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "domain": self.domain.value,
            "system_type": self.system_type,
            "path_points": [{"x": p[0], "y": p[1], "z": p[2]} for p in self.path_points],
            "start_connector_id": self.start_connector_id,
            "end_point_type": self.end_point_type,
            "pipe_size": self.pipe_size,
        }


class MEPSystem(ABC):
    """
    Abstract base class for MEP system handlers.

    Each MEP domain (plumbing, HVAC, electrical) implements this
    with domain-specific logic for extraction, routing, and sizing.
    """

    @property
    @abstractmethod
    def domain(self) -> MEPDomain:
        """Return the MEP domain this system handles."""
        pass

    @abstractmethod
    def extract_connectors(
        self,
        elements: List[Any],
        filter_config: Optional[Dict[str, Any]] = None
    ) -> List[MEPConnector]:
        """Extract MEP connectors from Revit elements."""
        pass

    @abstractmethod
    def calculate_routes(
        self,
        connectors: List[MEPConnector],
        framing_data: Dict[str, Any],
        target_points: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """Calculate routes from connectors through framing."""
        pass

    @abstractmethod
    def generate_penetrations(
        self,
        routes: List[MEPRoute],
        framing_elements: List[Any]
    ) -> List[Dict[str, Any]]:
        """Generate penetration data for framing members."""
        pass
```

### Integration Points

```yaml
CORE EXPORTS:
  - file: src/timber_framing_generator/core/__init__.py
  - pattern: "Add new exports while preserving existing ones"
  - code: |
      # Existing exports (PRESERVE)
      from .material_system import (
          MaterialSystem,
          FramingStrategy,
          # ... existing exports
      )

      # New exports (ADD)
      from .component_types import ComponentType
      from .building_component import BuildingComponent
      from .mep_system import MEPDomain, MEPConnector, MEPRoute, MEPSystem

BACKWARD COMPATIBILITY:
  - All existing imports must work unchanged
  - Test by running existing GH scripts
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Check new files
python -c "from src.timber_framing_generator.core.component_types import ComponentType; print('OK')"
python -c "from src.timber_framing_generator.core.building_component import BuildingComponent; print('OK')"
python -c "from src.timber_framing_generator.core.mep_system import MEPDomain, MEPConnector, MEPRoute, MEPSystem; print('OK')"

# Check existing imports still work
python -c "from src.timber_framing_generator.core import get_framing_strategy, MaterialSystem; print('OK')"
```

### Level 2: Unit Tests
```bash
# Run new tests
python -m pytest tests/core/test_component_types.py -v
python -m pytest tests/core/test_mep_system.py -v

# Run ALL existing tests (must still pass)
python -m pytest tests/ -v
```

### Level 3: Integration Test
```bash
# Verify GH scripts can import new types
python -c "
from src.timber_framing_generator.core import (
    get_framing_strategy,
    MaterialSystem,
    ComponentType,
    MEPDomain,
)
print('All imports successful')
"
```

---

## Final Checklist

- [ ] ComponentType enum created and exported
- [ ] BuildingComponent ABC created and exported
- [ ] MEPDomain enum created and exported
- [ ] MEPConnector dataclass created and exported
- [ ] MEPRoute dataclass created and exported
- [ ] MEPSystem ABC created and exported
- [ ] components/ directory structure created
- [ ] mep/ directory structure created
- [ ] core/__init__.py exports all new types
- [ ] All existing imports continue to work
- [ ] All existing tests pass
- [ ] New basic tests pass

---

## Anti-Patterns to Avoid

- ❌ Don't modify FramingStrategy ABC signature
- ❌ Don't move existing files (yet) - just add new ones
- ❌ Don't break existing import paths
- ❌ Don't add Rhino-dependent code to core abstractions
- ❌ Don't over-engineer - keep ABCs minimal

---

## Notes

This is a **non-breaking, additive refactor**. We're adding new abstractions alongside existing ones. The actual migration of wall code to components/walls/ will be a separate, future task once the new structure is proven.

The goal is to have the scaffolding in place so that:
1. Plumbing integration can start immediately after
2. Floor/roof framing can be added without restructuring
3. Existing wall framing continues to work unchanged
