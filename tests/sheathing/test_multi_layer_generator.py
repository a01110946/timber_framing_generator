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
    extract_max_framing_depth,
    LayerPanelResult,
    PANELIZABLE_FUNCTIONS,
    DEFAULT_LAYER_MATERIALS,
    MATERIAL_ALIASES,
    _get_layer_config,
    _determine_face,
    _resolve_material_key,
    _infer_framing_depth,
    _compute_fallback_w_offsets,
)
from src.timber_framing_generator.sheathing.sheathing_geometry import SHEATHING_GAP


# =============================================================================
# Helpers
# =============================================================================


def _make_wall_data(
    wall_length: float = 12.0,
    wall_height: float = 8.0,
    layers: list = None,
    openings: list = None,
    wall_thickness: float = None,
) -> dict:
    """Create minimal wall_data with an assembly."""
    assembly = {"layers": layers} if layers else None
    data = {
        "wall_id": "test_wall",
        "wall_length": wall_length,
        "wall_height": wall_height,
        "openings": openings or [],
        "wall_assembly": assembly,
    }
    if wall_thickness is not None:
        data["wall_thickness"] = wall_thickness
    return data


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
        assert _determine_face("core") == "core"


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

    def test_face_bounds_extension_passes_through(self) -> None:
        """Extension bounds pass through to panel layout.

        Junction "extend" adjustments push bounds past wall ends.
        The sheathing generator uses these extended bounds so that
        panels cover the corner intersection zone.
        """
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
        u_ends = [p["u_end"] for p in panels]
        # Extensions pass through — first panel starts before 0,
        # last panel ends past wall length (correct for corner wrapping)
        assert min(u_starts) < 0.0
        assert max(u_ends) > 12.0

    def test_face_bounds_trim_preserved(self) -> None:
        """Trim adjustments pull panels back from wall ends."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
            ],
        )
        result = generate_assembly_layers(
            wall_data,
            face_bounds={"exterior": (-0.5, 12.5), "interior": (0.5, 11.5)},
        )
        panels = result["layer_results"][0]["panels"]
        u_starts = [p["u_start"] for p in panels]
        u_ends = [p["u_end"] for p in panels]
        # Interior trims are preserved
        assert min(u_starts) >= 0.5 - 0.01
        assert max(u_ends) <= 11.5 + 0.01

    def test_face_bounds_fallback_to_u_bounds(self) -> None:
        """When face_bounds missing for a face, falls back to u_start/u_end."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            ],
        )
        # Fallback u_start_bound passes through (no clamping)
        result = generate_assembly_layers(
            wall_data,
            u_start_bound=-0.5,
            u_end_bound=12.5,
            face_bounds={"interior": (0.0, 12.0)},  # No exterior entry
        )
        panels = result["layer_results"][0]["panels"]
        u_starts = [p["u_start"] for p in panels]
        # Extension passes through — panels start before 0
        assert min(u_starts) < 0.0

    def test_different_bounds_per_face(self) -> None:
        """Exterior and interior layers use different bounds on same wall.

        Exterior extends while interior trims.
        """
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
                "exterior": (-0.5, 12.5),   # Extended (passes through)
                "interior": (0.5, 11.5),     # Trimmed
            },
        )
        assert result["layers_processed"] == 2

        ext_result = result["layer_results"][0]  # OSB
        int_result = result["layer_results"][1]  # Drywall

        assert ext_result["layer_side"] == "exterior"
        assert int_result["layer_side"] == "interior"

        ext_starts = [p["u_start"] for p in ext_result["panels"]]
        int_starts = [p["u_start"] for p in int_result["panels"]]

        # Exterior extended (starts before 0.0); interior trimmed (starts at 0.5)
        assert min(ext_starts) < min(int_starts)

    def test_core_bounds_trim_separate_from_exterior(self) -> None:
        """Core layers use their own trim bounds, not exterior bounds."""
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
                {"name": "Rigid Foam", "function": "thermal", "side": "core", "thickness": 0.083},
                {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
            ],
        )
        # Extensions pass through; trims are preserved per-face
        result = generate_assembly_layers(
            wall_data,
            face_bounds={
                "exterior": (-0.5, 12.5),     # Extended
                "core": (0.0, 12.0),           # Flush
                "interior": (0.2, 11.8),       # Trimmed
            },
        )
        assert result["layers_processed"] == 3

        ext_result = result["layer_results"][0]   # OSB (exterior)
        core_result = result["layer_results"][1]   # Rigid Foam (core)
        int_result = result["layer_results"][2]    # Drywall (interior)

        int_starts = [p["u_start"] for p in int_result["panels"]]

        # Interior is trimmed — starts after 0.0
        assert min(int_starts) >= 0.2 - 0.01

    def test_per_layer_name_bounds_override_face(self) -> None:
        """Per-layer-name bounds take priority over aggregate face bounds.

        When face_bounds has both 'OSB' (individual) and 'exterior'
        (aggregate), the OSB layer should use its own bounds.
        """
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
                "exterior": (0.0, 12.0),  # aggregate (should be fallback)
                "OSB": (0.3, 11.7),       # individual (should be used for OSB)
                "interior": (0.0, 12.0),
            },
        )
        osb_result = result["layer_results"][0]
        assert osb_result["layer_name"] == "OSB"
        osb_starts = [p["u_start"] for p in osb_result["panels"]]
        # OSB should use its individual bounds (0.3 start)
        assert min(osb_starts) >= 0.3 - 0.01

    def test_per_layer_name_different_amounts(self) -> None:
        """Two exterior layers with different per-layer bounds.

        Mimics the per-layer cumulative adjustment pattern where each
        exterior layer has a different trim amount.
        """
        wall_data = _make_wall_data(
            wall_length=12.0,
            layers=[
                {"name": "Siding", "function": "finish", "side": "exterior", "thickness": 0.036},
                {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
                {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.292},
                {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
            ],
        )
        result = generate_assembly_layers(
            wall_data,
            face_bounds={
                "exterior": (0.0, 12.0),       # fallback
                "OSB": (0.0, 11.5),            # OSB trims by 0.5
                "Siding": (0.0, 11.0),         # Siding trims by 1.0 (more)
                "Drywall": (0.0, 11.2),        # Drywall has own trim
                "interior": (0.0, 12.0),       # fallback
            },
        )
        # OSB should have more panels than Siding (Siding trims more)
        osb_ends = [p["u_end"] for p in result["layer_results"][1]["panels"]]
        siding_ends = [p["u_end"] for p in result["layer_results"][0]["panels"]]
        # Siding trims more → shorter layout → lower max u_end
        assert max(siding_ends) <= max(osb_ends) + 0.01


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


class TestGenerateAssemblyLayersMetadata:
    """Tests for assembly resolution metadata passthrough."""

    def test_metadata_passed_through(self) -> None:
        """Assembly resolver metadata should appear in output."""
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        # Simulate enrichment by resolve_all_walls
        wall_data["assembly_source"] = "catalog"
        wall_data["assembly_confidence"] = 0.8
        wall_data["assembly_notes"] = "Matched by keywords"
        wall_data["assembly_name"] = "2x4_exterior"
        wall_data["wall_type"] = "Basic Wall - 2x4 Exterior"

        result = generate_assembly_layers(wall_data)
        assert result["assembly_source"] == "catalog"
        assert result["assembly_confidence"] == 0.8
        assert result["assembly_name"] == "2x4_exterior"
        assert result["wall_type"] == "Basic Wall - 2x4 Exterior"

    def test_no_metadata_when_not_enriched(self) -> None:
        """Without resolver enrichment, metadata keys should be absent."""
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ])
        result = generate_assembly_layers(wall_data)
        assert "assembly_source" not in result
        assert "assembly_confidence" not in result

    def test_metadata_on_empty_assembly(self) -> None:
        """Metadata should appear even when no assembly produces panels."""
        wall_data = {
            "wall_id": "w1",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [],
            "assembly_source": "skipped",
            "assembly_confidence": 0.0,
        }
        result = generate_assembly_layers(wall_data)
        assert result["assembly_source"] == "skipped"
        assert result["total_panel_count"] == 0


