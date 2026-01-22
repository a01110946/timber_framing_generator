# File: src/timber_framing_generator/materials/timber/timber_profiles.py
"""
Standard lumber profiles for timber framing.

This module defines standard dimensional lumber profiles used in
timber wall framing. All dimensions are stored in FEET.

Lumber Naming Convention:
    - Nominal size (e.g., "2x4") refers to rough-cut dimensions
    - Actual size is smaller after drying and planing
    - 2x4 actual: 1.5" x 3.5" = 0.125' x 0.292'

Profile Orientation:
    - width: Through wall thickness (W direction in UVW)
    - depth: Along wall face (U direction for studs, V for plates)

Usage:
    from src.timber_framing_generator.materials.timber.timber_profiles import (
        TIMBER_PROFILES, get_timber_profile
    )

    profile = TIMBER_PROFILES["2x4"]
    stud_profile = get_timber_profile(ElementType.STUD)
"""

from typing import Dict

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    ElementProfile,
    ElementType,
)


# =============================================================================
# Standard Lumber Profiles
# =============================================================================

# All dimensions in FEET
# Actual lumber dimensions (after drying/planing):
#   Nominal 2x  → Actual 1.5" = 0.125'
#   Nominal x4  → Actual 3.5" = 0.2917'
#   Nominal x6  → Actual 5.5" = 0.4583'
#   Nominal x8  → Actual 7.25" = 0.6042'
#   Nominal x10 → Actual 9.25" = 0.7708'
#   Nominal x12 → Actual 11.25" = 0.9375'

TIMBER_PROFILES: Dict[str, ElementProfile] = {
    "2x4": ElementProfile(
        name="2x4",
        width=1.5 / 12,      # 1.5 inches = 0.125 feet (through wall)
        depth=3.5 / 12,      # 3.5 inches = 0.2917 feet (along wall face)
        material_system=MaterialSystem.TIMBER,
        properties={
            "nominal": "2x4",
            "actual_inches": (1.5, 3.5),
            "grade": "SPF #2",
        }
    ),
    "2x6": ElementProfile(
        name="2x6",
        width=1.5 / 12,      # 1.5 inches = 0.125 feet
        depth=5.5 / 12,      # 5.5 inches = 0.4583 feet
        material_system=MaterialSystem.TIMBER,
        properties={
            "nominal": "2x6",
            "actual_inches": (1.5, 5.5),
            "grade": "SPF #2",
        }
    ),
    "2x8": ElementProfile(
        name="2x8",
        width=1.5 / 12,      # 1.5 inches = 0.125 feet
        depth=7.25 / 12,     # 7.25 inches = 0.6042 feet
        material_system=MaterialSystem.TIMBER,
        properties={
            "nominal": "2x8",
            "actual_inches": (1.5, 7.25),
            "grade": "SPF #2",
        }
    ),
    "2x10": ElementProfile(
        name="2x10",
        width=1.5 / 12,      # 1.5 inches = 0.125 feet
        depth=9.25 / 12,     # 9.25 inches = 0.7708 feet
        material_system=MaterialSystem.TIMBER,
        properties={
            "nominal": "2x10",
            "actual_inches": (1.5, 9.25),
            "grade": "SPF #2",
        }
    ),
    "2x12": ElementProfile(
        name="2x12",
        width=1.5 / 12,      # 1.5 inches = 0.125 feet
        depth=11.25 / 12,    # 11.25 inches = 0.9375 feet
        material_system=MaterialSystem.TIMBER,
        properties={
            "nominal": "2x12",
            "actual_inches": (1.5, 11.25),
            "grade": "SPF #2",
        }
    ),
}


# =============================================================================
# Default Profile Assignments
# =============================================================================

# Maps element types to their default lumber profile
# These can be overridden by configuration
DEFAULT_TIMBER_PROFILES: Dict[ElementType, str] = {
    # Horizontal members (plates)
    ElementType.BOTTOM_PLATE: "2x4",
    ElementType.TOP_PLATE: "2x4",

    # Vertical members
    ElementType.STUD: "2x4",
    ElementType.KING_STUD: "2x4",
    ElementType.TRIMMER: "2x4",

    # Opening components
    ElementType.HEADER: "2x6",       # Headers often larger for load bearing
    ElementType.SILL: "2x4",
    ElementType.HEADER_CRIPPLE: "2x4",
    ElementType.SILL_CRIPPLE: "2x4",

    # Bracing
    ElementType.ROW_BLOCKING: "2x4",
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_timber_profile(
    element_type: ElementType,
    profile_override: str = None
) -> ElementProfile:
    """
    Get the lumber profile for a specific element type.

    Args:
        element_type: The type of framing element
        profile_override: Optional profile name to use instead of default

    Returns:
        ElementProfile for the requested element type

    Raises:
        KeyError: If the profile name is not found

    Example:
        >>> profile = get_timber_profile(ElementType.STUD)
        >>> print(profile.name)
        '2x4'
        >>> profile = get_timber_profile(ElementType.HEADER, "2x8")
        >>> print(profile.name)
        '2x8'
    """
    if profile_override:
        if profile_override not in TIMBER_PROFILES:
            raise KeyError(f"Unknown timber profile: {profile_override}")
        return TIMBER_PROFILES[profile_override]

    # Get default profile for this element type
    profile_name = DEFAULT_TIMBER_PROFILES.get(element_type, "2x4")
    return TIMBER_PROFILES[profile_name]


def list_available_profiles() -> list:
    """
    List all available timber profile names.

    Returns:
        List of profile name strings (e.g., ["2x4", "2x6", ...])
    """
    return list(TIMBER_PROFILES.keys())
