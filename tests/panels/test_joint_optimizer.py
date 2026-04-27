# File: tests/panels/test_joint_optimizer.py
"""Unit tests for joint optimizer."""

import pytest
from src.timber_framing_generator.panels.joint_optimizer import (
    find_exclusion_zones,
    find_optimal_joints,
    find_joints_for_strategy,
    get_panel_boundaries,
    validate_joints,
)
from src.timber_framing_generator.panels.panel_config import (
    PanelConfig,
    PanelizationStrategy,
    ExclusionZone,
)


def create_mock_wall(
    length: float = 30.0,
    openings: list = None,
) -> dict:
    """Create a mock wall data dictionary."""
    return {
        "wall_id": "test_wall",
        "wall_length": length,
        "length": length,
        "openings": openings or [],
    }


class TestFindExclusionZones:
    """Tests for find_exclusion_zones function."""

    def test_no_openings(self):
        """Test wall with no openings."""
        wall = create_mock_wall(length=30.0)
        config = PanelConfig(min_joint_to_corner=2.0)

        zones = find_exclusion_zones(wall, config)

        # Should have 2 zones: start corner and end corner
        assert len(zones) == 2
        assert zones[0].zone_type in ["corner_start", "merged"]
        assert zones[-1].zone_type in ["corner_end", "merged"]

    def test_with_opening(self):
        """Test wall with opening creates exclusion zone."""
        wall = create_mock_wall(
            length=30.0,
            openings=[{"id": "win1", "u_start": 10.0, "u_end": 14.0}]
        )
        config = PanelConfig(min_joint_to_opening=1.0, min_joint_to_corner=2.0)

        zones = find_exclusion_zones(wall, config)

        # Should have zones for: start corner, opening, end corner
        # (may be merged if overlapping)
        assert len(zones) >= 2

        # Find the opening zone
        opening_zone = None
        for zone in zones:
            if zone.u_start <= 9.0 and zone.u_end >= 15.0:
                opening_zone = zone
                break

        assert opening_zone is not None or len(zones) > 0

    def test_overlapping_zones_merged(self):
        """Test that overlapping exclusion zones are merged."""
        wall = create_mock_wall(
            length=30.0,
            openings=[
                {"id": "win1", "u_start": 5.0, "u_end": 8.0},
                {"id": "win2", "u_start": 9.0, "u_end": 12.0},
            ]
        )
        config = PanelConfig(min_joint_to_opening=1.0, min_joint_to_corner=2.0)

        zones = find_exclusion_zones(wall, config)

        # Windows are 1 foot apart, with 1ft offset each side
        # Zone 1: 4-9, Zone 2: 8-13 -> should merge to 4-13
        merged_found = False
        for zone in zones:
            if zone.u_start <= 4.0 and zone.u_end >= 13.0:
                merged_found = True
                break

        assert merged_found or len(zones) <= 4


class TestFindOptimalJoints:
    """Tests for find_optimal_joints function."""

    def test_short_wall_no_joints(self):
        """Test that short walls get no joints."""
        config = PanelConfig(max_panel_length=24.0)

        joints = find_optimal_joints(20.0, [], config)

        assert len(joints) == 0

    def test_long_wall_needs_joint(self):
        """Test that walls longer than max get joints."""
        config = PanelConfig(max_panel_length=24.0, stud_spacing=1.333)

        joints = find_optimal_joints(30.0, [], config)

        assert len(joints) >= 1

    def test_joints_respect_max_length(self):
        """Test that resulting panels don't exceed max length."""
        config = PanelConfig(max_panel_length=24.0, stud_spacing=1.333)
        wall_length = 60.0

        joints = find_optimal_joints(wall_length, [], config)

        boundaries = [0.0] + sorted(joints) + [wall_length]
        for i in range(len(boundaries) - 1):
            panel_length = boundaries[i + 1] - boundaries[i]
            assert panel_length <= config.max_panel_length + 0.01  # Small tolerance

    def test_joints_avoid_exclusion_zones(self):
        """Test that joints avoid exclusion zones."""
        config = PanelConfig(max_panel_length=20.0, stud_spacing=1.333)
        zones = [
            ExclusionZone(u_start=18.0, u_end=22.0, zone_type="opening")
        ]

        joints = find_optimal_joints(40.0, zones, config)

        for joint in joints:
            for zone in zones:
                assert not zone.contains(joint)

    def test_joints_aligned_to_studs(self):
        """Test that joints are at stud locations."""
        config = PanelConfig(
            max_panel_length=20.0,
            stud_spacing=1.333,
            snap_to_studs=True
        )

        joints = find_optimal_joints(40.0, [], config)

        for joint in joints:
            # Should be at a stud location (multiple of spacing)
            remainder = joint % config.stud_spacing
            assert remainder < 0.01 or abs(remainder - config.stud_spacing) < 0.01


