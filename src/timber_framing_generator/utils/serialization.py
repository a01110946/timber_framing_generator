# File: src/timber_framing_generator/utils/serialization.py

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script: serialization.py
Location: src/timber_framing_generator/utils/serialization.py
Author: Timber Framing Generator Team
Date Created: 2025-03-24
Last Modified: 2025-03-24

Description:
    Contains custom classes for serializing and deserializing timber framing 
    results, including Rhino geometry objects. This module provides a unified 
    structure for storing, transmitting, and retrieving framing results.

Usage:
    from src.timber_framing_generator.utils.serialization import (
        TimberFramingResults, DebugGeometry, 
        serialize_results, deserialize_results
    )
    
    # Create and populate a results object
    results = TimberFramingResults(wall_id="Wall_1")
    results.add_element("studs", stud_object)
    
    # Serialize to JSON
    json_str = serialize_results(results)
    
    # Deserialize from JSON
    recovered_results = deserialize_results(json_str)

Dependencies:
    - Rhino.Geometry
    - System
    - json
"""

from typing import Dict, List, Any, Optional, Union
import json
import Rhino.Geometry as rg
import System


class DebugGeometry:
    """
    Container for debug geometry elements used during framing generation.
    
    This class stores geometric elements used for debugging and visualization,
    such as points, planes, profiles, and paths.
    """
    
    def __init__(self) -> None:
        """Initialize empty collections for debug geometry."""
        self.points: List[rg.Point3d] = []
        self.planes: List[rg.Plane] = []
        self.profiles: List[rg.GeometryBase] = []
        self.paths: List[rg.Curve] = []


class TimberFramingResults:
    """
    Container for all wall framing results.
    
    This class organizes framing elements by type and provides methods for
    accessing and manipulating them. It can be serialized to JSON for
    storage or transmission over API endpoints.
    
    Attributes:
        wall_id: Unique identifier for the wall
        bottom_plates: List of bottom plate geometry
        top_plates: List of top plate geometry
        king_studs: List of king stud geometry
        studs: List of standard stud geometry
        headers: List of header geometry
        sills: List of sill geometry
        trimmers: List of trimmer geometry
        header_cripples: List of header cripple geometry
        sill_cripples: List of sill cripple geometry
        row_blocking: List of row blocking geometry
        cells: List of cell data dictionaries
        debug_geometry: DebugGeometry object containing debug elements
        base_plane: Wall base plane for reference
    """
    
    def __init__(self, wall_id: Optional[str] = None) -> None:
        """
        Initialize a TimberFramingResults container.
        
        Args:
            wall_id: Optional unique identifier for the wall
        """
        self.wall_id: Optional[str] = wall_id
        self.bottom_plates: List[rg.GeometryBase] = []
        self.top_plates: List[rg.GeometryBase] = []
        self.king_studs: List[rg.GeometryBase] = []
        self.studs: List[rg.GeometryBase] = []
        self.headers: List[rg.GeometryBase] = []
        self.sills: List[rg.GeometryBase] = []
        self.trimmers: List[rg.GeometryBase] = []
        self.header_cripples: List[rg.GeometryBase] = []
        self.sill_cripples: List[rg.GeometryBase] = []
        self.row_blocking: List[rg.GeometryBase] = []
        self.cells: List[Dict[str, Any]] = []
        self.debug_geometry: DebugGeometry = DebugGeometry()
        self.base_plane: Optional[rg.Plane] = None
        
    def add_element(self, element_type: str, element: rg.GeometryBase) -> None:
        """
        Add an element to the appropriate collection.
        
        Args:
            element_type: Type of element (e.g., "studs", "bottom_plates")
            element: Geometric element to add
        """
        if hasattr(self, element_type):
            getattr(self, element_type).append(element)
            
    def get_all_geometry(self) -> List[rg.GeometryBase]:
        """
        Return all geometric elements as a single list.
        
        Returns:
            Combined list of all framing elements
        """
        return (self.bottom_plates + self.top_plates + self.king_studs + 
                self.studs + self.headers + self.sills + self.trimmers +
                self.header_cripples + self.sill_cripples + self.row_blocking)
    
    def element_count(self, element_type: str) -> int:
        """
        Return count of elements by type.
        
        Args:
            element_type: Type of element to count
            
        Returns:
            Number of elements of the specified type
        """
        if hasattr(self, element_type):
            return len(getattr(self, element_type))
        return 0


class RhinoEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for Rhino geometry.
    
    This encoder handles serialization of Rhino geometry objects
    by encoding them as Base64 strings with appropriate type information.
    """
    
    def default(self, obj: Any) -> Any:
        """
        Custom encoding for special types.
        
        Args:
            obj: Object to encode
            
        Returns:
            JSON-serializable representation of the object
        """
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

