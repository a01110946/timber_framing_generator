# tests/api/conftest.py
import pytest
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