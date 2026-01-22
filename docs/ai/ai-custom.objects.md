# Guide: Simplified Timber Framing Generator with Custom Objects

## Overview

Instead of converting framing results to complex Grasshopper data trees, we'll create a custom object hierarchy that is:
1. Easier to maintain and debug
2. Compatible with JSON serialization/deserialization
3. Usable directly in Grasshopper components

## Custom Object Structure

```python
class TimberFramingResults:
    """Container for all wall framing results."""
    
    def __init__(self, wall_id=None):
        self.wall_id = wall_id
        self.bottom_plates = []
        self.top_plates = []
        self.king_studs = []
        self.studs = []
        self.headers = []
        self.sills = []
        self.trimmers = []
        self.header_cripples = []
        self.sill_cripples = []
        self.row_blocking = []
        self.cells = []
        self.debug_geometry = DebugGeometry()
        
    def add_element(self, element_type, element):
        """Add an element to the appropriate collection."""
        if hasattr(self, element_type):
            getattr(self, element_type).append(element)
            
    def get_all_geometry(self):
        """Return all geometric elements as a single list."""
        return (self.bottom_plates + self.top_plates + self.king_studs + 
                self.studs + self.headers + self.sills + self.trimmers +
                self.header_cripples + self.sill_cripples + self.row_blocking)
```

## Serialization Support

```python
import json
import Rhino.Geometry as rg
import System

class RhinoEncoder(json.JSONEncoder):
    """Custom JSON encoder for Rhino geometry."""
    
    def default(self, obj):
        # Handle Rhino geometry types
        if isinstance(obj, rg.GeometryBase):
            # Serialize to Base64 encoded string
            return {
                "___rhino_geometry___": True,
                "type": obj.GetType().Name,
                "data": System.Convert.ToBase64String(obj.Encode())
            }
        elif isinstance(obj, TimberFramingResults):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        elif isinstance(obj, DebugGeometry):
            return obj.__dict__
        return super().default(obj)

def rhino_object_hook(dct):
    """Hook to decode serialized Rhino geometry."""
    if "___rhino_geometry___" in dct:
        try:
            data = System.Convert.FromBase64String(dct["data"])
            return rg.GeometryBase.Decode(data)
        except:
            return dct
    return dct
```

## Updated Implementation for gh-main.py

