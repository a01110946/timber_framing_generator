# File: timber_framing_generator/framing_elements/headers.py

from typing import Dict, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.timber_framing_generator.utils.safe_rhino import safe_get_length, safe_create_extrusion
from src.timber_framing_generator.config.framing import FRAMING_PARAMS, get_framing_param
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


class HeaderGenerator:
    """
    Generates header framing elements above openings.

    Headers span between king studs above an opening, providing structural
    support and load transfer around the opening. This class handles the
    positioning, sizing, and geometric creation of header elements.
    """

    def __init__(self, wall_data: Dict[str, Any]):
        """
        Initialize the header generator with wall data and coordinate system.

        Args:
            wall_data: Dictionary containing wall information
            coordinate_system: Optional coordinate system for transformations
        """
        logger.debug("Initializing HeaderGenerator")
        logger.debug(f"Wall data: {wall_data}")
        
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "curves": [], "planes": [], "profiles": []}
        
        logger.debug("HeaderGenerator initialized successfully")

    def generate_header(
        self,
        opening_data: Dict[str, Any],
        king_stud_positions: Optional[Tuple[float, float]] = None,
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
            logger.info("===== HEADER GENERATION DETAILS =====")
            logger.debug(f"Opening data: {opening_data}")
            logger.debug(f"King stud positions: {king_stud_positions}")

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")

            logger.debug("Extracted opening data:")
            logger.debug(f"  opening_u_start: {opening_u_start}")
            logger.debug(f"  opening_width: {opening_width}")
            logger.debug(f"  opening_height: {opening_height}")
            logger.debug(f"  opening_v_start: {opening_v_start}")

            if None in (
                opening_u_start,
                opening_width,
                opening_height,
                opening_v_start,
            ):
                logger.warning("Missing required opening data for header generation")
                return None

            # Get essential parameters
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for header generation")
                return None

            # Calculate header dimensions from framing parameters
            # Uses wall_data config if available (for material-specific dimensions)
            king_stud_offset = get_framing_param("king_stud_offset", self.wall_data, 1.5 / 12 / 2)
            header_width = get_framing_param(
                "header_depth", self.wall_data, 5.5 / 12
            )  # Through wall thickness
            header_height = get_framing_param(
                "header_height", self.wall_data, 7.0 / 12
            )  # Vertical dimension
            header_height_above_opening = get_framing_param(
                "header_height_above_opening", self.wall_data, 0.0
            )  # Distance above opening

            logger.info("Header dimensions (wall_data config or FRAMING_PARAMS):")
            logger.info(f"  header_width (depth into wall): {header_width} ft = {header_width * 12} in")
            logger.info(f"  header_height (vertical): {header_height} ft = {header_height * 12} in")
            logger.info(f"  height_above_opening: {header_height_above_opening}")
            logger.info(f"  king_stud_offset: {king_stud_offset}")

            # Calculate header position (top of opening + half header height)
            opening_v_end = opening_v_start + opening_height
            header_v = opening_v_end + (header_height / 2) + header_height_above_opening

            logger.debug("Vertical position:")
            logger.debug(f"  opening_v_end: {opening_v_end}")
            logger.debug(f"  header_v: {header_v}")

            # Calculate header span
            if king_stud_positions:
                logger.debug("Using provided king stud positions for header")
                u_left, u_right = king_stud_positions

                # Check if these are centerlines or inner faces
                logger.debug(f"Raw king stud positions: u_left={u_left}, u_right={u_right}")

                # Adjust positions to use inner faces instead of centerlines
                inner_left = u_left + king_stud_offset
                inner_right = u_right - king_stud_offset
                logger.debug(f"  inner_left: {u_left} + {king_stud_offset} = {inner_left}")
                logger.debug(f"  inner_right: {u_right} - {king_stud_offset} = {inner_right}")
                logger.debug(
                    f"Adjusted for inner faces: u_left={inner_left}, u_right={inner_right}"
                )

                # Use the adjusted positions
                u_left = inner_left
                u_right = inner_right
            else:
                # Calculate positions based on opening with offsets
                logger.debug("No king stud positions provided, calculating based on opening")
                trimmer_width = get_framing_param("trimmer_width", self.wall_data, 1.5 / 12)
                u_left = opening_u_start - trimmer_width
                u_right = opening_u_start + opening_width + trimmer_width
                logger.debug(f"Calculated positions: u_left={u_left}, u_right={u_right}")

            logger.debug(
                f"Final header span: u_left={u_left}, u_right={u_right}, width={u_right-u_left}"
            )

            # 1. Create the centerline endpoints in wall-local coordinates
            # The wall's base_plane coordinate system is:
            #   - XAxis = along wall (U direction)
            #   - YAxis = vertical (V direction) - derived from World Z
            #   - ZAxis = wall normal (W direction)
            # Position using wall-local U,V coordinates via base_plane axes

            start_point = rg.Point3d.Add(
                base_plane.Origin,
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_left),
                    rg.Vector3d.Multiply(base_plane.YAxis, header_v),
                ),
            )

            end_point = rg.Point3d.Add(
                base_plane.Origin,
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_right),
                    rg.Vector3d.Multiply(base_plane.YAxis, header_v),
                ),
            )

            logger.debug("Header endpoints in world coordinates:")
            logger.debug(f"  start_point: {start_point}")
            logger.debug(f"  end_point: {end_point}")

            # Create the centerline as a curve
            centerline = rg.LineCurve(start_point, end_point)
            self.debug_geometry["curves"].append(centerline)
            logger.debug(f"Created centerline with length: {safe_get_length(centerline)}")

            # 2. Create a profile plane at the start point
            # Create vectors for the profile plane
            # X axis goes into the wall (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes up/down (for height)
            profile_y_axis = base_plane.YAxis

            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry["planes"].append(profile_plane)
            logger.debug("Created profile plane for header")

            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-header_width / 2, header_width / 2),
                rg.Interval(-header_height / 2, header_height / 2),
            )

            profile_curve = profile_rect.ToNurbsCurve()
            self.debug_geometry["profiles"].append(profile_rect)
            logger.debug(f"Created profile rectangle - width: {header_width}, height: {header_height}")

            # 4. Extrude the profile along the centerline
            # Calculate the vector from start to end
            extrusion_vector = rg.Vector3d(end_point - start_point)
            logger.debug(f"Extrusion vector length: {safe_get_length(extrusion_vector)}")
            
            try:
                logger.debug("Creating header extrusion")
                extrusion = safe_create_extrusion(profile_curve, extrusion_vector)
                if extrusion and hasattr(extrusion, 'IsValid') and extrusion.IsValid:
                    logger.info("Successfully created header")
                    # Check if already a Brep
                    if hasattr(extrusion, 'ToBrep'):
                        return extrusion.ToBrep()
                    else:
                        return extrusion
                else:
                    logger.warning("Primary extrusion method created invalid extrusion")
            except Exception as e:
                logger.warning(f"Failed to create valid header extrusion: {str(e)}")
                
            # Try alternative approach - direct box creation using wall-aligned plane
            try:
                logger.debug("Attempting box creation for header")
                # Use header_width (depth into wall) and header_height already calculated above
                # Don't redefine them here - use the values from lines 98-102

                # Safely get header length and handle null/invalid values
                header_length = safe_get_length(extrusion_vector)
                if header_length is None or header_length <= 0:
                    logger.warning("Invalid header length, using fallback value")
                    # Estimate length based on start and end points
                    if start_point is not None and end_point is not None:
                        header_length = start_point.DistanceTo(end_point)
                    else:
                        # Last resort - use a default value
                        header_length = 6.0  # Default header length of 6 feet

                logger.info(f"Creating header box with dimensions:")
                logger.info(f"  length (along wall): {header_length} ft = {header_length * 12} in")
                logger.info(f"  height (vertical): {header_height} ft = {header_height * 12} in")
                logger.info(f"  depth (into wall): {header_width} ft = {header_width * 12} in")

                # Ensure we have valid dimensions before creating the box
                if header_width <= 0 or header_height <= 0 or header_length <= 0:
                    raise ValueError(f"Invalid box dimensions: {header_width}x{header_height}x{header_length}")

                # Ensure start_point is valid
                if start_point is None:
                    logger.warning("Invalid start point for box creation, using origin")
                    start_point = rg.Point3d.Origin

                # FIX: Create a wall-aligned plane for the box
                # The box will extend along its X-axis, so we set:
                # - X-axis = wall direction (for length along wall)
                # - Y-axis = vertical (for height)
                # - Z-axis (implicit) = wall normal (for depth)
                box_plane = rg.Plane(
                    start_point,
                    base_plane.XAxis,  # X-axis = wall direction (for length)
                    base_plane.YAxis   # Y-axis = vertical (for height)
                )

                # Create a box for the header with wall-aligned orientation
                # Interval order: X (length along wall), Y (height), Z (depth into wall)
                # Use header_width (depth into wall) and header_height from main calculation
                logger.info(f"Box intervals being created:")
                logger.info(f"  X (length): 0 to {header_length}")
                logger.info(f"  Y (height): {-header_height/2} to {header_height/2}")
                logger.info(f"  Z (depth): {-header_width/2} to {header_width/2}")
                box = rg.Box(
                    box_plane,
                    rg.Interval(0, header_length),                   # X = length along wall
                    rg.Interval(-header_height/2, header_height/2), # Y = vertical height
                    rg.Interval(-header_width/2, header_width/2)    # Z = depth into wall (header_width)
                )

                if box and box.IsValid:
                    header_brep = box.ToBrep()
                    if header_brep and hasattr(header_brep, 'IsValid') and header_brep.IsValid:
                        # Verify actual dimensions of created Brep
                        bbox = header_brep.GetBoundingBox(True)
                        actual_x = bbox.Max.X - bbox.Min.X
                        actual_y = bbox.Max.Y - bbox.Min.Y
                        actual_z = bbox.Max.Z - bbox.Min.Z
                        logger.info(f"Created header Brep bounding box dimensions:")
                        logger.info(f"  World X extent: {actual_x} ft = {actual_x * 12} in")
                        logger.info(f"  World Y extent: {actual_y} ft = {actual_y * 12} in (depth into wall)")
                        logger.info(f"  World Z extent: {actual_z} ft = {actual_z * 12} in (VERTICAL HEIGHT)")
                        logger.info("Successfully created header using box creation method")
                        return header_brep
            except Exception as box_error:
                logger.warning(f"Box creation failed: {str(box_error)}")
            
            # Try another fallback - simple rectangle extrusion with wall-aligned plane
            try:
                logger.debug("Attempting direct rectangle extrusion for header")
                # Use header_width (depth into wall) and header_height from main calculation

                # FIX: Create wall-aligned profile plane
                # Profile should be in the wall-normal/vertical plane
                rect_plane = rg.Plane(
                    start_point,
                    base_plane.ZAxis,  # X = wall normal (for depth)
                    base_plane.YAxis   # Y = vertical (for height)
                )

                # Create rectangle with centered intervals
                # Use header_width for depth into wall, header_height for vertical
                rect = rg.Rectangle3d(
                    rect_plane,
                    rg.Interval(-header_width/2, header_width/2),
                    rg.Interval(-header_height/2, header_height/2)
                )

                # Convert to curve and extrude along wall direction
                rect_curve = rect.ToNurbsCurve()
                fallback_extrusion = safe_create_extrusion(rect_curve, extrusion_vector)

                if fallback_extrusion and hasattr(fallback_extrusion, 'IsValid') and fallback_extrusion.IsValid:
                    logger.info("Successfully created header using rectangle extrusion fallback")
                    # Check if already a Brep
                    if hasattr(fallback_extrusion, 'ToBrep'):
                        return fallback_extrusion.ToBrep()
                    else:
                        return fallback_extrusion
            except Exception as rect_error:
                logger.warning(f"Rectangle extrusion failed: {str(rect_error)}")

            # Final fallback - create wall-aligned box at start point
            try:
                logger.debug("Attempting emergency header creation")
                # FIX: Create wall-aligned box with correct orientation
                # X = wall direction (length), Y = vertical (height), Z = wall normal (depth)
                emergency_plane = rg.Plane(
                    start_point,
                    base_plane.XAxis,  # X = wall direction
                    base_plane.YAxis   # Y = vertical
                )

                emergency_box = rg.Box(
                    emergency_plane,
                    rg.Interval(0, header_length),                   # X = length along wall
                    rg.Interval(-header_height/2, header_height/2), # Y = height
                    rg.Interval(-header_width/2, header_width/2)    # Z = depth into wall (header_width)
                )

                brep = emergency_box.ToBrep()
                if brep and hasattr(brep, 'IsValid') and brep.IsValid:
                    logger.warning("Created emergency header as fallback")
                    return brep
            except Exception as final_error:
                logger.error(f"All header creation methods failed: {str(final_error)}")
                
            logger.warning("Failed to create valid header geometry")
            return None

        except Exception as e:
            logger.error(f"Error generating header: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _generate_header_fallback(
        self, opening_data, king_stud_positions=None
    ) -> Optional[rg.Brep]:
        """Fallback method for header generation when coordinate transformations fail."""
        try:
            logger.debug("Using fallback method for header generation")

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_height = opening_data.get("rough_height")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")

            # Calculate header v-coordinate (top of opening)
            opening_v_end = opening_v_start + opening_height
            header_height = get_framing_param("header_height", self.wall_data, 7.0 / 12)  # 7 inches default
            header_depth = get_framing_param("header_depth", self.wall_data, 3.5 / 12)   # 3.5 inches default
            header_v = opening_v_end + header_height / 2
            header_height_above_opening = get_framing_param(
                "header_height_above_opening", self.wall_data, 0.0
            )
            header_v = header_v + header_height_above_opening

            # Calculate positions based on opening with offsets
            trimmer_width = get_framing_param("trimmer_width", self.wall_data, 1.5 / 12)
            king_stud_offset = get_framing_param("king_stud_offset", self.wall_data, 1.5 / 12 / 2)

            # Get the base plane from wall data
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for fallback header generation")
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
                    rg.Interval(
                        -header_length / 2, header_length / 2
                    ),  # Length along x-axis
                    rg.Interval(
                        -header_height / 2, header_height / 2
                    ),  # Width into the wall
                    rg.Interval(
                        -header_depth / 2, header_depth / 2
                    ),  # Height centered on header_center
                )

                # Convert to Brep
                if box and box.IsValid:
                    logger.info("Successfully created header using fallback method")
                    return box.ToBrep()
                else:
                    logger.warning("Fallback method created invalid box")
                    return None

            except Exception as e:
                logger.error(f"Error in header fallback box creation: {str(e)}")
                return None

        except Exception as e:
            logger.error(f"Error in header fallback: {str(e)}")
            return None
