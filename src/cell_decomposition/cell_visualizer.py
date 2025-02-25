# File: src/cell_decomposition/cell_visualizer.py

import Rhino.Geometry as rg
import System.Drawing


def create_rectangles_from_cell_data(cells, base_plane):
    """
    Creates visualization geometry for cells, including opening locations.
    
    This function generates visual elements to help understand the cell decomposition:
    - Rectangles representing different cell types (SC, SCC, HCC)
    - Opening location points to verify cell positioning
    - Cell boundaries to confirm proper spacing
    
    Args:
        cells: A list of cell dictionaries from decompose_wall_to_cells()
        base_plane: The Rhino.Geometry.Plane representing the wall's base plane.
    
    Returns:
        A tuple containing:
        - List[rg.Rectangle3d]: Cell boundary rectangles
        - List[System.Drawing.Color]: Colors for the rectangles
        - List[rg.Point3d]: Opening location points
    
    Note:
        Cells of type 'WBC' (Wall Boundary Cell) are skipped to avoid overlaying duplicate geometry.
    """
    rectangles = []
    colors = []
    opening_points = []

    # First, let's understand what cells we're receiving
    print("\nCell Visualization Analysis:")
    print(f"Total cells received: {len(cells)}")
    
    # Count each cell type
    cell_types = {}
    for cell in cells:
        cell_type = cell.get("cell_type")
        cell_types[cell_type] = cell_types.get(cell_type, 0) + 1
    print("Cell type breakdown:")
    for cell_type, count in cell_types.items():
        print(f"  {cell_type}: {count} cells")

    # Define visualization colors
    color_map = {
        "SC": System.Drawing.Color.FromArgb(150, 80, 175, 200),    # Blue for studs
        "SCC": System.Drawing.Color.FromArgb(150, 220, 150, 200),  # Green for sill cripples
        "HCC": System.Drawing.Color.FromArgb(150, 210, 210, 100),  # Yellow for header cripples
        "OC": System.Drawing.Color.FromArgb(150, 255, 100, 100)    # Red for openings
    }

    for cell in cells:
        cell_type = cell.get("cell_type")
        
        # Skip WBC cells
        if cell_type == "WBC":
            continue
            
        print(f"\nProcessing {cell_type} cell:")
        
        # Process opening cells for points
        if cell_type == "OC":
            u_start = cell.get("u_start")
            v_start = cell.get("v_start")
            print(f"  Opening location: u={u_start}, v={v_start}")
            
            opening_point = base_plane.PointAt(u_start, v_start, 0)
            opening_points.append(opening_point)
            print("  Added opening point")
            
        # Create rectangle for visualization
        cp = cell.get("corner_points")
        if cp is not None and isinstance(cp, list) and len(cp) == 4:
            rect = rg.Rectangle3d(base_plane, cp[0], cp[2])
            rectangles.append(rect)
            colors.append(color_map.get(cell_type, System.Drawing.Color.Gray))
            print("  Added rectangle and color")
        else:
            print("  Warning: Invalid corner points")

    print("\nVisualization Results:")
    print(f"Created {len(rectangles)} rectangles")
    print(f"Created {len(colors)} colors")
    print(f"Created {len(opening_points)} opening points")

    return rectangles, colors, opening_points

def cell_type_to_short_code(cell_type):
    mapping = {
        "wall_boundary_cell": "WBC",
        "opening_cells": "OC",
        "stud_cells": "SC",
        "sill_cripple_cells": "SCC",
        "header_cripple_cells": "HCC"
    }
    return mapping.get(cell_type, cell_type)