import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header
from fastapi.responses import JSONResponse
from api.models.wall_models import WallDataInput, WallAnalysisJob
from api.utils.db import create_job, update_job, get_job, list_jobs, supabase
from api.utils.serialization import create_mock_wall_analysis
from typing import Dict, List, Any, Optional
import uuid
from datetime import datetime
import traceback

# Set up logging
import logging
logger = logging.getLogger("timber_framing.api")

router = APIRouter()

@router.post("/analyze", response_model=WallAnalysisJob)
async def analyze_wall(
    wall_data: WallDataInput,
    background_tasks: BackgroundTasks
):
    """
    Submit a wall for analysis.
    
    This endpoint accepts wall data and initiates the analysis process.
    The analysis runs asynchronously, and the results can be retrieved
    using the returned job_id.
    """
    logger.info("*** WALL ANALYSIS ENDPOINT CALLED ***")
    try:
        logger.info(f"Received wall analysis request with {len(wall_data.openings)} openings")
        
        # Create job ID
        job_id = str(uuid.uuid4())
        
        # Create job record using Pydantic model
        job = WallAnalysisJob(
            job_id=job_id,
            status="pending",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            wall_data=wall_data
        )
        
        # Convert to dict for Supabase and store job
        logger.info(f"Creating job {job_id} in database")
        job_dict = job.model_dump()
        
        # Add explicit debugging for the conversion
        logger.debug(f"Job dict structure: {type(job_dict)}")
        for key, value in job_dict.items():
            logger.debug(f"Key: {key}, Type: {type(value)}")
        
        db_result = create_job(job_dict)
        
        # Check if database operation succeeded
        if not db_result:
            logger.error(f"Failed to create job record in database for job_id: {job_id}")
            raise HTTPException(
                status_code=500, 
                detail="Failed to create analysis job in database"
            )
            
        logger.info(f"Successfully created job in database: {job_id}")
        
        # Start background task with job_id and wall_data
        background_tasks.add_task(process_wall_analysis, job_id, wall_data)
        logger.info(f"Started background analysis task for job_id: {job_id}")
        
        return job
        
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error in analyze_wall: {str(e)}\n{error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating analysis job: {str(e)}"
        )

# Test database connection
@router.get("/test-database", response_model=Dict[str, str])
async def test_database():
    """Simple test for database endpoint routing."""
    logger.info("Simple test-database endpoint called")
    return {"status": "test-database endpoint accessed successfully"}

@router.get("/api-test", response_model=Dict[str, str])
async def api_test():
    """Simple test endpoint that doesn't use the database."""
    return {"status": "success", "message": "API is working correctly"}

@router.get("/open-test", include_in_schema=True)
async def open_test():
    """Test endpoint with no authentication required."""
    logger.info("Open test endpoint called")
    return {"status": "success", "message": "This endpoint doesn't require authentication"}

@router.get("/", response_model=List[WallAnalysisJob])
async def list_wall_analyses(
    limit: int = 10, 
    offset: int = 0,
    status: Optional[str] = None
):
    """List wall analysis jobs."""
    logger.info(f"*** GET ENDPOINT CALLED ***")
    try:
        logger.info(f"Listing jobs: limit={limit}, offset={offset}, status={status}")
        jobs = list_jobs(limit, offset, status)
        logger.info(f"Retrieved {len(jobs)} jobs")
        return jobs
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error listing jobs: {str(e)}\n{error_detail}")
        raise HTTPException(status_code=500, detail=f"Error listing jobs: {str(e)}")

async def process_wall_analysis(job_id: str, wall_data: WallDataInput):
    """Process wall analysis in the background."""
    try:
        logger.info(f"Processing wall analysis for job {job_id}")
        
        # Update job status
        update_result = update_job(job_id, {"status": "processing"})
        if not update_result:
            logger.error(f"Failed to update job status to 'processing' for job {job_id}")
        
        # For MVP - just use mock data
        logger.info(f"Creating mock analysis result for job {job_id}")
        result = create_mock_wall_analysis(wall_data)
        
        # Update job with results
        logger.info(f"Updating job {job_id} with analysis results")
        update_result = update_job(job_id, {
            "status": "completed",
            "result": result
        })
        
        if update_result:
            logger.info(f"Job {job_id} completed successfully")
        else:
            logger.error(f"Failed to update job status to 'completed' for job {job_id}")
        
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error processing job {job_id}: {str(e)}\n{error_detail}")
        
        try:
            # Handle errors - attempt to update job status
            update_job(job_id, {
                "status": "failed",
                "error": str(e)
            })
        except Exception as update_error:
            logger.error(f"Failed to update error status for job {job_id}: {str(update_error)}")

# Explicitly add type constraint for job_id route
@router.get("/job/{job_id}", response_model=WallAnalysisJob)  # Note the /job/ prefix
async def get_wall_analysis(job_id: str):
    """Get the status and results of a wall analysis job."""
    try:
        logger.info(f"Retrieving job: {job_id}")
        job_data = get_job(job_id)
        
        if not job_data:
            logger.warning(f"Job not found: {job_id}")
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.info(f"Successfully retrieved job: {job_id}")
        return job_data
        
    except HTTPException:
        raise
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error retrieving job {job_id}: {str(e)}\n{error_detail}")
        raise HTTPException(status_code=500, detail=f"Error retrieving job: {str(e)}")