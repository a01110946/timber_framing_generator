# File: timber_framing_generator/config/framing.py

"""
Framing-specific configurations for the Timber Framing Generator.
This module contains all parameters, profiles, and settings related to
timber framing elements.
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional

from src.timber_framing_generator.config.units import ProjectUnits, convert_from_feet


class PlatePosition(Enum):
    """
    Defines the basic position categories for plates in a wall assembly.
    These positions determine how plates stack and reference their elevations.
    """

    BOTTOM = "bottom"  # Plates that reference from wall base elevation
    TOP = "top"  # Plates that reference from wall top elevation


@dataclass
class PlateConfig:
    """
    Configuration for plate positioning relative to reference elevation.

    structural_multiplier: Multiplier for structural representation
    schematic_multiplier: Multiplier for schematic representation
    reference: 'base' or 'top' - which wall elevation to reference from
    """

    structural_multiplier: float
    schematic_multiplier: float
    reference: str


# Configuration map defining plate positioning rules
PLATE_CONFIGS = {
    # Bottom plates: offset direction varies by representation type
    ("bottom", 1): PlateConfig(
        structural_multiplier=0.5,  # Up from base in structural
        schematic_multiplier=-0.5,  # Down from base in schematic
        reference="base",
    ),
    ("bottom", 2): [
        # Bottom plate
        PlateConfig(
            structural_multiplier=0.5, schematic_multiplier=-0.5, reference="base"
        ),
        # Sole plate
        PlateConfig(
            structural_multiplier=1.5, schematic_multiplier=-1.5, reference="base"
        ),
    ],
    # Top plates: always offset down from top
    ("top", 1): PlateConfig(
        structural_multiplier=-0.5,  # Always down from top
        schematic_multiplier=-0.5,  # Same for both representations
        reference="top",
    ),
    ("top", 2): [
        # Cap plate
        PlateConfig(
            structural_multiplier=-0.5, schematic_multiplier=-0.5, reference="top"
        ),
        # Top plate
        PlateConfig(
            structural_multiplier=-1.5, schematic_multiplier=-1.5, reference="top"
        ),
    ],
}


class RepresentationType(Enum):
    """Defines valid representation types for framing elements."""

    STRUCTURAL = "structural"
    SCHEMATIC = "schematic"


class PlateType(Enum):
    """Defines valid plate types."""

    BOTTOM_PLATE = "bottom_plate"
    TOP_PLATE = "top_plate"
    CAP_PLATE = "cap_plate"
    SOLE_PLATE = "sole_plate"


class BlockingPattern(Enum):
    """Defines valid patterns for row blocking installation."""

    INLINE = "inline"       # Blocks at same height across wall
    STAGGERED = "staggered" # Blocks at alternating heights between adjacent stud bays


@dataclass
class ProfileDimensions:
    """
    Stores dimensions for a framing profile.

    This class maintains the fundamental dimensions of lumber profiles used in framing.
    All dimensions are stored internally in feet but can be converted to other units
    as needed through the get_dimensions() method.

    Attributes:
        thickness: The profile's thickness in feet (e.g., 3.5/12 for a 2x4)
        width: The profile's width in feet (e.g., 1.5/12 for a 2x4)
        name: The profile's standard designation (e.g., "2x4")
        description: Human-readable description of the profile

    Example:
        A 2x4 lumber profile would be created as:
        >>> profile = ProfileDimensions(
        ...     thickness=3.5/12,  # 3.5 inches converted to feet
        ...     width=1.5/12,      # 1.5 inches converted to feet
        ...     name="2x4",
        ...     description="Standard 2x4 dimensional lumber"
        ... )
    """

    thickness: float  # In feet
    width: float  # In feet
    name: str
    description: str

    def get_dimensions(
        self, units: ProjectUnits = ProjectUnits.FEET
    ) -> Dict[str, float]:
        """
        Gets the profile dimensions in the requested units.

        This method converts the internally stored dimensions (which are in feet)
        to any supported unit system. This is crucial for interfacing with different
        parts of the system that might expect different units.

        Args:
            units: The desired output units (defaults to feet)
                  Uses ProjectUnits enum from our units configuration

        Returns:
            Dictionary with thickness and width in requested units

        Example:
            >>> profile = ProfileDimensions(3.5/12, 1.5/12, "2x4", "Standard 2x4")
            >>> dims = profile.get_dimensions(ProjectUnits.INCHES)
            >>> print(dims)
            {'thickness': 3.5, 'width': 1.5}
        """
        return {
            "thickness": convert_from_feet(self.thickness, units),
            "width": convert_from_feet(self.width, units),
        }


# Standard framing profiles (dimensions in feet)
# Note: "thickness" is the narrow face (1.5" for all dimensional lumber)
#       "width" is the wide face (varies: 2.5", 3.5", 5.5", 7.25", 9.25", 11.25")
PROFILES: Dict[str, ProfileDimensions] = {
    "2x3": ProfileDimensions(
        thickness=1.5 / 12,  # 1.5 inches in feet
        width=2.5 / 12,      # 2.5 inches in feet
        name="2x3",
        description="2x3 dimensional lumber",
    ),
    "2x4": ProfileDimensions(
        thickness=1.5 / 12,  # 1.5 inches in feet
        width=3.5 / 12,      # 3.5 inches in feet
        name="2x4",
        description="Standard 2x4 dimensional lumber",
    ),
    "2x6": ProfileDimensions(
        thickness=1.5 / 12,  # 1.5 inches in feet
        width=5.5 / 12,      # 5.5 inches in feet
        name="2x6",
        description="Standard 2x6 dimensional lumber",
    ),
    "2x8": ProfileDimensions(
        thickness=1.5 / 12,  # 1.5 inches in feet
        width=7.25 / 12,     # 7.25 inches in feet
        name="2x8",
        description="2x8 dimensional lumber",
    ),
    "2x10": ProfileDimensions(
        thickness=1.5 / 12,  # 1.5 inches in feet
        width=9.25 / 12,     # 9.25 inches in feet
        name="2x10",
        description="2x10 dimensional lumber",
    ),
    "2x12": ProfileDimensions(
        thickness=1.5 / 12,  # 1.5 inches in feet
        width=11.25 / 12,    # 11.25 inches in feet
        name="2x12",
        description="2x12 dimensional lumber",
    ),
}

# Framing parameters (all dimensions in feet)
FRAMING_PARAMS: Dict[str, Any] = {
    # Plate configuration
    "bottom_plate_layers": 1,
    "top_plate_layers": 2,
    # Default dimensions if not specified by profile
    "plate_thickness": 1.5 / 12,  # 3.5 inches in feet
    "plate_width": 3.5 / 12,  # 1.5 inches in feet
    # Stud parameters
    "stud_width": 1.5 / 12,  # 1.5 inches in feet
    "stud_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    "stud_spacing": 16.0 / 12,  # 16 inches in feet
    # King stud parameters
    "king_stud_width": 1.5 / 12,  # 1.5 inches in feet
    "king_stud_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    # Trimmer parameters
    "trimmer_width": 1.5 / 12,  # 1.5 inches in feet
    "trimmer_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    # Header parameters
    "header_height": 7 / 12,  # 7 inches in feet (vertical dimension of header)
    "header_depth": 3.5 / 12,  # 3.5 inches in feet (depth into wall)
    "header_height_above_opening": 0.0,  # 0 inches in feet
    # Cripple parameters
    "cripple_width": 1.5 / 12,  # 1.5 inches in feet
    "cripple_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    "cripple_spacing": 16.0 / 12,  # 16 inches in feet
    "min_cripple_length": 6.0 / 12,  # 6 inches in feet - minimum length for header/sill cripples
    # Sill parameters
    "sill_height": 1.5 / 12,  # 1.5 inches in feet
    "sill_depth": 3.5 / 12,  # 3.5 inches in feet (depth along wall)
    # Offsets and tolerances
    "minimum_stud_spacing": 16.0 / 12,  # 16 inches in feet
    "trimmer_offset": 1.5 / 12 / 2,  # 0.5 inches in feet
    "king_stud_offset": 1.5 / 12 / 2,  # 0.5 inches in feet
    # Validation thresholds
    "minimum_cell_width": 1.5 / 12,  # 1.5 inches in feet
    "minimum_cell_height": 1.5 / 12,  # 1.5 inches in feet
    # Row blocking parameters
    "include_blocking": True,        # Whether to include row blocking
    "block_spacing": 48.0 / 12.0,    # 48 inches (4 feet) in feet
    "first_block_height": 24.0 / 12.0,  # 24 inches (2 feet) from bottom plate
    "block_pattern": BlockingPattern.INLINE,  # Default blocking pattern
    "block_profile_override": None,   # Use same profile as studs by default
    "blocking_row_height_threshold_1": 4.0,  # 4' for a single row of blocking
    "blocking_row_height_threshold_2": 8.0,  # 8' for two rows of blocking
    "blocking_min_height": 1.5,  # Minimum cell height (in feet) required for blocking 
}


# Wall type to profile mapping
WALL_TYPE_PROFILES: Dict[str, str] = {
    # Exterior walls
    "2x4 EXT": "2x4",
    "2x4EXT": "2x4",
    "2x6 EXT": "2x6",
    "2x6EXT": "2x6",
    # Interior walls
    "2x4 INT": "2x4",
    "2x6 INT": "2x6",
}


def get_framing_param(param_name: str, wall_data: Dict[str, Any] = None, default=None):
    """
    Get a framing parameter, checking wall_data first, then FRAMING_PARAMS.

    This allows material-specific strategies to override default parameters
    by setting them in wall_data["framing_config"].

    Args:
        param_name: Name of the parameter (e.g., "stud_width")
        wall_data: Optional wall data dict that may contain framing_config
        default: Default value if not found anywhere

    Returns:
        Parameter value from wall_data["framing_config"], FRAMING_PARAMS, or default
    """
    # Check wall_data first (allows material-specific overrides)
    if wall_data and "framing_config" in wall_data:
        config = wall_data["framing_config"]
        if param_name in config:
            return config[param_name]

    # Fall back to FRAMING_PARAMS
    if param_name in FRAMING_PARAMS:
        return FRAMING_PARAMS[param_name]

    # Use provided default or FRAMING_PARAMS default
    return default if default is not None else FRAMING_PARAMS.get(param_name)


def _thickness_to_profile(thickness: float) -> Optional[str]:
    """
    Map wall thickness (in inches) to lumber profile.

    Uses ranges to handle nominal vs actual dimensions.
    Profiles checked from largest to smallest to find best fit.

    Args:
        thickness: Wall thickness in inches

    Returns:
        Profile name (e.g., "2x4") or None if no match
    """
    # Check from largest to smallest for best match
    # Ranges based on nominal dimensions (e.g., "4" in wall name → 2x4)
    # Boundary at 3.25 ensures "3" maps to 2x3 and "4" maps to 2x4
    if 11.0 <= thickness <= 12.5:
        return "2x12"
    elif 9.0 <= thickness < 11.0:
        return "2x10"
    elif 7.0 <= thickness < 9.0:
        return "2x8"
    elif 5.0 <= thickness < 7.0:
        return "2x6"
    elif 3.25 <= thickness < 5.0:
        return "2x4"
    elif 2.0 <= thickness < 3.25:
        return "2x3"
    return None


def _infer_profile_from_thickness(wall_type: str) -> Optional[str]:
    """
    Infer lumber profile from wall thickness mentioned in the name.

    Looks for patterns like:
    - "4"" or "6"" (with inch mark)
    - "- 4" or "- 6" (thickness at end after dash)
    - "4 inch" or "6 inch"
    - Standalone "4" or "6" as word boundaries

    Args:
        wall_type: Wall type string to parse

    Returns:
        Profile name (e.g., "2x4") or None if no thickness found
    """
    # Pattern: number followed by inch mark or "inch"
    inch_pattern = r'(\d+(?:\.\d+)?)\s*(?:"|inch|in\b)'
    match = re.search(inch_pattern, wall_type, re.IGNORECASE)
    if match:
        thickness = float(match.group(1))
        return _thickness_to_profile(thickness)

    # Pattern: dash followed by number at end (e.g., "W1 - 4")
    dash_pattern = r'-\s*(\d+(?:\.\d+)?)\s*$'
    match = re.search(dash_pattern, wall_type)
    if match:
        thickness = float(match.group(1))
        return _thickness_to_profile(thickness)

    # Pattern: standalone number that could be thickness (3-12 range)
    # Only match common wall thicknesses to avoid false positives
    standalone_pattern = r'\b([3-9]|1[0-2])(?:\.\d+)?\b'
    matches = re.findall(standalone_pattern, wall_type)
    for m in reversed(matches):  # Check from end (thickness often at end)
        thickness = float(m)
        profile = _thickness_to_profile(thickness)
        if profile:
            return profile

    return None


def get_profile_for_wall_type(wall_type: str) -> ProfileDimensions:
    """
    Gets the appropriate profile dimensions for a wall type.

    Handles various naming conventions through multiple fallback strategies:
    1. Exact match in WALL_TYPE_PROFILES
    2. Normalized match (uppercase, no spaces)
    3. Pattern match - look for "2xN" anywhere in string
    4. Thickness extraction from name (e.g., "Basic Wall - W1 - 4" → 2x4)
    5. Raise error with helpful message

    Args:
        wall_type: The wall type identifier. Supports formats like:
            - Standard: "2x4 EXT", "2x6 INT"
            - Revit default: "Basic Wall - W1 - 4", "Generic - 6"
            - With units: "4 inch", '6"'

    Returns:
        ProfileDimensions object with the appropriate dimensions

    Raises:
        KeyError: If wall type cannot be resolved to a known profile
    """
    # 1. Exact match
    profile_name = WALL_TYPE_PROFILES.get(wall_type)
    if profile_name and profile_name in PROFILES:
        return PROFILES[profile_name]

    # 2. Normalized match (uppercase, no spaces)
    normalized = wall_type.strip().upper().replace(" ", "")
    profile_name = WALL_TYPE_PROFILES.get(normalized)
    if profile_name and profile_name in PROFILES:
        return PROFILES[profile_name]

    # 3. Pattern match - look for "2xN" anywhere in string
    # Check from largest to smallest to avoid "2x1" matching in "2x12"
    wall_upper = wall_type.upper()
    for profile in ["2X12", "2X10", "2X8", "2X6", "2X4", "2X3"]:
        if profile in wall_upper:
            profile_lower = profile.lower()  # PROFILES uses lowercase keys
            if profile_lower in PROFILES:
                return PROFILES[profile_lower]

    # 4. Thickness extraction - find numbers that indicate wall thickness
    profile_name = _infer_profile_from_thickness(wall_type)
    if profile_name and profile_name in PROFILES:
        return PROFILES[profile_name]

    # 5. Failed - raise error with helpful message
    raise KeyError(
        f"Cannot determine profile for wall type: '{wall_type}'. "
        f"Add it to WALL_TYPE_PROFILES or use a recognizable format "
        f"(e.g., '2x4', '2x6', or include thickness like '4\"' or '6\"')."
    )


def calculate_plate_offset(
    thickness: float,
    position: PlatePosition,
    layer_count: int,
    layer_index: int,
    representation_type: str,
) -> float:
    """
    Calculate plate offset considering both position and representation type.

    Args:
        thickness: Plate thickness (typically 1.5 inches)
        position: PlatePosition.TOP or PlatePosition.BOTTOM
        layer_count: Number of plate layers (1 or 2)
        layer_index: Which layer in multi-layer system (0 = primary, 1 = secondary)
        representation_type: "structural" or "schematic"

    Returns:
        float: Offset distance from reference elevation
    """
    config = PLATE_CONFIGS[(position.value, layer_count)]

    # Get the appropriate config for single/multi-layer
    if isinstance(config, list):
        plate_config = config[layer_index]
    else:
        plate_config = config

    # Select multiplier based on representation type
    multiplier = (
        plate_config.structural_multiplier
        if representation_type == "structural"
        else plate_config.schematic_multiplier
    )

    return thickness * multiplier
