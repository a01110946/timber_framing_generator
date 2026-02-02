# File: tests/framing_elements/test_holddowns.py
"""Tests for holddown location generation."""

import pytest
from src.timber_framing_generator.framing_elements.holddowns import (
    generate_holddown_locations,
    HolddownLocation,
    HolddownPosition,
    get_holddown_summary,
)


class TestHolddownGeneration:
    """Tests for holddown location generation."""

    @pytest.fixture
    def simple_wall_data(self):
        """Create simple wall data without panels."""
        return {
            "wall_id": "test_wall_1",
            "wall_length": 12.0,  # 12 feet
            "wall_base_elevation": 0.0,
            "base_plane": None,  # No Rhino plane in tests
            "is_load_bearing": False,
        }

    @pytest.fixture
    def load_bearing_wall_data(self):
        """Create load-bearing wall data."""
        return {
            "wall_id": "test_wall_lb",
            "wall_length": 16.0,
            "wall_base_elevation": 12.0,  # Second floor
            "base_plane": None,
            "is_load_bearing": True,
        }

    @pytest.fixture
    def panelized_wall_data(self):
        """Create wall data with panels."""
        return {
            "wall_id": "test_wall_panelized",
            "wall_length": 24.0,  # 24 feet
            "wall_base_elevation": 0.0,
            "base_plane": None,
            "is_load_bearing": True,
        }

    @pytest.fixture
    def panels_data(self):
        """Create panel data for a 24' wall with 3 panels."""
        return [
            {"panel_id": "P1", "u_start": 0.0, "u_end": 8.0},
            {"panel_id": "P2", "u_start": 8.0, "u_end": 16.0},
            {"panel_id": "P3", "u_start": 16.0, "u_end": 24.0},
        ]

    def test_simple_wall_generates_two_holddowns(self, simple_wall_data):
        """Simple wall should have holddowns at both ends."""
        holddowns = generate_holddown_locations(simple_wall_data)

        assert len(holddowns) == 2
        positions = [h.position for h in holddowns]
        assert HolddownPosition.LEFT in positions
        assert HolddownPosition.RIGHT in positions

    def test_holddown_positions_at_wall_ends(self, simple_wall_data):
        """Holddowns should be offset from wall ends by half stud width."""
        config = {"stud_width": 0.125}  # 1.5 inches
        holddowns = generate_holddown_locations(simple_wall_data, config)

        left_holddown = next(h for h in holddowns if h.position == HolddownPosition.LEFT)
        right_holddown = next(h for h in holddowns if h.position == HolddownPosition.RIGHT)

        # Left holddown at stud_width/2 from left end
        assert left_holddown.u_coordinate == pytest.approx(0.0625, rel=1e-3)
        # Right holddown at stud_width/2 from right end
        assert right_holddown.u_coordinate == pytest.approx(12.0 - 0.0625, rel=1e-3)

    def test_load_bearing_flag_propagates(self, load_bearing_wall_data):
        """Load-bearing status should be set on holddowns."""
        holddowns = generate_holddown_locations(load_bearing_wall_data)

        assert all(h.is_load_bearing for h in holddowns)

    def test_elevation_from_wall_base(self, load_bearing_wall_data):
        """Holddown elevation should match wall base elevation."""
        holddowns = generate_holddown_locations(load_bearing_wall_data)

        assert all(h.elevation == 12.0 for h in holddowns)

    def test_panelized_wall_generates_holddowns_at_splices(
        self, panelized_wall_data, panels_data
    ):
        """Panelized wall should have holddowns at panel boundaries."""
        holddowns = generate_holddown_locations(
            panelized_wall_data,
            panels_data=panels_data
        )

        # 3 panels = 4 holddown locations (left, 2 splices, right)
        assert len(holddowns) == 4

        # Check positions
        positions = [h.position for h in holddowns]
        assert positions.count(HolddownPosition.LEFT) == 1
        assert positions.count(HolddownPosition.RIGHT) == 1
        assert positions.count(HolddownPosition.SPLICE) == 2

    def test_panelized_wall_without_splices(self, panelized_wall_data, panels_data):
        """When include_splices=False, only wall ends get holddowns."""
        config = {"include_splices": False}
        holddowns = generate_holddown_locations(
            panelized_wall_data,
            config=config,
            panels_data=panels_data
        )

        # Only left and right holddowns
        assert len(holddowns) == 2

    def test_holddown_ids_are_unique(self, panelized_wall_data, panels_data):
        """All holddown IDs should be unique."""
        holddowns = generate_holddown_locations(
            panelized_wall_data,
            panels_data=panels_data
        )

        ids = [h.id for h in holddowns]
        assert len(ids) == len(set(ids))

    def test_empty_wall_returns_no_holddowns(self):
        """Zero-length wall should return empty list."""
        wall_data = {
            "wall_id": "empty",
            "wall_length": 0,
            "wall_base_elevation": 0,
            "base_plane": None,
            "is_load_bearing": False,
        }
        holddowns = generate_holddown_locations(wall_data)

        assert len(holddowns) == 0

    def test_custom_offset_from_end(self, simple_wall_data):
        """Custom offset should position holddowns correctly."""
        config = {"offset_from_end": 0.5}  # 6 inches from end
        holddowns = generate_holddown_locations(simple_wall_data, config)

        left = next(h for h in holddowns if h.position == HolddownPosition.LEFT)
        right = next(h for h in holddowns if h.position == HolddownPosition.RIGHT)

        assert left.u_coordinate == 0.5
        assert right.u_coordinate == 11.5

    def test_holddown_to_dict_serialization(self, simple_wall_data):
        """HolddownLocation.to_dict() should serialize correctly."""
        holddowns = generate_holddown_locations(simple_wall_data)
        holddown_dict = holddowns[0].to_dict()

        assert "id" in holddown_dict
        assert "wall_id" in holddown_dict
        assert "position" in holddown_dict
        assert "u_coordinate" in holddown_dict
        assert holddown_dict["wall_id"] == "test_wall_1"


class TestHolddownSummary:
    """Tests for holddown summary statistics."""

    def test_summary_empty_list(self):
        """Summary of empty list should have zeros."""
        summary = get_holddown_summary([])

        assert summary["total_holddowns"] == 0
        assert summary["wall_end_holddowns"] == 0
        assert summary["splice_holddowns"] == 0

    def test_summary_counts(self):
        """Summary should correctly count holddown types."""
        # Create mock holddowns
        holddowns = [
            HolddownLocation(
                id="h1", wall_id="w1", panel_id=None,
                position=HolddownPosition.LEFT,
                point=None, u_coordinate=0, elevation=0,
                is_load_bearing=True
            ),
            HolddownLocation(
                id="h2", wall_id="w1", panel_id=None,
                position=HolddownPosition.RIGHT,
                point=None, u_coordinate=12, elevation=0,
                is_load_bearing=True
            ),
            HolddownLocation(
                id="h3", wall_id="w1", panel_id="P2",
                position=HolddownPosition.SPLICE,
                point=None, u_coordinate=8, elevation=0,
                is_load_bearing=True
            ),
        ]

        summary = get_holddown_summary(holddowns)

        assert summary["total_holddowns"] == 3
        assert summary["wall_end_holddowns"] == 2
        assert summary["splice_holddowns"] == 1
        assert summary["load_bearing_count"] == 3
