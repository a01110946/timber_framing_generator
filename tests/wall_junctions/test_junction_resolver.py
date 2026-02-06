# File: tests/wall_junctions/test_junction_resolver.py

"""Tests for wall junction resolution and per-layer adjustments.

Tests cover:
- Butt join resolution (primary extends, secondary trims)
- T-intersection resolution (continuous wall unchanged, terminating trims)
- Miter join calculation
- Priority strategies (longer_wall, exterior_first, alternate)
- User overrides
- Default layer thickness scaling
- Full pipeline (analyze_junctions)
"""

import pytest
import math

from src.timber_framing_generator.wall_junctions.junction_resolver import (
    analyze_junctions,
    resolve_all_junctions,
    build_wall_layers_map,
    build_default_wall_layers,
    build_wall_adjustments_map,
    _determine_priority,
    _calculate_butt_adjustments,
    _calculate_butt_adjustments_v2,
)
from src.timber_framing_generator.wall_junctions.junction_detector import (
    build_junction_graph,
)
from src.timber_framing_generator.wall_junctions.junction_types import (
    JunctionType,
    JoinType,
    AdjustmentType,
    WallConnection,
    WallLayerInfo,
    WallLayer,
    WallAssemblyDef,
    LayerFunction,
    LayerSide,
    JunctionGraph,
)


# =============================================================================
# Default Layer Tests
# =============================================================================


class TestDefaultWallLayers:
    """Tests for build_default_wall_layers."""

    def test_default_thickness_matches_assembly(self):
        # Default assembly: ext=0.0625, core=0.2917, int=0.0417
        layers = build_default_wall_layers("test", 0.3958)
        assert abs(layers.total_thickness - 0.3958) < 0.001
        assert abs(layers.exterior_thickness - 0.0625) < 0.001
        assert abs(layers.core_thickness - 0.2917) < 0.001
        assert abs(layers.interior_thickness - 0.0417) < 0.001
        assert layers.source == "default"

    def test_scaled_thickness(self):
        # Double the default thickness → all layers should double
        default_total = 0.0625 + 0.2917 + 0.0417  # ~0.3958
        layers = build_default_wall_layers("test", default_total * 2)
        assert abs(layers.exterior_thickness - 0.0625 * 2) < 0.001
        assert abs(layers.core_thickness - 0.2917 * 2) < 0.001
        assert abs(layers.interior_thickness - 0.0417 * 2) < 0.001

    def test_layers_sum_to_total(self):
        layers = build_default_wall_layers("test", 0.5)
        total = (
            layers.exterior_thickness
            + layers.core_thickness
            + layers.interior_thickness
        )
        assert abs(total - 0.5) < 0.001


class TestBuildWallLayersMap:
    """Tests for build_wall_layers_map."""

    def test_builds_layers_for_all_walls(self, l_corner_walls):
        layers = build_wall_layers_map(l_corner_walls)
        assert "wall_A" in layers
        assert "wall_B" in layers

    def test_override_applied(self, l_corner_walls):
        overrides = {
            "wall_A": {
                "exterior_thickness": 0.1,
                "core_thickness": 0.3,
                "interior_thickness": 0.05,
            }
        }
        layers = build_wall_layers_map(l_corner_walls, overrides)
        assert layers["wall_A"].source == "override"
        assert abs(layers["wall_A"].exterior_thickness - 0.1) < 0.001
        assert layers["wall_B"].source == "default"


# =============================================================================
# Priority Tests
# =============================================================================


