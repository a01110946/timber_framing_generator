# File: tests/sheathing/test_multi_layer_generator.py

"""Tests for multi-layer panel generator.

Tests cover:
- generate_assembly_layers() with various assemblies
- Per-layer rule application and config merging
- W offset computation per layer
- Layer filtering (include_functions)
- Per-layer config overrides
- Edge cases (no assembly, empty layers, unknown functions)
- Integration with SheathingGenerator output format
"""

import pytest

from src.timber_framing_generator.sheathing.multi_layer_generator import (
    generate_assembly_layers,
    LayerPanelResult,
    PANELIZABLE_FUNCTIONS,
    DEFAULT_LAYER_MATERIALS,
    _get_layer_config,
    _determine_face,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_wall_data(
    wall_length: float = 12.0,
    wall_height: float = 8.0,
    layers: list = None,
    openings: list = None,
) -> dict:
    """Create minimal wall_data with an assembly."""
    assembly = {"layers": layers} if layers else None
    return {
        "wall_id": "test_wall",
        "wall_length": wall_length,
        "wall_height": wall_height,
        "openings": openings or [],
        "wall_assembly": assembly,
    }


def _typical_exterior_assembly() -> list:
    """5-layer exterior wall assembly."""
    return [
        {
            "name": "Fiber Cement Siding",
            "function": "finish",
            "side": "exterior",
            "thickness": 5 / 16 / 12,  # ~0.026 ft
        },
        {
            "name": "House Wrap",
            "function": "membrane",
            "side": "exterior",
            "thickness": 0.001,
        },
        {
            "name": "OSB Sheathing",
            "function": "substrate",
            "side": "exterior",
            "thickness": 7 / 16 / 12,  # ~0.036 ft
        },
        {
            "name": "2x6 Studs + Batt",
            "function": "structure",
            "side": "core",
            "thickness": 5.5 / 12,  # 0.458 ft
        },
        {
            "name": "Gypsum Board",
            "function": "finish",
            "side": "interior",
            "thickness": 0.5 / 12,  # ~0.042 ft
        },
    ]


def _insulated_assembly() -> list:
    """Assembly with continuous insulation layer."""
    return [
        {
            "name": "Rigid Foam",
            "function": "thermal",
            "side": "exterior",
            "thickness": 2.0 / 12,  # 2 inches
        },
        {
            "name": "OSB Sheathing",
            "function": "substrate",
            "side": "exterior",
            "thickness": 7 / 16 / 12,
        },
        {
            "name": "2x6 Studs",
            "function": "structure",
            "side": "core",
            "thickness": 5.5 / 12,
        },
        {
            "name": "Drywall",
            "function": "finish",
            "side": "interior",
            "thickness": 5 / 8 / 12,
        },
    ]


# =============================================================================
# LayerPanelResult Tests
# =============================================================================


class TestLayerPanelResult:
    """Tests for LayerPanelResult dataclass."""

    def test_to_dict(self) -> None:
        result = LayerPanelResult(
            layer_name="OSB",
            layer_function="substrate",
            layer_side="exterior",
            w_offset=0.25,
            panels=[{"id": "p1"}, {"id": "p2"}],
            summary={"total_panels": 2},
            rules_applied={"stagger_pattern": "running_bond"},
        )
        d = result.to_dict()
        assert d["layer_name"] == "OSB"
        assert d["panel_count"] == 2
        assert d["w_offset"] == 0.25
        assert len(d["panels"]) == 2

    def test_to_dict_no_panels(self) -> None:
        result = LayerPanelResult(
            layer_name="Membrane",
            layer_function="membrane",
            layer_side="exterior",
            w_offset=None,
            panels=[],
            summary={},
            rules_applied={},
        )
        d = result.to_dict()
        assert d["panel_count"] == 0
        assert d["w_offset"] is None


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestDetermineFace:
    """Tests for _determine_face helper."""

    def test_interior_side(self) -> None:
        assert _determine_face("interior") == "interior"

    def test_exterior_side(self) -> None:
        assert _determine_face("exterior") == "exterior"

    def test_core_side(self) -> None:
        assert _determine_face("core") == "exterior"


class TestGetLayerConfig:
    """Tests for _get_layer_config helper."""

    def test_rules_config_applied(self) -> None:
        layer = {"function": "substrate", "side": "exterior"}
        rules_config = {"stagger_offset": 2.0, "min_piece_width": 0.5}
        config = _get_layer_config(layer, rules_config)
        assert config["stagger_offset"] == 2.0
        assert config["min_piece_width"] == 0.5

    def test_default_material_applied(self) -> None:
        layer = {"function": "substrate", "side": "exterior"}
        config = _get_layer_config(layer, {})
        assert config["material"] == "osb_7_16"

    def test_layer_material_overrides_default(self) -> None:
        layer = {"function": "substrate", "side": "exterior", "material": "osb_1_2"}
        config = _get_layer_config(layer, {})
        assert config["material"] == "osb_1_2"

    def test_base_config_overrides_all(self) -> None:
        layer = {"function": "substrate", "side": "exterior"}
        rules_config = {"stagger_offset": 2.0}
        base = {"stagger_offset": 4.0, "material": "custom_mat"}
        config = _get_layer_config(layer, rules_config, base)
        assert config["stagger_offset"] == 4.0
        assert config["material"] == "custom_mat"

    def test_default_panel_size(self) -> None:
        layer = {"function": "finish", "side": "interior"}
        config = _get_layer_config(layer, {})
        assert config["panel_size"] == "4x8"


# =============================================================================
# generate_assembly_layers Tests
# =============================================================================


class TestGenerateAssemblyLayersBasic:
    """Basic tests for generate_assembly_layers."""

    def test_no_assembly_returns_empty(self) -> None:
        wall_data = {
            "wall_id": "w1",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [],
        }
        result = generate_assembly_layers(wall_data)
        assert result["total_panel_count"] == 0
        assert result["layers_processed"] == 0
        assert result["layer_results"] == []

    def test_empty_layers_returns_empty(self) -> None:
        wall_data = _make_wall_data(layers=[])
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 0

    def test_structure_layer_skipped(self) -> None:
        """Structure layers are not panelizable."""
        wall_data = _make_wall_data(layers=[
            {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.3},
        ])
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 0

    def test_membrane_layer_skipped(self) -> None:
        """Membrane layers (WRB) are not panelizable by default."""
        wall_data = _make_wall_data(layers=[
            {"name": "WRB", "function": "membrane", "side": "exterior", "thickness": 0.001},
        ])
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 0

    def test_wall_id_preserved(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        wall_data["wall_id"] = "my_wall_42"
        result = generate_assembly_layers(wall_data)
        assert result["wall_id"] == "my_wall_42"


class TestGenerateAssemblyLayersSingle:
    """Tests for single-layer assemblies."""

    def test_single_substrate_layer(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 1
        assert result["total_panel_count"] > 0

        layer_result = result["layer_results"][0]
        assert layer_result["layer_name"] == "OSB"
        assert layer_result["layer_function"] == "substrate"
        assert layer_result["layer_side"] == "exterior"
        assert len(layer_result["panels"]) > 0

    def test_single_interior_finish(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
        ])
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 1

        layer_result = result["layer_results"][0]
        assert layer_result["layer_name"] == "Drywall"
        assert layer_result["layer_side"] == "interior"

    def test_single_thermal_layer(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "Rigid Foam", "function": "thermal", "side": "exterior", "thickness": 0.167},
        ])
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 1

        layer_result = result["layer_results"][0]
        assert layer_result["layer_name"] == "Rigid Foam"
        assert layer_result["layer_function"] == "thermal"


