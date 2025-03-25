"""
Speckle Integration Endpoints for the Timber Framing Generator API.

This module provides endpoints for interacting with the Speckle platform
to extract wall data and process it for timber framing generation.
"""

from typing import Dict, List, Any, Optional, Union
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import logging
import traceback
import uuid
from datetime import datetime
import os

# Import Speckle SDK
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token

# Import Speckle extractor
from timber_framing_generator.wall_data.speckle_data_extractor import (
    get_walls_from_speckle, 
    extract_wall_data_from_speckle
)

# Import models and utilities
from api.models.wall_models import WallAnalysisJob
from api.utils.db import create_job, update_job, get_job, list_jobs

# Set up logging
logger = logging.getLogger("timber_framing.api.speckle")

# Create router
router = APIRouter()

# Models for Speckle requests
class SpeckleStreamRequest(BaseModel):
    """Request model for Speckle stream analysis."""
    
    stream_id: str = Field(..., description="Speckle stream ID")
    commit_id: Optional[str] = Field("latest", description="Commit ID (default: latest)")
    token: str = Field(..., description="Speckle API token for authentication")
    branch_name: Optional[str] = Field(None, description="Optional branch name for results")
    
    class Config:
        schema_extra = {
            "example": {
                "stream_id": "739c86f047",
                "commit_id": "latest",
                "token": "your-speckle-token",
                "branch_name": "timber-framing-results"
            }
        }

class SpeckleJobResponse(BaseModel):
    """Response model for Speckle job creation."""
    
    job_id: str = Field(..., description="Job ID for tracking analysis")
    status: str = Field(..., description="Job status (pending, processing, completed, failed)")
    message: str = Field(..., description="Informational message")
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "message": "Speckle wall analysis job created successfully"
            }
        }

@router.post("/analyze", response_model=SpeckleJobResponse)
async def analyze_speckle_stream(
    request: SpeckleStreamRequest,
    background_tasks: BackgroundTasks
):
    """
    Extract and analyze walls from a Speckle stream.
    
    This endpoint connects to Speckle, extracts wall data, and processes it
    for timber framing generation. The analysis runs asynchronously, and
    the results can be retrieved using the returned job_id.
    
    Args:
        request: SpeckleStreamRequest with stream_id, commit_id, and token
        background_tasks: BackgroundTasks for async processing
        
    Returns:
        SpeckleJobResponse with job_id and status
    """
    try:
        logger.info(f"Received Speckle analysis request for stream: {request.stream_id}")
        
        # Create job ID
        job_id = str(uuid.uuid4())
        
        # Create initial job record
        job = WallAnalysisJob(
            job_id=job_id,
            status="pending",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            input_source="speckle",
            input_details={
                "stream_id": request.stream_id,
                "commit_id": request.commit_id,
                "branch_name": request.branch_name
            }
        )
        
        # Store job in database
        db_result = create_job(job.model_dump())
        if not db_result:
            logger.error(f"Failed to create job record in database for job_id: {job_id}")
            raise HTTPException(
                status_code=500,
                detail="Failed to create Speckle analysis job in database"
            )
        
        # Start background task to process Speckle data
        background_tasks.add_task(
            process_speckle_walls,
            job_id=job_id,
            stream_id=request.stream_id,
            commit_id=request.commit_id,
            token=request.token,
            branch_name=request.branch_name
        )
        
        logger.info(f"Started background Speckle analysis task for job_id: {job_id}")
        
        return SpeckleJobResponse(
            job_id=job_id,
            status="pending",
            message="Speckle wall analysis job created successfully"
        )
        
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error in analyze_speckle_stream: {str(e)}\n{error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating Speckle analysis job: {str(e)}"
        )

async def process_speckle_walls(
    job_id: str,
    stream_id: str,
    commit_id: str,
    token: str,
    branch_name: Optional[str] = None
):
    """
    Process walls from a Speckle stream in the background.
    
    Args:
        job_id: Job ID for tracking
        stream_id: Speckle stream ID
        commit_id: Commit ID or "latest"
        token: Speckle API token
        branch_name: Optional branch name for results
    """
    try:
        logger.info(f"Processing Speckle walls for job {job_id}")
        
        # Update job status to processing
        update_job(job_id, {"status": "processing"})
        
        # Initialize Speckle client
        client = SpeckleClient(host="https://speckle.xyz")
        client.authenticate_with_token(token)
        
        # Get walls from Speckle
        logger.info(f"Retrieving walls from Speckle stream {stream_id}, commit {commit_id}")
        speckle_walls = get_walls_from_speckle(client, stream_id, commit_id)
        
        if not speckle_walls:
            raise ValueError(f"No walls found in Speckle stream {stream_id}")
        
        logger.info(f"Found {len(speckle_walls)} walls in Speckle stream")
        
        # Extract wall data for each wall
        wall_data_list = []
        for i, speckle_wall in enumerate(speckle_walls):
            logger.info(f"Processing wall {i+1}/{len(speckle_walls)}")
            try:
                wall_data = extract_wall_data_from_speckle(speckle_wall)
                wall_data_list.append(wall_data)
            except Exception as wall_error:
                logger.warning(f"Error processing wall {i+1}: {str(wall_error)}")
                # Continue with other walls instead of failing completely
        
        # Store results in job
        result = {
            "wall_count": len(wall_data_list),
            "walls": wall_data_list
        }
        
        logger.info(f"Updating job {job_id} with {len(wall_data_list)} processed walls")
        update_job(job_id, {
            "status": "completed",
            "result": result,
            "updated_at": datetime.now()
        })
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error processing Speckle walls for job {job_id}: {str(e)}\n{error_detail}")
        
        # Update job with error
        update_job(job_id, {
            "status": "failed",
            "error": str(e),
            "updated_at": datetime.now()
        })

@router.get("/test", response_model=Dict[str, str])
async def test_speckle_endpoint():
    """Test endpoint for Speckle integration."""
    return {"status": "success", "message": "Speckle integration endpoint is working"}