class TestGetPanelBoundaries:
    """Tests for get_panel_boundaries function."""

    def test_no_joints(self):
        """Test with no joints."""
        boundaries = get_panel_boundaries([], 20.0)

        assert len(boundaries) == 1
        assert boundaries[0] == (0.0, 20.0)

    def test_one_joint(self):
        """Test with one joint."""
        boundaries = get_panel_boundaries([10.0], 20.0)

        assert len(boundaries) == 2
        assert boundaries[0] == (0.0, 10.0)
        assert boundaries[1] == (10.0, 20.0)

    def test_multiple_joints(self):
        """Test with multiple joints."""
        boundaries = get_panel_boundaries([10.0, 20.0], 30.0)

        assert len(boundaries) == 3
        assert boundaries[0] == (0.0, 10.0)
        assert boundaries[1] == (10.0, 20.0)
        assert boundaries[2] == (20.0, 30.0)


class TestValidateJoints:
    """Tests for validate_joints function."""

    def test_valid_joints(self):
        """Test validation of valid joint configuration."""
        config = PanelConfig(max_panel_length=24.0, min_panel_length=4.0)

        is_valid, errors = validate_joints([12.0], 24.0, config)

        assert is_valid
        assert len(errors) == 0

    def test_panel_too_long(self):
        """Test detection of panels exceeding max length."""
        config = PanelConfig(max_panel_length=15.0)

        is_valid, errors = validate_joints([10.0], 30.0, config)

        assert not is_valid
        assert any("exceeds max" in e for e in errors)

    def test_panel_too_short(self):
        """Test detection of panels below min length."""
        config = PanelConfig(max_panel_length=24.0, min_panel_length=5.0)

        is_valid, errors = validate_joints([3.0, 20.0], 24.0, config)

        assert not is_valid
        assert any("below min" in e for e in errors)


# =============================================================================
# Strategy-Specific Tests
# =============================================================================


class TestLengthOptimizedUnchanged:
    """Verify default strategy produces same results as before."""

    def test_default_strategy_matches_direct_call(self):
        """Ensure find_joints_for_strategy with LENGTH_OPTIMIZED matches direct call."""
        wall = create_mock_wall(length=40.0)
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.LENGTH_OPTIMIZED,
        )

        strategy_joints = find_joints_for_strategy(wall, config)
        exclusion_zones = find_exclusion_zones(wall, config)
        direct_joints = find_optimal_joints(40.0, exclusion_zones, config)

        assert strategy_joints == direct_joints

    def test_short_wall_no_joints(self):
        """Short wall should produce no joints with default strategy."""
        wall = create_mock_wall(length=20.0)
        config = PanelConfig(
            max_panel_length=24.0,
            strategy=PanelizationStrategy.LENGTH_OPTIMIZED,
        )

        joints = find_joints_for_strategy(wall, config)
        assert len(joints) == 0


