# File: src/wall_data/wall_helpers.py

from Autodesk.Revit import DB
import Rhino.Geometry as rg

def compute_wall_base_elevation(revit_wall, doc) -> float:
    """
    Computes the wall's base elevation based on the wall's base level and base offset.
    """
    base_level_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT)
    base_offset_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET)
    
    base_level = doc.GetElement(base_level_param.AsElementId()) if base_level_param and base_level_param.AsElementId() != DB.ElementId.InvalidElementId else None
    base_offset = base_offset_param.AsDouble() if base_offset_param else 0.0
    
    return (base_level.Elevation if base_level else 0.0) + base_offset

def get_wall_base_curve(revit_wall) -> rg.Curve:
    """
    Converts the wall's location curve from Revit to a Rhino curve.
    """
    from RhinoInside.Revit import Convert
    location_curve = revit_wall.Location.Curve
    if not isinstance(location_curve, DB.Curve):
        raise TypeError("Wall Location is not a Curve.")
    
    if isinstance(location_curve, DB.Line):
        start_pt = location_curve.GetEndPoint(0)
        end_pt = location_curve.GetEndPoint(1)
        return rg.LineCurve(
            rg.Point3d(start_pt.X, start_pt.Y, start_pt.Z),
            rg.Point3d(end_pt.X, end_pt.Y, end_pt.Z)
        )
    elif isinstance(location_curve, DB.Arc):
        return Convert.Geometry.ToArcCurve(location_curve)
    else:
        return Convert.Geometry.ToCurve(location_curve)

def get_wall_base_plane(revit_wall, base_curve: rg.Curve, base_elevation: float) -> rg.Plane:
    """
    Computes the wall's base plane using the base curve and base elevation.
    Forces the vertical direction to be the world Z axis.
    """
    # Get the wall's location curve.
    if revit_wall.Flipped:
        location_curve = revit_wall.Location.Curve.Flip()
    else:
        location_curve = revit_wall.Location.Curve

    # Use the first endpoint of the location curve.
    start_point = location_curve.GetEndPoint(0)
    # Set the origin to the wall's base elevation.
    origin = rg.Point3d(start_point.X, start_point.Y, start_point.Z + base_elevation)

    # X-axis: direction from start to end of the curve.
    end_point = location_curve.GetEndPoint(1)
    x_dir = rg.Vector3d(end_point.X - start_point.X, end_point.Y - start_point.Y, end_point.Z - start_point.Z)
    if not x_dir.IsZero:
        x_dir.Unitize()
    else:
        x_dir = rg.Vector3d(1, 0, 0)
    
    # Force vertical direction to be the world Z axis.
    y_dir = rg.Vector3d(0, 0, 1)
    # Compute the Z-axis as the cross product to get an orthonormal basis.
    z_dir = rg.Vector3d.CrossProduct(x_dir, y_dir)
    if z_dir.IsZero:
        y_dir = rg.Vector3d(0, 1, 0)
        z_dir = rg.Vector3d.CrossProduct(x_dir, y_dir)
    z_dir.Unitize()
    # Recompute Y for orthonormality.
    y_dir = rg.Vector3d.CrossProduct(z_dir, x_dir)
    y_dir.Unitize()

    return rg.Plane(origin, x_dir, y_dir)
