# File: tests/assemblies/test_assembly_views.py
"""Tests for AssemblyViewConfig, CreatedViewInfo, and view helpers.

Tests cover defaults, from_dict() with partial/full/empty/old-format dicts,
to_dict() roundtrip, DISPLAY_STYLE_MAP completeness, CreatedViewInfo,
schedule field parsing, and backward compatibility.
"""

import pytest

from src.timber_framing_generator.assemblies.assembly_views import (
    AssemblyViewConfig,
    CreatedViewInfo,
    DISPLAY_STYLE_MAP,
    DETAIL_LEVEL_MAP,
    DEFAULT_SCHEDULE_FIELDS,
    DEFAULT_TAKEOFF_FIELDS,
    _parse_field_names,
)


# =============================================================================
# AssemblyViewConfig Defaults
# =============================================================================

class TestAssemblyViewConfigDefaults:
    """Tests for AssemblyViewConfig default values."""

    def test_default_values(self) -> None:
        config = AssemblyViewConfig()
        assert config.include_3d is True
        assert config.include_front_elevation is True
        assert config.include_top_elevation is False
        assert config.include_material_takeoff is False
        assert config.detail_level == "Fine"
        assert config.display_style == "HiddenLine"

    def test_default_new_elevations(self) -> None:
        """New elevation defaults are all False."""
        config = AssemblyViewConfig()
        assert config.include_back_elevation is False
        assert config.include_bottom_elevation is False
        assert config.include_left_elevation is False
        assert config.include_right_elevation is False

    def test_default_schedules(self) -> None:
        """Schedule defaults are all False/empty."""
        config = AssemblyViewConfig()
        assert config.include_column_schedule is False
        assert config.include_framing_schedule is False
        assert config.schedule_fields == ""
        assert config.schedule_template_name == ""

    def test_default_takeoff_config(self) -> None:
        """Takeoff field/template defaults are empty strings."""
        config = AssemblyViewConfig()
        assert config.takeoff_fields == ""
        assert config.takeoff_template_name == ""

    def test_default_section_markers(self) -> None:
        """Section markers hidden by default."""
        config = AssemblyViewConfig()
        assert config.hide_section_markers is True

    def test_default_sheet(self) -> None:
        """Sheet creation off by default."""
        config = AssemblyViewConfig()
        assert config.include_sheet is False
        assert config.titleblock_name == ""

    def test_default_material_takeoff_is_false(self) -> None:
        """Material takeoff defaults to False (appears under Schedules, not Assembly)."""
        config = AssemblyViewConfig()
        assert config.include_material_takeoff is False


# =============================================================================
# AssemblyViewConfig.from_dict()
# =============================================================================

class TestAssemblyViewConfigFromDict:
    """Tests for from_dict() classmethod."""

    def test_from_none(self) -> None:
        config = AssemblyViewConfig.from_dict(None)
        assert config.detail_level == "Fine"
        assert config.include_3d is True

    def test_from_empty_dict(self) -> None:
        config = AssemblyViewConfig.from_dict({})
        assert config.detail_level == "Fine"
        assert config.display_style == "HiddenLine"
        assert config.include_material_takeoff is False

    def test_from_partial_dict(self) -> None:
        config = AssemblyViewConfig.from_dict({
            "detail_level": "Coarse",
            "include_material_takeoff": True,
        })
        assert config.detail_level == "Coarse"
        assert config.include_material_takeoff is True
        # Non-specified keys get defaults
        assert config.include_3d is True
        assert config.display_style == "HiddenLine"

    def test_from_full_dict(self) -> None:
        data = {
            "include_3d": False,
            "include_front_elevation": False,
            "include_top_elevation": True,
            "include_material_takeoff": True,
            "detail_level": "Medium",
            "display_style": "Shaded",
        }
        config = AssemblyViewConfig.from_dict(data)
        assert config.include_3d is False
        assert config.include_front_elevation is False
        assert config.include_top_elevation is True
        assert config.include_material_takeoff is True
        assert config.detail_level == "Medium"
        assert config.display_style == "Shaded"

    def test_from_dict_ignores_extra_keys(self) -> None:
        config = AssemblyViewConfig.from_dict({
            "detail_level": "Fine",
            "unknown_key": "ignored",
        })
        assert config.detail_level == "Fine"

    def test_backward_compat_old_6_key_dict(self) -> None:
        """Old JSON with only 6 keys produces valid config with new defaults."""
        old_data = {
            "include_3d": True,
            "include_front_elevation": True,
            "include_top_elevation": False,
            "include_material_takeoff": False,
            "detail_level": "Fine",
            "display_style": "HiddenLine",
        }
        config = AssemblyViewConfig.from_dict(old_data)
        # Original fields preserved
        assert config.include_3d is True
        assert config.detail_level == "Fine"
        # New fields get defaults
        assert config.include_back_elevation is False
        assert config.include_left_elevation is False
        assert config.include_right_elevation is False
        assert config.include_bottom_elevation is False
        assert config.include_column_schedule is False
        assert config.include_framing_schedule is False
        assert config.schedule_fields == ""
        assert config.hide_section_markers is True
        assert config.include_sheet is False
        assert config.titleblock_name == ""

    def test_from_full_expanded_dict(self) -> None:
        """Full dict with all 19 fields."""
        data = {
            "include_3d": False,
            "include_front_elevation": False,
            "include_top_elevation": True,
            "include_material_takeoff": True,
            "detail_level": "Medium",
            "display_style": "Consistent Colors",
            "include_back_elevation": True,
            "include_bottom_elevation": True,
            "include_left_elevation": True,
            "include_right_elevation": True,
            "include_column_schedule": True,
            "include_framing_schedule": True,
            "schedule_fields": "Family, Type",
            "schedule_template_name": "MyTemplate",
            "takeoff_fields": "Material: Name, Material: Volume",
            "takeoff_template_name": "TakeoffTemplate",
            "hide_section_markers": False,
            "include_sheet": True,
            "titleblock_name": "E1 30x42",
        }
        config = AssemblyViewConfig.from_dict(data)
        assert config.include_3d is False
        assert config.include_back_elevation is True
        assert config.include_column_schedule is True
        assert config.schedule_fields == "Family, Type"
        assert config.schedule_template_name == "MyTemplate"
        assert config.takeoff_fields == "Material: Name, Material: Volume"
        assert config.hide_section_markers is False
        assert config.include_sheet is True
        assert config.titleblock_name == "E1 30x42"


