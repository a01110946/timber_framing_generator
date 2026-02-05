# File: tests/mep/routing/test_revit_pipe_mapper.py
"""
Tests for Revit pipe/conduit mapping module.

Tests the route-to-pipe conversion, fitting detection,
and Revit configuration mapping.
"""

import pytest
import json
import math

from src.timber_framing_generator.mep.routing.revit_pipe_mapper import (
    get_revit_config,
    get_nominal_size,
    calculate_angle,
    detect_fitting_type,
    process_route,
    process_routes_to_pipes,
    detect_junctions,
    FittingType,
    PipeSpec,
    FittingSpec,
    PipeCreatorResult,
    REVIT_PIPE_TYPES,
    DEFAULT_PIPE_CONFIG,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_routes_json():
    """Sample routes JSON with multiple segments."""
    return json.dumps({
        "routes": [
            {
                "route_id": "route_001",
                "system_type": "sanitary_drain",
                "pipe_size": 0.1583,  # 1.5" pipe
                "segments": [
                    {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                    {"start": [5.0, 0.0, 4.0], "end": [5.0, 5.0, 4.0]},  # 90 degree turn
                ],
            },
        ]
    })


@pytest.fixture
def straight_route_json():
    """Route with no direction changes."""
    return json.dumps({
        "routes": [
            {
                "route_id": "straight_001",
                "system_type": "dhw",
                "pipe_size": 0.0729,  # 1/2" pipe
                "segments": [
                    {"start": [0.0, 0.0, 4.0], "end": [10.0, 0.0, 4.0]},
                ],
            },
        ]
    })


@pytest.fixture
def multiple_routes_json():
    """Multiple routes for junction detection."""
    return json.dumps({
        "routes": [
            {
                "route_id": "route_a",
                "system_type": "dcw",
                "segments": [
                    {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                ],
            },
            {
                "route_id": "route_b",
                "system_type": "dcw",
                "segments": [
                    {"start": [5.0, 0.0, 4.0], "end": [5.0, 5.0, 4.0]},  # Meets route_a at end
                ],
            },
        ]
    })


# ============================================================================
# Revit Configuration Tests
# ============================================================================

class TestGetRevitConfig:
    """Tests for Revit configuration mapping."""

    def test_sanitary_drain_config(self):
        """Sanitary drain maps to correct Revit config."""
        config = get_revit_config("sanitary_drain")

        assert config["category"] == "Pipe"
        assert config["system_type"] == "Sanitary"
        assert "Cast Iron" in config["pipe_type"]

    def test_dhw_config(self):
        """DHW maps to domestic hot water config."""
        config = get_revit_config("dhw")

        assert config["category"] == "Pipe"
        assert config["system_type"] == "Domestic Hot Water"

    def test_power_config(self):
        """Power maps to conduit config."""
        config = get_revit_config("power")

        assert config["category"] == "Conduit"
        assert config["system_type"] == "Power"

    def test_unknown_uses_default(self):
        """Unknown system type uses default config."""
        config = get_revit_config("unknown_type")

        assert config == DEFAULT_PIPE_CONFIG

    def test_override_applied(self):
        """Custom overrides are applied."""
        overrides = {
            "sanitary_drain": {
                "pipe_type": "Custom PVC",
            }
        }
        config = get_revit_config("sanitary_drain", overrides)

        assert config["pipe_type"] == "Custom PVC"

    def test_case_insensitive(self):
        """System type lookup is case insensitive."""
        config1 = get_revit_config("DHW")
        config2 = get_revit_config("dhw")
        config3 = get_revit_config("Dhw")

        assert config1 == config2 == config3


class TestGetNominalSize:
    """Tests for nominal pipe size mapping."""

    def test_half_inch(self):
        """1/2" pipe identified correctly."""
        size = get_nominal_size(0.0729)
        assert '1/2"' in size

    def test_one_inch(self):
        """1" pipe identified correctly."""
        size = get_nominal_size(0.1104)
        assert '1"' in size

    def test_one_and_half_inch(self):
        """1-1/2" pipe identified correctly."""
        size = get_nominal_size(0.1583)
        assert '1-1/2"' in size

    def test_two_inch(self):
        """2" pipe identified correctly."""
        size = get_nominal_size(0.1979)
        assert '2"' in size

    def test_custom_size(self):
        """Non-standard size marked as custom."""
        size = get_nominal_size(0.5)  # Very large, non-standard
        assert "custom" in size.lower()

    def test_zero_returns_unknown(self):
        """Zero diameter returns Unknown."""
        size = get_nominal_size(0)
        assert size == "Unknown"


# ============================================================================
# Angle Calculation Tests
# ============================================================================

class TestCalculateAngle:
    """Tests for angle calculation between segments."""

    def test_right_angle(self):
        """90 degree angle detected correctly."""
        p1 = (0.0, 0.0, 0.0)
        p2 = (5.0, 0.0, 0.0)
        p3 = (5.0, 5.0, 0.0)

        angle = calculate_angle(p1, p2, p3)
        assert 89.0 < angle < 91.0

    def test_straight_line(self):
        """180 degree (straight) angle detected."""
        p1 = (0.0, 0.0, 0.0)
        p2 = (5.0, 0.0, 0.0)
        p3 = (10.0, 0.0, 0.0)

        angle = calculate_angle(p1, p2, p3)
        assert angle > 175.0

    def test_45_degree_angle(self):
        """45 degree angle detected."""
        p1 = (0.0, 0.0, 0.0)
        p2 = (5.0, 0.0, 0.0)
        # 45 degrees from X axis
        p3 = (5.0 + 5.0 * math.cos(math.radians(45)),
              5.0 * math.sin(math.radians(45)),
              0.0)

        angle = calculate_angle(p1, p2, p3)
        # Should be 180 - 45 = 135 degrees (angle at vertex)
        # Actually with these points it's 45 from the incoming direction
        assert 130.0 < angle < 140.0

    def test_zero_length_segment(self):
        """Zero length segment returns 180 (straight)."""
        p1 = (0.0, 0.0, 0.0)
        p2 = (0.0, 0.0, 0.0)  # Same as p1
        p3 = (5.0, 0.0, 0.0)

        angle = calculate_angle(p1, p2, p3)
        assert angle == 180.0


class TestDetectFittingType:
    """Tests for fitting type detection from angles."""

    def test_90_degree_elbow(self):
        """90 degree angle produces elbow_90."""
        fitting = detect_fitting_type(90.0)
        assert fitting == FittingType.ELBOW_90

    def test_85_degree_is_elbow_90(self):
        """85 degrees within tolerance for 90 elbow."""
        fitting = detect_fitting_type(85.0)
        assert fitting == FittingType.ELBOW_90

    def test_45_degree_elbow(self):
        """45 degree angle produces elbow_45."""
        fitting = detect_fitting_type(45.0)
        assert fitting == FittingType.ELBOW_45

    def test_straight_no_fitting(self):
        """Straight (>175 degrees) needs no fitting."""
        fitting = detect_fitting_type(178.0)
        assert fitting is None

    def test_custom_angle(self):
        """Non-standard angle produces custom fitting."""
        fitting = detect_fitting_type(60.0)
        assert fitting == FittingType.CUSTOM

        fitting = detect_fitting_type(120.0)
        assert fitting == FittingType.CUSTOM


# ============================================================================
# Route Processing Tests
# ============================================================================

class TestProcessRoute:
    """Tests for single route processing."""

    def test_basic_route_processing(self):
        """Basic route produces pipes."""
        route = {
            "route_id": "test_001",
            "system_type": "dhw",
            "pipe_size": 0.0729,
            "segments": [
                {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
            ],
        }

        pipes, fittings, warnings = process_route(route, 0)

        assert len(pipes) == 1
        assert pipes[0].route_id == "test_001"
        assert pipes[0].system_type == "dhw"

    def test_multi_segment_route(self):
        """Multi-segment route produces multiple pipes."""
        route = {
            "route_id": "multi_001",
            "system_type": "sanitary_drain",
            "segments": [
                {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                {"start": [5.0, 0.0, 4.0], "end": [5.0, 5.0, 4.0]},
            ],
        }

        pipes, fittings, warnings = process_route(route, 0, create_fittings=True)

        assert len(pipes) == 2
        # 90 degree turn should create a fitting
        assert len(fittings) == 1
        assert fittings[0].fitting_type == FittingType.ELBOW_90

    def test_empty_segments_warning(self):
        """Empty segments produces warning."""
        route = {
            "route_id": "empty_001",
            "system_type": "dhw",
            "segments": [],
        }

        pipes, fittings, warnings = process_route(route, 0)

        assert len(pipes) == 0
        assert len(warnings) == 1
        assert "no segments" in warnings[0].lower()

    def test_fitting_disabled(self):
        """Fittings can be disabled."""
        route = {
            "route_id": "no_fit_001",
            "system_type": "dcw",
            "segments": [
                {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                {"start": [5.0, 0.0, 4.0], "end": [5.0, 5.0, 4.0]},
            ],
        }

        pipes, fittings, warnings = process_route(route, 0, create_fittings=False)

        assert len(pipes) == 2
        assert len(fittings) == 0  # No fittings when disabled


class TestProcessRoutesToPipes:
    """Tests for full route-to-pipes processing."""

    def test_process_valid_routes(self, sample_routes_json):
        """Valid routes JSON processes correctly."""
        result = process_routes_to_pipes(sample_routes_json)

        assert isinstance(result, PipeCreatorResult)
        assert len(result.pipes) >= 1
        assert "total_pipes" in result.to_dict()["summary"]

    def test_process_straight_route(self, straight_route_json):
        """Straight route has no fittings."""
        result = process_routes_to_pipes(straight_route_json)

        assert len(result.pipes) == 1
        assert len(result.fittings) == 0

    def test_invalid_json_warning(self):
        """Invalid JSON adds warning."""
        result = process_routes_to_pipes("not valid json")

        assert len(result.warnings) > 0
        assert "Invalid" in result.warnings[0]

    def test_empty_routes_warning(self):
        """Empty routes array adds warning."""
        result = process_routes_to_pipes('{"routes": []}')

        assert len(result.warnings) > 0
        assert "No routes" in result.warnings[0]

    def test_json_serialization(self, sample_routes_json):
        """Result can be serialized to JSON."""
        result = process_routes_to_pipes(sample_routes_json)
        json_str = result.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "pipes" in parsed
        assert "fittings" in parsed
        assert "summary" in parsed


# ============================================================================
# Junction Detection Tests
# ============================================================================

class TestDetectJunctions:
    """Tests for junction point detection."""

    def test_detect_meeting_routes(self, multiple_routes_json):
        """Routes meeting at same point detected as junction."""
        junctions = detect_junctions(multiple_routes_json)

        # Route A ends at (5,0,4), Route B starts at (5,0,4)
        assert len(junctions) == 1
        assert len(junctions[0]["connected_routes"]) == 2

    def test_no_junctions_isolated_routes(self):
        """Isolated routes have no junctions."""
        routes_json = json.dumps({
            "routes": [
                {
                    "route_id": "a",
                    "segments": [{"start": [0, 0, 0], "end": [5, 0, 0]}],
                },
                {
                    "route_id": "b",
                    "segments": [{"start": [100, 100, 100], "end": [105, 100, 100]}],
                },
            ]
        })

        junctions = detect_junctions(routes_json)
        assert len(junctions) == 0

    def test_junction_fitting_type(self, multiple_routes_json):
        """Junction has correct fitting type."""
        junctions = detect_junctions(multiple_routes_json)

        assert junctions[0]["fitting_type"] == "tee"

    def test_invalid_json_returns_empty(self):
        """Invalid JSON returns empty list."""
        junctions = detect_junctions("invalid json")
        assert junctions == []


# ============================================================================
# Data Class Tests
# ============================================================================

class TestPipeSpec:
    """Tests for PipeSpec data class."""

    def test_length_calculation(self):
        """Pipe length calculated from endpoints."""
        pipe = PipeSpec(
            id="test",
            route_id="route",
            system_type="dhw",
            start_point=(0.0, 0.0, 0.0),
            end_point=(3.0, 4.0, 0.0),  # 3-4-5 triangle
            diameter=0.0729,
            revit_config={},
        )

        assert pipe.length == 5.0

    def test_nominal_size_auto_set(self):
        """Nominal size automatically set from diameter."""
        pipe = PipeSpec(
            id="test",
            route_id="route",
            system_type="dhw",
            start_point=(0.0, 0.0, 0.0),
            end_point=(5.0, 0.0, 0.0),
            diameter=0.1583,  # 1-1/2"
            revit_config={},
        )

        assert '1-1/2"' in pipe.nominal_size

    def test_to_dict(self):
        """Pipe converts to dictionary."""
        pipe = PipeSpec(
            id="test",
            route_id="route",
            system_type="dhw",
            start_point=(0.0, 0.0, 0.0),
            end_point=(5.0, 0.0, 0.0),
            diameter=0.0729,
            revit_config={"category": "Pipe"},
        )

        d = pipe.to_dict()
        assert d["id"] == "test"
        assert d["start_point"] == [0.0, 0.0, 0.0]
        assert d["revit_config"]["category"] == "Pipe"


class TestFittingSpec:
    """Tests for FittingSpec data class."""

    def test_to_dict(self):
        """Fitting converts to dictionary."""
        fitting = FittingSpec(
            id="fit_001",
            fitting_type=FittingType.ELBOW_90,
            location=(5.0, 0.0, 4.0),
            connected_pipes=["pipe_001", "pipe_002"],
            angle=90.0,
            system_type="dhw",
            fitting_family="Generic - Copper",
        )

        d = fitting.to_dict()
        assert d["id"] == "fit_001"
        assert d["type"] == "elbow_90"
        assert d["angle"] == 90.0
        assert len(d["connected_pipes"]) == 2


class TestPipeCreatorResult:
    """Tests for PipeCreatorResult container."""

    def test_empty_result(self):
        """Empty result has correct structure."""
        result = PipeCreatorResult()

        d = result.to_dict()
        assert d["summary"]["total_pipes"] == 0
        assert d["summary"]["total_fittings"] == 0

    def test_to_json(self):
        """Result serializes to valid JSON."""
        result = PipeCreatorResult()
        result.pipes.append(PipeSpec(
            id="p1",
            route_id="r1",
            system_type="dhw",
            start_point=(0, 0, 0),
            end_point=(5, 0, 0),
            diameter=0.0729,
            revit_config={},
        ))

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert len(parsed["pipes"]) == 1
        assert parsed["summary"]["total_pipes"] == 1