class TestGenerateAssemblyLayersMulti:
    """Tests for multi-layer assemblies."""

    def test_typical_exterior_assembly(self) -> None:
        wall_data = _make_wall_data(layers=_typical_exterior_assembly())
        result = generate_assembly_layers(wall_data)

        # Should process: finish/ext, substrate/ext, finish/int = 3 panelizable
        # Membrane and structure are skipped
        assert result["layers_processed"] == 3
        assert result["total_panel_count"] > 0

        names = [r["layer_name"] for r in result["layer_results"]]
        assert "Fiber Cement Siding" in names
        assert "OSB Sheathing" in names
        assert "Gypsum Board" in names
        assert "House Wrap" not in names
        assert "2x6 Studs + Batt" not in names

    def test_insulated_assembly(self) -> None:
        wall_data = _make_wall_data(layers=_insulated_assembly())
        result = generate_assembly_layers(wall_data)

        # Should process: thermal/ext, substrate/ext, finish/int = 3
        assert result["layers_processed"] == 3

        names = [r["layer_name"] for r in result["layer_results"]]
        assert "Rigid Foam" in names
        assert "OSB Sheathing" in names
        assert "Drywall" in names

    def test_each_layer_has_panels(self) -> None:
        wall_data = _make_wall_data(layers=_typical_exterior_assembly())
        result = generate_assembly_layers(wall_data)

        for layer_result in result["layer_results"]:
            assert layer_result["panel_count"] > 0, (
                f"Layer {layer_result['layer_name']} has no panels"
            )


