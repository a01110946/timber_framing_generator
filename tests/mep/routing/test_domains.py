# File: tests/mep/routing/test_domains.py
"""Tests for routing domain structures."""

import pytest
from src.timber_framing_generator.mep.routing.domains import (
    Point2D,
    RoutingDomainType,
    RoutingDomain,
    Obstacle,
    create_wall_domain,
    create_floor_domain
)


class TestPoint2D:
    """Tests for Point2D dataclass."""

    def test_create_point(self):
        """Test creating a point."""
        pt = Point2D(3.5, 7.2)
        assert pt.u == 3.5
        assert pt.v == 7.2

    def test_to_tuple(self):
        """Test conversion to tuple."""
        pt = Point2D(3.5, 7.2)
        assert pt.to_tuple() == (3.5, 7.2)

    def test_from_tuple(self):
        """Test creation from tuple."""
        pt = Point2D.from_tuple((3.5, 7.2))
        assert pt.u == 3.5
        assert pt.v == 7.2

    def test_distance_to(self):
        """Test Euclidean distance."""
        pt1 = Point2D(0, 0)
        pt2 = Point2D(3, 4)
        assert pt1.distance_to(pt2) == pytest.approx(5.0)

    def test_manhattan_distance(self):
        """Test Manhattan distance."""
        pt1 = Point2D(0, 0)
        pt2 = Point2D(3, 4)
        assert pt1.manhattan_distance_to(pt2) == pytest.approx(7.0)

    def test_addition(self):
        """Test point addition."""
        pt1 = Point2D(1, 2)
        pt2 = Point2D(3, 4)
        result = pt1 + pt2
        assert result.u == 4
        assert result.v == 6

    def test_subtraction(self):
        """Test point subtraction."""
        pt1 = Point2D(5, 7)
        pt2 = Point2D(2, 3)
        result = pt1 - pt2
        assert result.u == 3
        assert result.v == 4

    def test_scale(self):
        """Test point scaling."""
        pt = Point2D(3, 4)
        result = pt.scale(2)
        assert result.u == 6
        assert result.v == 8

    def test_immutable(self):
        """Test that Point2D is immutable (frozen)."""
        pt = Point2D(3, 4)
        with pytest.raises(AttributeError):
            pt.u = 5


class TestObstacle:
    """Tests for Obstacle dataclass."""

    def test_create_obstacle(self):
        """Test creating an obstacle."""
        obs = Obstacle(
            id="stud_1",
            obstacle_type="stud",
            bounds=(1.0, 0.125, 1.125, 7.875),
            is_penetrable=True,
            max_penetration_ratio=0.4
        )

        assert obs.id == "stud_1"
        assert obs.obstacle_type == "stud"
        assert obs.min_u == 1.0
        assert obs.max_u == 1.125
        assert obs.is_penetrable is True

    def test_width_and_height(self):
        """Test width and height properties."""
        obs = Obstacle(
            id="obs_1",
            obstacle_type="test",
            bounds=(2, 3, 5, 8)  # 3 wide, 5 tall
        )
        assert obs.width == 3
        assert obs.height == 5

    def test_contains_point(self):
        """Test point containment check."""
        obs = Obstacle(
            id="obs_1",
            obstacle_type="test",
            bounds=(2, 2, 4, 4)
        )

        # Inside
        assert obs.contains_point(Point2D(3, 3)) is True

        # On edge
        assert obs.contains_point(Point2D(2, 3)) is True

        # Outside
        assert obs.contains_point(Point2D(1, 3)) is False
        assert obs.contains_point(Point2D(5, 3)) is False

    def test_intersects_segment(self):
        """Test segment intersection."""
        obs = Obstacle(
            id="obs_1",
            obstacle_type="test",
            bounds=(2, 2, 4, 4)
        )

        # Segment passes through
        assert obs.intersects_segment(Point2D(0, 3), Point2D(6, 3)) is True

        # Segment misses
        assert obs.intersects_segment(Point2D(0, 0), Point2D(6, 0)) is False

        # Segment ends inside
        assert obs.intersects_segment(Point2D(0, 3), Point2D(3, 3)) is True

    def test_serialization(self):
        """Test to_dict and from_dict."""
        obs = Obstacle(
            id="stud_1",
            obstacle_type="stud",
            bounds=(1.0, 0.125, 1.125, 7.875),
            is_penetrable=True,
            max_penetration_ratio=0.4
        )

        data = obs.to_dict()
        restored = Obstacle.from_dict(data)

        assert restored.id == obs.id
        assert restored.obstacle_type == obs.obstacle_type
        assert restored.bounds == obs.bounds
        assert restored.is_penetrable == obs.is_penetrable