class TestPanelLayerWOffset:
    """Tests that individual panel dicts carry layer_w_offset."""

    def test_exterior_panels_have_layer_w_offset(self) -> None:
        """Each panel dict should carry its layer_w_offset for geometry conversion."""
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
        ])
        result = generate_assembly_layers(wall_data)
        for panel in result["layer_results"][0]["panels"]:
            assert "layer_w_offset" in panel, (
                f"Panel {panel['id']} missing layer_w_offset"
            )
            assert panel["layer_w_offset"] > 0  # Exterior should be positive

    def test_interior_panels_have_negative_offset(self) -> None:
        """Interior panels should have negative layer_w_offset."""
        wall_data = _make_wall_data(layers=[
            {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
        ])
        result = generate_assembly_layers(wall_data)
        for panel in result["layer_results"][0]["panels"]:
            assert "layer_w_offset" in panel
            assert panel["layer_w_offset"] < 0  # Interior should be negative

    def test_panel_w_offset_matches_layer_w_offset(self) -> None:
        """Panel's embedded layer_w_offset should match the layer-level w_offset."""
        wall_data = _make_wall_data(layers=[
            {"name": "Siding", "function": "finish", "side": "exterior", "thickness": 0.026},
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "Studs", "function": "structure", "side": "core", "thickness": 0.458},
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.042},
        ])
        result = generate_assembly_layers(wall_data)
        for layer_result in result["layer_results"]:
            layer_w = layer_result["w_offset"]
            for panel in layer_result["panels"]:
                assert panel.get("layer_w_offset") == layer_w, (
                    f"Panel {panel['id']}: embedded {panel.get('layer_w_offset')} "
                    f"!= layer {layer_w}"
                )

    def test_exterior_sheathing_at_core_face(self) -> None:
        """Exterior sheathing closest to core should have w_offset = core_half."""
        core_thickness = 3.5 / 12  # 2x4
        osb_thickness = 7 / 16 / 12
        wall_data = _make_wall_data(layers=[
            {"name": "Siding", "function": "finish", "side": "exterior", "thickness": 0.5 / 12},
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": osb_thickness},
            {"name": "Studs", "function": "structure", "side": "core", "thickness": core_thickness},
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.5 / 12},
        ])
        result = generate_assembly_layers(wall_data)
        core_half = core_thickness / 2.0

        # Find OSB layer
        osb_layer = next(
            r for r in result["layer_results"] if r["layer_name"] == "OSB"
        )
        # OSB is the innermost exterior layer: should start at core_half + gap
        assert osb_layer["w_offset"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)
        # Siding should be further out: core_half + gap + osb_thickness
        siding_layer = next(
            r for r in result["layer_results"] if r["layer_name"] == "Siding"
        )
        assert siding_layer["w_offset"] == pytest.approx(
            core_half + SHEATHING_GAP + osb_thickness, abs=1e-6
        )

    def test_no_overlap_with_framing_bounds(self) -> None:
        """All sheathing panels must be positioned outside the framing core."""
        core_thickness = 3.5 / 12
        core_half = core_thickness / 2.0
        wall_data = _make_wall_data(layers=[
            {"name": "Siding", "function": "finish", "side": "exterior", "thickness": 0.5 / 12},
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core", "thickness": core_thickness},
            {"name": "Drywall", "function": "finish", "side": "interior", "thickness": 0.5 / 12},
        ])
        result = generate_assembly_layers(wall_data)
        for layer_result in result["layer_results"]:
            w_offset = layer_result["w_offset"]
            side = layer_result["layer_side"]
            assert w_offset is not None, (
                f"Layer {layer_result['layer_name']} has no w_offset"
            )
            if side == "exterior":
                assert w_offset >= core_half - 1e-9, (
                    f"Exterior layer {layer_result['layer_name']} "
                    f"w_offset={w_offset} overlaps framing at {core_half}"
                )
            elif side == "interior":
                assert w_offset <= -core_half + 1e-9, (
                    f"Interior layer {layer_result['layer_name']} "
                    f"w_offset={w_offset} overlaps framing at {-core_half}"
                )

    def test_catalog_2x4_no_overlap(self) -> None:
        """Catalog 2x4 exterior assembly: no layer overlaps framing bounds."""
        core_thickness = 3.5 / 12
        core_half = core_thickness / 2.0
        layers = [
            {"name": "exterior_finish", "function": "finish", "side": "exterior",
             "thickness": 0.5 / 12, "material": "Lap Siding"},
            {"name": "structural_sheathing", "function": "substrate", "side": "exterior",
             "thickness": 0.4375 / 12, "material": "OSB 7/16"},
            {"name": "framing_core", "function": "structure", "side": "core",
             "thickness": core_thickness, "material": '2x4 SPF @ 16" OC'},
            {"name": "interior_finish", "function": "finish", "side": "interior",
             "thickness": 0.5 / 12, "material": '1/2" Gypsum Board'},
        ]
        wall_data = _make_wall_data(layers=layers)
        result = generate_assembly_layers(wall_data)

        for layer_result in result["layer_results"]:
            w = layer_result["w_offset"]
            assert w is not None
            side = layer_result["layer_side"]
            if side == "exterior":
                assert w >= core_half - 1e-9
            else:
                assert w <= -core_half + 1e-9

            # Every panel in this layer should also have the offset
            for panel in layer_result["panels"]:
                assert panel.get("layer_w_offset") == w


class TestFallbackWOffsets:
    """Tests for _compute_fallback_w_offsets."""

    def test_fallback_matches_primary(self) -> None:
        """Fallback should produce same offsets as primary for catalog assemblies."""
        from src.timber_framing_generator.sheathing.multi_layer_generator import (
            _compute_fallback_w_offsets,
        )
        layers = [
            {"name": "exterior_finish", "function": "finish", "side": "exterior",
             "thickness": 0.5 / 12},
            {"name": "structural_sheathing", "function": "substrate", "side": "exterior",
             "thickness": 0.4375 / 12},
            {"name": "framing_core", "function": "structure", "side": "core",
             "thickness": 3.5 / 12},
            {"name": "interior_finish", "function": "finish", "side": "interior",
             "thickness": 0.5 / 12},
        ]
        assembly = {"layers": layers}
        offsets = _compute_fallback_w_offsets(assembly)

        core_half = 3.5 / 12 / 2.0
        osb_t = 0.4375 / 12

        assert offsets["structural_sheathing"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)
        assert offsets["exterior_finish"] == pytest.approx(core_half + SHEATHING_GAP + osb_t, abs=1e-6)
        assert offsets["interior_finish"] == pytest.approx(-(core_half + SHEATHING_GAP), abs=1e-6)

    def test_fallback_no_core_returns_empty(self) -> None:
        """Fallback returns empty if no core layer."""
        from src.timber_framing_generator.sheathing.multi_layer_generator import (
            _compute_fallback_w_offsets,
        )
        assembly = {"layers": [
            {"name": "OSB", "function": "substrate", "side": "exterior", "thickness": 0.036},
        ]}
        assert _compute_fallback_w_offsets(assembly) == {}


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


