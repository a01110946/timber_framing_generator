#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script: main.py
Location: src/timber_framing_generator/main.py
Author: [Your Name]
Date Created: 2025-03-16

Description:
    Main entry point for the Timber Framing Generator using Speckle integration.
    This script connects to Speckle, retrieves wall data, processes it through
    the timber framing generator, and sends the results back to Speckle.

Usage:
    python -m timber_framing_generator.main --stream <stream_id> --token <speckle_token>
    
Dependencies:
    - specklepy
    - rhino3dm
    - timber_framing_generator package
"""

import argparse
import os
import sys
from typing import List, Dict, Any

from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token

from timber_framing_generator.wall_data.speckle_data_extractor import (
    get_walls_from_speckle,
    extract_wall_data_from_speckle,
    send_framing_to_speckle
)
from timber_framing_generator.framing_elements.framing_generator import FramingGenerator


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Timber Framing Generator with Speckle integration"
    )
    
    # Speckle connection parameters
    parser.add_argument(
        "--stream", 
        required=True,
        help="Speckle stream ID containing the Revit model"
    )
    parser.add_argument(
        "--token", 
        help="Speckle authentication token (or set SPECKLE_TOKEN env variable)"
    )
    parser.add_argument(
        "--host", 
        default="https://speckle.xyz",
        help="Speckle server URL (default: https://speckle.xyz)"
    )
    parser.add_argument(
        "--commit", 
        default="latest",
        help="Specific commit ID to use (default: latest)"
    )
    
    # Output options
    parser.add_argument(
        "--output-branch", 
        default="timber-framing",
        help="Branch name for output (default: timber-framing)"
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save local output files (optional)"
    )
    
    # Processing options
    parser.add_argument(
        "--config", 
        help="Path to configuration file for framing parameters"
    )
    parser.add_argument(
        "--debug", 
        action="store_true",
        help="Enable debug output"
    )
    
    return parser.parse_args()


def setup_speckle_client(args):
    """Set up and authenticate the Speckle client."""
    # Get token from args or environment
    token = args.token or os.environ.get("SPECKLE_TOKEN")
    
    if not token:
        print("Error: Speckle token required. Provide with --token or set SPECKLE_TOKEN environment variable.")
        sys.exit(1)
    
    # Initialize client
    client = SpeckleClient(host=args.host)
    
    try:
        account = get_account_from_token(token, args.host)
        client.authenticate_with_token(token)
        print(f"✓ Connected to Speckle server as {account.email}")
        return client
    except Exception as e:
        print(f"Error connecting to Speckle: {str(e)}")
        sys.exit(1)


def process_walls(client, args):
    """Process walls from Speckle stream."""
    try:
        # Get walls from Speckle
        print(f"Retrieving walls from stream {args.stream}...")
        walls = get_walls_from_speckle(client, args.stream, args.commit)
        print(f"Found {len(walls)} walls")
        
        all_framing_results = {}
        
        # Process each wall
        for i, wall in enumerate(walls):
            print(f"\nProcessing wall {i+1}/{len(walls)}")
            
            # Extract wall data
            wall_data = extract_wall_data_from_speckle(wall)
            
            # Generate timber framing
            print(f"Generating timber framing for {wall_data.get('wall_type', 'wall')}")
            generator = FramingGenerator(
                wall_data=wall_data,
                framing_config={
                    "representation_type": "schematic",
                    "bottom_plate_layers": 1,
                    "top_plate_layers": 2
                }
            )
            
            framing_result = generator.generate_framing()
            all_framing_results[f"wall_{i}"] = framing_result
            
            # Write results to Speckle
            print(f"Sending framing elements to Speckle stream {args.stream}, branch {args.output_branch}")
            commit_id = send_framing_to_speckle(
                client,
                args.stream,
                args.output_branch,
                framing_result,
                wall_data,
                f"Timber framing for wall {i+1}"
            )
            print(f"✓ Committed to Speckle: {commit_id}")
            
            # Save local output if requested
            if args.output_dir:
                # Code to save local output
                pass
        
        print("\n✓ All walls processed successfully")
        print(f"View results at: {args.host}/streams/{args.stream}/branches/{args.output_branch}")
        
        return all_framing_results
        
    except Exception as e:
        print(f"Error processing walls: {str(e)}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)


def main():
    """Main entry point for the application."""
    print("\n=== Timber Framing Generator with Speckle ===\n")
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up Speckle client
    client = setup_speckle_client(args)
    
    # Process walls and generate framing
    results = process_walls(client, args)
    
    print("\n=== Processing complete ===\n")


if __name__ == "__main__":
    main()