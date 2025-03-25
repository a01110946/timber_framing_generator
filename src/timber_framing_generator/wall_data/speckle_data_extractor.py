#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script: speckle_data_extractor.py
Location: src/timber_framing_generator/wall_data/speckle_data_extractor.py
Author: Claude
Date Created: 2025-03-16
Last Modified: 2025-03-16

Description:
    Extracts wall data from a Revit model hosted on Speckle for use in the Timber
    Framing Generator. This module replaces direct Revit access with Speckle,
    allowing for processing without requiring Rhino.Inside.Revit.

Usage:
    from timber_framing_generator.wall_data.speckle_data_extractor import extract_wall_data_from_speckle
    
    # Connect to Speckle stream
    client = SpeckleClient(host="https://speckle.xyz")
    client.authenticate_with_token(token)
    
    # Get walls from Speckle stream
    stream_id = "your-stream-id"
    commit_id = "latest" # or specific commit ID
    speckle_walls = get_walls_from_speckle(client, stream_id, commit_id)
    
    # Extract wall data for each wall
    wall_data_list = []
    for speckle_wall in speckle_walls:
        wall_data = extract_wall_data_from_speckle(speckle_wall)
        wall_data_list.append(wall_data)

Dependencies:
    - specklepy
    - Rhino
    - rhino3dm
