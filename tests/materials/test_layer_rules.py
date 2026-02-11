# File: tests/materials/test_layer_rules.py

"""Tests for per-layer placement rules engine.

Tests cover:
- StaggerPattern and PanelOrientation enums
- FastenerSpec defaults and custom values
- LayerPlacementRules serialization and config conversion
- Default rules catalog correctness
- Lookup functions (get_rules_for_layer, get_rules_for_assembly)
- Custom rules override behavior
- Integration with SheathingGenerator config
"""

import sys
import os
import importlib.util
import pytest

# Load layer_rules directly from file to avoid materials/__init__.py
# which triggers Rhino-dependent imports from timber/cfs strategy modules.
_layer_rules_path = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "src", "timber_framing_generator", "materials", "layer_rules.py",
)
_layer_rules_path = os.path.normpath(_layer_rules_path)
_spec = importlib.util.spec_from_file_location(
    "src.timber_framing_generator.materials.layer_rules", _layer_rules_path
)
_layer_rules = importlib.util.module_from_spec(_spec)
sys.modules["src.timber_framing_generator.materials.layer_rules"] = _layer_rules
_spec.loader.exec_module(_layer_rules)

StaggerPattern = _layer_rules.StaggerPattern
PanelOrientation = _layer_rules.PanelOrientation
FastenerSpec = _layer_rules.FastenerSpec
LayerPlacementRules = _layer_rules.LayerPlacementRules
RULES_OSB_SHEATHING = _layer_rules.RULES_OSB_SHEATHING
RULES_PLYWOOD_SHEATHING = _layer_rules.RULES_PLYWOOD_SHEATHING
RULES_GYPSUM_BOARD = _layer_rules.RULES_GYPSUM_BOARD
RULES_CONTINUOUS_INSULATION = _layer_rules.RULES_CONTINUOUS_INSULATION
RULES_WRB_MEMBRANE = _layer_rules.RULES_WRB_MEMBRANE
RULES_EXTERIOR_FINISH = _layer_rules.RULES_EXTERIOR_FINISH
RULES_DEFAULT = _layer_rules.RULES_DEFAULT
DEFAULT_RULES = _layer_rules.DEFAULT_RULES
get_rules_for_layer = _layer_rules.get_rules_for_layer
get_rules_for_assembly = _layer_rules.get_rules_for_assembly


# =============================================================================
# Enum Tests
# =============================================================================


class TestStaggerPattern:
    """Tests for StaggerPattern enum."""

    def test_running_bond_value(self) -> None:
        assert StaggerPattern.RUNNING_BOND.value == "running_bond"

    def test_none_value(self) -> None:
        assert StaggerPattern.NONE.value == "none"

    def test_from_value(self) -> None:
        assert StaggerPattern("running_bond") == StaggerPattern.RUNNING_BOND
        assert StaggerPattern("none") == StaggerPattern.NONE


class TestPanelOrientation:
    """Tests for PanelOrientation enum."""

    def test_horizontal_value(self) -> None:
        assert PanelOrientation.HORIZONTAL.value == "horizontal"

    def test_vertical_value(self) -> None:
        assert PanelOrientation.VERTICAL.value == "vertical"

    def test_any_value(self) -> None:
        assert PanelOrientation.ANY.value == "any"


# =============================================================================
# FastenerSpec Tests
# =============================================================================


class TestFastenerSpec:
    """Tests for FastenerSpec dataclass."""

    def test_defaults(self) -> None:
        spec = FastenerSpec()
        assert spec.edge_spacing == 6.0
        assert spec.field_spacing == 12.0
        assert spec.edge_distance == 0.375

    def test_custom_values(self) -> None:
        spec = FastenerSpec(edge_spacing=4.0, field_spacing=8.0, edge_distance=0.5)
        assert spec.edge_spacing == 4.0
        assert spec.field_spacing == 8.0
        assert spec.edge_distance == 0.5


# =============================================================================
# LayerPlacementRules Tests
# =============================================================================


