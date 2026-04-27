# File: src/constructai_demo/wall_classifier.py
"""Classify walls by thickness into framing categories.

Uses Kreo-detected wall thickness to determine:
- Interior 2x4 (thickness < 0.115m / ~4.5")
- Exterior 2x4 (0.115m <= thickness < 0.14m / ~5.5")
- Exterior 2x6 (thickness >= 0.14m / garage front wall)
"""

from __future__ import annotations

from enum import Enum
from typing import List, Tuple

from .coordinate_converter import ConvertedWall


class WallClass(Enum):
    """Wall framing classification."""

    INTERIOR_2X4 = "interior_2x4"
    EXTERIOR_2X4 = "exterior_2x4"
    EXTERIOR_2X6 = "exterior_2x6"


# Two-threshold classification (meters):
#   < INTERIOR_THRESHOLD  -> interior 2x4
#   >= INTERIOR_THRESHOLD and < EXTERIOR_2X6_THRESHOLD -> exterior 2x4
#   >= EXTERIOR_2X6_THRESHOLD -> exterior 2x6 (garage front wall)
INTERIOR_THRESHOLD_M: float = 0.115
EXTERIOR_2X6_THRESHOLD_M: float = 0.14

# Target thicknesses for Revit wall type matching (in feet)
WALL_CLASS_THICKNESS_FT = {
    WallClass.INTERIOR_2X4: 3.5 / 12.0,  # 3.5 inches = 0.2917 ft
    WallClass.EXTERIOR_2X4: 3.5 / 12.0,  # 3.5 inches = 0.2917 ft (same stud, different assembly)
    WallClass.EXTERIOR_2X6: 5.5 / 12.0,  # 5.5 inches = 0.4583 ft
}

# Friendly display names
WALL_CLASS_NAMES = {
    WallClass.INTERIOR_2X4: "Generic - 3.5\" (2x4 INT)",
    WallClass.EXTERIOR_2X4: "Generic - 3.5\" (2x4 EXT)",
    WallClass.EXTERIOR_2X6: "Generic - 5.5\" (2x6 EXT)",
}


def classify_wall(thickness_m: float, is_exterior: bool = False) -> WallClass:
    """Classify a wall by its thickness and optional exterior flag.

    Uses two thresholds to distinguish three wall types:
    - Interior 2x4: thin walls (partitions)
    - Exterior 2x4: medium walls (exterior with stucco/insulation assembly)
    - Exterior 2x6: thick walls (garage front with wider assembly)

    If is_exterior=True and thickness alone would yield INTERIOR_2X4,
    the result is promoted to EXTERIOR_2X4. This honours Kreo's explicit
    exterior detection for thin exterior walls.

    Args:
        thickness_m: Wall thickness in meters from Kreo detection.
        is_exterior: Kreo-detected exterior flag (default False).

    Returns:
        WallClass enum value.
    """
    if thickness_m < INTERIOR_THRESHOLD_M:
        return WallClass.EXTERIOR_2X4 if is_exterior else WallClass.INTERIOR_2X4
    if thickness_m < EXTERIOR_2X6_THRESHOLD_M:
        return WallClass.EXTERIOR_2X4
    return WallClass.EXTERIOR_2X6


def classify_walls(walls: List[ConvertedWall]) -> List[Tuple[ConvertedWall, WallClass]]:
    """Classify a list of converted walls.

    Args:
        walls: List of ConvertedWall objects (with thickness_m).

    Returns:
        List of (wall, classification) tuples.
    """
    return [(wall, classify_wall(wall.thickness_m)) for wall in walls]


def get_classification_summary(walls: List[ConvertedWall]) -> dict:
    """Get a summary of wall classifications.

    Args:
        walls: List of ConvertedWall objects.

    Returns:
        Dict with counts per classification.
    """
    classified = classify_walls(walls)
    summary = {wc: 0 for wc in WallClass}
    for _, wc in classified:
        summary[wc] += 1
    return {wc.value: count for wc, count in summary.items()}
