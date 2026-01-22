# File: src/timber_framing_generator/materials/__init__.py
"""
Material-specific framing implementations.

This package contains strategy implementations for different framing
material systems (Timber, CFS, etc.).

Usage:
    from src.timber_framing_generator.materials.timber import TimberFramingStrategy
    from src.timber_framing_generator.materials.cfs import CFSFramingStrategy

    # Or use the factory pattern (recommended):
    from src.timber_framing_generator.core import get_framing_strategy, MaterialSystem
    strategy = get_framing_strategy(MaterialSystem.TIMBER)
    cfs_strategy = get_framing_strategy(MaterialSystem.CFS)
"""

# Import material modules to trigger strategy registration
from . import timber
from . import cfs

# Re-export for convenience
from .timber import TimberFramingStrategy
from .cfs import CFSFramingStrategy

__all__ = [
    "TimberFramingStrategy",
    "CFSFramingStrategy",
]
