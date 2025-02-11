# File: src/cell_decomposition/cell_visualizer.py

import Rhino.Geometry as rg
import System.Drawing


def create_rectangles_from_cell_data(cells, base_plane):
    """
    Creates a list of Rhino.Geometry.Rectangle3d objects and associated colors from a list of cell dictionaries.
    
    Args:
        cells: A list of cell dictionaries (each from deconstruct_all_cells).
        base_plane: The Rhino.Geometry.Plane representing the wall's base plane.
    
    Returns:
        A tuple containing:
          - A list of Rhino.Geometry.Rectangle3d objects representing the cells.
          - A list of System.Drawing.Color objects (one for each cell) for visualization.
    
    Note:
        Cells of type 'WBC' (Wall Boundary Cell) are skipped to avoid overlaying duplicate geometry.
    """
    rectangles = []
    colors = []

    # Define colors for each cell type.
    # You can adjust these colors as needed.
    color_map = {
        "SC": System.Drawing.Color.FromArgb(150, 80, 175, 200),
        "SCC": System.Drawing.Color.FromArgb(150, 220, 150, 200),
        "HCC": System.Drawing.Color.FromArgb(150, 210, 210, 100)
    }

    for cell in cells:
        # Skip 'WBC' cells so they are not visualized.
        if cell.get("cell_type") == "WBC" or cell.get("cell_type") is "OC":
            continue
        
        cp = cell.get("corner_points")
        if cp is not None and isinstance(cp, list) and len(cp) == 4:
            # Create a rectangle from the cell's first and third corner points.
            rect = rg.Rectangle3d(base_plane, cp[0], cp[2])
            rectangles.append(rect)
        else:
            print("Warning: Invalid or missing corner points for cell type:", cell.get("cell_type"))
    
    return rectangles, colors

def cell_type_to_short_code(cell_type):
    mapping = {
        "wall_boundary_cell": "WBC",
        "opening_cells": "OC",
        "stud_cells": "SC",
        "sill_cripple_cells": "SCC",
        "header_cripple_cells": "HCC"
    }
    return mapping.get(cell_type, cell_type)