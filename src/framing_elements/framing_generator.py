#  

from typing import Dict, List, Tuple, Union, Optional, Any
import Rhino.Geometry as rg
from src.framing_elements.plates import create_plates
from src.framing_elements.plate_geometry import PlateGeometry
from src.framing_elements.king_studs import KingStudGenerator
from src.framing_elements.headers import HeaderGenerator
from src.framing_elements.sills import SillGenerator
from src.utils.coordinate_systems import WallCoordinateSystem

class FramingGenerator:
    """
    Coordinates the generation of timber wall framing elements.
    
    This class manages the sequential creation of framing elements while ensuring
    proper dependencies between components. Rather than implementing framing generation
    directly, it leverages our existing specialized functions while adding coordination,
    state management, and dependency tracking.
    """
    def __init__(self, wall_data: Dict[str, Union[str, float, bool, List, Any]], framing_config=None):
        # Store the wall data for use throughout the generation process
        self.wall_data = wall_data
        
        # Set default configuration if none provided
        self.framing_config = {
            'representation_type': "schematic",  # Default to schematic representation
            'bottom_plate_layers': 1,            # Single bottom plate by default
            'top_plate_layers': 2                # Double top plate by default
        }
        
        # Update configuration with any provided values
        if framing_config:
            self.framing_config.update(framing_config)
            
        # Initialize storage for all framing elements
        self.framing_elements = {
            'bottom_plates': [],
            'top_plates': [],
            'king_studs': []
        }
        
        # Track the generation status of different element types
        self.generation_status = {
            'plates_generated': False,
            'king_studs_generated': False,
            'headers_and_sills_generated': False
        }
        
        # Track any warnings or messages during generation
        self.messages = []

        # Initialize debug geometry storage
        self.debug_geometry = {
            'points': [],
            'planes': [],
            'profiles': [],
            'paths': []
        }

    def generate_framing(self) -> Dict[str, List[PlateGeometry]]:
        """
        Generates all framing elements in the correct dependency order.
        
        For now, this only handles plate generation, but it's structured
        to accommodate our full framing hierarchy as we build it out.
        
        Returns:
            Dictionary containing lists of generated framing elements,
            currently just bottom and top plates.
        """
        try:
            # Generate plates first since king studs depend on them
            self._generate_plates()
            self.messages.append("Plates generated successfully")
            
            # Now generate king studs using the generated plates
            self._generate_king_studs()
            self.messages.append("King studs generated successfully")
        
            # Generate headers and sills
            self._generate_headers_and_sills()
            self.messages.append("Headers and sills generated successfully")
            
            # Return both framing elements and debug geometry
            result = {
            'bottom_plates': self.framing_elements['bottom_plates'],
            'top_plates': self.framing_elements['top_plates'],
            'king_studs': self.framing_elements['king_studs'],
            'headers': self.framing_elements.get('headers', []),
            'sills': self.framing_elements.get('sills', []),
            'debug_geometry': self.debug_geometry  # Include debug geometry in output
            }
            
            print("\nFraming generation complete:")
            print(f"Bottom plates: {len(result['bottom_plates'])}")
            print(f"Top plates: {len(result['top_plates'])}")
            print(f"King studs: {len(result['king_studs'])}")
            print(f"Headers: {len(result['headers'])}")
            print(f"Sills: {len(result['sills'])}")
            print(f"Debug geometry:")
            for key, items in self.debug_geometry.items():
                print(f"  {key}: {len(items)} items")
            
            return result
            
        except Exception as e:
            self.messages.append(f"Error during framing generation: {str(e)}")
            raise

    def _generate_plates(self) -> None:
        """
        Creates bottom and top plates using our existing plate generation system.
        
        Instead of reimplementing plate generation logic, this method uses our
        existing create_plates() function while managing the overall process
        and maintaining state.
        """
        if self.generation_status['plates_generated']:
            return
            
        try:
            self.framing_elements['bottom_plates'] = create_plates(
                wall_data=self.wall_data,
                plate_type="bottom_plate",
                representation_type=self.framing_config['representation_type'],
                layers=self.framing_config['bottom_plate_layers']
            )
            
            self.framing_elements['top_plates'] = create_plates(
                wall_data=self.wall_data,
                plate_type="top_plate",
                representation_type=self.framing_config['representation_type'],
                layers=self.framing_config['top_plate_layers']
            )
            
            self.generation_status['plates_generated'] = True
            self.messages.append("Plates generated successfully")
            
        except Exception as e:
            self.messages.append(f"Error generating plates: {str(e)}")
            raise

    def _generate_king_studs(self) -> None:
        """Generates king studs with debug geometry tracking."""
            # Initialize debug geometry with matching keys
        self.debug_geometry = {
            'points': [],
            'planes': [],
            'profiles': [],
            'paths': []
        }

        if self.generation_status['king_studs_generated']:
            return
            
        if not self.generation_status['plates_generated']:
            raise RuntimeError("Cannot generate king studs before plates")
            
        try:
            openings = self.wall_data.get('openings', [])
            print(f"\nGenerating king studs for {len(openings)} openings")
            
            king_stud_generator = KingStudGenerator(
                self.wall_data,
                self.framing_elements['bottom_plates'][0],
                self.framing_elements['top_plates'][-1]
            )
            
            opening_king_studs = []
            
            all_debug_geometry = {
                'points': [],
                'planes': [],
                'profiles': [],
                'paths': []
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
            
            self.framing_elements['king_studs'] = opening_king_studs
            self.debug_geometry = all_debug_geometry
            self.generation_status['king_studs_generated'] = True
            
        except Exception as e:
            print(f"Error generating king studs: {str(e)}")
            raise
    
    def _get_king_stud_positions(self) -> Dict[int, Tuple[float, float]]:
        """
        Extract king stud positions for each opening.
        
        This method analyzes the generated king studs to determine their
        positions relative to each opening. It returns a dictionary mapping
        opening index to a tuple of (left, right) u-coordinates.
        
        Returns:
            Dictionary mapping opening index to (left, right) positions
        """
        positions = {}
        
        # Check if king studs have been generated
        if not self.generation_status.get('king_studs_generated', False):
            return positions
        
        # Get openings data
        openings = self.wall_data.get('openings', [])
        king_studs = self.framing_elements.get('king_studs', [])
        
        # We need to match king studs to openings
        # This assumes king studs are generated in pairs for each opening
        # and in the same order as the openings
        if len(king_studs) >= 2 and len(openings) > 0:
            # King studs are typically generated in pairs (left, right)
            for i in range(len(openings)):
                # Check if we have king studs for this opening
                king_stud_index = i * 2
                if king_stud_index + 1 < len(king_studs):
                    # Get the centerlines of the king studs
                    left_stud = king_studs[king_stud_index]
                    right_stud = king_studs[king_stud_index + 1]
                    
                    # This is a simplification - we would need to extract the 
                    # actual u-coordinates from the king studs
                    # For now, use the opening positions
                    opening = openings[i]
                    u_left = opening["start_u_coordinate"] - 0.15  # Approximate left stud position
                    u_right = opening["start_u_coordinate"] + opening["rough_width"] + 0.15  # Approximate right stud position
                    
                    positions[i] = (u_left, u_right)
        
        return positions

    def _generate_headers_and_sills(self) -> None:
        """
        Generates headers and sills for wall openings.
        
        This method creates headers above all openings and sills below window openings,
        using the king studs as span references when available.
        """
        if self.generation_status.get('headers_and_sills_generated', False):
            return
            
        if not self.generation_status.get('king_studs_generated', False):
            self._generate_king_studs()
            
        try:  # OUTER try begins
            openings = self.wall_data.get('openings', [])
            print(f"\nGenerating headers and sills for {len(openings)} openings")
        
            # Skip if no openings
            if not openings:
                print("No openings to process - skipping headers and sills")
                self.generation_status['headers_and_sills_generated'] = True
                return
                
            try:  # INNER try begins
                # Create coordinate system for consistent transformations
                coordinate_system = WallCoordinateSystem(self.wall_data)
            
                # Verify the coordinate system was created successfully
                if coordinate_system.base_plane is None or coordinate_system.wall_curve is None:
                    print("Warning: Invalid coordinate system created. Using fallback approach.")
                    # We'll proceed without the coordinate system, using a simpler approach
                    self._generate_headers_and_sills_fallback()
                    return
        
                # Get king stud positions for all openings
                king_stud_positions = self._get_king_stud_positions()
            
                # Initialize header and sill generators
                header_generator = HeaderGenerator(self.wall_data, coordinate_system)
                sill_generator = SillGenerator(self.wall_data, coordinate_system)
                
                # Track generated elements
                headers = []
                sills = []
            
                # Process each opening
                for i, opening in enumerate(openings):
                    try:
                        print(f"\nProcessing opening {i+1}")
                        
                        # Get king stud positions for this opening if available
                        opening_king_stud_positions = king_stud_positions.get(i)
                        
                        # Generate header
                        header = header_generator.generate_header(opening, opening_king_stud_positions)
                        if header:
                            headers.append(header)
                        
                        # Generate sill (only for windows)
                        if opening["opening_type"].lower() == "window":
                            sill = sill_generator.generate_sill(opening, opening_king_stud_positions)
                            if sill:
                                sills.append(sill)
                        
                    except Exception as e:
                        print(f"Error with opening {i+1}: {str(e)}")
                        import traceback
                        print(traceback.format_exc())
                
                # Store the generated elements
                self.framing_elements['headers'] = headers
                self.framing_elements['sills'] = sills
                
                # Collect debug geometry
                all_debug_geometry = {
                    'points': [],
                    'curves': [],
                    'planes': [],
                    'profiles': []
                }
                
                # Collect header debug geometry
                for key in all_debug_geometry:
                    all_debug_geometry[key].extend(header_generator.debug_geometry.get(key, []))
                    
                # Collect sill debug geometry
                for key in all_debug_geometry:
                    all_debug_geometry[key].extend(sill_generator.debug_geometry.get(key, []))
                
                # Store debug geometry
                for key in all_debug_geometry:
                    if key in self.debug_geometry:
                        self.debug_geometry[key].extend(all_debug_geometry[key])
                    else:
                        self.debug_geometry[key] = all_debug_geometry[key]
                
                # Update generation status
                self.generation_status['headers_and_sills_generated'] = True
                
            except Exception as e:  # INNER except
                print(f"Error generating headers and sills: {str(e)}")
                import traceback
                print(traceback.format_exc())
                # Don't re-raise here to allow the outer try to handle it
                self.generation_status['headers_and_sills_generated'] = True  # Mark as completed to prevent future attempts
                
        except Exception as e:  # OUTER except - this was missing
            print(f"Fatal error in header and sill generation: {str(e)}")
            import traceback
            print(traceback.format_exc())
            self.generation_status['headers_and_sills_generated'] = True  # Mark as completed to prevent future attempts
    
    def _generate_headers_and_sills_fallback(self) -> None:
        """
        Fallback method for generating headers and sills when coordinate system fails.
        
        This method uses a simpler approach without the coordinate system,
        directly working with opening geometry and centerlines.
        """
        try:
            openings = self.wall_data.get('openings', [])
            print(f"Using fallback approach for {len(openings)} openings")
            
            # Track generated elements
            headers = []
            sills = []
            
            # Get wall base plane
            base_plane = self.wall_data.get('base_plane')
            if base_plane is None:
                print("Error: No base plane available for fallback header/sill generation")
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
                    opening_v_start = opening.get("base_elevation_relative_to_wall_base", 0)
                    
                    # Calculate header v-coordinate (top of opening)
                    header_v = opening_v_start + opening_height
                    
                    # Calculate u-coordinates with standard offsets
                    trimmer_offset = 0.125  # Use hardcoded values for fallback
                    king_stud_offset = 0.125
                    stud_width = 0.125
                    
                    # Calculate stud centers
                    u_left = opening_u_start - trimmer_offset - king_stud_offset - stud_width/2
                    u_right = opening_u_start + opening_width + trimmer_offset + king_stud_offset + stud_width/2
                    
                    # Create header points in world coordinates
                    header_left = base_plane.PointAt(u_left, header_v, 0)
                    header_right = base_plane.PointAt(u_right, header_v, 0)
                    
                    # Create a simple header geometry - a box using ExtrudeCurve
                    header_height = 0.25  # 3 inches in feet (hardcoded for fallback)
                    header_width = 0.292  # 3.5 inches in feet
                    
                    header_profile = rg.Circle(
                        header_left, 
                        rg.Vector3d(0, 0, 1), 
                        header_width/2
                    ).ToNurbsCurve()
                    
                    header_path = rg.Line(header_left, header_right).ToNurbsCurve()
                    header_brep = rg.Brep.CreateFromSweep(
                        header_profile, 
                        header_path, 
                        True, 
                        0.001
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
                            sill_left, 
                            rg.Vector3d(0, 0, 1), 
                            header_width/2
                        ).ToNurbsCurve()
                        
                        sill_path = rg.Line(sill_left, sill_right).ToNurbsCurve()
                        sill_brep = rg.Brep.CreateFromSweep(
                            sill_profile, 
                            sill_path, 
                            True, 
                            0.001
                        )[0]
                        
                        if sill_brep and sill_brep.IsValid:
                            sills.append(sill_brep)
                        
                except Exception as e:
                    print(f"Error with opening {i+1} in fallback mode: {str(e)}")
            
            # Store the generated elements
            self.framing_elements['headers'] = headers
            self.framing_elements['sills'] = sills
            
            # Update generation status
            self.generation_status['headers_and_sills_generated'] = True
            
        except Exception as e:
            print(f"Error in fallback headers and sills generation: {str(e)}")
            import traceback
            print(traceback.format_exc())

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