# tests/api/conftest.py
import pytest
from unittest.mock import MagicMock
import sys
import os
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

# Set test environment variables
os.environ["DEBUG"] = "true"
os.environ["API_KEY"] = "dev_key"
os.environ["USE_RHINO"] = "false"  # Use mock data for testing

@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client for testing."""
    mock_client = MagicMock()
    
    # Mock the 'table' method and its chain of calls
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_order = MagicMock()
    mock_limit = MagicMock()
    mock_offset = MagicMock()
    mock_execute = MagicMock()
    
    # Setup the response data
    mock_response = MagicMock()
    mock_response.data = [
        {
            "job_id": "test-job-id",
            "status": "completed",
            "created_at": "2025-03-11T00:00:00Z",
            "updated_at": "2025-03-11T00:01:00Z",
            "wall_data": {"wall_type": "2x4 EXT"},
            "result": {"cells": []},
            "error": None
        }
    ]
    
    # Chain the mock methods
    mock_execute.return_value = mock_response
    mock_offset.return_value = mock_execute
    mock_limit.return_value = mock_offset
    mock_order.return_value = mock_limit
    mock_eq.return_value = mock_order
    mock_select.return_value = mock_eq
    mock_table.return_value = mock_select
    mock_client.table.return_value = mock_table
    
    # Mock insert operation
    mock_insert = MagicMock()
    mock_insert.return_value = mock_execute
    mock_table.insert = mock_insert
    
    # Mock update operation
    mock_update = MagicMock()
    mock_update.return_value = mock_eq
    mock_table.update = mock_update
    
    return mock_client

@pytest.fixture(autouse=True)
def patch_supabase(monkeypatch, mock_supabase):
    """Patch the Supabase client with our mock."""
    monkeypatch.setattr("api.utils.db.supabase", mock_supabase)