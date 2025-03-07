# File: tests/framing_elements/test_plates.py

import sys
import os
print("Python path:", sys.path)

# Try this instead
try:
    import timber_framing_generator
    print("Package location:", timber_framing_generator.__file__)
except ImportError:
    # Add the src directory to the path
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))
    import timber_framing_generator
    print("Package loaded from path addition!")

import pytest
import unittest
from typing import List, Dict, Union, Optional, Any
from timber_framing_generator.framing_elements.location_data import get_plate_location_data
from timber_framing_generator.config.framing import PlatePosition
from timber_framing_generator.framing_elements.plate_parameters import PlateLayerConfig
from timber_framing_generator.framing_elements.plate_parameters import PlateParameters
from timber_framing_generator.framing_elements.plate_geometry import PlateGeometry
from timber_framing_generator.framing_elements.plates import create_plates

class TestPlateSystem:
    """
    Test suite for the plate generation system.
    
    This class provides methods to test each component of the plate system:
    - Location data extraction
    - Parameter generation
    - Geometry creation
    - Complete plate assembly
    
    It supports testing geometry creation for different software platforms while maintaining
    separation of concerns. The class is designed to work both as a standalone test suite and
    as a utility for testing plates within Grasshopper.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup runs before each test method."""
        self.debug = True
        self._results = {}
    
    def _get_wall_identifier(self, wall_data: Dict[str, Any]) -> str:
        """
        Generate a consistent identifier for a wall.
        
        This helper method ensures we have a reliable way to identify
        walls in our results, even if the wall data doesn't contain
        an explicit ID.
        
        Args:
            wall_data: Dictionary containing wall information
            
        Returns:
            str: A unique identifier for the wall
        """
        # Try to get wall ID from the data, or generate one based on position
        return str(wall_data.get('id', hash(frozenset(wall_data.items()))))
        
    def test_location_data(self, wall_data: Dict[str, Any]) -> Dict[str, Any]:
        """Test plate location data extraction for a single wall."""
        if self.debug:
            print("\nTesting location data extraction...")
        
        # First, verify we have a valid wall dictionary
        if not isinstance(wall_data, dict):
            raise TypeError("wall_data must be a dictionary")
        
        if 'cells' not in wall_data:
            raise KeyError("wall_data must contain 'cells' key")
        
        bottom_location = get_plate_location_data(
            wall_data,
            plate_type="bottom_plate",
            representation_type="structural"
        )
        
        top_location = get_plate_location_data(
            wall_data,
            plate_type="top_plate",
            representation_type="structural"
        )
        
        if self.debug:
            print(f"Bottom plate elevation: {bottom_location['reference_elevation']}")
            print(f"Top plate elevation: {top_location['reference_elevation']}")
        
        return {
            'bottom': bottom_location,
            'top': top_location
        }

    def test_parameters(
        self,
        wall_data: Dict[str, Any],
        representation_type: str = "structural"
    ) -> Dict[str, PlateParameters]:
        """
        Test plate parameter generation using the specified representation type.
        """
        if self.debug:
            print("\nTesting parameter generation...")
            print(f"Wall type: {wall_data['wall_type']}")
            print(f"Using representation type: {representation_type}")
        
        try:
            # Determine if wall is exterior for layer configuration
            is_exterior = wall_data['is_exterior_wall']
            num_layers = 2 if is_exterior else 1
            
            # Create configurations
            bottom_config = PlateLayerConfig(
                position=PlatePosition.BOTTOM,
                num_layers=num_layers
            )
            
            top_config = PlateLayerConfig(
                position=PlatePosition.TOP,
                num_layers=num_layers
            )
            
            bottom_params = []
            top_params = []
            
            for idx in range(num_layers):
                # Create parameters with proper representation type
                bottom_plate = PlateParameters.from_wall_type(
                    wall_type=wall_data['wall_type'],
                    layer_config=bottom_config,
                    layer_idx=idx,
                    representation_type=representation_type  # Pass it through
                )
                bottom_params.append(bottom_plate)
                
                top_plate = PlateParameters.from_wall_type(
                    wall_type=wall_data['wall_type'],
                    layer_config=top_config,
                    layer_idx=idx,
                    representation_type=representation_type  # Pass it through
                )
                top_params.append(top_plate)
            
            return {
                'bottom': bottom_params,
                'top': top_params
            }
            
        except Exception as e:
            print(f"Parameter generation failed: {str(e)}")
            print(f"Stack trace:")  # Add stack trace for better debugging
            import traceback
            print(traceback.format_exc())
            raise

    def test_complete_system(
        self,
        wall_data: Union[List[Dict[str, Any]], Dict[str, Any]],
        platform: str = "rhino",
        representation_type: str = "structural"
    ) -> Dict[str, Any]:
        """
        Run complete system test on a wall.
        
        This method orchestrates the testing of the entire plate system, including:
        1. Location data extraction
        2. Parameter generation
        3. Complete plate creation with specified representation
        
        Args:
            wall_data: Either a single wall dictionary or a dictionary of wall dictionaries
            platform: Target platform for geometry creation ("rhino", "revit", "speckle")
            representation_type: How to represent the plates ("structural" or "schematic")
                            - "structural": Plates are positioned based on their actual
                                            structural location (e.g., bottom plate centered
                                            below wall base)
                            - "schematic": Plates are positioned for visual clarity
                                            (e.g., bottom plate centered above wall base)
        
        Returns:
            Dictionary containing test results and generated geometries
        """
        try:
            # Ensure we have a list of walls
            if isinstance(wall_data, dict):
                walls_to_process = [wall_data]
            elif isinstance(wall_data, list):
                walls_to_process = wall_data
            else:
                raise TypeError("wall_data must be a dictionary or list of dictionaries")
            
            if self.debug:
                print(f"\nProcessing {len(walls_to_process)} walls...")
                print(f"Using representation type: {representation_type}")  # Debug output
            
            # Process each wall individually
            for wall_index, wall_data in enumerate(walls_to_process):
                if self.debug:
                    print(f"\nProcessing wall {wall_index}:")
                    print(f"Wall type: {wall_data.get('wall_type', 'Unknown')}")
                    print(f"{'Exterior' if wall_data.get('is_exterior_wall', False) else 'Interior'} wall")

                try:
                    # Process this individual wall
                    wall_results = {}
                    
                    # Test location data
                    wall_results['location_data'] = self.test_location_data(wall_data)
                    
                    # Test parameters - Pass representation_type here!
                    wall_results['parameters'] = self.test_parameters(
                        wall_data,
                        representation_type=representation_type  # Pass it through
                    )
                    
                    # Store results for this wall
                    self._results[str(wall_index)] = wall_results
                    
                except Exception as e:
                    print(f"Error processing wall {wall_index}: {str(e)}")
                    continue

            return self._results
            
        except Exception as e:
            print(f"Error during plate testing: {str(e)}")
            import traceback
            print(traceback.format_exc())
            raise

    def get_visualization_geometry(
        self,
        geometry_type: str = "all",
        platform: str = "rhino",
        wall_id: Optional[str] = None
    ) -> list:
        """
        Extract geometry objects for visualization, with platform-specific processing.
        
        Args:
            geometry_type: Type of geometry to return. Options are:
                - "centerline": Only returns centerline curves
                - "platform_geometry": Returns platform-specific geometry
                - "all": Returns both centerlines and platform geometry
            platform: Target platform for visualization processing.
                Different platforms may require different visualization preparations.
                
        Returns:
            list: A list of geometry objects prepared for the specified platform
        """
        geometries = []
        
        # Determine which results to process
        if wall_id is not None:
            walls_to_process = {wall_id: self._results.get(wall_id, {})}
        else:
            walls_to_process = self._results
        
        # Extract geometry from each wall
        for wall_id, wall_results in walls_to_process.items():
            if 'plates' not in wall_results:
                continue
                
            for plate in wall_results['plates']:
                if geometry_type == "centerline":
                    if platform == "rhino":
                        geometries.append(plate.centerline)
                elif geometry_type == "platform_geometry":
                    if platform == "rhino":
                        geometry_data = plate.get_geometry_data(platform)
                        geometries.append(geometry_data['platform_geometry'])
                elif geometry_type == "all":
                    if platform == "rhino":
                        geometry_data = plate.get_geometry_data(platform)
                        geometries.extend([plate.centerline,
                                        geometry_data['platform_geometry']])
        
        return geometries