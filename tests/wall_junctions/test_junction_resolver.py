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
    recompute_adjustments,
    resolve_all_junctions,
    build_wall_layers_map,
    build_default_wall_layers,
    build_wall_adjustments_map,
    _determine_priority,
    _calculate_butt_adjustments,
    _ordered_layers_core_outward,
    _build_layers_from_assembly,
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


class TestButtJoinDirections:
    """Tests verifying primary-dominates pattern at L-corner butt joints.

    At a butt joint:
    - Primary exterior EXTENDS (wraps outside corner)
    - Primary interior TRIMS (stops at opposing framing face)
    - Primary core EXTENDS
    - Secondary ALL layers TRIM (stop at opposing faces)
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

    def test_secondary_interior_trims(self, l_corner_walls):
        """Secondary interior TRIMS (primary covers inside corner)."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        int_adj = [a for a in wall_b_adjs if a.layer_name == "interior"]
        assert len(int_adj) == 1
        assert int_adj[0].adjustment_type == AdjustmentType.TRIM

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

    def test_primary_exterior_amount(self, l_corner_walls):
        """Primary ext extends by half_sec_core + sec_exterior_thickness."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        # Default layers for t=0.3958: ext=0.0625, core=0.2917, int=0.0417
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        ext_adj = [a for a in wall_a_adjs if a.layer_name == "exterior"][0]
        layers = build_default_wall_layers("wall_B", 0.3958)
        expected = layers.core_thickness / 2.0 + layers.exterior_thickness
        assert abs(ext_adj.amount - expected) < 0.001

    def test_secondary_interior_trim_amount(self, l_corner_walls):
        """Secondary int trims by half_pri_core + pri_interior_thickness."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        int_adj = [a for a in wall_b_adjs if a.layer_name == "interior"][0]
        layers = build_default_wall_layers("wall_A", 0.3958)
        expected = layers.core_thickness / 2.0 + layers.interior_thickness
        assert abs(int_adj.amount - expected) < 0.001

    def test_directions_with_four_room_layout(self, four_room_layout):
        """Verify directions hold for all corners in a rectangular room."""
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

            # Secondary: ALL TRIM
            assert secondary_adjs["exterior"].adjustment_type == AdjustmentType.TRIM
            assert secondary_adjs["core"].adjustment_type == AdjustmentType.TRIM
            assert secondary_adjs["interior"].adjustment_type == AdjustmentType.TRIM


# =============================================================================
# Per-Layer Cumulative Adjustment Tests
# =============================================================================


