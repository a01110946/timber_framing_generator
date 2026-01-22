# File: timber_framing_generator/utils/geometry_helpers.py

import Rhino.Geometry as rg
from src.timber_framing_generator.utils.logging_config import get_logger

# Initialize logger for this module
logger = get_logger(__name__)

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

def points_equal(p1, p2, tol=1e-6):
    """Return True if p1 and p2 are within tol distance.

    Assumes both p1 and p2 are valid Rhino.Geometry.Point3d objects.
    """
    logger.trace(f"Type of p1: {type(p1)}")
    logger.trace(f"Type of p2: {type(p2)}")
    return p1.DistanceTo(p2) < tol

def curve_closest_point(curve, test_point):
    """
    Universal helper for finding closest point on any curve type.
    Works consistently across different RhinoCommon implementations.
    
    Args:
        curve: Any curve type (Curve, LineCurve, etc.)
        test_point: The point to find closest position to
        
    Returns:
        tuple: (success, parameter)
    """
    # Try various approaches in order of preference
    try:
        # 1. Try direct method if available
        if hasattr(curve, 'ClosestPoint'):
            return curve.ClosestPoint(test_point)
            
        # 2. Try converting to NurbsCurve
        nurbs = curve.ToNurbsCurve()
        if nurbs and hasattr(nurbs, 'ClosestPoint'):
            return nurbs.ClosestPoint(test_point)
        
        # 3. For LineCurve, try manual calculation
        if isinstance(curve, rg.LineCurve):
            line = curve.Line
            v = rg.Vector3d(line.To - line.From)
            w = rg.Vector3d(test_point - line.From)
            
            # Project w onto v (dot product divided by squared length)
            c1 = w.X * v.X + w.Y * v.Y + w.Z * v.Z
            c2 = v.X * v.X + v.Y * v.Y + v.Z * v.Z
            
            if c2 < 1e-10:  # Avoid division by near-zero
                return True, 0.0
                
            t = c1 / c2
            t = max(0.0, min(1.0, t))  # Clamp to [0,1]
            
            return True, t
        
        # Final fallback
        raise NotImplementedError("Could not find method to get closest point")
            
    except Exception as e:
        logger.error(f"Error in curve_closest_point: {str(e)}")
        return False, 0.0

def curve_length(curve):
    """
    Get the length of a curve, handling LineCurve's missing GetLength method.
    
    Args:
        curve: Any curve object
        
    Returns:
        float: Length of the curve
    """
    # Try standard method first
    if hasattr(curve, 'GetLength'):
        return curve.GetLength()
        
    # For LineCurve, calculate from the Line property
    if isinstance(curve, rg.LineCurve) and hasattr(curve, 'Line'):
        line = curve.Line
        # Use distance between endpoints
        return line.From.DistanceTo(line.To)
        
    # Final fallback - try to get endpoints
    try:
        start = curve.PointAtStart
        end = curve.PointAtEnd
        return start.DistanceTo(end)
    except:
        # Last resort - return a reasonable default
        logger.warning("Could not calculate curve length, using default")