"""

from typing import Dict, List, Union, Optional, Any, Tuple
import Rhino.Geometry as rg
import math

# Import Speckle SDK
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token
from specklepy.objects import Base
from specklepy.objects.geometry import Point, Line, Polyline, Curve, Mesh

# Import cell decomposition components
from timber_framing_generator.cell_decomposition.cell_segmentation import decompose_wall_to_cells
from timber_framing_generator.cell_decomposition.cell_types import deconstruct_all_cells

# Define type hint for wall input data
WallInputData = Dict[
    str, Union[rg.Curve, float, bool, List[Dict[str, Union[str, float]]], rg.Plane]
]

def get_walls_from_speckle(
    client: SpeckleClient,
    stream_id: str,
    commit_id: str = "latest"
) -> List[Base]:
    """
    Retrieve wall objects from a Speckle stream.

    Args:
        client: Authenticated Speckle client
        stream_id: ID of the stream containing the Revit model
        commit_id: Specific commit ID or "latest" for most recent

    Returns:
        List of Speckle wall objects
    
    Raises:
        ValueError: If no walls are found or connection fails
    """
    try:
        # Get the commit data
        if commit_id == "latest":
            commits = client.commit.list(stream_id, limit=1)
            if not commits:
                raise ValueError(f"No commits found in stream {stream_id}")
            commit_id = commits[0].id
            
        # Get the commit object
        commit = client.commit.get(stream_id, commit_id)
        if not commit:
            raise ValueError(f"Commit {commit_id} not found in stream {stream_id}")
            
        # Get the object ID from the commit
        obj_id = commit.referencedObject
        
        # Receive the object data
        print(f"Receiving Speckle data from stream {stream_id}, commit {commit_id}")
        base_obj = operations.receive(obj_id, client)
        
        # Find and collect all walls
        walls = []
        
        # This function will recursively traverse the object tree and collect walls
        def collect_walls(obj: Base) -> None:
            # Check if the current object is a wall
            if hasattr(obj, "speckle_type") and "Wall" in obj.speckle_type:
                walls.append(obj)
                return
                
            # Traverse object properties
            for prop_name, prop_value in obj.__dict__.items():
                # Skip speckle-specific properties
                if prop_name.startswith("@") or prop_name == "__dict__":
                    continue
                    
                # Recursively process lists
                if isinstance(prop_value, list):
                    for item in prop_value:
                        if isinstance(item, Base):
                            collect_walls(item)
                # Recursively process Base objects
                elif isinstance(prop_value, Base):
                    collect_walls(prop_value)
        
        # Start traversal from the root object
        collect_walls(base_obj)
        
        print(f"Found {len(walls)} walls in Speckle stream")
        return walls
        
    except Exception as e:
        import traceback
        print(f"Error retrieving walls from Speckle: {str(e)}")
        print(traceback.format_exc())
        raise ValueError(f"Failed to get walls from Speckle: {str(e)}")

def convert_speckle_point_to_rhino(speckle_point: Union[Point, Dict[str, float]]) -> rg.Point3d:
    """
    Convert a Speckle point to a Rhino point.
    
    Args:
        speckle_point: Speckle Point object or dictionary with x, y, z coordinates
        
    Returns:
        Rhino Point3d object
    """
    if isinstance(speckle_point, Point):
        return rg.Point3d(speckle_point.x, speckle_point.y, speckle_point.z)
    elif isinstance(speckle_point, dict):
        return rg.Point3d(speckle_point.get("x", 0), 
                         speckle_point.get("y", 0), 
                         speckle_point.get("z", 0))
    elif hasattr(speckle_point, "x") and hasattr(speckle_point, "y") and hasattr(speckle_point, "z"):
        return rg.Point3d(speckle_point.x, speckle_point.y, speckle_point.z)
    else:
        raise TypeError(f"Unsupported point type: {type(speckle_point)}")

def convert_speckle_curve_to_rhino(speckle_curve: Union[Curve, Line, Polyline]) -> rg.Curve:
    """
    Convert a Speckle curve to a Rhino curve.
    
    Args:
        speckle_curve: Speckle curve object (Curve, Line, or Polyline)
        
    Returns:
        Rhino curve object
    """
    if isinstance(speckle_curve, Line):
        start = convert_speckle_point_to_rhino(speckle_curve.start)
        end = convert_speckle_point_to_rhino(speckle_curve.end)
        return rg.LineCurve(start, end)
    
    elif isinstance(speckle_curve, Polyline):
        points = [convert_speckle_point_to_rhino(pt) for pt in speckle_curve.points]
        if speckle_curve.closed:
            return rg.PolylineCurve(points + [points[0]])
        else:
            return rg.PolylineCurve(points)
    
    elif isinstance(speckle_curve, Curve):
        # Extract control points from the Speckle curve
        if hasattr(speckle_curve, "points") and speckle_curve.points:
            control_points = [convert_speckle_point_to_rhino(pt) for pt in speckle_curve.points]
            
            # Create a Rhino NURBS curve
            # This is a simplified approach - complex curves may need more detailed conversion
            degree = speckle_curve.degree if hasattr(speckle_curve, "degree") else 3
            nurbs_curve = rg.NurbsCurve.Create(False, degree, control_points)
            return nurbs_curve
        else:
            # Fallback to polyline approximation if no control points
            print("Warning: Converting complex curve to polyline approximation")
            points = []
            
            # Check for displayValue which often contains a polyline representation
            if hasattr(speckle_curve, "displayValue") and speckle_curve.displayValue:
                display_obj = speckle_curve.displayValue
                if hasattr(display_obj, "points") and display_obj.points:
                    points = [convert_speckle_point_to_rhino(pt) for pt in display_obj.points]
            
            if points:
                return rg.PolylineCurve(points)
            else:
                raise ValueError("Unable to convert Speckle curve to Rhino - insufficient data")
    
    else:
        raise TypeError(f"Unsupported curve type: {type(speckle_curve)}")

def create_base_plane_from_curve(
    base_curve: rg.Curve, 
    base_elevation: float
) -> rg.Plane:
    """
    Create a base plane for a wall using its base curve and elevation.
    
    Args:
        base_curve: Wall base curve in Rhino geometry
        base_elevation: Base elevation of the wall
        
    Returns:
        Rhino plane representing the wall's base plane
    """
    # Get start point of the curve
    start_point = base_curve.PointAtStart
    
    # Create origin point at base elevation
    origin = rg.Point3d(start_point.X, start_point.Y, base_elevation)
    
    # Get tangent at start for X direction
    tangent = base_curve.TangentAtStart
    if not tangent.Unitize():  # Normalize the vector
        raise ValueError("Unable to get valid tangent from base curve")
    
    # Y axis is vertical
    y_axis = rg.Vector3d(0, 0, 1)
    
    # Z axis is perpendicular to X and Y (into the wall)
    z_axis = rg.Vector3d.CrossProduct(tangent, y_axis)
    if not z_axis.Unitize():
        raise ValueError("Unable to calculate valid Z axis")
    
    # Create the plane
    return rg.Plane(origin, tangent, y_axis)

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
    
    # Strategy 1: Check for elements or openings collection
    if hasattr(wall_obj, "elements") and wall_obj.elements:
        for element in wall_obj.elements:
            opening = process_potential_opening(element, wall_obj)
            if opening:
                openings.append(opening)
    
    # Strategy 2: Check for doors and windows properties
    for prop_name in ["doors", "windows", "openings"]:
        if hasattr(wall_obj, prop_name) and getattr(wall_obj, prop_name):
            elements = getattr(wall_obj, prop_name)
            if isinstance(elements, list):
                for element in elements:
                    opening = process_potential_opening(element, wall_obj)
                    if opening:
                        openings.append(opening)
    
    # Strategy 3: Recursively search all properties for openings
    for prop_name, prop_value in wall_obj.__dict__.items():
        # Skip already processed properties and metadata
        if prop_name in ["elements", "doors", "windows", "openings"] or prop_name.startswith("@"):
            continue
            
        # Process lists
        if isinstance(prop_value, list):
            for item in prop_value:
                if isinstance(item, Base):
                    # Check if this item is a door or window
                    opening = process_potential_opening(item, wall_obj)
                    if opening:
                        openings.append(opening)
        
        # Process single object
        elif isinstance(prop_value, Base):
            opening = process_potential_opening(prop_value, wall_obj)
            if opening:
                openings.append(opening)
    
    print(f"Found {len(openings)} openings in wall")
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
    # Check if this is a door or window based on speckle_type
    if not hasattr(obj, "speckle_type"):
        return None
        
    # Determine opening type
    opening_type = None
    if "Door" in obj.speckle_type:
        opening_type = "door"
    elif "Window" in obj.speckle_type:
        opening_type = "window"
    else:
        return None
    
    print(f"Processing {opening_type} opening")
    
    # Extract position data
    location_point = None
    
    # Try multiple strategies to get position
    if hasattr(obj, "location") and obj.location:
        location_point = obj.location
    elif hasattr(obj, "basePoint") and obj.basePoint:
        location_point = obj.basePoint
    elif hasattr(obj, "insertionPoint") and obj.insertionPoint:
        location_point = obj.insertionPoint
    
    # If we couldn't find a position reference point, try bounding box
    if not location_point and hasattr(obj, "displayValue") and obj.displayValue:
        display_obj = obj.displayValue
        if hasattr(display_obj, "bbox") and display_obj.bbox:
            # Use center of bounding box
            bbox = display_obj.bbox
            min_point = Point(bbox.xMin, bbox.yMin, bbox.zMin)
            max_point = Point(bbox.xMax, bbox.yMax, bbox.zMax)
            # Create a center point
            location_point = Point(
                (min_point.x + max_point.x) / 2,
                (min_point.y + max_point.y) / 2,
                min_point.z  # Use bottom of bounding box for Z
            )
    
    if not location_point:
        print(f"Warning: Could not determine position for {opening_type}")
        return None
    
    # Convert to Rhino point
    location_point_rhino = convert_speckle_point_to_rhino(location_point)
    
    # Extract dimension data - try multiple property names
    rough_width = None
    rough_height = None
    
    # Width
    for width_prop in ["roughWidth", "width", "roughOpeningWidth", "openingWidth"]:
        if hasattr(obj, width_prop) and getattr(obj, width_prop) is not None:
            rough_width = float(getattr(obj, width_prop))
            break
    
    # Height
    for height_prop in ["roughHeight", "height", "roughOpeningHeight", "openingHeight"]:
        if hasattr(obj, height_prop) and getattr(obj, height_prop) is not None:
            rough_height = float(getattr(obj, height_prop))
            break
    
    # Sill height (for windows)
    sill_height = None
    for sill_prop in ["sillHeight", "elevationFromLevel"]:
        if hasattr(obj, sill_prop) and getattr(obj, sill_prop) is not None:
            sill_height = float(getattr(obj, sill_prop))
            break
    
    # Use 0 for doors as default sill height
    if opening_type == "door" and sill_height is None:
        sill_height = 0.0
    
    # If dimensions aren't available directly, try to compute from geometry
    if (rough_width is None or rough_height is None) and hasattr(obj, "displayValue"):
        display_obj = obj.displayValue
        if hasattr(display_obj, "bbox") and display_obj.bbox:
            bbox = display_obj.bbox
            if rough_width is None:
                rough_width = float(bbox.xMax - bbox.xMin)
            if rough_height is None:
                rough_height = float(bbox.zMax - bbox.zMin)
    
    if rough_width is None or rough_height is None:
        print(f"Warning: Could not determine dimensions for {opening_type}")
        return None
    
    # Get wall base curve for positioning
    wall_base_curve = None
    if hasattr(host_wall, "baseCurve") and host_wall.baseCurve:
        try:
            wall_base_curve = convert_speckle_curve_to_rhino(host_wall.baseCurve)
        except Exception as e:
            print(f"Error converting wall base curve: {str(e)}")
    
    if not wall_base_curve:
        print("Warning: Could not get wall base curve for positioning")
        return None
    
    # Project the opening location onto the wall base curve
    success, t = wall_base_curve.ClosestPoint(location_point_rhino)
    if not success:
        print("Warning: Failed to project opening onto wall base curve")
        return None
    
    # Calculate start coordinate (assume opening is centered on location point)
    rough_width_half = rough_width / 2.0
    start_u_coordinate = t - rough_width_half
    
    # Get wall base elevation (will need to be passed separately if not available)
    wall_base_elevation = 0.0
    if hasattr(host_wall, "baseElevation") and host_wall.baseElevation is not None:
        wall_base_elevation = float(host_wall.baseElevation)
    
    # Calculate base elevation relative to wall base
    base_elevation_relative_to_wall_base = sill_height
    if sill_height is None:
        # If sill height is not available, try to calculate from 3D positions
        if location_point_rhino.Z is not None and wall_base_elevation is not None:
            base_elevation_relative_to_wall_base = location_point_rhino.Z - wall_base_elevation
        else:
            print("Warning: Could not determine elevation for opening")
            return None
    
    # Create and return opening data
    opening_data = {
        "opening_type": opening_type,
        "opening_location_point": location_point_rhino,
        "start_u_coordinate": start_u_coordinate,
        "rough_width": rough_width,
        "rough_height": rough_height,
        "base_elevation_relative_to_wall_base": base_elevation_relative_to_wall_base,
    }
    
    print(f"Processed {opening_type} opening: width={rough_width}, height={rough_height}")
    return opening_data

def extract_wall_data_from_speckle(wall_obj: Base) -> WallInputData:
    """
    Extract wall data from a Speckle wall object.
    
    This function replaces extract_wall_data_from_revit, using Speckle
    objects instead of direct Revit API access.
    
    Args:
        wall_obj: Speckle wall object
        
    Returns:
        Dictionary with wall data for timber framing generation
    """
    try:
        print(f"Extracting data from Speckle wall: {getattr(wall_obj, 'id', 'unknown')}")
        
        # 1. Extract wall base curve
        wall_base_curve_rhino = None
        if hasattr(wall_obj, "baseCurve") and wall_obj.baseCurve:
            wall_base_curve_rhino = convert_speckle_curve_to_rhino(wall_obj.baseCurve)
        elif hasattr(wall_obj, "displayValue") and wall_obj.displayValue:
            # Try to extract base curve from display geometry
            display_obj = wall_obj.displayValue
            if hasattr(display_obj, "baseCurve") and display_obj.baseCurve:
                wall_base_curve_rhino = convert_speckle_curve_to_rhino(display_obj.baseCurve)
        
        if not wall_base_curve_rhino:
            raise ValueError("Could not extract wall base curve from Speckle object")
        
        # 2. Get wall base and top elevations
        wall_base_elevation = 0.0
        if hasattr(wall_obj, "baseElevation") and wall_obj.baseElevation is not None:
            wall_base_elevation = float(wall_obj.baseElevation)
        elif hasattr(wall_obj, "baseLevel") and hasattr(wall_obj.baseLevel, "elevation"):
            wall_base_elevation = float(wall_obj.baseLevel.elevation)
        
        wall_top_elevation = None
        if hasattr(wall_obj, "topElevation") and wall_obj.topElevation is not None:
            wall_top_elevation = float(wall_obj.topElevation)
        elif hasattr(wall_obj, "topLevel") and hasattr(wall_obj.topLevel, "elevation"):
            wall_top_elevation = float(wall_obj.topLevel.elevation)
        
        # If top elevation is not directly available, calculate from height
        if wall_top_elevation is None:
            if hasattr(wall_obj, "height") and wall_obj.height is not None:
                wall_height = float(wall_obj.height)
                wall_top_elevation = wall_base_elevation + wall_height
            elif hasattr(wall_obj, "unconnectedHeight") and wall_obj.unconnectedHeight is not None:
                wall_height = float(wall_obj.unconnectedHeight)
                wall_top_elevation = wall_base_elevation + wall_height
            else:
                # Last resort: try to calculate from bounding box
                if hasattr(wall_obj, "displayValue") and hasattr(wall_obj.displayValue, "bbox"):
                    bbox = wall_obj.displayValue.bbox
                    wall_height = float(bbox.zMax - bbox.zMin)
                    wall_top_elevation = wall_base_elevation + wall_height
                else:
                    raise ValueError("Could not determine wall top elevation or height")
        
        # 3. Determine if wall is exterior
        is_exterior_wall = False
        if hasattr(wall_obj, "isExterior") and wall_obj.isExterior is not None:
            is_exterior_wall = bool(wall_obj.isExterior)
        elif hasattr(wall_obj, "function") and wall_obj.function is not None:
            # Revit's function parameter: 1 = Exterior, 2 = Interior
            is_exterior_wall = str(wall_obj.function) == "1" or "exterior" in str(wall_obj.function).lower()
        
        # 4. Get wall type name
        wall_type_name = "Generic"
        if hasattr(wall_obj, "wallType") and wall_obj.wallType is not None:
            if isinstance(wall_obj.wallType, str):
                wall_type_name = wall_obj.wallType
            elif hasattr(wall_obj.wallType, "name"):
                wall_type_name = wall_obj.wallType.name
        elif hasattr(wall_obj, "type") and wall_obj.type is not None:
            if isinstance(wall_obj.type, str):
                wall_type_name = wall_obj.type
            elif hasattr(wall_obj.type, "name"):
                wall_type_name = wall_obj.type.name
        
        # 5. Get openings
        openings_data = find_openings_in_speckle_wall(wall_obj)
        
        # 6. Create base plane
        wall_base_plane = create_base_plane_from_curve(wall_base_curve_rhino, wall_base_elevation)
        
        # 7. Compute wall length and height
        wall_length = wall_base_curve_rhino.GetLength()
        wall_height = wall_top_elevation - wall_base_elevation
        
        # 8. Decompose wall into cells
        cell_data_dict = decompose_wall_to_cells(
            wall_length=wall_length,
            wall_height=wall_height,
            opening_data_list=openings_data,
            base_plane=wall_base_plane,
        )
        cells_list = deconstruct_all_cells(cell_data_dict)
        
        # 9. Build the final wall data dictionary
        wall_input_data_final: WallInputData = {
            "wall_type": wall_type_name,
            "wall_base_curve": wall_base_curve_rhino,
            "wall_length": wall_length,
            "base_plane": wall_base_plane,
            "wall_base_elevation": wall_base_elevation,
            "wall_top_elevation": wall_top_elevation,
            "wall_height": wall_height,
            "is_exterior_wall": is_exterior_wall,
            "openings": openings_data,
            "cells": cells_list,
        }
        
        # Remove speckle-specific properties
        if "base_level" in wall_input_data_final:
            wall_input_data_final.pop("base_level")
        if "top_level" in wall_input_data_final:
            wall_input_data_final.pop("top_level")
        
        print(f"Successfully extracted wall data: length={wall_length}, height={wall_height}")
        return wall_input_data_final
        
    except Exception as e:
        import traceback
        print(f"Error extracting wall data from Speckle: {str(e)}")
        print(traceback.format_exc())
        raise ValueError(f"Failed to extract wall data: {str(e)}")

def send_framing_to_speckle(
    client: SpeckleClient,
    stream_id: str,
    branch_name: str,
    framing_elements: Dict[str, List[Any]],
    wall_data: Dict[str, Any],
    commit_message: str = "Timber framing elements generated"
) -> str:
    """
    Send generated timber framing elements back to Speckle.
    
    Args:
        client: Authenticated Speckle client
        stream_id: Stream ID to send to
        branch_name: Branch name to commit to
        framing_elements: Dictionary of framing elements by type
        wall_data: Original wall data used to generate framing
        commit_message: Commit message
        
    Returns:
        Commit ID of the new commit
    """
    # Create a base object to hold all framing elements
    framing_object = Base(speckle_type="Objects.BuiltElements.Timber.FramingAssembly")
    
    # Add metadata
    framing_object.name = f"Timber Framing - {wall_data.get('wall_type', 'Wall')}"
    framing_object.description = "Generated by Timber Framing Generator"
    
    # Add reference to original wall
    framing_object.sourceWallType = wall_data.get("wall_type")
    framing_object.sourceWallLength = wall_data.get("wall_length")
    framing_object.sourceWallHeight = wall_data.get("wall_height")
    framing_object.isExteriorWall = wall_data.get("is_exterior_wall")
    
    # Convert and add framing elements by category
    for element_type, elements in framing_elements.items():
        # Skip empty categories
        if not elements:
            continue
            
        # Create a list to hold converted elements
        speckle_elements = []
        
        for element in elements:
            # Create a base object for the framing element
            speckle_element = Base(speckle_type=f"Objects.BuiltElements.Timber.{element_type}")
            
            # Add the element to the list
            # Note: Actual conversion would depend on the type of element
            # This is a placeholder - you would need to implement proper conversion
            speckle_elements.append(speckle_element)
        
        # Add the list to the framing object
        setattr(framing_object, element_type.lower(), speckle_elements)
    
    # Send the object to Speckle
    obj_id = operations.send(framing_object, [client.account])
    
    # Create a commit on the specified branch
    commit_id = client.commit.create(
        stream_id=stream_id,
        object_id=obj_id,
        branch_name=branch_name,
        message=commit_message
    )
    
    return commit_id


# Example usage
if __name__ == "__main__":
    # This is a simplified example showing the basic workflow
    
    # 1. Connect to Speckle
    token = "your-speckle-token"
    host = "https://speckle.xyz"  # Or your Speckle server
    
    client = SpeckleClient(host=host)
    account = get_account_from_token(token, host)
    client.authenticate_with_token(token)
    
    # 2. Get walls from a Speckle stream
    stream_id = "your-stream-id"
    commit_id = "latest"  # Or specific commit ID
    
    walls = get_walls_from_speckle(client, stream_id, commit_id)
    
    # 3. Process each wall
    for wall in walls:
        # Extract wall data
        wall_data = extract_wall_data_from_speckle(wall)
        
        # At this point, you would use your existing timber framing generator
        # to process the wall data and generate framing elements
        
        # Example (placeholder):
        # framing_elements = generate_timber_framing(wall_data)
        
        # 4. Send framing elements back to Speckle
        # send_framing_to_speckle(
        #     client, 
        #     stream_id, 
        #     "timber-framing",  # Branch name
        #     framing_elements, 
        #     wall_data
        # )
