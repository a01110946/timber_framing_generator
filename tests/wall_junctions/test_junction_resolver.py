# File: tests/wall_junctions/test_junction_resolver.py

"""Tests for wall junction resolution and per-layer adjustments.

Tests cover:
- Butt join resolution (primary extends, secondary trims)
- T-intersection resolution (continuous wall unchanged, terminating trims)
- Miter join calculation
- Priority strategies (longer_wall, exterior_first, alternate)
- User overrides
- Unscaled catalog layer thicknesses (no scaling to Revit wall_thickness)
- Corner-type-dependent directions and cumulative patterns (v2.4)
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
    _is_exterior_corner,
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

        # wall_A should have EXTEND adjustments (core always extends)
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

    def test_continuous_wall_has_midspan_adjustments(self, t_intersection_walls):
        graph = analyze_junctions(t_intersection_walls)

        # wall_A (continuous) should have midspan adjustments at the T-junction
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        t_adjs_for_a = [
            a for a in wall_a_adjs if a.junction_id in t_junction_ids
        ]
        # One-sided: core + approach-side layer = 2 midspan adjustments
        assert len(t_adjs_for_a) == 2
        # All should be midspan TRIM
        for adj in t_adjs_for_a:
            assert adj.end == "midspan"
            assert adj.adjustment_type == AdjustmentType.TRIM
            assert adj.midspan_u is not None


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
# Corner-Type-Dependent Direction Tests (v2.4)
# =============================================================================


class TestButtJoinDirections:
    """Tests verifying corner-type-dependent butt joint directions.

    The direction pattern depends on corner type:

    **EXTERIOR corner** (dot < 0): both walls' ext EXTEND, int TRIM.
    **INTERIOR corner** (dot >= 0): both walls' ext TRIM, int EXTEND.
    Primary core always EXTENDS, secondary core always TRIMS.

    Fixture corner classifications per ``_is_exterior_corner()``:

    - ``l_corner_walls``: dot = -1 → **EXTERIOR** corner
      Wall A z=(0,-1,0), Wall B at start outward=(0,1,0)
    - ``l_corner_interior_walls``: dot = +1 → **INTERIOR** corner
      Wall A z=(0,-1,0), Wall B at start outward=(0,-1,0)
    - ``four_room_layout``: all 4 corners → **EXTERIOR**
    """

    # --- l_corner_walls (EXTERIOR corner per _is_exterior_corner) ---

    def test_primary_exterior_extends_at_exterior_corner(self, l_corner_walls):
        """l_corner_walls is EXTERIOR: primary ext EXTENDS."""
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

    def test_primary_interior_trims_at_exterior_corner(self, l_corner_walls):
        """l_corner_walls is EXTERIOR: primary int TRIMS."""
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
        """Primary core always EXTENDS regardless of corner type."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        core_adj = [a for a in wall_a_adjs if a.layer_name == "core"]
        assert len(core_adj) == 1
        assert core_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_secondary_exterior_extends_at_exterior_corner(self, l_corner_walls):
        """l_corner_walls is EXTERIOR: secondary ext EXTENDS."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        ext_adj = [a for a in wall_b_adjs if a.layer_name == "exterior"]
        assert len(ext_adj) == 1
        assert ext_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_secondary_interior_trims_at_exterior_corner(self, l_corner_walls):
        """l_corner_walls is EXTERIOR: secondary int TRIMS."""
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
        """Secondary core always TRIMS regardless of corner type."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        core_adj = [a for a in wall_b_adjs if a.layer_name == "core"]
        assert len(core_adj) == 1
        assert core_adj[0].adjustment_type == AdjustmentType.TRIM

    def test_primary_exterior_amount_exterior_corner(self, l_corner_walls):
        """EXTERIOR corner: pri ext EXTENDS by half_sec_core + sec_ext."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        ext_adj = [a for a in wall_a_adjs if a.layer_name == "exterior"][0]
        # Fallback (no assembly): half_sec_core + sec_ext
        sec_layers = build_default_wall_layers("wall_B", 0.3958)
        expected = sec_layers.core_thickness / 2.0 + sec_layers.exterior_thickness
        assert ext_adj.adjustment_type == AdjustmentType.EXTEND
        assert abs(ext_adj.amount - expected) < 0.001

    def test_secondary_interior_trim_amount_exterior_corner(self, l_corner_walls):
        """EXTERIOR corner: sec int TRIMS by half_pri_core (shifted)."""
        graph = analyze_junctions(
            l_corner_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        int_adj = [a for a in wall_b_adjs if a.layer_name == "interior"][0]
        # Exterior corner fallback: sec_int_cumul = "shifted" → half_pri_core only
        pri_layers = build_default_wall_layers("wall_A", 0.3958)
        expected = pri_layers.core_thickness / 2.0
        assert int_adj.adjustment_type == AdjustmentType.TRIM
        assert abs(int_adj.amount - expected) < 0.001

    # --- l_corner_interior_walls (INTERIOR corner per _is_exterior_corner) ---

    def test_primary_exterior_trims_at_interior_corner(self, l_corner_interior_walls):
        """l_corner_interior_walls is INTERIOR: primary ext TRIMS."""
        graph = analyze_junctions(
            l_corner_interior_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        ext_adj = [a for a in wall_a_adjs if a.layer_name == "exterior"]
        assert len(ext_adj) == 1
        assert ext_adj[0].adjustment_type == AdjustmentType.TRIM

    def test_primary_interior_extends_at_interior_corner(self, l_corner_interior_walls):
        """l_corner_interior_walls is INTERIOR: primary int EXTENDS."""
        graph = analyze_junctions(
            l_corner_interior_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        int_adj = [a for a in wall_a_adjs if a.layer_name == "interior"]
        assert len(int_adj) == 1
        assert int_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_secondary_exterior_trims_at_interior_corner(self, l_corner_interior_walls):
        """l_corner_interior_walls is INTERIOR: secondary ext TRIMS."""
        graph = analyze_junctions(
            l_corner_interior_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        ext_adj = [a for a in wall_b_adjs if a.layer_name == "exterior"]
        assert len(ext_adj) == 1
        assert ext_adj[0].adjustment_type == AdjustmentType.TRIM

    def test_secondary_interior_extends_at_interior_corner(self, l_corner_interior_walls):
        """l_corner_interior_walls is INTERIOR: secondary int EXTENDS."""
        graph = analyze_junctions(
            l_corner_interior_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")
        int_adj = [a for a in wall_b_adjs if a.layer_name == "interior"]
        assert len(int_adj) == 1
        assert int_adj[0].adjustment_type == AdjustmentType.EXTEND

    def test_interior_corner_directions(self, l_corner_interior_walls):
        """Verify full direction set for INTERIOR corner."""
        graph = analyze_junctions(
            l_corner_interior_walls,
            default_join_type="butt",
            priority_strategy="longer_wall",
        )

        res = graph.resolutions[0]
        primary_adjs = {
            a.layer_name: a for a in res.layer_adjustments
            if a.wall_id == res.primary_wall_id
        }
        secondary_adjs = {
            a.layer_name: a for a in res.layer_adjustments
            if a.wall_id == res.secondary_wall_id
        }

        # INTERIOR: ext layers TRIM, int layers EXTEND
        assert primary_adjs["exterior"].adjustment_type == AdjustmentType.TRIM
        assert primary_adjs["core"].adjustment_type == AdjustmentType.EXTEND
        assert primary_adjs["interior"].adjustment_type == AdjustmentType.EXTEND

        assert secondary_adjs["exterior"].adjustment_type == AdjustmentType.TRIM
        assert secondary_adjs["core"].adjustment_type == AdjustmentType.TRIM
        assert secondary_adjs["interior"].adjustment_type == AdjustmentType.EXTEND

    # --- four_room_layout (all EXTERIOR corners) ---

    def test_directions_with_four_room_layout(self, four_room_layout):
        """Verify corner-type-dependent pattern for rectangular room.

        All 4 corners of a rectangular room are EXTERIOR per
        _is_exterior_corner (z_axes point outward from building,
        neighboring outward directions oppose z → dot < 0).

        EXTERIOR pattern:
        - Primary: ext EXTEND, core EXTEND, int TRIM
        - Secondary: ext EXTEND, core TRIM, int TRIM
        """
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

            # EXTERIOR pattern: ext EXTEND, int TRIM
            assert primary_adjs["exterior"].adjustment_type == AdjustmentType.EXTEND, (
                f"Junction {res.junction_id}: pri ext should EXTEND at EXTERIOR corner"
            )
            assert primary_adjs["core"].adjustment_type == AdjustmentType.EXTEND
            assert primary_adjs["interior"].adjustment_type == AdjustmentType.TRIM, (
                f"Junction {res.junction_id}: pri int should TRIM at EXTERIOR corner"
            )

            assert secondary_adjs["exterior"].adjustment_type == AdjustmentType.EXTEND
            assert secondary_adjs["core"].adjustment_type == AdjustmentType.TRIM
            assert secondary_adjs["interior"].adjustment_type == AdjustmentType.TRIM


# =============================================================================
# Per-Layer Cumulative Adjustment Tests
# =============================================================================


class TestPerLayerCumulativeAdjustments:
    """Tests for per-individual-layer cumulative adjustments.

    When walls have wall_assembly with individual layers, the resolver
    emits per-layer adjustments with cumulative amounts. Two patterns:
      - **Full** (add-then-compute): ``cumul += opp[i]; amount = half_core + cumul``
      - **Shifted** (compute-then-add): ``amount = half_core + cumul; cumul += opp[i]``

    The fixture connections create an EXTERIOR corner per _is_exterior_corner:
    - primary z=(0,-1,0), secondary at "start" dir=(0,1,0) → outward=(0,1,0)
    - dot((0,-1,0), (0,1,0)) = -1 → EXTERIOR

    EXTERIOR pattern for per-layer cumulative:
    - pri_ext: EXTEND, full
    - pri_int: TRIM, shifted
    - sec_ext: EXTEND, shifted
    - sec_int: TRIM, full
    """

    @pytest.fixture
    def primary_conn(self):
        return WallConnection(
            wall_id="wall_A", end="end",
            direction=(1, 0, 0), angle_at_junction=0.0,
            wall_thickness=0.50, wall_length=20.0,
            z_axis=(0, -1, 0),  # cross((1,0,0),(0,0,1)) → faces south
        )

    @pytest.fixture
    def secondary_conn(self):
        return WallConnection(
            wall_id="wall_B", end="start",
            direction=(0, 1, 0), angle_at_junction=90.0,
            wall_thickness=0.50, wall_length=15.0,
            z_axis=(1, 0, 0),  # cross((0,1,0),(0,0,1)) → faces east
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

    def test_primary_ext_full_cumulative_exterior_corner(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """EXTERIOR corner: pri ext EXTENDS with full cumulative (same-side).

        Primary ext accumulates sec_ext layers (same side matching).
        sec_ext has 2 layers (sheathing + siding, each 0.5").
        """
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_sec_core = layers_3_5in.core_thickness / 2.0
        sec_ext_thick = 1.0 / 24  # each sec ext layer is 0.5"

        pri_ext = [a for a in adjs if a.wall_id == "wall_A"
                   and a.layer_name in ("sheathing", "siding")]
        sheathing_adj = [a for a in pri_ext if a.layer_name == "sheathing"][0]
        siding_adj = [a for a in pri_ext if a.layer_name == "siding"][0]

        assert sheathing_adj.adjustment_type == AdjustmentType.EXTEND
        expected_sheathing = half_sec_core + sec_ext_thick
        assert abs(sheathing_adj.amount - expected_sheathing) < 0.001

        assert siding_adj.adjustment_type == AdjustmentType.EXTEND
        expected_siding = half_sec_core + 2 * sec_ext_thick
        assert abs(siding_adj.amount - expected_siding) < 0.001

        # Cumulative: siding amount > sheathing amount
        assert siding_adj.amount > sheathing_adj.amount

    def test_primary_int_full_cumulative_exterior_corner(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """EXTERIOR corner: pri int TRIMS with full cumulative."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_sec_core = layers_3_5in.core_thickness / 2.0

        gypsum_adj = [a for a in adjs if a.wall_id == "wall_A"
                      and a.layer_name == "gypsum"][0]
        # EXTERIOR: primary int TRIMS with full cumulative
        # full: amount = half_sec_core + sec_int[0].thickness (add then compute)
        assert gypsum_adj.adjustment_type == AdjustmentType.TRIM
        sec_int_thick = 1.0 / 24  # gypsum = 0.5" = 1/24 ft
        expected = half_sec_core + sec_int_thick
        assert abs(gypsum_adj.amount - expected) < 0.001

    def test_secondary_directions_exterior_corner(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """EXTERIOR corner: sec ext EXTENDS, sec int TRIMS."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        sec_adjs = [a for a in adjs if a.wall_id == "wall_B"]
        sec_ext = [a for a in sec_adjs if a.layer_name in ("sheathing", "siding")]
        sec_core = [a for a in sec_adjs if a.layer_name == "core"]
        sec_int = [a for a in sec_adjs if a.layer_name == "gypsum"]

        # EXTERIOR: secondary ext EXTENDS, core TRIMS
        assert all(a.adjustment_type == AdjustmentType.EXTEND for a in sec_ext)
        assert all(a.adjustment_type == AdjustmentType.TRIM for a in sec_core)
        # EXTERIOR: secondary int TRIMS
        assert all(a.adjustment_type == AdjustmentType.TRIM for a in sec_int)

    def test_secondary_ext_shifted_cumulative_exterior_corner(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """EXTERIOR corner: sec ext EXTENDS with shifted cumulative.

        Shifted (compute-then-add): innermost ext layer gets just
        half_pri_core; each subsequent gets +1 opposing layer.
        """
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_pri_core = layers_6in.core_thickness / 2.0
        pri_ext_thick = 1.0 / 24  # each pri ext layer is 0.5"

        sec_ext = [a for a in adjs if a.wall_id == "wall_B"
                   and a.layer_name in ("sheathing", "siding")]
        sheathing_adj = [a for a in sec_ext if a.layer_name == "sheathing"][0]
        siding_adj = [a for a in sec_ext if a.layer_name == "siding"][0]

        # Shifted: sheathing[0] = half_pri_core + 0 (compute before add)
        expected_sheathing = half_pri_core
        assert abs(sheathing_adj.amount - expected_sheathing) < 0.001

        # Shifted: siding[1] = half_pri_core + pri_ext[0]
        expected_siding = half_pri_core + pri_ext_thick
        assert abs(siding_adj.amount - expected_siding) < 0.001

        # Cumulative: siding amount > sheathing amount
        assert siding_adj.amount > sheathing_adj.amount

        # Secondary ext EXTENDS at EXTERIOR corner
        assert sheathing_adj.adjustment_type == AdjustmentType.EXTEND
        assert siding_adj.adjustment_type == AdjustmentType.EXTEND

    def test_secondary_int_shifted_cumulative_exterior_corner(
        self, primary_conn, secondary_conn, layers_6in, layers_3_5in,
        assembly_layers_6in, assembly_layers_3_5in,
    ):
        """EXTERIOR corner: sec int TRIMS with shifted cumulative."""
        adjs = _calculate_butt_adjustments(
            "j0", primary_conn, secondary_conn, layers_6in, layers_3_5in,
            primary_assembly_layers=assembly_layers_6in,
            secondary_assembly_layers=assembly_layers_3_5in,
        )
        half_pri_core = layers_6in.core_thickness / 2.0

        gypsum_adj = [a for a in adjs if a.wall_id == "wall_B"
                      and a.layer_name == "gypsum"][0]
        assert gypsum_adj.adjustment_type == AdjustmentType.TRIM
        expected = half_pri_core  # shifted cumulative: just half_core
        assert abs(gypsum_adj.amount - expected) < 0.001

    def test_interior_corner_per_layer_directions(self):
        """INTERIOR corner: pri ext TRIMS (shifted), sec ext TRIMS (full)."""
        # Create an INTERIOR corner: dot(pri_z, sec_outward) >= 0
        # pri z=(0,-1,0), sec at "start" dir=(0,-1,0) → outward=(0,-1,0)
        # dot((0,-1,0),(0,-1,0)) = +1 → interior
        pri_conn = WallConnection(
            wall_id="wall_A", end="end",
            direction=(1, 0, 0), angle_at_junction=0.0,
            wall_thickness=0.50, wall_length=20.0,
            z_axis=(0, -1, 0),
        )
        sec_conn = WallConnection(
            wall_id="wall_B", end="start",
            direction=(0, -1, 0), angle_at_junction=90.0,
            wall_thickness=0.50, wall_length=15.0,
            z_axis=(-1, 0, 0),
        )
        layers_a = WallLayerInfo(
            wall_id="wall_A", total_thickness=0.50,
            exterior_thickness=2.0 / 24, core_thickness=3.5 / 12,
            interior_thickness=1.0 / 24, source="test",
        )
        layers_b = WallLayerInfo(
            wall_id="wall_B", total_thickness=0.50,
            exterior_thickness=2.0 / 24, core_thickness=3.5 / 12,
            interior_thickness=1.0 / 24, source="test",
        )
        assembly_a = [
            {"name": "siding", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "sheathing", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "framing", "side": "core", "thickness": 3.5 / 12},
            {"name": "gypsum", "side": "interior", "thickness": 1.0 / 24},
        ]
        assembly_b = [
            {"name": "siding", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "sheathing", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "framing", "side": "core", "thickness": 3.5 / 12},
            {"name": "gypsum", "side": "interior", "thickness": 1.0 / 24},
        ]

        adjs = _calculate_butt_adjustments(
            "j0", pri_conn, sec_conn, layers_a, layers_b,
            primary_assembly_layers=assembly_a,
            secondary_assembly_layers=assembly_b,
        )

        half_core = (3.5 / 12) / 2.0
        ext_thick = 1.0 / 24
        int_thick = 1.0 / 24

        # INTERIOR: pri ext TRIMS with shifted cumulative
        pri_sheath = [a for a in adjs if a.wall_id == "wall_A" and a.layer_name == "sheathing"][0]
        pri_siding = [a for a in adjs if a.wall_id == "wall_A" and a.layer_name == "siding"][0]
        assert pri_sheath.adjustment_type == AdjustmentType.TRIM
        assert abs(pri_sheath.amount - half_core) < 0.001  # shifted: just half_core
        assert pri_siding.adjustment_type == AdjustmentType.TRIM
        assert abs(pri_siding.amount - (half_core + ext_thick)) < 0.001  # shifted: cumul grew

        # INTERIOR: pri int EXTENDS with full cumulative
        pri_gyp = [a for a in adjs if a.wall_id == "wall_A" and a.layer_name == "gypsum"][0]
        assert pri_gyp.adjustment_type == AdjustmentType.EXTEND
        assert abs(pri_gyp.amount - (half_core + int_thick)) < 0.001  # full

        # INTERIOR: sec ext TRIMS with full cumulative
        sec_sheath = [a for a in adjs if a.wall_id == "wall_B" and a.layer_name == "sheathing"][0]
        sec_siding = [a for a in adjs if a.wall_id == "wall_B" and a.layer_name == "siding"][0]
        assert sec_sheath.adjustment_type == AdjustmentType.TRIM
        assert abs(sec_sheath.amount - (half_core + ext_thick)) < 0.001  # full
        assert sec_siding.adjustment_type == AdjustmentType.TRIM
        assert abs(sec_siding.amount - (half_core + 2 * ext_thick)) < 0.001

        # INTERIOR: sec int EXTENDS with shifted cumulative
        sec_gyp = [a for a in adjs if a.wall_id == "wall_B" and a.layer_name == "gypsum"][0]
        assert sec_gyp.adjustment_type == AdjustmentType.EXTEND
        assert abs(sec_gyp.amount - half_core) < 0.001  # shifted: half_core only

    def test_asymmetric_layer_counts(self):
        """Wall with 3 ext layers vs wall with 1 ext layer.

        The secondary has only 1 ext layer (osb). This is an INTERIOR corner
        (default z_axis = (0,0,1), no explicit z_axis set).
        """
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

        # Default z_axis=(0,0,1), sec at "start" outward = (0,1,0)
        # dot((0,0,1),(0,1,0)) = 0 → INTERIOR (not < 0)
        # INTERIOR: pri_ext uses shifted cumulative
        half_sec_core = layers_b.core_thickness / 2.0
        osb_thick = 1.0 / 24  # raw catalog thickness

        pri_foam = [a for a in adjs if a.wall_id == "wall_A"
                    and a.layer_name == "foam"][0]
        pri_sheathing = [a for a in adjs if a.wall_id == "wall_A"
                         and a.layer_name == "sheathing"][0]
        pri_siding = [a for a in adjs if a.wall_id == "wall_A"
                      and a.layer_name == "siding"][0]

        # Shifted: foam[0] = half_sec_core + 0, then cumul += osb
        # Shifted: sheathing[1] = half_sec_core + osb, then cumul stays (no more sec_ext)
        # Shifted: siding[2] = half_sec_core + osb (cumul doesn't grow)
        assert abs(pri_foam.amount - half_sec_core) < 0.001
        assert abs(pri_sheathing.amount - (half_sec_core + osb_thick)) < 0.001
        assert abs(pri_siding.amount - (half_sec_core + osb_thick)) < 0.001

    def test_primary_int_interior_corner_full(self):
        """INTERIOR corner: pri int EXTENDS with full cumulative.

        At an interior corner, primary int gets half_sec_core + sec_int
        (full: add opposing int layer before computing amount).
        """
        # Create interior corner: dot(pri_z, sec_outward) >= 0
        pri_conn = WallConnection(
            wall_id="wall_A", end="end",
            direction=(1, 0, 0), angle_at_junction=0.0,
            wall_thickness=0.50, wall_length=20.0,
            z_axis=(0, -1, 0),
        )
        # sec at "start" dir=(0,-1,0) → outward=(0,-1,0)
        # dot((0,-1,0),(0,-1,0)) = +1 → interior
        sec_conn = WallConnection(
            wall_id="wall_B", end="start",
            direction=(0, -1, 0), angle_at_junction=90.0,
            wall_thickness=0.50, wall_length=15.0,
            z_axis=(-1, 0, 0),
        )
        layers_a = WallLayerInfo(
            wall_id="wall_A", total_thickness=0.50,
            exterior_thickness=2.0 / 24, core_thickness=6.0 / 12,
            interior_thickness=1.0 / 24, source="test",
        )
        layers_b = WallLayerInfo(
            wall_id="wall_B", total_thickness=0.50,
            exterior_thickness=2.0 / 24, core_thickness=3.5 / 12,
            interior_thickness=1.0 / 24, source="test",
        )
        assembly_a = [
            {"name": "siding", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "sheathing", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "framing", "side": "core", "thickness": 6.0 / 12},
            {"name": "gypsum", "side": "interior", "thickness": 1.0 / 24},
        ]
        assembly_b = [
            {"name": "siding", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "sheathing", "side": "exterior", "thickness": 1.0 / 24},
            {"name": "framing", "side": "core", "thickness": 3.5 / 12},
            {"name": "gypsum", "side": "interior", "thickness": 1.0 / 24},
        ]

        adjs = _calculate_butt_adjustments(
            "j0", pri_conn, sec_conn, layers_a, layers_b,
            primary_assembly_layers=assembly_a,
            secondary_assembly_layers=assembly_b,
        )
        half_sec_core = layers_b.core_thickness / 2.0
        sec_int_thick = 1.0 / 24  # gypsum = 0.5"

        gypsum_adj = [a for a in adjs if a.wall_id == "wall_A"
                      and a.layer_name == "gypsum"][0]
        # Interior corner: primary int EXTENDS with full
        # full: cumul += sec_int; amount = half_sec_core + cumul
        assert gypsum_adj.adjustment_type == AdjustmentType.EXTEND
        assert abs(gypsum_adj.amount - (half_sec_core + sec_int_thick)) < 0.001

    def test_fallback_directions_exterior_corner(self):
        """Fallback path: EXTERIOR corner → pri ext EXTEND, pri int TRIM."""
        # EXTERIOR corner: dot(A.z=(0,-1,0), B_outward=(0,1,0)) = -1
        conn_a = WallConnection(
            wall_id="wall_A", end="end", direction=(1, 0, 0),
            angle_at_junction=0.0, wall_thickness=0.40, wall_length=20.0,
            z_axis=(0, -1, 0),
        )
        conn_b = WallConnection(
            wall_id="wall_B", end="start", direction=(0, 1, 0),
            angle_at_junction=90.0, wall_thickness=0.40, wall_length=15.0,
            z_axis=(1, 0, 0),
        )
        layers_a = build_default_wall_layers("wall_A", 0.40)
        layers_b = build_default_wall_layers("wall_B", 0.40)

        adjs = _calculate_butt_adjustments(
            "j0", conn_a, conn_b, layers_a, layers_b,
        )
        pri_ext = [a for a in adjs if a.wall_id == "wall_A"
                   and a.layer_name == "exterior"][0]
        pri_int = [a for a in adjs if a.wall_id == "wall_A"
                   and a.layer_name == "interior"][0]

        # EXTERIOR: pri ext EXTEND, pri int TRIM
        assert pri_ext.adjustment_type == AdjustmentType.EXTEND
        assert pri_int.adjustment_type == AdjustmentType.TRIM

    def test_fallback_directions_interior_corner(self):
        """Fallback path: INTERIOR corner → pri ext TRIM, pri int EXTEND."""
        # INTERIOR corner: dot(A.z=(0,-1,0), B_outward=(0,-1,0)) = +1
        conn_a = WallConnection(
            wall_id="wall_A", end="end", direction=(1, 0, 0),
            angle_at_junction=0.0, wall_thickness=0.40, wall_length=20.0,
            z_axis=(0, -1, 0),
        )
        conn_b = WallConnection(
            wall_id="wall_B", end="start", direction=(0, -1, 0),
            angle_at_junction=90.0, wall_thickness=0.40, wall_length=15.0,
            z_axis=(-1, 0, 0),
        )
        layers_a = build_default_wall_layers("wall_A", 0.40)
        layers_b = build_default_wall_layers("wall_B", 0.40)

        adjs = _calculate_butt_adjustments(
            "j0", conn_a, conn_b, layers_a, layers_b,
        )
        pri_ext = [a for a in adjs if a.wall_id == "wall_A"
                   and a.layer_name == "exterior"][0]
        pri_int = [a for a in adjs if a.wall_id == "wall_A"
                   and a.layer_name == "interior"][0]
        sec_ext = [a for a in adjs if a.wall_id == "wall_B"
                   and a.layer_name == "exterior"][0]
        sec_int = [a for a in adjs if a.wall_id == "wall_B"
                   and a.layer_name == "interior"][0]

        # INTERIOR: ext TRIM, int EXTEND
        assert pri_ext.adjustment_type == AdjustmentType.TRIM
        assert pri_int.adjustment_type == AdjustmentType.EXTEND
        assert sec_ext.adjustment_type == AdjustmentType.TRIM
        assert sec_int.adjustment_type == AdjustmentType.EXTEND

    def test_fallback_respects_cumulative_patterns(self):
        """Fallback amounts respect full/shifted cumulative patterns per corner type.

        Primary wall always uses "full" cumulative (half_core + opposing thickness),
        secondary wall always uses "shifted" (half_core only).
        """
        layers_a = build_default_wall_layers("wall_A", 0.40)
        layers_b = build_default_wall_layers("wall_B", 0.40)

        conn_a = WallConnection(
            wall_id="wall_A", end="end", direction=(1, 0, 0),
            angle_at_junction=0.0, wall_thickness=0.40, wall_length=20.0,
            z_axis=(0, -1, 0),
        )

        # EXTERIOR corner: sec at "start" dir=(0,1,0) → outward=(0,1,0)
        # dot((0,-1,0),(0,1,0)) = -1 → EXTERIOR
        conn_b_ext = WallConnection(
            wall_id="wall_B", end="start", direction=(0, 1, 0),
            angle_at_junction=90.0, wall_thickness=0.40, wall_length=15.0,
            z_axis=(1, 0, 0),
        )
        ext_adjs = _calculate_butt_adjustments(
            "j0", conn_a, conn_b_ext, layers_a, layers_b,
        )

        half_sec_core = layers_b.core_thickness / 2.0
        half_pri_core = layers_a.core_thickness / 2.0

        # Core amounts are always half_opposing_core
        ext_core = [a for a in ext_adjs if a.wall_id == "wall_A"
                    and a.layer_name == "core"][0]
        assert abs(ext_core.amount - half_sec_core) < 0.001

        # EXTERIOR corner patterns: pri=full, sec=shifted
        # Primary ext: full → half_sec_core + sec.ext_thickness
        pri_ext = [a for a in ext_adjs if a.wall_id == "wall_A"
                   and a.layer_name == "exterior"][0]
        assert abs(pri_ext.amount - (half_sec_core + layers_b.exterior_thickness)) < 0.001

        # Primary int: full → half_sec_core + sec.int_thickness
        pri_int = [a for a in ext_adjs if a.wall_id == "wall_A"
                   and a.layer_name == "interior"][0]
        assert abs(pri_int.amount - (half_sec_core + layers_b.interior_thickness)) < 0.001

        # Secondary ext: shifted → half_pri_core only
        sec_ext = [a for a in ext_adjs if a.wall_id == "wall_B"
                   and a.layer_name == "exterior"][0]
        assert abs(sec_ext.amount - half_pri_core) < 0.001

        # Secondary int: shifted → half_pri_core only
        sec_int = [a for a in ext_adjs if a.wall_id == "wall_B"
                   and a.layer_name == "interior"][0]
        assert abs(sec_int.amount - half_pri_core) < 0.001

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
        """When wall has wall_assembly, use real (unscaled) layer thicknesses.

        Layer thicknesses represent real physical material dimensions and
        are NOT scaled to match Revit wall_thickness.  Here assembly
        total = 0.4 ft but wall_thickness = 0.5 ft -- the mismatch is
        logged as a warning but values remain unscaled.
        """
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
        # Raw catalog sums (no scaling applied)
        assert abs(info.exterior_thickness - 0.066) < 0.001  # 0.03 + 0.036
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

    def test_recompute_uses_unscaled_core(self):
        """Core amounts use unscaled catalog core_thickness / 2.

        The WallLayerInfo is built by build_wall_layers_map which now
        uses raw catalog thicknesses (no scaling). The core amount
        is half of the raw catalog core thickness.
        """
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        # Raw catalog core values (no scaling)
        sec_core_thick = 5.5 / 12   # W_SEC core
        pri_core_thick = 3.5 / 12   # W_PRI core

        # Primary core extends by half_sec_core (unscaled)
        pri_core = [a for a in result["W_PRI"]
                     if a["layer_name"] == "core"][0]
        assert pri_core["adjustment_type"] == "extend"
        assert abs(pri_core["amount"] - sec_core_thick / 2.0) < 0.001

        # Secondary core trims by half_pri_core (unscaled)
        sec_core = [a for a in result["W_SEC"]
                     if a["layer_name"] == "core"][0]
        assert sec_core["adjustment_type"] == "trim"
        assert abs(sec_core["amount"] - pri_core_thick / 2.0) < 0.001

    def test_recompute_primary_ext_cumulative(self):
        """Primary ext amount depends on corner type and cumulative pattern."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        # Raw catalog values (no scaling)
        sec_core_thick = 5.5 / 12
        sec_osb_thick = 7 / 16 / 12

        pri_osb = [a for a in result["W_PRI"]
                    if a["layer_name"] == "OSB Sheathing"][0]
        # Without explicit z_axis in connection data, corner type depends on
        # _rebuild_connection's z_axis extraction. The amounts are always
        # based on half_sec_core + cumulative(sec_ext); the cumulative
        # pattern (full or shifted) determines the exact value.
        # Just verify it's positive and reasonable.
        assert pri_osb["amount"] > 0
        assert pri_osb["amount"] >= sec_core_thick / 2.0

    def test_recompute_secondary_directions(self):
        """Secondary directions depend on corner type detected in recompute."""
        junctions_data = self._make_l_corner_junctions_data()
        walls = self._make_enriched_walls()
        result = recompute_adjustments(junctions_data, walls)

        # Core always trims for secondary
        sec_core = [a for a in result["W_SEC"] if a["layer_name"] == "core"][0]
        assert sec_core["adjustment_type"] == "trim"

        # OSB and Gypsum directions depend on corner type;
        # verify they're consistent (both ext or both int on same side)
        sec_osb = [a for a in result["W_SEC"] if a["layer_name"] == "OSB Sheathing"][0]
        sec_gyp = [a for a in result["W_SEC"] if a["layer_name"] == "Gypsum Board"][0]
        # ext and int should have OPPOSITE directions
        assert sec_osb["adjustment_type"] != sec_gyp["adjustment_type"]

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

        # Both walls get adjustments (TERM trims, CONT gets midspan gaps)
        assert "TERM" in result
        assert "CONT" in result

        # All TERM adjustments are trim
        for adj in result["TERM"]:
            assert adj["adjustment_type"] == "trim"

        # TERM core trims by half_cont_core (unscaled catalog value)
        cont_core_thick = 0.292  # raw catalog core

        term_core = [a for a in result["TERM"] if a["layer_name"] == "core"][0]
        expected = cont_core_thick / 2.0
        assert abs(term_core["amount"] - expected) < 0.001

        # CONT adjustments are midspan TRIM
        for adj in result["CONT"]:
            assert adj["adjustment_type"] == "trim"
            assert adj["end"] == "midspan"
            assert adj["midspan_u"] == 5.0


# =============================================================================
# Unscaled Thickness Tests (catalog thicknesses used as-is)
# =============================================================================


class TestUnscaledThickness:
    """Tests verifying that _build_layers_from_assembly uses raw catalog thicknesses.

    Layer thicknesses represent real physical material dimensions and
    are NOT compressed to fit within the Revit wall_thickness.  When
    the catalog total differs from Revit, a warning is logged but
    values remain unscaled.
    """

    def test_layers_use_catalog_values_when_mismatch(self):
        """Layers keep raw catalog thicknesses even when total != Revit."""
        walls = [{
            "wall_id": "W1",
            "wall_thickness": 0.5,  # Revit says 6"
            "wall_assembly": {
                "layers": [
                    {"name": "osb", "side": "exterior", "thickness": 0.036},
                    {"name": "studs", "side": "core", "thickness": 0.458},
                    {"name": "gyp", "side": "interior", "thickness": 0.042},
                ],
            },
        }]
        # Assembly total = 0.536 ft, Revit = 0.5 ft -- no scaling applied
        result = build_wall_layers_map(walls)
        info = result["W1"]
        assert info.source == "assembly"
        # Layers should sum to catalog total (0.536), NOT Revit (0.5)
        total = info.exterior_thickness + info.core_thickness + info.interior_thickness
        catalog_total = 0.036 + 0.458 + 0.042  # 0.536
        assert abs(total - catalog_total) < 0.001

    def test_raw_values_when_close(self):
        """Raw catalog values are always used regardless of proximity to Revit."""
        walls_no_scale = [{
            "wall_id": "W2",
            "wall_thickness": 0.375,  # Within 0.01 of 0.370
            "wall_assembly": {
                "layers": [
                    {"name": "osb", "side": "exterior", "thickness": 0.036},
                    {"name": "studs", "side": "core", "thickness": 0.292},
                    {"name": "gyp", "side": "interior", "thickness": 0.042},
                ],
            },
        }]
        result = build_wall_layers_map(walls_no_scale)
        info = result["W2"]
        # Raw catalog values used as-is
        assert abs(info.core_thickness - 0.292) < 0.001
        assert abs(info.exterior_thickness - 0.036) < 0.001
        assert abs(info.interior_thickness - 0.042) < 0.001

    def test_unscaled_layers_sum_to_catalog_total(self):
        """Layer thicknesses sum to catalog total, not Revit thickness."""
        walls = [{
            "wall_id": "W1",
            "wall_thickness": 0.333,  # 4" wall (Revit)
            "wall_assembly": {
                "layers": [
                    {"name": "stucco", "side": "exterior", "thickness": 0.052},
                    {"name": "osb", "side": "exterior", "thickness": 0.036},
                    {"name": "studs", "side": "core", "thickness": 0.292},
                    {"name": "gyp", "side": "interior", "thickness": 0.042},
                ],
            },
        }]
        # Assembly total = 0.422 ft, Revit = 0.333 ft
        result = build_wall_layers_map(walls)
        info = result["W1"]
        total = info.exterior_thickness + info.core_thickness + info.interior_thickness
        catalog_total = 0.052 + 0.036 + 0.292 + 0.042  # 0.422
        assert abs(total - catalog_total) < 0.001

    def test_unscaled_adjustments_use_catalog_geometry(self):
        """Fallback amounts use unscaled half_opposing_core + opposing layer thicknesses."""
        conn_a = WallConnection(
            wall_id="A", end="end", direction=(1, 0, 0),
            angle_at_junction=0, wall_thickness=0.5, wall_length=20.0,
        )
        conn_b = WallConnection(
            wall_id="B", end="start", direction=(0, 1, 0),
            angle_at_junction=90, wall_thickness=0.333, wall_length=10.0,
        )
        # Assembly total differs from wall_thickness
        walls = [
            {
                "wall_id": "A", "wall_thickness": 0.5, "wall_length": 20.0,
                "wall_assembly": _make_assembly(
                    [("OSB", 0.036)], 0.458, [("Gyp", 0.042)]
                ),
            },
            {
                "wall_id": "B", "wall_thickness": 0.333, "wall_length": 10.0,
                "wall_assembly": _make_assembly(
                    [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
                ),
            },
        ]
        layers = build_wall_layers_map(walls)

        # No assembly_layers passed -> uses fallback (aggregate) path
        adjs = _calculate_butt_adjustments(
            "j0", conn_a, conn_b, layers["A"], layers["B"],
        )

        half_sec_core = layers["B"].core_thickness / 2.0
        half_pri_core = layers["A"].core_thickness / 2.0

        # Primary core extends by half_sec_core only
        core_ext = [a for a in adjs if a.wall_id == "A"
                    and a.layer_name == "core"][0]
        assert abs(core_ext.amount - half_sec_core) < 0.001

        # Primary ext amount = half_sec_core (shifted at interior corner)
        ext_adj = [a for a in adjs if a.wall_id == "A"
                   and a.layer_name == "exterior"][0]
        assert abs(ext_adj.amount - half_sec_core) < 0.001

        # Primary int amount = half_sec_core + sec_int
        int_adj = [a for a in adjs if a.wall_id == "A"
                    and a.layer_name == "interior"][0]
        assert abs(int_adj.amount - (half_sec_core + layers["B"].interior_thickness)) < 0.001

        # Secondary core trims by half_pri_core
        sec_core = [a for a in adjs if a.wall_id == "B"
                    and a.layer_name == "core"][0]
        assert abs(sec_core.amount - half_pri_core) < 0.001

        # Secondary ext amount = half_pri_core + pri_ext
        sec_ext = [a for a in adjs if a.wall_id == "B"
                   and a.layer_name == "exterior"][0]
        assert abs(sec_ext.amount - (half_pri_core + layers["A"].exterior_thickness)) < 0.001

        # Unscaled layers sum to catalog total, not Revit wall_thickness
        total_a = layers["A"].exterior_thickness + layers["A"].core_thickness + layers["A"].interior_thickness
        catalog_a = 0.036 + 0.458 + 0.042  # 0.536
        assert abs(total_a - catalog_a) < 0.001
        total_b = layers["B"].exterior_thickness + layers["B"].core_thickness + layers["B"].interior_thickness
        catalog_b = 0.036 + 0.292 + 0.042  # 0.370
        assert abs(total_b - catalog_b) < 0.001


# =============================================================================
# Summary Corner Split Tests (Phase 1)
# =============================================================================


class TestSummaryCornerSplit:
    """Tests for corner_side on JunctionResolution and summary counts."""

    def test_exterior_corner_side_set(self, l_corner_walls):
        """l_corner_walls is an EXTERIOR corner: corner_side should be 'exterior'."""
        graph = analyze_junctions(l_corner_walls)
        res = graph.resolutions[0]
        assert res.corner_side == "exterior"

    def test_interior_corner_side_set(self, l_corner_interior_walls):
        """l_corner_interior_walls is an INTERIOR corner: corner_side should be 'interior'."""
        graph = analyze_junctions(l_corner_interior_walls)
        res = graph.resolutions[0]
        assert res.corner_side == "interior"

    def test_t_intersection_no_corner_side(self, t_intersection_walls):
        """T-intersection resolutions should have corner_side=None."""
        graph = analyze_junctions(t_intersection_walls)
        t_res = [
            r for r in graph.resolutions
            if any(
                n.junction_type == JunctionType.T_INTERSECTION
                for n in graph.nodes.values()
                if n.id == r.junction_id
            )
        ]
        for res in t_res:
            assert res.corner_side is None

    def test_summary_exterior_corners_count(self, four_room_layout):
        """Four-room layout has 4 exterior corners."""
        graph = analyze_junctions(four_room_layout)
        summary = graph._build_summary()
        assert summary["exterior_corners"] == 4
        assert summary["interior_corners"] == 0
        assert summary["l_corners"] == 4

    def test_summary_mixed_corners(self, l_corner_walls, l_corner_interior_walls):
        """Verify summary counts with both exterior and interior corners.

        Uses analyze_junctions on the combined walls of both fixtures.
        Note: These walls don't share endpoints so they form separate
        junctions, but we can verify corner_side is correctly set.
        """
        graph_ext = analyze_junctions(l_corner_walls)
        graph_int = analyze_junctions(l_corner_interior_walls)

        ext_count = sum(
            1 for r in graph_ext.resolutions if r.corner_side == "exterior"
        )
        int_count = sum(
            1 for r in graph_int.resolutions if r.corner_side == "interior"
        )
        assert ext_count == 1
        assert int_count == 1

    def test_corner_side_serialized(self, l_corner_walls):
        """corner_side should appear in serialized output."""
        import json

        graph = analyze_junctions(l_corner_walls)
        result = graph.to_dict()
        json_str = json.dumps(result)

        # Should contain corner_side in resolutions
        resolutions = result.get("resolutions", [])
        l_corner_res = [
            r for r in resolutions
            if r.get("corner_side") is not None
        ]
        assert len(l_corner_res) >= 1
        assert l_corner_res[0]["corner_side"] == "exterior"

    def test_summary_has_corner_keys(self, l_corner_walls):
        """Summary dict should include exterior_corners and interior_corners."""
        graph = analyze_junctions(l_corner_walls)
        summary = graph._build_summary()
        assert "exterior_corners" in summary
        assert "interior_corners" in summary


# =============================================================================
# T-Intersection Midspan Adjustment Tests (Phase 2)
# =============================================================================


class TestTIntersectionMidspan:
    """Tests for continuous wall midspan TRIM adjustments at T-intersections."""

    def test_midspan_core_amount(self, t_intersection_walls):
        """Continuous wall core midspan TRIM = half_terminating_core."""
        graph = analyze_junctions(t_intersection_walls)
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        t_adjs = [a for a in wall_a_adjs if a.junction_id in t_junction_ids]
        core_adj = [a for a in t_adjs if a.layer_name == "core"][0]

        # half_term_core = default wall_B core / 2
        term_layers = build_default_wall_layers("wall_B", 0.3958)
        expected = term_layers.core_thickness / 2.0
        assert abs(core_adj.amount - expected) < 0.001

    def test_midspan_approach_side_amount(self, t_intersection_walls):
        """Continuous wall approach-side midspan TRIM = half_term_core (shifted).

        Wall B starts at (15,0,0) → (15,10,0), outward=(0,1,0).
        Wall A z_axis=(0,-1,0). dot=-1 < 0 → approach_side="interior".
        So the interior layer gets the midspan gap, not exterior.

        Shifted cumulative: layer 0 gets half_term_core only (touches
        the terminating core face).
        """
        graph = analyze_junctions(t_intersection_walls)
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        t_adjs = [a for a in wall_a_adjs if a.junction_id in t_junction_ids]
        int_adj = [a for a in t_adjs if a.layer_name == "interior"][0]

        term_layers = build_default_wall_layers("wall_B", 0.3958)
        # Shifted pattern: layer 0 = half_term_core only
        expected = term_layers.core_thickness / 2.0
        assert abs(int_adj.amount - expected) < 0.001

    def test_midspan_u_value(self, t_intersection_walls):
        """midspan_u should be ~15.0 (middle of 30 ft wall)."""
        graph = analyze_junctions(t_intersection_walls)
        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        t_adjs = [a for a in wall_a_adjs if a.junction_id in t_junction_ids]
        assert all(a.midspan_u is not None for a in t_adjs)
        assert all(abs(a.midspan_u - 15.0) < 0.5 for a in t_adjs)

    def test_midspan_serialized(self, t_intersection_walls):
        """midspan_u should appear in serialized adjustment dicts.

        One-sided: only core + approach-side layer (interior) = 2 midspan adjs.
        """
        import json

        graph = analyze_junctions(t_intersection_walls)
        result = graph.to_dict()

        wall_adjs = result.get("wall_adjustments", {})
        wall_a_adjs = wall_adjs.get("wall_A", [])
        midspan_adjs = [
            a for a in wall_a_adjs
            if a.get("end") == "midspan"
        ]
        assert len(midspan_adjs) == 2  # core + exterior only (one-sided)
        for adj in midspan_adjs:
            assert "midspan_u" in adj
            assert abs(adj["midspan_u"] - 15.0) < 0.5

    def test_per_layer_midspan_with_assembly(self):
        """Per-layer midspan adjustments: one-sided + shifted cumulative.

        Wall A: (0,0,0)→(30,0,0), z_axis=(0,-1,0) (south).
        Wall B: (15,0,0)→(15,10,0), outward=(0,1,0) at "start".
        dot(z_axis, outward) = -1 < 0 → wall body on interior side.
        So only interior layers (Gyp) + core get midspan adjustments.
        Shifted pattern: Gyp (layer 0) = half_term_core only.
        """
        from tests.wall_junctions.conftest import create_mock_wall

        wall_a = create_mock_wall("A", (0, 0, 0), (30, 0, 0))
        wall_b = create_mock_wall("B", (15, 0, 0), (15, 10, 0), is_exterior=False)
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )

        graph = analyze_junctions([wall_a, wall_b])
        wall_a_adjs = graph.get_adjustments_for_wall("A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        midspan_adjs = [
            a for a in wall_a_adjs
            if a.junction_id in t_junction_ids and a.end == "midspan"
        ]

        # One-sided: core + Gyp (interior only) = 2 (no OSB/exterior)
        assert len(midspan_adjs) == 2

        half_term_core = 0.292 / 2.0
        core_adj = [a for a in midspan_adjs if a.layer_name == "core"][0]
        assert abs(core_adj.amount - half_term_core) < 0.001

        # Shifted pattern: Gyp (layer 0) = half_term_core only
        gyp_adj = [a for a in midspan_adjs if a.layer_name == "Gyp"][0]
        expected_gyp = half_term_core  # shifted: layer 0 touches core face
        assert abs(gyp_adj.amount - expected_gyp) < 0.001


# =============================================================================
# X-Crossing Resolution Tests (Phase 4)
# =============================================================================


class TestXCrossingResolution:
    """Tests for X-crossing resolution producing bidirectional midspan gaps."""

    def test_x_crossing_detected_and_resolved(self, x_crossing_walls):
        """X-crossing is detected and both walls get midspan adjustments."""
        graph = analyze_junctions(x_crossing_walls)

        x_nodes = [
            n for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        ]
        assert len(x_nodes) == 1

    def test_x_crossing_both_walls_have_adjustments(self, x_crossing_walls):
        """Both walls should have midspan adjustments at the crossing."""
        graph = analyze_junctions(x_crossing_walls)

        wall_a_adjs = graph.get_adjustments_for_wall("wall_A")
        wall_b_adjs = graph.get_adjustments_for_wall("wall_B")

        # Filter to X-crossing junction adjustments
        x_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        }

        a_x_adjs = [a for a in wall_a_adjs if a.junction_id in x_junction_ids]
        b_x_adjs = [a for a in wall_b_adjs if a.junction_id in x_junction_ids]

        # Both walls should get midspan adjustments
        assert len(a_x_adjs) > 0
        assert len(b_x_adjs) > 0

    def test_x_crossing_adjustments_are_midspan_trim(self, x_crossing_walls):
        """All X-crossing adjustments should be midspan TRIM."""
        graph = analyze_junctions(x_crossing_walls)

        x_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        }

        for wall_id, adjs in graph.wall_adjustments.items():
            x_adjs = [a for a in adjs if a.junction_id in x_junction_ids]
            for adj in x_adjs:
                assert adj.end == "midspan"
                assert adj.adjustment_type == AdjustmentType.TRIM
                assert adj.midspan_u is not None

    def test_x_crossing_midspan_u_values(self, x_crossing_walls):
        """midspan_u values should correspond to crossing point.

        Wall A: (0,10) → (30,10), length=30, crossing at (15,10) → u=15
        Wall B: (15,0) → (15,20), length=20, crossing at (15,10) → u=10
        """
        graph = analyze_junctions(x_crossing_walls)

        x_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        }

        wall_a_adjs = [
            a for a in graph.get_adjustments_for_wall("wall_A")
            if a.junction_id in x_junction_ids
        ]
        wall_b_adjs = [
            a for a in graph.get_adjustments_for_wall("wall_B")
            if a.junction_id in x_junction_ids
        ]

        # Wall A midspan_u ≈ 15.0
        for adj in wall_a_adjs:
            assert abs(adj.midspan_u - 15.0) < 0.5

        # Wall B midspan_u ≈ 10.0
        for adj in wall_b_adjs:
            assert abs(adj.midspan_u - 10.0) < 0.5

    def test_x_crossing_recompute(self):
        """Recompute handles X-crossing resolution correctly."""
        junctions_data = {
            "junctions": [{
                "id": "j0",
                "position": {"x": 15, "y": 10, "z": 0},
                "junction_type": "x_crossing",
                "connections": [
                    {
                        "wall_id": "WA",
                        "end": "midspan",
                        "is_midspan": True,
                        "midspan_u": 15.0,
                        "wall_thickness": 0.3958,
                        "is_exterior": True,
                    },
                    {
                        "wall_id": "WB",
                        "end": "midspan",
                        "is_midspan": True,
                        "midspan_u": 10.0,
                        "wall_thickness": 0.3958,
                        "is_exterior": True,
                    },
                ],
            }],
            "resolutions": [{
                "junction_id": "j0",
                "join_type": "butt",
                "primary_wall_id": "WA",
                "secondary_wall_id": "WB",
                "confidence": 0.9,
                "reason": "X-crossing",
                "is_user_override": False,
            }],
        }
        walls = [
            {
                "wall_id": "WA", "wall_thickness": 0.3958, "wall_length": 30.0,
                "wall_assembly": _make_assembly(
                    [("OSB", 0.036)], 0.292, [("Gyp", 0.042)],
                ),
            },
            {
                "wall_id": "WB", "wall_thickness": 0.3958, "wall_length": 20.0,
                "wall_assembly": _make_assembly(
                    [("OSB", 0.036)], 0.292, [("Gyp", 0.042)],
                ),
            },
        ]
        result = recompute_adjustments(junctions_data, walls)

        # Both walls should have midspan adjustments
        assert "WA" in result
        assert "WB" in result

        # WA midspan adjustments
        for adj in result["WA"]:
            assert adj["adjustment_type"] == "trim"
            assert adj["end"] == "midspan"
            assert adj["midspan_u"] == 15.0

        # WB midspan adjustments
        for adj in result["WB"]:
            assert adj["adjustment_type"] == "trim"
            assert adj["end"] == "midspan"
            assert adj["midspan_u"] == 10.0

    def test_x_crossing_no_endpoint_trims(self, x_crossing_walls):
        """X-crossing adjustments should NOT include endpoint trims.

        With midspan_only=True, neither wall should get terminating
        endpoint adjustments — only midspan gap adjustments.
        """
        graph = analyze_junctions(x_crossing_walls)

        x_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        }

        for wall_id, adjs in graph.wall_adjustments.items():
            x_adjs = [a for a in adjs if a.junction_id in x_junction_ids]
            for adj in x_adjs:
                # No endpoint adjustments (start/end) — only midspan
                assert adj.end == "midspan", (
                    f"Wall {wall_id} got endpoint adjustment end={adj.end}, "
                    f"expected only midspan adjustments for X-crossing"
                )


