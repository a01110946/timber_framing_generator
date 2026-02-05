# File: src/timber_framing_generator/mep/routing/oahs_router.py
"""
OAHS (Obstacle-Aware Hanan Sequential) routing algorithm.

Implements the core routing algorithm that:
1. Sequences connectors by priority
2. Routes each connector considering occupancy
3. Updates occupancy after each route
4. Handles conflicts and failures
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any

from .graph import MultiDomainGraph
from .occupancy import OccupancyMap
from .targets import RoutingTarget
from .route_segment import Route, RouteSegment
from .routing_result import RoutingResult, RoutingStatistics, FailedConnector
from .heuristics.base import ConnectorInfo, TargetHeuristic
from .multi_domain_pathfinder import MultiDomainPathfinder

logger = logging.getLogger(__name__)


class ConnectorSequencer:
    """
    Orders connectors for sequential routing.

    Connectors are sorted by system priority:
    1. Sanitary (gravity-dependent, most constrained)
    2. Vent (connected to sanitary)
    3. Supply (pressure-driven)
    4. Power (flexible)
    5. Data (most flexible)

    Within the same priority, connectors are sorted by distance
    to encourage nearby routes.
    """

    # System priority - lower number = higher priority (route first)
    SYSTEM_PRIORITY: Dict[str, int] = {
        "sanitary_drain": 1,
        "sanitary": 1,
        "drain": 1,
        "sanitary_vent": 2,
        "vent": 2,
        "domestic_hot_water": 3,
        "dhw": 3,
        "hot_water": 3,
        "domestic_cold_water": 4,
        "dcw": 4,
        "cold_water": 4,
        "supply": 4,
        "power": 5,
        "electrical": 5,
        "data": 6,
        "network": 6,
        "lighting": 7,
    }

    DEFAULT_PRIORITY: int = 10

    def __init__(self, reference_point: Optional[Tuple[float, float]] = None):
        """
        Initialize sequencer.

        Args:
            reference_point: Optional reference for distance-based sorting
        """
        self.reference_point = reference_point or (0, 0)

    def sequence(self, connectors: List[ConnectorInfo]) -> List[ConnectorInfo]:
        """
        Sort connectors by routing priority.

        Args:
            connectors: List of connectors to sequence

        Returns:
            Sorted list with highest priority first
        """
        def sort_key(conn: ConnectorInfo) -> Tuple[int, float]:
            # Primary: system priority
            system = conn.system_type.lower() if conn.system_type else ""
            priority = self.SYSTEM_PRIORITY.get(system, self.DEFAULT_PRIORITY)

            # Secondary: distance from reference (closer first)
            if conn.location:
                dx = conn.location[0] - self.reference_point[0]
                dy = conn.location[1] - self.reference_point[1]
                distance = (dx * dx + dy * dy) ** 0.5
            else:
                distance = 0

            return (priority, distance)

        return sorted(connectors, key=sort_key)

    def get_priority(self, system_type: str) -> int:
        """Get priority for a system type."""
        system = system_type.lower() if system_type else ""
        return self.SYSTEM_PRIORITY.get(system, self.DEFAULT_PRIORITY)

    def group_by_system(
        self,
        connectors: List[ConnectorInfo]
    ) -> Dict[str, List[ConnectorInfo]]:
        """Group connectors by system type."""
        groups: Dict[str, List[ConnectorInfo]] = {}
        for conn in connectors:
            system = conn.system_type or "unknown"
            if system not in groups:
                groups[system] = []
            groups[system].append(conn)
        return groups


class ConflictResolver:
    """
    Handles routing conflicts and failures.

    Implements strategies to resolve conflicts when a route
    cannot be found:
    1. Reroute with blocked nodes
    2. Try alternative targets
    3. Increase clearance
    4. Mark as unresolvable
    """

    MAX_REROUTE_ATTEMPTS: int = 3
    MAX_ALTERNATIVE_TARGETS: int = 3

    def __init__(
        self,
        pathfinder: MultiDomainPathfinder,
        occupancy: OccupancyMap
    ):
        """
        Initialize conflict resolver.

        Args:
            pathfinder: Multi-domain pathfinder instance
            occupancy: Current occupancy map
        """
        self.pathfinder = pathfinder
        self.occupancy = occupancy
        self.blocked_nodes: Set[int] = set()

    def resolve(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        failed_target_ids: Set[str]
    ) -> Tuple[Optional[Route], str]:
        """
        Attempt to resolve a routing conflict.

        Args:
            connector: The connector to route
            targets: Available targets
            failed_target_ids: Targets already tried

        Returns:
            Tuple of (Route or None, reason string)
        """
        # Try alternative targets
        for target in targets:
            if target.id in failed_target_ids:
                continue

            if len(failed_target_ids) >= self.MAX_ALTERNATIVE_TARGETS:
                break

            route = self._try_route(connector, target)
            if route:
                return route, f"Alternative target: {target.id}"

            failed_target_ids.add(target.id)

        return None, "All alternative targets exhausted"

    def _try_route(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget
    ) -> Optional[Route]:
        """Try to route to a specific target."""
        # Use wall_id as domain_id for connectors
        source_domain = connector.wall_id
        if not source_domain or not target.domain_id:
            return None

        # Extract 2D location from 3D
        conn_loc = (connector.location[0], connector.location[1])

        # Use plane_location for target (2D in domain space)
        target_loc = target.plane_location

        route = self.pathfinder.find_path(
            source_domain,
            conn_loc,
            target.domain_id,
            target_loc,
            route_id=f"route_{connector.id}",
            system_type=connector.system_type
        )

        return route


class OAHSRouter:
    """
    OAHS (Obstacle-Aware Hanan Sequential) routing algorithm.

    Orchestrates the complete routing process:
    1. Sequence connectors by priority
    2. For each connector, find best target and route
    3. Update occupancy after successful routes
    4. Handle conflicts and failures

    Attributes:
        mdg: Multi-domain graph for routing
        occupancy: Occupancy map for space tracking
        heuristics: Registry of target heuristics by system type
    """

    def __init__(
        self,
        mdg: MultiDomainGraph,
        occupancy: Optional[OccupancyMap] = None,
        heuristic_registry: Optional[Dict[str, TargetHeuristic]] = None
    ):
        """
        Initialize OAHS router.

        Args:
            mdg: Multi-domain graph with routing domains
            occupancy: Occupancy map (created if not provided)
            heuristic_registry: Map of system type to heuristic
        """
        self.mdg = mdg
        self.occupancy = occupancy or OccupancyMap()
        self.heuristics = heuristic_registry or {}
        self._pathfinder: Optional[MultiDomainPathfinder] = None
        self._sequencer = ConnectorSequencer()
        self._initialize_pathfinder()

    def _initialize_pathfinder(self) -> None:
        """Initialize the multi-domain pathfinder."""
        if self.mdg.unified_graph is not None:
            self._pathfinder = MultiDomainPathfinder(self.mdg)
        else:
            # Try to build unified graph
            try:
                self.mdg.build_unified_graph()
                self._pathfinder = MultiDomainPathfinder(self.mdg)
            except Exception as e:
                logger.warning(f"Could not initialize pathfinder: {e}")

    def route_all(
        self,
        connectors: List[ConnectorInfo],
        targets: List[RoutingTarget]
    ) -> RoutingResult:
        """
        Route all connectors to appropriate targets.

        Args:
            connectors: List of connectors to route
            targets: List of available routing targets

        Returns:
            RoutingResult with routes, failures, and statistics
        """
        start_time = time.time()
        result = RoutingResult()
        result.statistics.total_connectors = len(connectors)

        if not connectors:
            logger.info("No connectors to route")
            return result

        if not targets:
            logger.warning("No targets available")
            for conn in connectors:
                result.add_failure(conn, "No targets available", error_code="NO_TARGETS")
            return result

        # Sequence connectors by priority
        sequenced = self._sequencer.sequence(connectors)
        logger.info(f"Routing {len(sequenced)} connectors in priority order")

        # Build target lookup by system compatibility
        target_by_system = self._build_target_lookup(targets)

        # Route each connector
        for i, connector in enumerate(sequenced):
            logger.debug(
                f"Routing connector {i+1}/{len(sequenced)}: "
                f"{connector.id} ({connector.system_type})"
            )

            route = self._route_connector(connector, targets, target_by_system)

            if route:
                result.add_route(route)
                self._update_occupancy(route)
                logger.debug(f"  -> Success: {len(route.segments)} segments")
            else:
                result.add_failure(
                    connector,
                    "No path found to any target",
                    error_code="NO_PATH"
                )
                logger.debug(f"  -> Failed: no path found")

        # Record timing
        elapsed_ms = (time.time() - start_time) * 1000
        result.statistics.routing_time_ms = elapsed_ms

        logger.info(
            f"Routing complete: {result.statistics.successful_routes} success, "
            f"{result.statistics.failed_routes} failed in {elapsed_ms:.1f}ms"
        )

        return result

    def route_single(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget]
    ) -> Optional[Route]:
        """
        Route a single connector to best available target.

        Args:
            connector: Connector to route
            targets: Available targets

        Returns:
            Route if successful, None otherwise
        """
        target_lookup = self._build_target_lookup(targets)
        return self._route_connector(connector, targets, target_lookup)

    def _route_connector(
        self,
        connector: ConnectorInfo,
        all_targets: List[RoutingTarget],
        target_by_system: Dict[str, List[RoutingTarget]]
    ) -> Optional[Route]:
        """Route a single connector."""
        if self._pathfinder is None:
            logger.error("Pathfinder not initialized")
            return None

        # Get compatible targets for this system
        system = connector.system_type or ""
        compatible = target_by_system.get(system, [])

        if not compatible:
            # Fall back to all targets
            compatible = all_targets

        # Get heuristic for this system type
        heuristic = self.heuristics.get(system)

        # Try targets in priority order
        if heuristic:
            candidates = heuristic.find_candidates(connector, compatible)
            sorted_targets = [c.target for c in sorted(candidates, key=lambda c: c.score)]
        else:
            # Sort by distance as fallback
            sorted_targets = self._sort_targets_by_distance(connector, compatible)

        # Attempt routing to each target
        for target in sorted_targets[:5]:  # Limit attempts
            route = self._attempt_route(connector, target)
            if route:
                return route

        return None

    def _attempt_route(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget
    ) -> Optional[Route]:
        """Attempt to route connector to target."""
        if self._pathfinder is None:
            return None

        # Use wall_id as domain_id for connectors
        source_domain = connector.wall_id
        target_domain = target.domain_id

        if not source_domain or not target_domain:
            logger.debug(f"Missing domain: source={source_domain}, target={target_domain}")
            return None

        # Extract 2D location from 3D connector location
        conn_loc = (connector.location[0], connector.location[1])

        # Use plane_location for target (2D in domain space)
        target_loc = target.plane_location

        route = self._pathfinder.find_path(
            source_domain,
            conn_loc,
            target_domain,
            target_loc,
            route_id=f"route_{connector.id}_to_{target.id}",
            system_type=connector.system_type
        )

        return route

    def _update_occupancy(self, route: Route) -> None:
        """Update occupancy map with routed segments."""
        from .occupancy import OccupiedSegment

        # Default pipe diameter estimate based on system
        pipe_diameter = self._estimate_pipe_diameter(route.system_type)
        trade = self._get_trade(route.system_type)

        for segment in route.segments:
            if not segment.domain_id:
                continue

            # Create OccupiedSegment and reserve
            occupied = OccupiedSegment(
                route_id=route.id,
                system_type=route.system_type,
                trade=trade,
                start=segment.start,
                end=segment.end,
                diameter=pipe_diameter
            )
            self.occupancy.reserve(segment.domain_id, occupied)

    def _get_trade(self, system_type: str) -> str:
        """Get trade category for a system type."""
        system = system_type.lower() if system_type else ""
        plumbing = {"sanitary", "drain", "vent", "supply", "dhw", "dcw", "hot_water", "cold_water"}
        electrical = {"power", "electrical", "data", "network", "lighting"}

        if system in plumbing:
            return "plumbing"
        elif system in electrical:
            return "electrical"
        else:
            return "hvac"

    def _estimate_pipe_diameter(self, system_type: str) -> float:
        """Estimate pipe diameter for a system type."""
        # Diameters in feet
        system = system_type.lower() if system_type else ""
        diameters = {
            "sanitary": 0.333,  # 4"
            "sanitary_drain": 0.333,
            "drain": 0.333,
            "vent": 0.167,  # 2"
            "sanitary_vent": 0.167,
            "supply": 0.0625,  # 3/4"
            "dhw": 0.0625,
            "dcw": 0.0625,
            "power": 0.0833,  # 1" conduit
            "data": 0.0625,  # 3/4" conduit
        }
        return diameters.get(system, 0.0833)

    def _build_target_lookup(
        self,
        targets: List[RoutingTarget]
    ) -> Dict[str, List[RoutingTarget]]:
        """Build lookup of targets by compatible system."""
        lookup: Dict[str, List[RoutingTarget]] = {}

        for target in targets:
            # Add to all compatible systems (systems_served attribute)
            for system in (target.systems_served or []):
                if system not in lookup:
                    lookup[system] = []
                lookup[system].append(target)

            # Also add by target type if it maps to systems
            if target.target_type:
                type_str = target.target_type.value if hasattr(target.target_type, 'value') else str(target.target_type)
                if type_str not in lookup:
                    lookup[type_str] = []
                lookup[type_str].append(target)

        return lookup

    def _sort_targets_by_distance(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget]
    ) -> List[RoutingTarget]:
        """Sort targets by distance from connector."""
        def distance(target: RoutingTarget) -> float:
            if not connector.location or not target.plane_location:
                return float('inf')
            # Connector has 3D location, target plane_location is 2D
            cx, cy = connector.location[0], connector.location[1]
            tx, ty = target.plane_location[0], target.plane_location[1]
            dx = tx - cx
            dy = ty - cy
            return (dx * dx + dy * dy) ** 0.5

        return sorted(targets, key=distance)

    def get_statistics(self) -> Dict[str, Any]:
        """Get current routing statistics."""
        # Count total segments across all domains
        total_segments = 0
        for domain_id in self.mdg.domains.keys():
            total_segments += len(self.occupancy.get_segments(domain_id))

        return {
            "domains": len(self.mdg.domains),
            "occupancy_segments": total_segments,
            "heuristics_registered": list(self.heuristics.keys())
        }


def create_oahs_router(
    mdg: MultiDomainGraph,
    include_default_heuristics: bool = True
) -> OAHSRouter:
    """
    Create an OAHS router with optional default heuristics.

    Args:
        mdg: Multi-domain graph for routing
        include_default_heuristics: Whether to register default heuristics

    Returns:
        Configured OAHSRouter instance
    """
    heuristics: Dict[str, TargetHeuristic] = {}

    if include_default_heuristics:
        from .heuristics import (
            SanitaryHeuristic,
            VentHeuristic,
            SupplyHeuristic,
            PowerHeuristic,
            DataHeuristic
        )

        heuristics["sanitary"] = SanitaryHeuristic()
        heuristics["sanitary_drain"] = SanitaryHeuristic()
        heuristics["drain"] = SanitaryHeuristic()
        heuristics["vent"] = VentHeuristic()
        heuristics["sanitary_vent"] = VentHeuristic()
        heuristics["supply"] = SupplyHeuristic()
        heuristics["dhw"] = SupplyHeuristic()
        heuristics["dcw"] = SupplyHeuristic()
        heuristics["power"] = PowerHeuristic()
        heuristics["electrical"] = PowerHeuristic()
        heuristics["data"] = DataHeuristic()
        heuristics["network"] = DataHeuristic()

    return OAHSRouter(
        mdg=mdg,
        heuristic_registry=heuristics
    )