# =============================================================================
# _infer_framing_depth Tests
# =============================================================================


class TestInferFramingDepth:
    """Tests for _infer_framing_depth helper."""

    def test_2x4_material_name(self) -> None:
        assembly = {"layers": [
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 3.5 / 12, "material": '2x4 SPF @ 16" OC'},
        ]}
        depth = _infer_framing_depth(assembly)
        assert depth == pytest.approx(3.5 / 12, abs=1e-6)

    def test_2x6_material_name(self) -> None:
        assembly = {"layers": [
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 5.5 / 12, "material": '2x6 SPF @ 16" OC'},
        ]}
        depth = _infer_framing_depth(assembly)
        assert depth == pytest.approx(5.5 / 12, abs=1e-6)

    def test_no_material_returns_none(self) -> None:
        assembly = {"layers": [
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 3.5 / 12},
        ]}
        assert _infer_framing_depth(assembly) is None

    def test_non_lumber_material_returns_none(self) -> None:
        assembly = {"layers": [
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 3.5 / 12, "material": "Steel Studs 3.5 inch"},
        ]}
        assert _infer_framing_depth(assembly) is None

    def test_ignores_non_core_layers(self) -> None:
        assembly = {"layers": [
            {"name": "osb", "function": "substrate", "side": "exterior",
             "thickness": 0.036, "material": "2x4 something"},
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 5.5 / 12, "material": '2x6 SPF'},
        ]}
        depth = _infer_framing_depth(assembly)
        assert depth == pytest.approx(5.5 / 12, abs=1e-6)

    def test_empty_assembly(self) -> None:
        assert _infer_framing_depth({"layers": []}) is None
        assert _infer_framing_depth({}) is None


# =============================================================================
# Framing Depth Override Tests
# =============================================================================


