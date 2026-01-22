# Timber Framing Generator Architecture

## System Overview

The Timber Framing Generator is a Python-based tool designed to automate the creation of timber framing elements from wall data extracted from Revit models. It leverages Rhino.Inside.Revit to bridge between Revit and Rhinoceros/Grasshopper, enabling seamless data transfer and geometry generation.

## Core Architecture Principles

The system follows these architectural principles:

1. **Modular Design**: Components are organized into discrete, loosely coupled modules with clear responsibilities.
2. **Pipeline Processing**: Wall data flows through a defined pipeline: extraction → analysis → cell decomposition → framing generation.
3. **Separation of Concerns**: Clear separation between data extraction, analysis, geometry generation, and visualization.
4. **Extensibility**: System designed to accommodate additional framing types and building standards.
5. **Interoperability**: Uses Rhino.Inside.Revit as a bridge between different CAD systems.

## System Components

### 1. Wall Data Extraction Module

**Purpose**: Extract relevant wall data from Revit models.

**Key Classes/Modules**:
- `wall_data.revit_data_extractor`: Extracts wall geometry and properties from Revit
- `wall_data.wall_selector`: Handles wall selection in the Revit UI
- `wall_data.wall_input`: Provides data structures for wall definition

**Data Flow**:
1. User selects walls in Revit
2. System extracts geometric and parametric data
3. Wall data is structured for further processing

### 2. Cell Decomposition Module

**Purpose**: Decompose walls into structural cells for analysis and framing.

**Key Classes/Modules**:
- `cell_decomposition.cell_segmentation`: Algorithms for dividing walls into cells
- `cell_decomposition.cell_types`: Defines different cell types (wall boundary, opening, stud, etc.)
- `cell_decomposition.cell_visualizer`: Visualizes cell decomposition for validation

**Cell Types**:
- **WBC** (Wall Boundary Cell): Represents the entire wall
- **OC** (Opening Cell): Represents door/window openings
- **SC** (Stud Cell): Regions for standard studs
- **SCC** (Sill Cripple Cell): Regions below window openings
- **HCC** (Header Cripple Cell): Regions above openings

### 3. Framing Elements Module

**Purpose**: Generate timber framing geometry based on cell decomposition.

**Key Classes/Modules**:
- `framing_elements.plates`: Top and bottom plate generation
- `framing_elements.studs`: Standard stud generation
- `framing_elements.king_studs`: King stud generation around openings
- `framing_elements.headers`: Header generation above openings
- `framing_elements.sills`: Sill generation below windows
- `framing_elements.trimmers`: Trimmer stud generation
- `framing_elements.header_cripples`: Cripple stud generation above headers
- `framing_elements.sill_cripples`: Cripple stud generation below sills

**Structure**:
- Each framing element type has specialized generator classes
- Common geometry operations in `framing_elements.framing_geometry`
- Unified parameter system in respective parameter classes (e.g., `header_parameters`)

### 4. Coordinate System Management

**Purpose**: Manage transformations between different coordinate systems.

**Key Classes/Modules**:
- `utils.coordinate_systems`: Handles transformations between wall-local and world coordinates
- `framing_elements.location_data`: Manages location information for framing elements

**Coordinate Systems**:
- **UVW space**: Wall-relative coordinate system
  - U: Along wall length (wall_base_curve direction)
  - V: Vertical direction (perpendicular to base)
  - W: Through wall thickness (normal to wall face)
- **World space**: Rhino/Revit world coordinates

### 5. Configuration Module

**Purpose**: Manage configurable parameters for framing generation.

**Key Classes/Modules**:
- `config.framing`: Framing element dimensions and parameters
- `config.assembly`: Wall assembly layer configuration
- `config.units`: Unit conversion and management

### 6. Integration Interfaces

**Purpose**: Enable integration with external systems.

**Key Classes/Modules**:
- `api.main`: FastAPI application for external access
- `main.py`: Main entry point for Grasshopper component
- `scripts.export_to_revit`: Export generated framing back to Revit

## Data Flow Architecture

The data flows through the system in the following pipeline:

1. **Wall Selection** → **Data Extraction**
   - Input: User-selected Revit walls
   - Output: Structured wall data dictionaries

