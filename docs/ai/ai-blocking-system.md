# AI Reference Guide for Timber Framing Blocking System

## Introduction

This document provides definitive guidance for implementing a cell-aware blocking system in the Timber Framing Generator. Blocking elements are horizontal members installed between vertical studs to provide lateral support, bracing, and structural integrity. Current implementation issues show blocking elements ignoring cell boundaries, running through openings, and positioned at improper elevations.

## Key Data Structures and Cell System

### Wall Data Structure

The foundation of all framing operations:

```python
{
    "wall_type": str,                    # E.g., "2x4 EXT", "2x6 INT"
    "wall_base_curve": rg.Curve,         # Base curve defining wall path
    "wall_length": float,                # Length along base curve
    "base_plane": rg.Plane,              # Reference plane for wall
    "wall_base_elevation": float,        # Z-height of wall base
    "wall_top_elevation": float,         # Z-height of wall top
    "wall_height": float,                # Vertical height of wall
    "is_exterior_wall": bool,            # Whether wall is exterior
    "openings": List[Dict],              # Opening data
    "cells": List[Dict]                  # Cell decomposition data
}
```

### Cell Data Structure

Cells provide space division and organization:

```python
{
    "cell_type": str,                    # Type code (WBC, OC, SC, SCC, HCC)
    "u_start": float,                    # Start position along wall length
    "u_end": float,                      # End position along wall length
    "v_start": float,                    # Start height from wall base
    "v_end": float,                      # End height from wall base
    "corner_points": List[rg.Point3d],   # 3D corner points in world space
}
```

### Cell Type Definitions

The system uses these cell types:

1. **WBC (Wall Boundary Cell)**: Entire wall boundary
2. **OC (Opening Cell)**: Door or window openings
3. **SC (Stud Cell)**: Regions between openings for standard studs
4. **SCC (Sill Cripple Cell)**: Area below window openings
5. **HCC (Header Cripple Cell)**: Area above openings

## Why Blocking Must Use the Cell System

The screenshot reveals fundamental issues with current blocking implementations:

1. **Spatial Awareness Issue**: Blocking elements run through openings - a clear violation of structural reality
2. **Uniform Height Problem**: Blocking appears at uniform wall heights regardless of cell types
3. **Inconsistent Termination**: Blocking elements don't properly terminate at cell boundaries
4. **Elevation Inconsistency**: Blocking heights don't reflect proper positioning relative to headers/sills

Using the cell system for blocking is **mandatory** because:

1. Cells define valid **spatial boundaries** where blocking can exist
2. Cells provide **contextual information** about what type of space the blocking occupies
3. Cells establish **relationship hierarchies** between framing elements
4. Cells ensure **structural validity** by preventing impossible configurations

## Blocking Element Dependencies

A proper blocking system has these critical dependencies:

### 1. Cell-Based Positioning Dependencies

- **Parent Cell** → The specific cell where blocking will be placed, defining its horizontal span (u_start to u_end) and vertical zone (v_start to v_end)
- **Cell Type** → Classification of the parent cell that determines if blocking is appropriate and how it should be configured

These cell relationships are critical because:
1. The parent cell establishes the primary spatial boundaries for the blocking
2. Adjacent cells provide context for proper termination and continuity
3. Cell type determines the structural role and requirements for blocking

### 2. Element-Based Positioning Dependencies

- **Studs** → Provide connection points and affect blocking count
- **Plates** → Define the overall height boundaries
- **King Studs** → Provide termination points around openings
- **Headers/Sills** → May require special blocking conditions

### 3. Configuration Dependencies

- **Code Requirements** → Dictate spacing rules and minimum blocking
- **Framing Type** → Affects blocking dimensions and attachment methods
- **Spacing Rules** → Control vertical distribution of multiple blocking rows

## Decision Tree for Blocking Placement

For each cell in the wall:

1. **Is blocking appropriate for this cell type?**
   - YES for SC (Stud Cell)
   - YES for SCC (Sill Cripple Cell) with sufficient height (≥ blocking_height * 3)
   - YES for HCC (Header Cripple Cell) with sufficient height (≥ blocking_height * 3)
   - NO for OC (Opening Cell)
   - NO for WBC (Wall Boundary Cell) - already covered by sub-cells

2. **If appropriate, how many rows of blocking?**
   - Default rules (should be configurable via FRAMING_PARAMS):
     - Single row: When cell height < 48 inches
     - Two rows: When cell height ≥ 48 inches and < 96 inches
     - Three rows: When cell height ≥ 96 inches
   - These values should be read from configuration parameters:
     ```python
     FRAMING_PARAMS = {
         # Other parameters...
         "blocking_row_height_threshold_1": 48/12,  # 48 inches in feet
         "blocking_row_height_threshold_2": 96/12,  # 96 inches in feet
         "blocking_min_cell_height": None,  # Calculated from blocking_height if None
     }
     ```
   - Special cases: Follow specific code requirements or custom configurations

3. **Where should blocking be positioned vertically?**
   - Single row: At v_start + (v_end - v_start) / 2 (mid-height)
   - Two rows: At v_start + height/3 and v_start + 2*height/3
   - Three rows: At quarter points of height
   - Adjust to avoid conflicts with other elements

4. **What are the blocking start and end points?**
   - Start: cell.u_start + (regular_stud_width/2) - adjust further if connecting to king stud
   - End: cell.u_end - (regular_stud_width/2) - adjust further if connecting to king stud
   - Always adjust for the standard stud width at both ends, then make additional adjustments for special cases
   - Validate against actual stud positions in this cell to ensure proper connections

## Implementation Requirements

### 1. BlockingGenerator Class

Create a `BlockingGenerator` class following the established generator pattern:

```python
class BlockingGenerator:
    def __init__(
        self,
        wall_data: Dict[str, Any],
        stud_positions: Dict[str, List[float]],
        plate_data: Dict[str, Any]
    ):
        self.wall_data = wall_data
        self.stud_positions = stud_positions
        self.plate_data = plate_data
        self.debug_geometry = {"points": [], "planes": [], "profiles": [], "paths": []}
        
    def generate_blocking(self) -> List[rg.Brep]:
        """Generate blocking elements based on cell decomposition."""
        blocking_elements = []
        
        # Process each cell for appropriate blocking
        for cell in self.wall_data.get("cells", []):
            if self._is_blocking_appropriate(cell):
                count = self._determine_blocking_count(cell)
                elevations = self._calculate_blocking_elevations(cell, count)
                
                for elevation in elevations:
                    blocking = self._create_blocking_for_cell(cell, elevation)
                    if blocking:
                        blocking_elements.append(blocking)
        
        return blocking_elements
        
    def _is_blocking_appropriate(self, cell: Dict[str, Any]) -> bool:
        """Determine if blocking is appropriate for this cell type."""
        # Implementation logic here
        
    def _determine_blocking_count(self, cell: Dict[str, Any]) -> int:
        """Determine how many rows of blocking are needed in this cell."""
        # Implementation logic here
        
    def _calculate_blocking_elevations(
        self, cell: Dict[str, Any], count: int
    ) -> List[float]:
        """Calculate the elevations for blocking rows."""
        # Implementation logic here
        
    def _create_blocking_for_cell(
        self, cell: Dict[str, Any], elevation: float
    ) -> Optional[rg.Brep]:
        """Create blocking geometry at the specified elevation in the cell."""
        # Implementation logic here
```

### 2. Integration with FramingGenerator

Add blocking generation to the framing sequence in `FramingGenerator.generate_framing()`:

