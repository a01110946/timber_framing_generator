# tests/conftest.py
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import pytest
from typing import Dict, Any, List

@pytest.fixture
def wall_data() -> Dict[str, Any]:
    """Provides wall data for testing."""
    data: Dict[str, Any] = {
        "width": 10.0,
        "height": 8.0,
        "openings": [],
        "cells": [
            {
                "cell_type": "WBC",
                "data": {},
                "corner_points": [(0, 0, 0), (10, 0, 0), (10, 8, 0), (0, 8, 0)],  # Add corner_points!
            },
        ],
        "wall_type": "stud_wall",
        "is_exterior_wall": True,
        "reference_line": None,
        "base_plane": None,
    }
    return data