class TestDeterminePriority:
    """Tests for _determine_priority."""

    def _make_conn(self, wall_id, length=10.0, is_exterior=True):
        return WallConnection(
            wall_id=wall_id,
            end="end",
            direction=(1, 0, 0),
            angle_at_junction=0,
            wall_thickness=0.3958,
            wall_length=length,
            is_exterior=is_exterior,
        )

    def test_longer_wall_strategy(self):
        conn_long = self._make_conn("long", length=20.0)
        conn_short = self._make_conn("short", length=10.0)
        primary, secondary = _determine_priority(conn_long, conn_short, "longer_wall")
        assert primary.wall_id == "long"
        assert secondary.wall_id == "short"

    def test_longer_wall_reversed(self):
        conn_long = self._make_conn("long", length=20.0)
        conn_short = self._make_conn("short", length=10.0)
        # Pass short first — should still pick long as primary
        primary, secondary = _determine_priority(conn_short, conn_long, "longer_wall")
        assert primary.wall_id == "long"

    def test_exterior_first_strategy(self):
        conn_ext = self._make_conn("ext", is_exterior=True, length=5.0)
        conn_int = self._make_conn("int", is_exterior=False, length=20.0)
        primary, secondary = _determine_priority(conn_ext, conn_int, "exterior_first")
        assert primary.wall_id == "ext"

    def test_alternate_strategy(self):
        conn_a = self._make_conn("aaa")
        conn_b = self._make_conn("bbb")
        primary, _ = _determine_priority(conn_a, conn_b, "alternate")
        assert primary.wall_id == "aaa"  # "aaa" < "bbb"


# =============================================================================
# Butt Join Adjustment Tests
# =============================================================================


class TestButtAdjustments:
    """Tests for butt join per-layer adjustments."""

    def test_l_corner_butt_adjustments(self, l_corner_walls):
        graph = analyze_junctions(l_corner_walls, default_join_type="butt")

        # Find the L-corner junction
        l_corners = [
            n for n in graph.nodes.values()
            if n.junction_type == JunctionType.L_CORNER
        ]
        assert len(l_corners) == 1

        # Should have resolutions
        assert len(graph.resolutions) >= 1

        # Both walls should have adjustments
        assert len(graph.wall_adjustments) >= 1

    def test_primary_wall_extends(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )

        # wall_A is longer (20 ft vs 15 ft), so it should be primary (extends)
        resolution = graph.resolutions[0]
        assert resolution.primary_wall_id == "wall_A"
        assert resolution.join_type == JoinType.BUTT

        # wall_A should have EXTEND adjustments
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        extend_adjs = [a for a in wall_a_adjs if a.adjustment_type == AdjustmentType.EXTEND]
        assert len(extend_adjs) > 0

    def test_secondary_wall_trims(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )

        # wall_B is shorter, should be secondary (trims)
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        trim_adjs = [a for a in wall_b_adjs if a.adjustment_type == AdjustmentType.TRIM]
        assert len(trim_adjs) > 0

    def test_adjustment_amounts_are_positive(self, l_corner_walls):
        graph = analyze_junctions(l_corner_walls)

        for wall_id, adjs in graph.wall_adjustments.items():
            for adj in adjs:
                assert adj.amount > 0, (
                    f"Adjustment for {wall_id}/{adj.end}/{adj.layer_name} "
                    f"has non-positive amount: {adj.amount}"
                )

    def test_three_layers_per_wall(self, l_corner_walls):
        graph = analyze_junctions(l_corner_walls)

        for resolution in graph.resolutions:
            # Each resolution should have 3 adjustments per wall (core, ext, int)
            primary_adjs = [
                a for a in resolution.layer_adjustments
                if a.wall_id == resolution.primary_wall_id
            ]
            secondary_adjs = [
                a for a in resolution.layer_adjustments
                if a.wall_id == resolution.secondary_wall_id
            ]
            assert len(primary_adjs) == 3
            assert len(secondary_adjs) == 3

            # Check all three layers present
            primary_layers = {a.layer_name for a in primary_adjs}
            assert primary_layers == {"core", "exterior", "interior"}

    def test_different_thickness_asymmetric_adjustments(
        self, different_thickness_walls
    ):
        graph = analyze_junctions(
            different_thickness_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )

        # wall_thick (20 ft) should be primary, wall_thin (15 ft) secondary
        res = graph.resolutions[0]
        assert res.primary_wall_id == "wall_thick"

        # Primary core extends by secondary.core/2
        thick_adjs = graph.get_adjustments_for_wall("wall_thick")
        core_extend = [
            a for a in thick_adjs
            if a.layer_name == "core" and a.adjustment_type == AdjustmentType.EXTEND
        ]
        assert len(core_extend) == 1

        # Secondary core trims by primary.core/2
        thin_adjs = graph.get_adjustments_for_wall("wall_thin")
        core_trim = [
            a for a in thin_adjs
            if a.layer_name == "core" and a.adjustment_type == AdjustmentType.TRIM
        ]
        assert len(core_trim) == 1

        # Amounts should differ because thicknesses differ
        # Primary extends by secondary's half-core, secondary trims by primary's half-core
        # These should NOT be equal since thicknesses differ
        assert core_extend[0].amount != core_trim[0].amount


