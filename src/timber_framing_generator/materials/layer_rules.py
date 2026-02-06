# File: src/timber_framing_generator/materials/layer_rules.py

"""Per-layer placement rules for wall assembly materials.

Defines rules that govern how each material layer is placed on a wall:
stagger patterns, minimum piece widths, orientation constraints, and
fastener zone definitions. Rules are looked up by material function
and can be overridden per manufacturer or per project.

Usage:
    from src.timber_framing_generator.materials.layer_rules import (
        get_rules_for_layer,
        DEFAULT_RULES,
    )

    rules = get_rules_for_layer("substrate", "exterior")
    stagger = rules.stagger_offset  # feet
    min_width = rules.min_piece_width  # feet
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class StaggerPattern(Enum):
    """Joint stagger pattern between rows."""

    RUNNING_BOND = "running_bond"
    """Offset each row by stagger_offset (standard for sheathing)."""

    NONE = "none"
    """No stagger - joints align vertically."""


class PanelOrientation(Enum):
    """Panel orientation constraint."""

    HORIZONTAL = "horizontal"
    """Long dimension runs horizontally (standard for sheathing)."""

    VERTICAL = "vertical"
    """Long dimension runs vertically (standard for gypsum)."""

    ANY = "any"
    """No constraint on orientation."""


@dataclass
class FastenerSpec:
    """Fastener (nailing) specification for a layer.

    All dimensions in inches.

    Attributes:
        edge_spacing: Fastener spacing at panel perimeter.
        field_spacing: Fastener spacing in panel interior.
        edge_distance: Minimum distance from panel edge to fastener center.
    """

    edge_spacing: float = 6.0
    field_spacing: float = 12.0
    edge_distance: float = 0.375  # 3/8"


@dataclass
class LayerPlacementRules:
    """Placement rules for a single material layer.

    These rules map directly to parameters already consumed by the
    sheathing generator (stagger_offset, min_piece_width) and extend
    with fastener and orientation information.

    Attributes:
        stagger_pattern: How to offset joints between rows.
        stagger_offset: Offset amount in feet (for RUNNING_BOND).
        min_piece_width: Minimum acceptable panel width in feet.
        orientation: Required panel orientation.
        requires_blocking: Whether panel edges must land on framing.
        fasteners: Optional fastener specification.
        notes: Human-readable installation notes.
    """

    stagger_pattern: StaggerPattern = StaggerPattern.RUNNING_BOND
    stagger_offset: float = 2.0  # feet
    min_piece_width: float = 0.5  # 6 inches
    orientation: PanelOrientation = PanelOrientation.HORIZONTAL
    requires_blocking: bool = False
    fasteners: Optional[FastenerSpec] = None
    notes: str = ""

    def to_sheathing_config(self) -> Dict[str, Any]:
        """Convert to sheathing generator config dict.

        Returns dict keys compatible with SheathingGenerator config:
        stagger_offset and min_piece_width.
        """
        config: Dict[str, Any] = {}
        if self.stagger_pattern == StaggerPattern.RUNNING_BOND:
            config["stagger_offset"] = self.stagger_offset
        else:
            config["stagger_offset"] = 0.0
        config["min_piece_width"] = self.min_piece_width
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "stagger_pattern": self.stagger_pattern.value,
            "stagger_offset": self.stagger_offset,
            "min_piece_width": self.min_piece_width,
            "orientation": self.orientation.value,
            "requires_blocking": self.requires_blocking,
            "fasteners": {
                "edge_spacing": self.fasteners.edge_spacing,
                "field_spacing": self.fasteners.field_spacing,
                "edge_distance": self.fasteners.edge_distance,
            } if self.fasteners else None,
            "notes": self.notes,
        }


# =============================================================================
# Default Rules Catalog
# =============================================================================

# Key: (function, side) tuple -> LayerPlacementRules
# function values: "structure", "substrate", "thermal", "membrane", "finish"
# side values: "exterior", "core", "interior"

RULES_OSB_SHEATHING = LayerPlacementRules(
    stagger_pattern=StaggerPattern.RUNNING_BOND,
    stagger_offset=2.0,  # 2 ft standard per APA E30
    min_piece_width=0.5,  # 6"
    orientation=PanelOrientation.HORIZONTAL,
    requires_blocking=True,
    fasteners=FastenerSpec(edge_spacing=6.0, field_spacing=12.0, edge_distance=0.375),
    notes="APA E30: OSB structural sheathing. Stagger joints min 1 stud bay.",
)

RULES_PLYWOOD_SHEATHING = LayerPlacementRules(
    stagger_pattern=StaggerPattern.RUNNING_BOND,
    stagger_offset=2.0,
    min_piece_width=0.5,
    orientation=PanelOrientation.HORIZONTAL,
    requires_blocking=True,
    fasteners=FastenerSpec(edge_spacing=6.0, field_spacing=12.0, edge_distance=0.375),
    notes="APA E30: Plywood structural sheathing. Same stagger as OSB.",
)

RULES_GYPSUM_BOARD = LayerPlacementRules(
    stagger_pattern=StaggerPattern.RUNNING_BOND,
    stagger_offset=2.0,  # Offset from sheathing joints
    min_piece_width=0.667,  # 8"
    orientation=PanelOrientation.HORIZONTAL,
    requires_blocking=False,
    fasteners=FastenerSpec(edge_spacing=8.0, field_spacing=12.0, edge_distance=0.375),
    notes="GA-216: Gypsum board. Stagger joints from sheathing layer.",
)

RULES_CONTINUOUS_INSULATION = LayerPlacementRules(
    stagger_pattern=StaggerPattern.RUNNING_BOND,
    stagger_offset=2.0,
    min_piece_width=1.0,  # 12"
    orientation=PanelOrientation.ANY,
    requires_blocking=False,
    notes="Continuous insulation. Stagger joints, no gaps allowed.",
)

RULES_WRB_MEMBRANE = LayerPlacementRules(
    stagger_pattern=StaggerPattern.NONE,
    stagger_offset=0.0,
    min_piece_width=3.0,  # Full-width rolls
    orientation=PanelOrientation.HORIZONTAL,
    requires_blocking=False,
    notes="Weather-resistive barrier. Overlap min 6\" horizontal, 12\" vertical.",
)

RULES_EXTERIOR_FINISH = LayerPlacementRules(
    stagger_pattern=StaggerPattern.RUNNING_BOND,
    stagger_offset=1.333,  # 16" (one stud bay)
    min_piece_width=0.5,
    orientation=PanelOrientation.HORIZONTAL,
    requires_blocking=False,
    notes="Exterior finish (lap siding, fiber cement). Stagger by one stud bay.",
)

RULES_DEFAULT = LayerPlacementRules(
    stagger_pattern=StaggerPattern.RUNNING_BOND,
    stagger_offset=2.0,
    min_piece_width=0.5,
    orientation=PanelOrientation.HORIZONTAL,
    notes="Default rules when no specific match found.",
)

# Lookup table: (function, side) -> rules
DEFAULT_RULES: Dict[Tuple[str, str], LayerPlacementRules] = {
    ("substrate", "exterior"): RULES_OSB_SHEATHING,
    ("structure", "core"): RULES_DEFAULT,
    ("thermal", "exterior"): RULES_CONTINUOUS_INSULATION,
    ("membrane", "exterior"): RULES_WRB_MEMBRANE,
    ("finish", "exterior"): RULES_EXTERIOR_FINISH,
    ("finish", "interior"): RULES_GYPSUM_BOARD,
}


def get_rules_for_layer(
    function: str,
    side: str,
    custom_rules: Optional[Dict[Tuple[str, str], LayerPlacementRules]] = None,
) -> LayerPlacementRules:
    """Look up placement rules for a layer by function and side.

    Checks custom rules first (if provided), then DEFAULT_RULES,
    then falls back to RULES_DEFAULT.

    Args:
        function: Layer function ("substrate", "finish", etc.).
        side: Layer side ("exterior", "core", "interior").
        custom_rules: Optional project-specific rules override.

    Returns:
        LayerPlacementRules for the layer.
    """
    key = (function, side)

    if custom_rules and key in custom_rules:
        return custom_rules[key]

    return DEFAULT_RULES.get(key, RULES_DEFAULT)


def get_rules_for_assembly(
    wall_assembly: Dict[str, Any],
    custom_rules: Optional[Dict[Tuple[str, str], LayerPlacementRules]] = None,
) -> Dict[str, LayerPlacementRules]:
    """Get placement rules for every layer in an assembly.

    Args:
        wall_assembly: Assembly dict with "layers" list.
        custom_rules: Optional project-specific rules override.

    Returns:
        Dict mapping layer name to its LayerPlacementRules.
    """
    result: Dict[str, LayerPlacementRules] = {}
    for layer in wall_assembly.get("layers", []):
        name = layer.get("name", "unknown")
        function = layer.get("function", "structure")
        side = layer.get("side", "core")
        result[name] = get_rules_for_layer(function, side, custom_rules)
    return result
