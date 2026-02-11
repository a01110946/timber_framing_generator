# File: tests/wall_data/test_assembly_extractor.py

"""Tests for wall assembly extraction from Revit CompoundStructure.

Tests cover:
- Revit layer function mapping (pure Python)
- Layer side determination (pure Python)
- Assembly dict -> WallAssemblyDef conversion
- get_assembly_for_wall() with Revit-sourced assembly data
- WallData serialization roundtrip with wall_assembly field
"""

import json
import pytest

from src.timber_framing_generator.wall_data.assembly_extractor import (
    map_revit_layer_function,
    determine_layer_side,
    assembly_dict_to_def,
)
from src.timber_framing_generator.wall_junctions.junction_types import (
    WallAssemblyDef,
    WallLayer,
    LayerFunction,
    LayerSide,
)
from src.timber_framing_generator.config.assembly import (
    get_assembly_for_wall,
    ASSEMBLY_2X4_EXTERIOR,
    ASSEMBLY_2X4_INTERIOR,
)
from src.timber_framing_generator.core.json_schemas import (
    WallData,
    serialize_wall_data,
    deserialize_wall_data,
    PlaneData,
    Point3D,
    Vector3D,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def revit_exterior_assembly_dict():
    """Simulated CompoundStructure extraction result for a 2x6 exterior wall."""
    return {
        "name": "Basic Wall: 2x6 + Brick",
        "layers": [
            {
                "name": "exterior_finish",
                "thickness": 0.333,
                "function": "finish",
                "side": "exterior",
                "material": "Brick, Common",
                "priority": 10,
            },
            {
                "name": "exterior_thermal",
                "thickness": 0.0833,
                "function": "thermal",
                "side": "exterior",
                "material": "Air Space",
                "priority": 40,
            },
            {
                "name": "exterior_substrate",
                "thickness": 0.0417,
                "function": "substrate",
                "side": "exterior",
                "material": "OSB 1/2",
                "priority": 80,
            },
            {
                "name": "framing_structure",
                "thickness": 0.4583,
                "function": "structure",
                "side": "core",
                "material": "2x6 SPF @ 16\" OC",
                "priority": 100,
            },
            {
                "name": "interior_finish",
                "thickness": 0.0417,
                "function": "finish",
                "side": "interior",
                "material": "1/2\" Gypsum Board",
                "priority": 10,
            },
        ],
        "source": "revit",
    }


@pytest.fixture
def simple_wall_data():
    """Minimal WallData dict for testing get_assembly_for_wall."""
    return {
        "wall_id": "w1",
        "wall_type": "some_custom_type",
        "is_exterior": True,
    }


@pytest.fixture
def wall_data_with_assembly(revit_exterior_assembly_dict):
    """WallData dict that includes a Revit-extracted assembly."""
    return {
        "wall_id": "w1",
        "wall_type": "Basic Wall: 2x6 + Brick",
        "is_exterior": True,
        "wall_assembly": revit_exterior_assembly_dict,
    }


@pytest.fixture
def full_wall_data_obj():
    """Full WallData object for serialization testing."""
    return WallData(
        wall_id="w_test",
        wall_length=15.0,
        wall_height=8.0,
        wall_thickness=0.5,
        base_elevation=0.0,
        top_elevation=8.0,
        base_plane=PlaneData(
            origin=Point3D(0, 0, 0),
            x_axis=Vector3D(1, 0, 0),
            y_axis=Vector3D(0, 0, 1),
            z_axis=Vector3D(0, -1, 0),
        ),
        base_curve_start=Point3D(0, 0, 0),
        base_curve_end=Point3D(15, 0, 0),
        is_exterior=True,
        wall_type="Test Wall Type",
        wall_assembly={
            "name": "Test Wall Type",
            "layers": [
                {
                    "name": "ext_finish",
                    "thickness": 0.04,
                    "function": "finish",
                    "side": "exterior",
                    "material": "Siding",
                    "priority": 10,
                },
                {
                    "name": "framing_core",
                    "thickness": 0.29,
                    "function": "structure",
                    "side": "core",
                    "material": "2x4 SPF",
                    "priority": 100,
                },
                {
                    "name": "int_finish",
                    "thickness": 0.04,
                    "function": "finish",
                    "side": "interior",
                    "material": "Gypsum",
                    "priority": 10,
                },
            ],
            "source": "revit",
        },
    )


# =============================================================================
# map_revit_layer_function Tests
# =============================================================================


class TestMapRevitLayerFunction:
    """Tests for Revit layer function mapping."""

    def test_integer_structure(self):
        assert map_revit_layer_function(0) == "structure"

    def test_integer_substrate(self):
        assert map_revit_layer_function(1) == "substrate"

    def test_integer_thermal(self):
        assert map_revit_layer_function(2) == "thermal"

    def test_integer_membrane(self):
        assert map_revit_layer_function(3) == "membrane"

    def test_integer_finish1(self):
        assert map_revit_layer_function(4) == "finish"

    def test_integer_finish2(self):
        assert map_revit_layer_function(5) == "finish"

    def test_string_structure(self):
        assert map_revit_layer_function("Structure") == "structure"

    def test_string_finish1(self):
        assert map_revit_layer_function("Finish1") == "finish"

    def test_string_thermal_air(self):
        assert map_revit_layer_function("ThermalAir") == "thermal"

    def test_string_membrane(self):
        assert map_revit_layer_function("Membrane") == "membrane"

    def test_unknown_integer_defaults_to_structure(self):
        assert map_revit_layer_function(99) == "structure"

    def test_unknown_string_defaults_to_structure(self):
        assert map_revit_layer_function("FutureType") == "structure"


# =============================================================================
# determine_layer_side Tests
# =============================================================================


class TestDetermineLayerSide:
    """Tests for layer side determination from indices."""

    def test_before_core_is_exterior(self):
        assert determine_layer_side(0, 2, 3) == "exterior"
        assert determine_layer_side(1, 2, 3) == "exterior"

    def test_at_core_is_core(self):
        assert determine_layer_side(2, 2, 3) == "core"
        assert determine_layer_side(3, 2, 3) == "core"

    def test_after_core_is_interior(self):
        assert determine_layer_side(4, 2, 3) == "interior"
        assert determine_layer_side(5, 2, 3) == "interior"

    def test_single_core_layer(self):
        # Core is just layer 1 (index 1 to 1)
        assert determine_layer_side(0, 1, 1) == "exterior"
        assert determine_layer_side(1, 1, 1) == "core"
        assert determine_layer_side(2, 1, 1) == "interior"

    def test_no_core_boundary_all_core(self):
        # When core indices are -1, all layers treated as core
        assert determine_layer_side(0, -1, -1) == "core"
        assert determine_layer_side(3, -1, -1) == "core"

    def test_all_core(self):
        # Core spans all layers (index 0 to 4)
        assert determine_layer_side(0, 0, 4) == "core"
        assert determine_layer_side(2, 0, 4) == "core"
        assert determine_layer_side(4, 0, 4) == "core"


# =============================================================================
# assembly_dict_to_def Tests
# =============================================================================


class TestAssemblyDictToDef:
    """Tests for converting assembly dicts to WallAssemblyDef objects."""

    def test_basic_conversion(self, revit_exterior_assembly_dict):
        assembly = assembly_dict_to_def(revit_exterior_assembly_dict)
        assert isinstance(assembly, WallAssemblyDef)
        assert assembly.name == "Basic Wall: 2x6 + Brick"
        assert assembly.source == "revit"
        assert len(assembly.layers) == 5

    def test_layer_types_correct(self, revit_exterior_assembly_dict):
        assembly = assembly_dict_to_def(revit_exterior_assembly_dict)
        assert assembly.layers[0].function == LayerFunction.FINISH
        assert assembly.layers[0].side == LayerSide.EXTERIOR
        assert assembly.layers[3].function == LayerFunction.STRUCTURE
        assert assembly.layers[3].side == LayerSide.CORE
        assert assembly.layers[4].function == LayerFunction.FINISH
        assert assembly.layers[4].side == LayerSide.INTERIOR

    def test_thicknesses_preserved(self, revit_exterior_assembly_dict):
        assembly = assembly_dict_to_def(revit_exterior_assembly_dict)
        assert abs(assembly.layers[0].thickness - 0.333) < 0.001
        assert abs(assembly.layers[3].thickness - 0.4583) < 0.001

    def test_materials_preserved(self, revit_exterior_assembly_dict):
        assembly = assembly_dict_to_def(revit_exterior_assembly_dict)
        assert assembly.layers[0].material == "Brick, Common"
        assert assembly.layers[4].material == '1/2" Gypsum Board'

    def test_total_thickness(self, revit_exterior_assembly_dict):
        assembly = assembly_dict_to_def(revit_exterior_assembly_dict)
        expected = 0.333 + 0.0833 + 0.0417 + 0.4583 + 0.0417
        assert abs(assembly.total_thickness - expected) < 0.001

    def test_core_thickness(self, revit_exterior_assembly_dict):
        assembly = assembly_dict_to_def(revit_exterior_assembly_dict)
        assert abs(assembly.core_thickness - 0.4583) < 0.001

    def test_empty_assembly(self):
        assembly = assembly_dict_to_def({"name": "empty", "layers": []})
        assert assembly.total_thickness == 0.0

    def test_missing_fields_use_defaults(self):
        assembly = assembly_dict_to_def({
            "name": "minimal",
            "layers": [{"thickness": 0.3}],
        })
        assert len(assembly.layers) == 1
        assert assembly.layers[0].name == "unknown"
        assert assembly.layers[0].function == LayerFunction.STRUCTURE
        assert assembly.layers[0].side == LayerSide.CORE
        assert assembly.layers[0].priority == 50


# =============================================================================
# get_assembly_for_wall with Revit data Tests
# =============================================================================


class TestGetAssemblyForWallWithRevit:
    """Tests for assembly lookup preferring Revit-extracted data."""

    def test_revit_assembly_takes_priority(self, wall_data_with_assembly):
        assembly = get_assembly_for_wall(wall_data_with_assembly)
        assert assembly.name == "Basic Wall: 2x6 + Brick"
        assert assembly.source == "revit"
        assert len(assembly.layers) == 5

    def test_catalog_used_without_revit_data(self):
        wall = {"wall_id": "w1", "wall_type": "2x4_exterior"}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x4_exterior"
        assert assembly.source == "default"

    def test_default_exterior_without_type_or_assembly(self):
        wall = {"wall_id": "w1", "is_exterior": True}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x4_exterior"

    def test_default_interior_without_type_or_assembly(self):
        wall = {"wall_id": "w1", "is_exterior": False}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x4_interior"

    def test_revit_assembly_overrides_catalog_type(self, revit_exterior_assembly_dict):
        """Even if wall_type matches catalog, Revit assembly takes priority."""
        wall = {
            "wall_id": "w1",
            "wall_type": "2x4_interior",
            "wall_assembly": revit_exterior_assembly_dict,
        }
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "Basic Wall: 2x6 + Brick"
        assert assembly.source == "revit"

    def test_invalid_assembly_falls_back(self):
        """Invalid wall_assembly dict falls through to catalog/defaults."""
        wall = {
            "wall_id": "w1",
            "is_exterior": True,
            "wall_assembly": {"bad": "data"},
        }
        assembly = get_assembly_for_wall(wall)
        # Should fall back (bad data, but assembly_dict_to_def handles gracefully)
        assert assembly is not None

    def test_none_assembly_ignored(self):
        wall = {"wall_id": "w1", "is_exterior": True, "wall_assembly": None}
        assembly = get_assembly_for_wall(wall)
        assert assembly.name == "2x4_exterior"


# =============================================================================
# WallData Serialization with wall_assembly
# =============================================================================


class TestWallDataSerializationWithAssembly:
    """Tests for WallData JSON roundtrip with wall_assembly field."""

    def test_serialize_includes_assembly(self, full_wall_data_obj):
        json_str = serialize_wall_data(full_wall_data_obj)
        data = json.loads(json_str)
        assert "wall_assembly" in data
        assert data["wall_assembly"]["name"] == "Test Wall Type"
        assert len(data["wall_assembly"]["layers"]) == 3

    def test_deserialize_preserves_assembly(self, full_wall_data_obj):
        json_str = serialize_wall_data(full_wall_data_obj)
        restored = deserialize_wall_data(json_str)
        assert restored.wall_assembly is not None
        assert restored.wall_assembly["name"] == "Test Wall Type"
        assert len(restored.wall_assembly["layers"]) == 3

    def test_roundtrip_assembly_to_def(self, full_wall_data_obj):
        """Full roundtrip: WallData -> JSON -> WallData -> get_assembly_for_wall."""
        json_str = serialize_wall_data(full_wall_data_obj)
        restored = deserialize_wall_data(json_str)

        # Convert to dict for get_assembly_for_wall
        from dataclasses import asdict
        wall_dict = asdict(restored)
        assembly = get_assembly_for_wall(wall_dict)

        assert assembly.name == "Test Wall Type"
        assert assembly.source == "revit"
        assert len(assembly.layers) == 3
        assert abs(assembly.core_thickness - 0.29) < 0.01

    def test_serialize_without_assembly(self):
        wall = WallData(
            wall_id="w_no_asm",
            wall_length=10.0,
            wall_height=8.0,
            wall_thickness=0.5,
            base_elevation=0.0,
            top_elevation=8.0,
            base_plane=PlaneData(
                origin=Point3D(0, 0, 0),
                x_axis=Vector3D(1, 0, 0),
                y_axis=Vector3D(0, 0, 1),
                z_axis=Vector3D(0, -1, 0),
            ),
            base_curve_start=Point3D(0, 0, 0),
            base_curve_end=Point3D(10, 0, 0),
        )
        json_str = serialize_wall_data(wall)
        data = json.loads(json_str)
        assert data["wall_assembly"] is None

    def test_deserialize_without_assembly(self):
        wall = WallData(
            wall_id="w_no_asm",
            wall_length=10.0,
            wall_height=8.0,
            wall_thickness=0.5,
            base_elevation=0.0,
            top_elevation=8.0,
            base_plane=PlaneData(
                origin=Point3D(0, 0, 0),
                x_axis=Vector3D(1, 0, 0),
                y_axis=Vector3D(0, 0, 1),
                z_axis=Vector3D(0, -1, 0),
            ),
            base_curve_start=Point3D(0, 0, 0),
            base_curve_end=Point3D(10, 0, 0),
        )
        json_str = serialize_wall_data(wall)
        restored = deserialize_wall_data(json_str)
        assert restored.wall_assembly is None

    def test_is_flipped_preserved_in_roundtrip(self):
        """Verify is_flipped field survives serialization roundtrip."""
        wall = WallData(
            wall_id="w_flip",
            wall_length=10.0,
            wall_height=8.0,
            wall_thickness=0.5,
            base_elevation=0.0,
            top_elevation=8.0,
            base_plane=PlaneData(
                origin=Point3D(0, 0, 0),
                x_axis=Vector3D(1, 0, 0),
                y_axis=Vector3D(0, 0, 1),
                z_axis=Vector3D(0, -1, 0),
            ),
            base_curve_start=Point3D(0, 0, 0),
            base_curve_end=Point3D(10, 0, 0),
            is_flipped=True,
        )
        json_str = serialize_wall_data(wall)
        restored = deserialize_wall_data(json_str)
        assert restored.is_flipped is True
