# File: timber_framing_generator/config.py
"""
Global configuration for the Timber Framing Generator.

This file defines the parameters that control:
  - The overall wall assembly (layer thicknesses for exterior, core, and interior)
  - Framing element dimensions (studs, plates, headers, sills, etc.)
  - Sheathing and insulation details
  - Additional options such as stud staggering
  - Openings defaults

All dimensions are assumed to be in inches (or any other consistent unit) unless noted.
These parameters can later be connected to a UI so that users can adjust them as needed.
"""

# ==============================
# Wall Assembly (Layer) Settings
# ==============================
WALL_ASSEMBLY = {
    "exterior_layer_thickness": 0.75,  # Thickness of the exterior finish layer (e.g., sheathing/cladding)
    "core_layer_thickness": 3.5,         # Thickness of the core structural layer where framing is located
    "interior_layer_thickness": 0.5,     # Thickness of the interior finish layer (e.g., gypsum board)
    "total_wall_thickness": lambda: (
        WALL_ASSEMBLY["exterior_layer_thickness"] +
        WALL_ASSEMBLY["core_layer_thickness"] +
        WALL_ASSEMBLY["interior_layer_thickness"]
    ),
}

# ===========================
# Framing Element Parameters
# ===========================
FRAMING_PARAMS = {
    "stud_spacing": 16.0,       # Stud spacing (on-center distance) in inches
    "stud_width": 3.5,          # Actual width of a stud (e.g., 2x4 nominal, which is typically 1.5" x 3.5")
    "stud_depth": 3.5,          # Depth (or thickness) of the stud
    "top_plate_layers": 2,      # Number of top plate layers
    "plate_thickness": 3.5,     # Thickness for plates (usually similar to stud depth)
    "header_height": 6.0,       # Vertical clearance above an opening for the header (in inches)
    "header_depth": 5.5,        # Depth (thickness) of the header
    "sill_depth": 5.5,          # Depth (thickness) of the sill
    "staggered_studs": False,   # Boolean flag to enable/disable staggered stud layout
    "stagger_offset": 1.75,     # Offset amount for staggered studs (in inches)
}

# ===========================
# Standard Framing Profiles
# ===========================
# These are example values in inches.
# Note: The actual dimensions may differ based on regional standards.
PROFILES = {
    "2x4": {"thickness": 1.5, "width": 3.5},  # Nominal 2x4 (actual 1.5" x 3.5")
    "2x6": {"thickness": 1.5, "width": 5.5},  # Nominal 2x6 (actual 1.5" x 5.5")
    "custom": {"thickness": None, "width": None}  # Placeholder for manual input.
}

# ======================
# Sheathing & Insulation
# ======================
SHEATHING_PARAMS = {
    "sheathing_thickness": 0.5,   # Thickness of sheathing material (e.g., OSB or plywood)
    "insulation_thickness": 3.5,  # Thickness of insulation within the exterior layer (optional)
    "finish_thickness": 0.5,      # Thickness of interior finishing material (optional)
}

# ======================
# Openings Default Sizes
# ======================
OPENING_DEFAULTS = {
    "door": {
        "rough_width": 30.0,    # Typical rough opening width for a door (in inches)
        "rough_height": 80.0,   # Typical rough opening height for a door (in inches)
    },
    "window": {
        "rough_width": 36.0,    # Typical rough opening width for a window (in inches)
        "rough_height": 48.0,   # Typical rough opening height for a window (in inches)
    }
}

# ======================
# Unit Conversion Settings
# ======================
# (Optional: if you need to convert between units, define conversion factors here)
UNITS = {
    "inches_to_mm": 25.4,
    "mm_to_inches": 1 / 25.4,
    "feet_to_inches": 12.0,
}

# ======================
# Debug and Output Options
# ======================
DEBUG = True   # Set to True to print additional debug information during processing

# ======================
# Utility Functions
# ======================
def get_total_wall_thickness():
    """
    Returns the total wall thickness computed from the assembly layers.
    """
    return (
        WALL_ASSEMBLY["exterior_layer_thickness"] +
        WALL_ASSEMBLY["core_layer_thickness"] +
        WALL_ASSEMBLY["interior_layer_thickness"]
    )

# ======================
# End of Configuration
# ======================
if __name__ == '__main__':
    # For quick debugging/testing of parameter values:
    print("Wall Assembly Parameters:")
    for key, value in WALL_ASSEMBLY.items():
        if callable(value):
            print(f"  {key}: {value()}")
        else:
            print(f"  {key}: {value}")
    print("\nFraming Parameters:")
    for key, value in FRAMING_PARAMS.items():
        print(f"  {key}: {value}")
    print("\nSheathing Parameters:")
    for key, value in SHEATHING_PARAMS.items():
        print(f"  {key}: {value}")
    print("\nOpenings Defaults:")
    for typ, params in OPENING_DEFAULTS.items():
        print(f"  {typ}: {params}")
    print("\nUnit Conversions:")
    for key, value in UNITS.items():
        print(f"  {key}: {value}")