# =============================================================================
# T-Intersection Tests
# =============================================================================


class TestTIntersection:
    """Tests for T-intersection resolution."""

    def test_t_intersection_detected(self, t_intersection_walls):
        graph = analyze_junctions(t_intersection_walls)

        t_nodes = [
            n for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        ]
        assert len(t_nodes) == 1

    def test_continuous_wall_is_primary(self, t_intersection_walls):
        graph = analyze_junctions(t_intersection_walls)

        # wall_A is continuous, wall_B terminates
        t_resolutions = [
            r for r in graph.resolutions
            if any(
                n.junction_type == JunctionType.T_INTERSECTION
                for n in graph.nodes.values()
                if n.id == r.junction_id
            )
        ]
        assert len(t_resolutions) == 1
        assert t_resolutions[0].primary_wall_id == "wall_A"
        assert t_resolutions[0].secondary_wall_id == "wall_B"

    def test_terminating_wall_trims(self, t_intersection_walls):
        graph = analyze_junctions(t_intersection_walls)

        # wall_B (terminating) should have trim adjustments
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        assert len(wall_b_adjs) > 0
        assert all(a.adjustment_type == AdjustmentType.TRIM for a in wall_b_adjs)

    def test_continuous_wall_no_adjustments(self, t_intersection_walls):
        graph = analyze_junctions(t_intersection_walls)

        # wall_A (continuous) should NOT have adjustments at the T-junction
        # (it may have free-end adjustments at its actual endpoints)
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        # Filter to T-intersection adjustments only
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        t_adjs_for_a = [
            a for a in wall_a_adjs if a.junction_id in t_junction_ids
        ]
        assert len(t_adjs_for_a) == 0


# =============================================================================
# Miter Join Tests
# =============================================================================


class TestMiterJoin:
    """Tests for miter join resolution."""

    def test_miter_at_90_degrees(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls, default_join_type="miter"
        )

        miter_res = [r for r in graph.resolutions if r.join_type == JoinType.MITER]
        assert len(miter_res) == 1

        # All adjustments should be MITER type
        for adj in miter_res[0].layer_adjustments:
            assert adj.adjustment_type == AdjustmentType.MITER
            assert adj.miter_angle is not None
            # For 90° corner, miter angle should be ~45°
            assert abs(adj.miter_angle - 45.0) < 5.0

    def test_both_walls_get_miter_adjustments(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls, default_join_type="miter"
        )

        # Both walls should have adjustments (miter affects both)
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        assert len(wall_a_adjs) > 0
        assert len(wall_b_adjs) > 0


# =============================================================================
# User Override Tests
# =============================================================================


