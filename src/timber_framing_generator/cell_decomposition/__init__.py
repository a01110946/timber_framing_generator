# File: src/timber_framing_generator/cell_decomposition/__init__.py
"""
Cell decomposition module for wall framing generation.

This module provides:
- Cell types (SC, OC, HCC, SCC, WBC) creation and manipulation
- Wall-to-cell decomposition algorithms
- Panel-aware cell decomposition helpers

Example:
    >>> from src.timber_framing_generator.cell_decomposition import (
    ...     decompose_wall_to_cells,
    ...     get_openings_in_range,
    ...     generate_panel_cell_id,
    ... )
"""

from .cell_types import (
    CellDataDict,
    create_wall_boundary_cell_data,
    create_opening_cell_data,
    create_stud_cell_data,
    create_sill_cripple_cell_data,
    create_header_cripple_cell_data,
    deconstruct_cell,
    deconstruct_all_cells,
)

from .cell_segmentation import (
    decompose_wall_to_cells,
    # Panel-aware helpers
    get_openings_in_range,
    clip_opening_to_range,
    check_opening_spans_panel_joint,
    get_panel_id_prefix,
    generate_panel_cell_id,
)

__all__ = [
    # Cell types
    "CellDataDict",
    "create_wall_boundary_cell_data",
    "create_opening_cell_data",
    "create_stud_cell_data",
    "create_sill_cripple_cell_data",
    "create_header_cripple_cell_data",
    "deconstruct_cell",
    "deconstruct_all_cells",
    # Cell segmentation
    "decompose_wall_to_cells",
    # Panel-aware helpers
    "get_openings_in_range",
    "clip_opening_to_range",
    "check_opening_spans_panel_joint",
    "get_panel_id_prefix",
    "generate_panel_cell_id",
]
