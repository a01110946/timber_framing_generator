import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from api.models.wall_models import WallDataInput, WallAnalysisJob
from api.utils.db import create_job, update_job, get_job, list_jobs
from typing import Dict, List, Any, Optional
import uuid
from datetime import datetime

router = APIRouter()

# In-memory storage (replace with database in production)
wall_jobs: Dict[str, WallAnalysisJob] = {}

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
    # Create job ID
    job_id = str(uuid.uuid4())
    
    # Create job record
    job = WallAnalysisJob(
        job_id=job_id,
        status="pending",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        wall_data=wall_data
    )
    
    # Store job
    created_job = create_job(job)
    
    # Start background task
    background_tasks.add_task(process_wall_analysis, created_job, wall_data)
    
    return {**created_job, "wall_data": wall_data}

@router.get("/{job_id}", response_model=WallAnalysisJob)
async def get_wall_analysis(job_id: str):
    """
    Get the status and results of a wall analysis job.
    """
    job_data = get_job(job_id)
    
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job_data

@router.get("/", response_model=List[WallAnalysisJob])
async def list_wall_analyses(
    limit: int = 10, 
    offset: int = 0,
    status: Optional[str] = None
):
    """List wall analysis jobs."""
    return list_jobs(limit, offset, status)

async def process_wall_analysis(job_id: str, wall_data: WallDataInput):
    """Process wall analysis in the background."""
    try:
        # Update job status
        update_job(job_id, {"status": "processing"})
        
        # For MVP - just use mock data
        from api.utils.serialization import create_mock_wall_analysis
        result = create_mock_wall_analysis(wall_data)
        
        # Update job with results
        update_job(job_id, {
            "status": "completed",
            "result": result
        })
        
    except Exception as e:
        # Handle errors
        update_job(job_id, {
            "status": "failed",
            "error": str(e)
        })