# Offsite Construction System Architecture

A comprehensive architectural vision for an automated framing and MEP integration system for offsite/modular construction.

---

## Vision

Create a **unified system** that generates complete framed building components (walls, floors, roofs) with integrated MEP rough-ins, optimized for offsite fabrication. The system should:

1. Extract building data from Revit BIM models
2. Generate framing for multiple material systems (Timber, CFS)
3. Integrate MEP systems (Plumbing, HVAC, Electrical)
4. Produce fabrication-ready outputs (geometry, shop drawings, CNC data)

---

## Current State Analysis

### What We Have (Wall Framing)

```
src/timber_framing_generator/
├── core/                   # Core abstractions
│   ├── material_system.py  # FramingStrategy ABC, MaterialSystem enum
│   └── json_schemas.py     # WallData, CellData, FramingResults
├── materials/              # Material strategies
│   ├── timber/             # Timber profiles + strategy
│   └── cfs/                # CFS profiles + strategy
├── cell_decomposition/     # Wall → cells
├── framing_elements/       # Element generators
├── wall_data/              # Revit wall extraction
└── utils/                  # Geometry factory, logging
```

**Strengths:**
- Clean Strategy Pattern for materials
- JSON-based inter-component communication
- Modular GHPython components
- RhinoCommon assembly handling solved

**Limitations:**
- Tightly coupled to "walls" - naming and structure
- No floor/roof support
- No MEP integration
- No panel/module concept for offsite

---

## Proposed Architecture

### High-Level Module Structure

