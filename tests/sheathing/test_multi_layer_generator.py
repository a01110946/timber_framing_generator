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
    MATERIAL_ALIASES,
    _get_layer_config,
    _determine_face,
    _resolve_material_key,
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


class TestResolveMaterialKey:
    """Tests for _resolve_material_key helper."""

    def test_valid_key_returned_as_is(self) -> None:
        assert _resolve_material_key("osb_7_16") == "osb_7_16"
        assert _resolve_material_key("gypsum_1_2") == "gypsum_1_2"
        assert _resolve_material_key("fiber_cement_5_16") == "fiber_cement_5_16"

    def test_display_name_resolved(self) -> None:
        """SHEATHING_MATERIALS display names should resolve."""
        assert _resolve_material_key('OSB 7/16"') == "osb_7_16"
        assert _resolve_material_key('Gypsum Board 1/2"') == "gypsum_1_2"
        assert _resolve_material_key('Fiber Cement Siding 5/16"') == "fiber_cement_5_16"

    def test_catalog_names_resolved(self) -> None:
        """Assembly catalog display names should resolve via aliases."""
        assert _resolve_material_key("Lap Siding") == "lp_smartside_7_16"
        assert _resolve_material_key("OSB 7/16") == "osb_7_16"
        assert _resolve_material_key("OSB 1/2") == "osb_1_2"
        assert _resolve_material_key("Fiber Cement Siding") == "fiber_cement_5_16"
        assert _resolve_material_key('1/2" Gypsum Board') == "gypsum_1_2"

    def test_case_insensitive(self) -> None:
        assert _resolve_material_key("lap siding") == "lp_smartside_7_16"
        assert _resolve_material_key("LAP SIDING") == "lp_smartside_7_16"
        assert _resolve_material_key("osb 7/16") == "osb_7_16"

    def test_unknown_returns_none(self) -> None:
        assert _resolve_material_key("Unknown Material XYZ") is None
        assert _resolve_material_key('2x4 SPF @ 16" OC') is None

    def test_empty_returns_none(self) -> None:
        assert _resolve_material_key("") is None
        assert _resolve_material_key(None) is None

    def test_common_aliases(self) -> None:
        assert _resolve_material_key("Drywall") == "gypsum_1_2"
        assert _resolve_material_key("Plywood") == "structural_plywood_7_16"
        assert _resolve_material_key("Tyvek") == "housewrap"


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

    def test_display_name_material_resolved(self) -> None:
        """Display names like 'Lap Siding' should resolve to valid keys."""
        layer = {"function": "finish", "side": "exterior", "material": "Lap Siding"}
        config = _get_layer_config(layer, {})
        assert config["material"] == "lp_smartside_7_16"

    def test_unknown_material_ignored(self) -> None:
        """Unresolvable material names should be ignored (keep default)."""
        layer = {"function": "substrate", "side": "exterior", "material": '2x4 SPF @ 16" OC'}
        config = _get_layer_config(layer, {})
        # Should fall back to DEFAULT_LAYER_MATERIALS for (substrate, exterior)
        assert config["material"] == "osb_7_16"

    def test_catalog_osb_material_resolved(self) -> None:
        """Assembly catalog 'OSB 7/16' should resolve correctly."""
        layer = {"function": "substrate", "side": "exterior", "material": "OSB 7/16"}
        config = _get_layer_config(layer, {})
        assert config["material"] == "osb_7_16"

    def test_catalog_gypsum_material_resolved(self) -> None:
        """Assembly catalog gypsum name should resolve."""
        layer = {"function": "finish", "side": "interior", "material": '1/2" Gypsum Board'}
        config = _get_layer_config(layer, {})
        assert config["material"] == "gypsum_1_2"


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


class TestGenerateAssemblyLayersFaceBounds:
    """Tests for per-face junction bounds."""

    def test_face_bounds_applied_to_exterior(self) -> None:
        """Exterior layers should use exterior face bounds."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            ],
        )
        result = generate_assembly_layers(
            wall_data,
            face_bounds={"exterior": (-0.5, 12.5), "interior": (0.0, 12.0)},
        )
        panels = result["layer_results"][0]["panels"]
        u_starts = [p["u_start"] for p in panels]
        assert min(u_starts) <= 0.0  # Extended by exterior bounds

    def test_face_bounds_applied_to_interior(self) -> None:
        """Interior layers should use interior face bounds."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
            ],
        )
        # Interior trimmed, exterior extended
        result = generate_assembly_layers(
            wall_data,
            face_bounds={"exterior": (-0.5, 12.5), "interior": (0.5, 11.5)},
        )
        panels = result["layer_results"][0]["panels"]
        u_starts = [p["u_start"] for p in panels]
        u_ends = [p["u_end"] for p in panels]
        # Interior panels should NOT extend before 0.5
        assert min(u_starts) >= 0.0
        # Interior panels should NOT extend past 11.5 + panel_width
        assert max(u_ends) <= 12.0

    def test_face_bounds_fallback_to_u_bounds(self) -> None:
        """When face_bounds missing for a face, falls back to u_start/u_end."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            ],
        )
        result = generate_assembly_layers(
            wall_data,
            u_start_bound=-0.5,
            u_end_bound=12.5,
            face_bounds={"interior": (0.0, 12.0)},  # No exterior entry
        )
        panels = result["layer_results"][0]["panels"]
        u_starts = [p["u_start"] for p in panels]
        assert min(u_starts) <= 0.0  # Falls back to u_start_bound=-0.5

    def test_different_bounds_per_face(self) -> None:
        """Exterior and interior layers use different bounds on same wall."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
                {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.292},
                {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
            ],
        )
        result = generate_assembly_layers(
            wall_data,
            face_bounds={
                "exterior": (-0.5, 12.5),   # Extended at both ends
                "interior": (0.0, 12.0),     # Flush with wall
            },
        )
        assert result["layers_processed"] == 2

        ext_result = result["layer_results"][0]  # OSB
        int_result = result["layer_results"][1]  # Drywall

        assert ext_result["layer_side"] == "exterior"
        assert int_result["layer_side"] == "interior"

        ext_starts = [p["u_start"] for p in ext_result["panels"]]
        int_starts = [p["u_start"] for p in int_result["panels"]]

        # Exterior extended past wall start, interior not
        assert min(ext_starts) < min(int_starts)


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


