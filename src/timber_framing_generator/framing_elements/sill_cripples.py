# File: timber_framing_generator/framing_elements/sill_cripples.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
import math
from src.timber_framing_generator.config.framing import FRAMING_PARAMS, get_framing_param
from src.timber_framing_generator.utils.safe_rhino import safe_get_length, safe_create_extrusion

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


class SillCrippleGenerator:
    """
    Generates sill cripple studs below window openings.

    Sill cripples are vertical framing members placed between the bottom plate
    and the sill below a window opening. They transfer loads from the sill to
    the bottom plate and help support the wall structure below window openings.
    """

    def __init__(self, wall_data: Dict[str, Any]):
        """
        Initialize the sill cripple generator with wall data.

        Args:
            wall_data: Dictionary containing wall information including:
                - base_plane: Reference plane for wall coordinate system
                - wall_base_elevation: Base elevation of the wall
                - wall_top_elevation: Top elevation of the wall
        """
        logger.debug("Initializing SillCrippleGenerator")
        logger.trace(f"Wall data: {wall_data}")
        
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": [], "curves": []}
        logger.debug("SillCrippleGenerator initialized successfully")

    def generate_sill_cripples(
        self,
        opening_data: Dict[str, Any],
        sill_data: Dict[str, Any],
        bottom_plate_data: Dict[str, Any],
        trimmer_positions: Optional[Tuple[float, float]] = None,
    ) -> List[rg.Brep]:
        """
        Generate sill cripple studs below a window opening.

        This method creates a series of sill cripple studs between the bottom plate
        and the sill below a window opening. The cripples are spaced equidistantly
        between the trimmers on either side of the opening.

        Args:
            opening_data: Dictionary with opening information including:
                - start_u_coordinate: Position along wall where opening starts
                - rough_width: Width of the rough opening
                - opening_type: Type of opening ("window" or "door")
            sill_data: Dictionary with sill geometry information including:
                - bottom_elevation: Bottom face elevation of the sill
            bottom_plate_data: Dictionary with bottom plate information including:
                - top_elevation: Top face elevation of the bottom plate
            trimmer_positions: Optional tuple of (left, right) u-coordinates for trimmers
                               If not provided, calculated from opening dimensions

        Returns:
            List of sill cripple Brep geometries
        """
        logger.debug("Generating sill cripples")
        logger.trace(f"Opening data: {opening_data}")
        logger.trace(f"Sill data: {sill_data}")
        logger.trace(f"Bottom plate data: {bottom_plate_data}")
        logger.trace(f"Trimmer positions: {trimmer_positions}")
        
        try:
            # Only create sill cripples for windows, not doors
            opening_type = opening_data.get("opening_type", "").lower()
            if opening_type != "window":
                logger.info(f"Opening is not a window (type: {opening_type}) - skipping sill cripples")
                return []

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")

            if None in (opening_u_start, opening_width):
                logger.warning("Missing required opening data for sill cripple generation")
                return []
                
            logger.trace(f"Opening parameters - u_start: {opening_u_start}, width: {opening_width}")

            # Get essential parameters
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for sill cripple generation")
                return []

            # Calculate sill cripple dimensions from framing parameters
            # Uses wall_data config if available (for material-specific dimensions)
            cripple_width = get_framing_param(
                "cripple_width", self.wall_data, 1.5 / 12
            )  # Typically 1.5 inches
            cripple_depth = get_framing_param(
                "cripple_depth", self.wall_data, 3.5 / 12
            )  # Typically 3.5 inches
            cripple_spacing = get_framing_param(
                "cripple_spacing", self.wall_data, 16 / 12
            )  # Typically 16 inches
            
            logger.trace(f"Cripple dimensions - width: {cripple_width}, depth: {cripple_depth}, spacing: {cripple_spacing}")

            # Calculate vertical bounds
            # BUG FIX: Convert from absolute Z to relative (above base plane origin)
            # These elevations are absolute, but PointAt/Add adds them to origin.Z
            base_z = base_plane.Origin.Z if base_plane else 0.0
            sill_bottom_elevation_abs = sill_data.get("bottom_elevation")
            sill_bottom_elevation = sill_bottom_elevation_abs - base_z if sill_bottom_elevation_abs is not None else None

            # Try different keys for top elevation of bottom plate
            bottom_plate_top_elevation_abs = bottom_plate_data.get(
                "top_elevation"
            ) or bottom_plate_data.get("boundary_elevation")
            bottom_plate_top_elevation = bottom_plate_top_elevation_abs - base_z if bottom_plate_top_elevation_abs is not None else None

            logger.trace(f"Sill bottom elevation: {sill_bottom_elevation} (relative), absolute was {sill_bottom_elevation_abs}")
            logger.trace(f"Bottom plate top elevation: {bottom_plate_top_elevation} (relative), absolute was {bottom_plate_top_elevation_abs}")

            if None in (sill_bottom_elevation, bottom_plate_top_elevation):
                logger.warning("Missing elevation data for sill or bottom plate")
                logger.trace(f"Sill data keys: {sill_data.keys()}")
                logger.trace(f"Bottom plate data keys: {bottom_plate_data.keys()}")
                return []

            # Calculate horizontal positions
            # Offset by half cripple width so outer face aligns with trimmer/opening edge
            half_cripple_width = cripple_width / 2
            if trimmer_positions:
                # Use provided trimmer positions (these are trimmer inner faces)
                u_left, u_right = trimmer_positions

                u_left_inner = u_left + half_cripple_width
                u_right_inner = u_right - half_cripple_width
                logger.trace(f"Using provided trimmer positions: left={u_left}, right={u_right}")
            else:
                # Calculate positions based on opening with standard offsets
                # Opening edges define where cripple outer faces should be
                u_left_inner = opening_u_start + half_cripple_width
                u_right_inner = opening_u_start + opening_width - half_cripple_width
                logger.trace("Calculating positions based on opening dimensions")

            # Calculate internal width between inner faces
            internal_width = u_right_inner - u_left_inner
            
            logger.debug("Sill cripple calculation details:")
            logger.debug(f"Trimmer positions: left={u_left_inner}, right={u_right_inner}")
            logger.debug(f"Internal width: {internal_width}")
            logger.debug(f"Cripple spacing parameter: {cripple_spacing}")

            # Check if there's enough space for cripples
            if internal_width <= 0:
                logger.warning("Insufficient space for sill cripples (internal width <= 0)")
                return []
                
            # Handle case where there's only space for a single cripple
            if internal_width < cripple_spacing:
                logger.info("Space smaller than standard spacing, placing single center cripple")
                cripple_positions = [u_left_inner + (internal_width / 2)]
                cripple_count = 1
                num_spaces = 0
                actual_spacing = 0
            else:
                # Calculate number of spaces based on standard spacing
                try:
                    num_spaces = max(1, math.ceil(internal_width / cripple_spacing))
                    
                    # Number of cripples is one more than number of spaces
                    cripple_count = num_spaces + 1
                    
                    # Calculate actual spacing with safeguards for division by zero
                    if num_spaces > 0:
                        actual_spacing = internal_width / num_spaces
                    else:
                        actual_spacing = cripple_spacing
                        
                    logger.debug(f"Number of spaces: {num_spaces}")
                    logger.debug(f"Number of cripples: {cripple_count}")
                    logger.debug(f"Actual spacing: {actual_spacing}")
                    
                    # Generate cripple positions
                    cripple_positions = []
                    for i in range(cripple_count):
                        position = u_left_inner + i * actual_spacing
                        cripple_positions.append(position)
                        logger.trace(f"Cripple {i+1} position: {position}")
                except Exception as calc_error:
                    logger.warning(f"Error calculating cripple positions: {str(calc_error)}")
                    # Fallback: place a single cripple in the center
                    center_position = u_left_inner + (internal_width / 2)
                    cripple_positions = [center_position]
                    logger.info("Using fallback: single center cripple")
                    
            # Limit the number of cripples to prevent excessive generation
            max_cripples = 20  # Reasonable upper limit
            if len(cripple_positions) > max_cripples:
                logger.warning(f"Too many cripples calculated ({len(cripple_positions)}), limiting to {max_cripples}")
                # Take evenly distributed subset of positions
                step = len(cripple_positions) / max_cripples
                cripple_positions = [cripple_positions[int(i * step)] for i in range(max_cripples)]
            
            # Store sill cripples
            sill_cripples = []

            # Generate cripples at calculated positions
            for i, u_position in enumerate(cripple_positions):
                logger.debug(f"Creating cripple {i+1} at u={u_position}")
                # Create the cripple stud
                cripple = self._create_cripple_geometry(
                    base_plane,
                    u_position,
                    bottom_plate_top_elevation,
                    sill_bottom_elevation,
                    cripple_width,
                    cripple_depth,
                )

                if cripple is not None:
                    sill_cripples.append(cripple)
                    logger.trace(f"Successfully created cripple at u={u_position}")
                else:
                    logger.warning(f"Failed to create cripple at u={u_position}")

            logger.info(f"Generated {len(sill_cripples)} sill cripples")
            return sill_cripples

        except Exception as e:
            logger.error(f"Error generating sill cripples: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _create_cripple_geometry(
        self,
        base_plane: rg.Plane,
        u_coordinate: float,
        bottom_v: float,
        top_v: float,
        width: float,
        depth: float,
    ) -> Optional[rg.Brep]:
        """
        Create the geometry for a single sill cripple stud.

        This method creates a sill cripple stud by:
        1. Creating start and end points in the wall's coordinate system
        2. Creating a profile perpendicular to the stud's centerline
        3. Extruding the profile along the centerline

        Args:
            base_plane: Wall's base plane for coordinate system
            u_coordinate: Position along wall (horizontal)
            bottom_v: Bottom elevation of cripple (top of bottom plate)
            top_v: Top elevation of cripple (bottom of sill)
            width: Width of cripple (perpendicular to wall face)
            depth: Depth of cripple (parallel to wall length)

        Returns:
            Brep geometry for the cripple, or None if creation fails
        """
        logger.trace(f"Creating cripple geometry at u={u_coordinate}, v range={bottom_v}-{top_v}")
        logger.trace(f"Cripple dimensions - width: {width}, depth: {depth}")

        try:
            # 1. Create the centerline endpoints in wall-local coordinates
            # The wall's base_plane coordinate system is:
            #   - XAxis = along wall (U direction)
            #   - YAxis = vertical (V direction) - derived from World Z
            #   - ZAxis = wall normal (W direction)
            # Position using wall-local U,V coordinates via base_plane axes

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

            logger.trace(f"Cripple centerline - start: {start_point}, end: {end_point}")

            # Create centerline (for debugging)
            centerline = rg.Line(start_point, end_point).ToNurbsCurve()
            if "curves" in self.debug_geometry:
                self.debug_geometry["curves"].append(centerline)
            elif "paths" in self.debug_geometry:
                self.debug_geometry["paths"].append(centerline)
            else:
                # If neither key exists, create a new list
                self.debug_geometry["paths"] = [centerline]
            logger.trace("Created cripple centerline")

            # 2. Create a profile plane at the start point
            # Correctly orient the profile plane
            profile_x_axis = base_plane.ZAxis  # Perpendicular to wall face
            profile_y_axis = base_plane.XAxis  # Horizontal along wall length

            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            if "planes" in self.debug_geometry:
                self.debug_geometry["planes"].append(profile_plane)
            else:
                self.debug_geometry["planes"] = [profile_plane]
            logger.trace("Created profile plane for cripple cross-section")

            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-width / 2, width / 2),
                rg.Interval(-depth / 2, depth / 2),
            )

            if "profiles" in self.debug_geometry:
                self.debug_geometry["profiles"].append(profile_rect)
            else:
                self.debug_geometry["profiles"] = [profile_rect]
            logger.trace(f"Created profile rectangle - width: {width}, depth: {depth}")

            # 4. Extrude the profile along the centerline
            # Calculate the vector from start to end
            extrusion_vector = rg.Vector3d(end_point - start_point)
            logger.trace(f"Extrusion vector: ({extrusion_vector.X}, {extrusion_vector.Y}, {extrusion_vector.Z})")
            
            # Create the extrusion using the safe method
            brep = safe_create_extrusion(profile_rect.ToNurbsCurve(), extrusion_vector)
            
            try:
                # Primary method: extrusion
                if brep and hasattr(brep, 'IsValid') and brep.IsValid:
                    logger.debug("Successfully created cripple Brep using extrusion")
                    # Check if already a Brep
                    if hasattr(brep, 'ToBrep'):
                        return brep.ToBrep()
                    else:
                        return brep
                else:
                    logger.warning("Failed to create cripple Brep from extrusion operation")
            except Exception as extrusion_error:
                logger.warning(f"Extrusion failed: {str(extrusion_error)}")
                
            # Fallback method 1: box creation
            try:
                logger.debug("Attempting box creation for cripple")
                
                # Calculate height based on start and end points
                height = 0
                if start_point is not None and end_point is not None:
                    height = start_point.DistanceTo(end_point)
                    if height <= 0:
                        height = 1.0  # Default fallback height
                else:
                    height = 1.0  # Default fallback height
                    
                # Ensure we have valid dimensions
                if width <= 0:
                    width = 1.5/12.0  # Default width
                if depth <= 0:
                    depth = 3.5/12.0  # Default depth
                    
                # Create plane for box
                if start_point is None:
                    start_point = rg.Point3d.Origin
                    
                box_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
                
                # Create a box
                box = rg.Box(
                    box_plane,
                    rg.Interval(-width/2, width/2),
                    rg.Interval(-depth/2, depth/2),
                    rg.Interval(0, height)
                )
                
                if box and box.IsValid:
                    box_brep = box.ToBrep()
                    if box_brep and hasattr(box_brep, 'IsValid') and box_brep.IsValid:
                        logger.debug("Successfully created cripple using box method")
                        return box_brep
            except Exception as box_error:
                logger.warning(f"Box creation failed: {str(box_error)}")
                
            # Final fallback: emergency cube
            try:
                logger.debug("Creating emergency fallback cripple")
                
                # Get dimensions
                height = 1.0  # Default height
                if start_point is not None and end_point is not None:
                    height = start_point.DistanceTo(end_point)
                    if height <= 0:
                        height = 1.0
                
                # Create a box at origin
                emergency_box = rg.Box(
                    rg.Plane.WorldXY,
                    rg.Interval(-width/2, width/2),
                    rg.Interval(-depth/2, depth/2),
                    rg.Interval(0, height)
                )
                
                # Transform to correct position if we have a start point
                if start_point is not None:
                    transform = rg.Transform.Translation(
                        start_point.X,
                        start_point.Y,
                        start_point.Z
                    )
                    emergency_box.Transform(transform)
                
                emergency_brep = emergency_box.ToBrep()
                if emergency_brep and hasattr(emergency_brep, 'IsValid') and emergency_brep.IsValid:
                    logger.warning("Using emergency fallback geometry for cripple")
                    return emergency_brep
            except Exception as emergency_error:
                logger.error(f"Emergency fallback failed: {str(emergency_error)}")
                
            logger.error("All cripple creation methods failed")
            return None
            
        except Exception as e:
            # Main try-except block for the entire method
            logger.error(f"Error creating cripple geometry: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
