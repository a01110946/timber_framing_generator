# File: gh-main.py
"""
Main script for timber framing generation within Grasshopper.

This script is designed to be run in Python within the Grasshopper environment.
It integrates with Rhino and Revit to extract wall data, generate framing
elements, and convert the results into serializable objects.

The script handles the following main tasks:
1. Extracting data from selected Revit walls
2. Generating framing elements (studs, plates, headers, etc.)
3. Converting framing results into standardized TimberFramingResults objects

Note: This script requires the Rhino.Inside.Revit environment to function properly.

Usage:
    Place this script in a Python component within a Grasshopper definition.
    Ensure all necessary inputs (e.g., selected walls) are provided to the component.
"""

import sys
import os
import importlib
from typing import Dict, List, Any, Optional, Union, Tuple
import traceback
import tempfile
import os.path

# CRITICAL: Ensure we use RhinoCommon, not Rhino3dmIO
import clr

# STEP 1: Remove rhino3dm from sys.path BEFORE any Rhino imports
# The rhino3dm package provides Rhino.Geometry from Rhino3dmIO, which conflicts with RhinoCommon
_paths_to_remove = []
for _path in sys.path:
    if 'rhino3dm' in _path.lower() or 'site-packages' in _path.lower():
        _paths_to_remove.append(_path)

for _path in _paths_to_remove:
    sys.path.remove(_path)
    print(f"Removed from sys.path: {_path}")

# STEP 2: Remove any cached rhino3dm modules
_modules_to_remove = [k for k in list(sys.modules.keys())
                      if 'rhino3dm' in k.lower() or k.startswith('Rhino')]
for _mod in _modules_to_remove:
    del sys.modules[_mod]
print(f"Removed {len(_modules_to_remove)} cached Rhino/rhino3dm modules")

# STEP 3: Add CLR references to RhinoCommon
clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')
clr.AddReference('RhinoInside.Revit')

# STEP 4: Import Rhino from RhinoCommon
import Rhino
import Rhino.Geometry as rg

# STEP 5: Force sys.modules to use RhinoCommon
# This ensures all subsequent 'import Rhino' statements use our version
sys.modules['Rhino'] = Rhino
sys.modules['Rhino.Geometry'] = rg

# Verify we got RhinoCommon
try:
    _test_pt = rg.Point3d(0, 0, 0)
    _asm_name = _test_pt.GetType().Assembly.GetName().Name
    print(f"Rhino.Geometry is from assembly: {_asm_name}")
    if "RhinoCommon" in _asm_name:
        print("SUCCESS: Using RhinoCommon!")
    else:
        print(f"WARNING: Expected RhinoCommon but got {_asm_name}")
except Exception as e:
    print(f"Could not verify assembly: {e}")
import scriptcontext as sc
import ghpythonlib.treehelpers as th
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path
from Grasshopper.Kernel import GH_Convert, GH_Conversion
from Grasshopper.Kernel.Types import GH_Brep, GH_Curve, GH_Point, GH_Mesh, GH_Surface
from RhinoInside.Revit import Revit
import System

# Verify we have the correct assembly
try:
    # Try multiple ways to get assembly info
    _point_type = rg.Point3d(0, 0, 0).GetType()
    _assembly = _point_type.Assembly
    _rhino_assembly = _assembly.GetName().Name
    print(f"Rhino.Geometry loaded from assembly: {_rhino_assembly}")
    if "RhinoCommon" not in _rhino_assembly and "Rhino3dm" not in _rhino_assembly:
        print(f"Assembly details: {_assembly.FullName}")
except Exception as e:
    print(f"Could not verify assembly: {e}")
    # Try alternative method
    try:
        print(f"Rhino module location: {Rhino.__file__ if hasattr(Rhino, '__file__') else 'N/A'}")
        print(f"rg module: {rg}")
    except:
        pass


def patch_module_rhino_geometry(module):
    """
    Patch a module to use the correct Rhino.Geometry from RhinoCommon.
    This fixes the assembly mismatch issue where modules import Rhino3dmIO instead.
    """
    if hasattr(module, 'rg'):
        # Check if the module's rg is from the wrong assembly
        try:
            module_assembly = str(module.rg.Point3d.GetType().Assembly.FullName).split(',')[0]
            if module_assembly != "RhinoCommon":
                print(f"  Patching {module.__name__}: {module_assembly} -> RhinoCommon")
                module.rg = rg  # Replace with our correct rg
        except:
            pass


# =============================================================================
# RHINOCOMMON GEOMETRY FACTORY
# =============================================================================
# This factory creates geometry directly using RhinoCommon assembly types,
# bypassing any rhino3dm/Rhino3dmIO assembly conflicts.
#
# The solution uses .NET reflection to:
# 1. Find the RhinoCommon assembly from AppDomain
# 2. Get types directly from that assembly
# 3. Create instances using System.Activator.CreateInstance()
#
# This ensures all geometry is created with the correct assembly that
# Grasshopper expects.
# =============================================================================

