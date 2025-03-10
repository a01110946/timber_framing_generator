# api/utils/db.py
import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_job(job_id):
    """Get a job by ID."""
    response = supabase.table("wall_jobs").select("*").eq("job_id", job_id).execute()
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None

def list_jobs(limit=10, offset=0, status=None):
    """List jobs with optional filtering by status."""
    query = supabase.table("wall_jobs").select("*")
    if status:
        query = query.eq("status", status)
    
    response = query.order("created_at", desc=True).limit(limit).offset(offset).execute()
    return response.data

def create_job(job_data):
    """Create a new job."""
    response = supabase.table("wall_jobs").insert(job_data).execute()
    return response.data[0] if response.data else None

def update_job(job_id, update_data):
    """Update a job by ID."""
    # Ensure updated_at is set to current time
    update_data["updated_at"] = "now()"  # This uses PostgreSQL's now() function
    response = supabase.table("wall_jobs").update(update_data).eq("job_id", job_id).execute()
    return response.data[0] if response.data else None

def delete_job(job_id):
    """Delete a job by ID."""
    supabase.table("wall_jobs").delete().eq("job_id", job_id).execute()
    return True# Force update
