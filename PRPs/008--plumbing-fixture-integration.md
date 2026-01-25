# PRP: Plumbing Fixture Integration

> **Version:** 1.0
> **Created:** 2026-01-24
> **Status:** Ready
> **Branch:** feature/plumbing-integration

---

## Goal

Implement a complete plumbing fixture integration system that:
1. Extracts connectors from Revit plumbing fixtures
2. Calculates pipe routes to the nearest wall
3. Generates penetrations in wall framing for pipes
4. Outputs geometry for visualization and Revit baking

## Why

- **Offsite Construction Requirement**: Prefabricated wall panels need MEP rough-ins pre-installed
- **Integration with Framing**: Pipes must pass through framing; penetrations must be sized correctly
- **First MEP Domain**: Plumbing is the first of three MEP domains (HVAC and electrical to follow)
- **Customer Value**: Enables complete wall panel assembly with plumbing in factory

## What

### User-Visible Behavior

1. User selects plumbing fixtures in Revit (sinks, toilets, etc.)
2. User runs MEP Connector Extractor component → outputs connector data
3. User runs Pipe Router component → outputs routes to wall entry + vertical connection
4. User runs Penetration Generator → outputs penetration data
5. User can visualize pipes and penetrations in Rhino
6. User can bake penetrations back to Revit as openings

### Success Criteria

- [ ] Extract all pipe connectors from selected plumbing fixtures
- [ ] Calculate routes from fixture to nearest wall entry point
- [ ] Calculate first vertical connection inside wall
- [ ] Generate penetration specifications for studs in route path
- [ ] Output JSON compatible with existing framing pipeline
- [ ] Provide Rhino geometry for visualization (pipes, penetrations)
- [ ] All unit tests pass
- [ ] Integration test with Grasshopper successful

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Include these in your context window
Project Docs:
  - file: docs/ai/ai-mep-connectors-reference.md
    why: Complete Revit MEP connector API reference

  - file: docs/ai/ai-offsite-construction-architecture.md
    why: Overall architecture and MEP routing decisions

  - file: docs/ai/ai-coordinate-system-reference.md
    why: UVW coordinate system for wall-relative positioning

  - file: CLAUDE.md
    why: Project conventions and gotchas

Core Implementations:
  - file: src/timber_framing_generator/core/mep_system.py
    why: MEPSystem ABC, MEPConnector, MEPRoute dataclasses

  - file: src/timber_framing_generator/mep/core/base.py
    why: Existing MEP utilities (penetration sizing, distance, etc.)

  - file: src/timber_framing_generator/core/json_schemas.py
    why: Existing JSON serialization patterns

Existing Components:
  - file: scripts/gh_wall_analyzer.py
    why: Pattern for GHPython component structure

  - file: scripts/gh_framing_generator.py
    why: Pattern for JSON input/output in GH
```

### Current Codebase Structure

```
src/timber_framing_generator/
├── core/
│   ├── mep_system.py          # MEPDomain, MEPConnector, MEPRoute, MEPSystem ABC
│   └── json_schemas.py        # Existing serialization patterns
├── mep/
│   ├── __init__.py            # Exports core types
│   ├── core/
│   │   ├── __init__.py
│   │   └── base.py            # Penetration sizing, distance utilities
│   └── plumbing/
│       └── __init__.py        # Placeholder, to be implemented
├── utils/
│   └── geometry_factory.py    # RhinoCommon factory (assembly handling)
└── config/
    └── framing.py             # Existing framing parameters
```

### Desired Structure (files to add/modify)

```bash
# Show new/modified files with comments
src/timber_framing_generator/
├── mep/
│   ├── plumbing/
│   │   ├── __init__.py           # MODIFY: Export PlumbingSystem
│   │   ├── plumbing_system.py    # NEW: PlumbingSystem class (implements MEPSystem)
│   │   ├── connector_extractor.py # NEW: Extract connectors from Revit fixtures
│   │   ├── pipe_router.py        # NEW: Route calculation to wall entry
│   │   └── penetration_rules.py  # NEW: Plumbing-specific penetration rules
│   └── core/
│       └── base.py               # MODIFY: Add wall intersection logic

