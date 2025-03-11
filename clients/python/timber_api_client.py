# clients/python/timber_api_client.py
import requests
import time
import uuid
from typing import Dict, Any, Optional, List, Tuple

class TimberFramingClient:
    """
    Client for the Timber Framing API.
    
    This client provides methods to interact with the Timber Framing API,
    including submitting wall data for analysis, checking job status,
    and retrieving results.
    
    Attributes:
        base_url: Base URL of the API
        api_key: API key for authentication
        headers: Headers to include in all requests
    """
    
    def __init__(self, base_url: str, api_key: str):
        """
        Initialize the client.
        
        Args:
            base_url: Base URL of the API (e.g., "https://api.timber-framing.com")
            api_key: API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}
        
    def check_connection(self) -> Tuple[bool, str]:
        """
        Check if the API is accessible.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                headers=self.headers
            )
            if response.status_code == 200:
                return True, "Connection successful"
            else:
                return False, f"API returned status code {response.status_code}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
            
    def analyze_wall(
        self,
        wall_data: Dict[str, Any],
        polling: bool = True,
        max_polls: int = 60,
        poll_interval: float = 1.0
    ) -> Dict[str, Any]:
        """
        Submit a wall for analysis and optionally wait for results.
        
        Args:
            wall_data: Wall data dictionary with properties and openings
            polling: Whether to poll for results or return immediately
            max_polls: Maximum number of polling attempts
            poll_interval: Seconds between polling attempts
            
        Returns:
            Dictionary with job data or analysis results
            
        Raises:
            requests.HTTPError: If the API request fails
            TimeoutError: If polling times out before job completes
        """
        # Submit the job
        response = requests.post(
            f"{self.base_url}/walls/analyze",
            json=wall_data,
            headers=self.headers
        )
        response.raise_for_status()
        job_data = response.json()
        job_id = job_data["job_id"]
        
        if not polling:
            return job_data
            
        # Poll for results
        for _ in range(max_polls):
            result = self.get_analysis_result(job_id)
            if result["status"] in ["completed", "failed"]:
                return result
            time.sleep(poll_interval)
            
        raise TimeoutError(f"Timed out waiting for job {job_id} to complete")
        
    def get_analysis_result(self, job_id: str) -> Dict[str, Any]:
        """
        Get the results of a wall analysis job.
        
        Args:
            job_id: Job ID returned by analyze_wall
            
        Returns:
            Dictionary with job status and results
            
        Raises:
            requests.HTTPError: If the API request fails
        """
        response = requests.get(
            f"{self.base_url}/walls/job/{job_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
        
    def list_jobs(
        self, 
        limit: int = 10, 
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List wall analysis jobs.
        
        Args:
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            status: Optional filter for job status
            
        Returns:
            List of job dictionaries
            
        Raises:
            requests.HTTPError: If the API request fails
        """
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
            
        response = requests.get(
            f"{self.base_url}/walls/",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()