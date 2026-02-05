# PRP-017: MEP Routing Sequential Orchestrator

## Overview

**Feature**: Sequential Orchestrator for Multi-Zone, Multi-Trade Routing
**Branch**: `feature/mep-routing-phase7-orchestrator`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 7)

## Problem Statement

The OAHS router (Phase 6) handles individual connector routing. Phase 7 adds:

1. **Zone Partitioning**: Divide building into independent routing zones
2. **Trade Sequencing**: Route trades in priority order (Plumbing > HVAC > Electrical)
3. **Cross-Zone Boundaries**: Handle routes that span multiple zones
4. **Result Aggregation**: Combine zone results into unified output
5. **GHPython Integration**: Main `gh_mep_router.py` component

## Background: Multi-Trade Orchestration

In real MEP coordination, trades must be routed in sequence:

```
1. Plumbing (most constrained - gravity, large pipes)
2. HVAC (medium constraint - duct sizes, air flow)
3. Electrical (most flexible - small conduits, no gravity)
```

Within each trade, the OAHS router handles individual connectors.

## Solution Design

### 1. SequentialOrchestrator Class

```python
class SequentialOrchestrator:
    """
    Orchestrates multi-zone, multi-trade MEP routing.

    Coordinates routing across building zones while respecting
    trade priorities and spatial constraints.
    """

    def __init__(
        self,
        trade_config: TradeConfig,
        zone_strategy: ZonePartitionStrategy = None
    ):
        self.trade_config = trade_config
        self.zone_strategy = zone_strategy or DefaultZoneStrategy()
        self.routers: Dict[str, OAHSRouter] = {}

    def route_building(
        self,
        connectors: List[ConnectorInfo],
        walls: List[Dict],
        targets: List[RoutingTarget]
    ) -> OrchestrationResult:
        """Route all MEP systems for entire building."""

    def route_zone(
        self,
        zone_id: str,
        connectors: List[ConnectorInfo],
        targets: List[RoutingTarget]
    ) -> RoutingResult:
        """Route a single zone."""
```

### 2. TradeConfig Class

```python
@dataclass
class TradeConfig:
    """
    Configuration for trade prioritization and routing.

    Attributes:
        trade_order: List of trade names in routing priority
        trade_systems: Mapping from trade to system types
        clearances: Minimum clearances between trades
    """
    trade_order: List[str] = field(default_factory=lambda: [
        "plumbing", "hvac", "electrical"
    ])

    trade_systems: Dict[str, List[str]] = field(default_factory=lambda: {
        "plumbing": ["sanitary_drain", "sanitary_vent", "dhw", "dcw"],
        "hvac": ["supply_air", "return_air", "exhaust"],
        "electrical": ["power", "lighting", "data", "low_voltage"],
    })

    clearances: Dict[str, float] = field(default_factory=lambda: {
        "plumbing": 0.25,  # 3" minimum
        "hvac": 0.5,       # 6" minimum
        "electrical": 0.125,  # 1.5" minimum
    })
```

### 3. ZonePartitionStrategy

```python
class ZonePartitionStrategy(ABC):
    """Base class for zone partitioning strategies."""

    @abstractmethod
    def partition(
        self,
        walls: List[Dict],
        connectors: List[ConnectorInfo]
    ) -> List[RoutingZone]:
        """Partition building into routing zones."""


class DefaultZoneStrategy(ZonePartitionStrategy):
    """
    Default strategy: one zone per floor/level.
    """
    def partition(self, walls, connectors) -> List[RoutingZone]:
        # Group by floor level
        pass


class RoomBasedStrategy(ZonePartitionStrategy):
    """
    Alternative: one zone per room/space.
    """
    def partition(self, walls, connectors) -> List[RoutingZone]:
        # Group by room boundaries
        pass
```

### 4. OrchestrationResult

