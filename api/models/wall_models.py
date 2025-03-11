from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional, Union, Literal
from datetime import datetime
import uuid

class Point3D(BaseModel):
    """3D point coordinates."""
    x: float = Field(description="X coordinate")
    y: float = Field(description="Y coordinate")
    z: float = Field(description="Z coordinate")
    
    @field_validator('x', 'y', 'z')
    @classmethod
    def validate_coordinate(cls, v: float) -> float:
        """Validate that coordinate values are reasonable."""
        if abs(v) > 1000:  # Arbitrary large value check
            raise ValueError("Coordinate value exceeds reasonable range")
        return v

class Plane(BaseModel):
    """3D plane representation."""
    origin: Point3D
    x_axis: Point3D
    y_axis: Point3D
    z_axis: Point3D

class OpeningModel(BaseModel):
    """Data model for wall openings like doors and windows."""
    opening_type: Literal["door", "window"] = Field(
        description="Type of opening (door or window)"
    )
    start_u_coordinate: float = Field(
        description="Position along the wall's length", 
        ge=0
    )
    rough_width: float = Field(
        description="Width of rough opening", 
        gt=0
    )
    rough_height: float = Field(
        description="Height of rough opening", 
        gt=0
    )
    base_elevation_relative_to_wall_base: float = Field(
        description="Height from wall base to opening bottom", 
        ge=0
    )
    
    @model_validator(mode='after')
    def validate_opening(self) -> 'OpeningModel':
        """Validate opening dimensions and position."""
        # Check that window isn't too large for typical construction
        if self.opening_type == 'window':
            if self.rough_width > 10:  # Feet
                raise ValueError("Window width too large for typical construction")
            if self.rough_height > 8:  # Feet
                raise ValueError("Window height too large for typical construction")
                
        # Ensure door starts at wall base for 'door' type
        if self.opening_type == 'door' and self.base_elevation_relative_to_wall_base > 0.1:
            raise ValueError("Doors should typically start at or near wall base")
                
        return self

class WallDataInput(BaseModel):
    """Input data model for wall analysis."""
    wall_type: str = Field(
        description="Wall type code (e.g., '2x4 EXT', '2x6 INT')",
        min_length=3,
        max_length=50
    )
    wall_base_elevation: float = Field(
        description="Base elevation of the wall in project units"
    )
    wall_top_elevation: float = Field(
        description="Top elevation of the wall in project units"
    )
    wall_length: float = Field(
        description="Length of the wall in project units", 
        gt=0
    )
    wall_height: float = Field(
        description="Height of the wall in project units", 
        gt=0
    )
    is_exterior_wall: bool = Field(
        description="Whether this is an exterior wall"
    )
    openings: List[OpeningModel] = Field(
        default=[],
        description="List of wall openings (doors, windows)"
    )
    
    @model_validator(mode='after')
    def validate_wall(self) -> 'WallDataInput':
        """Validate wall dimensions and opening positions."""
        # Ensure wall height is consistent with base and top elevation
        height = self.wall_height
        base_elev = self.wall_base_elevation
        top_elev = self.wall_top_elevation
        
        calculated_height = top_elev - base_elev
        if abs(calculated_height - height) > 0.1:  # Allow slight rounding differences
            raise ValueError(
                f"Wall height ({height}) doesn't match elevation difference ({calculated_height})"
            )
                
        # Validate openings are within wall bounds
        wall_length = self.wall_length
        openings = self.openings
        
        for i, opening in enumerate(openings):
            # Check opening fits within wall length
            if opening.start_u_coordinate + opening.rough_width > wall_length:
                raise ValueError(
                    f"Opening {i+1} extends beyond wall length"
                )
                
            # Check opening fits within wall height
            wall_height = self.wall_height
            opening_top = opening.base_elevation_relative_to_wall_base + opening.rough_height
            if opening_top > wall_height:
                raise ValueError(
                    f"Opening {i+1} extends beyond wall height"
                )
                
            # Check for overlapping openings
            for j, other in enumerate(openings):
                if i != j:
                    # Check if horizontally overlapping
                    this_start = opening.start_u_coordinate
                    this_end = this_start + opening.rough_width
                    other_start = other.start_u_coordinate
                    other_end = other_start + other.rough_width
                    
                    # Check for horizontal overlap
                    if (this_start <= other_end and this_end >= other_start):
                        # Now check for vertical overlap
                        this_bottom = opening.base_elevation_relative_to_wall_base
                        this_top = this_bottom + opening.rough_height
                        other_bottom = other.base_elevation_relative_to_wall_base
                        other_top = other_bottom + other.rough_height
                        
                        if (this_bottom <= other_top and this_top >= other_bottom):
                            raise ValueError(
                                f"Opening {i+1} overlaps with opening {j+1}"
                            )
                        
        return self

class WallAnalysisJob(BaseModel):
    """Model for wall analysis job data."""
    job_id: str = Field(description="Unique job identifier")
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        description="Current job status"
    )
    created_at: datetime = Field(description="Job creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    wall_data: WallDataInput = Field(description="Wall data for analysis")
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Analysis results (when completed)"
    )
    error: Optional[str] = Field(
        default=None, description="Error message (when failed)"
    )
    
    @field_validator('job_id')
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        """Validate job_id is a valid UUID."""
        try:
            uuid_obj = uuid.UUID(v)
            return str(uuid_obj)
        except ValueError:
            raise ValueError("job_id must be a valid UUID")