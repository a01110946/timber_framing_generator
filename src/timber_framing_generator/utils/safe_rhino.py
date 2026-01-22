# File: src/timber_framing_generator/utils/safe_rhino.py

import Rhino.Geometry as rg
from src.timber_framing_generator.utils.geometry_helpers import (
    curve_length, curve_closest_point, create_extrusion, create_simple_extrusion
)

def safe_get_length(curve):
    """Safely get the length of any curve type."""
    try:
        return curve.GetLength()
    except AttributeError:
        return curve_length(curve)

def safe_closest_point(curve, point):
    """Safely get the closest point on any curve type."""
    try:
        return curve.ClosestPoint(point)
    except AttributeError:
        return curve_closest_point(curve, point)

def safe_create_extrusion(profile, vector):
    """Safely create extrusion geometry."""
    try:
        # Try standard method
        if hasattr(rg.Extrusion, 'CreateExtrusion'):
            extrusion = rg.Extrusion.CreateExtrusion(profile, vector)
            if extrusion and extrusion.IsValid:
                return extrusion.ToBrep()
    except:
        pass
        
    # Fallback to simplified geometry
    return create_simple_extrusion(profile, vector)

def safe_get_bounding_box(geometry_object, accurate=True):
    """
    Safely get the bounding box of any geometry object.
    
    Args:
        geometry_object: Any Rhino geometry object
        accurate: Whether to compute an accurate bounding box
        
    Returns:
        rg.BoundingBox: The bounding box of the object, or an empty box if one cannot be computed
    """
    try:
        # Try direct method first
        if hasattr(geometry_object, 'GetBoundingBox'):
            return geometry_object.GetBoundingBox(accurate)
            
        # For objects with control points (like curves)
        if hasattr(geometry_object, 'Points'):
            bbox = rg.BoundingBox.Empty
            for point in geometry_object.Points:
                if hasattr(point, 'Location'):
                    bbox.Union(point.Location)
                elif hasattr(point, 'X') and hasattr(point, 'Y') and hasattr(point, 'Z'):
                    bbox.Union(rg.Point3d(point.X, point.Y, point.Z))
            return bbox
            
        # For line curves
        if hasattr(geometry_object, 'PointAtStart') and hasattr(geometry_object, 'PointAtEnd'):
            bbox = rg.BoundingBox.Empty
            bbox.Union(geometry_object.PointAtStart)
            bbox.Union(geometry_object.PointAtEnd)
            return bbox
            
        # For other geometry, try to get extreme points
        if hasattr(geometry_object, 'GetBoundingBox'):
            return geometry_object.GetBoundingBox(accurate)
            
    except Exception as e:
        from ..utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.warning(f"Error getting bounding box: {str(e)}")
        
    # Return empty box if all methods fail
    return rg.BoundingBox.Empty

def safe_add_brep(brep_object):
    """
    Safely convert an object to Brep if needed.
    
    This function handles various object types and tries multiple approaches
    to return a valid Brep, including direct casting and conversion methods.
    """
    if brep_object is None:
        return None
    
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        # Case 1: Already a Brep - just return it
        if isinstance(brep_object, rg.Brep):
            return brep_object
            
        # Case 2: It's an Extrusion - convert to Brep
        if isinstance(brep_object, rg.Extrusion):
            return brep_object.ToBrep()
            
        # Case 3: It's a Curve - try to create a surface
        if isinstance(brep_object, rg.Curve):
            try:
                # Try to create a surface if it's a closed curve
                if brep_object.IsClosed:
                    surface = rg.Brep.CreatePlanarBreps(brep_object)
                    if surface and len(surface) > 0:
                        return surface[0]
            except Exception as e:
                logger.warning(f"Failed to create surface from curve: {str(e)}")
        
        # Case 4: It has a ToBrep method - use it
        if hasattr(brep_object, 'ToBrep') and callable(getattr(brep_object, 'ToBrep')):
            try:
                return brep_object.ToBrep()
            except Exception as e:
                logger.warning(f"ToBrep method failed: {str(e)}")
        
        # Case 5: Has an ExternalBoundary property (like Surface)
        if hasattr(brep_object, 'ToBrep') == False and hasattr(brep_object, 'IsSurface') and brep_object.IsSurface:
            try:
                return rg.Brep.CreateFromSurface(brep_object)
            except Exception as e:
                logger.warning(f"Failed to create Brep from surface: {str(e)}")
        
        # Case 6: Unknown type - log and return None
        logger.warning(f"Cannot convert {type(brep_object)} to Brep - no conversion method available")
        return brep_object  # Return the original object as a fallback
        
    except Exception as e:
        logger.warning(f"Error in safe_add_brep: {str(e)}")
        return brep_object  # Return the original object as a last resort

def is_valid_geometry(geom_obj):
    """Check if a geometry object is valid."""
    if geom_obj is None:
        return False

    try:
        if hasattr(geom_obj, 'IsValid'):
            return geom_obj.IsValid
        return True  # If no IsValid property, assume it's valid
    except:
        return False


