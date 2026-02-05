# File: src/timber_framing_generator/utils/geometry_factory.py
"""
RhinoCommon Geometry Factory for Grasshopper Integration.

This module provides a factory class that creates RhinoCommon geometry
via CLR reflection, bypassing the rhino3dm package which creates
incompatible Rhino3dmIO geometry.

The Problem:
    - rhino3dm Python package creates geometry from "Rhino3dmIO" assembly
    - Grasshopper expects geometry from "RhinoCommon" assembly
    - Despite identical type names, CLR treats them as incompatible
    - Results in "Data conversion failed from Goo to Brep" errors

The Solution:
    - Use CLR reflection to find the RhinoCommon assembly
    - Create geometry directly using Activator.CreateInstance
    - Extract coordinates as Python floats to "launder" through assembly boundary

Usage in GHPython:
    from src.timber_framing_generator.utils.geometry_factory import get_factory

    factory = get_factory()
    point = factory.create_point3d(1.0, 2.0, 3.0)
    brep = factory.create_box_brep_from_centerline(start, direction, length, width, depth)

See Also:
    - docs/ai/ai-geometry-assembly-solution.md
    - docs/ai/ai-grasshopper-rhino-patterns.md
"""

from typing import Tuple, List, Optional, Any, Union

# Type aliases for clarity
Point3DLike = Union[Tuple[float, float, float], Any]
Vector3DLike = Union[Tuple[float, float, float], Any]


