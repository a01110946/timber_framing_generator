# File: src/wall_data/wall_helpers.py

from Autodesk.Revit import DB
import Rhino.Geometry as rg


def compute_wall_base_elevation(revit_wall, doc) -> float:
    """
    Computes the wall's base elevation based on the wall's base level and base offset.
    
    Args:
        revit_wall: Revit wall element
        doc: Revit document
        
    Returns:
        Base elevation value in feet
        
    Raises:
        ValueError: If base level cannot be determined
    """
    try:
        # Get base constraint parameter
        base_level_param = revit_wall.get_Parameter(
            DB.BuiltInParameter.WALL_BASE_CONSTRAINT
        )

        if base_level_param:
            base_level_id = base_level_param.AsElementId()
            base_level = (
                doc.GetElement(base_level_id)
                if base_level_id != DB.ElementId.InvalidElementId
                else None
            )
        else:
            base_level = None
            # Try to get level from LevelId
            if hasattr(revit_wall, "LevelId"):
                base_level = doc.GetElement(revit_wall.LevelId)

        # Get base offset parameter
        base_offset_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET)
        base_offset = base_offset_param.AsDouble() if base_offset_param else 0.0

        base_elevation = (base_level.Elevation if base_level else 0.0) + base_offset
        return base_elevation
        
    except Exception as e:
        print(f"ERROR: Failed to compute wall base elevation for Revit wall: {revit_wall.Id}")
        print(f"ERROR details: {type(e).__name__}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        
        # Here's where you need to make a decision:
        # 1. Return None (will require handling None values)
        # 2. Return a default value (might cause subtle bugs)
        # 3. Re-raise the exception (will stop execution)
        
        # For now, re-raise the exception for clearer error messages
        raise


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
            rg.Point3d(end_pt.X, end_pt.Y, end_pt.Z),
        )
    elif isinstance(location_curve, DB.Arc):
        return Convert.Geometry.ToArcCurve(location_curve)
    else:
        return Convert.Geometry.ToCurve(location_curve)


def get_wall_base_plane(
    revit_wall, base_curve: rg.Curve, base_elevation: float
) -> rg.Plane:
    """
    Computes the wall's base plane using the base curve and base elevation.
    Forces the vertical direction to be the world Z axis.

    The origin is set at the wall's X,Y position and the absolute Z elevation
    from base_elevation (which is level elevation + offset).

    Note: revit_wall.Flipped indicates which face is exterior, NOT the wall direction.
    We always use the curve endpoints in their natural order to match get_wall_base_curve.
    """
    # Get the wall's location curve.
    location_curve = revit_wall.Location.Curve

    # Always use endpoints in natural order (consistent with get_wall_base_curve)
    # The Flipped property is about exterior face orientation, not curve direction
    start_point = location_curve.GetEndPoint(0)
    end_point = location_curve.GetEndPoint(1)

    # FIX: Use base_elevation directly for Z coordinate.
    # The base_elevation is already the absolute Z (level elevation + offset).
    # Previously we were adding start_point.Z + base_elevation, which could
    # double-count the elevation if start_point.Z was already at the level Z.
    origin = rg.Point3d(start_point.X, start_point.Y, base_elevation)
    x_dir = rg.Vector3d(
        end_point.X - start_point.X,
        end_point.Y - start_point.Y,
        end_point.Z - start_point.Z,
    )
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
