#  

from typing import Dict, List, Union, Optional, Any
from src.framing_elements.plates import create_plates
from src.framing_elements.plate_geometry import PlateGeometry
from src.framing_elements.king_studs import KingStudGenerator

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
            'king_studs_generated': False
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
            
            # Return both framing elements and debug geometry
            result = {
                'bottom_plates': self.framing_elements['bottom_plates'],
                'top_plates': self.framing_elements['top_plates'],
                'king_studs': self.framing_elements['king_studs'],
                'debug_geometry': self.debug_geometry  # Include debug geometry in output
            }
            
            print("\nFraming generation complete:")
            print(f"Bottom plates: {len(result['bottom_plates'])}")
            print(f"Top plates: {len(result['top_plates'])}")
            print(f"King studs: {len(result['king_studs'])}")
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