```python
@dataclass
class OrchestrationResult:
    """
    Complete result from orchestrated routing.

    Attributes:
        zone_results: Results per zone
        trade_results: Results per trade
        statistics: Aggregate statistics
        cross_zone_routes: Routes spanning zones
    """
    zone_results: Dict[str, RoutingResult]
    trade_results: Dict[str, RoutingResult]
    statistics: OrchestrationStatistics
    cross_zone_routes: List[Route]

    def get_all_routes(self) -> List[Route]:
        """Get all routes flattened."""

    def get_routes_by_trade(self, trade: str) -> List[Route]:
        """Get routes for a specific trade."""

    def to_json(self) -> str:
        """Export as JSON for downstream processing."""
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py              # Add new exports
    orchestrator.py          # SequentialOrchestrator, ZoneStrategy
    trade_config.py          # TradeConfig, trade-related types

scripts/
    gh_mep_router.py         # Main GHPython routing component

tests/mep/routing/
    test_orchestrator.py     # Unit and integration tests
```

## Implementation Steps

### Step 1: Trade Configuration
- TradeConfig dataclass
- Trade priority ordering
- Trade-to-system mapping

### Step 2: Zone Partitioning
- ZonePartitionStrategy base class
- DefaultZoneStrategy (by floor)
- RoutingZone dataclass

### Step 3: Sequential Orchestrator
- SequentialOrchestrator class
- Trade-by-trade routing loop
- Occupancy sharing between trades

### Step 4: Result Aggregation
- OrchestrationResult dataclass
- OrchestrationStatistics
- JSON export

### Step 5: GHPython Component
- gh_mep_router.py component
- Input: connectors_json, walls_json, targets_json
- Output: routes_json

### Step 6: Integration Tests
- Multi-trade bathroom scenario
- Multi-zone building scenario
- Cross-zone route validation

## Algorithm Details

### Trade Routing Sequence

```python
def route_building(self, connectors, walls, targets):
    # 1. Partition into zones
    zones = self.zone_strategy.partition(walls, connectors)

    # 2. Build graphs per zone
    graphs = {z.id: self._build_graph(z, walls) for z in zones}

    # 3. Initialize shared occupancy
    occupancy = OccupancyMap()

    # 4. Route each trade in priority order
    for trade in self.trade_config.trade_order:
        trade_connectors = self._filter_by_trade(connectors, trade)
        trade_targets = self._filter_targets_for_trade(targets, trade)

        for zone in zones:
            zone_connectors = self._filter_by_zone(trade_connectors, zone)
            result = self._route_zone(zone, zone_connectors, trade_targets)

            # Update shared occupancy
            self._apply_occupancy(occupancy, result.routes)

    # 5. Aggregate results
    return self._aggregate_results(zone_results, trade_results)
```

### Cross-Zone Boundary Handling

When a connector's target is in a different zone:

1. Find transition points between zones
2. Route from connector to zone boundary
3. Route from boundary to target in next zone
4. Join segments at boundary

## Test Cases

### Trade Sequencing
1. Plumbing routes first, uses optimal paths
2. Electrical routes around plumbing
3. Priority is respected

### Zone Partitioning
1. Single floor → single zone
2. Multi-floor → zone per floor
3. Custom strategy works

### Result Aggregation
1. All zone routes combined
2. Statistics are accurate
3. JSON export is valid

### GHPython Component
1. Accepts valid JSON inputs
2. Produces valid routes_json output
3. Handles missing inputs gracefully

## Exit Criteria

- [ ] TradeConfig with priority ordering
- [ ] ZonePartitionStrategy base and default implementation
- [ ] SequentialOrchestrator routing loop
- [ ] OrchestrationResult with aggregation
- [ ] gh_mep_router.py GHPython component
- [ ] Integration tests passing
- [ ] All unit tests passing

## Dependencies

- Phase 1: OccupancyMap, RoutingDomain
- Phase 2: TargetHeuristics, ConnectorInfo
- Phase 3: MultiDomainGraph, UnifiedGraphBuilder
- Phase 6: OAHSRouter, RoutingResult
