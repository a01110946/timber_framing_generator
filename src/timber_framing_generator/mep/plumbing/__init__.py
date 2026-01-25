# File: src/timber_framing_generator/mep/plumbing/__init__.py
"""
Plumbing system module.

This module provides plumbing-specific MEP integration:
- Plumbing fixture connector extraction
- Pipe routing through wall framing
- Penetration generation for drain, supply, and vent lines

System Types:
    - Sanitary: Drain/waste lines
    - DomesticColdWater: Cold water supply
    - DomesticHotWater: Hot water supply
    - Vent: Vent lines

Example:
    >>> from src.timber_framing_generator.mep.plumbing import PlumbingSystem
    >>> system = PlumbingSystem()
    >>> connectors = system.extract_connectors(fixtures)
    >>> routes = system.calculate_routes(connectors, framing_data, [], config)
"""

from .plumbing_system import PlumbingSystem
from .connector_extractor import (
    extract_plumbing_connectors,
    extract_connectors_from_json,
)
from .pipe_router import (
    calculate_pipe_routes,
    find_wall_entry,
    extract_walls_from_framing,
)
from .penetration_rules import (
    generate_plumbing_penetrations,
    get_pipe_size_info,
    STANDARD_PIPE_SIZES,
    PLUMBING_PENETRATION_CLEARANCE,
    MAX_PENETRATION_RATIO,
)
from .pipe_creator import (
    PipeSegment,
    PipeNetwork,
    parse_routes_json,
    parse_routes_to_segments,
    build_pipe_network,
    build_all_pipe_networks,
    get_networks_summary,
    get_revit_system_type_name,
    SYSTEM_TYPE_MAPPING,
)

__all__ = [
    # Main class
    "PlumbingSystem",
    # Connector extraction
    "extract_plumbing_connectors",
    "extract_connectors_from_json",
    # Pipe routing
    "calculate_pipe_routes",
    "find_wall_entry",
    "extract_walls_from_framing",
    # Penetration generation
    "generate_plumbing_penetrations",
    "get_pipe_size_info",
    # Constants
    "STANDARD_PIPE_SIZES",
    "PLUMBING_PENETRATION_CLEARANCE",
    "MAX_PENETRATION_RATIO",
    "SYSTEM_TYPE_MAPPING",
    # Pipe creation
    "PipeSegment",
    "PipeNetwork",
    "parse_routes_json",
    "parse_routes_to_segments",
    "build_pipe_network",
    "build_all_pipe_networks",
    "get_networks_summary",
    "get_revit_system_type_name",
]
