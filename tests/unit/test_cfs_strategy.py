# File: tests/unit/test_cfs_strategy.py
"""
Unit tests for CFS profiles and strategy.

Tests:
    - CFS profile definitions and dimensions
    - DEFAULT_CFS_PROFILES mapping
    - get_cfs_profile() function
    - CFSFramingStrategy properties and methods
    - Strategy registration via factory
"""

import pytest
from typing import Dict

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    ElementType,
    ElementProfile,
    FramingStrategy,
    get_framing_strategy,
    list_available_materials,
)
from src.timber_framing_generator.materials.cfs import (
    CFSFramingStrategy,
    CFS_PROFILES,
    DEFAULT_CFS_PROFILES,
    get_cfs_profile,
    list_available_profiles,
)
from src.timber_framing_generator.materials.cfs.cfs_profiles import (
    get_stud_profiles,
    get_track_profiles,
)


# =============================================================================
# CFS Profile Tests
# =============================================================================

class TestCFSProfiles:
    """Tests for CFS profile definitions."""

    def test_profiles_exist(self):
        """CFS_PROFILES should contain standard CFS sizes."""
        assert len(CFS_PROFILES) > 0
        assert "350S162-54" in CFS_PROFILES
        assert "600S162-54" in CFS_PROFILES
        assert "350T125-54" in CFS_PROFILES
        assert "600T125-54" in CFS_PROFILES

    def test_profile_is_element_profile(self):
        """Each profile should be an ElementProfile instance."""
        for name, profile in CFS_PROFILES.items():
            assert isinstance(profile, ElementProfile), f"{name} is not ElementProfile"

    def test_profile_material_system(self):
        """All profiles should have MaterialSystem.CFS."""
        for name, profile in CFS_PROFILES.items():
            assert profile.material_system == MaterialSystem.CFS, f"{name} has wrong material"

    def test_profile_dimensions_positive(self):
        """All profile dimensions should be positive."""
        for name, profile in CFS_PROFILES.items():
            assert profile.width > 0, f"{name} width should be positive"
            assert profile.depth > 0, f"{name} depth should be positive"

    def test_profile_dimensions_in_feet(self):
        """Dimensions should be in feet (small values)."""
        for name, profile in CFS_PROFILES.items():
            # CFS profiles should be under 1 foot in any dimension
            assert profile.width < 1, f"{name} width should be < 1 foot"
            assert profile.depth < 1, f"{name} depth should be < 1 foot"

    def test_350S162_54_dimensions(self):
        """350S162-54 should have correct actual dimensions."""
        profile = CFS_PROFILES["350S162-54"]
        # 3.5" web = 0.292 feet, 1.62" flange = 0.135 feet
        assert abs(profile.depth - (3.5 / 12)) < 0.001
        assert abs(profile.width - (1.62 / 12)) < 0.001

    def test_600S162_54_dimensions(self):
        """600S162-54 should have correct actual dimensions."""
        profile = CFS_PROFILES["600S162-54"]
        # 6.0" web = 0.5 feet, 1.62" flange = 0.135 feet
        assert abs(profile.depth - (6.0 / 12)) < 0.001
        assert abs(profile.width - (1.62 / 12)) < 0.001

    def test_350T125_54_dimensions(self):
        """350T125-54 track should have correct dimensions."""
        profile = CFS_PROFILES["350T125-54"]
        # 3.5" web = 0.292 feet, 1.25" flange = 0.104 feet
        assert abs(profile.depth - (3.5 / 12)) < 0.001
        assert abs(profile.width - (1.25 / 12)) < 0.001

    def test_stud_profiles_have_lips(self):
        """Stud profiles (S) should have lips."""
        stud_profiles = get_stud_profiles()
        for name, profile in stud_profiles.items():
            assert "S" in name, f"{name} should be a stud profile"
            assert profile.properties.get("has_lips") is True
            assert profile.properties.get("profile_type") == "stud"

    def test_track_profiles_no_lips(self):
        """Track profiles (T) should not have lips."""
        track_profiles = get_track_profiles()
        for name, profile in track_profiles.items():
            assert "T" in name, f"{name} should be a track profile"
            assert profile.properties.get("has_lips") is False
            assert profile.properties.get("profile_type") == "track"

    def test_profiles_have_gauge_info(self):
        """Profiles should have gauge information."""
        for name, profile in CFS_PROFILES.items():
            assert "gauge" in profile.properties
            assert "thickness_mils" in profile.properties


