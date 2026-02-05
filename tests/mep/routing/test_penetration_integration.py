# File: tests/mep/routing/test_penetration_integration.py
"""
Tests for MEP routing penetration integration.

Tests the bridge module that connects OAHS routing output to
existing penetration generation logic.
"""

import pytest
import json

from src.timber_framing_generator.mep.routing.penetration_integration import (
    integrate_routes_to_penetrations,
    penetrations_to_json,
    extract_penetration_points,
    get_penetration_info_string,
    _parse_routes_json,
    _parse_framing_json,
    _convert_routes,
    _route_dict_to_mep_route,
    _system_type_to_domain,
)
from src.timber_framing_generator.core.mep_system import MEPDomain


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_routes_json():
    """Sample routes JSON from OAHS router."""
    return json.dumps({
        "routes": [
            {
                "route_id": "route_001",
                "system_type": "sanitary_drain",
                "pipe_size": 0.1583,  # 1.5" pipe
                "segments": [
                    {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                    {"start": [5.0, 0.0, 4.0], "end": [10.0, 0.0, 4.0]},
                ],
                "junctions": [[5.0, 0.0, 4.0]],
            },
            {
                "route_id": "route_002",
                "system_type": "dhw",
                "pipe_size": 0.0729,  # 1/2" pipe
                "segments": [
                    {"start": [0.0, 5.0, 6.0], "end": [8.0, 5.0, 6.0]},
                ],
            },
        ]
    })


@pytest.fixture
def sample_framing_json():
    """Sample framing JSON from framing generator."""
    return json.dumps({
        "elements": [
            {
                "id": "stud_001",
                "element_type": "stud",
                "centerline": {
                    "start": {"x": 3.0, "y": 0.0, "z": 0.0},
                    "end": {"x": 3.0, "y": 0.0, "z": 8.0},
                },
                "profile": {
                    "width": 0.125,  # 1.5"
                    "depth": 0.292,  # 3.5"
                },
            },
            {
                "id": "stud_002",
                "element_type": "stud",
                "centerline": {
                    "start": {"x": 6.0, "y": 0.0, "z": 0.0},
                    "end": {"x": 6.0, "y": 0.0, "z": 8.0},
                },
                "profile": {
                    "width": 0.125,
                    "depth": 0.292,
                },
            },
            {
                "id": "header_001",
                "element_type": "header",  # Not a vertical element - should be filtered
                "centerline": {
                    "start": {"x": 0.0, "y": 0.0, "z": 7.0},
                    "end": {"x": 10.0, "y": 0.0, "z": 7.0},
                },
                "profile": {
                    "width": 0.292,
                    "depth": 0.125,
                },
            },
        ]
    })


@pytest.fixture
def empty_routes_json():
    """Empty routes JSON."""
    return json.dumps({"routes": []})


@pytest.fixture
def empty_framing_json():
    """Empty framing JSON."""
    return json.dumps({"elements": []})


# ============================================================================
# JSON Parsing Tests
# ============================================================================

class TestParseRoutesJson:
    """Tests for routes JSON parsing."""

    def test_parse_valid_routes(self, sample_routes_json):
        """Parse valid routes JSON."""
        routes = _parse_routes_json(sample_routes_json)

        assert len(routes) == 2
        assert routes[0]["route_id"] == "route_001"
        assert routes[1]["route_id"] == "route_002"

    def test_parse_empty_routes(self, empty_routes_json):
        """Parse empty routes JSON returns empty list."""
        routes = _parse_routes_json(empty_routes_json)

        assert routes == []

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid routes JSON"):
            _parse_routes_json("not valid json")

    def test_parse_missing_routes_key_raises(self):
        """JSON without 'routes' key raises ValueError."""
        with pytest.raises(ValueError, match="missing 'routes' key"):
            _parse_routes_json('{"other": []}')

    def test_parse_non_object_raises(self):
        """Non-object JSON raises ValueError."""
        with pytest.raises(ValueError, match="must be an object"):
            _parse_routes_json('["array", "not", "object"]')


class TestParseFramingJson:
    """Tests for framing JSON parsing."""

    def test_parse_elements_format(self, sample_framing_json):
        """Parse framing JSON with 'elements' key."""
        elements = _parse_framing_json(sample_framing_json)

        assert len(elements) == 3

    def test_parse_list_format(self):
        """Parse framing JSON as direct list."""
        framing_json = json.dumps([
            {"id": "stud_001", "element_type": "stud"},
        ])
        elements = _parse_framing_json(framing_json)

        assert len(elements) == 1

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid framing JSON"):
            _parse_framing_json("not valid json")

    def test_parse_empty_returns_empty(self, empty_framing_json):
        """Empty elements returns empty list."""
        elements = _parse_framing_json(empty_framing_json)

        assert elements == []


# ============================================================================
# Route Conversion Tests
# ============================================================================

class TestSystemTypeToDomain:
    """Tests for system type to domain conversion."""

    def test_sanitary_to_plumbing(self):
        """Sanitary types map to plumbing domain."""
        assert _system_type_to_domain("sanitary_drain") == MEPDomain.PLUMBING
        assert _system_type_to_domain("sanitary_vent") == MEPDomain.PLUMBING

    def test_water_to_plumbing(self):
        """Water types map to plumbing domain."""
        assert _system_type_to_domain("dhw") == MEPDomain.PLUMBING
        assert _system_type_to_domain("dcw") == MEPDomain.PLUMBING

    def test_hvac_to_hvac(self):
        """HVAC types map to HVAC domain."""
        assert _system_type_to_domain("hvac_supply") == MEPDomain.HVAC
        assert _system_type_to_domain("duct_supply") == MEPDomain.HVAC

    def test_electrical_to_electrical(self):
        """Electrical types map to electrical domain."""
        assert _system_type_to_domain("power") == MEPDomain.ELECTRICAL
        assert _system_type_to_domain("lighting") == MEPDomain.ELECTRICAL
        assert _system_type_to_domain("data") == MEPDomain.ELECTRICAL

    def test_unknown_defaults_to_plumbing(self):
        """Unknown types default to plumbing."""
        assert _system_type_to_domain("unknown") == MEPDomain.PLUMBING
        assert _system_type_to_domain("") == MEPDomain.PLUMBING


class TestRouteConversion:
    """Tests for route dictionary to MEPRoute conversion."""

    def test_convert_basic_route(self):
        """Convert basic route dictionary to MEPRoute."""
        route_dict = {
            "route_id": "test_route",
            "system_type": "sanitary_drain",
            "pipe_size": 0.1583,
            "segments": [
                {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
            ],
        }
        route = _route_dict_to_mep_route(route_dict)

        assert route.id == "test_route"
        assert route.system_type == "sanitary_drain"
        assert route.pipe_size == 0.1583
        assert len(route.path_points) == 2

    def test_convert_multi_segment_route(self):
        """Convert route with multiple segments."""
        route_dict = {
            "route_id": "multi_seg",
            "system_type": "dhw",
            "segments": [
                {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                {"start": [5.0, 0.0, 4.0], "end": [10.0, 0.0, 4.0]},
                {"start": [10.0, 0.0, 4.0], "end": [10.0, 5.0, 4.0]},
            ],
        }
        route = _route_dict_to_mep_route(route_dict)

        # Should have 4 unique points (no duplicates at junctions)
        assert len(route.path_points) == 4

    def test_convert_route_default_pipe_size(self):
        """Route without pipe_size gets default."""
        route_dict = {
            "route_id": "no_size",
            "system_type": "dcw",
            "segments": [
                {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
            ],
        }
        route = _route_dict_to_mep_route(route_dict)

        assert route.pipe_size == 0.0833  # Default 1"

    def test_convert_routes_filters_empty(self):
        """Convert routes filters out routes with no valid paths."""
        route_dicts = [
            {
                "route_id": "valid",
                "system_type": "sanitary_drain",
                "segments": [
                    {"start": [0.0, 0.0, 4.0], "end": [5.0, 0.0, 4.0]},
                ],
            },
            {
                "route_id": "empty",
                "system_type": "dhw",
                "segments": [],  # No segments
            },
        ]
        routes = _convert_routes(route_dicts)

        assert len(routes) == 1
        assert routes[0].id == "valid"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegrateRoutesToPenetrations:
    """Tests for full route-to-penetration integration."""

    def test_basic_integration(self, sample_routes_json, sample_framing_json):
        """Basic integration produces penetrations."""
        result = integrate_routes_to_penetrations(
            sample_routes_json,
            sample_framing_json
        )

        assert "penetrations" in result
        assert "summary" in result

    def test_summary_statistics(self, sample_routes_json, sample_framing_json):
        """Summary contains expected statistics."""
        result = integrate_routes_to_penetrations(
            sample_routes_json,
            sample_framing_json
        )

        summary = result["summary"]
        assert "total" in summary
        assert "allowed" in summary
        assert "blocked" in summary
        assert "reinforcement_required" in summary
        assert "routes_processed" in summary
        assert summary["routes_processed"] == 2

    def test_empty_routes_returns_empty(self, empty_routes_json, sample_framing_json):
        """Empty routes returns empty penetrations."""
        result = integrate_routes_to_penetrations(
            empty_routes_json,
            sample_framing_json
        )

        assert result["penetrations"] == []
        assert result["summary"]["total"] == 0

    def test_empty_framing_returns_empty(self, sample_routes_json, empty_framing_json):
        """Empty framing returns empty penetrations."""
        result = integrate_routes_to_penetrations(
            sample_routes_json,
            empty_framing_json
        )

        assert result["penetrations"] == []
        assert result["summary"]["total"] == 0

    def test_invalid_routes_raises(self, sample_framing_json):
        """Invalid routes JSON raises ValueError."""
        with pytest.raises(ValueError):
            integrate_routes_to_penetrations(
                "invalid json",
                sample_framing_json
            )

    def test_invalid_framing_raises(self, sample_routes_json):
        """Invalid framing JSON raises ValueError."""
        with pytest.raises(ValueError):
            integrate_routes_to_penetrations(
                sample_routes_json,
                "invalid json"
            )


class TestPenetrationsToJson:
    """Tests for JSON serialization."""

    def test_serialize_result(self, sample_routes_json, sample_framing_json):
        """Serialize penetration result to JSON."""
        result = integrate_routes_to_penetrations(
            sample_routes_json,
            sample_framing_json
        )
        json_str = penetrations_to_json(result)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "penetrations" in parsed
        assert "summary" in parsed


# ============================================================================
# Utility Tests
# ============================================================================

class TestExtractPenetrationPoints:
    """Tests for point extraction by status."""

    def test_extract_allowed_points(self):
        """Extract allowed penetration points."""
        penetrations = [
            {"location": {"x": 1.0, "y": 2.0, "z": 3.0}, "is_allowed": True, "reinforcement_required": False},
        ]
        allowed, blocked, reinforce = extract_penetration_points(penetrations)

        assert len(allowed) == 1
        assert len(blocked) == 0
        assert len(reinforce) == 0
        assert allowed[0] == (1.0, 2.0, 3.0)

    def test_extract_blocked_points(self):
        """Extract blocked penetration points."""
        penetrations = [
            {"location": {"x": 4.0, "y": 5.0, "z": 6.0}, "is_allowed": False, "reinforcement_required": False},
        ]
        allowed, blocked, reinforce = extract_penetration_points(penetrations)

        assert len(allowed) == 0
        assert len(blocked) == 1
        assert len(reinforce) == 0
        assert blocked[0] == (4.0, 5.0, 6.0)

    def test_extract_reinforcement_points(self):
        """Extract reinforcement-required points."""
        penetrations = [
            {"location": {"x": 7.0, "y": 8.0, "z": 9.0}, "is_allowed": True, "reinforcement_required": True},
        ]
        allowed, blocked, reinforce = extract_penetration_points(penetrations)

        assert len(allowed) == 0
        assert len(blocked) == 0
        assert len(reinforce) == 1
        assert reinforce[0] == (7.0, 8.0, 9.0)

    def test_extract_mixed_points(self):
        """Extract mixed penetration status."""
        penetrations = [
            {"location": {"x": 1.0, "y": 0.0, "z": 0.0}, "is_allowed": True, "reinforcement_required": False},
            {"location": {"x": 2.0, "y": 0.0, "z": 0.0}, "is_allowed": False, "reinforcement_required": False},
            {"location": {"x": 3.0, "y": 0.0, "z": 0.0}, "is_allowed": True, "reinforcement_required": True},
        ]
        allowed, blocked, reinforce = extract_penetration_points(penetrations)

        assert len(allowed) == 1
        assert len(blocked) == 1
        assert len(reinforce) == 1


class TestGetPenetrationInfoString:
    """Tests for info string generation."""

    def test_info_string_contains_summary(self, sample_routes_json, sample_framing_json):
        """Info string contains summary statistics."""
        result = integrate_routes_to_penetrations(
            sample_routes_json,
            sample_framing_json
        )
        info = get_penetration_info_string(result)

        assert "Penetration Analysis Results" in info
        assert "Routes processed" in info
        assert "Total penetrations" in info
        assert "Allowed" in info
        assert "Blocked" in info
        assert "Reinforcement required" in info

    def test_info_string_contains_code_limits(self, sample_routes_json, sample_framing_json):
        """Info string contains code limit information."""
        result = integrate_routes_to_penetrations(
            sample_routes_json,
            sample_framing_json
        )
        info = get_penetration_info_string(result)

        assert "40%" in info  # MAX_PENETRATION_RATIO
        assert "33%" in info  # REINFORCEMENT_THRESHOLD
