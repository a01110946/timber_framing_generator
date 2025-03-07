# File: src/config/__init__.py

"""
Configuration package for the Timber Framing Generator.
Provides a unified interface to all configuration systems:
- Unit management and conversion
- Framing profiles and parameters
- Wall assembly specifications
- System-wide defaults
"""

from timber_framing_generator.config.units import (
    get_project_units,
    convert_to_feet,
    convert_from_feet,
    ProjectUnits,
)

from timber_framing_generator.config.framing import (
    PROFILES,
    FRAMING_PARAMS,
    WALL_TYPE_PROFILES,
    ProfileDimensions,
    RepresentationType,
    PlateType,
    get_profile_for_wall_type,
)

from timber_framing_generator.config.assembly import (
    WALL_ASSEMBLY,
    SHEATHING_PARAMS,
    OPENING_DEFAULTS,
    get_assembly_dimensions,
)

# Debug flag for development
DEBUG = True


def get_system_info() -> dict:
    """
    Returns a complete overview of the current system configuration.
    Useful for debugging and validation.
    """
    current_units = get_project_units()
    return {
        "project_units": current_units.value,
        "wall_assembly": get_assembly_dimensions(current_units),
        "framing_params": {
            k: convert_from_feet(v, current_units)
            for k, v in FRAMING_PARAMS.items()
            if isinstance(v, (int, float))
        },
        "profiles": {
            name: profile.get_dimensions(current_units)
            for name, profile in PROFILES.items()
        },
    }


# When any module in the config package is run directly
if __name__ == "__main__":
    import json

    print("Current System Configuration:")
    print(json.dumps(get_system_info(), indent=2))
