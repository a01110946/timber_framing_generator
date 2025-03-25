#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
List available Speckle streams and models for the authenticated user.

This script connects to Speckle and lists all streams/models
that the user has access to, supporting both the new Projects/Models API
and the legacy Streams API.
"""

import os
import sys
import logging
from typing import List, Dict, Any, Optional, Union
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("speckle_list")

# Import Speckle SDK
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token

def list_user_streams_and_models(token: str) -> None:
    """
    List all streams and models that the user has access to.
    
    Args:
        token: Speckle API token
    """
    try:
        # Initialize Speckle client
        client = SpeckleClient(host="https://speckle.xyz")
        
        # Authenticate with token
        client.authenticate_with_token(token)
        logger.info("Authenticated with Speckle server")
        
        # Get account info to verify authentication
        account = get_account_from_token(token)
        if hasattr(account, 'name') and account.name:
            logger.info(f"Connected as: {account.name}")
        
        # Results storage
        all_results = {
            "models": [],
            "streams": []
        }
        
        # Try the new Projects/Models API first
        logger.info("\n=== LISTING MODELS (NEW API) ===")
        try:
            projects = client.project.list()
            
            for project in projects:
                logger.info(f"\nProject: {project.name} (ID: {project.id})")
                
                try:
                    # Get models in this project
                    models = client.model.list(project.id)
                    
                    for model in models:
                        logger.info(f"  Model: {model.name} (ID: {model.id})")
                        
                        # Get versions
                        try:
                            versions = client.version.list(model.id)
                            if versions and len(versions) > 0:
                                latest = versions[0]
                                logger.info(f"    Latest version: {latest.message} (ID: {latest.id})")
                                all_results["models"].append({
                                    "project_name": project.name,
                                    "project_id": project.id,
                                    "model_name": model.name,
                                    "model_id": model.id,
                                    "latest_version_id": latest.id,
                                    "latest_version_message": latest.message
                                })
                            else:
                                logger.info(f"    No versions found")
                                all_results["models"].append({
                                    "project_name": project.name,
                                    "project_id": project.id,
                                    "model_name": model.name,
                                    "model_id": model.id
                                })
                        except Exception as ve:
                            logger.info(f"    Could not get versions: {str(ve)}")
                            all_results["models"].append({
                                "project_name": project.name,
                                "project_id": project.id,
                                "model_name": model.name,
                                "model_id": model.id
                            })
                            
                except Exception as me:
                    logger.info(f"  Could not list models for project {project.id}: {str(me)}")
            
        except Exception as pe:
            logger.info(f"Could not list projects: {str(pe)}")
        
        # Try the legacy Streams API
        logger.info("\n=== LISTING STREAMS (LEGACY API) ===")
        try:
            streams = client.stream.list()
            
            for stream in streams:
                logger.info(f"\nStream: {stream.name} (ID: {stream.id})")
                
                try:
                    # Get branches
                    branches = client.branch.list(stream.id)
                    branches_info = []
                    
                    for branch in branches:
                        logger.info(f"  Branch: {branch.name}")
                        
                        # Get commits for this branch
                        try:
                            commits = client.commit.list(stream.id, limit=1, branch=branch.name)
                            if commits and len(commits) > 0:
                                latest = commits[0]
                                logger.info(f"    Latest commit: {latest.message} (ID: {latest.id})")
                                branches_info.append({
                                    "branch_name": branch.name,
                                    "latest_commit_id": latest.id,
                                    "latest_commit_message": latest.message
                                })
                            else:
                                logger.info(f"    No commits found")
                                branches_info.append({
                                    "branch_name": branch.name
                                })
                        except Exception as ce:
                            logger.info(f"    Could not get commits: {str(ce)}")
                            branches_info.append({
                                "branch_name": branch.name
                            })
                    
                    all_results["streams"].append({
                        "stream_name": stream.name,
                        "stream_id": stream.id,
                        "branches": branches_info
                    })
                            
                except Exception as be:
                    logger.info(f"  Could not list branches for stream {stream.id}: {str(be)}")
                    all_results["streams"].append({
                        "stream_name": stream.name,
                        "stream_id": stream.id
                    })
        
        except Exception as se:
            logger.info(f"Could not list streams: {str(se)}")
        
        # Print summary
        logger.info("\n=== SUMMARY ===")
        logger.info(f"Found {len(all_results['models'])} models (new API)")
        logger.info(f"Found {len(all_results['streams'])} streams (legacy API)")
        
        # Save results to file
        with open("speckle_list_results.json", "w") as f:
            json.dump(all_results, f, indent=2)
        logger.info(f"\nDetailed results saved to speckle_list_results.json")
            
    except Exception as e:
        logger.error(f"Error listing streams and models: {str(e)}")

if __name__ == "__main__":
    # Get Speckle token from the same location as your test script
    YOUR_SPECKLE_TOKEN = "2f04135c9d988fd5c263c586fbc03cf2d97621b93a"
    
    # Determine which token to use
    token = YOUR_SPECKLE_TOKEN
    
    # Verify we have a token
    if not token:
        print("No Speckle token provided.")
        sys.exit(1)
    
    # List streams and models
    list_user_streams_and_models(token)