class TestGenerateAssemblyLayersRules:
    """Tests that layer rules are correctly applied."""

    def test_substrate_rules_applied(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        result = generate_assembly_layers(wall_data)
        rules = result["layer_results"][0]["rules_applied"]
        assert rules["stagger_pattern"] == "running_bond"
        assert rules["stagger_offset"] == 2.0
        assert rules["min_piece_width"] == 0.5

    def test_interior_finish_rules_applied(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
        ])
        result = generate_assembly_layers(wall_data)
        rules = result["layer_results"][0]["rules_applied"]
        assert rules["stagger_pattern"] == "running_bond"
        assert rules["min_piece_width"] == pytest.approx(0.667, abs=0.001)

    def test_thermal_rules_applied(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "CI", "function": "thermal", "side": "exterior", "thickness": 0.167},
        ])
        result = generate_assembly_layers(wall_data)
        rules = result["layer_results"][0]["rules_applied"]
        assert rules["orientation"] == "any"
        assert rules["min_piece_width"] == 1.0


class TestGenerateAssemblyLayersFiltering:
    """Tests for layer filtering."""

    def test_include_only_substrate(self) -> None:
        wall_data = _make_wall_data(layers=_typical_exterior_assembly())
        result = generate_assembly_layers(
            wall_data, include_functions=["substrate"]
        )
        assert result["layers_processed"] == 1
        assert result["layer_results"][0]["layer_name"] == "OSB Sheathing"

    def test_include_only_finish(self) -> None:
        wall_data = _make_wall_data(layers=_typical_exterior_assembly())
        result = generate_assembly_layers(
            wall_data, include_functions=["finish"]
        )
        assert result["layers_processed"] == 2
        names = [r["layer_name"] for r in result["layer_results"]]
        assert "Fiber Cement Siding" in names
        assert "Gypsum Board" in names

    def test_include_thermal(self) -> None:
        wall_data = _make_wall_data(layers=_insulated_assembly())
        result = generate_assembly_layers(
            wall_data, include_functions=["thermal"]
        )
        assert result["layers_processed"] == 1
        assert result["layer_results"][0]["layer_name"] == "Rigid Foam"

    def test_include_membrane_explicitly(self) -> None:
        """Membrane excluded by default but can be included."""
        wall_data = _make_wall_data(layers=[
            {"name": "WRB", "function": "membrane", "side": "exterior", "thickness": 0.001},
        ])
        result = generate_assembly_layers(
            wall_data, include_functions=["membrane"]
        )
        assert result["layers_processed"] == 1


