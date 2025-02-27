# File: src/framing_elements/headers.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.utils.coordinate_systems import WallCoordinateSystem, FramingElementCoordinates
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
        wall_data: Dict[str, Any],
        coordinate_system: Optional[WallCoordinateSystem] = None
    ):
        """
        Initialize the header generator with wall data and coordinate system.
        
        Args:
            wall_data: Dictionary containing wall information
            coordinate_system: Optional coordinate system for transformations
        """
        self.wall_data = wall_data
        
        # Create coordinate system if not provided
        self.coordinate_system = coordinate_system or WallCoordinateSystem(wall_data)
        
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
            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")
            
            # Validate required data
            if None in (opening_u_start, opening_width, opening_height, opening_v_start):
                print("Missing required opening data, using fallback")
                return self._generate_header_fallback(opening_data, king_stud_positions)
            
            # Calculate header v-coordinate (top of opening)
            opening_v_end = opening_v_start + opening_height
            header_height = FRAMING_PARAMS.get("header_height", 1.5/12)
            header_v = opening_v_end + header_height / 2
            header_height_above_opening = FRAMING_PARAMS.get("header_height_above_opening", 0.0)
            header_v = header_v + header_height_above_opening
            
            # Calculate header u-coordinates (from king studs or derived from opening)
            if king_stud_positions:
                u_left, u_right = king_stud_positions
            else:
                # Calculate positions based on opening with offsets
                trimmer_width = FRAMING_PARAMS.get("trimmer_width", 1.5/12)
                king_stud_offset = FRAMING_PARAMS.get("king_stud_offset", 1.5/12/2)
                
                # Calculate stud centers
                u_left = opening_u_start - trimmer_width
                u_right = opening_u_start + opening_width + trimmer_width + king_stud_offset
                
                # Store these calculated points for visualization
                try:
                    left_point = self.coordinate_system.wall_to_world(u_left, header_v, 0)
                    right_point = self.coordinate_system.wall_to_world(u_right, header_v, 0)
                    
                    if left_point and right_point:
                        self.debug_geometry['points'].extend([left_point, right_point])
                except Exception as e:
                    print(f"Error creating debug points: {str(e)}")
            
            # Create header parameters based on wall type
            try:
                header_params = HeaderParameters.from_wall_type(
                    self.wall_data.get("wall_type", "2x4"),
                    opening_height
                )
            except Exception as e:
                print(f"Error creating header parameters: {str(e)}")
                return self._generate_header_fallback(opening_data, king_stud_positions)
            
            # Create coordinates for the header
            try:
                header_coords = FramingElementCoordinates(
                    u_start=u_left,
                    u_end=u_right,
                    v_start=header_v,
                    v_end=header_v,
                    w_center=0.0,
                    coordinate_system=self.coordinate_system
                )
                
                # Extract visualization geometry
                viz_geom = header_coords.get_debug_geometry()
                
                if 'centerline' in viz_geom and viz_geom['centerline']:
                    self.debug_geometry['curves'].append(viz_geom['centerline'])
                    
                if 'boundary' in viz_geom and viz_geom['boundary']:
                    self.debug_geometry['curves'].append(viz_geom['boundary'])
                    
                if 'corners' in viz_geom and viz_geom['corners']:
                    self.debug_geometry['points'].extend(viz_geom['corners'])
                    
                if 'profile_plane' in viz_geom and viz_geom['profile_plane']:
                    self.debug_geometry['planes'].append(viz_geom['profile_plane'])
                    
                # Get the profile plane for proper orientation
                profile_plane = header_coords.get_profile_plane()
                
                # If we don't have a valid profile plane, use fallback
                if profile_plane is None:
                    print("Profile plane is null, using fallback approach")
                    return self._generate_header_fallback(opening_data, king_stud_positions)
                    
                # Create the header profile as a rectangle
                header_profile = rg.Rectangle3d(
                    profile_plane,
                    rg.Interval(-header_params.width/2, header_params.width/2),
                    rg.Interval(-header_params.thickness/2, header_params.thickness/2)
                )
                
                self.debug_geometry['profiles'].append(header_profile)
                
                # Create the extrusion path
                centerline = header_coords.get_centerline()
                
                if centerline is None:
                    print("Centerline is null, using fallback approach")
                    return self._generate_header_fallback(opening_data, king_stud_positions)
                    
                # Create the extrusion
                profile_curve = header_profile.ToNurbsCurve()
                vector = rg.Vector3d(centerline.PointAtEnd - centerline.PointAtStart)
                
                extrusion = rg.Extrusion.CreateExtrusion(profile_curve, vector)
                
                # Convert to Brep and return
                if extrusion:
                    header_brep = extrusion.ToBrep()
                    return header_brep
                else:
                    print("Failed to create header extrusion, using fallback")
                    return self._generate_header_fallback(opening_data, king_stud_positions)
                    
            except Exception as e:
                print(f"Error creating header geometry: {str(e)}")
                return self._generate_header_fallback(opening_data, king_stud_positions)
                
        except Exception as e:
            print(f"Error generating header: {str(e)}")
            return self._generate_header_fallback(opening_data, king_stud_positions)
    
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