class RhinoCommonFactory:
    """
    Factory for creating RhinoCommon geometry directly via CLR reflection.

    This bypasses the rhino3dm package which creates Rhino3dmIO geometry
    that Grasshopper cannot use. All geometry created through this factory
    is guaranteed to be from the RhinoCommon assembly.
    """

    _instance = None
    _rc_assembly = None
    _types_cache = {}

    def __new__(cls):
        """Singleton pattern - reuse the same factory instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the factory by finding RhinoCommon assembly."""
        if self._initialized:
            return

        from System import AppDomain

        # Find RhinoCommon assembly
        for asm in AppDomain.CurrentDomain.GetAssemblies():
            name = asm.GetName().Name
            if name == "RhinoCommon":
                self._rc_assembly = asm
                print(f"RhinoCommonFactory: Found RhinoCommon assembly")
                break

        if self._rc_assembly is None:
            raise RuntimeError("RhinoCommon assembly not found in AppDomain")

        # Pre-cache commonly used types
        self._cache_types()
        self._initialized = True

    def _cache_types(self):
        """Pre-cache commonly used RhinoCommon types."""
        type_names = [
            "Rhino.Geometry.Point3d",
            "Rhino.Geometry.Vector3d",
            "Rhino.Geometry.Plane",
            "Rhino.Geometry.Line",
            "Rhino.Geometry.LineCurve",
            "Rhino.Geometry.PolylineCurve",
            "Rhino.Geometry.Polyline",
            "Rhino.Geometry.BoundingBox",
            "Rhino.Geometry.Box",
            "Rhino.Geometry.Interval",
            "Rhino.Geometry.Rectangle3d",
            "Rhino.Geometry.Extrusion",
            "Rhino.Geometry.Brep",
            "Rhino.Geometry.NurbsCurve",
            "Rhino.Geometry.NurbsSurface",
            "Rhino.Geometry.Curve",
        ]

        for full_name in type_names:
            short_name = full_name.split(".")[-1]
            self._types_cache[short_name] = self._rc_assembly.GetType(full_name)

    def _get_type(self, type_name: str):
        """Get a RhinoCommon type by short name."""
        if type_name not in self._types_cache:
            full_name = f"Rhino.Geometry.{type_name}"
            self._types_cache[type_name] = self._rc_assembly.GetType(full_name)
        return self._types_cache[type_name]

    def _create_instance(self, type_name: str, *args):
        """Create an instance of a RhinoCommon type."""
        from System import Activator, Array

        rc_type = self._get_type(type_name)
        if rc_type is None:
            raise TypeError(f"Could not find type: {type_name}")

        if len(args) == 0:
            return Activator.CreateInstance(rc_type)
        else:
            return Activator.CreateInstance(rc_type, Array[object](list(args)))

    # =========================================================================
    # Basic Geometry Creation Methods
    # =========================================================================

    def create_point3d(self, x: float, y: float, z: float):
        """Create a RhinoCommon Point3d from coordinates."""
        return self._create_instance("Point3d", float(x), float(y), float(z))

    def create_vector3d(self, x: float, y: float, z: float):
        """Create a RhinoCommon Vector3d from components."""
        return self._create_instance("Vector3d", float(x), float(y), float(z))

    def create_plane(self, origin, x_axis, y_axis):
        """
        Create a RhinoCommon Plane.

        Args:
            origin: Point3d or (x, y, z) tuple
            x_axis: Vector3d or (x, y, z) tuple
            y_axis: Vector3d or (x, y, z) tuple
        """
        # Convert origin if needed
        if isinstance(origin, (tuple, list)):
            origin = self.create_point3d(*origin)
        elif hasattr(origin, 'X'):  # Existing Point3d (possibly from wrong assembly)
            origin = self.create_point3d(float(origin.X), float(origin.Y), float(origin.Z))

        # Convert x_axis if needed
        if isinstance(x_axis, (tuple, list)):
            x_axis = self.create_vector3d(*x_axis)
        elif hasattr(x_axis, 'X'):
            x_axis = self.create_vector3d(float(x_axis.X), float(x_axis.Y), float(x_axis.Z))

        # Convert y_axis if needed
        if isinstance(y_axis, (tuple, list)):
            y_axis = self.create_vector3d(*y_axis)
        elif hasattr(y_axis, 'X'):
            y_axis = self.create_vector3d(float(y_axis.X), float(y_axis.Y), float(y_axis.Z))

        return self._create_instance("Plane", origin, x_axis, y_axis)

    def create_line(self, start_point, end_point):
        """
        Create a RhinoCommon Line.

        Args:
            start_point: Point3d or (x, y, z) tuple
            end_point: Point3d or (x, y, z) tuple
        """
        # Convert points if needed
        if isinstance(start_point, (tuple, list)):
            start_point = self.create_point3d(*start_point)
        elif hasattr(start_point, 'X'):
            start_point = self.create_point3d(float(start_point.X), float(start_point.Y), float(start_point.Z))

        if isinstance(end_point, (tuple, list)):
            end_point = self.create_point3d(*end_point)
        elif hasattr(end_point, 'X'):
            end_point = self.create_point3d(float(end_point.X), float(end_point.Y), float(end_point.Z))

        return self._create_instance("Line", start_point, end_point)

    def create_line_curve(self, start_point, end_point):
        """
        Create a RhinoCommon LineCurve.

        Args:
            start_point: Point3d or (x, y, z) tuple
            end_point: Point3d or (x, y, z) tuple
        """
        line = self.create_line(start_point, end_point)
        return self._create_instance("LineCurve", line)

    def create_closed_polyline_from_points(self, points):
        """
        Create a closed RhinoCommon curve from corner points.

        Uses NurbsCurve.Create static method via reflection (same pattern as
        create_surface_from_corners which works).

        Args:
            points: List of 4 corner points as Point3d or (x, y, z) tuples

        Returns:
            NurbsCurve from RhinoCommon assembly, or None if creation fails
        """
        from System import Array
        from System.Reflection import BindingFlags

        # Convert all points to RhinoCommon Point3d
        rc_points = []
        for pt in points:
            if isinstance(pt, (tuple, list)):
                rc_points.append(self.create_point3d(*pt))
            elif hasattr(pt, 'X'):
                rc_points.append(self.create_point3d(
                    float(pt.X), float(pt.Y), float(pt.Z)
                ))
            else:
                rc_points.append(pt)

        # Close by adding first point at end
        if len(rc_points) > 0:
            first_pt = rc_points[0]
            rc_points.append(self.create_point3d(
                float(first_pt.X), float(first_pt.Y), float(first_pt.Z)
            ))

        # Get NurbsCurve type
        RC_NurbsCurve = self._get_type("NurbsCurve")
        RC_Point3d = self._get_type("Point3d")

        if RC_NurbsCurve is None:
            print("  ERROR: Could not get NurbsCurve type")
            return None

        try:
            # Create typed Point3d array
            pt_array = Array.CreateInstance(RC_Point3d, len(rc_points))
            for i, pt in enumerate(rc_points):
                pt_array[i] = pt

            # Try NurbsCurve.Create static method with points array
            # Look for Create(IEnumerable<Point3d>, int degree, NurbsCurveKnotStyle)
            create_methods = RC_NurbsCurve.GetMethods(BindingFlags.Public | BindingFlags.Static)

            for method in create_methods:
                if method.Name == "Create":
                    params = method.GetParameters()
                    # Look for overload: Create(bool periodic, int degree, IEnumerable<Point3d>)
                    if len(params) == 3:
                        try:
                            # Try: Create(false, 1, points) for linear interpolation
                            result = method.Invoke(None, [False, 1, pt_array])
                            if result is not None:
                                return result
                        except:
                            pass

            # Fallback: Create 4 line curves and join them manually
            print("  NurbsCurve.Create failed, using LineCurve segments")
            line_curves = []
            for i in range(len(rc_points) - 1):
                line = self.create_line_curve(rc_points[i], rc_points[i + 1])
                if line is not None:
                    line_curves.append(line)

            if line_curves:
                # Return first line curve as minimal fallback
                return line_curves[0]

            return None

        except Exception as e:
            print(f"  create_closed_polyline_from_points error: {e}")
            return None

    def get_boundary_curves_from_surface(self, surface):
        """
        Extract boundary curves from a surface.

        Since create_surface_from_corners works, we can create the surface
        first and then extract its boundary as the rectangle curve.

        Args:
            surface: NurbsSurface from RhinoCommon

        Returns:
            Array of boundary curves, or None
        """
        if surface is None:
            return None

        try:
            # Get outer boundary curves from the surface
            # Brep has better boundary extraction
            brep = surface.ToBrep()
            if brep is not None:
                # Get naked edges (boundary)
                edges = brep.Edges
                if edges is not None and edges.Count > 0:
                    # Join the edges into a single curve
                    edge_curves = []
                    for i in range(edges.Count):
                        edge = edges[i]
                        if edge is not None:
                            crv = edge.DuplicateCurve()
                            if crv is not None:
                                edge_curves.append(crv)

                    if edge_curves:
                        # Try to join
                        RC_Curve = self._get_type("Curve")
                        if RC_Curve is not None and len(edge_curves) > 1:
                            from System import Array
                            from System.Reflection import BindingFlags

                            curve_array = Array.CreateInstance(RC_Curve, len(edge_curves))
                            for i, crv in enumerate(edge_curves):
                                curve_array[i] = crv

                            join_methods = RC_Curve.GetMethods(BindingFlags.Public | BindingFlags.Static)
                            for method in join_methods:
                                if method.Name == "JoinCurves":
                                    params = method.GetParameters()
                                    try:
                                        if len(params) >= 1:
                                            joined = method.Invoke(None, [curve_array])
                                            if joined is not None and len(joined) > 0:
                                                return joined[0]
                                    except:
                                        continue

                        # Return first edge if join fails
                        return edge_curves[0] if edge_curves else None

        except Exception as e:
            print(f"  get_boundary_curves_from_surface error: {e}")

        return None

    def create_surface_from_corners(self, p1, p2, p3, p4):
        """
        Create a RhinoCommon NurbsSurface from 4 corner points.

        Uses NurbsSurface.CreateFromCorners static method via proper reflection.

        Args:
            p1, p2, p3, p4: Corner points as Point3d or (x, y, z) tuples

        Returns:
            NurbsSurface from RhinoCommon assembly, or None if creation fails
        """
        from System.Reflection import BindingFlags

        # Convert all points to RhinoCommon Point3d
        corners = []
        for pt in [p1, p2, p3, p4]:
            if isinstance(pt, (tuple, list)):
                corners.append(self.create_point3d(*pt))
            elif hasattr(pt, 'X'):
                corners.append(self.create_point3d(
                    float(pt.X), float(pt.Y), float(pt.Z)
                ))
            else:
                corners.append(pt)

        # Get NurbsSurface type and invoke static method
        RC_NurbsSurface = self._get_type("NurbsSurface")
        if RC_NurbsSurface is None:
            print("  ERROR: Could not get NurbsSurface type")
            return None

        try:
            # Use reflection to invoke the static CreateFromCorners method
            method_info = RC_NurbsSurface.GetMethod(
                "CreateFromCorners",
                BindingFlags.Public | BindingFlags.Static,
                None,
                [self._get_type("Point3d")] * 4,  # 4 Point3d parameters
                None
            )

            if method_info is not None:
                result = method_info.Invoke(None, corners)
                return result
            else:
                # Try alternative: direct call (works in some IronPython versions)
                return RC_NurbsSurface.CreateFromCorners(
                    corners[0], corners[1], corners[2], corners[3]
                )
        except Exception as e:
            print(f"  NurbsSurface.CreateFromCorners error: {e}")
            return None

    def create_interval(self, t0: float, t1: float):
        """Create a RhinoCommon Interval."""
        return self._create_instance("Interval", float(t0), float(t1))

    def create_rectangle3d(self, plane, width: float, height: float):
        """
        Create a RhinoCommon Rectangle3d centered on a plane.

        Args:
            plane: Plane or origin point (will use XY axes)
            width: Width of rectangle
            height: Height of rectangle
        """
        # Convert plane if it's a point
        if isinstance(plane, (tuple, list)):
            origin = self.create_point3d(*plane)
            x_axis = self.create_vector3d(1.0, 0.0, 0.0)
            y_axis = self.create_vector3d(0.0, 1.0, 0.0)
            plane = self._create_instance("Plane", origin, x_axis, y_axis)
        elif hasattr(plane, 'Origin') and hasattr(plane, 'XAxis'):
            # Existing plane - convert it
            origin = self.create_point3d(float(plane.Origin.X), float(plane.Origin.Y), float(plane.Origin.Z))
            x_axis = self.create_vector3d(float(plane.XAxis.X), float(plane.XAxis.Y), float(plane.XAxis.Z))
            y_axis = self.create_vector3d(float(plane.YAxis.X), float(plane.YAxis.Y), float(plane.YAxis.Z))
            plane = self._create_instance("Plane", origin, x_axis, y_axis)

        # Create intervals for width and height (centered)
        x_interval = self.create_interval(-float(width) / 2.0, float(width) / 2.0)
        y_interval = self.create_interval(-float(height) / 2.0, float(height) / 2.0)

        return self._create_instance("Rectangle3d", plane, x_interval, y_interval)

    def create_bounding_box(self, min_point, max_point):
        """
        Create a RhinoCommon BoundingBox.

        Args:
            min_point: Point3d or (x, y, z) tuple for min corner
            max_point: Point3d or (x, y, z) tuple for max corner
        """
        if isinstance(min_point, (tuple, list)):
            min_point = self.create_point3d(*min_point)
        elif hasattr(min_point, 'X'):
            min_point = self.create_point3d(float(min_point.X), float(min_point.Y), float(min_point.Z))

        if isinstance(max_point, (tuple, list)):
            max_point = self.create_point3d(*max_point)
        elif hasattr(max_point, 'X'):
            max_point = self.create_point3d(float(max_point.X), float(max_point.Y), float(max_point.Z))

        return self._create_instance("BoundingBox", min_point, max_point)

    def create_box(self, bounding_box):
        """Create a RhinoCommon Box from a BoundingBox."""
        return self._create_instance("Box", bounding_box)

    # =========================================================================
    # Framing-Specific Geometry Creation
    # =========================================================================

    def create_extrusion_brep(self, profile_plane, width: float, depth: float,
                               direction, length: float):
        """
        Create a Brep by extruding a rectangular profile.

        This is the core method for creating timber framing elements (studs,
        plates, headers, etc.) from centerline and dimension data.

        Args:
            profile_plane: Plane at the profile center (start of extrusion)
            width: Width of the rectangular profile
            depth: Depth of the rectangular profile
            direction: Extrusion direction vector
            length: Length of extrusion

        Returns:
            Brep geometry from RhinoCommon assembly
        """
        # Create the profile rectangle
        rect = self.create_rectangle3d(profile_plane, width, depth)

        # Convert rectangle to NurbsCurve for extrusion
        rect_curve = rect.ToNurbsCurve()

        # Calculate the extrusion vector
        if isinstance(direction, (tuple, list)):
            direction = self.create_vector3d(*direction)
        elif hasattr(direction, 'X'):
            direction = self.create_vector3d(float(direction.X), float(direction.Y), float(direction.Z))

        # Scale direction by length
        ext_x = direction.X * length
        ext_y = direction.Y * length
        ext_z = direction.Z * length
        extrusion_vec = self.create_vector3d(ext_x, ext_y, ext_z)

        # Create extrusion
        RC_Extrusion = self._get_type("Extrusion")
        extrusion = RC_Extrusion.Create(rect_curve, float(length), True)

        if extrusion is not None and extrusion.IsValid:
            brep = extrusion.ToBrep()
            if brep is not None and brep.IsValid:
                return brep

        # Fallback: Create box from bounding box
        return self.create_box_brep_from_centerline(
            profile_plane.Origin, direction, length, width, depth
        )

    def create_box_brep_from_centerline(self, start_point, direction, length: float,
                                         width: float, depth: float):
        """
        Create a box Brep from centerline parameters.

        This creates a timber element as a simple box aligned with the centerline.

        Args:
            start_point: Start point of centerline
            direction: Direction vector (normalized)
            length: Length along direction
            width: Width perpendicular to direction (in XY plane)
            depth: Depth perpendicular to direction and width

        Returns:
            Brep geometry from RhinoCommon assembly
        """
        # Convert inputs
        if isinstance(start_point, (tuple, list)):
            sx, sy, sz = start_point
        else:
            sx, sy, sz = float(start_point.X), float(start_point.Y), float(start_point.Z)

        if isinstance(direction, (tuple, list)):
            dx, dy, dz = direction
        else:
            dx, dy, dz = float(direction.X), float(direction.Y), float(direction.Z)

        # Normalize direction
        mag = (dx*dx + dy*dy + dz*dz) ** 0.5
        if mag > 0:
            dx, dy, dz = dx/mag, dy/mag, dz/mag

        # Calculate end point
        ex = sx + dx * length
        ey = sy + dy * length
        ez = sz + dz * length

        # Calculate perpendicular vectors for width and depth
        # Simple approach: if direction is vertical, use X and Y
        # Otherwise, use cross products
        if abs(dz) > 0.9:  # Nearly vertical
            perp1 = (1.0, 0.0, 0.0)  # Width in X
            perp2 = (0.0, 1.0, 0.0)  # Depth in Y
        else:
            # Cross with Z to get perpendicular
            p1x = -dy
            p1y = dx
            p1z = 0.0
            # Normalize
            p1_mag = (p1x*p1x + p1y*p1y) ** 0.5
            if p1_mag > 0:
                p1x, p1y = p1x/p1_mag, p1y/p1_mag
            perp1 = (p1x, p1y, p1z)

            # Cross direction with perp1 to get perp2
            p2x = dy * p1z - dz * p1y
            p2y = dz * p1x - dx * p1z
            p2z = dx * p1y - dy * p1x
            perp2 = (p2x, p2y, p2z)

        # Calculate bounding box corners (accounting for width/depth offsets)
        half_w = width / 2.0
        half_d = depth / 2.0

        # Find min/max by checking all corners
        corners = []
        for start_end in [(sx, sy, sz), (ex, ey, ez)]:
            px, py, pz = start_end
            for w_sign in [-1, 1]:
                for d_sign in [-1, 1]:
                    cx = px + perp1[0] * half_w * w_sign + perp2[0] * half_d * d_sign
                    cy = py + perp1[1] * half_w * w_sign + perp2[1] * half_d * d_sign
                    cz = pz + perp1[2] * half_w * w_sign + perp2[2] * half_d * d_sign
                    corners.append((cx, cy, cz))

        # Find actual min/max from corners
        min_x = min(c[0] for c in corners)
        min_y = min(c[1] for c in corners)
        min_z = min(c[2] for c in corners)
        max_x = max(c[0] for c in corners)
        max_y = max(c[1] for c in corners)
        max_z = max(c[2] for c in corners)

        # Create bounding box and box
        bbox = self.create_bounding_box((min_x, min_y, min_z), (max_x, max_y, max_z))
        box = self.create_box(bbox)

        return box.ToBrep()

    def convert_geometry_from_rhino3dm(self, geom):
        """
        Convert geometry from Rhino3dmIO assembly to RhinoCommon assembly.

        This extracts the bounding box from the source geometry and creates
        a new box using RhinoCommon. While this loses exact shape fidelity,
        it works for simple box-like timber framing elements.

        Args:
            geom: Geometry object (likely from Rhino3dmIO)

        Returns:
            Brep from RhinoCommon assembly, or None if conversion fails
        """
        if geom is None:
            return None

        try:
            # Get bounding box coordinates
            bbox = geom.GetBoundingBox(True)
            if not bbox.IsValid:
                return None

            min_pt = (float(bbox.Min.X), float(bbox.Min.Y), float(bbox.Min.Z))
            max_pt = (float(bbox.Max.X), float(bbox.Max.Y), float(bbox.Max.Z))

            # Create RhinoCommon box
            rc_bbox = self.create_bounding_box(min_pt, max_pt)
            rc_box = self.create_box(rc_bbox)

            return rc_box.ToBrep()
        except Exception as e:
            print(f"RhinoCommonFactory.convert_geometry_from_rhino3dm error: {e}")
            return None


