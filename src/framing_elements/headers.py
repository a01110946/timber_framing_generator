# File: src/framing_elements/headers.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.framing_elements.header_parameters import HeaderParameters
from src.config.framing import FRAMING_PARAMS

class HeaderGenerator:
    """
    Generates header framing elements above openings.
    
    Headers span between king studs above an opening, providing structural
    support and load transfer around the opening. This class handles the
    positioning, sizing, and geometric creation of header elements.
    """
    
    def __init__(
        self,
        wall_data: Dict[str, Any]
        ):
        """
        Initialize the header generator with wall data and coordinate system.
        
        Args:
            wall_data: Dictionary containing wall information
            coordinate_system: Optional coordinate system for transformations
        """
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data
        
        # Initialize storage for debug geometry
        self.debug_geometry = {
            'points': [],
            'curves': [],
            'planes': [],
            'profiles': []
        }
    
    def generate_header(
        self,
        opening_data: Dict[str, Any],
        king_stud_positions: Optional[Tuple[float, float]] = None
    ) -> Optional[rg.Brep]:
        """
        Generate a header above an opening.
        
        This method creates a header based on:
        1. The opening data for positioning and dimensions
        2. Optional king stud positions for span length
        3. Wall type for appropriate profile selection
        
        Args:
            opening_data: Dictionary with opening information
            king_stud_positions: Optional tuple of (left, right) u-coordinates
                                 If not provided, calculated from opening width
                                 plus configured offsets
        
        Returns:
            Header geometry as a Rhino Brep
        """
        try:
            # Log input parameters
            print("\n===== HEADER GENERATION DETAILS =====")
            print(f"Opening data: {opening_data}")
            print(f"King stud positions: {king_stud_positions}")

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")
        
            print(f"Extracted opening data:")
            print(f"  opening_u_start: {opening_u_start}")
            print(f"  opening_width: {opening_width}")
            print(f"  opening_height: {opening_height}")
            print(f"  opening_v_start: {opening_v_start}")
            
            if None in (opening_u_start, opening_width, opening_height, opening_v_start):
                print("Missing required opening data")
                return None
            
            # Get essential parameters
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available")
                return None
                
            # Calculate header dimensions from framing parameters
            king_stud_offset = FRAMING_PARAMS.get("king_stud_offset", 1.5/12/2)
            header_width = FRAMING_PARAMS.get("header_depth", 5.5/12)  # Through wall thickness
            header_height = FRAMING_PARAMS.get("header_height", 7.0/12)  # Vertical dimension
            header_height_above_opening = FRAMING_PARAMS.get("header_height_above_opening", 0.0)    # Distance above opening
        
            print(f"Header dimensions:")
            print(f"  width: {header_width}")
            print(f"  height: {header_height}")
            print(f"  height_above_opening: {header_height_above_opening}")
            print(f"  king_stud_offset: {king_stud_offset}")
            
            # Calculate header position (top of opening + half header height)
            opening_v_end = opening_v_start + opening_height        
            header_v = opening_v_end + (header_height / 2) + header_height_above_opening
        
            print(f"Vertical position:")
            print(f"  opening_v_end: {opening_v_end}")
            print(f"  header_v: {header_v}")
            
            # Calculate header span
            if king_stud_positions:
                print("Using provided king stud positions for header")
                u_left, u_right = king_stud_positions
            
                # Check if these are centerlines or inner faces
                print(f"Raw king stud positions: u_left={u_left}, u_right={u_right}")
            
                # Adjust positions to use inner faces instead of centerlines
                inner_left = u_left + king_stud_offset
                inner_right = u_right - king_stud_offset
                print(f"  inner_left: {u_left} + {king_stud_offset} = {inner_left}")
                print(f"  inner_right: {u_right} - {king_stud_offset} = {inner_right}")            
                print(f"Adjusted for inner faces: u_left={inner_left}, u_right={inner_right}")
                
                # Use the adjusted positions
                u_left = inner_left
                u_right = inner_right
            else:
                # Calculate positions based on opening with offsets
                print("No king stud positions provided, calculating based on opening")
                trimmer_width = FRAMING_PARAMS.get("trimmer_width", 1.5/12)
                u_left = opening_u_start - trimmer_width
                u_right = opening_u_start + opening_width + trimmer_width
                print(f"Calculated positions: u_left={u_left}, u_right={u_right}")
        
                print(f"Final header span: u_left={u_left}, u_right={u_right}, width={u_right-u_left}")
            
            # 1. Create the centerline endpoints in world coordinates
            start_point = rg.Point3d.Add(
                base_plane.Origin, 
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_left),
                    rg.Vector3d.Multiply(base_plane.YAxis, header_v)
                )
            )
            
            end_point = rg.Point3d.Add(
                base_plane.Origin, 
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_right),
                    rg.Vector3d.Multiply(base_plane.YAxis, header_v)
                )
            )
        
            print(f"Header endpoints in world coordinates:")
            print(f"  start_point: {start_point}")
            print(f"  end_point: {end_point}")
            
            # Create the centerline as a curve
            centerline = rg.LineCurve(start_point, end_point)
            self.debug_geometry['curves'].append(centerline)
            
            # 2. Create a profile plane at the start point
            # Create vectors for the profile plane
            # X axis goes into the wall (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes up/down (for height)
            profile_y_axis = base_plane.YAxis
            
            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry['planes'].append(profile_plane)
            
            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-header_width/2, header_width/2),
                rg.Interval(-header_height/2, header_height/2)
            )
            
            profile_curve = profile_rect.ToNurbsCurve()
            self.debug_geometry['profiles'].append(profile_rect)
            
            # 4. Extrude the profile along the centerline
            # Calculate the vector from start to end
            extrusion_vector = rg.Vector3d(end_point - start_point)
            extrusion = rg.Extrusion.CreateExtrusion(profile_curve, extrusion_vector)
            
            print("===== END HEADER GENERATION DETAILS =====")
            
            # Convert to Brep and return
            if extrusion and extrusion.IsValid:
                return extrusion.ToBrep()
            else:
                print("Failed to create valid header extrusion")
                return None
                
        except Exception as e:
            print(f"Error generating header: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None

    def _generate_header_fallback(self, opening_data, king_stud_positions=None) -> Optional[rg.Brep]:
        """Fallback method for header generation when coordinate transformations fail."""
        try:
            print("Using fallback method for header generation")
            
            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")
            
            # Calculate header v-coordinate (top of opening)
            opening_v_end = opening_v_start + opening_height
            header_height = FRAMING_PARAMS.get("header_height", 1.5/12)
            header_depth = FRAMING_PARAMS.get("header_depth", 3.5/12)
            header_v = opening_v_end + header_height / 2
            header_height_above_opening = FRAMING_PARAMS.get("header_height_above_opening", 0.0)
            header_v = header_v + header_height_above_opening
        
            # Calculate positions based on opening with offsets
            trimmer_width = FRAMING_PARAMS.get("trimmer_width", 1.5/12)
            king_stud_offset = FRAMING_PARAMS.get("king_stud_offset", 1.5/12/2)
            
            # Get the base plane from wall data
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available for fallback header generation")
                return None
            
            # Calculate header center point (centered horizontally above the opening)
            header_center_u = opening_u_start + opening_width / 2
            header_center_v = header_v  # Center vertically above opening
            header_center = base_plane.PointAt(header_center_u, header_center_v, 0)
            
            # Create header length based on opening width plus some extension
            header_length = opening_width + trimmer_width + trimmer_width
            
            try:
                # Create box with proper orientation
                x_axis = base_plane.XAxis
                y_axis = base_plane.YAxis
                
                # Create a box plane centered on the header
                box_plane = rg.Plane(header_center, x_axis, y_axis)
                
                # Create the box with proper dimensions
                box = rg.Box(
                    box_plane,
                    rg.Interval(-header_length/2, header_length/2),  # Length along x-axis
                    rg.Interval(-header_height/2, header_height/2),    # Width into the wall
                    rg.Interval(-header_depth/2, header_depth/2)   # Height centered on header_center
                )
                
                # Convert to Brep
                if box and box.IsValid:
                    return box.ToBrep()
                else:
                    print("Created invalid box in fallback")
                    return None
            
            except Exception as e:
                print(f"Error in header fallback box creation: {str(e)}")
                return None
                
        except Exception as e:
            print(f"Error in header fallback: {str(e)}")
            return None