```
src/offsite_framing/                    # Consider renaming project
│
├── core/                               # Core abstractions and interfaces
│   ├── __init__.py
│   ├── component_types.py              # ComponentType enum (WALL, FLOOR, ROOF)
│   ├── material_system.py              # FramingStrategy ABC (existing)
│   ├── building_component.py           # BuildingComponent ABC (NEW)
│   ├── mep_system.py                   # MEPSystem ABC (NEW)
│   ├── panel_system.py                 # Panel/Module abstractions (NEW)
│   └── schemas/                        # JSON schemas
│       ├── component_data.py           # Generic component data
│       ├── framing_results.py          # Framing output schema
│       └── mep_data.py                 # MEP connector/route data
│
├── components/                         # Building component types (NEW)
│   ├── __init__.py
│   ├── base.py                         # Shared component logic
│   ├── walls/
│   │   ├── __init__.py
│   │   ├── wall_extractor.py           # Extract from Revit
│   │   ├── wall_decomposer.py          # Cell decomposition
│   │   └── wall_cells.py               # Wall-specific cell types
│   ├── floors/
│   │   ├── __init__.py
│   │   ├── floor_extractor.py          # Extract from Revit
│   │   ├── floor_decomposer.py         # Joist bay decomposition
│   │   └── floor_cells.py              # Floor-specific cell types
│   └── roofs/
│       ├── __init__.py
│       ├── roof_extractor.py           # Extract from Revit
│       ├── roof_decomposer.py          # Rafter bay decomposition
│       └── roof_cells.py               # Roof-specific cell types
│
├── materials/                          # Material strategies (existing, expanded)
│   ├── __init__.py
│   ├── base.py                         # Shared material logic
│   ├── timber/
│   │   ├── __init__.py
│   │   ├── timber_strategy.py          # Existing
│   │   ├── timber_profiles.py          # Existing
│   │   ├── timber_wall_framing.py      # Wall-specific framing
│   │   ├── timber_floor_framing.py     # Floor-specific framing (NEW)
│   │   └── timber_roof_framing.py      # Roof-specific framing (NEW)
│   └── cfs/
│       ├── __init__.py
│       ├── cfs_strategy.py             # Existing
│       ├── cfs_profiles.py             # Existing
│       ├── cfs_wall_framing.py         # Wall-specific framing
│       ├── cfs_floor_framing.py        # Floor-specific framing (NEW)
│       └── cfs_roof_framing.py         # Roof-specific framing (NEW)
│
├── mep/                                # MEP integration (NEW)
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── connector_extractor.py      # Extract connectors from Revit
│   │   ├── routing_engine.py           # Route calculation algorithms
│   │   ├── penetration_generator.py    # Create holes in framing
│   │   └── clash_detector.py           # Detect MEP/framing conflicts
│   ├── plumbing/
│   │   ├── __init__.py
│   │   ├── plumbing_extractor.py       # Fixtures, existing pipes
│   │   ├── pipe_router.py              # Pipe routing logic
│   │   └── plumbing_rules.py           # Plumbing code rules
│   ├── hvac/
│   │   ├── __init__.py
│   │   ├── hvac_extractor.py           # Equipment, existing ducts
│   │   ├── duct_router.py              # Duct routing logic
│   │   └── hvac_rules.py               # HVAC sizing/code rules
│   └── electrical/
│       ├── __init__.py
│       ├── electrical_extractor.py     # Panels, devices, fixtures
│       ├── conduit_router.py           # Conduit/wire routing
│       └── electrical_rules.py         # Electrical code rules
│
├── panels/                             # Offsite panel generation (NEW)
│   ├── __init__.py
│   ├── panel_generator.py              # Create panel boundaries
│   ├── panel_optimizer.py              # Optimize panel sizes/joints
│   ├── connection_details.py           # Inter-panel connections
│   └── shipping_constraints.py         # Size/weight limits
│
├── framing_elements/                   # Shared element generators (existing)
│   ├── __init__.py
│   ├── studs.py                        # Vertical members (walls)
│   ├── plates.py                       # Horizontal plates (walls)
│   ├── headers.py                      # Opening headers
│   ├── joists.py                       # Floor/ceiling joists (NEW)
│   ├── rafters.py                      # Roof rafters (NEW)
│   ├── rim_boards.py                   # Floor perimeter (NEW)
│   ├── blocking.py                     # All blocking types
│   └── sheathing.py                    # Panel sheathing (NEW)
│
├── output/                             # Output generation (NEW)
│   ├── __init__.py
│   ├── geometry_exporter.py            # Export to various formats
│   ├── shop_drawing_generator.py       # 2D fabrication drawings
│   ├── cut_list_generator.py           # Material cut lists
│   ├── cnc_exporter.py                 # CNC machine data
│   └── bim_exporter.py                 # Back to Revit/IFC
│
├── utils/                              # Utilities (existing, expanded)
│   ├── __init__.py
│   ├── geometry_factory.py             # RhinoCommon factory
│   ├── revit_helpers.py                # RiR utilities
│   ├── unit_conversion.py              # Unit handling
│   └── logging_config.py               # Logging
│
└── config/                             # Configuration
    ├── __init__.py
    ├── framing_standards.py            # Framing rules/dimensions
    ├── mep_standards.py                # MEP routing rules
    └── panel_standards.py              # Panel size constraints
```

---

## Core Abstractions

### 1. BuildingComponent ABC

```python
# core/building_component.py

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional

class ComponentType(Enum):
    """Types of building components."""
    WALL = "wall"
    FLOOR = "floor"
    ROOF = "roof"
    CEILING = "ceiling"


class BuildingComponent(ABC):
    """
    Abstract base class for building components (walls, floors, roofs).

    Each component type has its own:
    - Data extraction logic (from Revit)
    - Cell decomposition strategy
    - Framing element types
    - MEP penetration patterns
    """

    @property
    @abstractmethod
    def component_type(self) -> ComponentType:
        """Return the type of this component."""
        pass

    @abstractmethod
    def extract_data(self, revit_element: Any) -> Dict[str, Any]:
        """
        Extract component data from a Revit element.

        Args:
            revit_element: Revit Wall, Floor, or RoofBase element

        Returns:
            Standardized component data dictionary
        """
        pass

    @abstractmethod
    def decompose_to_cells(
        self,
        component_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Decompose component into cells for framing.

        Args:
            component_data: Extracted component data
            config: Decomposition configuration

        Returns:
            List of cell data dictionaries
        """
        pass

    @abstractmethod
    def get_framing_element_types(self) -> List[str]:
        """
        Return list of framing element types for this component.

        Example for walls: ["bottom_plate", "top_plate", "stud", "header", ...]
        Example for floors: ["rim_board", "joist", "blocking", "bridging", ...]
        """
        pass

    @abstractmethod
    def get_mep_zones(
        self,
        component_data: Dict[str, Any],
        framing_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Identify zones where MEP can be routed.

        Returns regions between framing members where pipes/ducts can pass.
        """
        pass
```

