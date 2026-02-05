# File: tests/mep/routing/test_targets.py
"""Tests for routing target structures."""

import pytest
from src.timber_framing_generator.mep.routing.targets import (
    TargetType,
    RoutingTarget,
    TargetCandidate,
    SYSTEM_TARGET_COMPATIBILITY,
    get_compatible_target_types,
    filter_targets_for_system,
    rank_targets_by_distance
)


class TestTargetType:
    """Tests for TargetType enum."""

    def test_target_types_exist(self):
        """Test that all expected target types exist."""
        assert TargetType.WET_WALL.value == "wet_wall"
        assert TargetType.FLOOR_PENETRATION.value == "floor_penetration"
        assert TargetType.CEILING_PENETRATION.value == "ceiling_penetration"
        assert TargetType.SHAFT.value == "shaft"
        assert TargetType.PANEL_BOUNDARY.value == "panel_boundary"
        assert TargetType.EQUIPMENT.value == "equipment"
        assert TargetType.MAIN_LINE.value == "main_line"


class TestSystemTargetCompatibility:
    """Tests for system-target compatibility mapping."""

    def test_plumbing_systems(self):
        """Test plumbing system compatibility."""
        # Sanitary can go to wet wall, floor penetration, shaft
        sanitary_targets = SYSTEM_TARGET_COMPATIBILITY.get("Sanitary", [])
        assert TargetType.WET_WALL in sanitary_targets
        assert TargetType.FLOOR_PENETRATION in sanitary_targets
        assert TargetType.SHAFT in sanitary_targets

        # Vent should route to wet wall or ceiling
        vent_targets = SYSTEM_TARGET_COMPATIBILITY.get("Vent", [])
        assert TargetType.WET_WALL in vent_targets
        assert TargetType.CEILING_PENETRATION in vent_targets

    def test_electrical_systems(self):
        """Test electrical system compatibility."""
        power_targets = SYSTEM_TARGET_COMPATIBILITY.get("Power", [])
        assert TargetType.PANEL_BOUNDARY in power_targets
        assert TargetType.EQUIPMENT in power_targets

    def test_get_compatible_target_types(self):
        """Test getting compatible types for a system."""
        targets = get_compatible_target_types("Sanitary")
        assert TargetType.WET_WALL in targets
        assert TargetType.FLOOR_PENETRATION in targets

        # Unknown system returns empty list
        unknown = get_compatible_target_types("UnknownSystem")
        assert unknown == []