```python
def generate_framing(self):
    # Generate plates first since king studs depend on them
    self._generate_plates()
    
    # Generate king studs using the generated plates
    self._generate_king_studs()
    
    # Generate headers and sills
    self._generate_headers_and_sills()
    
    # Generate trimmers
    self._generate_trimmers()
    
    # Generate header cripples
    self._generate_header_cripples()
    
    # Generate sill cripples
    self._generate_sill_cripples()
    
    # Generate standard studs
    self._generate_studs()
    
    # NEW: Generate blocking after all vertical elements
    self._generate_blocking()
```

### 3. Complete Blocking Element Creation

Follow this algorithm for the `_create_blocking_for_cell` method:

```python
def _create_blocking_for_cell(
    self, cell: Dict[str, Any], elevation: float
) -> Optional[rg.Brep]:
    """Create blocking geometry at the specified elevation in the cell."""
    try:
        base_plane = self.wall_data.get("base_plane")
        if not base_plane:
            return None
            
        # 1. Determine horizontal span
        u_start = cell.get("u_start")
        u_end = cell.get("u_end")
        
        # Adjust for stud connections
        stud_positions = self._get_stud_positions_in_cell(cell)
        if stud_positions:
            # Find left-most and right-most studs in this cell
            left_stud = min(stud_positions)
            right_stud = max(stud_positions)
            
            # Always adjust by half the regular stud width first
            stud_width = FRAMING_PARAMS.get("stud_width", 1.5/12)
            
            # Start with cell boundaries plus half stud width
            u_start = cell.get("u_start") + (stud_width / 2)
            u_end = cell.get("u_end") - (stud_width / 2)
            
            # Then check if we need to adjust for special studs like king studs
            king_stud_width = FRAMING_PARAMS.get("king_stud_width", stud_width)
            
            # Identify if left stud is a king stud by checking proximity to opening
            is_left_king_stud = any(
                abs(left_stud - (op.get("start_u_coordinate") - stud_width)) < 0.01
                for op in self.wall_data.get("openings", [])
            )
            
            # Identify if right stud is a king stud by checking proximity to opening
            is_right_king_stud = any(
                abs(right_stud - (op.get("start_u_coordinate") + op.get("rough_width") + stud_width)) < 0.01
                for op in self.wall_data.get("openings", [])
            )
            
            # Apply additional king stud adjustments if needed
            if is_left_king_stud:
                u_start = left_stud - (king_stud_width / 2)
            else:
                u_start = left_stud - (stud_width / 2)
                
            if is_right_king_stud:
                u_end = right_stud + (king_stud_width / 2)
            else:
                u_end = right_stud + (stud_width / 2)
            
        # 2. Create centerline endpoints
        start_point = rg.Point3d.Add(
            base_plane.Origin,
            rg.Vector3d.Add(
                rg.Vector3d.Multiply(base_plane.XAxis, u_start),
                rg.Vector3d.Multiply(base_plane.YAxis, elevation),
            ),
        )
        
        end_point = rg.Point3d.Add(
            base_plane.Origin,
            rg.Vector3d.Add(
                rg.Vector3d.Multiply(base_plane.XAxis, u_end),
                rg.Vector3d.Multiply(base_plane.YAxis, elevation),
            ),
        )
        
        # Create centerline
        centerline = rg.LineCurve(start_point, end_point)
        self.debug_geometry["paths"].append(centerline)
        
        # 3. Create profile
        blocking_width = FRAMING_PARAMS.get("blocking_width", 1.5/12)
        blocking_height = FRAMING_PARAMS.get("blocking_height", 3.5/12)
        
        profile_x_axis = base_plane.ZAxis
        profile_y_axis = base_plane.YAxis
        
        profile_plane = rg.Plane(start_point, profile_x_axis, profile_y_axis)
        self.debug_geometry["planes"].append(profile_plane)
        
        profile_rect = rg.Rectangle3d(
            profile_plane,
            rg.Interval(-blocking_width / 2, blocking_width / 2),
            rg.Interval(-blocking_height / 2, blocking_height / 2),
        )
        
        profile_curve = profile_rect.ToNurbsCurve()
        self.debug_geometry["profiles"].append(profile_rect)
        
        # 4. Create extrusion
        extrusion_vector = rg.Vector3d(end_point - start_point)
        extrusion = rg.Extrusion.CreateExtrusion(profile_curve, extrusion_vector)
        
        if extrusion and extrusion.IsValid:
            return extrusion.ToBrep().CapPlanarHoles(0.001)
        else:
            return None
            
    except Exception as e:
        print(f"Error creating blocking: {str(e)}")
        return None
```

