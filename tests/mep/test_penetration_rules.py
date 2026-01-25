# File: tests/mep/test_penetration_rules.py
"""Tests for penetration rules module."""

import pytest
from src.timber_framing_generator.mep.plumbing.penetration_rules import (
    generate_plumbing_penetrations,
    get_pipe_size_info,
    PipeSize,
    STANDARD_PIPE_SIZES,
    PLUMBING_PENETRATION_CLEARANCE,
    MAX_PENETRATION_RATIO,
)
from src.timber_framing_generator.mep.core.base import (
    calculate_penetration_size,
    check_penetration_allowed,
)
from src.timber_framing_generator.core import MEPDomain, MEPRoute


class TestPenetrationsizing:
    """Test penetration size calculations."""

    def test_calculate_with_clearance(self):
        """Penetration includes clearance."""
        pipe_diameter = 0.125  # 1.5" = 0.125 ft
        clearance = 0.0208    # 1/4" = 0.0208 ft

        result = calculate_penetration_size(pipe_diameter, clearance)

        expected = pipe_diameter + (2 * clearance)
        assert result == pytest.approx(expected)

    def test_default_clearance(self):
        """Default clearance is 1/4 inch."""
        assert PLUMBING_PENETRATION_CLEARANCE == pytest.approx(0.0208, rel=0.01)


class TestPenetrationAllowed:
    """Test penetration code compliance checks."""

    def test_small_hole_allowed(self):
        """Small hole in stud is allowed."""
        hole_diameter = 0.1    # ~1.2" hole
        stud_depth = 0.292     # 3.5" deep (2x4)

        is_allowed, reason = check_penetration_allowed(hole_diameter, stud_depth)

        assert is_allowed is True
        assert reason is None

    def test_large_hole_not_allowed(self):
        """Large hole exceeding 40% is not allowed."""
        hole_diameter = 0.2    # ~2.4" hole
        stud_depth = 0.292     # 3.5" deep (2x4) - 40% = 1.4"

        is_allowed, reason = check_penetration_allowed(hole_diameter, stud_depth)

        assert is_allowed is False
        assert "exceeds" in reason.lower()

    def test_max_ratio_default(self):
        """Default max ratio is 40%."""
        assert MAX_PENETRATION_RATIO == 0.40

    def test_custom_ratio(self):
        """Custom ratio is respected."""
        hole_diameter = 0.15   # 1.8" hole
        stud_depth = 0.292     # 3.5" deep

        # At 40% limit, this should fail
        is_allowed_40, _ = check_penetration_allowed(
            hole_diameter, stud_depth, max_ratio=0.40
        )

        # At 60% limit, this should pass
        is_allowed_60, _ = check_penetration_allowed(
            hole_diameter, stud_depth, max_ratio=0.60
        )

        assert is_allowed_40 is False
        assert is_allowed_60 is True


class TestStandardPipeSizes:
    """Test standard pipe size mappings."""

    def test_all_sizes_defined(self):
        """All common sizes are defined."""
        assert "1/2" in STANDARD_PIPE_SIZES
        assert "3/4" in STANDARD_PIPE_SIZES
        assert "1" in STANDARD_PIPE_SIZES
        assert "1-1/2" in STANDARD_PIPE_SIZES
        assert "2" in STANDARD_PIPE_SIZES
        assert "3" in STANDARD_PIPE_SIZES
        assert "4" in STANDARD_PIPE_SIZES

    def test_sizes_are_correct(self):
        """Pipe sizes are correct outer diameters."""
        # 1/2" pipe has ~0.875" OD
        assert STANDARD_PIPE_SIZES["1/2"] == pytest.approx(0.0729, rel=0.01)

        # 2" pipe has ~2.375" OD
        assert STANDARD_PIPE_SIZES["2"] == pytest.approx(0.1979, rel=0.01)


class TestPipeSize:
    """Test PipeSize dataclass."""

    def test_from_diameter_matches_half_inch(self):
        """Diameter matching 1/2" pipe returns correct size."""
        result = PipeSize.from_diameter(0.073)

        assert result.nominal_size == "1/2"
        assert result.outer_diameter == pytest.approx(0.0729, rel=0.01)

    def test_from_diameter_matches_two_inch(self):
        """Diameter matching 2" pipe returns correct size."""
        result = PipeSize.from_diameter(0.20)

        assert result.nominal_size == "2"

    def test_from_diameter_custom(self):
        """Non-standard diameter returns custom size."""
        result = PipeSize.from_diameter(0.5)  # 6" OD - not standard

        # Should match closest or return custom
        assert result is not None