class RhinoCommonFactory:
    """
    Factory for creating RhinoCommon geometry directly via CLR reflection.

    This bypasses the rhino3dm package which creates Rhino3dmIO geometry
    that Grasshopper cannot use. All geometry created through this factory
    is guaranteed to be from the RhinoCommon assembly.

    Singleton Pattern:
        Only one instance is created per process. Use get_factory() to obtain.

    Example:
        factory = RhinoCommonFactory()
        pt = factory.create_point3d(0, 0, 0)
        brep = factory.create_box_brep_from_centerline((0,0,0), (0,0,1), 8.0, 0.125, 0.292)
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
            "Rhino.Geometry.Circle",
            "Rhino.Geometry.Arc",
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

    def create_plane(self, origin: Point3DLike, x_axis: Vector3DLike, y_axis: Vector3DLike):
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
        elif hasattr(origin, 'X'):
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

    def create_line(self, start_point: Point3DLike, end_point: Point3DLike):
        """
        Create a RhinoCommon Line.

        Args:
            start_point: Point3d or (x, y, z) tuple
            end_point: Point3d or (x, y, z) tuple
        """
        if isinstance(start_point, (tuple, list)):
            start_point = self.create_point3d(*start_point)
        elif hasattr(start_point, 'X'):
            start_point = self.create_point3d(
                float(start_point.X), float(start_point.Y), float(start_point.Z)
            )

        if isinstance(end_point, (tuple, list)):
            end_point = self.create_point3d(*end_point)
        elif hasattr(end_point, 'X'):
            end_point = self.create_point3d(
                float(end_point.X), float(end_point.Y), float(end_point.Z)
            )

        return self._create_instance("Line", start_point, end_point)

    def create_line_curve(self, start_point: Point3DLike, end_point: Point3DLike):
        """
        Create a RhinoCommon LineCurve.

        Args:
            start_point: Point3d or (x, y, z) tuple
            end_point: Point3d or (x, y, z) tuple
        """
        line = self.create_line(start_point, end_point)
        return self._create_instance("LineCurve", line)

    def create_polyline_curve(self, points: List[Point3DLike]):
        """
        Create a RhinoCommon PolylineCurve from a list of points.

        Args:
            points: List of Point3d or (x, y, z) tuples

        Returns:
            PolylineCurve from RhinoCommon assembly
        """
        if not points or len(points) < 2:
            return None

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

        # Create Polyline by adding points one at a time
        # (avoids constructor overload issues with Activator.CreateInstance)
        polyline = self._create_instance("Polyline")
        for pt in rc_points:
            polyline.Add(pt)

        # Create PolylineCurve from Polyline
        return self._create_instance("PolylineCurve", polyline)

    def create_circle(
        self,
        center: Point3DLike,
        radius: float,
        normal: Vector3DLike = (0, 0, 1)
    ):
        """
        Create a RhinoCommon Circle as a NurbsCurve.

        Args:
            center: Center point as Point3d or (x, y, z) tuple
            radius: Circle radius
            normal: Normal vector for circle plane (default: Z-up)

        Returns:
            NurbsCurve representing the circle from RhinoCommon assembly
        """
        from System.Reflection import BindingFlags

        # Convert center to Point3d
        if isinstance(center, (tuple, list)):
            center_pt = self.create_point3d(*center)
        elif hasattr(center, 'X'):
            center_pt = self.create_point3d(
                float(center.X), float(center.Y), float(center.Z)
            )
        else:
            center_pt = center

        # Convert normal to Vector3d
        if isinstance(normal, (tuple, list)):
            normal_vec = self.create_vector3d(*normal)
        elif hasattr(normal, 'X'):
            normal_vec = self.create_vector3d(
                float(normal.X), float(normal.Y), float(normal.Z)
            )
        else:
            normal_vec = normal

        # Create plane from center and normal
        # Use Plane(origin, normal) constructor
        plane = self._create_instance("Plane", center_pt, normal_vec)

        # Get Circle type and create circle
        Circle_Type = self._get_type("Circle")
        if Circle_Type is None:
            # Fallback: cache it
            self._types_cache["Circle"] = self._rc_assembly.GetType("Rhino.Geometry.Circle")
            Circle_Type = self._types_cache["Circle"]

        # Create Circle(plane, radius)
        circle = self._create_instance("Circle", plane, float(radius))

        # Convert to NurbsCurve for output
        try:
            return circle.ToNurbsCurve()
        except Exception as e:
            print(f"create_circle error converting to NurbsCurve: {e}")
            return None

    def create_interval(self, t0: float, t1: float):
        """Create a RhinoCommon Interval."""
        return self._create_instance("Interval", float(t0), float(t1))

    def create_rectangle3d(self, plane, width: float, height: float):
        """
        Create a RhinoCommon Rectangle3d centered on a plane.

        Args:
            plane: Plane or origin point (will use XY axes if point)
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
            origin = self.create_point3d(
                float(plane.Origin.X), float(plane.Origin.Y), float(plane.Origin.Z)
            )
            x_axis = self.create_vector3d(
                float(plane.XAxis.X), float(plane.XAxis.Y), float(plane.XAxis.Z)
            )
            y_axis = self.create_vector3d(
                float(plane.YAxis.X), float(plane.YAxis.Y), float(plane.YAxis.Z)
            )
            plane = self._create_instance("Plane", origin, x_axis, y_axis)

        # Create intervals for width and height (centered)
        x_interval = self.create_interval(-float(width) / 2.0, float(width) / 2.0)
        y_interval = self.create_interval(-float(height) / 2.0, float(height) / 2.0)

        return self._create_instance("Rectangle3d", plane, x_interval, y_interval)

    def create_bounding_box(self, min_point: Point3DLike, max_point: Point3DLike):
        """
        Create a RhinoCommon BoundingBox.

        Args:
            min_point: Point3d or (x, y, z) tuple for min corner
            max_point: Point3d or (x, y, z) tuple for max corner
        """
        if isinstance(min_point, (tuple, list)):
            min_point = self.create_point3d(*min_point)
        elif hasattr(min_point, 'X'):
            min_point = self.create_point3d(
                float(min_point.X), float(min_point.Y), float(min_point.Z)
            )

        if isinstance(max_point, (tuple, list)):
            max_point = self.create_point3d(*max_point)
        elif hasattr(max_point, 'X'):
            max_point = self.create_point3d(
                float(max_point.X), float(max_point.Y), float(max_point.Z)
            )

        return self._create_instance("BoundingBox", min_point, max_point)

    def create_box(self, bounding_box):
        """Create a RhinoCommon Box from a BoundingBox."""
        return self._create_instance("Box", bounding_box)

    # =========================================================================
    # Surface and Curve Methods
    # =========================================================================

    def create_surface_from_corners(self, p1, p2, p3, p4):
        """
        Create a RhinoCommon NurbsSurface from 4 corner points.

        Uses NurbsSurface.CreateFromCorners static method via reflection.

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
            return None

        try:
            # Use reflection to invoke the static CreateFromCorners method
            method_info = RC_NurbsSurface.GetMethod(
                "CreateFromCorners",
                BindingFlags.Public | BindingFlags.Static,
                None,
                [self._get_type("Point3d")] * 4,
                None
            )

            if method_info is not None:
                result = method_info.Invoke(None, corners)
                return result
            else:
                # Try direct call (works in some environments)
                return RC_NurbsSurface.CreateFromCorners(
                    corners[0], corners[1], corners[2], corners[3]
                )
        except Exception as e:
            print(f"create_surface_from_corners error: {e}")
            return None

    def get_boundary_curves_from_surface(self, surface):
        """
        Extract boundary curves from a surface.

        Args:
            surface: NurbsSurface from RhinoCommon

        Returns:
            Joined boundary curve, or None
        """
        if surface is None:
            return None

        try:
            brep = surface.ToBrep()
            if brep is not None:
                edges = brep.Edges
                if edges is not None and edges.Count > 0:
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

                            join_methods = RC_Curve.GetMethods(
                                BindingFlags.Public | BindingFlags.Static
                            )
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

                        return edge_curves[0] if edge_curves else None

        except Exception as e:
            print(f"get_boundary_curves_from_surface error: {e}")

        return None

    # =========================================================================
    # Sheathing/Surface Geometry Creation
    # =========================================================================

    def create_planar_brep_from_corners(
        self,
        corners: List[Point3DLike]
    ) -> Optional[Any]:
        """
        Create a planar Brep from 4 corner points.

        Args:
            corners: List of 4 (x, y, z) tuples in order (counter-clockwise)

        Returns:
            RhinoCommon Brep or None if creation fails
        """
        if len(corners) != 4:
            return None

        # Create NurbsSurface from corners
        surface = self.create_surface_from_corners(
            corners[0], corners[1], corners[2], corners[3]
        )

        if surface is None:
            return None

        # Convert to Brep
        try:
            return surface.ToBrep()
        except Exception as e:
            print(f"create_planar_brep_from_corners error: {e}")
            return None

    def extrude_brep(
        self,
        brep: Any,
        direction: Tuple[float, float, float]
    ) -> Optional[Any]:
        """
        Extrude a planar Brep along a direction vector to create a solid.

        Args:
            brep: RhinoCommon Brep (planar surface)
            direction: (x, y, z) extrusion vector

        Returns:
            RhinoCommon Brep (solid) or None if extrusion fails
        """
        if brep is None:
            return None

        from System.Reflection import BindingFlags

        try:
            # Get first face of brep
            if not hasattr(brep, 'Faces') or brep.Faces.Count == 0:
                return None

            face = brep.Faces[0]

            # Create direction vector
            vec = self.create_vector3d(*direction)

            # Try to create extrusion from face
            # Use Surface.CreateExtrusion(direction, capped)
            RC_Brep = self._get_type("Brep")

            # Get the underlying surface
            srf = face.UnderlyingSurface()
            if srf is None:
                return None

            # Use Brep.CreateFromSurface and then extrusion approach
            # Alternative: Create box from bounding box of extruded corners

            # Get corner points of face
            corners = []
            edge_curves = []
            for i in range(brep.Edges.Count):
                edge = brep.Edges[i]
                start_pt = edge.PointAtStart
                corners.append((float(start_pt.X), float(start_pt.Y), float(start_pt.Z)))

            if len(corners) < 4:
                return None

            # Create extruded corners
            dx, dy, dz = direction
            extruded_corners = []
            for cx, cy, cz in corners[:4]:
                extruded_corners.append((cx + dx, cy + dy, cz + dz))

            # Create solid from 8 corners using bounding box approach
            all_corners = corners[:4] + extruded_corners
            min_x = min(c[0] for c in all_corners)
            min_y = min(c[1] for c in all_corners)
            min_z = min(c[2] for c in all_corners)
            max_x = max(c[0] for c in all_corners)
            max_y = max(c[1] for c in all_corners)
            max_z = max(c[2] for c in all_corners)

            # This is a simplified approach - creates axis-aligned box
            # For angled extrusions, we'd need more complex logic
            bbox = self.create_bounding_box(
                (min_x, min_y, min_z),
                (max_x, max_y, max_z)
            )
            box = self.create_box(bbox)
            return box.ToBrep()

        except Exception as e:
            print(f"extrude_brep error: {e}")
            return None

    def create_box_from_corners_and_thickness(
        self,
        corners: List[Tuple[float, float, float]],
        extrusion_vector: Tuple[float, float, float]
    ) -> Optional[Any]:
        """
        Create a box Brep from 4 corner points and an extrusion vector.

        This is more reliable than extrude_brep for creating sheathing panels.

        Args:
            corners: 4 corner points of the base face
            extrusion_vector: Vector defining thickness direction and magnitude

        Returns:
            RhinoCommon Brep or None
        """
        if len(corners) != 4:
            return None

        dx, dy, dz = extrusion_vector

        # Create all 8 corners
        all_corners = list(corners)
        for cx, cy, cz in corners:
            all_corners.append((cx + dx, cy + dy, cz + dz))

        # Find bounding box
        min_x = min(c[0] for c in all_corners)
        min_y = min(c[1] for c in all_corners)
        min_z = min(c[2] for c in all_corners)
        max_x = max(c[0] for c in all_corners)
        max_y = max(c[1] for c in all_corners)
        max_z = max(c[2] for c in all_corners)

        bbox = self.create_bounding_box(
            (min_x, min_y, min_z),
            (max_x, max_y, max_z)
        )
        box = self.create_box(bbox)
        return box.ToBrep()

    def boolean_difference(
        self,
        brep_a: Any,
        brep_b: Any,
        tolerance: float = 0.001
    ) -> Optional[Any]:
        """
        Boolean difference: brep_a - brep_b.

        Args:
            brep_a: Base Brep
            brep_b: Brep to subtract
            tolerance: Boolean operation tolerance

        Returns:
            Result Brep or None if operation fails
        """
        if brep_a is None or brep_b is None:
            return brep_a

        from System.Reflection import BindingFlags
        from System import Array

        try:
            RC_Brep = self._get_type("Brep")
            if RC_Brep is None:
                return brep_a

            # Get static CreateBooleanDifference method
            # Signature: CreateBooleanDifference(Brep, Brep, double)
            methods = RC_Brep.GetMethods(BindingFlags.Public | BindingFlags.Static)

            for method in methods:
                if method.Name == "CreateBooleanDifference":
                    params = method.GetParameters()
                    # Looking for (Brep, Brep, double) overload
                    if len(params) == 3:
                        param_types = [p.ParameterType.Name for p in params]
                        if param_types == ["Brep", "Brep", "Double"]:
                            results = method.Invoke(None, [brep_a, brep_b, float(tolerance)])
                            if results is not None and len(results) > 0:
                                return results[0]
                            break

            # If method not found or failed, return original
            return brep_a

        except Exception as e:
            print(f"boolean_difference error: {e}")
            return brep_a

    def boolean_difference_multiple(
        self,
        brep_base: Any,
        breps_to_subtract: List[Any],
        tolerance: float = 0.001
    ) -> Optional[Any]:
        """
        Boolean difference with multiple subtraction breps.

        Args:
            brep_base: Base Brep
            breps_to_subtract: List of Breps to subtract
            tolerance: Boolean operation tolerance

        Returns:
            Result Brep or original if operation fails
        """
        result = brep_base

        for brep_sub in breps_to_subtract:
            if brep_sub is None:
                continue
            new_result = self.boolean_difference(result, brep_sub, tolerance)
            if new_result is not None:
                result = new_result

        return result

    # =========================================================================
    # Framing-Specific Geometry Creation
    # =========================================================================

    def create_box_brep_from_centerline(
        self,
        start_point: Point3DLike,
        direction: Vector3DLike,
        length: float,
        width: float,
        depth: float,
        wall_x_axis: Optional[Tuple[float, float, float]] = None,
        wall_z_axis: Optional[Tuple[float, float, float]] = None,
    ):
        """
        Create a box Brep from centerline parameters.

        This is the primary method for creating timber/CFS framing elements
        as simple boxes aligned with the centerline.

        Args:
            start_point: Start point of centerline
            direction: Direction vector (will be normalized)
            length: Length along direction
            width: Width perpendicular to direction (W direction in UVW)
            depth: Depth perpendicular to direction and width (U direction)
            wall_x_axis: Optional wall X-axis direction (along wall length)
            wall_z_axis: Optional wall Z-axis direction (wall normal, into wall)

        Returns:
            Brep geometry from RhinoCommon assembly

        Note:
            For horizontal elements (plates, headers, sills), width and depth
            are swapped internally because profile dimensions are defined for
            vertical orientation but horizontal members are "laid flat".
        """
        # Convert inputs to floats
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
        # For vertical elements (studs): perp1=along wall (X-axis), perp2=into wall (Z-axis/normal)
        # For horizontal elements (plates): perp1=into wall (normal), perp2=vertical
        is_vertical = abs(dz) > 0.9

        if is_vertical:
            # Vertical members: use wall direction if available, else fall back to World axes
            if wall_x_axis and wall_z_axis:
                # Use wall-relative axes:
                # Profile width (1.5") = along wall face = wall X-axis
                # Profile depth (3.5") = through-wall thickness = wall Z-axis (normal)
                perp1 = wall_x_axis  # width direction = along wall (U)
                perp2 = wall_z_axis  # depth direction = wall normal (W)
            else:
                # Fall back to hardcoded World axes (legacy behavior)
                perp1 = (1.0, 0.0, 0.0)  # Width perpendicular in X
                perp2 = (0.0, 1.0, 0.0)  # Depth perpendicular in Y
        else:
            # Horizontal members: perp1 = wall normal (in XY plane), perp2 = vertical
            p1x = -dy
            p1y = dx
            p1z = 0.0
            p1_mag = (p1x*p1x + p1y*p1y) ** 0.5
            if p1_mag > 0:
                p1x, p1y = p1x/p1_mag, p1y/p1_mag
            perp1 = (p1x, p1y, p1z)

            # For horizontal elements, perp2 should be vertical (Z direction)
            # Cross direction with perp1 to get perp2
            p2x = dy * p1z - dz * p1y
            p2y = dz * p1x - dx * p1z
            p2z = dx * p1y - dy * p1x
            perp2 = (p2x, p2y, p2z)

        # Profile dimensions for vertical elements (studs, king studs, trimmers, cripples):
        #   - width = 1.5" = visible edge along wall face (what you see from exterior)
        #   - depth = 3.5" = through wall thickness (wall depth)
        #
        # This matches standard framing: stud narrow edge faces out, wide face = wall thickness
        # perp1 = wall_x_axis (along wall face), perp2 = wall_z_axis (wall normal/through wall)
        if is_vertical:
            half_w = width / 2.0  # 1.5"/2 along wall face (visible edge)
            half_d = depth / 2.0  # 3.5"/2 through wall (wall thickness)
        else:
            # Horizontal elements: depth into wall, width vertical
            half_w = depth / 2.0  # depth (3.5") goes into wall
            half_d = width / 2.0  # width (1.5") goes vertical

        corners = []
        for start_end in [(sx, sy, sz), (ex, ey, ez)]:
            px, py, pz = start_end
            for w_sign in [-1, 1]:
                for d_sign in [-1, 1]:
                    cx = px + perp1[0] * half_w * w_sign + perp2[0] * half_d * d_sign
                    cy = py + perp1[1] * half_w * w_sign + perp2[1] * half_d * d_sign
                    cz = pz + perp1[2] * half_w * w_sign + perp2[2] * half_d * d_sign
                    corners.append((cx, cy, cz))

        # Find min/max from corners
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

    def create_brep_from_element_data(self, element_data) -> Optional[Any]:
        """
        Create a Brep from FramingElementData.

        Args:
            element_data: FramingElementData object with centerline and profile info

        Returns:
            Brep geometry from RhinoCommon assembly
        """
        start = element_data.centerline_start
        end = element_data.centerline_end

        # Calculate direction and length
        dx = end.x - start.x
        dy = end.y - start.y
        dz = end.z - start.z
        length = (dx*dx + dy*dy + dz*dz) ** 0.5

        if length < 0.001:
            return None

        direction = (dx/length, dy/length, dz/length)

        return self.create_box_brep_from_centerline(
            start_point=(start.x, start.y, start.z),
            direction=direction,
            length=length,
            width=element_data.profile.width,
            depth=element_data.profile.depth,
        )

    def convert_geometry_from_rhino3dm(self, geom) -> Optional[Any]:
        """
        Convert geometry from Rhino3dmIO assembly to RhinoCommon assembly.

        Extracts the bounding box and recreates as RhinoCommon box.
        While this loses exact shape, it works for box-like framing elements.

        Args:
            geom: Geometry object (likely from Rhino3dmIO)

        Returns:
            Brep from RhinoCommon assembly, or None if conversion fails
        """
        if geom is None:
            return None

        try:
            bbox = geom.GetBoundingBox(True)
            if not bbox.IsValid:
                return None

            min_pt = (float(bbox.Min.X), float(bbox.Min.Y), float(bbox.Min.Z))
            max_pt = (float(bbox.Max.X), float(bbox.Max.Y), float(bbox.Max.Z))

            rc_bbox = self.create_bounding_box(min_pt, max_pt)
            rc_box = self.create_box(rc_bbox)

            return rc_box.ToBrep()
        except Exception as e:
            print(f"convert_geometry_from_rhino3dm error: {e}")
            return None


# =============================================================================
# Module-level convenience functions
# =============================================================================

_factory_instance: Optional[RhinoCommonFactory] = None


def get_factory() -> RhinoCommonFactory:
    """
    Get the singleton RhinoCommonFactory instance.

    Returns:
        RhinoCommonFactory instance

    Raises:
        RuntimeError: If RhinoCommon assembly is not available
    """
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = RhinoCommonFactory()
    return _factory_instance


def is_factory_available() -> bool:
    """
    Check if the RhinoCommonFactory can be initialized.

    Returns:
        True if factory is available, False otherwise
    """
    try:
        get_factory()
        return True
    except:
        return False


def create_point3d(x: float, y: float, z: float):
    """Convenience function to create a Point3d."""
    return get_factory().create_point3d(x, y, z)


def create_vector3d(x: float, y: float, z: float):
    """Convenience function to create a Vector3d."""
    return get_factory().create_vector3d(x, y, z)


def create_box_brep(
    start_point: Point3DLike,
    direction: Vector3DLike,
    length: float,
    width: float,
    depth: float,
    wall_x_axis: Optional[Tuple[float, float, float]] = None,
    wall_z_axis: Optional[Tuple[float, float, float]] = None,
):
    """Convenience function to create a box Brep from centerline."""
    return get_factory().create_box_brep_from_centerline(
        start_point, direction, length, width, depth, wall_x_axis, wall_z_axis
    )