# Create global factory instance
try:
    rc_factory = RhinoCommonFactory()
    print("RhinoCommonFactory initialized successfully")
except Exception as e:
    rc_factory = None
    print(f"WARNING: Could not initialize RhinoCommonFactory: {e}")


def patch_all_timber_modules():
    """
    Patch all timber_framing_generator modules to use RhinoCommon.
    Call this after importing/reloading modules.
    """
    print("Patching modules to use RhinoCommon...")
    patched = 0
    for name, module in sys.modules.items():
        if module is not None and 'timber_framing_generator' in name:
            patch_module_rhino_geometry(module)
            patched += 1
    print(f"  Checked {patched} modules")

# Store reference to ghdoc for geometry operations
# ghdoc is a special Grasshopper document that handles geometry correctly
try:
    import ghdoc
    GHDOC_AVAILABLE = True
except:
    GHDOC_AVAILABLE = False
    print("Warning: ghdoc not available")


def convert_to_gh_brep(brep):
    """
    Convert a Rhino.Geometry.Brep to a Grasshopper-compatible format.
    Tries multiple methods to handle cross-assembly conversion.

    Args:
        brep: Rhino.Geometry.Brep object

    Returns:
        Geometry compatible with Grasshopper output or None on failure
    """
    if brep is None:
        return None

    # Method 1: Try direct duplicate - sometimes this creates a new object in current context
    try:
        if hasattr(brep, 'DuplicateBrep'):
            dup = brep.DuplicateBrep()
            if dup is not None:
                return dup
    except Exception as e:
        print(f"DuplicateBrep error: {e}")

    # Method 2: Try Duplicate() (base GeometryBase method)
    try:
        if hasattr(brep, 'Duplicate'):
            dup = brep.Duplicate()
            if dup is not None:
                return dup
    except Exception as e:
        print(f"Duplicate error: {e}")

    # Method 3: Try using ghdoc to force geometry into GH context
    if GHDOC_AVAILABLE:
        try:
            current_doc = sc.doc
            sc.doc = ghdoc
            guid = sc.doc.Objects.AddBrep(brep)
            if guid != System.Guid.Empty:
                obj = sc.doc.Objects.FindId(guid)
                if obj and obj.Geometry:
                    result = obj.Geometry.Duplicate()
                    sc.doc.Objects.Delete(guid, True)
                    sc.doc = current_doc
                    return result
            sc.doc = current_doc
        except Exception as e:
            print(f"ghdoc conversion error: {e}")
            try:
                sc.doc = current_doc
            except:
                pass

    # Method 4: Return as-is and let GH try to handle it
    return brep


def convert_to_gh_curve(curve):
    """
    Convert a Rhino.Geometry.Curve to a Grasshopper-compatible GH_Curve.

    Args:
        curve: Rhino.Geometry.Curve object

    Returns:
        GH_Curve or None on failure
    """
    if curve is None:
        return None

    try:
        # Method 1: Direct CastFrom
        gh_curve = GH_Curve()
        if gh_curve.CastFrom(curve):
            return gh_curve
    except Exception as e:
        print(f"GH_Curve CastFrom error: {e}")

    try:
        # Method 2: GH_Convert
        gh_curve = GH_Curve()
        result = GH_Convert.ToGHCurve(curve, GH_Conversion.Both, gh_curve)
        if isinstance(result, tuple):
            success, gh_curve = result[0], result[1]
            if success and gh_curve is not None:
                return gh_curve
        elif result:
            return gh_curve
    except Exception as e:
        print(f"GH_Curve ToGHCurve error: {e}")

    return None


def convert_to_gh_point(point):
    """
    Convert a Rhino.Geometry.Point3d to a Grasshopper-compatible GH_Point.

    Args:
        point: Rhino.Geometry.Point3d object

    Returns:
        GH_Point or None on failure
    """
    if point is None:
        return None

    try:
        # Method 1: Direct CastFrom
        gh_point = GH_Point()
        if gh_point.CastFrom(point):
            return gh_point
    except Exception as e:
        print(f"GH_Point CastFrom error: {e}")

    try:
        # Method 2: GH_Convert
        gh_point = GH_Point()
        result = GH_Convert.ToGHPoint(point, GH_Conversion.Both, gh_point)
        if isinstance(result, tuple):
            success, gh_point = result[0], result[1]
            if success and gh_point is not None:
                return gh_point
        elif result:
            return gh_point
    except Exception as e:
        print(f"GH_Point ToGHPoint error: {e}")

    return None


