import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from api.models.wall_models import WallDataInput, WallAnalysisJob
from typing import Dict, List, Any
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
    wall_jobs[job_id] = job
    
    # Start background task
    background_tasks.add_task(process_wall_analysis, job_id, wall_data)
    
    return job

@router.get("/{job_id}", response_model=WallAnalysisJob)
async def get_wall_analysis(job_id: str):
    """
    Get the status and results of a wall analysis job.
    """
    if job_id not in wall_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return wall_jobs[job_id]

async def process_wall_analysis(job_id: str, wall_data: WallDataInput):
    """Process wall analysis in the background."""
    try:
        # Update job status
        wall_jobs[job_id].status = "processing"
        wall_jobs[job_id].updated_at = datetime.now()
        
        # Check if we should use Rhino or mock data
        use_rhino = os.environ.get("USE_RHINO", "false").lower() == "true"
        
        if use_rhino:
            # Use Rhino for processing
            from api.utils.rhino_integration import process_wall_with_rhino
            success, result = process_wall_with_rhino(wall_data.dict())
            
            if not success:
                raise Exception(result.get("error", "Unknown error in Rhino processing"))
        else:
            # Use mock data for testing
            from api.utils.serialization import create_mock_wall_analysis
            result = create_mock_wall_analysis(wall_data)
        
        # Update job with results
        wall_jobs[job_id].status = "completed"
        wall_jobs[job_id].result = result
        wall_jobs[job_id].updated_at = datetime.now()
        
    except Exception as e:
        # Handle errors
        wall_jobs[job_id].status = "failed"
        wall_jobs[job_id].error = str(e)
        wall_jobs[job_id].updated_at = datetime.now()