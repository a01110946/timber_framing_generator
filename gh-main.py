# File: gh-main.py
"""
Main script for timber framing generation within Grasshopper.

This script is designed to be run in Python within the Grasshopper environment.
It integrates with Rhino and Revit to extract wall data, generate framing
elements, and convert the results into Grasshopper data trees.

The script handles the following main tasks:
1. Extracting data from selected Revit walls
2. Generating framing elements (studs, plates, headers, etc.)
3. Converting framing results into Grasshopper-compatible data structures

Note: This script requires the Rhino.Inside.Revit environment to function properly.

Usage:
    Place this script in a Python component within a Grasshopper definition.
    Ensure all necessary inputs (e.g., selected walls) are provided to the component.
"""

import sys
import os
import importlib
from typing import Dict, List, Any, Tuple

import Rhino
import Rhino.Geometry as rg
import ghpythonlib.treehelpers as th
from RhinoInside.Revit import Revit

# NEW CODE: Simplified path handling
project_dir = r'C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator'

# Add to sys.path if not already there
if project_dir not in sys.path:
    sys.path.append(project_dir)
    print(f"Added {project_dir} to sys.path")

# NEW CODE: Module reloading function
def reload_timber_modules():
    """Reload all timber_framing_generator modules."""
    modules_to_reload = [m for m in sys.modules.keys() 
                      if m.startswith('src.timber_framing_generator')]
    
    reload_count = 0
    for module_name in modules_to_reload:
        try:
            importlib.reload(sys.modules[module_name])
            reload_count += 1
        except Exception as e:
            print(f"Failed to reload {module_name}: {str(e)}")
    
    print(f"Reloaded {reload_count} modules")
    return reload_count

# For debugging - print the current path
print("Python path:")
for p in sys.path:
    print(f"  {p}")

# NEW CODE: First try to import modules
try:
    from src.timber_framing_generator.wall_data.wall_selector import pick_walls_from_active_view
    from src.timber_framing_generator.wall_data.revit_data_extractor import extract_wall_data_from_revit
    from src.timber_framing_generator.cell_decomposition.cell_visualizer import create_rectangles_from_cell_data
    from src.timber_framing_generator.framing_elements.plates import create_plates
    from src.timber_framing_generator.framing_elements import FramingGenerator
    print("Successfully imported all modules")
except ImportError as e:
    print(f"Import error: {str(e)}")
    print("Make sure the timber_framing_generator package is correctly installed")
    # Exit or handle the error appropriately

# NEW CODE: Reload modules if requested
if reload:
    reload_count = reload_timber_modules()
    
    # Re-import after reloading to ensure we have the latest versions
    from src.timber_framing_generator.wall_data.wall_selector import pick_walls_from_active_view
    from src.timber_framing_generator.wall_data.revit_data_extractor import extract_wall_data_from_revit
    from src.timber_framing_generator.cell_decomposition.cell_visualizer import create_rectangles_from_cell_data
    from src.timber_framing_generator.framing_elements.plates import create_plates
    from src.timber_framing_generator.framing_elements import FramingGenerator
    print(f"Re-imported all modules after reloading {reload_count} modules")

def extract_wall_data(walls) -> List[Dict[str, Any]]:
	"""
	Extract data from selected Revit walls using our data extractor.
	
	This function processes each wall to capture its geometry, properties,
	and spatial information needed for framing generation. It handles
	errors gracefully and reports issues for individual walls.
	"""
	uidoc = Revit.ActiveUIDocument
	doc = uidoc.Document
	
	all_walls_data = []
	for wall in walls:
		try:
			wall_data = extract_wall_data_from_revit(wall, doc)
			all_walls_data.append(wall_data)
			print(f"Processed wall ID: {wall.Id}")
		except Exception as e:
			print(f"Error processing wall {wall.Id}: {str(e)}")
			
	return all_walls_data