def convert_to_gh_mesh(mesh):
    """
    Convert a Rhino.Geometry.Mesh to a Grasshopper-compatible GH_Mesh.

    Args:
        mesh: Rhino.Geometry.Mesh object

    Returns:
        GH_Mesh or None on failure
    """
    if mesh is None:
        return None

    try:
        # Method 1: Direct CastFrom
        gh_mesh = GH_Mesh()
        if gh_mesh.CastFrom(mesh):
            return gh_mesh
    except Exception as e:
        print(f"GH_Mesh CastFrom error: {e}")

    try:
        # Method 2: GH_Convert
        gh_mesh = GH_Mesh()
        result = GH_Convert.ToGHMesh(mesh, GH_Conversion.Both, gh_mesh)
        if isinstance(result, tuple):
            success, gh_mesh = result[0], result[1]
            if success and gh_mesh is not None:
                return gh_mesh
        elif result:
            return gh_mesh
    except Exception as e:
        print(f"GH_Mesh ToGHMesh error: {e}")

    return None


def convert_to_gh_surface(surface):
    """
    Convert a Rhino.Geometry.Surface to a Grasshopper-compatible GH_Surface.

    Args:
        surface: Rhino.Geometry.Surface object

    Returns:
        GH_Surface or None on failure
    """
    if surface is None:
        return None

    try:
        # Method 1: Direct CastFrom
        gh_surface = GH_Surface()
        if gh_surface.CastFrom(surface):
            return gh_surface
    except Exception as e:
        print(f"GH_Surface CastFrom error: {e}")

    try:
        # Method 2: GH_Convert
        gh_surface = GH_Surface()
        result = GH_Convert.ToGHSurface(surface, GH_Conversion.Both, gh_surface)
        if isinstance(result, tuple):
            success, gh_surface = result[0], result[1]
            if success and gh_surface is not None:
                return gh_surface
        elif result:
            return gh_surface
    except Exception as e:
        print(f"GH_Surface ToGHSurface error: {e}")

    return None


def convert_geometry_for_gh(geometry):
    """
    Convert any Rhino geometry to its Grasshopper-compatible equivalent.
    Automatically detects geometry type and applies appropriate conversion.

    Args:
        geometry: Any Rhino.Geometry object

    Returns:
        Grasshopper-compatible geometry (GH_Brep, GH_Curve, etc.) or None
    """
    if geometry is None:
        return None

    try:
        # Get the type name for more reliable type checking across assemblies
        type_name = geometry.GetType().Name

        # Check geometry type and convert accordingly
        if type_name == "Brep" or isinstance(geometry, rg.Brep):
            return convert_to_gh_brep(geometry)
        elif type_name == "Mesh" or isinstance(geometry, rg.Mesh):
            return convert_to_gh_mesh(geometry)
        elif type_name in ["Surface", "NurbsSurface", "BrepFace"] or isinstance(geometry, rg.Surface):
            return convert_to_gh_surface(geometry)
        elif type_name in ["Curve", "LineCurve", "NurbsCurve", "PolylineCurve", "ArcCurve"] or isinstance(geometry, rg.Curve):
            return convert_to_gh_curve(geometry)
        elif type_name == "Line":
            # Line is a struct, not a Curve - convert to LineCurve first
            try:
                # Use factory to create RhinoCommon LineCurve
                if rc_factory is not None:
                    start = (float(geometry.From.X), float(geometry.From.Y), float(geometry.From.Z))
                    end = (float(geometry.To.X), float(geometry.To.Y), float(geometry.To.Z))
                    return rc_factory.create_line_curve(start, end)
                else:
                    line_curve = rg.LineCurve(geometry)
                    return convert_to_gh_curve(line_curve)
            except Exception as e:
                print(f"Line conversion error: {e}")
                return None
        elif type_name == "Point3d" or isinstance(geometry, rg.Point3d):
            return convert_to_gh_point(geometry)
        elif type_name in ["Extrusion", "Box"]:
            # For objects that can be converted to Brep
            brep = geometry.ToBrep()
            if brep:
                return convert_to_gh_brep(brep)
        elif hasattr(geometry, 'ToBrep'):
            brep = geometry.ToBrep()
            if brep:
                return convert_to_gh_brep(brep)
        else:
            print(f"Unknown geometry type: {type_name} ({type(geometry)})")
    except Exception as e:
        print(f"Geometry conversion error for {type(geometry)}: {e}")

    return None


def convert_breps_for_output(brep_list, debug=False):
    """
    Convert Breps from Rhino.Inside context to Grasshopper-compatible geometry.

    Uses RhinoCommonFactory to handle assembly mismatch between Rhino3dmIO
    and RhinoCommon. All geometry is recreated using the correct assembly.

    Args:
        brep_list: List of Breps or objects with ToBrep() method
        debug: If True, print detailed diagnostic information

    Returns:
        List of Grasshopper-compatible geometry (from RhinoCommon assembly)
    """
    if not brep_list:
        return []

    result = []
    conversion_errors = 0
    factory_successes = 0
    direct_successes = 0

    for i, item in enumerate(brep_list):
        if item is None:
            continue

        converted = None

        try:
            # Check if item is from wrong assembly
            item_assembly = None
            if hasattr(item, 'GetType'):
                try:
                    item_assembly = item.GetType().Assembly.GetName().Name
                except:
                    pass

            if debug and i < 3:  # Only debug first 3 items
                print(f"\n  DEBUG item {i}:")
                print(f"    Input type: {type(item)}")
                print(f"    Input type name: {item.GetType().Name if hasattr(item, 'GetType') else 'N/A'}")
                print(f"    Input assembly: {item_assembly or 'N/A'}")
                if hasattr(item, 'IsValid'):
                    print(f"    IsValid: {item.IsValid}")

            # PRIMARY METHOD: Use RhinoCommonFactory if item is from wrong assembly
            if rc_factory is not None and item_assembly and item_assembly != "RhinoCommon":
                converted = rc_factory.convert_geometry_from_rhino3dm(item)
                if converted is not None:
                    factory_successes += 1
                    if debug and i < 3:
                        print(f"    Factory conversion: SUCCESS")
                        print(f"    Output assembly: {converted.GetType().Assembly.GetName().Name}")

            # FALLBACK: If factory failed or item is already from correct assembly
            if converted is None:
                # Item might already be from RhinoCommon
                if item_assembly == "RhinoCommon":
                    converted = item
                    direct_successes += 1
                    if debug and i < 3:
                        print(f"    Direct pass-through (already RhinoCommon)")
                else:
                    # Try legacy conversion methods
                    converted = convert_geometry_for_gh(item)
                    if converted is not None:
                        direct_successes += 1

            if debug and i < 3 and converted is not None:
                print(f"    Output type: {type(converted)}")
                if hasattr(converted, 'GetType'):
                    print(f"    Output type name: {converted.GetType().Name}")
                    print(f"    Output assembly: {converted.GetType().Assembly.GetName().Name}")

            if converted is not None:
                result.append(converted)
            else:
                conversion_errors += 1
        except Exception as e:
            print(f"Error converting geometry {i}: {e}")
            import traceback
            traceback.print_exc()
            conversion_errors += 1

    if debug or conversion_errors > 0:
        print(f"  Conversion summary: {len(result)} succeeded ({factory_successes} via factory, {direct_successes} direct), {conversion_errors} failed")

    return result

# Simplified path handling
project_dir = r'C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator'

# Add to sys.path if not already there
if project_dir not in sys.path:
    sys.path.append(project_dir)
    print(f"Added {project_dir} to sys.path")

from src.timber_framing_generator.utils.logging_config import TimberFramingLogger
log_dir = os.path.join(tempfile.gettempdir(), 'timber_framing_logs')
log_file = TimberFramingLogger.configure(debug_mode=True, log_dir=log_dir, rhino_mode=True)
logger = TimberFramingLogger.get_logger(__name__)
logger.info(f"Timber Framing Generator started. Logging to {log_file}")

# Module reloading function
def reload_timber_modules():
    """Reload all timber_framing_generator modules."""
    # First, ensure Rhino modules point to RhinoCommon
    # by injecting our correct Rhino into sys.modules
    sys.modules['Rhino'] = Rhino
    sys.modules['Rhino.Geometry'] = rg

    modules_to_reload = [m for m in sys.modules.keys()
                      if m.startswith('src.timber_framing_generator')]

    reload_count = 0
    for module_name in modules_to_reload:
        try:
            importlib.reload(sys.modules[module_name])
            reload_count += 1
        except Exception as e:
            print(f"Failed to reload {module_name}: {str(e)}")

    print(f"Reloaded {reload_count} modules")

    # Patch all modules after reload
    patch_all_timber_modules()

    return reload_count

# CRITICAL: Clear any cached timber modules before importing
# This ensures they import Rhino.Geometry from our forced sys.modules entry
_timber_modules_to_clear = [k for k in list(sys.modules.keys())
                            if 'timber_framing_generator' in k]
for _mod in _timber_modules_to_clear:
    del sys.modules[_mod]
print(f"Cleared {len(_timber_modules_to_clear)} cached timber modules")

# Now import modules fresh - they will use our Rhino from sys.modules
try:
    from src.timber_framing_generator.utils.serialization import (
        TimberFramingResults, DebugGeometry,
        serialize_results, deserialize_results
    )
    from src.timber_framing_generator.wall_data.wall_selector import pick_walls_from_active_view
    from src.timber_framing_generator.wall_data.revit_data_extractor import extract_wall_data_from_revit
    from src.timber_framing_generator.cell_decomposition.cell_visualizer import create_rectangles_from_cell_data
    from src.timber_framing_generator.framing_elements.plates import create_plates
    from src.timber_framing_generator.framing_elements import FramingGenerator
    print("Successfully imported all modules")
    # Patch modules to use RhinoCommon
    patch_all_timber_modules()
