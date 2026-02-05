# PRP-016: MEP Routing OAHS Core Algorithm

## Overview

**Feature**: OAHS (Obstacle-Aware Hanan Sequential) routing algorithm core
**Branch**: `feature/mep-routing-phase6-oahs`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 6)

## Problem Statement

The OAHS algorithm orchestrates the complete MEP routing process:

1. **Connector Sequencing**: Order connectors by system priority
2. **Sequential Routing**: Route each connector considering previous routes
3. **Occupancy Updates**: Mark routed segments to prevent conflicts
4. **Conflict Resolution**: Handle cases where routing fails
5. **Route Assembly**: Combine individual paths into complete routes

## Background: OAHS Algorithm

OAHS routes connectors sequentially, updating occupancy after each route:

```
1. Sort connectors by priority (sanitary > power > data)
2. For each connector:
   a. Find best target using heuristic
   b. Update graph with current occupancy
   c. Find path using A* or Hanan MST
   d. If path found:
      - Reserve space in occupancy map
      - Add route to results
   e. Else:
      - Try alternative targets
      - Mark as failed if all options exhausted
3. Return all successful routes
```

## Solution Design

### 1. OAHSRouter Class

```python
class OAHSRouter:
    """
    OAHS (Obstacle-Aware Hanan Sequential) routing algorithm.

    Orchestrates the complete routing process from connectors to routes.
    """

    def __init__(
        self,
        mdg: MultiDomainGraph,
        occupancy: OccupancyMap,
        heuristic_registry: Dict[str, TargetHeuristic]
    ):
        self.mdg = mdg
        self.occupancy = occupancy
        self.heuristics = heuristic_registry

    def route_all(
        self,
        connectors: List[ConnectorInfo],
        targets: List[RoutingTarget]
    ) -> RoutingResult:
        """Route all connectors to appropriate targets."""

    def route_single(
        self,
        connector: ConnectorInfo,
        available_targets: List[RoutingTarget]
    ) -> Optional[Route]:
        """Route a single connector."""
```

### 2. ConnectorSequencer Class

```python
class ConnectorSequencer:
    """
    Orders connectors for sequential routing.

    Priority order:
    1. Sanitary (gravity-dependent, most constrained)
    2. Vent (connected to sanitary)
    3. Supply (pressure-driven, flexible)
    4. Power (shared paths with supply)
    5. Data (most flexible)
    """

    SYSTEM_PRIORITY = {
        "sanitary_drain": 1,
        "sanitary_vent": 2,
        "domestic_hot_water": 3,
        "domestic_cold_water": 4,
        "power": 5,
        "data": 6,
        "lighting": 7,
    }

    def sequence(
        self,
        connectors: List[ConnectorInfo]
    ) -> List[ConnectorInfo]:
        """Sort connectors by routing priority."""
```

### 3. RoutingResult Class

```python
@dataclass
class RoutingResult:
    """
    Complete result of OAHS routing operation.

    Attributes:
        routes: Successfully routed paths
        failed: Connectors that couldn't be routed
        statistics: Routing statistics (time, conflicts, etc.)
        occupancy_map: Final occupancy state
    """
    routes: List[Route]
    failed: List[FailedConnector]
    statistics: RoutingStatistics
    occupancy_map: OccupancyMap
```

### 4. ConflictResolver Class

```python
class ConflictResolver:
    """
    Handles routing conflicts and failures.

    Strategies:
    - Reroute with blocked nodes
    - Try alternative targets
    - Request manual intervention
    """

    def resolve(
        self,
        connector: ConnectorInfo,
        failed_attempts: List[Route],
        occupancy: OccupancyMap
    ) -> Optional[Route]:
        """Attempt to resolve a routing conflict."""
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py              # Add new exports
    oahs_router.py           # OAHSRouter, ConnectorSequencer
    routing_result.py        # RoutingResult, FailedConnector
    conflict_resolver.py     # ConflictResolver

tests/mep/routing/
    test_oahs_router.py      # Unit tests
```

## Implementation Steps

### Step 1: Data Structures
- RoutingResult dataclass
- FailedConnector dataclass
- RoutingStatistics dataclass

### Step 2: Connector Sequencing
- Priority ordering
- Same-system grouping
- Spatial clustering

### Step 3: Core OAHS Loop
- Sequential routing
- Occupancy updates
- Progress tracking

### Step 4: Conflict Resolution
- Reroute attempts
- Target alternatives
- Failure handling

### Step 5: Tests
- Single connector routing
- Multi-connector sequencing
- Conflict scenarios
- Integration tests

## Algorithm Details

### Priority Ordering

Systems are routed in order of constraint level:

| Priority | System | Reason |
|----------|--------|--------|
| 1 | Sanitary Drain | Gravity slope requirement |
| 2 | Sanitary Vent | Must connect to drain |
| 3 | DHW | Temperature constraints |
| 4 | DCW | Less constrained than DHW |
| 5 | Power | Flexible routing |
| 6 | Data | Most flexible |

### Occupancy Update

After each successful route:
```python
def update_occupancy(route: Route, occupancy: OccupancyMap):
    for segment in route.segments:
        occupancy.reserve_segment(
            domain_id=segment.domain_id,
            start=segment.start,
            end=segment.end,
            diameter=route.pipe_diameter,
            route_id=route.id
        )
```

### Conflict Resolution Strategies

1. **Reroute with blocked nodes**: Mark conflicting nodes as blocked
2. **Alternative target**: Try next-best target from heuristic
3. **Larger clearance**: Increase pipe diameter in occupancy check
4. **Manual flag**: Mark for user intervention if all else fails

## Test Cases

### Single Connector
1. Route to nearest target
2. Route to prioritized target
3. Route blocked - find alternative

### Multi-Connector Sequencing
1. Two connectors same system
2. Two connectors different systems
3. Priority ordering verified

### Conflict Resolution
1. First route blocks second - reroute succeeds
2. All paths blocked - alternative target used
3. Complete failure - marked as failed

### Integration
1. Bathroom layout (toilet, sink, shower)
2. Kitchen layout (sink, dishwasher, disposal)
3. Electrical panel distribution

## Exit Criteria

- [ ] RoutingResult and related data structures
- [ ] ConnectorSequencer with priority ordering
- [ ] OAHSRouter core loop
- [ ] Occupancy updates after routing
- [ ] Conflict resolution strategies
- [ ] Integration with Phase 1-5 components
- [ ] All tests passing

## Dependencies

- Phase 1: OccupancyMap, RoutingDomain
- Phase 2: TargetHeuristics, ConnectorInfo
- Phase 3: MultiDomainGraph
- Phase 4: HananMST
- Phase 5: AStarPathfinder