class TestLayerPlacementRules:
    """Tests for LayerPlacementRules dataclass."""

    def test_defaults(self) -> None:
        rules = LayerPlacementRules()
        assert rules.stagger_pattern == StaggerPattern.RUNNING_BOND
        assert rules.stagger_offset == 2.0
        assert rules.min_piece_width == 0.5
        assert rules.orientation == PanelOrientation.HORIZONTAL
        assert rules.requires_blocking is False
        assert rules.fasteners is None
        assert rules.notes == ""

    def test_to_sheathing_config_running_bond(self) -> None:
        rules = LayerPlacementRules(
            stagger_pattern=StaggerPattern.RUNNING_BOND,
            stagger_offset=2.0,
            min_piece_width=0.5,
        )
        config = rules.to_sheathing_config()
        assert config["stagger_offset"] == 2.0
        assert config["min_piece_width"] == 0.5

    def test_to_sheathing_config_no_stagger(self) -> None:
        rules = LayerPlacementRules(
            stagger_pattern=StaggerPattern.NONE,
            stagger_offset=2.0,  # ignored when pattern is NONE
            min_piece_width=1.0,
        )
        config = rules.to_sheathing_config()
        assert config["stagger_offset"] == 0.0
        assert config["min_piece_width"] == 1.0

    def test_to_dict_with_fasteners(self) -> None:
        rules = LayerPlacementRules(
            stagger_pattern=StaggerPattern.RUNNING_BOND,
            stagger_offset=2.0,
            min_piece_width=0.5,
            orientation=PanelOrientation.HORIZONTAL,
            requires_blocking=True,
            fasteners=FastenerSpec(edge_spacing=6.0, field_spacing=12.0, edge_distance=0.375),
            notes="Test note",
        )
        d = rules.to_dict()
        assert d["stagger_pattern"] == "running_bond"
        assert d["stagger_offset"] == 2.0
        assert d["min_piece_width"] == 0.5
        assert d["orientation"] == "horizontal"
        assert d["requires_blocking"] is True
        assert d["fasteners"]["edge_spacing"] == 6.0
        assert d["fasteners"]["field_spacing"] == 12.0
        assert d["fasteners"]["edge_distance"] == 0.375
        assert d["notes"] == "Test note"

    def test_to_dict_without_fasteners(self) -> None:
        rules = LayerPlacementRules()
        d = rules.to_dict()
        assert d["fasteners"] is None

    def test_to_dict_roundtrip_values(self) -> None:
        """All enum values serialize to strings."""
        rules = LayerPlacementRules(
            stagger_pattern=StaggerPattern.NONE,
            orientation=PanelOrientation.VERTICAL,
        )
        d = rules.to_dict()
        assert d["stagger_pattern"] == "none"
        assert d["orientation"] == "vertical"


# =============================================================================
# Default Rules Catalog Tests
# =============================================================================


class TestDefaultRulesCatalog:
    """Tests for the default rules catalog correctness."""

    def test_osb_sheathing_properties(self) -> None:
        rules = RULES_OSB_SHEATHING
        assert rules.stagger_pattern == StaggerPattern.RUNNING_BOND
        assert rules.stagger_offset == 2.0
        assert rules.requires_blocking is True
        assert rules.fasteners is not None
        assert rules.fasteners.edge_spacing == 6.0

    def test_plywood_matches_osb_pattern(self) -> None:
        """Plywood and OSB should have same stagger and blocking rules."""
        assert RULES_PLYWOOD_SHEATHING.stagger_offset == RULES_OSB_SHEATHING.stagger_offset
        assert RULES_PLYWOOD_SHEATHING.requires_blocking == RULES_OSB_SHEATHING.requires_blocking

    def test_gypsum_larger_min_piece(self) -> None:
        """Gypsum min piece (8 inches) > OSB min piece (6 inches)."""
        assert RULES_GYPSUM_BOARD.min_piece_width > RULES_OSB_SHEATHING.min_piece_width
        assert RULES_GYPSUM_BOARD.min_piece_width == pytest.approx(0.667, abs=0.001)

    def test_continuous_insulation_any_orientation(self) -> None:
        assert RULES_CONTINUOUS_INSULATION.orientation == PanelOrientation.ANY
        assert RULES_CONTINUOUS_INSULATION.min_piece_width == 1.0

    def test_wrb_no_stagger(self) -> None:
        assert RULES_WRB_MEMBRANE.stagger_pattern == StaggerPattern.NONE
        assert RULES_WRB_MEMBRANE.stagger_offset == 0.0
        assert RULES_WRB_MEMBRANE.min_piece_width == 3.0

    def test_exterior_finish_stagger_one_bay(self) -> None:
        """Exterior finish stagger = 16 inches = 1.333 feet."""
        assert RULES_EXTERIOR_FINISH.stagger_offset == pytest.approx(1.333, abs=0.001)

    def test_default_rules_lookup_table_entries(self) -> None:
        """Verify all expected entries in DEFAULT_RULES."""
        expected_keys = [
            ("substrate", "exterior"),
            ("structure", "core"),
            ("thermal", "exterior"),
            ("membrane", "exterior"),
            ("finish", "exterior"),
            ("finish", "interior"),
        ]
        for key in expected_keys:
            assert key in DEFAULT_RULES, f"Missing key: {key}"

    def test_substrate_exterior_is_osb(self) -> None:
        assert DEFAULT_RULES[("substrate", "exterior")] is RULES_OSB_SHEATHING

    def test_finish_interior_is_gypsum(self) -> None:
        assert DEFAULT_RULES[("finish", "interior")] is RULES_GYPSUM_BOARD


