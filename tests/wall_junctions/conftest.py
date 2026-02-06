# File: tests/wall_junctions/conftest.py

"""Shared test fixtures for wall junction tests.

Provides mock wall data for various junction configurations:
L-corners, T-intersections, X-crossings, free ends, and non-orthogonal angles.
"""

import pytest
from typing import List, Dict


# =============================================================================
# Helper: Create a single mock wall
# =============================================================================


def create_mock_wall(
    wall_id: str,
    start: tuple,
    end: tuple,
    thickness: float = 0.3958,
    height: float = 8.0,
    is_exterior: bool = True,
) -> Dict:
    """Create a mock wall dict matching walls_json format.

    Args:
        wall_id: Unique wall identifier.
        start: (x, y, z) start point.
        end: (x, y, z) end point.
        thickness: Wall thickness in feet.
        height: Wall height in feet.
        is_exterior: Whether the wall is exterior.
    """
    import math

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)

    # Normalize direction
    if length > 0:
        x_axis = (dx / length, dy / length, dz / length)
    else:
        x_axis = (1.0, 0.0, 0.0)

    # Y-axis = world Z (vertical)
    y_axis = (0.0, 0.0, 1.0)

    # Z-axis = cross product of x_axis and y_axis (wall normal)
    z_axis = (
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    )

    return {
        "wall_id": wall_id,
        "wall_length": length,
        "wall_height": height,
        "wall_thickness": thickness,
        "base_elevation": start[2],
        "top_elevation": start[2] + height,
        "base_curve_start": {"x": start[0], "y": start[1], "z": start[2]},
        "base_curve_end": {"x": end[0], "y": end[1], "z": end[2]},
        "base_plane": {
            "origin": {"x": start[0], "y": start[1], "z": start[2]},
            "x_axis": {"x": x_axis[0], "y": x_axis[1], "z": x_axis[2]},
            "y_axis": {"x": y_axis[0], "y": y_axis[1], "z": y_axis[2]},
            "z_axis": {"x": z_axis[0], "y": z_axis[1], "z": z_axis[2]},
        },
        "openings": [],
        "is_exterior": is_exterior,
        "wall_type": "Generic - 6\" (test)",
        "metadata": {},
    }


# =============================================================================
# Fixtures: Junction Configurations
# =============================================================================


@pytest.fixture
def l_corner_walls() -> List[Dict]:
    """Two walls meeting at a 90-degree L-corner.

    Wall A: horizontal, 20 ft long, ends at (20, 0, 0)
    Wall B: vertical, 15 ft long, starts at (20, 0, 0)

    They share endpoint at (20, 0, 0).
    """
    return [
        create_mock_wall("wall_A", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0)),
        create_mock_wall("wall_B", (20.0, 0.0, 0.0), (20.0, 15.0, 0.0)),
    ]


@pytest.fixture
def t_intersection_walls() -> List[Dict]:
    """Wall B terminates mid-span of wall A (T-intersection).

    Wall A: horizontal, 30 ft, from (0,0,0) to (30,0,0)
    Wall B: vertical, 10 ft, starts at (15,0,0) — middle of wall A
    """
    return [
        create_mock_wall("wall_A", (0.0, 0.0, 0.0), (30.0, 0.0, 0.0)),
        create_mock_wall(
            "wall_B",
            (15.0, 0.0, 0.0),
            (15.0, 10.0, 0.0),
            is_exterior=False,
        ),
    ]


@pytest.fixture
def x_crossing_walls() -> List[Dict]:
    """Two walls crossing at (15, 10, 0).

    Wall A: horizontal, from (0, 10, 0) to (30, 10, 0)
    Wall B: vertical, from (15, 0, 0) to (15, 20, 0)
    """
    return [
        create_mock_wall("wall_A", (0.0, 10.0, 0.0), (30.0, 10.0, 0.0)),
        create_mock_wall("wall_B", (15.0, 0.0, 0.0), (15.0, 20.0, 0.0)),
    ]


@pytest.fixture
def free_end_wall() -> List[Dict]:
    """Single wall with no connections (both ends free)."""
    return [
        create_mock_wall("wall_solo", (5.0, 5.0, 0.0), (25.0, 5.0, 0.0)),
    ]


@pytest.fixture
def inline_walls() -> List[Dict]:
    """Two collinear walls meeting end-to-end.

    Wall A: (0, 0, 0) to (10, 0, 0)
    Wall B: (10, 0, 0) to (25, 0, 0)
    """
    return [
        create_mock_wall("wall_A", (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
        create_mock_wall("wall_B", (10.0, 0.0, 0.0), (25.0, 0.0, 0.0)),
    ]


@pytest.fixture
def angled_corner_walls() -> List[Dict]:
    """Two walls meeting at 45 degrees.

    Wall A: horizontal, from (0, 0, 0) to (10, 0, 0)
    Wall B: at 45°, from (10, 0, 0) to (17.07, 7.07, 0)
    """
    import math
    length_b = 10.0
    angle = math.radians(45)
    end_x = 10.0 + length_b * math.cos(angle)
    end_y = 0.0 + length_b * math.sin(angle)

    return [
        create_mock_wall("wall_A", (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
        create_mock_wall("wall_B", (10.0, 0.0, 0.0), (end_x, end_y, 0.0)),
    ]


@pytest.fixture
def different_thickness_walls() -> List[Dict]:
    """Two walls with different thicknesses meeting at L-corner.

    Wall A: 6" thick (0.5 ft), horizontal
    Wall B: 4" thick (0.333 ft), vertical
    """
    return [
        create_mock_wall(
            "wall_thick", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), thickness=0.5
        ),
        create_mock_wall(
            "wall_thin", (20.0, 0.0, 0.0), (20.0, 15.0, 0.0), thickness=0.333
        ),
    ]


@pytest.fixture
def four_room_layout() -> List[Dict]:
    """Realistic 4-wall room layout (rectangle).

    Forms a 20x15 ft rectangle:
    Wall A: bottom  (0,0) → (20,0)
    Wall B: right   (20,0) → (20,15)
    Wall C: top     (20,15) → (0,15)
    Wall D: left    (0,15) → (0,0)

    Should produce 4 L-corners.
    """
    return [
        create_mock_wall("wall_A", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0)),
        create_mock_wall("wall_B", (20.0, 0.0, 0.0), (20.0, 15.0, 0.0)),
        create_mock_wall("wall_C", (20.0, 15.0, 0.0), (0.0, 15.0, 0.0)),
        create_mock_wall("wall_D", (0.0, 15.0, 0.0), (0.0, 0.0, 0.0)),
    ]
