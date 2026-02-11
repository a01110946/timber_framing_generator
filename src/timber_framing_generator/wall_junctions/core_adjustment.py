# File: src/timber_framing_generator/wall_junctions/core_adjustment.py
"""Core layer junction adjustments for framing.

Computes per-wall ``framing_segments`` from junction core adjustments so
that downstream components (Cell Decomposer, Panel Decomposer, Framing
Generator, MEP Router) operate on correct adjusted framing boundaries.

``framing_segments`` is a list of ``[u_start, u_end]`` pairs defining the
effective framing runs for a wall, expressed in the wall's original U
coordinate system.

- **L-corner**: primary EXTENDS at one end, secondary TRIMS → single
  segment with shifted boundary.
- **T-intersection**: terminating wall TRIMS at its endpoint → single
  segment with shortened boundary.  Continuous wall is unaffected.
- **X-crossing**: secondary wall SPLITS at crossing point → multiple
  segments.  Primary wall runs through unaffected.

Usage:
    from src.timber_framing_generator.wall_junctions.core_adjustment import (
        compute_framing_segments,
    )

    enriched_walls = compute_framing_segments(junctions_data, walls_data)
    # Each wall dict now has a "framing_segments" key.
"""

from typing import Any, Dict, List, Tuple


def compute_framing_segments(
    junctions_data: Dict[str, Any],
    walls_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Enrich walls with ``framing_segments`` derived from core adjustments.

    Reads core ``LayerAdjustment`` records from *junctions_data* and computes
    the effective framing segment boundaries for each wall.

    - Endpoint adjustments (``end="start"``/``"end"``) shift segment edges.
    - Midspan adjustments (``end="midspan"``) split into multiple segments.
    - Continuous walls at T-intersections are unaffected (their midspan core
      adjustment is sheathing-only).
    - Primary walls at X-crossings are unaffected (they run through).

    Args:
        junctions_data: Parsed ``junctions_json`` dict containing at least
            ``wall_adjustments`` — a mapping of *wall_id* to a list of
            serialized ``LayerAdjustment`` dicts.
        walls_data: List of wall dicts.  **Not mutated.**

    Returns:
        New list of wall dicts — shallow copies of the originals — each
        with a ``framing_segments`` key added.  All other fields are
        preserved unchanged.

    Examples:
        >>> walls = [{"wall_id": "w1", "wall_length": 10.0}]
        >>> juncs = {"wall_adjustments": {}}
        >>> result = compute_framing_segments(juncs, walls)
        >>> result[0]["framing_segments"]
        [[0.0, 10.0]]
    """
    wall_adjustments = junctions_data.get("wall_adjustments", {})
    enriched: List[Dict[str, Any]] = []

    for wall in walls_data:
        wall_id = wall.get("wall_id", "")
        wall_length = float(wall.get("wall_length", 0.0))
        new_wall = dict(wall)  # Shallow copy — don't mutate original

        adjs = wall_adjustments.get(wall_id, [])
        core_adjs = [a for a in adjs if a.get("layer_name") == "core"]

        # ── Step 1: Compute endpoint shifts ──────────────────────────
        u_start, u_end = _compute_endpoint_shifts(core_adjs, wall_length)

        # ── Step 2: Collect midspan splits (X-crossings) ─────────────
        midspan_gaps = _collect_midspan_gaps(core_adjs)

        # ── Step 3: Build segments ───────────────────────────────────
        segments = _build_segments(u_start, u_end, midspan_gaps)

        new_wall["framing_segments"] = segments
        enriched.append(new_wall)

    return enriched


# =====================================================================
# Private helpers
# =====================================================================


def _compute_endpoint_shifts(
    core_adjs: List[Dict[str, Any]],
    wall_length: float,
) -> Tuple[float, float]:
    """Compute effective U-start and U-end from endpoint core adjustments.

    Only considers adjustments with ``end`` in ``("start", "end")``.
    A wall can have adjustments at both ends (e.g., primary at one end,
    secondary at the other).  When multiple adjustments target the same
    end, the most restrictive (largest trim / largest extend) wins.

    Args:
        core_adjs: List of core ``LayerAdjustment`` dicts.
        wall_length: Original wall length in feet.

    Returns:
        ``(effective_u_start, effective_u_end)`` in feet.
    """
    u_start = 0.0
    u_end = wall_length

    for adj in core_adjs:
        end = adj.get("end")
        adj_type = adj.get("adjustment_type", "")
        amount = float(adj.get("amount", 0.0))

        if end == "start":
            if adj_type == "trim":
                u_start = max(u_start, amount)
            elif adj_type == "extend":
                u_start = min(u_start, -amount)
        elif end == "end":
            if adj_type == "trim":
                u_end = min(u_end, wall_length - amount)
            elif adj_type == "extend":
                u_end = max(u_end, wall_length + amount)

    return u_start, u_end


def _collect_midspan_gaps(
    core_adjs: List[Dict[str, Any]],
) -> List[Tuple[float, float]]:
    """Collect midspan gap intervals from X-crossing adjustments.

    Each midspan core TRIM with a ``midspan_u`` value produces a gap
    ``(midspan_u - amount, midspan_u + amount)``.

    Args:
        core_adjs: List of core ``LayerAdjustment`` dicts.

    Returns:
        Sorted list of ``(gap_start, gap_end)`` tuples.
    """
    gaps: List[Tuple[float, float]] = []

    for adj in core_adjs:
        if adj.get("end") != "midspan":
            continue
        mid_u = adj.get("midspan_u")
        amount = float(adj.get("amount", 0.0))
        if mid_u is not None and amount > 0:
            gaps.append((float(mid_u) - amount, float(mid_u) + amount))

    gaps.sort(key=lambda g: g[0])
    return gaps


def _build_segments(
    u_start: float,
    u_end: float,
    midspan_gaps: List[Tuple[float, float]],
) -> List[List[float]]:
    """Build framing segment list from endpoint bounds and midspan gaps.

    Without gaps, returns a single segment ``[[u_start, u_end]]``.
    With gaps, splits into multiple segments around each gap.

    Args:
        u_start: Effective start U (may be < 0 for EXTEND).
        u_end: Effective end U (may be > wall_length for EXTEND).
        midspan_gaps: Sorted list of ``(gap_start, gap_end)`` from
            :func:`_collect_midspan_gaps`.

    Returns:
        List of ``[seg_start, seg_end]`` pairs.
    """
    if not midspan_gaps:
        return [[u_start, u_end]]

    segments: List[List[float]] = []
    seg_start = u_start

    for gap_start, gap_end in midspan_gaps:
        if gap_start > seg_start:
            segments.append([seg_start, gap_start])
        seg_start = gap_end

    if seg_start < u_end:
        segments.append([seg_start, u_end])

    return segments
