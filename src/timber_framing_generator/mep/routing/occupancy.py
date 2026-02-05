# File: src/timber_framing_generator/mep/routing/occupancy.py
"""
Occupancy tracking for MEP routing.

Manages reserved space in 2D routing planes to prevent conflicts
between different routes and trades.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math


@dataclass
class OccupiedSegment:
    """
    Represents a pipe/conduit segment occupying space in a routing plane.

    Attributes:
        route_id: Unique identifier for the route this segment belongs to
        system_type: MEP system type (e.g., "Sanitary", "DHW", "Power")
        trade: Trade category ("plumbing", "electrical", "hvac")
        start: Start point (u, v) in plane coordinates
        end: End point (u, v) in plane coordinates
        diameter: Pipe/conduit outer diameter in feet
        priority: Lower values = higher priority (placed first)
    """
    route_id: str
    system_type: str
    trade: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    diameter: float
    priority: int = 0

    def get_length(self) -> float:
        """Calculate segment length."""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.sqrt(dx * dx + dy * dy)

    def get_midpoint(self) -> Tuple[float, float]:
        """Get segment midpoint."""
        return (
            (self.start[0] + self.end[0]) / 2,
            (self.start[1] + self.end[1]) / 2
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "route_id": self.route_id,
            "system_type": self.system_type,
            "trade": self.trade,
            "start": list(self.start),
            "end": list(self.end),
            "diameter": self.diameter,
            "priority": self.priority
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OccupiedSegment":
        """Deserialize from dictionary."""
        return cls(
            route_id=data["route_id"],
            system_type=data["system_type"],
            trade=data["trade"],
            start=tuple(data["start"]),
            end=tuple(data["end"]),
            diameter=data["diameter"],
            priority=data.get("priority", 0)
        )


class OccupancyMap:
    """
    Tracks occupied space in 2D routing planes.

    Each plane (wall, floor, etc.) has its own occupancy tracking.
    Supports reservation, release, and conflict detection.

    Example:
        >>> occ = OccupancyMap()
        >>> segment = OccupiedSegment(
        ...     route_id="route_1",
        ...     system_type="Sanitary",
        ...     trade="plumbing",
        ...     start=(0, 0),
        ...     end=(5, 0),
        ...     diameter=0.125
        ... )
        >>> occ.reserve("wall_A", segment)
        >>> available, conflict = occ.is_available(
        ...     "wall_A", ((0, 0), (5, 0)), 0.125, clearance=0.0417
        ... )
        >>> print(available)  # False - space is occupied
    """

    # Default clearance between pipes (1/2 inch in feet)
    DEFAULT_CLEARANCE = 0.0417

    def __init__(self):
        """Initialize empty occupancy map."""
        self._planes: Dict[str, List[OccupiedSegment]] = {}

    @property
    def planes(self) -> Dict[str, List[OccupiedSegment]]:
        """Get all planes and their occupied segments."""
        return self._planes

    def get_plane_ids(self) -> List[str]:
        """Get list of all plane IDs with occupancy data."""
        return list(self._planes.keys())

    def get_segments(self, plane_id: str) -> List[OccupiedSegment]:
        """Get all occupied segments in a plane."""
        return self._planes.get(plane_id, [])

    def reserve(self, plane_id: str, segment: OccupiedSegment) -> None:
        """
        Reserve space for a segment in a plane.

        Args:
            plane_id: ID of the routing plane (e.g., "wall_A", "floor_1")
            segment: The segment to reserve space for
        """
        if plane_id not in self._planes:
            self._planes[plane_id] = []
        self._planes[plane_id].append(segment)

    def release(self, plane_id: str, route_id: str) -> int:
        """
        Release all segments belonging to a route.

        Args:
            plane_id: ID of the routing plane
            route_id: ID of the route to release

        Returns:
            Number of segments released
        """
        if plane_id not in self._planes:
            return 0

        original_count = len(self._planes[plane_id])
        self._planes[plane_id] = [
            seg for seg in self._planes[plane_id]
            if seg.route_id != route_id
        ]
        return original_count - len(self._planes[plane_id])

    def release_all(self, route_id: str) -> int:
        """
        Release all segments for a route across all planes.

        Args:
            route_id: ID of the route to release

        Returns:
            Total number of segments released
        """
        total_released = 0
        for plane_id in list(self._planes.keys()):
            total_released += self.release(plane_id, route_id)
        return total_released

    def is_available(
        self,
        plane_id: str,
        segment: Tuple[Tuple[float, float], Tuple[float, float]],
        diameter: float,
        clearance: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if space is available for a new segment.

        Args:
            plane_id: ID of the routing plane
            segment: ((start_u, start_v), (end_u, end_v)) coordinates
            diameter: Diameter of the new pipe/conduit
            clearance: Minimum clearance between pipes (default: 0.0417 ft = 1/2")

        Returns:
            Tuple of (is_available, conflicting_route_id or None)
        """
        if clearance is None:
            clearance = self.DEFAULT_CLEARANCE

        conflicts = self.get_conflicts(plane_id, segment, diameter, clearance)

        if conflicts:
            return False, conflicts[0].route_id
        return True, None

    def get_conflicts(
        self,
        plane_id: str,
        segment: Tuple[Tuple[float, float], Tuple[float, float]],
        diameter: float,
        clearance: Optional[float] = None
    ) -> List[OccupiedSegment]:
        """
        Get all segments that conflict with a proposed segment.

        Args:
            plane_id: ID of the routing plane
            segment: ((start_u, start_v), (end_u, end_v)) coordinates
            diameter: Diameter of the new pipe/conduit
            clearance: Minimum clearance between pipes

        Returns:
            List of conflicting OccupiedSegments
        """
        if clearance is None:
            clearance = self.DEFAULT_CLEARANCE

        if plane_id not in self._planes:
            return []

        conflicts = []
        start, end = segment

        for occupied in self._planes[plane_id]:
            # Calculate minimum required distance between centerlines
            min_distance = (diameter / 2) + (occupied.diameter / 2) + clearance

            # Check if segments are too close
            if self._segments_conflict(
                start, end,
                occupied.start, occupied.end,
                min_distance
            ):
                conflicts.append(occupied)

        return conflicts

    def _segments_conflict(
        self,
        a_start: Tuple[float, float],
        a_end: Tuple[float, float],
        b_start: Tuple[float, float],
        b_end: Tuple[float, float],
        min_distance: float
    ) -> bool:
        """
        Check if two line segments are within min_distance of each other.

        Uses segment-to-segment distance calculation.
        """
        # Calculate minimum distance between the two segments
        dist = self._segment_to_segment_distance(
            a_start, a_end, b_start, b_end
        )
        return dist < min_distance

    def _segment_to_segment_distance(
        self,
        a_start: Tuple[float, float],
        a_end: Tuple[float, float],
        b_start: Tuple[float, float],
        b_end: Tuple[float, float]
    ) -> float:
        """
        Calculate minimum distance between two line segments.

        Checks:
        1. If segments intersect (distance = 0)
        2. Distance from each endpoint to the other segment
        """
        # Check for intersection
        if self._segments_intersect(a_start, a_end, b_start, b_end):
            return 0.0

        # Calculate distances from endpoints to segments
        distances = [
            self._point_to_segment_distance(a_start, b_start, b_end),
            self._point_to_segment_distance(a_end, b_start, b_end),
            self._point_to_segment_distance(b_start, a_start, a_end),
            self._point_to_segment_distance(b_end, a_start, a_end),
        ]

        return min(distances)

    def _point_to_segment_distance(
        self,
        point: Tuple[float, float],
        seg_start: Tuple[float, float],
        seg_end: Tuple[float, float]
    ) -> float:
        """Calculate minimum distance from a point to a line segment."""
        px, py = point
        x1, y1 = seg_start
        x2, y2 = seg_end

        # Vector from seg_start to seg_end
        dx = x2 - x1
        dy = y2 - y1

        # Handle zero-length segment
        seg_length_sq = dx * dx + dy * dy
        if seg_length_sq < 1e-10:
            return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)

        # Parameter t of closest point on infinite line
        t = ((px - x1) * dx + (py - y1) * dy) / seg_length_sq

        # Clamp t to [0, 1] to stay on segment
        t = max(0, min(1, t))

        # Closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Distance from point to closest point
        return math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)

    def _segments_intersect(
        self,
        a_start: Tuple[float, float],
        a_end: Tuple[float, float],
        b_start: Tuple[float, float],
        b_end: Tuple[float, float]
    ) -> bool:
        """Check if two line segments intersect using cross product method."""
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        d1 = cross(b_start, b_end, a_start)
        d2 = cross(b_start, b_end, a_end)
        d3 = cross(a_start, a_end, b_start)
        d4 = cross(a_start, a_end, b_end)

        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True

        # Check for collinear cases
        eps = 1e-10
        if abs(d1) < eps and self._on_segment(b_start, b_end, a_start):
            return True
        if abs(d2) < eps and self._on_segment(b_start, b_end, a_end):
            return True
        if abs(d3) < eps and self._on_segment(a_start, a_end, b_start):
            return True
        if abs(d4) < eps and self._on_segment(a_start, a_end, b_end):
            return True

        return False

    def _on_segment(
        self,
        seg_start: Tuple[float, float],
        seg_end: Tuple[float, float],
        point: Tuple[float, float]
    ) -> bool:
        """Check if a point lies on a segment (assuming collinearity)."""
        return (
            min(seg_start[0], seg_end[0]) <= point[0] <= max(seg_start[0], seg_end[0]) and
            min(seg_start[1], seg_end[1]) <= point[1] <= max(seg_start[1], seg_end[1])
        )

    def get_total_segments(self) -> int:
        """Get total number of occupied segments across all planes."""
        return sum(len(segs) for segs in self._planes.values())

    def clear(self) -> None:
        """Clear all occupancy data."""
        self._planes.clear()

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "planes": {
                plane_id: [seg.to_dict() for seg in segments]
                for plane_id, segments in self._planes.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OccupancyMap":
        """Deserialize from dictionary."""
        occ = cls()
        for plane_id, segments in data.get("planes", {}).items():
            for seg_data in segments:
                occ.reserve(plane_id, OccupiedSegment.from_dict(seg_data))
        return occ