except ImportError as e:
    print(f"Import error: {str(e)}")
    print("Make sure the timber_framing_generator package is correctly installed")
    # Exit or handle the error appropriately

# Reload modules if requested
if reload:
    reload_count = reload_timber_modules()
    
    # Re-import after reloading to ensure we have the latest versions
    from src.timber_framing_generator.wall_data.wall_selector import pick_walls_from_active_view
    from src.timber_framing_generator.wall_data.revit_data_extractor import extract_wall_data_from_revit
    from src.timber_framing_generator.cell_decomposition.cell_visualizer import create_rectangles_from_cell_data
    from src.timber_framing_generator.framing_elements.plates import create_plates
    from src.timber_framing_generator.framing_elements import FramingGenerator
    from src.timber_framing_generator.utils.safe_rhino import safe_create_extrusion
    from src.timber_framing_generator.utils.safe_rhino import safe_add_brep
    from src.timber_framing_generator.utils.safe_rhino import is_valid_geometry
    from src.timber_framing_generator.utils.serialization import inspect_framing_results

    print(f"Re-imported all modules after reloading {reload_count} modules")
    # Patch modules to use RhinoCommon after reload
    patch_all_timber_modules()

print("DEBUG: Script starting")
print(f"DEBUG: TimberFramingResults imported: {TimberFramingResults is not None}")
print(f"DEBUG: DebugGeometry imported: {DebugGeometry is not None}")

def extract_wall_data(walls) -> List[Dict[str, Any]]:
    """
    Extract data from selected Revit walls using our data extractor.
    
    This function processes each wall to capture its geometry, properties,
    and spatial information needed for framing generation. It handles
    errors gracefully and reports issues for individual walls.
    """
    print("DEBUG: Starting wall data extraction")
    uidoc = Revit.ActiveUIDocument
    doc = uidoc.Document
    
    all_walls_data = []
    successfull_walls = 0
    for wall in walls:
        try:
            wall_data = extract_wall_data_from_revit(wall, doc)
            print(f"This is wall_data: {wall_data}")
            print(f"DEBUG: Raw wall_data exists: {wall_data is not None}")
            if wall_data is not None:
                successfull_walls += 1
                print(f"DEBUG: wall_data keys: {list(wall_data.keys())}")
                print(f"DEBUG: base_plane exists: {wall_data.get('base_plane') is not None}")
            all_walls_data.append(wall_data)
            print(f"Processed wall ID: {wall.Id}")
        except Exception as e:
            print(f"Error processing wall {wall.Id}: {str(e)}")
            import traceback
            print(f"Error: Traceback: {traceback.format_exc()}")
        print(f"DEBUG: Extracted data for {successfull_walls}/{len(walls)} walls")

    print(f"DEBUG: Extracted data for {len(all_walls_data)} walls")
    all_walls_data = [wall for wall in all_walls_data if wall is not None]
    print(f"DEBUG: After filtering None values, found {len(all_walls_data)} valid walls")
    print(f"DEBUG: Before filtering, wall data list has {len(all_walls_data)} items")
    valid_walls = []
    for i, wall in enumerate(all_walls_data):
        if wall is not None:
            valid_walls.append(wall)
            print(f"DEBUG: Wall {i} is valid")
        else:
            print(f"DEBUG: Wall {i} is None")
    all_walls_data = valid_walls
    print(f"DEBUG: After filtering None values, found {len(all_walls_data)} valid walls")
    return all_walls_data

def convert_framing_to_objects(all_framing_results: List[Dict[str, Any]]) -> List[TimberFramingResults]:
    """
    Convert framing results dictionaries to custom objects.
    
    Args:
        all_framing_results: List of framing result dictionaries
        
    Returns:
        List of TimberFramingResults objects
    """
    # Import safe_rhino utilities here to avoid circular imports
    from src.timber_framing_generator.utils.safe_rhino import safe_add_brep, is_valid_geometry
    import Rhino.Geometry as rg
    
    result_objects = []
    
    for wall_index, framing in enumerate(all_framing_results):
        # Create a result object for this wall
        result = TimberFramingResults(f"Wall_{wall_index}")
        
        logger.info(f"\nProcessing wall {wall_index}:")
        
        # Get base plane from various sources
        base_plane = None
        if 'base_plane' in framing:
            base_plane = framing['base_plane']
            logger.debug("  Found base_plane in framing results")
        elif 'wall_data' in framing and 'base_plane' in framing['wall_data']:
            base_plane = framing['wall_data']['base_plane']
            logger.debug("  Extracted base_plane from wall_data")
            
        result.base_plane = base_plane
        result.cells = framing.get('cells', [])
        result.wall_data = framing.get('wall_data', {})
        
        # Helper function to extract geometry with fallback methods
        def extract_geometry_with_fallback(element):
            """
            Extract geometry from framing element with multiple fallback methods.
            
            This function tries various approaches to extract valid geometry:
            1. Use get_geometry_data method if available
            2. Access brep property directly if it exists
            3. Access geometry property if it exists
            4. Create geometry from scratch if possible
            
            Returns:
                Rhino geometry object or None if extraction fails
            """
            try:
                # Special case: Direct handling of PlateGeometry objects
                if element.__class__.__name__ == "PlateGeometry":
                    try:
                        # Call create_rhino_geometry directly for PlateGeometry objects
                        rhino_geom = element.create_rhino_geometry()
                        if rhino_geom is not None:
                            logger.debug(f"  Successfully extracted geometry via direct PlateGeometry.create_rhino_geometry()")
                            return rhino_geom
                    except Exception as e:
                        logger.warning(f"  Error calling create_rhino_geometry: {str(e)}")
                
                # Method 1: Try using get_geometry_data
                if hasattr(element, 'get_geometry_data'):
                    try:
                        geometry_data = element.get_geometry_data(platform="rhino")
                        if 'platform_geometry' in geometry_data:
                            geom = geometry_data['platform_geometry']
                            logger.debug(f"  Successfully extracted geometry via get_geometry_data")
                            return safe_add_brep(geom)
                    except Exception as e:
                        logger.debug(f"  get_geometry_data failed: {str(e)}")
                
                # Method 2: Try accessing brep directly
                if hasattr(element, 'brep') and element.brep is not None:
                    brep = safe_add_brep(element.brep)
                    if brep is not None:
                        logger.debug(f"  Successfully extracted geometry via direct brep property")
                        return brep
                
                # Method 3: Try accessing geometry directly
                if hasattr(element, 'geometry') and element.geometry is not None:
                    geom = safe_add_brep(element.geometry)
                    if geom is not None:
                        logger.debug(f"  Successfully extracted geometry via direct geometry property")
                        return geom
                
                # Method 4: Try extracting from raw element properties
                if hasattr(element, 'centerline') and hasattr(element, 'profile'):
                    try:
                        # Get profile curve
                        profile_curve = element.profile.ToNurbsCurve()
                        
                        # Calculate direction from centerline
                        if hasattr(element.centerline, 'TangentAt') and callable(getattr(element.centerline, 'TangentAt')):
                            direction = element.centerline.TangentAt(0.0)
                            
                            # Scale by length
                            if hasattr(element.centerline, 'GetLength') and callable(getattr(element.centerline, 'GetLength')):
                                length = element.centerline.GetLength()
                                direction *= length
                                
                                # Create extrusion
                                from src.timber_framing_generator.utils.safe_rhino import safe_create_extrusion, safe_to_brep
                                extrusion = safe_create_extrusion(profile_curve, direction)
                                if extrusion is not None:
                                    brep = safe_to_brep(extrusion)
                                    if brep is not None:
                                        logger.debug(f"  Successfully created extrusion from centerline/profile properties")
                                        return brep
                    except Exception as e:
                        logger.debug(f"  Extrusion creation from properties failed: {str(e)}")
                
                # Method 5: Element might be geometry already
                result = safe_add_brep(element)
                if result is not None:
                    logger.debug(f"  Element was already valid geometry")
                    return result
                
                # Method 6: Final fallback - create a simple box
                if hasattr(element, 'GetBoundingBox') and callable(getattr(element, 'GetBoundingBox')):
                    try:
                        bbox = element.GetBoundingBox()
                        if not bbox.IsValid:
                            return None
                        
                        # Create a box from the bounding box
                        try:
                            box = rg.Box(bbox)
                            if box.IsValid:
                                brep = safe_to_brep(box)
                                if brep is not None and (not hasattr(brep, 'IsValid') or brep.IsValid):
                                    logger.debug("  Created fallback box geometry from bounding box")
                                    return brep
                        except Exception as box_error:
                            logger.debug(f"  Box creation from bbox failed: {str(box_error)}")
                            # Alternative: create Brep directly from bounding box
                            try:
                                brep = rg.Brep.CreateFromBox(bbox)
                                if brep and brep.IsValid:
                                    logger.debug("  Created fallback Brep directly from bounding box")
                                    return brep
                            except Exception as brep_error:
                                logger.debug(f"  Direct Brep creation from bbox failed: {str(brep_error)}")
                    except Exception as e:
                        logger.debug(f"  Box creation from bounding box failed: {str(e)}")
            
            except Exception as e:
                logger.warning(f"  Error extracting geometry: {str(e)}")
            
            # If we got here, all methods failed
            logger.error(f"  All geometry extraction methods failed")
            return None

        # Process all the main framing element categories
        framing_categories = [
            ('bottom_plates', result.bottom_plates),
            ('top_plates', result.top_plates),
            ('king_studs', result.king_studs),
            ('headers', result.headers),
            ('sills', result.sills),
            ('trimmers', result.trimmers),
            ('header_cripples', result.header_cripples),
            ('sill_cripples', result.sill_cripples),
            ('studs', result.studs),
            ('row_blocking', result.row_blocking),
        ]
        
        # Process each framing category
        for category_name, target_list in framing_categories:
            elements = framing.get(category_name, [])
            success_count = 0
            
            for element in elements:
                try:
                    geometry = extract_geometry_with_fallback(element)
                    if geometry is not None and (not hasattr(geometry, 'IsValid') or geometry.IsValid):
                        target_list.append(geometry)
                        success_count += 1
                except Exception as e:
                    logger.warning(f"  Error processing {category_name} element: {str(e)}")
            
            # Only log counts if there were elements to process
            if elements:
                if success_count > 0:
                    logger.debug(f"  Successfully created {success_count}/{len(elements)} {category_name}")
                else:
                    logger.warning(f"  Failed to create any valid {category_name} ({len(elements)} attempted)")
        
        # Log the counts of each element type
        logger.info(f"Wall {wall_index} element counts:")
        logger.info(f"- Bottom plates: {len(result.bottom_plates)}")
        logger.info(f"- Top plates: {len(result.top_plates)}")
        logger.info(f"- King studs: {len(result.king_studs)}")
        logger.info(f"- Headers: {len(result.headers)}")
        logger.info(f"- Sills: {len(result.sills)}")
        logger.info(f"- Trimmers: {len(result.trimmers)}")
        logger.info(f"- Header cripples: {len(result.header_cripples)}")
        logger.info(f"- Sill cripples: {len(result.sill_cripples)}")
        logger.info(f"- Studs: {len(result.studs)}")
        logger.info(f"- Row blocking: {len(result.row_blocking)}")
        
        # Set wall properties from the wall data
        if 'wall_data' in framing:
            wall_data = framing['wall_data']
            result.wall_type = wall_data.get('wall_type', 'Unknown')
            result.wall_length = wall_data.get('wall_length', 0.0)
            result.wall_height = wall_data.get('wall_height', 0.0)
            result.is_exterior_wall = wall_data.get('is_exterior_wall', False)
        
        result_objects.append(result)
        
    return result_objects