class TestPerLayerCumulativeAdjustments:
    """Tests for per-individual-layer cumulative adjustments.

    When walls have wall_assembly with individual layers, the resolver
    emits per-layer adjustments with cumulative amounts:
      primary ext[i]:  EXTEND  half_sec_core + sum(sec_ext[0:i+1])
      primary int[i]:  TRIM    half_sec_core + sum(sec_int[0:i+1])
      secondary ext[i]: TRIM   half_pri_core + sum(pri_ext[0:i+1])
      secondary int[i]: TRIM   half_pri_core + sum(pri_int[0:i+1])
    """

    @pytest.fixture
    def primary_conn(self):
        return WallConnection(
            wall_id="wall_A", end="end",
            direction=(1, 0, 0), angle_at_junction=0.0,
            wall_thickness=0.50, wall_length=20.0,
        )

    @pytest.fixture
    def secondary_conn(self):
        return WallConnection(
            wall_id="wall_B", end="start",
            direction=(0, 1, 0), angle_at_junction=90.0,
            wall_thickness=0.50, wall_length=15.0,
        )

    @pytest.fixture
    def assembly_layers_6in(self):
        """Assembly: 2 ext layers + 6" core + 1 int layer."""
        return [
            {"name": "siding", "function": "finish", "side": "exterior",
             "thickness": 1.0 / 24},      # 0.5"
            {"name": "sheathing", "function": "substrate", "side": "exterior",
             "thickness": 1.0 / 24},      # 0.5"
            {"name": "framing", "function": "structure", "side": "core",
             "thickness": 6.0 / 12},      # 6"
            {"name": "gypsum", "function": "finish", "side": "interior",
             "thickness": 1.0 / 24},      # 0.5"
        ]

    @pytest.fixture
    def assembly_layers_3_5in(self):
        """Assembly: 2 ext layers + 3.5" core + 1 int layer."""
        return [
            {"name": "siding", "function": "finish", "side": "exterior",
             "thickness": 1.0 / 24},      # 0.5"
            {"name": "sheathing", "function": "substrate", "side": "exterior",
             "thickness": 1.0 / 24},      # 0.5"
            {"name": "framing", "function": "structure", "side": "core",
             "thickness": 3.5 / 12},      # 3.5"
            {"name": "gypsum", "function": "finish", "side": "interior",
             "thickness": 1.0 / 24},      # 0.5"
        ]

    @pytest.fixture
    def layers_6in(self):
        return WallLayerInfo(
            wall_id="wall_A", total_thickness=0.50,
            exterior_thickness=2.0 / 24, core_thickness=6.0 / 12,
            interior_thickness=1.0 / 24, source="test",
        )

    @pytest.fixture
    def layers_3_5in(self):
        return WallLayerInfo(
            wall_id="wall_B", total_thickness=0.50,
            exterior_thickness=2.0 / 24, core_thickness=3.5 / 12,
            interior_thickness=1.0 / 24, source="test",
        )

    def test_per_layer_count(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """Should emit 1 core + 2 ext + 1 int per wall = 8 total."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        # Primary: core + sheathing + siding + gypsum = 4
        # Secondary: core + sheathing + siding + gypsum = 4
        assert len(adjs) == 8

    def test_primary_ext_cumulative_amounts(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """Primary ext layers extend by half_sec_core + cumulative sec ext."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_sec_core = (3.5 / 12) / 2.0  # secondary has 3.5" core
        sec_ext_1 = 1.0 / 24  # secondary sheathing (closest to core)
        sec_ext_2 = 1.0 / 24  # secondary siding

        pri_ext = [a for a in adjs if a.wall_id == "wall_A"
                   and a.layer_name in ("sheathing", "siding")]
        # Order: sheathing (closest to core) then siding
        sheathing_adj = [a for a in pri_ext if a.layer_name == "sheathing"][0]
        siding_adj = [a for a in pri_ext if a.layer_name == "siding"][0]

        assert sheathing_adj.adjustment_type == AdjustmentType.EXTEND
        assert abs(sheathing_adj.amount - (half_sec_core + sec_ext_1)) < 0.0001

        assert siding_adj.adjustment_type == AdjustmentType.EXTEND
        assert abs(siding_adj.amount - (half_sec_core + sec_ext_1 + sec_ext_2)) < 0.0001

    def test_primary_int_cumulative_amounts(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """Primary int layers trim by half_sec_core + cumulative sec int."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_sec_core = (3.5 / 12) / 2.0
        sec_int_1 = 1.0 / 24  # secondary gypsum

        gypsum_adj = [a for a in adjs if a.wall_id == "wall_A"
                      and a.layer_name == "gypsum"][0]
        assert gypsum_adj.adjustment_type == AdjustmentType.TRIM
        assert abs(gypsum_adj.amount - (half_sec_core + sec_int_1)) < 0.0001

    def test_secondary_all_trim(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """All secondary layers should TRIM."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        sec_adjs = [a for a in adjs if a.wall_id == "wall_B"]
        assert all(a.adjustment_type == AdjustmentType.TRIM for a in sec_adjs)

    def test_secondary_ext_cumulative_amounts(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """Secondary ext layers trim by half_pri_core + cumulative pri ext."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_pri_core = (6.0 / 12) / 2.0  # primary has 6" core
        pri_ext_1 = 1.0 / 24  # primary sheathing
        pri_ext_2 = 1.0 / 24  # primary siding

        sec_ext = [a for a in adjs if a.wall_id == "wall_B"
                   and a.layer_name in ("sheathing", "siding")]
        sheathing_adj = [a for a in sec_ext if a.layer_name == "sheathing"][0]
        siding_adj = [a for a in sec_ext if a.layer_name == "siding"][0]

        assert abs(sheathing_adj.amount - (half_pri_core + pri_ext_1)) < 0.0001
        assert abs(siding_adj.amount - (half_pri_core + pri_ext_1 + pri_ext_2)) < 0.0001

    def test_secondary_int_cumulative_amounts(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """Secondary int trims by half_pri_core + cumulative pri int."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_pri_core = (6.0 / 12) / 2.0
        pri_int_1 = 1.0 / 24  # primary gypsum

        gypsum_adj = [a for a in adjs if a.wall_id == "wall_B"
                      and a.layer_name == "gypsum"][0]
        assert abs(gypsum_adj.amount - (half_pri_core + pri_int_1)) < 0.0001

    def test_asymmetric_layer_counts(self):
        """Wall with 3 ext layers vs wall with 1 ext layer."""
        conn_a = WallConnection(
            wall_id="wall_A", end="end", direction=(1, 0, 0),
            angle_at_junction=0.0, wall_thickness=0.5, wall_length=20.0,
        )
        conn_b = WallConnection(
            wall_id="wall_B", end="start", direction=(0, 1, 0),
            angle_at_junction=90.0, wall_thickness=0.5, wall_length=15.0,
        )
        layers_a = WallLayerInfo(
            wall_id="wall_A", total_thickness=0.5,
            exterior_thickness=3.0 / 24, core_thickness=3.5 / 12,
            interior_thickness=1.0 / 24, source="test",
        )
        layers_b = WallLayerInfo(
            wall_id="wall_B", total_thickness=0.5,
            exterior_thickness=1.0 / 24, core_thickness=3.5 / 12,
            interior_thickness=1.0 / 24, source="test",
        )
        assembly_a = [
            {"name": "siding", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "sheathing", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "foam", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "framing", "side": "core", "thickness": 3.5 / 12},
            {"name": "gypsum", "side": "interior", "thickness": 1.0 / 24},
        ]
        assembly_b = [
            {"name": "osb", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "framing", "side": "core", "thickness": 3.5 / 12},
            {"name": "gypsum", "side": "interior", "thickness": 1.0 / 24},
        ]

        adjs = _calculate_butt_adjustments(
            "j0", conn_a, conn_b, layers_a, layers_b,
            primary_assembly_layers=assembly_a,
            secondary_assembly_layers=assembly_b,
        )

        # Primary (wall_A) has 3 ext layers.  Secondary (wall_B) has 1.
        # pri ext[0] "foam":      half_sec_core + sec_osb_thickness
        # pri ext[1] "sheathing": half_sec_core + sec_osb_thickness (no sec ext[1])
        # pri ext[2] "siding":    half_sec_core + sec_osb_thickness (no sec ext[2])
        half_sec_core = (3.5 / 12) / 2.0
        osb_t = 1.0 / 24

        pri_foam = [a for a in adjs if a.wall_id == "wall_A"
                    and a.layer_name == "foam"][0]
        pri_sheathing = [a for a in adjs if a.wall_id == "wall_A"
                         and a.layer_name == "sheathing"][0]
        pri_siding = [a for a in adjs if a.wall_id == "wall_A"
                      and a.layer_name == "siding"][0]

        # foam (ext[0]): cumulative = osb_t
        assert abs(pri_foam.amount - (half_sec_core + osb_t)) < 0.0001
        # sheathing (ext[1]): no sec_ext[1], cumulative stays osb_t
        assert abs(pri_sheathing.amount - (half_sec_core + osb_t)) < 0.0001
        # siding (ext[2]): same
        assert abs(pri_siding.amount - (half_sec_core + osb_t)) < 0.0001

    def test_fallback_without_assembly(self):
        """Without assembly layers, falls back to 3-aggregate."""
        conn_a = WallConnection(
            wall_id="wall_A", end="end", direction=(1, 0, 0),
            angle_at_junction=0.0, wall_thickness=0.40, wall_length=20.0,
        )
        conn_b = WallConnection(
            wall_id="wall_B", end="start", direction=(0, 1, 0),
            angle_at_junction=90.0, wall_thickness=0.40, wall_length=15.0,
        )
        layers_a = build_default_wall_layers("wall_A", 0.40)
        layers_b = build_default_wall_layers("wall_B", 0.40)

        adjs = _calculate_butt_adjustments(
            "j0", conn_a, conn_b, layers_a, layers_b,
        )
        # Should produce 6 adjustments (3 per wall)
        assert len(adjs) == 6
        names = {a.layer_name for a in adjs}
        assert names == {"core", "exterior", "interior"}


class TestOrderedLayersCoreOutward:
    """Tests for _ordered_layers_core_outward helper."""

    def test_exterior_layers_reversed(self):
        assembly = [
            {"name": "siding", "side": "exterior"},
            {"name": "sheathing", "side": "exterior"},
            {"name": "framing", "side": "core"},
            {"name": "gypsum", "side": "interior"},
        ]
        result = _ordered_layers_core_outward(assembly, "exterior")
        assert [l["name"] for l in result] == ["sheathing", "siding"]

    def test_interior_layers_not_reversed(self):
        assembly = [
            {"name": "sheathing", "side": "exterior"},
            {"name": "framing", "side": "core"},
            {"name": "gypsum", "side": "interior"},
            {"name": "paint", "side": "interior"},
        ]
        result = _ordered_layers_core_outward(assembly, "interior")
        assert [l["name"] for l in result] == ["gypsum", "paint"]

    def test_empty_side(self):
        assembly = [
            {"name": "framing", "side": "core"},
        ]
        result = _ordered_layers_core_outward(assembly, "exterior")
        assert result == []


# =============================================================================
# Build Layers From Assembly Tests
# =============================================================================


class TestBuildLayersFromAssembly:
    """Tests for _build_layers_from_assembly and updated build_wall_layers_map."""

    def test_assembly_layers_used_over_defaults(self):
        """When wall has wall_assembly, use real layer thicknesses."""
        walls = [{
            "wall_id": "W1",
            "wall_thickness": 0.5,
            "wall_assembly": {
                "layers": [
                    {"name": "siding", "side": "exterior", "thickness": 0.03},
                    {"name": "osb", "side": "exterior", "thickness": 0.036},
                    {"name": "studs", "side": "core", "thickness": 0.292},
                    {"name": "gyp", "side": "interior", "thickness": 0.042},
                ],
            },
        }]
        result = build_wall_layers_map(walls)
        info = result["W1"]
        assert info.source == "assembly"
        assert abs(info.exterior_thickness - 0.066) < 0.001
        assert abs(info.core_thickness - 0.292) < 0.001
        assert abs(info.interior_thickness - 0.042) < 0.001

    def test_no_assembly_falls_back_to_defaults(self):
        """Without wall_assembly, use proportionally scaled defaults."""
        walls = [{"wall_id": "W1", "wall_thickness": 0.4}]
        result = build_wall_layers_map(walls)
        assert result["W1"].source == "default"

    def test_override_takes_priority_over_assembly(self):
        """Layer overrides have highest priority."""
        walls = [{
            "wall_id": "W1",
            "wall_thickness": 0.5,
            "wall_assembly": {
                "layers": [
                    {"name": "studs", "side": "core", "thickness": 0.292},
                ],
            },
        }]
        overrides = {"W1": {"core_thickness": 0.458}}
        result = build_wall_layers_map(walls, layer_overrides=overrides)
        assert result["W1"].source == "override"
        assert abs(result["W1"].core_thickness - 0.458) < 0.001


# =============================================================================
# Recompute Adjustments Tests
# =============================================================================


def _make_assembly(ext_layers, core_thickness, int_layers):
    """Helper to build a wall_assembly dict.

    Args:
        ext_layers: List of (name, thickness) tuples for exterior layers.
        core_thickness: Core layer thickness.
        int_layers: List of (name, thickness) tuples for interior layers.

    Returns:
        Assembly dict with layers list.
    """
    layers = []
    for name, thick in ext_layers:
        layers.append({
            "name": name, "side": "exterior",
            "function": "substrate", "thickness": thick,
        })
    layers.append({
        "name": "framing_core", "side": "core",
        "function": "structure", "thickness": core_thickness,
    })
    for name, thick in int_layers:
        layers.append({
            "name": name, "side": "interior",
            "function": "finish", "thickness": thick,
        })
    return {"layers": layers}


class TestRecomputeAdjustments:
    """Tests for the Phase 2 recompute_adjustments() function."""

    def _make_l_corner_junctions_data(self):
        """Create a minimal junctions_json dict for an L-corner."""
        return {
            "version": "1.1",
            "junction_count": 1,
            "junctions": [{
                "id": "junction_0",
                "position": {"x": 0, "y": 0, "z": 0},
                "junction_type": "l_corner",
                "connections": [
                    {
                        "wall_id": "W_PRI",
                        "end": "end",
                        "is_midspan": False,
                        "midspan_u": None,
                        "wall_thickness": 0.333,
                        "is_exterior": True,
                    },
                    {
                        "wall_id": "W_SEC",
                        "end": "start",
                        "is_midspan": False,
                        "midspan_u": None,
                        "wall_thickness": 0.5,
                        "is_exterior": True,
                    },
                ],
            }],
            "resolutions": [{
                "junction_id": "junction_0",
                "join_type": "butt",
                "primary_wall_id": "W_PRI",
                "secondary_wall_id": "W_SEC",
                "confidence": 0.7,
                "reason": "test",
                "is_user_override": False,
            }],
            "wall_adjustments": {},
        }

    def _make_enriched_walls(self):
        """Create enriched walls with resolved assemblies.

        Wall W_PRI: 2x4 (core=3.5"/12), OSB ext (7/16"/12), gyp int (1/2"/12)
        Wall W_SEC: 2x6 (core=5.5"/12), OSB ext (7/16"/12), gyp int (1/2"/12)
        """
        return [
            {
                "wall_id": "W_PRI",
                "wall_thickness": 0.333,
                "wall_length": 20.0,
                "wall_assembly": _make_assembly(
                    ext_layers=[("OSB Sheathing", 7 / 16 / 12)],
                    core_thickness=3.5 / 12,
                    int_layers=[("Gypsum Board", 0.5 / 12)],
                ),
            },
            {
                "wall_id": "W_SEC",
                "wall_thickness": 0.5,
                "wall_length": 10.0,
                "wall_assembly": _make_assembly(
                    ext_layers=[("OSB Sheathing", 7 / 16 / 12)],
                    core_thickness=5.5 / 12,
                    int_layers=[("Gypsum Board", 0.5 / 12)],
                ),
            },
        ]

    def test_recompute_produces_per_layer_adjustments(self):
        """With assemblies, recompute emits per-individual-layer adjustments."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        # Both walls should have adjustments
        assert "W_PRI" in result
        assert "W_SEC" in result

        # Per-layer: core + OSB + Gypsum = 3 per wall = 6 total
        pri_names = [a["layer_name"] for a in result["W_PRI"]]
        assert "core" in pri_names
        assert "OSB Sheathing" in pri_names
        assert "Gypsum Board" in pri_names

    def test_recompute_uses_real_thicknesses(self):
        """Adjustment amounts should use assembly core thickness, not scaled defaults."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        # Primary core extends by half of secondary's core
        # Secondary core = 5.5/12 = 0.4583 ft → half = 0.2292 ft
        pri_core = [a for a in result["W_PRI"]
                     if a["layer_name"] == "core"][0]
        assert pri_core["adjustment_type"] == "extend"
        assert abs(pri_core["amount"] - (5.5 / 12 / 2)) < 0.001

        # Secondary core trims by half of primary's core
        # Primary core = 3.5/12 = 0.2917 ft → half = 0.1458 ft
        sec_core = [a for a in result["W_SEC"]
                     if a["layer_name"] == "core"][0]
        assert sec_core["adjustment_type"] == "trim"
        assert abs(sec_core["amount"] - (3.5 / 12 / 2)) < 0.001

    def test_recompute_primary_ext_cumulative(self):
        """Primary exterior extends by half_sec_core + sec_ext_thickness."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        pri_osb = [a for a in result["W_PRI"]
                    if a["layer_name"] == "OSB Sheathing"][0]
        expected = (5.5 / 12 / 2) + (7 / 16 / 12)
        assert pri_osb["adjustment_type"] == "extend"
        assert abs(pri_osb["amount"] - expected) < 0.001

    def test_recompute_secondary_all_trim(self):
        """All secondary layers should trim."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        for adj in result["W_SEC"]:
            assert adj["adjustment_type"] == "trim"

    def test_recompute_no_assemblies_uses_aggregate(self):
        """Without assemblies, falls back to aggregate adjustments."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = [
            {"wall_id": "W_PRI", "wall_thickness": 0.333, "wall_length": 20.0},
            {"wall_id": "W_SEC", "wall_thickness": 0.5, "wall_length": 10.0},
        ]
        result = recompute_adjustments(junctions_data, walls)

        # Should still produce adjustments (3 per wall)
        assert len(result["W_PRI"]) == 3
        assert len(result["W_SEC"]) == 3
        # Aggregate names: core, exterior, interior
        pri_names = sorted(a["layer_name"] for a in result["W_PRI"])
        assert pri_names == ["core", "exterior", "interior"]

    def test_recompute_empty_resolutions(self):
        """No resolutions → empty result."""
        junctions_data = {"junctions": [], "resolutions": []}
        result = recompute_adjustments(junctions_data, [])
        assert result == {}

    def test_round_trip_analyze_then_recompute(self):
        """Round-trip: analyze_junctions → to_dict → recompute.

        Verifies that recompute produces the same adjustments as the
        original analyze_junctions when using the same wall data.
        """
        from tests.wall_junctions.conftest import create_mock_wall

        # Two walls at an L-corner with assemblies
        wall_a = create_mock_wall("A", (0, 0, 0), (10, 0, 0), thickness=0.333)
        wall_b = create_mock_wall("B", (10, 0, 0), (10, 10, 0), thickness=0.5)
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.458, [("Gyp", 0.042)]
        )
        walls = [wall_a, wall_b]

        # Phase 1: full analysis
        graph = analyze_junctions(walls)
        original_json = graph.to_dict()

        # Phase 2: recompute from serialized topology
        recomputed = recompute_adjustments(original_json, walls)

        # Compare: same walls, same adjustment counts
        orig_adj = original_json["wall_adjustments"]
        for wall_id in orig_adj:
            assert wall_id in recomputed
            assert len(recomputed[wall_id]) == len(orig_adj[wall_id])

            # Same amounts (within floating point tolerance)
            for orig, recomp in zip(orig_adj[wall_id], recomputed[wall_id]):
                assert orig["layer_name"] == recomp["layer_name"]
                assert orig["adjustment_type"] == recomp["adjustment_type"]
                assert abs(orig["amount"] - recomp["amount"]) < 1e-6

    def test_t_intersection_recompute(self):
        """Recompute works for T-intersections."""
        junctions_data = {
            "junctions": [{
                "id": "j0",
                "position": {"x": 5, "y": 0, "z": 0},
                "junction_type": "t_intersection",
                "connections": [
                    {
                        "wall_id": "CONT",
                        "end": "midspan",
                        "is_midspan": True,
                        "midspan_u": 5.0,
                        "wall_thickness": 0.333,
                        "is_exterior": True,
                    },
                    {
                        "wall_id": "TERM",
                        "end": "start",
                        "is_midspan": False,
                        "midspan_u": None,
                        "wall_thickness": 0.5,
                        "is_exterior": True,
                    },
                ],
            }],
            "resolutions": [{
                "junction_id": "j0",
                "join_type": "butt",
                "primary_wall_id": "CONT",
                "secondary_wall_id": "TERM",
                "confidence": 0.95,
                "reason": "T-intersection",
                "is_user_override": False,
            }],
        }
        walls = [
            {
                "wall_id": "CONT", "wall_thickness": 0.333, "wall_length": 20.0,
                "wall_assembly": _make_assembly(
                    [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
                ),
            },
            {
                "wall_id": "TERM", "wall_thickness": 0.5, "wall_length": 10.0,
                "wall_assembly": _make_assembly(
                    [("OSB", 0.036)], 0.458, [("Gyp", 0.042)]
                ),
            },
        ]
        result = recompute_adjustments(junctions_data, walls)

        # Only terminating wall gets adjustments (T-intersection)
        assert "CONT" not in result
        assert "TERM" in result

        # All TERM adjustments are trim
        for adj in result["TERM"]:
            assert adj["adjustment_type"] == "trim"

        # TERM core trims by half of continuous core
        term_core = [a for a in result["TERM"] if a["layer_name"] == "core"][0]
        assert abs(term_core["amount"] - 0.292 / 2) < 0.001
