# Timber Framing Blocking System Implementation

## Overview

This document provides the definitive guide for implementing blocking elements in the Timber Framing Generator. Blocking elements are horizontal members installed between vertical studs to provide lateral support, bracing, and structural integrity.

## Technical Definition

Row blocking (also called "solid blocking" or simply "blocking") consists of lumber pieces of the same dimension as the studs, cut to fit between studs, and installed in one or more horizontal rows at specified heights in a wall assembly.

## Implementation Requirements

### Configuration Parameters
- **Block Spacing**: Vertical distance between rows (default: 4 feet)
- **Block Pattern**: How blocks should be arranged (inline, staggered, etc.)
- **First Block Height**: Height from bottom plate to first row
- **Block Profile**: Lumber profile to use (default: same as wall studs)
- **Include Blocking**: Boolean to toggle blocking generation

### Geometry Requirements
- Blocks must maintain the same profile and orientation as wall studs
- Blocks must fit precisely between studs with appropriate end cuts
- Support for both perpendicular and parallel wall intersections

## Cell-Based Approach

Blocking must use the cell system because:
1. Cells define valid **spatial boundaries** where blocking can exist
2. Cells provide **contextual information** about space types
3. Cells establish **relationship hierarchies** between framing elements
4. Cells ensure **structural validity** by preventing impossible configurations

### Cell Type Decision Tree

For each cell in the wall:

1. **Is blocking appropriate for this cell type?**
   - YES for SC (Stud Cell)
   - YES for SCC (Sill Cripple Cell) with sufficient height (≥ blocking_height * 3)
   - YES for HCC (Header Cripple Cell) with sufficient height (≥ blocking_height * 3)
   - NO for OC (Opening Cell)
   - NO for WBC (Wall Boundary Cell)

2. **If appropriate, how many rows of blocking?**
   - Single row: When cell height < 48 inches
   - Two rows: When cell height ≥ 48 inches and < 96 inches
   - Three rows: When cell height ≥ 96 inches

3. **Where should blocking be positioned vertically?**
   - Single row: At v_start + (v_end - v_start) / 2 (mid-height)
   - Two rows: At v_start + height/3 and v_start + 2*height/3
   - Three rows: At quarter points of height

## Implementation Structure

### BlockingGenerator Class

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
```

### Key Methods

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
```

### Blocking Creation

```python
def _create_blocking_for_cell(
    self, cell: Dict[str, Any], elevation: float
) -> Optional[rg.Brep]:
    """Create blocking geometry at the specified elevation in the cell."""
    try:
        base_plane = self.wall_data.get("base_plane")
        if not base_plane:
            return None
            
        # 1. Determine horizontal span (adjusted for stud connections)
        u_start = cell.get("u_start") 
        u_end = cell.get("u_end")
        # ... [stud position adjustment logic]
        
        # 2. Create centerline endpoints in UVW space
        start_point = base_plane.PointAt(u_start, elevation, 0)
        end_point = base_plane.PointAt(u_end, elevation, 0)
        
        # 3. Create centerline
        centerline = rg.LineCurve(start_point, end_point)
        
        # 4. Create profile and extrusion
        # ... [profile and extrusion generation logic]
        
        return extrusion.ToBrep().CapPlanarHoles(0.001)
            
    except Exception as e:
        print(f"Error creating blocking: {str(e)}")
        return None
```

## Integration with FramingGenerator

Add blocking generation to the framing sequence:

```python
def generate_framing(self):
    """Generate all framing elements for the wall."""
    # Generate plates first since king studs depend on them
    self._generate_plates()
    
    # Generate studs and other elements
    self._generate_king_studs()
    self._generate_headers_and_sills()
    self._generate_trimmers()
    self._generate_header_cripples()
    self._generate_sill_cripples()
    self._generate_studs()
    
    # NEW: Generate blocking after all vertical elements
    self._generate_blocking()
```

## Validation Criteria

A correctly implemented blocking system should:
1. Never have blocking running through openings
2. Always connect to proper vertical elements
3. Have proper elevations based on cell height
4. Maintain consistent dimensions and offsets

## Configuration Parameters

```python
FRAMING_PARAMS = {
    # Other parameters...
    "blocking_row_height_threshold_1": 48/12,  # 48 inches in feet
    "blocking_row_height_threshold_2": 96/12,  # 96 inches in feet
    "blocking_min_cell_height": None,  # Calculated from blocking_height if None
    "block_spacing": 48.0/12.0,  # 4ft default
    "first_block_height": 24.0/12.0,  # 2ft default
    "blocking_pattern": "staggered"  # "inline" or "staggered"
}
```

## Best Practices for Blocking Implementation

### Algorithmic Approach
1. **Always start with cell filtering** - Identify cells appropriate for blocking
2. **Calculate elevations based on cell height** - Avoid fixed elevations that ignore cell context
3. **Terminate at appropriate elements** - Connect blocks to proper vertical elements
4. **Validate results** - Check for collisions with openings

### Position Calculation

```python
def _calculate_blocking_elevations(
    self, cell: Dict[str, Any], count: int
) -> List[float]:
    """Calculate the elevations for blocking rows."""
    v_start = cell.get("v_start", 0)
    v_end = cell.get("v_end", 0)
    height = v_end - v_start
    
    # Apply first block height if configured
    first_block_height = FRAMING_PARAMS.get("first_block_height")
    if first_block_height is not None and count == 1:
        # Use configured height for single block
        return [v_start + first_block_height]
    
    # Calculate evenly distributed blocking positions
    elevations = []
    if count == 1:
        # Single row at mid-height
        elevations.append(v_start + height / 2)
    elif count == 2:
        # Two rows at 1/3 and 2/3 height
        elevations.append(v_start + height / 3)
        elevations.append(v_start + 2 * height / 3)
    elif count == 3:
        # Three rows at quarter points
        elevations.append(v_start + height / 4)
        elevations.append(v_start + height / 2)
        elevations.append(v_start + 3 * height / 4)
    else:
        # For more than 3 rows, distribute evenly
        for i in range(count):
            elevations.append(v_start + height * (i + 1) / (count + 1))
    
    return elevations
```