class TestFramingDepthOverride:
    """Tests that framing_depth correctly prevents sheathing-framing overlap."""

    def test_explicit_framing_depth_overrides_core(self) -> None:
        """Explicit framing_depth=2x6 on 2x4 assembly pushes layers out."""
        core_2x4 = 3.5 / 12
        depth_2x6 = 5.5 / 12
        framing_half = depth_2x6 / 2.0

        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core",
             "thickness": core_2x4, "material": '2x4 SPF @ 16" OC'},
            {"name": "Gyp", "function": "finish", "side": "interior",
             "thickness": 0.5 / 12},
        ])
        result = generate_assembly_layers(wall_data, framing_depth=depth_2x6)

        osb_layer = next(r for r in result["layer_results"] if r["layer_name"] == "OSB")
        gyp_layer = next(r for r in result["layer_results"] if r["layer_name"] == "Gyp")

        # OSB should start at framing_half + gap (2x6), not core_half (2x4)
        assert osb_layer["w_offset"] == pytest.approx(framing_half + SHEATHING_GAP, abs=1e-6)
        # Interior gyp at -(framing_half + gap)
        assert gyp_layer["w_offset"] == pytest.approx(-(framing_half + SHEATHING_GAP), abs=1e-6)

    def test_framing_depth_none_uses_auto_inference(self) -> None:
        """framing_depth=None auto-infers from '2x4' in core material name."""
        core_2x4 = 3.5 / 12
        core_half = core_2x4 / 2.0

        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core",
             "thickness": core_2x4, "material": '2x4 SPF @ 16" OC'},
        ])
        result = generate_assembly_layers(wall_data, framing_depth=None)

        osb_layer = result["layer_results"][0]
        # Auto-inferred 2x4 -> 3.5/12. core_half == framing_half -> same result + gap
        assert osb_layer["w_offset"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)

    def test_no_overlap_with_mismatched_framing(self) -> None:
        """When framing is 2x6 but assembly says 2x4, no panel overlaps framing."""
        core_2x4 = 3.5 / 12
        depth_2x6 = 5.5 / 12
        framing_half = depth_2x6 / 2.0

        wall_data = _make_wall_data(layers=[
            {"name": "Siding", "function": "finish", "side": "exterior",
             "thickness": 0.5 / 12},
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core",
             "thickness": core_2x4, "material": '2x4 SPF @ 16" OC'},
            {"name": "Gyp", "function": "finish", "side": "interior",
             "thickness": 0.5 / 12},
        ])
        result = generate_assembly_layers(wall_data, framing_depth=depth_2x6)

        for layer_result in result["layer_results"]:
            w = layer_result["w_offset"]
            side = layer_result["layer_side"]
            assert w is not None
            if side == "exterior":
                assert w >= framing_half - 1e-9, (
                    f"Exterior layer {layer_result['layer_name']} "
                    f"w_offset={w} overlaps framing at {framing_half}"
                )
            elif side == "interior":
                assert w <= -framing_half + 1e-9, (
                    f"Interior layer {layer_result['layer_name']} "
                    f"w_offset={w} overlaps framing at {-framing_half}"
                )

    def test_panels_carry_corrected_w_offset(self) -> None:
        """Individual panels should carry the framing-depth-corrected w_offset."""
        depth_2x6 = 5.5 / 12
        framing_half = depth_2x6 / 2.0

        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core",
             "thickness": 3.5 / 12, "material": '2x4 SPF @ 16" OC'},
        ])
        result = generate_assembly_layers(wall_data, framing_depth=depth_2x6)

        for panel in result["layer_results"][0]["panels"]:
            assert panel["layer_w_offset"] == pytest.approx(framing_half + SHEATHING_GAP, abs=1e-6)


class TestFallbackWOffsetsWithFramingDepth:
    """Tests for _compute_fallback_w_offsets with framing_depth."""

    def test_fallback_respects_framing_depth(self) -> None:
        """Fallback should use max(core_half, framing_depth/2)."""
        layers = [
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 3.5 / 12},
            {"name": "gyp", "function": "finish", "side": "interior",
             "thickness": 0.5 / 12},
        ]
        assembly = {"layers": layers}

        depth_2x6 = 5.5 / 12
        framing_half = depth_2x6 / 2.0

        offsets = _compute_fallback_w_offsets(assembly, framing_depth=depth_2x6)
        assert offsets["OSB"] == pytest.approx(framing_half + SHEATHING_GAP, abs=1e-6)
        assert offsets["gyp"] == pytest.approx(-(framing_half + SHEATHING_GAP), abs=1e-6)

    def test_fallback_framing_depth_none_unchanged(self) -> None:
        """Fallback with framing_depth=None should match default behavior."""
        layers = [
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "core", "function": "structure", "side": "core",
             "thickness": 3.5 / 12},
        ]
        assembly = {"layers": layers}
        core_half = 3.5 / 12 / 2.0

        offsets_default = _compute_fallback_w_offsets(assembly)
        offsets_none = _compute_fallback_w_offsets(assembly, framing_depth=None)
        assert offsets_default["OSB"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)
        assert offsets_none["OSB"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)


