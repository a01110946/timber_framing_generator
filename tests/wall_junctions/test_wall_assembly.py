# File: tests/wall_junctions/test_wall_assembly.py

"""Tests for multi-layer wall assembly system.

Tests cover:
- WallLayer and WallAssemblyDef creation
- Assembly thickness calculations
- Layer-by-side queries
- Legacy WallLayerInfo conversion
- Assembly catalog and lookup
- Serialization
"""

import pytest

from src.timber_framing_generator.wall_junctions.junction_types import (
    WallLayer,
    WallAssemblyDef,
    WallLayerInfo,
    LayerFunction,
    LayerSide,
)
from src.timber_framing_generator.config.assembly import (
    ASSEMBLY_2X4_EXTERIOR,
    ASSEMBLY_2X6_EXTERIOR,
    ASSEMBLY_2X4_INTERIOR,
    WALL_ASSEMBLIES,
    get_assembly_for_wall,
    convert_to_feet,
)


# =============================================================================
# WallLayer Tests
# =============================================================================


class TestWallLayer:
    """Tests for WallLayer dataclass."""

    def test_create_layer(self):
        layer = WallLayer(
            name="test_sheathing",
            function=LayerFunction.SUBSTRATE,
            side=LayerSide.EXTERIOR,
            thickness=0.0365,
            material="OSB 7/16",
            priority=80,
        )
        assert layer.name == "test_sheathing"
        assert layer.function == LayerFunction.SUBSTRATE
        assert layer.side == LayerSide.EXTERIOR
        assert abs(layer.thickness - 0.0365) < 0.001
        assert layer.priority == 80

    def test_default_values(self):
        layer = WallLayer(
            name="basic",
            function=LayerFunction.FINISH,
            side=LayerSide.INTERIOR,
            thickness=0.0417,
        )
        assert layer.material == ""
        assert layer.priority == 50
        assert layer.wraps_at_ends is False
        assert layer.wraps_at_inserts is False


# =============================================================================
# WallAssemblyDef Tests
# =============================================================================


class TestWallAssemblyDef:
    """Tests for WallAssemblyDef dataclass."""

    @pytest.fixture
    def simple_assembly(self):
        """Simple 3-layer assembly for testing."""
        return WallAssemblyDef(
            name="test_assembly",
            layers=[
                WallLayer("ext_finish", LayerFunction.FINISH,
                          LayerSide.EXTERIOR, thickness=0.05),
                WallLayer("sheathing", LayerFunction.SUBSTRATE,
                          LayerSide.EXTERIOR, thickness=0.04),
                WallLayer("core", LayerFunction.STRUCTURE,
                          LayerSide.CORE, thickness=0.30),
                WallLayer("int_finish", LayerFunction.FINISH,
                          LayerSide.INTERIOR, thickness=0.04),
            ],
            source="test",
        )

    def test_total_thickness(self, simple_assembly):
        expected = 0.05 + 0.04 + 0.30 + 0.04
        assert abs(simple_assembly.total_thickness - expected) < 0.001

    def test_core_thickness(self, simple_assembly):
        assert abs(simple_assembly.core_thickness - 0.30) < 0.001

    def test_exterior_thickness(self, simple_assembly):
        expected = 0.05 + 0.04  # ext_finish + sheathing
        assert abs(simple_assembly.exterior_thickness - expected) < 0.001

    def test_interior_thickness(self, simple_assembly):
        assert abs(simple_assembly.interior_thickness - 0.04) < 0.001

    def test_get_layers_by_side(self, simple_assembly):
        ext_layers = simple_assembly.get_layers_by_side(LayerSide.EXTERIOR)
        assert len(ext_layers) == 2
        assert ext_layers[0].name == "ext_finish"
        assert ext_layers[1].name == "sheathing"

        core_layers = simple_assembly.get_layers_by_side(LayerSide.CORE)
        assert len(core_layers) == 1
        assert core_layers[0].name == "core"

        int_layers = simple_assembly.get_layers_by_side(LayerSide.INTERIOR)
        assert len(int_layers) == 1
        assert int_layers[0].name == "int_finish"

    def test_to_legacy_layer_info(self, simple_assembly):
        legacy = simple_assembly.to_legacy_layer_info("wall_test")
        assert isinstance(legacy, WallLayerInfo)
        assert legacy.wall_id == "wall_test"
        assert abs(legacy.total_thickness - simple_assembly.total_thickness) < 0.001
        assert abs(legacy.exterior_thickness - simple_assembly.exterior_thickness) < 0.001
        assert abs(legacy.core_thickness - simple_assembly.core_thickness) < 0.001
        assert abs(legacy.interior_thickness - simple_assembly.interior_thickness) < 0.001
        assert legacy.source == "test"

    def test_to_dict(self, simple_assembly):
        d = simple_assembly.to_dict()
        assert d["name"] == "test_assembly"
        assert d["source"] == "test"
        assert len(d["layers"]) == 4
        assert d["layers"][0]["name"] == "ext_finish"
        assert d["layers"][0]["function"] == "finish"
        assert d["layers"][0]["side"] == "exterior"

    def test_empty_assembly(self):
        empty = WallAssemblyDef(name="empty", layers=[])
        assert empty.total_thickness == 0.0
        assert empty.core_thickness == 0.0
        assert empty.exterior_thickness == 0.0
        assert empty.interior_thickness == 0.0


