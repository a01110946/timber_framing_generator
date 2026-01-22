# File: src/timber_framing_generator/materials/cfs/__init__.py
"""
CFS (Cold-Formed Steel) framing materials package.

This package provides CFS-specific implementations of the framing strategy
pattern, including steel stud profiles and the CFSFramingStrategy.

Importing this module triggers strategy registration via register_strategy(),
allowing the factory to return CFSFramingStrategy for MaterialSystem.CFS.

Usage:
    # Direct import (triggers registration)
    from src.timber_framing_generator.materials.cfs import (
        CFSFramingStrategy,
        CFS_PROFILES,
        get_cfs_profile,
    )

    # Via factory (recommended)
    from src.timber_framing_generator.core import get_framing_strategy, MaterialSystem
    from src.timber_framing_generator.materials import cfs  # Triggers registration

    strategy = get_framing_strategy(MaterialSystem.CFS)
"""

from .cfs_profiles import (
    CFS_PROFILES,
    DEFAULT_CFS_PROFILES,
    get_cfs_profile,
    list_available_profiles,
)
from .cfs_strategy import CFSFramingStrategy

__all__ = [
    "CFSFramingStrategy",
    "CFS_PROFILES",
    "DEFAULT_CFS_PROFILES",
    "get_cfs_profile",
    "list_available_profiles",
]