class TestWallThicknessFramingDepthFallback:
    """Tests that wall_thickness from Revit is used when it exceeds
    the assembly's core_thickness (e.g., CFS profiles on a '2x4' assembly)."""

    def _cfs_wall_data(self, wall_thickness: float = 0.5) -> dict:
        """Wall with 2x4 assembly but CFS-scale wall_thickness (6 inches)."""
        return _make_wall_data(
            wall_thickness=wall_thickness,
            layers=[
                {"name": "OSB", "function": "substrate", "side": "exterior",
                 "thickness": 7 / 16 / 12},
                {"name": "Studs", "function": "structure", "side": "core",
                 "thickness": 3.5 / 12, "material": '2x4 SPF @ 16" OC'},
                {"name": "Gyp", "function": "finish", "side": "interior",
                 "thickness": 0.5 / 12},
            ],
        )

    def test_cfs_wall_uses_wall_thickness(self) -> None:
        """wall_thickness=0.5 (6in CFS) overrides inferred 3.5in '2x4' depth."""
        wall_data = self._cfs_wall_data(wall_thickness=0.5)
        result = generate_assembly_layers(wall_data, framing_depth=None)

        osb_layer = next(r for r in result["layer_results"] if r["layer_name"] == "OSB")
        # effective_half = max(core_half, wall_thickness/2) + gap
        # = max(3.5/24, 0.5/2) + 0.001 = 0.25 + 0.001 = 0.251
        expected = 0.5 / 2.0 + SHEATHING_GAP
        assert osb_layer["w_offset"] == pytest.approx(expected, abs=1e-6)

    def test_cfs_sheathing_clears_framing_zone(self) -> None:
        """All exterior layers start past framing half-depth."""
        wall_data = self._cfs_wall_data(wall_thickness=0.5)
        framing_half = 0.5 / 2.0  # 6in / 2 = 3in = 0.25 ft

        result = generate_assembly_layers(wall_data, framing_depth=None)

        for lr in result["layer_results"]:
            w = lr["w_offset"]
            if lr["layer_side"] == "exterior":
                assert w >= framing_half, (
                    f"Exterior {lr['layer_name']} w_offset={w} "
                    f"overlaps CFS framing at {framing_half}"
                )
            elif lr["layer_side"] == "interior":
                assert w <= -framing_half, (
                    f"Interior {lr['layer_name']} w_offset={w} "
                    f"overlaps CFS framing at {-framing_half}"
                )

    def test_no_wall_thickness_uses_inferred_depth(self) -> None:
        """Without wall_thickness, falls back to assembly inference."""
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core",
             "thickness": 3.5 / 12, "material": '2x4 SPF @ 16" OC'},
        ])
        # No wall_thickness key → falls back to _infer_framing_depth → 3.5/12
        result = generate_assembly_layers(wall_data, framing_depth=None)

        osb_layer = result["layer_results"][0]
        core_half = 3.5 / 12 / 2.0
        assert osb_layer["w_offset"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)

    def test_explicit_framing_depth_overrides_wall_thickness(self) -> None:
        """Explicit framing_depth takes priority over wall_thickness."""
        depth_2x8 = 7.25 / 12
        wall_data = self._cfs_wall_data(wall_thickness=0.5)

        result = generate_assembly_layers(wall_data, framing_depth=depth_2x8)

        osb_layer = next(r for r in result["layer_results"] if r["layer_name"] == "OSB")
        # explicit 2x8 (7.25") > wall_thickness (6") → uses 2x8
        expected = depth_2x8 / 2.0 + SHEATHING_GAP
        assert osb_layer["w_offset"] == pytest.approx(expected, abs=1e-6)

    def test_wall_thickness_in_inches_auto_converted(self) -> None:
        """wall_thickness > 2.0 is treated as inches and converted to feet."""
        wall_data = self._cfs_wall_data(wall_thickness=6.0)  # 6 inches

        result = generate_assembly_layers(wall_data, framing_depth=None)

        osb_layer = next(r for r in result["layer_results"] if r["layer_name"] == "OSB")
        # 6 inches > 2.0 → /12 → 0.5 ft → half = 0.25
        expected = 0.5 / 2.0 + SHEATHING_GAP
        assert osb_layer["w_offset"] == pytest.approx(expected, abs=1e-6)


# =============================================================================
# extract_max_framing_depth Tests
# =============================================================================


def _make_framing_element(depth: float, wall_id: str = "w1") -> dict:
    """Create a minimal framing element dict with a profile depth."""
    return {
        "id": "elem_1",
        "element_type": "stud",
        "profile": {
            "name": "test_profile",
            "width": 0.125,
            "depth": depth,
            "material_system": "cfs",
        },
        "metadata": {"wall_id": wall_id},
    }


def _make_framing_data(elements: list) -> dict:
    """Wrap elements in a FramingResults-like dict."""
    return {
        "wall_id": "all_walls",
        "material_system": "cfs",
        "elements": elements,
    }


