# File: tests/panels/test_panel_config.py
"""Unit tests for panel configuration."""

import pytest
from src.timber_framing_generator.panels.panel_config import (
    PanelConfig,
    PanelizationStrategy,
    CornerPriority,
    ExclusionZone,
)


class TestExclusionZone:
    """Tests for ExclusionZone dataclass."""

    def test_creation(self):
        """Test basic creation."""
        zone = ExclusionZone(u_start=5.0, u_end=10.0, zone_type="opening")
        assert zone.u_start == 5.0
        assert zone.u_end == 10.0
        assert zone.zone_type == "opening"
        assert zone.element_id is None

    def test_width_property(self):
        """Test width calculation."""
        zone = ExclusionZone(u_start=5.0, u_end=10.0, zone_type="opening")
        assert zone.width == 5.0

    def test_contains(self):
        """Test contains method."""
        zone = ExclusionZone(u_start=5.0, u_end=10.0, zone_type="opening")
        assert zone.contains(5.0)  # Start boundary
        assert zone.contains(7.5)  # Middle
        assert zone.contains(10.0)  # End boundary
        assert not zone.contains(4.9)  # Before
        assert not zone.contains(10.1)  # After

    def test_overlaps(self):
        """Test overlaps method."""
        zone1 = ExclusionZone(u_start=5.0, u_end=10.0, zone_type="opening")
        zone2 = ExclusionZone(u_start=8.0, u_end=15.0, zone_type="opening")
        zone3 = ExclusionZone(u_start=12.0, u_end=18.0, zone_type="opening")

        assert zone1.overlaps(zone2)  # Overlapping
        assert zone2.overlaps(zone1)  # Symmetric
        assert not zone1.overlaps(zone3)  # Not overlapping

    def test_invalid_bounds_raises(self):
        """Test that invalid bounds raise ValueError."""
        with pytest.raises(ValueError):
            ExclusionZone(u_start=10.0, u_end=5.0, zone_type="opening")


class TestPanelConfig:
    """Tests for PanelConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PanelConfig()
        assert config.max_panel_length == 24.0
        assert config.min_panel_length == 4.0
        assert config.max_panel_height == 12.0
        assert config.stud_spacing == 1.333
        assert config.corner_priority == CornerPriority.LONGER_WALL

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PanelConfig(
            max_panel_length=20.0,
            min_panel_length=6.0,
            stud_spacing=2.0,
        )
        assert config.max_panel_length == 20.0
        assert config.min_panel_length == 6.0
        assert config.stud_spacing == 2.0

    def test_corner_priority_string_conversion(self):
        """Test that string corner_priority is converted to enum."""
        config = PanelConfig(corner_priority="alternate")
        assert config.corner_priority == CornerPriority.ALTERNATE

    def test_validate_success(self):
        """Test validation of valid config."""
        config = PanelConfig()
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_invalid_panel_length(self):
        """Test validation catches invalid panel length."""
        config = PanelConfig(max_panel_length=-1.0)
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "max_panel_length must be positive" in str(exc_info.value)

    def test_validate_min_greater_than_max(self):
        """Test validation catches min > max."""
        config = PanelConfig(min_panel_length=30.0, max_panel_length=24.0)
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "min_panel_length" in str(exc_info.value)

    def test_validate_transport_less_than_panel(self):
        """Test validation catches transport < panel length."""
        config = PanelConfig(max_panel_length=50.0, max_transport_length=40.0)
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "max_transport_length" in str(exc_info.value)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = PanelConfig()
        d = config.to_dict()
        assert d["max_panel_length"] == 24.0
        assert d["corner_priority"] == "longer_wall"
        assert "stud_spacing" in d

    def test_from_dict(self):
        """Test creation from dictionary."""
        d = {
            "max_panel_length": 20.0,
            "stud_spacing": 2.0,
            "corner_priority": "alternate",
        }
        config = PanelConfig.from_dict(d)
        assert config.max_panel_length == 20.0
        assert config.stud_spacing == 2.0
        assert config.corner_priority == CornerPriority.ALTERNATE

    def test_for_residential(self):
        """Test residential preset."""
        config = PanelConfig.for_residential()
        assert config.max_panel_length == 24.0
        assert config.max_panel_height == 10.0
        assert config.stud_spacing == 1.333

    def test_for_commercial(self):
        """Test commercial preset."""
        config = PanelConfig.for_commercial()
        assert config.max_panel_length == 32.0
        assert config.max_panel_height == 14.0

    def test_for_24_oc(self):
        """Test 24" OC preset."""
        config = PanelConfig.for_24_oc()
        assert config.stud_spacing == 2.0