class TestUserOverrides:
    """Tests for user override functionality."""

    def test_override_join_type(self, l_corner_walls):
        nodes = build_junction_graph(l_corner_walls)
        junction_id = list(nodes.keys())[0]

        # Find the L-corner junction
        l_corner_ids = [
            nid for nid, n in nodes.items()
            if n.junction_type == JunctionType.L_CORNER
        ]

        if l_corner_ids:
            overrides = {l_corner_ids[0]: {"join_type": "miter"}}
            graph = analyze_junctions(
                l_corner_walls,
                default_join_type="butt",
                user_overrides=overrides,
            )

            # Should be miter despite default being butt
            l_corner_res = [
                r for r in graph.resolutions
                if r.junction_id == l_corner_ids[0]
            ]
            if l_corner_res:
                assert l_corner_res[0].join_type == JoinType.MITER

    def test_override_primary_wall(self, l_corner_walls):
        nodes = build_junction_graph(l_corner_walls)

        l_corner_ids = [
            nid for nid, n in nodes.items()
            if n.junction_type == JunctionType.L_CORNER
        ]

        if l_corner_ids:
            # Override: wall_B should be primary (despite being shorter)
            overrides = {l_corner_ids[0]: {"primary_wall_id": "wall_B"}}
            graph = analyze_junctions(
                l_corner_walls,
                priority_strategy="longer_wall",
                user_overrides=overrides,
            )

            l_corner_res = [
                r for r in graph.resolutions
                if r.junction_id == l_corner_ids[0]
            ]
            if l_corner_res:
                assert l_corner_res[0].primary_wall_id == "wall_B"
                assert l_corner_res[0].is_user_override is True
                assert l_corner_res[0].confidence == 1.0


# =============================================================================
# Full Pipeline Tests
# =============================================================================


class TestAnalyzeJunctions:
    """Tests for the full analyze_junctions pipeline."""

    def test_returns_junction_graph(self, l_corner_walls):
        graph = analyze_junctions(l_corner_walls)
        assert isinstance(graph, JunctionGraph)
        assert len(graph.nodes) > 0

    def test_to_dict_valid_json(self, l_corner_walls):
        import json

        graph = analyze_junctions(l_corner_walls)
        result = graph.to_dict()

        # Should be JSON-serializable
        json_str = json.dumps(result)
        assert len(json_str) > 0

        # Should have expected keys
        assert "version" in result
        assert "junctions" in result
        assert "wall_adjustments" in result
        assert "summary" in result

    def test_summary_counts(self, four_room_layout):
        graph = analyze_junctions(four_room_layout)
        summary = graph._build_summary()

        assert summary["l_corners"] == 4
        assert summary["total_junctions"] > 0

    def test_empty_walls_returns_empty_graph(self):
        graph = analyze_junctions([])
        assert len(graph.nodes) == 0
        assert len(graph.resolutions) == 0
        assert len(graph.wall_adjustments) == 0

    def test_get_adjustment_for_layer(self, l_corner_walls):
        graph = analyze_junctions(l_corner_walls)

        # Primary wall should have a core extend adjustment
        res = graph.resolutions[0]
        adj = graph.get_adjustment_for_layer(
            res.primary_wall_id,
            # Need to find which end
            graph.get_adjustments_for_wall(res.primary_wall_id)[0].end,
            "core",
        )
        assert adj is not None
        assert adj.layer_name == "core"


# =============================================================================
# Crossed Pattern Tests
# =============================================================================