### 2. Enhanced FramingStrategy ABC

```python
# core/material_system.py (enhanced)

class FramingStrategy(ABC):
    """
    Abstract base class for material-specific framing strategies.

    Extended to support multiple component types (wall, floor, roof).
    """

    @property
    @abstractmethod
    def material_system(self) -> MaterialSystem:
        """Return the material system (TIMBER, CFS)."""
        pass

    @abstractmethod
    def generate_framing(
        self,
        component_type: ComponentType,
        component_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> FramingResults:
        """
        Generate framing for any component type.

        Args:
            component_type: WALL, FLOOR, or ROOF
            component_data: Component geometry and properties
            cell_data: Cell decomposition results
            config: Framing configuration

        Returns:
            FramingResults with generated elements
        """
        pass

    @abstractmethod
    def get_profile_for_element(
        self,
        component_type: ComponentType,
        element_type: ElementType,
        config: Dict[str, Any]
    ) -> ElementProfile:
        """
        Get profile for element type, considering component context.

        Floor joists may use different profiles than wall studs.
        """
        pass
```

### 3. MEPSystem ABC

```python
# core/mep_system.py

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Tuple

class MEPDomain(Enum):
    """MEP system domains."""
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"


class MEPConnector:
    """Represents an MEP connector extracted from Revit."""

    def __init__(
        self,
        id: str,
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        domain: MEPDomain,
        system_type: str,
        owner_element_id: int,
        radius: float = None,
        flow_direction: str = None,
    ):
        self.id = id
        self.origin = origin
        self.direction = direction
        self.domain = domain
        self.system_type = system_type
        self.owner_element_id = owner_element_id
        self.radius = radius
        self.flow_direction = flow_direction


class MEPRoute:
    """Represents a calculated route for MEP elements."""

    def __init__(
        self,
        id: str,
        domain: MEPDomain,
        system_type: str,
        path_points: List[Tuple[float, float, float]],
        connector_start: MEPConnector,
        connector_end: Any,  # Could be another connector or a termination point
        pipe_size: float = None,
    ):
        self.id = id
        self.domain = domain
        self.system_type = system_type
        self.path_points = path_points
        self.connector_start = connector_start
        self.connector_end = connector_end
        self.pipe_size = pipe_size


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
        filter_config: Dict[str, Any] = None
    ) -> List[MEPConnector]:
        """
        Extract MEP connectors from Revit elements.

        Args:
            elements: Revit FamilyInstances (fixtures, equipment)
            filter_config: Optional filters (system types, etc.)

        Returns:
            List of MEPConnector objects
        """
        pass

    @abstractmethod
    def calculate_routes(
        self,
        connectors: List[MEPConnector],
        framing_data: Dict[str, Any],
        target_points: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """
        Calculate routes from connectors through framing.

        Args:
            connectors: Source connectors to route from
            framing_data: Generated framing (for avoidance/penetration)
            target_points: Destination points (wall stubs, mains, etc.)
            config: Routing configuration

        Returns:
            List of calculated routes
        """
        pass

    @abstractmethod
    def size_elements(
        self,
        routes: List[MEPRoute],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """
        Size MEP elements based on code and flow requirements.

        Args:
            routes: Routes to size
            config: Sizing rules and code requirements

        Returns:
            Routes with sizing information
        """
        pass

    @abstractmethod
    def generate_penetrations(
        self,
        routes: List[MEPRoute],
        framing_elements: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate penetration data for framing members.

        Args:
            routes: Calculated MEP routes
            framing_elements: Framing elements that routes pass through

        Returns:
            List of penetration specifications (location, size, reinforcement)
        """
        pass
```

### 4. Panel System

