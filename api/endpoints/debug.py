from fastapi import APIRouter, Depends
from typing import Dict, Any, List
import traceback
from api.utils.auth import get_api_key
from api.utils.db import supabase

debug_router = APIRouter()

@debug_router.get("/db-test")
async def test_database_connection(auth=Depends(get_api_key)):
    """Test the database connection with detailed output."""
    try:
        # Try a very simple query first
        response = supabase.table("wall_jobs").select("count", count="exact").limit(0).execute()
        
        # Check if we can get the count
        count = getattr(response, "count", None)
        
        # Try a more complex query
        sample_response = supabase.table("wall_jobs").select("*").limit(1).execute()
        
        # Attempt to get the data
        sample_data = []
        if hasattr(sample_response, "data") and sample_response.data:
            # Remove potentially large fields
            sample = sample_response.data[0].copy()
            if "wall_data" in sample:
                sample["wall_data"] = "DATA_PRESENT"
            if "result" in sample:
                sample["result"] = "DATA_PRESENT"
            sample_data = [sample]
        
        return {
            "connection": "success",
            "record_count": count,
            "sample_query_success": bool(hasattr(sample_response, "data")),
            "sample_data": sample_data,
            "supabase_client_initialized": supabase is not None
        }
    except Exception as e:
        return {
            "connection": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }