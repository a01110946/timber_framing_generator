# File: src/timber_framing_generator/mep/routing/domains.py
"""
Routing domain definitions for MEP routing.

Defines the 2D planes where routing occurs: wall cavities, floor cavities,
ceiling cavities, and vertical shafts.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


@dataclass(frozen=True)
class Point2D:
    """
    Immutable 2D point in plane coordinates.

    Attributes:
        u: First coordinate (along wall length, or X for floors)
        v: Second coordinate (vertical for walls, Y for floors)
    """
    u: float
    v: float

    def to_tuple(self) -> Tuple[float, float]:
        """Convert to tuple."""
        return (self.u, self.v)

    def distance_to(self, other: "Point2D") -> float:
        """Calculate Euclidean distance to another point."""
        import math
        return math.sqrt((self.u - other.u) ** 2 + (self.v - other.v) ** 2)

    def manhattan_distance_to(self, other: "Point2D") -> float:
        """Calculate Manhattan (rectilinear) distance to another point."""
        return abs(self.u - other.u) + abs(self.v - other.v)

    def __add__(self, other: "Point2D") -> "Point2D":
        """Add two points."""
        return Point2D(self.u + other.u, self.v + other.v)

    def __sub__(self, other: "Point2D") -> "Point2D":
        """Subtract two points."""
        return Point2D(self.u - other.u, self.v - other.v)

    def scale(self, factor: float) -> "Point2D":
        """Scale point by factor."""
        return Point2D(self.u * factor, self.v * factor)

    @classmethod
    def from_tuple(cls, t: Tuple[float, float]) -> "Point2D":
        """Create from tuple."""
        return cls(t[0], t[1])


class RoutingDomainType(Enum):
    """Types of routing domains in a building."""
    WALL_CAVITY = "wall_cavity"
    FLOOR_CAVITY = "floor_cavity"
    CEILING_CAVITY = "ceiling_cavity"
    SHAFT = "shaft"


@dataclass
class Obstacle:
    """
    An obstacle within a routing domain that must be avoided.

    Obstacles can be structural elements (studs, joists), existing pipes,
    or other obstructions.

    Attributes:
        id: Unique identifier
        obstacle_type: Type of obstacle ("stud", "joist", "pipe", "structural")
        bounds: Bounding box as (min_u, min_v, max_u, max_v)
        is_penetrable: Whether pipes can pass through (with penetration)
        max_penetration_ratio: Maximum hole size as ratio of obstacle depth
    """
    id: str
    obstacle_type: str
    bounds: Tuple[float, float, float, float]  # (min_u, min_v, max_u, max_v)
    is_penetrable: bool = False
    max_penetration_ratio: float = 0.4  # Code limit: 40% of member depth

    @property
    def min_u(self) -> float:
        return self.bounds[0]

    @property
    def min_v(self) -> float:
        return self.bounds[1]

    @property
    def max_u(self) -> float:
        return self.bounds[2]

    @property
    def max_v(self) -> float:
        return self.bounds[3]

    @property
    def width(self) -> float:
        """Width in U direction."""
        return self.max_u - self.min_u

    @property
    def height(self) -> float:
        """Height in V direction."""
        return self.max_v - self.min_v

    def contains_point(self, point: Point2D) -> bool:
        """Check if point is inside obstacle bounds."""
        return (
            self.min_u <= point.u <= self.max_u and
            self.min_v <= point.v <= self.max_v
        )

    def intersects_segment(
        self,
        start: Point2D,
        end: Point2D
    ) -> bool:
        """Check if a line segment intersects this obstacle."""
        # Use Liang-Barsky algorithm for line-box intersection
        dx = end.u - start.u
        dy = end.v - start.v

        p = [-dx, dx, -dy, dy]
        q = [
            start.u - self.min_u,
            self.max_u - start.u,
            start.v - self.min_v,
            self.max_v - start.v
        ]

        t_min = 0.0
        t_max = 1.0

        for i in range(4):
            if abs(p[i]) < 1e-10:
                if q[i] < 0:
                    return False
            else:
                t = q[i] / p[i]
                if p[i] < 0:
                    t_min = max(t_min, t)
                else:
                    t_max = min(t_max, t)

        return t_min <= t_max

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "obstacle_type": self.obstacle_type,
            "bounds": list(self.bounds),
            "is_penetrable": self.is_penetrable,
            "max_penetration_ratio": self.max_penetration_ratio
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Obstacle":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            obstacle_type=data["obstacle_type"],
            bounds=tuple(data["bounds"]),
            is_penetrable=data.get("is_penetrable", False),
            max_penetration_ratio=data.get("max_penetration_ratio", 0.4)
        )


@dataclass
class RoutingDomain:
    """
    A 2D routing domain (wall cavity, floor cavity, shaft, etc.).

    Attributes:
        id: Unique identifier (e.g., "wall_A", "floor_1")
        domain_type: Type of domain (WALL_CAVITY, FLOOR_CAVITY, etc.)
        bounds: Domain bounds as (min_u, max_u, min_v, max_v)
        thickness: Physical thickness of the cavity (for pipe fitting validation)
        obstacles: List of obstacles within this domain
        transitions: IDs of connected domains (for multi-domain routing)
        metadata: Additional domain-specific data
    """
    id: str
    domain_type: RoutingDomainType
    bounds: Tuple[float, float, float, float]  # (min_u, max_u, min_v, max_v)
    thickness: float = 0.292  # Default: 3.5" = 0.292 ft (2x4 wall)
    obstacles: List[Obstacle] = field(default_factory=list)
    transitions: List[str] = field(default_factory=list)  # Connected domain IDs
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def min_u(self) -> float:
        return self.bounds[0]

    @property
    def max_u(self) -> float:
        return self.bounds[1]

    @property
    def min_v(self) -> float:
        return self.bounds[2]

    @property
    def max_v(self) -> float:
        return self.bounds[3]

    @property
    def width(self) -> float:
        """Width in U direction."""
        return self.max_u - self.min_u

    @property
    def height(self) -> float:
        """Height in V direction."""
        return self.max_v - self.min_v

    def contains_point(self, point: Point2D) -> bool:
        """Check if point is within domain bounds."""
        return (
            self.min_u <= point.u <= self.max_u and
            self.min_v <= point.v <= self.max_v
        )

    def get_obstacles_at(self, point: Point2D) -> List[Obstacle]:
        """Get all obstacles containing a point."""
        return [obs for obs in self.obstacles if obs.contains_point(point)]

    def get_obstacles_intersecting(
        self,
        start: Point2D,
        end: Point2D
    ) -> List[Obstacle]:
        """Get all obstacles intersecting a line segment."""
        return [
            obs for obs in self.obstacles
            if obs.intersects_segment(start, end)
        ]

    def is_path_clear(
        self,
        start: Point2D,
        end: Point2D,
        allow_penetrable: bool = True
    ) -> bool:
        """
        Check if a path between two points is clear of obstacles.

        Args:
            start: Start point
            end: End point
            allow_penetrable: If True, penetrable obstacles don't block

        Returns:
            True if path is clear
        """
        for obs in self.obstacles:
            if obs.intersects_segment(start, end):
                if not allow_penetrable or not obs.is_penetrable:
                    return False
        return True

    def can_fit_pipe(self, diameter: float, clearance: float = 0.0208) -> bool:
        """
        Check if a pipe of given diameter can fit in this domain.

        Args:
            diameter: Pipe outer diameter in feet
            clearance: Required clearance on each side (default: 1/4")

        Returns:
            True if pipe fits
        """
        required_space = diameter + 2 * clearance
        return required_space <= self.thickness

    def add_obstacle(self, obstacle: Obstacle) -> None:
        """Add an obstacle to this domain."""
        self.obstacles.append(obstacle)

    def remove_obstacle(self, obstacle_id: str) -> bool:
        """Remove an obstacle by ID. Returns True if found and removed."""
        for i, obs in enumerate(self.obstacles):
            if obs.id == obstacle_id:
                self.obstacles.pop(i)
                return True
        return False

    def add_transition(self, domain_id: str) -> None:
        """Add a transition to another domain."""
        if domain_id not in self.transitions:
            self.transitions.append(domain_id)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "domain_type": self.domain_type.value,
            "bounds": list(self.bounds),
            "thickness": self.thickness,
            "obstacles": [obs.to_dict() for obs in self.obstacles],
            "transitions": self.transitions.copy(),
            "metadata": self.metadata.copy()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingDomain":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            domain_type=RoutingDomainType(data["domain_type"]),
            bounds=tuple(data["bounds"]),
            thickness=data.get("thickness", 0.292),
            obstacles=[Obstacle.from_dict(o) for o in data.get("obstacles", [])],
            transitions=data.get("transitions", []),
            metadata=data.get("metadata", {})
        )


def create_wall_domain(
    wall_id: str,
    length: float,
    height: float,
    thickness: float = 0.292,
    stud_spacing: float = 1.333,  # 16" OC
    stud_width: float = 0.125,   # 1.5"
    has_top_plate: bool = True,
    has_bottom_plate: bool = True,
    plate_thickness: float = 0.125
) -> RoutingDomain:
    """
    Create a wall cavity routing domain with stud obstacles.

    Args:
        wall_id: Unique wall identifier
        length: Wall length in feet
        height: Wall height in feet
        thickness: Wall cavity thickness (stud depth)
        stud_spacing: Stud spacing (typically 1.333 ft = 16")
        stud_width: Stud width (typically 0.125 ft = 1.5")
        has_top_plate: Whether wall has top plate
        has_bottom_plate: Whether wall has bottom plate
        plate_thickness: Plate thickness

    Returns:
        RoutingDomain configured for wall cavity routing
    """
    domain = RoutingDomain(
        id=wall_id,
        domain_type=RoutingDomainType.WALL_CAVITY,
        bounds=(0, length, 0, height),
        thickness=thickness,
        metadata={
            "stud_spacing": stud_spacing,
            "stud_width": stud_width
        }
    )

    # Add stud obstacles
    stud_index = 0
    u = stud_width / 2  # First stud centered at its width
    while u < length:
        stud_min_u = u - stud_width / 2
        stud_max_u = u + stud_width / 2

        # Studs run from bottom plate to top plate
        stud_min_v = plate_thickness if has_bottom_plate else 0
        stud_max_v = height - plate_thickness if has_top_plate else height

        domain.add_obstacle(Obstacle(
            id=f"{wall_id}_stud_{stud_index}",
            obstacle_type="stud",
            bounds=(stud_min_u, stud_min_v, stud_max_u, stud_max_v),
            is_penetrable=True,
            max_penetration_ratio=0.4
        ))

        stud_index += 1
        u += stud_spacing

    # Add end stud if not at spacing boundary
    if length - u + stud_spacing > stud_width:
        domain.add_obstacle(Obstacle(
            id=f"{wall_id}_stud_{stud_index}",
            obstacle_type="stud",
            bounds=(
                length - stud_width,
                plate_thickness if has_bottom_plate else 0,
                length,
                height - plate_thickness if has_top_plate else height
            ),
            is_penetrable=True,
            max_penetration_ratio=0.4
        ))

    # Add plate obstacles (not penetrable for routing)
    if has_bottom_plate:
        domain.add_obstacle(Obstacle(
            id=f"{wall_id}_bottom_plate",
            obstacle_type="plate",
            bounds=(0, 0, length, plate_thickness),
            is_penetrable=False
        ))

    if has_top_plate:
        domain.add_obstacle(Obstacle(
            id=f"{wall_id}_top_plate",
            obstacle_type="plate",
            bounds=(0, height - plate_thickness, length, height),
            is_penetrable=False
        ))

    return domain


def add_opening_obstacles(
    domain: RoutingDomain,
    openings: List[Dict[str, Any]],
) -> None:
    """Add door/window openings as non-penetrable obstacles to a routing domain.

    Doors become full-height no-go zones (nothing can route through a door opening).
    Windows become no-go zones within their opening bounds only, allowing
    routing above or below the window.

    Args:
        domain: Existing RoutingDomain to add obstacles to.
        openings: List of OpeningData-style dicts with keys:
            id, opening_type, u_start, u_end, v_start, v_end.
    """
    for opening in openings:
        opening_id = opening.get("id", "unknown")
        opening_type = opening.get("opening_type", "window")
        u_start = float(opening["u_start"])
        u_end = float(opening["u_end"])
        v_start = float(opening["v_start"])
        v_end = float(opening["v_end"])

        if opening_type == "door":
            # Doors: full height no-go zone from bottom to top of domain
            bounds = (u_start, domain.min_v, u_end, domain.max_v)
        else:
            # Windows: only the opening zone is blocked
            bounds = (u_start, v_start, u_end, v_end)

        domain.add_obstacle(Obstacle(
            id=f"{domain.id}_opening_{opening_id}",
            obstacle_type="opening",
            bounds=bounds,
            is_penetrable=False,
        ))


def create_floor_domain(
    floor_id: str,
    width: float,
    length: float,
    depth: float = 0.792,  # 9.5" TJI
    joist_spacing: float = 1.333,  # 16" OC
    joist_width: float = 0.146,   # 1.75" (TJI flange)
) -> RoutingDomain:
    """
    Create a floor cavity routing domain with joist obstacles.

    Args:
        floor_id: Unique floor identifier
        width: Floor width in feet (X direction)
        length: Floor length in feet (Y direction)
        depth: Floor cavity depth
        joist_spacing: Joist spacing
        joist_width: Joist flange width

    Returns:
        RoutingDomain configured for floor cavity routing
    """
    domain = RoutingDomain(
        id=floor_id,
        domain_type=RoutingDomainType.FLOOR_CAVITY,
        bounds=(0, width, 0, length),
        thickness=depth,
        metadata={
            "joist_spacing": joist_spacing,
            "joist_width": joist_width
        }
    )

    # Add joist obstacles (run along Y direction)
    joist_index = 0
    x = joist_width / 2
    while x < width:
        joist_min_u = x - joist_width / 2
        joist_max_u = x + joist_width / 2

        domain.add_obstacle(Obstacle(
            id=f"{floor_id}_joist_{joist_index}",
            obstacle_type="joist",
            bounds=(joist_min_u, 0, joist_max_u, length),
            is_penetrable=True,  # Can route through web openings
            max_penetration_ratio=0.6  # More generous for engineered joists
        ))

        joist_index += 1
        x += joist_spacing

    return domain