def convert_framing_to_trees(
	all_framing_results: List[Dict[str, List[rg.Brep]]],
	wall_count: int
) -> Tuple:
	"""Converts framing results into Grasshopper data trees."""
	# Initialize our nested lists
	nested_bottom_plates = []
	nested_top_plates = []
	nested_king_studs = []
	nested_headers = []
	nested_sills = []
	nested_trimmers = []
	nested_header_cripples = []
	nested_sill_cripples = []
	nested_studs = []
	nested_row_blocking = []  # New: List for row blocking

	# Add containers for cell visualization
	nested_cell_rectangles = []
	nested_opening_points = []
	
	# Add containers for debug geometry lists
	nested_debug_points = []
	nested_debug_planes = []
	nested_debug_profiles = []
	nested_debug_paths = []
	
	# Process each wall's framing results
	for wall_index in range(wall_count):
		if wall_index < len(all_framing_results):
			framing = all_framing_results[wall_index]
		
			print(f"\nProcessing wall {wall_index}:")
			cells = framing.get('cells', [])
			print(f"  Number of cells: {len(cells)}")
			
			# Get base plane - try multiple sources
			base_plane = None
			
			# 1. First try direct access from framing results
			if 'base_plane' in framing:
				base_plane = framing['base_plane']
				print("  Found base_plane in framing results")
				
			# 2. If not found, try extracting from wall_data
			elif 'wall_data' in framing and 'base_plane' in framing['wall_data']:
				base_plane = framing['wall_data']['base_plane']
				print("  Extracted base_plane from wall_data")
				
			# 3. If still not found, try deriving from bottom plate geometry
			elif 'bottom_plates' in framing and framing['bottom_plates']:
				# Get the first bottom plate
				bottom_plate = framing['bottom_plates'][0]
				if hasattr(bottom_plate, 'location_data') and 'base_plane' in bottom_plate.location_data:
					base_plane = bottom_plate.location_data['base_plane']
					print("  Derived base_plane from bottom plate location data")
			
			# Create visualization geometry if we have a base_plane
			if base_plane:
				try:
					rectangles, colors, points = create_rectangles_from_cell_data(
						cells,
						base_plane
					)
					
					print(f"  Visualization elements created:")
					print(f"    Rectangles: {len(rectangles)}")
					print(f"    Colors: {len(colors)}")
					print(f"    Points: {len(points)}")
					
					nested_cell_rectangles.append(rectangles)
					nested_opening_points.append(points)
				except Exception as e:
					print(f"  Error creating visualization: {str(e)}")
					nested_cell_rectangles.append([])
					nested_opening_points.append([])
			else:
				print("  No base_plane available for visualization")
				# Try creating a default plane based on the wall's position
				try:
					# Extract bottom plate to get wall position
					if 'bottom_plates' in framing and framing['bottom_plates']:
						bottom_plate = framing['bottom_plates'][0]
						if hasattr(bottom_plate, 'centerline') and bottom_plate.centerline:
							# Create a basic plane using the plate's centerline
							start_point = bottom_plate.centerline.PointAtStart
							end_point = bottom_plate.centerline.PointAtEnd
							
							# Define plane axes
							x_axis = rg.Vector3d(end_point - start_point)
							if x_axis.Length > 0:
								x_axis.Unitize()
								y_axis = rg.Vector3d(0, 0, 1)  # World up direction
								z_axis = rg.Vector3d.CrossProduct(x_axis, y_axis)
								z_axis.Unitize()
								y_axis = rg.Vector3d.CrossProduct(z_axis, x_axis)
								
								# Create plane
								default_plane = rg.Plane(start_point, x_axis, y_axis)
								print("  Created default plane from bottom plate centerline")
								
								# Create basic wall visualization
								rectangles, colors, points = create_rectangles_from_cell_data(
									[],  # Empty cells list
									default_plane
								)
								
								nested_cell_rectangles.append(rectangles)
								nested_opening_points.append(points)
								continue
					
					# If we couldn't create a default plane, add empty lists
					print("  Could not create default plane, using empty visualization")
					nested_cell_rectangles.append([])
					nested_opening_points.append([])
				except Exception as e:
					print(f"  Error creating default plane: {str(e)}")
					nested_cell_rectangles.append([])
					nested_opening_points.append([])
			
			# Get bottom plates for this wall
			wall_bottom_plates = []
			for plate in framing.get('bottom_plates', []):
				try:
					geometry_data = plate.get_geometry_data(platform="rhino")
					wall_bottom_plates.append(geometry_data['platform_geometry'])
				except Exception as e:
					print(f"  Error extracting bottom plate geometry: {str(e)}")
			nested_bottom_plates.append(wall_bottom_plates)
			
			# Get top plates for this wall
			wall_top_plates = []
			for plate in framing.get('top_plates', []):
				try:
					geometry_data = plate.get_geometry_data(platform="rhino")
					wall_top_plates.append(geometry_data['platform_geometry'])
				except Exception as e:
					print(f"  Error extracting top plate geometry: {str(e)}")
			nested_top_plates.append(wall_top_plates)
			
			# Get king studs for this wall
			wall_king_studs = framing.get('king_studs', [])
			nested_king_studs.append(wall_king_studs)
			
			# Get headers for this wall
			wall_headers = framing.get('headers', [])
			nested_headers.append(wall_headers)
			
			# Get sills for this wall
			wall_sills = framing.get('sills', [])
			nested_sills.append(wall_sills)
			
			# Get trimmers for this wall
			wall_trimmers = framing.get('trimmers', [])
			nested_trimmers.append(wall_trimmers)

			# Get header cripples for this wall
			wall_header_cripples = framing.get('header_cripples', [])
			nested_header_cripples.append(wall_header_cripples)

			# Get header cripples for this wall
			wall_sill_cripples = framing.get('sill_cripples', [])
			nested_sill_cripples.append(wall_sill_cripples)

			# Get studs for this wall
			wall_studs = framing.get('studs', [])
			nested_studs.append(wall_studs)
			
			# Get row blocking for this wall
			wall_row_blocking = framing.get('row_blocking', [])
			nested_row_blocking.append(wall_row_blocking)

			# Get debug geometry for this wall
			debug_geom = framing.get('debug_geometry', {})
			
			# Extract each type of debug geometry
			nested_debug_points.append(debug_geom.get('points', []))
			nested_debug_planes.append(debug_geom.get('planes', []))
			nested_debug_profiles.append(debug_geom.get('profiles', []))
			nested_debug_paths.append(debug_geom.get('paths', []))
			
			print(f"\nWall {wall_index} debug geometry:")
			print(f"  Points: {len(debug_geom.get('points', []))}")
			print(f"  Planes: {len(debug_geom.get('planes', []))}")
			print(f"  Profiles: {len(debug_geom.get('profiles', []))}")
			print(f"  Paths: {len(debug_geom.get('paths', []))}")
			
		else:
			# Add empty lists for walls that failed processing
			nested_bottom_plates.append([])
			nested_top_plates.append([])
			nested_king_studs.append([])
			nested_headers.append([])
			nested_sills.append([])
			nested_trimmers.append([])
			nested_header_cripples.append([])
			nested_sill_cripples.append([])
			nested_studs.append([])
			nested_row_blocking.append([])  # Add empty row blocking list
			nested_cell_rectangles.append([])
			nested_opening_points.append([])
			nested_debug_points.append([])
			nested_debug_planes.append([])
			nested_debug_profiles.append([])
			nested_debug_paths.append([])
	
	# Convert all nested lists to trees
	bottom_plates_tree = th.list_to_tree(nested_bottom_plates, source=[0])
	top_plates_tree = th.list_to_tree(nested_top_plates, source=[0])
	king_studs_tree = th.list_to_tree(nested_king_studs, source=[0])
	headers_tree = th.list_to_tree(nested_headers, source=[0])
	sills_tree = th.list_to_tree(nested_sills, source=[0])
	trimmers_tree = th.list_to_tree(nested_trimmers, source=[0])
	header_cripples_tree = th.list_to_tree(nested_header_cripples, source=[0])
	sill_cripples_tree = th.list_to_tree(nested_sill_cripples, source=[0])
	studs_tree = th.list_to_tree(nested_studs, source=[0])
	row_blocking_tree = th.list_to_tree(nested_row_blocking, source=[0])  # Convert row blocking to tree
	cell_rectangles_tree = th.list_to_tree(nested_cell_rectangles, source=[0])
	opening_points_tree = th.list_to_tree(nested_opening_points, source=[0])
	debug_points_tree = th.list_to_tree(nested_debug_points, source=[0])
	debug_planes_tree = th.list_to_tree(nested_debug_planes, source=[0])
	debug_profiles_tree = th.list_to_tree(nested_debug_profiles, source=[0])
	debug_paths_tree = th.list_to_tree(nested_debug_paths, source=[0])
	
	# Print detailed tree statistics
	print("\nDetailed tree statistics:")
	print(f"Bottom plates: {sum(len(x) for x in nested_bottom_plates)} items in {len(nested_bottom_plates)} branches")
	print(f"Top plates: {sum(len(x) for x in nested_top_plates)} items in {len(nested_top_plates)} branches")
	print(f"King studs: {sum(len(x) for x in nested_king_studs)} items in {len(nested_king_studs)} branches")
	print(f"Headers: {sum(len(x) for x in nested_headers)} items in {len(nested_headers)} branches")
	print(f"Sills: {sum(len(x) for x in nested_sills)} items in {len(nested_sills)} branches")
	print(f"Trimmers: {sum(len(x) for x in nested_trimmers)} items in {len(nested_trimmers)} branches")
	print(f"Header cripples: {sum(len(x) for x in nested_header_cripples)} items in {len(nested_header_cripples)} branches")
	print(f"Sill cripples: {sum(len(x) for x in nested_sill_cripples)} items in {len(nested_sill_cripples)} branches")
	print(f"Studs: {sum(len(x) for x in nested_studs)} items in {len(nested_studs)} branches")
	print(f"Row blocking: {sum(len(x) for x in nested_row_blocking)} items in {len(nested_row_blocking)} branches")  # Add row blocking stats
	print(f"Cell rectangles: {sum(len(x) for x in nested_cell_rectangles)} items in {len(nested_cell_rectangles)} branches")
	print(f"Opening points: {sum(len(x) for x in nested_opening_points)} items in {len(nested_opening_points)} branches")
	print(f"Debug points: {sum(len(x) for x in nested_debug_points)} items in {len(nested_debug_points)} branches")
	print(f"Debug planes: {sum(len(x) for x in nested_debug_planes)} items in {len(nested_debug_planes)} branches")
	print(f"Debug profiles: {sum(len(x) for x in nested_debug_profiles)} items in {len(nested_debug_profiles)} branches")
	print(f"Debug paths: {sum(len(x) for x in nested_debug_paths)} items in {len(nested_debug_paths)} branches")
	
	return (bottom_plates_tree, top_plates_tree, king_studs_tree, headers_tree, sills_tree, trimmers_tree,
			header_cripples_tree, sill_cripples_tree, studs_tree, row_blocking_tree,
			debug_points_tree, debug_planes_tree, debug_profiles_tree, debug_paths_tree,
			cell_rectangles_tree, opening_points_tree)

