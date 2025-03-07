# File: timber_framing_generator/framing_elements/sills.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
from timber_framing_generator.utils.coordinate_systems import (
    WallCoordinateSystem,
    FramingElementCoordinates,
)
from timber_framing_generator.framing_elements.sill_parameters import SillParameters
from timber_framing_generator.config.framing import FRAMING_PARAMS


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
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "curves": [], "planes": [], "profiles": []}

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
        try:
            # Only create sills for windows, not doors
            if opening_data.get("opening_type", "").lower() != "window":
                return None

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")

            if None in (opening_u_start, opening_width, opening_v_start):
                print("Missing required opening data")
                return None

            # Get essential parameters
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available")
                return None

            # Calculate sill dimensions from framing parameters
            sill_width = FRAMING_PARAMS.get(
                "sill_depth", 3.5 / 12
            )  # Through wall thickness
            sill_height = FRAMING_PARAMS.get(
                "sill_height", 1.5 / 12
            )  # Vertical dimension

            # Calculate sill position (equal to opening bottom)
            sill_v = opening_v_start - (sill_height / 2)

            # Calculate sill span based on opening with offsets
            u_left = opening_u_start
            u_right = opening_u_start + opening_width

            # 1. Create the centerline endpoints in world coordinates
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

            # Create the centerline as a curve
            centerline = rg.LineCurve(start_point, end_point)
            self.debug_geometry["curves"].append(centerline)

            # 2. Create a profile plane at the start point
            # Create vectors for the profile plane
            # X axis goes into the wall (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes up/down (for height)
            profile_y_axis = base_plane.YAxis

            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry["planes"].append(profile_plane)

            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-sill_width / 2, sill_width / 2),
                rg.Interval(-sill_height / 2, sill_height / 2),
            )

            profile_curve = profile_rect.ToNurbsCurve()
            self.debug_geometry["profiles"].append(profile_rect)

            # 4. Extrude the profile along the centerline
            # Calculate the vector from start to end
            extrusion_vector = rg.Vector3d(end_point - start_point)
            extrusion = rg.Extrusion.CreateExtrusion(profile_curve, extrusion_vector)

            # Convert to Brep and return
            if extrusion and extrusion.IsValid:
                return extrusion.ToBrep()
            else:
                print("Failed to create valid sill extrusion")
                return None

        except Exception as e:
            print(f"Error generating sill: {str(e)}")
            import traceback

            print(traceback.format_exc())
            return None

    def _generate_sill_fallback(
        self, opening_data, king_stud_positions=None
    ) -> Optional[rg.Brep]:
        """Fallback method for sill generation when coordinate transformations fail."""
        try:
            # Only create sills for windows, not doors
            if opening_data["opening_type"].lower() != "window":
                return None

            print("Using fallback method for sill generation")

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")
            opening_v_start = opening_data.get("base_elevation_relative_to_wall_base")

            # Calculate sill box dimensions
            sill_width = FRAMING_PARAMS.get("sill_width", 1.5 / 12)
            sill_depth = FRAMING_PARAMS.get("sill_depth", 3.5 / 12)
            sill_length = opening_width

            # Get the base plane from wall data
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available for fallback sill generation")
                return None

            # Calculate sill center point (centered horizontally below the opening)
            sill_center_u = opening_u_start + opening_width / 2
            sill_center_v = (
                opening_v_start - sill_width / 2
            )  # Center vertically below the opening
            sill_center = base_plane.PointAt(sill_center_u, sill_center_v, 0)

            try:
                # Create box with proper orientation
                x_axis = base_plane.XAxis
                y_axis = base_plane.YAxis

                # Create a box plane centered on the sill
                box_plane = rg.Plane(sill_center, x_axis, y_axis)

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

                # Convert to Brep
                if box and box.IsValid:
                    return box.ToBrep()
                else:
                    print("Created invalid box in fallback")
                    return None

            except Exception as e:
                print(f"Error in sill fallback box creation: {str(e)}")
                return None

        except Exception as e:
            print(f"Error in sill fallback: {str(e)}")
            return None