# =============================================================================
# AssemblyViewConfig.to_dict()
# =============================================================================

class TestAssemblyViewConfigToDict:
    """Tests for to_dict() method."""

    def test_to_dict_all_fields(self) -> None:
        config = AssemblyViewConfig(
            include_3d=False,
            include_front_elevation=True,
            include_top_elevation=True,
            include_material_takeoff=True,
            detail_level="Medium",
            display_style="Wireframe",
        )
        d = config.to_dict()
        assert d["include_3d"] is False
        assert d["include_front_elevation"] is True
        assert d["include_top_elevation"] is True
        assert d["include_material_takeoff"] is True
        assert d["detail_level"] == "Medium"
        assert d["display_style"] == "Wireframe"

    def test_to_dict_has_19_keys(self) -> None:
        d = AssemblyViewConfig().to_dict()
        assert len(d) == 19

    def test_to_dict_includes_new_fields(self) -> None:
        d = AssemblyViewConfig().to_dict()
        assert "include_back_elevation" in d
        assert "include_bottom_elevation" in d
        assert "include_left_elevation" in d
        assert "include_right_elevation" in d
        assert "include_column_schedule" in d
        assert "include_framing_schedule" in d
        assert "schedule_fields" in d
        assert "schedule_template_name" in d
        assert "takeoff_fields" in d
        assert "takeoff_template_name" in d
        assert "hide_section_markers" in d
        assert "include_sheet" in d
        assert "titleblock_name" in d

    def test_roundtrip(self) -> None:
        """from_dict(to_dict()) should produce identical config."""
        original = AssemblyViewConfig(
            include_3d=False,
            include_front_elevation=True,
            include_top_elevation=True,
            include_material_takeoff=True,
            detail_level="Coarse",
            display_style="Realistic",
            include_back_elevation=True,
            include_left_elevation=True,
            include_column_schedule=True,
            schedule_fields="Family, Cut Length",
            hide_section_markers=False,
            include_sheet=True,
            titleblock_name="E1 30x42",
        )
        roundtripped = AssemblyViewConfig.from_dict(original.to_dict())
        assert roundtripped.include_3d == original.include_3d
        assert roundtripped.include_front_elevation == original.include_front_elevation
        assert roundtripped.include_top_elevation == original.include_top_elevation
        assert roundtripped.include_material_takeoff == original.include_material_takeoff
        assert roundtripped.detail_level == original.detail_level
        assert roundtripped.display_style == original.display_style
        assert roundtripped.include_back_elevation == original.include_back_elevation
        assert roundtripped.include_left_elevation == original.include_left_elevation
        assert roundtripped.include_column_schedule == original.include_column_schedule
        assert roundtripped.schedule_fields == original.schedule_fields
        assert roundtripped.hide_section_markers == original.hide_section_markers
        assert roundtripped.include_sheet == original.include_sheet
        assert roundtripped.titleblock_name == original.titleblock_name

    def test_default_roundtrip(self) -> None:
        """Default config survives roundtrip."""
        original = AssemblyViewConfig()
        roundtripped = AssemblyViewConfig.from_dict(original.to_dict())
        assert roundtripped.to_dict() == original.to_dict()


