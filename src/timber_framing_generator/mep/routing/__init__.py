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
- Graph Builders: Wall, floor, and unified graph construction
"""

from .occupancy import OccupancyMap, OccupiedSegment
from .domains import RoutingDomainType, RoutingDomain, Obstacle, Point2D
from .targets import RoutingTarget, TargetType, TargetCandidate
from .graph import MultiDomainGraph, TransitionEdge, TransitionType
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
from .wall_graph import WallGraphBuilder, build_wall_graph_from_data
from .floor_graph import FloorGraphBuilder, build_floor_graph_from_bounds
from .graph_builder import (
    UnifiedGraphBuilder,
    TransitionGenerator,
    build_routing_graph,
)
from .route_segment import RouteSegment, SegmentDirection, Route
from .hanan_grid import (
    HananGrid,
    HananMST,
    SteinerTreeBuilder,
    compute_hanan_mst,
)
from .pathfinding import (
    AStarPathfinder,
    PathReconstructor,
    PathResult,
    find_shortest_path,
    find_path_as_route,
)
from .multi_domain_pathfinder import MultiDomainPathfinder
from .routing_result import (
    RoutingResult,
    RoutingStatistics,
    FailedConnector,
    RoutingRequest,
)
from .oahs_router import (
    OAHSRouter,
    ConnectorSequencer,
    ConflictResolver,
    create_oahs_router,
)

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
    "TransitionType",
    # Graph Builders
    "WallGraphBuilder",
    "FloorGraphBuilder",
    "UnifiedGraphBuilder",
    "TransitionGenerator",
    "build_wall_graph_from_data",
    "build_floor_graph_from_bounds",
    "build_routing_graph",
    # Route Segments
    "RouteSegment",
    "SegmentDirection",
    "Route",
    # Hanan Grid MST
    "HananGrid",
    "HananMST",
    "SteinerTreeBuilder",
    "compute_hanan_mst",
    # Pathfinding
    "AStarPathfinder",
    "PathReconstructor",
    "PathResult",
    "find_shortest_path",
    "find_path_as_route",
    "MultiDomainPathfinder",
    # Routing Results
    "RoutingResult",
    "RoutingStatistics",
    "FailedConnector",
    "RoutingRequest",
    # OAHS Router
    "OAHSRouter",
    "ConnectorSequencer",
    "ConflictResolver",
    "create_oahs_router",
]
