# File: src/framing_elements/plate_geometry.py

from typing import Dict, List, Optional, Union
import Rhino.Geometry as rg
from .plate_parameters import PlateParameters

class PlateGeometry:
    """
    Handles creation and transformation of plate geometry.
    
    This class separates geometric operations from parameter management
    and location data. It can generate different representations of the
    same plate for different systems (Rhino, Revit, etc).
    """
    
    def __init__(
        self,
        location_data: Dict,
        parameters: PlateParameters
    ):
        self.location_data = location_data
        self.parameters = parameters
        self.centerline = self._create_centerline()
        self.profile = self._create_profile()
        
    def _create_centerline(self) -> rg.Curve:
        """Creates the plate's centerline by offsetting reference line."""
        centerline = self.location_data["reference_line"].DuplicateCurve()
        translation = rg.Vector3d(0, 0, self.parameters.vertical_offset)
        centerline.Translate(translation)
        return centerline
    
    def _create_profile(self) -> rg.Rectangle3d:
        """Creates a profile rectangle at the start of centerline."""
        start_point = self.centerline.PointAtStart
        x_axis = self.centerline.TangentAtStart
        z_axis = self.location_data["base_plane"].ZAxis
        y_axis = rg.Vector3d.CrossProduct(z_axis, x_axis)
        
        profile_plane = rg.Plane(
            start_point,
            x_axis,
            y_axis
        )
        
        return rg.Rectangle3d(
            profile_plane,
            self.parameters.width,
            self.parameters.thickness
        )
    
    def create_rhino_geometry(self) -> rg.Brep:
        """Creates a Rhino Brep representation of the plate."""
        rail = self.centerline
        return rg.Brep.CreateFromExtrusion(
            self.profile.ToNurbsCurve(),
            rail.TangentAtStart
        )
    
    def get_geometry_data(self) -> Dict:
        """
        Returns a complete geometry definition that can be used
        by different systems to create their native geometry.
        """
        return {
            "centerline": self.centerline,
            "profile": self.profile,
            "width": self.parameters.width,
            "thickness": self.parameters.thickness,
            "framing_type": self.parameters.framing_type,
            "profile_name": self.parameters.profile_name,
            "reference_elevation": self.location_data["reference_elevation"],
            "base_plane": self.location_data["base_plane"]
        }