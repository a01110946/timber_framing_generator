# PRP-018: MEP Routing Sanitary Post-Processing

## Overview

**Feature**: Sanitary Post-Processing (Slope and Elbow Optimization)
**Branch**: `feature/mep-routing-phase8-sanitary`
**Issue**: #33 - MEP Routing Solver: OAHS Implementation Plan (Phase 8)

## Problem Statement

Sanitary routes from OAHS need post-processing to be code-compliant:

1. **Slope Application**: Horizontal drain segments need 1/4" per foot slope
2. **45° Elbow Optimization**: Replace 90° + 90° patterns with 45° + 45°
3. **Flow Direction**: Assign flow direction to each segment
4. **Slope Validation**: Check slopes fit within wall cavity constraints

## Background: Sanitary Piping Requirements

### Slope Requirements (IPC/UPC)
- Minimum slope: 1/4" per foot (1:48 ratio) for pipes ≤3"
- Minimum slope: 1/8" per foot (1:96 ratio) for pipes >3"
- Slope direction: Always toward drain stack

### Elbow Optimization
- 90° bends create turbulence and potential clogs
- 45° + 45° patterns improve flow characteristics
- Wye fittings preferred over tees for horizontal branches

## Solution Design

### 1. SlopeCalculator Class

```python
class SlopeCalculator:
    """
    Calculates and applies slope to sanitary segments.

    Slope is applied by adjusting Z coordinates along horizontal runs.
    """

    def __init__(
        self,
        min_slope: float = 0.0208,  # 1/4" per foot
        max_slope: float = 0.0417,  # 1/2" per foot
    ):
        self.min_slope = min_slope
        self.max_slope = max_slope

    def calculate_slope(self, segment: RouteSegment, pipe_diameter: float) -> float:
        """Calculate required slope for segment."""

    def apply_slope(self, route: Route, flow_direction: str) -> Route:
        """Apply slope adjustments to route segments."""

    def validate_slope(
        self,
        route: Route,
        cavity_height: float
    ) -> Tuple[bool, List[str]]:
        """Validate route slopes fit within cavity constraints."""
```

### 2. ElbowOptimizer Class

```python
class ElbowOptimizer:
    """
    Optimizes elbow configurations in routes.

    Replaces 90° patterns with 45° configurations where possible.
    """

    def __init__(self, min_segment_length: float = 0.5):
        self.min_segment_length = min_segment_length

    def find_90_patterns(self, route: Route) -> List[int]:
        """Find segment indices that form 90° turns."""

    def can_optimize(
        self,
        route: Route,
        pattern_index: int
    ) -> bool:
        """Check if pattern can be optimized to 45°."""

    def optimize_route(self, route: Route) -> Route:
        """Optimize all eligible patterns in route."""
```

### 3. FlowDirectionAssigner Class

```python
class FlowDirectionAssigner:
    """
    Assigns flow direction to route segments.

    For sanitary: flow is always toward drain/stack.
    For vent: flow is always upward.
    """

    def assign_flow(
        self,
        route: Route,
        target_location: Tuple[float, float, float]
    ) -> Route:
        """Assign flow direction based on target location."""

    def validate_gravity_flow(self, route: Route) -> Tuple[bool, List[str]]:
        """Validate flow directions respect gravity."""
```

### 4. SanitaryPostProcessor Class

```python
class SanitaryPostProcessor:
    """
    Complete sanitary route post-processing pipeline.

    Combines slope, elbow, and flow processing.
    """

    def __init__(
        self,
        slope_calculator: SlopeCalculator = None,
        elbow_optimizer: ElbowOptimizer = None,
        flow_assigner: FlowDirectionAssigner = None,
    ):
        self.slope_calc = slope_calculator or SlopeCalculator()
        self.elbow_opt = elbow_optimizer or ElbowOptimizer()
        self.flow_assign = flow_assigner or FlowDirectionAssigner()

    def process_route(
        self,
        route: Route,
        target: RoutingTarget,
        cavity_constraints: Dict[str, float] = None
    ) -> PostProcessResult:
        """Process a single sanitary route."""

    def process_all(
        self,
        routing_result: RoutingResult,
        targets: List[RoutingTarget]
    ) -> RoutingResult:
        """Process all sanitary routes in a result."""
```

