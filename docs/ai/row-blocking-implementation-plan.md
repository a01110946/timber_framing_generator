# Row Blocking Implementation Plan

## Overview
This document outlines the implementation plan for adding row blocking functionality to the Timber Framing Generator. Row blocking refers to horizontal framing members installed between vertical studs to provide lateral support, prevent stud rotation/twisting, add structural rigidity, and in some cases provide nailing surfaces for wall finishes.

## Technical Definition
Row blocking (also called "solid blocking" or simply "blocking") consists of lumber pieces of the same dimension as the studs, cut to fit between studs, and installed in one or more horizontal rows at specified heights in a wall assembly.

## Implementation Requirements

### 1. Parameters Required

#### Configuration Parameters
- **Block Spacing**: Vertical distance between rows of blocking (default: 4 feet)
- **Block Pattern**: How blocks should be arranged (inline, staggered, etc.)
- **First Block Height**: Height from bottom plate to first row of blocking
- **Block Profile**: Lumber profile to use (default: same as wall studs)
- **Include Blocking**: Boolean to toggle blocking generation
- **Special Locations**: Additional strategic locations (mid-height, fire blocking heights, etc.)

#### Structural Parameters
- **Continuity**: Whether the blocking should align across stud bays for full structural continuity
- **End Treatment**: Treatment of blocking at wall ends/openings

### 2. Geometry Requirements
- Blocks must maintain the same profile and orientation as wall studs
- Blocks must fit precisely between studs with appropriate end cuts
- Support for both perpendicular and parallel wall intersections

### 3. Integration Points
- **Framing Generator**: Add blocking generation after studs but before electrical/plumbing
- **Cell Decomposition**: May need a new cell type or attribute
- **Visualization**: Blocks should be identifiable in visualization system
- **Data Model**: Block positions and geometry need to be stored alongside other elements

## Technical Approach

### 1. Data Structure
Create a new class `RowBlocking` or `BlockingGenerator` that:
- Takes information about stud positions
- Calculates block positions based on configuration
- Generates the necessary blocking geometry

### 2. Implementation Steps
1. Create configuration parameters in `framing.py`
2. Develop `row_blocking.py` module with the primary generator class
3. Update framing sequence to include blocking generation
4. Add blocking to output data trees in Grasshopper
5. Add geometric constraints to avoid conflicts with openings

### 3. Algorithm Outline
1. Identify stud pairs that need blocking
2. Calculate block heights based on spacing configuration
3. Generate block geometry using same profile as studs
4. Position blocks in appropriate stud bays
5. Handle special cases (openings, wall ends)

### 4. Testing Strategy
1. Create unit tests for block positioning logic
2. Test with various wall configurations
3. Verify that blocks do not conflict with openings
4. Validate structural integrity of the blocking pattern

## Integration with Existing Code

### Module Structure
```
src/timber_framing_generator/
├── framing_elements/
│   ├── row_blocking.py      # NEW: Core implementation module
│   └── blocking_parameters.py  # NEW: Parameter definitions
├── config/
│   └── framing.py           # UPDATE: Add blocking parameters
```

### Key Classes
- `BlockingParameters`: Configure blocking parameters (similar to other element parameter classes)
- `RowBlockingGenerator`: Primary class to generate blocking geometry
- `BlockPositioning`: Helper functions for calculating blocking positions

## Future Considerations
- Support for fire blocking at specific heights
- Advanced patterns (staggered, diagonal, etc.)
- Special case handling around windows and doors
- Integration with MEP systems
- Support for insulation requirements

## Timeline
1. Configuration setup: 1-2 hours
2. Core algorithm: 4-6 hours
3. Integration: 2-3 hours
4. Testing: 3-4 hours
5. Documentation: 1-2 hours

## Implementation Priority
1. Basic functionality with single row of blocking
2. Multiple row support with fixed spacing
3. Advanced patterns and special cases
