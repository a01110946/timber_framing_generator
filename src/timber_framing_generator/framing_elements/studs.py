# File: timber_framing_generator/framing_elements/studs.py

from typing import Dict, List, Any, Optional
import Rhino.Geometry as rg
import math
from timber_framing_generator.config.framing import FRAMING_PARAMS, PROFILES

def calculate_stud_locations(
    cell, 
    stud_spacing=0.6, 
    start_location=None, 
    remove_first=False, 
    remove_last=False
):
    """
    Calculates stud locations for a given wall cell (or segment) based on its base geometry.
    This intermediate step takes a cell (which should include a base line or a segment)
    and returns a list of points representing the locations for studs.
    
    Keyword Args:
        stud_spacing (float): Desired spacing between studs.
        start_location: Optional starting point (rg.Point3d) or parameter on the base geometry
                        where stud distribution should begin.
        remove_first (bool): If True, skip the first stud (to avoid collision with a king stud).
        remove_last (bool): If True, skip the last stud.
    
    Returns:
        list: A list of rg.Point3d objects representing stud locations.
    """
    # Assume the cell contains a key "base_line" with a Rhino.Geometry.Curve representing the stud area.
    base_line = cell.get("base_line")
    if not base_line or not isinstance(base_line, rg.Curve):
        raise ValueError("Cell must contain a valid 'base_line' (Rhino.Geometry.Curve) for stud placement.")
    
    # Determine the starting parameter. If start_location is given and is a point, get its parameter on the line.
    if start_location and isinstance(start_location, rg.Point3d):
        success, t0 = base_line.ClosestPoint(start_location)
    else:
        t0 = 0.0

    # Compute the total length of the base_line.
    length = base_line.GetLength()
    # Determine number of studs (using stud_spacing)
    num_intervals = int(length / stud_spacing)
    # Create stud locations uniformly along the line.
    stud_points = [base_line.PointAt(t0 + (i / float(num_intervals)) * length) for i in range(num_intervals + 1)]
    
    # Optionally remove the first and/or last stud.
    if remove_first and stud_points:
        stud_points = stud_points[1:]
    if remove_last and stud_points:
        stud_points = stud_points[:-1]
    
    return stud_points

def generate_stud(profile="2x4", stud_height=2.4, stud_thickness=None, stud_width=None):
    dimensions = PROFILES.get(profile, {})
    thickness = stud_thickness or dimensions.get("thickness", 0.04)
    width = stud_width or dimensions.get("width", 0.09)

    if thickness is None or width is None:
        raise ValueError("Explicit dimensions must be provided for custom profiles.")

    stud = {
        "type": "stud",
        "profile": profile,
        "thickness": thickness,
        "width": width,
        "height": stud_height,
        "geometry": "placeholder_for_geometry"
    }

    return stud

