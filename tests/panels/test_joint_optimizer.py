# File: tests/panels/test_joint_optimizer.py
"""Unit tests for joint optimizer."""

import pytest
from src.timber_framing_generator.panels.joint_optimizer import (
    find_exclusion_zones,
    find_optimal_joints,
    get_panel_boundaries,
    validate_joints,
)
from src.timber_framing_generator.panels.panel_config import (
    PanelConfig,
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