class TestExtractMaxFramingDepth:
    """Tests for extract_max_framing_depth()."""

    def test_single_element(self) -> None:
        """Returns the depth of the only element."""
        data = _make_framing_data([_make_framing_element(0.458)])
        assert extract_max_framing_depth(data) == pytest.approx(0.458)

    def test_max_across_multiple_elements(self) -> None:
        """Returns the maximum depth across studs and plates."""
        data = _make_framing_data([
            _make_framing_element(0.458),   # 5.5" stud
            _make_framing_element(0.5),     # 6" plate
            _make_framing_element(0.292),   # 3.5" misc
        ])
        assert extract_max_framing_depth(data) == pytest.approx(0.5)

    def test_empty_elements(self) -> None:
        """Returns None when there are no elements."""
        data = _make_framing_data([])
        assert extract_max_framing_depth(data) is None

    def test_none_input(self) -> None:
        """Returns None for None input."""
        assert extract_max_framing_depth(None) is None

    def test_list_of_results(self) -> None:
        """Handles a list of FramingResults dicts."""
        data = [
            _make_framing_data([_make_framing_element(0.292)]),
            _make_framing_data([_make_framing_element(0.5)]),
        ]
        assert extract_max_framing_depth(data) == pytest.approx(0.5)

    def test_wall_id_filter(self) -> None:
        """Filters elements by wall_id when specified."""
        data = _make_framing_data([
            _make_framing_element(0.5, wall_id="w1"),
            _make_framing_element(0.292, wall_id="w2"),
        ])
        assert extract_max_framing_depth(data, wall_id="w2") == pytest.approx(0.292)

    def test_wall_id_filter_no_match(self) -> None:
        """Returns None when no elements match wall_id."""
        data = _make_framing_data([_make_framing_element(0.5, wall_id="w1")])
        assert extract_max_framing_depth(data, wall_id="w999") is None

    def test_missing_profile(self) -> None:
        """Skips elements without a profile dict."""
        data = _make_framing_data([{"id": "bad", "element_type": "stud"}])
        assert extract_max_framing_depth(data) is None

    def test_missing_depth(self) -> None:
        """Skips profiles without a depth key."""
        data = _make_framing_data([{
            "id": "bad",
            "element_type": "stud",
            "profile": {"name": "test", "width": 0.125},
            "metadata": {},
        }])
        assert extract_max_framing_depth(data) is None


class TestFramingJsonAutoDetectIntegration:
    """Integration: framing_json auto-detection feeds generate_assembly_layers."""

    def _cfs_wall_and_framing(self) -> tuple:
        """Wall with 2x4 assembly + CFS framing data (6" plates)."""
        wall_data = _make_wall_data(layers=[
            {"name": "OSB", "function": "substrate", "side": "exterior",
             "thickness": 7 / 16 / 12},
            {"name": "Studs", "function": "structure", "side": "core",
             "thickness": 3.5 / 12, "material": '2x4 SPF @ 16" OC'},
            {"name": "Gyp", "function": "finish", "side": "interior",
             "thickness": 0.5 / 12},
        ])
        # CFS framing: 5.5" studs and 6" plates
        framing_data = _make_framing_data([
            _make_framing_element(5.5 / 12),   # stud
            _make_framing_element(6.0 / 12),   # plate (largest)
        ])
        return wall_data, framing_data

    def test_auto_detected_depth_clears_cfs_framing(self) -> None:
        """extract_max_framing_depth + generate_assembly_layers clears CFS plates."""
        wall_data, framing_data = self._cfs_wall_and_framing()

        auto_depth = extract_max_framing_depth(framing_data)
        assert auto_depth == pytest.approx(6.0 / 12)

        result = generate_assembly_layers(wall_data, framing_depth=auto_depth)

        cfs_plate_half = 6.0 / 12 / 2.0  # 0.25 ft
        for lr in result["layer_results"]:
            w = lr["w_offset"]
            if lr["layer_side"] == "exterior":
                assert w >= cfs_plate_half, (
                    f"Exterior {lr['layer_name']} w_offset={w} "
                    f"overlaps CFS plate at {cfs_plate_half}"
                )

    def test_explicit_framing_depth_wins_over_auto(self) -> None:
        """Explicit framing_depth from config takes priority over framing_json."""
        wall_data, framing_data = self._cfs_wall_and_framing()

        auto_depth = extract_max_framing_depth(framing_data)
        explicit_depth = 7.25 / 12  # 2x8

        # Explicit is bigger — should be used
        result = generate_assembly_layers(wall_data, framing_depth=explicit_depth)
        osb_layer = next(r for r in result["layer_results"] if r["layer_name"] == "OSB")
        expected = explicit_depth / 2.0 + SHEATHING_GAP
        assert osb_layer["w_offset"] == pytest.approx(expected, abs=1e-6)

    def test_without_framing_json_falls_back_to_inference(self) -> None:
        """Without framing_json, falls back to _infer_framing_depth."""
        wall_data, _ = self._cfs_wall_and_framing()

        # No framing_depth passed → infers 3.5/12 from "2x4" in core name
        result = generate_assembly_layers(wall_data, framing_depth=None)
        osb_layer = next(r for r in result["layer_results"] if r["layer_name"] == "OSB")
        core_half = 3.5 / 12 / 2.0
        assert osb_layer["w_offset"] == pytest.approx(core_half + SHEATHING_GAP, abs=1e-6)


