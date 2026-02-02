# File: src/timber_framing_generator/materials/cfs/cfs_profiles.py
"""
Standard CFS (Cold-Formed Steel) profiles for steel stud framing.

This module defines standard CFS profiles used in light-gauge steel
wall framing. All dimensions are stored in FEET.

CFS Naming Convention:
    600S162-54
    │   │   │
    │   │   └── Gauge (54 mil = 0.054")
    │   └────── Flange width (162 = 1.62", 125 = 1.25", 250 = 2.50")
    └────────── Web depth (600 = 6.00")

    S = Stud (C-section with lips)
    T = Track (C-section without lips, used for top/bottom)

Flange Width Variants:
    S125 / T125 = 1.25" flange - Standard wall studs, bottom tracks
    S162 / T162 = 1.62" flange - Structural/joist applications
    S200 / T200 = 2.00" flange - Sill tracks
    S250 / T250 = 2.50" flange - Top tracks, load-bearing studs

Profile Dimensions:
    CFS profiles store actual CFS dimensions:
    - width: Flange width (visible edge when installed)
    - depth: Web depth (wall thickness direction)

    The properties dict contains detailed dimensions for reference.

Usage:
    from src.timber_framing_generator.materials.cfs.cfs_profiles import (
        CFS_PROFILES, get_cfs_profile
    )

    profile = CFS_PROFILES["362S125-54"]
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
# Standard steel gauges (per ASTM A653):
#   18 mil = 0.018" = 25 gauge
#   27 mil = 0.027" = 22 gauge
#   33 mil = 0.033" = 20 gauge (Fy = 33 ksi)
#   43 mil = 0.043" = 18 gauge (Fy = 33 ksi)
#   54 mil = 0.054" = 16 gauge (Fy = 50 ksi)
#   68 mil = 0.068" = 14 gauge (Fy = 50 ksi)
#   97 mil = 0.097" = 12 gauge (Fy = 50 ksi)

CFS_PROFILES: Dict[str, ElementProfile] = {
    # =========================================================================
    # STUDS - S162 FLANGE (1.62" - Structural/Joist Applications)
    # =========================================================================

    # 3.5" web studs (350 series)
    "350S162-33": ElementProfile(
        name="350S162-33",
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=3.5 / 12,      # Web depth: 3.5" = wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=3.5 / 12,      # Web depth = wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=3.5 / 12,      # Web depth = wall thickness
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

    # 3.625" web studs (362-series, common Clark Dietrich size)
    "362S162-33": ElementProfile(
        name="362S162-33",
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=3.625 / 12,    # Web depth: 3.625"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.62,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "362S162-43": ElementProfile(
        name="362S162-43",
        width=1.62 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.62,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": True,
            "lip_depth_inches": 0.5,
        }
    ),
    "362S162-54": ElementProfile(
        name="362S162-54",
        width=1.62 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=5.5 / 12,      # 2x6 equivalent wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=5.5 / 12,      # 2x6 equivalent wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=5.5 / 12,      # 2x6 equivalent wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=5.5 / 12,      # 2x6 equivalent wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=7.25 / 12,     # 2x8 equivalent wall thickness
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
        width=1.62 / 12,     # Actual CFS flange width (1.62")
        depth=7.25 / 12,     # 2x8 equivalent wall thickness
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
    # STUDS - S125 FLANGE (1.25" - Standard Wall Studs)
    # =========================================================================

    # 3 5/8" web studs (362 series, S125 flange) - Non-bearing partitions
    "362S125-33": ElementProfile(
        name="362S125-33",
        width=1.25 / 12,     # Flange width: 1.25"
        depth=3.625 / 12,    # Web depth: 3 5/8"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 33,
            "wall_type": "non-bearing",
        }
    ),
    "362S125-43": ElementProfile(
        name="362S125-43",
        width=1.25 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 33,
            "wall_type": "non-bearing",
        }
    ),
    "362S125-54": ElementProfile(
        name="362S125-54",
        width=1.25 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "non-bearing",
        }
    ),
    "362S125-68": ElementProfile(
        name="362S125-68",
        width=1.25 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "sill_track",
        }
    ),
    # 362S162-68: Load-bearing stud with wider flange (1.62")
    "362S162-68": ElementProfile(
        name="362S162-68",
        width=1.62 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.62,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "load_bearing",
        }
    ),
    # 362T125-68: Load-bearing bottom track (68 mil)
    "362T125-68": ElementProfile(
        name="362T125-68",
        width=1.25 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": False,
            "fy_ksi": 50,
            "wall_type": "load_bearing",
        }
    ),
    # 362T250-68: Load-bearing top track (68 mil, wider flange)
    "362T250-68": ElementProfile(
        name="362T250-68",
        width=2.50 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.625,
            "flange_width_inches": 2.50,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": False,
            "fy_ksi": 50,
            "wall_type": "load_bearing",
        }
    ),

    # 4" web studs (400 series, S125 flange) - Non-bearing partitions
    "400S125-33": ElementProfile(
        name="400S125-33",
        width=1.25 / 12,     # Flange width: 1.25"
        depth=4.0 / 12,      # Web depth: 4"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 4.0,
            "flange_width_inches": 1.25,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 33,
            "wall_type": "non-bearing",
        }
    ),
    "400S125-43": ElementProfile(
        name="400S125-43",
        width=1.25 / 12,
        depth=4.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 4.0,
            "flange_width_inches": 1.25,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 33,
            "wall_type": "non-bearing",
        }
    ),
    "400S125-54": ElementProfile(
        name="400S125-54",
        width=1.25 / 12,
        depth=4.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 4.0,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "non-bearing",
        }
    ),
    "400S125-68": ElementProfile(
        name="400S125-68",
        width=1.25 / 12,
        depth=4.0 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 4.0,
            "flange_width_inches": 1.25,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "sill_track",
        }
    ),

    # 5 1/2" web studs (550 series, S125 flange) - Non-bearing partitions
    "550S125-33": ElementProfile(
        name="550S125-33",
        width=1.25 / 12,     # Flange width: 1.25"
        depth=5.5 / 12,      # Web depth: 5 1/2"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 5.5,
            "flange_width_inches": 1.25,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 33,
            "wall_type": "non-bearing",
        }
    ),
    "550S125-43": ElementProfile(
        name="550S125-43",
        width=1.25 / 12,
        depth=5.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 5.5,
            "flange_width_inches": 1.25,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 33,
            "wall_type": "non-bearing",
        }
    ),
    "550S125-54": ElementProfile(
        name="550S125-54",
        width=1.25 / 12,
        depth=5.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 5.5,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "non-bearing",
        }
    ),
    "550S125-68": ElementProfile(
        name="550S125-68",
        width=1.25 / 12,
        depth=5.5 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 5.5,
            "flange_width_inches": 1.25,
            "gauge": 68,
            "thickness_mils": 68,
            "has_lips": True,
            "lip_depth_inches": 0.5,
            "fy_ksi": 50,
            "wall_type": "sill_track",
        }
    ),

    # =========================================================================
    # STUDS - S250 FLANGE (2.50" - Load-Bearing Applications)
    # =========================================================================

    # 5 1/2" web studs (550 series, S250 flange) - Load-bearing walls
    "550S250-97": ElementProfile(
        name="550S250-97",
        width=2.5 / 12,      # Flange width: 2 1/2"
        depth=5.5 / 12,      # Web depth: 5 1/2"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "stud",
            "web_depth_inches": 5.5,
            "flange_width_inches": 2.5,
            "gauge": 97,
            "thickness_mils": 97,
            "has_lips": True,
            "lip_depth_inches": 0.625,
            "fy_ksi": 50,
            "wall_type": "load-bearing",
        }
    ),

    # =========================================================================
    # TRACKS - T125 FLANGE (1.25" - Bottom Tracks)
    # =========================================================================

    # 3.5" web tracks (for horizontal members, flange is vertical height)
    "350T125-33": ElementProfile(
        name="350T125-33",
        width=1.25 / 12,     # Flange width: 1.25" = track height (vertical)
        depth=3.5 / 12,      # Web depth: 3.5" = wall thickness
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
        width=1.25 / 12,     # Flange width = track height
        depth=3.5 / 12,      # Web depth = wall thickness
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
        width=1.25 / 12,     # Flange width = track height
        depth=3.5 / 12,      # Web depth = wall thickness
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

    # 3.625" web tracks (362-series, common Clark Dietrich size)
    "362T125-33": ElementProfile(
        name="362T125-33",
        width=1.25 / 12,     # Flange width: 1.25" = track height
        depth=3.625 / 12,    # Web depth: 3.625"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 33,
            "thickness_mils": 33,
            "has_lips": False,
        }
    ),
    "362T125-43": ElementProfile(
        name="362T125-43",
        width=1.25 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 43,
            "thickness_mils": 43,
            "has_lips": False,
        }
    ),
    "362T125-54": ElementProfile(
        name="362T125-54",
        width=1.25 / 12,
        depth=3.625 / 12,
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.625,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "bottom",
        }
    ),

    # 4" web tracks (400 series, T125 flange) - Bottom tracks
    "400T125-54": ElementProfile(
        name="400T125-54",
        width=1.25 / 12,     # Flange width: 1.25"
        depth=4.0 / 12,      # Web depth: 4"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 4.0,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "bottom",
        }
    ),

    # 5 1/2" web tracks (550 series, T125 flange) - Bottom tracks
    "550T125-54": ElementProfile(
        name="550T125-54",
        width=1.25 / 12,     # Flange width: 1.25"
        depth=5.5 / 12,      # Web depth: 5 1/2"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 5.5,
            "flange_width_inches": 1.25,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "bottom",
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

    # =========================================================================
    # TRACKS - T200 FLANGE (2.00" - Sill Tracks)
    # =========================================================================

    # 5 1/2" web tracks (550 series, T200 flange) - Sill tracks for load-bearing
    "550T200-54": ElementProfile(
        name="550T200-54",
        width=2.0 / 12,      # Flange width: 2"
        depth=5.5 / 12,      # Web depth: 5 1/2"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 5.5,
            "flange_width_inches": 2.0,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "sill",
        }
    ),

    # =========================================================================
    # TRACKS - T250 FLANGE (2.50" - Top Tracks)
    # =========================================================================

    # 3 5/8" web tracks (362 series, T250 flange) - Top tracks
    "362T250-54": ElementProfile(
        name="362T250-54",
        width=2.5 / 12,      # Flange width: 2 1/2"
        depth=3.625 / 12,    # Web depth: 3 5/8"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 3.625,
            "flange_width_inches": 2.5,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "top",
        }
    ),

    # 4" web tracks (400 series, T250 flange) - Top tracks
    "400T250-54": ElementProfile(
        name="400T250-54",
        width=2.5 / 12,      # Flange width: 2 1/2"
        depth=4.0 / 12,      # Web depth: 4"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 4.0,
            "flange_width_inches": 2.5,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "top",
        }
    ),

    # 5 1/2" web tracks (550 series, T250 flange) - Top tracks
    "550T250-54": ElementProfile(
        name="550T250-54",
        width=2.5 / 12,      # Flange width: 2 1/2"
        depth=5.5 / 12,      # Web depth: 5 1/2"
        material_system=MaterialSystem.CFS,
        properties={
            "profile_type": "track",
            "web_depth_inches": 5.5,
            "flange_width_inches": 2.5,
            "gauge": 54,
            "thickness_mils": 54,
            "has_lips": False,
            "track_type": "top",
        }
    ),
}


# =============================================================================
# Default Profile Assignments
# =============================================================================

# Maps element types to their default CFS profile for NON-BEARING walls
# Uses 362 series (3 5/8") with S125 flange, 54 mil gauge
DEFAULT_CFS_PROFILES: Dict[ElementType, str] = {
    # Tracks for horizontal members (plates)
    ElementType.BOTTOM_PLATE: "362T125-54",   # Bottom track (T125 = 1.25" flange)
    ElementType.TOP_PLATE: "362T250-54",      # Top track (T250 = 2.5" flange)

    # Studs for vertical members (S125 = standard wall studs)
    ElementType.STUD: "362S125-54",
    ElementType.KING_STUD: "362S125-54",
    ElementType.TRIMMER: "362S125-54",

    # Opening components
    ElementType.HEADER: "600S162-54",         # Headers use deeper S162 profiles
    ElementType.SILL: "362S125-54",
    ElementType.HEADER_CRIPPLE: "362S125-54",
    ElementType.SILL_CRIPPLE: "362S125-54",

    # Bracing (bridging in CFS terminology)
    ElementType.ROW_BLOCKING: "362S125-54",
}

# Maps element types to their default CFS profile for LOAD-BEARING walls
# Uses 362 series (3 5/8") with S162 flange, 68 mil gauge (thicker for structural)
DEFAULT_CFS_PROFILES_LOAD_BEARING: Dict[ElementType, str] = {
    # Tracks for horizontal members - thicker gauge for load transfer
    ElementType.BOTTOM_PLATE: "362T125-68",   # Bottom track (68 mil gauge)
    ElementType.TOP_PLATE: "362T250-68",      # Top track (68 mil gauge)

    # Studs for vertical members - S162 flange for better load capacity
    ElementType.STUD: "362S162-68",
    ElementType.KING_STUD: "362S162-68",
    ElementType.TRIMMER: "362S162-68",

    # Opening components - structural grade
    ElementType.HEADER: "600S162-68",         # Headers use deeper profiles, 68 mil
    ElementType.SILL: "362S162-68",
    ElementType.HEADER_CRIPPLE: "362S162-68",
    ElementType.SILL_CRIPPLE: "362S162-68",

    # Bracing (bridging in CFS terminology)
    ElementType.ROW_BLOCKING: "362S162-68",
}

# =============================================================================
# Profile Selection by Wall Width
# =============================================================================

# Maps wall width (inches) to profile series
WALL_WIDTH_TO_SERIES: Dict[float, str] = {
    3.5: "350",      # 3 1/2" walls
    3.625: "362",    # 3 5/8" walls
    4.0: "400",      # 4" walls
    5.5: "550",      # 5 1/2" walls
    6.0: "600",      # 6" walls
    8.0: "800",      # 8" walls
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_series_for_wall_thickness(wall_thickness_inches: float) -> str:
    """
    Get the appropriate CFS series for a given wall thickness.

    Args:
        wall_thickness_inches: Wall thickness in inches

    Returns:
        Series string (e.g., "600" for 6" walls)
    """
    # Find the closest matching series
    best_series = "362"  # Default fallback
    best_diff = float('inf')

    for width, series in WALL_WIDTH_TO_SERIES.items():
        diff = abs(width - wall_thickness_inches)
        if diff < best_diff:
            best_diff = diff
            best_series = series

    return best_series


def get_cfs_profile(
    element_type: ElementType,
    profile_override: str = None,
    wall_thickness_inches: float = None,
    is_load_bearing: bool = False
) -> ElementProfile:
    """
    Get the CFS profile for a specific element type.

    Args:
        element_type: The type of framing element
        profile_override: Optional profile name to use instead of default
        wall_thickness_inches: Optional wall thickness to select appropriate series
        is_load_bearing: Whether wall is load-bearing (uses thicker gauge profiles)

    Returns:
        ElementProfile for the requested element type

    Raises:
        KeyError: If the profile name is not found

    Example:
        >>> profile = get_cfs_profile(ElementType.STUD)
        >>> print(profile.name)
        '362S125-54'
        >>> profile = get_cfs_profile(ElementType.STUD, wall_thickness_inches=6.0)
        >>> print(profile.name)
        '600S125-54'
        >>> profile = get_cfs_profile(ElementType.STUD, is_load_bearing=True)
        >>> print(profile.name)
        '362S162-68'
    """
    if profile_override:
        if profile_override not in CFS_PROFILES:
            raise KeyError(f"Unknown CFS profile: {profile_override}")
        return CFS_PROFILES[profile_override]

    # Get default profile for this element type based on load-bearing status
    # Load-bearing walls use thicker gauges (68 mil vs 54 mil) and wider flanges
    defaults_table = DEFAULT_CFS_PROFILES_LOAD_BEARING if is_load_bearing else DEFAULT_CFS_PROFILES
    default_profile_name = defaults_table.get(element_type, "362S125-54")

    # If wall thickness provided, adjust the series
    if wall_thickness_inches is not None:
        target_series = get_series_for_wall_thickness(wall_thickness_inches)
        # Replace the series in the default profile name
        # E.g., "362S125-54" -> "600S125-54" for 6" walls
        import re
        adjusted_name = re.sub(r'^\d{3}', target_series, default_profile_name)

        # Check if the adjusted profile exists
        if adjusted_name in CFS_PROFILES:
            return CFS_PROFILES[adjusted_name]
        else:
            # Fallback: try to find a similar profile in the target series
            # Look for any profile in the target series with same type (S/T) and gauge
            match = re.match(r'^(\d{3})([ST])(\d+)-(\d+)', default_profile_name)
            if match:
                _, profile_type, flange, gauge = match.groups()
                # Try common flange widths
                for try_flange in [flange, "125", "162", "200", "250"]:
                    try_name = f"{target_series}{profile_type}{try_flange}-{gauge}"
                    if try_name in CFS_PROFILES:
                        return CFS_PROFILES[try_name]

    # Fallback to default
    return CFS_PROFILES[default_profile_name]


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


def get_profile_for_wall(
    wall_width_inches: float,
    element_type: ElementType,
    is_load_bearing: bool = False,
    gauge: int = 54,
) -> ElementProfile:
    """
    Get the appropriate CFS profile for a wall based on its width.

    This function selects the correct profile series based on wall thickness
    and returns the appropriate stud or track profile.

    Args:
        wall_width_inches: Wall thickness in inches (3.625, 4.0, 5.5, etc.)
        element_type: Type of framing element (STUD, TOP_PLATE, BOTTOM_PLATE)
        is_load_bearing: Whether the wall is load-bearing (uses heavier gauge)
        gauge: Steel gauge in mils (33, 43, 54, 68, 97). Defaults to 54 (16 GA).

    Returns:
        ElementProfile for the requested configuration

    Raises:
        KeyError: If no matching profile is found

    Example:
        >>> profile = get_profile_for_wall(3.625, ElementType.STUD)
        >>> print(profile.name)
        '362S125-54'
        >>> profile = get_profile_for_wall(5.5, ElementType.TOP_PLATE)
        >>> print(profile.name)
        '550T250-54'
    """
    # Find the closest matching series
    series = WALL_WIDTH_TO_SERIES.get(wall_width_inches)
    if series is None:
        # Find closest match
        closest = min(WALL_WIDTH_TO_SERIES.keys(),
                      key=lambda x: abs(x - wall_width_inches))
        series = WALL_WIDTH_TO_SERIES[closest]

    # Determine profile type based on element type
    if element_type in (ElementType.BOTTOM_PLATE, ElementType.TOP_PLATE,
                        ElementType.SILL):
        profile_type = "T"  # Track
        if element_type == ElementType.TOP_PLATE:
            flange = "250"  # Top tracks use 2.5" flange
        elif element_type == ElementType.SILL and wall_width_inches >= 5.5:
            flange = "200"  # Sill tracks for larger walls use 2" flange
        else:
            flange = "125"  # Bottom tracks use 1.25" flange
    else:
        profile_type = "S"  # Stud
        if is_load_bearing and wall_width_inches >= 5.5:
            flange = "250"  # Load-bearing 5.5"+ walls use 2.5" flange studs
        else:
            flange = "125"  # Standard wall studs use 1.25" flange

    # Build profile name
    profile_name = f"{series}{profile_type}{flange}-{gauge}"

    if profile_name not in CFS_PROFILES:
        # Try to find a reasonable fallback
        fallback_name = f"{series}{profile_type}125-{gauge}"
        if fallback_name in CFS_PROFILES:
            return CFS_PROFILES[fallback_name]
        raise KeyError(
            f"CFS profile not found: {profile_name}. "
            f"Available profiles for {series} series: "
            f"{[p for p in CFS_PROFILES.keys() if p.startswith(series)]}"
        )

    return CFS_PROFILES[profile_name]


def get_profiles_for_wall_schedule(
    wall_width_inches: float,
    wall_height_ft: float,
    is_load_bearing: bool = False,
) -> Dict[str, str]:
    """
    Get the complete set of profiles for a wall based on schedule tables.

    This mimics the wall stud schedules from structural drawings, selecting
    appropriate gauges based on wall height.

    Args:
        wall_width_inches: Wall thickness in inches
        wall_height_ft: Wall height in feet
        is_load_bearing: Whether the wall is load-bearing

    Returns:
        Dict mapping element types to profile names:
        {
            "stud": "362S125-33",
            "top_track": "362T250-54",
            "bottom_track": "362T125-54",
            ...
        }

    Example:
        >>> profiles = get_profiles_for_wall_schedule(3.625, 15.0)
        >>> print(profiles["stud"])
        '362S125-33'
    """
    # Determine gauge based on wall height (simplified schedule)
    # Based on typical non-bearing partition schedules
    if is_load_bearing:
        gauge = 97  # 12 GA for load-bearing
    elif wall_height_ft <= 15.0:
        gauge = 33  # 20 GA for shorter walls
    elif wall_height_ft <= 17.5:
        gauge = 43  # 18 GA for medium walls
    elif wall_height_ft <= 20.0:
        gauge = 54  # 16 GA for taller walls
    else:
        gauge = 68  # 14 GA for very tall walls

    series = WALL_WIDTH_TO_SERIES.get(wall_width_inches, "362")

    # Build profile set
    if is_load_bearing and wall_width_inches >= 5.5:
        stud_profile = f"550S250-97"
    else:
        stud_profile = f"{series}S125-{gauge}"

    return {
        "stud": stud_profile,
        "king_stud": stud_profile,
        "trimmer": stud_profile,
        "sill_cripple": stud_profile,
        "header_cripple": stud_profile,
        "top_track": f"{series}T250-54",
        "bottom_track": f"{series}T125-54",
        "sill_track": f"{series}S125-68" if not is_load_bearing else f"550T200-54",
    }
