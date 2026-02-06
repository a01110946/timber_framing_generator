# File: tests/config/test_assembly_resolver.py

"""Tests for assembly resolution strategy.

Tests cover:
- All 4 resolution modes (auto, revit_only, catalog, custom)
- Catalog keyword matching with various Revit Wall Type name patterns
- Custom map with string keys and inline dict values
- Confidence scoring
- Batch resolution and summary
- Edge cases (empty data, invalid modes, unmapped types)
"""

import pytest

from src.timber_framing_generator.config.assembly_resolver import (
    AssemblyResolution,
    resolve_assembly,
    resolve_all_walls,
    summarize_resolutions,
    match_wall_type_to_catalog,
    _score_match,
    _has_explicit_assembly,
    _infer_assembly_from_thickness,
    _lookup_custom_map,
    CATALOG_KEYWORDS,
    VALID_MODES,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_wall(
    wall_type: str = "",
    wall_assembly: dict = None,
    is_exterior: bool = False,
    wall_thickness: float = 0.0,
    wall_id: str = "w1",
) -> dict:
    """Create a minimal wall dict for testing."""
    wall = {
        "wall_id": wall_id,
        "wall_type": wall_type,
        "is_exterior": is_exterior,
        "wall_thickness": wall_thickness,
        "wall_length": 12.0,
        "wall_height": 8.0,
        "openings": [],
    }
    if wall_assembly is not None:
        wall["wall_assembly"] = wall_assembly
    return wall


def _make_revit_assembly(name: str = "Revit Wall") -> dict:
    """Create a minimal Revit-extracted assembly dict."""
    return {
        "name": name,
        "source": "revit",
        "layers": [
            {"name": "ext_finish", "function": "finish", "side": "exterior", "thickness": 0.026},
            {"name": "ext_substrate", "function": "substrate", "side": "exterior", "thickness": 0.036},
            {"name": "core", "function": "structure", "side": "core", "thickness": 0.292},
            {"name": "int_finish", "function": "finish", "side": "interior", "thickness": 0.042},
        ],
    }


def _make_single_layer_assembly() -> dict:
    """Assembly with only one layer (not considered explicit)."""
    return {
        "name": "Single",
        "source": "default",
        "layers": [
            {"name": "core", "function": "structure", "side": "core", "thickness": 0.292},
        ],
    }


# =============================================================================
# AssemblyResolution Tests
# =============================================================================


class TestAssemblyResolution:
    """Tests for the AssemblyResolution dataclass."""

    def test_to_metadata(self) -> None:
        res = AssemblyResolution(
            assembly={"name": "test"},
            source="catalog",
            confidence=0.8,
            notes="Matched by keywords",
            assembly_name="2x6_exterior",
        )
        meta = res.to_metadata()
        assert meta["assembly_source"] == "catalog"
        assert meta["assembly_confidence"] == 0.8
        assert meta["assembly_notes"] == "Matched by keywords"
        assert meta["assembly_name"] == "2x6_exterior"


# =============================================================================
# Catalog Keyword Matching Tests
# =============================================================================


class TestMatchWallTypeToCatalog:
    """Tests for fuzzy Wall Type name -> catalog matching."""

    def test_basic_wall_2x6_exterior(self) -> None:
        result = match_wall_type_to_catalog("Basic Wall - 2x6 Exterior")
        assert result is not None
        key, conf = result
        assert key == "2x6_exterior"
        assert conf >= 0.7

    def test_basic_wall_2x4_exterior(self) -> None:
        result = match_wall_type_to_catalog("Basic Wall - 2x4 Exterior")
        assert result is not None
        key, conf = result
        assert key == "2x4_exterior"
        assert conf >= 0.7

    def test_generic_interior_partition(self) -> None:
        result = match_wall_type_to_catalog('Generic - 4" Interior Partition')
        assert result is not None
        key, conf = result
        assert key == "2x4_interior"
        assert conf >= 0.6

    def test_simple_exterior(self) -> None:
        """Just the word 'exterior' should match an exterior assembly."""
        result = match_wall_type_to_catalog("Exterior Wall")
        assert result is not None
        key, conf = result
        assert "exterior" in key

    def test_simple_interior(self) -> None:
        result = match_wall_type_to_catalog("Interior Partition")
        assert result is not None
        key, conf = result
        assert key == "2x4_interior"

    def test_no_match_cryptic_name(self) -> None:
        """Cryptic names like 'CW 102-50-100p' should not match."""
        result = match_wall_type_to_catalog("CW 102-50-100p")
        assert result is None

    def test_no_match_empty(self) -> None:
        assert match_wall_type_to_catalog("") is None
        assert match_wall_type_to_catalog(None) is None

    def test_case_insensitive(self) -> None:
        result = match_wall_type_to_catalog("BASIC WALL - 2X6 EXTERIOR")
        assert result is not None
        assert result[0] == "2x6_exterior"

    def test_negative_keywords_prevent_wrong_match(self) -> None:
        """2x6 in name should prevent matching 2x4_exterior."""
        result = match_wall_type_to_catalog("2x6 Exterior Insulated")
        assert result is not None
        key, _ = result
        assert key == "2x6_exterior"  # Not 2x4_exterior

    def test_2x4_with_size_hint_higher_confidence(self) -> None:
        """Size hint match should give higher confidence than base."""
        result_with_size = match_wall_type_to_catalog("2x4 Exterior Wall")
        result_without = match_wall_type_to_catalog("Exterior Wall")
        assert result_with_size is not None
        assert result_without is not None
        assert result_with_size[1] > result_without[1]


class TestScoreMatch:
    """Tests for the internal _score_match function."""

    def test_required_all_present(self) -> None:
        score = _score_match("exterior wall 2x4", CATALOG_KEYWORDS["2x4_exterior"])
        assert score >= 0.6

    def test_required_missing(self) -> None:
        score = _score_match("interior wall", CATALOG_KEYWORDS["2x4_exterior"])
        assert score == 0.0

    def test_negative_disqualifies(self) -> None:
        score = _score_match("2x6 exterior wall", CATALOG_KEYWORDS["2x4_exterior"])
        assert score == 0.0

    def test_required_any(self) -> None:
        score_int = _score_match("interior wall", CATALOG_KEYWORDS["2x4_interior"])
        score_part = _score_match("partition wall", CATALOG_KEYWORDS["2x4_interior"])
        assert score_int >= 0.6
        assert score_part >= 0.6


# =============================================================================
# Has Explicit Assembly Tests
# =============================================================================


class TestHasExplicitAssembly:
    """Tests for _has_explicit_assembly check."""

    def test_revit_assembly_is_explicit(self) -> None:
        wall = _make_wall(wall_assembly=_make_revit_assembly())
        assert _has_explicit_assembly(wall) is True

    def test_single_layer_not_explicit(self) -> None:
        wall = _make_wall(wall_assembly=_make_single_layer_assembly())
        assert _has_explicit_assembly(wall) is False

    def test_no_assembly_not_explicit(self) -> None:
        wall = _make_wall()
        assert _has_explicit_assembly(wall) is False

    def test_default_source_not_explicit(self) -> None:
        assembly = _make_revit_assembly()
        assembly["source"] = "default"
        wall = _make_wall(wall_assembly=assembly)
        assert _has_explicit_assembly(wall) is False


# =============================================================================
# Auto Mode Tests
# =============================================================================


class TestResolveAutoMode:
    """Tests for auto resolution mode."""

    def test_explicit_assembly_used_first(self) -> None:
        """Revit assembly takes priority over everything."""
        wall = _make_wall(
            wall_type="2x6 Exterior",  # Would match catalog
            wall_assembly=_make_revit_assembly("Custom Revit"),
            is_exterior=True,
        )
        res = resolve_assembly(wall, mode="auto")
        assert res.source == "explicit"
        assert res.confidence == 1.0

    def test_catalog_fallback_when_no_revit(self) -> None:
        wall = _make_wall(wall_type="Basic Wall - 2x6 Exterior", is_exterior=True)
        res = resolve_assembly(wall, mode="auto")
        assert res.source == "catalog"
        assert res.confidence >= 0.6
        assert res.assembly_name == "2x6_exterior"

    def test_inferred_fallback_when_no_catalog_match(self) -> None:
        wall = _make_wall(
            wall_type="CW 102-50-100p",
            is_exterior=True,
            wall_thickness=0.6,
        )
        res = resolve_assembly(wall, mode="auto")
        assert res.source == "inferred"
        assert res.confidence >= 0.3

    def test_default_fallback_exterior(self) -> None:
        wall = _make_wall(is_exterior=True)
        res = resolve_assembly(wall, mode="auto")
        assert res.source in ("inferred", "default")
        assert "exterior" in res.assembly_name

    def test_default_fallback_interior(self) -> None:
        wall = _make_wall(is_exterior=False)
        res = resolve_assembly(wall, mode="auto")
        assert res.source in ("inferred", "default")
        assert "interior" in res.assembly_name

    def test_assembly_has_layers(self) -> None:
        """Resolved assembly should have actual layer data."""
        wall = _make_wall(wall_type="2x4 Exterior", is_exterior=True)
        res = resolve_assembly(wall, mode="auto")
        assert res.assembly is not None
        assert len(res.assembly.get("layers", [])) >= 2


# =============================================================================
# Revit-Only Mode Tests
# =============================================================================


class TestResolveRevitOnlyMode:
    """Tests for revit_only resolution mode."""

    def test_explicit_assembly_used(self) -> None:
        wall = _make_wall(wall_assembly=_make_revit_assembly())
        res = resolve_assembly(wall, mode="revit_only")
        assert res.source == "explicit"
        assert res.confidence == 1.0

    def test_no_assembly_skipped(self) -> None:
        wall = _make_wall(wall_type="2x6 Exterior", is_exterior=True)
        res = resolve_assembly(wall, mode="revit_only")
        assert res.source == "skipped"
        assert res.assembly is None
        assert res.confidence == 0.0

    def test_single_layer_skipped(self) -> None:
        """Single-layer assemblies are not considered explicit."""
        wall = _make_wall(wall_assembly=_make_single_layer_assembly())
        res = resolve_assembly(wall, mode="revit_only")
        assert res.source == "skipped"


# =============================================================================
# Catalog Mode Tests
# =============================================================================


class TestResolveCatalogMode:
    """Tests for catalog resolution mode."""

    def test_ignores_revit_assembly(self) -> None:
        """Even with Revit data, catalog mode uses name matching."""
        wall = _make_wall(
            wall_type="2x6 Exterior",
            wall_assembly=_make_revit_assembly("Revit Assembly"),
            is_exterior=True,
        )
        res = resolve_assembly(wall, mode="catalog")
        assert res.source == "catalog"
        assert res.assembly_name == "2x6_exterior"

    def test_no_match_uses_inference(self) -> None:
        wall = _make_wall(
            wall_type="CW 102-50-100p",
            is_exterior=True,
            wall_thickness=0.6,
        )
        res = resolve_assembly(wall, mode="catalog")
        assert res.source == "inferred"

    def test_interior_catalog_match(self) -> None:
        wall = _make_wall(wall_type="Interior Partition")
        res = resolve_assembly(wall, mode="catalog")
        assert res.source == "catalog"
        assert res.assembly_name == "2x4_interior"


# =============================================================================
# Custom Mode Tests
# =============================================================================


class TestResolveCustomMode:
    """Tests for custom resolution mode with per-Wall-Type mappings."""

    def test_string_value_maps_to_catalog(self) -> None:
        """String value in custom map should resolve to catalog assembly."""
        wall = _make_wall(wall_type="My Custom 2x6")
        custom_map = {"My Custom 2x6": "2x6_exterior"}
        res = resolve_assembly(wall, mode="custom", custom_map=custom_map)
        assert res.source == "custom"
        assert res.confidence == 1.0
        assert res.assembly is not None
        assert res.assembly_name == "2x6_exterior"

    def test_dict_value_used_inline(self) -> None:
        """Dict value in custom map should be used as inline assembly."""
        wall = _make_wall(wall_type="Special Wall")
        custom_assembly = {
            "name": "special",
            "layers": [
                {"name": "ext", "function": "finish", "side": "exterior", "thickness": 0.05},
                {"name": "core", "function": "structure", "side": "core", "thickness": 0.3},
            ],
        }
        custom_map = {"Special Wall": custom_assembly}
        res = resolve_assembly(wall, mode="custom", custom_map=custom_map)
        assert res.source == "custom"
        assert res.assembly is not None
        assert len(res.assembly["layers"]) == 2

    def test_unmapped_type_falls_back_to_auto(self) -> None:
        """Wall Types not in the custom map fall back to auto behavior."""
        wall = _make_wall(wall_type="2x4 Exterior", is_exterior=True)
        custom_map = {"Other Wall": "2x6_exterior"}
        res = resolve_assembly(wall, mode="custom", custom_map=custom_map)
        # Falls back to auto, which does catalog match
        assert res.source in ("catalog", "inferred", "default")

    def test_case_insensitive_lookup(self) -> None:
        wall = _make_wall(wall_type="My Custom Wall")
        custom_map = {"my custom wall": "2x4_interior"}
        res = resolve_assembly(wall, mode="custom", custom_map=custom_map)
        assert res.source == "custom"

    def test_invalid_catalog_key_returns_none(self) -> None:
        """Invalid catalog key in custom map should not crash."""
        wall = _make_wall(wall_type="Bad Key Wall")
        custom_map = {"Bad Key Wall": "nonexistent_key"}
        res = resolve_assembly(wall, mode="custom", custom_map=custom_map)
        # Falls back to auto since custom lookup returns None
        assert res.source != "custom"

    def test_empty_custom_map_falls_back(self) -> None:
        wall = _make_wall(wall_type="Any Wall", is_exterior=True)
        res = resolve_assembly(wall, mode="custom", custom_map={})
        assert res.source in ("catalog", "inferred", "default")

    def test_multiple_wall_types_mapped(self) -> None:
        """Different wall types should resolve to different assemblies."""
        custom_map = {
            "Exterior Framed": "2x6_exterior",
            "Interior Partition": "2x4_interior",
        }
        wall_ext = _make_wall(wall_type="Exterior Framed", wall_id="w1")
        wall_int = _make_wall(wall_type="Interior Partition", wall_id="w2")

        res_ext = resolve_assembly(wall_ext, mode="custom", custom_map=custom_map)
        res_int = resolve_assembly(wall_int, mode="custom", custom_map=custom_map)

        assert res_ext.assembly_name == "2x6_exterior"
        assert res_int.assembly_name == "2x4_interior"


# =============================================================================
# Batch Resolution Tests
# =============================================================================


class TestResolveAllWalls:
    """Tests for resolve_all_walls batch processing."""

    def test_enriches_all_walls(self) -> None:
        walls = [
            _make_wall(wall_type="2x6 Exterior", is_exterior=True, wall_id="w1"),
            _make_wall(wall_type="Interior Partition", wall_id="w2"),
        ]
        enriched = resolve_all_walls(walls, mode="auto")
        assert len(enriched) == 2

        for wall in enriched:
            assert "assembly_source" in wall
            assert "assembly_confidence" in wall
            assert "assembly_notes" in wall
            assert "assembly_name" in wall

    def test_does_not_mutate_originals(self) -> None:
        walls = [_make_wall(wall_type="2x6 Exterior", is_exterior=True)]
        original_keys = set(walls[0].keys())
        resolve_all_walls(walls, mode="auto")
        assert set(walls[0].keys()) == original_keys

    def test_sets_wall_assembly_when_resolved(self) -> None:
        """Enriched walls should have wall_assembly set."""
        walls = [_make_wall(wall_type="2x4 Exterior", is_exterior=True)]
        enriched = resolve_all_walls(walls, mode="auto")
        assert "wall_assembly" in enriched[0]
        assert enriched[0]["wall_assembly"] is not None

    def test_custom_mode_with_batch(self) -> None:
        custom_map = {"Type A": "2x6_exterior", "Type B": "2x4_interior"}
        walls = [
            _make_wall(wall_type="Type A", wall_id="w1"),
            _make_wall(wall_type="Type B", wall_id="w2"),
            _make_wall(wall_type="Unmapped", wall_id="w3", is_exterior=True),
        ]
        enriched = resolve_all_walls(walls, mode="custom", custom_map=custom_map)

        assert enriched[0]["assembly_source"] == "custom"
        assert enriched[1]["assembly_source"] == "custom"
        assert enriched[2]["assembly_source"] != "custom"  # Falls back


class TestSummarizeResolutions:
    """Tests for summarize_resolutions."""

    def test_counts_by_source(self) -> None:
        walls = [
            {"assembly_source": "explicit", "assembly_confidence": 1.0},
            {"assembly_source": "catalog", "assembly_confidence": 0.8},
            {"assembly_source": "catalog", "assembly_confidence": 0.7},
            {"assembly_source": "default", "assembly_confidence": 0.1},
        ]
        summary = summarize_resolutions(walls)
        assert summary["total_walls"] == 4
        assert summary["by_source"]["explicit"] == 1
        assert summary["by_source"]["catalog"] == 2
        assert summary["by_source"]["default"] == 1

    def test_average_confidence(self) -> None:
        walls = [
            {"assembly_source": "explicit", "assembly_confidence": 1.0},
            {"assembly_source": "default", "assembly_confidence": 0.0},
        ]
        summary = summarize_resolutions(walls)
        assert summary["average_confidence"] == 0.5

    def test_empty_list(self) -> None:
        summary = summarize_resolutions([])
        assert summary["total_walls"] == 0
        assert summary["average_confidence"] == 0.0


# =============================================================================
# Thickness Inference Tests
# =============================================================================


class TestInferFromThickness:
    """Tests for thickness-based assembly inference."""

    def test_thick_exterior_infers_2x6(self) -> None:
        result = _infer_assembly_from_thickness(
            {"is_exterior": True, "wall_thickness": 0.6}
        )
        assert result is not None
        key, _ = result
        assert key == "2x6_exterior"

    def test_thin_exterior_infers_2x4(self) -> None:
        result = _infer_assembly_from_thickness(
            {"is_exterior": True, "wall_thickness": 0.4}
        )
        assert result is not None
        key, _ = result
        assert key == "2x4_exterior"

    def test_interior_infers_2x4_interior(self) -> None:
        result = _infer_assembly_from_thickness(
            {"is_exterior": False, "wall_thickness": 0.3}
        )
        assert result is not None
        key, _ = result
        assert key == "2x4_interior"

    def test_confidence_is_moderate(self) -> None:
        result = _infer_assembly_from_thickness(
            {"is_exterior": True, "wall_thickness": 0.4}
        )
        assert result is not None
        _, conf = result
        assert 0.3 <= conf <= 0.5


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and invalid inputs."""

    def test_invalid_mode_defaults_to_auto(self) -> None:
        wall = _make_wall(wall_type="2x4 Exterior", is_exterior=True)
        res = resolve_assembly(wall, mode="invalid_mode")
        assert res.source in ("catalog", "inferred", "default")

    def test_none_custom_map_ok(self) -> None:
        wall = _make_wall(wall_type="2x4 Exterior", is_exterior=True)
        res = resolve_assembly(wall, mode="custom", custom_map=None)
        assert res.source in ("catalog", "inferred", "default")

    def test_empty_wall_data(self) -> None:
        wall = _make_wall()
        res = resolve_assembly(wall, mode="auto")
        assert res.assembly is not None  # Gets a default
        assert res.source in ("inferred", "default")

    def test_revit_only_with_notes(self) -> None:
        """Skipped walls should have descriptive notes."""
        wall = _make_wall(wall_type="My Wall Type")
        res = resolve_assembly(wall, mode="revit_only")
        assert "My Wall Type" in res.notes
        assert "revit_only" in res.notes
