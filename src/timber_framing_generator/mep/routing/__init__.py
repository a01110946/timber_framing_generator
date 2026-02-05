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
- TargetCandidateGenerator: Finds targets using pluggable heuristics
- Heuristics: System-specific target selection strategies
"""

from .occupancy import OccupancyMap, OccupiedSegment
from .domains import RoutingDomainType, RoutingDomain, Obstacle, Point2D
from .targets import RoutingTarget, TargetType, TargetCandidate
from .graph import MultiDomainGraph, TransitionEdge
from .target_generator import (
    TargetCandidateGenerator,
    detect_wet_walls,
    generate_targets_from_walls,
    WetWallInfo,
)
from .heuristics import (
    TargetHeuristic,
    SanitaryHeuristic,
    VentHeuristic,
    SupplyHeuristic,
    PowerHeuristic,
    DataHeuristic,
)
from .heuristics.base import ConnectorInfo

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
    "TargetCandidate",
    # Target Generator
    "TargetCandidateGenerator",
    "ConnectorInfo",
    "WetWallInfo",
    "detect_wet_walls",
    "generate_targets_from_walls",
    # Heuristics
    "TargetHeuristic",
    "SanitaryHeuristic",
    "VentHeuristic",
    "SupplyHeuristic",
    "PowerHeuristic",
    "DataHeuristic",
    # Graph
    "MultiDomainGraph",
    "TransitionEdge",
]
