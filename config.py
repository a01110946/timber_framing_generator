# File: /src/config.py

PROJECT_UNITS = "feet"  # or "meters", "inches", etc.

def get_project_units():
    """Returns the project units as a string."""
    return PROJECT_UNITS

def convert_to_feet(value, current_units):
    """Converts a value from current_units to feet."""
    if current_units == "feet":
        return value
    elif current_units == "meters":
        return value * 3.28084
    elif current_units == "inches":
        return value / 12.0
    else:
        raise ValueError(f"Unsupported unit: {current_units}")

def convert_from_feet(value, target_units):
    """Converts a value from feet to target_units."""
    if target_units == "feet":
        return value
    elif target_units == "meters":
        return value / 3.28084
    elif target_units == "inches":
        return value * 12.0
    else:
        raise ValueError(f"Unsupported unit: {target_units}")

# Example usage in other modules:
# from src.config import get_project_units, convert_to_feet, convert_from_feet
# current_project_units = get_project_units()
# value_in_feet = convert_to_feet(10, "meters") # Convert 10 meters to feet