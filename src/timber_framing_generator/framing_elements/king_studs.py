# File: timber_framing_generator/framing_elements/king_studs.py

from typing import Dict, List, Any, Tuple
import Rhino.Geometry as rg
from src.timber_framing_generator.framing_elements.plate_geometry import PlateGeometry
from src.timber_framing_generator.config.framing import FRAMING_PARAMS, get_framing_param
from src.timber_framing_generator.framing_elements.framing_geometry import (
    create_stud_profile,
)
from src.timber_framing_generator.utils.safe_rhino import safe_create_extrusion

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


def debug_stud_position(base_plane: rg.Plane, u_coord: float, stud_depth: float):
    """Helps visualize and verify stud positioning relative to openings."""
    inner_face = base_plane.PointAt(u_coord + stud_depth / 2, 0, 0)
    outer_face = base_plane.PointAt(u_coord - stud_depth / 2, 0, 0)
    center = base_plane.PointAt(u_coord, 0, 0)

    logger.debug(f"Stud position check:")
    logger.debug(f"- Center: {center}")
    logger.debug(f"- Inner face: {inner_face}")
    logger.debug(f"- Outer face: {outer_face}")


def create_king_studs(
    wall_data: Dict[str, Any],
    opening_data: Dict[str, Any],
    plate_data: Dict[str, float],
    framing_params: Dict[str, Any],
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
    logger.info("Creating king studs")
    logger.debug(f"Wall data: {wall_data}")
    logger.debug(f"Opening data: {opening_data}")
    logger.debug(f"Plate data: {plate_data}")
    logger.debug(f"Framing params: {framing_params}")
    
    # Initialize debug geometry collections
    debug_geom = {"points": [], "planes": [], "profiles": [], "paths": []}

    try:
        # Get base geometry and parameters
        base_plane = wall_data["base_plane"]
        debug_geom["planes"].append(base_plane)
        logger.debug("Retrieved base plane from wall data")

        # 1. Extract dimensions
        stud_width = framing_params.get("stud_width", 1.5 / 12)
        stud_depth = framing_params.get("stud_depth", 3.5 / 12)
        trimmer_width = framing_params.get("trimmer_width", 1.5 / 12)
        king_stud_width = framing_params.get("king_stud_width", 1.5 / 12)

        logger.debug("Dimensions:")
        logger.debug(f"  Stud width: {stud_width}")
        logger.debug(f"  Stud depth: {stud_depth}")
        logger.debug(f"  Trimmer width: {trimmer_width}")
        logger.debug(f"  King stud width: {king_stud_width}")

        # 2. Get elevations
        bottom_elevation = plate_data["bottom_plate_elevation"]
        top_elevation = plate_data["top_elevation"]

        logger.debug("Elevations:")
        logger.debug(f"  Bottom: {bottom_elevation}")
        logger.debug(f"  Top: {top_elevation}")

        # 3. Calculate horizontal positions
        opening_start = opening_data["start_u_coordinate"]
        opening_width = opening_data["rough_width"]

        left_u = opening_start - trimmer_width - (king_stud_width / 2)
        right_u = opening_start + opening_width + trimmer_width + (king_stud_width / 2)
        
        logger.debug("Position calculations:")
        logger.debug(f"Opening start: {opening_start}")
        logger.debug(f"Opening width: {opening_width}")
        logger.debug(f"Trimmer offset: {trimmer_width}")
        logger.debug(f"King stud offset: {king_stud_width}")
        logger.debug(f"Left king stud position: {left_u}")
        logger.debug(f"Right king stud position: {right_u}")

        # 4. Create points using the wall's coordinate system
        stud_points = []
        for u_coord in [left_u, right_u]:
            # Create bottom point
            logger.debug(f"Creating points for u_coord = {u_coord}:")
            bottom = base_plane.PointAt(
                u_coord,  # X - Position along wall
                bottom_elevation,  # Z - Height from base
                0,  # Y - Center in wall thickness
            )
            debug_geom["points"].append(bottom)
            logger.debug(f"Resulting point: X={bottom.X}, Y={bottom.Y}, Z={bottom.Z}")
            logger.debug(
                f"Base plane origin: X={base_plane.Origin.X}, Y={base_plane.Origin.Y}, Z={base_plane.Origin.Z}"
            )
            logger.debug(
                f"Base plane X axis: X={base_plane.XAxis.X}, Y={base_plane.XAxis.Y}, Z={base_plane.XAxis.Z}"
            )

            # Create top point
            top = base_plane.PointAt(
                u_coord,  # X - Same position along wall
                top_elevation,  # Z - Height at top
                0,  # Y - Center in wall thickness
            )
            debug_geom["points"].append(top)
            logger.debug(f"Top point: X={top.X}, Y={top.Y}, Z={top.Z}")

            # Create path line for visualization
            path_line = rg.Line(bottom, top)
            debug_geom["paths"].append(path_line)
            logger.debug(f"Created path line with length: {path_line.Length}")

            stud_points.append((bottom, top))

        # 5. Generate king stud geometry
        logger.debug("Generating king stud geometry")
        king_studs = []
        for i, (bottom, top) in enumerate(stud_points):
            try:
                # Calculate path vector
                path_vector = top - bottom
                path_length = path_vector.Length
                logger.debug(f"King stud {i+1} path length: {path_length}")

                # Create profile plane
                stud_plane = rg.Plane(bottom, base_plane.XAxis, base_plane.ZAxis * (-1))
                debug_geom["planes"].append(stud_plane)
                logger.debug(f"Created profile plane for king stud {i+1}")

                # Create profile
                profile = create_stud_profile(
                    bottom, stud_plane, stud_width, stud_depth
                )
                debug_geom["profiles"].append(profile)
                logger.debug(f"Created profile for king stud {i+1}")

                profile_curve = profile.ToNurbsCurve()
                logger.debug("Converted profile to NURBS curve")

                # Create extrusion using safe method
                extrusion_vector = top - bottom
                try:
                    logger.debug("Attempting to create extrusion")
                    extrusion = safe_create_extrusion(profile_curve, extrusion_vector)
                    if not (extrusion and hasattr(extrusion, 'IsValid') and extrusion.IsValid):
                        logger.warning('Invalid extrusion created, will try alternative method')
                        raise AttributeError('Invalid extrusion created')
                    
                    # Convert to Brep with safe handling
                    if hasattr(extrusion, 'ToBrep'):
                        king_stud = extrusion.ToBrep(True)
                    else:
                        # Already a Brep
                        king_stud = extrusion
                
                except Exception as e:
                    logger.warning(f'Failed to create extrusion with default method: {str(e)}')
                    
                    # Try creating a direct box instead
                    try:
                        # Create box using path and profile dimensions
                        width = framing_params.get("king_stud_width", 1.5 / 12)
                        depth = framing_params.get("framing_depth", 3.5 / 12)
                        
                        # Get the path points
                        origin = bottom
                        path_length = (top - bottom).Length
                        
                        # Create a box along the vertical axis
                        logger.debug(f"Attempting to create box with dimensions w={width}, d={depth}, h={path_length}")
                        
                        # Create a plane for the box
                        plane = rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
                        
                        try:
                            # Box centered on the stud position
                            box = rg.Box(
                                plane,
                                rg.Interval(-width/2, width/2),
                                rg.Interval(-depth/2, depth/2),
                                rg.Interval(0, path_length)
                            )
                            king_stud = box.ToBrep()
                            logger.debug("Successfully created box geometry for king stud")
                        except Exception as box_error:
                            logger.warning(f"Box creation failed: {str(box_error)}")
                            
                            # Try creating an extrusion directly
                            try:
                                rect = rg.Rectangle3d(
                                    rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.YAxis),
                                    width,
                                    depth
                                )
                                profile_curve = rect.ToNurbsCurve()
                                king_stud = safe_create_extrusion(profile_curve, top - bottom)
                                logger.debug("Created king stud via direct rectangle extrusion")
                            except Exception as rect_error:
                                logger.warning(f"Rectangle extrusion failed: {str(rect_error)}")
                                king_stud = None
                    except Exception as fallback_error:
                        logger.warning(f"All fallback methods failed: {str(fallback_error)}")
                        king_stud = None
                
                # Check and add valid king stud
                if king_stud and hasattr(king_stud, 'IsValid') and king_stud.IsValid:
                    king_studs.append(king_stud)
                    logger.debug(f"Successfully created king stud {i+1}")
                else:
                    logger.warning(f"Failed to create valid king stud {i+1}")

            except Exception as e:
                logger.error(f"Error creating king stud: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())

        logger.info(f"Created {len(king_studs)} king studs")
        return king_studs, debug_geom

    except Exception as e:
        logger.error(f"Error in create_king_studs: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
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
        top_plate: PlateGeometry,
    ):
        logger.debug("Initializing KingStudGenerator")
        logger.debug(f"Wall data: {wall_data}")
        
        self.wall_data = wall_data
        self.bottom_plate = bottom_plate
        self.top_plate = top_plate
        self.king_studs_cache = {}
        
        logger.debug("KingStudGenerator initialized")

    def generate_king_studs(self, opening_data: Dict[str, Any]) -> List[rg.Brep]:
        """Generates king studs for a given opening with detailed debug info."""
        logger.info(f"Generating king studs for opening")
        logger.debug(f"Opening data: {opening_data}")
        
        # Get boundary data from both plates
        bottom_data = self.bottom_plate.get_boundary_data()
        top_data = self.top_plate.get_boundary_data()

        logger.debug("Plate boundary data:")
        logger.debug("Bottom plate:")
        logger.debug(f"  Reference elevation: {bottom_data['reference_elevation']}")
        logger.debug(f"  Boundary elevation: {bottom_data['boundary_elevation']}")
        logger.debug(f"  Thickness: {bottom_data['thickness']}")
        logger.debug("Top plate:")
        logger.debug(f"  Reference elevation: {top_data['reference_elevation']}")
        logger.debug(f"  Boundary elevation: {top_data['boundary_elevation']}")
        logger.debug(f"  Thickness: {top_data['thickness']}")

        # Create plate data dictionary with the correct keys
        plate_data = {
            "bottom_plate_elevation": bottom_data["boundary_elevation"],
            "top_elevation": top_data[
                "boundary_elevation"
            ],  
            "plate_thickness": bottom_data["thickness"],
        }

        logger.debug("Opening data:")
        logger.debug(f"  {opening_data}")

        # Initialize debug geometry storage
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}

        # Build framing params - use wall_data config if available, else FRAMING_PARAMS
        framing_params = {
            "stud_width": get_framing_param("stud_width", self.wall_data, 1.5 / 12),
            "stud_depth": get_framing_param("stud_depth", self.wall_data, 3.5 / 12),
            "trimmer_width": get_framing_param("trimmer_width", self.wall_data, 1.5 / 12),
            "king_stud_width": get_framing_param("king_stud_width", self.wall_data, 1.5 / 12),
            "framing_depth": get_framing_param("stud_depth", self.wall_data, 3.5 / 12),
        }
        logger.debug(f"Using framing params: {framing_params}")

        # Generate king studs with debug geometry
        king_studs, debug_geom = create_king_studs(
            self.wall_data, opening_data, plate_data, framing_params
        )

        # Store debug geometry
        self.debug_geometry.update(debug_geom)

        # Log what we created
        logger.debug(f"Debug geometry generated:")
        logger.debug(f"  Points: {len(self.debug_geometry['points'])}")
        logger.debug(f"  Planes: {len(self.debug_geometry['planes'])}")
        logger.debug(f"  Profiles: {len(self.debug_geometry['profiles'])}")
        logger.debug(f"  Paths: {len(self.debug_geometry['paths'])}")

        return king_studs
