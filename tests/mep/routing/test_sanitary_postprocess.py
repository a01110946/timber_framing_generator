# File: tests/mep/routing/test_sanitary_postprocess.py
"""
Unit tests for sanitary post-processing.

Tests cover:
- Slope calculation and application
- Elbow optimization (90° to 45°)
- Flow direction assignment
- Unified post-processor pipeline
"""

import pytest
import math

from src.timber_framing_generator.mep.routing import (
    SlopeCalculator,
    ElbowOptimizer,
    FlowDirectionAssigner,
    SanitaryPostProcessor,
    PostProcessResult,
    SlopeInfo,
    apply_sanitary_postprocess,
    RouteSegment,
    SegmentDirection,
    Route,
    RoutingResult,
    RoutingTarget,
    TargetType,
)


# =============================================================================
# Slope Info Tests
# =============================================================================

class TestSlopeInfo:
    """Tests for SlopeInfo dataclass."""

    def test_z_change(self):
        """Test Z change calculation."""
        info = SlopeInfo(
            segment_index=0,
            original_start_z=0.0,
            original_end_z=0.0,
            applied_start_z=0.5,
            applied_end_z=0.0,
        )
        assert info.z_change == 0.5

    def test_to_dict(self):
        """Test serialization."""
        info = SlopeInfo(
            segment_index=1,
            slope_ratio=0.0208,
        )
        data = info.to_dict()
        assert data["segment_index"] == 1
        assert data["slope_ratio"] == 0.0208


# =============================================================================
# Post Process Result Tests
# =============================================================================

class TestPostProcessResult:
    """Tests for PostProcessResult dataclass."""

    def _make_route(self, route_id="r1", system_type="sanitary_drain"):
        """Helper to create a Route."""
        return Route(
            id=route_id,
            system_type=system_type,
        )

    def test_is_valid_no_errors(self):
        """Test validity with no errors."""
        route = self._make_route()
        result = PostProcessResult(
            original_route=route,
            processed_route=route,
        )
        assert result.is_valid

    def test_is_valid_with_errors(self):
        """Test validity with errors."""
        route = self._make_route()
        result = PostProcessResult(
            original_route=route,
            processed_route=route,
            validation_errors=["Error 1"],
        )
        assert not result.is_valid

    def test_to_dict(self):
        """Test serialization."""
        route = self._make_route()
        result = PostProcessResult(
            original_route=route,
            processed_route=route,
            slope_applied=True,
            elbows_optimized=2,
        )
        data = result.to_dict()
        assert data["slope_applied"]
        assert data["elbows_optimized"] == 2


# =============================================================================
# Slope Calculator Tests
# =============================================================================

class TestSlopeCalculator:
    """Tests for SlopeCalculator."""

    def test_default_values(self):
        """Test default slope values."""
        calc = SlopeCalculator()
        assert calc.max_slope == 0.0417

    def test_get_required_slope_small_pipe(self):
        """Test slope for small pipes (≤3")."""
        calc = SlopeCalculator()
        # 2" pipe = 0.167' diameter
        slope = calc.get_required_slope(0.167)
        assert slope == pytest.approx(1.0 / 48.0, rel=0.01)  # 1/4" per foot

    def test_get_required_slope_large_pipe(self):
        """Test slope for large pipes (>3")."""
        calc = SlopeCalculator()
        # 4" pipe = 0.333' diameter
        slope = calc.get_required_slope(0.333)
        assert slope == pytest.approx(1.0 / 96.0, rel=0.01)  # 1/8" per foot

    def test_get_required_slope_custom_min(self):
        """Test with custom minimum slope."""
        calc = SlopeCalculator(min_slope=0.05)
        slope = calc.get_required_slope(0.167)
        assert slope == 0.05

    def test_calculate_z_drop(self):
        """Test Z drop calculation."""
        calc = SlopeCalculator()
        # 10 foot run with 1/4" per foot slope
        z_drop = calc.calculate_z_drop(10.0, 0.167)
        expected = 10.0 * (1.0 / 48.0)  # 10 * 0.0208 ≈ 0.208'
        assert z_drop == pytest.approx(expected, rel=0.01)

    def test_apply_slope_empty_route(self):
        """Test slope application to empty route."""
        calc = SlopeCalculator()
        route = Route(id="r1", system_type="sanitary_drain")
        new_route, info = calc.apply_slope(route, 0.0)
        assert len(info) == 0

    def test_apply_slope_horizontal_segment(self):
        """Test slope application to horizontal segment."""
        calc = SlopeCalculator()
        segment = RouteSegment(
            start=(0.0, 4.0),
            end=(10.0, 4.0),
            direction=SegmentDirection.HORIZONTAL,
            length=10.0,
        )
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[segment],
        )

        new_route, slope_info = calc.apply_slope(route, 0.0)

        assert len(slope_info) == 1
        assert slope_info[0].slope_ratio == pytest.approx(1.0 / 48.0, rel=0.01)

    def test_validate_slope_fits(self):
        """Test validation when slope fits in cavity."""
        calc = SlopeCalculator()
        segment = RouteSegment(
            start=(0.0, 4.0),
            end=(5.0, 4.0),
            direction=SegmentDirection.HORIZONTAL,
            length=5.0,
        )
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[segment],
        )

        is_valid, errors = calc.validate_slope(route, 0.5)  # 6" cavity
        assert is_valid
        assert len(errors) == 0

    def test_validate_slope_exceeds_cavity(self):
        """Test validation when slope exceeds cavity."""
        calc = SlopeCalculator()
        # Very long run in small cavity
        segment = RouteSegment(
            start=(0.0, 4.0),
            end=(100.0, 4.0),
            direction=SegmentDirection.HORIZONTAL,
            length=100.0,
        )
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[segment],
        )

        is_valid, errors = calc.validate_slope(route, 0.25)  # 3" cavity
        assert not is_valid
        assert len(errors) == 1
        assert "exceeds" in errors[0].lower()


