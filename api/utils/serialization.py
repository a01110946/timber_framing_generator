from typing import Dict, Any, List
from api.models.wall_models import WallDataInput, Point3D

def serialize_point3d(point) -> Dict[str, float]:
    """
    Serialize a Rhino.Geometry.Point3d to a dictionary.
    """
    return {
        "x": point.X,
        "y": point.Y,
        "z": point.Z
    }

def serialize_plane(plane) -> Dict[str, Any]:
    """
    Serialize a Rhino.Geometry.Plane to a dictionary.
    """
    return {
        "origin": serialize_point3d(plane.Origin),
        "x_axis": serialize_point3d(plane.XAxis),
        "y_axis": serialize_point3d(plane.YAxis),
        "z_axis": serialize_point3d(plane.ZAxis)
    }

def create_mock_wall_analysis(wall_data: WallDataInput) -> Dict[str, Any]:
    """
    Create a mock wall analysis result for testing.
    
    In production, this would call your actual analysis code.
    """
    # Create a mock base plane
    base_plane = {
        "origin": {"x": 0, "y": 0, "z": wall_data.wall_base_elevation},
        "x_axis": {"x": 1, "y": 0, "z": 0},
        "y_axis": {"x": 0, "y": 0, "z": 1},
        "z_axis": {"x": 0, "y": 1, "z": 0}
    }
    
    # Create mock cells
    cells = [
        {
            "cell_type": "WBC",
            "u_start": 0,
            "u_end": wall_data.wall_length,
            "v_start": 0,
            "v_end": wall_data.wall_height,
            "corner_points": [
                {"x": 0, "y": 0, "z": wall_data.wall_base_elevation},
                {"x": wall_data.wall_length, "y": 0, "z": wall_data.wall_base_elevation},
                {"x": wall_data.wall_length, "y": 0, "z": wall_data.wall_top_elevation},
                {"x": 0, "y": 0, "z": wall_data.wall_top_elevation}
            ]
        }
    ]
    
    # Add cells for each opening
    for opening in wall_data.openings:
        cells.append({
            "cell_type": "OC",
            "opening_type": opening.opening_type,
            "u_start": opening.start_u_coordinate,
            "u_end": opening.start_u_coordinate + opening.rough_width,
            "v_start": opening.base_elevation_relative_to_wall_base,
            "v_end": opening.base_elevation_relative_to_wall_base + opening.rough_height,
            "corner_points": [
                {"x": opening.start_u_coordinate, "y": 0, "z": wall_data.wall_base_elevation + opening.base_elevation_relative_to_wall_base},
                {"x": opening.start_u_coordinate + opening.rough_width, "y": 0, "z": wall_data.wall_base_elevation + opening.base_elevation_relative_to_wall_base},
                {"x": opening.start_u_coordinate + opening.rough_width, "y": 0, "z": wall_data.wall_base_elevation + opening.base_elevation_relative_to_wall_base + opening.rough_height},
                {"x": opening.start_u_coordinate, "y": 0, "z": wall_data.wall_base_elevation + opening.base_elevation_relative_to_wall_base + opening.rough_height}
            ]
        })
    
    return {
        "wall_data": wall_data.dict(),
        "base_plane": base_plane,
        "cells": cells,
        "analysis_timestamp": "2023-09-20T12:34:56Z"
    }