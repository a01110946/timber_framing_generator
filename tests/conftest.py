# File: tests/conftest.py
import sys
import pytest
import os

@pytest.fixture
def wall_data():
    """Provides wall data for testing."""
    # Import Rhino.Geometry for type annotations
    if is_ci_environment():
        import Rhino.Geometry as rg

        return {
            "width": 10.0,
            "height": 8.0,
            "wall_type": "2x4 EXT",
            "is_exterior_wall": True,
            "wall_base_elevation": 0.0,
            "wall_top_elevation": 8.0,
            "openings": [],
            "cells": [
                {
                    "cell_type": "WBC",
                    "u_start": 0.0,
                    "u_end": 10.0,
                    "v_start": 0.0,
                    "v_end": 8.0,
                    "corner_points": [
                        rg.Point3d(0, 0, 0),
                        rg.Point3d(10, 0, 0),
                        rg.Point3d(10, 8, 0),
                        rg.Point3d(0, 8, 0),
                    ],
                }
            ],
            "base_plane": rg.Plane(),
            "reference_line": rg.Curve(),
        }
    else:
        # For non-CI environments, return a simpler structure
        return {
            "width": 10.0,
            "height": 8.0,
            "wall_type": "2x4 EXT",
            "is_exterior_wall": True,
            "wall_base_elevation": 0.0,
            "wall_top_elevation": 8.0,
            "openings": [],
            "cells": [{"cell_type": "WBC"}],
        }
