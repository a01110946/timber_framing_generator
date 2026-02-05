# File: src/timber_framing_generator/mep/routing/route_segment.py
"""
Route segment representation for MEP routing.

Defines the basic building block of an MEP route path.
"""

from dataclasses import dataclass, field
from typing import Tuple, Optional, Dict, Any
from enum import Enum


class SegmentDirection(Enum):
    """Direction of a route segment."""
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    DIAGONAL = "diagonal"  # For non-rectilinear connections


@dataclass
class RouteSegment:
    """
    A single segment in an MEP route.

    Represents a straight-line path between two points in the routing
    graph. Segments are typically horizontal or vertical (rectilinear)
    for MEP routing.

    Attributes:
        start: Start point coordinates (x, y)
        end: End point coordinates (x, y)
        direction: Segment direction (horizontal/vertical)
        length: Physical length of segment
        cost: Routing cost including penetration penalties
        domain_id: ID of the routing domain this segment is in
        is_steiner: Whether this connects to a Steiner junction point
        crosses_obstacle: Whether this segment crosses a framing member
        obstacle_type: Type of obstacle crossed (stud, joist, etc.)
        metadata: Additional segment metadata
    """
    start: Tuple[float, float]
    end: Tuple[float, float]
    direction: SegmentDirection = field(default=SegmentDirection.HORIZONTAL)
    length: float = 0.0
    cost: float = 0.0
    domain_id: str = ""
    is_steiner: bool = False
    crosses_obstacle: bool = False
    obstacle_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Calculate length and direction if not set."""
        if self.length == 0.0:
            dx = abs(self.end[0] - self.start[0])
            dy = abs(self.end[1] - self.start[1])
            self.length = dx + dy  # Manhattan distance

        # Auto-detect direction
        if self.direction == SegmentDirection.HORIZONTAL:
            dx = abs(self.end[0] - self.start[0])
            dy = abs(self.end[1] - self.start[1])
            if dx > 1e-6 and dy > 1e-6:
                self.direction = SegmentDirection.DIAGONAL
            elif dy > dx:
                self.direction = SegmentDirection.VERTICAL

        if self.cost == 0.0:
            self.cost = self.length

    def reversed(self) -> 'RouteSegment':
        """Return a copy with start and end swapped."""
        return RouteSegment(
            start=self.end,
            end=self.start,
            direction=self.direction,
            length=self.length,
            cost=self.cost,
            domain_id=self.domain_id,
            is_steiner=self.is_steiner,
            crosses_obstacle=self.crosses_obstacle,
            obstacle_type=self.obstacle_type,
            metadata=self.metadata.copy()
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "start": list(self.start),
            "end": list(self.end),
            "direction": self.direction.value,
            "length": self.length,
            "cost": self.cost,
            "domain_id": self.domain_id,
            "is_steiner": self.is_steiner,
            "crosses_obstacle": self.crosses_obstacle,
            "obstacle_type": self.obstacle_type,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RouteSegment':
        """Create from dictionary."""
        direction = data.get("direction", "horizontal")
        if isinstance(direction, str):
            direction = SegmentDirection(direction)

        return cls(
            start=tuple(data["start"]),
            end=tuple(data["end"]),
            direction=direction,
            length=data.get("length", 0.0),
            cost=data.get("cost", 0.0),
            domain_id=data.get("domain_id", ""),
            is_steiner=data.get("is_steiner", False),
            crosses_obstacle=data.get("crosses_obstacle", False),
            obstacle_type=data.get("obstacle_type"),
            metadata=data.get("metadata", {})
        )


@dataclass
class Route:
    """
    A complete MEP route from source to target.

    Composed of multiple RouteSegments forming a connected path.

    Attributes:
        id: Unique route identifier
        system_type: MEP system type (sanitary, supply, vent, power, etc.)
        segments: List of route segments in order
        source: Source point (connector location)
        target: Target point (main/riser/panel location)
        total_cost: Sum of all segment costs
        total_length: Sum of all segment lengths
        domains_crossed: List of domain IDs traversed
    """
    id: str
    system_type: str
    segments: list = field(default_factory=list)
    source: Optional[Tuple[float, float]] = None
    target: Optional[Tuple[float, float]] = None
    total_cost: float = 0.0
    total_length: float = 0.0
    domains_crossed: list = field(default_factory=list)

    def __post_init__(self):
        """Calculate totals from segments."""
        if self.segments and self.total_cost == 0.0:
            self.total_cost = sum(s.cost for s in self.segments)
        if self.segments and self.total_length == 0.0:
            self.total_length = sum(s.length for s in self.segments)
        if self.segments and not self.domains_crossed:
            seen = set()
            for s in self.segments:
                if s.domain_id and s.domain_id not in seen:
                    self.domains_crossed.append(s.domain_id)
                    seen.add(s.domain_id)

    def add_segment(self, segment: RouteSegment) -> None:
        """Add a segment to the route."""
        self.segments.append(segment)
        self.total_cost += segment.cost
        self.total_length += segment.length
        if segment.domain_id and segment.domain_id not in self.domains_crossed:
            self.domains_crossed.append(segment.domain_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "system_type": self.system_type,
            "segments": [s.to_dict() for s in self.segments],
            "source": list(self.source) if self.source else None,
            "target": list(self.target) if self.target else None,
            "total_cost": self.total_cost,
            "total_length": self.total_length,
            "domains_crossed": self.domains_crossed
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Route':
        """Create from dictionary."""
        segments = [RouteSegment.from_dict(s) for s in data.get("segments", [])]
        return cls(
            id=data["id"],
            system_type=data["system_type"],
            segments=segments,
            source=tuple(data["source"]) if data.get("source") else None,
            target=tuple(data["target"]) if data.get("target") else None,
            total_cost=data.get("total_cost", 0.0),
            total_length=data.get("total_length", 0.0),
            domains_crossed=data.get("domains_crossed", [])
        )
