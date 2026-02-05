# PRP-013: MEP Routing Graph Construction

## Overview

**Feature**: Multi-domain graph construction for MEP routing
**Branch**: `feature/mep-routing-phase3-graph`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 3)

## Problem Statement

The MEP routing solver needs to construct graphs that represent:
1. **Wall cavities**: 2D routing planes in UV space with stud obstacles
2. **Floor cavities**: 2D routing planes in XY space with joist obstacles
3. **Transitions**: Connections between domains at physical intersections

The graphs must:
- Mark obstacles (studs, joists) that require penetration
- Generate routing channels between framing members
- Connect domains at transition points (wall corners, wall-floor intersections)
- Support integration with existing WallData and cell decomposition structures

## Solution Design

### 1. Wall Routing Graph Builder

Builds a 2D grid graph for wall cavity routing in UV coordinates.

```python
class WallGraphBuilder:
    """
    Builds routing graphs for wall cavities.

    Creates nodes at routing points (stud bay centers, opening edges)
    and edges along valid routing paths (between studs, through studs
    with penetration).
    """

    def __init__(self, domain: RoutingDomain, grid_resolution: float = 0.5):
        self.domain = domain
        self.resolution = grid_resolution  # Grid spacing in feet

    def build_grid_graph(
        self,
        occupancy: Optional[OccupancyMap] = None
    ) -> nx.Graph:
        """Build grid graph with obstacle marking."""

    def add_terminal_nodes(
        self,
        graph: nx.Graph,
        terminals: List[Tuple[float, float]]
    ) -> List[int]:
        """Add terminal nodes (fixtures, targets) to graph."""

    def mark_stud_obstacles(
        self,
        graph: nx.Graph,
        studs: List[Obstacle]
    ) -> None:
        """Mark edges that cross studs (penetration required)."""
```

### 2. Floor Routing Graph Builder

Builds a 2D grid graph for floor cavity routing in XY coordinates.

```python
class FloorGraphBuilder:
    """
    Builds routing graphs for floor cavities.

    Floor routing considers:
    - Joist/truss web opening zones
    - Penetration size limits through joists
    - Clear zones for ductwork and large pipes
    """

    def __init__(self, domain: RoutingDomain, grid_resolution: float = 1.0):
        self.domain = domain
        self.resolution = grid_resolution

    def build_grid_graph(
        self,
        occupancy: Optional[OccupancyMap] = None
    ) -> nx.Graph:
        """Build grid graph with joist obstacle marking."""

    def mark_joist_obstacles(
        self,
        graph: nx.Graph,
        joists: List[Obstacle]
    ) -> None:
        """Mark edges that cross joists."""
```

### 3. Transition Generator

Creates transition edges between domains.

```python
class TransitionGenerator:
    """
    Generates transition nodes and edges between routing domains.

    Handles:
    - Wall-to-floor transitions at base plates
    - Wall-to-wall transitions at corners
    - Wall-to-shaft transitions
    """

    def generate_wall_to_floor_transitions(
        self,
        wall_domain: RoutingDomain,
        floor_domain: RoutingDomain,
        wall_graph: nx.Graph,
        floor_graph: nx.Graph
    ) -> List[TransitionEdge]:
        """Generate transitions at wall base."""

    def generate_wall_to_wall_transitions(
        self,
        wall_a: RoutingDomain,
        wall_b: RoutingDomain,
        graph_a: nx.Graph,
        graph_b: nx.Graph
    ) -> List[TransitionEdge]:
        """Generate transitions at wall corners."""
```

### 4. Unified Graph Builder

Assembles the complete multi-domain graph.

