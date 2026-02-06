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
from typing import List, Dict, Tuple, Optional

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
    LayerSide,
    WallAssemblyDef,
    WallLayer,
)
from .junction_detector import _outward_direction_at_junction, _calculate_angle

logger = logging.getLogger(__name__)


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
        else:
            result[wall_id] = build_default_wall_layers(wall_id, thickness)

    return result


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


def _calculate_butt_adjustments(
    junction_id: str,
    primary: WallConnection,
    secondary: WallConnection,
    primary_layers: WallLayerInfo,
    secondary_layers: WallLayerInfo,
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments for a butt join.

    Uses the CROSSED PATTERN at L-corners:
      - Exterior layers follow the primary wall (extend on outside corner)
      - Interior layers follow the secondary wall (extend on inside corner)
      - Core layers follow wall role (primary extends, secondary trims)

    Primary wall:
      - core:     EXTEND by secondary.core_thickness / 2
      - exterior: EXTEND by secondary.total_thickness / 2 (wraps outside corner)
      - interior: TRIM by secondary.core_thickness / 2 (secondary's interior covers this)

    Secondary wall:
      - core:     TRIM by primary.core_thickness / 2
      - exterior: TRIM by primary.core_thickness / 2 (butts against primary's exterior)
      - interior: EXTEND by primary.total_thickness / 2 (wraps inside corner)
    """
    adjustments = []

    half_sec_core = secondary_layers.core_thickness / 2.0
    half_sec_total = secondary_layers.total_thickness / 2.0
    half_pri_core = primary_layers.core_thickness / 2.0
    half_pri_total = primary_layers.total_thickness / 2.0

    # PRIMARY: exterior extends, core extends, interior TRIMS
    for layer_name, adj_type, amount in [
        ("core", AdjustmentType.EXTEND, half_sec_core),
        ("exterior", AdjustmentType.EXTEND, half_sec_total),
        ("interior", AdjustmentType.TRIM, half_sec_core),
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # SECONDARY: exterior trims, core trims, interior EXTENDS
    for layer_name, adj_type, amount in [
        ("core", AdjustmentType.TRIM, half_pri_core),
        ("exterior", AdjustmentType.TRIM, half_pri_core),
        ("interior", AdjustmentType.EXTEND, half_pri_total),
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=primary.wall_id,
        ))

    return adjustments


def _calculate_butt_adjustments_v2(
    junction_id: str,
    primary: WallConnection,
    secondary: WallConnection,
    primary_assembly: WallAssemblyDef,
    secondary_assembly: WallAssemblyDef,
) -> List[LayerAdjustment]:
    """Calculate per-layer adjustments for a butt join using multi-layer assemblies.

    Applies the crossed pattern to each individual layer based on its side:
      - EXTERIOR-side layers follow the primary wall (extend on outside corner)
      - INTERIOR-side layers follow the secondary wall (extend on inside corner)
      - CORE layers follow wall role (primary extends, secondary trims)

    Also emits legacy 3-name adjustments for backward compatibility.

    Args:
        junction_id: Junction identifier.
        primary: Primary wall connection (extends at outside corner).
        secondary: Secondary wall connection (trims at outside corner).
        primary_assembly: Full assembly definition for primary wall.
        secondary_assembly: Full assembly definition for secondary wall.

    Returns:
        List of LayerAdjustments for all layers of both walls.
    """
    adjustments = []

    half_sec_core = secondary_assembly.core_thickness / 2.0
    half_sec_total = secondary_assembly.total_thickness / 2.0
    half_pri_core = primary_assembly.core_thickness / 2.0
    half_pri_total = primary_assembly.total_thickness / 2.0

    # --- PRIMARY WALL: per-layer ---
    for layer in primary_assembly.layers:
        if layer.side == LayerSide.CORE:
            adj_type = AdjustmentType.EXTEND
            amount = half_sec_core
        elif layer.side == LayerSide.EXTERIOR:
            adj_type = AdjustmentType.EXTEND
            amount = half_sec_total
        else:  # INTERIOR
            adj_type = AdjustmentType.TRIM
            amount = half_sec_core

        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer.name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # --- SECONDARY WALL: per-layer ---
    for layer in secondary_assembly.layers:
        if layer.side == LayerSide.CORE:
            adj_type = AdjustmentType.TRIM
            amount = half_pri_core
        elif layer.side == LayerSide.EXTERIOR:
            adj_type = AdjustmentType.TRIM
            amount = half_pri_core
        else:  # INTERIOR
            adj_type = AdjustmentType.EXTEND
            amount = half_pri_total

        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer.name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=primary.wall_id,
        ))

    # --- LEGACY 3-name adjustments for backward compatibility ---
    # Primary: exterior extends, core extends, interior trims
    for layer_name, adj_type, amount in [
        ("core", AdjustmentType.EXTEND, half_sec_core),
        ("exterior", AdjustmentType.EXTEND, half_sec_total),
        ("interior", AdjustmentType.TRIM, half_sec_core),
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=primary.wall_id,
            end=primary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
            connecting_wall_id=secondary.wall_id,
        ))

    # Secondary: exterior trims, core trims, interior extends
    for layer_name, adj_type, amount in [
        ("core", AdjustmentType.TRIM, half_pri_core),
        ("exterior", AdjustmentType.TRIM, half_pri_core),
        ("interior", AdjustmentType.EXTEND, half_pri_total),
    ]:
        adjustments.append(LayerAdjustment(
            wall_id=secondary.wall_id,
            end=secondary.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=adj_type,
            amount=amount,
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
) -> List[LayerAdjustment]:
    """Calculate adjustments for a T-intersection.

    The continuous wall is NOT adjusted (it passes through).
    The terminating wall trims at its end meeting the continuous wall.

    Terminating wall trims:
      - core:     by continuous.core_thickness / 2
      - exterior: by continuous.core_thickness / 2
      - interior: by continuous.core_thickness / 2
    """
    adjustments = []

    half_cont_core = continuous_layers.core_thickness / 2.0

    for layer_name in ("core", "exterior", "interior"):
        adjustments.append(LayerAdjustment(
            wall_id=terminating.wall_id,
            end=terminating.end,
            junction_id=junction_id,
            layer_name=layer_name,
            adjustment_type=AdjustmentType.TRIM,
            amount=half_cont_core,
            connecting_wall_id=continuous.wall_id,
        ))

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

        adjustments = _calculate_t_intersection_adjustments(
            node.id, continuous, terminating, cont_layers, term_layers
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

    # Calculate per-layer adjustments
    if join_type == JoinType.BUTT:
        adjustments = _calculate_butt_adjustments(
            node.id, primary, secondary, pri_layers, sec_layers
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

    return JunctionResolution(
        junction_id=node.id,
        join_type=join_type,
        primary_wall_id=primary.wall_id,
        secondary_wall_id=secondary.wall_id,
        confidence=confidence,
        reason=reason,
        layer_adjustments=adjustments,
        is_user_override=is_override,
    )


def _resolve_multi_wall_junction(
    node: JunctionNode,
    wall_layers: Dict[str, WallLayerInfo],
    default_join_type: str,
    priority_strategy: str,
    override: Optional[Dict],
) -> List[JunctionResolution]:
    """Resolve a junction with 3+ walls by processing pairwise.

    For X-crossings: identify the two inline pairs and resolve each
    pair independently.

    For multi-way: resolve the dominant pair first, then remaining.
    """
    resolutions = []
    connections = node.connections

    if node.junction_type == JunctionType.X_CROSSING and len(connections) == 4:
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
                temp_node, wall_layers, default_join_type, priority_strategy, override
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
                temp_node, wall_layers, default_join_type, priority_strategy, override
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
                node, wall_layers, default_join_type, priority_strategy, override
            )
            resolutions.append(resolution)

        elif node.junction_type in (
            JunctionType.X_CROSSING,
            JunctionType.MULTI_WAY,
        ):
            multi_res = _resolve_multi_wall_junction(
                node, wall_layers, default_join_type, priority_strategy, override
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

    # Phase 3+4: Resolve junctions and calculate adjustments
    resolutions = resolve_all_junctions(
        nodes,
        wall_layers,
        default_join_type=default_join_type,
        priority_strategy=priority_strategy,
        user_overrides=user_overrides,
    )

    # Build per-wall adjustment lookup
    wall_adjustments = build_wall_adjustments_map(resolutions)

    return JunctionGraph(
        nodes=nodes,
        wall_layers=wall_layers,
        resolutions=resolutions,
        wall_adjustments=wall_adjustments,
    )
