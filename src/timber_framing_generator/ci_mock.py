"""
Mock modules for CI testing environment.
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
    
    # Base class for geometry objects
    class MockGeometryBase:
        """Base class for all geometry objects in Rhino."""
        def __init__(self):
            self.IsValid = True
            
        def GetBoundingBox(self, accurate=True):
            bbox = MagicMock()
            bbox.Min = MockPoint3d(0, 0, 0) if 'MockPoint3d' in globals() else None
            bbox.Max = MockPoint3d(10, 10, 10) if 'MockPoint3d' in globals() else None
            bbox.IsValid = True
            return bbox
    
    # Create geometry classes with proper inheritance
    class MockPoint3d(MockGeometryBase):
        def __init__(self, x=0, y=0, z=0):
            super().__init__()
            self.X = x
            self.Y = y
            self.Z = z
            
        def DistanceTo(self, other):
            return 0.0
            
        def Transform(self, transform):
            """Transform this point by a transformation matrix."""
            # In a mock, we can simply return True to indicate success
            return True
            
        def __repr__(self):
            return f"MockPoint3d({self.X}, {self.Y}, {self.Z})"
    
    class MockVector3d(MockGeometryBase):
        def __init__(self, x=0, y=0, z=0):
            super().__init__()
            self.X = x
            self.Y = y
            self.Z = z
            
        def __mul__(self, other):
            if isinstance(other, (int, float)):
                return MockVector3d(self.X * other, self.Y * other, self.Z * other)
            return 0.0
            
        @staticmethod
        def Multiply(vector, scalar):
            return MockVector3d(vector.X * scalar, vector.Y * scalar, vector.Z * scalar)
            
        @staticmethod
        def Add(v1, v2):
            return MockVector3d(v1.X + v2.X, v1.Y + v2.Y, v1.Z + v2.Z)
            
        @staticmethod
        def CrossProduct(v1, v2):
            """Calculate cross product of two vectors."""
            return MockVector3d(1, 0, 0)  # Simplified mock implementation
            
        def Unitize(self):
            return True
            
        def Length(self):
            return 1.0
    
    class MockPlane(MockGeometryBase):
        def __init__(self, origin=None, x_axis=None, y_axis=None):
            super().__init__()
            self.Origin = origin or MockPoint3d()
            self.XAxis = x_axis or MockVector3d(1, 0, 0)
            self.YAxis = y_axis or MockVector3d(0, 1, 0)
            self.ZAxis = MockVector3d(0, 0, 1)
            
        def PointAt(self, u, v, w=0):
            return MockPoint3d(u, v, w)
            
        @staticmethod
        def WorldXY():
            """Return the world XY plane."""
            return MockPlane()
    
    class MockTransform(MockGeometryBase):
        def __init__(self):
            super().__init__()
            self.IsValid = True
            
        @staticmethod
        def PlaneToPlane(source_plane, target_plane):
            """Create a transformation from source to target plane."""
            transform = MockTransform()
            return transform
            
        @staticmethod
        def Identity():
            """Create an identity transformation."""
            return MockTransform()
    
    class MockCurve(MockGeometryBase):
        def __init__(self):
            super().__init__()
            self.PointAtStart = MockPoint3d()
            self.PointAtEnd = MockPoint3d(10, 0, 0)
            
        def DuplicateCurve(self):
            return MockCurve()
            
        def Translate(self, vector):
            return True
            
        def GetLength(self):
            return 10.0
            
        def TangentAt(self, t):
            return MockVector3d(1, 0, 0)
            
        def ClosestPoint(self, point, extend=False):
            """Find the closest point on the curve to a given point."""
            return True, 0.5  # success, parameter
    
    class MockLineCurve(MockCurve):
        def __init__(self, start_point=None, end_point=None):
            super().__init__()
            if start_point:
                self.PointAtStart = start_point
            if end_point:
                self.PointAtEnd = end_point
                
        @staticmethod
        def CreateFromLine(line):
            """Create a curve from a line."""
            return MockLineCurve()
    
    class MockLine(MockGeometryBase):
        def __init__(self, start=None, end=None):
            super().__init__()
            self.From = start or MockPoint3d()
            self.To = end or MockPoint3d(10, 0, 0)
            
        def ToNurbsCurve(self):
            """Convert to a NURBS curve."""
            return MockCurve()
    
    class MockRectangle3d(MockGeometryBase):
        def __init__(self, plane=None, interval1=None, interval2=None):
            super().__init__()
            self.Plane = plane or MockPlane()
            self.Width = 1.0
            self.Height = 1.0
            
        def ToNurbsCurve(self):
            return MockCurve()
    
    class MockInterval:
        def __init__(self, t0=0, t1=1):
            self.T0 = t0
            self.T1 = t1
    
    class MockBrep(MockGeometryBase):
        def __init__(self):
            super().__init__()
            
        @staticmethod
        def CreateFromSweep(rail, shape, closed=True, tolerance=0.01):
            return [MockBrep()]
            
        def CapPlanarHoles(self, tolerance):
            return self
            
        def IsPointInside(self, point, tolerance, strictly_in):
            """Check if a point is inside the Brep."""
            return True
    
    class MockExtrusion(MockGeometryBase):
        def __init__(self):
            super().__init__()
            
        @staticmethod
        def CreateExtrusion(profile, direction):
            return MockExtrusion()
            
        @staticmethod
        def Create(profile, height, cap=True):
            return MockExtrusion()
            
        def ToBrep(self, splitKinkyFaces=True):
            return MockBrep()
    
    # Create mock Geometry module
    class MockGeometry:
        GeometryBase = MockGeometryBase
        Point3d = MockPoint3d
        Vector3d = MockVector3d
        Plane = MockPlane
        Curve = MockCurve
        LineCurve = MockLineCurve
        Line = MockLine
        Rectangle3d = MockRectangle3d
        Interval = MockInterval
        Brep = MockBrep
        Extrusion = MockExtrusion
        Transform = MockTransform
        
        # Additional placeholders
        Surface = type('Surface', (MockGeometryBase,), {
            'CreateExtrusion': staticmethod(lambda curve, direction: MagicMock())
        })
        
        # Common methods
        @staticmethod
        def ToNurbsCurve(curve):
            return MockCurve()
    
    # Create and install the mocks
    rhino_mock = MagicMock()
    rhino_mock.Geometry = MockGeometry
    
    rhinoinside_mock = MagicMock()
    rhinoinside_mock.load = MagicMock()
    
    # Install the mocks
    sys.modules['rhinoinside'] = rhinoinside_mock
    sys.modules['Rhino'] = rhino_mock
    sys.modules['Rhino.Geometry'] = rhino_mock.Geometry
    
    print("Mocks installed for CI environment")