class TestGenerateAssemblyLayersCatalog:
    """Tests with assembly catalog display-name materials (the real GH scenario)."""

    def _catalog_2x4_exterior_layers(self) -> list:
        """Mimics the layers from ASSEMBLY_2X4_EXTERIOR in config/assembly.py."""
        return [
            {
                "name": "exterior_finish",
                "function": "finish",
                "side": "exterior",
                "thickness": 0.5 / 12,
                "material": "Lap Siding",
            },
            {
                "name": "structural_sheathing",
                "function": "substrate",
                "side": "exterior",
                "thickness": 0.4375 / 12,
                "material": "OSB 7/16",
            },
            {
                "name": "framing_core",
                "function": "structure",
                "side": "core",
                "thickness": 3.5 / 12,
                "material": '2x4 SPF @ 16" OC',
            },
            {
                "name": "interior_finish",
                "function": "finish",
                "side": "interior",
                "thickness": 0.5 / 12,
                "material": '1/2" Gypsum Board',
            },
        ]

    def test_catalog_assembly_produces_panels(self) -> None:
        """Catalog assemblies with display-name materials must produce panels."""
        wall_data = _make_wall_data(layers=self._catalog_2x4_exterior_layers())
        result = generate_assembly_layers(wall_data)

        # 3 panelizable: finish/ext, substrate/ext, finish/int
        assert result["layers_processed"] == 3
        assert result["total_panel_count"] > 0

        for layer_result in result["layer_results"]:
            assert layer_result["panel_count"] > 0, (
                f"Layer '{layer_result['layer_name']}' produced 0 panels"
            )

    def test_catalog_interior_assembly_produces_panels(self) -> None:
        """Interior assembly with gypsum on both sides."""
        layers = [
            {
                "name": "finish_a",
                "function": "finish",
                "side": "exterior",
                "thickness": 0.5 / 12,
                "material": '1/2" Gypsum Board',
            },
            {
                "name": "framing_core",
                "function": "structure",
                "side": "core",
                "thickness": 3.5 / 12,
                "material": '2x4 SPF @ 16" OC',
            },
            {
                "name": "finish_b",
                "function": "finish",
                "side": "interior",
                "thickness": 0.5 / 12,
                "material": '1/2" Gypsum Board',
            },
        ]
        wall_data = _make_wall_data(layers=layers)
        result = generate_assembly_layers(wall_data)
        assert result["layers_processed"] == 2
        assert result["total_panel_count"] > 0


class TestGenerateAssemblyLayersPanelIds:
    """Tests that multi-layer panels have unique, layer-aware IDs."""

    def test_different_layers_have_unique_ids(self) -> None:
        """Two exterior layers on the same face must produce distinct panel IDs."""
        wall_data = _make_wall_data(
            wall_length=8.0,
            layers=[
                {"name": "Siding", "function": "finish", "side": "exterior", "thickness": 0.026},
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
                {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
            ],
        )
        result = generate_assembly_layers(wall_data)

        all_ids = []
        for layer_result in result["layer_results"]:
            for panel in layer_result["panels"]:
                all_ids.append(panel["id"])

        # Should have no duplicates
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate panel IDs found: {[x for x in all_ids if all_ids.count(x) > 1]}"
        )

    def test_panel_id_contains_layer_name(self) -> None:
        """Panel IDs should contain the sanitized layer name."""
        wall_data = _make_wall_data(
            wall_length=4.0,
            layers=[
                {"name": "Fiber Cement Siding", "function": "finish", "side": "exterior", "thickness": 0.026},
            ],
        )
        result = generate_assembly_layers(wall_data)
        panel_id = result["layer_results"][0]["panels"][0]["id"]
        assert "fiber_cement_siding" in panel_id

    def test_full_assembly_all_ids_unique(self) -> None:
        """All panel IDs across a full 5-layer assembly must be globally unique."""
        wall_data = _make_wall_data(layers=_typical_exterior_assembly())
        result = generate_assembly_layers(wall_data)

        all_ids = []
        for layer_result in result["layer_results"]:
            for panel in layer_result["panels"]:
                all_ids.append(panel["id"])

        assert len(all_ids) > 0
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate IDs: {[x for x in all_ids if all_ids.count(x) > 1]}"
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