2. **Wall Data Analysis** → **Cell Decomposition**
   - Input: Wall data dictionaries
   - Output: Cell data structures with geometric information
   
3. **Cell Processing** → **Framing Generation**
   - Input: Cell data structures
   - Output: Framing element geometry

4. **Framing Output** → **Visualization / Export**
   - Input: Framing element geometry
   - Output: Visual display or Revit family instances

## Key Design Decisions

### Wall Data Representation

Walls are represented using a dictionary structure containing:
- Base curve geometry (`wall_base_curve`)
- Base plane (`base_plane`)
- Wall dimensions (`wall_length`, `wall_height`)
- Elevation data (`wall_base_elevation`, `wall_top_elevation`)
- Opening information (`openings`)
- Cell decomposition (`cells`)

This representation provides a comprehensive model that supports both analysis and geometry generation.

### Cell-Based Decomposition Strategy

The system uses cell decomposition to simplify wall framing:
1. Decompose walls into rectangular cells
2. Classify cells based on position and function
3. Apply framing rules to each cell type
4. Generate appropriate framing elements for each cell

This approach simplifies complex wall layouts into manageable pieces for which framing generation rules can be systematically applied.

### Geometry Generation Approach

Framing geometry is generated using these principles:
1. Create centerlines for all framing elements
2. Define profiles perpendicular to centerlines
3. Extrude profiles along centerlines to create solid geometry
4. Apply material properties and additional attributes

This strategy ensures correct orientation and positioning of all framing elements.

### Transformation and Coordinate Management

The system uses multiple coordinate systems:
1. Revit model coordinates (for data extraction)
2. Wall-local UVW coordinates (for cell decomposition and framing placement)
3. Rhino world coordinates (for visualization)

Transformations between these systems are managed by the coordinate system utility classes.

## Integration with External Systems

### Revit Integration (via Rhino.Inside.Revit)

The system uses Rhino.Inside.Revit to:
1. Access Revit API from Python/Grasshopper
2. Extract wall data directly from Revit elements
3. Convert Revit geometry to Rhino geometry
4. Optionally export generated framing back to Revit

### Grasshopper Integration

The system integrates with Grasshopper through:
1. Python components that call system functionality
2. Data tree structures for organizing output
3. Visual feedback in the Grasshopper viewport

### API Interface (Future/In-Progress)

The system includes a FastAPI interface that allows:
1. Submitting wall data for analysis
2. Retrieving framing generation results
3. Integration with external systems

## Testing and Validation Architecture

The system includes:
1. Unit tests for core functionality
2. Visual validation tools in Grasshopper

## Configuration and Extensibility

The system is configurable through:
1. `config` module parameters for framing dimensions
2. Profile definitions for different lumber sizes
3. Wall assembly definitions for different wall types

## Future Architecture Extensions

The architecture supports these planned extensions:
1. Advanced framing optimization algorithms
2. Additional framing types (roof, floor, etc.)
3. Enhanced visualization and documentation
4. Material takeoff and cost analysis capabilities

## Diagram: System Components and Data Flow

```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│                   │     │                   │     │                   │
│  Revit Model      │────▶│  Wall Data        │────▶│  Cell             │
│  (Input Source)   │     │  Extraction       │     │  Decomposition    │
│                   │     │                   │     │                   │
└───────────────────┘     └───────────────────┘     └─────────┬─────────┘
                                                              │
                                                              │
                                                              ▼
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│                   │     │                   │     │                   │
│  Revit            │◀────│  Framing          │◀────│  Framing Element  │
│  (Export Target)  │     │  Geometry         │     │  Generation       │
│                   │     │                   │     │                   │
└───────────────────┘     └───────────────────┘     └───────────────────┘
```

## Diagram: Module Dependencies

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  wall_data      │────▶│  cell_          │────▶│  framing_       │
│                 │     │  decomposition  │     │  elements       │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                      utils & config                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Technical Details

This architecture documentation provides a high-level overview. For detailed implementation specifics, refer to the following resources:
- Source code documentation in the `src` directory
- Function and class docstrings
- Unit test cases for behavioral examples
- The design specification document for detailed framing rules
