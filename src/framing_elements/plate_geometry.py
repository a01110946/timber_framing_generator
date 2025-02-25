# File: src/framing_elements/plate_geometry.py

from typing import Dict, Optional, Any
import Rhino.Geometry as rg
from src.config.framing import PlatePosition, FRAMING_PARAMS
from src.config.units import convert_from_feet, ProjectUnits
from .plate_parameters import PlateParameters

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
    
    def __init__(
        self,
        location_data: Dict,
        parameters: PlateParameters
    ):
        """
        Initialize the plate geometry with location data and parameters.
        
        Note that platform-specific geometry (Rhino, Revit, etc.) is not created
        during initialization. Instead, it is generated on-demand through specific
        methods for each platform.
        
        Args:
            location_data: Dictionary containing spatial information
            parameters: PlateParameters instance with dimensional data
        """
        self.location_data = location_data
        self.parameters = parameters
        # Create basic geometric elements used by all platforms
        self.centerline = self._create_centerline()
        self.profile = self._create_profile()
    
    def _create_centerline(self) -> rg.Curve:
        """
        Creates the plate's centerline by offsetting reference line.
        
        This is a fundamental geometric element used across all platforms.
        """
        centerline = self.location_data["reference_line"].DuplicateCurve()
        start_z = centerline.PointAtStart.Z
        print(f"Initial centerline Z: {start_z}")
        
        translation = rg.Vector3d(0, 0, self.parameters.vertical_offset)
        print(f"Applying vertical offset: {self.parameters.vertical_offset}")
        
        centerline.Translate(translation)
        new_z = centerline.PointAtStart.Z
        print(f"Final centerline Z: {new_z}")
        
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
        # Get the start point for the profile
        start_point = self.centerline.PointAt(0.0)
        
        # Get the Z-axis (centerline direction)
        z_axis = self.centerline.TangentAt(0.0)
        z_axis.Unitize()
        
        # Get the Y-axis (wall's vertical direction)
        y_axis = self.location_data["base_plane"].YAxis
        y_axis.Unitize()
        
        # Calculate X-axis as perpendicular to both Y and Z
        x_axis = rg.Vector3d.CrossProduct(y_axis, z_axis)
        x_axis.Unitize()
        
        # Create the profile plane with these axes
        profile_plane = rg.Plane(
            start_point,
            x_axis,
            y_axis
        )
        
        # Calculate the half-dimensions for centering
        half_thickness = self.parameters.thickness / 2.0
        half_width = self.parameters.width / 2.0
        
        # Create centered rectangle using intervals
        # This creates the rectangle centered on the plane's origin
        return rg.Rectangle3d(
            profile_plane,
            rg.Interval(-half_width, half_width),          # Centered width
            rg.Interval(-half_thickness, half_thickness)   # Centered thickness
        )

    def get_boundary_data(self) -> Dict[str, float]:
        """
        Returns critical elevation data needed for connecting framing elements.
        The boundary elevation represents the surface where other framing 
        elements connect - the top of bottom plates or bottom of top plates.
        """
        # Get the plate's centerline elevation
        centerline_elevation = self.centerline.PointAtStart.Z
        thickness = self.parameters.thickness
        
        # The logic remains simple because we're already working with
        # the correct plate - either the uppermost bottom plate or
        # lowermost top plate
        if self.parameters.plate_type in ["bottom_plate", "sole_plate"]:
            # For bottom plates, framing sits on the top surface
            reference_elevation = centerline_elevation - (thickness/2)
            boundary_elevation = centerline_elevation + (thickness/2)
        else:
            # For top plates, framing ends at the bottom surface
            reference_elevation = centerline_elevation + (thickness/2)
            boundary_elevation = centerline_elevation - (thickness/2)
            
        return {
            "reference_elevation": reference_elevation,
            "boundary_elevation": boundary_elevation,
            "thickness": thickness
        }

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
        # Ensure we have all required keys
        required_keys = {"reference_elevation", "boundary_elevation", "thickness"}
        if not all(key in data for key in required_keys):
            raise ValueError(f"Missing required keys: {required_keys - set(data.keys())}")
            
        # Validate thickness is positive and reasonable
        min_thickness = convert_from_feet(0.5/12, ProjectUnits.FEET)  # 0.5 inches
        max_thickness = convert_from_feet(12.0/12, ProjectUnits.FEET)  # 12 inches
        if not min_thickness <= data["thickness"] <= max_thickness:
            raise ValueError(
                f"Plate thickness {data['thickness']} outside valid range "
                f"[{min_thickness}, {max_thickness}]"
            )
            
        # Validate elevation differences make sense for the plate position
        elevation_diff = abs(data["boundary_elevation"] - data["reference_elevation"])
        if not 0 < elevation_diff <= data["thickness"] * 2:  # Allow for double plates
            raise ValueError(
                f"Invalid elevation difference {elevation_diff} "
                f"for thickness {data['thickness']}"
            )
            
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
        # Get the profile curve (our cross-section)
        profile_curve = self.profile.ToNurbsCurve()
        
        # Calculate the direction vector using TangentAt(0.0)
        # Parameter 0.0 represents the start of the curve
        direction = self.centerline.TangentAt(0.0)
        
        # Scale the direction vector by the length of the centerline
        length = self.centerline.GetLength()
        direction *= length
        
        # Create the extrusion using Rhino.Geometry.Extrusion
        extrusion = rg.Extrusion.CreateExtrusion(profile_curve, direction)
        
        # Convert the extrusion to a Brep
        if extrusion is not None:
            brep = extrusion.ToBrep()
            brep = brep.CapPlanarHoles(0.001)  # Cap any planar holes
            return brep
        else:
            raise ValueError("Failed to create extrusion for plate geometry")
    
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
            "framing_type": self.parameters.plate_type, # Modified from framing_type to plate_name
            "profile_name": self.parameters.profile_name,
            "reference_elevation": self.location_data["reference_elevation"],
            "base_plane": self.location_data["base_plane"]
        }
        
        # Add platform-specific geometry
        if platform.lower() == "rhino":
            data["platform_geometry"] = self.create_rhino_geometry()
        elif platform.lower() == "revit":
            data["platform_geometry"] = self.create_revit_geometry()
        elif platform.lower() == "speckle":
            data["platform_geometry"] = self.create_speckle_geometry()
        
        return data