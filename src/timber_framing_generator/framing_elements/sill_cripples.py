# File: timber_framing_generator/framing_elements/sill_cripples.py

from typing import Dict, List, Any, Tuple, Optional
import Rhino.Geometry as rg
import math
from timber_framing_generator.config.framing import FRAMING_PARAMS


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
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}

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
        try:
            # Only create sill cripples for windows, not doors
            if opening_data.get("opening_type", "").lower() != "window":
                print("Opening is not a window - skipping sill cripples")
                return []

            # Extract opening information
            opening_u_start = opening_data.get("start_u_coordinate")
            opening_width = opening_data.get("rough_width")

            if None in (opening_u_start, opening_width):
                print("Missing required opening data")
                return []

            # Get essential parameters
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available")
                return []

            # Calculate sill cripple dimensions from framing parameters
            cripple_width = FRAMING_PARAMS.get(
                "cripple_width", 1.5 / 12
            )  # Typically 1.5 inches
            cripple_depth = FRAMING_PARAMS.get(
                "cripple_depth", 3.5 / 12
            )  # Typically 3.5 inches
            cripple_spacing = FRAMING_PARAMS.get(
                "cripple_spacing", 16 / 12
            )  # Typically 16 inches

            # Calculate vertical bounds
            sill_bottom_elevation = sill_data.get("bottom_elevation")

            # Try different keys for top elevation of bottom plate
            bottom_plate_top_elevation = bottom_plate_data.get(
                "top_elevation"
            ) or bottom_plate_data.get("boundary_elevation")

            print(f"Sill bottom elevation: {sill_bottom_elevation}")
            print(f"Bottom plate top elevation: {bottom_plate_top_elevation}")

            if None in (sill_bottom_elevation, bottom_plate_top_elevation):
                print("Missing elevation data for sill or bottom plate")
                print(f"Sill data keys: {sill_data.keys()}")
                print(f"Bottom plate data keys: {bottom_plate_data.keys()}")
                return []

            # Calculate horizontal positions
            if trimmer_positions:
                # Use provided trimmer positions
                u_left, u_right = trimmer_positions

                u_left_inner = u_left + cripple_width
                u_right_inner = u_right - cripple_width
            else:
                # Calculate positions based on opening with standard offsets
                u_left_inner = opening_u_start + cripple_width
                u_right_inner = opening_u_start + opening_width - cripple_width

            # Calculate internal width between inner faces
            internal_width = u_right_inner - u_left_inner

            print(f"\nSill cripple calculation details:")
            print(f"  Trimmer positions: left={u_left_inner}, right={u_right_inner}")
            print(f"  Internal width: {internal_width}")
            print(f"  Cripple spacing parameter: {cripple_spacing}")

            # Calculate number of spaces based on standard spacing
            num_spaces = math.ceil(internal_width / cripple_spacing)

            # Number of cripples is one more than number of spaces
            cripple_count = num_spaces + 1

            # Calculate actual spacing
            actual_spacing = internal_width / num_spaces

            print(f"  Number of spaces: {num_spaces}")
            print(f"  Number of cripples: {cripple_count}")
            print(f"  Actual spacing: {actual_spacing}")

            # Generate cripple positions
            cripple_positions = []
            for i in range(cripple_count):
                position = u_left_inner + i * actual_spacing
                cripple_positions.append(position)
                print(f"  Cripple {i+1} position: {position}")

            # TODO: Implement alternative spacing mode where spacing is exact value from FRAMING_PARAMS["cripple_spacing"]
            # except for the last sill cripple which adjusts to the remainder space

            # Store sill cripples
            sill_cripples = []

            # Generate cripples at calculated positions
            for u_position in cripple_positions:
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

            return sill_cripples

        except Exception as e:
            print(f"Error generating sill cripples: {str(e)}")
            import traceback

            print(traceback.format_exc())
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
            Brep geometry for the sill cripple stud, or None if creation fails
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

            # Create the centerline as a curve
            centerline = rg.LineCurve(start_point, end_point)
            self.debug_geometry["paths"].append(centerline)

            # 2. Create a profile plane at the start point
            # X axis goes across wall thickness (for width)
            profile_x_axis = base_plane.ZAxis
            # Y axis goes along wall length (for depth)
            profile_y_axis = base_plane.XAxis

            profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
            self.debug_geometry["planes"].append(profile_plane)

            # 3. Create a rectangular profile centered on the plane
            profile_rect = rg.Rectangle3d(
                profile_plane,
                rg.Interval(-depth / 2, depth / 2),
                rg.Interval(-width / 2, width / 2),
            )

            profile_curve = profile_rect.ToNurbsCurve()
            self.debug_geometry["profiles"].append(profile_rect)

            # 4. Extrude the profile along the centerline path
            # Calculate the vector from start to end
            path_vector = rg.Vector3d(end_point - start_point)

            # Create the extrusion
            extrusion = rg.Extrusion.CreateExtrusion(profile_curve, path_vector)

            # Convert to Brep and return
            if extrusion and extrusion.IsValid:
                return extrusion.ToBrep().CapPlanarHoles(0.001)
            else:
                print("Failed to create valid sill cripple extrusion")
                return None

        except Exception as e:
            print(f"Error creating sill cripple geometry: {str(e)}")
            import traceback

            print(traceback.format_exc())
            return None
