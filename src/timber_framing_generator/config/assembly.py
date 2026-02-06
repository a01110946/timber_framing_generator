# File: timber_framing_generator/config/assembly.py

"""
Wall assembly configuration for the Timber Framing Generator.
This module defines the overall wall system architecture and assembly parameters.
All dimensions are stored in project units (configurable through units.py).
"""

from dataclasses import dataclass
from typing import Dict, Any, Callable, Optional
from src.timber_framing_generator.utils.units import (
    ProjectUnits,
    convert_to_feet,
    convert_from_feet,
    get_project_units,
)
from src.timber_framing_generator.wall_junctions.junction_types import (
    WallLayer,
    WallAssemblyDef,
    LayerFunction,
    LayerSide,
)


@dataclass
class WallAssembly:
    """Defines the wall assembly configuration with automatic unit conversion."""

    exterior_layer_thickness: float
    core_layer_thickness: float
    interior_layer_thickness: float

    @property
    def total_wall_thickness(self) -> float:
        """Calculates total wall thickness in current project units."""
        return (
            self.exterior_layer_thickness
            + self.core_layer_thickness
            + self.interior_layer_thickness
        )


@dataclass
class OpeningDefaults:
    """Default dimensions for wall openings."""

    rough_width: float
    rough_height: float


# Wall assembly configuration - stored internally in feet
WALL_ASSEMBLY = WallAssembly(
    exterior_layer_thickness=convert_to_feet(0.75, "inches"),
    core_layer_thickness=convert_to_feet(3.5, "inches"),
    interior_layer_thickness=convert_to_feet(0.5, "inches"),
)

# Sheathing parameters
SHEATHING_PARAMS = {
    "sheathing_thickness": convert_to_feet(0.5, "inches"),
    "insulation_thickness": convert_to_feet(3.5, "inches"),
    "finish_thickness": convert_to_feet(0.5, "inches"),
}

# Opening defaults configuration
OPENING_DEFAULTS = {
    "door": OpeningDefaults(
        rough_width=convert_to_feet(30.0, "inches"),
        rough_height=convert_to_feet(80.0, "inches"),
    ),
    "window": OpeningDefaults(
        rough_width=convert_to_feet(36.0, "inches"),
        rough_height=convert_to_feet(48.0, "inches"),
    ),
}


def get_assembly_dimensions(units: ProjectUnits = None) -> Dict[str, float]:
    """
    Gets all assembly dimensions in the specified units.
    If no units specified, uses current project units.
    """
    if units is None:
        units = get_project_units()

    return {
        "exterior_layer": convert_from_feet(
            WALL_ASSEMBLY.exterior_layer_thickness, units
        ),
        "core_layer": convert_from_feet(WALL_ASSEMBLY.core_layer_thickness, units),
        "interior_layer": convert_from_feet(
            WALL_ASSEMBLY.interior_layer_thickness, units
        ),
        "total_thickness": convert_from_feet(WALL_ASSEMBLY.total_wall_thickness, units),
    }


# =============================================================================
# Multi-Layer Assembly Catalog
# =============================================================================

# Standard 2x4 exterior wall (outside to inside)
ASSEMBLY_2X4_EXTERIOR = WallAssemblyDef(
    name="2x4_exterior",
    layers=[
        WallLayer(
            "exterior_finish", LayerFunction.FINISH, LayerSide.EXTERIOR,
            thickness=convert_to_feet(0.5, "inches"),
            material="Lap Siding", priority=10,
        ),
        WallLayer(
            "structural_sheathing", LayerFunction.SUBSTRATE, LayerSide.EXTERIOR,
            thickness=convert_to_feet(0.4375, "inches"),
            material="OSB 7/16", priority=80,
        ),
        WallLayer(
            "framing_core", LayerFunction.STRUCTURE, LayerSide.CORE,
            thickness=convert_to_feet(3.5, "inches"),
            material="2x4 SPF @ 16\" OC", priority=100,
        ),
        WallLayer(
            "interior_finish", LayerFunction.FINISH, LayerSide.INTERIOR,
            thickness=convert_to_feet(0.5, "inches"),
            material="1/2\" Gypsum Board", priority=10,
        ),
    ],
    source="default",
)

# Standard 2x6 exterior wall (outside to inside)
ASSEMBLY_2X6_EXTERIOR = WallAssemblyDef(
    name="2x6_exterior",
    layers=[
        WallLayer(
            "exterior_finish", LayerFunction.FINISH, LayerSide.EXTERIOR,
            thickness=convert_to_feet(0.625, "inches"),
            material="Fiber Cement Siding", priority=10,
        ),
        WallLayer(
            "structural_sheathing", LayerFunction.SUBSTRATE, LayerSide.EXTERIOR,
            thickness=convert_to_feet(0.5, "inches"),
            material="OSB 1/2", priority=80,
        ),
        WallLayer(
            "framing_core", LayerFunction.STRUCTURE, LayerSide.CORE,
            thickness=convert_to_feet(5.5, "inches"),
            material="2x6 SPF @ 16\" OC", priority=100,
        ),
        WallLayer(
            "interior_finish", LayerFunction.FINISH, LayerSide.INTERIOR,
            thickness=convert_to_feet(0.5, "inches"),
            material="1/2\" Gypsum Board", priority=10,
        ),
    ],
    source="default",
)

# Interior partition wall (gypsum on both sides)
ASSEMBLY_2X4_INTERIOR = WallAssemblyDef(
    name="2x4_interior",
    layers=[
        WallLayer(
            "finish_a", LayerFunction.FINISH, LayerSide.EXTERIOR,
            thickness=convert_to_feet(0.5, "inches"),
            material="1/2\" Gypsum Board", priority=10,
        ),
        WallLayer(
            "framing_core", LayerFunction.STRUCTURE, LayerSide.CORE,
            thickness=convert_to_feet(3.5, "inches"),
            material="2x4 SPF @ 16\" OC", priority=100,
        ),
        WallLayer(
            "finish_b", LayerFunction.FINISH, LayerSide.INTERIOR,
            thickness=convert_to_feet(0.5, "inches"),
            material="1/2\" Gypsum Board", priority=10,
        ),
    ],
    source="default",
)

# Assembly catalog for lookup
WALL_ASSEMBLIES: Dict[str, WallAssemblyDef] = {
    "2x4_exterior": ASSEMBLY_2X4_EXTERIOR,
    "2x6_exterior": ASSEMBLY_2X6_EXTERIOR,
    "2x4_interior": ASSEMBLY_2X4_INTERIOR,
}


def get_assembly_for_wall(wall_data: Dict) -> WallAssemblyDef:
    """Get the appropriate assembly for a wall.

    Lookup order:
    1. wall_data["wall_assembly"] if present (deserialized WallAssemblyDef)
    2. WALL_ASSEMBLIES[wall_data["wall_type"]] if wall_type matches catalog
    3. ASSEMBLY_2X4_EXTERIOR if is_exterior
    4. ASSEMBLY_2X4_INTERIOR otherwise

    Args:
        wall_data: Wall dictionary from walls_json.

    Returns:
        WallAssemblyDef for the wall.
    """
    # Check wall type catalog
    wall_type = wall_data.get("wall_type", "")
    if wall_type in WALL_ASSEMBLIES:
        return WALL_ASSEMBLIES[wall_type]

    # Default by exterior/interior
    is_exterior = wall_data.get("is_exterior", False)
    return ASSEMBLY_2X4_EXTERIOR if is_exterior else ASSEMBLY_2X4_INTERIOR
