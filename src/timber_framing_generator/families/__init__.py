# File: src/timber_framing_generator/families/__init__.py
"""
Family Resolver system for automated Revit family loading.

This package provides a cloud-based family resolver that:
- Maintains a JSON manifest of required Revit families
- Downloads missing families from a remote provider (GitHub, GCS)
- Caches families locally for offline use
- Loads families into Revit via Document.LoadFamily()
- Activates types via FamilySymbol.Activate()

Usage:
    from src.timber_framing_generator.families import (
        FamilyResolver, FamilyManifest, ResolutionResult,
        GitHubProvider, FamilyCache,
    )
"""

# Manifest schema
from .manifest import (
    FamilyTypeInfo,
    FamilyEntry,
    FamilyManifest,
    parse_manifest,
    serialize_manifest,
    validate_manifest,
    get_required_profiles,
    get_families_for_elements,
)

# Providers
from .providers import (
    FamilyProvider,
    GitHubProvider,
    LocalFileProvider,
)

# Cache
from .cache import FamilyCache

# Resolver
from .resolver import (
    ResolutionResult,
    FamilyResolver,
)

__all__ = [
    # Manifest
    "FamilyTypeInfo",
    "FamilyEntry",
    "FamilyManifest",
    "parse_manifest",
    "serialize_manifest",
    "validate_manifest",
    "get_required_profiles",
    "get_families_for_elements",
    # Providers
    "FamilyProvider",
    "GitHubProvider",
    "LocalFileProvider",
    # Cache
    "FamilyCache",
    # Resolver
    "ResolutionResult",
    "FamilyResolver",
]