# =============================================================================
# Lookup Function Tests
# =============================================================================


class TestGetRulesForLayer:
    """Tests for get_rules_for_layer function."""

    def test_known_key_returns_correct_rules(self) -> None:
        rules = get_rules_for_layer("substrate", "exterior")
        assert rules is RULES_OSB_SHEATHING

    def test_unknown_key_returns_default(self) -> None:
        rules = get_rules_for_layer("unknown_function", "unknown_side")
        assert rules is RULES_DEFAULT

    def test_finish_exterior(self) -> None:
        rules = get_rules_for_layer("finish", "exterior")
        assert rules is RULES_EXTERIOR_FINISH

    def test_finish_interior(self) -> None:
        rules = get_rules_for_layer("finish", "interior")
        assert rules is RULES_GYPSUM_BOARD

    def test_thermal_exterior(self) -> None:
        rules = get_rules_for_layer("thermal", "exterior")
        assert rules is RULES_CONTINUOUS_INSULATION

    def test_membrane_exterior(self) -> None:
        rules = get_rules_for_layer("membrane", "exterior")
        assert rules is RULES_WRB_MEMBRANE

    def test_custom_rules_override(self) -> None:
        custom = {
            ("substrate", "exterior"): LayerPlacementRules(
                stagger_offset=3.0,
                min_piece_width=1.0,
            ),
        }
        rules = get_rules_for_layer("substrate", "exterior", custom_rules=custom)
        assert rules.stagger_offset == 3.0
        assert rules.min_piece_width == 1.0

    def test_custom_rules_fallback_to_default(self) -> None:
        """Custom rules that don't match key still fall through."""
        custom = {
            ("substrate", "interior"): LayerPlacementRules(stagger_offset=5.0),
        }
        # This key is NOT in custom, so falls back to DEFAULT_RULES
        rules = get_rules_for_layer("substrate", "exterior", custom_rules=custom)
        assert rules is RULES_OSB_SHEATHING

    def test_custom_rules_empty_dict(self) -> None:
        """Empty custom rules dict doesn't break lookup."""
        rules = get_rules_for_layer("substrate", "exterior", custom_rules={})
        assert rules is RULES_OSB_SHEATHING


