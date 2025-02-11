# File: src/framing_elements/plates.py

import Rhino.Geometry as rg
from config import FRAMING_PARAMS, PROFILES

def generate_plate(
    base_geometry, 
    profile="2x4", 
    framing_type="top_plate", 
    mounting_mode="schematic",
    plate_thickness=None, 
    plate_width=None
):
    """
    Generates a plate using both its base geometry (which positions and orients it)
    and framing parameters. The user can either pass a standard profile name (e.g., "2x4", "2x6")
    or a Revit profile object. Additionally, a keyword argument 'framing_type' allows the user to
    specify the type (e.g., "top_plate", "cap_plate", "bottom_plate", "sole_plate") so that
    the appropriate offset is applied.
    
    Args:
        base_geometry: The base geometry (typically a Rhino.Geometry.Curve, or tuple of points)
                       that defines the placement of the plate.
        profile (str or object): Either a standard profile name or a Revit profile object.
        framing_type (str): Specifies the type of plate. Options include "top_plate", "cap_plate",
                            "bottom_plate", "sole_plate". Defaults to "top_plate".
        mounting_mode (str): Specifies the mounting mode for the plate. Options include "schematic", "structural". Defaults to "schematic".
        plate_thickness (float, optional): Explicit thickness. Overrides profile if provided.
        plate_width (float, optional): Explicit width. Overrides profile if provided.
    
    Returns:
        dict: A dictionary containing the plate's geometry, metadata, and derived dimensions.
    """
    # Determine dimensions from profile
    if isinstance(profile, str):
        dimensions = PROFILES.get(profile, {})
        thickness = plate_thickness or dimensions.get("thickness", FRAMING_PARAMS.get("plate_thickness", 0.04))
        width = plate_width or dimensions.get("width", FRAMING_PARAMS.get("plate_width", 0.09))
    else:
        # Assume profile is a Revit profile object with attributes Thickness and Width.
        thickness = plate_thickness or getattr(profile, "Thickness", FRAMING_PARAMS.get("plate_thickness", 0.04))
        width = plate_width or getattr(profile, "Width", FRAMING_PARAMS.get("plate_width", 0.09))
    
    # Determine offset based on framing_type:
    # Here, the assumption is that the base_geometry (a line) is at the wall's nominal level.
    if framing_type in ["top_plate", "cap_plate"]:
        if framing_type == "top_plate":
            offset = thickness / 2.0  # upward offset
        elif framing_type == "cap_plate":
            offset = 3 * thickness / 2.0
    elif framing_type in ["bottom_plate", "sole_plate"]:
        if framing_type == "bottom_plate":
            offset = -thickness / 2.0  # downward offset
        elif framing_type == "sole_plate":
            offset = -3 * thickness / 2.0
    else:
        offset = 0
    
    # Generate the plate geometry based on the base geometry.
    # Here, we assume base_geometry is a Rhino.Geometry.Curve.
    if isinstance(base_geometry, rg.Curve):
        plate_curve = base_geometry.DuplicateCurve()
        translation = rg.Vector3d(0, 0, offset)
        plate_curve.Translate(translation)
    else:
        raise ValueError("Unsupported base_geometry type. Expected a Rhino.Geometry.Curve.")
    
    return {
        "type": "plate",
        "framing_type": framing_type,
        "profile": profile,
        "thickness": thickness,
        "width": width,
        "base_geometry": base_geometry,
        "geometry": plate_curve
    }

def create_top_plate(base_curve: rg.Curve, elevation: float, top_plate_layers: int = None, plate_thickness: float = None) -> list:
    """
    Create top plate curves from the wall's base curve at a given elevation.
    
    If top_plate_layers == 1:
        - Returns a single plate curve offset downward by half the plate thickness.
    If top_plate_layers == 2:
        - Returns two curves: the first (the top plate) offset by half the plate thickness,
          and the second (the cap plate) offset by 1.5 times the plate thickness.
          
    Parameters:
        base_curve (rg.Curve): The wall's base curve.
        elevation (float): The starting elevation for the top plate (i.e. the top of the wall).
        top_plate_layers (int, optional): Number of top plate layers. Defaults to FRAMING_PARAMS["top_plate_layers"].
        plate_thickness (float, optional): The thickness of a plate. Defaults to FRAMING_PARAMS["plate_thickness"].
    
    Returns:
        list of rg.Curve: A list of top plate curves.
    """
    if top_plate_layers is None:
        top_plate_layers = FRAMING_PARAMS.get("top_plate_layers", 1)
    if plate_thickness is None:
        plate_thickness = FRAMING_PARAMS.get("plate_thickness", 3.5)
    
    plates = []
    if top_plate_layers == 1:
        # Single top plate: offset downward by half the plate thickness
        translation = rg.Vector3d(0, 0, elevation - plate_thickness/2)
        plate = base_curve.DuplicateCurve()
        plate.Translate(translation)
        plates.append(plate)
    elif top_plate_layers == 2:
        # Two layers: cap plate centered at elevation - plate_thickness/2,
        # and top plate centered at elevation - 3*plate_thickness/2.
        translation1 = rg.Vector3d(0, 0, elevation - plate_thickness/2)
        plate1 = base_curve.DuplicateCurve()
        plate1.Translate(translation1)
        
        translation2 = rg.Vector3d(0, 0, elevation - 3*plate_thickness/2)
        plate2 = base_curve.DuplicateCurve()
        plate2.Translate(translation2)
        
        plates.extend([plate1, plate2])
    else:
        raise ValueError("Unsupported number of top plate layers: {}".format(top_plate_layers))
    return plates

