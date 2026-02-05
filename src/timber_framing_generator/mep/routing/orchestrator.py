# File: src/timber_framing_generator/mep/routing/orchestrator.py
"""
Sequential orchestrator for multi-zone, multi-trade MEP routing.

Coordinates routing across building zones while respecting
trade priorities and spatial constraints.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

from .trade_config import TradeConfig, Trade, RoutingZone, create_default_trade_config
from .routing_result import RoutingResult, RoutingStatistics
from .route_segment import Route
from .heuristics.base import ConnectorInfo
from .targets import RoutingTarget
from .occupancy import OccupancyMap

if TYPE_CHECKING:
    from .oahs_router import OAHSRouter
    from .graph import MultiDomainGraph

logger = logging.getLogger(__name__)


# =============================================================================
# Zone Partitioning Strategies
# =============================================================================

class ZonePartitionStrategy(ABC):
    """
    Base class for zone partitioning strategies.

    Defines how to divide a building into independent routing zones.
    """

    @abstractmethod
    def partition(
        self,
        walls: List[Dict],
        connectors: List[ConnectorInfo]
    ) -> List[RoutingZone]:
        """
        Partition building into routing zones.

        Args:
            walls: List of wall data dictionaries
            connectors: List of connectors to route

        Returns:
            List of RoutingZone objects
        """
        pass


class DefaultZoneStrategy(ZonePartitionStrategy):
    """
    Default strategy: one zone per floor level.

    Groups walls and connectors by their Z elevation into floor-based zones.
    """

    def __init__(self, floor_height: float = 10.0):
        """
        Initialize default zone strategy.

        Args:
            floor_height: Typical floor height for grouping (feet)
        """
        self.floor_height = floor_height

    def partition(
        self,
        walls: List[Dict],
        connectors: List[ConnectorInfo]
    ) -> List[RoutingZone]:
        """Partition by floor level."""
        if not walls and not connectors:
            return []

        # Group by floor level
        floor_groups: Dict[int, Dict] = {}

        # Process walls
        for wall in walls:
            z = wall.get("base_elevation", 0.0)
            floor = int(z / self.floor_height)
            if floor not in floor_groups:
                floor_groups[floor] = {
                    "walls": [],
                    "connectors": [],
                    "min_x": float("inf"),
                    "max_x": float("-inf"),
                    "min_y": float("inf"),
                    "max_y": float("-inf"),
                }
            floor_groups[floor]["walls"].append(wall.get("id", ""))
            self._update_bounds(floor_groups[floor], wall)

        # Process connectors
        for conn in connectors:
            z = conn.location[2] if len(conn.location) > 2 else 0.0
            floor = int(z / self.floor_height)
            if floor not in floor_groups:
                floor_groups[floor] = {
                    "walls": [],
                    "connectors": [],
                    "min_x": float("inf"),
                    "max_x": float("-inf"),
                    "min_y": float("inf"),
                    "max_y": float("-inf"),
                }
            floor_groups[floor]["connectors"].append(conn.id)
            # Update bounds from connector location
            x, y = conn.location[0], conn.location[1]
            grp = floor_groups[floor]
            grp["min_x"] = min(grp["min_x"], x)
            grp["max_x"] = max(grp["max_x"], x)
            grp["min_y"] = min(grp["min_y"], y)
            grp["max_y"] = max(grp["max_y"], y)

        # Create zones
        zones = []
        for floor, data in sorted(floor_groups.items()):
            bounds = (
                data["min_x"],
                data["max_x"],
                data["min_y"],
                data["max_y"],
            )
            zone = RoutingZone(
                id=f"floor_{floor}",
                name=f"Floor {floor}",
                level=floor,
                bounds=bounds,
                wall_ids=data["walls"],
                connector_ids=data["connectors"],
            )
            zones.append(zone)

        return zones

    def _update_bounds(self, group: Dict, wall: Dict):
        """Update zone bounds from wall data."""
        # Try to get wall geometry bounds
        start = wall.get("start_point", [0, 0, 0])
        end = wall.get("end_point", [0, 0, 0])

        for pt in [start, end]:
            if len(pt) >= 2:
                group["min_x"] = min(group["min_x"], pt[0])
                group["max_x"] = max(group["max_x"], pt[0])
                group["min_y"] = min(group["min_y"], pt[1])
                group["max_y"] = max(group["max_y"], pt[1])


class SingleZoneStrategy(ZonePartitionStrategy):
    """
    Simple strategy: entire building as one zone.

    Useful for small buildings or when zone boundaries don't matter.
    """

    def partition(
        self,
        walls: List[Dict],
        connectors: List[ConnectorInfo]
    ) -> List[RoutingZone]:
        """Create single zone for entire building."""
        # Collect all IDs
        wall_ids = [w.get("id", "") for w in walls]
        connector_ids = [c.id for c in connectors]

        # Calculate overall bounds
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")

        for wall in walls:
            start = wall.get("start_point", [0, 0, 0])
            end = wall.get("end_point", [0, 0, 0])
            for pt in [start, end]:
                if len(pt) >= 2:
                    min_x = min(min_x, pt[0])
                    max_x = max(max_x, pt[0])
                    min_y = min(min_y, pt[1])
                    max_y = max(max_y, pt[1])

        for conn in connectors:
            x, y = conn.location[0], conn.location[1]
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

        return [RoutingZone(
            id="building",
            name="Entire Building",
            level=0,
            bounds=(min_x, max_x, min_y, max_y),
            wall_ids=wall_ids,
            connector_ids=connector_ids,
        )]


# =============================================================================
# Orchestration Result
# =============================================================================

@dataclass
class OrchestrationStatistics:
    """
    Statistics for orchestrated routing across zones and trades.

    Attributes:
        total_zones: Number of zones processed
        total_trades: Number of trades processed
        total_connectors: Total connectors across all zones
        successful_routes: Total successful routes
        failed_routes: Total failed routes
        total_length: Total route length
        total_cost: Total route cost
        orchestration_time_ms: Time for complete orchestration
        zone_times_ms: Time per zone
        trade_times_ms: Time per trade
    """
    total_zones: int = 0
    total_trades: int = 0
    total_connectors: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    total_length: float = 0.0
    total_cost: float = 0.0
    orchestration_time_ms: float = 0.0
    zone_times_ms: Dict[str, float] = field(default_factory=dict)
    trade_times_ms: Dict[str, float] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_connectors == 0:
            return 0.0
        return (self.successful_routes / self.total_connectors) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_zones": self.total_zones,
            "total_trades": self.total_trades,
            "total_connectors": self.total_connectors,
            "successful_routes": self.successful_routes,
            "failed_routes": self.failed_routes,
            "success_rate": self.success_rate,
            "total_length": self.total_length,
            "total_cost": self.total_cost,
            "orchestration_time_ms": self.orchestration_time_ms,
            "zone_times_ms": self.zone_times_ms,
            "trade_times_ms": self.trade_times_ms,
        }


@dataclass
class OrchestrationResult:
    """
    Complete result from orchestrated routing.

    Attributes:
        zone_results: Results per zone
        trade_results: Results per trade
        statistics: Aggregate statistics
        cross_zone_routes: Routes spanning zones (future)
        zones: Zone definitions used
    """
    zone_results: Dict[str, RoutingResult] = field(default_factory=dict)
    trade_results: Dict[str, RoutingResult] = field(default_factory=dict)
    statistics: OrchestrationStatistics = field(
        default_factory=OrchestrationStatistics
    )
    cross_zone_routes: List[Route] = field(default_factory=list)
    zones: List[RoutingZone] = field(default_factory=list)

    def get_all_routes(self) -> List[Route]:
        """Get all routes flattened across zones and trades."""
        routes = []
        for result in self.zone_results.values():
            routes.extend(result.routes)
        return routes

    def get_routes_by_trade(self, trade: str) -> List[Route]:
        """Get routes for a specific trade."""
        if trade in self.trade_results:
            return self.trade_results[trade].routes
        return []

    def get_routes_by_zone(self, zone_id: str) -> List[Route]:
        """Get routes for a specific zone."""
        if zone_id in self.zone_results:
            return self.zone_results[zone_id].routes
        return []

    def is_complete(self) -> bool:
        """Check if all connectors were successfully routed."""
        return all(r.is_complete() for r in self.zone_results.values())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "zone_results": {
                k: v.to_dict() for k, v in self.zone_results.items()
            },
            "trade_results": {
                k: v.to_dict() for k, v in self.trade_results.items()
            },
            "statistics": self.statistics.to_dict(),
            "cross_zone_routes": [r.to_dict() for r in self.cross_zone_routes],
            "zones": [z.to_dict() for z in self.zones],
            "is_complete": self.is_complete(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Export as JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# Sequential Orchestrator
# =============================================================================

class SequentialOrchestrator:
    """
    Orchestrates multi-zone, multi-trade MEP routing.

    Coordinates routing across building zones while respecting
    trade priorities and spatial constraints.
    """

    def __init__(
        self,
        trade_config: Optional[TradeConfig] = None,
        zone_strategy: Optional[ZonePartitionStrategy] = None
    ):
        """
        Initialize the orchestrator.

        Args:
            trade_config: Trade configuration (uses default if None)
            zone_strategy: Zone partitioning strategy (uses DefaultZoneStrategy if None)
        """
        self.trade_config = trade_config or create_default_trade_config()
        self.zone_strategy = zone_strategy or DefaultZoneStrategy()
        self._occupancy = OccupancyMap()

    def route_building(
        self,
        connectors: List[ConnectorInfo],
        walls: List[Dict],
        targets: List[RoutingTarget],
        mdg_factory: Optional[callable] = None
    ) -> OrchestrationResult:
        """
        Route all MEP systems for entire building.

        Args:
            connectors: All connectors to route
            walls: All wall data
            targets: All routing targets
            mdg_factory: Optional factory to create MultiDomainGraph per zone

        Returns:
            OrchestrationResult with all routes and statistics
        """
        start_time = time.time()
        result = OrchestrationResult()

        # 1. Partition into zones
        zones = self.zone_strategy.partition(walls, connectors)
        result.zones = zones
        result.statistics.total_zones = len(zones)
        logger.info(f"Partitioned building into {len(zones)} zones")

        # 2. Get enabled trades
        enabled_trades = self.trade_config.get_enabled_trades()
        result.statistics.total_trades = len(enabled_trades)

        # 3. Build connector lookup
        connector_by_id = {c.id: c for c in connectors}
        target_by_id = {t.id: t for t in targets}

        # 4. Route each trade in priority order
        for trade in enabled_trades:
            trade_start = time.time()
            trade_result = RoutingResult()
            trade_systems = self.trade_config.get_systems_for_trade(trade)

            # Filter connectors for this trade
            trade_connectors = [
                c for c in connectors
                if c.system_type.lower() in [s.lower() for s in trade_systems]
            ]

            logger.info(
                f"Routing trade {trade.value}: {len(trade_connectors)} connectors"
            )

            # Route each zone
            for zone in zones:
                zone_start = time.time()

                # Get connectors in this zone
                zone_connectors = [
                    c for c in trade_connectors
                    if c.id in zone.connector_ids or self._connector_in_zone(c, zone)
                ]

                if not zone_connectors:
                    continue

                # Route zone
                zone_result = self._route_zone_for_trade(
                    zone, zone_connectors, targets, trade, mdg_factory
                )

                # Merge into zone results
                if zone.id not in result.zone_results:
                    result.zone_results[zone.id] = RoutingResult()
                self._merge_results(result.zone_results[zone.id], zone_result)

                # Merge into trade results
                self._merge_results(trade_result, zone_result)

                # Track zone time
                zone_time = (time.time() - zone_start) * 1000
                result.statistics.zone_times_ms[zone.id] = (
                    result.statistics.zone_times_ms.get(zone.id, 0) + zone_time
                )

            result.trade_results[trade.value] = trade_result
            trade_time = (time.time() - trade_start) * 1000
            result.statistics.trade_times_ms[trade.value] = trade_time

        # 5. Aggregate statistics
        self._aggregate_statistics(result)
        result.statistics.orchestration_time_ms = (time.time() - start_time) * 1000

        return result

    def route_zone(
        self,
        zone: RoutingZone,
        connectors: List[ConnectorInfo],
        targets: List[RoutingTarget],
        mdg_factory: Optional[callable] = None
    ) -> RoutingResult:
        """
        Route a single zone with all trades.

        Args:
            zone: Zone to route
            connectors: Connectors in this zone
            targets: Available targets
            mdg_factory: Optional factory to create MultiDomainGraph

        Returns:
            RoutingResult for the zone
        """
        result = RoutingResult()

        for trade in self.trade_config.get_enabled_trades():
            trade_systems = self.trade_config.get_systems_for_trade(trade)
            trade_connectors = [
                c for c in connectors
                if c.system_type.lower() in [s.lower() for s in trade_systems]
            ]

            if trade_connectors:
                trade_result = self._route_zone_for_trade(
                    zone, trade_connectors, targets, trade, mdg_factory
                )
                self._merge_results(result, trade_result)

        return result

    def _route_zone_for_trade(
        self,
        zone: RoutingZone,
        connectors: List[ConnectorInfo],
        targets: List[RoutingTarget],
        trade: Trade,
        mdg_factory: Optional[callable]
    ) -> RoutingResult:
        """Route connectors in a zone for a specific trade."""
        from .oahs_router import OAHSRouter

        # Filter targets for trade systems
        trade_systems = self.trade_config.get_systems_for_trade(trade)
        trade_targets = [
            t for t in targets
            if self._target_serves_trade(t, trade_systems)
        ]

        if not trade_targets:
            # No targets for this trade - mark all as failed
            result = RoutingResult()
            for conn in connectors:
                result.add_failure(
                    conn,
                    f"No targets available for trade {trade.value}",
                    [],
                    "NO_TARGETS"
                )
            return result

        # Create or get router
        # For now, create a minimal graph and router
        # In full implementation, mdg_factory would provide proper graph
        if mdg_factory:
            mdg = mdg_factory(zone)
        else:
            # Create minimal graph structure
            from .graph import MultiDomainGraph
            mdg = MultiDomainGraph()

        router = OAHSRouter(mdg, occupancy=self._occupancy)

        # Route connectors
        result = router.route_all(connectors, trade_targets)

        # Update shared occupancy from successful routes
        for route in result.routes:
            self._reserve_route_occupancy(route, trade)

        return result

    def _target_serves_trade(
        self,
        target: RoutingTarget,
        trade_systems: List[str]
    ) -> bool:
        """Check if a target can serve any system in the trade."""
        for system in trade_systems:
            if target.can_serve_system(system):
                return True
        return False

    def _connector_in_zone(
        self,
        connector: ConnectorInfo,
        zone: RoutingZone
    ) -> bool:
        """Check if connector is within zone bounds."""
        x, y = connector.location[0], connector.location[1]
        return zone.contains_point(x, y)

    def _reserve_route_occupancy(self, route: Route, trade: Trade) -> None:
        """Reserve space in occupancy map for a route."""
        from .occupancy import OccupiedSegment
        clearance = self.trade_config.get_clearance(trade)

        for segment in route.segments:
            occupied = OccupiedSegment(
                start=segment.start,
                end=segment.end,
                width=clearance * 2,  # Width is diameter
                route_id=route.id,
                trade=trade.value,
            )
            domain_id = segment.domain_id or "default"
            self._occupancy.reserve(domain_id, occupied)

    def _merge_results(
        self,
        target: RoutingResult,
        source: RoutingResult
    ) -> None:
        """Merge source results into target."""
        target.routes.extend(source.routes)
        target.failed.extend(source.failed)
        target.statistics.successful_routes += source.statistics.successful_routes
        target.statistics.failed_routes += source.statistics.failed_routes
        target.statistics.total_length += source.statistics.total_length
        target.statistics.total_cost += source.statistics.total_cost

    def _aggregate_statistics(self, result: OrchestrationResult) -> None:
        """Aggregate statistics from all zone results."""
        stats = result.statistics
        for zone_result in result.zone_results.values():
            stats.total_connectors += (
                zone_result.statistics.successful_routes +
                zone_result.statistics.failed_routes
            )
            stats.successful_routes += zone_result.statistics.successful_routes
            stats.failed_routes += zone_result.statistics.failed_routes
            stats.total_length += zone_result.statistics.total_length
            stats.total_cost += zone_result.statistics.total_cost

    def get_occupancy(self) -> OccupancyMap:
        """Get the current occupancy map."""
        return self._occupancy

    def reset_occupancy(self) -> None:
        """Reset the occupancy map for a fresh routing session."""
        self._occupancy = OccupancyMap()


# =============================================================================
# Factory Functions
# =============================================================================

def create_orchestrator(
    trade_config: Optional[TradeConfig] = None,
    zone_strategy: Optional[ZonePartitionStrategy] = None
) -> SequentialOrchestrator:
    """
    Create a SequentialOrchestrator with given configuration.

    Args:
        trade_config: Trade configuration (uses default if None)
        zone_strategy: Zone partitioning strategy (uses default if None)

    Returns:
        Configured SequentialOrchestrator
    """
    return SequentialOrchestrator(trade_config, zone_strategy)


def create_single_zone_orchestrator(
    trade_config: Optional[TradeConfig] = None
) -> SequentialOrchestrator:
    """
    Create an orchestrator that treats entire building as one zone.

    Args:
        trade_config: Trade configuration

    Returns:
        SequentialOrchestrator with SingleZoneStrategy
    """
    return SequentialOrchestrator(trade_config, SingleZoneStrategy())