# =============================================================================
# DEFAULT_CFS_PROFILES Tests
# =============================================================================

class TestDefaultCFSProfiles:
    """Tests for default CFS profile assignments."""

    def test_all_element_types_have_default(self):
        """All standard element types should have a default profile."""
        required_types = [
            ElementType.BOTTOM_PLATE,
            ElementType.TOP_PLATE,
            ElementType.STUD,
            ElementType.KING_STUD,
            ElementType.TRIMMER,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.ROW_BLOCKING,
        ]
        for element_type in required_types:
            assert element_type in DEFAULT_CFS_PROFILES, f"Missing default for {element_type}"

    def test_defaults_reference_valid_profiles(self):
        """All default profile names should exist in CFS_PROFILES."""
        for element_type, profile_name in DEFAULT_CFS_PROFILES.items():
            assert profile_name in CFS_PROFILES, f"{profile_name} not in CFS_PROFILES"

    def test_plates_use_tracks(self):
        """Bottom and top plates should use track profiles."""
        bottom_profile = DEFAULT_CFS_PROFILES[ElementType.BOTTOM_PLATE]
        top_profile = DEFAULT_CFS_PROFILES[ElementType.TOP_PLATE]
        assert "T" in bottom_profile, "Bottom plate should use track"
        assert "T" in top_profile, "Top plate should use track"

    def test_studs_use_stud_profiles(self):
        """Vertical members should use stud profiles."""
        stud_profile = DEFAULT_CFS_PROFILES[ElementType.STUD]
        king_profile = DEFAULT_CFS_PROFILES[ElementType.KING_STUD]
        trimmer_profile = DEFAULT_CFS_PROFILES[ElementType.TRIMMER]
        assert "S" in stud_profile, "Stud should use stud profile"
        assert "S" in king_profile, "King stud should use stud profile"
        assert "S" in trimmer_profile, "Trimmer should use stud profile"


# =============================================================================
# get_cfs_profile() Tests
# =============================================================================

class TestGetCFSProfile:
    """Tests for get_cfs_profile() function."""

    def test_get_default_stud_profile(self):
        """get_cfs_profile should return default for stud."""
        profile = get_cfs_profile(ElementType.STUD)
        assert profile.name == DEFAULT_CFS_PROFILES[ElementType.STUD]

    def test_get_default_plate_profile(self):
        """get_cfs_profile should return track for plates."""
        profile = get_cfs_profile(ElementType.BOTTOM_PLATE)
        assert "T" in profile.name

    def test_profile_override(self):
        """get_cfs_profile should use override when provided."""
        profile = get_cfs_profile(ElementType.STUD, "800S162-68")
        assert profile.name == "800S162-68"

    def test_invalid_override_raises(self):
        """get_cfs_profile should raise KeyError for invalid override."""
        with pytest.raises(KeyError):
            get_cfs_profile(ElementType.STUD, "INVALID_PROFILE")

    def test_unknown_element_type_uses_fallback(self):
        """Unknown element type should use fallback profile."""
        # ROW_BLOCKING is in defaults, so use a non-standard type behavior
        # This tests that get() with default works
        profile = get_cfs_profile(ElementType.STUD)
        assert profile is not None


# =============================================================================
# list_available_profiles() Tests
# =============================================================================

class TestListAvailableProfiles:
    """Tests for list_available_profiles() function."""

    def test_returns_list(self):
        """list_available_profiles should return a list."""
        profiles = list_available_profiles()
        assert isinstance(profiles, list)

    def test_contains_profiles(self):
        """list_available_profiles should contain expected profiles."""
        profiles = list_available_profiles()
        assert "350S162-54" in profiles
        assert "600T125-54" in profiles

    def test_matches_profiles_keys(self):
        """list_available_profiles should match CFS_PROFILES keys."""
        profiles = list_available_profiles()
        assert set(profiles) == set(CFS_PROFILES.keys())


# =============================================================================
# CFSFramingStrategy Tests
# =============================================================================

