# File: src/timber_framing_generator/mep/routing/__init__.py
"""
MEP Routing Module

Provides the Obstacle-Aware Hanan Sequential (OAHS) routing solver
for MEP systems in offsite panelized construction.

Components:
- OccupancyMap: Tracks reserved space to prevent conflicts
- RoutingDomain: Represents 2D routing planes (walls, floors)
- RoutingTarget: Valid destinations for MEP routes
- MultiDomainGraph: Unified graph spanning all domains
"""

from .occupancy import OccupancyMap, OccupiedSegment
from .domains import RoutingDomainType, RoutingDomain, Obstacle, Point2D
from .targets import RoutingTarget, TargetType
from .graph import MultiDomainGraph, TransitionEdge

__all__ = [
    # Occupancy
    "OccupancyMap",
    "OccupiedSegment",
    # Domains
    "RoutingDomainType",
    "RoutingDomain",
    "Obstacle",
    "Point2D",
    # Targets
    "RoutingTarget",
    "TargetType",
    # Graph
    "MultiDomainGraph",
    "TransitionEdge",
]
