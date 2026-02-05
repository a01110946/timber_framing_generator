# PRP-012: MEP Routing Target Candidate Generator

## Overview

**Feature**: Target Candidate Generator with pluggable heuristics
**Branch**: `feature/mep-routing-phase2-targets`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 2)

## Problem Statement

MEP connectors (fixture connections, device terminations) need to find appropriate routing targets. Different MEP system types have different routing behaviors:
- **Sanitary**: Gravity-driven, must find drain stack or floor penetration
- **Vent**: Routes upward to vent stack in wet wall or roof penetration
- **DHW/DCW**: Pressure system, flexible routing to risers
- **Electrical**: Routes to panel or junction box via ceiling

The system needs:
1. A flexible, pluggable heuristic architecture
2. System-specific target selection logic
3. Wet wall detection (for plumbing systems)
4. Floor penetration zone identification
5. Candidate ranking and filtering

## Solution Design

### 1. Target Candidate Generator

Base class that orchestrates target finding using pluggable heuristics:

```python
class TargetCandidateGenerator:
    """
    Generates ranked target candidates for MEP connectors.

    Uses system-specific heuristics to find and rank potential
    routing targets based on fixture location, system type,
    and building geometry.
    """

    def __init__(self):
        self.heuristics: Dict[str, TargetHeuristic] = {}
        self.targets: List[RoutingTarget] = []
        self.domains: List[RoutingDomain] = []

    def register_heuristic(self, system_type: str, heuristic: TargetHeuristic)
    def add_target(self, target: RoutingTarget)
    def add_domain(self, domain: RoutingDomain)
    def find_candidates(
        self,
        connector: ConnectorInfo,
        max_candidates: int = 5
    ) -> List[TargetCandidate]
```

### 2. Heuristic Base Class

Abstract base for system-specific heuristics:

```python
class TargetHeuristic(ABC):
    """
    Base class for target selection heuristics.

    Each MEP system type has its own heuristic that understands
    how to find and rank appropriate targets.
    """

    @abstractmethod
    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain]
    ) -> List[TargetCandidate]

    @abstractmethod
    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget
    ) -> float
```

### 3. Plumbing Heuristics

```python
class SanitaryHeuristic(TargetHeuristic):
    """
    Heuristic for sanitary (drain) systems.

    Priorities:
    1. Wet wall with drain stack (adjacent or back-to-back)
    2. Shaft with drain stack
    3. Floor penetration to below

    Considers: gravity flow, pipe slope, stack location
    """

class VentHeuristic(TargetHeuristic):
    """
    Heuristic for vent systems.

    Priorities:
    1. Combine with sanitary route to wet wall
    2. Dedicated vent in wet wall
    3. Ceiling penetration to roof vent
    """

class SupplyHeuristic(TargetHeuristic):
    """
    Heuristic for DHW/DCW (pressure supply) systems.

    Priorities:
    1. Riser in wet wall
    2. Ceiling distribution with drop
    3. Floor penetration with rise
    """
```

### 4. Electrical Heuristics

```python
class PowerHeuristic(TargetHeuristic):
    """
    Heuristic for electrical power circuits.

    Priorities:
    1. Panel boundary (wall route to panel)
    2. Junction box in ceiling (homerun)
    """

class DataHeuristic(TargetHeuristic):
    """
    Heuristic for data/low-voltage systems.

    Priorities:
    1. Patch panel / IDF
    2. Ceiling raceway

    Maintains separation from power.
    """
```

### 5. Connector Info Structure

```python
@dataclass
class ConnectorInfo:
    """
    Information about an MEP connector needing a route.

    Attributes:
        id: Unique identifier
        system_type: MEP system (Sanitary, DHW, Power, etc.)
        location: 3D world coordinates
        direction: Flow direction (inward/outward)
        diameter: Pipe/conduit size
        fixture_id: ID of parent fixture/device
        fixture_type: Type of fixture (Sink, Toilet, Outlet, etc.)
        wall_id: ID of wall fixture is mounted on (if any)
        elevation: Z elevation
    """
    id: str
    system_type: str
    location: Tuple[float, float, float]
    direction: str  # "inward" or "outward"
    diameter: float
    fixture_id: Optional[str] = None
    fixture_type: Optional[str] = None
    wall_id: Optional[str] = None
    elevation: float = 0.0
```

### 6. Wet Wall Detection

```python
def detect_wet_walls(
    walls: List[WallData],
    fixtures: List[FixtureInfo],
    adjacency_threshold: float = 2.0
) -> List[str]:
    """
    Identify walls that are or should be wet walls.

    Criteria:
    - Multiple plumbing fixtures mounted
    - Adjacent to bathroom/kitchen
    - Back-to-back with another wet wall candidate
    - Has existing drain stack

    Returns list of wall IDs that qualify as wet walls.
    """
```

