# File: timber_framing_generator/framing_elements/studs.py

from typing import Dict, List, Any, Optional
import Rhino.Geometry as rg
import math
from src.timber_framing_generator.config.framing import FRAMING_PARAMS, PROFILES
from src.timber_framing_generator.utils.safe_rhino import safe_closest_point, safe_get_length, safe_create_extrusion, safe_get_bounding_box
from ..utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)


def calculate_stud_locations(
    cell, stud_spacing=0.6, start_location=None, remove_first=False, remove_last=False
):
    """
    Calculates stud locations for a given wall cell (or segment) based on its base geometry.
    This intermediate step takes a cell (which should include a base line or a segment)
    and returns a list of points representing the locations for studs.

    Keyword Args:
        stud_spacing (float): Desired spacing between studs.
        start_location: Optional starting point (rg.Point3d) or parameter on the base geometry
                        where stud distribution should begin.
        remove_first (bool): If True, skip the first stud (to avoid collision with a king stud).
        remove_last (bool): If True, skip the last stud.

    Returns:
        list: A list of rg.Point3d objects representing stud locations.
    """
    logger.debug("Calculating stud locations")
    logger.debug(f"Parameters - stud_spacing: {stud_spacing}, remove_first: {remove_first}, remove_last: {remove_last}")
    
    # Assume the cell contains a key "base_line" with a Rhino.Geometry.Curve representing the stud area.
    base_line = cell.get("base_line")
    if not base_line or not isinstance(base_line, rg.Curve):
        logger.error("Invalid base_line for stud placement")
        raise ValueError(
            "Cell must contain a valid 'base_line' (Rhino.Geometry.Curve) for stud placement."
        )

    # Determine the starting parameter. If start_location is given and is a point, get its parameter on the line.
    if start_location and isinstance(start_location, rg.Point3d):
        logger.debug(f"Using start location point: ({start_location.X}, {start_location.Y}, {start_location.Z})")
        success, t0 = safe_closest_point(base_line, start_location)
        if not success:
            logger.warning("Failed to find closest point on base_line, using parameter 0.0")
            t0 = 0.0
        else:
            logger.debug(f"Found parameter t0={t0} on base_line")
    else:
        logger.debug("No start location provided, using parameter 0.0")
        t0 = 0.0

    # Compute the total length of the base_line.
    length = safe_get_length(base_line)
    logger.debug(f"Base line length: {length}")
    
    # Determine number of studs (using stud_spacing)
    num_intervals = int(length / stud_spacing)
    logger.debug(f"Calculated {num_intervals+1} studs at spacing {stud_spacing}")
    
    # Create stud locations uniformly along the line.
    stud_points = [
        base_line.PointAt(t0 + (i / float(num_intervals)) * length)
        for i in range(num_intervals + 1)
    ]
    logger.debug(f"Generated {len(stud_points)} initial stud points")

    # Optionally remove the first and/or last stud.
    if remove_first and stud_points:
        logger.debug("Removing first stud")
        stud_points = stud_points[1:]
    if remove_last and stud_points:
        logger.debug("Removing last stud")
        stud_points = stud_points[:-1]

    logger.debug(f"Returning {len(stud_points)} stud locations")
    return stud_points

def generate_stud(profile="2x4", stud_height=2.4, stud_thickness=None, stud_width=None):
    """
    Generate a stud data structure with the specified profile or dimensions.
    
    Args:
        profile (str): Standard lumber profile (e.g., "2x4")
        stud_height (float): Height of the stud
        stud_thickness (float, optional): Override thickness from profile
        stud_width (float, optional): Override width from profile
        
    Returns:
        dict: Dictionary containing stud information
    """
    logger.debug(f"Generating stud with profile: {profile}")
    
    dimensions = PROFILES.get(profile, {})
    thickness = stud_thickness or dimensions.get("thickness", 0.04)
    width = stud_width or dimensions.get("width", 0.09)
    
    logger.debug(f"Using dimensions - thickness: {thickness}, width: {width}, height: {stud_height}")

    if thickness is None or width is None:
        logger.error("Missing dimensions for custom profile")
        raise ValueError("Explicit dimensions must be provided for custom profiles.")

    stud = {
        "type": "stud",
        "profile": profile,
        "thickness": thickness,
        "width": width,
        "height": stud_height,
        "geometry": "placeholder_for_geometry",
    }
    
    logger.debug("Stud data structure created successfully")
    return stud