class TestRoutingTarget:
    """Tests for RoutingTarget dataclass."""

    def test_create_target(self):
        """Test creating a routing target."""
        target = RoutingTarget(
            id="wet_wall_1",
            target_type=TargetType.WET_WALL,
            location=(5.0, 3.0, 0.0),
            domain_id="wall_A",
            plane_location=(5.0, 3.0),
            systems_served=["Sanitary", "DHW", "DCW", "Vent"],
            capacity=0.333
        )

        assert target.id == "wet_wall_1"
        assert target.target_type == TargetType.WET_WALL
        assert target.location == (5.0, 3.0, 0.0)
        assert target.capacity == 0.333

    def test_can_serve_system_explicit(self):
        """Test system compatibility with explicit systems_served list."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(0, 0, 0),
            domain_id="wall_A",
            plane_location=(0, 0),
            systems_served=["Sanitary", "DHW"]
        )

        assert target.can_serve_system("Sanitary") is True
        assert target.can_serve_system("DHW") is True
        assert target.can_serve_system("Power") is False

    def test_can_serve_system_from_mapping(self):
        """Test system compatibility using default mapping."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(0, 0, 0),
            domain_id="wall_A",
            plane_location=(0, 0),
            systems_served=[]  # Empty - use mapping
        )

        # WET_WALL should serve plumbing systems based on mapping
        assert target.can_serve_system("Sanitary") is True
        assert target.can_serve_system("Vent") is True
        # But not electrical (Power goes to PANEL_BOUNDARY, not WET_WALL)
        assert target.can_serve_system("Power") is False

    def test_can_fit_pipe(self):
        """Test pipe fitting validation."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(0, 0, 0),
            domain_id="wall_A",
            plane_location=(0, 0),
            capacity=0.333  # 4" pipe
        )

        assert target.can_fit_pipe(0.25) is True  # 3" pipe
        assert target.can_fit_pipe(0.333) is True  # 4" pipe exactly
        assert target.can_fit_pipe(0.5) is False  # 6" pipe

    def test_distance_to(self):
        """Test 3D distance calculation."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(0, 0, 0),
            domain_id="wall_A",
            plane_location=(0, 0)
        )

        # 3-4-0 = 5 in 2D, plus Z
        dist = target.distance_to((3, 4, 0))
        assert dist == pytest.approx(5.0)

    def test_plane_distance_to(self):
        """Test 2D plane distance calculation."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(0, 0, 0),
            domain_id="wall_A",
            plane_location=(0, 0)
        )

        dist = target.plane_distance_to((3, 4))
        assert dist == pytest.approx(5.0)

    def test_manhattan_distance_to(self):
        """Test Manhattan distance calculation."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(0, 0, 0),
            domain_id="wall_A",
            plane_location=(0, 0)
        )

        dist = target.manhattan_distance_to((3, 4))
        assert dist == pytest.approx(7.0)

    def test_serialization(self):
        """Test to_dict and from_dict."""
        target = RoutingTarget(
            id="wet_wall_1",
            target_type=TargetType.WET_WALL,
            location=(5.0, 3.0, 0.0),
            domain_id="wall_A",
            plane_location=(5.0, 3.0),
            systems_served=["Sanitary", "DHW"],
            capacity=0.333,
            priority=1,
            is_available=True,
            metadata={"wall_type": "wet"}
        )

        data = target.to_dict()
        restored = RoutingTarget.from_dict(data)

        assert restored.id == target.id
        assert restored.target_type == target.target_type
        assert restored.location == target.location
        assert restored.systems_served == target.systems_served
        assert restored.metadata == target.metadata


class TestTargetCandidate:
    """Tests for TargetCandidate dataclass."""

    def test_create_candidate(self):
        """Test creating a target candidate."""
        target = RoutingTarget(
            id="t1",
            target_type=TargetType.WET_WALL,
            location=(5, 3, 0),
            domain_id="wall_A",
            plane_location=(5, 3)
        )

        candidate = TargetCandidate(
            target=target,
            score=5.5,
            distance=5.0,
            routing_domain="wall_A",
            requires_floor_routing=False,
            notes="Closest wet wall"
        )

        assert candidate.target == target
        assert candidate.score == 5.5
        assert candidate.distance == 5.0
        assert candidate.requires_floor_routing is False

    def test_sorting(self):
        """Test that candidates sort by score."""
        target = RoutingTarget(
            id="t1", target_type=TargetType.WET_WALL,
            location=(0, 0, 0), domain_id="d1", plane_location=(0, 0)
        )

        c1 = TargetCandidate(target=target, score=10.0, distance=10.0, routing_domain="d1")
        c2 = TargetCandidate(target=target, score=5.0, distance=5.0, routing_domain="d1")
        c3 = TargetCandidate(target=target, score=7.0, distance=7.0, routing_domain="d1")

        candidates = [c1, c2, c3]
        candidates.sort()

        assert candidates[0].score == 5.0
        assert candidates[1].score == 7.0
        assert candidates[2].score == 10.0


