# File: src/timber_framing_generator/mep/routing/postprocess/sanitary.py
"""
Sanitary post-processing for MEP routing.

Implements slope application, elbow optimization, and flow direction
assignment for sanitary drain and vent routes.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from copy import deepcopy

from ..route_segment import RouteSegment, SegmentDirection, Route
from ..routing_result import RoutingResult
from ..targets import RoutingTarget

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SlopeInfo:
    """
    Information about slope applied to a segment.

    Attributes:
        segment_index: Index of segment in route
        original_start_z: Original Z coordinate at start
        original_end_z: Original Z coordinate at end
        applied_start_z: New Z coordinate at start
        applied_end_z: New Z coordinate at end
        slope_ratio: Applied slope ratio (rise/run)
    """
    segment_index: int
    original_start_z: float = 0.0
    original_end_z: float = 0.0
    applied_start_z: float = 0.0
    applied_end_z: float = 0.0
    slope_ratio: float = 0.0

    @property
    def z_change(self) -> float:
        """Total Z change applied."""
        return abs(self.applied_end_z - self.applied_start_z)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "segment_index": self.segment_index,
            "original_start_z": self.original_start_z,
            "original_end_z": self.original_end_z,
            "applied_start_z": self.applied_start_z,
            "applied_end_z": self.applied_end_z,
            "slope_ratio": self.slope_ratio,
            "z_change": self.z_change,
        }


@dataclass
class ElbowPattern:
    """
    A detected elbow pattern in a route.

    Attributes:
        start_index: Index of first segment in pattern
        pattern_type: Type of pattern ("90_horizontal_to_vertical", etc.)
        can_optimize: Whether pattern can be optimized
        reason: Reason if cannot optimize
    """
    start_index: int
    pattern_type: str = "90_corner"
    can_optimize: bool = True
    reason: str = ""


@dataclass
class PostProcessResult:
    """
    Result of sanitary post-processing.

    Attributes:
        original_route: Unmodified route
        processed_route: Modified route with slope/elbows
        slope_applied: Whether slope was successfully applied
        slope_info: Details of slope application
        elbows_optimized: Number of elbows optimized
        elbow_patterns: Detected elbow patterns
        flow_direction: Assigned flow direction
        validation_errors: Any validation issues
        warnings: Non-fatal warnings
    """
    original_route: Route
    processed_route: Route
    slope_applied: bool = False
    slope_info: List[SlopeInfo] = field(default_factory=list)
    elbows_optimized: int = 0
    elbow_patterns: List[ElbowPattern] = field(default_factory=list)
    flow_direction: str = "unknown"
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if result has no validation errors."""
        return len(self.validation_errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_route_id": self.original_route.id,
            "processed_route_id": self.processed_route.id,
            "slope_applied": self.slope_applied,
            "slope_info": [s.to_dict() for s in self.slope_info],
            "elbows_optimized": self.elbows_optimized,
            "elbow_patterns": [
                {"start_index": p.start_index, "type": p.pattern_type}
                for p in self.elbow_patterns
            ],
            "flow_direction": self.flow_direction,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "is_valid": self.is_valid,
        }


# =============================================================================
# Slope Calculator
# =============================================================================

