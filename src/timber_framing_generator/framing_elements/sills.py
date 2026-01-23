# File: timber_framing_generator/framing_elements/sills.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from src.timber_framing_generator.utils.coordinate_systems import (
    WallCoordinateSystem,
    FramingElementCoordinates,
)
from src.timber_framing_generator.framing_elements.sill_parameters import SillParameters
from src.timber_framing_generator.config.framing import FRAMING_PARAMS
from src.timber_framing_generator.utils.safe_rhino import safe_get_length, safe_create_extrusion

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


class SillGenerator:
    """
    Generates sill framing elements below window openings.

    Sills are horizontal members that provide support at the bottom of window openings.
    This class handles the positioning, sizing, and geometric creation of sill elements.
    """

    def __init__(self, wall_data: Dict[str, Any]):
        """
        Initialize the sill generator with wall data and coordinate system.

        Args:
            wall_data: Dictionary containing wall information
            coordinate_system: Optional coordinate system for transformations
        """
        logger.debug("Initializing SillGenerator")
        logger.debug(f"Wall data: {wall_data}")
        
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "curves": [], "planes": [], "profiles": []}
        logger.debug("SillGenerator initialized successfully")

    def generate_sill(self, opening_data: Dict[str, Any]) -> Optional[rg.Brep]:
        """
        Generate a sill for a window opening.

        This method creates a sill based on:
        1. The opening data for positioning and dimensions
        2. Wall type for appropriate profile selection # TODO: Add this

        The method only creates sills for window openings, not for doors.

        Args:
            opening_data: Dictionary with opening information

        Returns:
            Sill geometry as a Rhino Brep, or None for door openings
        """
        logger.debug("Generating sill for opening")
        logger.debug(f"Opening data: {opening_data}")
        
        try:
            # Only create sills for windows, not doors
            opening_type = opening_data.get("opening_type", "").lower()
            if opening_type != "window":
                logger.info(f"Skipping sill generation for non-window opening type: {opening_type}")
                return None

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")

            if None in (opening_u_start, opening_width, opening_v_start):
                logger.warning("Missing required opening data for sill generation")
                return None
                
            logger.debug(f"Opening parameters - u_start: {opening_u_start}, width: {opening_width}, v_start: {opening_v_start}")

            # Get essential parameters
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for sill generation")
                return None

            # Calculate sill dimensions from framing parameters
            sill_width = FRAMING_PARAMS.get(
                "sill_depth", 3.5 / 12
            )  # Through wall thickness
            sill_height = FRAMING_PARAMS.get(
                "sill_height", 1.5 / 12
            )  # Vertical dimension
            
            logger.debug(f"Sill dimensions - width: {sill_width}, height: {sill_height}")

            # Calculate sill position (equal to opening bottom)
            sill_v = opening_v_start - (sill_height / 2)

            # Calculate sill span based on opening with offsets
            u_left = opening_u_start
            u_right = opening_u_start + opening_width

            logger.debug(f"Sill position - v: {sill_v}, u range: {u_left}-{u_right}")

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
                    rg.Vector3d.Multiply(base_plane.YAxis, sill_v),
                ),
            )

            end_point = rg.Point3d.Add(
                base_plane.Origin,
                rg.Vector3d.Add(
                    rg.Vector3d.Multiply(base_plane.XAxis, u_right),
                    rg.Vector3d.Multiply(base_plane.YAxis, sill_v),
                ),
            )

            logger.debug(f"Centerline start point: ({start_point.X}, {start_point.Y}, {start_point.Z})")
            logger.debug(f"Centerline end point: ({end_point.X}, {end_point.Y}, {end_point.Z})")

            # Create the centerline as a curve
            centerline = rg.LineCurve(start_point, end_point)
            self.debug_geometry["curves"].append(centerline)
            logger.debug(f"Centerline created with length: {safe_get_length(centerline)}")

            # 2. Create a profile plane at the start point
            # Create vectors for the profile plane
            # X axis goes into the wall (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes up/down (for height)
            profile_y_axis = base_plane.YAxis

            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry["planes"].append(profile_plane)
            logger.debug("Profile plane created for sill cross-section")

            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-sill_width / 2, sill_width / 2),
                rg.Interval(-sill_height / 2, sill_height / 2),
            )

            profile_curve = profile_rect.ToNurbsCurve()
            self.debug_geometry["profiles"].append(profile_rect)
            logger.debug(f"Created profile rectangle - width: {sill_width}, height: {sill_height}")

            # 4. Extrude the profile along the centerline
            # Calculate the vector from start to end
            extrusion_vector = rg.Vector3d(end_point - start_point)
            logger.debug(f"Extrusion vector: ({extrusion_vector.X}, {extrusion_vector.Y}, {extrusion_vector.Z})")
            
            try:
                # Primary method: Extrusion
                extrusion = safe_create_extrusion(profile_curve, extrusion_vector)
                
                # Convert to Brep and return
                if extrusion and hasattr(extrusion, 'IsValid') and extrusion.IsValid:
                    logger.debug("Successfully created sill extrusion")
                    # Check if already a Brep
                    if hasattr(extrusion, 'ToBrep'):
                        return extrusion.ToBrep()
                    else:
                        return extrusion
                else:
                    logger.warning("Failed to create valid sill extrusion with primary method")
            except Exception as extrusion_error:
                logger.warning(f"Sill extrusion failed: {str(extrusion_error)}")
                
            # Fallback method 1: Box creation
            try:
                logger.debug("Attempting box creation for sill")

                # Get sill dimensions
                sill_length = safe_get_length(extrusion_vector)
                if sill_length is None or sill_length <= 0:
                    logger.warning("Invalid sill length, using fallback value")
                    if start_point is not None and end_point is not None:
                        sill_length = start_point.DistanceTo(end_point)
                    else:
                        # Default value as last resort
                        sill_length = 3.0

                # FIX: Create wall-aligned plane with correct orientation
                # X = wall direction (length), Y = vertical (height), Z = wall normal (depth)
                box_plane = rg.Plane(
                    start_point,
                    base_plane.XAxis,  # X-axis = wall direction (for length)
                    base_plane.YAxis   # Y-axis = vertical (for height)
                )

                # Create a box for the sill with wall-aligned orientation
                box = rg.Box(
                    box_plane,
                    rg.Interval(0, sill_length),                 # X = length along wall
                    rg.Interval(-sill_height/2, sill_height/2), # Y = vertical height
                    rg.Interval(-sill_width/2, sill_width/2)    # Z = depth into wall
                )
                
                if box and box.IsValid:
                    sill_brep = box.ToBrep()
                    if sill_brep and hasattr(sill_brep, 'IsValid') and sill_brep.IsValid:
                        logger.debug("Successfully created sill using box creation method")
                        return sill_brep
            except Exception as box_error:
                logger.warning(f"Box creation for sill failed: {str(box_error)}")
                
            # Fallback method 2: Direct rectangle extrusion
            try:
                logger.debug("Attempting direct rectangle extrusion for sill")

                # FIX: Create wall-aligned profile plane
                rect_plane = rg.Plane(
                    start_point,
                    base_plane.ZAxis,  # X = wall normal (for depth)
                    base_plane.YAxis   # Y = vertical (for height)
                )

                # Create rectangle with centered intervals
                rect = rg.Rectangle3d(
                    rect_plane,
                    rg.Interval(-sill_width/2, sill_width/2),
                    rg.Interval(-sill_height/2, sill_height/2)
                )

                # Convert to curve and extrude along wall direction
                rect_curve = rect.ToNurbsCurve()
                direct_extrusion = safe_create_extrusion(rect_curve, extrusion_vector)
                
                if direct_extrusion and hasattr(direct_extrusion, 'IsValid') and direct_extrusion.IsValid:
                    logger.debug("Successfully created sill using direct rectangle extrusion")
                    if hasattr(direct_extrusion, 'ToBrep'):
                        return direct_extrusion.ToBrep()
                    else:
                        return direct_extrusion
            except Exception as rect_error:
                logger.warning(f"Rectangle extrusion for sill failed: {str(rect_error)}")
                
            # Final fallback: Emergency wall-aligned box
            try:
                logger.debug("Creating emergency fallback sill")

                # Get sill dimensions
                sill_length = 0
                if start_point is not None and end_point is not None:
                    sill_length = start_point.DistanceTo(end_point)
                else:
                    sill_length = 3.0  # Default fallback

                # FIX: Create wall-aligned box with correct orientation
                # X = wall direction (length), Y = vertical (height), Z = wall normal (depth)
                emergency_plane = rg.Plane(
                    start_point,
                    base_plane.XAxis,  # X = wall direction
                    base_plane.YAxis   # Y = vertical
                )

                emergency_box = rg.Box(
                    emergency_plane,
                    rg.Interval(0, sill_length),                 # X = length along wall
                    rg.Interval(-sill_height/2, sill_height/2), # Y = height
                    rg.Interval(-sill_width/2, sill_width/2)    # Z = depth into wall
                )

                emergency_brep = emergency_box.ToBrep()
                if emergency_brep and hasattr(emergency_brep, 'IsValid') and emergency_brep.IsValid:
                    logger.warning("Using emergency fallback geometry for sill")
                    return emergency_brep
            except Exception as emergency_error:
                logger.error(f"Emergency fallback for sill failed: {str(emergency_error)}")
                
            logger.error("All sill creation methods failed")
            return None
            
        except Exception as e:
            # Main try/except block for the entire method
            logger.error(f"Error generating sill: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _generate_sill_fallback(
        self, opening_data, king_stud_positions=None
    ) -> Optional[rg.Brep]:
        """Fallback method for sill generation when coordinate transformations fail."""
        logger.debug("Using fallback method for sill generation")
        logger.debug(f"Opening data: {opening_data}")
        
        try:
            # Only create sills for windows, not doors
            opening_type = opening_data.get("opening_type", "").lower()
            if opening_type != "window":
                logger.info(f"Skipping fallback sill generation for non-window opening type: {opening_type}")
                return None

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")
            
            if None in (opening_u_start, opening_width, opening_v_start):
                logger.warning("Missing required opening data for fallback sill generation")
                return None
                
            logger.debug(f"Opening parameters - u_start: {opening_u_start}, width: {opening_width}, v_start: {opening_v_start}")

            # Calculate sill box dimensions
            sill_width = FRAMING_PARAMS.get("sill_width", 1.5 / 12)
            sill_depth = FRAMING_PARAMS.get("sill_depth", 3.5 / 12)
            sill_length = opening_width
            
            logger.debug(f"Sill dimensions - width: {sill_width}, depth: {sill_depth}, length: {sill_length}")

            # Get the base plane from wall data
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for fallback sill generation")
                return None

            # Calculate sill center point (centered horizontally below the opening)
            sill_center_u = opening_u_start + opening_width / 2
            sill_center_v = (
                opening_v_start - sill_width / 2
            )  # Center vertically below the opening
            sill_center = base_plane.PointAt(sill_center_u, sill_center_v, 0)
            
            logger.debug(f"Sill center point: ({sill_center.X}, {sill_center.Y}, {sill_center.Z})")

            try:
                # Create box with proper orientation
                x_axis = base_plane.XAxis
                y_axis = base_plane.YAxis

                # Create a box plane centered on the sill
                box_plane = rg.Plane(sill_center, x_axis, y_axis)
                logger.debug("Created box plane for sill")

                # Create the box with proper dimensions
                box = rg.Box(
                    box_plane,
                    rg.Interval(
                        -sill_length / 2, sill_length / 2
                    ),  # Length along x-axis
                    rg.Interval(-sill_width / 2, sill_width / 2),  # Width into the wall
                    rg.Interval(
                        -sill_depth / 2, sill_depth / 2
                    ),  # Height centered on sill_center
                )
                logger.debug("Created box geometry for sill")

                # Convert to Brep
                if box and box.IsValid:
                    logger.debug("Successfully created fallback sill box")
                    return box.ToBrep()
                else:
                    logger.warning("Failed to create valid fallback sill box")

            except Exception as inner_e:
                logger.error(f"Inner error creating fallback sill box: {str(inner_e)}")

            return None

        except Exception as e:
            logger.error(f"Error in fallback sill generation: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