class StudGenerator:
    """
    Generates standard wall studs within stud cells.
    
    Studs are vertical framing members placed at regular intervals along the wall.
    They run from the top face of the bottom plate to the bottom face of the top plate.
    This class uses existing Stud Cell (SC) information from cell decomposition
    to determine where studs should be placed with proper spacing.
    """
    
    def __init__(
        self,
        wall_data: Dict[str, Any],
        bottom_plate: Any,
        top_plate: Any,
        king_studs: List[rg.Brep] = None
    ):
        """
        Initialize the stud generator with wall data and plate references.
        
        Args:
            wall_data: Dictionary containing wall information including:
                - base_plane: Reference plane for wall coordinate system
                - cells: List of cell dictionaries from decomposition
            bottom_plate: The bottom plate object (for elevation reference)
            top_plate: The top plate object (for elevation reference)
            king_studs: Optional list of king stud geometries to avoid overlap
        """
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data
        self.bottom_plate = bottom_plate
        self.top_plate = top_plate
        self.king_studs = king_studs or []
        
        # Initialize storage for debug geometry
        self.debug_geometry = {
            'points': [],
            'planes': [],
            'profiles': [],
            'paths': []
        }
        
        # Extract and store king stud positions for reference
        self.king_stud_positions = self._extract_king_stud_positions()
    
    def _extract_king_stud_positions(self) -> List[float]:
        """
        Extract U-coordinates of king studs to avoid overlap.
        
        Returns:
            List of U-coordinates (along wall length) where king studs are positioned
        """
        positions = []
        
        if not self.king_studs:
            print("No king studs provided to avoid overlap")
            return positions
            
        try:
            base_plane = self.wall_data.get('base_plane')
            if base_plane is None:
                print("No base plane available for king stud position extraction")
                return positions
                
            # Process each king stud to extract its U-coordinate
            for stud in self.king_studs:
                # Get bounding box of king stud
                bbox = stud.GetBoundingBox(True)
                if not bbox.IsValid:
                    continue
                    
                # Calculate center point of bounding box
                center_x = (bbox.Min.X + bbox.Max.X) / 2
                center_y = (bbox.Min.Y + bbox.Max.Y) / 2
                center_point = rg.Point3d(center_x, center_y, bbox.Min.Z)
                
                # Project onto wall base plane to get u-coordinate
                u_coordinate = self._project_point_to_u_coordinate(center_point, base_plane)
                positions.append(u_coordinate)
                
            print(f"Extracted {len(positions)} king stud positions: {positions}")
            return positions
            
        except Exception as e:
            print(f"Error extracting king stud positions: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return positions
            
    def _project_point_to_u_coordinate(self, point: rg.Point3d, base_plane: rg.Plane) -> float:
        """
        Project a 3D point onto the wall's u-axis to get its u-coordinate.
        
        Args:
            point: The 3D point to project
            base_plane: The wall's base plane
            
        Returns:
            The u-coordinate (distance along wall)
        """
        try:
            # Vector from base plane origin to the point
            vec = point - base_plane.Origin
            
            # Project this vector onto the u-axis (XAxis)
            # Use the dot product for projection
            u = vec * base_plane.XAxis
            
            return u
            
        except Exception as e:
            print(f"Error projecting point to u-coordinate: {str(e)}")
            return 0.0
    
    def generate_studs(self) -> List[rg.Brep]:
        """
        Generate studs based on Stud Cell (SC) information.
        
        This method processes all stud cells and generates studs with proper
        spacing according to the configured stud spacing parameter. Studs run
        from the top of the bottom plate to the bottom of the top plate.
        
        Returns:
            List of stud Brep geometries
        """
        try:
            # Get wall cells from the wall data
            cells = self.wall_data.get('cells', [])
            if not cells:
                print("No cells found in wall data")
                return []
                
            # Extract only Stud Cells (SC)
            stud_cells = [cell for cell in cells if cell.get('cell_type') == 'SC']
            
            print(f"\nFound {len(stud_cells)} Stud Cells (SC) in wall data")
            
            if not stud_cells:
                print("No Stud Cells (SC) found in wall data")
                return []
            
            # Get plate boundary elevations
            try:
                plate_data = self._get_plate_boundary_data()
                if not plate_data:
                    print("Failed to get plate boundary data")
                    return []
                    
                bottom_elevation = plate_data['bottom_elevation']
                top_elevation = plate_data['top_elevation']
                
                print(f"Stud vertical bounds: bottom={bottom_elevation}, top={top_elevation}")
                
                # Create debug point at these elevations for verification
                base_plane = self.wall_data.get('base_plane')
                if base_plane:
                    debug_bottom = rg.Point3d.Add(
                        base_plane.Origin,
                        rg.Vector3d.Multiply(base_plane.YAxis, bottom_elevation)
                    )
                    debug_top = rg.Point3d.Add(
                        base_plane.Origin,
                        rg.Vector3d.Multiply(base_plane.YAxis, top_elevation)
                    )
                    self.debug_geometry['points'].extend([debug_bottom, debug_top])
                    
            except Exception as e:
                print(f"Error getting plate boundary data: {str(e)}")
                import traceback
                print(traceback.format_exc())
                return []
            
            # Get essential parameters
            base_plane = self.wall_data.get('base_plane')
            if base_plane is None:
                print("No base plane available")
                return []
                
            # Calculate stud dimensions from framing parameters
            stud_width = FRAMING_PARAMS.get("stud_width", 1.5/12)   # Typically 1.5 inches
            stud_depth = FRAMING_PARAMS.get("stud_depth", 3.5/12)   # Typically 3.5 inches
            stud_spacing = FRAMING_PARAMS.get("stud_spacing", 16/12)  # Typically 16 inches
            
            print(f"Stud parameters: width={stud_width}, depth={stud_depth}, spacing={stud_spacing}")
            
            # Store all generated studs
            all_studs = []
            
            # Process each stud cell
            for i, cell in enumerate(stud_cells):
                try:
                    print(f"\nProcessing Stud Cell {i+1}")
                    
                    # Extract cell boundaries
                    u_start = cell.get('u_start')
                    u_end = cell.get('u_end')
                    
                    if None in (u_start, u_end):
                        print(f"Invalid stud cell boundaries: u_start={u_start}, u_end={u_end}")
                        continue
                        
                    cell_width = u_end - u_start
                    print(f"Cell bounds: u_start={u_start}, u_end={u_end}, width={cell_width}")
                    
                    # Adjust cell boundaries to account for stud depth (half width at each end)
                    adjusted_u_start = u_start + (stud_width / 2)
                    adjusted_u_end = u_end - (stud_width / 2)
                    
                    # Check if we still have valid width after adjustment
                    if adjusted_u_end <= adjusted_u_start:
                        print(f"Cell too narrow after boundary adjustment")
                        continue
                        
                    print(f"Adjusted bounds: u_start={adjusted_u_start}, u_end={adjusted_u_end}")
                    
                    # Calculate stud positions within this cell, accounting for king studs
                    stud_positions = self._calculate_stud_positions(
                        adjusted_u_start, 
                        adjusted_u_end, 
                        stud_spacing,
                        stud_depth
                    )
                    
                    # Filter out positions that would conflict with king studs
                    filtered_positions = self._filter_king_stud_conflicts(
                        stud_positions, 
                        stud_depth
                    )
                    
                    print(f"Calculated {len(stud_positions)} stud positions in cell")
                    print(f"After filtering king stud conflicts: {len(filtered_positions)} positions")
                    
                    # Generate a stud at each position
                    cell_studs = []
                    for j, u_pos in enumerate(filtered_positions):
                        stud = self._create_stud_geometry(
                            base_plane,
                            u_pos,
                            bottom_elevation,
                            top_elevation,
                            stud_width,
                            stud_depth
                        )
                        
                        if stud is not None:
                            cell_studs.append(stud)
                            print(f"  Created stud {j+1} at u={u_pos}")
                        else:
                            print(f"  Failed to create stud {j+1} at u={u_pos}")
                    
                    all_studs.extend(cell_studs)
                    
                except Exception as e:
                    print(f"Error processing stud cell {i+1}: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    continue
            
            print(f"\nGenerated {len(all_studs)} studs total")
            return all_studs
                
        except Exception as e:
            print(f"Error generating studs: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []
    
    def _get_plate_boundary_data(self) -> Dict[str, float]:
        """
        Extract boundary elevations from the top and bottom plates.
        
        Returns a dictionary with bottom_elevation (top face of bottom plate)
        and top_elevation (bottom face of top plate) for positioning studs.
        
        Returns:
            Dictionary with boundary elevations, or None if extraction fails
        """
        try:
            print("\nExtracting plate boundary data:")
            
            # Get boundary data from bottom plate
            bottom_plate_data = self.bottom_plate.get_boundary_data()
            if not bottom_plate_data:
                print("Failed to get bottom plate boundary data")
                return None
                
            # Get boundary data from top plate
            top_plate_data = self.top_plate.get_boundary_data()
            if not top_plate_data:
                print("Failed to get top plate boundary data")
                return None
        
            # Debug - print ALL data from the plates to identify what's going wrong
            print(f"Full bottom plate data: {bottom_plate_data}")
            print(f"Full top plate data: {top_plate_data}")
        
            # Check what absolute elevation data is available
            wall_base_elevation = self.wall_data.get('wall_base_elevation', 0.0)
            wall_top_elevation = self.wall_data.get('wall_top_elevation', 0.0)
            print(f"Wall base elevation: {wall_base_elevation}")
            print(f"Wall top elevation: {wall_top_elevation}")
        
            # Get absolute elevations from plate data
            # Using "boundary_elevation" values which should be absolute world coordinates
            bottom_elevation = bottom_plate_data.get('boundary_elevation')
            top_elevation = top_plate_data.get('boundary_elevation')
            
            print(f"Bottom plate data: {bottom_plate_data}")
            print(f"Top plate data: {top_plate_data}")
        
            if bottom_elevation is None or top_elevation is None:
                print("WARNING: Missing elevation data - falling back to relative calculations")
                # Try to calculate absolute elevations using wall data
                bottom_elevation = wall_base_elevation + bottom_plate_data.get('thickness', 0.0)
                top_elevation = wall_top_elevation - top_plate_data.get('thickness', 0.0)
            
            print(f"Using bottom elevation: {bottom_elevation}")
            print(f"Using top elevation: {top_elevation}")
            
            # Validate that elevations make sense (bottom should be below top)
            if bottom_elevation >= top_elevation:
                print(f"WARNING: Invalid elevations - bottom ({bottom_elevation}) is not below top ({top_elevation})")
                # Try to correct by using relative wall heights if available
                if wall_top_elevation > wall_base_elevation:
                    bottom_elevation = wall_base_elevation + (1.5*2/12)  # 3 inches (double 2x layers) up from base
                    top_elevation = wall_top_elevation - (1.5*2/12)     # 3 inches (double 2x layers) down from top
                    print(f"Corrected to bottom: {bottom_elevation}, top: {top_elevation}")
                
            return {
                'bottom_elevation': bottom_elevation,
                'top_elevation': top_elevation
            }
                
        except Exception as e:
            print(f"Error getting plate boundary data: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def _calculate_stud_positions(
        self, 
        start_u: float, 
        end_u: float, 
        spacing: float,
        stud_depth: float
    ) -> List[float]:
        """
        Calculate stud positions within a cell with proper spacing.
        
        This method determines where to place studs within the given
        U-coordinate range, using the specified on-center spacing.
        
        Args:
            start_u: Starting U-coordinate of the cell (already adjusted for stud depth)
            end_u: Ending U-coordinate of the cell (already adjusted for stud depth)
            spacing: On-center spacing between studs
            stud_depth: Depth of stud along wall length
            
        Returns:
            List of U-coordinates for stud placement
        """
        try:
            # Verify that the cell has valid width
            cell_width = end_u - start_u
            if cell_width <= 0:
                print(f"Invalid cell width: {cell_width}")
                return []
                
            # Place first stud at adjusted start of cell
            positions = [start_u]
            
            # Calculate how many full spacing intervals fit in the cell
            available_distance = cell_width - stud_depth
            num_intervals = int(available_distance / spacing)
            
            print(f"Cell adjusted width: {cell_width}, Available distance: {available_distance}")
            print(f"Spacing: {spacing}, Number of spacing intervals: {num_intervals}")
            
            # Place intermediate studs at regular intervals
            for i in range(1, num_intervals + 1):
                pos = start_u + i * spacing
                # Ensure we don't exceed the end boundary
                if pos < end_u:
                    positions.append(pos)
            
            # If there's enough space for another stud at the end, add it
            # Only add if it's at least half a stud depth away from the last stud
            last_stud_pos = positions[-1] if positions else start_u
            if (end_u - last_stud_pos) >= stud_depth:
                positions.append(end_u)
                
            print(f"Calculated {len(positions)} stud positions: {positions}")
            return positions
            
        except Exception as e:
            print(f"Error calculating stud positions: {str(e)}")
            return []
    
    def _filter_king_stud_conflicts(
        self, 
        stud_positions: List[float],
        stud_depth: float
    ) -> List[float]:
        """
        Filter out stud positions that would conflict with king studs.
        
        Args:
            stud_positions: List of potential stud U-coordinates
            stud_depth: Depth of stud along wall length for collision checking
            
        Returns:
            Filtered list of stud positions with no king stud conflicts
        """
        if not self.king_stud_positions:
            return stud_positions
            
        filtered_positions = []
        
        for pos in stud_positions:
            # Check if this position conflicts with any king stud
            conflicts = False
            
            for king_pos in self.king_stud_positions:
                # Calculate the distance between this stud and the king stud
                distance = abs(pos - king_pos)
                
                # If the distance is less than the sum of their half-depths,
                # they overlap and we should skip this position
                if distance < stud_depth:
                    conflicts = True
                    print(f"Stud at u={pos} conflicts with king stud at u={king_pos}")
                    break
                    
            if not conflicts:
                filtered_positions.append(pos)
                
        return filtered_positions
    
    def _create_stud_geometry(
        self,
        base_plane: rg.Plane,
        u_coordinate: float,
        bottom_v: float,
        top_v: float,
        width: float,
        depth: float
    ) -> Optional[rg.Brep]:
        """
        Create the geometry for a single stud.
        
        This method creates a stud by:
        1. Calculating the horizontal position using the base plane and u_coordinate
        2. Creating start and end points at the correct absolute elevations
        3. Creating a profile perpendicular to the stud's centerline
        4. Extruding the profile along the centerline path
        
        Args:
            base_plane: Wall's base plane for coordinate system
            u_coordinate: Position along wall (horizontal)
            bottom_v: Bottom elevation of stud (top of bottom plate)
            top_v: Top elevation of stud (bottom of top plate)
            width: Width of stud (perpendicular to wall face)
            depth: Depth of stud (parallel to wall length)
            
        Returns:
            Brep geometry for the stud, or None if creation fails
        """
        try:
            print(f"Creating stud at u={u_coordinate}")
            print(f"  Absolute elevations: bottom={bottom_v}, top={top_v}")
            
            # Calculate the components of the horizontal offset
            x_offset = base_plane.XAxis.X * u_coordinate
            y_offset = base_plane.XAxis.Y * u_coordinate
            z_offset = base_plane.XAxis.Z * u_coordinate
            
            # Calculate the base point coordinates
            base_x = base_plane.Origin.X + x_offset
            base_y = base_plane.Origin.Y + y_offset
            
            # Create start and end points with correct coordinates
            start_point = rg.Point3d(base_x, base_y, bottom_v)
            end_point = rg.Point3d(base_x, base_y, top_v)
            
            # Create the centerline as a curve
            centerline = rg.LineCurve(start_point, end_point)
            self.debug_geometry['paths'].append(centerline)
            
            # 2. Create a profile plane at the start point
            # X axis goes across wall thickness (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes along wall length (for depth)
            profile_y_axis = base_plane.XAxis
            
            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry['planes'].append(profile_plane)
            
            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-depth/2, depth/2),
                rg.Interval(-width/2, width/2)
            )
            
            profile_curve = profile_rect.ToNurbsCurve()
            self.debug_geometry['profiles'].append(profile_rect)
            
            # 4. Extrude the profile along the centerline path
            # Calculate the vector from start to end
            path_vector = rg.Vector3d(end_point - start_point)
            
            # Create the extrusion
            extrusion = rg.Extrusion.CreateExtrusion(profile_curve, path_vector)
            
            # Convert to Brep and return
            if extrusion and extrusion.IsValid:
                return extrusion.ToBrep().CapPlanarHoles(0.001)
            else:
                print("Failed to create valid stud extrusion")
                return None
                
        except Exception as e:
            print(f"Error creating stud geometry: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None
