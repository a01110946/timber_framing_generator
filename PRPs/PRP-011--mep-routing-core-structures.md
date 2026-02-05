# PRP-011: MEP Routing Core Data Structures

## Overview

**Feature**: Core data structures for MEP routing solver
**Branch**: `feature/mep-routing-phase1-core`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan

## Problem Statement

The MEP routing solver requires foundational data structures for:
1. Tracking occupied space (preventing routing conflicts)
2. Representing routing domains (wall cavities, floor cavities, shafts)
3. Defining routing targets (wet walls, penetration zones, shafts)
4. Managing multi-domain graphs

## Solution Design

### 1. OccupancyMap

Tracks reserved space in 2D planes to prevent routing conflicts between trades.

```python
@dataclass
class OccupiedSegment:
    route_id: str
    system_type: str
    trade: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    diameter: float
    priority: int

class OccupancyMap:
    def __init__(self):
        self.planes: Dict[str, List[OccupiedSegment]] = {}

    def is_available(plane_id, segment, diameter, clearance) -> Tuple[bool, Optional[str]]
    def reserve(plane_id, segment) -> None
    def release(plane_id, route_id) -> None
    def get_conflicts(plane_id, segment, diameter) -> List[OccupiedSegment]
```

### 2. RoutingDomain

Enumeration and data structures for different routing domains.

```python
class RoutingDomainType(Enum):
    WALL_CAVITY = "wall_cavity"
    FLOOR_CAVITY = "floor_cavity"
    CEILING_CAVITY = "ceiling_cavity"
    SHAFT = "shaft"

@dataclass
class RoutingDomain:
    id: str
    domain_type: RoutingDomainType
    bounds: Tuple[float, float, float, float]  # min_u, max_u, min_v, max_v
    obstacles: List[Obstacle]
    transitions: List[str]  # IDs of connected domains
```

### 3. RoutingTarget

Represents valid destinations for MEP routes.

```python
@dataclass
class RoutingTarget:
    id: str
    target_type: str  # "wet_wall", "floor_penetration", "shaft"
    location: Tuple[float, float, float]
    domain_id: str
    systems_served: List[str]
    capacity: float
    priority: int
```

### 4. MultiDomainGraph

Container for unified routing graph spanning all domains.

```python
@dataclass
class MultiDomainGraph:
    domains: Dict[str, RoutingDomain]
    domain_graphs: Dict[str, nx.Graph]
    transitions: List[TransitionEdge]
    unified_graph: nx.Graph
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py
    occupancy.py      # OccupancyMap, OccupiedSegment
    domains.py        # RoutingDomainType, RoutingDomain, Obstacle
    targets.py        # RoutingTarget, TargetType
    graph.py          # MultiDomainGraph, TransitionEdge

tests/mep/routing/
    __init__.py
    test_occupancy.py
    test_domains.py
    test_targets.py
```

## Implementation Steps

1. Create directory structure
2. Implement `occupancy.py` with OccupancyMap
3. Implement `domains.py` with RoutingDomain
4. Implement `targets.py` with RoutingTarget
5. Implement `graph.py` with MultiDomainGraph
6. Write unit tests
7. Verify all tests pass

## Exit Criteria

- [ ] OccupancyMap can reserve segments and detect conflicts
- [ ] Domain structures support 2D wall and floor planes
- [ ] RoutingTarget supports all MEP system types
- [ ] MultiDomainGraph can hold multiple domain graphs
- [ ] All unit tests pass

## Dependencies

- `networkx` for graph structures
- Existing `MEPConnector` and `MEPRoute` from `core/mep_system.py`
