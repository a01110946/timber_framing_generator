# tests/api/test_walls.py
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import uuid
import os
import json

# Import your application
from api.main import app
from api.models.wall_models import WallDataInput, WallAnalysisJob

# Create test client
client = TestClient(app)

# Test API key
TEST_API_KEY = "dev_key"

@pytest.fixture
def api_headers():
    """Fixture for API headers with authentication."""
    return {"X-API-Key": TEST_API_KEY}

@pytest.fixture
def sample_wall_data():
    """Fixture for sample wall data."""
    return {
        "wall_type": "2x4 EXT",
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 8.0,
        "wall_length": 10.0,
        "wall_height": 8.0,
        "is_exterior_wall": True,
        "openings": [
            {
                "opening_type": "window",
                "start_u_coordinate": 3.0,
                "rough_width": 2.0,
                "rough_height": 3.0,
                "base_elevation_relative_to_wall_base": 3.0
            }
        ]
    }

@pytest.fixture
def test_auth_required(sample_wall_data):
    """Test that authentication is required for protected endpoints."""
    # Try without API key
    response = client.post("/walls/analyze", json=sample_wall_data)
    assert response.status_code == 401
    
    # Try with invalid API key
    response = client.post("/walls/analyze", json=sample_wall_data, 
                          headers={"X-API-Key": "invalid_key"})
    assert response.status_code == 401

def test_wall_analysis_submission(api_headers, sample_wall_data):
    """Test submitting a wall for analysis."""
    response = client.post("/walls/analyze", json=sample_wall_data, headers=api_headers)
    assert response.status_code == 200
    
    # Check response structure
    job_data = response.json()
    assert "job_id" in job_data
    assert job_data["status"] in ["pending", "processing"]
    assert "created_at" in job_data
    assert "updated_at" in job_data
    
    # Save job ID for following test
    job_id = job_data["job_id"]
    
    # Wait a moment for processing
    import time
    time.sleep(2)
    
    # Get job results
    response = client.get(f"/walls/job/{job_id}", headers=api_headers)
    assert response.status_code == 200
    
    # Check job result structure
    job_result = response.json()
    assert job_result["job_id"] == job_id
    assert job_result["status"] in ["pending", "processing", "completed", "failed"]
    
    # If completed, check result structure
    if job_result["status"] == "completed":
        assert "result" in job_result
        result = job_result["result"]
        assert "cells" in result
        assert "base_plane" in result

def test_validation_errors(api_headers):
    """Test input validation for wall data."""
    # Test with invalid wall height (negative)
    invalid_data = {
        "wall_type": "2x4 EXT",
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 8.0,
        "wall_length": 10.0,
        "wall_height": -1.0,  # Invalid
        "is_exterior_wall": True,
        "openings": []
    }
    
    response = client.post("/walls/analyze", json=invalid_data, headers=api_headers)
    assert response.status_code == 422  # Validation error
    
    # Test with opening extending beyond wall
    invalid_data = {
        "wall_type": "2x4 EXT",
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 8.0,
        "wall_length": 10.0,
        "wall_height": 8.0,
        "is_exterior_wall": True,
        "openings": [
            {
                "opening_type": "window",
                "start_u_coordinate": 8.0,
                "rough_width": 3.0,  # Makes it extend beyond wall
                "rough_height": 3.0,
                "base_elevation_relative_to_wall_base": 3.0
            }
        ]
    }
    
    response = client.post("/walls/analyze", json=invalid_data, headers=api_headers)
    assert response.status_code == 422  # Validation error

def test_nonexistent_job(api_headers):
    """Test retrieving a job that doesn't exist."""
    random_id = str(uuid.uuid4())
    response = client.get(f"/walls/job/{random_id}", headers=api_headers)
    assert response.status_code == 404
    
    # Test with invalid UUID format
    response = client.get("/walls/job/not-a-uuid", headers=api_headers)
    assert response.status_code == 400  # Bad request

def test_list_jobs(api_headers):
    """Test listing jobs with pagination and filtering."""
    response = client.get("/walls/", headers=api_headers)
    assert response.status_code == 200
    
    # Result should be a list
    jobs = response.json()
    assert isinstance(jobs, list)
    
    # Test with limit parameter
    response = client.get("/walls/?limit=5", headers=api_headers)
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) <= 5
    
    # Test with status filter
    response = client.get("/walls/?status=completed", headers=api_headers)
    assert response.status_code == 200
    jobs = response.json()
    
    # All returned jobs should have the specified status
    for job in jobs:
        assert job["status"] == "completed"

@pytest.fixture
def basic_wall_data():
    """Minimal wall data that passes validation."""
    return {
        "wall_type": "2x4 EXT",
        "wall_base_elevation": 0.0,
        "wall_top_elevation": 8.0,
        "wall_length": 10.0,
        "wall_height": 8.0,
        "is_exterior_wall": True
    }

def test_auth_required(basic_wall_data):
    """Test that authentication is required for protected endpoints."""
    # Try without API key - pass valid data to avoid validation errors
    response = client.post("/walls/analyze", json=basic_wall_data)
    assert response.status_code == 401