# File: src/timber_framing_generator/mep/routing/heuristics/base.py
"""
Base class for MEP routing target heuristics.

Provides the abstract interface that all system-specific heuristics implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

from ..targets import RoutingTarget, TargetCandidate, TargetType
from ..domains import RoutingDomain


@dataclass
class ConnectorInfo:
    """
    Information about an MEP connector needing a route.

    Attributes:
        id: Unique identifier for this connector
        system_type: MEP system type (Sanitary, DHW, Power, etc.)
        location: 3D world coordinates (x, y, z)
        direction: Flow direction - "inward" (towards fixture) or "outward" (away)
        diameter: Pipe/conduit diameter in feet
        fixture_id: ID of parent fixture/device (if any)
        fixture_type: Type of fixture (Sink, Toilet, Outlet, etc.)
        wall_id: ID of wall fixture is mounted on (if wall-mounted)
        elevation: Z elevation in feet
        metadata: Additional connector-specific data
    """
    id: str
    system_type: str
    location: Tuple[float, float, float]
    direction: str  # "inward" or "outward"
    diameter: float
    fixture_id: Optional[str] = None
    fixture_type: Optional[str] = None
    wall_id: Optional[str] = None
    elevation: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "system_type": self.system_type,
            "location": list(self.location),
            "direction": self.direction,
            "diameter": self.diameter,
            "fixture_id": self.fixture_id,
            "fixture_type": self.fixture_type,
            "wall_id": self.wall_id,
            "elevation": self.elevation,
            "metadata": self.metadata.copy()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorInfo":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            system_type=data["system_type"],
            location=tuple(data["location"]),
            direction=data["direction"],
            diameter=data["diameter"],
            fixture_id=data.get("fixture_id"),
            fixture_type=data.get("fixture_type"),
            wall_id=data.get("wall_id"),
            elevation=data.get("elevation", 0.0),
            metadata=data.get("metadata", {})
        )


class TargetHeuristic(ABC):
    """
    Base class for target selection heuristics.

    Each MEP system type has its own heuristic that understands
    how to find and rank appropriate routing targets.

    Subclasses implement system-specific logic for:
    - Which target types are valid
    - How to score and rank targets
    - System-specific constraints (gravity, clearance, etc.)
    """

    # Default scoring weights - subclasses can override
    distance_weight: float = 1.0
    priority_weight: float = 0.1
    floor_change_penalty: float = 10.0

    @property
    @abstractmethod
    def system_types(self) -> List[str]:
        """List of system types this heuristic handles."""
        pass

    @property
    @abstractmethod
    def preferred_target_types(self) -> List[TargetType]:
        """Target types this heuristic prefers, in priority order."""
        pass

    @abstractmethod
    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """
        Find and rank candidate targets for a connector.

        Args:
            connector: The MEP connector needing a target
            targets: All available routing targets
            domains: Available routing domains
            max_candidates: Maximum number of candidates to return

        Returns:
            List of TargetCandidates, sorted by score (best first)
        """
        pass

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """
        Calculate a score for a target (lower is better).

        Default implementation combines distance and priority.
        Subclasses can override for system-specific scoring.

        Args:
            connector: The connector seeking a target
            target: The target being scored
            domain: Optional domain for additional context

        Returns:
            Score value (lower is better)
        """
        # Calculate Manhattan distance (better for rectilinear routing)
        distance = self._manhattan_distance_3d(connector.location, target.location)

        # Base score
        score = (
            self.distance_weight * distance +
            self.priority_weight * target.priority
        )

        # Penalty for floor changes
        floor_diff = abs(connector.elevation - target.location[2]) / 10.0  # ~10ft floors
        score += self.floor_change_penalty * floor_diff

        return score

    def _manhattan_distance_3d(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float]
    ) -> float:
        """Calculate 3D Manhattan distance."""
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2])

    def _euclidean_distance_3d(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float]
    ) -> float:
        """Calculate 3D Euclidean distance."""
        import math
        return math.sqrt(
            (p1[0] - p2[0])**2 +
            (p1[1] - p2[1])**2 +
            (p1[2] - p2[2])**2
        )

    def _filter_by_target_type(
        self,
        targets: List[RoutingTarget],
        allowed_types: List[TargetType]
    ) -> List[RoutingTarget]:
        """Filter targets to only allowed types."""
        return [t for t in targets if t.target_type in allowed_types]

    def _filter_by_capacity(
        self,
        targets: List[RoutingTarget],
        min_diameter: float
    ) -> List[RoutingTarget]:
        """Filter targets by minimum capacity."""
        return [t for t in targets if t.can_fit_pipe(min_diameter)]

    def _filter_available(
        self,
        targets: List[RoutingTarget]
    ) -> List[RoutingTarget]:
        """Filter to only available targets."""
        return [t for t in targets if t.is_available]

    def _create_candidate(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None,
        notes: str = ""
    ) -> TargetCandidate:
        """Create a TargetCandidate with calculated score."""
        distance = self._manhattan_distance_3d(connector.location, target.location)
        score = self.score_target(connector, target, domain)

        return TargetCandidate(
            target=target,
            score=score,
            distance=distance,
            routing_domain=target.domain_id,
            requires_floor_routing=(
                target.target_type == TargetType.FLOOR_PENETRATION
            ),
            notes=notes or f"Distance: {distance:.2f} ft, Score: {score:.2f}"
        )


class FallbackHeuristic(TargetHeuristic):
    """
    Fallback heuristic for unknown or generic system types.

    Uses simple distance-based ranking without system-specific logic.
    """

    @property
    def system_types(self) -> List[str]:
        return []  # Handles any system type as fallback

    @property
    def preferred_target_types(self) -> List[TargetType]:
        # Accept any target type
        return list(TargetType)

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find candidates using simple distance ranking."""
        # Filter available targets with sufficient capacity
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Score all valid targets
        candidates = []
        for target in valid_targets:
            if target.can_serve_system(connector.system_type):
                candidate = self._create_candidate(
                    connector, target,
                    notes="Fallback: distance-based ranking"
                )
                candidates.append(candidate)

        # Sort by score and return top candidates
        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]