class StudGenerator:
    """
    Generates standard wall studs within stud cells.

    Studs are vertical framing members placed at regular intervals along the wall.
    They run from the top face of the bottom plate to the bottom face of the top plate.
    This class uses existing Stud Cell (SC) information from cell decomposition
    to determine where studs should be placed with proper spacing.
    """

    def __init__(
        self,
        wall_data: Dict[str, Any],
        bottom_plate: Any,
        top_plate: Any,
        king_studs: List[rg.Brep] = None,
    ):
        """
        Initialize the stud generator with wall data and plate references.

        Args:
            wall_data: Dictionary containing wall information including:
                - base_plane: Reference plane for wall coordinate system
                - cells: List of cell dictionaries from decomposition
            bottom_plate: The bottom plate object (for elevation reference)
            top_plate: The top plate object (for elevation reference)
            king_studs: Optional list of king stud geometries to avoid overlap
        """
        logger.debug("Initializing StudGenerator")
        logger.debug(f"Wall data: {wall_data}")
        
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data
        self.bottom_plate = bottom_plate
        self.top_plate = top_plate
        self.king_studs = king_studs or []
        
        logger.debug(f"Bottom plate: {bottom_plate}")
        logger.debug(f"Top plate: {top_plate}")
        logger.debug(f"King studs count: {len(self.king_studs)}")

        # Initialize storage for debug geometry
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}

        # Extract and store king stud positions for reference
        self.king_stud_positions = self._extract_king_stud_positions()
        logger.debug(f"Extracted {len(self.king_stud_positions)} king stud positions")

    def _extract_king_stud_positions(self) -> List[float]:
        """
        Extract U-coordinates of king studs to avoid overlap.

        Returns:
            List of U-coordinates (along wall length) where king studs are positioned
        """
        logger.debug("Extracting king stud positions")
        positions = []

        if not self.king_studs:
            logger.info("No king studs provided to avoid overlap")
            return positions

        try:
            base_plane = self.wall_data.get("base_plane")
            if base_plane is None:
                logger.warning("No base plane available for king stud position extraction")
                return positions

            # Process each king stud to extract its U-coordinate
            for i, stud in enumerate(self.king_studs):
                logger.debug(f"Processing king stud {i+1}")
                # Get bounding box of king stud
                bbox = safe_get_bounding_box(stud, True)
                if not bbox.IsValid:
                    logger.warning(f"Invalid bounding box for king stud {i+1}")
                    continue

                # Calculate center point of bounding box
                center_x = (bbox.Min.X + bbox.Max.X) / 2
                center_y = (bbox.Min.Y + bbox.Max.Y) / 2
                center_point = rg.Point3d(center_x, center_y, bbox.Min.Z)
                logger.debug(f"King stud center point: ({center_point.X}, {center_point.Y}, {center_point.Z})")

                # Project onto wall base plane to get u-coordinate
                u_coordinate = self._project_point_to_u_coordinate(
                    center_point, base_plane
                )
                positions.append(u_coordinate)
                logger.debug(f"King stud {i+1} u-coordinate: {u_coordinate}")

            logger.debug(f"Extracted {len(positions)} king stud positions: {positions}")
            return positions

        except Exception as e:
            logger.error(f"Error extracting king stud positions: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return positions

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
        logger.debug(f"Projecting point ({point.X}, {point.Y}, {point.Z}) to u-coordinate")
        try:
            # Vector from base plane origin to the point
            vec = point - base_plane.Origin

            # Project this vector onto the u-axis (XAxis)
            # Use the dot product for projection
            u = vec * base_plane.XAxis
            logger.debug(f"Calculated u-coordinate: {u}")

            return u

        except Exception as e:
            logger.error(f"Error projecting point to u-coordinate: {str(e)}")
            return 0.0

    def generate_studs(self) -> List[rg.Brep]:
        """
        Generate standard wall studs based on stud cells.

        This method processes all stud cells (SC) and generates studs with
        proper spacing according to the configured stud spacing parameter.

        Returns:
            List of Brep geometries representing wall studs
        """
        logger.debug("Generating standard wall studs")
        
        try:
            # Extract cell data from wall data
            cells = self.wall_data.get("cells", [])
            base_plane = self.wall_data.get("base_plane")

            # Debug print
            print(f"\n=== STUD GENERATOR: generate_studs() ===")
            print(f"Cells from wall_data: {len(cells)}")
            for i, cell in enumerate(cells):
                ct = cell.get("type", "NO_TYPE")
                ct2 = cell.get("cell_type", "NO_CELL_TYPE")
                print(f"  Cell {i}: type='{ct}', cell_type='{ct2}'")
            print(f"Base plane: {base_plane is not None}")

            if not cells:
                logger.warning("No cells available for stud generation")
                print("WARNING: No cells available for stud generation")
                return []

            if base_plane is None:
                logger.warning("No base plane available for stud generation")
                print("WARNING: No base plane available for stud generation")
                return []

            logger.debug(f"Found {len(cells)} cells for stud processing")
            print(f"Found {len(cells)} cells for stud processing")

            # Extract dimensions from framing parameters
            stud_width = FRAMING_PARAMS.get("stud_width", 1.5 / 12)  # Default to 1.5 inches
            stud_depth = FRAMING_PARAMS.get("stud_depth", 3.5 / 12)  # Default to 3.5 inches
            stud_spacing = FRAMING_PARAMS.get("stud_spacing", 16 / 12)  # Default to 16 inches on center
            logger.debug(f"Stud dimensions - width: {stud_width}, depth: {stud_depth}, spacing: {stud_spacing}")

            # Calculate vertical extents for studs
            bottom_elevation = self._get_bottom_elevation()
            top_elevation = self._get_top_elevation()
            
            if bottom_elevation is None or top_elevation is None:
                logger.warning("Could not determine stud extents from plates")
                return []
                
            logger.debug(f"Stud vertical extents - bottom: {bottom_elevation}, top: {top_elevation}")

            # Process all cells marked as stud cells (SC)
            all_studs = []
            processed_cells = 0
            
            for cell in cells:
                cell_type = cell.get("type")

                # Debug: show every cell being evaluated
                print(f"  Evaluating cell: type='{cell_type}', id='{cell.get('id', 'unknown')}'")

                # Skip cells that are not stud cells
                if cell_type != "SC":
                    print(f"    -> Skipping (not SC)")
                    continue

                processed_cells += 1
                print(f"    -> PROCESSING as SC cell #{processed_cells}")
                logger.debug(f"Processing stud cell {processed_cells}")
                
                try:
                    # Get the horizontal region of the cell
                    u_start = cell.get("u_start")
                    u_end = cell.get("u_end")

                    if u_start is None or u_end is None:
                        logger.warning("Stud cell missing u-coordinate boundaries")
                        print(f"    WARNING: Cell missing u_start or u_end")
                        continue

                    logger.debug(f"Stud cell boundaries - u_start: {u_start}, u_end: {u_end}")
                    print(f"    Cell bounds: u_start={u_start}, u_end={u_end}, width={u_end - u_start}")
                    print(f"    Stud spacing: {stud_spacing}")
                    print(f"    Vertical range: bottom={bottom_elevation}, top={top_elevation}")

                    # Calculate stud positions within this cell
                    stud_positions = self._calculate_stud_positions(u_start, u_end, stud_spacing)
                    logger.debug(f"Calculated {len(stud_positions)} stud positions in cell")
                    print(f"    Calculated stud positions: {len(stud_positions)} - {stud_positions[:5] if stud_positions else 'NONE'}")

                    # Filter out positions too close to king studs
                    original_count = len(stud_positions)
                    stud_positions = self._filter_positions_by_king_studs(
                        stud_positions, stud_width * 1.5
                    )
                    logger.debug(f"{len(stud_positions)} positions remain after king stud filtering")
                    print(f"    After king stud filter: {len(stud_positions)} (was {original_count})")

                    # Create studs at each position
                    studs_created = 0
                    studs_failed = 0
                    for pos in stud_positions:
                        stud = self._create_stud_geometry(
                            base_plane,
                            pos,
                            bottom_elevation,
                            top_elevation,
                            stud_width,
                            stud_depth,
                        )
                        if stud:
                            all_studs.append(stud)
                            studs_created += 1
                            logger.debug(f"Created stud at u={pos}")
                        else:
                            studs_failed += 1
                            print(f"    FAILED to create stud at u={pos}")
                    print(f"    Studs created: {studs_created}, failed: {studs_failed}")

                except Exception as e:
                    logger.error(f"Error processing stud cell: {str(e)}")
                    continue

            logger.info(f"Generated {len(all_studs)} standard wall studs")
            print(f"=== STUD GENERATOR SUMMARY ===")
            print(f"Processed {processed_cells} SC cells")
            print(f"Generated {len(all_studs)} standard wall studs")
            print(f"=== END STUD GENERATOR ===\n")
            return all_studs

        except Exception as e:
            logger.error(f"Error generating studs: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _get_bottom_elevation(self) -> Optional[float]:
        """
        Get the elevation of the top of the bottom plate.

        Returns:
            The elevation value, or None if it cannot be determined
        """
        logger.debug("Getting bottom elevation for studs")
        try:
            # If we have a bottom plate reference, extract its top elevation
            if self.bottom_plate is not None:
                # Get bounding box of bottom plate
                bbox = safe_get_bounding_box(self.bottom_plate, True)
                if bbox.IsValid:
                    elevation = bbox.Max.Z
                    logger.debug(f"Bottom elevation from plate bounding box: {elevation}")
                    return elevation

            # Fallback to wall data if available
            bottom_plate_thickness = FRAMING_PARAMS.get("plate_thickness", 1.5 / 12)
            wall_base_elevation = self.wall_data.get("wall_base_elevation", 0.0)
            elevation = wall_base_elevation + bottom_plate_thickness
            logger.debug(f"Bottom elevation from wall data: {elevation}")
            return elevation

        except Exception as e:
            logger.error(f"Error determining bottom elevation: {str(e)}")
            return None

    def _get_top_elevation(self) -> Optional[float]:
        """
        Get the elevation of the bottom of the FIRST top plate (not cap plate).

        Studs should end at the bottom face of the first top plate, which is
        at wall_top - plate_thickness (the top plate top face is at wall_top).

        Returns:
            The elevation value, or None if it cannot be determined
        """
        logger.debug("Getting top elevation for studs")
        try:
            # Get plate thickness for calculations
            plate_thickness = FRAMING_PARAMS.get("plate_thickness", 1.5 / 12)

            # If we have a top plate reference, extract its bottom elevation
            # NOTE: self.top_plate should be the FIRST top plate (not cap plate)
            # Its top face should be at wall_top, bottom face at wall_top - thickness
            if self.top_plate is not None:
                # Get bounding box of top plate
                bbox = safe_get_bounding_box(self.top_plate, True)
                if bbox.IsValid:
                    # Use bbox.Min.Z for the bottom of the plate
                    elevation = bbox.Min.Z
                    logger.debug(f"Top elevation from plate bounding box: {elevation}")
                    print(f"    DEBUG _get_top_elevation: bbox.Min.Z = {elevation}, bbox.Max.Z = {bbox.Max.Z}")
                    return elevation

            # Fallback to wall data if available
            # Studs end at bottom of top plate = wall_top - plate_thickness
            wall_height = self.wall_data.get("wall_height")
            wall_base_elevation = self.wall_data.get("wall_base_elevation", 0.0)

            if wall_height is not None:
                # Wall top elevation minus plate thickness gives bottom of top plate
                wall_top = wall_base_elevation + wall_height
                elevation = wall_top - plate_thickness
                logger.debug(f"Top elevation from wall data (wall_top - thickness): {elevation}")
                print(f"    DEBUG _get_top_elevation fallback: wall_top={wall_top}, thickness={plate_thickness}, result={elevation}")
                return elevation

            logger.warning("Could not determine top elevation")
            return None

        except Exception as e:
            logger.error(f"Error determining top elevation: {str(e)}")
            return None

    def _calculate_stud_positions(
        self, u_start: float, u_end: float, stud_spacing: float
    ) -> List[float]:
        """
        Calculate stud positions within a cell based on spacing.

        CRITICAL: Every wall MUST have studs at both ends, regardless of wall length.
        For short walls, we place end studs even if the wall is narrower than stud spacing.

        End studs at wall boundaries (u=0 or u=wall_length) are offset inward
        by half the stud width so the stud edge aligns with the wall edge.

        Studs at SC/OC boundaries are removed since those are king stud positions.

        Args:
            u_start: Starting u-coordinate of the cell
            u_end: Ending u-coordinate of the cell
            stud_spacing: Desired spacing between studs

        Returns:
            List of u-coordinates where studs should be placed
        """
        logger.debug(f"Calculating stud positions from {u_start} to {u_end} with spacing {stud_spacing}")
        try:
            # Get wall length and stud dimensions for boundary detection
            wall_length = self.wall_data.get("wall_length", 0)
            stud_width = FRAMING_PARAMS.get("stud_width", 1.5 / 12)
            half_stud_width = stud_width / 2

            # Calculate the width of the cell
            cell_width = u_end - u_start
            logger.debug(f"Cell width: {cell_width}")

            # Tolerance for boundary detection
            tol = 0.01

            # Determine if this cell is at wall boundaries
            is_at_wall_start = abs(u_start) < tol
            is_at_wall_end = wall_length > 0 and abs(u_end - wall_length) < tol

            # CRITICAL: Always start with end studs at wall boundaries
            # Every wall MUST have studs at both ends
            positions = []

            # If cell starts at wall start, add end stud (offset inward)
            if is_at_wall_start:
                end_stud_pos = half_stud_width
                positions.append(end_stud_pos)
                logger.debug(f"Added wall start stud at u={end_stud_pos}")
                print(f"    Added wall START stud at u={end_stud_pos:.4f}")

            # If cell ends at wall end, add end stud (offset inward)
            if is_at_wall_end:
                end_stud_pos = wall_length - half_stud_width
                # Only add if it's not too close to the start stud
                if not positions or abs(end_stud_pos - positions[0]) > stud_width:
                    positions.append(end_stud_pos)
                    logger.debug(f"Added wall end stud at u={end_stud_pos}")
                    print(f"    Added wall END stud at u={end_stud_pos:.4f}")
                else:
                    logger.debug(f"Wall too short for separate end stud (would overlap start stud)")
                    print(f"    Wall too short - end stud would overlap start stud")

            # Now calculate intermediate studs based on spacing
            # Only if there's enough room for at least one intermediate stud
            internal_start = u_start if not is_at_wall_start else half_stud_width + stud_width
            internal_end = u_end if not is_at_wall_end else wall_length - half_stud_width - stud_width

            internal_width = internal_end - internal_start

            if internal_width > stud_spacing * 0.5:
                # Calculate number of intermediate studs
                num_intermediate = max(0, int(internal_width / stud_spacing))
                logger.debug(f"Can fit {num_intermediate} intermediate studs in internal width {internal_width}")
                print(f"    Internal width={internal_width:.4f}, can fit {num_intermediate} intermediate studs")

                if num_intermediate > 0:
                    # Distribute intermediate studs evenly
                    actual_spacing = internal_width / (num_intermediate + 1)
                    for i in range(1, num_intermediate + 1):
                        pos = internal_start + i * actual_spacing
                        positions.append(pos)
                        logger.debug(f"Added intermediate stud at u={pos}")
                        print(f"    Added intermediate stud at u={pos:.4f}")

            # Handle cells that are NOT at wall boundaries (bounded by openings)
            # These cells have king studs at their edges, so we don't add studs at u_start/u_end
            if not is_at_wall_start and not is_at_wall_end:
                # This cell is between openings - only add intermediate studs
                if cell_width > stud_spacing:
                    num_studs = int(cell_width / stud_spacing)
                    if num_studs > 0:
                        actual_spacing = cell_width / (num_studs + 1)
                        for i in range(1, num_studs + 1):
                            pos = u_start + i * actual_spacing
                            # Don't add if too close to cell boundaries (king stud positions)
                            if pos - u_start > stud_width and u_end - pos > stud_width:
                                positions.append(pos)
                                logger.debug(f"Added interior cell stud at u={pos}")
                                print(f"    Added interior cell stud at u={pos:.4f}")

            # Sort positions and remove duplicates
            positions = sorted(set(positions))

            # Filter out positions at SC/OC boundaries (king stud positions)
            # These are at u_start or u_end when NOT at wall boundaries
            filtered_positions = []
            for pos in positions:
                # Check if at cell boundary (not wall boundary) - these are king stud positions
                is_near_cell_start = abs(pos - u_start) < tol and not is_at_wall_start
                is_near_cell_end = abs(pos - u_end) < tol and not is_at_wall_end

                if is_near_cell_start or is_near_cell_end:
                    logger.debug(f"Removing stud at {pos} (king stud position)")
                    print(f"    Removing stud at u={pos:.3f} (OC boundary = king stud position)")
                else:
                    filtered_positions.append(pos)

            logger.debug(f"Calculated stud positions: {filtered_positions}")
            print(f"    Final stud positions: {[f'{p:.4f}' for p in filtered_positions]}")
            return filtered_positions

        except Exception as e:
            logger.error(f"Error calculating stud positions: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _filter_positions_by_king_studs(
        self, positions: List[float], min_distance: float
    ) -> List[float]:
        """
        Filter out stud positions that are too close to king studs.

        Args:
            positions: List of candidate stud positions (u-coordinates)
            min_distance: Minimum distance to keep from king studs

        Returns:
            Filtered list of positions that are safe from king studs
        """
        logger.debug(f"Filtering {len(positions)} positions to avoid king studs")
        logger.debug(f"Using minimum distance: {min_distance}")
        
        if not self.king_stud_positions:
            logger.debug("No king stud positions to filter against")
            return positions

        try:
            filtered_positions = []
            for pos in positions:
                # Check distance to all king studs
                too_close = False
                for king_pos in self.king_stud_positions:
                    distance = abs(pos - king_pos)
                    if distance < min_distance:
                        logger.debug(f"Position {pos} too close to king stud at {king_pos} (distance: {distance})")
                        too_close = True
                        break

                if not too_close:
                    filtered_positions.append(pos)

            logger.debug(f"Filtered to {len(filtered_positions)} positions")
            return filtered_positions

        except Exception as e:
            logger.error(f"Error filtering positions by king studs: {str(e)}")
            return positions

    def _create_stud_geometry(
        self,
        base_plane: rg.Plane,
        u_coordinate: float,
        bottom_v: float,
        top_v: float,
        width: float,
        depth: float,
    ) -> Optional[rg.Brep]:
        """
        Create the geometry for a single stud.

        Args:
            base_plane: Wall's base plane for coordinate system
            u_coordinate: Position along wall (horizontal)
            bottom_v: Bottom elevation of stud
            top_v: Top elevation of stud
            width: Width of stud (perpendicular to wall face)
            depth: Depth of stud (parallel to wall length)

        Returns:
            Brep geometry for the stud, or None if creation fails
        """
        logger.debug(f"Creating stud geometry at u={u_coordinate}, v range={bottom_v}-{top_v}")
        logger.debug(f"Stud dimensions - width: {width}, depth: {depth}")
        
        try:
            # 1. Create the centerline endpoints in world coordinates
            # Position along wall using XAxis (U direction)
            # Vertical position uses Z coordinate directly (V direction)
            point_along_wall = rg.Point3d.Add(
                base_plane.Origin,
                rg.Vector3d.Multiply(base_plane.XAxis, u_coordinate)
            )

            # Create start point at bottom elevation (Z = bottom_v)
            start_point = rg.Point3d(point_along_wall.X, point_along_wall.Y, bottom_v)

            # Create end point at top elevation (Z = top_v)
            end_point = rg.Point3d(point_along_wall.X, point_along_wall.Y, top_v)
            
            logger.debug(f"Centerline start point: ({start_point.X}, {start_point.Y}, {start_point.Z})")
            logger.debug(f"Centerline end point: ({end_point.X}, {end_point.Y}, {end_point.Z})")
            print(f"      Stud centerline: start=({start_point.X:.2f}, {start_point.Y:.2f}, {start_point.Z:.2f}) end=({end_point.X:.2f}, {end_point.Y:.2f}, {end_point.Z:.2f})")

            # Create the centerline as a curve
            # Convert to NurbsCurve to ensure proper type for SweepOneRail.PerformSweep()
            centerline = rg.LineCurve(start_point, end_point).ToNurbsCurve()
            self.debug_geometry["paths"].append(centerline)
            logger.debug(f"Centerline length: {safe_get_length(centerline)}")

            # 2. Create a HORIZONTAL profile plane at the start point
            # For vertical studs, the profile must be perpendicular to the centerline
            # Since centerline is vertical (Z direction), profile plane must be horizontal
            # Use a simple horizontal plane with normal pointing UP
            profile_plane = rg.Plane(start_point, rg.Vector3d.ZAxis)
            print(f"      Profile plane normal: ({profile_plane.Normal.X:.2f}, {profile_plane.Normal.Y:.2f}, {profile_plane.Normal.Z:.2f})")
            self.debug_geometry["planes"].append(profile_plane)
            logger.debug("Created horizontal profile plane for stud cross-section")

            # 3. Create a rectangle for the profile
            # For timber framing studs:
            # - Width (1.5") = visible on wall face, runs ALONG wall direction
            # - Depth (3.5") = wall thickness, runs PERPENDICULAR to wall face (wall normal)
            half_width = width / 2
            half_depth = depth / 2

            # Project wall directions onto horizontal plane for profile orientation
            wall_normal_horiz = rg.Vector3d(base_plane.ZAxis.X, base_plane.ZAxis.Y, 0)
            wall_along_horiz = rg.Vector3d(base_plane.XAxis.X, base_plane.XAxis.Y, 0)

            # Normalize (handle zero-length vectors)
            if wall_normal_horiz.Length > 0.001:
                wall_normal_horiz.Unitize()
            else:
                wall_normal_horiz = rg.Vector3d(0, 1, 0)  # Default Y
            if wall_along_horiz.Length > 0.001:
                wall_along_horiz.Unitize()
            else:
                wall_along_horiz = rg.Vector3d(1, 0, 0)  # Default X

            # Create corners in world XY, offset from start_point
            # Width (1.5") along wall, Depth (3.5") through wall thickness
            c1 = rg.Point3d(
                start_point.X - wall_along_horiz.X * half_width - wall_normal_horiz.X * half_depth,
                start_point.Y - wall_along_horiz.Y * half_width - wall_normal_horiz.Y * half_depth,
                start_point.Z
            )
            c2 = rg.Point3d(
                start_point.X + wall_along_horiz.X * half_width - wall_normal_horiz.X * half_depth,
                start_point.Y + wall_along_horiz.Y * half_width - wall_normal_horiz.Y * half_depth,
                start_point.Z
            )
            c3 = rg.Point3d(
                start_point.X + wall_along_horiz.X * half_width + wall_normal_horiz.X * half_depth,
                start_point.Y + wall_along_horiz.Y * half_width + wall_normal_horiz.Y * half_depth,
                start_point.Z
            )
            c4 = rg.Point3d(
                start_point.X - wall_along_horiz.X * half_width + wall_normal_horiz.X * half_depth,
                start_point.Y - wall_along_horiz.Y * half_width + wall_normal_horiz.Y * half_depth,
                start_point.Z
            )

            # Debug: store corners
            for corner in [c1, c2, c3, c4]:
                self.debug_geometry["points"].append(corner)

            # Create closed polyline for profile
            profile_poly = rg.Polyline([c1, c2, c3, c4, c1])  # Close the loop
            profile_curve = profile_poly.ToNurbsCurve()
            self.debug_geometry["profiles"].append(profile_curve)
            logger.debug("Created profile rectangle in horizontal plane")

            # 4. Extrude the profile along the vertical direction
            # Using Extrusion.Create for simple vertical extrusion
            # Note: Extrusion.Create extrudes OPPOSITE to curve plane normal when height > 0
            # Our profile plane normal is (0,0,1) pointing UP, so we need NEGATIVE height
            # to extrude UPWARD (in direction of normal)
            extrusion_height = -(end_point.Z - start_point.Z)

            print(f"      Extrusion height: {extrusion_height:.2f} (negative = extrude UP)")

            # Create extrusion from planar profile curve
            # Extrusion.Create(planarCurve, height, cap) -> Extrusion
            extrusion = rg.Extrusion.Create(profile_curve, extrusion_height, True)

            if extrusion is None:
                logger.warning("Failed to create extrusion")
                print(f"      EXTRUSION FAILED: Extrusion.Create returned None")
                return None

            # Convert Extrusion to Brep for compatibility with rest of pipeline
            brep = extrusion.ToBrep()
            if brep is None:
                logger.warning("Failed to convert extrusion to Brep")
                print(f"      EXTRUSION FAILED: ToBrep returned None")
                return None

            logger.debug("Successfully created stud Brep via extrusion")
            print(f"      EXTRUSION SUCCESS: Created stud Brep")
            return brep

        except Exception as e:
            logger.error(f"Error creating stud geometry: {str(e)}")
            import traceback
            tb = traceback.format_exc()
            logger.error(tb)
            print(f"      EXCEPTION: {str(e)}")
            print(f"      TRACEBACK: {tb}")
            return None