class TestGenerateAssemblyLayersConfig:
    """Tests for per-layer config overrides."""

    def test_global_config_applied(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        result = generate_assembly_layers(
            wall_data, config={"panel_size": "4x10"}
        )
        assert result["layers_processed"] == 1
        assert result["total_panel_count"] > 0

    def test_per_layer_config_override(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
        ])
        result = generate_assembly_layers(
            wall_data,
            layer_configs={"OSB": {"panel_size": "4x10"}},
        )
        assert result["layers_processed"] == 2

    def test_u_bounds_applied(self) -> None:
        """Junction bounds should limit panel extent."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            ],
        )
        result = generate_assembly_layers(
            wall_data, u_start_bound=-0.5, u_end_bound=12.5
        )
        panels = result["layer_results"][0]["panels"]
        # Verify panels extend beyond wall boundaries
        u_starts = [p["u_start"] for p in panels]
        u_ends = [p["u_end"] for p in panels]
        assert min(u_starts) <= 0.0  # Extends before wall start
        assert max(u_ends) >= 12.0  # Extends to wall end


class TestGenerateAssemblyLayersWOffset:
    """Tests for W offset computation."""

    def test_single_layer_has_w_offset(self) -> None:
        """W offset should be computed for assembly layers."""
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
        ])
        result = generate_assembly_layers(wall_data)
        # OSB is panelizable, studs are not
        assert result["layers_processed"] == 1
        layer = result["layer_results"][0]
        # W offset should be computed (not None) when assembly has layers
        # For a single substrate layer next to core, w_offset = core_half
        assert layer["w_offset"] is not None

    def test_multi_layer_different_offsets(self) -> None:
        """Different layers should have different W offsets."""
        wall_data = _make_wall_data(layers=[
            {"name": "Siding", "function": "finish", "side": "exterior", "thickness": 0.026},
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
        ])
        result = generate_assembly_layers(wall_data)
        offsets = {
            r["layer_name"]: r["w_offset"]
            for r in result["layer_results"]
            if r["w_offset"] is not None
        }
        # Exterior layers should have positive W, interior negative
        if "Siding" in offsets and "OSB" in offsets:
            assert offsets["Siding"] > offsets["OSB"]  # Siding is further out
        if "OSB" in offsets and "Drywall" in offsets:
            assert offsets["OSB"] > offsets["Drywall"]  # OSB exterior > drywall interior


class TestGenerateAssemblyLayersOpenings:
    """Tests for assemblies with openings."""

    def test_openings_create_cutouts(self) -> None:
        wall_data = _make_wall_data(
            wall_length=12.0,
            wall_height=8.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            ],
            openings=[
                {
                    "u_start": 4.0,
                    "width": 3.0,
                    "v_start": 2.0,
                    "height": 4.0,
                    "opening_type": "window",
                },
            ],
        )
        result = generate_assembly_layers(wall_data)
        panels = result["layer_results"][0]["panels"]

        # Some panels should have cutouts
        panels_with_cutouts = [
            p for p in panels if len(p.get("cutouts", [])) > 0
        ]
        assert len(panels_with_cutouts) > 0

    def test_all_layers_get_same_openings(self) -> None:
        """Openings should be cut from every panelizable layer."""
        wall_data = _make_wall_data(
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
                {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
                {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
            ],
            openings=[
                {
                    "u_start": 4.0,
                    "width": 3.0,
                    "v_start": 2.0,
                    "height": 4.0,
                    "opening_type": "window",
                },
            ],
        )
        result = generate_assembly_layers(wall_data)
        for layer_result in result["layer_results"]:
            panels = layer_result["panels"]
            has_cutout = any(
                len(p.get("cutouts", [])) > 0 for p in panels
            )
            assert has_cutout, (
                f"Layer {layer_result['layer_name']} missing opening cutout"
            )


class TestGenerateAssemblyLayersSummary:
    """Tests for layer summaries."""

    def test_summary_per_layer(self) -> None:
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        result = generate_assembly_layers(wall_data)
        summary = result["layer_results"][0]["summary"]
        assert "total_panels" in summary
        assert "gross_area_sqft" in summary
        assert summary["total_panels"] > 0

    def test_total_count_matches_sum(self) -> None:
        wall_data = _make_wall_data(layers=_typical_exterior_assembly())
        result = generate_assembly_layers(wall_data)
        per_layer_sum = sum(r["panel_count"] for r in result["layer_results"])
        assert result["total_panel_count"] == per_layer_sum