def create_bottom_plate(base_curve: rg.Curve, elevation: float, bottom_plate_layers: int = 1, plate_thickness: float = None) -> list:
    """
    Create bottom plate curves from the wall's base curve at a given elevation.
    
    For a single layer, the bottom plate is offset upward by half the plate thickness.
    For two layers, returns two curves:
      - The first (bottom plate) offset upward by half the plate thickness.
      - The second (cap bottom plate) offset upward by 1.5 times the plate thickness.
    
    Parameters:
        base_curve (rg.Curve): The wall's base curve.
        elevation (float): The starting elevation for the bottom plate (i.e. the base of the wall).
        bottom_plate_layers (int, optional): Number of bottom plate layers (default is 1).
        plate_thickness (float, optional): The thickness of a plate. Defaults to FRAMING_PARAMS["plate_thickness"].
    
    Returns:
        list of rg.Curve: A list of bottom plate curves.
    """
    if plate_thickness is None:
        plate_thickness = FRAMING_PARAMS.get("plate_thickness", 3.5)
    
    plates = []
    if bottom_plate_layers == 1:
        # Single bottom plate: offset upward by half the plate thickness.
        translation = rg.Vector3d(0, 0, elevation + plate_thickness/2)
        plate = base_curve.DuplicateCurve()
        plate.Translate(translation)
        plates.append(plate)
    elif bottom_plate_layers == 2:
        # Two layers: first plate offset by half the plate thickness,
        # second (cap) plate offset by 1.5 times the plate thickness upward.
        translation1 = rg.Vector3d(0, 0, elevation + plate_thickness/2)
        plate1 = base_curve.DuplicateCurve()
        plate1.Translate(translation1)
        
        translation2 = rg.Vector3d(0, 0, elevation + 3*plate_thickness/2)
        plate2 = base_curve.DuplicateCurve()
        plate2.Translate(translation2)
        
        plates.extend([plate1, plate2])
    else:
        raise ValueError("Unsupported number of bottom plate layers: {}".format(bottom_plate_layers))
    return plates

def calculate_plate_locations(wall_data, plate_type="top_plate", offset=None):
    """
    Calculates the placement curve for a plate given wall data.
    
    Args:
        wall_data (dict): A dictionary containing wall data. Must include the key
                          "wall_base_curve" which is a Rhino.Geometry.Curve.
        plate_type (str): Specifies the type of plate. Options include:
                          "top_plate", "cap_plate", "bottom_plate", "sole_plate".
                          The default is "top_plate".
        offset (float, optional): A vertical offset to apply to the base curve. If not
                                  provided, a default is computed based on plate_type.
    
    Returns:
        rg.Curve: A Rhino.Geometry.Curve representing the placement location for the plate.
    
    Example:
        >>> # Given a wall_data dictionary with a valid "wall_base_curve":
        >>> placement_curve = calculate_plate_locations(wall_data, plate_type="top_plate")
    """
    # Retrieve the base curve from the wall data.
    base_curve = wall_data.get("wall_base_curve")
    if base_curve is None:
        raise ValueError("Wall data must include 'wall_base_curve' for plate placement.")
    
    # Determine a default offset based on the plate type if no offset is provided.
    # Here we use a hardcoded default thickness; in production, read this from config.
    default_thickness = 0.04  # Example default thickness in whatever unit is used (e.g., meters or inches)
    if offset is None:
        if plate_type == "top_plate":
            offset = default_thickness / 2.0   # Upward offset: half the thickness.
        elif plate_type == "cap_plate":
            offset = 3 * default_thickness / 2.0  # Upward offset: one and a half times the thickness.
        elif plate_type == "bottom_plate":
            offset = - default_thickness / 2.0  # Downward offset.
        elif plate_type == "sole_plate":
            offset = - 3 * default_thickness / 2.0
        else:
            offset = 0.0  # Fallback if an unrecognized plate type is provided.
    
    # Duplicate the base curve and translate it vertically by the computed offset.
    placement_curve = base_curve.DuplicateCurve()
    translation = rg.Vector3d(0, 0, offset)
    placement_curve.Translate(translation)
    
    return placement_curve

### In the future, see if we can, in addition to the 'plate_thickness' parameter, add a 'profile' or 'class of stud' input and derive the thickness from there.
### The idea being, we can have multiple options of setting these values, depending on which information is available, more flexibility for the user (and LLMs).
### To accomplish this, should we explore keyword arguments or have multiple functions.