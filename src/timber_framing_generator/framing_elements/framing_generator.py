# File: timber_framing_generator/framing_elements/framing_generator.py

import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
import sys
import math
import traceback

try:
    import rhinoscriptsyntax as rs  # type: ignore
except ImportError:
    print("rhinoscriptsyntax not available")
    
try:
    import scriptcontext as sc  # type: ignore
except ImportError:
    print("scriptcontext not available")

# Check if we're running in Grasshopper/Rhino
is_rhino_environment: bool = 'rhinoscriptsyntax' in sys.modules or 'scriptcontext' in sys.modules

# Always import Rhino.Geometry for type annotations
import Rhino  # type: ignore
import Rhino.Geometry as rg  # type: ignore

# Only import rhinoinside if not already in Rhino environment
if not is_rhino_environment:
    import rhinoinside
    rhinoinside.load()
    # Removed the import Rhino  # type: ignore and import Rhino.Geometry as rg  # type: ignore from here

# Project imports using relative imports to avoid module path issues
from ..framing_elements.plates import create_plates
from ..framing_elements.plate_geometry import PlateGeometry
from ..framing_elements.king_studs import KingStudGenerator
from ..framing_elements.headers import HeaderGenerator
from ..framing_elements.sills import SillGenerator
from ..framing_elements.trimmers import TrimmerGenerator
from ..framing_elements.header_cripples import HeaderCrippleGenerator
from ..framing_elements.sill_cripples import SillCrippleGenerator
from ..framing_elements.studs import StudGenerator
from ..framing_elements.row_blocking import RowBlockingGenerator
from ..framing_elements.blocking_parameters import BlockingParameters

# Import only what exists in the framing module
from ..config.framing import FRAMING_PARAMS, PROFILES, BlockingPattern


