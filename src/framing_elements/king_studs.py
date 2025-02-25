# File: src/framing_elements/king_studs.py

from typing import Dict, List, Any, Tuple
import Rhino.Geometry as rg
from .plate_geometry import PlateGeometry
from src.config.framing import FRAMING_PARAMS
from src.framing_elements.framing_geometry import create_stud_profile

def debug_stud_position(base_plane: rg.Plane, u_coord: float, stud_depth: float):
    """Helps visualize and verify stud positioning relative to openings."""
    inner_face = base_plane.PointAt(u_coord + stud_depth/2, 0, 0)
    outer_face = base_plane.PointAt(u_coord - stud_depth/2, 0, 0)
    center = base_plane.PointAt(u_coord, 0, 0)
    
    print(f"\nStud position check:")
    print(f"- Center: {center}")
    print(f"- Inner face: {inner_face}")
    print(f"- Outer face: {outer_face}")

def create_king_studs(
    wall_data: Dict[str, Any],
    opening_data: Dict[str, Any],
    plate_data: Dict[str, float],
    framing_params: Dict[str, Any]
) -> Tuple[List[rg.Brep], Dict[str, List[rg.GeometryBase]]]:
    """
    Creates king studs with debug geometry.
    
    Returns a tuple of:
    - List of king stud Breps
    - Dictionary of debug geometry containing:
        - points: List[rg.Point3d]
        - planes: List[rg.Plane]
        - profiles: List[rg.Rectangle3d]
        - paths: List[rg.Curve]
    """
    # Initialize debug geometry collections
    debug_geom = {
        'points': [],
        'planes': [],
        'profiles': [],
        'paths': []
    }
    
    try:
        # Get base geometry and parameters
        base_plane = wall_data["base_plane"]
        debug_geom['planes'].append(base_plane)
        
        # Extract dimensions
        stud_width = framing_params.get("stud_width", 1.5/12)
        stud_depth = framing_params.get("stud_depth", 3.5/12)
        trimmer_width = framing_params.get("trimmer_width", 3.5/12)
        king_stud_width = framing_params.get("king_stud_width", 3.5/12)
        
        print("\nDimensions:")
        print(f"  Stud width: {stud_width}")
        print(f"  Stud depth: {stud_depth}")
        print(f"  Trimmer width: {trimmer_width}")
        print(f"  King stud offset: {king_stud_width}")
        
        # Get elevations
        bottom_elevation = plate_data["bottom_plate_elevation"]
        top_elevation = plate_data["top_elevation"]
        
        print("\nElevations:")
        print(f"  Bottom: {bottom_elevation}")
        print(f"  Top: {top_elevation}")
        
        # 3. Calculate horizontal positions
        opening_start = opening_data["start_u_coordinate"]
        opening_width = opening_data["rough_width"]
        
        left_u = opening_start - (trimmer_width + king_stud_width)
        right_u = opening_start + opening_width + trimmer_width + king_stud_width

        # Print the calculated positions
        print("\nPosition calculations:")
        print(f"Opening start: {opening_start}")
        print(f"Opening width: {opening_width}")
        print(f"Trimmer offset: {trimmer_width}")
        print(f"King stud offset: {king_stud_width}")
        print(f"Left king stud position: {left_u}")
        print(f"Right king stud position: {right_u}")
        
        # 4. Create points using the wall's coordinate system
        stud_points = []
        for u_coord in [left_u, right_u]:
            # Create bottom point
            print(f"\nCreating points for u_coord = {u_coord}:")
            bottom = base_plane.PointAt(
                u_coord,               # X - Position along wall
                bottom_elevation,      # Z - Height from base
                0                      # Y - Center in wall thickness
            )
            debug_geom['points'].append(bottom)
            print(f"Resulting point: X={bottom.X}, Y={bottom.Y}, Z={bottom.Z}")
            print(f"Base plane origin: X={base_plane.Origin.X}, Y={base_plane.Origin.Y}, Z={base_plane.Origin.Z}")
            print(f"Base plane X axis: X={base_plane.XAxis.X}, Y={base_plane.XAxis.Y}, Z={base_plane.XAxis.Z}")
            
            # Create top point
            top = base_plane.PointAt(
                u_coord,               # X - Same position along wall
                top_elevation,         # Z - Height at top
                0                      # Y - Center in wall thickness
            )
            debug_geom['points'].append(top)
            
            # Create path line for visualization
            path_line = rg.Line(bottom, top)
            debug_geom['paths'].append(path_line)
            
            stud_points.append((bottom, top))
        
        # 5. Generate king stud geometry
        king_studs = []
        for bottom, top in stud_points:
            try:
                # Calculate path vector
                path_vector = top - bottom
                path_length = path_vector.Length
                
                # Create profile plane
                stud_plane = rg.Plane(
                    bottom,                    
                    base_plane.XAxis,               
                    base_plane.ZAxis * (-1)         
                )
                debug_geom['planes'].append(stud_plane)
                
                # Create profile
                profile = create_stud_profile(
                    bottom,
                    stud_plane,
                    stud_width,
                    stud_depth
                )
                debug_geom['profiles'].append(profile)
                
                profile_curve = profile.ToNurbsCurve()
                
                # Create extrusion
                extrusion = rg.Extrusion.Create(
                    profile_curve,
                    path_length,
                    True
                )

                king_stud = extrusion.ToBrep(True)
                if king_stud:
                    king_studs.append(king_stud)
            
            except Exception as e:
                print(f"Error creating king stud: {str(e)}")
                
        return king_studs, debug_geom
        
    except Exception as e:
        print(f"\nError in create_king_studs: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return [], debug_geom

class KingStudGenerator:
    """
    Generates king studs for wall openings based on plate boundaries.
    
    This class coordinates the creation of king studs by:
    1. Using plate geometry to establish vertical bounds
    2. Using opening data to determine horizontal positions
    3. Generating the actual stud geometry with proper profiles
    """
    
    def __init__(
        self,
        wall_data: Dict[str, Any],
        bottom_plate: PlateGeometry,
        top_plate: PlateGeometry
    ):
        self.wall_data = wall_data
        self.bottom_plate = bottom_plate
        self.top_plate = top_plate
        self.king_studs_cache = {}
        
    def generate_king_studs(self, opening_data: Dict[str, Any]) -> List[rg.Brep]:
        """Generates king studs for a given opening with detailed debug info."""
        # Get boundary data from both plates
        bottom_data = self.bottom_plate.get_boundary_data()
        top_data = self.top_plate.get_boundary_data()
        
        print("\nPlate boundary data:")
        print("Bottom plate:")
        print(f"  Reference elevation: {bottom_data['reference_elevation']}")
        print(f"  Boundary elevation: {bottom_data['boundary_elevation']}")
        print(f"  Thickness: {bottom_data['thickness']}")
        print("Top plate:")
        print(f"  Reference elevation: {top_data['reference_elevation']}")
        print(f"  Boundary elevation: {top_data['boundary_elevation']}")
        print(f"  Thickness: {top_data['thickness']}")
        
        # Create plate data dictionary with the correct keys
        plate_data = {
            "bottom_plate_elevation": bottom_data["boundary_elevation"],
            "top_elevation": top_data["reference_elevation"],  # Changed from boundary_elevation
            "plate_thickness": bottom_data["thickness"]
        }
        
        print("\nOpening data:")
        print(f"  {opening_data}")
        
        # Initialize debug geometry storage
        self.debug_geometry = {
            'points': [],
            'planes': [],
            'profiles': [],
            'paths': []
        }
        
        # Generate king studs with debug geometry
        king_studs, debug_geom = create_king_studs(
            self.wall_data,
            opening_data,
            plate_data,
            FRAMING_PARAMS
        )
        
        # Store debug geometry
        self.debug_geometry.update(debug_geom)
        
        # Log what we created
        print(f"\nDebug geometry generated:")
        print(f"  Points: {len(self.debug_geometry['points'])}")
        print(f"  Planes: {len(self.debug_geometry['planes'])}")
        print(f"  Profiles: {len(self.debug_geometry['profiles'])}")
        print(f"  Paths: {len(self.debug_geometry['paths'])}")
        
        return king_studs