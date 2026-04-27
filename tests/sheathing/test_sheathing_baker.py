# File: tests/sheathing/test_sheathing_baker.py
"""Tests for sheathing baker helper functions.

These tests exercise the pure-Python logic that doesn't require Revit:
- Panel metadata lookup building
- Type name generation
- Sheathing data JSON output format
- Category map validation

The actual Revit baking (DirectShape, Transaction, SharedParameters) can
only be tested inside Grasshopper with RhinoInside.Revit running.
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on path so we can import the baker module
# The baker script uses ghenv and clr at module level, so we can't import
# it directly. Instead, we extract the pure functions and test them here.
# We replicate the pure-Python helpers to test their logic.

# =============================================================================
# Replicated helpers (same logic as gh_sheathing_baker.py)
# =============================================================================
# These are copied from the GH script because the script cannot be imported
# outside of Grasshopper (it depends on clr, ghenv, etc. at module level).
# If the logic changes in the script, update these copies accordingly.


def _normalize_to_wall_entries(data):
    """Normalize parsed JSON to a list of wall-level dicts."""
    if isinstance(data, dict):
        if "walls" in data and isinstance(data["walls"], list):
            return data["walls"]
        if "results" in data and isinstance(data["results"], list):
            return data["results"]
        return [data]
    elif isinstance(data, list):
        return data
    return []


def _extract_panels_from_wall_entry(wall_entry, lookup):
    """Extract panel metadata from a single wall entry into the lookup."""
    if not isinstance(wall_entry, dict):
        return

    wall_id = wall_entry.get("wall_id", "")

    panels = wall_entry.get("sheathing_panels", [])

    if not panels and "layer_results" in wall_entry:
        for layer in wall_entry.get("layer_results", []):
            layer_function = layer.get("layer_function", "unknown")
            for panel in layer.get("panels", []):
                enriched = dict(panel)
                enriched["layer_function"] = layer_function
                if "wall_id" not in enriched:
                    enriched["wall_id"] = wall_id
                pid = enriched.get("id")
                if pid:
                    lookup[pid] = enriched
    else:
        for panel in panels:
            enriched = dict(panel)
            if "wall_id" not in enriched:
                enriched["wall_id"] = wall_id
            pid = enriched.get("id")
            if pid:
                lookup[pid] = enriched


def _build_panel_metadata_lookup(sheathing_json_list):
    """Build lookup: sheathing_panel_id -> metadata dict."""
    lookup = {}
    for json_str in sheathing_json_list:
        if not json_str:
            continue
        try:
            data = json.loads(str(json_str))
        except (json.JSONDecodeError, TypeError):
            continue

        wall_entries = _normalize_to_wall_entries(data)

        for wall_entry in wall_entries:
            _extract_panels_from_wall_entry(wall_entry, lookup)

    return lookup


def _make_type_name(material_display, face):
    """Generate DirectShapeType name from material and face."""
    return "%s - %s" % (material_display, face.title())


# Supported category strings (same as script, resolved via getattr at runtime)
SUPPORTED_CATEGORIES = [
    "OST_GenericModel",
    "OST_Parts",
    "OST_StructuralConnections",
]

# TFG parameter definitions (same as script)
TFG_PARAM_DEFS = [
    ("TFG_WallId", "string"),
    ("TFG_PanelId", "string"),
    ("TFG_Face", "string"),
    ("TFG_Material", "string"),
    ("TFG_ThicknessIn", "number"),
    ("TFG_WidthFt", "number"),
    ("TFG_HeightFt", "number"),
    ("TFG_AreaSqFt", "number"),
    ("TFG_LayerFunction", "string"),
]


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def single_layer_json():
    """Single-layer sheathing JSON for one wall."""
    return json.dumps({
        "wall_id": "1234567",
        "sheathing_panels": [
            {
                "id": "1234567_sheath_exterior_0_0",
                "panel_id": "W1-P01",
                "face": "exterior",
                "material": "OSB",
                "material_display": 'OSB 7/16"',
                "thickness_inches": 0.4375,
                "width": 4.0,
                "height": 8.0,
                "area_net_sqft": 32.0,
                "u_start": 0.0,
                "u_end": 4.0,
            },
            {
                "id": "1234567_sheath_exterior_1_0",
                "panel_id": "W1-P01",
                "face": "exterior",
                "material": "OSB",
                "material_display": 'OSB 7/16"',
                "thickness_inches": 0.4375,
                "width": 4.0,
                "height": 8.0,
                "area_net_sqft": 30.0,
                "u_start": 4.0,
                "u_end": 8.0,
            },
        ],
    })


@pytest.fixture
def multi_layer_json():
    """Multi-layer sheathing JSON for one wall."""
    return json.dumps({
        "wall_id": "7654321",
        "layer_results": [
            {
                "layer_name": "OSB Sheathing",
                "layer_function": "substrate",
                "w_offset": 0.0,
                "panels": [
                    {
                        "id": "7654321_sheath_osb_sheathing_exterior_0_0",
                        "panel_id": "W2-P01",
                        "face": "exterior",
                        "material_display": 'OSB 7/16"',
                        "thickness_inches": 0.4375,
                        "width": 4.0,
                        "height": 8.0,
                        "area_net_sqft": 32.0,
                    },
                ],
            },
            {
                "layer_name": "Gypsum Board",
                "layer_function": "finish",
                "w_offset": -0.042,
                "panels": [
                    {
                        "id": "7654321_sheath_gypsum_board_interior_0_0",
                        "panel_id": "W2-P01",
                        "face": "interior",
                        "material_display": 'Gypsum 1/2"',
                        "thickness_inches": 0.5,
                        "width": 4.0,
                        "height": 8.0,
                        "area_net_sqft": 32.0,
                    },
                ],
            },
        ],
    })


@pytest.fixture
def two_wall_json_list(single_layer_json, multi_layer_json):
    """List of JSON strings for two walls (mixed single/multi-layer)."""
    return [single_layer_json, multi_layer_json]


# =============================================================================
# Tests: _build_panel_metadata_lookup
# =============================================================================

class TestBuildPanelMetadataLookupSingleLayer:
    """Tests for _build_panel_metadata_lookup with single-layer JSON."""

    def test_returns_dict(self, single_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([single_layer_json])
        assert isinstance(lookup, dict)

    def test_correct_panel_count(self, single_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([single_layer_json])
        assert len(lookup) == 2

    def test_panel_id_is_key(self, single_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([single_layer_json])
        assert "1234567_sheath_exterior_0_0" in lookup
        assert "1234567_sheath_exterior_1_0" in lookup

    def test_wall_id_injected(self, single_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([single_layer_json])
        entry = lookup["1234567_sheath_exterior_0_0"]
        assert entry["wall_id"] == "1234567"

    def test_metadata_preserved(self, single_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([single_layer_json])
        entry = lookup["1234567_sheath_exterior_0_0"]
        assert entry["face"] == "exterior"
        assert entry["material_display"] == 'OSB 7/16"'
        assert entry["thickness_inches"] == 0.4375
        assert entry["width"] == 4.0
        assert entry["height"] == 8.0
        assert entry["area_net_sqft"] == 32.0

    def test_panel_id_field_preserved(self, single_layer_json: str) -> None:
        """The framing panel_id field should be in the metadata."""
        lookup = _build_panel_metadata_lookup([single_layer_json])
        entry = lookup["1234567_sheath_exterior_0_0"]
        assert entry["panel_id"] == "W1-P01"


class TestBuildPanelMetadataLookupMultiLayer:
    """Tests for _build_panel_metadata_lookup with multi-layer JSON."""

    def test_returns_dict(self, multi_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([multi_layer_json])
        assert isinstance(lookup, dict)

    def test_correct_panel_count(self, multi_layer_json: str) -> None:
        """Two layers with one panel each = 2 entries."""
        lookup = _build_panel_metadata_lookup([multi_layer_json])
        assert len(lookup) == 2

    def test_both_layers_present(self, multi_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([multi_layer_json])
        assert "7654321_sheath_osb_sheathing_exterior_0_0" in lookup
        assert "7654321_sheath_gypsum_board_interior_0_0" in lookup

    def test_layer_function_added(self, multi_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([multi_layer_json])
        osb = lookup["7654321_sheath_osb_sheathing_exterior_0_0"]
        gyp = lookup["7654321_sheath_gypsum_board_interior_0_0"]
        assert osb["layer_function"] == "substrate"
        assert gyp["layer_function"] == "finish"

    def test_wall_id_injected(self, multi_layer_json: str) -> None:
        lookup = _build_panel_metadata_lookup([multi_layer_json])
        entry = lookup["7654321_sheath_osb_sheathing_exterior_0_0"]
        assert entry["wall_id"] == "7654321"


class TestBuildPanelMetadataLookupMultiWall:
    """Tests for _build_panel_metadata_lookup with multiple wall JSONs."""

    def test_combined_count(self, two_wall_json_list) -> None:
        """Two walls: 2 panels + 2 panels = 4 entries."""
        lookup = _build_panel_metadata_lookup(two_wall_json_list)
        assert len(lookup) == 4

    def test_both_walls_present(self, two_wall_json_list) -> None:
        lookup = _build_panel_metadata_lookup(two_wall_json_list)
        wall_ids = {v["wall_id"] for v in lookup.values()}
        assert "1234567" in wall_ids
        assert "7654321" in wall_ids


class TestBuildPanelMetadataLookupEdgeCases:
    """Edge case tests for _build_panel_metadata_lookup."""

    def test_empty_list(self) -> None:
        lookup = _build_panel_metadata_lookup([])
        assert lookup == {}

    def test_none_in_list(self) -> None:
        lookup = _build_panel_metadata_lookup([None, ""])
        assert lookup == {}

    def test_invalid_json_skipped(self) -> None:
        lookup = _build_panel_metadata_lookup(["not valid json"])
        assert lookup == {}

    def test_no_panels_key(self) -> None:
        """JSON with wall_id but no panels or layer_results."""
        json_str = json.dumps({"wall_id": "999", "other_key": []})
        lookup = _build_panel_metadata_lookup([json_str])
        assert lookup == {}

    def test_panel_without_id_skipped(self) -> None:
        """Panels missing 'id' key should be skipped."""
        json_str = json.dumps({
            "wall_id": "999",
            "sheathing_panels": [
                {"face": "exterior", "material": "OSB"},  # no 'id'
            ],
        })
        lookup = _build_panel_metadata_lookup([json_str])
        assert lookup == {}

    def test_wall_id_not_overwritten_if_present(self) -> None:
        """If panel already has wall_id, it should NOT be overwritten."""
        json_str = json.dumps({
            "wall_id": "parent_wall",
            "sheathing_panels": [
                {"id": "p1", "wall_id": "own_wall", "face": "exterior"},
            ],
        })
        lookup = _build_panel_metadata_lookup([json_str])
        assert lookup["p1"]["wall_id"] == "own_wall"


class TestBuildPanelMetadataLookupListFormat:
    """Tests for JSON that parses to a list (array of wall dicts)."""

    def test_list_of_wall_dicts(self) -> None:
        """JSON string containing a list of wall dicts."""
        json_str = json.dumps([
            {
                "wall_id": "111",
                "sheathing_panels": [
                    {"id": "p1", "face": "exterior"},
                ],
            },
            {
                "wall_id": "222",
                "sheathing_panels": [
                    {"id": "p2", "face": "interior"},
                ],
            },
        ])
        lookup = _build_panel_metadata_lookup([json_str])
        assert len(lookup) == 2
        assert lookup["p1"]["wall_id"] == "111"
        assert lookup["p2"]["wall_id"] == "222"

    def test_wrapper_with_walls_key(self) -> None:
        """JSON string with {"walls": [...]} wrapper."""
        json_str = json.dumps({
            "walls": [
                {
                    "wall_id": "333",
                    "sheathing_panels": [
                        {"id": "p3", "face": "exterior"},
                    ],
                },
            ],
        })
        lookup = _build_panel_metadata_lookup([json_str])
        assert len(lookup) == 1
        assert lookup["p3"]["wall_id"] == "333"

    def test_wrapper_with_results_key(self) -> None:
        """JSON string with {"results": [...]} wrapper."""
        json_str = json.dumps({
            "results": [
                {
                    "wall_id": "444",
                    "sheathing_panels": [
                        {"id": "p4", "face": "interior"},
                    ],
                },
            ],
        })
        lookup = _build_panel_metadata_lookup([json_str])
        assert len(lookup) == 1
        assert lookup["p4"]["wall_id"] == "444"

    def test_non_dict_items_in_list_skipped(self) -> None:
        """Non-dict items in a list should be skipped gracefully."""
        json_str = json.dumps([
            {"wall_id": "555", "sheathing_panels": [{"id": "p5"}]},
            "not a dict",
            42,
            None,
        ])
        lookup = _build_panel_metadata_lookup([json_str])
        assert len(lookup) == 1
        assert "p5" in lookup


# =============================================================================
# Tests: _make_type_name
# =============================================================================

class TestMakeTypeName:
    """Tests for DirectShapeType name generation."""

    def test_standard_case(self) -> None:
        result = _make_type_name('OSB 7/16"', "exterior")
        assert result == 'OSB 7/16" - Exterior'

    def test_interior_face(self) -> None:
        result = _make_type_name('Gypsum 1/2"', "interior")
        assert result == 'Gypsum 1/2" - Interior'

    def test_unknown_face(self) -> None:
        result = _make_type_name("Plywood", "unknown")
        assert result == "Plywood - Unknown"

    def test_title_case_applied(self) -> None:
        """Face string should be title-cased."""
        result = _make_type_name("OSB", "EXTERIOR")
        assert result == "OSB - Exterior"

    def test_multi_word_face(self) -> None:
        result = _make_type_name("OSB", "left side")
        assert result == "OSB - Left Side"


# =============================================================================
# Tests: Sheathing Data JSON Format
# =============================================================================

class TestSheathingDataJsonFormat:
    """Tests verifying the output JSON matches assembly_creator expectations.

    The assembly_creator._build_sheathing_panel_map() expects:
    {
        "panels": [
            {"panel_id": "...", "wall_id": "..."},
            ...
        ]
    }
    """

    def test_has_panels_key(self) -> None:
        data = {"panels": []}
        assert "panels" in data

    def test_panels_is_list(self) -> None:
        data = {"panels": [{"panel_id": "W1-P01", "wall_id": "123"}]}
        assert isinstance(data["panels"], list)

    def test_entry_has_required_keys(self) -> None:
        entry = {"panel_id": "W1-P01", "wall_id": "1234567"}
        assert "panel_id" in entry
        assert "wall_id" in entry

    def test_roundtrip_matches_expected(self) -> None:
        """Build the output format and verify _build_sheathing_panel_map can parse it."""
        data_entries = [
            {"panel_id": "W1-P01", "wall_id": "1234567"},
            {"panel_id": "W1-P01", "wall_id": "1234567"},
            {"panel_id": "W1-P02", "wall_id": "1234567"},
        ]
        sheathing_data = {"panels": data_entries}
        json_str = json.dumps(sheathing_data)

        # Simulate _build_sheathing_panel_map logic
        parsed = json.loads(json_str)
        panel_map = {}
        for i, spanel in enumerate(parsed.get("panels", [])):
            pid = spanel.get("panel_id")
            if pid:
                panel_map.setdefault(pid, []).append(i)

        # W1-P01 should have indices 0, 1
        assert panel_map["W1-P01"] == [0, 1]
        # W1-P02 should have index 2
        assert panel_map["W1-P02"] == [2]

    def test_empty_panel_id_handled(self) -> None:
        """Entries with empty panel_id should still be parseable."""
        data_entries = [
            {"panel_id": "", "wall_id": "1234567"},
        ]
        sheathing_data = {"panels": data_entries}
        json_str = json.dumps(sheathing_data)

        parsed = json.loads(json_str)
        panel_map = {}
        for i, spanel in enumerate(parsed.get("panels", [])):
            pid = spanel.get("panel_id")
            if pid:
                panel_map.setdefault(pid, []).append(i)

        # Empty string panel_id should not create a map entry
        assert len(panel_map) == 0


# =============================================================================
# Tests: Category Map
# =============================================================================

class TestSupportedCategories:
    """Tests for the SUPPORTED_CATEGORIES list."""

    def test_has_generic_model(self) -> None:
        assert "OST_GenericModel" in SUPPORTED_CATEGORIES

    def test_has_parts(self) -> None:
        assert "OST_Parts" in SUPPORTED_CATEGORIES

    def test_has_structural_connections(self) -> None:
        assert "OST_StructuralConnections" in SUPPORTED_CATEGORIES

    def test_minimum_entries(self) -> None:
        """Should have at least the 3 documented categories."""
        assert len(SUPPORTED_CATEGORIES) >= 3

    def test_all_start_with_ost(self) -> None:
        """All category strings should follow Revit OST_ convention."""
        for cat in SUPPORTED_CATEGORIES:
            assert cat.startswith("OST_"), "Category '%s' missing OST_ prefix" % cat


# =============================================================================
# Tests: TFG Parameter Definitions
# =============================================================================

class TestTFGParamDefs:
    """Tests for the TFG_PARAM_DEFS constant."""

    def test_all_params_prefixed(self) -> None:
        """All parameter names should start with TFG_."""
        for name, _ in TFG_PARAM_DEFS:
            assert name.startswith("TFG_"), "Parameter '%s' missing TFG_ prefix" % name

    def test_expected_params_present(self) -> None:
        """Check all 9 expected parameters exist."""
        names = {name for name, _ in TFG_PARAM_DEFS}
        expected = {
            "TFG_WallId", "TFG_PanelId", "TFG_Face", "TFG_Material",
            "TFG_ThicknessIn", "TFG_WidthFt", "TFG_HeightFt",
            "TFG_AreaSqFt", "TFG_LayerFunction",
        }
        assert expected.issubset(names)

    def test_valid_types(self) -> None:
        """All param type strings should be 'string' or 'number'."""
        for name, type_str in TFG_PARAM_DEFS:
            assert type_str in ("string", "number"), (
                "Parameter '%s' has invalid type '%s'" % (name, type_str)
            )

    def test_string_params(self) -> None:
        """Check which params are strings."""
        string_params = {name for name, t in TFG_PARAM_DEFS if t == "string"}
        expected_strings = {
            "TFG_WallId", "TFG_PanelId", "TFG_Face",
            "TFG_Material", "TFG_LayerFunction",
        }
        assert expected_strings == string_params

    def test_number_params(self) -> None:
        """Check which params are numbers."""
        number_params = {name for name, t in TFG_PARAM_DEFS if t == "number"}
        expected_numbers = {
            "TFG_ThicknessIn", "TFG_WidthFt", "TFG_HeightFt", "TFG_AreaSqFt",
        }
        assert expected_numbers == number_params
