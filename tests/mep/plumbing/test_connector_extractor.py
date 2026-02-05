# File: tests/mep/plumbing/test_connector_extractor.py
"""Tests for plumbing connector extraction and fixture type classification.

Tests the connector_extractor module's fixture type classification logic
and the MEPConnector fixture_type/fixture_family field handling.
"""

import pytest

from src.timber_framing_generator.core.mep_system import MEPConnector, MEPDomain
from src.timber_framing_generator.mep.plumbing.connector_extractor import (
    FIXTURE_TYPE_RULES,
    _classify_fixture_type,
    _get_fixture_info,
)


# --- Tests for _classify_fixture_type ---


class TestClassifyFixtureType:
    """Tests for keyword-based fixture type classification."""

    @pytest.mark.parametrize(
        "family_name,expected",
        [
            ("M_Water Closet - Flush Tank", "toilet"),
            ("Toilet - Elongated", "toilet"),
            ("WC Wall Mounted", "toilet"),
            ("M_Lavatory - Round", "sink"),
            ("Kitchen Sink - Double Bowl", "sink"),
            ("Wash Basin", "sink"),
            ("Vanity - 48in", "sink"),
            ("Bath Tub - Whirlpool", "bathtub"),
            ("Bathtub - Standard", "bathtub"),
            ("Tub-Shower Combo", "bathtub"),
            ("Shower Stall - 36x36", "shower"),
            ("Floor Drain - 4in", "floor_drain"),
            ("Floor Drain Round", "floor_drain"),
            ("Urinal - Wall Hung", "urinal"),
            ("Dishwasher - Standard", "dishwasher"),
            ("Washing Machine Outlet", "washing_machine"),
            ("Hose Bib - Exterior", "hose_bib"),
        ],
    )
    def test_known_fixtures(self, family_name: str, expected: str) -> None:
        """Known fixture family names classify correctly."""
        assert _classify_fixture_type(family_name) == expected

    def test_case_insensitive(self) -> None:
        """Classification is case-insensitive."""
        assert _classify_fixture_type("TOILET FLUSH VALVE") == "toilet"
        assert _classify_fixture_type("kitchen SINK") == "sink"
        assert _classify_fixture_type("Shower HEAD") == "shower"

    def test_unknown_fixture(self) -> None:
        """Unrecognized family names return 'unknown'."""
        assert _classify_fixture_type("Generic Plumbing Fixture") == "unknown"
        assert _classify_fixture_type("SomeCustomFamily") == "unknown"
        assert _classify_fixture_type("") == "unknown"

    def test_priority_order(self) -> None:
        """More specific keywords match before generic ones.

        'water_closet' matches before 'drain' would match for a
        hypothetical family named 'Water Closet Drain'.
        """
        # "water_closet" should match "toilet" not "floor_drain"
        result = _classify_fixture_type("Water_Closet Floor Drain Combo")
        assert result == "toilet"

    def test_drain_keyword_matches_floor_drain(self) -> None:
        """The 'drain' keyword matches floor_drain type."""
        assert _classify_fixture_type("Area Drain - 6in") == "floor_drain"


# --- Tests for _get_fixture_info ---


class TestGetFixtureInfo:
    """Tests for Revit element fixture info extraction."""

    def test_with_full_hierarchy(self) -> None:
        """Element with Symbol.Family.Name extracts correctly."""

        class MockFamily:
            Name = "M_Water Closet - Flush Tank"

        class MockSymbol:
            Family = MockFamily()

        class MockElement:
            Symbol = MockSymbol()

        fixture_type, fixture_family = _get_fixture_info(MockElement())
        assert fixture_type == "toilet"
        assert fixture_family == "M_Water Closet - Flush Tank"

    def test_no_symbol(self) -> None:
        """Element without Symbol returns (None, None)."""

        class MockElement:
            pass

        fixture_type, fixture_family = _get_fixture_info(MockElement())
        assert fixture_type is None
        assert fixture_family is None

    def test_no_family(self) -> None:
        """Element with Symbol but no Family returns (None, None)."""

        class MockSymbol:
            pass

        class MockElement:
            Symbol = MockSymbol()

        fixture_type, fixture_family = _get_fixture_info(MockElement())
        assert fixture_type is None
        assert fixture_family is None

    def test_no_name(self) -> None:
        """Element with Symbol.Family but no Name returns (None, None)."""

        class MockFamily:
            pass

        class MockSymbol:
            Family = MockFamily()

        class MockElement:
            Symbol = MockSymbol()

        fixture_type, fixture_family = _get_fixture_info(MockElement())
        assert fixture_type is None
        assert fixture_family is None