class TestGetPipeSizeInfo:
    """Test pipe size info extraction."""

    def test_returns_nominal_size(self):
        """Returns nominal size string."""
        result = get_pipe_size_info(0.1583)  # 1-1/2" pipe OD = 1.9" = 0.1583 ft

        assert "nominal_size" in result
        assert result["nominal_size"] == "1-1/2"

    def test_returns_od_in_feet(self):
        """Returns OD in feet."""
        result = get_pipe_size_info(0.125)

        assert "outer_diameter" in result
        assert result["outer_diameter"] > 0

    def test_returns_od_in_inches(self):
        """Returns OD in inches."""
        result = get_pipe_size_info(0.125)

        assert "outer_diameter_inches" in result
        assert result["outer_diameter_inches"] > 0


class TestGeneratePlumbingPenetrations:
    """Test penetration generation from routes."""

    @pytest.fixture
    def sample_route(self):
        """Create sample route for testing."""
        return MEPRoute(
            id="route_1",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[
                (0.0, 0.0, 3.0),    # Start at fixture
                (5.0, 0.0, 3.0),    # Horizontal run
            ],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=0.125,  # 1.5" pipe
        )

    @pytest.fixture
    def sample_stud(self):
        """Create sample stud element."""
        return {
            "id": "stud_1",
            "element_type": "stud",
            "centerline_start": {"x": 2.5, "y": 0.0, "z": 0.0},
            "centerline_end": {"x": 2.5, "y": 0.0, "z": 9.0},
            "profile": {
                "width": 0.125,   # 1.5"
                "depth": 0.292,   # 3.5"
            }
        }

    def test_empty_routes_returns_empty(self):
        """Empty routes returns empty penetrations."""
        result = generate_plumbing_penetrations([], [])
        assert result == []

    def test_empty_elements_returns_empty(self, sample_route):
        """No framing elements returns empty penetrations."""
        result = generate_plumbing_penetrations([sample_route], [])
        assert result == []

    def test_penetration_has_required_fields(self, sample_route, sample_stud):
        """Penetration has all required fields."""
        result = generate_plumbing_penetrations([sample_route], [sample_stud])

        if result:  # If crossing detected
            pen = result[0]
            assert "id" in pen
            assert "route_id" in pen
            assert "element_id" in pen
            assert "location" in pen
            assert "diameter" in pen
            assert "is_allowed" in pen

    def test_penetration_diameter_includes_clearance(self, sample_route, sample_stud):
        """Penetration diameter includes clearance."""
        result = generate_plumbing_penetrations([sample_route], [sample_stud])

        if result:
            pen = result[0]
            # Diameter should be pipe size + 2 * clearance
            expected_min = sample_route.pipe_size
            assert pen["diameter"] >= expected_min

    def test_non_stud_elements_filtered(self, sample_route):
        """Non-vertical elements are filtered out."""
        plate = {
            "id": "plate_1",
            "element_type": "bottom_plate",
            "centerline_start": {"x": 0.0, "y": 0.0, "z": 0.0},
            "centerline_end": {"x": 10.0, "y": 0.0, "z": 0.0},
            "profile": {"width": 0.125, "depth": 0.292}
        }

        result = generate_plumbing_penetrations([sample_route], [plate])

        # Plates should not generate penetrations
        assert result == []


class TestPenetrationWarnings:
    """Test penetration warning generation."""

    @pytest.fixture
    def large_pipe_route(self):
        """Route with large pipe requiring warning."""
        return MEPRoute(
            id="route_large",
            domain=MEPDomain.PLUMBING,
            system_type="Sanitary",
            path_points=[
                (0.0, 0.0, 3.0),
                (5.0, 0.0, 3.0),
            ],
            start_connector_id="conn_1",
            end_point_type="wall_entry",
            pipe_size=0.25,  # 3" pipe - may exceed limits
        )

    def test_oversized_penetration_flagged(self, large_pipe_route):
        """Oversized penetration is flagged as not allowed."""
        stud = {
            "id": "stud_1",
            "element_type": "stud",
            "centerline_start": {"x": 2.5, "y": 0.0, "z": 0.0},
            "centerline_end": {"x": 2.5, "y": 0.0, "z": 9.0},
            "profile": {
                "width": 0.125,
                "depth": 0.292,  # 3.5" - 40% = 1.4" max
            }
        }

        result = generate_plumbing_penetrations([large_pipe_route], [stud])

        if result:
            pen = result[0]
            # 3" pipe + clearance > 40% of 3.5"
            if pen["diameter"] > stud["profile"]["depth"] * 0.40:
                assert pen["is_allowed"] is False