class SlopeCalculator:
    """
    Calculates and applies slope to sanitary drain segments.

    Slope is applied by adjusting Z coordinates along horizontal runs.
    Per IPC/UPC codes:
    - Pipes ≤3": Minimum 1/4" per foot (0.0208 ratio)
    - Pipes >3": Minimum 1/8" per foot (0.0104 ratio)
    """

    # Slope constants (rise/run ratio)
    SLOPE_QUARTER_INCH = 1.0 / 48.0  # 1/4" per foot ≈ 0.0208
    SLOPE_EIGHTH_INCH = 1.0 / 96.0   # 1/8" per foot ≈ 0.0104

    # Diameter threshold for slope selection (3" in feet)
    LARGE_PIPE_THRESHOLD = 0.25  # 3" = 0.25'

    def __init__(
        self,
        min_slope: Optional[float] = None,
        max_slope: float = 0.0417,  # 1/2" per foot max
        default_slope: Optional[float] = None,
    ):
        """
        Initialize slope calculator.

        Args:
            min_slope: Minimum slope ratio (default auto-calculated by pipe size)
            max_slope: Maximum slope ratio
            default_slope: Default slope when not auto-calculating
        """
        self.min_slope = min_slope
        self.max_slope = max_slope
        self.default_slope = default_slope or self.SLOPE_QUARTER_INCH

    def get_required_slope(self, pipe_diameter: float) -> float:
        """
        Get minimum required slope for pipe diameter.

        Args:
            pipe_diameter: Pipe diameter in feet

        Returns:
            Required slope ratio
        """
        if self.min_slope is not None:
            return self.min_slope

        if pipe_diameter > self.LARGE_PIPE_THRESHOLD:
            return self.SLOPE_EIGHTH_INCH
        return self.SLOPE_QUARTER_INCH

    def calculate_z_drop(
        self,
        horizontal_length: float,
        pipe_diameter: float
    ) -> float:
        """
        Calculate Z drop for a horizontal run.

        Args:
            horizontal_length: Length of horizontal segment in feet
            pipe_diameter: Pipe diameter in feet

        Returns:
            Required Z drop in feet
        """
        slope = self.get_required_slope(pipe_diameter)
        return horizontal_length * slope

    def apply_slope(
        self,
        route: Route,
        target_z: float,
        flow_toward_target: bool = True
    ) -> Tuple[Route, List[SlopeInfo]]:
        """
        Apply slope to route segments.

        Slope is applied to horizontal segments working backward from target.
        Vertical segments maintain their position.

        Args:
            route: Route to process
            target_z: Z elevation at the target end
            flow_toward_target: If True, flow goes toward target (drain)

        Returns:
            Tuple of (modified route, slope info list)
        """
        if not route.segments:
            return route, []

        slope_infos = []
        pipe_diameter = getattr(route, 'pipe_diameter', 0.0833)  # Default 1"

        # Work backwards from target
        processed_segments = []
        current_z = target_z

        segments_to_process = (
            list(reversed(route.segments))
            if flow_toward_target
            else route.segments
        )

        for i, segment in enumerate(segments_to_process):
            original_index = (
                len(route.segments) - 1 - i
                if flow_toward_target
                else i
            )

            if segment.direction == SegmentDirection.HORIZONTAL:
                # Calculate slope
                slope = self.get_required_slope(pipe_diameter)
                z_drop = segment.length * slope

                # Create sloped segment
                new_segment = self._create_sloped_segment(
                    segment,
                    start_z=current_z + z_drop,
                    end_z=current_z,
                )
                slope_info = SlopeInfo(
                    segment_index=original_index,
                    original_start_z=segment.start[1] if len(segment.start) > 1 else 0,
                    original_end_z=segment.end[1] if len(segment.end) > 1 else 0,
                    applied_start_z=current_z + z_drop,
                    applied_end_z=current_z,
                    slope_ratio=slope,
                )
                slope_infos.append(slope_info)
                current_z = current_z + z_drop
            else:
                # Vertical segment - keep at current Z
                new_segment = segment
                # Vertical segments traverse Z, update current_z
                if segment.direction == SegmentDirection.VERTICAL:
                    # Assume segment.length is the vertical distance
                    current_z = current_z + segment.length

            processed_segments.insert(0 if flow_toward_target else len(processed_segments), new_segment)

        # Reverse if we processed backward
        if flow_toward_target:
            processed_segments = list(reversed(processed_segments))

        # Create new route with processed segments
        new_route = Route(
            id=route.id,
            system_type=route.system_type,
            segments=processed_segments,
            total_length=route.total_length,
            total_cost=route.total_cost,
            metadata={**route.metadata, "slope_applied": True},
        )

        return new_route, slope_infos

    def _create_sloped_segment(
        self,
        segment: RouteSegment,
        start_z: float,
        end_z: float
    ) -> RouteSegment:
        """Create a new segment with slope applied."""
        # Update the segment's Z coordinates
        new_start = (segment.start[0], start_z) if len(segment.start) >= 2 else segment.start
        new_end = (segment.end[0], end_z) if len(segment.end) >= 2 else segment.end

        return RouteSegment(
            start=new_start,
            end=new_end,
            direction=segment.direction,
            length=segment.length,
            cost=segment.cost,
            domain_id=segment.domain_id,
            is_steiner=segment.is_steiner,
            crosses_obstacle=segment.crosses_obstacle,
        )

    def validate_slope(
        self,
        route: Route,
        cavity_height: float
    ) -> Tuple[bool, List[str]]:
        """
        Validate that route slopes fit within cavity constraints.

        Args:
            route: Route to validate
            cavity_height: Available cavity height in feet

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        pipe_diameter = getattr(route, 'pipe_diameter', 0.0833)

        total_z_drop = 0.0
        for segment in route.segments:
            if segment.direction == SegmentDirection.HORIZONTAL:
                z_drop = self.calculate_z_drop(segment.length, pipe_diameter)
                total_z_drop += z_drop

        # Check if total drop fits in cavity
        # Account for pipe diameter and clearances
        required_height = total_z_drop + pipe_diameter + 0.125  # 1.5" clearance

        if required_height > cavity_height:
            errors.append(
                f"Total Z drop ({total_z_drop:.3f}') exceeds available "
                f"cavity height ({cavity_height:.3f}')"
            )

        return len(errors) == 0, errors


# =============================================================================
# Elbow Optimizer
# =============================================================================

class ElbowOptimizer:
    """
    Optimizes elbow configurations in sanitary routes.

    Replaces 90° turn patterns with 45° configurations where possible
    to improve flow characteristics.
    """

    def __init__(self, min_segment_length: float = 0.5):
        """
        Initialize elbow optimizer.

        Args:
            min_segment_length: Minimum segment length to create (feet)
        """
        self.min_segment_length = min_segment_length

    def find_90_patterns(self, route: Route) -> List[ElbowPattern]:
        """
        Find 90° turn patterns in route.

        Patterns are where direction changes from horizontal to vertical
        or vice versa.

        Args:
            route: Route to analyze

        Returns:
            List of detected patterns
        """
        patterns = []

        if len(route.segments) < 2:
            return patterns

        for i in range(len(route.segments) - 1):
            seg1 = route.segments[i]
            seg2 = route.segments[i + 1]

            # Check for direction change
            if self._is_90_turn(seg1.direction, seg2.direction):
                pattern_type = f"{seg1.direction.value}_to_{seg2.direction.value}"
                pattern = ElbowPattern(
                    start_index=i,
                    pattern_type=pattern_type,
                    can_optimize=True,
                )

                # Check if optimization is possible
                if seg1.length < self.min_segment_length * 2:
                    pattern.can_optimize = False
                    pattern.reason = "Segment too short"
                elif seg2.length < self.min_segment_length * 2:
                    pattern.can_optimize = False
                    pattern.reason = "Next segment too short"

                patterns.append(pattern)

        return patterns

    def _is_90_turn(
        self,
        dir1: SegmentDirection,
        dir2: SegmentDirection
    ) -> bool:
        """Check if two directions form a 90° turn."""
        horizontal = {SegmentDirection.HORIZONTAL}
        vertical = {SegmentDirection.VERTICAL}

        return (
            (dir1 in horizontal and dir2 in vertical) or
            (dir1 in vertical and dir2 in horizontal)
        )

    def optimize_pattern(
        self,
        route: Route,
        pattern: ElbowPattern
    ) -> Tuple[Route, bool]:
        """
        Optimize a single 90° pattern.

        Replaces 90° turn with two 45° turns by inserting a diagonal segment.

        Args:
            route: Route containing the pattern
            pattern: Pattern to optimize

        Returns:
            Tuple of (modified route, whether optimization was applied)
        """
        if not pattern.can_optimize:
            return route, False

        idx = pattern.start_index
        if idx >= len(route.segments) - 1:
            return route, False

        seg1 = route.segments[idx]
        seg2 = route.segments[idx + 1]

        # Calculate 45° transition point
        # Use half of the shorter segment length for diagonal
        diagonal_length = min(
            seg1.length * 0.5,
            seg2.length * 0.5,
            self.min_segment_length * 2
        )

        if diagonal_length < self.min_segment_length:
            return route, False

        # Create three segments to replace two
        # 1. Shortened first segment
        # 2. Diagonal transition
        # 3. Shortened second segment

        new_seg1 = RouteSegment(
            start=seg1.start,
            end=seg1.end,  # Will be adjusted
            direction=seg1.direction,
            length=seg1.length - diagonal_length / math.sqrt(2),
            cost=seg1.cost * (1 - diagonal_length / (2 * seg1.length)),
            domain_id=seg1.domain_id,
        )

        diagonal = RouteSegment(
            start=seg1.end,  # Junction point
            end=seg2.start,  # Junction point
            direction=SegmentDirection.DIAGONAL,
            length=diagonal_length,
            cost=diagonal_length * 1.2,  # Slightly higher cost for fitting
            domain_id=seg1.domain_id,
        )

        new_seg2 = RouteSegment(
            start=seg2.start,
            end=seg2.end,
            direction=seg2.direction,
            length=seg2.length - diagonal_length / math.sqrt(2),
            cost=seg2.cost * (1 - diagonal_length / (2 * seg2.length)),
            domain_id=seg2.domain_id,
        )

        # Build new segment list
        new_segments = (
            route.segments[:idx] +
            [new_seg1, diagonal, new_seg2] +
            route.segments[idx + 2:]
        )

        new_route = Route(
            id=route.id,
            system_type=route.system_type,
            segments=new_segments,
            total_length=sum(s.length for s in new_segments),
            total_cost=sum(s.cost for s in new_segments),
            metadata={**route.metadata, "elbows_optimized": True},
        )

        return new_route, True

    def optimize_route(self, route: Route) -> Tuple[Route, int]:
        """
        Optimize all eligible 90° patterns in route.

        Args:
            route: Route to optimize

        Returns:
            Tuple of (optimized route, number of patterns optimized)
        """
        patterns = self.find_90_patterns(route)
        optimizable = [p for p in patterns if p.can_optimize]

        if not optimizable:
            return route, 0

        # Optimize patterns from end to start to preserve indices
        current_route = route
        count = 0

        for pattern in reversed(optimizable):
            current_route, was_optimized = self.optimize_pattern(
                current_route, pattern
            )
            if was_optimized:
                count += 1

        return current_route, count


# =============================================================================
# Flow Direction Assigner
# =============================================================================

class FlowDirectionAssigner:
    """
    Assigns flow direction to route segments.

    For sanitary drains: flow toward drain stack (downward/outward)
    For sanitary vents: flow upward toward roof
    """

    DRAIN_SYSTEMS = {"sanitary_drain", "sanitary", "storm_drain"}
    VENT_SYSTEMS = {"sanitary_vent", "vent"}

    def get_flow_direction(self, system_type: str) -> str:
        """
        Determine flow direction for system type.

        Args:
            system_type: MEP system type

        Returns:
            Flow direction ("toward_target", "away_from_target", "bidirectional")
        """
        system_lower = system_type.lower()

        if system_lower in self.DRAIN_SYSTEMS:
            return "toward_target"
        elif system_lower in self.VENT_SYSTEMS:
            return "away_from_target"  # Vent flows up, away from drain
        else:
            return "bidirectional"  # Pressure systems

    def assign_flow(
        self,
        route: Route,
        target_location: Tuple[float, float, float] = None
    ) -> Tuple[Route, str]:
        """
        Assign flow direction to route.

        Args:
            route: Route to process
            target_location: Location of target (for direction reference)

        Returns:
            Tuple of (route with flow metadata, flow direction)
        """
        flow_direction = self.get_flow_direction(route.system_type)

        # Add flow metadata to route
        new_metadata = {
            **route.metadata,
            "flow_direction": flow_direction,
        }

        new_route = Route(
            id=route.id,
            system_type=route.system_type,
            segments=route.segments,
            total_length=route.total_length,
            total_cost=route.total_cost,
            metadata=new_metadata,
        )

        return new_route, flow_direction

    def validate_gravity_flow(
        self,
        route: Route,
        target_z: float = 0.0
    ) -> Tuple[bool, List[str]]:
        """
        Validate that flow direction respects gravity.

        For drain systems, validates no uphill flow.

        Args:
            route: Route to validate
            target_z: Z elevation of target

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        system_type = route.system_type.lower()

        if system_type not in self.DRAIN_SYSTEMS:
            return True, []  # Only validate drains

        # Check that route generally flows downward toward target
        # This is a simplified check - full validation would check each segment
        if route.segments:
            first_seg = route.segments[0]
            last_seg = route.segments[-1]

            # Get Z values (assuming 2D tuples with Y as Z for wall plane)
            start_z = first_seg.start[1] if len(first_seg.start) > 1 else 0
            end_z = last_seg.end[1] if len(last_seg.end) > 1 else 0

            if end_z > start_z:
                errors.append(
                    f"Drain route flows uphill: start Z={start_z:.3f}, "
                    f"end Z={end_z:.3f}"
                )

        return len(errors) == 0, errors


