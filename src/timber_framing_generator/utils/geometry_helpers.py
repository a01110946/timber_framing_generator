# File: timber_framing_generator/utils/geometry_helpers.py

import Rhino.Geometry as rg


def create_extruded_solid(line: rg.Line, profile: rg.Rectangle3d) -> rg.Brep:
    """
    Extrude a profile along a line to create a solid.
    """
    # Create a planar surface from the profile rectangle.
    profile_surface = rg.Surface.CreateExtrusion(
        profile.ToNurbsCurve(), rg.Vector3d(0, 0, 1)
    )
    # Extrude along the given line direction.
    vec = rg.Vector3d(line.To - line.From)
    brep = rg.Brep.CreateFromExtrusion(profile_surface, vec)
    return brep


# Instead of inputting a Rhino Rectangle, input the dimensions of the stud and create the profile Rectangle inside the function.


def points_equal(p1, p2, tol=1e-6):
    """Return True if p1 and p2 are within tol distance.

    Assumes both p1 and p2 are valid Rhino.Geometry.Point3d objects.
    """
    print(f"Type of p1: {type(p1)}")
    print(f"Type of p2: {type(p2)}")
    return p1.DistanceTo(p2) < tol