```python
class UnifiedGraphBuilder:
    """
    Builds the complete routing graph from wall and floor domains.

    Integrates with WallData and cell decomposition for framing info.
    """

    def build_from_walls(
        self,
        walls_data: List[Dict],
        floor_bounds: Optional[Tuple] = None,
        connectors: Optional[List[ConnectorInfo]] = None,
        targets: Optional[List[RoutingTarget]] = None
    ) -> MultiDomainGraph:
        """Build complete graph from wall data."""

    def build_from_json(
        self,
        walls_json: str,
        cells_json: Optional[str] = None
    ) -> MultiDomainGraph:
        """Build graph from JSON input."""
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py              # Add new exports
    graph_builder.py         # Main graph building interface
    wall_graph.py            # WallGraphBuilder
    floor_graph.py           # FloorGraphBuilder
    transition_generator.py  # TransitionGenerator

scripts/
    gh_mep_graph_builder.py  # GHPython component

tests/mep/routing/
    test_graph_builder.py    # Integration tests
    test_wall_graph.py       # Wall graph unit tests
    test_floor_graph.py      # Floor graph unit tests
```

## Implementation Steps

### Step 1: Wall Graph Builder
- Grid generation in UV space
- Stud obstacle marking
- Penetration cost edges

### Step 2: Floor Graph Builder
- Grid generation in XY space
- Joist obstacle marking
- Web opening zones

### Step 3: Transition Generator
- Wall-floor transitions
- Wall-wall corner transitions

### Step 4: Unified Graph Builder
- Multi-domain assembly
- WallData integration

### Step 5: GHPython Component
- Graph visualization
- Debug output

### Step 6: Tests
- Unit tests per builder
- Integration tests

## Grid Resolution Strategy

Wall cavity grid:
- Horizontal (U): 4" increments (0.333 ft) - matches typical stud bay
- Vertical (V): 6" increments (0.5 ft) - standard pipe/conduit spacing

Floor cavity grid:
- Both directions: 12" increments (1.0 ft) - joist spacing

## Edge Costs

| Edge Type | Base Cost | Notes |
|-----------|-----------|-------|
| Horizontal in-bay | 1.0 × length | Easy routing |
| Vertical in-bay | 1.0 × length | Easy routing |
| Through stud | 5.0 × length | Penetration penalty |
| Through joist | 3.0 × length | Web opening |
| Transition | 2.0 | Domain change overhead |

## GHPython Component Design

### gh_mep_graph_builder.py

**Inputs**:
| Name | Type | Description |
|------|------|-------------|
| walls_json | str | Wall geometry JSON |
| cells_json | str | Optional cell decomposition JSON |
| connectors_json | str | Optional connector positions |
| targets_json | str | Optional target positions |
| config | str | Grid resolution, etc. |
| run | bool | Execute toggle |

**Outputs**:
| Name | Type | Description |
|------|------|-------------|
| graph_json | str | Serialized graph for debugging |
| node_points | Point3d[] | Graph nodes for visualization |
| edge_lines | Line[] | Graph edges for visualization |
| transition_lines | Line[] | Cross-domain transitions |
| debug_info | str | Statistics and debug info |

## Test Cases

### Wall Graph Tests
1. Empty wall - no obstacles
2. Wall with studs at 16" OC
3. Wall with opening (door/window)
4. Multiple stud bays

### Floor Graph Tests
1. Empty floor
2. Floor with joists at 16" OC
3. Floor with penetration zones

### Transition Tests
1. Single wall to floor
2. Two walls at corner
3. Three walls meeting at T-junction

### Integration Tests
1. Build from WallData JSON
2. Add connectors and targets as terminals
3. Verify path exists between all terminals

## Exit Criteria

- [x] WallGraphBuilder creates correct UV grid
- [ ] FloorGraphBuilder creates correct XY grid
- [ ] Stud/joist obstacles marked with penetration cost
- [ ] Transitions generated at wall-floor intersections
- [ ] Transitions generated at wall-wall corners
- [ ] Integration with WallData JSON working
- [ ] GHPython component displays graph
- [ ] All unit tests passing

## Dependencies

- Phase 1: Core structures (MultiDomainGraph, RoutingDomain, Obstacle)
- Phase 2: Target generator (for terminal positions)
- networkx library for graph operations