class FramingGenerator:
    """
    Coordinates the generation of timber wall framing elements.

    This class manages the sequential creation of framing elements while ensuring
    proper dependencies between components. Rather than implementing framing generation
    directly, it leverages our existing specialized functions while adding coordination,
    state management, and dependency tracking.
    """

    def __init__(
        self,
        wall_data: Dict[str, Union[str, float, bool, List, Any]],
        framing_config=None,
    ):
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data

        # Set default configuration if none provided
        self.framing_config = {
            "representation_type": "schematic",  # Default to schematic representation
            "bottom_plate_layers": 1,  # Single bottom plate by default
            "top_plate_layers": 2,  # Double top plate by default
            "include_blocking": FRAMING_PARAMS.get("include_blocking", True),  # Include row blocking by default
            "block_spacing": FRAMING_PARAMS.get("block_spacing", 48.0/12.0),  # Default block spacing
            "first_block_height": FRAMING_PARAMS.get("first_block_height", 24.0/12.0),  # Default first block height
        }

        # Update configuration with any provided values
        if framing_config:
            self.framing_config.update(framing_config)

        # Initialize storage for all framing elements
        self.framing_elements = {
            "bottom_plates": [],
            "top_plates": [],
            "king_studs": [],
        }

        # Track the generation status of different element types
        self.generation_status = {
            "plates_generated": False,
            "king_studs_generated": False,
            "headers_and_sills_generated": False,
            "studs_generated": False,
            "blocking_generated": False,
        }

        # Track any warnings or messages during generation
        self.messages = []

        # Initialize debug geometry storage
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}

    def generate_framing(self) -> Dict[str, List[rg.Brep]]:
        """
        Generate all framing elements.
        
        Returns:
            A dictionary containing all generated framing elements.
        """
        start_time = datetime.datetime.now()
        print("\nStarting framing generation...")
        
        # Generate plates
        self._generate_plates()
        
        # King studs
        self._generate_king_studs()
        
        # Headers and sills
        self._generate_headers_and_sills()
        
        # Trimmers
        self._generate_trimmers()
        
        # Header cripples
        self._generate_header_cripples()
        
        # Sill cripples
        self._generate_sill_cripples()
        
        # Standard studs
        self._generate_studs()
        
        # Row blocking
        try:
            # Check if row blocking is already generated
            if self.generation_status.get("blocking_generated", False):
                print("Row blocking already generated, skipping.")
            else:
                # Generate row blocking using the already generated studs
                if "studs" in self.framing_elements and self.framing_elements["studs"]:
                    blocking = self._generate_row_blocking(studs=self.framing_elements["studs"])
                    
                    # Store the generated blocking
                    self.framing_elements["row_blocking"] = blocking
                    
                    # Collect debug geometry from the blocking generator
                    # Note: This part will need to be updated if we need debug geometry
                    
                    # Update generation status
                    self.generation_status["blocking_generated"] = True
                    print(f"Row blocking generation complete: {len(blocking)} blocks created")
                else:
                    print("No studs available for row blocking, skipping.")
                    self.framing_elements["row_blocking"] = []
                    self.generation_status["blocking_generated"] = True
        except Exception as e:
            print(f"Error in main generate_framing while processing row blocking: {str(e)}")
            # Initialize empty list to prevent errors downstream
            self.framing_elements["row_blocking"] = []
            self.generation_status["blocking_generated"] = True
        
        end_time = datetime.datetime.now()
        print(f"Framing generation complete in {(end_time - start_time).total_seconds():.2f} seconds")
        
        # Display debugging info for wall
        self._print_wall_data_diagnostic()
        
        print("Framing generation complete:")
        print(f"Bottom plates: {len(self.framing_elements.get('bottom_plates', []))}")
        print(f"Top plates: {len(self.framing_elements.get('top_plates', []))}")
        print(f"King studs: {len(self.framing_elements.get('king_studs', []))}")
        print(f"Headers: {len(self.framing_elements.get('headers', []))}")
        print(f"Sills: {len(self.framing_elements.get('sills', []))}")
        print(f"Trimmers: {len(self.framing_elements.get('trimmers', []))}")
        print(f"Header cripples: {len(self.framing_elements.get('header_cripples', []))}")
        print(f"Sill cripples: {len(self.framing_elements.get('sill_cripples', []))}")
        print(f"Studs: {len(self.framing_elements.get('studs', []))}")
        print(f"Row blocking: {len(self.framing_elements.get('row_blocking', []))}")
        
        # Print debug geometry count
        print("Debug geometry:")
        for key, items in self.debug_geometry.items():
            print(f"  {key}: {len(items)} items")
            
        return self.framing_elements

    def _generate_plates(self):
        """
        Generate top and bottom wall plates.
        """
        try:
            # Skip if plates already generated
            if self.generation_status["plates_generated"]:
                return

            self.framing_elements["bottom_plates"] = create_plates(
                wall_data=self.wall_data,
                plate_type="bottom_plate",
                representation_type=self.framing_config["representation_type"],
                layers=self.framing_config["bottom_plate_layers"],
            )

            self.framing_elements["top_plates"] = create_plates(
                wall_data=self.wall_data,
                plate_type="top_plate",
                representation_type=self.framing_config["representation_type"],
                layers=self.framing_config["top_plate_layers"],
            )

            self.generation_status["plates_generated"] = True
            self.messages.append("Plates generated successfully")
            print(f"Created {len(self.framing_elements['bottom_plates'])} bottom plates")
            print(f"Created {len(self.framing_elements['top_plates'])} top plates")
            
        except Exception as e:
            print(f"Error generating plates: {str(e)}")
            self.messages.append(f"Error generating plates: {str(e)}")
            
            # Initialize empty collections as fallback
            self.framing_elements["bottom_plates"] = []
            self.framing_elements["top_plates"] = []
            self.generation_status["plates_generated"] = True  # Mark as done to prevent retry

    def _generate_king_studs(self) -> None:
        """Generates king studs with debug geometry tracking."""
        # Initialize debug geometry with matching keys
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}

        try:
            if self.generation_status["king_studs_generated"]:
                return

            if not self.generation_status["plates_generated"]:
                raise RuntimeError("Cannot generate king studs before plates")

            openings = self.wall_data.get("openings", [])
            print(f"\nGenerating king studs for {len(openings)} openings")

            king_stud_generator = KingStudGenerator(
                self.wall_data,
                self.framing_elements["bottom_plates"][0],
                self.framing_elements["top_plates"][-1],
            )

            opening_king_studs = []

            all_debug_geometry = {
                "points": [],
                "planes": [],
                "profiles": [],
                "paths": [],
            }

            for i, opening in enumerate(openings):
                try:
                    print(f"\nProcessing opening {i+1}")
                    king_studs = king_stud_generator.generate_king_studs(opening)
                    opening_king_studs.extend(king_studs)

                    # Collect debug geometry
                    for key in all_debug_geometry:
                        all_debug_geometry[key].extend(
                            king_stud_generator.debug_geometry.get(key, [])
                        )

                except Exception as e:
                    print(f"Error with opening {i+1}: {str(e)}")
                    import traceback

                    print(traceback.format_exc())

            self.framing_elements["king_studs"] = opening_king_studs
            self.debug_geometry = all_debug_geometry
            self.generation_status["king_studs_generated"] = True

        except Exception as e:
            print(f"Error generating king studs: {str(e)}")
            raise

    def _get_king_stud_positions(self) -> Dict[int, Tuple[float, float]]:
        """
        Extract actual king stud positions from generated geometry.

        This method analyzes the generated king stud geometries to determine
        their exact positions, allowing other framing elements to position
        themselves correctly relative to the king studs.

        Returns:
            Dictionary mapping opening index to (left_u, right_u) positions
        """
        try:
            positions = {}

            # Check if king studs have been generated
            if not self.generation_status.get("king_studs_generated", False):
                print("King studs not yet generated, can't extract positions")
                return positions

            # Get openings and king studs
            openings = self.wall_data.get("openings", [])
            king_studs = self.framing_elements.get("king_studs", [])

            # Get the base plane for position calculations
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available for king stud position extraction")
                return positions

            # Verify we have enough king studs (should be pairs for each opening)
            if len(king_studs) < 2 or len(openings) == 0:
                print(
                    f"Not enough king studs ({len(king_studs)}) or openings ({len(openings)})"
                )
                return positions

            # Process each opening
            for i in range(len(openings)):
                # Calculate the index for this opening's king studs (2 per opening)
                left_index = i * 2
                right_index = i * 2 + 1

                # Verify we have studs for this opening
                if right_index >= len(king_studs):
                    print(f"Missing king studs for opening {i+1}")
                    continue

                # Get the stud geometries
                left_stud = king_studs[left_index]
                right_stud = king_studs[right_index]

                try:
                    # Extract centerlines from the king stud geometries
                    left_centerline = self._extract_centerline_from_stud(left_stud)
                    right_centerline = self._extract_centerline_from_stud(right_stud)

                    if left_centerline is None or right_centerline is None:
                        print(f"Failed to extract centerlines for opening {i+1}")
                        continue

                    # Get the u-coordinates (along the wall) for each stud
                    # For this we need the start points of each centerline
                    left_start = left_centerline.PointAtStart
                    right_start = right_centerline.PointAtStart

                    # Project these points onto the base plane's X axis
                    # to get their u-coordinates
                    left_u = self._project_point_to_u_coordinate(left_start, base_plane)
                    right_u = self._project_point_to_u_coordinate(right_start, base_plane)

                    # Store the inner face positions for header placement
                    positions[i] = (left_u, right_u)

                    print(f"Extracted king stud positions for opening {i+1}:")
                    print(f"  Left stud centerline: u={left_u}")
                    print(f"  Right stud centerline: u={right_u}")

                    # DEBUG: Calculate and report stud inner faces
                    king_stud_width = FRAMING_PARAMS.get("king_stud_width", 1.5 / 12)
                    inner_left = left_u + (king_stud_width / 2)
                    inner_right = right_u - (king_stud_width / 2)
                    print(f"  Inner face positions: left={inner_left}, right={inner_right}")
                    print(f"  Resulting span width: {inner_right - inner_left}")

                except Exception as e:
                    print(
                        f"Error extracting king stud positions for opening {i+1}: {str(e)}"
                    )
                    import traceback

                    print(traceback.format_exc())

            return positions

        except Exception as e:
            print(f"Error getting king stud positions: {str(e)}")
            import traceback

            print(traceback.format_exc())
            return {}

    def _extract_centerline_from_stud(self, stud_brep: rg.Brep) -> Optional[rg.Curve]:
        """
        Extract the centerline curve from a stud Brep.

        This method analyzes the geometry of a stud to find its centerline.
        For king studs, the centerline should be a vertical line running through
        the center of the stud.

        Args:
            stud_brep: The Brep geometry of the stud

        Returns:
            The centerline curve, or None if extraction fails
        """
        try:
            # If we stored path curves in debug geometry during king stud creation,
            # check their type and handle accordingly
            for path in self.debug_geometry.get("paths", []):
                try:
                    # Different ways to get start point depending on type
                    if isinstance(path, rg.LineCurve):
                        test_point = path.PointAtStart
                    elif isinstance(path, rg.Line):
                        test_point = path.From  # Line uses From/To
                        path = rg.LineCurve(
                            path
                        )  # Convert to LineCurve for consistency
                    else:
                        test_point = path.PointAt(0)  # Generic curve

                    # Test if this path is related to our stud
                    if stud_brep.IsPointInside(test_point, 0.01, True):
                        return path
                except Exception as e:
                    print(f"Error checking path: {str(e)}")
                    continue

            # If we can't find a path curve, try to extract it from the Brep
            # For a typical extruded stud, we can use the Brep's bounding box
            bbox = stud_brep.GetBoundingBox(True)
            if bbox.IsValid:
                # Vertical centerline through the middle of the stud
                center_x = (bbox.Min.X + bbox.Max.X) / 2
                center_y = (bbox.Min.Y + bbox.Max.Y) / 2

                # Create a line from bottom to top
                start = rg.Point3d(center_x, center_y, bbox.Min.Z)
                end = rg.Point3d(center_x, center_y, bbox.Max.Z)

                return rg.LineCurve(start, end)

            # If that fails, return None
            print("Failed to extract centerline from stud Brep")
            return None

        except Exception as e:
            print(f"Error extracting centerline from stud: {str(e)}")
            return None

    def _project_point_to_u_coordinate(
        self, point: rg.Point3d, base_plane: rg.Plane
    ) -> float:
        """
        Project a 3D point onto the wall's u-axis to get its u-coordinate.

        Args:
            point: The 3D point to project
            base_plane: The wall's base plane

        Returns:
            The u-coordinate (distance along wall)
        """
        try:
            # Vector from base plane origin to the point
            vec = point - base_plane.Origin

            # Project this vector onto the u-axis (XAxis)
            # Use the dot product for projection
            u = vec * base_plane.XAxis

            return u

        except Exception as e:
            print(f"Error projecting point to u-coordinate: {str(e)}")
            return 0.0

    def _generate_headers_and_sills(self) -> None:
        """
        Generates headers and sills for wall openings.

        This method creates headers above all openings and sills below window openings,
        using the king studs as span references when available.
        """
        try:
            if self.generation_status.get("headers_and_sills_generated", False):
                return

            if not self.generation_status.get("king_studs_generated", False):
                self._generate_king_studs()

            openings = self.wall_data.get("openings", [])
            print(f"\nGenerating headers and sills for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                print("No openings to process - skipping headers and sills")
                self.generation_status["headers_and_sills_generated"] = True
                return

            # Create header and sill generators
            # These now use direct base plane approach - no coordinate system needed!
            header_generator = HeaderGenerator(self.wall_data)
            sill_generator = SillGenerator(self.wall_data)

            # Track generated elements
            headers = []
            sills = []

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    print(f"\nProcessing opening {i+1}")

                    # Get king stud positions for this opening if available
                    opening_king_stud_positions = self._get_king_stud_positions().get(i)

                    # Generate header using direct base plane approach
                    header = header_generator.generate_header(
                        opening, opening_king_stud_positions
                    )
                    if header:
                        headers.append(header)
                        print(f"Successfully created header for opening {i+1}")

                    # Generate sill using direct base plane approach
                    if opening["opening_type"].lower() == "window":
                        sill = sill_generator.generate_sill(opening)
                        if sill:
                            sills.append(sill)
                            print(f"Successfully created sill for opening {i+1}")

                except Exception as e:
                    print(f"Error with opening {i+1}: {str(e)}")
                    import traceback

                    print(traceback.format_exc())
                    continue

            # Store the generated elements
            self.framing_elements["headers"] = headers
            self.framing_elements["sills"] = sills

            # Collect debug geometry
            for generator in [header_generator, sill_generator]:
                for key in ["points", "planes", "profiles", "curves"]:
                    if (
                        key in generator.debug_geometry
                        and generator.debug_geometry[key]
                    ):
                        if key in self.debug_geometry:
                            self.debug_geometry[key].extend(
                                generator.debug_geometry[key]
                            )
                        else:
                            self.debug_geometry[key] = generator.debug_geometry[key]

            # Update generation status
            self.generation_status["headers_and_sills_generated"] = True

        except Exception as e:
            print(f"Error generating headers and sills: {str(e)}")
            import traceback

            print(traceback.format_exc())

            # Mark as completed to prevent future attempts
            self.generation_status["headers_and_sills_generated"] = True

            # Initialize empty lists to prevent errors downstream
            self.framing_elements["headers"] = []
            self.framing_elements["sills"] = []

    def _generate_headers_and_sills_fallback(self) -> None:
        """
        Fallback method for generating headers and sills when coordinate system fails.

        This method uses a simpler approach without the coordinate system,
        directly working with opening geometry and centerlines.
        """
        try:
            openings = self.wall_data.get("openings", [])
            print(f"Using fallback approach for {len(openings)} openings")

            # Track generated elements
            headers = []
            sills = []

            # Get wall base plane
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print(
                    "Error: No base plane available for fallback header/sill generation"
                )
                return

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    print(f"Processing opening {i+1} in fallback mode")

                    # Extract opening information
                    opening_type = opening.get("opening_type", "")
                    opening_u_start = opening.get("start_u_coordinate", 0)
                    opening_width = opening.get("rough_width", 0)
                    opening_height = opening.get("rough_height", 0)
                    opening_v_start = opening.get(
                        "base_elevation_relative_to_wall_base", 0
                    )

                    # Calculate header v-coordinate (top of opening)
                    header_v = opening_v_start + opening_height

                    # Calculate u-coordinates with standard offsets
                    trimmer_offset = 0.125  # Use hardcoded values for fallback
                    king_stud_offset = 0.125
                    stud_width = 0.125

                    # Calculate stud centers
                    u_left = (
                        opening_u_start
                        - trimmer_offset
                        - king_stud_offset
                        - stud_width / 2
                    )
                    u_right = (
                        opening_u_start
                        + opening_width
                        + trimmer_offset
                        + king_stud_offset
                        + stud_width / 2
                    )

                    # Create header points in world coordinates
                    header_left = base_plane.PointAt(u_left, header_v, 0)
                    header_right = base_plane.PointAt(u_right, header_v, 0)

                    # Create a simple header geometry - a box using ExtrudeCurve
                    header_height = 0.25  # 3 inches in feet (hardcoded for fallback)
                    header_width = 0.292  # 3.5 inches in feet

                    header_profile = rg.Circle(
                        header_left, rg.Vector3d(0, 0, 1), header_width / 2
                    ).ToNurbsCurve()

                    header_path = rg.Line(header_left, header_right).ToNurbsCurve()
                    header_brep = rg.Brep.CreateFromSweep(
                        header_profile, header_path, True, 0.001
                    )[0]

                    if header_brep and header_brep.IsValid:
                        headers.append(header_brep)

                    # Only create sills for windows
                    if opening_type.lower() == "window":
                        # Calculate sill v-coordinate (bottom of opening)
                        sill_v = opening_v_start

                        # Create sill points
                        sill_left = base_plane.PointAt(u_left, sill_v, 0)
                        sill_right = base_plane.PointAt(u_right, sill_v, 0)

                        # Create simple sill geometry (same approach as header)
                        sill_height = 0.25
                        sill_profile = rg.Circle(
                            sill_left, rg.Vector3d(0, 0, 1), header_width / 2
                        ).ToNurbsCurve()

                        sill_path = rg.Line(sill_left, sill_right).ToNurbsCurve()
                        sill_brep = rg.Brep.CreateFromSweep(
                            sill_profile, sill_path, True, 0.001
                        )[0]

                        if sill_brep and sill_brep.IsValid:
                            sills.append(sill_brep)

                except Exception as e:
                    print(f"Error with opening {i+1} in fallback mode: {str(e)}")

            # Store the generated elements
            self.framing_elements["headers"] = headers
            self.framing_elements["sills"] = sills

            # Update generation status
            self.generation_status["headers_and_sills_generated"] = True

        except Exception as e:
            print(f"Error in fallback headers and sills generation: {str(e)}")
            import traceback

            print(traceback.format_exc())

    def _generate_trimmers(self) -> None:
        """
        Generates trimmer studs for all wall openings.

        Trimmers are generated after headers to ensure proper vertical alignment
        with the header bottom elevation. Each opening gets a pair of trimmers
        that run from the bottom plate to the underside of the header.
        """
        try:
            if self.generation_status.get("trimmers_generated", False):
                return

            # Ensure plates are generated first
            if not self.generation_status.get("plates_generated", False):
                self._generate_plates()

            # Ensure dependencies are generated first
            if not self.generation_status.get("headers_and_sills_generated", False):
                self._generate_headers_and_sills()

            openings = self.wall_data.get("openings", [])
            print(f"\nGenerating trimmers for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                print("No openings to process - skipping trimmers")
                self.generation_status["trimmers_generated"] = True
                self.framing_elements["trimmers"] = []
                return

            # Create trimmer generator
            trimmer_generator = TrimmerGenerator(self.wall_data)

            # Track generated elements
            trimmers = []

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    print(f"\nProcessing opening {i+1}")

                    # Get header bottom elevation for this opening if available
                    header_bottom = self._get_header_bottom_elevation(i)

                    # Get bottom plate boundary data as a dictionary
                    bottom_plate = self.framing_elements["bottom_plates"][0]
                    plate_boundary_data = bottom_plate.get_boundary_data()

                    print(f"Bottom plate boundary data: {plate_boundary_data}")

                    # Generate trimmers for this opening
                    opening_trimmers = trimmer_generator.generate_trimmers(
                        opening,
                        plate_boundary_data,
                        header_bottom_elevation=header_bottom,
                    )

                    if opening_trimmers:
                        trimmers.extend(opening_trimmers)
                        print(
                            f"Successfully created {len(opening_trimmers)} trimmers for opening {i+1}"
                        )

                except Exception as e:
                    print(f"Error creating trimmers for opening {i+1}: {str(e)}")
                    import traceback

                    print(traceback.format_exc())
                    continue

            # Store the generated elements
            self.framing_elements["trimmers"] = trimmers

            # Collect debug geometry
            for key in ["points", "planes", "profiles", "paths"]:
                if (
                    key in trimmer_generator.debug_geometry
                    and trimmer_generator.debug_geometry[key]
                ):
                    if key in self.debug_geometry:
                        self.debug_geometry[key].extend(
                            trimmer_generator.debug_geometry[key]
                        )
                    else:
                        self.debug_geometry[key] = trimmer_generator.debug_geometry[key]

            # Update generation status
            self.generation_status["trimmers_generated"] = True

        except Exception as e:
            print(f"Error generating trimmers: {str(e)}")
            import traceback

            print(traceback.format_exc())

            # Mark as completed to prevent future attempts
            self.generation_status["trimmers_generated"] = True

            # Store the generated elements
            self.framing_elements["trimmers"] = []

    def _generate_header_cripples(self) -> None:
        """
        Generates header cripple studs above wall openings.

        Header cripples are the short vertical studs that go between the top of
        the header and the underside of the top plate. They provide support for
        the top plate and transfer loads from it to the header below.
        """
        try:
            if self.generation_status.get("header_cripples_generated", False):
                return

            # Ensure dependencies are generated first
            if not self.generation_status.get("plates_generated", False):
                self._generate_plates()

            if not self.generation_status.get("headers_and_sills_generated", False):
                self._generate_headers_and_sills()

            if not self.generation_status.get("trimmers_generated", False):
                self._generate_trimmers()

            openings = self.wall_data.get("openings", [])
            print(f"\nGenerating header cripples for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                print("No openings to process - skipping header cripples")
                self.generation_status["header_cripples_generated"] = True
                self.framing_elements["header_cripples"] = []
                return

            # Create header cripple generator
            header_cripple_generator = HeaderCrippleGenerator(self.wall_data)

            # Get top plate data
            if not self.framing_elements.get("top_plates"):
                print("No top plates available for header cripple generation")
                self.generation_status["header_cripples_generated"] = True
                self.framing_elements["header_cripples"] = []
                return

            # Get the lowest top plate (should be the last one in the list - for double top plates)
            top_plate = self.framing_elements["top_plates"][-1]
            top_plate_data = top_plate.get_boundary_data()

            print(f"Top plate data for header cripples:")
            for key, value in top_plate_data.items():
                print(f"  {key}: {value}")

            # Track generated elements
            header_cripples = []

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    print(f"\nProcessing opening {i+1} for header cripples")

                    # Check opening type - generally headers are only needed above windows and doors
                    opening_type = opening.get("opening_type", "").lower()
                    print(f"Opening type: {opening_type}")

                    # Get header data including top elevation
                    headers = self.framing_elements.get("headers", [])
                    print(f"Available headers: {len(headers)}")

                    if i >= len(headers):
                        print(f"No header found for opening {i+1}, skipping")
                        continue

                    # Get header top elevation for this opening
                    header = headers[i]

                    # Get bounding box of header
                    bbox = header.GetBoundingBox(True)
                    if not bbox.IsValid:
                        print(f"Invalid bounding box for header {i+1}, skipping")
                        continue

                    # Get the top elevation of the header from the bounding box
                    header_top_elevation = bbox.Max.Z
                    print(f"Header top elevation: {header_top_elevation}")

                    # Create header data dictionary with required elevation
                    header_data = {"top_elevation": header_top_elevation}

                    # Get trimmer positions for this opening
                    trimmer_positions = self._get_trimmer_positions(i)
                    if trimmer_positions:
                        print(
                            f"Trimmer positions for opening {i+1}: left={trimmer_positions[0]}, right={trimmer_positions[1]}"
                        )
                    else:
                        print(
                            f"No trimmer positions found for opening {i+1}, will calculate from opening data"
                        )

                    # Generate header cripples for this opening
                    opening_cripples = (
                        header_cripple_generator.generate_header_cripples(
                            opening, header_data, top_plate_data, trimmer_positions
                        )
                    )

                    if opening_cripples:
                        header_cripples.extend(opening_cripples)
                        print(
                            f"Successfully created {len(opening_cripples)} header cripples for opening {i+1}"
                        )
                    else:
                        print(f"No header cripples created for opening {i+1}")

                except Exception as e:
                    print(f"Error creating header cripples for opening {i+1}: {str(e)}")
                    import traceback

                    print(traceback.format_exc())
                    continue

            # Store the generated elements
            self.framing_elements["header_cripples"] = header_cripples

            # Collect debug geometry
            for key in ["points", "planes", "profiles", "paths"]:
                if (
                    key in header_cripple_generator.debug_geometry
                    and header_cripple_generator.debug_geometry[key]
                ):
                    if key in self.debug_geometry:
                        self.debug_geometry[key].extend(
                            header_cripple_generator.debug_geometry[key]
                        )
                    else:
                        self.debug_geometry[
                            key
                        ] = header_cripple_generator.debug_geometry[key]

            # Update generation status
            self.generation_status["header_cripples_generated"] = True
            print(
                f"Header cripple generation complete: {len(header_cripples)} cripples created"
            )

        except Exception as e:
            print(f"Error generating header cripples: {str(e)}")
            import traceback

            print(traceback.format_exc())

            # Mark as completed to prevent future attempts
            self.generation_status["header_cripples_generated"] = True

            # Initialize empty list to prevent errors downstream
            self.framing_elements["header_cripples"] = []

    def _get_header_top_elevation(self, opening_index: int) -> Optional[float]:
        """
        Get the top elevation of the header for a specific opening.

        This method extracts the header top elevation from the generated
        header geometry if available.

        Args:
            opening_index: Index of the opening to get header for

        Returns:
            Top elevation of the header, or None if not available
        """
        try:
            headers = self.framing_elements.get("headers", [])
            print(f"Headers available: {len(headers)}")

            if opening_index < len(headers):
                header = headers[opening_index]
                print(f"Retrieved header for opening {opening_index}")

                # Get bounding box of header
                bbox = header.GetBoundingBox(True)
                print(f"Bounding box valid: {bbox.IsValid}")

                if bbox.IsValid:
                    print(f"Header bounds: Min={bbox.Min.Z}, Max={bbox.Max.Z}")
                    # Return the top elevation of the header
                    return bbox.Max.Z
                else:
                    print("Invalid bounding box for header")

            return None

        except Exception as e:
            print(f"Error getting header top elevation: {str(e)}")
            import traceback

            print(traceback.format_exc())
            return None

    def _get_header_bottom_elevation(self, opening_index: int) -> Optional[float]:
        """
        Get the bottom elevation of the header for a specific opening.

        This method extracts the header bottom elevation from the generated
        header geometry if available.

        Args:
            opening_index: Index of the opening to get header for

        Returns:
            Bottom elevation of the header, or None if not available
        """
        try:
            headers = self.framing_elements.get("headers", [])
            if opening_index < len(headers):
                header = headers[opening_index]

                # Get bounding box of header
                bbox = header.GetBoundingBox(True)
                if bbox.IsValid:
                    # Return the bottom elevation of the header
                    return bbox.Min.Z

            return None

        except Exception as e:
            print(f"Error getting header elevation: {str(e)}")
            return None

    def _generate_sill_cripples(self) -> None:
        """
        Generates sill cripple studs below window openings.

        Sill cripples are the short vertical studs that go between the top of
        the bottom plate and the underside of the sill below window openings.
        They provide support for the sill and transfer loads from it to the
        bottom plate below.
        """
        try:
            if self.generation_status.get("sill_cripples_generated", False):
                return

            # Ensure dependencies are generated first
            if not self.generation_status.get("plates_generated", False):
                self._generate_plates()

            if not self.generation_status.get("headers_and_sills_generated", False):
                self._generate_headers_and_sills()

            if not self.generation_status.get("trimmers_generated", False):
                self._generate_trimmers()

            openings = self.wall_data.get("openings", [])
            print(f"\nGenerating sill cripples for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                print("No openings to process - skipping sill cripples")
                self.generation_status["sill_cripples_generated"] = True
                self.framing_elements["sill_cripples"] = []
                return

            # Create sill cripple generator
            sill_cripple_generator = SillCrippleGenerator(self.wall_data)

            # Get bottom plate data
            if not self.framing_elements.get("bottom_plates"):
                print("No bottom plates available for sill cripple generation")
                self.generation_status["sill_cripples_generated"] = True
                self.framing_elements["sill_cripples"] = []
                return

            # Get the top bottom plate (should be the first one in the list for single bottom plate)
            bottom_plate = self.framing_elements["bottom_plates"][0]
            bottom_plate_data = bottom_plate.get_boundary_data()

            print(f"Bottom plate data for sill cripples:")
            for key, value in bottom_plate_data.items():
                print(f"  {key}: {value}")

            # Track generated elements
            sill_cripples = []

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    # Only process window openings
                    if opening.get("opening_type", "").lower() != "window":
                        print(f"Opening {i+1} is not a window, skipping sill cripples")
                        continue

                    print(f"\nProcessing opening {i+1} for sill cripples")

                    # Get sill data including bottom elevation
                    sills = self.framing_elements.get("sills", [])
                    print(f"Available sills: {len(sills)}")

                    # Find the sill for this opening
                    sill_index = None
                    for j, s in enumerate(sills):
                        # This is a simplified approach - in practice, you might need a more
                        # sophisticated way to match sills to window openings
                        if j == i:
                            sill_index = j
                            break

                    if sill_index is None or sill_index >= len(sills):
                        print(f"No sill found for window opening {i+1}, skipping")
                        continue

                    # Get sill bottom elevation for this opening
                    sill = sills[sill_index]

                    # Get bounding box of sill
                    bbox = sill.GetBoundingBox(True)
                    if not bbox.IsValid:
                        print(f"Invalid bounding box for sill {i+1}, skipping")
                        continue

                    # Get the bottom elevation of the sill from the bounding box
                    sill_bottom_elevation = bbox.Min.Z
                    print(f"Sill bottom elevation: {sill_bottom_elevation}")

                    # Create sill data dictionary with required elevation
                    sill_data = {"bottom_elevation": sill_bottom_elevation}

                    # Get trimmer positions for this opening
                    trimmer_positions = self._get_trimmer_positions(i)
                    if trimmer_positions:
                        print(
                            f"Trimmer positions for opening {i+1}: left={trimmer_positions[0]}, right={trimmer_positions[1]}"
                        )
                    else:
                        print(
                            f"No trimmer positions found for opening {i+1}, will calculate from opening data"
                        )

                    # Generate sill cripples for this opening
                    opening_cripples = sill_cripple_generator.generate_sill_cripples(
                        opening, sill_data, bottom_plate_data, trimmer_positions
                    )

                    if opening_cripples:
                        sill_cripples.extend(opening_cripples)
                        print(
                            f"Successfully created {len(opening_cripples)} sill cripples for opening {i+1}"
                        )
                    else:
                        print(f"No sill cripples created for opening {i+1}")

                except Exception as e:
                    print(f"Error creating sill cripples for opening {i+1}: {str(e)}")
                    import traceback

                    print(traceback.format_exc())
                    continue

            # Store the generated elements
            self.framing_elements["sill_cripples"] = sill_cripples

            # Collect debug geometry
            for key in ["points", "planes", "profiles", "paths"]:
                if (
                    key in sill_cripple_generator.debug_geometry
                    and sill_cripple_generator.debug_geometry[key]
                ):
                    if key in self.debug_geometry:
                        self.debug_geometry[key].extend(
                            sill_cripple_generator.debug_geometry[key]
                        )
                    else:
                        self.debug_geometry[
                            key
                        ] = sill_cripple_generator.debug_geometry[key]

            # Update generation status
            self.generation_status["sill_cripples_generated"] = True
            print(
                f"Sill cripple generation complete: {len(sill_cripples)} cripples created"
            )

        except Exception as e:
            print(f"Error generating sill cripples: {str(e)}")
            import traceback

            print(traceback.format_exc())

            # Mark as completed to prevent future attempts
            self.generation_status["sill_cripples_generated"] = True

            # Initialize empty list to prevent errors downstream
            self.framing_elements["sill_cripples"] = []

    def _get_trimmer_positions(
        self, opening_index: int
    ) -> Optional[Tuple[float, float]]:
        """
        Get the U-coordinates of the trimmers for a specific opening.

        This method extracts the trimmer positions from the generated
        trimmer geometry if available.

        Args:
            opening_index: Index of the opening to get trimmers for

        Returns:
            Tuple of (left, right) U-coordinates, or None if not available
        """
        try:
            print(f"\nDEBUG: _get_trimmer_positions for opening {opening_index}")
            trimmers = self.framing_elements.get("trimmers", [])
            print(f"Total trimmers available: {len(trimmers)}")

            if len(trimmers) < (opening_index + 1) * 2:
                print(
                    f"Not enough trimmers: need {(opening_index + 1) * 2}, have {len(trimmers)}"
                )
                return None

            # Get the pair of trimmers for this opening
            start_idx = opening_index * 2
            end_idx = (opening_index + 1) * 2
            opening_trimmers = trimmers[start_idx:end_idx]
            print(
                f"Extracted trimmers for opening {opening_index}: indices {start_idx} to {end_idx-1}"
            )
            print(f"Number of trimmers extracted: {len(opening_trimmers)}")

            if len(opening_trimmers) != 2:
                print(f"Expected 2 trimmers, got {len(opening_trimmers)}")
                return None

            # Get the base plane for position calculations
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                print("No base plane available")
                return None

            # Get bounding boxes for each trimmer to determine their positions
            trimmer_positions = []
            for i, trimmer in enumerate(opening_trimmers):
                bbox = trimmer.GetBoundingBox(True)
                if not bbox.IsValid:
                    print(f"Invalid bounding box for trimmer {i}")
                    continue

                # Calculate center point of bounding box
                center_x = (bbox.Min.X + bbox.Max.X) / 2
                center_y = (bbox.Min.Y + bbox.Max.Y) / 2
                center_point = rg.Point3d(center_x, center_y, bbox.Min.Z)

                # Project onto wall base plane to get u-coordinate
                u_coordinate = self._project_point_to_u_coordinate(
                    center_point, base_plane
                )
                trimmer_positions.append(u_coordinate)
                print(
                    f"Trimmer {i} center: ({center_x}, {center_y}), u-coordinate: {u_coordinate}"
                )

            if len(trimmer_positions) != 2:
                print(f"Failed to get positions for both trimmers")
                return None

            # Sort positions to ensure left < right
            trimmer_positions.sort()
            left_u, right_u = trimmer_positions

            print(f"Final trimmer positions: left={left_u}, right={right_u}")
            print(f"Distance between trimmers: {right_u - left_u}")

            return (left_u, right_u)

        except Exception as e:
            print(f"Error getting trimmer positions: {str(e)}")
            import traceback

            print(traceback.format_exc())
            return None

    def _generate_studs(self) -> None:
        """
        Generates standard wall studs based on Stud Cell (SC) information.

        This method creates vertical studs at regular intervals within stud cells,
        running from the top of the bottom plate to the bottom of the top plate.
        Stud positions are determined based on the configured stud spacing.
        """
        try:
            if self.generation_status.get("studs_generated", False):
                return

            # Ensure dependencies are generated first
            if not self.generation_status.get("plates_generated", False):
                self._generate_plates()

            if not self.generation_status.get("king_studs_generated", False):
                self._generate_king_studs()

            print("\nGenerating standard wall studs")

            # Create stud generator with king stud information to avoid overlaps
            stud_generator = StudGenerator(
                self.wall_data,
                self.framing_elements["bottom_plates"][0],  # Bottom plate (first one)
                self.framing_elements["top_plates"][-1],  # Top plate (last one)
                self.framing_elements.get(
                    "king_studs", []
                ),  # Pass king studs to avoid overlap
            )

            # Generate the studs
            studs = stud_generator.generate_studs()

            # Store the generated studs
            self.framing_elements["studs"] = studs

            # Collect debug geometry
            for key in ["points", "planes", "profiles", "paths"]:
                if (
                    key in stud_generator.debug_geometry
                    and stud_generator.debug_geometry[key]
                ):
                    if key in self.debug_geometry:
                        self.debug_geometry[key].extend(
                            stud_generator.debug_geometry[key]
                        )
                    else:
                        self.debug_geometry[key] = stud_generator.debug_geometry[key]

            # Update generation status
            self.generation_status["studs_generated"] = True
            print(f"Stud generation complete: {len(studs)} studs created")

        except Exception as e:
            print(f"Error generating studs: {str(e)}")
            import traceback

            print(traceback.format_exc())

            # Mark as completed to prevent future attempts
            self.generation_status["studs_generated"] = True

            # Initialize empty list to prevent errors downstream
            self.framing_elements["studs"] = []

    def _generate_row_blocking(self, studs: List[rg.Brep] = None) -> List[rg.Brep]:
        """
        Generate row blocking between wall studs.
        
        Args:
            studs: Optionally provide the list of studs to use for blocking.
                   If not provided, uses studs that were previously generated.
                   
        Returns:
            List of row blocking elements (Breps)
        """
        try:
            if not self.framing_config.get("include_blocking", False):
                return []
            
            # Get current studs if not provided
            if studs is None:
                studs = self.framing_elements["studs"] or []
            
            # If no studs, can't generate blocking
            if not studs:
                return []
                
            print("Generating row blocking")
            print(f"Framing config: {self.framing_config}")
            
            # Create blocking parameters
            blocking_params = BlockingParameters(
                include_blocking=self.framing_config.get("include_blocking", False),
                block_spacing=self.framing_config.get("block_spacing", 4.0),
                first_block_height=self.framing_config.get("first_block_height", 2.0),
                # Get pattern from framing config, default to "inline"
                pattern=self.framing_config.get("blocking_pattern", "inline")
            )
            
            print(f"Created blocking parameters: include={blocking_params.include_blocking}, "
                  f"spacing={blocking_params.block_spacing}, first_height={blocking_params.first_block_height}, "
                  f"pattern={blocking_params.pattern}")
            
            # Get a profile name for blocks - use the stud profile if available
            block_profile_name = self.framing_config.get("stud_profile", "2x4")
            
            # Get wall height from wall data
            wall_height = self.wall_data.get("height", 8.0)  # Default to 8' if not specified
            
            # Check for alternative wall height keys in wall_data
            if "wall_height" in self.wall_data:
                wall_height = self.wall_data.get("wall_height")
            elif "wall_top_elevation" in self.wall_data and "wall_base_elevation" in self.wall_data:
                wall_height = self.wall_data.get("wall_top_elevation") - self.wall_data.get("wall_base_elevation")
                
            print(f"Using wall height: {wall_height}ft")
            
            # Create row blocking generator with correct parameters
            blocking_generator = RowBlockingGenerator(
                wall_data=self.wall_data,
                studs=studs,  # Pass the list of studs
                framing_config=self.framing_config  # Pass the full config
            )
            
            # Update framing_config directly with pattern if needed
            if "blocking_pattern" in self.framing_config:
                pattern_str = self.framing_config["blocking_pattern"].lower().strip()
                if pattern_str == "staggered":
                    print("Explicitly setting pattern to STAGGERED in blocking generator")
                    from ..config.framing import BlockingPattern
                    blocking_generator.blocking_params.pattern = BlockingPattern.STAGGERED
                else:
                    print("Explicitly setting pattern to INLINE in blocking generator")
                    from ..config.framing import BlockingPattern
                    blocking_generator.blocking_params.pattern = BlockingPattern.INLINE
            
            # Update blocking params with our config values
            blocking_generator.blocking_params.include_blocking = blocking_params.include_blocking
            blocking_generator.blocking_params.block_spacing = blocking_params.block_spacing
            blocking_generator.blocking_params.first_block_height = blocking_params.first_block_height
                    
            # Set debugging params
            print(f"Set blocking param include_blocking = {blocking_generator.blocking_params.include_blocking}")
            print(f"Set blocking param block_spacing = {blocking_generator.blocking_params.block_spacing}")
            print(f"Set blocking param first_block_height = {blocking_generator.blocking_params.first_block_height}")
            
            # Get the base plane - this is required for proper coordinate calculations
            base_plane = self.wall_data.get("base_plane")
            if not base_plane or not isinstance(base_plane, rg.Plane):
                print("Error: Missing or invalid base_plane in wall data")
                return []
                
            # Calculate stud positions directly using stud geometries and base plane
            print(f"Setting {len(studs)} stud positions for blocking")
            stud_positions = []
            
            # Extract stud centerline U coordinates
            for i, stud in enumerate(studs):
                if not stud:
                    continue
                    
                # Get stud center point (at mid-height)
                try:
                    centroid = self._get_brep_centroid(stud)
                    if not centroid:
                        print(f"Warning: Could not calculate centroid for stud {i+1}")
                        continue
                        
                    # Project directly onto the base plane to get U coordinate
                    u_coord = self._project_point_to_u_coordinate(centroid, base_plane)
                    
                    # Log with safe access to point coordinates
                    print(f"Point: {centroid.X},{centroid.Y},{centroid.Z}, "
                          f"Wall Origin: {base_plane.Origin.X},{base_plane.Origin.Y},{base_plane.Origin.Z}, "
                          f"U-coord: {u_coord}")
                    
                    stud_positions.append(u_coord)
                    
                except Exception as e:
                    print(f"Error calculating stud position: {str(e)}")
                    continue
            
            # Sort positions from start to end of wall
            stud_positions.sort()
            
            # Set stud positions in blocking generator 
            blocking_generator.set_stud_positions(studs=None, positions=stud_positions)
            print(f"Updated stud positions: {len(stud_positions)} studs found")
            
            # Generate blocking
            blocking = blocking_generator.generate_blocking()
            
            if not blocking:
                print("Warning: No row blocking generated")
                
            return blocking
            
        except Exception as e:
            print(f"Error generating row blocking: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

    def get_generation_status(self) -> Dict[str, bool]:
        """
        Returns the current status of framing generation.

        This helper method allows users (including LLMs) to check what
        elements have been generated so far.

        Returns:
            Dictionary mapping element types to their generation status
        """
        return self.generation_status

    def get_messages(self) -> List[str]:
        """
        Returns any messages or warnings generated during framing creation.

        This helps with debugging and provides feedback to users about
        the generation process.

        Returns:
            List of message strings accumulated during generation
        """
        return self.messages

    def _print_wall_data_diagnostic(self) -> None:
        """
        Prints a diagnostic summary of the wall data for debugging purposes.
        """
        try:
            print("\nWall data diagnostic for wall {}:".format(
                self.wall_data.get('wall_id', 'Unknown')
            ))
            # Check for key wall data elements
            print(f"  base_plane: {self.wall_data.get('base_plane') is not None}")
            print(f"  wall_base_curve: {self.wall_data.get('wall_base_curve') is not None}")
            print(f"  wall_base_elevation: {self.wall_data.get('wall_base_elevation')}")
            print(f"  wall_top_elevation: {self.wall_data.get('wall_top_elevation')}")
        except Exception as e:
            print(f"Error printing wall data diagnostic: {str(e)}")
            import traceback
            print(traceback.format_exc())

    def _world_to_wall_u_coordinate(self, point: rg.Point3d) -> float:
        """
        Convert a world point to the wall's U coordinate (distance along wall).
        
        Args:
            point: Point in world coordinates
            
        Returns:
            U-coordinate (distance along wall)
        """
        try:
            # Get the base plane
            base_plane = self.wall_data.get("base_plane")
            if not base_plane:
                raise ValueError("Wall data missing base plane")
                
            # Project the point to the wall's U coordinate
            return self._project_point_to_u_coordinate(point, base_plane)
        
        except Exception as e:
            print(f"Error converting point to U-coordinate: {str(e)}")
            return 0.0

    def _get_brep_centroid(self, brep: rg.Brep) -> rg.Point3d:
        """
        Calculate the centroid (center point) of a Brep.
        
        This method extracts the center point of a Brep by using its bounding box.
        For complex Breps, this is an approximation of the true centroid.
        
        Args:
            brep: The Brep geometry to calculate centroid for
            
        Returns:
            Point3d representing the centroid
            
        Raises:
            ValueError: If the Brep is invalid or cannot compute bounding box
        """
        if not brep or not isinstance(brep, rg.Brep):
            raise ValueError("Invalid Brep provided")
            
        # Get bounding box in world coordinates
        bbox = brep.GetBoundingBox(True)
        
        if not bbox.IsValid:
            raise ValueError("Invalid bounding box for Brep")
            
        # Calculate centroid as average of min and max points
        centroid = rg.Point3d(
            (bbox.Min.X + bbox.Max.X) / 2.0,
            (bbox.Min.Y + bbox.Max.Y) / 2.0,
            (bbox.Min.Z + bbox.Max.Z) / 2.0
        )
        
        return centroid