```python
# core/panel_system.py

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple


class PanelBoundary:
    """Defines the boundary of an offsite panel."""

    def __init__(
        self,
        id: str,
        component_type: str,  # wall, floor, roof
        vertices: List[Tuple[float, float, float]],
        thickness: float,
        connections: List[Dict[str, Any]],  # Connection points to adjacent panels
    ):
        self.id = id
        self.component_type = component_type
        self.vertices = vertices
        self.thickness = thickness
        self.connections = connections


class Panel:
    """Represents a complete offsite panel with framing and MEP."""

    def __init__(
        self,
        id: str,
        boundary: PanelBoundary,
        framing_elements: List[Any],
        mep_elements: List[Any],
        penetrations: List[Dict[str, Any]],
        sheathing: List[Any],
        metadata: Dict[str, Any],
    ):
        self.id = id
        self.boundary = boundary
        self.framing_elements = framing_elements
        self.mep_elements = mep_elements
        self.penetrations = penetrations
        self.sheathing = sheathing
        self.metadata = metadata


class PanelGenerator(ABC):
    """
    Abstract base class for panel generation.

    Handles dividing building components into shippable panels,
    optimizing joint locations, and generating connection details.
    """

    @abstractmethod
    def generate_panel_boundaries(
        self,
        component_data: Dict[str, Any],
        constraints: Dict[str, Any]
    ) -> List[PanelBoundary]:
        """
        Divide a component into panel boundaries.

        Args:
            component_data: Building component data
            constraints: Size, weight, shipping constraints

        Returns:
            List of panel boundaries
        """
        pass

    @abstractmethod
    def optimize_panel_joints(
        self,
        boundaries: List[PanelBoundary],
        framing_data: Dict[str, Any],
        mep_routes: List[Any]
    ) -> List[PanelBoundary]:
        """
        Optimize joint locations to avoid MEP and minimize waste.
        """
        pass

    @abstractmethod
    def generate_connection_details(
        self,
        panel: Panel,
        adjacent_panels: List[Panel]
    ) -> List[Dict[str, Any]]:
        """
        Generate connection details between panels.
        """
        pass
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         REVIT MODEL                                  │
│                                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────────────┐ │
│  │  Walls  │  │ Floors  │  │  Roofs  │  │ MEP (Fixtures/Equipment)│ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └───────────┬─────────────┘ │
└───────┼────────────┼────────────┼───────────────────┼───────────────┘
        │            │            │                   │
        ▼            ▼            ▼                   ▼
┌───────────────────────────────────────┐  ┌─────────────────────────┐
│      COMPONENT EXTRACTION             │  │   MEP EXTRACTION        │
│                                       │  │                         │
│  • Geometry (boundaries, openings)    │  │  • Connector locations  │
│  • Properties (type, materials)       │  │  • System types         │
│  • Levels and constraints             │  │  • Flow directions      │
│  • Adjacent elements                  │  │  • Sizing data          │
└───────────────────┬───────────────────┘  └───────────┬─────────────┘
                    │                                  │
                    ▼                                  │
┌───────────────────────────────────────┐              │
│      CELL DECOMPOSITION               │              │
│                                       │              │
│  Walls:  WBC → OC → SC/HCC/SCC        │              │
│  Floors: Bay cells, opening cells     │              │
│  Roofs:  Rafter bays, valleys/hips    │              │
└───────────────────┬───────────────────┘              │
                    │                                  │
                    ▼                                  │
┌───────────────────────────────────────┐              │
│      FRAMING GENERATION               │              │
│      (Material Strategy)              │              │
│                                       │              │
│  • Plates/Tracks, Studs/Joists        │              │
│  • Headers, Blocking, Bridging        │              │
│  • Profile assignment                 │              │
│  • Centerline + metadata              │              │
└───────────────────┬───────────────────┘              │
                    │                                  │
                    │◄─────────────────────────────────┘
                    ▼
┌───────────────────────────────────────────────────────┐
│              MEP ROUTING                              │
│                                                       │
│  • Route from connectors to targets (walls/mains)    │
│  • Avoid framing members or plan penetrations        │
│  • Size pipes/ducts per code                         │
│  • Detect and resolve clashes                        │
└───────────────────┬───────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────┐
│           PENETRATION GENERATION                      │
│                                                       │
│  • Calculate hole locations in framing               │
│  • Size holes (MEP diameter + clearance)             │
│  • Add reinforcement where required                  │
│  • Modify framing geometry                           │
└───────────────────┬───────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────┐
│           PANEL ASSEMBLY                              │
│                                                       │
│  • Divide into shippable panel sizes                 │
│  • Optimize joint locations                          │
│  • Generate connection details                       │
│  • Add lifting/handling points                       │
└───────────────────┬───────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────┐
│                 OUTPUT                                │
│                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │  Geometry   │  │ Shop Dwgs   │  │  BIM Data   │   │
│  │  (Rhino/    │  │ (2D PDF/    │  │  (Revit/    │   │
│  │   STEP)     │  │  DXF)       │  │   IFC)      │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
│                                                       │
│  ┌─────────────┐  ┌─────────────┐                    │
│  │  Cut Lists  │  │  CNC Data   │                    │
│  │  (CSV/      │  │  (BTL/      │                    │
│  │   Excel)    │  │   DSTV)     │                    │
│  └─────────────┘  └─────────────┘                    │
└───────────────────────────────────────────────────────┘
```