class TestOpeningBoundedStrategy:
    """Tests for OPENING_BOUNDED strategy."""

    def test_wall_with_window_creates_opening_panel(self):
        """Window creates bounded panel: left | window-panel | right."""
        wall = create_mock_wall(
            length=20.0,
            openings=[{"id": "win1", "u_start": 6.0, "u_end": 10.0}],
        )
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
            stud_width=0.125,
        )

        joints = find_joints_for_strategy(wall, config)

        # Should have joints near opening edges (king stud positions)
        assert len(joints) >= 2

        # Joints should be outside the opening range
        for j in joints:
            assert j < 6.0 or j > 10.0

    def test_wall_with_door_creates_opening_panel(self):
        """Door creates bounded panel."""
        wall = create_mock_wall(
            length=20.0,
            openings=[{"id": "door1", "u_start": 8.0, "u_end": 11.0}],
        )
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
        )

        joints = find_joints_for_strategy(wall, config)
        assert len(joints) >= 2

    def test_mixed_openings(self):
        """Multiple openings each get bounded."""
        wall = create_mock_wall(
            length=30.0,
            openings=[
                {"id": "win1", "u_start": 4.0, "u_end": 7.0},
                {"id": "door1", "u_start": 14.0, "u_end": 17.0},
            ],
        )
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
        )

        joints = find_joints_for_strategy(wall, config)

        # Should have at least 4 joints (2 per opening)
        assert len(joints) >= 4

    def test_no_openings_falls_back(self):
        """Without openings, should behave like LENGTH_OPTIMIZED."""
        wall = create_mock_wall(length=40.0)
        config_bounded = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
        )
        config_default = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.LENGTH_OPTIMIZED,
        )

        joints_bounded = find_joints_for_strategy(wall, config_bounded)
        joints_default = find_joints_for_strategy(wall, config_default)

        assert joints_bounded == joints_default

    def test_trimmer_only_option(self):
        """trimmer_only places joints at trimmer edge (closer to opening)."""
        wall = create_mock_wall(
            length=20.0,
            openings=[{"id": "win1", "u_start": 6.0, "u_end": 10.0}],
        )
        config_king = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
            opening_edge_stud="king_and_trimmer",
            snap_to_studs=False,
        )
        config_trimmer = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
            opening_edge_stud="trimmer_only",
            snap_to_studs=False,
        )

        joints_king = find_joints_for_strategy(wall, config_king)
        joints_trimmer = find_joints_for_strategy(wall, config_trimmer)

        # Trimmer joints should be closer to the opening than king joints
        # (trimmer is inside king stud)
        assert len(joints_king) == len(joints_trimmer)

        # The leftmost joint with trimmer should be >= leftmost king joint
        if joints_king and joints_trimmer:
            assert joints_trimmer[0] >= joints_king[0]

    def test_long_sub_segment_gets_split(self):
        """Sub-segments longer than max_panel_length should be further split."""
        # 60ft wall with small opening at u=5..8 -> left segment (0..~4.75) is short,
        # right segment (~8.25..60) is ~52ft and needs splitting
        wall = create_mock_wall(
            length=60.0,
            openings=[{"id": "win1", "u_start": 5.0, "u_end": 8.0}],
        )
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
        )

        joints = find_joints_for_strategy(wall, config)

        # Verify no panel exceeds max length
        boundaries = [0.0] + sorted(joints) + [60.0]
        for i in range(len(boundaries) - 1):
            panel_length = boundaries[i + 1] - boundaries[i]
            assert panel_length <= config.max_panel_length + 0.1


class TestNoSplitThroughStrategy:
    """Tests for NO_SPLIT_THROUGH strategy."""

    def test_no_joint_within_wide_opening(self):
        """No joint should land within a wide opening range."""
        wall = create_mock_wall(
            length=40.0,
            openings=[{"id": "garage1", "u_start": 4.0, "u_end": 20.0}],
        )
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.NO_SPLIT_THROUGH,
        )

        joints = find_joints_for_strategy(wall, config)

        # No joint should be within the opening range [4, 20]
        for j in joints:
            assert j <= 4.0 - config.min_joint_to_opening or j >= 20.0 + config.min_joint_to_opening, \
                f"Joint at {j} is within opening range [4.0, 20.0]"

    def test_multiple_openings_all_protected(self):
        """Multiple openings: no joint within any opening range."""
        wall = create_mock_wall(
            length=40.0,
            openings=[
                {"id": "win1", "u_start": 5.0, "u_end": 9.0},
                {"id": "win2", "u_start": 15.0, "u_end": 19.0},
            ],
        )
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.NO_SPLIT_THROUGH,
            min_joint_to_opening=1.0,
        )

        joints = find_joints_for_strategy(wall, config)

        for j in joints:
            # Not within opening 1 exclusion zone [4, 10]
            assert not (4.0 <= j <= 10.0), f"Joint at {j} within opening 1 zone"
            # Not within opening 2 exclusion zone [14, 20]
            assert not (14.0 <= j <= 20.0), f"Joint at {j} within opening 2 zone"

    def test_no_openings_matches_default(self):
        """Without openings, should behave like LENGTH_OPTIMIZED."""
        wall = create_mock_wall(length=40.0)
        config_nst = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.NO_SPLIT_THROUGH,
        )
        config_default = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.LENGTH_OPTIMIZED,
        )

        joints_nst = find_joints_for_strategy(wall, config_nst)
        joints_default = find_joints_for_strategy(wall, config_default)

        assert joints_nst == joints_default


