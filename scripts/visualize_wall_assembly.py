# File: scripts/visualize_wall_assembly.py

#!/usr/bin/env python
"""
A simple script to load wall data, generate framing cells, and visualize the assembly in Rhino.
"""

from wall_data.revit_data_extractor import extract_wall_data_from_revit
from cell_decomposition.cell_visualizer import create_rectangles_from_cell_data
from config import DEBUG
import Rhino.Geometry as rg

# For example purposes, assume my_revit_walls is provided (e.g., from Revit)
my_revit_walls = []  # Replace with your list of Revit wall elements
doc = None         # Replace with your active Revit document reference

all_rectangles = []
all_colors = []

# Process each wall.
for wall in my_revit_walls:
    wall_data = extract_wall_data_from_revit(wall, doc)
    base_plane = wall_data["base_plane"]
    cells = wall_data["cells"]
    rects, colors = create_rectangles_from_cell_data(cells, base_plane)
    all_rectangles.extend(rects)
    all_colors.extend(colors)

if DEBUG:
    print("Generated", len(all_rectangles), "rectangles for visualization.")
    
# Now, pass all_rectangles and all_colors to your Rhino display components.