---

## Grasshopper Component Pipeline

### Phase 1: Current (Walls Only)
```
1. Wall Analyzer        → wall_json
2. Cell Decomposer      → cell_json
3. Framing Generator    → elements_json
4. Geometry Converter   → Breps
5. Revit Baker          → Revit elements
```

### Phase 2: Expanded (Walls + MEP)
```
 1. Wall Analyzer        → wall_json
 2. MEP Connector        → mep_connectors_json
    Extractor
 3. Cell Decomposer      → cell_json
 4. Framing Generator    → elements_json
 5. MEP Router           → mep_routes_json
 6. Penetration          → penetrations_json
    Generator
 7. Geometry Converter   → Breps (framing + penetrations)
 8. Revit Baker          → Revit elements
```

### Phase 3: Full System
```
 1. Component Analyzer   → component_json (walls/floors/roofs)
 2. MEP Extractor        → mep_json (all domains)
 3. Cell Decomposer      → cells_json
 4. Framing Generator    → framing_json
 5. MEP Router           → routes_json
 6. Clash Detector       → clashes_json
 7. Penetration          → penetrations_json
    Generator
 8. Panel Assembler      → panels_json
 9. Geometry Converter   → Breps
10. Output Generator     → Shop drawings, cut lists, CNC
11. Revit Baker          → Revit elements
```

---

## Implementation Roadmap

### Phase 1: Foundation (COMPLETE)
- [x] Wall framing generation
- [x] Timber and CFS material strategies
- [x] JSON-based component communication
- [x] Revit Baker for output
- [x] CSR and plane-based orientation

### Phase 2: Architecture Refactor (CURRENT)
- [ ] Restructure codebase for multi-component support
- [ ] Add core abstractions (BuildingComponent, MEPSystem)
- [ ] Reorganize into components/materials/mep structure
- [ ] Maintain backward compatibility with existing wall framing

### Phase 3: Plumbing Integration
- [ ] MEP Connector Extractor component
- [ ] Plumbing fixture connector extraction
- [ ] Pipe routing (fixture → wall entry + first connection)
- [ ] Penetration generation for wall studs
- [ ] Plumbing-specific GH components

### Phase 4: Floor Framing (Open-Web Trusses)
- [ ] Floor data extraction from Revit
- [ ] Open-web truss bay decomposition
- [ ] Floor framing generation (trusses, rim boards, blocking)
- [ ] Floor MEP penetrations (through truss webs)

### Phase 5: Floor Framing (Platform + I-Joist)
- [ ] Platform framing with solid lumber joists
- [ ] I-joist profile support
- [ ] Joist penetration rules (different from trusses)

### Phase 6: Enhanced MEP
- [ ] HVAC connector extraction
- [ ] Electrical connector extraction
- [ ] Multi-system routing
- [ ] Clash detection
- [ ] Configurable target points

### Phase 7: Roof Framing
- [ ] Roof data extraction
- [ ] Stick-built rafter generation
- [ ] Ridge boards, collar ties
- [ ] Roof penetrations (vents, chimneys)

