# File: src/utils/coordinate_systems.py

import Rhino.Geometry as rg
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass

class WallCoordinateSystem:
    """
    Manages transformations between wall-local coordinates and world coordinates.
    
    The wall coordinate system uses these axes:
    - U-axis: Along the wall length (wall_base_curve direction)
    - V-axis: Vertical direction (perpendicular to base plane)
    - W-axis: Through wall thickness (normal to wall face)
    
    This class handles conversions in both directions and maintains debugging
    geometry for visualization of the coordinate system.
    """
    
    def __init__(self, wall_data: Dict[str, Any]):
        """
        Initialize the coordinate system from wall data.
        
        Args:
            wall_data: Wall data dictionary containing:
                - base_plane: rg.Plane for orientation
                - wall_base_curve: rg.Curve representing wall baseline
                - wall_base_elevation: Base elevation
        """
        # Initialize with safe defaults
        self.base_plane = None
        self.wall_curve = None
        self.base_elevation = 0.0
        self.top_elevation = 0.0
        self._to_world_transform = None
        self._to_wall_transform = None
        self.debug_geometry = {
            'axes': [],
            'grid': [],
            'origin': None
        }
        
        # Add this to track initialization status
        self.initialization_failed = False

        try:
            # Extract required data from wall_data
            self.base_plane = wall_data.get("base_plane")
            self.wall_curve = wall_data.get("wall_base_curve")
            self.base_elevation = wall_data.get("wall_base_elevation", 0.0)
            self.top_elevation = wall_data.get("wall_top_elevation", 0.0)
            
            # Validate inputs
            if self.base_plane is None:
                print("Warning: base_plane is None in wall_data")
                self.initialization_failed = True 
                return
            if self.wall_curve is None:
                print("Warning: wall_base_curve is None in wall_data")
                self.initialization_failed = True
                return
                
            print(f"Initializing WallCoordinateSystem with valid base plane and curve")
            
            # Create transformations
            try:
                self._to_world_transform = self._compute_to_world_transform()
                if self._to_world_transform is None or not self._to_world_transform.IsValid:
                    print("Warning: Failed to create valid to-world transform")
                    self.initialization_failed = True
                    return
                    
                self._to_wall_transform = self._compute_to_wall_transform()
                if self._to_wall_transform is None or not self._to_wall_transform.IsValid:
                    print("Warning: Failed to create valid to-wall transform")
                    self.initialization_failed = True
                    return
            except Exception as e:
                print(f"Error computing transformations: {str(e)}")
                self.initialization_failed = True
                return
                
            # Now create debug geometry ONLY if we have valid transforms
            self.debug_geometry['origin'] = self.base_plane.Origin
            
            # Create axes visualization
            try:
                self.debug_geometry['axes'] = self._create_axes_visualization()
                print(f"Created {len(self.debug_geometry['axes'])} axis lines")
            except Exception as e:
                print(f"Error creating axes visualization: {str(e)}")
                # Note: Not setting initialization_failed here since this is non-critical
                
            # Skip grid visualization - it's causing problems
            # It's better to just disable it for now
            self.debug_geometry['grid'] = []
                
        except Exception as e:
            print(f"Error initializing WallCoordinateSystem: {str(e)}")
            import traceback
            print(traceback.format_exc())
            self.initialization_failed = True
    
    def _compute_to_world_transform(self) -> Optional[rg.Transform]:
        """Compute transformation matrix from wall to world coordinates."""
        try:
            # Create a transformation from wall coordinates to world coordinates
            transform = rg.Transform.PlaneToPlane(
                rg.Plane.WorldXY,  # Source plane (wall coordinates)
                self.base_plane    # Target plane (world coordinates)
            )
            
            if transform is None or not transform.IsValid:
                print("Warning: Created invalid wall-to-world transform")
                return None
                
            print(f"Created wall-to-world transform. Valid: {transform.IsValid}")
            return transform
        except Exception as e:
            print(f"Error computing wall-to-world transform: {str(e)}")
            return None
    
    def is_valid(self) -> bool:
        """
        Check if the coordinate system is fully initialized and operational.
        
        This method performs comprehensive validation to ensure the coordinate
        system can reliably transform points between wall and world coordinates.
        
        Returns:
            bool: True if all required components are valid and working
        """
        # First check if initialization was explicitly marked as failed
        if self.initialization_failed:
            return False
            
        # Then check if all required components exist
        if not (self.base_plane is not None and 
                self.wall_curve is not None and
                self._to_world_transform is not None and 
                self._to_wall_transform is not None):
            return False
            
        # Check if transforms are valid
        if not (self._to_world_transform.IsValid and 
                self._to_wall_transform.IsValid):
            return False
            
        # Perform a practical test: try to transform a point
        test_point = rg.Point3d(0, 0, 0)  # Origin in wall coordinates
        test_copy = rg.Point3d(test_point)
        
        # Test if transformation works in practice
        transformation_works = test_copy.Transform(self._to_world_transform)
        
        # If transformation fails, log detailed information
        if not transformation_works:
            print("Coordinate system validation: transformation test failed")
            print(f"  base_plane origin: {self.base_plane.Origin}")
            print(f"  base_plane X-axis: {self.base_plane.XAxis}")
            print(f"  base_plane Y-axis: {self.base_plane.YAxis}")
            return False
            
        return True
    
    def _compute_to_wall_transform(self) -> Optional[rg.Transform]:
        """Compute transformation matrix from world to wall coordinates."""
        try:
            # Create a transformation from world coordinates to wall coordinates
            transform = rg.Transform.PlaneToPlane(
                self.base_plane,   # Source plane (world coordinates)
                rg.Plane.WorldXY   # Target plane (wall coordinates)
            )
            
            if transform is None or not transform.IsValid:
                print("Warning: Created invalid world-to-wall transform")
                return None
                
            print(f"Created world-to-wall transform. Valid: {transform.IsValid}")
            return transform
        except Exception as e:
            print(f"Error computing world-to-wall transform: {str(e)}")
            return None
    
    def wall_to_world(self, u: float, v: float, w: float = 0.0) -> Optional[rg.Point3d]:
        """
        Convert wall coordinates (u,v,w) to world coordinates with improved robustness.
        
        Args:
            u: Position along wall length
            v: Height from wall base
            w: Depth through wall thickness (default 0 = wall center)
            
        Returns:
            Point in world coordinates, or None if transformation fails
        """
        try:
            # Check for invalid transforms or numerically problematic geometry
            transform_valid = (self._to_world_transform is not None and 
                            self._to_world_transform.IsValid)
            
            # Check for numerically problematic base plane (new condition)
            potentially_unstable = False
            if self.base_plane is not None:
                potentially_unstable = (abs(self.base_plane.XAxis.X) < 1e-10 or 
                                    abs(self.base_plane.YAxis.Y) < 1e-10)
                
            # Use direct point_at approach if transform is invalid or potentially unstable
            if not transform_valid or potentially_unstable:
                if not transform_valid:
                    print(f"Transform invalid for u={u}, v={v}, w={w} - using point_at method")
                elif potentially_unstable:
                    print(f"Potentially unstable geometry for u={u}, v={v}, w={w} - using point_at method")
                    
                direct_point = self.point_at(u, v, w)
                if direct_point is None:
                    print(f"  point_at also failed - base_plane is {self.base_plane is not None}")
                return direct_point
                
            # Standard transformation path when transform is valid and geometry is stable
            wall_point = rg.Point3d(u, v, w)
            world_point = rg.Point3d(wall_point)
            
            # Attempt the transformation
            if not world_point.Transform(self._to_world_transform):
                print(f"Point transformation failed for u={u}, v={v}, w={w} - falling back to point_at")
                return self.point_at(u, v, w)  # Fall back to direct method if transform fails
                
            return world_point
            
        except Exception as e:
            print(f"Error in wall_to_world for u={u}, v={v}, w={w}: {str(e)}")
            return self.point_at(u, v, w)  # Final fallback using direct method
    
    def world_to_wall(self, point: rg.Point3d) -> Optional[Tuple[float, float, float]]:
        """
        Convert world coordinates to wall coordinates (u,v,w).
        
        Args:
            point: Point in world coordinates
            
        Returns:
            Tuple of (u, v, w) coordinates in wall space
        """
        try:
            # Validate transform and point
            if self._to_wall_transform is None or not self._to_wall_transform.IsValid:
                print(f"Cannot transform point: invalid world-to-wall transform")
                return None
                
            if point is None:
                print(f"Cannot transform None point")
                return None
            
            # Make a copy to transform
            wall_point = rg.Point3d(point)
            
            # Transform the point
            if not wall_point.Transform(self._to_wall_transform):
                print(f"World-to-wall transformation failed for point {point}")
                return None
                
            # Return as tuple
            return wall_point.X, wall_point.Y, wall_point.Z
            
        except Exception as e:
            print(f"Error in world_to_wall: {str(e)}")
            return None
        
    def create_wall_plane(self, 
                         u: float, 
                         v: float,
                         normal_dir: str = "w") -> Optional[rg.Plane]:
        """
        Create a plane at the specified wall coordinates.
        
        This is useful for creating properly oriented profiles for
        framing elements at specific positions along the wall.
        
        Args:
            u: Position along wall length
            v: Height from wall base
            normal_dir: Direction for plane normal ('u', 'v', or 'w')
                        Defaults to 'w' (through wall thickness)
            
        Returns:
            Oriented plane in world coordinates
        """
        try:
            # Get the origin in world coordinates
            origin = self.wall_to_world(u, v, 0)
            if origin is None:
                print(f"Failed to get origin point at u={u}, v={v}")
                return None
            
            # Set up axes based on requested normal direction
            if normal_dir == "u":
                # Normal along wall length (for end cuts)
                x_axis = self.base_plane.YAxis  # v-direction
                y_axis = self.base_plane.ZAxis  # w-direction
            elif normal_dir == "v":
                # Normal in vertical direction (for horizontal elements)
                x_axis = self.base_plane.XAxis  # u-direction
                y_axis = self.base_plane.ZAxis  # w-direction
            else:  # "w" - default
                # Normal through wall thickness (for vertical elements)
                x_axis = self.base_plane.XAxis  # u-direction
                y_axis = self.base_plane.YAxis  # v-direction
            
            # Create the plane
            return rg.Plane(origin, x_axis, y_axis)
            
        except Exception as e:
            print(f"Error creating wall plane at u={u}, v={v}: {str(e)}")
            return None
    
    def _create_axes_visualization(self) -> List[rg.Curve]:
        """Create visualization curves for the coordinate axes."""
        curves = []
        try:
            if self.base_plane is None:
                return curves
                
            origin = self.base_plane.Origin
            scale = 1.0  # 1-foot axes
            
            # Create axes showing the coordinate system
            u_axis = rg.LineCurve(origin, origin + self.base_plane.XAxis * scale)
            v_axis = rg.LineCurve(origin, origin + self.base_plane.YAxis * scale)
            w_axis = rg.LineCurve(origin, origin + self.base_plane.ZAxis * scale)
            
            if u_axis is not None: curves.append(u_axis)
            if v_axis is not None: curves.append(v_axis)
            if w_axis is not None: curves.append(w_axis)
            
        except Exception as e:
            print(f"Error creating axes visualization: {str(e)}")
            
        return curves
    
    def _create_grid_visualization(self, 
                                u_divisions: int = 5, 
                                v_divisions: int = 3) -> List[rg.Curve]:
        """Create a grid visualization for the wall coordinate system."""
        curves = []
        try:
            # Get wall dimensions and validate them
            wall_length = self.wall_curve.GetLength()
            wall_height = self.top_elevation - self.base_elevation
            
            # Safety check - make sure dimensions are valid
            if wall_length <= 0 or wall_height <= 0:
                print(f"Warning: Invalid wall dimensions for grid visualization. Length: {wall_length}, Height: {wall_height}")
                return curves
                
            print(f"Creating grid visualization for wall: Length={wall_length}, Height={wall_height}")
            
            # Create u-lines (vertical)
            for i in range(u_divisions + 1):
                u = (i / u_divisions) * wall_length
                try:
                    start = self.wall_to_world(u, 0, 0)
                    end = self.wall_to_world(u, wall_height, 0)
                    
                    # Safety check - make sure points are valid
                    if start is not None and end is not None:
                        curves.append(rg.LineCurve(start, end))
                        print(f"  Created vertical grid line at u={u}")
                    else:
                        print(f"  Warning: Invalid points for vertical grid line at u={u}")
                except Exception as e:
                    print(f"  Error creating vertical grid line at u={u}: {str(e)}")
            
            # Create v-lines (horizontal)
            for i in range(v_divisions + 1):
                v = (i / v_divisions) * wall_height
                try:
                    start = self.wall_to_world(0, v, 0)
                    end = self.wall_to_world(wall_length, v, 0)
                    
                    # Safety check - make sure points are valid
                    if start is not None and end is not None:
                        curves.append(rg.LineCurve(start, end))
                        print(f"  Created horizontal grid line at v={v}")
                    else:
                        print(f"  Warning: Invalid points for horizontal grid line at v={v}")
                except Exception as e:
                    print(f"  Error creating horizontal grid line at v={v}: {str(e)}")
        
        except Exception as e:
            print(f"Error creating grid visualization: {str(e)}")
            
        print(f"Created {len(curves)} grid visualization curves")
        return curves
    
    # Add to WallCoordinateSystem class

    def point_at(self, u: float, v: float, w: float = 0.0) -> rg.Point3d:
        """
        Get a point in world coordinates using direct base plane evaluation.
        
        This is a more reliable alternative to wall_to_world when transforms fail.
        """
        try:
            # Use the base plane directly to create a point
            if self.base_plane is None:
                print(f"Cannot create point: base_plane is None")
                return None
                
            # Create the point using the base plane's coordinate system
            point = self.base_plane.PointAt(u, v, w)
            return point
        except Exception as e:
            print(f"Error in point_at for u={u}, v={v}, w={w}: {str(e)}")
            return None