# =============================================================================
# Assembly Catalog Tests
# =============================================================================


class TestAssemblyCatalog:
    """Tests for the default assembly catalog."""

    def test_catalog_has_standard_assemblies(self):
        assert "2x4_exterior" in WALL_ASSEMBLIES
        assert "2x6_exterior" in WALL_ASSEMBLIES
        assert "2x4_interior" in WALL_ASSEMBLIES

    def test_2x4_exterior_layers(self):
        a = ASSEMBLY_2X4_EXTERIOR
        assert len(a.layers) == 4
        # Core should be 3.5 inches
        assert abs(a.core_thickness - convert_to_feet(3.5, "inches")) < 0.001
        # Should have layers on both sides
        assert a.exterior_thickness > 0
        assert a.interior_thickness > 0

    def test_2x6_exterior_layers(self):
        a = ASSEMBLY_2X6_EXTERIOR
        # Core should be 5.5 inches
        assert abs(a.core_thickness - convert_to_feet(5.5, "inches")) < 0.001

    def test_2x4_interior_symmetric(self):
        a = ASSEMBLY_2X4_INTERIOR
        # Interior partition: gypsum on both sides, same thickness
        assert abs(a.exterior_thickness - a.interior_thickness) < 0.001

    def test_assembly_thicknesses_sum_correctly(self):
        for name, assembly in WALL_ASSEMBLIES.items():
            layer_sum = sum(l.thickness for l in assembly.layers)
            assert abs(layer_sum - assembly.total_thickness) < 0.0001, (
                f"Assembly {name}: layer sum {layer_sum} != total {assembly.total_thickness}"
            )

    def test_every_assembly_has_core(self):
        for name, assembly in WALL_ASSEMBLIES.items():
            core_layers = assembly.get_layers_by_side(LayerSide.CORE)
            assert len(core_layers) >= 1, f"Assembly {name} has no core layer"


class TestGetAssemblyForWall:
    """Tests for get_assembly_for_wall lookup."""

    def test_exterior_wall_gets_exterior_assembly(self):
        wall = {"wall_id": "w1", "is_exterior": True}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x4_exterior"

    def test_interior_wall_gets_interior_assembly(self):
        wall = {"wall_id": "w1", "is_exterior": False}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x4_interior"

    def test_wall_type_overrides_default(self):
        wall = {"wall_id": "w1", "is_exterior": False, "wall_type": "2x6_exterior"}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x6_exterior"

    def test_unknown_wall_type_falls_back(self):
        wall = {"wall_id": "w1", "is_exterior": True, "wall_type": "unknown_type"}
        assembly = get_assembly_for_wall(wall)
        # Should fall back to exterior default
        assert assembly.name == "2x4_exterior"