```python
# File: gh-main.py
"""
Simplified main script for timber framing generation within Grasshopper.
Uses custom objects instead of complex data tree conversion.
"""

import sys
import os
import importlib
import json
from typing import Dict, List, Any, Optional

import Rhino
import Rhino.Geometry as rg
import System
from RhinoInside.Revit import Revit

# Classes for structure and serialization
class DebugGeometry:
    """Container for debug geometry."""
    
    def __init__(self):
        self.points = []
        self.planes = []
        self.profiles = []
        self.paths = []

class TimberFramingResults:
    """Container for wall framing results."""
    
    def __init__(self, wall_id=None):
        self.wall_id = wall_id
        self.bottom_plates = []
        self.top_plates = []
        self.king_studs = []
        self.studs = []
        self.headers = []
        self.sills = []
        self.trimmers = []
        self.header_cripples = []
        self.sill_cripples = []
        self.row_blocking = []
        self.cells = []
        self.debug_geometry = DebugGeometry()
        self.base_plane = None
        
    def add_element(self, element_type, element):
        """Add an element to the appropriate collection."""
        if hasattr(self, element_type):
            getattr(self, element_type).append(element)
            
    def get_all_geometry(self):
        """Return all geometric elements as a single list."""
        return (self.bottom_plates + self.top_plates + self.king_studs + 
                self.studs + self.headers + self.sills + self.trimmers +
                self.header_cripples + self.sill_cripples + self.row_blocking)
    
    def element_count(self, element_type):
        """Return count of elements by type."""
        if hasattr(self, element_type):
            return len(getattr(self, element_type))
        return 0

# Project imports (same as before)
# ...

def extract_wall_data(walls) -> List[Dict[str, Any]]:
    """Extract data from selected Revit walls using our data extractor."""
    # Same implementation as before
    # ...

def convert_framing_to_objects(all_framing_results: List[Dict[str, Any]]) -> List[TimberFramingResults]:
    """Convert framing results dictionaries to custom objects."""
    result_objects = []
    
    for wall_index, framing in enumerate(all_framing_results):
        # Create a result object for this wall
        result = TimberFramingResults(f"Wall_{wall_index}")
        
        print(f"\nProcessing wall {wall_index}:")
        
        # Get base plane from various sources
        base_plane = None
        if 'base_plane' in framing:
            base_plane = framing['base_plane']
        elif 'wall_data' in framing and 'base_plane' in framing['wall_data']:
            base_plane = framing['wall_data']['base_plane']
        # Add more fallbacks if needed
        
        result.base_plane = base_plane
        result.cells = framing.get('cells', [])
        
        # Add bottom plates
        for plate in framing.get('bottom_plates', []):
            try:
                geometry_data = plate.get_geometry_data(platform="rhino")
                result.bottom_plates.append(geometry_data['platform_geometry'])
            except Exception as e:
                print(f"Error extracting bottom plate geometry: {str(e)}")
        
        # Add top plates
        for plate in framing.get('top_plates', []):
            try:
                geometry_data = plate.get_geometry_data(platform="rhino")
                result.top_plates.append(geometry_data['platform_geometry'])
            except Exception as e:
                print(f"Error extracting top plate geometry: {str(e)}")
        
        # Add other elements
        result.king_studs = framing.get('king_studs', [])
        result.headers = framing.get('headers', [])
        result.sills = framing.get('sills', [])
        result.trimmers = framing.get('trimmers', [])
        result.header_cripples = framing.get('header_cripples', [])
        result.sill_cripples = framing.get('sill_cripples', [])
        result.studs = framing.get('studs', [])
        result.row_blocking = framing.get('row_blocking', [])
        
        # Add debug geometry
        debug_geom = framing.get('debug_geometry', {})
        result.debug_geometry.points = debug_geom.get('points', [])
        result.debug_geometry.planes = debug_geom.get('planes', [])
        result.debug_geometry.profiles = debug_geom.get('profiles', [])
        result.debug_geometry.paths = debug_geom.get('paths', [])
        
        # Log statistics
        print(f"Wall {wall_index} element counts:")
        print(f"- Bottom plates: {len(result.bottom_plates)}")
        print(f"- Top plates: {len(result.top_plates)}")
        print(f"- King studs: {len(result.king_studs)}")
        # More counts...
        
        result_objects.append(result)
        
    return result_objects

# Main execution for the Grasshopper component
def main():
    """Main execution for the Grasshopper component."""
    if run:
        # Extract wall data
        wall_dict = extract_wall_data(walls)
        wall_count = len(wall_dict)
        print(f"\nProcessing {wall_count} walls")
        
        # Define our configuration
        framing_config = {
            'representation_type': "schematic",
            'bottom_plate_layers': 1,
            'top_plate_layers': 2,
            'include_blocking': True,
            'block_spacing': 48.0/12.0,
            'first_block_height': 24.0/12.0,
            'blocking_pattern': "staggered"
        }
        
        # Process each wall and store results
        all_framing_results = []
        
        for i, wall_data in enumerate(wall_dict):
            try:
                print(f"\nProcessing wall {i+1} of {wall_count}")
                generator = FramingGenerator(
                    wall_data=wall_data,
                    framing_config=framing_config
                )
                
                framing = generator.generate_framing()
                all_framing_results.append(framing)
                
                # Diagnostic output remains the same
                # ...
                
            except Exception as e:
                print(f"Error processing wall {i+1}: {str(e)}")
                import traceback
                print(traceback.format_exc())
                continue
        
        # Convert framing results to custom objects
        framing_objects = convert_framing_to_objects(all_framing_results)
        
        # Return a single object instead of multiple trees
        return framing_objects
    else:
        return None

# Execute main function and assign outputs
result = main()
```

## JSON Serialization/Deserialization

```python
def serialize_results(results):
    """Serialize TimberFramingResults to JSON string."""
    encoder = RhinoEncoder()
    return json.dumps(results, cls=encoder)

def deserialize_results(json_string):
    """Deserialize JSON string to TimberFramingResults objects."""
    return json.loads(json_string, object_hook=rhino_object_hook)

# Example usage:
# json_data = serialize_results(framing_objects)
# reconstructed_objects = deserialize_results(json_data)
```

## Grasshopper Integration Tips

1. **Create components to access specific element types:**
   ```python
   # In a Grasshopper Python component
   def process_results(results_object):
       if results_object is None:
           return None
       
       # Extract bottom plates from the results object
       return results_object.bottom_plates
   
   # Set up inputs/outputs in GH
   a = process_results(results)
   ```

2. **Access by property path using reflection:**
   ```python
   def get_property(obj, property_path):
       """Get property value by path (e.g., 'debug_geometry.points')"""
       if obj is None:
           return None
           
       parts = property_path.split('.')
       value = obj
       
       for part in parts:
           if hasattr(value, part):
               value = getattr(value, part)
           else:
               return None
               
       return value
   
   # Example usage
   points = get_property(results, "debug_geometry.points")
   ```

3. **Using with HTTP requests:**
   ```python
   import requests
   
   def send_results_to_api(results, api_url):
       """Send results to API endpoint."""
       json_data = serialize_results(results)
       
       response = requests.post(
           api_url,
           data=json_data,
           headers={"Content-Type": "application/json"}
       )
       
       return response.status_code == 200
   ```

## Implementation Steps

1. Create the custom classes (TimberFramingResults, DebugGeometry)
2. Implement JSON serialization/deserialization
3. Replace convert_framing_to_trees with convert_framing_to_objects
4. Update main() to return custom objects instead of data trees
5. Create Grasshopper components to extract and display specific elements

This approach greatly simplifies the workflow, improves maintainability, and provides a cleaner interface for API integration.