# --- Tests for MEPConnector fixture fields ---


class TestMEPConnectorFixtureFields:
    """Tests for MEPConnector fixture_type and fixture_family fields."""

    def _make_connector(self, **kwargs) -> MEPConnector:
        """Helper to create MEPConnector with defaults."""
        defaults = {
            "id": "test_001",
            "origin": (1.0, 2.0, 3.0),
            "direction": (0.0, 0.0, -1.0),
            "domain": MEPDomain.PLUMBING,
            "system_type": "Sanitary",
            "owner_element_id": 12345,
        }
        defaults.update(kwargs)
        return MEPConnector(**defaults)

    def test_fixture_type_defaults_none(self) -> None:
        """fixture_type defaults to None when not provided."""
        conn = self._make_connector()
        assert conn.fixture_type is None
        assert conn.fixture_family is None

    def test_fixture_type_set(self) -> None:
        """fixture_type and fixture_family can be set."""
        conn = self._make_connector(
            fixture_type="toilet",
            fixture_family="M_Water Closet - Flush Tank",
        )
        assert conn.fixture_type == "toilet"
        assert conn.fixture_family == "M_Water Closet - Flush Tank"

    def test_to_dict_without_fixture_fields(self) -> None:
        """to_dict omits fixture fields when None (backward compat)."""
        conn = self._make_connector()
        data = conn.to_dict()
        assert "fixture_type" not in data
        assert "fixture_family" not in data

    def test_to_dict_with_fixture_fields(self) -> None:
        """to_dict includes fixture fields when set."""
        conn = self._make_connector(
            fixture_type="sink",
            fixture_family="Kitchen Sink - Double Bowl",
        )
        data = conn.to_dict()
        assert data["fixture_type"] == "sink"
        assert data["fixture_family"] == "Kitchen Sink - Double Bowl"

    def test_from_dict_without_fixture_fields(self) -> None:
        """from_dict handles missing fixture fields (backward compat)."""
        data = {
            "id": "test_001",
            "origin": {"x": 1.0, "y": 2.0, "z": 3.0},
            "direction": {"x": 0.0, "y": 0.0, "z": -1.0},
            "domain": "plumbing",
            "system_type": "Sanitary",
            "owner_element_id": 12345,
        }
        conn = MEPConnector.from_dict(data)
        assert conn.fixture_type is None
        assert conn.fixture_family is None

    def test_from_dict_with_fixture_fields(self) -> None:
        """from_dict parses fixture fields when present."""
        data = {
            "id": "test_001",
            "origin": {"x": 1.0, "y": 2.0, "z": 3.0},
            "direction": {"x": 0.0, "y": 0.0, "z": -1.0},
            "domain": "plumbing",
            "system_type": "Sanitary",
            "owner_element_id": 12345,
            "fixture_type": "toilet",
            "fixture_family": "M_Water Closet - Flush Tank",
        }
        conn = MEPConnector.from_dict(data)
        assert conn.fixture_type == "toilet"
        assert conn.fixture_family == "M_Water Closet - Flush Tank"

    def test_round_trip_serialization(self) -> None:
        """to_dict -> from_dict preserves fixture fields."""
        original = self._make_connector(
            fixture_type="bathtub",
            fixture_family="Bath Tub - Whirlpool",
        )
        data = original.to_dict()
        restored = MEPConnector.from_dict(data)
        assert restored.fixture_type == original.fixture_type
        assert restored.fixture_family == original.fixture_family
