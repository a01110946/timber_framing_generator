# File: src/timber_framing_generator/mep/__init__.py
"""
MEP (Mechanical, Electrical, Plumbing) integration module.

This module provides MEP system integration for offsite framing:
- Connector extraction from Revit fixtures/equipment
- Route calculation through framing
- Penetration generation for framing members

Submodules:
    core: Base classes and utilities for all MEP domains
    plumbing: Plumbing-specific implementation
    hvac: HVAC-specific implementation (future)
    electrical: Electrical-specific implementation (future)

Example:
    >>> from src.timber_framing_generator.mep import PlumbingSystem
    >>> from src.timber_framing_generator.mep.core import MEPDomain, MEPConnector
    >>>
    >>> plumbing = PlumbingSystem()
    >>> connectors = plumbing.extract_connectors(fixtures)
"""

from src.timber_framing_generator.core.mep_system import (
    MEPDomain,
    MEPConnector,
    MEPRoute,
    MEPSystem,
)

__all__ = [
    "MEPDomain",
    "MEPConnector",
    "MEPRoute",
    "MEPSystem",
]
