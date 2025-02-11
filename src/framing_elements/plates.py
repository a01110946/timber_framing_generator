# File: src/framing_elements/plates.py

from typing import List, Dict, Optional
import Rhino.Geometry as rg
from src.config.assembly import FRAMING_PARAMS

from .location_data import get_plate_location_data
from .plate_parameters import PlateParameters
from .plate_geometry import PlateGeometry

def create_plates(
    wall_data: Dict,
    plate_type: str = "bottom_plate",
    representation_type: str = "structural",
    profile_override: Optional[str] = None,
    layers: Optional[int] = None
) -> List[Dict]:
    """
    Creates plate data for a wall, handling single or double plate configurations.
    
    This is the main entry point for plate creation, orchestrating:
    1. Location data extraction
    2. Parameter determination
    3. Geometry creation
    
    Returns a list of dictionaries containing complete plate definitions.
    """
    # Determine number of layers
    layers = layers or FRAMING_PARAMS.get(f"{plate_type}_layers", 1)
    if layers not in [1, 2]:
        raise ValueError(f"Unsupported number of {plate_type} layers: {layers}")
    
    plates = []
    
    if layers == 1:
        # Single plate layer
        location_data = get_plate_location_data(
            wall_data,
            plate_type,
            representation_type
        )
        
        parameters = PlateParameters.from_wall_type(
            wall_data["wall_type"],
            plate_type,
            representation_type,
            profile_override
        )
        
        geometry = PlateGeometry(location_data, parameters)
        plates.append(geometry.get_geometry_data())
        
    else:
        # Double plate layer - create both plates
        plate_types = {
            "bottom_plate": ["sole_plate", "bottom_plate"],
            "top_plate": ["top_plate", "cap_plate"]
        }.get(plate_type)
        
        if not plate_types:
            raise ValueError(f"Double layer not supported for {plate_type}")
        
        for layer_type in plate_types:
            location_data = get_plate_location_data(
                wall_data,
                layer_type,
                representation_type
            )
            
            parameters = PlateParameters.from_wall_type(
                wall_data["wall_type"],
                layer_type,
                representation_type,
                profile_override
            )
            
            geometry = PlateGeometry(location_data, parameters)
            plates.append(geometry.get_geometry_data())
    
    return plates