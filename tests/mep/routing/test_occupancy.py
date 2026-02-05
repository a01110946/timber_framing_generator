# File: tests/mep/routing/test_occupancy.py
"""Tests for OccupancyMap and OccupiedSegment."""

import pytest
from src.timber_framing_generator.mep.routing.occupancy import (
    OccupancyMap,
    OccupiedSegment
)


class TestOccupiedSegment:
    """Tests for OccupiedSegment dataclass."""

    def test_create_segment(self):
        """Test creating an occupied segment."""
        segment = OccupiedSegment(
            route_id="route_1",
            system_type="Sanitary",
            trade="plumbing",
            start=(0, 0),
            end=(5, 0),
            diameter=0.125
        )

        assert segment.route_id == "route_1"
        assert segment.system_type == "Sanitary"
        assert segment.trade == "plumbing"
        assert segment.start == (0, 0)
        assert segment.end == (5, 0)
        assert segment.diameter == 0.125
        assert segment.priority == 0  # Default

    def test_get_length(self):
        """Test segment length calculation."""
        # Horizontal segment
        seg_h = OccupiedSegment(
            route_id="r1", system_type="DHW", trade="plumbing",
            start=(0, 0), end=(3, 0), diameter=0.1
        )
        assert seg_h.get_length() == pytest.approx(3.0)

        # Vertical segment
        seg_v = OccupiedSegment(
            route_id="r2", system_type="DHW", trade="plumbing",
            start=(0, 0), end=(0, 4), diameter=0.1
        )
        assert seg_v.get_length() == pytest.approx(4.0)

        # Diagonal segment (3-4-5 triangle)
        seg_d = OccupiedSegment(
            route_id="r3", system_type="DHW", trade="plumbing",
            start=(0, 0), end=(3, 4), diameter=0.1
        )
        assert seg_d.get_length() == pytest.approx(5.0)

    def test_get_midpoint(self):
        """Test segment midpoint calculation."""
        segment = OccupiedSegment(
            route_id="r1", system_type="DHW", trade="plumbing",
            start=(2, 4), end=(6, 8), diameter=0.1
        )
        midpoint = segment.get_midpoint()
        assert midpoint == (4, 6)

    def test_serialization(self):
        """Test to_dict and from_dict."""
        segment = OccupiedSegment(
            route_id="route_1",
            system_type="Sanitary",
            trade="plumbing",
            start=(1.5, 2.5),
            end=(5.5, 2.5),
            diameter=0.125,
            priority=2
        )

        data = segment.to_dict()
        restored = OccupiedSegment.from_dict(data)

        assert restored.route_id == segment.route_id
        assert restored.system_type == segment.system_type
        assert restored.start == segment.start
        assert restored.end == segment.end
        assert restored.diameter == segment.diameter
        assert restored.priority == segment.priority


