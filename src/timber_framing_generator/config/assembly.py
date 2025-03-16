# File: timber_framing_generator/config/assembly.py

"""
Wall assembly configuration for the Timber Framing Generator.
This module defines the overall wall system architecture and assembly parameters.
All dimensions are stored in project units (configurable through units.py).
"""

from dataclasses import dataclass
from typing import Dict, Any, Callable
from src.timber_framing_generator.utils.units import (
    ProjectUnits,
    convert_to_feet,
    convert_from_feet,
    get_project_units,
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