scripts/
├── gh_mep_connector_extractor.py # NEW: GHPython component
├── gh_pipe_router.py             # NEW: GHPython component
└── gh_penetration_generator.py   # NEW: GHPython component

tests/
└── mep/
    ├── __init__.py               # NEW
    ├── test_plumbing_system.py   # NEW
    ├── test_connector_extractor.py # NEW
    └── test_pipe_router.py       # NEW
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: Revit API access in GHPython
# - FamilyInstance.MEPModel may be None for non-MEP families
# - ConnectorManager may be None even for MEP families
# - Always check for None before accessing connectors
# - Connector.Domain determines which properties are available

# CRITICAL: Connector properties by domain
# - Plumbing: Use Connector.PipeSystemType, Connector.Radius
# - HVAC: Use Connector.DuctSystemType, can have Width/Height
# - Electrical: Use Connector.ElectricalSystemType

# CRITICAL: Direction convention
# - Connector.CoordinateSystem.BasisZ points OUTWARD from element
# - This is the direction to route pipes FROM the fixture

# CRITICAL: Units
# - Revit API uses feet internally
# - Connector.Origin is in feet
# - Connector.Radius is in feet

# CRITICAL: Wall intersection
# - Need to find where connector ray intersects wall face
# - Wall base_plane + length + height defines wall bounding box
# - Must handle walls at various orientations

# CRITICAL: Penetration limits
# - Max hole diameter = 40% of stud depth (code typical)
# - For 2x6 (5.5" deep), max hole = 2.2" diameter
# - For 2x4 (3.5" deep), max hole = 1.4" diameter
# - Larger pipes need alternative framing (headers, double studs)
```

---

## Implementation Blueprint

### Data Models

```python
# Already defined in core/mep_system.py:
# - MEPDomain (enum)
# - MEPConnector (dataclass)
# - MEPRoute (dataclass)
# - MEPSystem (ABC)

# New models needed:

@dataclass
class PlumbingPipeSize:
    """Standard plumbing pipe sizes."""
    nominal_size: str  # e.g., "1/2", "3/4", "1", "1-1/2", "2", "3", "4"
    outer_diameter: float  # feet
    inner_diameter: float  # feet

    @classmethod
    def from_radius(cls, radius_ft: float) -> "PlumbingPipeSize":
        """Infer nominal size from connector radius."""
        # Map connector radius to standard pipe sizes
        pass

STANDARD_PIPE_SIZES = {
    "1/2": PlumbingPipeSize("1/2", 0.0729, 0.0521),   # 0.875" OD
    "3/4": PlumbingPipeSize("3/4", 0.0875, 0.0646),   # 1.05" OD
    "1": PlumbingPipeSize("1", 0.1104, 0.0854),       # 1.325" OD
    "1-1/2": PlumbingPipeSize("1-1/2", 0.1583, 0.1271),  # 1.9" OD
    "2": PlumbingPipeSize("2", 0.1979, 0.1604),       # 2.375" OD
    "3": PlumbingPipeSize("3", 0.2917, 0.2521),       # 3.5" OD
    "4": PlumbingPipeSize("4", 0.375, 0.3354),        # 4.5" OD
}
```

### Tasks (in execution order)

```yaml
Task 1: Create PlumbingSystem class
  - CREATE: src/timber_framing_generator/mep/plumbing/plumbing_system.py
  - IMPLEMENT: PlumbingSystem(MEPSystem)
  - METHODS: domain property, extract_connectors, calculate_routes, generate_penetrations
  - MIRROR pattern from: materials/timber/timber_strategy.py (Strategy implementation)

Task 2: Create connector extraction module
  - CREATE: src/timber_framing_generator/mep/plumbing/connector_extractor.py
  - IMPLEMENT: Functions to extract connectors from Revit FamilyInstances
  - HANDLE: None checks, domain filtering, system type filtering
  - RETURN: List[MEPConnector]

