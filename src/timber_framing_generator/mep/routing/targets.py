# File: src/timber_framing_generator/mep/routing/targets.py
"""
Routing target definitions for MEP routing.

Defines valid destinations for MEP routes: wet walls, floor penetrations,
shafts, and other connection points.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


class TargetType(Enum):
    """Types of routing targets."""
    WET_WALL = "wet_wall"              # Wall with plumbing stack/risers
    FLOOR_PENETRATION = "floor_penetration"  # Drop through floor
    CEILING_PENETRATION = "ceiling_penetration"  # Rise through ceiling
    SHAFT = "shaft"                    # Vertical service shaft
    PANEL_BOUNDARY = "panel_boundary"  # Edge of prefab panel
    EQUIPMENT = "equipment"            # Connection to equipment
    MAIN_LINE = "main_line"            # Connection to building main


# System type to compatible target types mapping
SYSTEM_TARGET_COMPATIBILITY = {
    # Plumbing
    "Sanitary": [TargetType.WET_WALL, TargetType.FLOOR_PENETRATION, TargetType.SHAFT],
    "Vent": [TargetType.WET_WALL, TargetType.CEILING_PENETRATION, TargetType.SHAFT],
    "DomesticHotWater": [TargetType.WET_WALL, TargetType.FLOOR_PENETRATION,
                         TargetType.CEILING_PENETRATION, TargetType.SHAFT],
    "DomesticColdWater": [TargetType.WET_WALL, TargetType.FLOOR_PENETRATION,
                          TargetType.CEILING_PENETRATION, TargetType.SHAFT],
    # Electrical
    "Power": [TargetType.PANEL_BOUNDARY, TargetType.CEILING_PENETRATION,
              TargetType.EQUIPMENT],
    "Lighting": [TargetType.CEILING_PENETRATION, TargetType.PANEL_BOUNDARY],
    "Data": [TargetType.PANEL_BOUNDARY, TargetType.CEILING_PENETRATION,
             TargetType.EQUIPMENT],
    "LowVoltage": [TargetType.PANEL_BOUNDARY, TargetType.CEILING_PENETRATION],
    # HVAC
    "SupplyAir": [TargetType.CEILING_PENETRATION, TargetType.SHAFT],
    "ReturnAir": [TargetType.CEILING_PENETRATION, TargetType.SHAFT],
    "Exhaust": [TargetType.CEILING_PENETRATION, TargetType.SHAFT],
}


@dataclass
class RoutingTarget:
    """
    A valid destination for MEP routes.

    Represents places where pipes/conduits can connect: wet walls,
    floor penetration zones, shafts, panel boundaries, etc.

    Attributes:
        id: Unique identifier
        target_type: Type of target (WET_WALL, SHAFT, etc.)
        location: 3D world coordinates (x, y, z)
        domain_id: ID of the routing domain this target is in
        plane_location: 2D coordinates in the domain plane (u, v)
        systems_served: List of compatible MEP system types
        capacity: Maximum pipe/conduit size that can connect (feet)
        priority: Selection priority (lower = prefer this target)
        is_available: Whether target can accept new connections
        metadata: Additional target-specific data
    """
    id: str
    target_type: TargetType
    location: Tuple[float, float, float]  # World (x, y, z)
    domain_id: str
    plane_location: Tuple[float, float]   # Domain (u, v)
    systems_served: List[str] = field(default_factory=list)
    capacity: float = 0.333  # Default: 4" pipe max
    priority: int = 0
    is_available: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_serve_system(self, system_type: str) -> bool:
        """Check if this target can serve a given system type."""
        # If systems_served is empty, check compatibility mapping
        if not self.systems_served:
            compatible_targets = SYSTEM_TARGET_COMPATIBILITY.get(system_type, [])
            return self.target_type in compatible_targets
        return system_type in self.systems_served

    def can_fit_pipe(self, diameter: float) -> bool:
        """Check if a pipe of given diameter can connect to this target."""
        return diameter <= self.capacity

    def distance_to(self, point: Tuple[float, float, float]) -> float:
        """Calculate 3D Euclidean distance to a point."""
        import math
        dx = self.location[0] - point[0]
        dy = self.location[1] - point[1]
        dz = self.location[2] - point[2]
        return math.sqrt(dx*dx + dy*dy + dz*dz)

    def plane_distance_to(self, point: Tuple[float, float]) -> float:
        """Calculate 2D distance in plane coordinates."""
        import math
        du = self.plane_location[0] - point[0]
        dv = self.plane_location[1] - point[1]
        return math.sqrt(du*du + dv*dv)

    def manhattan_distance_to(self, point: Tuple[float, float]) -> float:
        """Calculate Manhattan distance in plane coordinates."""
        du = abs(self.plane_location[0] - point[0])
        dv = abs(self.plane_location[1] - point[1])
        return du + dv

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "target_type": self.target_type.value,
            "location": list(self.location),
            "domain_id": self.domain_id,
            "plane_location": list(self.plane_location),
            "systems_served": self.systems_served.copy(),
            "capacity": self.capacity,
            "priority": self.priority,
            "is_available": self.is_available,
            "metadata": self.metadata.copy()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingTarget":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            target_type=TargetType(data["target_type"]),
            location=tuple(data["location"]),
            domain_id=data["domain_id"],
            plane_location=tuple(data["plane_location"]),
            systems_served=data.get("systems_served", []),
            capacity=data.get("capacity", 0.333),
            priority=data.get("priority", 0),
            is_available=data.get("is_available", True),
            metadata=data.get("metadata", {})
        )


@dataclass
class TargetCandidate:
    """
    A ranked candidate target for a connector.

    Used during target selection to compare options.

    Attributes:
        target: The routing target
        score: Lower is better (combines distance, priority, etc.)
        distance: Distance from connector to target
        routing_domain: Primary domain for routing to this target
        requires_floor_routing: Whether routing requires floor penetration
        notes: Explanation of why this candidate was selected
    """
    target: RoutingTarget
    score: float
    distance: float
    routing_domain: str
    requires_floor_routing: bool = False
    notes: str = ""

    def __lt__(self, other: "TargetCandidate") -> bool:
        """Enable sorting by score."""
        return self.score < other.score


def get_compatible_target_types(system_type: str) -> List[TargetType]:
    """Get list of compatible target types for a system type."""
    return SYSTEM_TARGET_COMPATIBILITY.get(system_type, [])


def filter_targets_for_system(
    targets: List[RoutingTarget],
    system_type: str,
    min_capacity: float = 0.0
) -> List[RoutingTarget]:
    """
    Filter targets to only those compatible with a system type.

    Args:
        targets: List of all available targets
        system_type: MEP system type to filter for
        min_capacity: Minimum required capacity

    Returns:
        Filtered list of compatible targets
    """
    return [
        t for t in targets
        if t.can_serve_system(system_type)
        and t.can_fit_pipe(min_capacity)
        and t.is_available
    ]


def rank_targets_by_distance(
    targets: List[RoutingTarget],
    from_point: Tuple[float, float, float],
    use_manhattan: bool = True
) -> List[TargetCandidate]:
    """
    Rank targets by distance from a point.

    Args:
        targets: List of targets to rank
        from_point: Source point (x, y, z)
        use_manhattan: Use Manhattan distance (for rectilinear routing)

    Returns:
        List of TargetCandidates sorted by distance
    """
    candidates = []

    for target in targets:
        if use_manhattan:
            # Project to 2D and use Manhattan distance
            from_2d = (from_point[0], from_point[1])
            target_2d = (target.location[0], target.location[1])
            distance = (abs(from_2d[0] - target_2d[0]) +
                       abs(from_2d[1] - target_2d[1]) +
                       abs(from_point[2] - target.location[2]))
        else:
            distance = target.distance_to(from_point)

        # Score combines distance and priority
        score = distance + target.priority * 0.1

        candidates.append(TargetCandidate(
            target=target,
            score=score,
            distance=distance,
            routing_domain=target.domain_id,
            requires_floor_routing=(
                target.target_type == TargetType.FLOOR_PENETRATION
            ),
            notes=f"Distance: {distance:.2f} ft, Priority: {target.priority}"
        ))

    candidates.sort()
    return candidates
