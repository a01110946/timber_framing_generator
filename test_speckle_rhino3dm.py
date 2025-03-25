#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for Speckle integration using rhino3dm.

This script tests the Speckle integration for the Timber Framing Generator
by connecting to a Speckle stream, extracting wall data, and printing the results.
It uses rhino3dm as a replacement for the full Rhino environment.
"""

# Standard library imports
import os
import sys
import json
import time
import logging
import traceback
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
import uuid

try:
    # Core Speckle imports - keep these minimal
    from specklepy.api import operations
    from specklepy.api.client import SpeckleClient
    from specklepy.api.credentials import get_account_from_token
    from specklepy.objects.base import Base
    from specklepy.transports.server import ServerTransport
    
    # rhino3dm import for geometry
    import rhino3dm as r3d
    
    # Helper for recursive traversal of Speckle objects
    def traverse(obj):
        """
        Generator function to traverse all properties of a Speckle object recursively.
        
        Args:
            obj: A Speckle object or any Python object to traverse
            
        Yields:
            Each non-None property of the object
        """
        if obj is None:
            return
            
        yield obj
        
        if isinstance(obj, Base):
            for prop_name in obj.get_dynamic_member_names():
                prop_value = getattr(obj, prop_name)
                
                if isinstance(prop_value, list):
                    for item in prop_value:
                        yield from traverse(item)
                else:
                    yield from traverse(prop_value)
        elif isinstance(obj, dict):
            for value in obj.values():
                yield from traverse(value)
        elif isinstance(obj, list):
            for item in obj:
                yield from traverse(item)
                
except ImportError as e:
    print(f"Error importing Speckle SDK: {str(e)}")
    print("Please install the required packages with: pip install specklepy")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("speckle_test")

# Add src directory to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

# Define type hint for wall input data
WallInputData = Dict[
    str, Union[r3d.Curve, float, bool, List[Dict[str, Union[str, float]]], r3d.Plane]
]

def get_walls_from_speckle(client: SpeckleClient, stream_id: str, commit_id: str = "latest") -> List[Base]:
    """
    Get all wall objects from a Speckle stream.
    
    Args:
        client: Speckle client
        stream_id: Stream ID
        commit_id: Commit ID or "latest"
        
    Returns:
        List of wall objects
    """
    walls = []
    
    try:
        # Use the legacy or new API to get the latest commit
        if commit_id == "latest":
            logger.info(f"Retrieving walls from stream: {stream_id}, commit: {commit_id}")
            
            # Try legacy API first
            commits = client.commit.list(stream_id, limit=1)
            if commits and len(commits) > 0:
                commit_id = commits[0].id
                logger.info(f"Using latest commit: {commit_id}")
            else:
                # Try new API
                try:
                    versions = client.version.list(stream_id, limit=1)
                    if versions and len(versions) > 0:
                        commit_id = versions[0].id
                        logger.info(f"Using latest version: {commit_id}")
                    else:
                        raise ValueError("No commits or versions found")
                except Exception as e:
                    logger.error(f"Error listing versions: {str(e)}")
                    raise ValueError(f"No commits found for stream: {stream_id}")
        
        # Get the commit or version
        try:
            # Try legacy commit API first
            commit = None
            try:
                commit = client.commit.get(stream_id, commit_id)
                obj_id = commit.referencedObject
                logger.info(f"Receiving Speckle data from stream {stream_id}, commit {commit_id}")
            except Exception as ce:
                logger.warning(f"Error accessing commit via legacy API: {str(ce)}")
                
                # Try new version API
                try:
                    version = client.version.get(stream_id, commit_id)
                    obj_id = version.referencedObject
                    logger.info(f"Receiving Speckle data from model {stream_id}, version {commit_id}")
                except Exception as ve:
                    logger.error(f"Error accessing version: {str(ve)}")
                    raise ValueError(f"Failed to get commit or version: {str(ce)}, {str(ve)}")
            
            # Create a server transport for receiving data
            try:
                # The ServerTransport needs the client instance and stream ID
                transport = ServerTransport(client=client, stream_id=stream_id)
                
                # Receive the object using operations.receive
                base_obj = operations.receive(obj_id=obj_id, remote_transport=transport)
                logger.info(f"Successfully received object from Speckle")
                
                # Debug: Log the structure of the received object
                if hasattr(base_obj, 'get_dynamic_member_names'):
                    member_names = base_obj.get_dynamic_member_names()
                    logger.info(f"Top-level object members: {member_names}")
                    
                    # Detailed exploration of each top-level member
                    for member_name in member_names:
                        member_value = getattr(base_obj, member_name)
                        
                        # Check if it's a collection
                        if isinstance(member_value, list):
                            logger.info(f"Collection '{member_name}' has {len(member_value)} items")
                            
                            # Show sample of first few items
                            for i, item in enumerate(member_value[:3]):  # Just check first 3 items
                                if hasattr(item, 'get_dynamic_member_names'):
                                    item_members = item.get_dynamic_member_names()
                                    logger.info(f"  Item {i} members: {item_members}")
                                else:
                                    logger.info(f"  Item {i} type: {type(item)}")
                        
                        # Check if it's a dictionary or Base object
                        elif isinstance(member_value, (dict, Base)):
                            if isinstance(member_value, dict):
                                logger.info(f"Dict '{member_name}' has keys: {list(member_value.keys())[:10]}")  # Show first 10 keys
                            elif hasattr(member_value, 'get_dynamic_member_names'):
                                submembers = member_value.get_dynamic_member_names()
                                logger.info(f"Object '{member_name}' has members: {submembers}")
                    
                    # Special case for @Types which often contains model schema
                    if hasattr(base_obj, '@Types'):
                        types_obj = getattr(base_obj, '@Types')
                        logger.info(f"@Types type: {type(types_obj)}")
                        
                        if isinstance(types_obj, dict):
                            logger.info(f"@Types keys: {list(types_obj.keys())[:10]}")  # First 10 keys
                            
                            # Look for wall-related keys
                            wall_keys = [k for k in types_obj.keys() if 'wall' in k.lower()]
                            if wall_keys:
                                logger.info(f"Wall-related keys in @Types: {wall_keys}")
                    
                    # Special case for info which may have model metadata
                    if hasattr(base_obj, 'info'):
                        info_obj = getattr(base_obj, 'info')
                        logger.info(f"info type: {type(info_obj)}")
                        
                        if hasattr(info_obj, 'get_dynamic_member_names'):
                            info_members = info_obj.get_dynamic_member_names()
                            logger.info(f"info members: {info_members}")
                        
                        # Check for objects collection which might contain the actual model objects
                        if hasattr(info_obj, 'objects') and isinstance(info_obj.objects, list):
                            logger.info(f"Found 'objects' collection with {len(info_obj.objects)} items")
                            
                            # Check first few objects
                            for i, obj in enumerate(info_obj.objects[:5]):  # First 5 objects
                                if hasattr(obj, 'get_dynamic_member_names'):
                                    obj_members = obj.get_dynamic_member_names()
                                    logger.info(f"  Object {i} members: {obj_members}")
                                    
                                    # Check if this is a wall
                                    if hasattr(obj, 'category') and obj.category == "Walls":
                                        logger.info(f"  Found wall in objects[{i}]")
                                        walls.append(obj)
                        
                        # Check for locations collection which might contain the building elements
                        if hasattr(info_obj, 'locations') and isinstance(info_obj.locations, list):
                            logger.info(f"Found 'locations' collection with {len(info_obj.locations)} items")
                            
                            # Check first locations object
                            for loc_idx, location in enumerate(info_obj.locations):
                                if hasattr(location, 'get_dynamic_member_names'):
                                    location_members = location.get_dynamic_member_names()
                                    logger.info(f"  Location {loc_idx} members: {location_members}")
                                    
                                    # Look for elements or objects collection within location
                                    for location_member in location_members:
                                        member_value = getattr(location, location_member)
                                        if isinstance(member_value, list):
                                            logger.info(f"    Collection '{location_member}' has {len(member_value)} items")
                                            
                                            # Check first few elements
                                            wall_count_in_location = 0
                                            for i, element in enumerate(member_value[:20]):  # Check first 20 items
                                                # Try to identify walls based on various criteria
                                                found_wall = False
                                                
                                                # Check if it has category = Walls
                                                if hasattr(element, 'category') and element.category == "Walls":
                                                    wall_count_in_location += 1
                                                    found_wall = True
                                                    if element not in walls:
                                                        walls.append(element)
                                                
                                                # Check speckle_type for RevitWall
                                                elif hasattr(element, 'speckle_type') and "RevitWall" in element.speckle_type:
                                                    wall_count_in_location += 1
                                                    found_wall = True
                                                    if element not in walls:
                                                        walls.append(element)
                                                
                                                # Check @speckle_type in __dict__ for RevitWall
                                                elif hasattr(element, '__dict__') and '@speckle_type' in element.__dict__ and "RevitWall" in element.__dict__['@speckle_type']:
                                                    wall_count_in_location += 1
                                                    found_wall = True
                                                    if element not in walls:
                                                        walls.append(element)
                                                
                                                # Check family name or any other wall indicators
                                                elif hasattr(element, 'family') and hasattr(element.family, 'name') and "Wall" in element.family.name:
                                                    wall_count_in_location += 1
                                                    found_wall = True
                                                    if element not in walls:
                                                        walls.append(element)

                                                if found_wall and i < 3:  # Just log details for first 3 walls
                                                    if hasattr(element, 'get_dynamic_member_names'):
                                                        wall_members = element.get_dynamic_member_names()
                                                        logger.info(f"      Found wall in {location_member}[{i}] with members: {wall_members}")
                                            
                                            if wall_count_in_location > 0:
                                                logger.info(f"    Found {wall_count_in_location} walls in '{location_member}' collection")
                
            except Exception as e:
                logger.error(f"Error creating transport or receiving data: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Try alternative approach with direct operations receive
                try:
                    logger.info("Trying alternative approach with direct operations.receive")
                    base_obj = operations.receive(obj_id, client)
                except Exception as e2:
                    logger.error(f"Alternative approach failed: {str(e2)}")
                    raise ValueError(f"Failed to retrieve data from Speckle: {str(e)}, {str(e2)}")
            
            # Multiple approaches to find walls
            
            # Approach 1: Look for objects with speckle_type containing RevitWall
            wall_count = 0
            for element in traverse(base_obj):
                if hasattr(element, '@speckle_type') and isinstance(element.__dict__.get('@speckle_type'), str):
                    speckle_type = element.__dict__.get('@speckle_type')
                    if "RevitWall" in speckle_type:
                        walls.append(element)
                        wall_count += 1
                        logger.info(f"Found RevitWall by @speckle_type: {speckle_type}")
                elif hasattr(element, 'speckle_type') and isinstance(element.speckle_type, str):
                    if "RevitWall" in element.speckle_type:
                        walls.append(element)
                        wall_count += 1
                        logger.info(f"Found RevitWall by speckle_type: {element.speckle_type}")
            
            logger.info(f"Found {wall_count} walls by type in Speckle stream")
            
            # Approach 2: Look for objects with RevitWall property
            revit_wall_count = 0
            for element in traverse(base_obj):
                if hasattr(element, 'RevitWall'):
                    walls.append(element)
                    revit_wall_count += 1
                    logger.info(f"Found object with RevitWall property")
            
            logger.info(f"Found {revit_wall_count} objects with RevitWall property")
            
            # Approach 3: Look by category
            category_wall_count = 0
            for element in traverse(base_obj):
                if hasattr(element, 'category') and isinstance(element.category, str) and element.category == "Walls":
                    if element not in walls:  # Avoid duplicates
                        walls.append(element)
                        category_wall_count += 1
                        logger.info(f"Found wall by category: {element.category}")
            
            logger.info(f"Found {category_wall_count} walls by category")
            
            # Approach 4: Look for objects with builtInCategory OST_Walls
            built_in_count = 0
            for element in traverse(base_obj):
                if hasattr(element, 'builtInCategory') and element.builtInCategory == "OST_Walls":
                    if element not in walls:  # Avoid duplicates
                        walls.append(element)
                        built_in_count += 1
                        logger.info(f"Found wall by builtInCategory: {element.builtInCategory}")
            
            logger.info(f"Found {built_in_count} walls by builtInCategory")
            
            # Check elements or objects arrays in the top level
            for member_name in base_obj.get_dynamic_member_names():
                member_value = getattr(base_obj, member_name)
                if isinstance(member_value, list):
                    logger.info(f"Checking collection '{member_name}' with {len(member_value)} items")
                    
                    for item in member_value:
                        if hasattr(item, '@speckle_type') and "RevitWall" in item.__dict__.get('@speckle_type', ''):
                            if item not in walls:
                                walls.append(item)
                                logger.info(f"Found wall in collection {member_name}")
                        elif hasattr(item, 'RevitWall'):
                            if item not in walls:
                                walls.append(item)
                                logger.info(f"Found object with RevitWall property in collection {member_name}")
            
            # Special case: check @data member which often contains the actual model data
            if hasattr(base_obj, '@data') and isinstance(base_obj.__dict__.get('@data'), list):
                data_items = base_obj.__dict__.get('@data')
                logger.info(f"Found @data collection with {len(data_items)} items")
                
                for item in data_items:
                    if hasattr(item, '@speckle_type') and "RevitWall" in item.__dict__.get('@speckle_type', ''):
                        if item not in walls:
                            walls.append(item)
                            logger.info(f"Found wall in @data collection")
                    elif hasattr(item, 'RevitWall'):
                        if item not in walls:
                            walls.append(item)
                            logger.info(f"Found object with RevitWall property in @data collection")
            
            if len(walls) == 0:
                logger.warning("No walls found in Speckle stream using any approach")
                
            return walls
        
        except Exception as e:
            logger.error(f"Error retrieving object: {str(e)}")
            logger.error(traceback.format_exc())
            raise ValueError(f"Failed to retrieve Speckle object: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error retrieving walls from Speckle: {str(e)}")
        logger.error(traceback.format_exc())
        raise ValueError(f"Failed to get walls from Speckle: {str(e)}")
        
    return walls

def extract_wall_data_from_speckle(wall_obj: Base) -> Dict[str, Any]:
    """
    Extract wall data from a Speckle wall object.
    
    Args:
        wall_obj: Speckle wall object
        
    Returns:
        Dictionary with wall data
    """
    try:
        wall_data = {}
        
        # Extract RevitWall data if present (we expect it to be nested inside)
        revit_wall = None
        if hasattr(wall_obj, 'RevitWall'):
            revit_wall = wall_obj.RevitWall
        elif hasattr(wall_obj, 'speckle_type') and "RevitWall" in wall_obj.speckle_type:
            revit_wall = wall_obj
            
        if revit_wall:
            # Extract wall ID
            wall_data["wall_id"] = getattr(revit_wall, 'id', str(uuid.uuid4()))
            
            # Extract wall name and type
            wall_data["wall_name"] = getattr(revit_wall, 'family', "Unknown Wall")
            wall_data["wall_type"] = getattr(revit_wall, 'type', "Unknown Type")
            
            # Extract wall dimensions
            wall_data["base_elevation"] = getattr(revit_wall, 'baseOffset', 0.0)
            wall_data["top_elevation"] = getattr(revit_wall, 'topOffset', 0.0)
            wall_data["wall_height"] = getattr(revit_wall, 'height', 0.0)
            
            # Get wall length from baseLine if available
            wall_data["wall_length"] = 0.0
            if hasattr(revit_wall, 'baseLine') and hasattr(revit_wall.baseLine, 'length'):
                wall_data["wall_length"] = revit_wall.baseLine.length
            elif hasattr(revit_wall, 'parameters') and 'Length' in revit_wall.parameters:
                wall_data["wall_length"] = revit_wall.parameters['Length']
                
            # Extract wall thickness
            wall_data["wall_thickness"] = 0.0
            if hasattr(revit_wall, 'parameters') and 'Width' in revit_wall.parameters:
                wall_data["wall_thickness"] = revit_wall.parameters['Width']
                
            # Extract structural flag
            wall_data["is_structural"] = getattr(revit_wall, 'structural', False)
            
            # Extract base geometry
            if hasattr(revit_wall, 'baseLine'):
                wall_data["base_curve"] = str(revit_wall.baseLine)
                
                # Create a base plane from the baseLine if possible
                if hasattr(revit_wall.baseLine, 'start') and hasattr(revit_wall.baseLine, 'end'):
                    start_pt = revit_wall.baseLine.start
                    end_pt = revit_wall.baseLine.end
                    wall_data["base_plane"] = f"Plane from {start_pt} to {end_pt}"
            else:
                wall_data["base_curve"] = None
                wall_data["base_plane"] = None
                
            # Find all openings (windows, doors) in the wall
            openings = []
            
            # Check for elements array which might contain openings
            if hasattr(revit_wall, 'elements') and revit_wall.elements:
                for element in revit_wall.elements:
                    # Check if this element is a window or door
                    if hasattr(element, 'speckle_type'):
                        # Extract opening data
                        opening_data = {
                            "id": getattr(element, 'id', str(uuid.uuid4())),
                            "type": "Unknown"
                        }
                        
                        # Determine if it's a window or door
                        if "Window" in element.speckle_type:
                            opening_data["type"] = "Window"
                        elif "Door" in element.speckle_type:
                            opening_data["type"] = "Door"
                        
                        # Get opening dimensions if available
                        if hasattr(element, 'height'):
                            opening_data["height"] = element.height
                        if hasattr(element, 'width'):
                            opening_data["width"] = element.width
                            
                        openings.append(opening_data)
            
            wall_data["openings"] = openings
            
            # Add any additional parameters if available
            if hasattr(revit_wall, 'parameters'):
                wall_data["parameters"] = revit_wall.parameters
                
            return wall_data
        else:
            # Fallback for non-Revit walls
            logger.info(f"Using fallback extraction for non-Revit wall")
            
            # Basic wall info
            wall_data["wall_id"] = getattr(wall_obj, 'id', str(uuid.uuid4()))
            wall_data["wall_name"] = getattr(wall_obj, 'name', "Unknown Wall")
            wall_data["wall_type"] = getattr(wall_obj, 'type', "Unknown Type")
            
            # Default values for other properties
            wall_data["base_elevation"] = getattr(wall_obj, 'baseElevation', 0.0)
            wall_data["top_elevation"] = getattr(wall_obj, 'topElevation', 0.0)
            wall_data["wall_thickness"] = getattr(wall_obj, 'thickness', 0.0)
            wall_data["wall_length"] = getattr(wall_obj, 'length', 0.0)
            wall_data["wall_height"] = getattr(wall_obj, 'height', 0.0)
            wall_data["is_structural"] = getattr(wall_obj, 'structural', True)
            wall_data["openings"] = []
            wall_data["base_curve"] = None
            wall_data["base_plane"] = None
            
            return wall_data
            
    except Exception as e:
        logger.error(f"Error extracting wall data: {str(e)}")
        logger.error(traceback.format_exc())
        raise ValueError(f"Failed to extract wall data: {str(e)}")

def convert_speckle_point_to_rhino3dm(speckle_point: Union[Dict[str, float], r3d.Point3d]) -> r3d.Point3d:
    """
    Convert a Speckle point to a rhino3dm Point3d.
    
    Args:
        speckle_point: Speckle Point object or dictionary with x, y, z coordinates
        
    Returns:
        rhino3dm Point3d object
    """
    if isinstance(speckle_point, dict):
        return r3d.Point3d(speckle_point.get("x", 0), 
                          speckle_point.get("y", 0), 
                          speckle_point.get("z", 0))
    elif isinstance(speckle_point, r3d.Point3d):
        return speckle_point
    else:
        raise TypeError(f"Unsupported point type: {type(speckle_point)}")

def convert_speckle_curve_to_rhino3dm(speckle_curve: Union[Base, r3d.Curve]) -> r3d.Curve:
    """
    Convert a Speckle curve to a rhino3dm curve.
    
    Args:
        speckle_curve: Speckle curve object (Curve, Line, or Polyline)
        
    Returns:
        rhino3dm curve object
    """
    if isinstance(speckle_curve, Base):
        if hasattr(speckle_curve, "displayValue") and speckle_curve.displayValue:
            display_obj = speckle_curve.displayValue
            if hasattr(display_obj, "points") and display_obj.points:
                points = [convert_speckle_point_to_rhino3dm(pt) for pt in display_obj.points]
                polyline = r3d.Polyline()
                for pt in points:
                    polyline.Add(pt.X, pt.Y, pt.Z)
                return r3d.PolylineCurve(polyline)
        else:
            logger.warning(f"Failed to convert Speckle curve: {speckle_curve}")
            # Return a default line as fallback
            return r3d.LineCurve(r3d.Line(r3d.Point3d(0,0,0), r3d.Point3d(1,0,0)))
    elif isinstance(speckle_curve, r3d.Curve):
        return speckle_curve
    else:
        logger.warning(f"Unsupported curve type: {type(speckle_curve)}")
        # Return a default line as fallback
        return r3d.LineCurve(r3d.Line(r3d.Point3d(0,0,0), r3d.Point3d(1,0,0)))

def create_base_plane_from_curve(base_curve: r3d.Curve, base_elevation: float) -> r3d.Plane:
    """
    Create a base plane for a wall using its base curve and elevation.
    
    Args:
        base_curve: Wall base curve in rhino3dm geometry
        base_elevation: Base elevation of the wall
        
    Returns:
        rhino3dm plane representing the wall's base plane
    """
    try:
        # Get curve domain
        domain = base_curve.Domain
        
        # Get point at the middle of the curve
        t = (domain.Min + domain.Max) / 2.0
        curve_point = base_curve.PointAt(t)
        
        # Get tangent vector at the point
        tangent = base_curve.TangentAt(t)
        
        # Create Z-axis vector
        z_axis = r3d.Vector3d(0, 0, 1)
        
        # Create Y-axis as cross product of Z and tangent
        y_axis = r3d.Vector3d.CrossProduct(z_axis, tangent)
        y_axis.Unitize()
        
        # Ensure tangent is normalized
        tangent.Unitize()
        
        # Create point with elevation
        origin = r3d.Point3d(curve_point.X, curve_point.Y, base_elevation)
        
        # Create X, Y, Z frame for the plane
        plane = r3d.Plane(origin, tangent, y_axis)
        
        return plane
        
    except Exception as e:
        logger.error(f"Error creating base plane: {str(e)}")
        # Return XY plane as fallback
        return r3d.Plane.WorldXY()

def find_openings_in_speckle_wall(wall_obj: Base) -> List[Dict[str, Any]]:
    """
    Find door and window openings in a Speckle wall object.
    
    This function searches for openings by:
    1. Looking for direct children/references in the wall object
    2. Checking for embedded opening elements
    3. Examining displayValue for geometric representations
    
    Args:
        wall_obj: Speckle wall object
        
    Returns:
        List of opening dictionaries with type, dimensions and position
    """
    openings = []
    
    # Helper function to check if an object is a potential opening
    def is_opening_type(obj_type: str) -> bool:
        opening_types = ["Door", "Window", "Opening", "Insert"]
        return any(opening_type in obj_type for opening_type in opening_types)
    
    # 1. Look for elements property which might contain openings
    if hasattr(wall_obj, "elements") and wall_obj.elements:
        for element in wall_obj.elements:
            if (hasattr(element, "speckle_type") and 
                is_opening_type(element.speckle_type)):
                opening_data = process_potential_opening(element, wall_obj)
                if opening_data:
                    openings.append(opening_data)
    
    # 2. Look for inserts/openings property
    for prop_name in ["inserts", "openings", "insert", "opening"]:
        if hasattr(wall_obj, prop_name):
            prop_value = getattr(wall_obj, prop_name)
            
            # Handle both single object and lists
            if isinstance(prop_value, list):
                for item in prop_value:
                    if hasattr(item, "speckle_type"):
                        opening_data = process_potential_opening(item, wall_obj)
                        if opening_data:
                            openings.append(opening_data)
            elif hasattr(prop_value, "speckle_type"):
                opening_data = process_potential_opening(prop_value, wall_obj)
                if opening_data:
                    openings.append(opening_data)
    
    # 3. Check all properties that might contain openings
    for prop_name, prop_value in wall_obj.__dict__.items():
        # Skip already processed properties and speckle internal properties
        if (prop_name in ["elements", "inserts", "openings", "insert", "opening"] or
            prop_name.startswith("@") or prop_name == "__dict__"):
            continue
            
        # Process lists of objects
        if isinstance(prop_value, list):
            for item in prop_value:
                if (isinstance(item, Base) and 
                    hasattr(item, "speckle_type") and
                    is_opening_type(item.speckle_type)):
                    opening_data = process_potential_opening(item, wall_obj)
                    if opening_data:
                        openings.append(opening_data)
                    
        # Process individual objects
        elif (isinstance(prop_value, Base) and 
              hasattr(prop_value, "speckle_type") and
              is_opening_type(prop_value.speckle_type)):
            opening_data = process_potential_opening(prop_value, wall_obj)
            if opening_data:
                openings.append(opening_data)
    
    logger.info(f"Found {len(openings)} openings in wall")
    return openings

def process_potential_opening(obj: Base, host_wall: Base) -> Optional[Dict[str, Any]]:
    """
    Process a Speckle object to determine if it's an opening and extract data.
    
    Args:
        obj: Potential opening object
        host_wall: Parent wall object
        
    Returns:
        Opening dictionary or None if not an opening
    """
    try:
        # Determine opening type
        opening_type = "generic"
        if hasattr(obj, "speckle_type"):
            if "Door" in obj.speckle_type:
                opening_type = "door"
            elif "Window" in obj.speckle_type:
                opening_type = "window"
        
        # Initialize opening data
        opening = {
            "type": opening_type,
            "id": getattr(obj, "id", "unknown"),
            "width": 0.0,
            "height": 0.0,
            "sill_height": 0.0,
            "position": {"x": 0, "y": 0, "z": 0}
        }
        
        # Extract dimensions
        if hasattr(obj, "width"):
            opening["width"] = obj.width
        elif hasattr(obj, "Width"):
            opening["width"] = obj.Width
            
        if hasattr(obj, "height"):
            opening["height"] = obj.height
        elif hasattr(obj, "Height"):
            opening["height"] = obj.Height
            
        # Extract position
        if hasattr(obj, "location") and obj.location:
            loc = obj.location
            opening["position"] = {
                "x": getattr(loc, "x", 0),
                "y": getattr(loc, "y", 0),
                "z": getattr(loc, "z", 0)
            }
        elif hasattr(obj, "baseLine") and obj.baseLine:
            # For doors, use the midpoint of the baseline
            if hasattr(obj.baseLine, "start") and hasattr(obj.baseLine, "end"):
                start = obj.baseLine.start
                end = obj.baseLine.end
                opening["position"] = {
                    "x": (getattr(start, "x", 0) + getattr(end, "x", 0)) / 2,
                    "y": (getattr(start, "y", 0) + getattr(end, "y", 0)) / 2,
                    "z": (getattr(start, "z", 0) + getattr(end, "z", 0)) / 2
                }
        
        # Extract sill height for windows
        if opening_type == "window":
            if hasattr(obj, "sillHeight"):
                opening["sill_height"] = obj.sillHeight
            elif hasattr(obj, "SillHeight"):
                opening["sill_height"] = obj.SillHeight
        
        # If we couldn't get essential dimensions, this may not be a valid opening
        if opening["width"] == 0 or opening["height"] == 0:
            # Try to find dimensions from geometry
            if hasattr(obj, "displayValue") and obj.displayValue:
                # TODO: Extract dimensions from displayValue if needed
                logger.warning("Extracting dimensions from displayValue not implemented yet")
                
        return opening
        
    except Exception as e:
        logger.error(f"Error processing potential opening: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def get_parameters(wall_obj: Base) -> Dict[str, Any]:
    """
    Extract parameter values from a Speckle wall object.
    
    Args:
        wall_obj: Speckle wall object
        
    Returns:
        Dictionary of parameter names and values
    """
    parameters = {}
    
    # Try to extract parameters from the wall object
    if hasattr(wall_obj, "parameters") and wall_obj.parameters:
        if isinstance(wall_obj.parameters, dict):
            return wall_obj.parameters
        elif isinstance(wall_obj.parameters, list):
            for param in wall_obj.parameters:
                if hasattr(param, "name") and hasattr(param, "value"):
                    parameters[param.name] = param.value
    
    # Check for Revit elements, these might contain parameters
    for prop_name, prop_value in wall_obj.__dict__.items():
        # Skip already processed properties and speckle internal properties
        if (prop_name in ["elements", "inserts", "openings", "insert", "opening"] or
            prop_name.startswith("@") or prop_name == "__dict__"):
            continue
            
        # Process lists of objects
        if isinstance(prop_value, list):
            for item in prop_value:
                if isinstance(item, Base) and hasattr(item, "parameters"):
                    if isinstance(item.parameters, dict):
                        parameters.update(item.parameters)
                    elif isinstance(item.parameters, list):
                        for param in item.parameters:
                            if hasattr(param, "name") and hasattr(param, "value"):
                                parameters[param.name] = param.value
                                
        # Process Base objects directly
        elif isinstance(prop_value, Base) and hasattr(prop_value, "parameters"):
            if isinstance(prop_value.parameters, dict):
                parameters.update(prop_value.parameters)
            elif isinstance(prop_value.parameters, list):
                for param in prop_value.parameters:
                    if hasattr(param, "name") and hasattr(param, "value"):
                        parameters[param.name] = param.value
    
    return parameters

def find_stream_id_by_name(client, name):
    """
    Find a stream ID by its name.
    
    Args:
        client: Speckle client
        name: Stream name
        
    Returns:
        Stream ID if found, None otherwise
    """
    try:
        # List all streams
        streams = client.stream.list()
        
        if streams:
            # Log all available streams for debugging
            logger.info(f"Available streams ({len(streams)}):")
            for i, stream in enumerate(streams):
                logger.info(f"  {i+1}. '{stream.name}' (ID: {stream.id})")
        
        # Find the stream with matching name
        for stream in streams:
            if stream.name == name:
                logger.info(f"Found stream: {stream.name} (ID: {stream.id})")
                return stream.id
            
            # Also check for partial matches
            elif name.lower() in stream.name.lower():
                logger.info(f"Found stream with partial name match: {stream.name} (ID: {stream.id})")
                
        # If we got here, no exact match was found
        logger.warning(f"No stream found with exact name: {name}")
        
        # Look for alternate streams that might contain model data
        model_streams = []
        for stream in streams:
            # Look for streams that might contain Revit data
            if any(term in stream.name.lower() for term in ["revit", "model", "wall", "building", "project"]):
                model_streams.append(stream)
        
        if model_streams:
            logger.info(f"Found {len(model_streams)} potential model streams:")
            for i, stream in enumerate(model_streams):
                logger.info(f"  {i+1}. '{stream.name}' (ID: {stream.id})")
            
            # Return the first potential model stream
            if len(model_streams) > 0:
                return model_streams[0].id
        
        return None
    except Exception as e:
        logger.error(f"Error finding stream by name: {str(e)}")
        return None

def test_speckle_integration(stream_name: Optional[str] = None):
    """
    Test integration with Speckle.
    
    Args:
        stream_name: Name of the stream to retrieve walls from, or None to use a fixed stream ID
    """
    logger.info("Testing Speckle integration")
    
    try:
        # Read token from file
        with open("speckle_token.txt", "r") as f:
            token = f.read().strip()
            logger.info("Token loaded from file")

        # Initialize Speckle client
        client = SpeckleClient(host="https://speckle.xyz")
        logger.info("Initialized Speckle client")

        # Authenticate using token
        client.authenticate(token=token)
        logger.info("Authenticated with Speckle")

        # Get stream ID from stream name or use default
        stream_id = None
        if stream_name:
            stream_id = find_stream_id_by_name(client, stream_name)
            if not stream_id:
                logger.error(f"Stream with name '{stream_name}' not found")
                raise ValueError(f"Stream with name '{stream_name}' not found")
            logger.info(f"Found stream '{stream_name}' with ID: {stream_id}")
        else:
            # Use a fixed stream ID for testing if no name provided
            stream_id = "TestWalls"  # Replace with your test stream ID
            logger.info(f"Using fixed stream ID: {stream_id}")
        
        # Get walls from Speckle
        walls = get_walls_from_speckle(client, stream_id)
        logger.info(f"Retrieved {len(walls)} walls from Speckle stream {stream_id}")
        
        # Extract wall data for each wall
        wall_data_list = []
        for i, wall in enumerate(walls):
            try:
                wall_data = extract_wall_data_from_speckle(wall)
                wall_data_list.append(wall_data)
                logger.info(f"Processed wall {i+1}/{len(walls)}: {wall_data['wall_name']} - {wall_data['wall_type']}")
            except Exception as e:
                logger.error(f"Error processing wall {i+1}/{len(walls)}: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Write wall data to JSON file
        output_filename = f"speckle_walls_{stream_id}.json"
        
        # Ensure data is JSON serializable
        def json_serializable(obj):
            if isinstance(obj, (int, float, str, bool, type(None))):
                return obj
            elif isinstance(obj, (list, tuple)):
                return [json_serializable(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: json_serializable(value) for key, value in obj.items()}
            else:
                return str(obj)
            
        serializable_wall_data = json_serializable(wall_data_list)
        
        with open(output_filename, "w") as f:
            json.dump(serializable_wall_data, f, indent=2)
        
        logger.info(f"Wall data saved to {output_filename}")
        
        return wall_data_list
    
    except Exception as e:
        logger.error(f"Error in Speckle integration test: {str(e)}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    try:
        # Set up logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Test with stream name
        test_speckle_integration(stream_name="20250122_Summerstone 1550_script test")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
