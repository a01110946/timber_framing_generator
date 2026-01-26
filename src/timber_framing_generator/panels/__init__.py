# File: src/timber_framing_generator/panels/__init__.py
"""
Wall panelization system module.

This module provides wall panelization for offsite construction:
- Panel configuration and size constraints
- Corner handling for accurate panel geometry
- Joint optimization with exclusion zones
- Panel decomposition with stud alignment

Example:
    >>> from src.timber_framing_generator.panels import (
    ...     PanelConfig, decompose_wall_to_panels, decompose_all_walls
    ... )
    >>> config = PanelConfig(max_panel_length=24.0)
    >>> results = decompose_wall_to_panels(wall_data, framing_data, config)
    >>> print(f"Created {results['total_panel_count']} panels")
"""

from .panel_config import (
    PanelConfig,
    CornerPriority,
    ExclusionZone,
)

from .corner_handler import (
    WallEndpoint,
    WallCornerInfo,
    detect_wall_corners,
    calculate_corner_adjustments,
    apply_corner_adjustments,
    get_adjusted_wall_length,
)

from .joint_optimizer import (
    find_exclusion_zones,
    find_optimal_joints,
    get_panel_boundaries,
    validate_joints,
)

from .panel_decomposer import (
    decompose_wall_to_panels,
    decompose_all_walls,
    serialize_panel_results,
    deserialize_panel_results,
)

__all__ = [
    # Configuration
    "PanelConfig",
    "CornerPriority",
    "ExclusionZone",
    # Corner handling
    "WallEndpoint",
    "WallCornerInfo",
    "detect_wall_corners",
    "calculate_corner_adjustments",
    "apply_corner_adjustments",
    "get_adjusted_wall_length",
    # Joint optimization
    "find_exclusion_zones",
    "find_optimal_joints",
    "get_panel_boundaries",
    "validate_joints",
    # Panel decomposition
    "decompose_wall_to_panels",
    "decompose_all_walls",
    "serialize_panel_results",
    "deserialize_panel_results",
]
