# File: timber_framing_generator/cell_decomposition/cell_types.py

from typing import Dict, Union

CellDataDict = Dict[str, Union[str, float, list]]  # Type hint for Cell Data Dictionary


def create_wall_boundary_cell_data(u_range: list, v_range: list) -> CellDataDict:
    """Creates a dictionary representing Wall Boundary Cell (WBC) data."""
    return {
        "cell_type": "WBC",
        "u_start": u_range[0],
        "u_end": u_range[1],
        "v_start": v_range[0],
        "v_end": v_range[1],
    }


def create_opening_cell_data(
    u_range: list, v_range: list, opening_type: str
) -> CellDataDict:
    """Creates a dictionary representing Opening Cell (OC) data."""
    return {
        "cell_type": "OC",
        "opening_type": opening_type,
        "u_start": u_range[0],
        "u_end": u_range[1],
        "v_start": v_range[0],
        "v_end": v_range[1],
    }


def create_stud_cell_data(u_range: list, v_range: list) -> CellDataDict:
    """Creates a dictionary representing Stud Cell (SC) data."""
    return {
        "cell_type": "SC",
        "u_start": u_range[0],
        "u_end": u_range[1],
        "v_start": v_range[0],
        "v_end": v_range[1],
    }


def create_sill_cripple_cell_data(u_range: list, v_range: list) -> CellDataDict:
    """Creates a dictionary representing Sill Cripple Cell (SCC) data."""
    return {
        "cell_type": "SCC",
        "u_start": u_range[0],
        "u_end": u_range[1],
        "v_start": v_range[0],
        "v_end": v_range[1],
    }


def create_header_cripple_cell_data(u_range: list, v_range: list) -> CellDataDict:
    """Creates a dictionary representing Header Cripple Cell (HCC) data."""
    return {
        "cell_type": "HCC",
        "u_start": u_range[0],
        "u_end": u_range[1],
        "v_start": v_range[0],
        "v_end": v_range[1],
    }


def deconstruct_cell(cell):
    """
    Generalized function to deconstruct any cell type into its components for Grasshopper.

    Args:
        cell: The custom cell object.

    Returns:
        A dictionary containing deconstructed components.
    """
    return {
        "cell_type": cell.get("cell_type"),
        "u_start": cell.get("u_start"),
        "u_end": cell.get("u_end"),
        "v_start": cell.get("v_start"),
        "v_end": cell.get("v_end"),
        "corner_points": cell.get("corner_points"),
    }


def deconstruct_all_cells(cell_data):
    """
    Deconstructs all cell types into components for Grasshopper compatibility.

    Args:
        cell_data: A dictionary containing categorized cells (by type).

    Returns:
        A list of dictionaries for all cells, with their deconstructed data.
    """
    all_deconstructed_cells = []
    for key, cells in cell_data.items():
        if isinstance(cells, list):
            for cell in cells:
                all_deconstructed_cells.append(deconstruct_cell(cell))
        elif isinstance(cells, dict):
            all_deconstructed_cells.append(deconstruct_cell(cells))
    return all_deconstructed_cells


"""
def deconstruct_all_cells(cell_data: dict) -> list:
    \"\"\"
    Flattens the cell data dictionary into a single list of cell dictionaries.
    \"\"\"
    all_cells = []
    for key, cells in cell_data.items():
        if isinstance(cells, list):
            for cell in cells:
                all_cells.append(deconstruct_cell(cell))
        elif isinstance(cells, dict):
            all_cells.append(deconstruct_cell(cells))
    return all_cells
"""