class TestPanelizationStrategy:
    """Tests for PanelizationStrategy enum and PanelConfig strategy fields."""

    def test_default_strategy(self):
        """Test default strategy is LENGTH_OPTIMIZED."""
        config = PanelConfig()
        assert config.strategy == PanelizationStrategy.LENGTH_OPTIMIZED

    def test_strategy_string_conversion(self):
        """Test that string strategy is converted to enum."""
        config = PanelConfig(strategy="opening_bounded")
        assert config.strategy == PanelizationStrategy.OPENING_BOUNDED

    def test_strategy_enum_values(self):
        """Test all strategy enum values exist."""
        assert PanelizationStrategy.LENGTH_OPTIMIZED.value == "length_optimized"
        assert PanelizationStrategy.OPENING_BOUNDED.value == "opening_bounded"
        assert PanelizationStrategy.NO_SPLIT_THROUGH.value == "no_split_through"
        assert PanelizationStrategy.EQUAL_LENGTH.value == "equal_length"

    def test_strategy_to_dict(self):
        """Test strategy is included in to_dict output."""
        config = PanelConfig(strategy=PanelizationStrategy.OPENING_BOUNDED)
        d = config.to_dict()
        assert d["strategy"] == "opening_bounded"
        assert d["opening_edge_stud"] == "king_and_trimmer"
        assert d["stud_width"] == 0.125

    def test_strategy_from_dict(self):
        """Test strategy is correctly parsed from dict."""
        d = {
            "strategy": "no_split_through",
            "opening_edge_stud": "trimmer_only",
            "stud_width": 0.125,
        }
        config = PanelConfig.from_dict(d)
        assert config.strategy == PanelizationStrategy.NO_SPLIT_THROUGH
        assert config.opening_edge_stud == "trimmer_only"

    def test_strategy_from_dict_defaults(self):
        """Test from_dict with missing strategy uses default."""
        config = PanelConfig.from_dict({})
        assert config.strategy == PanelizationStrategy.LENGTH_OPTIMIZED
        assert config.opening_edge_stud == "king_and_trimmer"

    def test_strategy_roundtrip(self):
        """Test to_dict -> from_dict roundtrip preserves strategy."""
        original = PanelConfig(
            strategy=PanelizationStrategy.EQUAL_LENGTH,
            opening_edge_stud="trimmer_only",
        )
        d = original.to_dict()
        restored = PanelConfig.from_dict(d)
        assert restored.strategy == original.strategy
        assert restored.opening_edge_stud == original.opening_edge_stud

    def test_validate_invalid_opening_edge_stud(self):
        """Test validation catches invalid opening_edge_stud."""
        config = PanelConfig(opening_edge_stud="invalid_value")
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "opening_edge_stud" in str(exc_info.value)

    def test_validate_invalid_stud_width(self):
        """Test validation catches non-positive stud_width."""
        config = PanelConfig(stud_width=0)
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "stud_width" in str(exc_info.value)

    def test_default_opening_edge_stud(self):
        """Test default opening_edge_stud is king_and_trimmer."""
        config = PanelConfig()
        assert config.opening_edge_stud == "king_and_trimmer"

    def test_default_stud_width(self):
        """Test default stud_width is 0.125 ft (1.5 inches)."""
        config = PanelConfig()
        assert config.stud_width == 0.125
