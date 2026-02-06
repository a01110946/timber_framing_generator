# File: src/timber_framing_generator/wall_junctions/__init__.py

"""Wall junction analysis module.

Detects, classifies, and resolves wall junctions (L-corners, T-intersections,
X-crossings) to produce per-layer extension/trim adjustments for downstream
components (framing, sheathing, finishes).

Usage:
    from src.timber_framing_generator.wall_junctions import analyze_junctions

    graph = analyze_junctions(walls_data)
    junctions_json = json.dumps(graph.to_dict(), indent=2)

    # Get adjustments for a specific wall
    adjustments = graph.get_adjustments_for_wall("wall_A")
"""

from .junction_types import (
    JunctionType,
    JoinType,
    AdjustmentType,
    LayerFunction,
    LayerSide,
    WallConnection,
    JunctionNode,
    WallLayerInfo,
    WallLayer,
    WallAssemblyDef,
    LayerAdjustment,
    JunctionResolution,
    JunctionGraph,
)

from .junction_detector import build_junction_graph

from .junction_resolver import (
    analyze_junctions,
    resolve_all_junctions,
    build_wall_layers_map,
    build_wall_adjustments_map,
    build_default_wall_layers,
)

__all__ = [
    # Main entry point
    "analyze_junctions",
    # Types
    "JunctionType",
    "JoinType",
    "AdjustmentType",
    "LayerFunction",
    "LayerSide",
    "WallConnection",
    "JunctionNode",
    "WallLayerInfo",
    "WallLayer",
    "WallAssemblyDef",
    "LayerAdjustment",
    "JunctionResolution",
    "JunctionGraph",
    # Detector
    "build_junction_graph",
    # Resolver
    "resolve_all_junctions",
    "build_wall_layers_map",
    "build_wall_adjustments_map",
    "build_default_wall_layers",
]
