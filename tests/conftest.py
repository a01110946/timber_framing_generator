# tests/conftest.py
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import pytest
from unittest.mock import MagicMock
from typing import Dict, Any, List

# Determine if we're running in CI
is_ci = 'CI' in sys.modules or 'GITHUB_ACTIONS' in sys.modules

# Only apply mocks if we're in CI environment
if is_ci:
    print("CI environment detected - applying Rhino mocks")
    
    # Create a basic Point3d mock class
    class MockPoint3d:
        def __init__(self, x=0, y=0, z=0):
            self.X = x
            self.Y = y
            self.Z = z
            
        def DistanceTo(self, other):
            return 0.0
            
        def __repr__(self):
            return f"MockPoint3d({self.X}, {self.Y}, {self.Z})"
    
    # Create a basic Plane mock class
    class MockPlane:
        def __init__(self, origin=None, x_axis=None, y_axis=None):
            self.Origin = origin or MockPoint3d()
            self.XAxis = x_axis or MockVector3d(1, 0, 0)
            self.YAxis = y_axis or MockVector3d(0, 1, 0)
            self.ZAxis = y_axis or MockVector3d(0, 0, 1)
            
        def PointAt(self, u, v, w=0):
            return MockPoint3d(u, v, w)
            
    # Create a basic Vector3d mock class
    class MockVector3d:
        def __init__(self, x=0, y=0, z=0):
            self.X = x
            self.Y = y
            self.Z = z
            
        def __mul__(self, other):
            # Handle vector * scalar
            if isinstance(other, (int, float)):
                return MockVector3d(self.X * other, self.Y * other, self.Z * other)
            return 0.0
            
        @staticmethod
        def Multiply(vector, scalar):
            return MockVector3d(vector.X * scalar, vector.Y * scalar, vector.Z * scalar)
            
        @staticmethod
        def Add(v1, v2):
            return MockVector3d(v1.X + v2.X, v1.Y + v2.Y, v1.Z + v2.Z)
            
        def Unitize(self):
            # Pretend to make this a unit vector
            return True
    
    # Create a basic Curve mock class
    class MockCurve:
        def __init__(self):
            pass
            
        def GetLength(self):
            return 10.0
            
        def PointAtStart(self):
            return MockPoint3d(0, 0, 0)
            
        def PointAtEnd(self):
            return MockPoint3d(10, 0, 0)
            
        def DuplicateCurve(self):
            return MockCurve()
            
        def Translate(self, vector):
            return True
    
    # Create a basic LineCurve mock
    class MockLineCurve(MockCurve):
        def __init__(self, start=None, end=None):
            super().__init__()
            self.PointAtStart = start or MockPoint3d()
            self.PointAtEnd = end or MockPoint3d(10, 0, 0)
    
    # Create a basic Rectangle3d mock
    class MockRectangle3d:
        def __init__(self, plane=None, width=1.0, height=1.0):
            self.Plane = plane or MockPlane()
            self.Width = width
            self.Height = height
            
        def ToNurbsCurve(self):
            return MockCurve()
    
    # Create a basic Brep mock
    class MockBrep:
        @staticmethod
        def CreateFromSweep(rail, shape, closed, tolerance):
            return [MockBrep()]
            
        def CapPlanarHoles(self, tolerance):
            return self
    
    # Create a basic Extrusion mock
    class MockExtrusion:
        @staticmethod
        def CreateExtrusion(profile, direction):
            return MockExtrusion()
            
        @staticmethod
        def Create(profile, height, cap):
            return MockExtrusion()
            
        def ToBrep(self, splitKinkyFaces=True):
            return MockBrep()
            
        @property
        def IsValid(self):
            return True
    
    # Create base Geometry mock module
    class MockGeometry:
        Point3d = MockPoint3d
        Vector3d = MockVector3d
        Plane = MockPlane
        LineCurve = MockLineCurve
        Rectangle3d = MockRectangle3d
        Curve = MockCurve
        Brep = MockBrep
        Extrusion = MockExtrusion
    
    # Create mock modules
    rhinoinside_mock = MagicMock()
    rhino_mock = MagicMock()
    rhino_mock.Geometry = MockGeometry
    
    # Register mocks
    sys.modules['rhinoinside'] = rhinoinside_mock
    sys.modules['Rhino'] = rhino_mock
    sys.modules['Rhino.Geometry'] = rhino_mock.Geometry

# Normal pytest fixtures go here
@pytest.fixture
def wall_data():
    """Provides wall data for testing."""
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
                    MockPoint3d(0, 0, 0) if is_ci else None,
                    MockPoint3d(10, 0, 0) if is_ci else None,
                    MockPoint3d(10, 8, 0) if is_ci else None,
                    MockPoint3d(0, 8, 0) if is_ci else None,
                ]
            }
        ],
        "base_plane": MockPlane() if is_ci else None,
        "reference_line": MockCurve() if is_ci else None,
    }