# =============================================================================
# One-Sided and Shifted Cumulative Midspan Tests
# =============================================================================


class TestMidspanOneSidedAndShifted:
    """Tests for one-sided midspan gapping and shifted cumulative pattern.

    Key geometry for approach-side detection:
      _outward_direction_at_junction(terminating) points AWAY from junction
      along the terminating wall, i.e., toward where the wall BODY is.

      dot(continuous.z_axis, outward):
        dot < 0 → wall body on -z (interior) side → gap interior layers
        dot >= 0 → wall body on +z (exterior) side → gap exterior layers
    """

    def test_midspan_one_sided_interior(self):
        """Wall B body is on the interior side of wall A → gap interior only.

        Wall A: (0,0,0) → (30,0,0), z_axis=(0,-1,0) (south = exterior)
        Wall B: (15,0,0) → (15,10,0), outward=(0,1,0) (north)
            dot((0,-1,0), (0,1,0)) = -1 < 0 → body on interior side
        """
        from tests.wall_junctions.conftest import create_mock_wall

        wall_a = create_mock_wall("A", (0, 0, 0), (30, 0, 0))
        wall_b = create_mock_wall("B", (15, 0, 0), (15, 10, 0), is_exterior=False)
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )

        graph = analyze_junctions([wall_a, wall_b])
        wall_a_adjs = graph.get_adjustments_for_wall("A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        midspan_adjs = [
            a for a in wall_a_adjs
            if a.junction_id in t_junction_ids and a.end == "midspan"
        ]

        layer_names = {a.layer_name for a in midspan_adjs}
        # Wall body on interior (-z) side → gap core + Gyp (interior)
        assert "core" in layer_names
        assert "Gyp" in layer_names
        assert "OSB" not in layer_names  # exterior not gapped
        assert len(midspan_adjs) == 2

    def test_midspan_one_sided_exterior(self):
        """Wall B body is on the exterior side of wall A → gap exterior only.

        Wall A: (0,0,0) → (30,0,0), z_axis=(0,-1,0) (south = exterior)
        Wall B: (15,0,0) → (15,-10,0), outward=(0,-1,0) (south)
            dot((0,-1,0), (0,-1,0)) = +1 >= 0 → body on exterior side
        """
        from tests.wall_junctions.conftest import create_mock_wall

        wall_a = create_mock_wall("A", (0, 0, 0), (30, 0, 0))
        wall_b = create_mock_wall("B", (15, 0, 0), (15, -10, 0), is_exterior=False)
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )

        graph = analyze_junctions([wall_a, wall_b])
        wall_a_adjs = graph.get_adjustments_for_wall("A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        midspan_adjs = [
            a for a in wall_a_adjs
            if a.junction_id in t_junction_ids and a.end == "midspan"
        ]

        layer_names = {a.layer_name for a in midspan_adjs}
        # Wall body on exterior (+z) side → gap core + OSB (exterior)
        assert "core" in layer_names
        assert "OSB" in layer_names
        assert "Gyp" not in layer_names  # interior not gapped
        assert len(midspan_adjs) == 2

    def test_midspan_shifted_cumulative(self):
        """Shifted cumulative pattern: layer 0 = half_term_core,
        layer 1 = half_term_core + term_layer[0].thickness.

        Uses two interior layers to verify cumulative progression.
        Wall B body is on interior side (dot < 0) for this geometry.
        """
        from tests.wall_junctions.conftest import create_mock_wall

        wall_a = create_mock_wall("A", (0, 0, 0), (30, 0, 0))
        wall_b = create_mock_wall("B", (15, 0, 0), (15, 10, 0), is_exterior=False)
        # Two interior layers on each wall to test cumulative on approach side
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042), ("Paint", 0.002)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042), ("Paint", 0.002)]
        )

        graph = analyze_junctions([wall_a, wall_b])
        wall_a_adjs = graph.get_adjustments_for_wall("A")
        t_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.T_INTERSECTION
        }
        midspan_adjs = [
            a for a in wall_a_adjs
            if a.junction_id in t_junction_ids and a.end == "midspan"
        ]

        half_term_core = 0.292 / 2.0

        # core
        core_adj = [a for a in midspan_adjs if a.layer_name == "core"][0]
        assert abs(core_adj.amount - half_term_core) < 0.001

        # Interior layers (approach side for this geometry):
        # _ordered_layers_core_outward("interior") returns layers as-is
        # (interior layers are already core-outward in assembly order).
        # Assembly int layers: [Gyp, Paint] → core-outward = [Gyp, Paint]
        # term_int core-outward for wall_b: [Gyp, Paint]
        #
        # Shifted: layer 0 (Gyp) = half_term_core + 0 = half_term_core
        gyp_adj = [a for a in midspan_adjs if a.layer_name == "Gyp"][0]
        assert abs(gyp_adj.amount - half_term_core) < 0.001

        # layer 1 (Paint) = half_term_core + term_int[0].thick = + 0.042
        paint_adj = [a for a in midspan_adjs if a.layer_name == "Paint"][0]
        expected_paint = half_term_core + 0.042  # Gyp thickness
        assert abs(paint_adj.amount - expected_paint) < 0.001

    def test_x_crossing_both_sides_gapped(self):
        """X-crossing: both exterior and interior layers get midspan gaps.

        Unlike T-intersections (one-sided), X-crossings gap BOTH sides
        because the crossing wall passes through the entire continuous wall.
        """
        from tests.wall_junctions.conftest import create_mock_wall

        wall_a = create_mock_wall("A", (0, 10, 0), (30, 10, 0))
        wall_b = create_mock_wall("B", (15, 0, 0), (15, 20, 0))
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )

        graph = analyze_junctions([wall_a, wall_b])

        # Get midspan adjustments for wall A at the X-crossing
        x_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        }
        wall_a_adjs = graph.get_adjustments_for_wall("A")
        midspan_adjs = [
            a for a in wall_a_adjs
            if a.junction_id in x_junction_ids and a.end == "midspan"
        ]

        layer_names = {a.layer_name for a in midspan_adjs}
        # X-crossing: BOTH sides gapped → core + OSB + Gyp = 3
        assert "core" in layer_names
        assert "OSB" in layer_names
        assert "Gyp" in layer_names
        assert len(midspan_adjs) == 3

    def test_x_crossing_interlocking_amounts(self):
        """X-crossing: primary wall uses shifted, secondary uses full cumulative.

        Primary (wall A) first layers → half_term_core (shifted: no extra)
        Secondary (wall B) first layers → half_term_core + term_first_layer (full)

        This creates interlocking gaps that don't overlap at the crossing.
        """
        from tests.wall_junctions.conftest import create_mock_wall

        wall_a = create_mock_wall("A", (0, 10, 0), (30, 10, 0))
        wall_b = create_mock_wall("B", (15, 0, 0), (15, 20, 0))
        wall_a["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )
        wall_b["wall_assembly"] = _make_assembly(
            [("OSB", 0.036)], 0.292, [("Gyp", 0.042)]
        )

        graph = analyze_junctions([wall_a, wall_b])

        x_junction_ids = {
            n.id for n in graph.nodes.values()
            if n.junction_type == JunctionType.X_CROSSING
        }

        half_b_core = 0.292 / 2  # = 0.146
        half_a_core = 0.292 / 2  # = 0.146

        # Wall A (primary) — shifted cumulative: first layers = half_term_core
        wall_a_adjs = graph.get_adjustments_for_wall("A")
        a_midspan = [
            a for a in wall_a_adjs
            if a.junction_id in x_junction_ids and a.end == "midspan"
        ]
        a_osb = [a for a in a_midspan if a.layer_name == "OSB"][0]
        a_gyp = [a for a in a_midspan if a.layer_name == "Gyp"][0]
        # Primary: shifted → first ext/int layer amount = half_term_core only
        assert abs(a_osb.amount - half_b_core) < 1e-6, (
            f"Wall A OSB expected {half_b_core}, got {a_osb.amount}"
        )
        assert abs(a_gyp.amount - half_b_core) < 1e-6, (
            f"Wall A Gyp expected {half_b_core}, got {a_gyp.amount}"
        )

        # Wall B (secondary) — full cumulative: first layers = half_term_core + term_first_layer
        wall_b_adjs = graph.get_adjustments_for_wall("B")
        b_midspan = [
            a for a in wall_b_adjs
            if a.junction_id in x_junction_ids and a.end == "midspan"
        ]
        b_osb = [a for a in b_midspan if a.layer_name == "OSB"][0]
        b_gyp = [a for a in b_midspan if a.layer_name == "Gyp"][0]
        # Secondary: full → first ext layer = half_term_core + term_ext[0].thickness
        #   ext: term_ext = [OSB (substrate)] → full: half_core + 0.036
        #   int: term_int = [Gyp (finish)] → full: half_core + 0.042
        expected_b_osb = half_a_core + 0.036  # half_core + OSB thickness
        expected_b_gyp = half_a_core + 0.042  # half_core + Gyp thickness
        assert abs(b_osb.amount - expected_b_osb) < 1e-6, (
            f"Wall B OSB expected {expected_b_osb}, got {b_osb.amount}"
        )
        assert abs(b_gyp.amount - expected_b_gyp) < 1e-6, (
            f"Wall B Gyp expected {expected_b_gyp}, got {b_gyp.amount}"
        )