### Stud Connection Logic

```python
def _get_stud_positions_in_cell(self, cell: Dict[str, Any]) -> List[float]:
    """Get positions of all studs within this cell."""
    u_start = cell.get("u_start")
    u_end = cell.get("u_end")
    
    # Filter stud positions to those within this cell
    positions = []
    for position in self.stud_positions.get("regular_studs", []):
        if u_start <= position <= u_end:
            positions.append(position)
    
    # Add king stud positions at cell boundaries
    for position in self.stud_positions.get("king_studs", []):
        if abs(position - u_start) < 0.01 or abs(position - u_end) < 0.01:
            positions.append(position)
    
    return sorted(positions)
```

## Advanced Features

### Staggered Blocking Pattern

For "staggered" blocking pattern:

```python
def _apply_blocking_pattern(self, cells: List[Dict[str, Any]]) -> None:
    """Apply the configured blocking pattern to cells."""
    pattern = FRAMING_PARAMS.get("blocking_pattern", "inline")
    
    if pattern == "staggered":
        # For staggered pattern, offset every other cell's blocks
        for i, cell in enumerate(cells):
            if i % 2 == 1:  # Odd-indexed cells
                # Adjust blocking elevations
                elevations = cell.get("blocking_elevations", [])
                if elevations:
                    # Offset by 1/4 of the spacing between blocks
                    block_spacing = FRAMING_PARAMS.get("block_spacing", 4.0/12.0)
                    offset = block_spacing / 4
                    
                    # Apply offset
                    cell["blocking_elevations"] = [
                        elevation + offset for elevation in elevations
                    ]
```

### Fire Blocking Compliance

```python
def _apply_fire_blocking_requirements(self, cells: List[Dict[str, Any]]) -> None:
    """Apply fire blocking requirements to cells."""
    # Check if fire blocking is required
    fire_blocking_required = FRAMING_PARAMS.get("fire_blocking_required", False)
    if not fire_blocking_required:
        return
        
    # Get maximum allowed distance between fire blocks
    max_distance = FRAMING_PARAMS.get("fire_blocking_max_distance", 10.0)
    
    # Process each cell
    for cell in cells:
        v_start = cell.get("v_start", 0)
        v_end = cell.get("v_end", 0)
        height = v_end - v_start
        
        # If cell height exceeds maximum distance, ensure blocking exists
        if height > max_distance:
            # Get existing blocking elevations
            elevations = cell.get("blocking_elevations", [])
            
            # Check if we need to add more blocks
            if not elevations:
                # Add block at mid-height
                cell["blocking_elevations"] = [v_start + height / 2]
            else:
                # Check distances between existing blocks
                prev_elevation = v_start
                new_elevations = []
                
                for elevation in sorted(elevations):
                    # If distance from previous elevation is too large, add block
                    if elevation - prev_elevation > max_distance:
                        # Add block at midpoint
                        new_elevations.append(prev_elevation + (elevation - prev_elevation) / 2)
                    
                    new_elevations.append(elevation)
                    prev_elevation = elevation
                
                # Check distance from last block to top
                if v_end - prev_elevation > max_distance:
                    new_elevations.append(prev_elevation + (v_end - prev_elevation) / 2)
                
                cell["blocking_elevations"] = new_elevations
```

## Integration with FramingGenerator

```python
def _generate_blocking(self):
    """Generate all blocking elements."""
    # Get stud positions
    stud_positions = self._collect_stud_positions()
    
    # Initialize blocking generator
    blocking_generator = BlockingGenerator(
        wall_data=self.wall_data,
        stud_positions=stud_positions,
        plate_data=self._get_plate_data()
    )
    
    # Generate blocking
    blocking_elements = blocking_generator.generate_blocking()
    
    # Add to framing results
    self.framing_result["row_blocking"] = blocking_elements
    
    # Add debug geometry
    self.debug_geometry["points"].extend(blocking_generator.debug_geometry["points"])
    self.debug_geometry["planes"].extend(blocking_generator.debug_geometry["planes"])
    self.debug_geometry["profiles"].extend(blocking_generator.debug_geometry["profiles"])
    self.debug_geometry["paths"].extend(blocking_generator.debug_geometry["paths"])
```

## Testing Strategy

1. **Unit testing** - Test blocking logic with different cell configurations
2. **Visual validation** - Visualize blocking placement for verification
3. **Edge cases** - Test with minimal wall heights, unusual openings
4. **Configuration testing** - Verify all configuration parameters work correctly

### Test Cases
1. Simple wall without openings
2. Wall with single door
3. Wall with multiple windows at different heights
4. Wall with tight spacing between openings
5. Very tall and very short walls

## Implementation Timeline

1. **Configuration parameters** - Add parameters to framing.py (1-2 hours)
2. **Core generator** - Implement BlockingGenerator class (4-6 hours)
3. **Integration** - Add to FramingGenerator workflow (2-3 hours)
4. **Testing & debugging** - Validate results and fix issues (3-4 hours)
5. **Documentation** - Update docs with new feature (1-2 hours)