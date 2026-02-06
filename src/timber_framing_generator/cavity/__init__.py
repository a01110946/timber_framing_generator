# File: src/timber_framing_generator/cavity/__init__.py
"""
Cavity module for wall framing.

Computes rectangular voids (cavities) between framing members.
Reusable by MEP routing, insulation, sheathing, nailing, and electrical.

Hierarchy: Wall -> Panel -> Cell -> Cavity
"""

from .cavity import Cavity, CavityConfig, serialize_cavities, deserialize_cavities
from .cavity_decomposer import (
    decompose_wall_cavities,
    find_cavity_for_uv,
    find_nearest_cavity,
    find_adjacent_cavities,
)

__all__ = [
    "Cavity",
    "CavityConfig",
    "decompose_wall_cavities",
    "find_cavity_for_uv",
    "find_nearest_cavity",
    "find_adjacent_cavities",
    "serialize_cavities",
    "deserialize_cavities",
]