class TestFilterTargetsForSystem:
    """Tests for filter_targets_for_system function."""

    def test_filter_by_system(self):
        """Test filtering targets by system type."""
        targets = [
            RoutingTarget(
                id="t1", target_type=TargetType.WET_WALL,
                location=(0, 0, 0), domain_id="d1", plane_location=(0, 0),
                systems_served=["Sanitary", "DHW"]
            ),
            RoutingTarget(
                id="t2", target_type=TargetType.PANEL_BOUNDARY,
                location=(5, 0, 0), domain_id="d1", plane_location=(5, 0),
                systems_served=["Power", "Data"]
            ),
            RoutingTarget(
                id="t3", target_type=TargetType.WET_WALL,
                location=(10, 0, 0), domain_id="d1", plane_location=(10, 0),
                systems_served=["Sanitary"],
                is_available=False  # Not available
            ),
        ]

        # Filter for Sanitary - should get t1 only (t3 is not available)
        result = filter_targets_for_system(targets, "Sanitary")
        assert len(result) == 1
        assert result[0].id == "t1"

        # Filter for Power
        result = filter_targets_for_system(targets, "Power")
        assert len(result) == 1
        assert result[0].id == "t2"

    def test_filter_by_capacity(self):
        """Test filtering by minimum capacity."""
        targets = [
            RoutingTarget(
                id="t1", target_type=TargetType.WET_WALL,
                location=(0, 0, 0), domain_id="d1", plane_location=(0, 0),
                systems_served=["Sanitary"],
                capacity=0.167  # 2" pipe max
            ),
            RoutingTarget(
                id="t2", target_type=TargetType.WET_WALL,
                location=(5, 0, 0), domain_id="d1", plane_location=(5, 0),
                systems_served=["Sanitary"],
                capacity=0.333  # 4" pipe max
            ),
        ]

        # Filter for 3" pipe - only t2 fits
        result = filter_targets_for_system(targets, "Sanitary", min_capacity=0.25)
        assert len(result) == 1
        assert result[0].id == "t2"


class TestRankTargetsByDistance:
    """Tests for rank_targets_by_distance function."""

    def test_rank_by_euclidean(self):
        """Test ranking by Euclidean distance."""
        targets = [
            RoutingTarget(
                id="far", target_type=TargetType.WET_WALL,
                location=(10, 10, 0), domain_id="d1", plane_location=(10, 10)
            ),
            RoutingTarget(
                id="near", target_type=TargetType.WET_WALL,
                location=(1, 1, 0), domain_id="d1", plane_location=(1, 1)
            ),
            RoutingTarget(
                id="mid", target_type=TargetType.WET_WALL,
                location=(5, 5, 0), domain_id="d1", plane_location=(5, 5)
            ),
        ]

        candidates = rank_targets_by_distance(targets, (0, 0, 0), use_manhattan=False)

        assert candidates[0].target.id == "near"
        assert candidates[1].target.id == "mid"
        assert candidates[2].target.id == "far"

    def test_rank_by_manhattan(self):
        """Test ranking by Manhattan distance."""
        targets = [
            RoutingTarget(
                id="t1", target_type=TargetType.WET_WALL,
                location=(3, 4, 0), domain_id="d1", plane_location=(3, 4)
                # Manhattan: 3+4 = 7
            ),
            RoutingTarget(
                id="t2", target_type=TargetType.WET_WALL,
                location=(5, 0, 0), domain_id="d1", plane_location=(5, 0)
                # Manhattan: 5+0 = 5
            ),
        ]

        candidates = rank_targets_by_distance(targets, (0, 0, 0), use_manhattan=True)

        # t2 is closer by Manhattan distance
        assert candidates[0].target.id == "t2"
        assert candidates[1].target.id == "t1"

    def test_priority_affects_score(self):
        """Test that priority affects ranking score."""
        targets = [
            RoutingTarget(
                id="high_priority", target_type=TargetType.WET_WALL,
                location=(5, 0, 0), domain_id="d1", plane_location=(5, 0),
                priority=0  # High priority
            ),
            RoutingTarget(
                id="low_priority", target_type=TargetType.WET_WALL,
                location=(4, 0, 0), domain_id="d1", plane_location=(4, 0),
                priority=20  # Low priority
            ),
        ]

        candidates = rank_targets_by_distance(targets, (0, 0, 0))

        # Even though low_priority is closer, high_priority might rank better
        # due to priority factor (depends on weighting)
        # With priority weight of 0.1, scores are:
        # high_priority: 5 + 0*0.1 = 5.0
        # low_priority: 4 + 20*0.1 = 6.0
        assert candidates[0].target.id == "high_priority"
