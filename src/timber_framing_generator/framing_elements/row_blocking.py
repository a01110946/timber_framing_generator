# File: timber_framing_generator/framing_elements/row_blocking.py

"""
Row blocking generation for timber framing.

Row blocking (also called "solid blocking") refers to horizontal framing members 
installed between vertical studs to provide lateral support, prevent stud rotation/twisting, 
add structural rigidity, and provide nailing surfaces for wall finishes.

This module handles the calculation and creation of row blocking geometry based on
stud positions and configuration parameters.
"""

import sys
from typing import Dict, List, Any, Optional
import math
import Rhino.Geometry as rg

from src.timber_framing_generator.config.framing import (
    FRAMING_PARAMS, 
    PROFILES,
    BlockingPattern,
    get_profile_for_wall_type
)
from src.timber_framing_generator.framing_elements.blocking_parameters import (
    BlockingParameters,
    BlockingLayerConfig
)


class RowBlockingGenerator:
    """
    Generates row blocking elements between studs.
    
    Row blocking consists of horizontal members installed between studs to provide
    lateral support and prevent stud rotation. This class takes stud positions and
    wall data to calculate appropriate blocking positions and generate the geometry.
    
    Attributes:
        wall_data: Dictionary with wall information
        studs: List of stud geometries
        blocking_params: Parameters for blocking configuration
        debug_geometry: Storage for debug visualization (optional)
    """
    
    def __init__(self, wall_data: Dict[str, Any], studs: List[rg.Brep] = None, framing_config: Dict[str, Any] = None):
        """
        Initialize row blocking generator with wall data and framing config.
        
        Args:
            wall_data: Dictionary with wall geometry and parameter data
            studs: Optional list of stud Brep geometries to determine stud positions
            framing_config: Optional override framing configuration
        """
        self.wall_data = wall_data
        self.studs = studs or []
        self.wall_height = wall_data.get('wall_top_elevation', 0) - wall_data.get('wall_base_elevation', 0)
        
        # Get local framing configuration (provided or from defaults)
        self.framing_config = framing_config if framing_config else {}
        
        # Initialize blocking parameters
        self.blocking_params = BlockingParameters()
        
        # Explicitly handle blocking pattern conversion if it's a string
        if framing_config and 'blocking_pattern' in framing_config:
            pattern_value = framing_config['blocking_pattern']
            print(f"Row blocking received pattern: {pattern_value}, type: {type(pattern_value)}")
            
            if isinstance(pattern_value, str):
                pattern_str = pattern_value.lower().strip()
                if pattern_str == "staggered":
                    self.blocking_params.pattern = BlockingPattern.STAGGERED
                    print(f"Explicitly set pattern to STAGGERED")
                else:
                    self.blocking_params.pattern = BlockingPattern.INLINE
                    print(f"Explicitly set pattern to INLINE")
        
        # Override default parameters if config provided
        if framing_config:
            for key, value in framing_config.items():
                if hasattr(self.blocking_params, key) and key != 'blocking_pattern':
                    setattr(self.blocking_params, key, value)
                    print(f"Set blocking param {key} = {value}")
        
        # Initialize stud positions (empty if no studs provided)
        self.stud_positions = []
        if self.studs:
            self.stud_positions = self._extract_stud_positions()
        
        # Get wall and block profiles
        self.wall_profile = get_profile_for_wall_type(wall_data.get("wall_type", "2x4"))
        self.block_profile_name = self.blocking_params.get_block_profile(self.wall_profile.name)
        self.block_profile = PROFILES.get(self.block_profile_name, self.wall_profile)
        
        # Storage for debug geometry
        self.debug_geometry = {
            "points": [],
            "planes": [],
            "profiles": [],
            "paths": []
        }
        
    def set_stud_positions(self, studs: List[rg.Brep] = None, positions: List[float] = None) -> None:
        """
        Set or update the stud positions for blocking.
        
        Args:
            studs: List of stud Brep geometries to determine stud positions
            positions: Option to directly provide precalculated U-coordinate positions
                      Takes precedence over studs if both are provided
        """
        if positions is not None and len(positions) > 0:
            # Use provided positions directly
            self.stud_positions = sorted(positions)
            print(f"Using {len(self.stud_positions)} provided stud positions")
        elif studs is not None:
            # Extract positions from stud geometries
            self.studs = studs
            self.stud_positions = self._extract_stud_positions()
        else:
            # No valid input provided
            print("Warning: No stud data or positions provided")
            self.stud_positions = []
            
        print(f"Updated stud positions: {len(self.stud_positions)} studs found")
    
    def _extract_stud_positions(self) -> List[float]:
        """
        Extract U-coordinates of studs along the wall.
        
        Returns:
            List of U-coordinates (along wall length) where studs are positioned
        """
        positions = []
        base_plane = self.wall_data.get("base_plane")
        
        if not base_plane or not isinstance(base_plane, rg.Plane):
            raise ValueError("Wall data must contain a valid base_plane")
        
        for stud in self.studs:
            if not stud:
                continue
                
            # Get the center point of the stud
            if hasattr(stud, "GetBoundingBox"):
                bbox = stud.GetBoundingBox(True)
                center = (bbox.Min + bbox.Max) / 2.0
                
                # Project to U coordinate on base plane
                u_coord = self._project_point_to_u_coordinate(center, base_plane)
                positions.append(u_coord)
        
        # Sort positions along the wall
        positions.sort()
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
        # Get wall direction vector (X axis of the base plane)
        wall_direction = base_plane.XAxis
        
        # Get vector from plane origin to point
        vector_to_point = point - base_plane.Origin
        
        # Project this vector onto the wall direction to get the U coordinate
        u_coord = rg.Vector3d.Multiply(vector_to_point, wall_direction)
        
        print(f"Point: {point}, Wall Origin: {base_plane.Origin}, U-coord: {u_coord}")
        return u_coord
    
    def generate_blocking(self) -> List[rg.Brep]:
        """
        Generate row blocking elements for a wall.
        
        Returns:
            List of Brep geometries representing blocking
        """
        print("\n===== ROW BLOCKING DIAGNOSTIC INFO =====")
        print(f"Include blocking flag: {self.blocking_params.include_blocking}")
        print(f"Wall height: {self.wall_height}")
        print(f"Wall elevations: base={self.wall_data.get('wall_base_elevation')}, top={self.wall_data.get('wall_top_elevation')}")
    
        # Skip if blocking is disabled or no stud positions
        if not self.blocking_params.include_blocking:
            print("Blocking is disabled, skipping generation")
            return []
        
        if not self.stud_positions or len(self.stud_positions) < 2:
            print(f"Not enough stud positions for blocking: {len(self.stud_positions)}")
            return []
        
        # Calculate heights for blocking rows
        print(f"\nCalculating block heights for wall height: {self.wall_height}ft")
        block_heights = self.blocking_params.calculate_block_heights(self.wall_height)
        
        # Get block dimensions from profile
        try:
            # Try to get dimensions from the profile
            dims = self.block_profile.get_dimensions()
            block_width = dims["width"]  # Vertical dimension (usually 1.5" for 2x4)
            block_thickness = dims["thickness"]  # Horizontal dimension (usually 3.5" for 2x4)
            print(f"Block profile dimensions: {dims}")
        except (AttributeError, KeyError) as e:
            # Fallback to direct attributes if get_dimensions not available or dimensions not found
            print(f"Using direct profile attributes - get_dimensions failed: {str(e)}")
            try:
                # Try nominal_width/nominal_depth
                block_width = self.block_profile.nominal_width
                block_thickness = self.block_profile.nominal_depth
            except AttributeError:
                # Last resort - try width/depth directly
                try:
                    block_width = self.block_profile.width
                    block_thickness = self.block_profile.depth
                except AttributeError:
                    # If all else fails, use default values for 2x4
                    print("WARNING: Could not determine block dimensions, using defaults for 2x4")
                    block_width = 1.5 / 12.0  # 1.5 inches in feet
                    block_thickness = 3.5 / 12.0  # 3.5 inches in feet
        
        print(f"Block profile: {self.block_profile_name}, width: {block_width}, thickness: {block_thickness}")
        
        # Show stud information
        print(f"Number of studs: {len(self.stud_positions)}")
        print(f"Stud positions: {self.stud_positions}")

        # Get pattern and make sure it's properly set (debugging)
        print(f"Blocking pattern: {self.blocking_params.pattern}")
        print(f"Blocking pattern type: {type(self.blocking_params.pattern)}")
        if self.framing_config and 'blocking_pattern' in self.framing_config:
            print(f"Config blocking pattern: {self.framing_config['blocking_pattern']}")
        
        # Get wall base plane
        base_plane = self.wall_data.get("base_plane")
        if not base_plane:
            print("Missing wall base plane, cannot generate blocking")
            return []
    
        blocks = []
        blocks_at_height = {}  # Keep track of blocks created at each height
    
        # Generate blocking rows at each height
        for height_index, height in enumerate(block_heights):
            print(f"\nProcessing blocking row at height: {height}")
            blocks_at_height[height] = 0  # Initialize counter for this height
                
            # For each pair of adjacent studs, create a block between them
            for i in range(len(self.stud_positions) - 1):
                start_stud_idx = i
                end_stud_idx = i + 1
                
                # For staggered pattern, skip every other block in alternating rows
                if (self.blocking_params.pattern == BlockingPattern.STAGGERED and 
                    ((height_index % 2 == 0 and i % 2 == 1) or 
                     (height_index % 2 == 1 and i % 2 == 0))):
                    print(f"  Skipping block between studs at {self.stud_positions[start_stud_idx]} and {self.stud_positions[end_stud_idx]} (staggered pattern)")
                    continue
                
                start_u = self.stud_positions[start_stud_idx]
                end_u = self.stud_positions[end_stud_idx]
                span = end_u - start_u
                
                print(f"  Creating block between studs at {start_u} and {end_u} (span: {span})")
                
                # Create the actual block geometry
                block = self._create_block_geometry(
                    base_plane, 
                    start_u,
                    end_u,
                    height, 
                    block_width, 
                    block_thickness
                )
                
                if block:
                    blocks.append(block)
                    blocks_at_height[height] += 1
                    print(f"  Added block at height {height} between studs {start_stud_idx} and {end_stud_idx}")
                else:
                    print(f"  Failed to create block at height {height} between studs {start_stud_idx} and {end_stud_idx}")
                    
            print(f"Created {blocks_at_height[height]} blocks at height {height}")
        
        print(f"Total blocks created: {len(blocks)}")
        print("===== END ROW BLOCKING DIAGNOSTIC INFO =====")
        return blocks
    
    def _create_block_geometry(
        self,
        base_plane: rg.Plane,
        start_u: float,
        end_u: float,
        height: float,
        width: float, 
        thickness: float,
    ) -> Optional[rg.Brep]:
        """
        Create the 3D geometry for a single block.

        Args:
            base_plane: Base plane of the wall
            start_u: U-coordinate of start stud centerline
            end_u: U-coordinate of end stud centerline
            height: Height from the base of the wall to the block centerline
            width: Width of the blocking element (usually the nominal height)
            thickness: Thickness of the blocking element (usually the nominal width)

        Returns:
            Brep representing the blocking element or None if creation failed
        """
        try:
            # Calculate block center and length
            center_u = (start_u + end_u) / 2
            length = abs(end_u - start_u)
            
            # Get wall base elevation from wall data
            wall_base_elevation = self.wall_data.get('wall_base_elevation', 0)
            
            # Calculate the center point of the block in world coordinates
            block_origin_pt = base_plane.PointAt(center_u, 0)
            
            # Adjust the height to be relative to wall base
            absolute_height = wall_base_elevation + height
            
            # Create a 3D point at the center of the block
            block_origin = rg.Point3d(block_origin_pt.X, block_origin_pt.Y, absolute_height)
            
            # Create vectors for the block orientation
            # X axis is along the wall length (U direction)
            x_axis = base_plane.XAxis
            
            # Y axis is the vertical direction (up)
            y_axis = base_plane.YAxis
            
            # Z axis is perpendicular to the wall (outward/inward)
            z_axis = base_plane.ZAxis
            
            # Create the block plane at the center of the block
            block_plane = rg.Plane(block_origin, x_axis, y_axis)
            
            # Store this plane for debugging
            self.debug_geometry["planes"].append(block_plane)
            
            # Get stud width for adjusting the block length
            stud_width = FRAMING_PARAMS.get("stud_width", 1.5 / 12)  # Default to 1.5 inches in feet
            
            # Calculate the sweep path (will stretch between studs)
            # Adjust for stud width to make block fit between inner faces of studs
            adjusted_length = length - stud_width
            
            # Create path curve in the block plane
            # The path runs along the X axis of the block plane (between studs)
            path_start = block_plane.PointAt(-adjusted_length/2, 0)
            path_end = block_plane.PointAt(adjusted_length/2, 0)
            path_curve = rg.LineCurve(path_start, path_end)
            
            # Store the path for debugging
            self.debug_geometry["paths"].append(path_curve.DuplicateCurve())
            
            # Create cross-section profile for the block
            # The profile is perpendicular to the path, with height along Y and thickness along Z
            profile_plane = rg.Plane(
                path_start,  # Start at beginning of path
                z_axis,      # Y axis is vertical (up)
                y_axis       # Z axis is perpendicular to wall
            )
            
            # Create rectangle for profile - in the Y-Z plane
            # Width is vertical dimension, thickness is through-wall dimension
            profile_rect = rg.Rectangle3d(profile_plane, width, thickness)
            profile_curve = profile_rect.ToNurbsCurve()
            
            # Center the profile vertically on the path
            # Move the profile down by half its height so it's centered on the path
            translation_vector = rg.Vector3d(base_plane.ZAxis * -width / 2)
            
            translation = rg.Transform.Translation(translation_vector)
            profile_curve.Transform(translation)
            
            # Store the profile for debugging
            self.debug_geometry["profiles"].append(profile_curve.DuplicateCurve())
            
            # Create the block geometry by sweeping the profile along the path
            sweep = rg.SweepOneRail()
            sweep.AngleToleranceRadians = 0.01
            sweep.ClosedSweep = False
            sweep.SweepTolerance = 0.01
            
            # Perform the sweep operation
            breps = sweep.PerformSweep(path_curve, [profile_curve])
            
            if breps and len(breps) > 0:
                self.debug_geometry["points"].append(block_origin)
                return breps[0]
            else:
                print(f"  Error in sweep operation - no breps created")
                return None
                
        except Exception as e:
            print(f"Error creating block geometry: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None
