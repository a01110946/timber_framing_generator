# File: tests/unit/test_timber_strategy.py
"""
Unit tests for timber framing strategy.

Tests cover:
- Timber profile definitions and lookups
- TimberFramingStrategy implementation
- Strategy registration and retrieval
"""

import pytest

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    ElementType,
    ElementProfile,
    get_framing_strategy,
    list_available_materials,
)


class TestTimberProfiles:
    """Test timber profile definitions."""

    def test_profiles_module_imports(self):
        """Timber profiles module can be imported."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            TIMBER_PROFILES,
            DEFAULT_TIMBER_PROFILES,
            get_timber_profile,
        )
        assert TIMBER_PROFILES is not None
        assert DEFAULT_TIMBER_PROFILES is not None

    def test_standard_profiles_exist(self):
        """Standard lumber profiles are defined."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            TIMBER_PROFILES,
        )
        assert "2x4" in TIMBER_PROFILES
        assert "2x6" in TIMBER_PROFILES
        assert "2x8" in TIMBER_PROFILES
        assert "2x10" in TIMBER_PROFILES
        assert "2x12" in TIMBER_PROFILES

    def test_profile_is_element_profile(self):
        """Profiles are ElementProfile instances."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            TIMBER_PROFILES,
        )
        profile = TIMBER_PROFILES["2x4"]
        assert isinstance(profile, ElementProfile)

    def test_profile_dimensions_in_feet(self):
        """Profile dimensions are in feet and reasonable."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            TIMBER_PROFILES,
        )
        profile = TIMBER_PROFILES["2x4"]

        # 2x4 actual: 1.5" x 3.5" = 0.125' x 0.2917'
        assert profile.width == pytest.approx(1.5 / 12, rel=0.01)
        assert profile.depth == pytest.approx(3.5 / 12, rel=0.01)

    def test_profile_material_system(self):
        """Profiles are tagged with TIMBER material system."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            TIMBER_PROFILES,
        )
        for name, profile in TIMBER_PROFILES.items():
            assert profile.material_system == MaterialSystem.TIMBER, (
                f"Profile {name} should have TIMBER material system"
            )

    def test_get_timber_profile_default(self):
        """Can get default profile by element type."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            get_timber_profile,
        )
        profile = get_timber_profile(ElementType.STUD)
        assert profile.name == "2x4"

    def test_get_timber_profile_override(self):
        """Can override profile for element type."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            get_timber_profile,
        )
        profile = get_timber_profile(ElementType.HEADER, "2x8")
        assert profile.name == "2x8"

    def test_get_timber_profile_invalid_raises(self):
        """Invalid profile name raises KeyError."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            get_timber_profile,
        )
        with pytest.raises(KeyError):
            get_timber_profile(ElementType.STUD, "invalid_profile")

    def test_default_profiles_cover_all_types(self):
        """Default profiles defined for all timber element types."""
        from src.timber_framing_generator.materials.timber.timber_profiles import (
            DEFAULT_TIMBER_PROFILES,
        )
        expected_types = [
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
        for et in expected_types:
            assert et in DEFAULT_TIMBER_PROFILES, f"Missing default for {et}"


class TestTimberStrategy:
    """Test TimberFramingStrategy implementation."""

    def test_strategy_import(self):
        """Strategy can be imported."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        assert TimberFramingStrategy is not None

    def test_strategy_instantiation(self):
        """Strategy can be instantiated."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()
        assert strategy is not None

    def test_material_system_property(self):
        """Strategy reports TIMBER as material system."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()
        assert strategy.material_system == MaterialSystem.TIMBER

    def test_default_profiles_property(self):
        """Strategy provides default profiles for element types."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()
        profiles = strategy.default_profiles

        assert isinstance(profiles, dict)
        assert ElementType.STUD in profiles
        assert isinstance(profiles[ElementType.STUD], ElementProfile)
        assert profiles[ElementType.STUD].material_system == MaterialSystem.TIMBER

    def test_generation_sequence(self):
        """Generation sequence includes expected types in order."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()
        sequence = strategy.get_generation_sequence()

        assert isinstance(sequence, list)
        assert len(sequence) > 0

        # Check key elements are present
        assert ElementType.BOTTOM_PLATE in sequence
        assert ElementType.TOP_PLATE in sequence
        assert ElementType.STUD in sequence
        assert ElementType.ROW_BLOCKING in sequence

        # Check order: plates before studs
        plate_idx = sequence.index(ElementType.BOTTOM_PLATE)
        stud_idx = sequence.index(ElementType.STUD)
        assert plate_idx < stud_idx, "Plates should be generated before studs"

    def test_element_types(self):
        """Element types list covers all timber framing elements."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()
        types = strategy.get_element_types()

        expected = [
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
        for et in expected:
            assert et in types, f"Missing element type: {et}"

    def test_get_profile_method(self):
        """get_profile method returns appropriate profile."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()

        profile = strategy.get_profile(ElementType.STUD)
        assert profile.name == "2x4"

    def test_get_profile_with_override(self):
        """get_profile respects config overrides."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()

        config = {"profile_overrides": {"header": "2x10"}}
        profile = strategy.get_profile(ElementType.HEADER, config)
        assert profile.name == "2x10"

    def test_create_methods_return_lists(self):
        """All create_* methods return lists (even if empty in Phase 2)."""
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )
        strategy = TimberFramingStrategy()

        # Phase 2: methods return empty lists
        horizontal = strategy.create_horizontal_members({}, {}, {})
        vertical = strategy.create_vertical_members({}, {}, [], {})
        opening = strategy.create_opening_members({}, {}, [], {})
        bracing = strategy.create_bracing_members({}, {}, [], {})

        assert isinstance(horizontal, list)
        assert isinstance(vertical, list)
        assert isinstance(opening, list)
        assert isinstance(bracing, list)


class TestStrategyRegistration:
    """Test strategy registration and factory retrieval."""

    def test_timber_in_available_materials(self):
        """TIMBER is listed in available materials after import."""
        # Import triggers registration
        from src.timber_framing_generator.materials.timber import timber_strategy  # noqa: F401

        available = list_available_materials()
        assert MaterialSystem.TIMBER in available

    def test_get_framing_strategy_timber(self):
        """Can retrieve timber strategy via factory."""
        # Import triggers registration
        from src.timber_framing_generator.materials.timber import (
            TimberFramingStrategy,
        )

        strategy = get_framing_strategy(MaterialSystem.TIMBER)
        assert isinstance(strategy, TimberFramingStrategy)

    def test_strategy_singleton(self):
        """Strategy factory returns the same registered instance."""
        from src.timber_framing_generator.materials.timber import timber_strategy  # noqa: F401

        strategy1 = get_framing_strategy(MaterialSystem.TIMBER)
        strategy2 = get_framing_strategy(MaterialSystem.TIMBER)
        assert strategy1 is strategy2