Task 3: Create pipe routing module
  - CREATE: src/timber_framing_generator/mep/plumbing/pipe_router.py
  - IMPLEMENT: Route calculation from connector to wall entry
  - IMPLEMENT: Vertical connection point calculation
  - HANDLE: Wall intersection, multiple walls, no wall found
  - RETURN: List[MEPRoute]

Task 4: Create penetration rules module
  - CREATE: src/timber_framing_generator/mep/plumbing/penetration_rules.py
  - IMPLEMENT: Plumbing-specific penetration sizing
  - IMPLEMENT: Code compliance checks
  - DEFINE: Standard pipe sizes dictionary

Task 5: Update base.py with wall intersection
  - MODIFY: src/timber_framing_generator/mep/core/base.py
  - IMPLEMENT: find_nearest_wall_entry with actual logic
  - IMPLEMENT: ray-plane intersection for wall faces
  - IMPLEMENT: point-in-wall-boundary check

Task 6: Update plumbing __init__.py
  - MODIFY: src/timber_framing_generator/mep/plumbing/__init__.py
  - EXPORT: PlumbingSystem, extract_connectors, route_pipes

Task 7: Create GH MEP Connector Extractor component
  - CREATE: scripts/gh_mep_connector_extractor.py
  - INPUTS: plumbing_fixtures (list), run (bool)
  - OUTPUTS: connectors_json, connector_points, connector_vectors, debug_info
  - PATTERN: Follow gh_wall_analyzer.py structure

Task 8: Create GH Pipe Router component
  - CREATE: scripts/gh_pipe_router.py
  - INPUTS: connectors_json, walls_json, config
  - OUTPUTS: routes_json, route_curves, debug_info
  - PATTERN: Calculate routes, output as JSON + geometry

Task 9: Create GH Penetration Generator component
  - CREATE: scripts/gh_penetration_generator.py
  - INPUTS: routes_json, framing_json
  - OUTPUTS: penetrations_json, penetration_points, debug_info
  - PATTERN: Cross-reference routes with framing, output penetration specs

Task 10: Create unit tests
  - CREATE: tests/mep/__init__.py
  - CREATE: tests/mep/test_plumbing_system.py
  - CREATE: tests/mep/test_connector_extractor.py
  - CREATE: tests/mep/test_pipe_router.py
  - PATTERN: Follow tests/core/test_mep_system.py patterns
```

### Pseudocode (with CRITICAL details)

```python
# Task 1: PlumbingSystem class

