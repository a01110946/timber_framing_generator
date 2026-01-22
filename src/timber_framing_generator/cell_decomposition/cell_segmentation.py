# File: timber_framing_generator/cell_decomposition/cell_segmentation.py

from typing import List, Dict, Union
import Rhino.Geometry as rg
from src.timber_framing_generator.cell_decomposition.cell_types import (
    create_wall_boundary_cell_data,
    create_opening_cell_data,
    create_stud_cell_data,
    create_sill_cripple_cell_data,
    create_header_cripple_cell_data,
    CellDataDict,  # Import the type hint
)


def _calculate_corner_points(
    u_start: float, u_end: float, v_start: float, v_end: float, base_plane
) -> List:
    """
    Calculates corner points for a cell data dictionary based on u and v ranges
    using the provided base_plane. The method uses base_plane.PointAt(u, v) so that
    the points are correctly placed in the plane's coordinate system.

    If u_start > u_end or v_start > v_end, the values are swapped so that the lower value comes first.
    """
    # Ensure that u_start is less than u_end, and v_start less than v_end.
    if u_start > u_end:
        u_start, u_end = u_end, u_start
    if v_start > v_end:
        v_start, v_end = v_end, v_start

    # Use the plane's local coordinate system. In RhinoCommon, Plane.PointAt(u, v) returns:
    #   base_plane.Origin + (base_plane.XAxis * u) + (base_plane.YAxis * v)
    pt1 = base_plane.PointAt(u_start, v_start)
    pt2 = base_plane.PointAt(u_end, v_start)
    pt3 = base_plane.PointAt(u_end, v_end)
    pt4 = base_plane.PointAt(u_start, v_end)

    return [pt1, pt2, pt3, pt4]


def decompose_wall_to_cells(
    wall_length: float,
    wall_height: float,
    opening_data_list: List[Dict[str, Union[str, float]]],
    base_plane: rg.Plane,
) -> Dict[str, Union[CellDataDict, List[CellDataDict]]]:
    """
    Decomposes a wall into cells (dictionaries) based on openings and a base plane.

    Args:
        wall_length: The length of the wall.
        wall_height: The height of the wall.
        opening_data_list: A list of dictionaries, each representing an opening.
        base_plane: The Rhino.Geometry.Plane representing the wall's base plane.

    Returns:
        A dictionary containing the different cell types and their data dictionaries,
        including corner points in world coordinates (computed using base_plane).
    """
    try:
            # Original code with added debug statements
        print(f"DEBUG: Decomposing wall: length={wall_length}, height={wall_height}")
        print(f"DEBUG: Number of openings: {len(opening_data_list)}")
        print(f"DEBUG: Base plane valid: {base_plane is not None}")

        # 1. Create the wall boundary cell (covers the entire wall)
        wall_boundary_cell_data = create_wall_boundary_cell_data(
            u_range=[0.0, wall_length], v_range=[0.0, wall_height]
        )

        # 2. For each opening, create an opening cell
        opening_cells_data = []
        for opening_data in opening_data_list:
            oc_data = create_opening_cell_data(
                u_range=[
                    opening_data["start_u_coordinate"],
                    opening_data["start_u_coordinate"] + opening_data["rough_width"],
                ],
                v_range=[
                    opening_data["base_elevation_relative_to_wall_base"],
                    opening_data["base_elevation_relative_to_wall_base"]
                    + opening_data["rough_height"],
                ],
                opening_type=opening_data["opening_type"],
            )
            opening_cells_data.append(oc_data)

        # 3. Create stud cells in the gaps between openings.
        stud_cells_data = []
        current_u = 0.0
        # Sort the opening cells by their starting u-coordinate.
        sorted_opening_cells_data = sorted(
            opening_cells_data, key=lambda cell_data: cell_data["u_start"]
        )
        for opening_cell_data in sorted_opening_cells_data:
            if opening_cell_data["u_start"] > current_u:
                stud_cells_data.append(
                    create_stud_cell_data(
                        u_range=[current_u, opening_cell_data["u_start"]],
                        v_range=[0.0, wall_height],
                    )
                )
            current_u = max(current_u, opening_cell_data["u_end"])
        if current_u < wall_length:
            stud_cells_data.append(
                create_stud_cell_data(
                    u_range=[current_u, wall_length], v_range=[0.0, wall_height]
                )
            )

        # 4. For each opening cell, create sill and header cripple cells with validation.
        sill_cripple_cells_data = []
        header_cripple_cells_data = []
        tol = 1e-6  # Tolerance for valid dimensions.
        for opening_cell_data in opening_cells_data:
            u_start = opening_cell_data["u_start"]
            u_end = opening_cell_data["u_end"]
            v_start = opening_cell_data["v_start"]
            # For a sill cripple cell, require that the horizontal extent is positive
            # and that the opening's bottom is above the wall's base.
            if (u_end - u_start) > tol and (v_start > tol):
                sill_cell = create_sill_cripple_cell_data(
                    u_range=[u_start, u_end], v_range=[0.0, v_start]
                )
                sill_cripple_cells_data.append(sill_cell)
            else:
                print(
                    "Skipping sill cripple cell: u_range=({},{}) or insufficient v_range (v_start={})".format(
                        u_start, u_end, v_start
                    )
                )

            # For a header cripple cell, require that the horizontal extent is positive
            # and that there is vertical space between the opening's top and the wall's top.
            if (u_end - u_start) > tol and (
                (wall_height - opening_cell_data["v_end"]) > tol
            ):
                header_cell = create_header_cripple_cell_data(
                    u_range=[u_start, u_end],
                    v_range=[opening_cell_data["v_end"], wall_height],
                )
                header_cripple_cells_data.append(header_cell)
            else:
                print(
                    "Skipping header cripple cell: insufficient vertical space (v_end={}, wall_height={})".format(
                        opening_cell_data.get("v_end"), wall_height
                    )
                )

        # 5. Build a dictionary grouping the different cell types.
        cell_data_dict = {
            "wall_boundary_cell": wall_boundary_cell_data,
            "opening_cells": opening_cells_data,
            "stud_cells": stud_cells_data,
            "sill_cripple_cells": sill_cripple_cells_data,
            "header_cripple_cells": header_cripple_cells_data,
        }

        # 6. For each cell in the dictionary, compute its corner points.
        # Assume that _calculate_corner_points is available (imported or defined in this module)
        for key, cell_group in cell_data_dict.items():
            if isinstance(cell_group, list):
                for cell in cell_group:
                    u_s = cell.get("u_start")
                    u_e = cell.get("u_end")
                    v_s = cell.get("v_start")
                    v_e = cell.get("v_end")
                    # Only compute corner points if all four values are present.
                    if None not in [u_s, u_e, v_s, v_e]:
                        cell["corner_points"] = _calculate_corner_points(
                            u_s, u_e, v_s, v_e, base_plane
                        )
            elif isinstance(cell_group, dict):
                u_s = cell_group.get("u_start")
                u_e = cell_group.get("u_end")
                v_s = cell_group.get("v_start")
                v_e = cell_group.get("v_end")
                if None not in [u_s, u_e, v_s, v_e]:
                    cell_group["corner_points"] = _calculate_corner_points(
                        u_s, u_e, v_s, v_e, base_plane
                    )

        return cell_data_dict
    except Exception as e:
        print(f"DEBUG: Error in decompose_wall_to_cells: {str(e)}")
    import traceback
    print(traceback.format_exc())
    raise

