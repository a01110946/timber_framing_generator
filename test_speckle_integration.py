#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for Speckle integration.

This script tests the Speckle integration for the Timber Framing Generator
by connecting to a Speckle stream, extracting wall data, and printing the results.
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional
import logging

# Add src directory to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("speckle_test")

# Import Speckle functions - direct import from path
try:
    from timber_framing_generator.wall_data.speckle_data_extractor import (
        get_walls_from_speckle,
        extract_wall_data_from_speckle
    )
    logger.info("Successfully imported Speckle functions")
except ImportError as e:
    logger.error(f"Import error: {str(e)}")
    # Try direct import as fallback
    sys.path.insert(0, os.path.join(project_root, "src", "timber_framing_generator", "wall_data"))
    try:
        from speckle_data_extractor import get_walls_from_speckle, extract_wall_data_from_speckle
        logger.info("Successfully imported Speckle functions using direct path")
    except ImportError as e2:
        logger.error(f"Second import error: {str(e2)}")
        raise

# Import Speckle SDK
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token

def test_speckle_integration(stream_id: str, token: str, commit_id: str = "latest"):
    """
    Test Speckle integration by extracting wall data from a stream.
    
    Args:
        stream_id: Speckle stream ID
        token: Speckle API token
        commit_id: Commit ID or "latest"
    """
    try:
        logger.info(f"Testing Speckle integration with stream: {stream_id}")
        
        # Initialize Speckle client
        client = SpeckleClient(host="https://speckle.xyz")
        client.authenticate_with_token(token)
        
        logger.info(f"Authenticated with Speckle server")
        
        # Get account info to verify authentication
        account = get_account_from_token(token)
        logger.info(f"Connected as: {account.name} ({account.email})")
        
        # Get walls from Speckle
        logger.info(f"Retrieving walls from stream: {stream_id}, commit: {commit_id}")
        walls = get_walls_from_speckle(client, stream_id, commit_id)
        
        if not walls:
            logger.warning("No walls found in the Speckle stream")
            return
        
        logger.info(f"Found {len(walls)} walls in the stream")
        
        # Extract data from each wall
        wall_data_list = []
        for i, wall in enumerate(walls):
            logger.info(f"Processing wall {i+1}/{len(walls)}")
            try:
                # Print basic wall information for debugging
                logger.info(f"Wall ID: {getattr(wall, 'id', 'N/A')}")
                logger.info(f"Wall Type: {getattr(wall, 'speckle_type', 'N/A')}")
                
                # Extract detailed wall data
                wall_data = extract_wall_data_from_speckle(wall)
                
                # Add to list
                wall_data_list.append(wall_data)
                
                # Print summary of extracted data
                logger.info(f"Wall {i+1} data extracted:")
                logger.info(f"  - Base elevation: {wall_data.get('base_elevation', 'N/A')}")
                logger.info(f"  - Top elevation: {wall_data.get('top_elevation', 'N/A')}")
                logger.info(f"  - Wall thickness: {wall_data.get('wall_thickness', 'N/A')}")
                logger.info(f"  - Openings: {len(wall_data.get('openings', []))}")
                
            except Exception as e:
                logger.error(f"Error processing wall {i+1}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Save wall data to JSON file for inspection
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f"speckle_walls_{stream_id}.json")
        with open(output_file, "w") as f:
            json.dump(wall_data_list, f, indent=2, default=str)
        
        logger.info(f"Saved wall data to: {output_file}")
        logger.info(f"Successfully processed {len(wall_data_list)} walls")
        
    except Exception as e:
        logger.error(f"Error in Speckle integration test: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Get Speckle token from environment variable or prompt user
    token = os.environ.get("SPECKLE_TOKEN")
    if not token:
        token = input("Enter your Speckle API token: ")
    
    # Use the stream ID provided by the user
    stream_id = "739c86f047"  # Default stream ID
    
    # You can also override the stream ID from command line
    if len(sys.argv) > 1:
        stream_id = sys.argv[1]
    
    # Run the test
    test_speckle_integration(stream_id, token)