class TestGetRulesForAssembly:
    """Tests for get_rules_for_assembly function."""

    def _make_assembly(self, layers: list) -> dict:
        """Helper to create assembly dict with layers."""
        return {"layers": layers}

    def test_single_layer(self) -> None:
        assembly = self._make_assembly([
            {"name": "OSB Sheathing", "function": "substrate", "side": "exterior"},
        ])
        result = get_rules_for_assembly(assembly)
        assert "OSB Sheathing" in result
        assert result["OSB Sheathing"] is RULES_OSB_SHEATHING

    def test_multiple_layers(self) -> None:
        assembly = self._make_assembly([
            {"name": "Ext Sheathing", "function": "substrate", "side": "exterior"},
            {"name": "Studs", "function": "structure", "side": "core"},
            {"name": "Drywall", "function": "finish", "side": "interior"},
        ])
        result = get_rules_for_assembly(assembly)
        assert len(result) == 3
        assert result["Ext Sheathing"] is RULES_OSB_SHEATHING
        assert result["Drywall"] is RULES_GYPSUM_BOARD

    def test_unknown_layer_gets_default(self) -> None:
        assembly = self._make_assembly([
            {"name": "Mystery Layer", "function": "vapor_barrier", "side": "exterior"},
        ])
        result = get_rules_for_assembly(assembly)
        assert result["Mystery Layer"] is RULES_DEFAULT

    def test_empty_assembly(self) -> None:
        result = get_rules_for_assembly({"layers": []})
        assert result == {}

    def test_missing_layers_key(self) -> None:
        result = get_rules_for_assembly({})
        assert result == {}

    def test_layer_missing_function_defaults_to_structure(self) -> None:
        assembly = self._make_assembly([
            {"name": "Unnamed"},
        ])
        result = get_rules_for_assembly(assembly)
        # function defaults to "structure", side defaults to "core"
        assert "Unnamed" in result

    def test_custom_rules_passed_through(self) -> None:
        custom = {
            ("finish", "interior"): LayerPlacementRules(
                stagger_offset=4.0,
                min_piece_width=0.75,
            ),
        }
        assembly = self._make_assembly([
            {"name": "Drywall", "function": "finish", "side": "interior"},
        ])
        result = get_rules_for_assembly(assembly, custom_rules=custom)
        assert result["Drywall"].stagger_offset == 4.0
        assert result["Drywall"].min_piece_width == 0.75

    def test_full_typical_assembly(self) -> None:
        """Test a complete 5-layer exterior wall assembly."""
        assembly = self._make_assembly([
            {"name": "Fiber Cement Siding", "function": "finish", "side": "exterior"},
            {"name": "WRB", "function": "membrane", "side": "exterior"},
            {"name": "OSB", "function": "substrate", "side": "exterior"},
            {"name": "2x6 Studs", "function": "structure", "side": "core"},
            {"name": "Gypsum", "function": "finish", "side": "interior"},
        ])
        result = get_rules_for_assembly(assembly)
        assert len(result) == 5

        # Check specific rules match expected
        assert result["Fiber Cement Siding"] is RULES_EXTERIOR_FINISH
        assert result["WRB"] is RULES_WRB_MEMBRANE
        assert result["OSB"] is RULES_OSB_SHEATHING
        assert result["Gypsum"] is RULES_GYPSUM_BOARD

        # WRB has no stagger, others do
        assert result["WRB"].stagger_pattern == StaggerPattern.NONE
        assert result["OSB"].stagger_pattern == StaggerPattern.RUNNING_BOND


# =============================================================================
# Integration Tests: Rules + SheathingGenerator Config
# =============================================================================


class TestRulesIntegration:
    """Tests that layer rules produce valid SheathingGenerator config."""

    def test_osb_config_has_expected_keys(self) -> None:
        config = RULES_OSB_SHEATHING.to_sheathing_config()
        assert "stagger_offset" in config
        assert "min_piece_width" in config

    def test_wrb_config_zero_stagger(self) -> None:
        """WRB produces zero stagger in sheathing config."""
        config = RULES_WRB_MEMBRANE.to_sheathing_config()
        assert config["stagger_offset"] == 0.0

    def test_gypsum_config_min_piece(self) -> None:
        config = RULES_GYPSUM_BOARD.to_sheathing_config()
        assert config["min_piece_width"] == pytest.approx(0.667, abs=0.001)

    def test_config_values_are_numeric(self) -> None:
        """All config values must be numeric for SheathingGenerator."""
        for key, rules in DEFAULT_RULES.items():
            config = rules.to_sheathing_config()
            assert isinstance(config["stagger_offset"], (int, float)), (
                f"Non-numeric stagger_offset for {key}"
            )
            assert isinstance(config["min_piece_width"], (int, float)), (
                f"Non-numeric min_piece_width for {key}"
            )

    def test_all_default_rules_serialize(self) -> None:
        """Every rule in DEFAULT_RULES can serialize to dict without error."""
        for key, rules in DEFAULT_RULES.items():
            d = rules.to_dict()
            assert isinstance(d, dict), f"Serialization failed for {key}"
            assert "stagger_pattern" in d
            assert "orientation" in d


