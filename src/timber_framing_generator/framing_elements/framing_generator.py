# File: timber_framing_generator/framing_elements/framing_generator.py

import os
import tempfile
import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
import sys
import math
import traceback

# Import our custom logging system
from ..utils.logging_config import get_logger, TimberFramingLogger

# Ensure logging is properly configured with TRACE level support
# If not already configured elsewhere, configure it here
log_dir = os.path.join(tempfile.gettempdir(), "timber_framing_generator")
TimberFramingLogger.configure(log_dir=log_dir, debug_mode=True)

# Initialize logger for this module with module-specific name
logger = get_logger(__name__)

try:
    import rhinoscriptsyntax as rs  # type: ignore
except ImportError:
    logger.warning("rhinoscriptsyntax not available")
    
try:
    import scriptcontext as sc  # type: ignore
except ImportError:
    logger.warning("scriptcontext not available")

# Check if we're running in Grasshopper/Rhino
is_rhino_environment: bool = 'rhinoscriptsyntax' in sys.modules or 'scriptcontext' in sys.modules
logger.debug(f"Running in Rhino environment: {is_rhino_environment}")

# Always import Rhino.Geometry for type annotations
import Rhino  # type: ignore
import Rhino.Geometry as rg  # type: ignore
from src.timber_framing_generator.utils.safe_rhino import safe_get_length, safe_get_bounding_box

