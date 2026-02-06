# File: src/timber_framing_generator/cavity/cavity.py
"""
Cavity data model for wall framing.

A Cavity is the smallest rectangular void between framing members in a wall.
Bounded by studs (left/right) and plates/headers/sills/blocking (top/bottom).

This is a foundational data layer reusable by:
- MEP routing (pipe placement within bays)
- Insulation (fill quantities and sizing)
- Sheathing (nailing patterns per bay)
- Electrical (box placement and wire runs)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class CavityConfig:
    """Configuration for cavity decomposition.

    Attributes:
        min_clear_width: Minimum cavity width to keep (feet). Filters out
            zero-width bays like king_stud+trimmer adjacency.
        min_clear_height: Minimum cavity height to keep (feet).
        stud_width: Stud face width in feet (derived mode). Default 1.5".
        stud_spacing: Stud center-to-center spacing in feet (derived mode).
            Default 16" OC. NOT hardcoded -- use actual wall config.
        plate_thickness: Top/bottom plate thickness in feet. Default 1.5".
        tolerance: Geometric comparison tolerance in feet.
    """
    min_clear_width: float = 0.01     # ~0.12" filter threshold
    min_clear_height: float = 0.01
    stud_width: float = 0.125         # 1.5" = 0.125 ft
    stud_spacing: float = 1.333       # 16" OC = 1.333 ft
    plate_thickness: float = 0.125    # 1.5" = 0.125 ft
    tolerance: float = 1e-4


@dataclass
class Cavity:
    """A rectangular void between framing members in a wall.

    Cavities are the smallest addressable zones in the wall hierarchy:
    Wall -> Panel -> Cell -> Cavity

    Each cavity is bounded by exactly four framing members (or wall edges).

    Attributes:
        id: Unique identifier, e.g. "wall_A_cav_3".
        wall_id: Parent wall identifier.
        cell_id: Parent cell identifier (SC, SCC, HCC).
        u_min: Left boundary U-coordinate (inside face of left member).
        u_max: Right boundary U-coordinate (inside face of right member).
        v_min: Bottom boundary V-coordinate (top of bottom plate/sill/blocking).
        v_max: Top boundary V-coordinate (bottom of top plate/header/blocking).
        depth: Wall cavity depth (thickness available for routing).
        left_member: Type of left bounding member
            ("stud", "king_stud", "trimmer", "wall_edge").
        right_member: Type of right bounding member.
        top_member: Type of top bounding member
            ("top_plate", "header", "blocking", "wall_edge").
        bottom_member: Type of bottom bounding member
            ("bottom_plate", "sill", "blocking", "wall_edge").
        metadata: Additional cavity-specific data.
    """
    id: str
    wall_id: str
    cell_id: str
    u_min: float
    u_max: float
    v_min: float
    v_max: float
    depth: float
    left_member: str
    right_member: str
    top_member: str
    bottom_member: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def clear_width(self) -> float:
        """Clear width available inside the cavity (U direction)."""
        return self.u_max - self.u_min

    @property
    def clear_height(self) -> float:
        """Clear height available inside the cavity (V direction)."""
        return self.v_max - self.v_min

    @property
    def center_u(self) -> float:
        """Center U-coordinate of the cavity."""
        return (self.u_min + self.u_max) / 2.0

    @property
    def center_v(self) -> float:
        """Center V-coordinate of the cavity."""
        return (self.v_min + self.v_max) / 2.0

    def contains_uv(self, u: float, v: float, tolerance: float = 1e-4) -> bool:
        """Check if a UV point is inside this cavity.

        Args:
            u: U-coordinate to test.
            v: V-coordinate to test.
            tolerance: Boundary tolerance (inclusive).

        Returns:
            True if the point is within cavity bounds.
        """
        return (
            self.u_min - tolerance <= u <= self.u_max + tolerance
            and self.v_min - tolerance <= v <= self.v_max + tolerance
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize cavity to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Cavity":
        """Deserialize cavity from dictionary.

        Args:
            data: Dictionary with cavity fields.

        Returns:
            Cavity instance.
        """
        return cls(
            id=data["id"],
            wall_id=data["wall_id"],
            cell_id=data["cell_id"],
            u_min=float(data["u_min"]),
            u_max=float(data["u_max"]),
            v_min=float(data["v_min"]),
            v_max=float(data["v_max"]),
            depth=float(data["depth"]),
            left_member=data["left_member"],
            right_member=data["right_member"],
            top_member=data["top_member"],
            bottom_member=data["bottom_member"],
            metadata=data.get("metadata", {}),
        )


def serialize_cavities(cavities: List[Cavity]) -> str:
    """Serialize a list of cavities to JSON string.

    Args:
        cavities: List of Cavity objects.

    Returns:
        JSON string representation.
    """
    return json.dumps([c.to_dict() for c in cavities], indent=2)


def deserialize_cavities(json_str: str) -> List[Cavity]:
    """Deserialize a JSON string to a list of cavities.

    Args:
        json_str: JSON string (array of cavity dicts).

    Returns:
        List of Cavity objects.
    """
    data = json.loads(json_str)
    return [Cavity.from_dict(d) for d in data]
