# File: timber_framing_generator/cell_decomposition/cell_visualizer.py

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
        For walls without cells, a basic wall outline is created for visualization.
    """
    rectangles = []
    colors = []
    opening_points = []

    # First, let's understand what cells we're receiving
    print("\nCell Visualization Analysis:")
    print(f"Total cells received: {len(cells)}")
    
    # For better debugging, print a warning if we receive no cells
    if not cells:
        print("WARNING: No cells provided for visualization - creating basic wall outline instead")
        
        # Create a basic wall outline if we have a valid base_plane
        if base_plane:
            try:
                # Use reasonable defaults for wall dimensions
                wall_width = 10.0  # Default width in feet
                wall_height = 8.0  # Default height in feet
                
                print(f"Creating wall outline with dimensions {wall_width}' x {wall_height}'")
                
                # Create rectangle for wall outline using intervals
                try:
                    wall_rect = rg.Rectangle3d(
                        base_plane,
                        rg.Interval(0, wall_width),
                        rg.Interval(0, wall_height)
                    )
                    
                    rectangles.append(wall_rect)
                    colors.append(System.Drawing.Color.FromArgb(80, 150, 150, 150))  # Semi-transparent gray
                    
                    print(f"Successfully created wall outline rectangle")
                except Exception as e:
                    print(f"Error creating rectangle: {str(e)}")
            except Exception as e:
                print(f"Error creating wall outline: {str(e)}")
        else:
            print("Cannot create wall outline: base_plane is None")
            
        return rectangles, colors, opening_points
    
    # Count each cell type and log cell structure details
    cell_types = {}
    for i, cell in enumerate(cells):
        cell_type = cell.get("cell_type")
        cell_types[cell_type] = cell_types.get(cell_type, 0) + 1
        
        # For opening cells, print more details
        if cell_type == "OC":  # Opening Cell
            print(f"  Opening cell {i+1}: u={cell.get('u_start'):.3f}-{cell.get('u_end'):.3f}, v={cell.get('v_start'):.3f}-{cell.get('v_end'):.3f}")
            if 'corner_points' in cell:
                print(f"  Has corner points: {len(cell['corner_points']) if cell['corner_points'] else 0}")
            else:
                print("  No corner points found!")
    
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
            u_end = cell.get("u_end")
            v_end = cell.get("v_end")
            print(f"  Opening location: u={u_start:.3f}-{u_end:.3f}, v={v_start:.3f}-{v_end:.3f}")
            print(f"  Opening dimensions: width={u_end-u_start:.3f}, height={v_end-v_start:.3f}")
            
            # Create opening point at the bottom-left corner
            if base_plane:
                opening_point = base_plane.PointAt(u_start, v_start, 0)
                opening_points.append(opening_point)
                print(f"  Added opening point at ({opening_point.X:.3f}, {opening_point.Y:.3f}, {opening_point.Z:.3f})")
            else:
                print("  Warning: base_plane is None, cannot create opening point")
            
        # Create rectangle for visualization
        cp = cell.get("corner_points")
        if cp is not None and isinstance(cp, list) and len(cp) == 4:
            try:
                # Print corner point coordinates for debugging
                print("  Corner points:")
                for i, point in enumerate(cp):
                    print(f"    Point {i}: ({point.X:.3f}, {point.Y:.3f}, {point.Z:.3f})")
                
                # Create rectangle only if base_plane is valid
                if base_plane:
                    rect = rg.Rectangle3d(base_plane, cp[0], cp[2])
                    rectangles.append(rect)
                    colors.append(color_map.get(cell_type, System.Drawing.Color.Gray))
                    print("  Added rectangle and color")
                else:
                    print("  Warning: base_plane is None, cannot create rectangle")
            except Exception as e:
                print(f"  Error creating rectangle: {str(e)}")
        else:
            print(f"  Warning: Invalid corner points: {cp}")
            if cp is None:
                print("  corner_points is None")
            elif not isinstance(cp, list):
                print(f"  corner_points is not a list, but a {type(cp)}")
            elif len(cp) != 4:
                print(f"  corner_points has {len(cp)} points instead of 4")

    print("\nVisualization Results:")
    print(f"Created {len(rectangles)} rectangles")
    print(f"Created {len(colors)} colors")
    print(f"Created {len(opening_points)} opening points")

    return rectangles, colors, opening_points