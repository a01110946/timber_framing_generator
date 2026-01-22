# File: src/timber_framing_generator/materials/__init__.py
"""
Material-specific framing implementations.

This package contains strategy implementations for different framing
material systems (Timber, CFS, etc.).

Usage:
    from src.timber_framing_generator.materials.timber import TimberFramingStrategy

    # Or use the factory pattern:
    from src.timber_framing_generator.core import get_framing_strategy, MaterialSystem
    strategy = get_framing_strategy(MaterialSystem.TIMBER)
"""

# Import material modules to trigger strategy registration
from . import timber

# Re-export for convenience
from .timber import TimberFramingStrategy

__all__ = [
    "TimberFramingStrategy",
]