# =============================================================================
# Unified Post-Processor
# =============================================================================

class SanitaryPostProcessor:
    """
    Complete sanitary route post-processing pipeline.

    Combines slope application, elbow optimization, and flow direction
    assignment into a single processing pipeline.
    """

    SANITARY_SYSTEMS = {
        "sanitary_drain", "sanitary_vent", "sanitary", "vent", "storm_drain"
    }

    def __init__(
        self,
        slope_calculator: Optional[SlopeCalculator] = None,
        elbow_optimizer: Optional[ElbowOptimizer] = None,
        flow_assigner: Optional[FlowDirectionAssigner] = None,
        apply_slope: bool = True,
        optimize_elbows: bool = True,
    ):
        """
        Initialize post-processor.

        Args:
            slope_calculator: Slope calculator instance
            elbow_optimizer: Elbow optimizer instance
            flow_assigner: Flow direction assigner instance
            apply_slope: Whether to apply slope
            optimize_elbows: Whether to optimize elbows
        """
        self.slope_calc = slope_calculator or SlopeCalculator()
        self.elbow_opt = elbow_optimizer or ElbowOptimizer()
        self.flow_assign = flow_assigner or FlowDirectionAssigner()
        self.apply_slope = apply_slope
        self.optimize_elbows = optimize_elbows

    def is_sanitary_route(self, route: Route) -> bool:
        """Check if route is a sanitary system."""
        return route.system_type.lower() in self.SANITARY_SYSTEMS

    def process_route(
        self,
        route: Route,
        target: Optional[RoutingTarget] = None,
        cavity_constraints: Optional[Dict[str, float]] = None
    ) -> PostProcessResult:
        """
        Process a single sanitary route.

        Args:
            route: Route to process
            target: Routing target (for flow direction)
            cavity_constraints: Cavity height constraints by domain

        Returns:
            PostProcessResult with processed route
        """
        result = PostProcessResult(
            original_route=route,
            processed_route=route,
        )

        if not self.is_sanitary_route(route):
            result.warnings.append(
                f"Route {route.id} is not a sanitary system, skipping"
            )
            return result

        current_route = route

        # 1. Assign flow direction
        current_route, flow_dir = self.flow_assign.assign_flow(
            current_route,
            target.location if target else None
        )
        result.flow_direction = flow_dir

        # 2. Apply slope (for drains)
        if self.apply_slope and route.system_type.lower() in {"sanitary_drain", "sanitary", "storm_drain"}:
            target_z = target.location[2] if target and len(target.location) > 2 else 0.0
            current_route, slope_info = self.slope_calc.apply_slope(
                current_route,
                target_z,
                flow_toward_target=True
            )
            result.slope_applied = True
            result.slope_info = slope_info

            # Validate slope
            cavity_height = 0.5  # Default 6"
            if cavity_constraints:
                domain = route.segments[0].domain_id if route.segments else "default"
                cavity_height = cavity_constraints.get(domain, 0.5)

            is_valid, errors = self.slope_calc.validate_slope(
                current_route, cavity_height
            )
            if not is_valid:
                result.validation_errors.extend(errors)

        # 3. Optimize elbows
        if self.optimize_elbows:
            patterns = self.elbow_opt.find_90_patterns(current_route)
            result.elbow_patterns = patterns

            current_route, count = self.elbow_opt.optimize_route(current_route)
            result.elbows_optimized = count

        # 4. Validate gravity flow (for drains)
        if route.system_type.lower() in {"sanitary_drain", "sanitary", "storm_drain"}:
            is_valid, errors = self.flow_assign.validate_gravity_flow(
                current_route,
                target.location[2] if target and len(target.location) > 2 else 0.0
            )
            if not is_valid:
                result.validation_errors.extend(errors)

        result.processed_route = current_route
        return result

    def process_all(
        self,
        routing_result: RoutingResult,
        targets: Optional[List[RoutingTarget]] = None,
        cavity_constraints: Optional[Dict[str, float]] = None
    ) -> Tuple[RoutingResult, List[PostProcessResult]]:
        """
        Process all sanitary routes in a routing result.

        Args:
            routing_result: Complete routing result
            targets: List of routing targets
            cavity_constraints: Cavity height constraints

        Returns:
            Tuple of (modified routing result, list of post-process results)
        """
        post_results = []
        processed_routes = []
        target_map = {t.id: t for t in (targets or [])}

        for route in routing_result.routes:
            if self.is_sanitary_route(route):
                # Find matching target
                target = target_map.get(route.metadata.get("target_id"))

                result = self.process_route(route, target, cavity_constraints)
                post_results.append(result)
                processed_routes.append(result.processed_route)
            else:
                processed_routes.append(route)

        # Create new routing result with processed routes
        new_result = RoutingResult(
            routes=processed_routes,
            failed=routing_result.failed,
            statistics=routing_result.statistics,
            timestamp=routing_result.timestamp,
            metadata={
                **routing_result.metadata,
                "sanitary_postprocess_applied": True,
            },
        )

        return new_result, post_results


# =============================================================================
# Convenience Functions
# =============================================================================

def apply_sanitary_postprocess(
    routing_result: RoutingResult,
    targets: Optional[List[RoutingTarget]] = None,
    apply_slope: bool = True,
    optimize_elbows: bool = True,
) -> Tuple[RoutingResult, List[PostProcessResult]]:
    """
    Convenience function to apply sanitary post-processing.

    Args:
        routing_result: Routing result to process
        targets: Routing targets
        apply_slope: Whether to apply slope
        optimize_elbows: Whether to optimize elbows

    Returns:
        Tuple of (processed result, post-process details)
    """
    processor = SanitaryPostProcessor(
        apply_slope=apply_slope,
        optimize_elbows=optimize_elbows,
    )
    return processor.process_all(routing_result, targets)