def rhino_object_hook(dct: Dict[str, Any]) -> Union[Dict[str, Any], rg.GeometryBase]:
    """
    Hook to decode serialized Rhino geometry.
    
    Args:
        dct: Dictionary that might contain serialized Rhino geometry
        
    Returns:
        Deserialized Rhino geometry object or the original dictionary
    """
    if "___rhino_geometry___" in dct:
        try:
            data = System.Convert.FromBase64String(dct["data"])
            return rg.GeometryBase.Decode(data)
        except Exception:
            # If decoding fails, return the original dictionary
            return dct
    return dct

def serialize_results(results: Union[TimberFramingResults, List[TimberFramingResults]]) -> str:
    """
    Serialize TimberFramingResults to JSON string.
    
    Args:
        results: Single result object or list of result objects
        
    Returns:
        JSON string representation
    """
    encoder = RhinoEncoder()
    return json.dumps(results, cls=encoder)

def deserialize_results(json_string: str) -> Union[TimberFramingResults, List[TimberFramingResults]]:
    """
    Deserialize JSON string to TimberFramingResults objects.
    
    Args:
        json_string: JSON string to deserialize
        
    Returns:
        Deserialized TimberFramingResults object(s)
    """
    return json.loads(json_string, object_hook=rhino_object_hook)

def get_property(obj: Any, property_path: str) -> Any:
    """
    Get property value by path (e.g., 'debug_geometry.points')
    
    Args:
        obj: Object to get property from
        property_path: Dot-separated path to the property
        
    Returns:
        Property value or None if not found
    """
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

def inspect_framing_results(framing_object):
    """
    Inspect and print details of a TimberFramingResults object.
    """
    print(f"Framing object type: {type(framing_object).__name__}")
    
    # Check wall data
    if hasattr(framing_object, 'wall_data') and framing_object.wall_data:
        print("\nWall properties:")
        for key in ['wall_type', 'wall_length', 'wall_height', 'is_exterior_wall']:
            if key in framing_object.wall_data:
                print(f"  {key}: {framing_object.wall_data.get(key)}")
    
    # Print count of each framing element type
    print("\nFraming element counts:")
    for prop in [
        'bottom_plates', 'top_plates', 'king_studs', 'headers', 
        'sills', 'trimmers', 'header_cripples', 'sill_cripples', 
        'studs', 'row_blocking'
    ]:
        if hasattr(framing_object, prop):
            elements = getattr(framing_object, prop)
            if isinstance(elements, list):
                print(f"  {prop}: {len(elements)} elements")
                
                # Print details about the first element if available
                if elements:
                    first_elem = elements[0]
                    print(f"    First element type: {type(first_elem).__name__}")
                    
                    # Get bounding box if available
                    if hasattr(first_elem, 'GetBoundingBox'):
                        try:
                            bbox = first_elem.GetBoundingBox(True)
                            if bbox.IsValid:
                                print(f"    Dimensions: W={bbox.Max.X-bbox.Min.X:.2f}, D={bbox.Max.Y-bbox.Min.Y:.2f}, H={bbox.Max.Z-bbox.Min.Z:.2f}")
                        except:
                            print("    Could not get bounding box")