### 5. PostProcessResult

```python
@dataclass
class PostProcessResult:
    """
    Result of sanitary post-processing.

    Attributes:
        original_route: Unmodified route
        processed_route: Modified route with slope/elbows
        slope_applied: Whether slope was applied
        elbows_optimized: Number of elbows optimized
        validation_errors: Any validation issues
    """
    original_route: Route
    processed_route: Route
    slope_applied: bool = False
    elbows_optimized: int = 0
    validation_errors: List[str] = field(default_factory=list)
```

## File Structure

```
src/timber_framing_generator/mep/routing/postprocess/
    __init__.py
    sanitary.py          # SlopeCalculator, ElbowOptimizer
    flow_direction.py    # FlowDirectionAssigner
    processor.py         # SanitaryPostProcessor

tests/mep/routing/
    test_sanitary_postprocess.py
```

## Implementation Steps

### Step 1: Data Structures
- PostProcessResult dataclass
- SlopeInfo dataclass
- ElbowPattern detection

### Step 2: Slope Calculator
- Calculate required slope
- Apply slope to segments
- Validate against constraints

### Step 3: Elbow Optimizer
- Detect 90° patterns
- Replace with 45° + 45°
- Adjust segment geometry

### Step 4: Flow Direction
- Assign direction based on target
- Validate gravity flow

### Step 5: Unified Processor
- SanitaryPostProcessor class
- Integration with RoutingResult
- Error handling

### Step 6: Tests
- Slope calculation tests
- Elbow optimization tests
- Flow direction tests
- Integration tests

## Algorithm Details

### Slope Application

```python
def apply_slope(self, route: Route, target_z: float) -> Route:
    """Apply slope to horizontal segments."""
    processed_segments = []
    current_z = target_z  # Start from target

    # Work backwards from target
    for segment in reversed(route.segments):
        if segment.direction == SegmentDirection.HORIZONTAL:
            # Calculate z rise
            rise = segment.length * self.min_slope
            new_segment = segment.with_slope(
                start_z=current_z + rise,
                end_z=current_z
            )
            current_z = current_z + rise
        else:
            # Vertical segments don't change
            new_segment = segment.with_z(current_z)

        processed_segments.insert(0, new_segment)

    return Route(segments=processed_segments, ...)
```

### 45° Elbow Detection

```
Pattern Detection:
    H  V      becomes    H  D  V
    └──┘                 └──╲──┘

Where:
- H = horizontal segment
- V = vertical segment
- D = 45° diagonal segment
```

## Test Cases

### Slope Calculation
1. Standard 3" pipe → 1/4"/ft slope
2. 4" pipe → 1/8"/ft slope
3. Long horizontal run → validates correctly

### Elbow Optimization
1. Single 90° pattern → optimized to 45°+45°
2. Multiple patterns in route → all optimized
3. Constrained space → no optimization

### Flow Direction
1. Drain route → flow toward stack
2. Vent route → flow upward
3. Multi-segment route → consistent direction

### Integration
1. Complete bathroom route → fully processed
2. Kitchen route → slope and flow assigned
3. Invalid route → validation errors returned

## Exit Criteria

- [ ] SlopeCalculator with slope application
- [ ] ElbowOptimizer with 45° conversion
- [ ] FlowDirectionAssigner with validation
- [ ] SanitaryPostProcessor unified pipeline
- [ ] PostProcessResult with diagnostics
- [ ] Integration with RoutingResult
- [ ] All tests passing

## Dependencies

- Phase 4: RouteSegment, Route
- Phase 6: RoutingResult
- Phase 7: OrchestrationResult (optional)
