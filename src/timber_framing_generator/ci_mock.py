"""
Mock modules for CI testing environment.

This module provides mock implementations of Rhino and related modules
to allow tests to run in CI environments where the actual dependencies
are not available.
"""

import sys
import os
from unittest.mock import MagicMock

# Function to determine if we're in CI
def is_ci_environment():
    return (
        'CI' in os.environ or 
        'GITHUB_ACTIONS' in os.environ or
        'GITHUB_WORKFLOW' in os.environ
    )

# Only apply mocks if in CI environment
if is_ci_environment():
    print("CI environment detected - applying Rhino/Inside mocks")
    
    # Create basic mock classes
    class MockPoint3d:
        def __init__(self, x=0, y=0, z=0):
            self.X = x
            self.Y = y
            self.Z = z
            
        def DistanceTo(self, other):
            return 0.0
    
    class MockVector3d:
        def __init__(self, x=0, y=0, z=0):
            self.X = x
            self.Y = y
            self.Z = z
            
        @staticmethod
        def Multiply(vector, scalar):
            return MockVector3d(vector.X * scalar, vector.Y * scalar, vector.Z * scalar)
            
        @staticmethod
        def Add(v1, v2):
            return MockVector3d(v1.X + v2.X, v1.Y + v2.Y, v1.Z + v2.Z)
    
    class MockPlane:
        def __init__(self, origin=None, x_axis=None, y_axis=None):
            self.Origin = origin or MockPoint3d()
            self.XAxis = x_axis or MockVector3d(1, 0, 0)
            self.YAxis = y_axis or MockVector3d(0, 1, 0)
            self.ZAxis = MockVector3d(0, 0, 1)
            
        def PointAt(self, u, v, w=0):
            return MockPoint3d(u, v, w)
    
    class MockCurve:
        def DuplicateCurve(self):
            return self
            
        def Translate(self, vector):
            return True
            
        def GetLength(self):
            return 10.0
    
    # Create mock Geometry module
    class MockGeometry:
        Point3d = MockPoint3d
        Vector3d = MockVector3d
        Plane = MockPlane
        Curve = MockCurve
        LineCurve = type('LineCurve', (MockCurve,), {})
        Rectangle3d = type('Rectangle3d', (), {'ToNurbsCurve': lambda self: MockCurve()})
        Extrusion = type('Extrusion', (), {
            'CreateExtrusion': staticmethod(lambda *args: MagicMock()),
            'ToBrep': lambda self: MagicMock(),
            'IsValid': True
        })
    
    # Create and install the mocks
    rhino_mock = MagicMock()
    rhino_mock.Geometry = MockGeometry
    
    rhinoinside_mock = MagicMock()
    
    # Install the mocks
    sys.modules['rhinoinside'] = rhinoinside_mock
    sys.modules['Rhino'] = rhino_mock
    sys.modules['Rhino.Geometry'] = rhino_mock.Geometry
    
    print("Mocks installed for CI environment")