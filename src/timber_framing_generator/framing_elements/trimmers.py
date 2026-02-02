# File: timber_framing_generator/framing_elements/trimmers.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.timber_framing_generator.utils.safe_rhino import safe_get_length, safe_create_extrusion
from src.timber_framing_generator.config.framing import FRAMING_PARAMS, get_framing_param

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


class TrimmerGenerator:
    """
    Generates trimmer studs for wall openings.

    Trimmer studs are vertical framing members placed directly alongside door and
    window openings. They support the header above the opening and transfer loads
    from the header to the bottom plate. Trimmers typically run from the bottom plate
    to the underside of the header, working in tandem with king studs that run the
    full height of the wall.
    """

    def __init__(self, wall_data: Dict[str, Any]):
        """
        Initialize the trimmer generator with wall data.

        Args:
            wall_data: Dictionary containing wall information including:
                - base_plane: Reference plane for wall coordinate system
                - wall_base_elevation: Base elevation of the wall
                - wall_top_elevation: Top elevation of the wall
        """
        logger.debug("Initializing TrimmerGenerator")
        logger.debug(f"Wall data: {wall_data}")
        
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}
        logger.debug("TrimmerGenerator initialized successfully")

    def generate_trimmers(
        self,
        opening_data: Dict[str, Any],
        plate_data: Dict[str, float],
        header_bottom_elevation: Optional[float] = None,
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
        logger.debug("Generating trimmer studs for wall opening")
        logger.debug(f"Opening data: {opening_data}")
        logger.debug(f"Plate data: {plate_data}")
        logger.debug(f"Header bottom elevation: {header_bottom_elevation}")
        
        try:
            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")

            logger.debug(f"Opening parameters - u_start: {opening_u_start}, width: {opening_width}, height: {opening_height}, v_start: {opening_v_start}")

            if None in (
                opening_u_start,
                opening_width,
                opening_height,
                opening_v_start,
            ):
                logger.warning("Missing required opening data for trimmer generation")
                return []

            # Get essential wall parameters
            base_plane = self.wall_data.get("base_plane")

            # Get bottom elevation from plate boundary data
            # BUG FIX: Convert from absolute Z to relative (above base plane origin)
            # boundary_elevation is absolute, but PointAt/Add adds it to origin.Z
            base_z = base_plane.Origin.Z if base_plane else 0.0
            bottom_elevation_absolute = plate_data.get("boundary_elevation", 0.0)
            bottom_elevation = bottom_elevation_absolute - base_z
            logger.debug(f"Using bottom plate elevation: {bottom_elevation} (relative), absolute was {bottom_elevation_absolute}")

            if base_plane is None:
                logger.warning("No base plane available for trimmer generation")
                return []

            # Calculate trimmer dimensions from framing parameters
            # Uses wall_data config if available (for material-specific dimensions)
            trimmer_width = get_framing_param(
                "trimmer_width", self.wall_data, 1.5 / 12
            )  # Typically 1.5 inches for timber
            trimmer_depth = get_framing_param(
                "trimmer_depth", self.wall_data, 3.5 / 12
            )  # Typically 3.5 inches for timber
            
            logger.debug(f"Trimmer dimensions - width: {trimmer_width}, depth: {trimmer_depth}")

            # Calculate header bottom elevation if not provided
            opening_v_end = opening_v_start + opening_height
            header_bottom = (
                header_bottom_elevation
                if header_bottom_elevation is not None
                else opening_v_end
            )
            logger.debug(f"Calculated header bottom elevation: {header_bottom}")

            # Calculate trimmer vertical extent
            bottom_v = bottom_elevation  # Start at bottom plate
            top_v = header_bottom  # End at underside of header
            logger.debug(f"Trimmer vertical extent - bottom: {bottom_v}, top: {top_v}")

            # Calculate horizontal positions with offset from opening edges
            # Typically trimmers are centered at the rough opening edges
            trimmer_offset = trimmer_width / 2  # Center the trimmer at the opening edge

            # Calculate actual u-coordinates for left and right trimmers
            u_left = opening_u_start - trimmer_offset
            u_right = opening_u_start + opening_width + trimmer_offset
            
            logger.debug(f"Trimmer horizontal positions - left: {u_left}, right: {u_right}")

            # Store trimmer studs
            trimmer_studs = []

            # Generate both left and right trimmers
            for u_position in [u_left, u_right]:
                logger.debug(f"Creating trimmer at u-coordinate: {u_position}")
                try:
                    # Create the trimmer stud
                    trimmer = self._create_trimmer_geometry(
                        base_plane,
                        u_position,
                        bottom_v,
                        top_v,
                        trimmer_width,
                        trimmer_depth,
                    )

                    if trimmer is not None:
                        trimmer_studs.append(trimmer)
                        logger.debug(f"Successfully created trimmer at u={u_position}")
                    else:
                        logger.warning(f"Failed to create trimmer at u={u_position}")
                except Exception as e:
                    logger.error(f"Error creating trimmer at u={u_position}: {str(e)}")

            logger.debug(f"Generated {len(trimmer_studs)} trimmer studs")
            return trimmer_studs

        except Exception as e:
            logger.error(f"Error generating trimmers: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _create_trimmer_geometry(
        self,
        base_plane: rg.Plane,
        u_coordinate: float,
        bottom_v: float,
        top_v: float,
        width: float,
        depth: float,
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
                    rg.Vector3d.Multiply(base_plane.YAxis, bottom_v),
                ),
            )

            end_point = rg.Point3d.Add(
                base_plane.Origin,
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_coordinate),
                    rg.Vector3d.Multiply(base_plane.YAxis, top_v),
                ),
            )
            self.debug_geometry["points"].extend([start_point, end_point])
            logger.debug(f"Created trimmer centerline from {start_point} to {end_point}")

            # 2. Create a profile plane at the start point
            # Profile plane is perpendicular to the centerline
            # X axis goes across wall thickness (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes along wall length (for depth)
            profile_y_axis = base_plane.XAxis

            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry["planes"].append(profile_plane)
            logger.debug("Created profile plane for trimmer cross-section")

            # 3. Create a rectangle for the profile
            half_width = width / 2
            half_depth = depth / 2
            rect_corners = [
                rg.Point3d(-half_width, -half_depth, 0),  # lower left
                rg.Point3d(half_width, -half_depth, 0),   # lower right
                rg.Point3d(half_width, half_depth, 0),    # upper right
                rg.Point3d(-half_width, half_depth, 0),   # upper left
            ]
            logger.debug("Created rectangle corners for trimmer cross-section")

            # Transform corners to profile plane
            transform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, profile_plane)
            for i, corner in enumerate(rect_corners):
                corner.Transform(transform)
                self.debug_geometry["points"].append(corner)

            # Create polygon from corners
            profile_poly = rg.Polyline([*rect_corners, rect_corners[0]])  # Close the loop
            profile_curve = profile_poly.ToNurbsCurve()
            self.debug_geometry["profiles"].append(profile_curve)
            logger.debug("Transformed rectangle to profile plane")

            # 4. Extrude the profile along the centerline
            # Calculate direction vector from start to end point
            direction_vector = rg.Vector3d(end_point - start_point)
            logger.debug(f"Extrusion vector: ({direction_vector.X}, {direction_vector.Y}, {direction_vector.Z})")

            try:
                # Primary method: extrusion
                brep = safe_create_extrusion(profile_curve, direction_vector)
                
                if brep is not None and hasattr(brep, 'IsValid') and brep.IsValid:
                    logger.debug("Successfully created trimmer Brep using extrusion")
                    # Check if we need to convert to Brep
                    if hasattr(brep, 'ToBrep'):
                        return brep.ToBrep()
                    else:
                        return brep
                else:
                    logger.warning("Failed to create trimmer Brep from extrusion operation")
            except Exception as extrusion_error:
                logger.warning(f"Extrusion error: {str(extrusion_error)}")
            
            # Fallback method 1: Try creating a box
            try:
                logger.debug("Attempting box creation for trimmer")
                # Create a box for the trimmer using the dimensions
                height = safe_get_length(direction_vector)
                
                # Handle None or invalid height
                if height is None or height <= 0:
                    logger.warning("Could not calculate curve length, using default")
                    if start_point is not None and end_point is not None:
                        height = start_point.DistanceTo(end_point)
                    else:
                        # Default value as last resort
                        height = 8.0 / 12.0  # 8 inches in feet
                        
                # Ensure we have valid dimensions for the box
                if half_width is None or half_width <= 0:
                    half_width = 0.75 / 12.0  # Default 1.5 inches / 2
                    logger.warning(f"Invalid half_width, using default: {half_width}")
                
                if half_depth is None or half_depth <= 0:
                    half_depth = 1.75 / 12.0  # Default 3.5 inches / 2
                    logger.warning(f"Invalid half_depth, using default: {half_depth}")
                
                # Create a plane at the start point with proper orientation
                box_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
                
                # Create box
                box = rg.Box(
                    box_plane,
                    rg.Interval(-half_width, half_width),
                    rg.Interval(-half_depth, half_depth),
                    rg.Interval(0, height)
                )
                
                if box and hasattr(box, 'IsValid') and box.IsValid:
                    logger.debug("Successfully created trimmer using box")
                    trimmer_brep = box.ToBrep()
                    return trimmer_brep
                else:
                    logger.warning("Box creation error: Invalid box geometry")
            except Exception as box_error:
                logger.warning(f"Box creation error: {str(box_error)}")
            
            # Fallback method 2: Try creating a sweep
            try:
                logger.debug("Attempting sweep creation for trimmer")
                
                # Create line for path
                if start_point is None or end_point is None:
                    raise ValueError("Invalid start or end point for sweep")
                    
                path_line = rg.Line(start_point, end_point)
                path_curve = path_line.ToNurbsCurve()
                
                if path_curve is None:
                    raise ValueError("Failed to create path curve")
                
                # Create new profile
                new_profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
                new_profile = rg.Rectangle3d(
                    new_profile_plane,
                    rg.Interval(-half_width, half_width),
                    rg.Interval(-half_depth, half_depth)
                )
                
                if new_profile is None or not new_profile.IsValid:
                    raise ValueError("Failed to create profile rectangle")
                    
                new_profile_curve = new_profile.ToNurbsCurve()
                if new_profile_curve is None:
                    raise ValueError("Failed to convert profile to curve")
                
                # Perform sweep
                sweep = rg.SweepOneRail()
                sweep.AngleToleranceRadians = 0.1
                sweep.ClosedSweep = False
                sweep.SweepTolerance = 0.01
                
                breps = sweep.PerformSweep(path_curve, new_profile_curve)
                
                if breps and len(breps) > 0 and breps[0].IsValid:
                    logger.debug("Successfully created trimmer using sweep")
                    return breps[0]
                else:
                    logger.warning("Sweep creation error: Failed to create valid sweep")
            except Exception as sweep_error:
                logger.warning(f"Sweep creation error: {str(sweep_error)}")
            
            # Final fallback method: Create an emergency box at origin and transform
            try:
                logger.debug("Creating emergency fallback for trimmer")
                
                # Ensure we have valid values for the dimensions
                emergency_height = 8.0 / 12.0  # 8 inches in feet
                if start_point is not None and end_point is not None:
                    emergency_height = start_point.DistanceTo(end_point)
                    if emergency_height <= 0:
                        emergency_height = 8.0 / 12.0
                        
                emergency_width = 1.5 / 12.0  # 1.5 inches in feet
                emergency_depth = 3.5 / 12.0  # 3.5 inches in feet
                
                # Create box at origin
                emergency_box = rg.Box(
                    rg.Plane.WorldXY,
                    rg.Interval(-emergency_width/2, emergency_width/2),
                    rg.Interval(-emergency_depth/2, emergency_depth/2),
                    rg.Interval(0, emergency_height)
                )
                
                # Transform to correct position if we have start point
                if start_point is not None:
                    transform = rg.Transform.Translation(
                        start_point.X,
                        start_point.Y,
                        start_point.Z
                    )
                    emergency_box.Transform(transform)
                
                emergency_brep = emergency_box.ToBrep()
                if emergency_brep and hasattr(emergency_brep, 'IsValid') and emergency_brep.IsValid:
                    logger.warning("Using emergency fallback geometry for trimmer")
                    return emergency_brep
                else:
                    logger.error("Emergency fallback failed: Invalid emergency box")
            except Exception as emergency_error:
                logger.error(f"Emergency fallback failed: {str(emergency_error)}")
            
            logger.error("All trimmer creation methods failed")
            return None
            
        except Exception as e:
            # Main try/except block for the entire function
            logger.error(f"Error creating trimmer geometry: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