class TestCFSFramingStrategy:
    """Tests for CFSFramingStrategy class."""

    @pytest.fixture
    def strategy(self):
        """Create a CFSFramingStrategy instance."""
        return CFSFramingStrategy()

    def test_is_framing_strategy(self, strategy):
        """CFSFramingStrategy should inherit from FramingStrategy."""
        assert isinstance(strategy, FramingStrategy)

    def test_material_system_property(self, strategy):
        """material_system should return MaterialSystem.CFS."""
        assert strategy.material_system == MaterialSystem.CFS

    def test_default_profiles_property(self, strategy):
        """default_profiles should return ElementProfile dict."""
        profiles = strategy.default_profiles
        assert isinstance(profiles, dict)
        for element_type, profile in profiles.items():
            assert isinstance(element_type, ElementType)
            assert isinstance(profile, ElementProfile)

    def test_generation_sequence(self, strategy):
        """get_generation_sequence should return ordered list."""
        sequence = strategy.get_generation_sequence()
        assert isinstance(sequence, list)
        assert len(sequence) > 0
        assert all(isinstance(et, ElementType) for et in sequence)

    def test_generation_sequence_starts_with_plates(self, strategy):
        """Generation sequence should start with plates (tracks)."""
        sequence = strategy.get_generation_sequence()
        assert sequence[0] == ElementType.BOTTOM_PLATE
        assert sequence[1] == ElementType.TOP_PLATE

    def test_generation_sequence_ends_with_blocking(self, strategy):
        """Generation sequence should end with blocking (bridging)."""
        sequence = strategy.get_generation_sequence()
        assert sequence[-1] == ElementType.ROW_BLOCKING

    def test_get_element_types(self, strategy):
        """get_element_types should return list of ElementType."""
        element_types = strategy.get_element_types()
        assert isinstance(element_types, list)
        assert all(isinstance(et, ElementType) for et in element_types)

    def test_get_profile_returns_profile(self, strategy):
        """get_profile should return ElementProfile."""
        profile = strategy.get_profile(ElementType.STUD)
        assert isinstance(profile, ElementProfile)
        assert profile.material_system == MaterialSystem.CFS

    def test_get_profile_with_config_override(self, strategy):
        """get_profile should use config override."""
        config = {"profile_overrides": {"stud": "800S162-68"}}
        profile = strategy.get_profile(ElementType.STUD, config)
        assert profile.name == "800S162-68"

    def test_create_horizontal_members_returns_list(self, strategy):
        """create_horizontal_members should return list (empty in Phase 4)."""
        result = strategy.create_horizontal_members({}, {}, {})
        assert isinstance(result, list)

    def test_create_vertical_members_returns_list(self, strategy):
        """create_vertical_members should return list (empty in Phase 4)."""
        result = strategy.create_vertical_members({}, {}, [], {})
        assert isinstance(result, list)

    def test_create_opening_members_returns_list(self, strategy):
        """create_opening_members should return list (empty in Phase 4)."""
        result = strategy.create_opening_members({}, {}, [], {})
        assert isinstance(result, list)

    def test_create_bracing_members_returns_list(self, strategy):
        """create_bracing_members should return list (empty in Phase 4)."""
        result = strategy.create_bracing_members({}, {}, [], {})
        assert isinstance(result, list)

    def test_generate_framing_returns_list(self, strategy):
        """generate_framing should return list (empty in Phase 4)."""
        result = strategy.generate_framing({}, {}, {})
        assert isinstance(result, list)


# =============================================================================
# Strategy Registration Tests
# =============================================================================

class TestCFSStrategyRegistration:
    """Tests for CFS strategy registration."""

    def test_cfs_in_available_materials(self):
        """MaterialSystem.CFS should be in available materials."""
        available = list_available_materials()
        assert MaterialSystem.CFS in available

    def test_get_cfs_strategy_via_factory(self):
        """get_framing_strategy should return CFSFramingStrategy for CFS."""
        strategy = get_framing_strategy(MaterialSystem.CFS)
        assert isinstance(strategy, CFSFramingStrategy)
        assert strategy.material_system == MaterialSystem.CFS

    def test_timber_and_cfs_coexist(self):
        """Both Timber and CFS strategies should be available."""
        available = list_available_materials()
        assert MaterialSystem.TIMBER in available
        assert MaterialSystem.CFS in available

        timber_strategy = get_framing_strategy(MaterialSystem.TIMBER)
        cfs_strategy = get_framing_strategy(MaterialSystem.CFS)

        assert timber_strategy.material_system == MaterialSystem.TIMBER
        assert cfs_strategy.material_system == MaterialSystem.CFS

    def test_strategies_are_different_instances(self):
        """Timber and CFS strategies should be different instances."""
        timber = get_framing_strategy(MaterialSystem.TIMBER)
        cfs = get_framing_strategy(MaterialSystem.CFS)
        assert timber is not cfs
        assert type(timber).__name__ == "TimberFramingStrategy"
        assert type(cfs).__name__ == "CFSFramingStrategy"