def generate_wall_plates(wall_data):
	"""
	Generate bottom and top plates for a wall.
	
	This function creates the actual plate geometry based on the wall data,
	handling both single-layer bottom plates and double-layer top plates.
	"""
	# Create bottom plates (single layer)
	bottom_plates = create_plates(
		wall_data=wall_data,
		plate_type="bottom_plate",
		representation_type="schematic",
		layers=1
	)
	
	# Create top plates (double layer)
	top_plates = create_plates(
		wall_data=wall_data,
		plate_type="top_plate",
		representation_type="schematic",
		layers=2
	)
	
	# Get the actual geometry
	bottom_plate_geometry = []
	top_plate_geometry = []
	
	for plate in bottom_plates:
		geometry_data = plate.get_geometry_data(platform="rhino")
		bottom_plate_geometry.append(geometry_data['platform_geometry'])
		
	for plate in top_plates:
		geometry_data = plate.get_geometry_data(platform="rhino")
		top_plate_geometry.append(geometry_data['platform_geometry'])
		
	return bottom_plate_geometry, top_plate_geometry

# Main execution for the Grasshopper component
def main():
	"""Main execution for the Grasshopper component."""
	if run:
		
		# Extract wall data
		wall_dict = extract_wall_data(walls)
		wall_count = len(wall_dict)
		print(f"\nProcessing {wall_count} walls")
		
		# Define our configuration
		framing_config = {
			'representation_type': "schematic",
			'bottom_plate_layers': 1,
			'top_plate_layers': 2,
			'include_blocking': True,
			'block_spacing': 48.0/12.0,  # 4ft default
			'first_block_height': 24.0/12.0,  # 2ft default
			'blocking_pattern': "staggered"  # Options: "inline" or "staggered"
		}
		
		# Process each wall and store results
		all_framing_results = []
		
		for i, wall_data in enumerate(wall_dict):
			try:
				print(f"\nProcessing wall {i+1} of {wall_count}")
				generator = FramingGenerator(
					wall_data=wall_data,
					framing_config=framing_config
				)
				
				framing = generator.generate_framing()
				all_framing_results.append(framing)

				print(f"Wall data diagnostic for wall {i+1}:")
				print(f"  base_plane: {wall_data.get('base_plane') is not None}")
				print(f"  wall_base_curve: {wall_data.get('wall_base_curve') is not None}")
				print(f"  wall_base_elevation: {wall_data.get('wall_base_elevation')}")
				print(f"  wall_top_elevation: {wall_data.get('wall_top_elevation')}")
				
				print(f"Wall {i+1} results:")
				print(f"- Bottom plates: {len(framing.get('bottom_plates', []))}")
				print(f"- Top plates: {len(framing.get('top_plates', []))}")
				print(f"- King studs: {len(framing.get('king_studs', []))}")
				print(f"- Headers: {len(framing.get('headers', []))}")
				print(f"- Sills: {len(framing.get('sills', []))}")
				print(f"- Trimmers: {len(framing.get('trimmers', []))}")
				print(f"- Header cripples: {len(framing.get('header_cripples', []))}")
				print(f"- Sill cripples: {len(framing.get('sill_cripples', []))}")
				print(f"- Studs: {len(framing.get('studs', []))}")
				
			except Exception as e:
				print(f"Error processing wall {i+1}: {str(e)}")
				import traceback
				print(traceback.format_exc())
				continue
		
		print("\nConverting results to trees...")
		
		# Get all trees from conversion function
		(bottom_plates_tree, 
		 top_plates_tree, 
		 king_studs_tree,
		 headers_tree,
		 sills_tree,
		 trimmers_tree,
		 header_cripples_tree,
		 sill_cripples_tree,
		 studs_tree,
		 row_blocking_tree,
		 debug_points_tree,
		 debug_planes_tree,
		 debug_profiles_tree,
		 debug_paths_tree,
		 cell_rectangles_tree,
		 opening_points_tree) = convert_framing_to_trees(
			all_framing_results,
			wall_count
		)
		
		print("\nFinal tree statistics:")
		print(f"Bottom plates tree branch count: {bottom_plates_tree.BranchCount}")
		print(f"Top plates tree branch count: {top_plates_tree.BranchCount}")
		print(f"King studs tree branch count: {king_studs_tree.BranchCount}")
		print(f"Headers tree branch count: {headers_tree.BranchCount}")
		print(f"Sills tree branch count: {sills_tree.BranchCount}")
		print(f"Trimmers tree branch count: {trimmers_tree.BranchCount}")
		print(f"Header cripples tree branch count: {header_cripples_tree.BranchCount}")
		print(f"Sill cripples tree branch count: {sill_cripples_tree.BranchCount}")
		print(f"Studs tree branch count: {studs_tree.BranchCount}")
		print(f"Row blocking tree branch count: {row_blocking_tree.BranchCount}")
		print(f"Debug points tree branch count: {debug_points_tree.BranchCount}")
		print(f"Debug planes tree branch count: {debug_planes_tree.BranchCount}")
		print(f"Debug profiles tree branch count: {debug_profiles_tree.BranchCount}")
		print(f"Debug paths tree branch count: {debug_paths_tree.BranchCount}")
		
		# Assign all outputs
		a = bottom_plates_tree
		b = top_plates_tree
		c = king_studs_tree
		d = debug_points_tree
		e = debug_planes_tree
		f = debug_profiles_tree
		g = debug_paths_tree
		h = cell_rectangles_tree
		i = opening_points_tree
		j = headers_tree
		k = sills_tree
		l = trimmers_tree
		m = header_cripples_tree
		n = sill_cripples_tree
		o = studs_tree
		p = row_blocking_tree
	else:
		# Initialize all outputs as None when not running
		a = b = c = d = e = f = g = h = i = j = k = l = m = n = o = p = None
		
	return a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p

# Execute main function and assign outputs
a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p = main()

print(f'This is the item count for DataTree "a": {a.DataCount}')
print(f'This is the item count for DataTree "b": {b.DataCount}')
print(f'This is the item count for DataTree "c": {c.DataCount}')
print(f'This is the item count for DataTree "d": {d.DataCount}')
print(f'This is the item count for DataTree "e": {e.DataCount}')
print(f'This is the item count for DataTree "f": {f.DataCount}')
print(f'This is the item count for DataTree "g": {g.DataCount}')
print(f'This is the item count for DataTree "h": {h.DataCount}')
print(f'This is the item count for DataTree "i": {i.DataCount}')
print(f'This is the item count for DataTree "j": {j.DataCount}')
print(f'This is the item count for DataTree "k": {k.DataCount}')
print(f'This is the item count for DataTree "l": {l.DataCount}')
print(f'This is the item count for DataTree "m": {m.DataCount}')
print(f'This is the item count for DataTree "n": {n.DataCount}')
print(f'This is the item count for DataTree "o": {o.DataCount}')
print(f'This is the item count for DataTree "p": {p.DataCount}')