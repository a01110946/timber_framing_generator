# File: src/timber_framing_generator/sheathing/sheathing_profiles.py
"""
Sheathing material profiles and standard panel sizes.

Defines common sheathing materials (plywood, OSB, gypsum) with their
properties and standard panel dimensions.

Usage:
    from src.timber_framing_generator.sheathing.sheathing_profiles import (
        SHEATHING_MATERIALS, PANEL_SIZES, get_sheathing_material
    )
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class SheathingType(Enum):
    """Types of sheathing applications."""
    STRUCTURAL = "structural"       # Shear walls, lateral bracing
    NON_STRUCTURAL = "non_structural"  # Interior partitions
    EXTERIOR = "exterior"           # Weather barrier


@dataclass
class SheathingMaterial:
    """
    Definition of a sheathing material.

    Attributes:
        name: Material identifier (e.g., "structural_plywood_7_16")
        display_name: Human-readable name
        material_type: Base material (plywood, osb, gypsum, etc.)
        thickness_inches: Panel thickness in inches
        sheathing_type: Application type (structural, non-structural, exterior)
        properties: Additional material properties
    """
    name: str
    display_name: str
    material_type: str
    thickness_inches: float
    sheathing_type: SheathingType
    properties: Dict[str, any] = None

    def __post_init__(self):
        if self.properties is None:
            self.properties = {}

    @property
    def thickness_feet(self) -> float:
        """Return thickness in feet."""
        return self.thickness_inches / 12.0


@dataclass
class PanelSize:
    """
    Standard panel dimensions.

    Attributes:
        name: Size identifier (e.g., "4x8")
        width_feet: Panel width in feet
        height_feet: Panel height in feet
    """
    name: str
    width_feet: float
    height_feet: float

    @property
    def width_inches(self) -> float:
        return self.width_feet * 12

    @property
    def height_inches(self) -> float:
        return self.height_feet * 12


# =============================================================================
# Standard Panel Sizes
# =============================================================================

PANEL_SIZES: Dict[str, PanelSize] = {
    "4x8": PanelSize("4x8", 4.0, 8.0),
    "4x9": PanelSize("4x9", 4.0, 9.0),
    "4x10": PanelSize("4x10", 4.0, 10.0),
    "4x12": PanelSize("4x12", 4.0, 12.0),
}

DEFAULT_PANEL_SIZE = "4x8"


# =============================================================================
# Sheathing Materials
# =============================================================================

SHEATHING_MATERIALS: Dict[str, SheathingMaterial] = {
    # Structural Plywood
    "structural_plywood_7_16": SheathingMaterial(
        name="structural_plywood_7_16",
        display_name="Structural Plywood 7/16\"",
        material_type="plywood",
        thickness_inches=7/16,  # 0.4375"
        sheathing_type=SheathingType.STRUCTURAL,
        properties={
            "grade": "CDX",
            "span_rating": "24/16",
            "allowable_shear": 200,  # plf for 8d nails @ 6" edge
        }
    ),
    "structural_plywood_15_32": SheathingMaterial(
        name="structural_plywood_15_32",
        display_name="Structural Plywood 15/32\"",
        material_type="plywood",
        thickness_inches=15/32,  # 0.46875"
        sheathing_type=SheathingType.STRUCTURAL,
        properties={
            "grade": "CDX",
            "span_rating": "32/16",
            "allowable_shear": 255,
        }
    ),
    "structural_plywood_1_2": SheathingMaterial(
        name="structural_plywood_1_2",
        display_name="Structural Plywood 1/2\"",
        material_type="plywood",
        thickness_inches=0.5,
        sheathing_type=SheathingType.STRUCTURAL,
        properties={
            "grade": "CDX",
            "span_rating": "32/16",
            "allowable_shear": 280,
        }
    ),
    "structural_plywood_19_32": SheathingMaterial(
        name="structural_plywood_19_32",
        display_name="Structural Plywood 19/32\"",
        material_type="plywood",
        thickness_inches=19/32,  # 0.59375"
        sheathing_type=SheathingType.STRUCTURAL,
        properties={
            "grade": "CDX",
            "span_rating": "40/20",
            "allowable_shear": 340,
        }
    ),

    # OSB (Oriented Strand Board)
    "osb_7_16": SheathingMaterial(
        name="osb_7_16",
        display_name="OSB 7/16\"",
        material_type="osb",
        thickness_inches=7/16,
        sheathing_type=SheathingType.STRUCTURAL,
        properties={
            "span_rating": "24/16",
            "allowable_shear": 200,
        }
    ),
    "osb_1_2": SheathingMaterial(
        name="osb_1_2",
        display_name="OSB 1/2\"",
        material_type="osb",
        thickness_inches=0.5,
        sheathing_type=SheathingType.STRUCTURAL,
        properties={
            "span_rating": "32/16",
            "allowable_shear": 280,
        }
    ),

    # Gypsum Board (Drywall)
    "gypsum_1_2": SheathingMaterial(
        name="gypsum_1_2",
        display_name="Gypsum Board 1/2\"",
        material_type="gypsum",
        thickness_inches=0.5,
        sheathing_type=SheathingType.NON_STRUCTURAL,
        properties={
            "fire_rating": "Type X",
        }
    ),
    "gypsum_5_8": SheathingMaterial(
        name="gypsum_5_8",
        display_name="Gypsum Board 5/8\"",
        material_type="gypsum",
        thickness_inches=5/8,
        sheathing_type=SheathingType.NON_STRUCTURAL,
        properties={
            "fire_rating": "Type X",
        }
    ),

    # Exterior Sheathing
    "densglass_1_2": SheathingMaterial(
        name="densglass_1_2",
        display_name="DensGlass 1/2\"",
        material_type="glass_mat_gypsum",
        thickness_inches=0.5,
        sheathing_type=SheathingType.EXTERIOR,
        properties={
            "moisture_resistant": True,
            "mold_resistant": True,
        }
    ),
    "densglass_5_8": SheathingMaterial(
        name="densglass_5_8",
        display_name="DensGlass 5/8\"",
        material_type="glass_mat_gypsum",
        thickness_inches=5/8,
        sheathing_type=SheathingType.EXTERIOR,
        properties={
            "moisture_resistant": True,
            "mold_resistant": True,
        }
    ),
}

# Default materials by sheathing type
DEFAULT_MATERIALS: Dict[SheathingType, str] = {
    SheathingType.STRUCTURAL: "structural_plywood_7_16",
    SheathingType.NON_STRUCTURAL: "gypsum_1_2",
    SheathingType.EXTERIOR: "densglass_1_2",
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_sheathing_material(
    material_name: str = None,
    sheathing_type: SheathingType = None
) -> SheathingMaterial:
    """
    Get a sheathing material by name or type.

    Args:
        material_name: Specific material name (e.g., "structural_plywood_7_16")
        sheathing_type: Type of sheathing to get default for

    Returns:
        SheathingMaterial instance

    Raises:
        KeyError: If material name not found
    """
    if material_name:
        if material_name not in SHEATHING_MATERIALS:
            raise KeyError(f"Unknown sheathing material: {material_name}")
        return SHEATHING_MATERIALS[material_name]

    if sheathing_type:
        default_name = DEFAULT_MATERIALS.get(sheathing_type, "structural_plywood_7_16")
        return SHEATHING_MATERIALS[default_name]

    # Return default structural
    return SHEATHING_MATERIALS["structural_plywood_7_16"]


def get_panel_size(size_name: str = None) -> PanelSize:
    """
    Get a panel size by name.

    Args:
        size_name: Panel size name (e.g., "4x8", "4x10")

    Returns:
        PanelSize instance
    """
    if size_name is None:
        size_name = DEFAULT_PANEL_SIZE

    if size_name not in PANEL_SIZES:
        raise KeyError(f"Unknown panel size: {size_name}")

    return PANEL_SIZES[size_name]


def list_materials_by_type(sheathing_type: SheathingType) -> list:
    """
    List all materials of a given sheathing type.

    Args:
        sheathing_type: Type to filter by

    Returns:
        List of material names
    """
    return [
        name for name, mat in SHEATHING_MATERIALS.items()
        if mat.sheathing_type == sheathing_type
    ]
