# File: src/constructai_demo/coordinate_converter.py
"""Convert Kreo pixel coordinates to Revit feet.

Pipeline: Pixel (top-left origin) -> Meters (Y-flipped) -> Feet (Revit internal)

The scale (meters per pixel) is derived from the wall data itself by comparing
each wall's pixel distance to its real-world length in meters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .kreo_parser import KreoOpening, KreoPoint, KreoWall


METERS_TO_FEET: float = 3.28084


@dataclass
class ConvertedPoint:
    """A point in Revit feet (bottom-left origin, Y-up)."""

    x: float  # feet
    y: float  # feet


@dataclass
class ConvertedWall:
    """A wall with coordinates in Revit feet."""

    p1: ConvertedPoint
    p2: ConvertedPoint
    length_ft: float
    thickness_ft: float
    thickness_m: float  # keep original for classification
    original_index: int
    is_exterior: bool = False


@dataclass
class ConvertedOpening:
    """A door/window with coordinates in Revit feet."""

    p1: ConvertedPoint
    p2: ConvertedPoint
    width_ft: float
    opening_type: str  # 'door' or 'window'
    original_index: int
    revit_type: Optional[str] = None
    sill_height_in: Optional[float] = None


@dataclass
class ConvertedElements:
    """All elements converted to Revit feet."""

    walls: List[ConvertedWall] = field(default_factory=list)
    doors: List[ConvertedOpening] = field(default_factory=list)
    windows: List[ConvertedOpening] = field(default_factory=list)
    scale_m_per_px: float = 0.0
    max_y_px: float = 0.0


def compute_scale(walls: List[KreoWall]) -> float:
    """Derive meters-per-pixel scale from wall data.

    For each wall, computes pixel distance between p1 and p2, then divides
    the known real-world length by the pixel distance. Averages across all
    walls for robustness.

    Args:
        walls: List of parsed KreoWall objects.

    Returns:
        Scale in meters per pixel.

    Raises:
        ValueError: If no walls provided or all have zero pixel distance.
    """
    if not walls:
        raise ValueError("Cannot compute scale from empty wall list")

    scales: List[float] = []
    for wall in walls:
        px_dist = _pixel_distance(wall.p1, wall.p2)
        if px_dist > 1e-6:  # avoid division by zero
            scales.append(wall.length / px_dist)

    if not scales:
        raise ValueError("All walls have zero pixel distance")

    return sum(scales) / len(scales)


def find_max_y(walls: List[KreoWall],
               doors: List[KreoOpening] | None = None,
               windows: List[KreoOpening] | None = None) -> float:
    """Find the maximum Y pixel coordinate across all elements.

    Used for Y-axis flipping (top-left to bottom-left origin).

    Args:
        walls: List of parsed wall objects.
        doors: Optional list of door objects.
        windows: Optional list of window objects.

    Returns:
        Maximum Y pixel value.
    """
    max_y = 0.0
    for wall in walls:
        max_y = max(max_y, wall.p1.y, wall.p2.y)
    for opening in (doors or []):
        max_y = max(max_y, opening.p1.y, opening.p2.y)
    for opening in (windows or []):
        max_y = max(max_y, opening.p1.y, opening.p2.y)
    return max_y


def convert_point(px: float, py: float,
                  scale: float, max_y_px: float) -> ConvertedPoint:
    """Convert a single pixel coordinate to Revit feet.

    Args:
        px: X pixel coordinate.
        py: Y pixel coordinate.
        scale: Meters per pixel.
        max_y_px: Maximum Y pixel value (for Y-flip).

    Returns:
        ConvertedPoint in Revit feet with bottom-left origin.
    """
    # Convert to meters with Y-flip
    x_m = px * scale
    y_m = (max_y_px - py) * scale

    # Convert to feet
    return ConvertedPoint(
        x=x_m * METERS_TO_FEET,
        y=y_m * METERS_TO_FEET,
    )


def convert_all_elements(
    walls: List[KreoWall],
    doors: List[KreoOpening] | None = None,
    windows: List[KreoOpening] | None = None,
) -> ConvertedElements:
    """Convert all Kreo elements from pixel coordinates to Revit feet.

    Args:
        walls: Parsed wall objects.
        doors: Parsed door objects (optional).
        windows: Parsed window objects (optional).

    Returns:
        ConvertedElements with all coordinates in Revit feet.
    """
    doors = doors or []
    windows = windows or []

    scale = compute_scale(walls)
    max_y_px = find_max_y(walls, doors, windows)

    converted_walls: List[ConvertedWall] = []
    for wall in walls:
        p1 = convert_point(wall.p1.x, wall.p1.y, scale, max_y_px)
        p2 = convert_point(wall.p2.x, wall.p2.y, scale, max_y_px)
        converted_walls.append(ConvertedWall(
            p1=p1,
            p2=p2,
            length_ft=wall.length * METERS_TO_FEET,
            thickness_ft=wall.thickness * METERS_TO_FEET,
            thickness_m=wall.thickness,
            original_index=wall.index,
        ))

    converted_doors: List[ConvertedOpening] = []
    for door in doors:
        p1 = convert_point(door.p1.x, door.p1.y, scale, max_y_px)
        p2 = convert_point(door.p2.x, door.p2.y, scale, max_y_px)
        converted_doors.append(ConvertedOpening(
            p1=p1,
            p2=p2,
            width_ft=door.length * METERS_TO_FEET,
            opening_type="door",
            original_index=door.index,
        ))

    converted_windows: List[ConvertedOpening] = []
    for window in windows:
        p1 = convert_point(window.p1.x, window.p1.y, scale, max_y_px)
        p2 = convert_point(window.p2.x, window.p2.y, scale, max_y_px)
        converted_windows.append(ConvertedOpening(
            p1=p1,
            p2=p2,
            width_ft=window.length * METERS_TO_FEET,
            opening_type="window",
            original_index=window.index,
        ))

    return ConvertedElements(
        walls=converted_walls,
        doors=converted_doors,
        windows=converted_windows,
        scale_m_per_px=scale,
        max_y_px=max_y_px,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pixel_distance(p1: KreoPoint, p2: KreoPoint) -> float:
    """Euclidean distance between two pixel points."""
    return math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)
