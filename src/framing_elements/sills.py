# File: src/framing_elements/sills.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.utils.coordinate_systems import WallCoordinateSystem, FramingElementCoordinates
from src.framing_elements.sill_parameters import SillParameters
from src.config.framing import FRAMING_PARAMS

class SillGenerator:
    """
    Generates sill framing elements below window openings.
    
    Sills are horizontal members that provide support at the bottom of window openings.
    This class handles the positioning, sizing, and geometric creation of sill elements.
    """
    
    def __init__(
        self,
        wall_data: Dict[str, Any],
        coordinate_system: Optional[WallCoordinateSystem] = None
    ):
        """
        Initialize the sill generator with wall data and coordinate system.
        
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
    
    def generate_sill(
        self,
        opening_data: Dict[str, Any],
        king_stud_positions: Optional[Tuple[float, float]] = None
    ) -> Optional[rg.Brep]:
        """
        Generate a sill for a window opening.
        
        This method creates a sill based on:
        1. The opening data for positioning and dimensions
        2. Optional king stud positions for span length
        3. Wall type for appropriate profile selection
        
        The method only creates sills for window openings, not for doors.
        
        Args:
            opening_data: Dictionary with opening information
            king_stud_positions: Optional tuple of (left, right) u-coordinates
                                 If not provided, calculated from opening width
                                 plus configured offsets
        
        Returns:
            Sill geometry as a Rhino Brep, or None for door openings
        """
        try:
            # Only create sills for windows, not doors
            if opening_data["opening_type"].lower() != "window":
                return None
            
            # Only create sills for windows, not doors
            if opening_data["opening_type"].lower() != "window":
                return None
                
            # Extract opening information
            opening_u_start = opening_data["start_u_coordinate"]
            opening_width = opening_data["rough_width"]
            opening_v_start = opening_data["base_elevation_relative_to_wall_base"]
            
            # Calculate sill v-coordinate (bottom of opening)
            sill_v = opening_v_start
            
            # Calculate sill u-coordinates (from king studs or derived from opening)
            if king_stud_positions:
                u_left, u_right = king_stud_positions
            else:
                # Calculate positions based on opening with offsets
                trimmer_offset = FRAMING_PARAMS.get("trimmer_offset", 0.5/12)
                king_stud_offset = FRAMING_PARAMS.get("king_stud_offset", 0.5/12)
                stud_width = FRAMING_PARAMS.get("stud_width", 1.5/12)
                
                # Calculate stud centers
                u_left = opening_u_start - trimmer_offset - king_stud_offset - stud_width/2
                u_right = opening_u_start + opening_width + trimmer_offset + king_stud_offset + stud_width/2
                
                # Store these calculated points for visualization
                left_point = self.coordinate_system.wall_to_world(u_left, sill_v, 0)
                right_point = self.coordinate_system.wall_to_world(u_right, sill_v, 0)
                self.debug_geometry['points'].extend([left_point, right_point])
            
            # Create sill parameters based on wall type
            sill_params = SillParameters.from_wall_type(
                self.wall_data["wall_type"],
                opening_width
            )
            
            # Create coordinates for the sill
            # Sill is BELOW the opening, so v_end is at opening bottom and v_start is below that
            sill_coords = FramingElementCoordinates(
                u_start=u_left,
                u_end=u_right,
                v_start=sill_v - sill_params.height,  # Sill extends downward from opening bottom
                v_end=sill_v,
                coordinate_system=self.coordinate_system
            )
            
            # Extract visualization geometry
            viz_geom = sill_coords.get_debug_geometry()
            self.debug_geometry['curves'].append(viz_geom['centerline'])
            self.debug_geometry['curves'].append(viz_geom['boundary'])
            self.debug_geometry['points'].extend(viz_geom['corners'])
            self.debug_geometry['planes'].append(viz_geom['profile_plane'])
            
            # Get the profile plane for proper orientation
            profile_plane = sill_coords.get_profile_plane()

            # Add this before creating the Rectangle3d
            if profile_plane is None:
                print("Profile plane is null, using fallback approach for sill")
                return self._generate_sill_fallback(opening_data, king_stud_positions)
            
            # Create the sill profile as a rectangle
            sill_profile = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-sill_params.width/2, sill_params.width/2),
                rg.Interval(-sill_params.thickness/2, sill_params.thickness/2)
            )
            self.debug_geometry['profiles'].append(sill_profile)
            
            # Create the extrusion path
            centerline = sill_coords.get_centerline()
            
            # Create the extrusion
            profile_curve = sill_profile.ToNurbsCurve()
            extrusion = rg.Extrusion.CreateExtrusion(
                profile_curve,
                rg.Vector3d(centerline.PointAtEnd - centerline.PointAtStart)
            )
            
            # Convert to Brep and return
            sill_brep = extrusion.ToBrep()
            
            return sill_brep
        except Exception as e:
            print(f"Error generating sill: {str(e)}")
            return self._generate_sill_fallback(opening_data, king_stud_positions)
    
    def _generate_sill_fallback(self, opening_data, king_stud_positions=None) -> Optional[rg.Brep]:
        """Fallback method for sill generation when coordinate transformations fail."""
        try:
            # Only create sills for windows, not doors
            if opening_data["opening_type"].lower() != "window":
                return None
                
            print("Using fallback method for sill generation")
            
            # Extract opening information
            opening_u_start = opening_data["start_u_coordinate"]
            opening_width = opening_data["rough_width"]
            opening_v_start = opening_data["base_elevation_relative_to_wall_base"]
            
            # Get the base plane from wall data
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available for fallback sill generation")
                return None
                
            # Get sill dimensions
            sill_height = 0.25  # Default height (3 inches)
            sill_width = 0.292  # Default width (3.5 inches)
            
            # Calculate sill center point (centered horizontally below the opening)
            sill_center_u = opening_u_start + opening_width / 2
            sill_center_v = opening_v_start - sill_height / 2  # Center vertically below the opening
            sill_center = base_plane.PointAt(sill_center_u, sill_center_v, 0)
            
            # Create sill length based on opening width plus some extension
            sill_length = opening_width + 0.5  # Add 6 inches total (3 on each side)
            
            try:
                # Create box with proper orientation
                x_axis = base_plane.XAxis
                y_axis = base_plane.YAxis
                
                # Create a box plane centered on the sill
                box_plane = rg.Plane(sill_center, x_axis, y_axis)
                
                # Create the box with proper dimensions
                box = rg.Box(
                    box_plane,
                    rg.Interval(-sill_length/2, sill_length/2),  # Length along x-axis
                    rg.Interval(-sill_width/2, sill_width/2),    # Width into the wall
                    rg.Interval(-sill_height/2, sill_height/2)   # Height centered on sill_center
                )
                
                # Convert to Brep
                if box and box.IsValid:
                    return box.ToBrep()
                else:
                    print("Created invalid box in fallback")
                    return None
            
            except Exception as e:
                print(f"Error in sill fallback box creation: {str(e)}")
                return None
                
        except Exception as e:
            print(f"Error in sill fallback: {str(e)}")
            return None