# =============================================================================
# Fix 1: Flip Normalization Tests (PRP-026)
# =============================================================================


def _normalize_flip(wall_data: dict) -> dict:
    """Standalone copy of _normalize_flip for testing (from GH components).

    Negates z_axis when is_flipped=True so +z = physical exterior.
    """
    if not wall_data.get("is_flipped", False):
        return wall_data
    wall = dict(wall_data)
    bp = dict(wall.get("base_plane", {}))
    z = bp.get("z_axis", {})
    bp["z_axis"] = {
        "x": -z.get("x", 0),
        "y": -z.get("y", 0),
        "z": -z.get("z", 0),
    }
    wall["base_plane"] = bp
    return wall


class TestFlipNormalization:
    """Tests for _normalize_flip() — Fix 1 from PRP-026.

    When Revit's is_flipped flag is True, z_axis points toward the
    building interior. _normalize_flip negates z_axis so all downstream
    code can consistently use +z_axis = physical exterior.
    """

    def test_flipped_wall_z_axis_negated(self) -> None:
        """z_axis should be negated when is_flipped=True."""
        wall = {
            "wall_id": "W1",
            "is_flipped": True,
            "base_plane": {
                "origin": {"x": 0, "y": 0, "z": 0},
                "x_axis": {"x": 0, "y": 1, "z": 0},
                "y_axis": {"x": 0, "y": 0, "z": 1},
                "z_axis": {"x": 1, "y": 0, "z": 0},
            },
        }
        result = _normalize_flip(wall)
        z = result["base_plane"]["z_axis"]
        assert z["x"] == -1
        assert z["y"] == 0
        assert z["z"] == 0

    def test_non_flipped_wall_unchanged(self) -> None:
        """z_axis should remain unchanged when is_flipped=False."""
        wall = {
            "wall_id": "W1",
            "is_flipped": False,
            "base_plane": {
                "origin": {"x": 0, "y": 0, "z": 0},
                "x_axis": {"x": 0, "y": 1, "z": 0},
                "y_axis": {"x": 0, "y": 0, "z": 1},
                "z_axis": {"x": 1, "y": 0, "z": 0},
            },
        }
        result = _normalize_flip(wall)
        z = result["base_plane"]["z_axis"]
        assert z["x"] == 1
        assert z["y"] == 0
        assert z["z"] == 0

    def test_missing_is_flipped_treated_as_false(self) -> None:
        """Wall without is_flipped key should be unchanged."""
        wall = {
            "wall_id": "W1",
            "base_plane": {
                "z_axis": {"x": 0, "y": -1, "z": 0},
            },
        }
        result = _normalize_flip(wall)
        z = result["base_plane"]["z_axis"]
        assert z["y"] == -1

    def test_original_wall_not_mutated(self) -> None:
        """Original wall dict should not be modified."""
        wall = {
            "wall_id": "W1",
            "is_flipped": True,
            "base_plane": {
                "z_axis": {"x": 1, "y": 0, "z": 0},
            },
        }
        _ = _normalize_flip(wall)
        # Original z_axis should be unchanged
        assert wall["base_plane"]["z_axis"]["x"] == 1

    def test_flipped_wall_x_axis_preserved(self) -> None:
        """Other base_plane axes should remain unchanged."""
        wall = {
            "wall_id": "W1",
            "is_flipped": True,
            "base_plane": {
                "x_axis": {"x": 0, "y": 1, "z": 0},
                "y_axis": {"x": 0, "y": 0, "z": 1},
                "z_axis": {"x": 1, "y": 0, "z": 0},
            },
        }
        result = _normalize_flip(wall)
        assert result["base_plane"]["x_axis"]["y"] == 1
        assert result["base_plane"]["y_axis"]["z"] == 1

    def test_diagonal_z_axis_negated(self) -> None:
        """Non-axis-aligned z_axis should be fully negated."""
        wall = {
            "wall_id": "W1",
            "is_flipped": True,
            "base_plane": {
                "z_axis": {"x": 0.707, "y": 0.707, "z": 0},
            },
        }
        result = _normalize_flip(wall)
        z = result["base_plane"]["z_axis"]
        assert abs(z["x"] - (-0.707)) < 0.001
        assert abs(z["y"] - (-0.707)) < 0.001