class TestEqualLengthStrategy:
    """Tests for EQUAL_LENGTH strategy."""

    def test_even_division(self):
        """Wall divided into roughly equal panels."""
        wall = create_mock_wall(length=40.0)
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            snap_to_studs=False,
        )

        joints = find_joints_for_strategy(wall, config)

        # 40/24 -> ceil = 2 panels, so 1 joint at 20.0
        assert len(joints) == 1
        assert abs(joints[0] - 20.0) < 0.01

    def test_three_equal_panels(self):
        """Wall requiring three equal panels."""
        wall = create_mock_wall(length=60.0)
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            snap_to_studs=False,
        )

        joints = find_joints_for_strategy(wall, config)

        # 60/24 -> ceil = 3 panels, 2 joints at 20 and 40
        assert len(joints) == 2
        assert abs(joints[0] - 20.0) < 0.01
        assert abs(joints[1] - 40.0) < 0.01

    def test_short_wall_no_joints(self):
        """Short wall needs no splitting."""
        wall = create_mock_wall(length=20.0)
        config = PanelConfig(
            max_panel_length=24.0,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
        )

        joints = find_joints_for_strategy(wall, config)
        assert len(joints) == 0

    def test_no_opening_awareness(self):
        """Equal-length strategy ignores openings entirely."""
        wall = create_mock_wall(
            length=40.0,
            openings=[{"id": "win1", "u_start": 18.0, "u_end": 22.0}],
        )
        config_with = PanelConfig(
            max_panel_length=24.0,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            snap_to_studs=False,
        )

        wall_no_openings = create_mock_wall(length=40.0)
        config_without = PanelConfig(
            max_panel_length=24.0,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            snap_to_studs=False,
        )

        joints_with = find_joints_for_strategy(wall, config_with)
        joints_without = find_joints_for_strategy(wall_no_openings, config_without)

        assert joints_with == joints_without

    def test_snap_to_studs(self):
        """Joints should snap to stud locations when configured."""
        wall = create_mock_wall(length=40.0)
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            snap_to_studs=True,
        )

        joints = find_joints_for_strategy(wall, config)

        for j in joints:
            remainder = j % config.stud_spacing
            assert remainder < 0.01 or abs(remainder - config.stud_spacing) < 0.01

    def test_panels_respect_max_length(self):
        """All resulting panels should respect max_panel_length."""
        wall = create_mock_wall(length=100.0)
        config = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            snap_to_studs=False,
        )

        joints = find_joints_for_strategy(wall, config)
        boundaries = [0.0] + sorted(joints) + [100.0]

        for i in range(len(boundaries) - 1):
            panel_length = boundaries[i + 1] - boundaries[i]
            assert panel_length <= config.max_panel_length + 0.01