def generate_wall_plates(wall_data):
    """
    Generate bottom and top plates for a wall.
    
    This function creates the actual plate geometry based on the wall data,
    handling both single-layer bottom plates and double-layer top plates.
    """
    # Create bottom plates (single layer)
    bottom_plates = create_plates(
        wall_data=wall_data,
        plate_type="bottom_plate",
        representation_type="schematic",
        layers=1
    )
    
    # Create top plates (double layer)
    top_plates = create_plates(
        wall_data=wall_data,
        plate_type="top_plate",
        representation_type="schematic",
        layers=2
    )
    
    # Get the actual geometry
    bottom_plate_geometry = []
    top_plate_geometry = []
    
    for plate in bottom_plates:
        geometry_data = plate.get_geometry_data(platform="rhino")
        bottom_plate_geometry.append(geometry_data['platform_geometry'])
        
    for plate in top_plates:
        geometry_data = plate.get_geometry_data(platform="rhino")
        top_plate_geometry.append(geometry_data['platform_geometry'])
        
    return bottom_plate_geometry, top_plate_geometry

# Main execution for the Grasshopper component
def main():
    """Main execution for the Grasshopper component."""
    if not run:
        logger.debug("Not running - toggle 'run' to execute")
        return None
        
    # Reload modules if requested
    if reload:
        reload_count = reload_timber_modules()
        
        # Re-import after reload
        from src.timber_framing_generator.utils.serialization import (
            TimberFramingResults, DebugGeometry
        )
        from src.timber_framing_generator.wall_data.revit_data_extractor import extract_wall_data_from_revit
        from src.timber_framing_generator.framing_elements import FramingGenerator
        from src.timber_framing_generator.utils.safe_rhino import (
            safe_create_extrusion, safe_add_brep
        )
        logger.debug(f"Re-imported all modules after reloading {reload_count} modules")
        # Patch modules to use RhinoCommon
        patch_all_timber_modules()
    
    try:
        # Extract wall data
        wall_dict = extract_wall_data(walls)
        logger.debug("Wall data extraction complete")
        
        if not wall_dict:
            logger.warning("No valid walls found to process")
            return []
            
        wall_count = len(wall_dict)
        logger.info(f"Processing {wall_count} walls")
        
        # Define framing configuration
        framing_config = {
            'representation_type': "schematic",
            'bottom_plate_layers': 1,
            'top_plate_layers': 2,
            'include_blocking': True,
            'block_spacing': 48.0/12.0,  # 4ft default
            'first_block_height': 24.0/12.0,  # 2ft default
            'blocking_pattern': "inline"  # Options: "inline" or "staggered"
        }
        
        # Process each wall
        all_framing_results = []
        
        for i, wall_data in enumerate(wall_dict):
            try:
                logger.info(f"Processing wall {i+1} of {wall_count}")
                
                # Validate wall data
                base_plane = wall_data.get('base_plane')
                wall_base_curve = wall_data.get('wall_base_curve')
                
                if base_plane is None or wall_base_curve is None:
                    logger.warning(f"Wall {i+1} missing critical geometry - skipping")
                    continue
                    
                # Generate framing for this wall
                generator = FramingGenerator(
                    wall_data=wall_data,
                    framing_config=framing_config
                )
                
                framing_result = generator.generate_framing()
                
                # Add wall data to the result
                framing_result['wall_data'] = wall_data
                
                # Add debug geometry
                if hasattr(generator, 'debug_geometry'):
                    framing_result['debug_geometry'] = generator.debug_geometry
                
                all_framing_results.append(framing_result)
                
                # Log results
                logger.info(f"Wall {i+1} framing generated successfully")
                
            except Exception as e:
                logger.error(f"Error generating framing for wall {i+1}: {str(e)}")
                logger.error(traceback.format_exc())
                continue
                
        # Convert framing results to objects
        logger.info("Converting framing results to objects")
        framing_objects = convert_framing_to_objects(all_framing_results)
        # After generating the framing objects
        if framing_objects and len(framing_objects) > 0:
            print("\nDetailed inspection of first framing object:")
            inspect_framing_results(framing_objects[0])
        
        logger.info(f"Created {len(framing_objects)} TimberFramingResults objects")
        return framing_objects
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        logger.error(traceback.format_exc())
        return []

# Execute main function and assign result to output
framing_objects = main()