class TestOccupancyMap:
    """Tests for OccupancyMap class."""

    def test_empty_map(self):
        """Test empty occupancy map."""
        occ = OccupancyMap()
        assert occ.get_total_segments() == 0
        assert occ.get_plane_ids() == []

    def test_reserve_segment(self):
        """Test reserving a segment."""
        occ = OccupancyMap()
        segment = OccupiedSegment(
            route_id="route_1",
            system_type="Sanitary",
            trade="plumbing",
            start=(0, 0),
            end=(5, 0),
            diameter=0.125
        )

        occ.reserve("wall_A", segment)

        assert occ.get_total_segments() == 1
        assert "wall_A" in occ.get_plane_ids()
        assert len(occ.get_segments("wall_A")) == 1

    def test_is_available_empty_plane(self):
        """Test availability on empty plane."""
        occ = OccupancyMap()
        available, conflict = occ.is_available(
            "wall_A",
            ((0, 0), (5, 0)),
            diameter=0.125
        )
        assert available is True
        assert conflict is None

    def test_is_available_with_conflict(self):
        """Test availability detection with conflict."""
        occ = OccupancyMap()

        # Reserve a segment
        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1",
            system_type="Sanitary",
            trade="plumbing",
            start=(0, 1),
            end=(5, 1),
            diameter=0.125
        ))

        # Try to place overlapping segment
        available, conflict = occ.is_available(
            "wall_A",
            ((2, 1), (4, 1)),  # Same line, overlapping
            diameter=0.125,
            clearance=0.0417
        )

        assert available is False
        assert conflict == "route_1"

    def test_is_available_parallel_segments(self):
        """Test availability for parallel segments with clearance."""
        occ = OccupancyMap()

        # Reserve a segment
        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1",
            system_type="Sanitary",
            trade="plumbing",
            start=(0, 1),
            end=(5, 1),
            diameter=0.125  # 1.5" pipe
        ))

        # Parallel segment too close (within clearance)
        available_close, _ = occ.is_available(
            "wall_A",
            ((0, 1.1), (5, 1.1)),  # 0.1 ft = 1.2" apart
            diameter=0.125,
            clearance=0.0417  # 0.5" clearance
        )
        # Required: 0.125/2 + 0.125/2 + 0.0417 = 0.1667 ft
        # Actual: 0.1 ft - too close
        assert available_close is False

        # Parallel segment far enough
        available_far, _ = occ.is_available(
            "wall_A",
            ((0, 1.3), (5, 1.3)),  # 0.3 ft = 3.6" apart
            diameter=0.125,
            clearance=0.0417
        )
        assert available_far is True

    def test_release_segment(self):
        """Test releasing segments."""
        occ = OccupancyMap()

        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1", system_type="S", trade="p",
            start=(0, 0), end=(1, 0), diameter=0.1
        ))
        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_2", system_type="S", trade="p",
            start=(0, 2), end=(1, 2), diameter=0.1
        ))

        assert occ.get_total_segments() == 2

        released = occ.release("wall_A", "route_1")
        assert released == 1
        assert occ.get_total_segments() == 1

    def test_release_all(self):
        """Test releasing all segments for a route across planes."""
        occ = OccupancyMap()

        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1", system_type="S", trade="p",
            start=(0, 0), end=(1, 0), diameter=0.1
        ))
        occ.reserve("wall_B", OccupiedSegment(
            route_id="route_1", system_type="S", trade="p",
            start=(0, 0), end=(1, 0), diameter=0.1
        ))
        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_2", system_type="S", trade="p",
            start=(0, 2), end=(1, 2), diameter=0.1
        ))

        assert occ.get_total_segments() == 3

        released = occ.release_all("route_1")
        assert released == 2
        assert occ.get_total_segments() == 1

    def test_get_conflicts(self):
        """Test getting list of conflicting segments."""
        occ = OccupancyMap()

        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1", system_type="S", trade="p",
            start=(0, 1), end=(5, 1), diameter=0.125
        ))
        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_2", system_type="S", trade="p",
            start=(2, 0), end=(2, 3), diameter=0.125
        ))
        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_3", system_type="S", trade="p",
            start=(0, 5), end=(5, 5), diameter=0.125  # Far away
        ))

        # Query segment that crosses both route_1 and route_2
        conflicts = occ.get_conflicts(
            "wall_A",
            ((1, 0), (3, 2)),
            diameter=0.125,
            clearance=0.0417
        )

        conflict_ids = {c.route_id for c in conflicts}
        assert "route_1" in conflict_ids or "route_2" in conflict_ids
        assert "route_3" not in conflict_ids

    def test_serialization(self):
        """Test to_dict and from_dict."""
        occ = OccupancyMap()

        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1", system_type="Sanitary", trade="plumbing",
            start=(0, 0), end=(5, 0), diameter=0.125
        ))
        occ.reserve("wall_B", OccupiedSegment(
            route_id="route_2", system_type="DHW", trade="plumbing",
            start=(0, 0), end=(3, 3), diameter=0.083
        ))

        data = occ.to_dict()
        restored = OccupancyMap.from_dict(data)

        assert restored.get_total_segments() == 2
        assert "wall_A" in restored.get_plane_ids()
        assert "wall_B" in restored.get_plane_ids()

    def test_clear(self):
        """Test clearing all occupancy data."""
        occ = OccupancyMap()

        occ.reserve("wall_A", OccupiedSegment(
            route_id="route_1", system_type="S", trade="p",
            start=(0, 0), end=(1, 0), diameter=0.1
        ))
        occ.reserve("wall_B", OccupiedSegment(
            route_id="route_2", system_type="S", trade="p",
            start=(0, 0), end=(1, 0), diameter=0.1
        ))

        occ.clear()

        assert occ.get_total_segments() == 0
        assert occ.get_plane_ids() == []


class TestOccupancyMapGeometry:
    """Tests for geometric calculations in OccupancyMap."""

    def test_point_to_segment_distance(self):
        """Test point-to-segment distance calculation."""
        occ = OccupancyMap()

        # Point directly on segment
        dist = occ._point_to_segment_distance(
            (2, 0), (0, 0), (5, 0)
        )
        assert dist == pytest.approx(0.0)

        # Point perpendicular to segment
        dist = occ._point_to_segment_distance(
            (2, 3), (0, 0), (5, 0)
        )
        assert dist == pytest.approx(3.0)

        # Point closest to segment endpoint
        dist = occ._point_to_segment_distance(
            (-3, 4), (0, 0), (5, 0)
        )
        assert dist == pytest.approx(5.0)  # 3-4-5 triangle to (0,0)

    def test_segments_intersect(self):
        """Test segment intersection detection."""
        occ = OccupancyMap()

        # Crossing segments
        assert occ._segments_intersect(
            (0, 0), (5, 5),
            (0, 5), (5, 0)
        ) is True

        # Parallel non-intersecting
        assert occ._segments_intersect(
            (0, 0), (5, 0),
            (0, 1), (5, 1)
        ) is False

        # T-junction (touching at endpoint)
        assert occ._segments_intersect(
            (0, 0), (5, 0),
            (2.5, 0), (2.5, 5)
        ) is True

    def test_segment_to_segment_distance(self):
        """Test segment-to-segment distance calculation."""
        occ = OccupancyMap()

        # Intersecting segments
        dist = occ._segment_to_segment_distance(
            (0, 0), (5, 5),
            (0, 5), (5, 0)
        )
        assert dist == pytest.approx(0.0)

        # Parallel segments 1 unit apart
        dist = occ._segment_to_segment_distance(
            (0, 0), (5, 0),
            (0, 1), (5, 1)
        )
        assert dist == pytest.approx(1.0)
