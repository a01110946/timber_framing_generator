# File: src/utils/data_extractor.py

import ghpythonlib.treehelpers as th
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

def extract_wall_assembly_keys(all_walls_data):
    """
    Given a list of wall data dictionaries (each containing keys for the wall,
    its openings, and its cells), this function extracts the values for a set of
    keys and returns a dictionary mapping each key to a list of values.

    The keys extracted are:
      - wall_base_curve
      - wall_base_elevation
      - wall_top_elevation
      - base_plane
      - is_exterior_wall
      - opening_type
      - opening_location_point
      - rough_width
      - rough_height
      - base_elevation_relative_to_wall_base
      - cell_type
      - u_start
      - u_end
      - v_start
      - v_end
      - corner_points

    Args:
        all_walls_data (list): A list of wall data dictionaries.

    Returns:
        dict: A dictionary where each key (as above) maps to a list of extracted values.
    """
    wall_base_curves = []
    wall_base_elevations = []
    wall_top_elevations = []
    base_planes = []
    is_exterior_walls = []

    opening_types = []
    opening_location_points = []
    rough_widths = []
    rough_heights = []
    base_elevations_relative = []

    cell_types = []
    u_starts = []
    u_ends = []
    v_starts = []
    v_ends = []
    all_corner_points = []  # each entry is typically a list of four Rhino.Point3d

    # Loop through each wall data dictionary.
    for wall in all_walls_data:
        # Extract wall-level keys.
        wall_base_curves.append(wall.get("wall_base_curve"))
        wall_base_elevations.append(wall.get("wall_base_elevation"))
        wall_top_elevations.append(wall.get("wall_top_elevation"))
        base_planes.append(wall.get("base_plane"))
        is_exterior_walls.append(wall.get("is_exterior_wall"))

        # Openings: each wall may have a list of opening dictionaries.
        openings = wall.get("openings", [])
        for op in openings:
            opening_types.append(op.get("opening_type"))
            opening_location_points.append(op.get("opening_location_point"))
            rough_widths.append(op.get("rough_width"))
            rough_heights.append(op.get("rough_height"))
            base_elevations_relative.append(op.get("base_elevation_relative_to_wall_base"))

        # Cells: each wall may have a list of cell dictionaries.
        cells = wall.get("cells", [])
        for cell in cells:
            cell_types.append(cell.get("cell_type"))
            u_starts.append(cell.get("u_start"))
            u_ends.append(cell.get("u_end"))
            v_starts.append(cell.get("v_start"))
            v_ends.append(cell.get("v_end"))
            all_corner_points.append(cell.get("corner_points"))

    return {
        "wall_base_curve": wall_base_curves,
        "wall_base_elevation": wall_base_elevations,
        "wall_top_elevation": wall_top_elevations,
        "base_plane": base_planes,
        "is_exterior_wall": is_exterior_walls,
        "opening_type": opening_types,
        "opening_location_point": opening_location_points,
        "rough_width": rough_widths,
        "rough_height": rough_heights,
        "base_elevation_relative_to_wall_base": base_elevations_relative,
        "cell_type": cell_types,
        "u_start": u_starts,
        "u_end": u_ends,
        "v_start": v_starts,
        "v_end": v_ends,
        "corner_points": all_corner_points,
    }

def convert_all_walls_data_to_nested_lists(all_walls_data):
    """
    Converts a list of wall data dictionaries into a dictionary of nested lists,
    one branch per wall, for each key. This organizes the data so that every wall
    gets its own branch in the output DataTrees.

    Expected keys per wall dictionary:
      - Wall-level keys (one value per wall):
            "wall_base_curve", "wall_base_elevation", "wall_top_elevation",
            "base_plane", "is_exterior_wall"
      - Opening keys (list per wall; may be empty if no openings):
            "opening_type", "opening_location_point", "rough_width",
            "rough_height", "base_elevation_relative_to_wall_base"
      - Cell keys (list per wall; may be empty):
            "cell_type", "u_start", "u_end", "v_start", "v_end", "corner_points"

    Returns:
        dict: A dictionary where each key maps to a nested list structured as:
              [[wall1_value(s)], [wall2_value(s)], ...]
    """
    wall_base_curves = []
    wall_base_elevations = []
    wall_top_elevations = []
    base_planes = []
    is_exterior_walls = []

    opening_types = []
    opening_location_points = []
    rough_widths = []
    rough_heights = []
    base_elevations_relative = []

    cell_types = []
    u_starts = []
    u_ends = []
    v_starts = []
    v_ends = []
    corner_points_all = []

    # Iterate through each wall data dictionary.
    for wall in all_walls_data:
        # Wall-level keys: each branch gets a single-element list.
        wall_base_curves.append([wall.get("wall_base_curve")])
        wall_base_elevations.append([wall.get("wall_base_elevation")])
        wall_top_elevations.append([wall.get("wall_top_elevation")])
        base_planes.append([wall.get("base_plane")])
        is_exterior_walls.append([wall.get("is_exterior_wall")])
        
        # Opening keys: for each wall, append the entire list (even if empty).
        openings = wall.get("openings", [])
        ot_list = []
        olp_list = []
        rw_list = []
        rh_list = []
        ber_list = []
        for op in openings:
            ot_list.append(op.get("opening_type"))
            olp_list.append(op.get("opening_location_point"))
            rw_list.append(op.get("rough_width"))
            rh_list.append(op.get("rough_height"))
            ber_list.append(op.get("base_elevation_relative_to_wall_base"))
        opening_types.append(ot_list)
        opening_location_points.append(olp_list)
        rough_widths.append(rw_list)
        rough_heights.append(rh_list)
        base_elevations_relative.append(ber_list)
        
        # Cell keys: for each wall, append the entire list of cell values.
        cells = wall.get("cells", [])
        ct_list = []
        us_list = []
        ue_list = []
        vs_list = []
        ve_list = []
        cp_list = []
        for cell in cells:
            ct_list.append(cell.get("cell_type"))
            us_list.append(cell.get("u_start"))
            ue_list.append(cell.get("u_end"))
            vs_list.append(cell.get("v_start"))
            ve_list.append(cell.get("v_end"))
            cp_list.append(cell.get("corner_points"))
        cell_types.append(ct_list)
        u_starts.append(us_list)
        u_ends.append(ue_list)
        v_starts.append(vs_list)
        v_ends.append(ve_list)
        corner_points_all.append(cp_list)
    
    return {
        "wall_base_curve": wall_base_curves,
        "wall_base_elevation": wall_base_elevations,
        "wall_top_elevation": wall_top_elevations,
        "base_plane": base_planes,
        "is_exterior_wall": is_exterior_walls,
        "opening_type": opening_types,
        "opening_location_point": opening_location_points,
        "rough_width": rough_widths,
        "rough_height": rough_heights,
        "base_elevation_relative_to_wall_base": base_elevations_relative,
        "cell_type": cell_types,
        "u_start": u_starts,
        "u_end": u_ends,
        "v_start": v_starts,
        "v_end": v_ends,
        "corner_points": corner_points_all,
    }