## File Structure

```
src/timber_framing_generator/mep/routing/
    __init__.py              # Add new exports
    target_generator.py      # TargetCandidateGenerator, ConnectorInfo
    heuristics/
        __init__.py          # Export all heuristics
        base.py              # TargetHeuristic ABC
        plumbing.py          # Sanitary, Vent, Supply heuristics
        electrical.py        # Power, Data heuristics

scripts/
    gh_mep_target_finder.py  # GHPython component

tests/mep/routing/
    test_target_generator.py # Unit tests
    test_heuristics.py       # Heuristic-specific tests
```

## Implementation Steps

### Step 1: Create Heuristic Base Class
- Define `TargetHeuristic` ABC in `heuristics/base.py`
- Define common scoring utilities

### Step 2: Implement Plumbing Heuristics
- `SanitaryHeuristic` - drain routing
- `VentHeuristic` - vent routing
- `SupplyHeuristic` - DHW/DCW routing

### Step 3: Implement Electrical Heuristics
- `PowerHeuristic` - circuit routing
- `DataHeuristic` - low-voltage routing

### Step 4: Implement Target Candidate Generator
- `TargetCandidateGenerator` class
- `ConnectorInfo` dataclass
- Heuristic registration and dispatch

### Step 5: Implement Wet Wall Detection
- Wall analysis functions
- Fixture adjacency checking

### Step 6: Create GHPython Component
- `gh_mep_target_finder.py`
- Input: connectors_json, walls_json, targets (optional)
- Output: targets_json, debug info

### Step 7: Write Tests
- Unit tests for each heuristic
- Integration tests for generator
- Mock fixture and wall data

## GHPython Component Design

### gh_mep_target_finder.py

**Inputs**:
| Name | Type | Description |
|------|------|-------------|
| connectors_json | str | JSON with MEP connectors from Revit |
| walls_json | str | JSON with wall geometry |
| config | str | Optional configuration JSON |
| run | bool | Execute toggle |

**Outputs**:
| Name | Type | Description |
|------|------|-------------|
| targets_json | str | JSON with generated targets and candidates |
| target_points | Point3d[] | Target locations for visualization |
| candidate_lines | Line[] | Lines from connectors to candidates |
| debug_info | str | Debug information |

**Processing**:
1. Parse connectors from JSON
2. Generate targets from wall geometry (wet walls, penetration zones)
3. For each connector, find candidate targets using appropriate heuristic
4. Output ranked candidates as JSON

## Scoring Formula

Target scoring combines multiple factors:

```python
score = (
    distance_factor * distance +
    priority_factor * target.priority +
    system_match_factor * (0 if compatible else 1000) +
    floor_change_penalty * abs(floor_diff) +
    wet_wall_bonus * (-5 if target.is_wet_wall else 0)
)

# Default weights
distance_factor = 1.0
priority_factor = 0.1
system_match_factor = 1.0
floor_change_penalty = 10.0
wet_wall_bonus = 1.0
```

## Test Cases

### Unit Tests

1. **SanitaryHeuristic**
   - Prefers wet wall with drain stack
   - Falls back to floor penetration
   - Rejects ceiling targets

2. **VentHeuristic**
   - Combines with sanitary route when possible
   - Finds dedicated vent stack
   - Routes to ceiling if no wall option

3. **SupplyHeuristic**
   - Finds supply riser in wet wall
   - Accepts ceiling distribution

4. **PowerHeuristic**
   - Routes to panel boundary
   - Uses junction box for homerun

5. **TargetCandidateGenerator**
   - Registers and dispatches heuristics
   - Returns ranked candidates
   - Handles unknown system types gracefully

### Integration Tests

1. **Bathroom scenario**: Multiple fixtures finding wet wall
2. **Kitchen island**: Floor penetration for isolated fixtures
3. **Electrical outlets**: Panel routing through walls

## Exit Criteria

- [x] `TargetCandidateGenerator` class implemented
- [ ] All plumbing heuristics working (Sanitary, Vent, Supply)
- [ ] All electrical heuristics working (Power, Data)
- [ ] Wet wall detection functional
- [ ] GHPython component functional
- [ ] All unit tests passing
- [ ] Candidate ranking produces expected results

## Dependencies

- Phase 1: Core structures (RoutingTarget, RoutingDomain, etc.)

## Notes

- Heuristics are intentionally simple for Phase 1
- Future phases can add ML/RL-based heuristics using same interface
- Wet wall detection is heuristic-based, can be refined with real data