# Only import rhinoinside if not already in Rhino environment
if not is_rhino_environment:
    logger.info("Not in Rhino environment, loading rhinoinside")
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
        logger.debug("Initializing FramingGenerator")
        logger.debug(f"Wall data keys: {list(wall_data.keys())}")
        
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
            logger.debug("Updating framing config with provided values")
            logger.debug(f"Custom framing config: {framing_config}")
            self.framing_config.update(framing_config)
        
        logger.debug(f"Final framing config: {self.framing_config}")

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
        logger.debug("FramingGenerator initialization complete")

    def generate_framing(self) -> Dict[str, List[rg.Brep]]:
        """
        Generate all framing elements.
        
        Returns:
            A dictionary containing all generated framing elements.
        """
        start_time = datetime.datetime.now()
        logger.info("\nStarting framing generation...")
        
        # Generate plates
        logger.debug("Generating plates")
        self._generate_plates()
        
        # King studs
        logger.debug("Generating king studs")
        self._generate_king_studs()
        
        # Headers and sills
        logger.debug("Generating headers and sills")
        self._generate_headers_and_sills()
        
        # Trimmers
        logger.debug("Generating trimmers")
        self._generate_trimmers()
        
        # Header cripples
        logger.debug("Generating header cripples")
        self._generate_header_cripples()
        
        # Sill cripples
        logger.debug("Generating sill cripples")
        self._generate_sill_cripples()
        
        # Standard studs
        logger.debug("Generating standard studs")
        self._generate_studs()
        
        # Row blocking
        logger.debug("Generating row blocking")
        try:
            # Check if row blocking is already generated
            if self.generation_status.get("blocking_generated", False):
                logger.info("Row blocking already generated, skipping.")
            else:
                # Generate row blocking using the already generated studs
                if "studs" in self.framing_elements and self.framing_elements["studs"]:
                    logger.debug(f"Found {len(self.framing_elements['studs'])} studs for blocking")
                    blocking = self._generate_row_blocking(studs=self.framing_elements["studs"])
                    
                    # Store the generated blocking
                    self.framing_elements["row_blocking"] = blocking
                    
                    # Collect debug geometry from the blocking generator
                    # Note: This part will need to be updated if we need debug geometry
                    
                    # Update generation status
                    self.generation_status["blocking_generated"] = True
                    logger.info(f"Row blocking generation complete: {len(blocking)} blocks created")
                else:
                    logger.warning("No studs available for row blocking, skipping.")
                    self.framing_elements["row_blocking"] = []
                    self.generation_status["blocking_generated"] = True
        except Exception as e:
            logger.error(f"Error in main generate_framing while processing row blocking: {str(e)}")
            logger.error(traceback.format_exc())
            # Initialize empty list to prevent errors downstream
            self.framing_elements["row_blocking"] = []
            self.generation_status["blocking_generated"] = True
        
        end_time = datetime.datetime.now()
        elapsed_time = (end_time - start_time).total_seconds()
        logger.info(f"Framing generation complete in {elapsed_time:.2f} seconds")
        
        # Display debugging info for wall
        self._log_wall_data_diagnostic()
        
        logger.info("Framing generation complete:")
        logger.info(f"Bottom plates: {len(self.framing_elements.get('bottom_plates', []))}")
        logger.info(f"Top plates: {len(self.framing_elements.get('top_plates', []))}")
        logger.info(f"King studs: {len(self.framing_elements.get('king_studs', []))}")
        logger.info(f"Headers: {len(self.framing_elements.get('headers', []))}")
        logger.info(f"Sills: {len(self.framing_elements.get('sills', []))}")
        logger.info(f"Trimmers: {len(self.framing_elements.get('trimmers', []))}")
        logger.info(f"Header cripples: {len(self.framing_elements.get('header_cripples', []))}")
        logger.info(f"Sill cripples: {len(self.framing_elements.get('sill_cripples', []))}")
        logger.info(f"Studs: {len(self.framing_elements.get('studs', []))}")
        logger.info(f"Row blocking: {len(self.framing_elements.get('row_blocking', []))}")
        
        # Log debug geometry count
        logger.debug("Debug geometry:")
        for key, items in self.debug_geometry.items():
            logger.debug(f"  {key}: {len(items)} items")
            
        return self.framing_elements

    def _generate_plates(self):
        """
        Generate top and bottom wall plates.
        """
        try:
            logger.debug("Starting plate generation")
            logger.debug("Wall base curve type: " + str(type(self.wall_data.get("wall_base_curve"))))
            
            # Skip if plates already generated
            if self.generation_status["plates_generated"]:
                logger.debug("Plates already generated, skipping")
                return

            logger.debug("Creating bottom plates")
            self.framing_elements["bottom_plates"] = create_plates(
                wall_data=self.wall_data,
                plate_type="bottom_plate",
                representation_type=self.framing_config["representation_type"],
                layers=self.framing_config["bottom_plate_layers"],
            )

            logger.debug("Creating top plates")
            self.framing_elements["top_plates"] = create_plates(
                wall_data=self.wall_data,
                plate_type="top_plate",
                representation_type=self.framing_config["representation_type"],
                layers=self.framing_config["top_plate_layers"],
            )

            self.generation_status["plates_generated"] = True
            self.messages.append("Plates generated successfully")
            logger.info(f"Created {len(self.framing_elements['bottom_plates'])} bottom plates")
            logger.info(f"Created {len(self.framing_elements['top_plates'])} top plates")
            
            # Add more detailed logging for debug level
            for i, plate in enumerate(self.framing_elements['bottom_plates']):
                logger.debug(f"Bottom plate {i} - length: {plate.length if hasattr(plate, 'length') else 'unknown'}")
            
            for i, plate in enumerate(self.framing_elements['top_plates']):
                logger.debug(f"Top plate {i} - length: {plate.length if hasattr(plate, 'length') else 'unknown'}")
            
        except Exception as e:
            logger.error(f"Error generating plates: {str(e)}")
            logger.error(traceback.format_exc())
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
            logger.debug("Starting king stud generation")
            if self.generation_status["king_studs_generated"]:
                logger.debug("King studs already generated, skipping")
                return

            if not self.generation_status["plates_generated"]:
                logger.error("Cannot generate king studs before plates")
                raise RuntimeError("Cannot generate king studs before plates")

            openings = self.wall_data.get("openings", [])
            logger.info(f"\nGenerating king studs for {len(openings)} openings")
            logger.debug(f"Openings data: {openings}")

            # Debug logging for bottom plate and top plate being used
            # For double plates: use the innermost plates (the ones that studs connect to)
            # bottom_plates: [sole_plate, bottom_plate] or [bottom_plate] -> use [0] for single, [-1] for uppermost
            # top_plates: [top_plate, cap_plate] or [top_plate] -> use [0] for the lowest one
            bottom_plate = self.framing_elements["bottom_plates"][-1]  # Uppermost bottom plate
            top_plate = self.framing_elements["top_plates"][0]  # Lowest top plate
            logger.debug(f"Using bottom plate: {id(bottom_plate)}")
            logger.debug(f"Using top plate: {id(top_plate)}")

            king_stud_generator = KingStudGenerator(
                self.wall_data,
                bottom_plate,
                top_plate,
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
                    logger.info(f"\nProcessing opening {i+1}")
                    logger.debug(f"Opening {i+1} data: {opening}")
                    
                    king_studs = king_stud_generator.generate_king_studs(opening)
                    logger.debug(f"Generated {len(king_studs)} king studs for opening {i+1}")
                    opening_king_studs.extend(king_studs)

                    # Log details about each generated king stud
                    for j, stud in enumerate(king_studs):
                        logger.debug(f"King stud {j} for opening {i+1} - position: {'left' if j == 0 else 'right'}")

                    # Collect debug geometry
                    for key in all_debug_geometry:
                        debug_items = king_stud_generator.debug_geometry.get(key, [])
                        all_debug_geometry[key].extend(debug_items)
                        logger.debug(f"Added {len(debug_items)} debug {key} for opening {i+1}")

                except Exception as e:
                    logger.error(f"Error with opening {i+1}: {str(e)}")
                    logger.error(traceback.format_exc())

            self.framing_elements["king_studs"] = opening_king_studs
            self.debug_geometry = all_debug_geometry
            self.generation_status["king_studs_generated"] = True
            logger.info(f"King stud generation complete: {len(opening_king_studs)} king studs created")

        except Exception as e:
            logger.error(f"Error generating king studs: {str(e)}")
            logger.error(traceback.format_exc())
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
                logger.warning("King studs not yet generated, can't extract positions")
                return positions

            # Get openings and king studs
            openings = self.wall_data.get("openings", [])
            king_studs = self.framing_elements.get("king_studs", [])

            # Get the base plane for position calculations
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available")
                return positions

            # Verify we have enough king studs (should be pairs for each opening)
            if len(king_studs) < 2 or len(openings) == 0:
                logger.warning(f"Not enough king studs ({len(king_studs)}) or openings ({len(openings)})")
                return positions

            # Process each opening
            for i in range(len(openings)):
                # Calculate the index for this opening's king studs (2 per opening)
                left_index = i * 2
                right_index = i * 2 + 1

                # Verify we have studs for this opening
                if right_index >= len(king_studs):
                    logger.warning(f"Missing king studs for opening {i+1}")
                    continue

                # Get the stud geometries
                left_stud = king_studs[left_index]
                right_stud = king_studs[right_index]

                try:
                    # Extract centerlines from the king stud geometries
                    left_centerline = self._extract_centerline_from_stud(left_stud)
                    right_centerline = self._extract_centerline_from_stud(right_stud)

                    if left_centerline is None or right_centerline is None:
                        logger.warning(f"Failed to extract centerlines for opening {i+1}")
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

                    logger.info(f"Extracted king stud positions for opening {i+1}:")
                    logger.info(f"  Left stud centerline: u={left_u}")
                    logger.info(f"  Right stud centerline: u={right_u}")

                    # DEBUG: Calculate and report stud inner faces
                    king_stud_width = FRAMING_PARAMS.get("king_stud_width", 1.5 / 12)
                    inner_left = left_u + (king_stud_width / 2)
                    inner_right = right_u - (king_stud_width / 2)
                    logger.info(f"  Inner face positions: left={inner_left}, right={inner_right}")
                    logger.info(f"  Resulting span width: {inner_right - inner_left}")

                except Exception as e:
                    logger.error(f"Error extracting king stud positions for opening {i+1}: {str(e)}")
                    logger.error(traceback.format_exc())

            return positions

        except Exception as e:
            logger.error(f"Error getting king stud positions: {str(e)}")
            logger.error(traceback.format_exc())
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
                    # Check if IsPointInside method exists
                    if hasattr(stud_brep, 'IsPointInside'):
                        if stud_brep.IsPointInside(test_point, 0.01, True):
                            return path
                    else:
                        # Fallback method if IsPointInside isn't available
                        try:
                            # Use closest point method instead
                            closest_point = stud_brep.ClosestPoint(test_point)
                            if closest_point and test_point.DistanceTo(closest_point) < 0.05:
                                # If the point is very close to the Brep, consider it inside
                                logger.debug("Using fallback proximity check for point inside Brep")
                                return path
                        except Exception as closest_point_error:
                            logger.debug(f"Fallback closest point check failed: {str(closest_point_error)}")
                            
                            # Final fallback - check if point is within bounding box
                            try:
                                bbox = safe_get_bounding_box(stud_brep, True)
                                if bbox and bbox.IsValid and bbox.Contains(test_point):
                                    logger.debug("Using bounding box check for point inside Brep")
                                    return path
                            except Exception as bbox_error:
                                logger.debug(f"Bounding box check failed: {str(bbox_error)}")
                except Exception as e:
                    logger.error(f"Error checking path: {str(e)}")
                    continue

            # If we can't find a path curve, try to extract it from the Brep
            # For a typical extruded stud, we can use the Brep's bounding box
            bbox = safe_get_bounding_box(stud_brep, True)
            if bbox.IsValid:
                # Vertical centerline through the middle of the stud
                center_x = (bbox.Min.X + bbox.Max.X) / 2
                center_y = (bbox.Min.Y + bbox.Max.Y) / 2

                # Create a line from bottom to top
                start = rg.Point3d(center_x, center_y, bbox.Min.Z)
                end = rg.Point3d(center_x, center_y, bbox.Max.Z)

                return rg.LineCurve(start, end)

            # If that fails, return None
            logger.warning("Failed to extract centerline from stud Brep")
            return None

        except Exception as e:
            logger.error(f"Error extracting centerline from stud: {str(e)}")
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
            logger.error(f"Error projecting point to u-coordinate: {str(e)}")
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
            logger.info(f"\nGenerating headers and sills for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                logger.info("No openings to process - skipping headers and sills")
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
                    logger.info(f"\nProcessing opening {i+1}")

                    # Get king stud positions for this opening if available
                    opening_king_stud_positions = self._get_king_stud_positions().get(i)

                    # Generate header using direct base plane approach
                    header = header_generator.generate_header(
                        opening, opening_king_stud_positions
                    )
                    if header:
                        headers.append(header)
                        logger.info(f"Successfully created header for opening {i+1}")

                    # Generate sill using direct base plane approach
                    if opening["opening_type"].lower() == "window":
                        sill = sill_generator.generate_sill(opening)
                        if sill:
                            sills.append(sill)
                            logger.info(f"Successfully created sill for opening {i+1}")

                except Exception as e:
                    logger.error(f"Error with opening {i+1}: {str(e)}")
                    logger.error(traceback.format_exc())
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
            logger.error(f"Error generating headers and sills: {str(e)}")
            logger.error(traceback.format_exc())

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
            logger.info(f"Using fallback approach for {len(openings)} openings")

            # Track generated elements
            headers = []
            sills = []

            # Get wall base plane
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for fallback header/sill generation")
                return

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    logger.info(f"Processing opening {i+1} in fallback mode")

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
                    logger.error(f"Error with opening {i+1} in fallback mode: {str(e)}")

            # Store the generated elements
            self.framing_elements["headers"] = headers
            self.framing_elements["sills"] = sills

            # Update generation status
            self.generation_status["headers_and_sills_generated"] = True

        except Exception as e:
            logger.error(f"Error in fallback headers and sills generation: {str(e)}")
            logger.error(traceback.format_exc())

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
            logger.info(f"\nGenerating trimmers for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                logger.info("No openings to process - skipping trimmers")
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
                    logger.info(f"\nProcessing opening {i+1}")

                    # Get header bottom elevation for this opening if available
                    header_bottom = self._get_header_bottom_elevation(i)

                    # Get bottom plate boundary data as a dictionary
                    # For double bottom plates [sole_plate, bottom_plate], use [-1] for the uppermost one
                    bottom_plate = self.framing_elements["bottom_plates"][-1]
                    plate_boundary_data = bottom_plate.get_boundary_data()

                    logger.info(f"Bottom plate boundary data: {plate_boundary_data}")

                    # Generate trimmers for this opening
                    opening_trimmers = trimmer_generator.generate_trimmers(
                        opening,
                        plate_boundary_data,
                        header_bottom_elevation=header_bottom,
                    )

                    if opening_trimmers:
                        trimmers.extend(opening_trimmers)
                        logger.info(
                            f"Successfully created {len(opening_trimmers)} trimmers for opening {i+1}"
                        )

                except Exception as e:
                    logger.error(f"Error creating trimmers for opening {i+1}: {str(e)}")
                    logger.error(traceback.format_exc())
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
            logger.error(f"Error generating trimmers: {str(e)}")
            logger.error(traceback.format_exc())

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
            logger.info(f"\nGenerating header cripples for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                logger.info("No openings to process - skipping header cripples")
                self.generation_status["header_cripples_generated"] = True
                self.framing_elements["header_cripples"] = []
                return

            # Create header cripple generator
            header_cripple_generator = HeaderCrippleGenerator(self.wall_data)

            # Get top plate data
            if not self.framing_elements.get("top_plates"):
                logger.warning("No top plates available for header cripple generation")
                self.generation_status["header_cripples_generated"] = True
                self.framing_elements["header_cripples"] = []
                return

            # Get the lowest top plate (the first one in the list for double top plates)
            # For double top plates: [top_plate, cap_plate] - we need top_plate[0]
            # The "lowest" top plate is the one at index 0, whose bottom face is where studs connect
            top_plate = self.framing_elements["top_plates"][0]
            top_plate_data = top_plate.get_boundary_data()

            logger.info(f"Top plate data for header cripples:")
            for key, value in top_plate_data.items():
                logger.info(f"  {key}: {value}")

            # Track generated elements
            header_cripples = []

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    logger.info(f"\nProcessing opening {i+1} for header cripples")

                    # Check opening type - generally headers are only needed above windows and doors
                    opening_type = opening.get("opening_type", "").lower()
                    logger.info(f"Opening type: {opening_type}")

                    # Get header data including top elevation
                    headers = self.framing_elements.get("headers", [])
                    logger.info(f"Available headers: {len(headers)}")

                    if i >= len(headers):
                        logger.warning(f"No header found for opening {i+1}, skipping")
                        continue

                    # Get header top elevation for this opening
                    header = headers[i]

                    # Get bounding box of header
                    bbox = safe_get_bounding_box(header, True)
                    if not bbox.IsValid:
                        logger.warning(f"Invalid bounding box for header {i+1}, skipping")
                        continue

                    # Get the top elevation of the header from the bounding box
                    header_top_elevation = bbox.Max.Z
                    logger.info(f"Header top elevation: {header_top_elevation}")

                    # Create header data dictionary with required elevation
                    header_data = {"top_elevation": header_top_elevation}

                    # Get trimmer positions for this opening
                    trimmer_positions = self._get_trimmer_positions(i)
                    if trimmer_positions:
                        logger.info(
                            f"Trimmer positions for opening {i+1}: left={trimmer_positions[0]}, right={trimmer_positions[1]}"
                        )
                    else:
                        logger.warning(
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
                        logger.info(
                            f"Successfully created {len(opening_cripples)} header cripples for opening {i+1}"
                        )
                    else:
                        logger.warning(f"No header cripples created for opening {i+1}")

                except Exception as e:
                    logger.error(f"Error creating header cripples for opening {i+1}: {str(e)}")
                    logger.error(traceback.format_exc())
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
            logger.info(
                f"Header cripple generation complete: {len(header_cripples)} cripples created"
            )

        except Exception as e:
            logger.error(f"Error generating header cripples: {str(e)}")
            logger.error(traceback.format_exc())

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
            logger.info(f"Headers available: {len(headers)}")

            if opening_index < len(headers):
                header = headers[opening_index]
                logger.info(f"Retrieved header for opening {opening_index}")

                # Get bounding box of header
                bbox = safe_get_bounding_box(header, True)
                logger.info(f"Bounding box valid: {bbox.IsValid}")

                if bbox.IsValid:
                    logger.info(f"Header bounds: Min={bbox.Min.Z}, Max={bbox.Max.Z}")
                    # Return the top elevation of the header
                    return bbox.Max.Z
                else:
                    logger.warning("Invalid bounding box for header")

            return None

        except Exception as e:
            logger.error(f"Error getting header top elevation: {str(e)}")
            logger.error(traceback.format_exc())
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
                bbox = safe_get_bounding_box(header, True)
                if bbox.IsValid:
                    # Return the bottom elevation of the header
                    return bbox.Min.Z

            return None

        except Exception as e:
            logger.error(f"Error getting header elevation: {str(e)}")
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
            logger.info(f"\nGenerating sill cripples for {len(openings)} openings")

            # Skip if no openings
            if not openings:
                logger.info("No openings to process - skipping sill cripples")
                self.generation_status["sill_cripples_generated"] = True
                self.framing_elements["sill_cripples"] = []
                return

            # Create sill cripple generator
            sill_cripple_generator = SillCrippleGenerator(self.wall_data)

            # Get bottom plate data
            if not self.framing_elements.get("bottom_plates"):
                logger.warning("No bottom plates available for sill cripple generation")
                self.generation_status["sill_cripples_generated"] = True
                self.framing_elements["sill_cripples"] = []
                return

            # Get the uppermost bottom plate (where sill cripples connect to)
            # For double bottom plates [sole_plate, bottom_plate], use [-1] for the uppermost one
            bottom_plate = self.framing_elements["bottom_plates"][-1]
            bottom_plate_data = bottom_plate.get_boundary_data()

            logger.info(f"Bottom plate data for sill cripples:")
            for key, value in bottom_plate_data.items():
                logger.info(f"  {key}: {value}")

            # Track generated elements
            sill_cripples = []

            # Process each opening
            for i, opening in enumerate(openings):
                try:
                    # Only process window openings
                    if opening.get("opening_type", "").lower() != "window":
                        logger.info(f"Opening {i+1} is not a window, skipping sill cripples")
                        continue

                    logger.info(f"\nProcessing opening {i+1} for sill cripples")

                    # Get sill data including bottom elevation
                    sills = self.framing_elements.get("sills", [])
                    logger.info(f"Available sills: {len(sills)}")

                    # Find the sill for this opening
                    sill_index = None
                    for j, s in enumerate(sills):
                        # This is a simplified approach - in practice, you might need a more
                        # sophisticated way to match sills to window openings
                        if j == i:
                            sill_index = j
                            break

                    if sill_index is None or sill_index >= len(sills):
                        logger.warning(f"No sill found for window opening {i+1}, skipping")
                        continue

                    # Get sill bottom elevation for this opening
                    sill = sills[sill_index]

                    # Get bounding box of sill
                    bbox = safe_get_bounding_box(sill, True)
                    if not bbox.IsValid:
                        logger.warning(f"Invalid bounding box for sill {i+1}, skipping")
                        continue

                    # Get the bottom elevation of the sill from the bounding box
                    sill_bottom_elevation = bbox.Min.Z
                    logger.info(f"Sill bottom elevation: {sill_bottom_elevation}")

                    # Create sill data dictionary with required elevation
                    sill_data = {"bottom_elevation": sill_bottom_elevation}

                    # Get trimmer positions for this opening
                    trimmer_positions = self._get_trimmer_positions(i)
                    if trimmer_positions:
                        logger.info(
                            f"Trimmer positions for opening {i+1}: left={trimmer_positions[0]}, right={trimmer_positions[1]}"
                        )
                    else:
                        logger.warning(
                            f"No trimmer positions found for opening {i+1}, will calculate from opening data"
                        )

                    # Generate sill cripples for this opening
                    opening_cripples = sill_cripple_generator.generate_sill_cripples(
                        opening, sill_data, bottom_plate_data, trimmer_positions
                    )

                    if opening_cripples:
                        sill_cripples.extend(opening_cripples)
                        logger.info(
                            f"Successfully created {len(opening_cripples)} sill cripples for opening {i+1}"
                        )
                    else:
                        logger.warning(f"No sill cripples created for opening {i+1}")

                except Exception as e:
                    logger.error(f"Error creating sill cripples for opening {i+1}: {str(e)}")
                    logger.error(traceback.format_exc())
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
            logger.info(
                f"Sill cripple generation complete: {len(sill_cripples)} cripples created"
            )

        except Exception as e:
            logger.error(f"Error generating sill cripples: {str(e)}")
            logger.error(traceback.format_exc())

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
            logger.debug(f"\nDEBUG: _get_trimmer_positions for opening {opening_index}")
            trimmers = self.framing_elements.get("trimmers", [])
            logger.info(f"Total trimmers available: {len(trimmers)}")

            if len(trimmers) < (opening_index + 1) * 2:
                logger.warning(
                    f"Not enough trimmers: need {(opening_index + 1) * 2}, have {len(trimmers)}"
                )
                return None

            # Get the pair of trimmers for this opening
            start_idx = opening_index * 2
            end_idx = (opening_index + 1) * 2
            opening_trimmers = trimmers[start_idx:end_idx]
            logger.info(
                f"Extracted trimmers for opening {opening_index}: indices {start_idx} to {end_idx-1}"
            )
            logger.info(f"Number of trimmers extracted: {len(opening_trimmers)}")

            if len(opening_trimmers) != 2:
                logger.warning(f"Expected 2 trimmers, got {len(opening_trimmers)}")
                return None

            # Get the base plane for position calculations
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available")
                return None

            # Get bounding boxes for each trimmer to determine their positions
            trimmer_positions = []
            for i, trimmer in enumerate(opening_trimmers):
                bbox = safe_get_bounding_box(trimmer, True)
                if not bbox.IsValid:
                    logger.warning(f"Invalid bounding box for trimmer {i}")
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
                logger.info(
                    f"Trimmer {i} center: ({center_x}, {center_y}), u-coordinate: {u_coordinate}"
                )

            if len(trimmer_positions) != 2:
                logger.warning(f"Failed to get positions for both trimmers")
                return None

            # Sort positions to ensure left < right
            trimmer_positions.sort()
            left_u, right_u = trimmer_positions

            logger.info(f"Final trimmer positions: left={left_u}, right={right_u}")
            logger.info(f"Distance between trimmers: {right_u - left_u}")

            return (left_u, right_u)

        except Exception as e:
            logger.error(f"Error getting trimmer positions: {str(e)}")
            logger.error(traceback.format_exc())
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

            logger.info("\nGenerating standard wall studs")

            # Create stud generator with king stud information to avoid overlaps
            # For double plates: studs connect to innermost plates
            # bottom_plates: [sole_plate, bottom_plate] or [bottom_plate] -> use [-1] for uppermost
            # top_plates: [top_plate, cap_plate] or [top_plate] -> use [0] for lowest
            stud_generator = StudGenerator(
                self.wall_data,
                self.framing_elements["bottom_plates"][-1],  # Uppermost bottom plate
                self.framing_elements["top_plates"][0],  # Lowest top plate
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
            logger.info(f"Stud generation complete: {len(studs)} studs created")

        except Exception as e:
            logger.error(f"Error generating studs: {str(e)}")
            logger.error(traceback.format_exc())

            # Mark as completed to prevent future attempts
            self.generation_status["studs_generated"] = True

            # Initialize empty list to prevent errors downstream
            self.framing_elements["studs"] = []

    def _generate_row_blocking(self, studs: List[rg.Brep] = None) -> List[rg.Brep]:
        """
        Generate row blocking elements between studs.
        
        This method generates horizontal blocking elements between studs in the wall frame.
        
        Args:
            studs: List of stud geometries (Breps)
            
        Returns:
            List of block geometries (Breps)
        """
        if not self.framing_config.get("include_blocking", False):
            logger.info("Row blocking is disabled in config")
            return []
            
        if not studs and not hasattr(self, "studs"):
            logger.info("No studs provided for row blocking")
            return []
            
        # Use provided studs or studs from the generator
        all_studs = studs if studs else getattr(self, "studs", [])
        
        # Check if cells exist in wall_data, create self.cells attribute if needed
        if not hasattr(self, "cells"):
            if "cells" in self.wall_data:
                self.cells = self.wall_data["cells"]
                logger.info(f"Loaded {len(self.cells)} cells from wall_data")
            else:
                logger.warning("No cells available in wall_data")
                self.cells = []
                return []
        
        # Group studs by cell to help with debugging
        stud_positions_by_cell = {}
        stud_count = len(all_studs) if all_studs else 0
        logger.info(f"\n===== ROW BLOCKING SETUP =====")
        logger.info(f"Total studs available: {stud_count}")
        
        # Group king studs by cell
        king_stud_count = len(self.king_studs) if hasattr(self, "king_studs") else 0
        logger.info(f"King studs available: {king_stud_count}")
        
        # Count header cripples and sill cripples
        header_cripple_count = len(self.framing_elements.get("header_cripples", []))
        sill_cripple_count = len(self.framing_elements.get("sill_cripples", []))
        logger.info(f"Header cripples available: {header_cripple_count}")
        logger.info(f"Sill cripples available: {sill_cripple_count}")
        
        # Print detailed information about header cripples
        if header_cripple_count > 0:
            logger.info("\nHEADER CRIPPLE DETAILS:")
            for i, cripple in enumerate(self.framing_elements.get("header_cripples", [])):
                # Get bounding box
                if hasattr(cripple, "GetBoundingBox"):
                    try:
                        bbox = safe_get_bounding_box(cripple, True)
                        min_pt = bbox.Min
                        max_pt = bbox.Max
                        
                        # Get u-coordinate in wall domain
                        u_coord = self._project_point_to_u_coordinate(min_pt, self.wall_data.get("base_plane"))
                        
                        # Get height (z-range)
                        z_min = min_pt.Z
                        z_max = max_pt.Z
                        height = z_max - z_min
                        
                        logger.info(f"  Header Cripple {i+1}: u={u_coord:.4f}, height={height:.4f}, z-range={z_min:.4f} to {z_max:.4f}")
                        
                        # Find cell for this cripple
                        cell_found = False
                        for cell in self.cells:
                            u_start = cell.get("u_start", 0)
                            u_end = cell.get("u_end", 0)
                            cell_type = cell.get("cell_type", "unknown")
                            
                            # Check if cripple is in this cell
                            if u_start <= u_coord <= u_end:
                                cell_id = f"{cell_type}_{u_start}_{u_end}"
                                logger.info(f"    Belongs to cell: {cell_id}")
                                cell_found = True
                                
                                # Add to stud positions for this cell
                                if cell_id not in stud_positions_by_cell:
                                    stud_positions_by_cell[cell_id] = []
                                
                                # Add the u-coordinate to the list if not already there
                                if u_coord not in stud_positions_by_cell[cell_id]:
                                    stud_positions_by_cell[cell_id].append(u_coord)
                                    logger.info(f"    Added to cell {cell_id} for blocking")
                                    
                                # For header cripples, we especially care about HCC cells
                                if cell_type == "HCC":
                                    logger.info(f"    This is a header cripple in an HCC cell - perfect match!")
                        
                        if not cell_found:
                            logger.warning(f"    WARNING: Could not find a cell for header cripple at u={u_coord:.4f}")
                    except Exception as e:
                        logger.error(f"Error getting header cripple {i+1} info: {str(e)}")
                else:
                    logger.info(f"  Header Cripple {i+1}: Could not get bounding box")
        
        # Print detailed information about sill cripples
        if sill_cripple_count > 0:
            logger.info("\nSILL CRIPPLE DETAILS:")
            for i, cripple in enumerate(self.framing_elements.get("sill_cripples", [])):
                # Get bounding box
                if hasattr(cripple, "GetBoundingBox"):
                    try:
                        bbox = safe_get_bounding_box(cripple, True)
                        min_pt = bbox.Min
                        max_pt = bbox.Max
                        
                        # Get u-coordinate in wall domain
                        u_coord = self._project_point_to_u_coordinate(min_pt, self.wall_data.get("base_plane"))
                        
                        # Get height (z-range)
                        z_min = min_pt.Z
                        z_max = max_pt.Z
                        height = z_max - z_min
                        
                        logger.info(f"  Sill Cripple {i+1}: u={u_coord:.4f}, height={height:.4f}, z-range={z_min:.4f} to {z_max:.4f}")
                        
                        # Find cell for this cripple
                        cell_found = False
                        for cell in self.cells:
                            u_start = cell.get("u_start", 0)
                            u_end = cell.get("u_end", 0)
                            cell_type = cell.get("cell_type", "unknown")
                            
                            # Check if cripple is in this cell
                            if u_start <= u_coord <= u_end:
                                cell_id = f"{cell_type}_{u_start}_{u_end}"
                                logger.info(f"    Belongs to cell: {cell_id}")
                                cell_found = True
                                
                                # Add to stud positions for this cell
                                if cell_id not in stud_positions_by_cell:
                                    stud_positions_by_cell[cell_id] = []
                                
                                # Add the u-coordinate to the list if not already there
                                if u_coord not in stud_positions_by_cell[cell_id]:
                                    stud_positions_by_cell[cell_id].append(u_coord)
                                    logger.info(f"    Added to cell {cell_id} for blocking")
                                    
                                # For sill cripples, we especially care about SCC cells
                                if cell_type == "SCC":
                                    logger.info(f"    This is a sill cripple in an SCC cell - perfect match!")
                        
                        if not cell_found:
                            logger.warning(f"    WARNING: Could not find a cell for sill cripple at u={u_coord:.4f}")
                    except Exception as e:
                        logger.error(f"Error getting sill cripple {i+1} info: {str(e)}")
                else:
                    logger.info(f"  Sill Cripple {i+1}: Could not get bounding box")
        
        # Process regular studs
        for i, stud in enumerate(all_studs):
            try:
                # Get the bounding box of the stud
                bbox = safe_get_bounding_box(stud, True)
                min_pt = bbox.Min
                max_pt = bbox.Max
                
                # Get the u-coordinate (position along wall length)
                u_coord = self._project_point_to_u_coordinate(min_pt, self.wall_data.get("base_plane"))
                
                # Find which cell this stud belongs to
                for cell in self.cells:
                    u_start = cell.get("u_start", 0)
                    u_end = cell.get("u_end", 0)
                    cell_type = cell.get("cell_type", "unknown")
                    
                    # Check if stud is in this cell
                    if u_start <= u_coord <= u_end:
                        cell_id = f"{cell_type}_{u_start}_{u_end}"
                        
                        # Add to stud positions for this cell
                        if cell_id not in stud_positions_by_cell:
                            stud_positions_by_cell[cell_id] = []
                        
                        # Add the u-coordinate to the list
                        if u_coord not in stud_positions_by_cell[cell_id]:
                            stud_positions_by_cell[cell_id].append(u_coord)
            except Exception as e:
                logger.error(f"Error processing stud {i}: {str(e)}")
        
        # Process king studs (if any)
        if hasattr(self, "king_studs") and self.king_studs:
            for i, stud in enumerate(self.king_studs):
                try:
                    # Get the bounding box of the king stud
                    bbox = safe_get_bounding_box(stud, True)
                    min_pt = bbox.Min
                    max_pt = bbox.Max
                    
                    # Get the u-coordinate (position along wall length)
                    u_coord = self._project_point_to_u_coordinate(min_pt, self.wall_data.get("base_plane"))
                    
                    # Find which cell this king stud belongs to
                    for cell in self.cells:
                        u_start = cell.get("u_start", 0)
                        u_end = cell.get("u_end", 0)
                        cell_type = cell.get("cell_type", "unknown")
                        
                        # Check if king stud is in this cell or at a boundary
                        if u_start <= u_coord <= u_end or abs(u_coord - u_start) < 0.001 or abs(u_coord - u_end) < 0.001:
                            cell_id = f"{cell_type}_{u_start}_{u_end}"
                            
                            # Add to stud positions for this cell
                            if cell_id not in stud_positions_by_cell:
                                stud_positions_by_cell[cell_id] = []
                            
                            # Add the u-coordinate to the list
                            if u_coord not in stud_positions_by_cell[cell_id]:
                                stud_positions_by_cell[cell_id].append(u_coord)
                except Exception as e:
                    logger.error(f"Error processing king stud {i}: {str(e)}")
        
        # Print summary by cell
        logger.info("\nVERTICAL ELEMENTS BY CELL:")
        for cell_id, positions in stud_positions_by_cell.items():
            logger.info(f"  Cell {cell_id}: {len(positions)} vertical elements at positions {[f'{pos:.4f}' for pos in sorted(positions)]}")
        
        if not stud_positions_by_cell:
            logger.warning("No stud positions collected for blocking - check cell assignments")
            return []
            
        # Make sure the cells are included in wall_data for the blocking generator
        if "cells" not in self.wall_data:
            self.wall_data["cells"] = self.cells
            
        # Get the header cripples and sill cripples from framing_elements
        header_cripples = self.framing_elements.get("header_cripples", [])
        sill_cripples = self.framing_elements.get("sill_cripples", [])
            
        # Create the RowBlockingGenerator with all appropriate framing elements
        blocking_generator = RowBlockingGenerator(
            wall_data=self.wall_data, 
            studs=self.framing_elements.get("studs", []),
            king_studs=self.framing_elements.get("king_studs", []),
            trimmers=self.framing_elements.get("trimmers", []),
            header_cripples=header_cripples,
            sill_cripples=sill_cripples,
            blocking_pattern=self.framing_config.get("blocking_pattern", "INLINE"),
            include_blocking=self.framing_config.get("include_blocking", True),
            block_spacing=self.framing_config.get("block_spacing", 4.0),
            first_block_height=self.framing_config.get("first_block_height", 2.0)
        )
        
        logger.info(f"Created RowBlockingGenerator with {len(stud_positions_by_cell)} cells")
        logger.info(f"Passed {len(header_cripples)} header cripples")
        logger.info(f"Passed {len(sill_cripples)} sill cripples")
        logger.info("===== END ROW BLOCKING SETUP =====\n")
        
        # Generate the blocking elements
        return blocking_generator.generate_blocking()
        
    def _log_wall_data_diagnostic(self):
        """Log diagnostic information about wall data"""
        logger.info("\n===== WALL DATA DIAGNOSTIC =====")
        if hasattr(self, 'wall_data'):
            logger.info(f"Wall ID: {self.wall_data.get('wall_id', 'Unknown')}")
            logger.info(f"Wall height: {self.wall_data.get('wall_height', 'Unknown')}")
            logger.info(f"Wall length: {self.wall_data.get('wall_length', 'Unknown')}")
            logger.info(f"Number of cells: {len(self.wall_data.get('cells', []))}")
            logger.info(f"Number of openings: {len(self.wall_data.get('openings', []))}")
        else:
            logger.info("No wall data available")
        logger.info("===== END WALL DATA DIAGNOSTIC =====\n")
