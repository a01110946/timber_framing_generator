# File: src/timber_framing_generator/materials/cfs/cfs_profiles.py
"""
Standard CFS (Cold-Formed Steel) profiles for steel stud framing.

This module defines standard CFS profiles used in light-gauge steel
wall framing. All dimensions are stored in FEET.

CFS Naming Convention:
    600S162-54
    │   │   │
    │   │   └── Gauge (54 mil = 0.054")
    │   └────── Flange width (1.62" for studs, 1.25" for tracks)
    └────────── Web depth (6.00")

    S = Stud (C-section with lips)
    T = Track (C-section without lips, used for top/bottom)

Profile Orientation:
    - width: Flange width (through wall thickness, W direction in UVW)
    - depth: Web depth (along wall face, U direction for studs)

Usage:
    from src.timber_framing_generator.materials.cfs.cfs_profiles import (
        CFS_PROFILES, get_cfs_profile
    )

    profile = CFS_PROFILES["350S162-54"]
    track_profile = get_cfs_profile(ElementType.BOTTOM_PLATE)
"""

from typing import Dict

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    ElementProfile,
    ElementType,
)


# =============================================================================
# Standard CFS Profiles
# =============================================================================

# All dimensions in FEET
# Standard steel gauges:
#   33 mil = 0.033" = 20 gauge
#   43 mil = 0.043" = 18 gauge
#   54 mil = 0.054" = 16 gauge
#   68 mil = 0.068" = 14 gauge
#   97 mil = 0.097" = 12 gauge

CFS_PROFILES: Dict[str, ElementProfile] = {
    # =========================================================================
    # STUDS (C-sections with lips)
    # =========================================================================

    # 3.5" web studs (equivalent to 2x4 wall)
    "350S162-33": ElementProfile(
        name="350S162-33",
        width=1.62 / 12,     # Flange width: 1.62" = 0.135 feet
        depth=3.5 / 12,      # Web depth: 3.5" = 0.292 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.62,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "350S162-43": ElementProfile(
        name="350S162-43",
        width=1.62 / 12,
        depth=3.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.62,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "350S162-54": ElementProfile(
        name="350S162-54",
        width=1.62 / 12,
        depth=3.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.62,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),

    # 6" web studs (equivalent to 2x6 wall)
    "600S162-33": ElementProfile(
        name="600S162-33",
        width=1.62 / 12,
        depth=6.0 / 12,      # Web depth: 6.0" = 0.5 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.62,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "600S162-43": ElementProfile(
        name="600S162-43",
        width=1.62 / 12,
        depth=6.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.62,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "600S162-54": ElementProfile(
        name="600S162-54",
        width=1.62 / 12,
        depth=6.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.62,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "600S162-68": ElementProfile(
        name="600S162-68",
        width=1.62 / 12,
        depth=6.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.62,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),

    # 8" web studs (deeper walls)
    "800S162-54": ElementProfile(
        name="800S162-54",
        width=1.62 / 12,
        depth=8.0 / 12,      # Web depth: 8.0" = 0.667 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 8.0,
            "flange_width_inches": 1.62,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "800S162-68": ElementProfile(
        name="800S162-68",
        width=1.62 / 12,
        depth=8.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 8.0,
            "flange_width_inches": 1.62,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),

    # =========================================================================
    # TRACKS (C-sections without lips, for top/bottom)
    # =========================================================================

    # 3.5" web tracks
    "350T125-33": ElementProfile(
        name="350T125-33",
        width=1.25 / 12,     # Flange width: 1.25" = 0.104 feet
        depth=3.5 / 12,      # Web depth: 3.5" = 0.292 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.25,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": False,
        }
    ),
    "350T125-43": ElementProfile(
        name="350T125-43",
        width=1.25 / 12,
        depth=3.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.25,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": False,
        }
    ),
    "350T125-54": ElementProfile(
        name="350T125-54",
        width=1.25 / 12,
        depth=3.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.5,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
        }
    ),

    # 6" web tracks
    "600T125-33": ElementProfile(
        name="600T125-33",
        width=1.25 / 12,
        depth=6.0 / 12,      # Web depth: 6.0" = 0.5 feet
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.25,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": False,
        }
    ),
    "600T125-43": ElementProfile(
        name="600T125-43",
        width=1.25 / 12,
        depth=6.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.25,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": False,
        }
    ),
    "600T125-54": ElementProfile(
        name="600T125-54",
        width=1.25 / 12,
        depth=6.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 6.0,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
        }
    ),

    # 8" web tracks
    "800T125-54": ElementProfile(
        name="800T125-54",
        width=1.25 / 12,
        depth=8.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 8.0,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
        }
    ),
    "800T125-68": ElementProfile(
        name="800T125-68",
        width=1.25 / 12,
        depth=8.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 8.0,
            "flange_width_inches": 1.25,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": False,
        }
    ),
}


# =============================================================================
# Default Profile Assignments
# =============================================================================

# Maps element types to their default CFS profile
# Uses 3.5" (350) profiles as default, matching typical 2x4 wall equivalence
DEFAULT_CFS_PROFILES: Dict[ElementType, str] = {
    # Tracks for horizontal members (plates)
    ElementType.BOTTOM_PLATE: "350T125-54",   # Bottom track
    ElementType.TOP_PLATE: "350T125-54",      # Top track

    # Studs for vertical members
    ElementType.STUD: "350S162-54",
    ElementType.KING_STUD: "350S162-54",
    ElementType.TRIMMER: "350S162-54",

    # Opening components
    ElementType.HEADER: "600S162-54",         # Deeper studs for headers
    ElementType.SILL: "350S162-54",
    ElementType.HEADER_CRIPPLE: "350S162-54",
    ElementType.SILL_CRIPPLE: "350S162-54",

    # Bracing (bridging in CFS terminology)
    ElementType.ROW_BLOCKING: "350S162-54",
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_cfs_profile(
    element_type: ElementType,
    profile_override: str = None
) -> ElementProfile:
    """
    Get the CFS profile for a specific element type.

    Args:
        element_type: The type of framing element
        profile_override: Optional profile name to use instead of default

    Returns:
        ElementProfile for the requested element type

    Raises:
        KeyError: If the profile name is not found

    Example:
        >>> profile = get_cfs_profile(ElementType.STUD)
        >>> print(profile.name)
        '350S162-54'
        >>> profile = get_cfs_profile(ElementType.HEADER, "800S162-68")
        >>> print(profile.name)
        '800S162-68'
    """
    if profile_override:
        if profile_override not in CFS_PROFILES:
            raise KeyError(f"Unknown CFS profile: {profile_override}")
        return CFS_PROFILES[profile_override]

    # Get default profile for this element type
    profile_name = DEFAULT_CFS_PROFILES.get(element_type, "350S162-54")
    return CFS_PROFILES[profile_name]


def list_available_profiles() -> list:
    """
    List all available CFS profile names.

    Returns:
        List of profile name strings (e.g., ["350S162-54", "600T125-43", ...])
    """
    return list(CFS_PROFILES.keys())


def get_stud_profiles() -> Dict[str, ElementProfile]:
    """
    Get only stud profiles (C-sections with lips).

    Returns:
        Dict of stud profiles
    """
    return {
        name: profile
        for name, profile in CFS_PROFILES.items()
        if profile.properties.get("profile_type") == "stud"
    }


def get_track_profiles() -> Dict[str, ElementProfile]:
    """
    Get only track profiles (C-sections without lips).

    Returns:
        Dict of track profiles
    """
    return {
        name: profile
        for name, profile in CFS_PROFILES.items()
        if profile.properties.get("profile_type") == "track"
    }
