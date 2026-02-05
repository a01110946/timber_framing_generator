# File: src/timber_framing_generator/mep/routing/routing_result.py
"""
Routing result data structures for OAHS algorithm.

Defines the complete result of a routing operation including
successful routes, failures, and statistics.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

from .route_segment import Route
from .heuristics.base import ConnectorInfo


@dataclass
class FailedConnector:
    """
    Information about a connector that couldn't be routed.

    Attributes:
        connector: The connector that failed
        reason: Human-readable failure reason
        attempted_targets: Targets that were tried
        error_code: Machine-readable error code
        recoverable: Whether this might succeed with different conditions
    """
    connector: ConnectorInfo
    reason: str
    attempted_targets: List[str] = field(default_factory=list)
    error_code: str = "ROUTING_FAILED"
    recoverable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "connector_id": self.connector.id,
            "system_type": self.connector.system_type,
            "location": list(self.connector.location),
            "reason": self.reason,
            "attempted_targets": self.attempted_targets,
            "error_code": self.error_code,
            "recoverable": self.recoverable
        }


@dataclass
class RoutingStatistics:
    """
    Statistics about a routing operation.

    Attributes:
        total_connectors: Number of connectors to route
        successful_routes: Number of successful routes
        failed_routes: Number of failed routes
        total_length: Total length of all routes
        total_cost: Total cost of all routes
        routing_time_ms: Time taken for routing in milliseconds
        conflicts_resolved: Number of conflicts that were resolved
        reroute_attempts: Number of reroute attempts made
    """
    total_connectors: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    total_length: float = 0.0
    total_cost: float = 0.0
    routing_time_ms: float = 0.0
    conflicts_resolved: int = 0
    reroute_attempts: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_connectors == 0:
            return 0.0
        return (self.successful_routes / self.total_connectors) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_connectors": self.total_connectors,
            "successful_routes": self.successful_routes,
            "failed_routes": self.failed_routes,
            "success_rate": self.success_rate,
            "total_length": self.total_length,
            "total_cost": self.total_cost,
            "routing_time_ms": self.routing_time_ms,
            "conflicts_resolved": self.conflicts_resolved,
            "reroute_attempts": self.reroute_attempts
        }


@dataclass
class RoutingResult:
    """
    Complete result of an OAHS routing operation.

    Contains all successful routes, failed connectors, and
    statistics about the routing operation.

    Attributes:
        routes: List of successfully routed paths
        failed: List of connectors that couldn't be routed
        statistics: Routing statistics
        timestamp: When the routing was performed
        metadata: Additional metadata about the routing
    """
    routes: List[Route] = field(default_factory=list)
    failed: List[FailedConnector] = field(default_factory=list)
    statistics: RoutingStatistics = field(default_factory=RoutingStatistics)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_route(self, route: Route) -> None:
        """Add a successful route and update statistics."""
        self.routes.append(route)
        self.statistics.successful_routes += 1
        self.statistics.total_length += route.total_length
        self.statistics.total_cost += route.total_cost

    def add_failure(
        self,
        connector: ConnectorInfo,
        reason: str,
        attempted_targets: Optional[List[str]] = None,
        error_code: str = "ROUTING_FAILED"
    ) -> None:
        """Add a failed connector and update statistics."""
        failed = FailedConnector(
            connector=connector,
            reason=reason,
            attempted_targets=attempted_targets or [],
            error_code=error_code
        )
        self.failed.append(failed)
        self.statistics.failed_routes += 1

    def get_routes_by_system(self, system_type: str) -> List[Route]:
        """Get all routes for a specific system type."""
        return [r for r in self.routes if r.system_type == system_type]

    def get_routes_in_domain(self, domain_id: str) -> List[Route]:
        """Get routes that pass through a specific domain."""
        return [
            r for r in self.routes
            if domain_id in r.domains_crossed
        ]

    def is_complete(self) -> bool:
        """Check if all connectors were successfully routed."""
        return len(self.failed) == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "routes": [r.to_dict() for r in self.routes],
            "failed": [f.to_dict() for f in self.failed],
            "statistics": self.statistics.to_dict(),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "is_complete": self.is_complete()
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RoutingResult':
        """Create from dictionary."""
        # Note: Full deserialization would need Route.from_dict
        # This is a simplified version
        result = cls(
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {})
        )

        # Statistics
        stats_data = data.get("statistics", {})
        result.statistics = RoutingStatistics(
            total_connectors=stats_data.get("total_connectors", 0),
            successful_routes=stats_data.get("successful_routes", 0),
            failed_routes=stats_data.get("failed_routes", 0),
            total_length=stats_data.get("total_length", 0.0),
            total_cost=stats_data.get("total_cost", 0.0),
            routing_time_ms=stats_data.get("routing_time_ms", 0.0),
            conflicts_resolved=stats_data.get("conflicts_resolved", 0),
            reroute_attempts=stats_data.get("reroute_attempts", 0)
        )

        return result


@dataclass
class RoutingRequest:
    """
    Request for a routing operation.

    Encapsulates all inputs needed for routing.

    Attributes:
        connectors: Connectors to route
        targets: Available routing targets
        config: Routing configuration options
    """
    connectors: List[ConnectorInfo] = field(default_factory=list)
    targets: List[Any] = field(default_factory=list)  # RoutingTarget
    config: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        """
        Validate the routing request.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.connectors:
            errors.append("No connectors provided")

        if not self.targets:
            errors.append("No targets provided")

        for i, conn in enumerate(self.connectors):
            if not conn.id:
                errors.append(f"Connector {i} has no ID")
            if not conn.system_type:
                errors.append(f"Connector {conn.id} has no system type")

        return errors