@dataclass
class FramingElementCoordinates:
    """
    Stores and manages key coordinates for a framing element.
    
    This class handles the positioning data for framing elements,
    providing both wall-space and world-space representations.
    It also facilitates the extraction of debug geometry.
    """
    # Wall-space coordinates (u, v, w system)
    u_start: float
    u_end: float
    v_start: float 
    v_end: float
    w_center: float = 0.0  # Default to wall centerline
    
    # Reference to the wall coordinate system
    coordinate_system: Optional['WallCoordinateSystem'] = None
    
    @property
    def length(self) -> float:
        """Get element length based on orientation."""
        if self.is_horizontal:
            return abs(self.u_end - self.u_start)
        else:
            return abs(self.v_end - self.v_start)
    
    @property
    def is_horizontal(self) -> bool:
        """Determine if the element is horizontal based on start/end points."""
        return abs(self.v_end - self.v_start) < 0.001
    
    @property
    def is_vertical(self) -> bool:
        """Determine if the element is vertical based on start/end points."""
        return abs(self.u_end - self.u_start) < 0.001
    
    def get_world_corners(self) -> List[Optional[rg.Point3d]]:
        """Get corner points in world coordinates."""
        corners = []
        
        try:
            if self.coordinate_system is None:
                print("Warning: coordinate_system is None in FramingElementCoordinates")
                return [None, None, None, None]
                
            # Get the four corners in world coordinates
            corners = [
                self.coordinate_system.wall_to_world(self.u_start, self.v_start, self.w_center),
                self.coordinate_system.wall_to_world(self.u_end, self.v_start, self.w_center),
                self.coordinate_system.wall_to_world(self.u_end, self.v_end, self.w_center),
                self.coordinate_system.wall_to_world(self.u_start, self.v_end, self.w_center)
            ]
            
            # Filter out None values
            corners = [corner for corner in corners if corner is not None]
            
        except Exception as e:
            print(f"Error getting world corners: {str(e)}")
            
        return corners
    
    def get_centerline(self) -> Optional[rg.Curve]:
        """Get element centerline in world coordinates."""
        try:
            if self.coordinate_system is None:
                print("Warning: coordinate_system is None in FramingElementCoordinates")
                return None
                
            if self.is_horizontal:
                # For horizontal elements, centerline runs along u-axis at mid-v
                start = self.coordinate_system.wall_to_world(
                    self.u_start, (self.v_start + self.v_end) / 2, self.w_center
                )
                end = self.coordinate_system.wall_to_world(
                    self.u_end, (self.v_start + self.v_end) / 2, self.w_center
                )
            else:
                # For vertical elements, centerline runs along v-axis at mid-u
                start = self.coordinate_system.wall_to_world(
                    (self.u_start + self.u_end) / 2, self.v_start, self.w_center
                )
                end = self.coordinate_system.wall_to_world(
                    (self.u_start + self.u_end) / 2, self.v_end, self.w_center
                )
            
            # Verify both points exist before creating curve
            if start is None or end is None:
                print("Warning: Unable to create centerline - one or both points are None")
                return None
                
            return rg.LineCurve(start, end)
            
        except Exception as e:
            print(f"Error getting centerline: {str(e)}")
            return None
    
    def get_profile_plane(self) -> Optional[rg.Plane]:
        """Get profile plane in world coordinates."""
        try:
            if self.coordinate_system is None:
                print("Warning: coordinate_system is None in FramingElementCoordinates")
                return None
                
            # Determine midpoints
            u_mid = (self.u_start + self.u_end) / 2
            v_mid = (self.v_start + self.v_end) / 2
            
            # For horizontal elements, profile normal is vertical (v-direction)
            if self.is_horizontal:
                return self.coordinate_system.create_wall_plane(u_mid, v_mid, "v")
            # For vertical elements, profile normal is through wall (w-direction)
            else:
                return self.coordinate_system.create_wall_plane(u_mid, v_mid, "w")
                
        except Exception as e:
            print(f"Error getting profile plane: {str(e)}")
            return None
    
    def get_debug_geometry(self) -> Dict[str, Any]:
        """Extract debug geometry for visualization."""
        result = {
            'corners': [],
            'centerline': None,
            'boundary': None,
            'profile_plane': None,
            'reference_points': []
        }
        
        try:
            if self.coordinate_system is None:
                print("Warning: coordinate_system is None in FramingElementCoordinates")
                return result
                
            # Create corners and centerline
            try:
                corners = self.get_world_corners()
                if corners and len(corners) == 4:
                    result['corners'] = corners
                    
                    # Create a boundary rectangle if we have valid corners
                    try:
                        boundary = rg.PolylineCurve([
                            corners[0], corners[1], corners[2], corners[3], corners[0]
                        ])
                        result['boundary'] = boundary
                    except Exception as e:
                        print(f"Error creating boundary: {str(e)}")
                else:
                    print(f"Warning: Invalid corners array: {len(corners) if corners else 0} points")
            except Exception as e:
                print(f"Error getting corners: {str(e)}")
            
            try:
                centerline = self.get_centerline()
                if centerline is not None:
                    result['centerline'] = centerline
            except Exception as e:
                print(f"Error getting centerline: {str(e)}")
            
            try:
                profile_plane = self.get_profile_plane()
                if profile_plane is not None:
                    result['profile_plane'] = profile_plane
            except Exception as e:
                print(f"Error getting profile plane: {str(e)}")
            
            # Create reference points at key locations
            try:
                start_point = self.coordinate_system.wall_to_world(self.u_start, self.v_start, self.w_center)
                end_point = self.coordinate_system.wall_to_world(self.u_end, self.v_end, self.w_center)
                if start_point is not None and end_point is not None:
                    result['reference_points'] = [start_point, end_point]
            except Exception as e:
                print(f"Error getting reference points: {str(e)}")
                
            return result
            
        except Exception as e:
            print(f"Error in get_debug_geometry: {str(e)}")
            return result