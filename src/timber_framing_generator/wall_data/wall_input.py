# File: src/wall_data/wall_input.py

from typing import List, Dict, Union, Optional
import Rhino.Geometry as rg  # Import Rhino Geometry for type hinting

WallInputData = Dict[
    str, Union[rg.Curve, float, bool, List[Dict[str, Union[str, float]]]]
]  # Type hint for Wall Input Data


def create_wall_data_dict(
    wall_base_curve: rg.Curve,  # Rhino Curve Geometry object
    wall_base_elevation: float,
    wall_top_elevation: float,
    is_exterior_wall: bool,
    openings_data: Optional[
        List[Dict[str, Union[str, float]]]
    ] = None,  # List of opening data dictionaries, now optional
) -> WallInputData:
    """
    Creates a dictionary representing wall input data.

    Args:
        wall_base_curve: Rhino Curve geometry object representing the wall's base curve.
        wall_base_elevation: Base elevation of the wall in project units.
        wall_top_elevation: Top elevation of the wall in project units.
        is_exterior_wall: True if the wall is an exterior wall, False if interior.
        openings_data: (Optional) List of dictionaries, where each dictionary represents
                       data for an opening (window or door) in the wall.
                       Defaults to None, which is treated as no openings.

    Returns:
        A dictionary containing the wall input data, structured as WallInputData type.
    """
    if openings_data is None:
        openings_data = []

    wall_data: WallInputData = {
        "wall_base_curve": wall_base_curve,
        "wall_base_elevation": wall_base_elevation,
        "wall_top_elevation": wall_top_elevation,
        "is_exterior_wall": is_exterior_wall,
        "openings": openings_data,
    }

    return wall_data


def create_opening_data_dict(
    opening_type: str,  # "window" or "door"
    start_u_coordinate: float,
    rough_width: float,
    rough_height: float,
    base_elevation_relative_to_wall_base: float,
) -> Dict[str, Union[str, float]]:
    """
    Creates a dictionary representing opening data for a single opening.

    Args:
        opening_type: Type of opening, either "window" or "door" (string).
        start_u_coordinate: U coordinate along the wall's base curve where the opening starts.
        rough_width: Rough width of the opening in project units.
        rough_height: Rough height of the opening in project units.
        base_elevation_relative_to_wall_base: Vertical distance from the wall's base elevation
                                             to the bottom of the opening in project units.

    Returns:
        A dictionary containing the opening data.
    """
    opening_data: Dict[str, Union[str, float]] = {
        "opening_type": opening_type,
        "start_u_coordinate": start_u_coordinate,
        "rough_width": rough_width,
        "rough_height": rough_height,
        "base_elevation_relative_to_wall_base": base_elevation_relative_to_wall_base,
    }
    return opening_data