# =============================================================================
# Elbow Optimizer Tests
# =============================================================================

class TestElbowOptimizer:
    """Tests for ElbowOptimizer."""

    def test_find_90_patterns_empty(self):
        """Test pattern finding on empty route."""
        opt = ElbowOptimizer()
        route = Route(id="r1", system_type="sanitary")
        patterns = opt.find_90_patterns(route)
        assert len(patterns) == 0

    def test_find_90_patterns_single_segment(self):
        """Test pattern finding with single segment."""
        opt = ElbowOptimizer()
        route = Route(
            id="r1",
            system_type="sanitary",
            segments=[
                RouteSegment(
                    start=(0, 0), end=(10, 0),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                )
            ]
        )
        patterns = opt.find_90_patterns(route)
        assert len(patterns) == 0

    def test_find_90_patterns_horizontal_to_vertical(self):
        """Test finding horizontal-to-vertical pattern."""
        opt = ElbowOptimizer()
        route = Route(
            id="r1",
            system_type="sanitary",
            segments=[
                RouteSegment(
                    start=(0, 0), end=(10, 0),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
                RouteSegment(
                    start=(10, 0), end=(10, 8),
                    direction=SegmentDirection.VERTICAL,
                    length=8.0,
                ),
            ]
        )
        patterns = opt.find_90_patterns(route)
        assert len(patterns) == 1
        assert patterns[0].start_index == 0
        assert "horizontal" in patterns[0].pattern_type.lower()

    def test_find_90_patterns_too_short(self):
        """Test pattern marked as not optimizable when segment too short."""
        opt = ElbowOptimizer(min_segment_length=0.5)
        route = Route(
            id="r1",
            system_type="sanitary",
            segments=[
                RouteSegment(
                    start=(0, 0), end=(0.3, 0),  # Less than 2 * min_length
                    direction=SegmentDirection.HORIZONTAL,
                    length=0.3,
                ),
                RouteSegment(
                    start=(0.3, 0), end=(0.3, 8),
                    direction=SegmentDirection.VERTICAL,
                    length=8.0,
                ),
            ]
        )
        patterns = opt.find_90_patterns(route)
        assert len(patterns) == 1
        assert not patterns[0].can_optimize
        assert "short" in patterns[0].reason.lower()

    def test_optimize_route_no_patterns(self):
        """Test optimization with no patterns."""
        opt = ElbowOptimizer()
        route = Route(
            id="r1",
            system_type="sanitary",
            segments=[
                RouteSegment(
                    start=(0, 0), end=(10, 0),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
            ]
        )
        new_route, count = opt.optimize_route(route)
        assert count == 0

    def test_optimize_route_single_pattern(self):
        """Test optimization of single 90° pattern."""
        opt = ElbowOptimizer(min_segment_length=0.3)
        route = Route(
            id="r1",
            system_type="sanitary",
            segments=[
                RouteSegment(
                    start=(0, 0), end=(10, 0),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
                RouteSegment(
                    start=(10, 0), end=(10, 8),
                    direction=SegmentDirection.VERTICAL,
                    length=8.0,
                ),
            ]
        )
        new_route, count = opt.optimize_route(route)
        assert count == 1
        # Should now have 3 segments (shortened horizontal, diagonal, shortened vertical)
        assert len(new_route.segments) == 3


# =============================================================================
# Flow Direction Assigner Tests
# =============================================================================

class TestFlowDirectionAssigner:
    """Tests for FlowDirectionAssigner."""

    def test_drain_flow_direction(self):
        """Test flow direction for drains."""
        assigner = FlowDirectionAssigner()
        direction = assigner.get_flow_direction("sanitary_drain")
        assert direction == "toward_target"

    def test_vent_flow_direction(self):
        """Test flow direction for vents."""
        assigner = FlowDirectionAssigner()
        direction = assigner.get_flow_direction("sanitary_vent")
        assert direction == "away_from_target"

    def test_supply_flow_direction(self):
        """Test flow direction for supply systems."""
        assigner = FlowDirectionAssigner()
        direction = assigner.get_flow_direction("dhw")
        assert direction == "bidirectional"

    def test_assign_flow(self):
        """Test flow assignment to route."""
        assigner = FlowDirectionAssigner()
        route = Route(id="r1", system_type="sanitary_drain")
        new_route, direction = assigner.assign_flow(route)
        assert direction == "toward_target"
        assert new_route.metadata.get("flow_direction") == "toward_target"

    def test_validate_gravity_flow_valid(self):
        """Test gravity validation for downhill flow."""
        assigner = FlowDirectionAssigner()
        # Route flows downhill (start Z > end Z)
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[
                RouteSegment(
                    start=(0, 4.5),  # Higher Y = Higher Z
                    end=(10, 4.0),   # Lower Y = Lower Z
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
            ]
        )
        is_valid, errors = assigner.validate_gravity_flow(route)
        assert is_valid

    def test_validate_gravity_flow_invalid(self):
        """Test gravity validation for uphill flow."""
        assigner = FlowDirectionAssigner()
        # Route flows uphill
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[
                RouteSegment(
                    start=(0, 4.0),  # Lower Z
                    end=(10, 5.0),   # Higher Z - BAD
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
            ]
        )
        is_valid, errors = assigner.validate_gravity_flow(route)
        assert not is_valid
        assert len(errors) == 1
        assert "uphill" in errors[0].lower()

    def test_validate_skips_non_drains(self):
        """Test that validation skips non-drain systems."""
        assigner = FlowDirectionAssigner()
        route = Route(id="r1", system_type="power")
        is_valid, errors = assigner.validate_gravity_flow(route)
        assert is_valid


# =============================================================================
# Sanitary Post-Processor Tests
# =============================================================================

class TestSanitaryPostProcessor:
    """Tests for SanitaryPostProcessor."""

    def _make_route(self, route_id="r1", system_type="sanitary_drain"):
        """Helper to create a basic route."""
        return Route(
            id=route_id,
            system_type=system_type,
            segments=[
                RouteSegment(
                    start=(0, 4.0),
                    end=(10, 4.0),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
            ]
        )

    def _make_target(self, target_id="t1"):
        """Helper to create a target."""
        return RoutingTarget(
            id=target_id,
            target_type=TargetType.WET_WALL,
            location=(10.0, 0.0, 0.0),
            domain_id="wall_1",
            plane_location=(10.0, 0.0),
            systems_served=["sanitary_drain"],
        )

    def test_is_sanitary_route(self):
        """Test sanitary system detection."""
        processor = SanitaryPostProcessor()
        assert processor.is_sanitary_route(self._make_route())
        assert processor.is_sanitary_route(
            self._make_route(system_type="sanitary_vent")
        )
        assert not processor.is_sanitary_route(
            self._make_route(system_type="power")
        )

    def test_process_route_basic(self):
        """Test basic route processing."""
        processor = SanitaryPostProcessor()
        route = self._make_route()
        result = processor.process_route(route)

        assert result.slope_applied
        assert result.flow_direction == "toward_target"

    def test_process_route_non_sanitary(self):
        """Test processing non-sanitary route."""
        processor = SanitaryPostProcessor()
        route = self._make_route(system_type="power")
        result = processor.process_route(route)

        assert not result.slope_applied
        assert len(result.warnings) == 1

    def test_process_route_with_target(self):
        """Test processing with target."""
        processor = SanitaryPostProcessor()
        route = self._make_route()
        target = self._make_target()
        result = processor.process_route(route, target)

        assert result.slope_applied

    def test_process_all_mixed_routes(self):
        """Test processing mixed sanitary and non-sanitary routes."""
        processor = SanitaryPostProcessor()

        routing_result = RoutingResult()
        routing_result.routes = [
            self._make_route("r1", "sanitary_drain"),
            self._make_route("r2", "power"),
            self._make_route("r3", "sanitary_vent"),
        ]

        new_result, post_results = processor.process_all(routing_result)

        # Should have processed 2 sanitary routes
        assert len(post_results) == 2
        assert new_result.metadata.get("sanitary_postprocess_applied")

    def test_disabled_slope(self):
        """Test with slope disabled."""
        processor = SanitaryPostProcessor(apply_slope=False)
        route = self._make_route()
        result = processor.process_route(route)

        assert not result.slope_applied

    def test_disabled_elbows(self):
        """Test with elbow optimization disabled."""
        processor = SanitaryPostProcessor(optimize_elbows=False)
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[
                RouteSegment(
                    start=(0, 0), end=(10, 0),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
                RouteSegment(
                    start=(10, 0), end=(10, 8),
                    direction=SegmentDirection.VERTICAL,
                    length=8.0,
                ),
            ]
        )
        result = processor.process_route(route)

        assert result.elbows_optimized == 0


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_apply_sanitary_postprocess(self):
        """Test the convenience function."""
        routing_result = RoutingResult()
        routing_result.routes = [
            Route(
                id="r1",
                system_type="sanitary_drain",
                segments=[
                    RouteSegment(
                        start=(0, 4.0),
                        end=(10, 4.0),
                        direction=SegmentDirection.HORIZONTAL,
                        length=10.0,
                    ),
                ]
            )
        ]

        new_result, post_results = apply_sanitary_postprocess(routing_result)

        assert len(post_results) == 1
        assert post_results[0].slope_applied


# =============================================================================
# Integration Tests
# =============================================================================

class TestPostProcessIntegration:
    """Integration tests for sanitary post-processing."""

    def test_complete_bathroom_route(self):
        """Test processing a complete bathroom drain route."""
        # Simulate a route from toilet to stack
        route = Route(
            id="toilet_drain",
            system_type="sanitary_drain",
            segments=[
                # Horizontal from toilet to wall
                RouteSegment(
                    start=(3, 4),
                    end=(8, 4),
                    direction=SegmentDirection.HORIZONTAL,
                    length=5.0,
                ),
                # Vertical down wall
                RouteSegment(
                    start=(8, 4),
                    end=(8, 0),
                    direction=SegmentDirection.VERTICAL,
                    length=4.0,
                ),
            ],
            total_length=9.0,
        )

        processor = SanitaryPostProcessor()
        target = RoutingTarget(
            id="drain_stack",
            target_type=TargetType.WET_WALL,
            location=(8.0, 0.0, 0.0),
            domain_id="wall_1",
            plane_location=(8.0, 0.0),
            systems_served=["sanitary_drain"],
        )

        result = processor.process_route(route, target)

        assert result.is_valid
        assert result.slope_applied
        assert result.flow_direction == "toward_target"

    def test_vent_route_no_slope(self):
        """Test that vent routes don't get slope applied."""
        route = Route(
            id="vent",
            system_type="sanitary_vent",
            segments=[
                RouteSegment(
                    start=(3, 4),
                    end=(3, 8),
                    direction=SegmentDirection.VERTICAL,
                    length=4.0,
                ),
            ]
        )

        processor = SanitaryPostProcessor()
        result = processor.process_route(route)

        # Vent should not have slope applied (only drains get slope)
        assert not result.slope_applied
        assert result.flow_direction == "away_from_target"

    def test_post_process_result_serialization(self):
        """Test that results can be serialized."""
        route = Route(
            id="r1",
            system_type="sanitary_drain",
            segments=[
                RouteSegment(
                    start=(0, 4),
                    end=(10, 4),
                    direction=SegmentDirection.HORIZONTAL,
                    length=10.0,
                ),
            ]
        )

        processor = SanitaryPostProcessor()
        result = processor.process_route(route)

        # Should serialize without error
        data = result.to_dict()
        assert "slope_applied" in data
        assert "flow_direction" in data
        assert "is_valid" in data