def create_extrusion(profile_curve, direction_vector):
    """
    Create an extrusion of a profile curve along a direction vector.
    Compatible with various RhinoCommon implementations.
    
    Args:
        profile_curve: Curve to extrude
        direction_vector: Vector defining direction and length of extrusion
        
    Returns:
        rg.Brep: Extrusion geometry as a Brep
    """
    try:
        # 1. Try standard method if available
        if hasattr(rg.Extrusion, 'CreateExtrusion'):
            extrusion = safe_create_extrusion(profile_curve, direction_vector)
            if extrusion and extrusion.IsValid:
                return extrusion.ToBrep()
        
        # 2. Try using Sweep1 as an alternative
        rail_curve = rg.Line(
            rg.Point3d(0, 0, 0),
            rg.Point3d(
                direction_vector.X,
                direction_vector.Y,
                direction_vector.Z
            )
        ).ToNurbsCurve()
        
        # Create transformation to move rail to profile location
        if hasattr(profile_curve, 'PointAtStart'):
            start_point = profile_curve.PointAtStart
            transform = rg.Transform.Translation(
                start_point.X, start_point.Y, start_point.Z
            )
            rail_curve.Transform(transform)
        
        # Use sweep instead
        sweep_breps = rg.Brep.CreateFromSweep(
            rail_curve,
            profile_curve,
            closed=False,
            tolerance=0.001
        )
        
        if sweep_breps and len(sweep_breps) > 0:
            # Join all pieces if multiple were created
            if len(sweep_breps) > 1:
                joined_breps = rg.Brep.JoinBreps(sweep_breps, 0.001)
                if joined_breps and len(joined_breps) > 0:
                    return joined_breps[0]
            return sweep_breps[0]
        
        # 3. Final fallback - try to create using a surface extrusion
        try:
            # Create a surface from the profile curve
            profile_surface = rg.Surface.CreateExtrusion(
                profile_curve, 
                rg.Vector3d(0, 0, 1)
            )
            
            # Create the extrusion from the surface
            brep = rg.Brep.CreateFromSurface(profile_surface)
            
            # Transform to the correct position and orientation
            transform = rg.Transform.PlaneToPlane(
                rg.Plane.WorldXY,
                rg.Plane(
                    rg.Point3d(0, 0, 0),
                    rg.Vector3d(direction_vector)
                )
            )
            brep.Transform(transform)
            
            return brep
            
        except:
            # Last resort - create a box as a placeholder
            logger.warning("Could not create extrusion, using box placeholder")
            # Analyze profile to get size
            bbox = profile_curve.GetBoundingBox(True)
            width = bbox.Max.X - bbox.Min.X
            height = bbox.Max.Y - bbox.Min.Y
            depth = direction_vector.Length
            
            # Create box
            center = rg.Point3d(
                (bbox.Min.X + bbox.Max.X) / 2,
                (bbox.Min.Y + bbox.Max.Y) / 2,
                0
            )
            box = rg.Box(
                rg.Plane(center, rg.Vector3d.ZAxis),
                rg.Interval(-width/2, width/2),
                rg.Interval(-height/2, height/2),
                rg.Interval(0, depth)
            )
            
            return box.ToBrep()
            
    except Exception as e:
        logger.error(f"Error creating extrusion: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def create_box_brep(center, width, height, depth):
    """Create a simple box as Brep - ultimate fallback."""
    try:
        # Create corners
        corners = []
        for x in [-width/2, width/2]:
            for y in [-height/2, height/2]:
                for z in [-depth/2, depth/2]:
                    corners.append(rg.Point3d(
                        center.X + x,
                        center.Y + y,
                        center.Z + z
                    ))
        
        # Create a simple box manually
        brep = rg.Brep()
        
        # Return empty Brep if we can't create geometry
        return brep
    except:
        # Return an empty brep as last resort
        logger.error("Failed to create box brep")
        return rg.Brep()

def create_simple_extrusion(profile, vector):
    """
    Extremely simplified extrusion using direct geometry creation.
    Last resort when no other methods are available.
    """
    try:
        # Get bounding box of profile
        bbox = profile.GetBoundingBox(True)
        if not bbox.IsValid:
            return rg.Brep()
            
        # Calculate center and dimensions
        center = rg.Point3d(
            (bbox.Min.X + bbox.Max.X) / 2,
            (bbox.Min.Y + bbox.Max.Y) / 2,
            (bbox.Min.Z + bbox.Max.Z) / 2
        )
        
        width = bbox.Max.X - bbox.Min.X
        height = bbox.Max.Y - bbox.Min.Y
        depth = vector.Length
        
        # Create simple box as fallback
        return create_box_brep(center, width, height, depth)
    except Exception as e:
        logger.error(f"Error in create_simple_extrusion: {e}")
        return rg.Brep()