class PlumbingSystem(MEPSystem):
    """
    Plumbing-specific MEP system handler.

    Handles extraction of plumbing connectors, pipe routing to walls,
    and penetration generation for wall framing.
    """

    @property
    def domain(self) -> MEPDomain:
        return MEPDomain.PLUMBING

    def extract_connectors(
        self,
        elements: List[Any],
        filter_config: Optional[Dict[str, Any]] = None
    ) -> List[MEPConnector]:
        """Extract plumbing connectors from Revit fixtures."""
        from .connector_extractor import extract_plumbing_connectors
        return extract_plumbing_connectors(elements, filter_config)

    def calculate_routes(
        self,
        connectors: List[MEPConnector],
        framing_data: Dict[str, Any],
        target_points: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """Calculate pipe routes from connectors to wall entry + vertical."""
        from .pipe_router import calculate_pipe_routes
        return calculate_pipe_routes(
            connectors,
            framing_data,
            target_points,
            config
        )

    def generate_penetrations(
        self,
        routes: List[MEPRoute],
        framing_elements: List[Any]
    ) -> List[Dict[str, Any]]:
        """Generate penetration specs for wall studs."""
        from .penetration_rules import generate_plumbing_penetrations
        return generate_plumbing_penetrations(routes, framing_elements)
```

```python
# Task 2: Connector extraction

def extract_plumbing_connectors(
    elements: List[Any],
    filter_config: Optional[Dict[str, Any]] = None
) -> List[MEPConnector]:
    """
    Extract plumbing connectors from Revit FamilyInstances.

    Args:
        elements: List of Revit FamilyInstances (plumbing fixtures)
        filter_config: Optional filters:
            - system_types: List of PipeSystemType values to include
            - exclude_connected: Skip already-connected connectors

    Returns:
        List of MEPConnector objects
    """
    connectors = []
    system_types = filter_config.get("system_types") if filter_config else None
    exclude_connected = filter_config.get("exclude_connected", False) if filter_config else False

    for element in elements:
        # CRITICAL: Check for MEPModel
        mep_model = element.MEPModel
        if mep_model is None:
            continue

        # CRITICAL: Check for ConnectorManager
        conn_manager = mep_model.ConnectorManager
        if conn_manager is None:
            continue

        # Iterate connectors
        for conn in conn_manager.Connectors:
            # Filter by domain
            if conn.Domain != Domain.DomainPiping:
                continue

            # Filter by connection status
            if exclude_connected and conn.IsConnected:
                continue

            # Filter by system type
            if system_types and str(conn.PipeSystemType) not in system_types:
                continue

            # Extract position and direction
            origin = conn.Origin
            direction = conn.CoordinateSystem.BasisZ

            # Create MEPConnector
            mep_conn = MEPConnector(
                id=f"{element.Id.IntegerValue}_{conn.Id}",
                origin=(origin.X, origin.Y, origin.Z),
                direction=(direction.X, direction.Y, direction.Z),
                domain=MEPDomain.PLUMBING,
                system_type=str(conn.PipeSystemType),
                owner_element_id=element.Id.IntegerValue,
                radius=conn.Radius,
                flow_direction=str(conn.FlowDirection) if hasattr(conn, 'FlowDirection') else None,
            )
            connectors.append(mep_conn)

    return connectors
```

```python
# Task 3: Pipe routing

def calculate_pipe_routes(
    connectors: List[MEPConnector],
    framing_data: Dict[str, Any],
    target_points: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> List[MEPRoute]:
    """
    Calculate pipe routes from connectors to wall entries.

    Strategy: Fixture → Wall Entry → First Vertical Connection

    Args:
        connectors: Source connectors from fixtures
        framing_data: Wall framing data (for wall geometry)
        target_points: Not used in Phase 1 (auto-find nearest wall)
        config: Routing configuration:
            - max_search_distance: Max distance to find wall (default 10')
            - prefer_horizontal: Prefer horizontal runs (default True)

    Returns:
        List of MEPRoute objects
    """
    routes = []
    walls = extract_walls_from_framing(framing_data)
    max_distance = config.get("max_search_distance", 10.0)

    for connector in connectors:
        # Step 1: Find nearest wall entry point
        wall_entry = find_wall_entry(
            connector.origin,
            connector.direction,
            walls,
            max_distance
        )

        if wall_entry is None:
            # No wall found - skip or create warning
            continue

        # Step 2: Calculate vertical connection point
        vertical_point = calculate_vertical_point(
            wall_entry["entry_point"],
            wall_entry["wall_thickness"],
            wall_entry["wall_normal"],
            connector.system_type
        )

        # Step 3: Build route path
        path_points = [
            connector.origin,           # Start at fixture connector
            wall_entry["entry_point"],  # Horizontal run to wall
            vertical_point,             # First connection inside wall
        ]

        # Create route
        route = MEPRoute(
            id=f"route_{connector.id}",
            domain=MEPDomain.PLUMBING,
            system_type=connector.system_type,
            path_points=path_points,
            start_connector_id=connector.id,
            end_point_type="vertical_connection",
            pipe_size=connector.radius * 2 if connector.radius else None,
            end_point=vertical_point,
        )
        routes.append(route)

    return routes


def find_wall_entry(
    origin: Tuple[float, float, float],
    direction: Tuple[float, float, float],
    walls: List[Dict[str, Any]],
    max_distance: float
) -> Optional[Dict[str, Any]]:
    """
    Find where a ray from connector intersects nearest wall.

    Uses ray-plane intersection for each wall face.
    """
    best_entry = None
    best_distance = max_distance

    for wall in walls:
        # Get wall face plane (exterior face)
        wall_plane = get_wall_face_plane(wall)

        # Ray-plane intersection
        intersection = ray_plane_intersection(
            origin, direction, wall_plane
        )

        if intersection is None:
            continue

        # Check if intersection is within wall bounds
        if not point_in_wall_bounds(intersection, wall):
            continue

        # Check distance
        distance = distance_3d(origin, intersection)
        if distance < best_distance:
            best_distance = distance
            best_entry = {
                "wall_id": wall["id"],
                "entry_point": intersection,
                "distance": distance,
                "wall_normal": wall_plane["normal"],
                "wall_thickness": wall.get("thickness", 0.333),  # Default 4"
            }

    return best_entry
```

```python
# Task 4: Penetration rules

PLUMBING_PENETRATION_CLEARANCE = 0.0208  # 1/4" clearance around pipe

def generate_plumbing_penetrations(
    routes: List[MEPRoute],
    framing_elements: List[Any]
) -> List[Dict[str, Any]]:
    """
    Generate penetration specifications for wall studs.

    For each route segment that passes through a stud, create a penetration.
    """
    penetrations = []

    for route in routes:
        if len(route.path_points) < 2:
            continue

        pipe_diameter = route.pipe_size or 0.0833  # Default 1" pipe

        # Check each segment of the route
        for i in range(len(route.path_points) - 1):
            p1 = route.path_points[i]
            p2 = route.path_points[i + 1]

            # Find studs that this segment passes through
            crossed_studs = find_studs_crossed_by_segment(
                p1, p2, framing_elements
            )

            for stud in crossed_studs:
                # Calculate penetration center
                center = calculate_segment_stud_intersection(p1, p2, stud)

                # Calculate penetration size
                hole_diameter = calculate_penetration_size(
                    pipe_diameter,
                    PLUMBING_PENETRATION_CLEARANCE
                )

                # Check if penetration is allowed
                stud_depth = stud.get("profile", {}).get("depth", 0.292)  # 3.5" default
                is_allowed, reason = check_penetration_allowed(
                    hole_diameter,
                    stud_depth
                )

                penetration = {
                    "id": f"pen_{route.id}_{stud['id']}",
                    "route_id": route.id,
                    "element_id": stud["id"],
                    "element_type": "stud",
                    "location": {
                        "x": center[0],
                        "y": center[1],
                        "z": center[2]
                    },
                    "diameter": hole_diameter,
                    "pipe_size": pipe_diameter,
                    "system_type": route.system_type,
                    "is_allowed": is_allowed,
                    "warning": reason if not is_allowed else None,
                    "reinforcement_required": hole_diameter > (stud_depth * 0.33),
                }
                penetrations.append(penetration)

    return penetrations
```

```python
# Task 7: GH MEP Connector Extractor component structure

"""
GHPython Component: MEP Connector Extractor
File: scripts/gh_mep_connector_extractor.py

Extracts MEP connectors from plumbing fixtures for pipe routing.

Inputs:
    plumbing_fixtures (list): Revit FamilyInstance elements (plumbing fixtures)
    system_types (list): Optional filter for system types (Sanitary, DomesticColdWater, etc.)
    exclude_connected (bool): Skip already-connected connectors
    run (bool): Execute toggle

Outputs:
    connectors_json (str): JSON with connector data
    connector_points (list): Point3d for each connector (visualization)
    connector_vectors (list): Vector3d for each connector direction
    debug_info (str): Processing summary
"""

# Import handling for Rhino/Revit environment
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RhinoCommon')

from Autodesk.Revit.DB import Domain
import Rhino.Geometry as rg
import json

# Module imports with reload handling for development
import sys
for mod_name in list(sys.modules.keys()):
    if 'timber_framing_generator' in mod_name:
        del sys.modules[mod_name]

from src.timber_framing_generator.mep.plumbing import extract_plumbing_connectors
from src.timber_framing_generator.core import MEPConnector

def main():
    """Main component execution."""
    # Initialize outputs
    connectors_json = "{}"
    connector_points = []
    connector_vectors = []
    debug_lines = []

    if not run:
        debug_lines.append("Toggle 'run' to True to execute")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    if not plumbing_fixtures:
        debug_lines.append("No fixtures provided")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    # Build filter config
    filter_config = {}
    if system_types:
        filter_config["system_types"] = list(system_types)
    if exclude_connected:
        filter_config["exclude_connected"] = True

    # Extract connectors
    connectors = extract_plumbing_connectors(plumbing_fixtures, filter_config)
    debug_lines.append(f"Extracted {len(connectors)} connectors from {len(plumbing_fixtures)} fixtures")

    # Build JSON output
    output_data = {
        "connectors": [c.to_dict() for c in connectors],
        "count": len(connectors),
    }
    connectors_json = json.dumps(output_data, indent=2)

    # Build geometry outputs for visualization
    for conn in connectors:
        pt = rg.Point3d(conn.origin[0], conn.origin[1], conn.origin[2])
        vec = rg.Vector3d(conn.direction[0], conn.direction[1], conn.direction[2])
        connector_points.append(pt)
        connector_vectors.append(vec)

    debug_lines.append(f"System types: {set(c.system_type for c in connectors)}")

    return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

# Execute
connectors_json, connector_points, connector_vectors, debug_info = main()
```

### Integration Points

```yaml
CONFIG:
  - file: src/timber_framing_generator/config/mep_standards.py (NEW)
  - pattern: "Define PLUMBING_PARAMS with penetration limits, clearances"

IMPORTS:
  - file: src/timber_framing_generator/mep/__init__.py
  - pattern: "Export PlumbingSystem from plumbing module"

  - file: src/timber_framing_generator/mep/plumbing/__init__.py
  - pattern: "Export PlumbingSystem, extract_plumbing_connectors, etc."

JSON SCHEMAS:
  - file: src/timber_framing_generator/core/mep_system.py
  - pattern: "MEPConnector.to_dict(), MEPRoute.to_dict() already defined"

GRASSHOPPER:
  - file: scripts/gh_mep_connector_extractor.py (NEW)
  - file: scripts/gh_pipe_router.py (NEW)
  - file: scripts/gh_penetration_generator.py (NEW)
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run FIRST - fix errors before proceeding
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Linting
python -m flake8 src/timber_framing_generator/mep/ --max-line-length=88

# Type checking
python -m mypy src/timber_framing_generator/mep/
```

### Level 2: Unit Tests

```python
# Test cases for PlumbingSystem
import pytest
from src.timber_framing_generator.mep.plumbing import PlumbingSystem
from src.timber_framing_generator.core import MEPDomain, MEPConnector

class TestPlumbingSystem:
    """Test PlumbingSystem implementation."""

    def test_domain_is_plumbing(self):
        """PlumbingSystem returns PLUMBING domain."""
        system = PlumbingSystem()
        assert system.domain == MEPDomain.PLUMBING

    def test_extract_connectors_empty_list(self):
        """Empty input returns empty list."""
        system = PlumbingSystem()
        result = system.extract_connectors([])
        assert result == []

    def test_calculate_routes_with_connectors(self):
        """Routes are calculated for valid connectors."""
        # Mock connector data
        pass

    def test_generate_penetrations(self):
        """Penetrations are generated for routes through studs."""
        pass


class TestConnectorExtraction:
    """Test connector extraction functions."""

    def test_extract_from_valid_fixture(self):
        """Connectors extracted from MEP fixture."""
        pass

    def test_filter_by_system_type(self):
        """Only matching system types are extracted."""
        pass


class TestPipeRouter:
    """Test pipe routing functions."""

    def test_find_nearest_wall(self):
        """Nearest wall is found correctly."""
        pass

    def test_route_includes_vertical_connection(self):
        """Route extends to vertical connection point."""
        pass


class TestPenetrationRules:
    """Test penetration generation."""

    def test_penetration_size_with_clearance(self):
        """Penetration includes clearance."""
        from src.timber_framing_generator.mep.core.base import calculate_penetration_size
        diameter = calculate_penetration_size(0.0833, 0.0208)  # 1" pipe
        assert diameter == pytest.approx(0.0833 + 2 * 0.0208)

    def test_large_penetration_flagged(self):
        """Oversized penetrations are flagged."""
        pass
```

```bash
# Run and iterate until passing
python -m pytest tests/mep/ -v

# Run all tests
python -m pytest tests/ -v
```

### Level 3: Integration Test (Grasshopper)

```bash
# Manual test in Grasshopper:
# 1. Open Rhino with Grasshopper
# 2. Connect to Revit via Rhino.Inside.Revit
# 3. Select plumbing fixtures (sinks, toilets)
# 4. Connect to MEP Connector Extractor component
# 5. Toggle 'run' to True
# 6. Verify:
#    - connectors_json contains valid JSON
#    - connector_points are visible in Rhino
#    - connector_vectors point outward from fixtures
#
# 7. Connect connectors_json to Pipe Router
# 8. Verify:
#    - routes_json contains routes to walls
#    - route_curves show pipe paths
#
# 9. Connect routes_json + framing_json to Penetration Generator
# 10. Verify:
#    - penetrations_json contains penetration specs
#    - penetration_points show hole locations

# Expected outcomes:
# - Connector points at fixture outlets
# - Routes extend to nearest wall face
# - Routes include vertical connection inside wall
# - Penetrations sized for pipe + clearance
# - Warnings for oversized penetrations
```

---

## Final Checklist

- [ ] PlumbingSystem class implements MEPSystem ABC correctly
- [ ] extract_plumbing_connectors handles None MEPModel gracefully
- [ ] Pipe router finds nearest wall using ray-plane intersection
- [ ] Routes include wall entry + vertical connection points
- [ ] Penetration sizes include 1/4" clearance
- [ ] Oversized penetrations flagged with warnings
- [ ] All unit tests pass: `python -m pytest tests/mep/ -v`
- [ ] No linting errors: `python -m flake8 src/timber_framing_generator/mep/`
- [ ] GH Connector Extractor outputs valid JSON and geometry
- [ ] GH Pipe Router outputs routes and curves
- [ ] GH Penetration Generator outputs penetration specs
- [ ] JSON format compatible with existing framing pipeline

---

## Anti-Patterns to Avoid

- ❌ Don't access Connector properties without checking Domain first
- ❌ Don't assume MEPModel or ConnectorManager exist (check for None)
- ❌ Don't forget to convert Revit XYZ to tuples for serialization
- ❌ Don't hardcode pipe sizes - use connector.Radius
- ❌ Don't skip penetration validation (code compliance matters)
- ❌ Don't create routes without at least 2 path points
- ❌ Don't ignore wall orientation when finding wall entry
- ❌ Don't forget clearance when sizing penetrations

---

## Notes

### Phase 1 Scope (This PRP)
- Plumbing connectors only (Domain.DomainPiping)
- Route to nearest wall + first vertical connection
- Penetrations in wall studs only
- Manual pipe sizing (use connector radius)

### Future Phases
- Phase 2: HVAC connector extraction and duct routing
- Phase 3: Electrical connector extraction
- Phase 4: Configurable target points (main lines, stacks)
- Phase 5: Full system routing with clash detection
- Phase 6: Automatic pipe sizing based on fixture units

### Key Decisions
1. **Wall Entry Point**: Intersection of connector ray with wall face
2. **Vertical Connection**: Center of wall, offset by half thickness
3. **Penetration Clearance**: 1/4" around pipe (configurable)
4. **Max Penetration Ratio**: 40% of stud depth (code typical)