class TestCrossedPattern:
    """Tests verifying the crossed pattern at L-corner butt joints.

    At a butt joint:
    - Primary exterior EXTENDS (wraps outside corner)
    - Primary interior TRIMS (secondary's interior covers inside corner)
    - Secondary exterior TRIMS (butts against primary)
    - Secondary interior EXTENDS (wraps inside corner)
    """

    def test_primary_exterior_extends(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        # wall_A is primary (longer)
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        ext_adj = [a for a in wall_a_adjs if a.layer_name == "exterior"]
        assert len(ext_adj) == 1
        assert ext_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_primary_interior_trims(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        int_adj = [a for a in wall_a_adjs if a.layer_name == "interior"]
        assert len(int_adj) == 1
        assert int_adj[0].adjustment_type == AdjustmentType.TRIM

    def test_primary_core_extends(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        core_adj = [a for a in wall_a_adjs if a.layer_name == "core"]
        assert len(core_adj) == 1
        assert core_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_secondary_exterior_trims(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        ext_adj = [a for a in wall_b_adjs if a.layer_name == "exterior"]
        assert len(ext_adj) == 1
        assert ext_adj[0].adjustment_type == AdjustmentType.TRIM

    def test_secondary_interior_extends(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        int_adj = [a for a in wall_b_adjs if a.layer_name == "interior"]
        assert len(int_adj) == 1
        assert int_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_secondary_core_trims(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        core_adj = [a for a in wall_b_adjs if a.layer_name == "core"]
        assert len(core_adj) == 1
        assert core_adj[0].adjustment_type == AdjustmentType.TRIM

    def test_primary_exterior_extends_by_half_secondary_total(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        # Both walls have same thickness (0.3958), so half_total = 0.1979
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        ext_adj = [a for a in wall_a_adjs if a.layer_name == "exterior"][0]
        # Secondary total / 2
        expected = 0.3958 / 2.0
        assert abs(ext_adj.amount - expected) < 0.001

    def test_secondary_interior_extends_by_half_primary_total(self, l_corner_walls):
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        int_adj = [a for a in wall_b_adjs if a.layer_name == "interior"][0]
        # Primary total / 2
        expected = 0.3958 / 2.0
        assert abs(int_adj.amount - expected) < 0.001

    def test_crossed_pattern_with_four_room_layout(self, four_room_layout):
        """Verify crossed pattern holds for all corners in a rectangular room."""
        graph = analyze_junctions(
            four_room_layout,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )

        for res in graph.resolutions:
            if res.join_type != JoinType.BUTT:
                continue

            primary_adjs = {
                a.layer_name: a for a in res.layer_adjustments
                if a.wall_id == res.primary_wall_id
            }
            secondary_adjs = {
                a.layer_name: a for a in res.layer_adjustments
                if a.wall_id == res.secondary_wall_id
            }

            # Primary: exterior extends, core extends, interior trims
            assert primary_adjs["exterior"].adjustment_type == AdjustmentType.EXTEND
            assert primary_adjs["core"].adjustment_type == AdjustmentType.EXTEND
            assert primary_adjs["interior"].adjustment_type == AdjustmentType.TRIM

            # Secondary: exterior trims, core trims, interior extends
            assert secondary_adjs["exterior"].adjustment_type == AdjustmentType.TRIM
            assert secondary_adjs["core"].adjustment_type == AdjustmentType.TRIM
            assert secondary_adjs["interior"].adjustment_type == AdjustmentType.EXTEND


# =============================================================================
# Multi-Layer (v2) Butt Adjustment Tests
# =============================================================================


class TestButtAdjustmentsV2:
    """Tests for _calculate_butt_adjustments_v2 with multi-layer assemblies."""

    @pytest.fixture
    def primary_conn(self):
        return WallConnection(
            wall_id="wall_A", end="end",
            direction=(1, 0, 0), angle_at_junction=0.0,
            wall_thickness=0.40, wall_length=20.0,
        )

    @pytest.fixture
    def secondary_conn(self):
        return WallConnection(
            wall_id="wall_B", end="start",
            direction=(0, 1, 0), angle_at_junction=90.0,
            wall_thickness=0.40, wall_length=15.0,
        )

    @pytest.fixture
    def test_assembly(self):
        """4-layer assembly for testing."""
        return WallAssemblyDef(
            name="test",
            layers=[
                WallLayer("siding", LayerFunction.FINISH,
                          LayerSide.EXTERIOR, thickness=0.04),
                WallLayer("sheathing", LayerFunction.SUBSTRATE,
                          LayerSide.EXTERIOR, thickness=0.04),
                WallLayer("framing", LayerFunction.STRUCTURE,
                          LayerSide.CORE, thickness=0.29),
                WallLayer("drywall", LayerFunction.FINISH,
                          LayerSide.INTERIOR, thickness=0.04),
            ],
        )

    def test_v2_produces_per_layer_adjustments(
        self, primary_conn, secondary_conn, test_assembly
    ):
        adjs = _calculate_butt_adjustments_v2(
            "j0", primary_conn, secondary_conn,
            test_assembly, test_assembly,
        )
        # Should have: 4 per-layer for primary + 4 per-layer for secondary
        # + 3 legacy for primary + 3 legacy for secondary = 14
        assert len(adjs) == 14

    def test_v2_primary_exterior_layers_extend(
        self, primary_conn, secondary_conn, test_assembly
    ):
        adjs = _calculate_butt_adjustments_v2(
            "j0", primary_conn, secondary_conn,
            test_assembly, test_assembly,
        )
        # Per-layer: siding and sheathing (both exterior-side) should EXTEND
        primary_per_layer = [
            a for a in adjs
            if a.wall_id == "wall_A" and a.layer_name in ("siding", "sheathing")
        ]
        assert len(primary_per_layer) == 2
        for a in primary_per_layer:
            assert a.adjustment_type == AdjustmentType.EXTEND

    def test_v2_primary_interior_layers_trim(
        self, primary_conn, secondary_conn, test_assembly
    ):
        adjs = _calculate_butt_adjustments_v2(
            "j0", primary_conn, secondary_conn,
            test_assembly, test_assembly,
        )
        # Drywall (interior-side) should TRIM
        primary_drywall = [
            a for a in adjs
            if a.wall_id == "wall_A" and a.layer_name == "drywall"
        ]
        assert len(primary_drywall) == 1
        assert primary_drywall[0].adjustment_type == AdjustmentType.TRIM

    def test_v2_secondary_interior_layers_extend(
        self, primary_conn, secondary_conn, test_assembly
    ):
        adjs = _calculate_butt_adjustments_v2(
            "j0", primary_conn, secondary_conn,
            test_assembly, test_assembly,
        )
        # Secondary drywall (interior-side) should EXTEND
        sec_drywall = [
            a for a in adjs
            if a.wall_id == "wall_B" and a.layer_name == "drywall"
        ]
        assert len(sec_drywall) == 1
        assert sec_drywall[0].adjustment_type == AdjustmentType.EXTEND

    def test_v2_includes_legacy_adjustments(
        self, primary_conn, secondary_conn, test_assembly
    ):
        adjs = _calculate_butt_adjustments_v2(
            "j0", primary_conn, secondary_conn,
            test_assembly, test_assembly,
        )
        # Legacy names should be present for backward compatibility
        legacy_names = {"core", "exterior", "interior"}
        primary_legacy = [
            a for a in adjs
            if a.wall_id == "wall_A" and a.layer_name in legacy_names
        ]
        assert len(primary_legacy) == 3

        secondary_legacy = [
            a for a in adjs
            if a.wall_id == "wall_B" and a.layer_name in legacy_names
        ]
        assert len(secondary_legacy) == 3

    def test_v2_legacy_crossed_pattern(
        self, primary_conn, secondary_conn, test_assembly
    ):
        adjs = _calculate_butt_adjustments_v2(
            "j0", primary_conn, secondary_conn,
            test_assembly, test_assembly,
        )
        # Legacy adjustments should follow crossed pattern
        pri_legacy = {
            a.layer_name: a for a in adjs
            if a.wall_id == "wall_A" and a.layer_name in ("core", "exterior", "interior")
        }
        assert pri_legacy["exterior"].adjustment_type == AdjustmentType.EXTEND
        assert pri_legacy["core"].adjustment_type == AdjustmentType.EXTEND
        assert pri_legacy["interior"].adjustment_type == AdjustmentType.TRIM

        sec_legacy = {
            a.layer_name: a for a in adjs
            if a.wall_id == "wall_B" and a.layer_name in ("core", "exterior", "interior")
        }
        assert sec_legacy["exterior"].adjustment_type == AdjustmentType.TRIM
        assert sec_legacy["core"].adjustment_type == AdjustmentType.TRIM
        assert sec_legacy["interior"].adjustment_type == AdjustmentType.EXTEND
