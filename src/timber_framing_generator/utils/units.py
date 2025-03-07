# File: timber_framing_generator/utils/units.py
from enum import Enum

class ProjectUnits(Enum):
    """Enumeration of supported project units."""
    FEET = "feet"
    METERS = "meters"
    INCHES = "inches"

# Current project units setting
_PROJECT_UNITS = ProjectUnits.FEET

def get_project_units() -> ProjectUnits:
    """Returns the current project units setting."""
    return _PROJECT_UNITS

def convert_to_feet(value: float, current_units: str) -> float:
    """Converts a value from the specified units to feet."""
    if current_units.lower() == "inches":
        return value / 12.0
    elif current_units.lower() == "meters":
        return value * 3.28084
    elif current_units.lower() == "feet":
        return value
    else:
        raise ValueError(f"Unsupported unit: {current_units}")

def convert_from_feet(value: float, target_units: str) -> float:
    """Converts a value from feet to the specified units."""
    if target_units.lower() == "inches":
        return value * 12.0
    elif target_units.lower() == "meters":
        return value / 3.28084
    elif target_units.lower() == "feet":
        return value
    else:
        raise ValueError(f"Unsupported unit: {target_units}")

def inches_to_mm(inches: float) -> float:
    return inches * 25.4

def mm_to_inches(mm: float) -> float:
    return mm / 25.4

def feet_to_inches(feet: float) -> float:
    return feet * 12.0