# =============================================================================
# DISPLAY_STYLE_MAP
# =============================================================================

class TestDisplayStyleMap:
    """Tests for DISPLAY_STYLE_MAP completeness."""

    def test_has_all_seven_entries(self) -> None:
        assert len(DISPLAY_STYLE_MAP) == 7

    def test_contains_wireframe(self) -> None:
        assert "Wireframe" in DISPLAY_STYLE_MAP

    def test_contains_hidden_line(self) -> None:
        assert "HiddenLine" in DISPLAY_STYLE_MAP
        assert DISPLAY_STYLE_MAP["HiddenLine"] == "HLR"

    def test_contains_shaded(self) -> None:
        assert "Shaded" in DISPLAY_STYLE_MAP
        assert DISPLAY_STYLE_MAP["Shaded"] == "Shading"

    def test_contains_shaded_with_edges(self) -> None:
        assert "Shaded with Edges" in DISPLAY_STYLE_MAP
        assert DISPLAY_STYLE_MAP["Shaded with Edges"] == "ShadingWithEdges"

    def test_contains_consistent_colors(self) -> None:
        assert "Consistent Colors" in DISPLAY_STYLE_MAP
        assert DISPLAY_STYLE_MAP["Consistent Colors"] == "FlatColors"

    def test_contains_realistic(self) -> None:
        assert "Realistic" in DISPLAY_STYLE_MAP

    def test_contains_realistic_with_edges(self) -> None:
        assert "Realistic with Edges" in DISPLAY_STYLE_MAP
        assert DISPLAY_STYLE_MAP["Realistic with Edges"] == "RealisticWithEdges"


class TestDetailLevelMap:
    """Tests for DETAIL_LEVEL_MAP."""

    def test_has_three_entries(self) -> None:
        assert len(DETAIL_LEVEL_MAP) == 3

    def test_all_levels_present(self) -> None:
        for level in ("Coarse", "Medium", "Fine"):
            assert level in DETAIL_LEVEL_MAP


# =============================================================================
# CreatedViewInfo
# =============================================================================

class TestCreatedViewInfo:
    """Tests for CreatedViewInfo dataclass."""

    def test_basic_creation(self) -> None:
        vi = CreatedViewInfo("Front Elevation")
        assert vi.view_name == "Front Elevation"
        assert vi.view_id is None
        assert vi.view_type == "elevation"

    def test_with_all_fields(self) -> None:
        vi = CreatedViewInfo("3D Orthographic", view_id=42, view_type="3d")
        assert vi.view_name == "3D Orthographic"
        assert vi.view_id == 42
        assert vi.view_type == "3d"

    def test_schedule_type(self) -> None:
        vi = CreatedViewInfo(
            "Structural Framing Schedule", view_id=99, view_type="schedule",
        )
        assert vi.view_type == "schedule"

    def test_takeoff_type(self) -> None:
        vi = CreatedViewInfo("Material Takeoff", view_id=88, view_type="takeoff")
        assert vi.view_type == "takeoff"


# =============================================================================
# Schedule Field Parsing
# =============================================================================

class TestParseFieldNames:
    """Tests for _parse_field_names() helper."""

    def test_empty_string_returns_defaults(self) -> None:
        result = _parse_field_names("", ["A", "B"])
        assert result == ["A", "B"]

    def test_none_like_empty_returns_defaults(self) -> None:
        result = _parse_field_names("  ", ["X", "Y"])
        assert result == ["X", "Y"]

    def test_comma_separated_parsing(self) -> None:
        result = _parse_field_names("Family, Type, Cut Length", [])
        assert result == ["Family", "Type", "Cut Length"]

    def test_strips_whitespace(self) -> None:
        result = _parse_field_names("  Family ,  Type  ", [])
        assert result == ["Family", "Type"]

    def test_filters_empty_entries(self) -> None:
        result = _parse_field_names("Family,,Type,", [])
        assert result == ["Family", "Type"]

    def test_single_field(self) -> None:
        result = _parse_field_names("Volume", [])
        assert result == ["Volume"]


class TestDefaultFieldLists:
    """Tests for default field list constants."""

    def test_default_schedule_fields(self) -> None:
        assert DEFAULT_SCHEDULE_FIELDS == ["Family", "Type", "Cut Length"]

    def test_default_takeoff_fields(self) -> None:
        assert DEFAULT_TAKEOFF_FIELDS == [
            "Type", "Count", "Material: Name", "Material: Area",
        ]
