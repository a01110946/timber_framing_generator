# File: src/timber_framing_generator/wall_junctions/junction_resolver.py

"""Wall junction join resolution and per-layer adjustment calculation.

Given a classified junction graph, this module:
1. Determines join type (butt/miter) for each junction
2. Determines priority (which wall extends vs trims)
3. Calculates per-layer adjustments based on wall layer thicknesses
4. Supports user overrides for any junction

All measurements are in feet.
"""

import math
import logging
from typing import Any, List, Dict, Tuple, Optional

from .junction_types import (
    JunctionNode,
    JunctionType,
    JoinType,
    AdjustmentType,
    WallConnection,
    WallLayerInfo,
    LayerAdjustment,
    JunctionResolution,
    JunctionGraph,
    _serialize_adjustment,
)
from .junction_detector import (
    _outward_direction_at_junction,
    _calculate_angle,
    _extract_z_axis,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Diagnostic Logging (set True to enable verbose per-layer trace)
# =============================================================================
DIAG_ENABLED = True

# Version marker — printed on import to confirm updated code is loaded.
# Bump this value whenever the adjustment logic changes.
_RESOLVER_VERSION = "2.8-primary-dominates-butt"
print(f"[JUNC-RESOLVER] junction_resolver.py version {_RESOLVER_VERSION} loaded")


def _diag(msg: str) -> None:
    """Print diagnostic message when DIAG_ENABLED is True."""
    if DIAG_ENABLED:
        print(f"[JUNC-DIAG] {msg}")


# =============================================================================
# Default Layer Info
# =============================================================================

# From config/assembly.py: ext=0.75", core=3.5", int=0.5" (in feet)
_DEFAULT_EXT_FT = 0.75 / 12.0    # 0.0625 ft
_DEFAULT_CORE_FT = 3.5 / 12.0    # 0.2917 ft
_DEFAULT_INT_FT = 0.5 / 12.0     # 0.0417 ft
_DEFAULT_TOTAL_FT = _DEFAULT_EXT_FT + _DEFAULT_CORE_FT + _DEFAULT_INT_FT


def build_default_wall_layers(
    wall_id: str,
    total_thickness: float,
) -> WallLayerInfo:
    """Create default layer info scaled from assembly.py defaults.

    If the wall's total thickness differs from the default assembly
    thickness, all layer thicknesses are scaled proportionally.

    Args:
        wall_id: Wall identifier.
        total_thickness: Total wall thickness in feet.

    Returns:
        WallLayerInfo with proportionally scaled layers.
    """
    if _DEFAULT_TOTAL_FT > 0 and abs(total_thickness - _DEFAULT_TOTAL_FT) > 0.001:
        scale = total_thickness / _DEFAULT_TOTAL_FT
    else:
        scale = 1.0

    return WallLayerInfo(
        wall_id=wall_id,
        total_thickness=total_thickness,
        exterior_thickness=_DEFAULT_EXT_FT * scale,
        core_thickness=_DEFAULT_CORE_FT * scale,
        interior_thickness=_DEFAULT_INT_FT * scale,
        source="default",
    )


def build_wall_layers_map(
    walls_data: List[Dict],
    layer_overrides: Optional[Dict[str, Dict]] = None,
) -> Dict[str, WallLayerInfo]:
    """Build WallLayerInfo for every wall.

    Priority order:
    1. Explicit ``layer_overrides`` (highest)
    2. Resolved ``wall_assembly`` layers (from assembly_resolver)
    3. Proportionally-scaled defaults (lowest)

    Args:
        walls_data: List of wall dicts from walls_json.
        layer_overrides: Optional dict of wall_id → layer thickness overrides
            with keys: exterior_thickness, core_thickness, interior_thickness.

    Returns:
        Dict mapping wall_id to WallLayerInfo.
    """
    result = {}
    overrides = layer_overrides or {}

    for wall in walls_data:
        wall_id = wall["wall_id"]
        thickness = wall.get("wall_thickness", _DEFAULT_TOTAL_FT)

        if wall_id in overrides:
            ov = overrides[wall_id]
            result[wall_id] = WallLayerInfo(
                wall_id=wall_id,
                total_thickness=thickness,
                exterior_thickness=ov.get("exterior_thickness", _DEFAULT_EXT_FT),
                core_thickness=ov.get("core_thickness", _DEFAULT_CORE_FT),
                interior_thickness=ov.get("interior_thickness", _DEFAULT_INT_FT),
                source="override",
            )
        elif _has_assembly_layers(wall):
            result[wall_id] = _build_layers_from_assembly(wall_id, wall["wall_assembly"], thickness)
        else:
            result[wall_id] = build_default_wall_layers(wall_id, thickness)

    return result


def _has_assembly_layers(wall: Dict) -> bool:
    """Check if a wall has resolved assembly layers."""
    assembly = wall.get("wall_assembly")
    return bool(assembly and assembly.get("layers"))


def _build_layers_from_assembly(
    wall_id: str,
    wall_assembly: Dict,
    total_thickness: float,
) -> WallLayerInfo:
    """Build WallLayerInfo from resolved assembly layers.

    Sums actual (unscaled) layer thicknesses by side
    (exterior/core/interior).  The catalog thicknesses represent
    real physical material dimensions and must NOT be compressed
    to fit within ``total_thickness``.

    If the catalog total differs from the Revit wall thickness,
    a warning is logged but no scaling is applied.  The mismatch
    should be resolved via better assembly selection or user
    configuration, not by compressing material dimensions.

    Args:
        wall_id: Wall identifier.
        wall_assembly: Assembly dict with "layers" list.
        total_thickness: Total wall thickness from Revit (feet).

    Returns:
        WallLayerInfo with actual (unscaled) layer thicknesses.
    """
    layers = wall_assembly.get("layers", [])
    ext_t = sum(l.get("thickness", 0.0) for l in layers if l.get("side") == "exterior")
    core_t = sum(l.get("thickness", 0.0) for l in layers if l.get("side") == "core")
    int_t = sum(l.get("thickness", 0.0) for l in layers if l.get("side") == "interior")

    assembly_total = ext_t + core_t + int_t
    if (
        assembly_total > 0
        and total_thickness > 0
        and abs(assembly_total - total_thickness) > 0.01
    ):
        logger.warning(
            "Wall %s: catalog assembly total (%.4f ft / %.2f in) differs from "
            "Revit wall_thickness (%.4f ft / %.2f in). Using unscaled catalog "
            "thicknesses for junction adjustments.",
            wall_id, assembly_total, assembly_total * 12,
            total_thickness, total_thickness * 12,
        )

    return WallLayerInfo(
        wall_id=wall_id,
        total_thickness=total_thickness,
        exterior_thickness=ext_t,
        core_thickness=core_t,
        interior_thickness=int_t,
        source="assembly",
    )


def _build_wall_assemblies_map(
    walls_data: List[Dict],
) -> Dict[str, List[Dict]]:
    """Extract individual assembly layers from each wall.

    Args:
        walls_data: List of wall dicts, each optionally containing
            ``wall_assembly.layers``.

    Returns:
        Dict mapping wall_id to list of assembly layer dicts.
        Only includes walls that have assembly layers.
    """
    result: Dict[str, List[Dict]] = {}
    for wall in walls_data:
        wall_id = wall.get("wall_id", "")
        assembly = wall.get("wall_assembly")
        if assembly and assembly.get("layers"):
            result[wall_id] = assembly["layers"]
    return result


def _ordered_layers_core_outward(
    assembly_layers: List[Dict],
    side: str,
) -> List[Dict]:
    """Get layers for a side, ordered from core outward.

    Assembly layers are ordered outside-to-inside (Revit convention).
    Exterior layers need to be reversed for core-outward ordering.
    Interior layers are already in core-outward order.

    Args:
        assembly_layers: Full list of assembly layer dicts.
        side: "exterior" or "interior".

    Returns:
        List of layer dicts ordered from closest-to-core to outermost.
    """
    side_layers = [l for l in assembly_layers if l.get("side") == side]
    if side == "exterior":
        return list(reversed(side_layers))
    return side_layers


# =============================================================================
# Priority Determination
# =============================================================================


def _determine_priority(
    conn_a: WallConnection,
    conn_b: WallConnection,
    strategy: str,
) -> Tuple[WallConnection, WallConnection]:
    """Determine which wall is primary (extends) in a butt join.

    Args:
        conn_a: First wall connection.
        conn_b: Second wall connection.
        strategy: Priority strategy name.

    Returns:
        (primary, secondary) tuple where primary extends.
    """
    if strategy == "longer_wall":
        if conn_a.wall_length >= conn_b.wall_length:
            return conn_a, conn_b
        return conn_b, conn_a

    elif strategy == "exterior_first":
        # Exterior walls get priority over interior
        if conn_a.is_exterior and not conn_b.is_exterior:
            return conn_a, conn_b
        if conn_b.is_exterior and not conn_a.is_exterior:
            return conn_b, conn_a
        # Both same — fall back to longer wall
        if conn_a.wall_length >= conn_b.wall_length:
            return conn_a, conn_b
        return conn_b, conn_a

    elif strategy == "alternate":
        # Consistent alternation by wall_id comparison
        if conn_a.wall_id < conn_b.wall_id:
            return conn_a, conn_b
        return conn_b, conn_a

    # Default: conn_a is primary
    return conn_a, conn_b


def _determine_t_priority(
    connections: List[WallConnection],
) -> Tuple[WallConnection, WallConnection]:
    """For T-intersections, find the continuous and terminating walls.

    The continuous wall (passes through) is primary. The terminating
    wall (ends at the junction) is secondary.

    Returns:
        (continuous_wall, terminating_wall).
    """
    midspan_conns = [c for c in connections if c.is_midspan]
    endpoint_conns = [c for c in connections if not c.is_midspan]

    if midspan_conns and endpoint_conns:
        # Midspan = continuous wall, endpoint = terminating wall
        return midspan_conns[0], endpoint_conns[0]

    # Fallback for 3-connection T-junctions detected by angle:
    # Find the pair with ~180° angle (inline = continuous wall's two ends)
    if len(connections) >= 3:
        best_pair = None
        best_angle = 0.0
        for i in range(len(connections)):
            for j in range(i + 1, len(connections)):
                out_i = _outward_direction_at_junction(connections[i])
                out_j = _outward_direction_at_junction(connections[j])
                angle = _calculate_angle(out_i, out_j)
                if angle > best_angle:
                    best_angle = angle
                    best_pair = (i, j)

        if best_pair and best_angle > 150.0:
            # The third connection is the terminating wall
            inline_ids = {best_pair[0], best_pair[1]}
            for k in range(len(connections)):
                if k not in inline_ids:
                    # continuous wall = either of the inline pair (pick first)
                    return connections[best_pair[0]], connections[k]

    # Can't determine — return first two
    if len(connections) >= 2:
        return connections[0], connections[1]
    return connections[0], connections[0]


# =============================================================================
# Per-Layer Adjustment Calculation
# =============================================================================


def _is_exterior_corner(
    primary: WallConnection,
    secondary: WallConnection,
) -> bool:
    """Determine if an L-corner is an exterior corner (building outside).

    Uses the dot product of the primary wall's z_axis (exterior normal)
    and the secondary wall's outward direction at the junction.

    - Negative dot product: z_axes point outward from the corner
      (exterior corner — building outside).
    - Positive dot product: z_axes point inward toward the corner
      (interior corner — room inside).

    Args:
        primary: Primary wall connection (with z_axis populated).
        secondary: Secondary wall connection (with direction populated).

    Returns:
        True if the corner is an exterior corner.
    """
    out_sec = _outward_direction_at_junction(secondary)
    dot = (
        primary.z_axis[0] * out_sec[0]
        + primary.z_axis[1] * out_sec[1]
        + primary.z_axis[2] * out_sec[2]
    )
    return dot < 0


def _calculate_butt_adjustments(
    junction_id: str,
    primary: WallConnection,
    secondary: WallConnection,
    primary_layers: WallLayerInfo,
    secondary_layers: WallLayerInfo,
    primary_assembly_layers: Optional[List[Dict]] = None,
    secondary_assembly_layers: Optional[List[Dict]] = None,
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments for a butt join.

    The primary wall dominates both faces of the corner. The exact
    EXTEND/TRIM pattern depends on whether the corner is exterior
    (building outside) or interior (room inside):

    **Interior corner** (z_axes point into corner):
      - Primary exterior EXTENDS, core EXTENDS, interior TRIMS
      - Secondary exterior TRIMS, core TRIMS, interior EXTENDS

    **Exterior corner** (z_axes point away from corner):
      - Primary exterior TRIMS, core EXTENDS, interior EXTENDS
      - Secondary exterior EXTENDS, core TRIMS, interior TRIMS

    Two cumulative patterns control per-layer amounts:
      - **Full** (add-then-compute): ``cumul += opp[i]; amount = half_core + cumul``
      - **Shifted** (compute-then-add): ``amount = half_core + cumul; cumul += opp[i]``

    Layer thicknesses are used as-is from the catalog (unscaled).

    When ``primary_assembly_layers`` / ``secondary_assembly_layers``
    are provided, adjustments are emitted per individual layer name.
    Otherwise, falls back to 3-aggregate (exterior/core/interior)
    adjustments using aggregate thicknesses from ``WallLayerInfo``.

    Args:
        junction_id: Junction identifier.
        primary: Primary wall connection (extends at outside corner).
        secondary: Secondary wall connection (trims).
        primary_layers: Aggregate layer info for primary wall.
        secondary_layers: Aggregate layer info for secondary wall.
        primary_assembly_layers: Optional list of individual layer dicts
            for the primary wall (from wall_assembly["layers"]).
        secondary_assembly_layers: Optional list of individual layer
            dicts for the secondary wall.

    Returns:
        List of LayerAdjustments for both walls.
    """
    adjustments: List[LayerAdjustment] = []

    half_sec_core = secondary_layers.core_thickness / 2.0
    half_pri_core = primary_layers.core_thickness / 2.0

    # Determine corner type (exterior vs interior)
    exterior_corner = _is_exterior_corner(primary, secondary)

    # Corner-type-dependent direction and cumulative pattern assignment.
    # At exterior corners: ext layers EXTEND (continuous exterior surface),
    #   int layers TRIM.
    # At interior corners: ext layers TRIM, int layers EXTEND (continuous
    #   interior surface).
    if exterior_corner:
        pri_ext_dir, pri_ext_cumul = AdjustmentType.EXTEND, "full"
        pri_int_dir, pri_int_cumul = AdjustmentType.TRIM, "full"
        sec_ext_dir, sec_ext_cumul = AdjustmentType.EXTEND, "shifted"
        sec_int_dir, sec_int_cumul = AdjustmentType.TRIM, "shifted"
    else:
        pri_ext_dir, pri_ext_cumul = AdjustmentType.TRIM, "shifted"
        pri_int_dir, pri_int_cumul = AdjustmentType.EXTEND, "full"
        sec_ext_dir, sec_ext_cumul = AdjustmentType.TRIM, "full"
        sec_int_dir, sec_int_cumul = AdjustmentType.EXTEND, "shifted"

    # ===== DIAGNOSTIC: Butt adjustment inputs =====
    _diag(f"=== _calculate_butt_adjustments [{junction_id}] ===")
    _diag(f"  CORNER TYPE: {'EXTERIOR' if exterior_corner else 'INTERIOR'}")
    _diag(f"  -> DIRECTIONS: pri_ext={pri_ext_dir.value}, pri_int={pri_int_dir.value}, "
           f"sec_ext={sec_ext_dir.value}, sec_int={sec_int_dir.value}")
    _diag(f"  -> CUMULATIVE: pri_ext={pri_ext_cumul}, pri_int={pri_int_cumul}, "
           f"sec_ext={sec_ext_cumul}, sec_int={sec_int_cumul}")
    _diag(f"  ASSUMPTION: amounts are distances from each wall's Revit centerline endpoint along its U-axis")
    _diag(f"  ASSUMPTION: wall endpoints meet at/near the virtual centerline corner")
    _diag(f"  ASSUMPTION: +z_axis = physical exterior face")
    _diag(f"  PRIMARY: wall={primary.wall_id} end={primary.end} "
           f"thick={primary.wall_thickness:.6f} ft ({primary.wall_thickness*12:.4f} in) "
           f"len={primary.wall_length:.4f} ft")
    _diag(f"    layers: ext={primary_layers.exterior_thickness:.6f} ft ({primary_layers.exterior_thickness*12:.4f} in), "
           f"core={primary_layers.core_thickness:.6f} ft ({primary_layers.core_thickness*12:.4f} in), "
           f"int={primary_layers.interior_thickness:.6f} ft ({primary_layers.interior_thickness*12:.4f} in) "
           f"[source={primary_layers.source}]")
    _diag(f"    half_pri_core={half_pri_core:.6f} ft ({half_pri_core*12:.4f} in)")
    _diag(f"  SECONDARY: wall={secondary.wall_id} end={secondary.end} "
           f"thick={secondary.wall_thickness:.6f} ft ({secondary.wall_thickness*12:.4f} in) "
           f"len={secondary.wall_length:.4f} ft")
    _diag(f"    layers: ext={secondary_layers.exterior_thickness:.6f} ft ({secondary_layers.exterior_thickness*12:.4f} in), "
           f"core={secondary_layers.core_thickness:.6f} ft ({secondary_layers.core_thickness*12:.4f} in), "
           f"int={secondary_layers.interior_thickness:.6f} ft ({secondary_layers.interior_thickness*12:.4f} in) "
           f"[source={secondary_layers.source}]")
    _diag(f"    half_sec_core={half_sec_core:.6f} ft ({half_sec_core*12:.4f} in)")
    _diag(f"  has_primary_assembly_layers={primary_assembly_layers is not None and len(primary_assembly_layers or []) > 0}")
    _diag(f"  has_secondary_assembly_layers={secondary_assembly_layers is not None and len(secondary_assembly_layers or []) > 0}")
    if primary_assembly_layers:
        for al in primary_assembly_layers:
            _diag(f"    pri_asm: name={al.get('name')} side={al.get('side')} "
                   f"thick={al.get('thickness', 0):.6f} ft ({al.get('thickness', 0)*12:.4f} in)")
    if secondary_assembly_layers:
        for al in secondary_assembly_layers:
            _diag(f"    sec_asm: name={al.get('name')} side={al.get('side')} "
                   f"thick={al.get('thickness', 0):.6f} ft ({al.get('thickness', 0)*12:.4f} in)")

    if primary_assembly_layers and secondary_assembly_layers:
        # ----------------------------------------------------------
        # Per-individual-layer cumulative adjustments (unscaled)
        # ----------------------------------------------------------
        # Layer thicknesses are used as-is from the catalog.  They
        # represent real physical material dimensions and are NOT
        # compressed to fit within the Revit wall_thickness.
        sec_ext = _ordered_layers_core_outward(secondary_assembly_layers, "exterior")
        sec_int = _ordered_layers_core_outward(secondary_assembly_layers, "interior")
        pri_ext = _ordered_layers_core_outward(primary_assembly_layers, "exterior")
        pri_int = _ordered_layers_core_outward(primary_assembly_layers, "interior")

        _diag("  PER-LAYER PATH active (unscaled catalog thicknesses)")
        _diag("  sec_ext (core-outward): " + str([f"{l.get('name')}={l.get('thickness',0):.6f}ft ({l.get('thickness',0)*12:.4f}in)" for l in sec_ext]))
        _diag("  sec_int (core-outward): " + str([f"{l.get('name')}={l.get('thickness',0):.6f}ft ({l.get('thickness',0)*12:.4f}in)" for l in sec_int]))
        _diag("  pri_ext (core-outward): " + str([f"{l.get('name')}={l.get('thickness',0):.6f}ft ({l.get('thickness',0)*12:.4f}in)" for l in pri_ext]))
        _diag("  pri_int (core-outward): " + str([f"{l.get('name')}={l.get('thickness',0):.6f}ft ({l.get('thickness',0)*12:.4f}in)" for l in pri_int]))

        # --- PRIMARY WALL ---
        # Core: EXTEND by half_sec_core (centerline to opposing core edge)
        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id, end=primary.end,
            junction_id=junction_id, layer_name="core",
            adjustment_type=AdjustmentType.EXTEND,
            amount=half_sec_core,
            connecting_wall_id=secondary.wall_id,
        ))
        _diag(f"  ADJ PRIMARY core: EXTEND {half_sec_core:.6f} ft ({half_sec_core*12:.4f} in) "
               f"= half_sec_core at end={primary.end}")

        # Primary exterior: direction and cumulative pattern from corner type
        p_ext = _ordered_layers_core_outward(primary_assembly_layers, "exterior")
        cumulative = 0.0
        for i, p_layer in enumerate(p_ext):
            opp_name = sec_ext[i].get("name", "?") if i < len(sec_ext) else "NONE(opp ran out)"
            opp_thick = sec_ext[i].get("thickness", 0.0) if i < len(sec_ext) else 0.0
            if pri_ext_cumul == "full":
                if i < len(sec_ext):
                    cumulative += opp_thick
                amount = half_sec_core + cumulative
            else:  # shifted
                amount = half_sec_core + cumulative
                if i < len(sec_ext):
                    cumulative += opp_thick
            adjustments.append(LayerAdjustment(
                wall_id=primary.wall_id, end=primary.end,
                junction_id=junction_id,
                layer_name=p_layer.get("name", f"exterior_{i}"),
                adjustment_type=pri_ext_dir,
                amount=amount,
                connecting_wall_id=secondary.wall_id,
            ))
            _diag(f"  ADJ PRIMARY ext[{i}] '{p_layer.get('name')}': {pri_ext_dir.value.upper()} {amount:.6f} ft ({amount*12:.4f} in) "
                   f"= half_sec_core({half_sec_core:.6f}) + cumul({cumulative:.6f}) "
                   f"[opp[{i}] '{opp_name}'={opp_thick:.6f} ft] "
                   f"pattern={pri_ext_cumul} at end={primary.end}")

        # Primary interior: direction and cumulative pattern from corner type
        p_int = _ordered_layers_core_outward(primary_assembly_layers, "interior")
        cumulative = 0.0
        for i, p_layer in enumerate(p_int):
            opp_name = sec_int[i].get("name", "?") if i < len(sec_int) else "NONE(opp ran out)"
            opp_thick = sec_int[i].get("thickness", 0.0) if i < len(sec_int) else 0.0
            if pri_int_cumul == "full":
                if i < len(sec_int):
                    cumulative += opp_thick
                amount = half_sec_core + cumulative
            else:  # shifted
                amount = half_sec_core + cumulative
                if i < len(sec_int):
                    cumulative += opp_thick
            adjustments.append(LayerAdjustment(
                wall_id=primary.wall_id, end=primary.end,
                junction_id=junction_id,
                layer_name=p_layer.get("name", f"interior_{i}"),
                adjustment_type=pri_int_dir,
                amount=amount,
                connecting_wall_id=secondary.wall_id,
            ))
            _diag(f"  ADJ PRIMARY int[{i}] '{p_layer.get('name')}': {pri_int_dir.value.upper()} {amount:.6f} ft ({amount*12:.4f} in) "
                   f"= half_sec_core({half_sec_core:.6f}) + cumul({cumulative:.6f}) "
                   f"[opp[{i}] '{opp_name}'={opp_thick:.6f} ft] "
                   f"pattern={pri_int_cumul} at end={primary.end}")

        # --- SECONDARY WALL ---
        # Core: TRIM by half_pri_core (centerline to opposing core edge)
        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id, end=secondary.end,
            junction_id=junction_id, layer_name="core",
            adjustment_type=AdjustmentType.TRIM,
            amount=half_pri_core,
            connecting_wall_id=primary.wall_id,
        ))
        _diag(f"  ADJ SECONDARY core: TRIM {half_pri_core:.6f} ft ({half_pri_core*12:.4f} in) "
               f"= half_pri_core at end={secondary.end}")

        # Secondary exterior: direction and cumulative pattern from corner type
        s_ext = _ordered_layers_core_outward(secondary_assembly_layers, "exterior")
        cumulative = 0.0
        for i, s_layer in enumerate(s_ext):
            opp_name = pri_ext[i].get("name", "?") if i < len(pri_ext) else "NONE(opp ran out)"
            opp_thick = pri_ext[i].get("thickness", 0.0) if i < len(pri_ext) else 0.0
            if sec_ext_cumul == "full":
                if i < len(pri_ext):
                    cumulative += opp_thick
                amount = half_pri_core + cumulative
            else:  # shifted
                amount = half_pri_core + cumulative
                if i < len(pri_ext):
                    cumulative += opp_thick
            adjustments.append(LayerAdjustment(
                wall_id=secondary.wall_id, end=secondary.end,
                junction_id=junction_id,
                layer_name=s_layer.get("name", f"exterior_{i}"),
                adjustment_type=sec_ext_dir,
                amount=amount,
                connecting_wall_id=primary.wall_id,
            ))
            _diag(f"  ADJ SECONDARY ext[{i}] '{s_layer.get('name')}': {sec_ext_dir.value.upper()} {amount:.6f} ft ({amount*12:.4f} in) "
                   f"= half_pri_core({half_pri_core:.6f}) + cumul({cumulative:.6f}) "
                   f"[opp[{i}] '{opp_name}'={opp_thick:.6f} ft] "
                   f"pattern={sec_ext_cumul} at end={secondary.end}")

        # Secondary interior: direction and cumulative pattern from corner type
        s_int = _ordered_layers_core_outward(secondary_assembly_layers, "interior")
        cumulative = 0.0
        for i, s_layer in enumerate(s_int):
            opp_name = pri_int[i].get("name", "?") if i < len(pri_int) else "NONE(opp ran out)"
            opp_thick = pri_int[i].get("thickness", 0.0) if i < len(pri_int) else 0.0
            if sec_int_cumul == "full":
                if i < len(pri_int):
                    cumulative += opp_thick
                amount = half_pri_core + cumulative
            else:  # shifted
                amount = half_pri_core + cumulative
                if i < len(pri_int):
                    cumulative += opp_thick
            adjustments.append(LayerAdjustment(
                wall_id=secondary.wall_id, end=secondary.end,
                junction_id=junction_id,
                layer_name=s_layer.get("name", f"interior_{i}"),
                adjustment_type=sec_int_dir,
                amount=amount,
                connecting_wall_id=primary.wall_id,
            ))
            _diag(f"  ADJ SECONDARY int[{i}] '{s_layer.get('name')}': {sec_int_dir.value.upper()} {amount:.6f} ft ({amount*12:.4f} in) "
                   f"= half_pri_core({half_pri_core:.6f}) + cumul({cumulative:.6f}) "
                   f"[opp[{i}] '{opp_name}'={opp_thick:.6f} ft] "
                   f"pattern={sec_int_cumul} at end={secondary.end}")

    else:
        # ----------------------------------------------------------
        # Fallback: 3-aggregate adjustments (no individual layers)
        # Uses WallLayerInfo.  Directions change based on corner type.
        # ----------------------------------------------------------
        _diag(f"  FALLBACK PATH (no individual assembly layers)")
        _diag(f"  CORNER TYPE: {'EXTERIOR' if exterior_corner else 'INTERIOR'}")
        _diag(f"  WARNING: all layers on same side get identical adjustment amount")

        # PRIMARY wall — "full" adds opposing layer thickness, "shifted" uses half_core only
        pri_ext_amount = (half_sec_core + secondary_layers.exterior_thickness
                          if pri_ext_cumul == "full" else half_sec_core)
        pri_int_amount = (half_sec_core + secondary_layers.interior_thickness
                          if pri_int_cumul == "full" else half_sec_core)
        for layer_name, adj_type, amount in [
            ("core", AdjustmentType.EXTEND, half_sec_core),
            ("exterior", pri_ext_dir, pri_ext_amount),
            ("interior", pri_int_dir, pri_int_amount),
        ]:
            adjustments.append(LayerAdjustment(
                wall_id=primary.wall_id, end=primary.end,
                junction_id=junction_id, layer_name=layer_name,
                adjustment_type=adj_type, amount=amount,
                connecting_wall_id=secondary.wall_id,
            ))

        # SECONDARY wall — "full" adds opposing layer thickness, "shifted" uses half_core only
        sec_ext_amount = (half_pri_core + primary_layers.exterior_thickness
                          if sec_ext_cumul == "full" else half_pri_core)
        sec_int_amount = (half_pri_core + primary_layers.interior_thickness
                          if sec_int_cumul == "full" else half_pri_core)
        for layer_name, adj_type, amount in [
            ("core", AdjustmentType.TRIM, half_pri_core),
            ("exterior", sec_ext_dir, sec_ext_amount),
            ("interior", sec_int_dir, sec_int_amount),
        ]:
            adjustments.append(LayerAdjustment(
                wall_id=secondary.wall_id, end=secondary.end,
                junction_id=junction_id, layer_name=layer_name,
                adjustment_type=adj_type, amount=amount,
                connecting_wall_id=primary.wall_id,
            ))

    return adjustments


def _calculate_miter_adjustments(
    junction_id: str,
    conn_a: WallConnection,
    conn_b: WallConnection,
    layers_a: WallLayerInfo,
    layers_b: WallLayerInfo,
    junction_angle: float,
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments for a miter join.

    For a miter join, each layer is cut at the bisector angle.
    The extension amount for a layer at offset d from centerline:
        extension = d / tan(angle / 2)

    Args:
        junction_id: Junction identifier.
        conn_a: First wall connection.
        conn_b: Second wall connection.
        layers_a: Layer info for first wall.
        layers_b: Layer info for second wall.
        junction_angle: Angle between outward directions at junction (degrees).
    """
    adjustments = []

    # Half-angle for miter calculation
    half_angle_rad = math.radians(junction_angle / 2.0)

    # Guard against degenerate angles
    if half_angle_rad < 0.01:  # Nearly 0° (overlapping walls)
        logger.warning(
            "Junction %s: degenerate miter angle %.1f°, skipping",
            junction_id,
            junction_angle,
        )
        return adjustments

    tan_half = math.tan(half_angle_rad)

    for conn, layers in [(conn_a, layers_a), (conn_b, layers_b)]:
        # Each layer's offset from centerline determines its miter extension
        # Core: offset = core_thickness / 2 from centerline on each side
        # Exterior: offset = core/2 + ext_thickness
        # Interior: offset = core/2 + int_thickness

        half_core = layers.core_thickness / 2.0

        layer_offsets = {
            "core": half_core,
            "exterior": half_core + layers.exterior_thickness,
            "interior": half_core + layers.interior_thickness,
        }

        for layer_name, offset in layer_offsets.items():
            amount = offset / tan_half if tan_half > 1e-6 else 0.0

            adjustments.append(LayerAdjustment(
                wall_id=conn.wall_id,
                end=conn.end,
                junction_id=junction_id,
                layer_name=layer_name,
                adjustment_type=AdjustmentType.MITER,
                amount=amount,
                miter_angle=junction_angle / 2.0,
                connecting_wall_id=(
                    conn_b.wall_id if conn is conn_a else conn_a.wall_id
                ),
            ))

    return adjustments


def _calculate_t_intersection_adjustments(
    junction_id: str,
    continuous: WallConnection,
    terminating: WallConnection,
    continuous_layers: WallLayerInfo,
    terminating_layers: WallLayerInfo,
    continuous_assembly_layers: Optional[List[Dict]] = None,
    terminating_assembly_layers: Optional[List[Dict]] = None,
    midspan_only: bool = False,
    midspan_cumulative: str = "shifted",
) -> List[LayerAdjustment]:
    """Calculate adjustments for a T-intersection.

    The continuous wall gets midspan gap adjustments where the
    terminating wall meets it.  The terminating wall trims all
    layers at the junction end (unless ``midspan_only=True``).

    Each terminating layer trims by ``half_cont_core`` plus the
    cumulative thickness of the continuous wall's layers on
    the same side up to that layer's stack position.

    Midspan adjustments are **one-sided** for T-intersections: only
    the layers on the side the terminating wall body is on get gaps
    (plus core, which always gets a gap).  For X-crossings
    (``midspan_only=True``), both sides get gaps.

    Midspan cumulative pattern:
      - **shifted** (compute-then-add): layer 0 = ``half_term_core``,
        layer 1 = ``half_term_core + term[0]``.  Used for the primary
        wall at X-crossings and for T-intersections.
      - **full** (add-then-compute): layer 0 = ``half_term_core + term[0]``,
        layer 1 = ``half_term_core + term[0] + term[1]``.  Used for
        the secondary wall at X-crossings to create interlocking gaps.

    Args:
        junction_id: Junction identifier.
        continuous: Continuous wall connection (passes through).
        terminating: Terminating wall connection (butts against continuous).
        continuous_layers: Aggregate layer info for continuous wall.
        terminating_layers: Aggregate layer info for terminating wall.
        continuous_assembly_layers: Optional individual layer dicts for
            the continuous wall.
        terminating_assembly_layers: Optional individual layer dicts for
            the terminating wall.
        midspan_only: If True, skip terminating endpoint adjustments.
            Used for X-crossings where neither wall actually terminates.
        midspan_cumulative: Cumulative pattern for midspan gap widths.
            "shifted" (default) or "full".

    Returns:
        List of LayerAdjustments for the terminating and continuous walls.
    """
    adjustments: List[LayerAdjustment] = []

    half_cont_core = continuous_layers.core_thickness / 2.0

    # When the terminating wall is also a midspan connection (X-crossings),
    # its adjustments need the midspan_u value so downstream can create gaps.
    term_midspan_u = terminating.midspan_u if terminating.is_midspan else None

    _diag(f"\n=== T-INTERSECTION ADJUSTMENTS (junction={junction_id}) ===")
    _diag(f"  ASSUMPTION: Terminating wall endpoint is AT the virtual centerline corner")
    _diag(f"  ASSUMPTION: half_cont_core is the distance from centerline to continuous core face")
    _diag(f"  Continuous wall: {continuous.wall_id} (passes through, NO adjustments)")
    _diag(f"    wall_thickness={continuous.wall_thickness:.6f} ft ({continuous.wall_thickness*12:.4f} in)")
    _diag(f"    layers: ext={continuous_layers.exterior_thickness:.6f}, "
           f"core={continuous_layers.core_thickness:.6f}, "
           f"int={continuous_layers.interior_thickness:.6f}")
    _diag(f"  Terminating wall: {terminating.wall_id} end={terminating.end} (ALL layers TRIM)")
    _diag(f"    wall_thickness={terminating.wall_thickness:.6f} ft ({terminating.wall_thickness*12:.4f} in)")
    _diag(f"    layers: ext={terminating_layers.exterior_thickness:.6f}, "
           f"core={terminating_layers.core_thickness:.6f}, "
           f"int={terminating_layers.interior_thickness:.6f}")
    _diag(f"  half_cont_core = {half_cont_core:.6f} ft ({half_cont_core*12:.4f} in)")
    _diag(f"  midspan_only = {midspan_only}")

    # =================================================================
    # Terminating wall endpoint adjustments (skip when midspan_only)
    # =================================================================
    if not midspan_only:
        if continuous_assembly_layers and terminating_assembly_layers:
            # Per-layer cumulative adjustments (unscaled catalog thicknesses)
            cont_ext = _ordered_layers_core_outward(continuous_assembly_layers, "exterior")
            cont_int = _ordered_layers_core_outward(continuous_assembly_layers, "interior")

            _diag("  PER-LAYER PATH active (unscaled catalog thicknesses)")
            _diag("  cont_ext (core-outward): " + str([f"{l.get('name')}={l.get('thickness',0):.6f}ft ({l.get('thickness',0)*12:.4f}in)" for l in cont_ext]))
            _diag("  cont_int (core-outward): " + str([f"{l.get('name')}={l.get('thickness',0):.6f}ft ({l.get('thickness',0)*12:.4f}in)" for l in cont_int]))

            # Core: TRIM by half_cont_core
            adjustments.append(LayerAdjustment(
                wall_id=terminating.wall_id, end=terminating.end,
                junction_id=junction_id, layer_name="core",
                adjustment_type=AdjustmentType.TRIM,
                amount=half_cont_core,
                connecting_wall_id=continuous.wall_id,
                midspan_u=term_midspan_u,
            ))
            _diag(f"  ADJ TERM core: TRIM {half_cont_core:.6f} ft ({half_cont_core*12:.4f} in) "
                   f"= half_cont_core")

            # Terminating exterior: each TRIMS by half_cont_core + cumulative(cont_ext)
            t_ext = _ordered_layers_core_outward(terminating_assembly_layers, "exterior")
            cumulative = 0.0
            for i, t_layer in enumerate(t_ext):
                cont_layer_name = cont_ext[i].get("name", "?") if i < len(cont_ext) else "NONE(cont ran out)"
                cont_layer_thick = cont_ext[i].get("thickness", 0.0) if i < len(cont_ext) else 0.0
                if i < len(cont_ext):
                    cumulative += cont_ext[i].get("thickness", 0.0)
                amount = half_cont_core + cumulative
                adjustments.append(LayerAdjustment(
                    wall_id=terminating.wall_id, end=terminating.end,
                    junction_id=junction_id,
                    layer_name=t_layer.get("name", f"exterior_{i}"),
                    adjustment_type=AdjustmentType.TRIM,
                    amount=amount,
                    connecting_wall_id=continuous.wall_id,
                    midspan_u=term_midspan_u,
                ))
                _diag(f"  ADJ TERM ext[{i}] '{t_layer.get('name')}': TRIM {amount:.6f} ft ({amount*12:.4f} in) "
                       f"= half_cont_core({half_cont_core:.6f}) + cumul({cumulative:.6f}) "
                       f"[opposing: '{cont_layer_name}' thick={cont_layer_thick:.6f} ft ({cont_layer_thick*12:.4f} in)]")

            # Terminating interior: each TRIMS by half_cont_core + cumulative(cont_int)
            t_int = _ordered_layers_core_outward(terminating_assembly_layers, "interior")
            cumulative = 0.0
            for i, t_layer in enumerate(t_int):
                cont_layer_name = cont_int[i].get("name", "?") if i < len(cont_int) else "NONE(cont ran out)"
                cont_layer_thick = cont_int[i].get("thickness", 0.0) if i < len(cont_int) else 0.0
                if i < len(cont_int):
                    cumulative += cont_int[i].get("thickness", 0.0)
                amount = half_cont_core + cumulative
                adjustments.append(LayerAdjustment(
                    wall_id=terminating.wall_id, end=terminating.end,
                    junction_id=junction_id,
                    layer_name=t_layer.get("name", f"interior_{i}"),
                    adjustment_type=AdjustmentType.TRIM,
                    amount=amount,
                    connecting_wall_id=continuous.wall_id,
                    midspan_u=term_midspan_u,
                ))
                _diag(f"  ADJ TERM int[{i}] '{t_layer.get('name')}': TRIM {amount:.6f} ft ({amount*12:.4f} in) "
                       f"= half_cont_core({half_cont_core:.6f}) + cumul({cumulative:.6f}) "
                       f"[opposing: '{cont_layer_name}' thick={cont_layer_thick:.6f} ft ({cont_layer_thick*12:.4f} in)]")

        else:
            # Fallback: 3-aggregate adjustments (unscaled WallLayerInfo)
            _diag("  FALLBACK PATH (no assembly layers) — 3 aggregate adjustments")
            for layer_name, amount in [
                ("core", half_cont_core),
                ("exterior",
                 half_cont_core + continuous_layers.exterior_thickness),
                ("interior",
                 half_cont_core + continuous_layers.interior_thickness),
            ]:
                adjustments.append(LayerAdjustment(
                    wall_id=terminating.wall_id, end=terminating.end,
                    junction_id=junction_id, layer_name=layer_name,
                    adjustment_type=AdjustmentType.TRIM, amount=amount,
                    connecting_wall_id=continuous.wall_id,
                    midspan_u=term_midspan_u,
                ))
                _diag(f"  ADJ TERM '{layer_name}': TRIM {amount:.6f} ft ({amount*12:.4f} in)")
    else:
        _diag("  SKIPPING terminating endpoint adjustments (midspan_only=True)")

    # ===================================================================
    # Continuous wall midspan adjustments
    # ===================================================================
    # The continuous wall's sheathing needs a gap where the terminating
    # wall meets it.
    #
    # **T-intersection (midspan_only=False)**: One-sided gaps — only
    # layers on the side where the terminating wall body IS get gaps.
    #
    # **X-crossing (midspan_only=True)**: Both-sided gaps — the crossing
    # wall passes through both sides of the continuous wall.
    #
    # Approach side detection (for T-intersections):
    #   _outward_direction_at_junction(terminating) points AWAY from the
    #   junction, i.e., toward where the terminating wall body IS.
    #   dot(continuous.z_axis, outward):
    #   - dot < 0: outward opposes z_axis → wall body is on -z side → INTERIOR
    #   - dot >= 0: outward aligns with z_axis → wall body is on +z side → EXTERIOR
    #
    # Cumulative pattern controlled by midspan_cumulative:
    #   "shifted" (compute-then-add): layer 0 = half_term_core
    #   "full"    (add-then-compute): layer 0 = half_term_core + term[0]
    half_term_core = terminating_layers.core_thickness / 2.0
    midspan_u = continuous.midspan_u

    if midspan_u is not None:
        # Determine which side of the continuous wall the terminating
        # wall body is on
        term_outward = _outward_direction_at_junction(terminating)
        dot_approach = (
            continuous.z_axis[0] * term_outward[0]
            + continuous.z_axis[1] * term_outward[1]
            + continuous.z_axis[2] * term_outward[2]
        )
        # dot < 0 → wall body on -z (interior) side
        # dot >= 0 → wall body on +z (exterior) side
        approach_side = "interior" if dot_approach < 0 else "exterior"

        # X-crossing: both sides get gaps (crossing wall passes through)
        # T-intersection: only the approach side gets gaps
        gap_exterior = midspan_only or approach_side == "exterior"
        gap_interior = midspan_only or approach_side == "interior"

        use_full = midspan_cumulative == "full"

        # Asymmetric gap edge: which term side faces +U vs -U of cont wall
        cont_x = continuous.direction
        term_z = terminating.z_axis
        dot_term_z_cont_x = (
            term_z[0] * cont_x[0]
            + term_z[1] * cont_x[1]
            + term_z[2] * cont_x[2]
        )
        # dot > 0: term exterior faces +U, term interior faces -U
        # dot < 0: term exterior faces -U, term interior faces +U
        # dot == 0: symmetric (ext -> +U arbitrarily)

        _diag(f"\n  CONTINUOUS WALL MIDSPAN ADJUSTMENTS (midspan_u={midspan_u:.4f})")
        _diag(f"  half_term_core = {half_term_core:.6f} ft ({half_term_core*12:.4f} in)")
        _diag(f"  approach_side = {approach_side} (dot={dot_approach:.4f})")
        _diag(f"  gap_exterior={gap_exterior}, gap_interior={gap_interior} "
               f"(midspan_only={midspan_only})")
        _diag(f"  midspan_cumulative = {midspan_cumulative}")
        _diag(f"  dot_term_z_cont_x = {dot_term_z_cont_x:.4f}")

        if terminating_assembly_layers and continuous_assembly_layers:
            term_ext = _ordered_layers_core_outward(terminating_assembly_layers, "exterior")
            term_int = _ordered_layers_core_outward(terminating_assembly_layers, "interior")
            _diag(f"  term_ext: {len(term_ext)} layers, term_int: {len(term_int)} layers")

            # Continuous wall core midspan:
            # - T-intersection: core runs through (no gap). Skip.
            # - X-crossing primary (shifted): core runs through. Skip.
            # - X-crossing secondary (full): core terminates at primary. TRIM.
            if use_full:
                adjustments.append(LayerAdjustment(
                    wall_id=continuous.wall_id, end="midspan",
                    junction_id=junction_id, layer_name="core",
                    adjustment_type=AdjustmentType.TRIM,
                    amount=half_term_core,
                    connecting_wall_id=terminating.wall_id,
                    midspan_u=midspan_u,
                ))
                _diag(f"  ADJ CONT core: TRIM {half_term_core:.6f} ft at midspan_u={midspan_u:.4f} "
                       f"(secondary wall core terminates at X-crossing)")
            else:
                _diag(f"  SKIP CONT core midspan (primary/continuous wall core runs through)")

            # --- Asymmetric gap edge computation ---
            # dot_term_z_cont_x computed above (before branch)
            if dot_term_z_cont_x >= 0:
                term_pos_layers = term_ext  # layers on the +U side
                term_neg_layers = term_int  # layers on the -U side
            else:
                term_pos_layers = term_int  # layers on the +U side
                term_neg_layers = term_ext  # layers on the -U side

            _diag(f"  ASYMMETRIC GAP: dot_term_z_cont_x={dot_term_z_cont_x:.4f} "
                   f"-> +U uses term_{'ext' if dot_term_z_cont_x >= 0 else 'int'} "
                   f"({len(term_pos_layers)} layers), "
                   f"-U uses term_{'int' if dot_term_z_cont_x >= 0 else 'ext'} "
                   f"({len(term_neg_layers)} layers)")

            # Continuous wall exterior layers
            if gap_exterior:
                c_ext = _ordered_layers_core_outward(continuous_assembly_layers, "exterior")
                cumul_pos = 0.0
                cumul_neg = 0.0
                for i, c_layer in enumerate(c_ext):
                    if use_full:
                        # Full: add FIRST, then compute
                        if i < len(term_pos_layers):
                            cumul_pos += term_pos_layers[i].get("thickness", 0.0)
                        if i < len(term_neg_layers):
                            cumul_neg += term_neg_layers[i].get("thickness", 0.0)
                        amount_pos = half_term_core + cumul_pos
                        amount_neg_val = half_term_core + cumul_neg
                    else:
                        # Shifted: compute FIRST, then add
                        amount_pos = half_term_core + cumul_pos
                        amount_neg_val = half_term_core + cumul_neg
                        if i < len(term_pos_layers):
                            cumul_pos += term_pos_layers[i].get("thickness", 0.0)
                        if i < len(term_neg_layers):
                            cumul_neg += term_neg_layers[i].get("thickness", 0.0)
                    # Set amount_neg only when it differs from amount_pos
                    adj_amount_neg = amount_neg_val if abs(amount_neg_val - amount_pos) > 1e-9 else None
                    adjustments.append(LayerAdjustment(
                        wall_id=continuous.wall_id, end="midspan",
                        junction_id=junction_id,
                        layer_name=c_layer.get("name", f"exterior_{i}"),
                        adjustment_type=AdjustmentType.TRIM,
                        amount=amount_pos,
                        connecting_wall_id=terminating.wall_id,
                        midspan_u=midspan_u,
                        amount_neg=adj_amount_neg,
                    ))
                    _diag(f"  ADJ CONT ext[{i}] '{c_layer.get('name')}': TRIM "
                           f"amount_pos={amount_pos:.6f} amount_neg={amount_neg_val:.6f} ft "
                           f"({midspan_cumulative} cumul_pos={cumul_pos:.6f} cumul_neg={cumul_neg:.6f}) "
                           f"at midspan_u={midspan_u:.4f}")
            else:
                _diag("  SKIPPING exterior midspan (approach_side=interior, T-intersection)")

            # Continuous wall interior layers
            if gap_interior:
                c_int = _ordered_layers_core_outward(continuous_assembly_layers, "interior")
                cumul_pos = 0.0
                cumul_neg = 0.0
                for i, c_layer in enumerate(c_int):
                    if use_full:
                        # Full: add FIRST, then compute
                        if i < len(term_pos_layers):
                            cumul_pos += term_pos_layers[i].get("thickness", 0.0)
                        if i < len(term_neg_layers):
                            cumul_neg += term_neg_layers[i].get("thickness", 0.0)
                        amount_pos = half_term_core + cumul_pos
                        amount_neg_val = half_term_core + cumul_neg
                    else:
                        # Shifted: compute FIRST, then add
                        amount_pos = half_term_core + cumul_pos
                        amount_neg_val = half_term_core + cumul_neg
                        if i < len(term_pos_layers):
                            cumul_pos += term_pos_layers[i].get("thickness", 0.0)
                        if i < len(term_neg_layers):
                            cumul_neg += term_neg_layers[i].get("thickness", 0.0)
                    # Set amount_neg only when it differs from amount_pos
                    adj_amount_neg = amount_neg_val if abs(amount_neg_val - amount_pos) > 1e-9 else None
                    adjustments.append(LayerAdjustment(
                        wall_id=continuous.wall_id, end="midspan",
                        junction_id=junction_id,
                        layer_name=c_layer.get("name", f"interior_{i}"),
                        adjustment_type=AdjustmentType.TRIM,
                        amount=amount_pos,
                        connecting_wall_id=terminating.wall_id,
                        midspan_u=midspan_u,
                        amount_neg=adj_amount_neg,
                    ))
                    _diag(f"  ADJ CONT int[{i}] '{c_layer.get('name')}': TRIM "
                           f"amount_pos={amount_pos:.6f} amount_neg={amount_neg_val:.6f} ft "
                           f"({midspan_cumulative} cumul_pos={cumul_pos:.6f} cumul_neg={cumul_neg:.6f}) "
                           f"at midspan_u={midspan_u:.4f}")
            else:
                _diag("  SKIPPING interior midspan (approach_side=exterior, T-intersection)")

        else:
            # Fallback: aggregate midspan adjustments (no assembly layers)
            _diag(f"  CONT MIDSPAN FALLBACK (no assembly layers, pattern={midspan_cumulative})")
            # Core: NO midspan TRIM — core runs continuously through junction
            # Core: only TRIM for X-crossing secondary (use_full), skip otherwise
            if use_full:
                adjustments.append(LayerAdjustment(
                    wall_id=continuous.wall_id, end="midspan",
                    junction_id=junction_id, layer_name="core",
                    adjustment_type=AdjustmentType.TRIM,
                    amount=half_term_core,
                    connecting_wall_id=terminating.wall_id,
                    midspan_u=midspan_u,
                ))
                _diag(f"  ADJ CONT 'core': TRIM {half_term_core:.6f} ft at midspan_u={midspan_u:.4f}")
            else:
                _diag(f"  SKIP CONT 'core' midspan (primary/continuous wall core runs through)")

            # Asymmetric: map term ext/int to +U/-U based on dot_term_z_cont_x
            if dot_term_z_cont_x >= 0:
                term_pos_thick = terminating_layers.exterior_thickness
                term_neg_thick = terminating_layers.interior_thickness
            else:
                term_pos_thick = terminating_layers.interior_thickness
                term_neg_thick = terminating_layers.exterior_thickness

            if gap_exterior:
                if use_full:
                    ext_amount_pos = half_term_core + term_pos_thick
                    ext_amount_neg = half_term_core + term_neg_thick
                else:
                    ext_amount_pos = half_term_core
                    ext_amount_neg = half_term_core
                adj_amount_neg = ext_amount_neg if abs(ext_amount_neg - ext_amount_pos) > 1e-9 else None
                adjustments.append(LayerAdjustment(
                    wall_id=continuous.wall_id, end="midspan",
                    junction_id=junction_id, layer_name="exterior",
                    adjustment_type=AdjustmentType.TRIM, amount=ext_amount_pos,
                    connecting_wall_id=terminating.wall_id,
                    midspan_u=midspan_u,
                    amount_neg=adj_amount_neg,
                ))
                _diag(f"  ADJ CONT 'exterior': TRIM pos={ext_amount_pos:.6f} neg={ext_amount_neg:.6f} ft "
                       f"at midspan_u={midspan_u:.4f}")
            if gap_interior:
                if use_full:
                    int_amount_pos = half_term_core + term_pos_thick
                    int_amount_neg = half_term_core + term_neg_thick
                else:
                    int_amount_pos = half_term_core
                    int_amount_neg = half_term_core
                adj_amount_neg = int_amount_neg if abs(int_amount_neg - int_amount_pos) > 1e-9 else None
                adjustments.append(LayerAdjustment(
                    wall_id=continuous.wall_id, end="midspan",
                    junction_id=junction_id, layer_name="interior",
                    adjustment_type=AdjustmentType.TRIM, amount=int_amount_pos,
                    connecting_wall_id=terminating.wall_id,
                    midspan_u=midspan_u,
                    amount_neg=adj_amount_neg,
                ))
                _diag(f"  ADJ CONT 'interior': TRIM pos={int_amount_pos:.6f} neg={int_amount_neg:.6f} ft "
                       f"at midspan_u={midspan_u:.4f}")
    else:
        _diag("  No midspan_u on continuous wall — skipping midspan adjustments")

    _diag(f"  Total T-intersection adjustments: {len(adjustments)}")
    return adjustments


# =============================================================================
# Junction Resolution
# =============================================================================


def _resolve_two_wall_junction(
    node: JunctionNode,
    wall_layers: Dict[str, WallLayerInfo],
    default_join_type: str,
    priority_strategy: str,
    override: Optional[Dict],
    wall_assemblies: Optional[Dict[str, List[Dict]]] = None,
) -> JunctionResolution:
    """Resolve a junction between two walls (L-corner or T-intersection)."""
    # Get the two main connections (skip extra for now)
    non_midspan = [c for c in node.connections if not c.is_midspan]
    midspan = [c for c in node.connections if c.is_midspan]

    # T-intersection handling
    if node.junction_type == JunctionType.T_INTERSECTION:
        continuous, terminating = _determine_t_priority(node.connections)

        cont_layers = wall_layers.get(
            continuous.wall_id,
            build_default_wall_layers(continuous.wall_id, continuous.wall_thickness),
        )
        term_layers = wall_layers.get(
            terminating.wall_id,
            build_default_wall_layers(terminating.wall_id, terminating.wall_thickness),
        )

        cont_assembly = (wall_assemblies or {}).get(continuous.wall_id)
        term_assembly = (wall_assemblies or {}).get(terminating.wall_id)

        adjustments = _calculate_t_intersection_adjustments(
            node.id, continuous, terminating, cont_layers, term_layers,
            continuous_assembly_layers=cont_assembly,
            terminating_assembly_layers=term_assembly,
        )

        return JunctionResolution(
            junction_id=node.id,
            join_type=JoinType.BUTT,
            primary_wall_id=continuous.wall_id,
            secondary_wall_id=terminating.wall_id,
            confidence=0.95,
            reason="T-intersection: continuous wall unchanged, terminating wall trims",
            layer_adjustments=adjustments,
            is_user_override=False,
        )

    # L-Corner handling
    if len(non_midspan) < 2:
        logger.warning("Junction %s has < 2 non-midspan connections", node.id)
        return JunctionResolution(
            junction_id=node.id,
            join_type=JoinType.NONE,
            primary_wall_id=non_midspan[0].wall_id if non_midspan else "",
            secondary_wall_id="",
            confidence=0.0,
            reason="Insufficient connections for resolution",
        )

    conn_a = non_midspan[0]
    conn_b = non_midspan[1]

    # Determine join type
    if override and "join_type" in override:
        join_type = JoinType(override["join_type"])
    else:
        join_type = JoinType(default_join_type)

    # Determine priority
    if override and "primary_wall_id" in override:
        if override["primary_wall_id"] == conn_a.wall_id:
            primary, secondary = conn_a, conn_b
        else:
            primary, secondary = conn_b, conn_a
        confidence = 1.0
        reason = "User override"
        is_override = True
    else:
        primary, secondary = _determine_priority(conn_a, conn_b, priority_strategy)
        confidence = 0.7
        reason = f"Auto: {priority_strategy} strategy"
        is_override = False

    # Get layer info
    pri_layers = wall_layers.get(
        primary.wall_id,
        build_default_wall_layers(primary.wall_id, primary.wall_thickness),
    )
    sec_layers = wall_layers.get(
        secondary.wall_id,
        build_default_wall_layers(secondary.wall_id, secondary.wall_thickness),
    )

    # Get individual assembly layers (if available)
    pri_assembly = (wall_assemblies or {}).get(primary.wall_id)
    sec_assembly = (wall_assemblies or {}).get(secondary.wall_id)

    # Calculate per-layer adjustments
    if join_type == JoinType.BUTT:
        adjustments = _calculate_butt_adjustments(
            node.id, primary, secondary, pri_layers, sec_layers,
            primary_assembly_layers=pri_assembly,
            secondary_assembly_layers=sec_assembly,
        )
    elif join_type == JoinType.MITER:
        out_a = _outward_direction_at_junction(primary)
        out_b = _outward_direction_at_junction(secondary)
        angle = _calculate_angle(out_a, out_b)
        adjustments = _calculate_miter_adjustments(
            node.id, primary, secondary, pri_layers, sec_layers, angle
        )
    else:
        adjustments = []

    # Determine corner side for L-corners
    corner_side = None
    if node.junction_type == JunctionType.L_CORNER:
        corner_side = (
            "exterior" if _is_exterior_corner(primary, secondary) else "interior"
        )

    return JunctionResolution(
        junction_id=node.id,
        join_type=join_type,
        primary_wall_id=primary.wall_id,
        secondary_wall_id=secondary.wall_id,
        confidence=confidence,
        reason=reason,
        layer_adjustments=adjustments,
        is_user_override=is_override,
        corner_side=corner_side,
    )


def _resolve_multi_wall_junction(
    node: JunctionNode,
    wall_layers: Dict[str, WallLayerInfo],
    default_join_type: str,
    priority_strategy: str,
    override: Optional[Dict],
    wall_assemblies: Optional[Dict[str, List[Dict]]] = None,
) -> List[JunctionResolution]:
    """Resolve a junction with 3+ walls by processing pairwise.

    For X-crossings: identify the two inline pairs and resolve each
    pair independently.

    For multi-way: resolve the dominant pair first, then remaining.
    """
    resolutions = []
    connections = node.connections

    if node.junction_type == JunctionType.X_CROSSING and len(connections) == 2 and all(c.is_midspan for c in connections):
        # Two-midspan X-crossing detected via centerline intersection.
        # Each wall is both "continuous through" and "crossed by" the other.
        # Emit bidirectional midspan TRIM adjustments.
        conn_a = connections[0]
        conn_b = connections[1]

        layers_a = wall_layers.get(
            conn_a.wall_id,
            build_default_wall_layers(conn_a.wall_id, conn_a.wall_thickness),
        )
        layers_b = wall_layers.get(
            conn_b.wall_id,
            build_default_wall_layers(conn_b.wall_id, conn_b.wall_thickness),
        )

        asm_a = (wall_assemblies or {}).get(conn_a.wall_id)
        asm_b = (wall_assemblies or {}).get(conn_b.wall_id)

        # Wall A gets a gap where wall B crosses it
        adjs_a = _calculate_t_intersection_adjustments(
            node.id, conn_a, conn_b, layers_a, layers_b,
            continuous_assembly_layers=asm_a,
            terminating_assembly_layers=asm_b,
            midspan_only=True,
        )
        # Wall B gets a gap where wall A crosses it (secondary: full cumulative)
        adjs_b = _calculate_t_intersection_adjustments(
            node.id, conn_b, conn_a, layers_b, layers_a,
            continuous_assembly_layers=asm_b,
            terminating_assembly_layers=asm_a,
            midspan_only=True,
            midspan_cumulative="full",
        )

        all_adjustments = adjs_a + adjs_b
        resolutions.append(JunctionResolution(
            junction_id=node.id,
            join_type=JoinType.BUTT,
            primary_wall_id=conn_a.wall_id,
            secondary_wall_id=conn_b.wall_id,
            confidence=0.9,
            reason="X-crossing: bidirectional midspan gaps",
            layer_adjustments=all_adjustments,
        ))

    elif node.junction_type == JunctionType.X_CROSSING and len(connections) == 4:
        # Find two inline pairs
        pairs = _find_inline_pairs(connections)
        for pair in pairs:
            # Create a temporary 2-wall node for each pair
            temp_node = JunctionNode(
                id=node.id,
                position=node.position,
                junction_type=JunctionType.L_CORNER,
                connections=list(pair),
            )
            res = _resolve_two_wall_junction(
                temp_node, wall_layers, default_join_type,
                priority_strategy, override, wall_assemblies,
            )
            resolutions.append(res)
    else:
        # Multi-way: process pairwise with the first two connections
        logger.warning(
            "Junction %s is multi-way (%d connections) — "
            "resolving first pair only (best-effort)",
            node.id,
            len(connections),
        )
        if len(connections) >= 2:
            temp_node = JunctionNode(
                id=node.id,
                position=node.position,
                junction_type=JunctionType.L_CORNER,
                connections=connections[:2],
            )
            res = _resolve_two_wall_junction(
                temp_node, wall_layers, default_join_type,
                priority_strategy, override, wall_assemblies,
            )
            resolutions.append(res)

    return resolutions


def _find_inline_pairs(
    connections: List[WallConnection],
    threshold: float = 170.0,
) -> List[Tuple[WallConnection, WallConnection]]:
    """Find pairs of connections that are approximately inline (~180°)."""
    pairs = []
    used = set()

    for i in range(len(connections)):
        if i in used:
            continue
        for j in range(i + 1, len(connections)):
            if j in used:
                continue
            out_i = _outward_direction_at_junction(connections[i])
            out_j = _outward_direction_at_junction(connections[j])
            angle = _calculate_angle(out_i, out_j)
            if angle >= threshold:
                pairs.append((connections[i], connections[j]))
                used.add(i)
                used.add(j)
                break

    return pairs


# =============================================================================
# Main Entry Points
# =============================================================================


def resolve_all_junctions(
    nodes: Dict[str, JunctionNode],
    wall_layers: Dict[str, WallLayerInfo],
    default_join_type: str = "butt",
    priority_strategy: str = "longer_wall",
    user_overrides: Optional[Dict[str, Dict]] = None,
    wall_assemblies: Optional[Dict[str, List[Dict]]] = None,
) -> List[JunctionResolution]:
    """Resolve join type and priority for every junction.

    Args:
        nodes: Junction graph nodes from build_junction_graph().
        wall_layers: Layer info per wall from build_wall_layers_map().
        default_join_type: "butt" or "miter".
        priority_strategy: "longer_wall", "exterior_first", or "alternate".
        user_overrides: Optional dict of junction_id → override settings.
            Each override can have:
            - "join_type": "butt" or "miter"
            - "primary_wall_id": wall_id of wall that should extend

    Returns:
        List of JunctionResolution with layer adjustments.
    """
    resolutions = []
    overrides = user_overrides or {}

    for node in nodes.values():
        if node.junction_type in (JunctionType.FREE_END, JunctionType.INLINE):
            continue

        override = overrides.get(node.id)

        if node.junction_type in (
            JunctionType.L_CORNER,
            JunctionType.T_INTERSECTION,
        ):
            resolution = _resolve_two_wall_junction(
                node, wall_layers, default_join_type,
                priority_strategy, override, wall_assemblies,
            )
            resolutions.append(resolution)

        elif node.junction_type in (
            JunctionType.X_CROSSING,
            JunctionType.MULTI_WAY,
        ):
            multi_res = _resolve_multi_wall_junction(
                node, wall_layers, default_join_type,
                priority_strategy, override, wall_assemblies,
            )
            resolutions.extend(multi_res)

    logger.info("Resolved %d junctions", len(resolutions))
    return resolutions


def build_wall_adjustments_map(
    resolutions: List[JunctionResolution],
) -> Dict[str, List[LayerAdjustment]]:
    """Build a per-wall lookup of all layer adjustments.

    Collects all LayerAdjustments from all resolutions and groups
    them by wall_id for easy downstream consumption.

    Args:
        resolutions: List of junction resolutions.

    Returns:
        Dict mapping wall_id to list of LayerAdjustments.
    """
    result: Dict[str, List[LayerAdjustment]] = {}

    for resolution in resolutions:
        for adj in resolution.layer_adjustments:
            if adj.wall_id not in result:
                result[adj.wall_id] = []
            result[adj.wall_id].append(adj)

    return result


def analyze_junctions(
    walls_data: List[Dict],
    tolerance: float = 0.1,
    t_intersection_tolerance: float = 0.15,
    inline_angle_threshold: float = 170.0,
    default_join_type: str = "butt",
    priority_strategy: str = "longer_wall",
    user_overrides: Optional[Dict[str, Dict]] = None,
    layer_overrides: Optional[Dict[str, Dict]] = None,
) -> JunctionGraph:
    """Main entry point: analyze all wall junctions end-to-end.

    This is the single function that downstream code should call.
    It runs the full pipeline: detect → classify → resolve → adjust.

    Args:
        walls_data: List of wall dicts from walls_json.
        tolerance: Endpoint matching tolerance in feet.
        t_intersection_tolerance: T-intersection matching tolerance in feet.
        inline_angle_threshold: Angle threshold for inline detection (degrees).
        default_join_type: Default join strategy ("butt" or "miter").
        priority_strategy: Priority strategy ("longer_wall", "exterior_first", "alternate").
        user_overrides: Per-junction overrides (junction_id → settings).
        layer_overrides: Per-wall layer thickness overrides (wall_id → thicknesses).

    Returns:
        JunctionGraph with all nodes, resolutions, and per-wall adjustments.
    """
    from .junction_detector import build_junction_graph

    # Phase 1+2: Build and classify junction graph
    nodes = build_junction_graph(
        walls_data,
        tolerance=tolerance,
        t_intersection_tolerance=t_intersection_tolerance,
        inline_angle_threshold=inline_angle_threshold,
    )

    # Build layer info for all walls
    wall_layers = build_wall_layers_map(walls_data, layer_overrides)

    # Build individual assembly layer map (for per-layer cumulative adjustments)
    wall_assemblies = _build_wall_assemblies_map(walls_data)

    # Phase 3+4: Resolve junctions and calculate adjustments
    resolutions = resolve_all_junctions(
        nodes,
        wall_layers,
        default_join_type=default_join_type,
        priority_strategy=priority_strategy,
        user_overrides=user_overrides,
        wall_assemblies=wall_assemblies,
    )

    # Build per-wall adjustment lookup
    wall_adjustments = build_wall_adjustments_map(resolutions)

    return JunctionGraph(
        nodes=nodes,
        wall_layers=wall_layers,
        resolutions=resolutions,
        wall_adjustments=wall_adjustments,
    )


def recompute_adjustments(
    junctions_data: Dict[str, Any],
    walls_data: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Recompute per-layer adjustments using resolved assembly data.

    Phase 2 of the two-phase junction processing flow:

    - Phase 1 (Junction Analyzer): detect junctions, classify, determine
      primary/secondary walls. Outputs topology + best-effort adjustments.
    - Phase 2 (this function): recompute adjustment amounts using the
      actual assembly layers from enriched ``walls_data``.

    This solves the chicken-and-egg problem where assembly resolution
    happens after junction detection: the Junction Analyzer runs on
    raw Revit walls (possibly only a single core layer), while this
    function runs after ``resolve_all_walls()`` has assigned full
    multi-layer assemblies.

    Args:
        junctions_data: Parsed junctions_json dict. Must contain:
            - ``junctions``: list of node dicts with connections.
            - ``resolutions``: list of resolution dicts with
              ``junction_id``, ``join_type``, ``primary_wall_id``,
              ``secondary_wall_id``.
        walls_data: Wall dicts **with resolved** ``wall_assembly``.
            Each wall should have been processed by ``resolve_all_walls()``.

    Returns:
        Dict mapping wall_id to list of serialized adjustment dicts.
        Drop-in replacement for ``junctions_data["wall_adjustments"]``.
    """
    # Build lookup maps from enriched walls
    _diag("=== recompute_adjustments (Phase 2) ===")
    _diag(f"  walls_data count: {len(walls_data)}")
    wall_layers = build_wall_layers_map(walls_data)
    wall_assemblies = _build_wall_assemblies_map(walls_data)
    wall_lookup: Dict[str, Dict] = {
        w.get("wall_id", ""): w for w in walls_data
    }
    _diag(f"  wall_layers: {list(wall_layers.keys())}")
    _diag(f"  wall_assemblies: {list(wall_assemblies.keys())}")
    for wid, wli in wall_layers.items():
        _diag(f"    WallLayerInfo[{wid}]: ext={wli.exterior_thickness:.6f} "
               f"core={wli.core_thickness:.6f} int={wli.interior_thickness:.6f} "
               f"total={wli.total_thickness:.6f} source={wli.source}")
    for wid, asm in wall_assemblies.items():
        _diag(f"    Assembly[{wid}]: {len(asm)} layers")
        for al in asm:
            _diag(f"      {al.get('name')} side={al.get('side')} "
                   f"thick={al.get('thickness', 0):.6f} ft func={al.get('function')}")

    # Read topology from junctions_data
    resolutions_data = junctions_data.get("resolutions", [])
    junctions_list = junctions_data.get("junctions", [])
    node_lookup: Dict[str, Dict] = {j["id"]: j for j in junctions_list}

    if not resolutions_data:
        logger.info("recompute_adjustments: no resolutions in junctions_data")
        return {}

    logger.info(
        "recompute_adjustments: %d resolutions, %d walls with assemblies",
        len(resolutions_data),
        len(wall_assemblies),
    )

    all_adjustments: Dict[str, List[LayerAdjustment]] = {}

    for res_data in resolutions_data:
        junction_id = res_data["junction_id"]
        join_type = res_data.get("join_type", "butt")
        primary_wall_id = res_data["primary_wall_id"]
        secondary_wall_id = res_data["secondary_wall_id"]

        # Find the junction node
        node_data = node_lookup.get(junction_id)
        if not node_data:
            logger.warning(
                "recompute: junction %s not found in nodes", junction_id
            )
            continue

        junction_type = node_data.get("junction_type", "l_corner")
        connections = node_data.get("connections", [])

        # Find primary and secondary connection dicts
        primary_conn_data = _find_connection(
            connections, primary_wall_id, junction_type, is_primary=True
        )
        secondary_conn_data = _find_connection(
            connections, secondary_wall_id, junction_type, is_primary=False
        )

        if not primary_conn_data or not secondary_conn_data:
            logger.warning(
                "recompute: missing connections for junction %s "
                "(pri=%s, sec=%s)",
                junction_id, primary_wall_id, secondary_wall_id,
            )
            continue

        # Reconstruct minimal WallConnection objects
        primary_conn = _rebuild_connection(
            primary_conn_data, wall_lookup.get(primary_wall_id, {})
        )
        secondary_conn = _rebuild_connection(
            secondary_conn_data, wall_lookup.get(secondary_wall_id, {})
        )

        # Get layer info (now uses assembly data when available)
        pri_layers = wall_layers.get(
            primary_wall_id,
            build_default_wall_layers(primary_wall_id, primary_conn.wall_thickness),
        )
        sec_layers = wall_layers.get(
            secondary_wall_id,
            build_default_wall_layers(secondary_wall_id, secondary_conn.wall_thickness),
        )

        # Get individual assembly layers
        pri_assembly = wall_assemblies.get(primary_wall_id)
        sec_assembly = wall_assemblies.get(secondary_wall_id)

        # Compute adjustments using the existing calculation functions
        if junction_type == "x_crossing":
            # X-crossing: bidirectional midspan gaps (both walls get gaps)
            adjs_a = _calculate_t_intersection_adjustments(
                junction_id, primary_conn, secondary_conn,
                pri_layers, sec_layers,
                continuous_assembly_layers=pri_assembly,
                terminating_assembly_layers=sec_assembly,
                midspan_only=True,
            )
            adjs_b = _calculate_t_intersection_adjustments(
                junction_id, secondary_conn, primary_conn,
                sec_layers, pri_layers,
                continuous_assembly_layers=sec_assembly,
                terminating_assembly_layers=pri_assembly,
                midspan_only=True,
                midspan_cumulative="full",
            )
            adjustments = adjs_a + adjs_b
        elif junction_type == "t_intersection":
            adjustments = _calculate_t_intersection_adjustments(
                junction_id, primary_conn, secondary_conn,
                pri_layers, sec_layers,
                continuous_assembly_layers=pri_assembly,
                terminating_assembly_layers=sec_assembly,
            )
        elif join_type == "butt":
            adjustments = _calculate_butt_adjustments(
                junction_id, primary_conn, secondary_conn,
                pri_layers, sec_layers,
                primary_assembly_layers=pri_assembly,
                secondary_assembly_layers=sec_assembly,
            )
        else:
            # Miter — skip for recompute (amounts are angle-based, not assembly-based)
            continue

        # Accumulate adjustments by wall_id
        for adj in adjustments:
            if adj.wall_id not in all_adjustments:
                all_adjustments[adj.wall_id] = []
            all_adjustments[adj.wall_id].append(adj)

    # Serialize to dict format (matching junctions_json wall_adjustments)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for wall_id, adjs in all_adjustments.items():
        result[wall_id] = [_serialize_adjustment(adj) for adj in adjs]

    logger.info(
        "recompute_adjustments: %d walls, %d total adjustments",
        len(result),
        sum(len(v) for v in result.values()),
    )
    return result


def _find_connection(
    connections: List[Dict],
    wall_id: str,
    junction_type: str,
    is_primary: bool,
) -> Optional[Dict]:
    """Find a connection dict for a wall in the serialized connections list.

    For T-intersections, the primary (continuous) wall may be the
    midspan connection. For L-corners, prefer non-midspan connections.

    Args:
        connections: List of serialized connection dicts.
        wall_id: Wall ID to find.
        junction_type: Junction type string.
        is_primary: Whether looking for the primary wall.

    Returns:
        Connection dict, or None if not found.
    """
    # Collect all matches for this wall_id
    matches = [c for c in connections if c.get("wall_id") == wall_id]
    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]

    # Multiple matches (e.g., T-intersection with midspan + endpoint)
    if junction_type == "t_intersection" and is_primary:
        # Primary in T-intersection is the continuous wall (midspan)
        midspan = [c for c in matches if c.get("is_midspan", False)]
        if midspan:
            return midspan[0]

    # Default: prefer non-midspan
    non_midspan = [c for c in matches if not c.get("is_midspan", False)]
    return non_midspan[0] if non_midspan else matches[0]


def _rebuild_connection(
    conn_data: Dict,
    wall_data: Dict,
) -> WallConnection:
    """Reconstruct a WallConnection from serialized data + wall lookup.

    The serialized connection has wall_id, end, direction, wall_thickness,
    is_midspan, is_exterior, z_axis. Wall length comes from wall_data.

    Args:
        conn_data: Serialized connection dict from junctions_json.
        wall_data: Wall dict from enriched walls_data.

    Returns:
        WallConnection with enough fields for adjustment calculation.
    """
    # Extract z_axis: prefer serialized connection data, then wall_data
    z_axis_data = conn_data.get("z_axis")
    if isinstance(z_axis_data, dict):
        z_axis = (z_axis_data["x"], z_axis_data["y"], z_axis_data["z"])
    elif wall_data:
        z_axis = _extract_z_axis(wall_data)
    else:
        z_axis = (0.0, 0.0, 1.0)

    # Extract direction: prefer serialized connection (always correct),
    # fall back to wall_data base_plane.x_axis.
    direction = (0.0, 0.0, 0.0)
    dir_data = conn_data.get("direction")
    if isinstance(dir_data, dict):
        direction = (dir_data["x"], dir_data["y"], dir_data["z"])
    elif wall_data:
        bp = wall_data.get("base_plane", {})
        x_axis = bp.get("x_axis")
        if isinstance(x_axis, dict):
            direction = (x_axis["x"], x_axis["y"], x_axis["z"])

    return WallConnection(
        wall_id=conn_data["wall_id"],
        end=conn_data["end"],
        direction=direction,
        angle_at_junction=0.0,
        wall_thickness=conn_data.get(
            "wall_thickness",
            wall_data.get("wall_thickness", 0.0),
        ),
        wall_length=wall_data.get("wall_length", 0.0),
        is_exterior=conn_data.get("is_exterior", False),
        is_midspan=conn_data.get("is_midspan", False),
        midspan_u=conn_data.get("midspan_u"),
        z_axis=z_axis,
    )