class TestRoutingDomain:
    """Tests for RoutingDomain class."""

    def test_create_domain(self):
        """Test creating a routing domain."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8),  # 10 ft wide, 8 ft tall
            thickness=0.292  # 3.5" stud
        )

        assert domain.id == "wall_A"
        assert domain.domain_type == RoutingDomainType.WALL_CAVITY
        assert domain.width == 10
        assert domain.height == 8
        assert domain.thickness == 0.292

    def test_contains_point(self):
        """Test point containment in domain."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        )

        assert domain.contains_point(Point2D(5, 4)) is True
        assert domain.contains_point(Point2D(0, 0)) is True  # On edge
        assert domain.contains_point(Point2D(11, 4)) is False
        assert domain.contains_point(Point2D(-1, 4)) is False

    def test_can_fit_pipe(self):
        """Test pipe fitting validation."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8),
            thickness=0.292  # 3.5" = 0.292 ft
        )

        # 2" pipe (0.167 ft) with 1/4" clearance each side (0.0208 ft)
        # Required: 0.167 + 2*0.0208 = 0.208 ft - fits
        assert domain.can_fit_pipe(0.167) is True

        # 4" pipe (0.333 ft) - doesn't fit
        assert domain.can_fit_pipe(0.333) is False

    def test_add_remove_obstacle(self):
        """Test adding and removing obstacles."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        )

        obs = Obstacle(
            id="stud_1",
            obstacle_type="stud",
            bounds=(1, 0.125, 1.125, 7.875)
        )

        domain.add_obstacle(obs)
        assert len(domain.obstacles) == 1

        removed = domain.remove_obstacle("stud_1")
        assert removed is True
        assert len(domain.obstacles) == 0

        removed_again = domain.remove_obstacle("stud_1")
        assert removed_again is False

    def test_get_obstacles_at_point(self):
        """Test getting obstacles at a point."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        )

        domain.add_obstacle(Obstacle(
            id="stud_1", obstacle_type="stud",
            bounds=(1, 0, 1.125, 8)
        ))
        domain.add_obstacle(Obstacle(
            id="stud_2", obstacle_type="stud",
            bounds=(2.333, 0, 2.458, 8)
        ))

        # Point on stud_1
        obstacles = domain.get_obstacles_at(Point2D(1.05, 4))
        assert len(obstacles) == 1
        assert obstacles[0].id == "stud_1"

        # Point not on any stud
        obstacles = domain.get_obstacles_at(Point2D(1.5, 4))
        assert len(obstacles) == 0

    def test_is_path_clear(self):
        """Test path clearance check."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        )

        # Non-penetrable obstacle
        domain.add_obstacle(Obstacle(
            id="plate", obstacle_type="plate",
            bounds=(0, 0, 10, 0.125),
            is_penetrable=False
        ))

        # Penetrable obstacle
        domain.add_obstacle(Obstacle(
            id="stud", obstacle_type="stud",
            bounds=(2, 0.125, 2.125, 7.875),
            is_penetrable=True
        ))

        # Path through plate (blocked)
        assert domain.is_path_clear(
            Point2D(5, -0.5), Point2D(5, 0.5),
            allow_penetrable=True
        ) is False

        # Path through stud with penetration allowed
        assert domain.is_path_clear(
            Point2D(1, 4), Point2D(3, 4),
            allow_penetrable=True
        ) is True

        # Path through stud without penetration allowed
        assert domain.is_path_clear(
            Point2D(1, 4), Point2D(3, 4),
            allow_penetrable=False
        ) is False

    def test_add_transition(self):
        """Test adding transitions to other domains."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8)
        )

        domain.add_transition("floor_1")
        domain.add_transition("wall_B")
        domain.add_transition("floor_1")  # Duplicate - should not add

        assert len(domain.transitions) == 2
        assert "floor_1" in domain.transitions
        assert "wall_B" in domain.transitions

    def test_serialization(self):
        """Test to_dict and from_dict."""
        domain = RoutingDomain(
            id="wall_A",
            domain_type=RoutingDomainType.WALL_CAVITY,
            bounds=(0, 10, 0, 8),
            thickness=0.292
        )
        domain.add_obstacle(Obstacle(
            id="stud_1", obstacle_type="stud",
            bounds=(1, 0.125, 1.125, 7.875)
        ))
        domain.add_transition("floor_1")

        data = domain.to_dict()
        restored = RoutingDomain.from_dict(data)

        assert restored.id == domain.id
        assert restored.domain_type == domain.domain_type
        assert restored.bounds == domain.bounds
        assert len(restored.obstacles) == 1
        assert len(restored.transitions) == 1


class TestCreateWallDomain:
    """Tests for create_wall_domain helper function."""

    def test_create_basic_wall(self):
        """Test creating a basic wall domain."""
        domain = create_wall_domain(
            wall_id="wall_A",
            length=10.0,
            height=8.0
        )

        assert domain.id == "wall_A"
        assert domain.domain_type == RoutingDomainType.WALL_CAVITY
        assert domain.width == 10.0
        assert domain.height == 8.0

    def test_wall_has_studs(self):
        """Test that wall has stud obstacles."""
        domain = create_wall_domain(
            wall_id="wall_A",
            length=10.0,
            height=8.0,
            stud_spacing=1.333  # 16" OC
        )

        stud_obstacles = [o for o in domain.obstacles if o.obstacle_type == "stud"]
        assert len(stud_obstacles) >= 7  # ~10/1.333 studs

        # Studs should be penetrable
        for stud in stud_obstacles:
            assert stud.is_penetrable is True

    def test_wall_has_plates(self):
        """Test that wall has plate obstacles."""
        domain = create_wall_domain(
            wall_id="wall_A",
            length=10.0,
            height=8.0,
            has_top_plate=True,
            has_bottom_plate=True
        )

        plate_obstacles = [o for o in domain.obstacles if o.obstacle_type == "plate"]
        assert len(plate_obstacles) == 2

        # Plates should not be penetrable
        for plate in plate_obstacles:
            assert plate.is_penetrable is False


class TestCreateFloorDomain:
    """Tests for create_floor_domain helper function."""

    def test_create_basic_floor(self):
        """Test creating a basic floor domain."""
        domain = create_floor_domain(
            floor_id="floor_1",
            width=20.0,
            length=30.0
        )

        assert domain.id == "floor_1"
        assert domain.domain_type == RoutingDomainType.FLOOR_CAVITY
        assert domain.width == 20.0
        assert domain.height == 30.0

    def test_floor_has_joists(self):
        """Test that floor has joist obstacles."""
        domain = create_floor_domain(
            floor_id="floor_1",
            width=20.0,
            length=30.0,
            joist_spacing=1.333  # 16" OC
        )

        joist_obstacles = [o for o in domain.obstacles if o.obstacle_type == "joist"]
        assert len(joist_obstacles) >= 14  # ~20/1.333 joists

        # Joists should be penetrable (web openings)
        for joist in joist_obstacles:
            assert joist.is_penetrable is True
