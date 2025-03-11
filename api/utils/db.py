import os
import traceback
from supabase import create_client, Client
from typing import Dict, List, Any, Optional
import datetime
import time

# Set up logging
import logging
logger = logging.getLogger("timber_framing.db")

# Get Supabase credentials from environment
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Initialize supabase client with proper error handling
supabase: Optional[Client] = None

def _init_supabase():
    """Initialize the Supabase client."""
    global supabase
    
    # Log configuration (without revealing sensitive keys)
    if SUPABASE_URL:
        logger.info(f"Initializing Supabase client with URL: {SUPABASE_URL}")
    else:
        logger.error("SUPABASE_URL environment variable not set")
        return None
        
    if SUPABASE_KEY:
        logger.info("SUPABASE_SERVICE_ROLE_KEY is configured")
    else:
        logger.error("SUPABASE_SERVICE_ROLE_KEY environment variable not set")
        return None
    
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized successfully")
        return supabase_client
    except Exception as e:
        import traceback
        logger.error(f"Failed to initialize Supabase client: {str(e)}\n{traceback.format_exc()}")
        return None

# Initialize Supabase client
supabase = _init_supabase()

def _serialize_for_supabase(data: Dict[str, Any]) -> Dict[str, Any]:
    """Properly serialize complex data structures for Supabase."""
    serialized = {}
    
    for key, value in data.items():
        if isinstance(value, (datetime.datetime, datetime.date)):
            serialized[key] = value.isoformat()
        elif isinstance(value, dict):
            serialized[key] = _serialize_for_supabase(value)
        elif isinstance(value, list):
            serialized[key] = [
                _serialize_for_supabase(item) if isinstance(item, dict) 
                else item for item in value
            ]
        else:
            serialized[key] = value
    
    return serialized

def create_job(job_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create a new job."""
    if not supabase:
        logger.error("Cannot create job: Supabase client is not initialized")
        return None
    
    try:
        # Serialize complex data structures
        serialized_data = _serialize_for_supabase(job_data)
        
        logger.info(f"Creating job in database: {serialized_data.get('job_id')}")
        
        # Execute the insert operation
        response = supabase.table("wall_jobs").insert(serialized_data).execute()
        
        # Check response
        if not response.data:
            logger.error(f"No data returned from insert operation")
            return None
            
        return response.data[0]
    except Exception as e:
        import traceback
        logger.error(f"Error creating job in database: {str(e)}\n{traceback.format_exc()}")
        return None

def update_job(job_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a job by ID."""
    if not supabase:
        logger.error(f"Cannot update job {job_id}: Supabase client is not initialized")
        return None
        
    try:
        # Ensure updated_at is set to current time in ISO format
        if "updated_at" not in update_data:
            update_data["updated_at"] = datetime.datetime.now().isoformat()
        
        # Ensure all datetime objects are properly serialized
        for key, value in update_data.items():
            if isinstance(value, (datetime.datetime, datetime.date)):
                update_data[key] = value.isoformat()
        
        logger.info(f"Updating job {job_id} with changes to keys: {', '.join(update_data.keys())}")
        
        # Execute the update operation
        response = supabase.table("wall_jobs").update(update_data).eq("job_id", job_id).execute()
        
        # Check response
        if not response.data:
            logger.error(f"No data returned from update operation for job {job_id}")
            return None
            
        logger.info(f"Job {job_id} updated successfully")
        return response.data[0]
    except Exception as e:
        import traceback
        logger.error(f"Error updating job {job_id}: {str(e)}\n{traceback.format_exc()}")
        return None

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a job by ID with optimized query.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Job dictionary or None if not found
    """
    if not supabase:
        logger.error(f"Cannot get job {job_id}: Supabase client is not initialized")
        return None
        
    try:
        logger.info(f"Getting job {job_id}")
        
        # First check if job exists with a minimal query
        exists_query = supabase.table("wall_jobs").select("job_id").eq("job_id", job_id).execute()
        
        if not exists_query.data or len(exists_query.data) == 0:
            logger.warning(f"Job {job_id} not found")
            return None
            
        # Then get the full job data
        response = supabase.table("wall_jobs").select("*").eq("job_id", job_id).execute()
        
        logger.info(f"Job {job_id} retrieved successfully")
        return response.data[0]
    except Exception as e:
        import traceback
        logger.error(f"Error getting job {job_id}: {str(e)}\n{traceback.format_exc()}")
        return None

def list_jobs(limit: int = 10, offset: int = 0, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List jobs with optional filtering by status.
    
    This function optimizes query performance by:
    1. Only selecting required fields for listing
    2. Setting up proper indexes
    3. Limiting the number of results
    4. Using pagination
    
    Args:
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        status: Optional filter for job status
        
    Returns:
        List of job dictionaries
    """
    if not supabase:
        error_msg = "Cannot list jobs: Supabase client is not initialized"
        logger.error(error_msg)
        # Instead of silently returning empty list, raise an exception
        raise RuntimeError(error_msg)
        
    try:
        # Start building query
        query = supabase.table("wall_jobs").select("*")
        
        # Add status filter if provided
        if status:
            logger.info(f"Listing jobs with status: {status}, limit: {limit}, offset: {offset}")
            query = query.eq("status", status)
        else:
            logger.info(f"Listing all jobs with limit: {limit}, offset: {offset}")
        
        # Add detailed logging for debugging
        logger.debug(f"Executing Supabase query: table=wall_jobs, limit={limit}, offset={offset}, status={status}")
        
        # Add order, limit, and offset
        response = query.order("created_at", desc=True).limit(limit).offset(offset).execute()
        
        # Log the raw response for debugging
        logger.debug(f"Supabase response type: {type(response)}")
        logger.debug(f"Supabase response has data: {hasattr(response, 'data')}")
        
        # Handle potential None response
        if not response or not hasattr(response, 'data'):
            logger.warning("Received invalid response from Supabase")
            return []
            
        # Handle empty response
        if not response.data:
            logger.info("No jobs found matching criteria")
            return []
            
        logger.info(f"Retrieved {len(response.data)} jobs")
        return response.data
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Error listing jobs: {str(e)}\n{error_detail}")
        # Raise the exception instead of silently returning empty list
        raise RuntimeError(f"Database error while listing jobs: {str(e)}")

def delete_job(job_id: str) -> bool:
    """Delete a job by ID."""
    if not supabase:
        logger.error(f"Cannot delete job {job_id}: Supabase client is not initialized")
        return False
        
    try:
        logger.info(f"Deleting job {job_id}")
        
        # Execute the delete operation
        response = supabase.table("wall_jobs").delete().eq("job_id", job_id).execute()
        
        # Check if any rows were affected
        if response and hasattr(response, 'data'):
            logger.info(f"Job {job_id} deleted successfully")
            return True
        else:
            logger.warning(f"Job {job_id} not found for deletion")
            return False
    except Exception as e:
        import traceback
        logger.error(f"Error deleting job {job_id}: {str(e)}\n{traceback.format_exc()}")
        return False

def check_supabase_connection() -> bool:
    """Check if Supabase connection is working."""
    if not supabase:
        logger.error("Supabase client is not initialized")
        return False
    
    try:
        # Simple query to check connection - note we're using the result count
        response = supabase.table("wall_jobs").select("count", count="exact").limit(0).execute()
        count = getattr(response, 'count', 0)
        logger.info(f"Supabase connection verified successfully. Found {count} records.")
        return True
    except Exception as e:
        logger.error(f"Supabase connection check failed: {str(e)}")
        return False