## Validation Criteria

A correctly implemented blocking system should:

1. **Never have blocking running through openings**
2. **Always connect to proper vertical elements** (studs, king studs)
3. **Have proper elevations based on cell height**
4. **Maintain consistent dimensions and offsets**
5. **Follow proper building code requirements for spacing**
6. **Adapt to different wall configurations**

## Best Practices

1. **Always start with cell filtering** - Know which cells need blocking
2. **Calculate elevations based on cell height** - Avoid fixed elevations
3. **Terminate at appropriate elements** - Connect to studs, not empty space
4. **Use debug geometry** - Visualize calculation steps
5. **Validate results** - Check for collisions with openings
6. **Follow established geometry creation patterns** - Be consistent with other generators

## Implementation Example

Here's a sample implementation of the `_is_blocking_appropriate` and `_determine_blocking_count` methods:

```python
def _is_blocking_appropriate(self, cell: Dict[str, Any]) -> bool:
    """Determine if blocking is appropriate for this cell type."""
    cell_type = cell.get("cell_type")
    
    # Explicit cell type filtering
    if cell_type == "OC":  # Opening Cell - never needs blocking
        return False
        
    if cell_type == "WBC":  # Wall Boundary Cell - already covered by sub-cells
        return False
        
    # Check cell height - need minimum height for blocking
    v_start = cell.get("v_start", 0)
    v_end = cell.get("v_end", 0)
    height = v_end - v_start
    
    # Get minimum height from configuration or calculate default
    blocking_height = FRAMING_PARAMS.get("blocking_height", 3.5/12)
    min_cell_height = FRAMING_PARAMS.get("blocking_min_cell_height")
    
    # If not configured, use 3x blocking height as reasonable minimum
    # This ensures enough space for the blocking plus clearance above and below
    if min_cell_height is None:
        min_cell_height = blocking_height * 3
    
    if height < min_cell_height:
        return False
        
    # For specific cell types, apply additional rules
    if cell_type == "SC":  # Stud Cell - most common for blocking
        return True
        
    if cell_type in ["SCC", "HCC"]:  # Cripple cells - need sufficient height
        return height >= min_cell_height
        
    return False  # Default to no blocking if cell type unknown

def _determine_blocking_count(self, cell: Dict[str, Any]) -> int:
    """Determine how many rows of blocking are needed in this cell."""
    v_start = cell.get("v_start", 0)
    v_end = cell.get("v_end", 0)
    height = v_end - v_start
    
    # Read thresholds from configuration with defaults
    threshold_1 = FRAMING_PARAMS.get("blocking_row_height_threshold_1", 48/12)  # 4 feet default
    threshold_2 = FRAMING_PARAMS.get("blocking_row_height_threshold_2", 96/12)  # 8 feet default
    
    # Custom function for special cases (if defined)
    custom_blocking_count_func = FRAMING_PARAMS.get("custom_blocking_count_function")
    if custom_blocking_count_func and callable(custom_blocking_count_func):
        return custom_blocking_count_func(cell, height)
    
    # Standard configurable blocking count rules
    if height < threshold_1:
        return 1
    elif height < threshold_2:
        return 2
    else:
        return 3
```

By following these guidelines, the blocking generator will correctly respect cell boundaries, properly position blocking elements, and maintain structural integrity throughout the framing system.