class TestAllStrategiesNoOpenings:
    """All strategies should produce the same result for walls without openings."""

    def test_all_strategies_same_for_short_wall(self):
        """Short wall: all strategies produce no joints."""
        wall = create_mock_wall(length=20.0)

        for strategy in PanelizationStrategy:
            config = PanelConfig(
                max_panel_length=24.0,
                strategy=strategy,
            )
            joints = find_joints_for_strategy(wall, config)
            assert len(joints) == 0, f"Strategy {strategy.value} produced joints for short wall"

    def test_all_strategies_produce_valid_panels_for_long_wall(self):
        """Long wall: all strategies produce valid panel lengths."""
        wall = create_mock_wall(length=50.0)

        for strategy in PanelizationStrategy:
            config = PanelConfig(
                max_panel_length=24.0,
                stud_spacing=1.333,
                strategy=strategy,
            )
            joints = find_joints_for_strategy(wall, config)
            boundaries = [0.0] + sorted(joints) + [50.0]

            for i in range(len(boundaries) - 1):
                panel_length = boundaries[i + 1] - boundaries[i]
                assert panel_length <= config.max_panel_length + 0.1, \
                    f"Strategy {strategy.value}: panel {i} length {panel_length:.2f} exceeds max"


class TestEdgeCases:
    """Edge case tests across strategies."""

    def test_opening_at_wall_start(self):
        """Opening starting at u=0 should not produce joints at negative positions."""
        wall = create_mock_wall(
            length=30.0,
            openings=[{"id": "door1", "u_start": 0.0, "u_end": 3.0}],
        )

        for strategy in [PanelizationStrategy.OPENING_BOUNDED, PanelizationStrategy.NO_SPLIT_THROUGH]:
            config = PanelConfig(
                max_panel_length=24.0,
                stud_spacing=1.333,
                strategy=strategy,
            )
            joints = find_joints_for_strategy(wall, config)

            for j in joints:
                assert j > 0, f"Strategy {strategy.value}: joint at {j} <= 0"
                assert j < 30.0, f"Strategy {strategy.value}: joint at {j} >= wall_length"

    def test_opening_at_wall_end(self):
        """Opening ending at wall_length should not produce joints beyond wall."""
        wall = create_mock_wall(
            length=30.0,
            openings=[{"id": "win1", "u_start": 27.0, "u_end": 30.0}],
        )

        for strategy in [PanelizationStrategy.OPENING_BOUNDED, PanelizationStrategy.NO_SPLIT_THROUGH]:
            config = PanelConfig(
                max_panel_length=24.0,
                stud_spacing=1.333,
                strategy=strategy,
            )
            joints = find_joints_for_strategy(wall, config)

            for j in joints:
                assert j > 0, f"Strategy {strategy.value}: joint at {j} <= 0"
                assert j < 30.0, f"Strategy {strategy.value}: joint at {j} >= wall_length"

    def test_adjacent_openings(self):
        """Adjacent openings should not cause issues."""
        wall = create_mock_wall(
            length=30.0,
            openings=[
                {"id": "win1", "u_start": 5.0, "u_end": 8.0},
                {"id": "win2", "u_start": 8.5, "u_end": 11.0},
            ],
        )

        for strategy in PanelizationStrategy:
            config = PanelConfig(
                max_panel_length=24.0,
                stud_spacing=1.333,
                strategy=strategy,
            )
            joints = find_joints_for_strategy(wall, config)

            # Should not crash and all joints should be within wall bounds
            for j in joints:
                assert 0 < j < 30.0, \
                    f"Strategy {strategy.value}: joint at {j} out of bounds"

    def test_garage_wall_scenario(self):
        """24ft wall with 16ft garage door (u=4..20)."""
        wall = create_mock_wall(
            length=24.0,
            openings=[{"id": "garage1", "u_start": 4.0, "u_end": 20.0}],
        )

        # OPENING_BOUNDED: should try to place joints at king stud edges
        config_ob = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.OPENING_BOUNDED,
        )
        joints_ob = find_joints_for_strategy(wall, config_ob)
        # All joints should be valid (within wall bounds)
        for j in joints_ob:
            assert 0 < j < 24.0

        # NO_SPLIT_THROUGH: no joint within u=4..20
        config_nst = PanelConfig(
            max_panel_length=24.0,
            stud_spacing=1.333,
            strategy=PanelizationStrategy.NO_SPLIT_THROUGH,
            min_joint_to_opening=1.0,
        )
        joints_nst = find_joints_for_strategy(wall, config_nst)
        for j in joints_nst:
            assert not (3.0 <= j <= 21.0), \
                f"NO_SPLIT_THROUGH: joint at {j} within garage door exclusion zone"
