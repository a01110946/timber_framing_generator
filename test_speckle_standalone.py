#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Standalone Speckle connection test.

This script tests the basic connectivity to a Speckle stream without requiring
Rhino libraries, to verify we can access the Speckle data before running in Grasshopper.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("speckle_test")

# Import Speckle SDK
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token
from specklepy.objects import Base

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

def inspect_wall_object(wall_obj: Base) -> Dict[str, Any]:
    """
    Inspect a Speckle wall object and return its properties without Rhino dependencies.
    
    Args:
        wall_obj: Speckle wall object
        
    Returns:
        Dictionary with wall properties
    """
    wall_info = {
        "id": getattr(wall_obj, "id", "N/A"),
        "speckle_type": getattr(wall_obj, "speckle_type", "N/A"),
        "properties": {},
        "geometry": {}
    }
    
    # Collect basic properties
    for prop_name, prop_value in wall_obj.__dict__.items():
        # Skip speckle-specific properties and complex objects
        if prop_name.startswith("@") or prop_name == "__dict__":
            continue
            
        # Skip complex objects and collect only simple properties
        if isinstance(prop_value, (str, int, float, bool)):
            wall_info["properties"][prop_name] = prop_value
        elif prop_value is None:
            wall_info["properties"][prop_name] = None
        elif isinstance(prop_value, list) and all(isinstance(x, (str, int, float, bool)) for x in prop_value):
            wall_info["properties"][prop_name] = prop_value
    
    # Specifically look for geometry data we need
    if hasattr(wall_obj, "baseElevation"):
        wall_info["geometry"]["baseElevation"] = wall_obj.baseElevation
    if hasattr(wall_obj, "topElevation"):
        wall_info["geometry"]["topElevation"] = wall_obj.topElevation
    if hasattr(wall_obj, "width"):
        wall_info["geometry"]["width"] = wall_obj.width
    if hasattr(wall_obj, "height"):
        wall_info["geometry"]["height"] = wall_obj.height
    if hasattr(wall_obj, "baseCurve"):
        wall_info["geometry"]["has_baseCurve"] = True
    if hasattr(wall_obj, "location"):
        wall_info["geometry"]["has_location"] = True
    
    # Look for openings
    openings = []
    
    # Function to check if an object is an opening
    def is_potential_opening(obj: Base) -> bool:
        if hasattr(obj, "speckle_type"):
            opening_types = ["Door", "Window", "Opening"]
            return any(ot in obj.speckle_type for ot in opening_types)
        return False
    
    # Look for elements that might be openings
    for prop_name, prop_value in wall_obj.__dict__.items():
        if prop_name.startswith("@") or prop_name == "__dict__":
            continue
            
        # Check in lists
        if isinstance(prop_value, list):
            for item in prop_value:
                if isinstance(item, Base) and is_potential_opening(item):
                    openings.append({
                        "id": getattr(item, "id", "N/A"),
                        "type": getattr(item, "speckle_type", "Unknown"),
                        "properties": {
                            k: v for k, v in item.__dict__.items() 
                            if not k.startswith("@") and k != "__dict__" and isinstance(v, (str, int, float, bool))
                        }
                    })
        # Check direct objects
        elif isinstance(prop_value, Base) and is_potential_opening(prop_value):
            openings.append({
                "id": getattr(prop_value, "id", "N/A"),
                "type": getattr(prop_value, "speckle_type", "Unknown"),
                "properties": {
                    k: v for k, v in prop_value.__dict__.items() 
                    if not k.startswith("@") and k != "__dict__" and isinstance(v, (str, int, float, bool))
                }
            })
    
    wall_info["openings"] = openings
    
    return wall_info

def test_speckle_connection(stream_id: str, token: str, commit_id: str = "latest"):
    """
    Test Speckle connection and explore wall data.
    
    Args:
        stream_id: Speckle stream ID
        token: Speckle API token
        commit_id: Commit ID or "latest"
    """
    try:
        logger.info(f"Testing Speckle connection to stream: {stream_id}")
        
        # Initialize Speckle client
        client = SpeckleClient(host="https://speckle.xyz")
        client.authenticate_with_token(token)
        
        logger.info(f"Authenticated with Speckle server")
        
        # Get account info to verify authentication
        account = get_account_from_token(token)
        logger.info(f"Connected as: {account.name} ({account.email})")
        
        # Get stream details
        stream = client.stream.get(stream_id)
        logger.info(f"Stream info:")
        logger.info(f"  - Name: {stream.name}")
        logger.info(f"  - Description: {stream.description}")
        logger.info(f"  - Created: {stream.createdAt}")
        
        # List commits
        commits = client.commit.list(stream_id, limit=5)
        logger.info(f"Recent commits ({len(commits)}):")
        for commit in commits:
            logger.info(f"  - ID: {commit.id}")
            logger.info(f"    Message: {commit.message}")
            logger.info(f"    Created: {commit.createdAt}")
        
        # Get walls from Speckle
        logger.info(f"Retrieving walls from stream: {stream_id}, commit: {commit_id}")
        walls = get_walls_from_speckle(client, stream_id, commit_id)
        
        if not walls:
            logger.warning("No walls found in the Speckle stream")
            return
        
        logger.info(f"Found {len(walls)} walls in the stream")
        
        # Inspect each wall
        wall_data_list = []
        for i, wall in enumerate(walls):
            logger.info(f"Inspecting wall {i+1}/{len(walls)}")
            try:
                wall_info = inspect_wall_object(wall)
                wall_data_list.append(wall_info)
                
                # Print summary
                logger.info(f"Wall {i+1} info:")
                logger.info(f"  - Type: {wall_info['speckle_type']}")
                logger.info(f"  - Properties: {len(wall_info['properties'])} items")
                logger.info(f"  - Geometry info: {len(wall_info['geometry'])} items")
                logger.info(f"  - Openings: {len(wall_info['openings'])}")
                
            except Exception as e:
                logger.error(f"Error inspecting wall {i+1}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Save results to file
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f"speckle_walls_{stream_id}_info.json")
        with open(output_file, "w") as f:
            json.dump(wall_data_list, f, indent=2, default=str)
        
        logger.info(f"Saved wall info to: {output_file}")
        
    except Exception as e:
        logger.error(f"Error testing Speckle connection: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Use the stream ID provided by the user
    stream_id = "739c86f047"  # Default stream ID
    
    # Default test token - replace with your token for testing
    default_token = None
    
    # Get Speckle token from environment variable, command line, or use default
    token = os.environ.get("SPECKLE_TOKEN")
    
    # Get stream_id and token from command line args if provided
    if len(sys.argv) > 1:
        if sys.argv[1] != "-":  # Use - to skip and use default
            stream_id = sys.argv[1]
            
    if len(sys.argv) > 2:
        token = sys.argv[2]
    
    # If no token found, prompt user
    if not token:
        if default_token:
            token = default_token
            print(f"Using default test token")
        else:
            print("Speckle token is required. You can:")
            print("1. Set SPECKLE_TOKEN environment variable")
            print("2. Pass token as second command line argument: python test_speckle_standalone.py <stream_id> <token>")
            print("3. Add a default_token in the script for testing purposes")
            sys.exit(1)
    
    # Run the test
    test_speckle_connection(stream_id, token)
