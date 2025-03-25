# File: timber_framing_generator/main.py

import sys

# Development mode flag
DEV_MODE = True

if DEV_MODE:
    # Get project root directory
    project_root = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

    # Import and use the development utilities
    sys.path.append(project_root)
    from src.timber_framing_generator.dev_utils.reload_modules import (
        clear_module_cache,
        reload_project_modules,
    )

    # Clear cache and reload modules
    clear_module_cache(project_root)
    reload_project_modules(project_root)

# Now import using relative paths from within timber_framing_generator
from src.timber_framing_generator.wall_data.wall_selector import pick_walls_from_active_view
from src.timber_framing_generator.wall_data.revit_data_extractor import (
    extract_wall_data_from_revit,
)
from src.timber_framing_generator.utils.data_extractor import (
    extract_wall_assembly_keys,
    convert_all_walls_data_to_nested_lists,
)
from src.timber_framing_generator.cell_decomposition.cell_visualizer import (
    create_rectangles_from_cell_data,
)
from src.timber_framing_generator.framing_elements.plates import create_plates
from tests.framing_elements.test_plates import TestPlateSystem
from src.timber_framing_generator.framing_elements.studs import (
    calculate_stud_locations,
    generate_stud,
)

# The rest of your imports
import ghpythonlib.treehelpers as th
import ghpythonlib.components as ghcomp
import Grasshopper as gh
import ghpythonlib.components as ghcomp
from RhinoInside.Revit import Revit

walls = walls

def grasshopper_entry_point(walls, run=False):
    """
    Entry point for Grasshopper execution.
    
    Args:
        walls: Revit wall elements from Grasshopper/Revit
        run: Boolean parameter from Grasshopper to trigger execution
    
    Returns:
        Various outputs for Grasshopper visualization
    """
    if not run:
        return None

def main(walls):
    uidoc = Revit.ActiveUIDocument
    doc = uidoc.Document

    # Prompt the user to select walls in the active view.
    # walls = pick_walls_from_active_view()
    print("Selected {} walls from the active view.".format(len(walls)))

    all_walls_data = []
    for wall in walls:
        try:
            wall_data = extract_wall_data_from_revit(wall, doc)
            all_walls_data.append(wall_data)
            print("Processed wall ID: {}".format(wall.Id))
        except Exception as e:
            print("Error processing wall {}: {}".format(wall.Id, e))

    # For demonstration, print a summary of the first wall data if available.
    if all_walls_data:
        first_wall = all_walls_data[40]
        # print("First wall data summary:")
        # for key, value in first_wall.items():
        # print("  {}: {}".format(key, value))
    else:
        print("No wall data extracted.")

    return all_walls_data


# --- Grasshopper component execution ---
# Assume 'run' is a Boolean input from Grasshopper that triggers execution.
# You can also have output parameters to pass on the extracted wall data.
if run:
    wall_dict = main(walls)

    # Create a plate system tester
    plate_tester = TestPlateSystem(debug=True)

    # Test the plate system
    test_wall = wall_dict

    # Run the tests
    test_results = plate_tester.test_complete_system(
        test_wall, platform="rhino", representation_type="schematic"
    )
    print(f"These are the test results: {test_results}")

    # Create plates for each wall
    all_plates = []
    all_base_curves = []

    for wall_index, wall_data in enumerate(wall_dict):
        try:
            # Extract the wall base curve for reference
            if "wall_base_curve" in wall_data:
                all_base_curves.append(wall_data["wall_base_curve"])

            # Create plates using the wall data directly
            bottom_plates = create_plates(
                wall_data=wall_data,
                plate_type="bottom_plate",
                representation_type="schematic",
                layers=2,
            )

            top_plates = create_plates(
                wall_data=wall_data,
                plate_type="top_plate",
                representation_type="schematic",
                layers=2,
            )

            all_plates.extend(bottom_plates)
            all_plates.extend(top_plates)

            # Store the created plates in the test results
            test_results[str(wall_index)] = {"plates": bottom_plates + top_plates}

        except Exception as e:
            print(f"Error creating plates for wall {wall_index}: {str(e)}")
            continue

    # Get visualization geometry
    centerlines = plate_tester.get_visualization_geometry(
        geometry_type="centerline", platform="rhino"
    )
    solids = plate_tester.get_visualization_geometry(
        geometry_type="platform_geometry", platform="rhino"
    )

    # Convert to Grasshopper trees
    plates_centerlines = th.list_to_tree(centerlines, source=[0])
    plates_solids = th.list_to_tree(solids, source=[0])
    base_curves_tree = th.list_to_tree(all_base_curves, source=[0])

    # Convert the list of wall dictionaries into nested lists (one branch per wall)
    nested_data = convert_all_walls_data_to_nested_lists(wall_dict)

    # Convert each key's nested list to a DataTree.
    wall_curve = th.list_to_tree(nested_data["wall_base_curve"], source=[0])
    base_elevation = th.list_to_tree(nested_data["wall_base_elevation"], source=[0])
    top_elevation = th.list_to_tree(nested_data["wall_top_elevation"], source=[0])
    base_plane = th.list_to_tree(nested_data["base_plane"], source=[0])
    is_exterior_wall = th.list_to_tree(nested_data["is_exterior_wall"], source=[0])
    opening_type = th.list_to_tree(nested_data["opening_type"], source=[0])
    opening_location_point = th.list_to_tree(
        nested_data["opening_location_point"], source=[0]
    )
    rough_width = th.list_to_tree(nested_data["rough_width"], source=[0])
    rough_height = th.list_to_tree(nested_data["rough_height"], source=[0])
    base_elevation_relative_to_wall_base = th.list_to_tree(
        nested_data["base_elevation_relative_to_wall_base"], source=[0]
    )
    cell_type = th.list_to_tree(nested_data["cell_type"], source=[0])
    u_start = th.list_to_tree(nested_data["u_start"], source=[0])
    u_end = th.list_to_tree(nested_data["u_end"], source=[0])
    v_start = th.list_to_tree(nested_data["v_start"], source=[0])
    v_end = th.list_to_tree(nested_data["v_end"], source=[0])
    corner_points = th.list_to_tree(nested_data["corner_points"], source=[0])
else:
    A = None


# print(wall_dict[51])
# --- New Step: Visualize the Cells (excluding WBC cells) ---
all_rectangles = []
all_colors = []
# Loop through each wall and generate cell rectangles.
for wall in wall_dict:
    base_plane = wall.get("base_plane")
    cells = wall.get("cells", [])
    # The create_rectangles_from_cell_data function is set up to skip 'WBC' cells.
    rects, colors = create_rectangles_from_cell_data(cells, base_plane)
    all_rectangles.extend(rects)
    all_colors.extend(colors)

# Convert the visualization lists into DataTrees.
rectangles_crv = th.list_to_tree(all_rectangles, source=[0])
rectangles_srf = ghcomp.BoundarySurfaces(rectangles_crv)

# top_plate_location = calculate_plate_locations(wall_dict[40], plate_type="top_plate")
# bottom_plate_location = calculate_plate_locations(wall_dict[40], plate_type="bottom_plate")
# top_plates_40 = generate_plate(top_plate_location, profile="2x4")
# print(wall_dict[51])
# top_plates_40_line = top_plates_40['base_geometry']
