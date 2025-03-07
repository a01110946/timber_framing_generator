# File: timber_framing_generator/config/units.py

"""
Unit management and conversion functionality for the Timber Framing Generator.
This module handles all unit-related operations and configurations.
"""

from enum import Enum
from typing import Union, Dict

class ProjectUnits(Enum):
    """
    Enumeration of supported project units.
    Using an enum provides type safety and autocompletion support.
    """
    FEET = "feet"
    METERS = "meters"
    INCHES = "inches"

# Current project units setting
_PROJECT_UNITS = ProjectUnits.FEET

# Conversion factors to feet
_CONVERSION_TO_FEET: Dict[ProjectUnits, float] = {
    ProjectUnits.FEET: 1.0,
    ProjectUnits.METERS: 3.28084,
    ProjectUnits.INCHES: 1/12.0
}

# Conversion factors from feet
_CONVERSION_FROM_FEET: Dict[ProjectUnits, float] = {
    ProjectUnits.FEET: 1.0,
    ProjectUnits.METERS: 1/3.28084,
    ProjectUnits.INCHES: 12.0
}

def get_project_units() -> ProjectUnits:
    """
    Returns the current project units setting.
    
    Returns:
        ProjectUnits enum representing the current project units
    """
    return _PROJECT_UNITS

def set_project_units(units: Union[ProjectUnits, str]) -> None:
    """
    Sets the project units.
    
    Args:
        units: Either a ProjectUnits enum value or a string matching an enum name
        
    Raises:
        ValueError: If the provided units are not supported
    """
    global _PROJECT_UNITS
    
    if isinstance(units, str):
        try:
            units = ProjectUnits(units.lower())
        except ValueError:
            raise ValueError(f"Unsupported unit string: {units}")
    
    if not isinstance(units, ProjectUnits):
        raise ValueError(f"Units must be ProjectUnits enum or string, got {type(units)}")
        
    _PROJECT_UNITS = units

def convert_to_feet(value: float, current_units: Union[ProjectUnits, str]) -> float:
    """
    Converts a value from the specified units to feet.
    
    Args:
        value: The numeric value to convert
        current_units: The units to convert from (ProjectUnits enum or string)
        
    Returns:
        The value converted to feet
        
    Raises:
        ValueError: If the provided units are not supported
    """
    if isinstance(current_units, str):
        try:
            current_units = ProjectUnits(current_units.lower())
        except ValueError:
            raise ValueError(f"Unsupported unit: {current_units}")
            
    conversion_factor = _CONVERSION_TO_FEET.get(current_units)
    if conversion_factor is None:
        raise ValueError(f"No conversion factor found for {current_units}")
        
    return value * conversion_factor

def convert_from_feet(value: float, target_units: Union[ProjectUnits, str]) -> float:
    """
    Converts a value from feet to the specified target units.
    
    Args:
        value: The numeric value in feet to convert
        target_units: The units to convert to (ProjectUnits enum or string)
        
    Returns:
        The converted value in the target units
        
    Raises:
        ValueError: If the provided units are not supported
    """
    if isinstance(target_units, str):
        try:
            target_units = ProjectUnits(target_units.lower())
        except ValueError:
            raise ValueError(f"Unsupported unit: {target_units}")
            
    conversion_factor = _CONVERSION_FROM_FEET.get(target_units)
    if conversion_factor is None:
        raise ValueError(f"No conversion factor found for {target_units}")
        
    return value * conversion_factor