def safe_to_brep_if_needed(geometry_object):
    """
    Convert geometry to Brep only if needed.

    If the object is already a Brep, returns it directly without calling ToBrep().
    If it has a ToBrep() method (like Extrusion), calls it.
    Otherwise returns None.

    This function prevents the common error of calling .ToBrep() on an object
    that is already a Brep (which raises "Brep object has no attribute ToBrep").

    Args:
        geometry_object: Rhino geometry object (Brep, Extrusion, Box, etc.)

    Returns:
        rg.Brep: Valid Brep object, or None if conversion failed

    Example:
        result = safe_create_extrusion(profile, direction)  # May return Brep or Extrusion
        brep = safe_to_brep_if_needed(result)  # Safely converts to Brep
    """
    if geometry_object is None:
        return None

    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        # Case 1: Already a Brep - return as-is (most common case)
        if isinstance(geometry_object, rg.Brep):
            if geometry_object.IsValid:
                return geometry_object
            else:
                logger.warning("Brep object is invalid")
                return None

        # Case 2: Has ToBrep method (Extrusion, Box, etc.) - use it
        if hasattr(geometry_object, 'ToBrep') and callable(getattr(geometry_object, 'ToBrep')):
            try:
                brep = geometry_object.ToBrep()
                if brep is not None and brep.IsValid:
                    return brep
                else:
                    logger.warning(f"ToBrep() returned invalid result for {type(geometry_object)}")
            except Exception as e:
                logger.warning(f"ToBrep() failed for {type(geometry_object)}: {str(e)}")

        # Case 3: Unknown type - cannot convert
        logger.warning(f"Cannot convert {type(geometry_object)} to Brep")
        return None

    except Exception as e:
        logger.error(f"Error in safe_to_brep_if_needed: {str(e)}")
        return None

def safe_to_brep(brep_object):
    """
    Safely convert an object to a Brep, handling various types and failure cases.
    
    Args:
        brep_object: Object to convert to a Brep
        
    Returns:
        A Rhino.Geometry.Brep object, or None if conversion failed
    """
    # Avoid None inputs
    if brep_object is None:
        return None
        
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        # Case 1: Already a Brep - just return it
        if isinstance(brep_object, rg.Brep):
            return brep_object
            
        # Case 2: It's an Extrusion - convert to Brep
        if isinstance(brep_object, rg.Extrusion):
            try:
                return brep_object.ToBrep()
            except Exception as e:
                logger.warning(f"Extrusion.ToBrep() failed: {str(e)}")
                # Try alternative conversion
                
        # Case 3: It's a Curve - try to create a surface
        if isinstance(brep_object, rg.Curve):
            try:
                # Try to create a surface if it's a closed curve
                if brep_object.IsClosed:
                    surface = rg.Brep.CreatePlanarBreps(brep_object)
                    if surface and len(surface) > 0:
                        return surface[0]
            except Exception as e:
                logger.warning(f"Failed to create surface from curve: {str(e)}")
        
        # Case 4: It has a ToBrep method - use it
        if hasattr(brep_object, 'ToBrep') and callable(getattr(brep_object, 'ToBrep')):
            try:
                return brep_object.ToBrep()
            except Exception as e:
                logger.warning(f"ToBrep method failed: {str(e)}")
        
        # Case 5: Has Surface properties
        if hasattr(brep_object, 'IsSurface') and brep_object.IsSurface:
            try:
                return rg.Brep.CreateFromSurface(brep_object)
            except Exception as e:
                logger.warning(f"Failed to create Brep from surface: {str(e)}")
        
        # Case 6: It's a Box - properly handle conversion
        if isinstance(brep_object, rg.Box):
            try:
                # Create Brep directly from the box corners
                box = brep_object
                corners = box.GetCorners()
                if corners and len(corners) == 8:
                    # Create Brep from box faces
                    brep = rg.Brep()
                    # Bottom face (0,1,2,3)
                    bottom_surface = rg.PlaneSurface.CreateFromCorners(
                        corners[0], corners[1], corners[2], corners[3]
                    )
                    if bottom_surface:
                        brep.Faces.AddFace(bottom_surface)
                    
                    # Top face (4,5,6,7)
                    top_surface = rg.PlaneSurface.CreateFromCorners(
                        corners[4], corners[5], corners[6], corners[7]
                    )
                    if top_surface:
                        brep.Faces.AddFace(top_surface)
                    
                    # Try to create a valid Brep
                    if brep.IsValid:
                        return brep
                    
                    # Fallback: try to create a box from BoundingBox
                    bbox = brep_object.BoundingBox
                    if bbox.IsValid:
                        return rg.Brep.CreateFromBox(bbox)
            except Exception as box_err:
                logger.warning(f"Failed to create Brep from Box: {str(box_err)}")
        
        # Case 7: Unknown type - log and return the original object as fallback
        logger.warning(f"Cannot convert {type(brep_object)} to Brep - no conversion method available")
        return brep_object  # Return the original object as a fallback
        
    except Exception as e:
        logger.error(f"Unexpected error in safe_to_brep: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return None