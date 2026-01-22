# File: timber_framing_generator/framing_elements/plate_geometry.py

from typing import Dict, Optional, Any
import Rhino.Geometry as rg
from src.timber_framing_generator.utils.safe_rhino import safe_create_extrusion, safe_get_length
from src.timber_framing_generator.config.framing import PlatePosition, FRAMING_PARAMS
from src.timber_framing_generator.config.units import convert_from_feet, ProjectUnits
from src.timber_framing_generator.framing_elements.plate_parameters import PlateParameters

# Import our custom logging module
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


class PlateGeometry:
    """
    Handles creation and transformation of plate geometry.

    This class implements a modular approach to geometry creation, allowing
    different geometric representations for various software platforms
    (Rhino, Revit, Speckle, etc.). It separates geometric operations from
    parameter management and location data.

    The class maintains basic geometric elements (centerline and profile) that
    can be used to generate platform-specific geometry on demand, rather than
    at initialization. This approach:
    1. Provides flexibility for different software platforms
    2. Allows for optimized memory usage
    3. Enables platform-specific optimizations
    4. Facilitates future extensions to new platforms
    """

    def __init__(self, location_data: Dict, parameters: PlateParameters):
        """
        Initialize the plate geometry with location data and parameters.

        Note that platform-specific geometry (Rhino, Revit, etc.) is not created
        during initialization. Instead, it is generated on-demand through specific
        methods for each platform.

        Args:
            location_data: Dictionary containing spatial information
            parameters: PlateParameters instance with dimensional data
        """
        logger.debug(f"Initializing PlateGeometry for {parameters.plate_type}")
        logger.trace(f"Location data: {location_data}")
        logger.trace(f"Parameters: {parameters}")
        
        self.location_data = location_data
        self.parameters = parameters
        # Create basic geometric elements used by all platforms
        self.centerline = self._create_centerline()
        self.profile = self._create_profile()
        
        logger.debug(f"PlateGeometry initialized successfully")

    def _create_centerline(self) -> rg.Curve:
        """
        Creates the plate's centerline by offsetting reference line.

        This is a fundamental geometric element used across all platforms.
        """
        logger.debug("Creating plate centerline")
        centerline = self.location_data["reference_line"].DuplicateCurve()
        start_z = centerline.PointAtStart.Z
        logger.trace(f"Initial centerline Z: {start_z}")

        translation = rg.Vector3d(0, 0, self.parameters.vertical_offset)
        logger.debug(f"Applying vertical offset: {self.parameters.vertical_offset}")

        centerline.Translate(translation)
        new_z = centerline.PointAtStart.Z
        logger.trace(f"Final centerline Z: {new_z}")
        
        logger.debug(f"Centerline created with length: {safe_get_length(centerline)}")
        return centerline

    def _create_profile(self) -> rg.Rectangle3d:
        """
        Creates a profile rectangle centered on the plate's centerline.

        The profile is positioned so that:
        1. The centerline runs through the middle of the profile
        2. The profile extends equally in both directions from the centerline
        3. The orientation maintains proper alignment with the wall

        This centering is achieved by:
        - Creating a coordinate system with the centerline at (0,0)
        - Extending the profile dimensions symmetrically:
            * -thickness/2 to +thickness/2 in the wall's normal direction
            * -width/2 to +width/2 in the vertical direction

        For example, if we have:
            - thickness = 1.5 inches
            - width = 3.5 inches
        The profile will extend:
            - 0.75 inches each way from centerline (thickness/2)
            - 1.75 inches up and down (width/2)

        Returns:
            rg.Rectangle3d: A centered rectangular profile ready for extrusion
        """
        logger.debug("Creating plate profile")
        
        # Get the start point for the profile
        start_point = self.centerline.PointAt(0.0)
        logger.trace(f"Profile start point: ({start_point.X}, {start_point.Y}, {start_point.Z})")

        # Get the Z-axis (centerline direction)
        z_axis = self.centerline.TangentAt(0.0)
        z_axis.Unitize()
        logger.trace(f"Z-axis (centerline direction): ({z_axis.X}, {z_axis.Y}, {z_axis.Z})")

        # Get the Y-axis (wall's vertical direction)
        y_axis = self.location_data["base_plane"].YAxis
        y_axis.Unitize()
        logger.trace(f"Y-axis (wall vertical): ({y_axis.X}, {y_axis.Y}, {y_axis.Z})")

        # Calculate X-axis as perpendicular to both Y and Z
        x_axis = rg.Vector3d.CrossProduct(y_axis, z_axis)
        x_axis.Unitize()
        logger.trace(f"X-axis (wall normal): ({x_axis.X}, {x_axis.Y}, {x_axis.Z})")

        # Create the profile plane with these axes
        profile_plane = rg.Plane(start_point, x_axis, y_axis)
        logger.trace("Created profile plane for plate cross-section")

        # Calculate the half-dimensions for centering
        half_thickness = self.parameters.thickness / 2.0
        half_width = self.parameters.width / 2.0
        logger.trace(f"Half-dimensions - thickness: {half_thickness}, width: {half_width}")

        # Create centered rectangle using intervals
        # This creates the rectangle centered on the plane's origin
        rectangle = rg.Rectangle3d(
            profile_plane,
            rg.Interval(-half_width, half_width),  # Centered width
            rg.Interval(-half_thickness, half_thickness),  # Centered thickness
        )
        
        logger.debug(f"Created profile rectangle - width: {self.parameters.width}, thickness: {self.parameters.thickness}")
        return rectangle

    def get_boundary_data(self) -> Dict[str, float]:
        """
        Returns critical elevation data needed for connecting framing elements.
        The boundary elevation represents the surface where other framing
        elements connect - the top of bottom plates or bottom of top plates.
        """
        logger.debug(f"Calculating boundary data for {self.parameters.plate_type}")
        
        # Get the plate's centerline elevation
        centerline_elevation = self.centerline.PointAtStart.Z
        thickness = self.parameters.thickness
        logger.trace(f"Centerline elevation: {centerline_elevation}, thickness: {thickness}")

        # The logic remains simple because we're already working with
        # the correct plate - either the uppermost bottom plate or
        # lowermost top plate
        if self.parameters.plate_type in ["bottom_plate", "sole_plate"]:
            # For bottom plates, framing sits on the top surface
            reference_elevation = centerline_elevation - (thickness / 2)
            boundary_elevation = centerline_elevation + (thickness / 2)
            logger.trace(f"Bottom plate - reference below, boundary above")
        else:
            # For top plates, framing ends at the bottom surface
            reference_elevation = centerline_elevation + (thickness / 2)
            boundary_elevation = centerline_elevation - (thickness / 2)
            logger.trace(f"Top plate - reference above, boundary below")

        data = {
            "reference_elevation": reference_elevation,
            "boundary_elevation": boundary_elevation,
            "thickness": thickness,
        }
        
        logger.debug(f"Boundary data: reference={reference_elevation:.4f}, boundary={boundary_elevation:.4f}")
        return data

    def validate_boundary_data(self, data: Dict[str, float]) -> bool:
        """
        Validates the computed boundary data to ensure it makes physical sense.

        Args:
            data: Dictionary of boundary data to validate

        Returns:
            bool: True if the data is valid, False otherwise

        Raises:
            ValueError: If validation fails with details about the issue
        """
        logger.debug(f"Validating boundary data for {self.parameters.plate_type}")
        logger.trace(f"Data to validate: {data}")
        
        # Ensure we have all required keys
        required_keys = {"reference_elevation", "boundary_elevation", "thickness"}
        if not all(key in data for key in required_keys):
            missing_keys = required_keys - set(data.keys())
            error_msg = f"Missing required keys: {missing_keys}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate thickness is positive and reasonable
        min_thickness = convert_from_feet(0.5 / 12, ProjectUnits.FEET)  # 0.5 inches
        max_thickness = convert_from_feet(12.0 / 12, ProjectUnits.FEET)  # 12 inches
        if not min_thickness <= data["thickness"] <= max_thickness:
            error_msg = (
                f"Plate thickness {data['thickness']} outside valid range "
                f"[{min_thickness}, {max_thickness}]"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate elevation differences make sense for the plate position
        elevation_diff = abs(data["boundary_elevation"] - data["reference_elevation"])
        if not 0 < elevation_diff <= data["thickness"] * 2:  # Allow for double plates
            error_msg = (
                f"Invalid elevation difference {elevation_diff} "
                f"for thickness {data['thickness']}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.debug("Boundary data validation successful")
        return True

    def create_rhino_geometry(self) -> rg.Brep:
        """
        Creates a Rhino-specific geometric representation of the plate using extrusion.

        This method creates plate geometry through these steps:
        1. Gets the profile curve that defines the plate's cross-section
        2. Calculates the direction vector from the centerline using TangentAt(0.0)
        3. Creates an extrusion using Rhino.Geometry.Extrusion
        4. Converts the extrusion to a Brep for final representation

        Returns:
            rg.Brep: A solid representation of the plate as a Rhino Brep

        Note:
            We use TangentAt(0.0) to get the direction at the start of the curve,
            where 0.0 represents the start parameter of the curve. The resulting
            vector is then scaled by the curve length to define the full extrusion.
        """
        logger.debug("Creating Rhino geometry for plate")
        
        try:
            # Get the profile curve (our cross-section)
            profile_curve = self.profile.ToNurbsCurve()
            logger.trace("Converted profile to NURBS curve")
    
            # Calculate the direction vector using TangentAt(0.0)
            # Parameter 0.0 represents the start of the curve
            direction = self.centerline.TangentAt(0.0)
            logger.trace("Calculated direction vector from centerline")
    
            # Scale the direction vector by the length of the centerline
            length = safe_get_length(self.centerline)
            direction *= length
            logger.trace(f"Scaled direction vector by centerline length: {length}")
    
            # Create the extrusion using Rhino.Geometry.Extrusion
            # NOTE: safe_create_extrusion may return a Brep directly, not an Extrusion
            result = safe_create_extrusion(profile_curve, direction)
            logger.trace("Created geometry from safe_create_extrusion")

            # Convert to Brep if needed (handle both Brep and Extrusion returns)
            if result is not None:
                try:
                    # Check if already a Brep (safe_create_extrusion returns Brep)
                    if isinstance(result, rg.Brep):
                        brep = result
                        logger.trace("Result is already a Brep")
                    elif hasattr(result, 'ToBrep') and callable(getattr(result, 'ToBrep')):
                        brep = result.ToBrep()
                        logger.trace("Converted Extrusion to Brep")
                    else:
                        brep = None
                        logger.warning(f"Cannot convert {type(result)} to Brep")

                    if brep is not None and brep.IsValid:
                        try:
                            capped_brep = brep.CapPlanarHoles(0.001)  # Cap any planar holes
                            if capped_brep is not None and capped_brep.IsValid:
                                logger.debug("Created Brep with capped holes")
                                return capped_brep
                            return brep  # Return original if capping fails
                        except Exception as e:
                            logger.warning(f"Failed to cap planar holes: {str(e)}")
                            return brep  # Return the uncapped brep
                except Exception as e:
                    logger.warning(f"Failed to process geometry result: {str(e)}")
                    
                # If ToBrep fails, try alternative method - create a box from result
                try:
                    bbox = result.GetBoundingBox(True)
                    if bbox.IsValid:
                        box = rg.Box(bbox)
                        brep = box.ToBrep()
                        if brep is not None and brep.IsValid:
                            logger.debug("Created box Brep from result bounding box as fallback")
                            return brep
                except Exception as e:
                    logger.warning(f"Failed to create box from result: {str(e)}")
                    
            # If extrusion fails, create a simple box from profile and direction
            try:
                bbox = self.profile.BoundingBox
                if bbox.IsValid:
                    # Create a simple box using extrusion parameters
                    corner = bbox.Min
                    dx = bbox.Max.X - bbox.Min.X
                    dy = bbox.Max.Y - bbox.Min.Y
                    dz = length  # Use centerline length
                    
                    # Create box from dimensions
                    try:
                        box = rg.Box(
                            rg.Plane(corner, rg.Vector3d.ZAxis),
                            rg.Interval(0, dx),
                            rg.Interval(0, dy),
                            rg.Interval(0, dz)
                        )
                        brep = box.ToBrep()
                        if brep is not None and brep.IsValid:
                            logger.debug("Created simple box Brep as final fallback")
                            return brep
                    except Exception as e:
                        logger.warning(f"Failed to create simple box: {str(e)}")
            except Exception as e:
                logger.warning(f"Failed to create box from profile: {str(e)}")
                    
            # If all other methods failed, try a direct box creation
            try:
                point1 = self.centerline.PointAtStart
                point2 = self.centerline.PointAtEnd
                width = self.parameters.width
                thickness = self.parameters.thickness
                
                # Create a box along the centerline
                center_vector = point2 - point1
                center_vector.Unitize()
                
                # Create perpendicular vectors
                if abs(center_vector.Z) < 0.9:  # Not nearly vertical
                    perp1 = rg.Vector3d.CrossProduct(center_vector, rg.Vector3d.ZAxis)
                else:  # Nearly vertical, use X axis for cross product
                    perp1 = rg.Vector3d.CrossProduct(center_vector, rg.Vector3d.XAxis)
                
                perp1.Unitize()
                perp2 = rg.Vector3d.CrossProduct(center_vector, perp1)
                perp2.Unitize()
                
                # Scale vectors by dimensions
                perp1 *= thickness / 2
                perp2 *= width / 2
                
                # Create corner points
                corners = [
                    point1 + perp1 + perp2,
                    point1 + perp1 - perp2,
                    point1 - perp1 - perp2,
                    point1 - perp1 + perp2,
                    point2 + perp1 + perp2,
                    point2 + perp1 - perp2,
                    point2 - perp1 - perp2,
                    point2 - perp1 + perp2
                ]
                
                # Create box from corners using proper Rhino constructor
                try:
                    # CORRECT: Create BoundingBox from corner points, then Box from BoundingBox
                    # rg.Box does NOT accept 8 separate Point3d arguments
                    corner_points = [
                        rg.Point3d(corners[0].X, corners[0].Y, corners[0].Z),
                        rg.Point3d(corners[1].X, corners[1].Y, corners[1].Z),
                        rg.Point3d(corners[2].X, corners[2].Y, corners[2].Z),
                        rg.Point3d(corners[3].X, corners[3].Y, corners[3].Z),
                        rg.Point3d(corners[4].X, corners[4].Y, corners[4].Z),
                        rg.Point3d(corners[5].X, corners[5].Y, corners[5].Z),
                        rg.Point3d(corners[6].X, corners[6].Y, corners[6].Z),
                        rg.Point3d(corners[7].X, corners[7].Y, corners[7].Z)
                    ]
                    bbox = rg.BoundingBox(corner_points)
                    if bbox.IsValid:
                        box = rg.Box(bbox)
                        brep = box.ToBrep()
                        if brep is not None and brep.IsValid:
                            logger.debug("Created corner-based box as extreme fallback")
                            return brep
                except Exception as e:
                    logger.warning(f"Failed to create corner-based box: {str(e)}")
                    
                # Try creating a direct box from points
                try:
                    # Create a more direct approach with a simple box
                    origin = self.centerline.PointAtStart
                    width = self.parameters.width
                    thickness = self.parameters.thickness
                    length = safe_get_length(self.centerline)
                    
                    box = rg.Box(
                        rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.YAxis),
                        rg.Interval(-width/2, width/2),
                        rg.Interval(-thickness/2, thickness/2),
                        rg.Interval(0, length)
                    )
                    brep = box.ToBrep()
                    if brep is not None and brep.IsValid:
                        logger.debug("Created direct box from dimensions as extreme fallback")
                        return brep
                except Exception as e:
                    logger.warning(f"Failed to create direct box: {str(e)}")
            except Exception as e:
                logger.warning(f"Failed to create geometry from centerline: {str(e)}")
                    
            # If all other methods failed, return a simple placeholder cube as absolute last resort
            logger.error("All geometry creation methods failed, creating emergency placeholder")
            
        except Exception as e:
            logger.error(f"Error in create_rhino_geometry: {str(e)}")
            
        # Return a simple placeholder cube as absolute last resort
        try:
            cube = rg.Box(
                rg.Plane.WorldXY,
                rg.Interval(-0.5, 0.5),
                rg.Interval(-0.5, 0.5),
                rg.Interval(-0.5, 0.5)
            )
            logger.warning("Returning emergency placeholder cube as absolute last resort")
            return cube.ToBrep()
        except Exception as final_e:
            logger.error(f"Even the emergency placeholder failed: {str(final_e)}")
            return None  # Absolute last resort is to return None

    def create_revit_geometry(self) -> Optional[Any]:
        """
        Creates a Revit-specific geometric representation of the plate.

        Returns:
            Optional[Any]: A Revit-compatible geometric element

        Note:
            Implementation pending. This method will create geometry
            specifically optimized for Revit's API and data structures.
        """
        # TODO: Implement Revit-specific geometry creation
        pass

    def create_speckle_geometry(self) -> Optional[Any]:
        """
        Creates a Speckle-specific geometric representation of the plate.

        Returns:
            Optional[Any]: A Speckle-compatible geometric element

        Note:
            Implementation pending. This method will create geometry
            specifically optimized for Speckle's transport format.
        """
        # TODO: Implement Speckle-specific geometry creation
        pass

    def get_geometry_data(self, platform: str = "rhino") -> Dict:
        """
        Returns a complete geometry definition for the specified platform.

        Args:
            platform: Target platform ("rhino", "revit", "speckle")
                     Defaults to "rhino" for backward compatibility

        Returns:
            Dictionary containing all geometric data and metadata

        Note:
            This method acts as a facade, providing a consistent interface
            while handling platform-specific geometry creation internally.
        """
        # Common data for all platforms
        data = {
            "centerline": self.centerline,
            "profile": self.profile,
            "width": self.parameters.width,
            "thickness": self.parameters.thickness,
            "framing_type": self.parameters.plate_type,  # Modified from framing_type to plate_name
            "profile_name": self.parameters.profile_name,
            "reference_elevation": self.location_data["reference_elevation"],
            "base_plane": self.location_data["base_plane"],
        }

        # Add platform-specific geometry
        if platform.lower() == "rhino":
            data["platform_geometry"] = self.create_rhino_geometry()
        elif platform.lower() == "revit":
            data["platform_geometry"] = self.create_revit_geometry()
        elif platform.lower() == "speckle":
            data["platform_geometry"] = self.create_speckle_geometry()

        logger.debug(f"Geometry data prepared for {platform} platform")
        return data

    def GetBoundingBox(self, accurate=True):
        """
        Get the bounding box of the plate geometry.
        
        Args:
            accurate: Whether to compute an accurate box (ignored, for compatibility)
            
        Returns:
            rg.BoundingBox: Bounding box containing the plate geometry
        """
        logger.debug("Getting bounding box for plate geometry")
        
        try:
            # If we have a raw_geometry property with a brep, use its bounding box
            if hasattr(self, "raw_geometry") and self.raw_geometry:
                if hasattr(self.raw_geometry, "GetBoundingBox"):
                    return self.raw_geometry.GetBoundingBox(accurate)
            
            # Otherwise, create a bounding box from the centerline and profile
            centerline = self._create_centerline()
            if not centerline:
                logger.warning("Cannot create bounding box - no centerline available")
                return rg.BoundingBox.Empty
            
            # Create a bounding box that encompasses the extruded profile
            profile = self._create_profile()
            if not profile:
                logger.warning("Cannot create bounding box - no profile available")
                return rg.BoundingBox.Empty
            
            # Get centerline points
            start_point = centerline.PointAtStart
            end_point = centerline.PointAtEnd
            
            # Get profile corners
            corners = [
                profile.Corner(0), profile.Corner(1), 
                profile.Corner(2), profile.Corner(3)
            ]
            
            # Create bbox from profile corners
            # Note: Profile corners are already in world coordinates (created at centerline start),
            # so we DON'T add start_point to them - that would double the coordinates!
            bbox = rg.BoundingBox.Empty
            for corner in corners:
                bbox.Union(corner)

            # Calculate offset from start to end for the extruded profile
            offset_vector = rg.Vector3d(
                end_point.X - start_point.X,
                end_point.Y - start_point.Y,
                end_point.Z - start_point.Z
            )

            # Add end profile corners (start corners + offset along centerline)
            for corner in corners:
                end_corner = rg.Point3d(
                    corner.X + offset_vector.X,
                    corner.Y + offset_vector.Y,
                    corner.Z + offset_vector.Z
                )
                bbox.Union(end_corner)
            
            return bbox
            
        except Exception as e:
            logger.error(f"Error creating bounding box: {str(e)}")
            return rg.BoundingBox.Empty
