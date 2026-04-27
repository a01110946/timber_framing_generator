# File: src/constructai_demo/opening_matcher.py
"""Match doors and windows to their host walls.

Each opening's midpoint is compared to all wall line segments.
The nearest wall (within tolerance) becomes the host.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from .coordinate_converter import ConvertedOpening, ConvertedPoint, ConvertedWall


# Maximum distance (feet) for an opening to be matched to a wall
DEFAULT_TOLERANCE_FT: float = 1.0


@dataclass
class MatchedOpening:
    """An opening matched to its host wall.

    Attributes:
        opening: The converted opening data.
        host_wall_index: Index into the walls list.
        distance_ft: Distance from opening midpoint to wall segment.
        parameter_t: Normalized position along host wall (0=start, 1=end).
        insertion_point: Point on the wall line closest to opening midpoint.
    """

    opening: ConvertedOpening
    host_wall_index: int
    distance_ft: float
    parameter_t: float
    insertion_point: ConvertedPoint


def match_openings_to_walls(
    walls: List[ConvertedWall],
    openings: List[ConvertedOpening],
    tolerance_ft: float = DEFAULT_TOLERANCE_FT,
) -> Dict[int, List[MatchedOpening]]:
    """Match each opening to its nearest host wall.

    Args:
        walls: List of converted walls in Revit feet.
        openings: List of converted openings (doors and/or windows).
        tolerance_ft: Maximum distance for a valid match.

    Returns:
        Dict mapping wall index -> list of MatchedOpening assigned to it.
        Openings beyond tolerance are excluded (logged but not matched).
    """
    result: Dict[int, List[MatchedOpening]] = {}
    unmatched: List[int] = []

    for opening in openings:
        mid = _midpoint(opening.p1, opening.p2)
        best_wall_idx = -1
        best_dist = float("inf")
        best_t = 0.0
        best_closest = ConvertedPoint(0.0, 0.0)

        for wall_idx, wall in enumerate(walls):
            dist, t, closest = point_to_segment_distance(
                mid, wall.p1, wall.p2
            )
            if dist < best_dist:
                best_dist = dist
                best_wall_idx = wall_idx
                best_t = t
                best_closest = closest

        if best_dist <= tolerance_ft and best_wall_idx >= 0:
            matched = MatchedOpening(
                opening=opening,
                host_wall_index=best_wall_idx,
                distance_ft=best_dist,
                parameter_t=best_t,
                insertion_point=best_closest,
            )
            result.setdefault(best_wall_idx, []).append(matched)
        else:
            unmatched.append(opening.original_index)

    return result


def point_to_segment_distance(
    point: ConvertedPoint,
    seg_start: ConvertedPoint,
    seg_end: ConvertedPoint,
) -> tuple[float, float, ConvertedPoint]:
    """Compute distance from a point to a line segment.

    Args:
        point: The query point.
        seg_start: Start of the line segment.
        seg_end: End of the line segment.

    Returns:
        Tuple of (distance, parameter_t, closest_point):
        - distance: Perpendicular distance in feet.
        - parameter_t: Normalized parameter (0=start, 1=end) of closest point.
        - closest_point: The closest point on the segment.
    """
    dx = seg_end.x - seg_start.x
    dy = seg_end.y - seg_start.y
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq < 1e-12:
        # Degenerate segment (zero length)
        dist = math.sqrt(
            (point.x - seg_start.x) ** 2 + (point.y - seg_start.y) ** 2
        )
        return dist, 0.0, ConvertedPoint(seg_start.x, seg_start.y)

    # Project point onto line, clamped to [0, 1]
    t = ((point.x - seg_start.x) * dx + (point.y - seg_start.y) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))

    closest = ConvertedPoint(
        x=seg_start.x + t * dx,
        y=seg_start.y + t * dy,
    )

    dist = math.sqrt(
        (point.x - closest.x) ** 2 + (point.y - closest.y) ** 2
    )
    return dist, t, closest


def get_unmatched_openings(
    openings: List[ConvertedOpening],
    matched: Dict[int, List[MatchedOpening]],
) -> List[ConvertedOpening]:
    """Find openings that were not matched to any wall.

    Args:
        openings: All openings that were attempted.
        matched: Result from match_openings_to_walls.

    Returns:
        List of unmatched openings.
    """
    matched_indices = set()
    for wall_matches in matched.values():
        for m in wall_matches:
            matched_indices.add(m.opening.original_index)

    return [o for o in openings if o.original_index not in matched_indices]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _midpoint(p1: ConvertedPoint, p2: ConvertedPoint) -> ConvertedPoint:
    """Compute the midpoint of two points."""
    return ConvertedPoint(
        x=(p1.x + p2.x) / 2.0,
        y=(p1.y + p2.y) / 2.0,
    )
