from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union, Literal
from datetime import datetime

class Point3D(BaseModel):
    x: float
    y: float
    z: float

class Plane(BaseModel):
    origin: Point3D
    x_axis: Point3D
    y_axis: Point3D
    z_axis: Point3D

class OpeningModel(BaseModel):
    opening_type: Literal["door", "window"]
    start_u_coordinate: float
    rough_width: float
    rough_height: float
    base_elevation_relative_to_wall_base: float

class WallDataInput(BaseModel):
    wall_type: str
    wall_base_elevation: float
    wall_top_elevation: float
    wall_length: float
    wall_height: float
    is_exterior_wall: bool
    openings: List[OpeningModel] = []

class WallAnalysisJob(BaseModel):
    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    wall_data: WallDataInput
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None