# File: src/timber_framing_generator/materials/timber/__init__.py
"""
Timber framing strategy implementation.

This module provides the TimberFramingStrategy which implements
the FramingStrategy interface for standard timber/lumber framing.

Usage:
    from src.timber_framing_generator.materials.timber import TimberFramingStrategy
    from src.timber_framing_generator.materials.timber.timber_profiles import (
        TIMBER_PROFILES, get_timber_profile
    )
"""

from .timber_strategy import TimberFramingStrategy
from .timber_profiles import (
    TIMBER_PROFILES,
    DEFAULT_TIMBER_PROFILES,
    get_timber_profile,
)

__all__ = [
    "TimberFramingStrategy",
    "TIMBER_PROFILES",
    "DEFAULT_TIMBER_PROFILES",
    "get_timber_profile",
]