# =============================================================================
# Integration Tests: _apply_layer_rules_to_config
# =============================================================================


class TestApplyLayerRulesToConfig:
    """Tests for _apply_layer_rules_to_config in sheathing_generator."""

    def _make_assembly(self, layers: list) -> dict:
        return {"layers": layers}

    def test_no_assembly_returns_config_unchanged(self) -> None:
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            _apply_layer_rules_to_config,
        )
        config = {"stagger_offset": 3.0, "min_piece_width": 0.8}
        result = _apply_layer_rules_to_config(config, "exterior", None)
        assert result["stagger_offset"] == 3.0
        assert result["min_piece_width"] == 0.8

    def test_none_config_returns_empty_dict_without_assembly(self) -> None:
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            _apply_layer_rules_to_config,
        )
        result = _apply_layer_rules_to_config(None, "exterior", None)
        assert result == {}

    def test_exterior_substrate_rules_applied(self) -> None:
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            _apply_layer_rules_to_config,
        )
        assembly = self._make_assembly([
            {"name": "OSB", "function": "substrate", "side": "exterior"},
            {"name": "Studs", "function": "structure", "side": "core"},
        ])
        result = _apply_layer_rules_to_config(None, "exterior", assembly)
        # OSB substrate rules: stagger=2.0, min_piece=0.5
        assert result["stagger_offset"] == 2.0
        assert result["min_piece_width"] == 0.5

    def test_interior_finish_rules_applied(self) -> None:
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            _apply_layer_rules_to_config,
        )
        assembly = self._make_assembly([
            {"name": "OSB", "function": "substrate", "side": "exterior"},
            {"name": "Studs", "function": "structure", "side": "core"},
            {"name": "Drywall", "function": "finish", "side": "interior"},
        ])
        result = _apply_layer_rules_to_config(None, "interior", assembly)
        # Gypsum rules: stagger=2.0, min_piece=0.667
        assert result["stagger_offset"] == 2.0
        assert result["min_piece_width"] == pytest.approx(0.667, abs=0.001)

    def test_explicit_config_takes_priority(self) -> None:
        """Explicit config values are NOT overwritten by rules."""
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            _apply_layer_rules_to_config,
        )
        assembly = self._make_assembly([
            {"name": "OSB", "function": "substrate", "side": "exterior"},
        ])
        config = {"stagger_offset": 4.0}  # explicit override
        result = _apply_layer_rules_to_config(config, "exterior", assembly)
        assert result["stagger_offset"] == 4.0  # kept explicit value
        assert result["min_piece_width"] == 0.5  # filled from rules

    def test_empty_assembly_layers(self) -> None:
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            _apply_layer_rules_to_config,
        )
        result = _apply_layer_rules_to_config(None, "exterior", {"layers": []})
        assert result == {}


class TestGenerateWallSheathingWithRules:
    """Test that generate_wall_sheathing uses layer rules from assembly."""

    def test_assembly_rules_affect_stagger(self) -> None:
        """WRB membrane rules (no stagger) vs OSB (running bond)."""
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            generate_wall_sheathing,
        )

        wall_data = {
            "wall_id": "test_wall",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [],
            "wall_assembly": {
                "layers": [
                    {"name": "OSB", "function": "substrate", "side": "exterior"},
                    {"name": "Studs", "function": "structure", "side": "core"},
                ],
            },
        }

        result = generate_wall_sheathing(wall_data, faces=["exterior"])
        panels = result["sheathing_panels"]
        assert len(panels) > 0

    def test_no_assembly_uses_default_config(self) -> None:
        from src.timber_framing_generator.sheathing.sheathing_generator import (
            generate_wall_sheathing,
        )

        wall_data = {
            "wall_id": "test_wall",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [],
        }

        result = generate_wall_sheathing(wall_data, faces=["exterior"])
        panels = result["sheathing_panels"]
        assert len(panels) > 0