# Extract geometry from framing_objects for Grasshopper outputs
# These variables should match the output parameters in your Grasshopper component
if framing_objects and len(framing_objects) > 0:
    # Collect all geometry by type across all walls
    all_bottom_plates = []
    all_top_plates = []
    all_king_studs = []
    all_headers = []
    all_sills = []
    all_trimmers = []
    all_header_cripples = []
    all_sill_cripples = []
    all_studs = []
    all_row_blocking = []
    all_base_curves = []

    for result in framing_objects:
        # Extract plates
        if hasattr(result, 'bottom_plates') and result.bottom_plates:
            all_bottom_plates.extend(result.bottom_plates)
        if hasattr(result, 'top_plates') and result.top_plates:
            all_top_plates.extend(result.top_plates)

        # Extract framing around openings
        if hasattr(result, 'king_studs') and result.king_studs:
            all_king_studs.extend(result.king_studs)
        if hasattr(result, 'headers') and result.headers:
            all_headers.extend(result.headers)
        if hasattr(result, 'sills') and result.sills:
            all_sills.extend(result.sills)
        if hasattr(result, 'trimmers') and result.trimmers:
            all_trimmers.extend(result.trimmers)
        if hasattr(result, 'header_cripples') and result.header_cripples:
            all_header_cripples.extend(result.header_cripples)
        if hasattr(result, 'sill_cripples') and result.sill_cripples:
            all_sill_cripples.extend(result.sill_cripples)

        # Extract studs and blocking
        if hasattr(result, 'studs') and result.studs:
            all_studs.extend(result.studs)
        if hasattr(result, 'row_blocking') and result.row_blocking:
            all_row_blocking.extend(result.row_blocking)

        # Extract wall base curve from wall_data
        if hasattr(result, 'wall_data') and result.wall_data:
            if 'wall_base_curve' in result.wall_data:
                curve = result.wall_data['wall_base_curve']
                # Convert any curve to Line for Grasshopper type compatibility
                try:
                    line = rg.Line(curve.PointAtStart, curve.PointAtEnd)
                    all_base_curves.append(line)
                except:
                    all_base_curves.append(curve)

    # Convert Breps to Grasshopper-compatible geometry
    # Enable debug=True to see detailed conversion info
    print(f"\n=== Converting geometry to Grasshopper format ===")

    # These output variable names should match your Grasshopper component parameters
    # Enable debug on first category to understand what's happening
    bottom_plates = convert_breps_for_output(all_bottom_plates, debug=True)
    print(f"  Bottom plates: {len(all_bottom_plates)} -> {len(bottom_plates)}")

    top_plates = convert_breps_for_output(all_top_plates)
    print(f"  Top plates: {len(all_top_plates)} -> {len(top_plates)}")

    king_studs = convert_breps_for_output(all_king_studs)
    print(f"  King studs: {len(all_king_studs)} -> {len(king_studs)}")

    headers = convert_breps_for_output(all_headers)
    print(f"  Headers: {len(all_headers)} -> {len(headers)}")

    sills = convert_breps_for_output(all_sills)
    print(f"  Sills: {len(all_sills)} -> {len(sills)}")

    trimmers = convert_breps_for_output(all_trimmers)
    print(f"  Trimmers: {len(all_trimmers)} -> {len(trimmers)}")

    header_cripples = convert_breps_for_output(all_header_cripples)
    print(f"  Header cripples: {len(all_header_cripples)} -> {len(header_cripples)}")

    sill_cripples = convert_breps_for_output(all_sill_cripples)
    print(f"  Sill cripples: {len(all_sill_cripples)} -> {len(sill_cripples)}")

    studs = convert_breps_for_output(all_studs)
    print(f"  Studs: {len(all_studs)} -> {len(studs)}")

    row_blocking = convert_breps_for_output(all_row_blocking)
    print(f"  Row blocking: {len(all_row_blocking)} -> {len(row_blocking)}")

    # Convert curves using the same pattern
    base_curves = [convert_geometry_for_gh(c) for c in all_base_curves if c is not None]
    base_curves = [c for c in base_curves if c is not None]
    print(f"  Base curves: {len(all_base_curves)} -> {len(base_curves)}")

    # Also provide a combined "solids" output with all framing geometry
    all_solids = (all_bottom_plates + all_top_plates + all_king_studs +
                  all_headers + all_sills + all_trimmers +
                  all_header_cripples + all_sill_cripples +
                  all_studs + all_row_blocking)
    solids = convert_breps_for_output(all_solids)
    print(f"  Total solids: {len(all_solids)} -> {len(solids)}")

    logger.info(f"Output summary:")
    logger.info(f"  Bottom plates: {len(all_bottom_plates)}")
    logger.info(f"  Top plates: {len(all_top_plates)}")
    logger.info(f"  King studs: {len(all_king_studs)}")
    logger.info(f"  Headers: {len(all_headers)}")
    logger.info(f"  Sills: {len(all_sills)}")
    logger.info(f"  Trimmers: {len(all_trimmers)}")
    logger.info(f"  Header cripples: {len(all_header_cripples)}")
    logger.info(f"  Sill cripples: {len(all_sill_cripples)}")
    logger.info(f"  Studs: {len(all_studs)}")
    logger.info(f"  Row blocking: {len(all_row_blocking)}")
    logger.info(f"  Total solids: {len(all_solids)}")

    # =============================================================================
    # DATA OUTPUTS - Extract data for downstream components
    # =============================================================================
    print("\n=== Extracting data outputs ===")

    # Import DataTree for grafted outputs
    from Grasshopper import DataTree
    from Grasshopper.Kernel.Data import GH_Path

    # Wall-level data (one per wall)
    wall_dicts = []  # Raw wall data as string representations
    wall_curves = []
    base_elevations = []
    top_elevations = []
    base_planes = []
    is_exterior_walls = []

    # Opening data (flattened across all walls)
    opening_types = []
    opening_location_points = []
    rough_widths = []
    rough_heights = []
    base_elevations_relative = []

    # Cell data (flattened across all walls)
    cell_types = []
    u_starts = []
    u_ends = []
    v_starts = []
    v_ends = []

    # Grafted outputs using DataTree (one branch per cell)
    corner_points_tree = DataTree[object]()
    rectangles_crv_tree = DataTree[object]()
    rectangles_srf_tree = DataTree[object]()
    centerlines_list = []

    cell_index = 0  # Global cell index for tree paths

    for framing_obj in framing_objects:
        # Extract wall data
        if hasattr(framing_obj, 'wall_data') and framing_obj.wall_data:
            wd = framing_obj.wall_data

            # Wall dict - create a summary string
            wall_summary = {
                'wall_type': wd.get('wall_type', 'unknown'),
                'wall_length': wd.get('wall_length', 0),
                'wall_height': wd.get('wall_height', 0),
                'is_exterior': wd.get('is_exterior_wall', False),
                'num_openings': len(wd.get('openings', [])),
                'num_cells': len(wd.get('cells', []))
            }
            wall_dicts.append(str(wall_summary))

            # Wall curve - handle Line type explicitly
            wc = wd.get('wall_base_curve')
            if wc is not None:
                try:
                    wc_type = wc.GetType().Name
                    print(f"  Wall curve type: {wc_type}")
                    if wc_type == "Line":
                        # Convert Line to LineCurve using factory
                        if rc_factory is not None:
                            start = (float(wc.From.X), float(wc.From.Y), float(wc.From.Z))
                            end = (float(wc.To.X), float(wc.To.Y), float(wc.To.Z))
                            rc_curve = rc_factory.create_line_curve(start, end)
                            wall_curves.append(rc_curve)
                            print(f"    Converted Line to LineCurve")
                        else:
                            wall_curves.append(rg.LineCurve(wc))
                    elif wc_type == "LineCurve":
                        # Already a LineCurve - convert using factory
                        if rc_factory is not None:
                            start = (float(wc.PointAtStart.X), float(wc.PointAtStart.Y), float(wc.PointAtStart.Z))
                            end = (float(wc.PointAtEnd.X), float(wc.PointAtEnd.Y), float(wc.PointAtEnd.Z))
                            rc_curve = rc_factory.create_line_curve(start, end)
                            wall_curves.append(rc_curve)
                            print(f"    Converted LineCurve via factory")
                        else:
                            wall_curves.append(wc)
                    else:
                        # Other curve types
                        converted = convert_geometry_for_gh(wc)
                        wall_curves.append(converted if converted else None)
                        print(f"    Converted {wc_type} via convert_geometry_for_gh: {converted is not None}")
                except Exception as e:
                    print(f"  Wall curve conversion error: {e}")
                    import traceback
                    traceback.print_exc()
                    wall_curves.append(None)
            else:
                print(f"  Wall curve is None in wall data")
                wall_curves.append(None)

            # Elevations
            base_elevations.append(wd.get('wall_base_elevation', 0))
            top_elevations.append(wd.get('wall_top_elevation', 0))

            # Base plane - convert using factory
            bp = wd.get('base_plane')
            if bp is not None:
                try:
                    if rc_factory is not None:
                        origin = (float(bp.Origin.X), float(bp.Origin.Y), float(bp.Origin.Z))
                        x_axis = (float(bp.XAxis.X), float(bp.XAxis.Y), float(bp.XAxis.Z))
                        y_axis = (float(bp.YAxis.X), float(bp.YAxis.Y), float(bp.YAxis.Z))
                        rc_plane = rc_factory.create_plane(origin, x_axis, y_axis)
                        base_planes.append(rc_plane)
                    else:
                        base_planes.append(bp)
                except Exception as e:
                    print(f"  Base plane conversion error: {e}")
                    base_planes.append(None)
            else:
                base_planes.append(None)

            # Exterior flag
            is_exterior_walls.append(wd.get('is_exterior_wall', False))

            # Openings
            openings = wd.get('openings', [])
            for opening in openings:
                opening_types.append(opening.get('type', opening.get('opening_type', 'unknown')))
                rough_widths.append(opening.get('rough_width', 0))
                rough_heights.append(opening.get('rough_height', 0))
                base_elevations_relative.append(opening.get('base_elevation_relative_to_wall_base', 0))

                # Opening location point - try multiple possible keys
                loc_pt = opening.get('location_point') or opening.get('start_point') or opening.get('position')
                if loc_pt is not None:
                    try:
                        if rc_factory is not None:
                            rc_pt = rc_factory.create_point3d(
                                float(loc_pt.X), float(loc_pt.Y), float(loc_pt.Z)
                            )
                            opening_location_points.append(rc_pt)
                        else:
                            opening_location_points.append(loc_pt)
                    except Exception as e:
                        print(f"  Opening point conversion error: {e}")
                        opening_location_points.append(None)
                else:
                    # Create point from u_start if available
                    u_start_val = opening.get('start_u_coordinate', opening.get('u_start'))
                    if u_start_val is not None and bp is not None:
                        try:
                            # Create point at opening start using base plane
                            v_val = opening.get('base_elevation_relative_to_wall_base', 0)
                            if rc_factory is not None:
                                pt_origin = bp.Origin
                                pt_x = float(pt_origin.X) + float(bp.XAxis.X) * float(u_start_val)
                                pt_y = float(pt_origin.Y) + float(bp.XAxis.Y) * float(u_start_val)
                                pt_z = float(pt_origin.Z) + float(v_val)
                                rc_pt = rc_factory.create_point3d(pt_x, pt_y, pt_z)
                                opening_location_points.append(rc_pt)
                            else:
                                opening_location_points.append(None)
                        except:
                            opening_location_points.append(None)
                    else:
                        opening_location_points.append(None)

            # Cells
            cells = wd.get('cells', [])
            print(f"  Processing {len(cells)} cells for wall")

            for cell in cells:
                cell_types.append(cell.get('cell_type', 'unknown'))
                u_starts.append(cell.get('u_start', 0))
                u_ends.append(cell.get('u_end', 0))
                v_starts.append(cell.get('v_start', 0))
                v_ends.append(cell.get('v_end', 0))

                # Corner points - use DataTree (grafted: one branch per cell)
                corners = cell.get('corner_points', [])
                cell_path = GH_Path(cell_index)

                # Debug: show corner data availability
                if cell_index == 0:  # Only print for first cell to avoid spam
                    print(f"  First cell corner_points: {len(corners) if corners else 0} points")
                    if corners and len(corners) > 0:
                        pt = corners[0]
                        print(f"    Sample point type: {type(pt).__name__}")
                        if hasattr(pt, 'X'):
                            print(f"    Sample coords: ({pt.X}, {pt.Y}, {pt.Z})")

                if corners and len(corners) >= 4:
                    try:
                        # Convert corner points and add to tree
                        rc_corners = []
                        for pt in corners:
                            if rc_factory is not None:
                                rc_pt = rc_factory.create_point3d(
                                    float(pt.X), float(pt.Y), float(pt.Z)
                                )
                                rc_corners.append(rc_pt)
                                corner_points_tree.Add(rc_pt, cell_path)
                            else:
                                corner_points_tree.Add(pt, cell_path)
                                rc_corners.append(pt)

                        # Create surface and curve from corners
                        if rc_factory is not None and len(rc_corners) >= 4:
                            srf = None

                            # Step 1: Create surface from 4 corner points (this works!)
                            try:
                                srf = rc_factory.create_surface_from_corners(
                                    rc_corners[0], rc_corners[1],
                                    rc_corners[2], rc_corners[3]
                                )
                                if srf is not None:
                                    rectangles_srf_tree.Add(srf, cell_path)
                                    if cell_index == 0:
                                        print(f"  Cell {cell_index}: Created surface")
                                else:
                                    print(f"  Cell {cell_index}: Surface returned None")

                            except Exception as e:
                                print(f"  Cell {cell_index} surface creation error: {e}")

                            # Step 2: Extract boundary curve from surface
                            # Since surface creation works, get its edges as the rectangle curve
                            try:
                                if srf is not None:
                                    boundary_crv = rc_factory.get_boundary_curves_from_surface(srf)
                                    if boundary_crv is not None:
                                        rectangles_crv_tree.Add(boundary_crv, cell_path)
                                        if cell_index == 0:
                                            print(f"  Cell {cell_index}: Extracted boundary curve from surface")
                                    else:
                                        # Fallback: try creating curve directly from points
                                        rect_crv = rc_factory.create_closed_polyline_from_points(rc_corners[:4])
                                        if rect_crv is not None:
                                            rectangles_crv_tree.Add(rect_crv, cell_path)
                                            if cell_index == 0:
                                                print(f"  Cell {cell_index}: Created polyline from points")
                                        else:
                                            print(f"  Cell {cell_index}: Both curve methods failed")
                                else:
                                    # No surface, try direct curve creation
                                    rect_crv = rc_factory.create_closed_polyline_from_points(rc_corners[:4])
                                    if rect_crv is not None:
                                        rectangles_crv_tree.Add(rect_crv, cell_path)

                            except Exception as e:
                                print(f"  Cell {cell_index} curve creation error: {e}")

                    except Exception as e:
                        print(f"  Cell {cell_index} corner points error: {e}")

                cell_index += 1

    print(f"  Wall data: {len(wall_curves)} walls, {len(wall_dicts)} dicts")
    print(f"  Openings: {len(opening_types)} openings, {len(opening_location_points)} points")
    print(f"  Cells: {len(cell_types)} cells, {cell_index} processed")
    print(f"  Corner points tree: {corner_points_tree.BranchCount} branches")
    print(f"  Rectangle curves tree: {rectangles_crv_tree.BranchCount} branches")
    print(f"  Rectangle surfaces tree: {rectangles_srf_tree.BranchCount} branches")

    # Assign to output variables (these names must match GH component outputs)
    wall_dict = wall_dicts
    wall_curve = wall_curves
    base_elevation = base_elevations
    top_elevation = top_elevations
    base_plane = base_planes
    is_exterior_wall = is_exterior_walls
    opening_type = opening_types
    opening_location_point = opening_location_points
    rough_width = rough_widths
    rough_height = rough_heights
    base_elevation_relative_to_wall_base = base_elevations_relative
    cell_type = cell_types
    u_start = u_starts
    u_end = u_ends
    v_start = v_starts
    v_end = v_ends
    corner_points = corner_points_tree  # DataTree: one branch per cell with 4 points
    rectangles_crv = rectangles_crv_tree  # DataTree: one curve per cell
    rectangles_srf = rectangles_srf_tree  # DataTree: one surface per cell
    centerlines = centerlines_list  # Not implemented yet

