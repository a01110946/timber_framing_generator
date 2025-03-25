# File: timber_framing_generator/framing_elements/row_blocking.py

"""
Row blocking generation for timber framing.

Row blocking (also called "solid blocking") refers to horizontal framing members 
installed between vertical studs to provide lateral support, prevent stud rotation/twisting, 
add structural rigidity, and provide nailing surfaces for wall finishes.

This module handles the calculation and creation of row blocking geometry based on
cell decomposition and stud positions.
"""

import sys
from typing import Dict, List, Any, Optional, Tuple
import math
import Rhino.Geometry as rg

from src.timber_framing_generator.config.framing import (
    FRAMING_PARAMS, 
    PROFILES,
    BlockingPattern,
    get_profile_for_wall_type
)
from src.timber_framing_generator.framing_elements.blocking_parameters import (
    BlockingParameters,
    BlockingLayerConfig
)


class RowBlockingGenerator:
    """
    Generates row blocking elements between studs based on cell decomposition.
    
    Row blocking consists of horizontal members installed between studs to provide
    lateral support and prevent stud rotation. This class uses the cell system to
    properly place blocking elements within appropriate spatial boundaries.
    
    Attributes:
        wall_data: Dictionary with wall information including cells
        stud_positions: Dictionary of stud positions by cell type
        blocking_params: Parameters for blocking configuration
        debug_geometry: Storage for debug visualization
    """
    
    def __init__(
        self, 
        wall_data: Dict[str, Any], 
        studs: Optional[List[Any]] = None, 
        king_studs: Optional[List[Any]] = None, 
        trimmers: Optional[List[Any]] = None,
        header_cripples: Optional[List[Any]] = None,
        sill_cripples: Optional[List[Any]] = None,
        blocking_pattern: Optional[str] = None,
        include_blocking: Optional[bool] = None,
        block_spacing: Optional[float] = None,
        first_block_height: Optional[float] = None
    ) -> None:
        """
        Initialize the row blocking generator.
        
        Args:
            wall_data: Dictionary containing wall configuration data
            studs: List of standard studs
            king_studs: List of king studs
            trimmers: List of trimmer studs
            header_cripples: List of header cripple studs
            sill_cripples: List of sill cripple studs
            blocking_pattern: Pattern for blocking (inline, staggered, etc.)
            include_blocking: Flag to enable/disable blocking
            block_spacing: Spacing between blocks in feet
            first_block_height: Height of first block row in feet
        """
        self.wall_data = wall_data
        self.wall_base_elevation = wall_data.get("wall_base_elevation", 0)
        self.wall_top_elevation = wall_data.get("wall_top_elevation", 0)
        
        # Store the provided framing elements
        self.studs = studs or []
        self.king_studs = king_studs or []
        self.trimmers = trimmers or []
        self.header_cripples = header_cripples or []
        self.sill_cripples = sill_cripples or []
        
        # Initialize blocking parameters
        self.blocking_params = BlockingParameters()
        
        # Explicitly handle blocking pattern conversion
        if blocking_pattern is not None:
            if isinstance(blocking_pattern, str):
                print(f"Row blocking received pattern: {blocking_pattern}, type: {type(blocking_pattern)}")
                
                pattern_str = blocking_pattern.upper().strip()
                if pattern_str == "STAGGERED":
                    self.blocking_params.pattern = BlockingPattern.STAGGERED
                    print(f"Explicitly set pattern to STAGGERED")
                else:
                    self.blocking_params.pattern = BlockingPattern.INLINE
                    print(f"Explicitly set pattern to INLINE")
            else:
                self.blocking_params.pattern = blocking_pattern
        
        # Override specific parameters if provided
        if include_blocking is not None:
            self.blocking_params.include_blocking = include_blocking
            print(f"Set blocking param include_blocking = {include_blocking}")
            
        if block_spacing is not None:
            self.blocking_params.block_spacing = block_spacing
            print(f"Set blocking param block_spacing = {block_spacing}")
            
        if first_block_height is not None:
            self.blocking_params.first_block_height = first_block_height
            print(f"Set blocking param first_block_height = {first_block_height}")
        
        # Initialize stud positions dictionary
        self.stud_positions = {}
        
        # Get wall and block profiles
        self.wall_profile = get_profile_for_wall_type(wall_data.get("wall_type", "2x4"))
        self.block_profile_name = self.blocking_params.get_block_profile(self.wall_profile.name)
        self.block_profile = PROFILES.get(self.block_profile_name, self.wall_profile)
        
        # Try to get blocking height thresholds from config, otherwise use defaults
        self.blocking_height_threshold_1 = FRAMING_PARAMS.get("blocking_row_height_threshold_1", 48/12)  # 48 inches in feet
        self.blocking_height_threshold_2 = FRAMING_PARAMS.get("blocking_row_height_threshold_2", 96/12)  # 96 inches in feet
        
        # Calculate minimum cell height for blocking from profile or default
        try:
            dims = self.block_profile.get_dimensions()
            self.blocking_min_height = dims["width"] * 3  # Use block width (vertical dimension) * 3
        except (AttributeError, KeyError):
            # Default to 3x nominal width of framing (e.g., 4.5" for 2x4)
            self.blocking_min_height = 4.5/12 * 3  # 13.5 inches in feet
            
        # Storage for debug geometry
        self.debug_geometry = {
            "points": [],
            "planes": [],
            "profiles": [],
            "paths": []
        }
        
    def set_stud_positions(self, stud_positions: Dict[str, List[float]]) -> None:
        """
        Set or update the stud positions by cell type.
        
        Args:
            stud_positions: Dictionary mapping cell IDs to stud position lists
        """
        if stud_positions is not None:
            self.stud_positions = stud_positions
            print(f"Updated stud positions: cells={len(self.stud_positions.keys())}")
            for cell_id, positions in self.stud_positions.items():
                print(f"  Cell {cell_id}: {len(positions)} studs")
        else:
            print("Warning: No stud position data provided")
            self.stud_positions = {}
    
    def generate_blocking(self) -> List[rg.Brep]:
        """
        Generate row blocking elements for a wall based on cell decomposition.
        
        Returns:
            List of Brep geometries representing blocking elements
        """
        print("\n===== ROW BLOCKING DIAGNOSTIC INFO =====")
        print(f"Include blocking flag: {self.blocking_params.include_blocking}")
        print(f"Wall height: {self.wall_top_elevation - self.wall_base_elevation}")
        print(f"Wall elevations: base={self.wall_base_elevation}, top={self.wall_top_elevation}")
    
        # Skip if blocking is disabled
        if not self.blocking_params.include_blocking:
            print("Blocking is disabled, skipping generation")
            return []
        
        # Get wall cells
        cells = self.wall_data.get("cells", [])
        if not cells:
            print("No cells found in wall data, cannot generate blocking")
            return []
            
        # Get base plane for coordinate transformations
        base_plane = self.wall_data.get("base_plane")
        if not base_plane:
            print("Missing wall base plane, cannot generate blocking")
            return []
        
        # Get dimensions for stud width adjustment
        try:
            dims = self.block_profile.get_dimensions()
            block_width = dims["width"]  # Vertical dimension (usually 1.5" for 2x4)
            block_thickness = dims["thickness"]  # Horizontal dimension (usually 3.5" for 2x4)
            print(f"Block profile dimensions: {dims}")
        except (AttributeError, KeyError) as e:
            # Fallback to direct attributes if get_dimensions not available
            print(f"Using direct profile attributes - get_dimensions failed: {str(e)}")
            try:
                # Try nominal_width/nominal_depth
                block_width = self.block_profile.nominal_width
                block_thickness = self.block_profile.nominal_depth
            except AttributeError:
                # Last resort - try width/depth directly
                try:
                    block_width = self.block_profile.width
                    block_thickness = self.block_profile.depth
                except AttributeError:
                    # Default to 3x nominal width of framing (e.g., 4.5" for 2x4)
                    print("WARNING: Could not determine block dimensions, using defaults for 2x4")
                    block_width = 1.5 / 12.0  # 1.5 inches in feet
                    block_thickness = 3.5 / 12.0  # 3.5 inches in feet
                    
        print(f"Block profile: {self.block_profile_name}, width: {block_width}, thickness: {block_thickness}")
        
        # Get stud width for adjusting block lengths
        stud_width = FRAMING_PARAMS.get("stud_width", 1.5 / 12)  # Default to 1.5 inches in feet
            
        # Store all generated blocks
        all_blocks = []
        
        # First, try to use standard cells for blocking
        standard_cells_successful = False
        
        # Process header cripples and assign them to cells
        print("\nProcessing header cripples:")
        header_cripple_count = len(self.header_cripples)
        print(f"Total header cripples found: {header_cripple_count}")
        
        for i, cripple in enumerate(self.header_cripples):
            try:
                # Get the bounding box of the cripple
                bbox = cripple.GetBoundingBox(True)
                if not bbox:
                    print(f"  Header Cripple {i+1}: Could not get bounding box")
                    continue
                    
                min_pt = bbox.Min
                max_pt = bbox.Max
                
                # Get the u-coordinate (position along wall length)
                u_coord = self._project_point_to_u_coordinate(min_pt, base_plane)
                print(f"  Header Cripple {i+1}: u-coordinate = {u_coord:.4f}, height range: {min_pt.Z:.4f} to {max_pt.Z:.4f}")
                
                # Find the HCC cell this cripple belongs to
                assigned = False
                for cell in cells:
                    cell_id = cell.get("cell_id", "")
                    cell_type = cell.get("cell_type", "")
                    
                    # Only process HeaderCrippleCells
                    if cell_type != "HCC":
                        continue
                        
                    # Get cell bounds directly from cell data
                    u_start = cell.get("u_start", 0)
                    u_end = cell.get("u_end", 0)
                    
                    # Check if cripple position is within cell bounds with a small tolerance
                    if u_start - 0.1 <= u_coord <= u_end + 0.1:
                        # Initialize the list for this cell if not already done
                        if cell_id not in self.stud_positions:
                            self.stud_positions[cell_id] = []
                            
                        # Add the cripple position to this cell
                        self.stud_positions[cell_id].append(u_coord)
                        print(f"    Assigned header cripple at position {u_coord:.4f} to cell {cell_id} (u_start={u_start}, u_end={u_end})")
                        assigned = True
                
                if not assigned:
                    print(f"    WARNING: Could not assign header cripple at position {u_coord:.4f} to any HCC cell")
            except Exception as e:
                print(f"  Error processing header cripple {i+1}: {str(e)}")
        
        # Process sill cripples and assign them to cells
        print("\nProcessing sill cripples:")
        sill_cripple_count = len(self.sill_cripples)
        print(f"Total sill cripples found: {sill_cripple_count}")
        
        for i, cripple in enumerate(self.sill_cripples):
            try:
                # Get the bounding box of the cripple
                bbox = cripple.GetBoundingBox(True)
                if not bbox:
                    print(f"  Sill Cripple {i+1}: Could not get bounding box")
                    continue
                    
                min_pt = bbox.Min
                max_pt = bbox.Max
                
                # Get the u-coordinate (position along wall length)
                u_coord = self._project_point_to_u_coordinate(min_pt, base_plane)
                print(f"  Sill Cripple {i+1}: u-coordinate = {u_coord:.4f}, height range: {min_pt.Z:.4f} to {max_pt.Z:.4f}")
                
                # Find the SCC cell this cripple belongs to
                assigned = False
                for cell in cells:
                    cell_id = cell.get("cell_id", "")
                    cell_type = cell.get("cell_type", "")
                    
                    # Only process SillCrippleCells
                    if cell_type != "SCC":
                        continue
                        
                    # Get cell bounds directly from cell data
                    u_start = cell.get("u_start", 0)
                    u_end = cell.get("u_end", 0)
                    
                    # Check if cripple position is within cell bounds with a small tolerance
                    if u_start - 0.1 <= u_coord <= u_end + 0.1:
                        # Initialize the list for this cell if not already done
                        if cell_id not in self.stud_positions:
                            self.stud_positions[cell_id] = []
                            
                        # Add the cripple position to this cell
                        self.stud_positions[cell_id].append(u_coord)
                        print(f"    Assigned sill cripple at position {u_coord:.4f} to cell {cell_id} (u_start={u_start}, u_end={u_end})")
                        assigned = True
                
                if not assigned:
                    print(f"    WARNING: Could not assign sill cripple at position {u_coord:.4f} to any SCC cell")
            except Exception as e:
                print(f"  Error processing sill cripple {i+1}: {str(e)}")
        
        print("\nCompleted processing header and sill cripples")
        print(f"Total cells with stud positions: {len(self.stud_positions)}")
        
        # Generate and return the blocking elements
        all_blocks = self._generate_row_blocking(self.stud_positions, block_width, block_thickness, base_plane)
        print(f"Total blocks created: {len(all_blocks)}")
        print("===== END ROW BLOCKING DIAGNOSTIC INFO =====")
        return all_blocks
    
    def _project_point_to_u_coordinate(self, point: rg.Point3d, base_plane: rg.Plane) -> float:
        """
        Project a 3D point onto the wall base plane and get the U coordinate.
        
        Args:
            point: 3D point to project
            base_plane: Wall base plane
            
        Returns:
            U coordinate along the wall length
        """
        try:
            # Convert world coordinates to a u-coordinate
            # We need to get the distance from the base plane origin along the X-axis direction
            
            # Create vector from plane origin to the point
            vector_to_point = rg.Vector3d(point - base_plane.Origin)
            
            # Project this vector onto the X-axis of the base plane
            # The dot product gives us the scalar projection
            u_coordinate = vector_to_point * base_plane.XAxis
            
            # Print debug information
            print(f"DEBUG: Point({point.X:.4f}, {point.Y:.4f}, {point.Z:.4f})")
            print(f"DEBUG: Plane Origin({base_plane.Origin.X:.4f}, {base_plane.Origin.Y:.4f}, {base_plane.Origin.Z:.4f})")
            print(f"DEBUG: Plane X-Axis({base_plane.XAxis.X:.4f}, {base_plane.XAxis.Y:.4f}, {base_plane.XAxis.Z:.4f})")
            print(f"DEBUG: Vector to point({vector_to_point.X:.4f}, {vector_to_point.Y:.4f}, {vector_to_point.Z:.4f})")
            print(f"DEBUG: Projected u-coordinate: {u_coordinate:.4f}")
            
            return u_coordinate
            
        except Exception as e:
            print(f"Error in _project_point_to_u_coordinate: {str(e)}")
            
            # Use direct coordinate extraction as fallback
            try:
                # Just extract X coordinate (assumes wall is aligned with world X axis)
                print(f"Using fallback coordinate extraction, point X: {point.X}")
                return point.X
            except Exception as e2:
                print(f"Fallback also failed: {str(e2)}")
                return 0.0
    
    def _process_cripples(self, cells, hcc_cells, scc_cells):
        """
        Process header and sill cripples, assigning them to appropriate cells.
        
        Args:
            cells: Dictionary of cells
            hcc_cells: Output dictionary to store cells with header cripples
            scc_cells: Output dictionary to store cells with sill cripples
        """
        print("\nProcessing header cripples:")
        header_cripples_found = 0
        
        base_plane = self.wall_data.get('base_plane')
        print(f"Base plane: Origin({base_plane.Origin.X:.4f}, {base_plane.Origin.Y:.4f}, {base_plane.Origin.Z:.4f})")
        print(f"Base plane X-axis: ({base_plane.XAxis.X:.4f}, {base_plane.XAxis.Y:.4f}, {base_plane.XAxis.Z:.4f})")
        print(f"Base plane Y-axis: ({base_plane.YAxis.X:.4f}, {base_plane.YAxis.Y:.4f}, {base_plane.YAxis.Z:.4f})")
        
        # Process header cripples
        for hc in self.header_cripples:
            header_cripples_found += 1
            
            # Get the u-coordinate and height range
            try:
                # For Brep objects, we need to extract the centerpoint
                if isinstance(hc, rg.Brep):
                    # Get the bounding box and use its center point
                    bbox = hc.GetBoundingBox(True)
                    hc_point = bbox.Center
                    print(f"  HC{header_cripples_found} using bounding box center: ({hc_point.X:.4f}, {hc_point.Y:.4f}, {hc_point.Z:.4f})")
                else:
                    # Try to use centerline method if available
                    if hasattr(hc, 'get_centerline_start_point'):
                        hc_point = hc.get_centerline_start_point()
                        print(f"  HC{header_cripples_found} using centerline start point")
                    else:
                        # Fallback to center of mass if neither available
                        hc_point = rg.AreaMassProperties.Compute(hc).Centroid
                        print(f"  HC{header_cripples_found} using centroid: ({hc_point.X:.4f}, {hc_point.Y:.4f}, {hc_point.Z:.4f})")
            except Exception as e:
                print(f"  Error getting point for header cripple: {str(e)}")
                continue
            
            print(f"  HC{header_cripples_found} point: ({hc_point.X:.4f}, {hc_point.Y:.4f}, {hc_point.Z:.4f})")
            
            # Get the u-coordinate (position along wall length)
            u_coord = self._project_point_to_u_coordinate(hc_point, base_plane)
            print(f"  Header Cripple {header_cripples_found}: u-coordinate = {u_coord:.4f}, height range: {hc_point.Z:.4f} to {hc_point.Z:.4f}")
            
            # Find the HCC cell this cripple belongs to
            found_cell = False
            for cell_key, cell in cells.items():
                if not cell_key.startswith("HCC_"):
                    continue
                    
                # Extract u-range from cell key (format: HCC_start_end)
                parts = cell_key.split("_")
                if len(parts) >= 3:
                    try:
                        u_start = float(parts[1])
                        u_end = float(parts[2])
                        
                        # Check if cripple is in this cell's range
                        if u_start <= u_coord <= u_end:
                            # Add the u-coordinate to the cell's vertical elements
                            if 'vertical_elements' not in cell:
                                cell['vertical_elements'] = []
                            
                            # Add as string to match format from framing generator
                            u_str = f"{u_coord:.4f}"
                            if u_str not in cell['vertical_elements']:
                                cell['vertical_elements'].append(u_str)
                                
                            # Also add to HCC cells dictionary
                            hcc_cells[cell_key] = cell
                            found_cell = True
                            
                            print(f"    Assigned header cripple at position {u_coord:.4f} to cell {cell_key}")
                    except (ValueError, IndexError):
                        continue
            
            if not found_cell:
                print(f"    WARNING: Could not assign header cripple at position {u_coord:.4f} to any HCC cell")
        
        print(f"Total header cripples found: {header_cripples_found}")
        
        # Process sill cripples
        print("\nProcessing sill cripples:")
        sill_cripples_found = 0
        
        for sc in self.sill_cripples:
            sill_cripples_found += 1
            
            # Get the u-coordinate and height range
            try:
                # For Brep objects, we need to extract the centerpoint
                if isinstance(sc, rg.Brep):
                    # Get the bounding box and use its center point
                    bbox = sc.GetBoundingBox(True)
                    sc_point = bbox.Center
                    print(f"  SC{sill_cripples_found} using bounding box center: ({sc_point.X:.4f}, {sc_point.Y:.4f}, {sc_point.Z:.4f})")
                else:
                    # Try to use centerline method if available
                    if hasattr(sc, 'get_centerline_start_point'):
                        sc_point = sc.get_centerline_start_point()
                        print(f"  SC{sill_cripples_found} using centerline start point")
                    else:
                        # Fallback to center of mass if neither available
                        sc_point = rg.AreaMassProperties.Compute(sc).Centroid
                        print(f"  SC{sill_cripples_found} using centroid: ({sc_point.X:.4f}, {sc_point.Y:.4f}, {sc_point.Z:.4f})")
            except Exception as e:
                print(f"  Error getting point for sill cripple: {str(e)}")
                continue
            
            print(f"  SC{sill_cripples_found} point: ({sc_point.X:.4f}, {sc_point.Y:.4f}, {sc_point.Z:.4f})")
            
            # Get the u-coordinate (position along wall length)
            u_coord = self._project_point_to_u_coordinate(sc_point, base_plane)
            print(f"  Sill Cripple {sill_cripples_found}: u-coordinate = {u_coord:.4f}, height range: {sc_point.Z:.4f} to {sc_point.Z:.4f}")
            
            # Find the SCC cell this cripple belongs to
            found_cell = False
            for cell_key, cell in cells.items():
                if not cell_key.startswith("SCC_"):
                    continue
                    
                # Extract u-range from cell key (format: SCC_start_end)
                parts = cell_key.split("_")
                if len(parts) >= 3:
                    try:
                        u_start = float(parts[1])
                        u_end = float(parts[2])
                        
                        # Check if cripple is in this cell's range
                        if u_start <= u_coord <= u_end:
                            # Add the u-coordinate to the cell's vertical elements
                            if 'vertical_elements' not in cell:
                                cell['vertical_elements'] = []
                            
                            # Add as string to match format from framing generator
                            u_str = f"{u_coord:.4f}"
                            if u_str not in cell['vertical_elements']:
                                cell['vertical_elements'].append(u_str)
                                
                            # Also add to SCC cells dictionary
                            scc_cells[cell_key] = cell
                            found_cell = True
                            
                            print(f"    Assigned sill cripple at position {u_coord:.4f} to cell {cell_key}")
                    except (ValueError, IndexError):
                        continue
            
            if not found_cell:
                print(f"    WARNING: Could not assign sill cripple at position {u_coord:.4f} to any SCC cell")
        
        print(f"Total sill cripples found: {sill_cripples_found}")
        print(f"Completed processing header and sill cripples")
    
    def _generate_row_blocking(self, cells, block_width, block_thickness, base_plane):
        """
        Generate row blocking elements for the given cells.
        
        Args:
            cells: Dictionary of cells with vertical elements
            block_width: Width of blocking elements
            block_thickness: Thickness of blocking elements
            base_plane: Base plane of the wall
            
        Returns:
            List of row blocking Brep elements
        """
        blocks = []
        include_blocking = self.blocking_params.include_blocking
        if not include_blocking:
            print("Blocking is disabled via parameters")
            return blocks
        
        # Get blocking heights based on wall height
        wall_height = self.wall_top_elevation - self.wall_base_elevation
        print(f"Wall height: {wall_height}")
        print(f"Wall elevations: base={self.wall_base_elevation}, top={self.wall_top_elevation}")
        
        # Get block heights from pattern or calculate them
        if self.blocking_params.first_block_height:
            first_block_height = self.blocking_params.first_block_height
            block_heights = [first_block_height]
            
            # If wall is higher than twice the first block height, add additional blocks
            remaining_height = wall_height - first_block_height
            spacing = self.blocking_params.block_spacing
            
            if remaining_height > spacing:
                num_additional_blocks = int(remaining_height / spacing)
                for i in range(num_additional_blocks):
                    block_heights.append(first_block_height + spacing * (i + 1))
        else:
            # Default to 1/3 and 2/3 of wall height
            block_heights = [wall_height / 3, 2 * wall_height / 3]
        
        print(f"Block profile dimensions: {{'thickness': {block_thickness}, 'width': {block_width}}}")
        print(f"Block profile: 2x4, width: {block_width}, thickness: {block_thickness}")
        print(f"Calculated block heights: {block_heights}")
        
        # Process header and sill cripples
        hcc_cells = {}
        scc_cells = {}
        self._process_cripples(cells, hcc_cells, scc_cells)
        
        # For each cell type, create blocks between studs
        cells_with_studs = 0
        for cell_key, stud_positions in cells.items():
            # Skip cells without stud positions
            if not stud_positions:
                continue
            
            print(f"Processing cell {cell_key} with {len(stud_positions)} vertical elements")
            cells_with_studs += 1
            
            # Create a cell dictionary with the required structure
            cell_dict = {
                'vertical_elements': stud_positions,
                'cell_id': cell_key
            }
            
            blocks_in_cell = self._create_blocking_for_cell(
                cell_dict, 
                block_heights, 
                block_thickness, 
                block_width,
                base_plane
            )
            blocks.extend(blocks_in_cell)
        
        print(f"Total cells with stud positions: {cells_with_studs}")
        print(f"Total blocks created: {len(blocks)}")
        return blocks
    
    def _create_blocking_for_cell(self, cell, block_heights, block_thickness, block_width, base_plane):
        """
        Create blocking elements for a single cell.
        
        Args:
            cell: Dictionary with cell data
            block_heights: List of heights for blocking elements
            block_thickness: Thickness of blocking elements
            block_width: Width of blocking elements
            base_plane: Base plane of the wall
            
        Returns:
            List of blocking Brep elements
        """
        blocks = []
        
        # Extract vertical elements (stud positions)
        # Sometimes these are stored as strings, so convert to floats
        vertical_elements = cell.get('vertical_elements', [])
        
        # Try to handle both list and string formats
        stud_positions = []
        for pos in vertical_elements:
            try:
                # Handle string representation
                if isinstance(pos, str):
                    stud_positions.append(float(pos))
                else:
                    stud_positions.append(float(pos))
            except (ValueError, TypeError) as e:
                print(f"Error converting stud position {pos}: {str(e)}")
                # Skip this position
                continue
        
        # Sort stud positions
        stud_positions = sorted(stud_positions)
        
        if len(stud_positions) < 2:
            cell_id = cell.get('cell_id', 'unknown')
            print(f"Not enough studs in cell {cell_id} to create blocking. Found {len(stud_positions)} positions.")
            return blocks  # Need at least 2 studs to create blocking
        
        # Create blocking between adjacent studs
        for i in range(len(stud_positions) - 1):
            left_stud_pos = stud_positions[i]
            right_stud_pos = stud_positions[i + 1]
            
            # Skip if studs are too close
            if right_stud_pos - left_stud_pos < 0.5:  # Minimum 6" between studs
                continue
            
            # Create a block at each height
            for block_height in block_heights:
                # Convert from feet to actual height
                block_center_z = self.wall_base_elevation + block_height
                
                # Create center point for the block
                center_u = (left_stud_pos + right_stud_pos) / 2
                center_point = self._create_point_at_u_coordinate(
                    center_u, block_center_z, base_plane
                )
                
                # Calculate length (span between studs minus stud width)
                block_length = right_stud_pos - left_stud_pos - 0.125
                
                # Create the block
                block = self._create_block_brep(
                    center_point, 
                    block_length, 
                    block_width, 
                    block_thickness,
                    base_plane
                )
                
                if block:
                    blocks.append(block)
                    print(f"Created block between studs at {left_stud_pos:.4f} and {right_stud_pos:.4f} at height {block_height:.4f}")
        
        return blocks
        
    def _create_point_at_u_coordinate(self, u_coordinate, z_coordinate, base_plane):
        """
        Create a 3D point at the given U and Z coordinates.
        
        Args:
            u_coordinate: U coordinate along the wall
            z_coordinate: Z coordinate (height)
            base_plane: Base plane of the wall
            
        Returns:
            3D point
        """
        try:
            # Start at the origin of the base plane
            point = rg.Point3d(base_plane.Origin)
            
            # Move along the X axis of the base plane by u_coordinate
            x_vector = rg.Vector3d(base_plane.XAxis)
            x_vector *= u_coordinate
            point += x_vector
            
            # Move along the Z axis by z_coordinate
            z_vector = rg.Vector3d(0, 0, 1)  # World Z axis
            z_vector *= z_coordinate
            point += z_vector
            
            return point
        except Exception as e:
            print(f"Error creating point at u-coordinate: {str(e)}")
            
            # Use direct coordinate extraction as fallback
            try:
                # Just extract X coordinate (assumes wall is aligned with world X axis)
                print(f"Using fallback coordinate extraction, point X: {u_coordinate}")
                return rg.Point3d(u_coordinate, 0, z_coordinate)
            except Exception as e2:
                print(f"Fallback also failed: {str(e2)}")
                return None
            
    def _create_block_brep(self, center_point, length, width, thickness, base_plane):
        """
        Create a block Brep at the specified location.
        
        Args:
            center_point: Center point of the block
            length: Length of the block (along wall)
            width: Width of the block (perpendicular to wall)
            thickness: Thickness of the block (height)
            base_plane: Base plane of the wall
            
        Returns:
            Block Brep
        """
        try:
            # Create a box centered at the point
            half_length = length / 2
            half_width = width / 2
            half_thickness = thickness / 2
            
            # Create transform from world to wall coordinates
            plane_at_center = rg.Plane(center_point, base_plane.XAxis, base_plane.YAxis)
            
            # Create the box
            block = rg.Box(plane_at_center, 
                          rg.Interval(-half_length, half_length),
                          rg.Interval(-half_width, half_width),
                          rg.Interval(-half_thickness, half_thickness))
            
            return block.ToBrep()
        except Exception as e:
            print(f"Error creating block brep: {str(e)}")
            return None

    def generate(self) -> List[rg.Brep]:
        """
        Generate row blocking elements based on configured cells and studs.
        
        Returns:
            List of row blocking Brep elements
        """
        blocks = []
        include_blocking = self.blocking_params.include_blocking
        if not include_blocking:
            print("Blocking is disabled via parameters")
            return blocks
            
        # Get wall height
        wall_height = self.wall_top_elevation - self.wall_base_elevation
        print(f"Wall height: {wall_height}")
        print(f"Wall elevations: base={self.wall_base_elevation}, top={self.wall_top_elevation}")
        
        # Get block heights from pattern or calculate them
        if self.blocking_params.first_block_height:
            first_block_height = self.blocking_params.first_block_height
            block_heights = [first_block_height]
            
            # If wall is higher than twice the first block height, add additional blocks
            remaining_height = wall_height - first_block_height
            spacing = self.blocking_params.block_spacing
            
            if remaining_height > spacing:
                num_additional_blocks = int(remaining_height / spacing)
                for i in range(num_additional_blocks):
                    block_heights.append(first_block_height + spacing * (i + 1))
        else:
            # Default to 1/3 and 2/3 of wall height
            block_heights = [wall_height / 3, 2 * wall_height / 3]
        
        # Get blocking pattern
        pattern = self.blocking_params.pattern
        
        # Get base plane from wall data - always use this for consistency
        base_plane = self.wall_data.get("base_plane")
        if base_plane is None:
            print("No base plane found in wall data, using WorldXY")
            base_plane = rg.Plane.WorldXY
        
        # Get dimensions for stud width adjustment
        try:
            dims = self.block_profile.get_dimensions()
            block_width = dims["width"]  # Vertical dimension (usually 1.5" for 2x4)
            block_thickness = dims["thickness"]  # Horizontal dimension (usually 3.5" for 2x4)
            print(f"Using block profile dimensions: {dims}")
        except (AttributeError, KeyError) as e:
            # Fallback to direct attributes if get_dimensions not available
            print(f"Using direct profile attributes - get_dimensions failed: {str(e)}")
            try:
                # Try nominal_width/nominal_depth
                block_width = self.block_profile.nominal_width
                block_thickness = self.block_profile.nominal_depth
            except AttributeError:
                # Last resort - try width/depth directly
                try:
                    block_width = self.block_profile.width
                    block_thickness = self.block_profile.depth
                except AttributeError:
                    # Default to standard 2x4 dimensions
                    print("WARNING: Could not determine block dimensions, using defaults for 2x4")
                    block_width = 1.5 / 12.0  # 1.5 inches in feet
                    block_thickness = 3.5 / 12.0  # 3.5 inches in feet
            
        print(f"Using block dimensions: width={block_width}, thickness={block_thickness}")
            
        if pattern == BlockingPattern.STAGGERED:
            print("Using STAGGERED blocking pattern")
            # Create cells dictionary from stud_positions
            cells_dict = {}
            for cell_id, positions in self.stud_positions.items():
                if positions:  # Only include cells with stud positions
                    cells_dict[cell_id] = positions
            
            if cells_dict:
                blocks = self._create_staggered_blocking(cells_dict, block_heights, block_thickness, block_width, base_plane)
            else:
                print("No cells with stud positions found for staggered blocking")
        elif pattern == BlockingPattern.INLINE:
            print("Using INLINE blocking pattern")
            
            # Check if we have stud positions
            if self.stud_positions:
                blocks = self._generate_row_blocking(self.stud_positions, block_width, block_thickness, base_plane)
            else:
                print("No stud positions found for inline blocking")
        else:
            print(f"Unsupported blocking pattern: {pattern}")
        
        print(f"Generated {len(blocks)} blocking elements")
        return blocks
    
    def _create_staggered_blocking(self, cells, block_heights, block_thickness, block_width, base_plane):
        """
        Create staggered pattern blocking across cells.
        
        Args:
            cells: Dictionary of cells
            block_heights: List of block heights
            block_thickness: Thickness of blocking
            block_width: Width of blocking
            base_plane: Base plane for coordinates
            
        Returns:
            List of blocking Brep elements
        """
        blocks = []
        pattern = self.blocking_params.pattern
        
        print(f"Creating staggered blocking with pattern: {pattern}")
        
        # TODO: Implement staggered blocking pattern
        
        return blocks
