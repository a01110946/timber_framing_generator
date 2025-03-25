# Speckle Integration Plan for Timber Framing Generator

## Overview

This document outlines the approach to replace direct Revit access with Speckle in the Timber Framing Generator workflow. By leveraging Speckle as an intermediary, we can process Revit models without requiring Rhino.Inside.Revit, allowing for more flexible deployment options.

## Current Workflow Analysis

The existing workflow relies on Rhino.Inside.Revit to:
1. Access Revit wall elements directly
2. Extract geometric and parameter data from walls
3. Identify openings using the `FindInserts` method
4. Process this data to generate timber framing elements
5. Visualize results in the Revit context

The most critical dependencies on Revit in `revit_data_extractor.py` are:
- Wall geometry extraction
- Parameter access (`wall_type`, elevations, etc.)
- Opening detection via `FindInserts`
- Conversion from Revit to Rhino geometry

## Proposed Speckle Integration Workflow

### 1. Data Access Phase

Instead of accessing Revit directly, we'll:
- Connect to Speckle server using the Python SDK
- Receive the Revit model data from a specified Speckle stream
- Extract wall elements and their properties from the Speckle objects
- Identify openings through parent-child relationships in the Speckle object graph

### 2. Data Processing Phase

The processing phase remains largely unchanged:
- Convert Speckle geometry to Rhino geometry
- Use existing cell decomposition logic
- Generate timber framing elements using the same algorithms

### 3. Visualization Phase

For visualization, we'll:
- Convert generated timber framing elements to Speckle objects
- Send these elements back to Speckle as a new commit or branch
- Visualize using Speckle's web viewer or through Rhino with Speckle Connector

## Key Replacements for Revit Dependencies

### Wall Base Curve Extraction

**Current:** 
```python
wall_base_curve_rhino = get_wall_base_curve(revit_wall)
```

**Replacement:**
Extract wall base curve from Speckle wall object's `baseCurve` or `outline` property and convert to Rhino geometry.

### Wall Parameters

**Current:**
```python
base_level_param = revit_wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT)
# Additional parameter extraction...
```

**Replacement:**
Access wall parameters from Speckle object properties (`baseElevation`, `topElevation`, etc.).

### Opening Detection (FindInserts)

**Current:**
```python
insert_ids = revit_wall.FindInserts(True, False, True, True)
for insert_id in insert_ids:
    insert_element = revit_wall.Document.GetElement(insert_id)
    # Process openings...
```

**Replacement:**
Traverse the Speckle object graph to find openings related to the wall. These might be:
- Child elements of the wall object
- Elements with a host property referencing the wall
- Elements whose geometry intersects with the wall

### Coordinate System and Geometry Conversion

**Current:**
Relies on `RhinoInside.Revit.Convert.Geometry` for conversion.

**Replacement:**
Use Speckle's built-in conversion methods or manual conversion from Speckle to Rhino geometry.

## Implementation Steps

1. **Install and Configure Speckle SDK**
   - Install the Speckle Python SDK (`pip install specklepy`)
   - Set up authentication with the Speckle server

2. **Create Speckle Data Extractor**
   - Implement a new `extract_wall_data_from_speckle` function
   - Connect to Speckle and receive model data
   - Extract walls and their properties
   - Identify openings through the object graph

3. **Geometry Conversion**
   - Convert Speckle geometry to Rhino geometry
   - Ensure consistent coordinate systems
   - Validate geometric relationships

4. **Testing and Validation**
   - Compare results with Rhino.Inside.Revit workflow
   - Validate geometric accuracy and parameter fidelity
   - Ensure all necessary data is captured

5. **Visualization Pipeline**
   - Implement conversion of timber framing elements to Speckle objects
   - Create commit/branch management for results
   - Test visualization in Speckle web viewer and Rhino

## Challenges and Considerations

1. **Object Relationships**
   - Speckle's object graph might structure wall-opening relationships differently than Revit's API
   - May require traversing multiple levels of the object hierarchy

2. **Geometric Accuracy**
   - Ensure precise conversion between Speckle and Rhino geometry
   - Validate coordinate systems and transformations

3. **Parameter Mapping**
   - Map Revit-specific parameters to Speckle object properties
   - Handle missing or differently structured parameters

4. **Performance**
   - Consider caching strategies for large models
   - Implement efficient filtering to process only relevant objects

## Future Extensions

1. **Two-way Synchronization**
   - Enable pushing generated framing back to the original Revit model via Speckle
   - Support updating existing framing based on model changes

2. **Multi-platform Support**
   - Extend to support other platforms (Rhino, Grasshopper, web)
   - Create platform-specific visualization adapters

3. **Versioning and Collaboration**
   - Leverage Speckle's versioning capabilities for design iterations
   - Enable collaborative workflows through branch management