else:
    # No framing objects - set all outputs to empty lists/trees
    from Grasshopper import DataTree
    from Grasshopper.Kernel.Data import GH_Path

    # Geometry outputs
    bottom_plates = []
    top_plates = []
    king_studs = []
    headers = []
    sills = []
    trimmers = []
    header_cripples = []
    sill_cripples = []
    studs = []
    row_blocking = []
    base_curves = []
    solids = []

    # Data outputs
    wall_dict = []
    wall_curve = []
    base_elevation = []
    top_elevation = []
    base_plane = []
    is_exterior_wall = []
    opening_type = []
    opening_location_point = []
    rough_width = []
    rough_height = []
    base_elevation_relative_to_wall_base = []
    cell_type = []
    u_start = []
    u_end = []
    v_start = []
    v_end = []
    corner_points = DataTree[object]()  # Empty tree
    rectangles_crv = DataTree[object]()  # Empty tree
    rectangles_srf = DataTree[object]()  # Empty tree
    centerlines = []

    # Also initialize the all_* variables for the diagnostic section
    all_bottom_plates = []
    all_top_plates = []
    all_king_studs = []
    all_headers = []
    all_sills = []
    all_trimmers = []
    all_header_cripples = []
    all_sill_cripples = []
    all_studs = []
    all_row_blocking = []
    all_base_curves = []
    logger.warning("No framing objects generated - all outputs are empty")


# =============================================================================
# DIAGNOSTIC TEST SECTION
# =============================================================================
# This section tests the RhinoCommonFactory independently of framing generation.
# It creates a test box using the factory to verify CLR-based geometry creation works.
#
# OUTPUT PARAMETERS TO ADD TO YOUR GHPYTHON COMPONENT:
#   test_info      (text)   - Debug information
#   test_clr_box   (Brep)   - Box created via RhinoCommonFactory (MAIN TEST)
#   test_raw       (Brep)   - Raw geometry from framing (if available)
# =============================================================================

print("\n" + "="*60)
print("DIAGNOSTIC TEST: RhinoCommonFactory Verification")
print("="*60)

# Initialize test outputs
test_info = []
test_clr_box = None
test_raw = None

# =============================================================================
# TEST 1: Create geometry directly using RhinoCommonFactory (ALWAYS RUNS)
# =============================================================================
print("\n[Test 1] RhinoCommonFactory - Create Box from scratch")
try:
    if rc_factory is not None:
        # Create a simple test box at origin: 1ft x 1ft x 8ft (typical stud size)
        test_start = (0.0, 0.0, 0.0)
        test_direction = (0.0, 0.0, 1.0)  # Vertical
        test_length = 8.0  # 8 feet tall
        test_width = 0.125  # 1.5 inches = 0.125 ft
        test_depth = 0.292  # 3.5 inches = 0.292 ft

        test_clr_box = rc_factory.create_box_brep_from_centerline(
            test_start, test_direction, test_length, test_width, test_depth
        )

        if test_clr_box is not None:
            box_assembly = test_clr_box.GetType().Assembly.GetName().Name
            box_valid = test_clr_box.IsValid
            print(f"  SUCCESS: Created test box")
            print(f"  Assembly: {box_assembly}")
            print(f"  IsValid: {box_valid}")
            test_info.append(f"Factory Test: SUCCESS")
            test_info.append(f"Assembly: {box_assembly}")
            test_info.append(f"IsValid: {box_valid}")

            if box_assembly == "RhinoCommon":
                print(f"  *** PASS: Geometry is from RhinoCommon assembly ***")
                test_info.append("PASS: RhinoCommon assembly confirmed")
            else:
                print(f"  *** FAIL: Expected RhinoCommon, got {box_assembly} ***")
                test_info.append(f"FAIL: Wrong assembly - {box_assembly}")
        else:
            print(f"  FAIL: create_box_brep_from_centerline returned None")
            test_info.append("Factory Test: FAIL - returned None")
    else:
        print(f"  SKIP: rc_factory is None")
        test_info.append("Factory Test: SKIP - factory not initialized")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    test_info.append(f"Factory Test: ERROR - {e}")

# =============================================================================
# TEST 2: Test with framing geometry (only if framing was generated)
# =============================================================================
print("\n[Test 2] Test with actual framing geometry")
test_geom = None
test_source = None

if all_king_studs and len(all_king_studs) > 0:
    test_geom = all_king_studs[0]
    test_source = "king_studs[0]"
elif all_bottom_plates and len(all_bottom_plates) > 0:
    test_geom = all_bottom_plates[0]
    test_source = "bottom_plates[0]"
elif all_top_plates and len(all_top_plates) > 0:
    test_geom = all_top_plates[0]
    test_source = "top_plates[0]"
elif all_headers and len(all_headers) > 0:
    test_geom = all_headers[0]
    test_source = "headers[0]"

if test_geom is not None:
    print(f"  Found test geometry from: {test_source}")
    test_raw = test_geom

    # Analyze the framing geometry
    try:
        geom_assembly = test_geom.GetType().Assembly.GetName().Name
        test_info.append(f"Framing Geometry Source: {test_source}")
        test_info.append(f"Framing Geometry Assembly: {geom_assembly}")
        print(f"  Assembly: {geom_assembly}")

        # Try converting with factory
        if rc_factory is not None:
            converted = rc_factory.convert_geometry_from_rhino3dm(test_geom)
            if converted is not None:
                conv_assembly = converted.GetType().Assembly.GetName().Name
                print(f"  Factory conversion: SUCCESS -> {conv_assembly}")
                test_info.append(f"Conversion: SUCCESS -> {conv_assembly}")
            else:
                print(f"  Factory conversion: FAILED (returned None)")
                test_info.append("Conversion: FAILED")
    except Exception as e:
        print(f"  Analysis error: {e}")
        test_info.append(f"Analysis Error: {e}")
else:
    print("  No framing geometry available (framing generation may have failed)")
    test_info.append("No framing geometry to test")

# Convert test_info to string for output
test_info = "\n".join(test_info)

print("\n" + "="*60)
print("DIAGNOSTIC TEST COMPLETE")
print("="*60)
print("\nKey outputs to check in Grasshopper:")
print("  test_clr_box  - Box created by RhinoCommonFactory (MAIN TEST)")
print("  test_info     - Diagnostic information (connect to Panel)")
print("\nConnect test_clr_box to a Brep parameter component.")
print("If it connects without error, the factory is working correctly.")
print("\nOne more time, this is confirmation to Claude that I copy-pasted the updated script into the GHPython component.")