### Phase 8: Panel System
- [ ] Panel boundary generation
- [ ] Optimized irregular joint placement
- [ ] Connection details
- [ ] Shipping constraints

### Phase 9: Output & Fabrication (LOD 400)
- [ ] Connection hardware specification
- [ ] Shop drawing generation
- [ ] Cut list generation
- [ ] CNC export (BTL, DSTV)

---

## Key Design Decisions

### 1. JSON as Interchange Format
**Decision**: Continue using JSON for inter-component communication.
**Rationale**: Inspectable, debuggable, technology-agnostic, version-controllable.

### 2. Strategy Pattern for Extensibility
**Decision**: Use Strategy pattern for materials AND MEP domains.
**Rationale**: Easy to add new materials (CLT, SIP) or MEP systems without changing core logic.

### 3. Component-Agnostic Core
**Decision**: Abstract building components to share decomposition/generation patterns.
**Rationale**: Walls, floors, and roofs have similar patterns (cells → elements → geometry).

### 4. MEP as Overlay
**Decision**: Generate framing first, then route MEP, then create penetrations.
**Rationale**: Framing drives structure; MEP adapts to it. Enables clash detection.

### 5. Panel as Assembly
**Decision**: Panels combine framing + MEP + connections as a unit.
**Rationale**: Matches offsite fabrication workflow where panels are complete units.

---

## Architectural Decisions (Finalized)

### 1. Roof Framing Approach
**Decision**: Start with **stick-built rafters** (individual members).

**Rationale**:
- Matches wall framing pattern (individual members in cells)
- Better fit for panelized offsite construction
- Simpler MEP penetration logic
- Can add truss support later as "pass-through"

### 2. Floor System Types
**Decision**: Implement in order:
1. **Open-Web Floor Trusses** (first priority - customer requirement)
2. **Platform Framing** (solid lumber joists)
3. **I-Joist Systems** (future)

**Rationale**:
- Open-web trusses are used by first customer
- Easy MEP routing through open webs
- Platform framing is most common, good fallback
- I-joists can be added as profile type

### 3. MEP Connection Points
**Decision**: **Wall entry + first vertical connection**

Routes terminate at:
1. Wall entry point (horizontal stub)
2. First connection inside wall (supports vertical connections)

Future expansion:
- Phase 2: Wall entry + first connection
- Phase 3: Configurable target points
- Phase 4: Full system routing with stacks/mains

**Rationale**:
- Provides immediate value over simple stub-out
- Supports vertical pipe runs (critical for plumbing)
- Clear interface between prefab panel and field work

### 4. Panel Joint Strategy
**Decision**: **Optimized irregular joints** (CRITICAL)

Joints are placed intelligently:
- Never cut through openings
- Avoid MEP penetration locations
- Align with stud/joist locations when possible
- Respect maximum panel size constraints

**Rationale**:
- Fixed grid constantly hits openings
- Structural integrity must be maintained
- Variable panel sizes are normal in offsite construction

### 5. Code Compliance
**Decision**: **Engineer-configurable, not built-in**

System provides geometry generation; engineers configure:
- Stud/joist spacing (12", 16", 24" OC)
- Header sizes per span range
- MEP penetration limits (max hole size, edge distance)
- Panel size/weight constraints

**Rationale**:
- Code requirements vary by jurisdiction
- Engineering judgment must drive design
- Configurability enables flexibility

### 6. Level of Detail
**Decision**: **LOD 350** (current), with clear path to **LOD 400**

Current (LOD 350):
- Accurate centerlines for all members
- Correct profiles assigned
- Proper spacing and positioning
- Complete opening framing

Future (LOD 400):
- Connection hardware specification
- Fastener schedules
- Sheathing with nailing patterns
- CNC-ready geometry

**Rationale**:
- Current LOD enables MEP routing and visualization
- Connection details can be added incrementally
- CNC export as specialized output module

---

## References

- Current codebase: `src/timber_framing_generator/`
- Wall framing patterns: `docs/ai/ai-modular-architecture-plan.md`
- MEP connectors: `docs/ai/ai-mep-connectors-reference.md`
- RiR patterns: `docs/ai/ai-rir-revit-patterns.md`
