# File: src/framing_elements/trimmers.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.config.framing import FRAMING_PARAMS

class TrimmerGenerator:
    """
    Generates trimmer studs for wall openings.
    
    Trimmer studs are vertical framing members placed directly alongside door and 
    window openings. They support the header above the opening and transfer loads 
    from the header to the bottom plate. Trimmers typically run from the bottom plate 
    to the underside of the header, working in tandem with king studs that run the 
    full height of the wall.
    """
    
    def __init__(
        self,
        wall_data: Dict[str, Any]
    ):
        """
        Initialize the trimmer generator with wall data.
        
        Args:
            wall_data: Dictionary containing wall information including:
                - base_plane: Reference plane for wall coordinate system
                - wall_base_elevation: Base elevation of the wall
                - wall_top_elevation: Top elevation of the wall
        """
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data
        
        # Initialize storage for debug geometry
        self.debug_geometry = {
            'points': [],
            'planes': [],
            'profiles': [],
            'paths': []
        }
    
    def generate_trimmers(
        self,
        opening_data: Dict[str, Any],
        plate_data: Dict[str, float],
        header_bottom_elevation: Optional[float] = None
    ) -> List[rg.Brep]:
        """
        Generate trimmer studs for a wall opening.
        
        This method creates a pair of trimmer studs at the sides of an opening.
        Trimmers run from the bottom plate to the underside of the header,
        providing support for the header and transferring loads around the opening.
        
        Args:
            opening_data: Dictionary with opening information including:
                - start_u_coordinate: Position along wall where opening starts
                - rough_width: Width of the rough opening
                - base_elevation_relative_to_wall_base: Height from wall base to opening bottom
            plate_data: Dictionary containing plate boundary data from get_boundary_data()
            header_bottom_elevation: Optional elevation for the bottom of the header
                If not provided, calculated from opening height
        
        Returns:
            List of trimmer stud Brep geometries (typically two - left and right)
        """
        try:
            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")
            
            if None in (opening_u_start, opening_width, opening_height, opening_v_start):
                print("Missing required opening data")
                return []
            
            # Get essential wall parameters
            base_plane = self.wall_data.get("base_plane")
            
            # Get bottom elevation from plate boundary data
            bottom_elevation = plate_data.get("boundary_elevation", 0.0)
            print(f"Using bottom plate elevation: {bottom_elevation}")
            
            if base_plane is None:
                print("No base plane available")
                return []
                
            # Calculate trimmer dimensions from framing parameters
            trimmer_width = FRAMING_PARAMS.get("trimmer_width", 1.5/12)   # Typically 1.5 inches
            trimmer_depth = FRAMING_PARAMS.get("trimmer_depth", 3.5/12)   # Typically 3.5 inches
            
            # Calculate header bottom elevation if not provided
            opening_v_end = opening_v_start + opening_height
            header_bottom = header_bottom_elevation if header_bottom_elevation is not None else opening_v_end
            
            # Calculate trimmer vertical extent
            bottom_v = bottom_elevation # Start at bottom plate
            top_v = header_bottom  # End at underside of header
            
            # Calculate horizontal positions with offset from opening edges
            # Typically trimmers are centered at the rough opening edges
            trimmer_offset = trimmer_width / 2  # Center the trimmer at the opening edge
            
            # Calculate actual u-coordinates for left and right trimmers
            u_left = opening_u_start - trimmer_offset
            u_right = opening_u_start + opening_width + trimmer_offset
            
            # Store trimmer studs
            trimmer_studs = []
            
            # Generate both left and right trimmers
            for u_position in [u_left, u_right]:
                try:
                    # Create the trimmer stud
                    trimmer = self._create_trimmer_geometry(
                        base_plane, 
                        u_position, 
                        bottom_v, 
                        top_v, 
                        trimmer_width, 
                        trimmer_depth
                    )
                    
                    if trimmer is not None:
                        trimmer_studs.append(trimmer)
                except Exception as e:
                    print(f"Error creating trimmer at u={u_position}: {str(e)}")
            
            return trimmer_studs
                
        except Exception as e:
            print(f"Error generating trimmers: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []
    
    def _create_trimmer_geometry(
        self,
        base_plane: rg.Plane,
        u_coordinate: float,
        bottom_v: float,
        top_v: float,
        width: float,
        depth: float
    ) -> Optional[rg.Brep]:
        """
        Create the geometry for a single trimmer stud.
        
        This method creates a trimmer stud by:
        1. Creating start and end points in the wall's coordinate system
        2. Creating a profile perpendicular to the stud's centerline
        3. Extruding the profile along the centerline
        
        Args:
            base_plane: Wall's base plane for coordinate system
            u_coordinate: Position along wall (horizontal)
            bottom_v: Bottom elevation of trimmer
            top_v: Top elevation of trimmer
            width: Width of trimmer (perpendicular to wall face)
            depth: Depth of trimmer (parallel to wall length)
            
        Returns:
            Brep geometry for the trimmer stud, or None if creation fails
        """
        try:
            # 1. Create the centerline endpoints in world coordinates
            start_point = rg.Point3d.Add(
                base_plane.Origin, 
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_coordinate),
                    rg.Vector3d.Multiply(base_plane.YAxis, bottom_v)
                )
            )
            
            end_point = rg.Point3d.Add(
                base_plane.Origin, 
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_coordinate),
                    rg.Vector3d.Multiply(base_plane.YAxis, top_v)
                )
            )
            
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
                return extrusion.ToBrep()
            else:
                print("Failed to create valid trimmer extrusion")
                return None
                
        except Exception as e:
            print(f"Error creating trimmer geometry: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None