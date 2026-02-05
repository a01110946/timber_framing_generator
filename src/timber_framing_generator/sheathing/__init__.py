# File: src/timber_framing_generator/sheathing/__init__.py
"""
Sheathing generation module for wall framing.

This module provides functionality to generate sheathing panels (plywood,
OSB, gypsum) for walls with proper layout, joint staggering, and opening cutouts.

Key Components:
    - SheathingGenerator: Main class for generating sheathing panels
    - SheathingPanel: Data class representing a single sheathing panel
    - SheathingMaterial: Material specifications (thickness, type, properties)
    - PanelSize: Standard panel dimensions (4x8, 4x9, 4x10)

Configuration Options:
    All values are configurable with sensible defaults:
    - panel_size: "4x8" (default), "4x9", "4x10", "4x12"
    - stagger_offset: 2.0 feet (default) - joint stagger between rows
    - min_piece_width: 0.5 feet (default) - minimum panel piece width
    - material: "structural_plywood_7_16" (default) - sheathing material

Example:
    >>> from src.timber_framing_generator.sheathing import (
    ...     SheathingGenerator, generate_wall_sheathing
    ... )
    >>>
    >>> # Simple usage
    >>> result = generate_wall_sheathing(wall_data)
    >>>
    >>> # With configuration
    >>> config = {
    ...     "panel_size": "4x10",
    ...     "material": "osb_1_2",
    ...     "stagger_offset": 4.0,
    ... }
    >>> result = generate_wall_sheathing(wall_data, config)
"""

from .sheathing_profiles import (
    SheathingMaterial,
    SheathingType,
    PanelSize,
    SHEATHING_MATERIALS,
    PANEL_SIZES,
    DEFAULT_MATERIALS,
    DEFAULT_PANEL_SIZE,
    get_sheathing_material,
    get_panel_size,
    list_materials_by_type,
)

from .sheathing_generator import (
    SheathingGenerator,
    SheathingPanel,
    Cutout,
    generate_wall_sheathing,
)

from .sheathing_geometry import (
    SheathingPanelGeometry,
    create_sheathing_breps,
    create_sheathing_breps_batch,
    uvw_to_world,
    create_panel_brep,
)

__all__ = [
    # Classes
    "SheathingGenerator",
    "SheathingPanel",
    "SheathingPanelGeometry",
    "SheathingMaterial",
    "SheathingType",
    "PanelSize",
    "Cutout",
    # Dictionaries
    "SHEATHING_MATERIALS",
    "PANEL_SIZES",
    "DEFAULT_MATERIALS",
    "DEFAULT_PANEL_SIZE",
    # Functions
    "get_sheathing_material",
    "get_panel_size",
    "list_materials_by_type",
    "generate_wall_sheathing",
    # Geometry functions
    "create_sheathing_breps",
    "create_sheathing_breps_batch",
    "uvw_to_world",
    "create_panel_brep",
]
