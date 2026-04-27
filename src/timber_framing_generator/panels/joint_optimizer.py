# File: src/timber_framing_generator/panels/joint_optimizer.py
"""
Optimal panel joint placement algorithm.

Places panel joints to:
1. Respect maximum panel length constraints
2. Avoid exclusion zones (openings, corners, shear panels)
3. Align with stud locations for structural support
4. Minimize total number of panels

The algorithm uses dynamic programming to find the minimum number of
panels while satisfying all constraints.

Example:
    >>> exclusion_zones = find_exclusion_zones(wall_data, config)
    >>> joints = find_optimal_joints(wall_length, exclusion_zones, config)
    >>> print(f"Optimal joints at: {joints}")
"""

from typing import List, Tuple, Optional
import math

from .panel_config import PanelConfig, PanelizationStrategy, ExclusionZone


def find_exclusion_zones(
    wall_data: dict,
    config: PanelConfig
) -> List[ExclusionZone]:
    """Identify regions where panel joints cannot be placed.

    Creates exclusion zones around:
    - Wall openings (doors, windows) with configured offset
    - Wall corners (start and end) with configured offset
    - Shear panels if structural data is available

    Args:
        wall_data: WallData dictionary with openings
        config: Panel configuration with offset rules

    Returns:
        List of exclusion zones sorted by u_start
    """
    zones = []

    wall_length = wall_data.get("wall_length", wall_data.get("length", 0))

    # Exclusion zones around openings
    for opening in wall_data.get("openings", []):
        u_start = opening.get("u_start", 0)
        u_end = opening.get("u_end", 0)

        # Zone extends from (opening_start - offset) to (opening_end + offset)
        zone_start = max(0, u_start - config.min_joint_to_opening)
        zone_end = min(wall_length, u_end + config.min_joint_to_opening)

        zones.append(ExclusionZone(
            u_start=zone_start,
            u_end=zone_end,
            zone_type="opening",
            element_id=opening.get("id"),
        ))

    # Exclusion zone at wall start (corner)
    if config.min_joint_to_corner > 0:
        zones.append(ExclusionZone(
            u_start=0,
            u_end=min(wall_length, config.min_joint_to_corner),
            zone_type="corner_start",
        ))

    # Exclusion zone at wall end (corner)
    if config.min_joint_to_corner > 0:
        zones.append(ExclusionZone(
            u_start=max(0, wall_length - config.min_joint_to_corner),
            u_end=wall_length,
            zone_type="corner_end",
        ))

    # TODO: Add shear panel exclusion zones from structural data
    # This would require additional structural information in wall_data

    # Sort by u_start
    zones.sort(key=lambda z: z.u_start)

    # Merge overlapping zones
    return _merge_overlapping_zones(zones)


def _merge_overlapping_zones(zones: List[ExclusionZone]) -> List[ExclusionZone]:
    """Merge overlapping or adjacent exclusion zones.

    Args:
        zones: List of ExclusionZone objects sorted by u_start

    Returns:
        Merged list with no overlaps
    """
    if not zones:
        return []

    merged = [ExclusionZone(
        u_start=zones[0].u_start,
        u_end=zones[0].u_end,
        zone_type=zones[0].zone_type,
        element_id=zones[0].element_id,
    )]

    for zone in zones[1:]:
        last = merged[-1]

        # Check for overlap (including adjacent zones)
        if zone.u_start <= last.u_end + 0.001:  # Small tolerance for floating point
            # Merge: extend last zone
            merged[-1] = ExclusionZone(
                u_start=last.u_start,
                u_end=max(last.u_end, zone.u_end),
                zone_type="merged",  # Mark as merged
                element_id=None,
            )
        else:
            merged.append(ExclusionZone(
                u_start=zone.u_start,
                u_end=zone.u_end,
                zone_type=zone.zone_type,
                element_id=zone.element_id,
            ))

    return merged


def _in_exclusion_zone(u: float, zones: List[ExclusionZone]) -> bool:
    """Check if a U coordinate is in any exclusion zone.

    Args:
        u: U coordinate to check (feet)
        zones: List of exclusion zones

    Returns:
        True if u is within any exclusion zone
    """
    for zone in zones:
        if zone.u_start <= u <= zone.u_end:
            return True
    return False


def _generate_stud_aligned_candidates(
    wall_length: float,
    stud_spacing: float,
    min_offset: float = 0.0
) -> List[float]:
    """Generate candidate joint positions aligned with studs.

    Joints should occur at stud locations for structural support.
    This generates positions at each stud along the wall.

    Args:
        wall_length: Total wall length (feet)
        stud_spacing: Stud spacing (feet), typically 1.333 for 16" OC
        min_offset: Minimum distance from wall start for first candidate

    Returns:
        List of candidate U coordinates
    """
    candidates = []
    pos = stud_spacing

    while pos < wall_length:
        if pos >= min_offset:
            candidates.append(pos)
        pos += stud_spacing

    return candidates


def _snap_to_nearest_stud(
    u: float,
    stud_spacing: float
) -> float:
    """Snap a U coordinate to the nearest stud location.

    Args:
        u: U coordinate to snap (feet)
        stud_spacing: Stud spacing (feet)

    Returns:
        Snapped U coordinate
    """
    return round(u / stud_spacing) * stud_spacing


def find_optimal_joints(
    wall_length: float,
    exclusion_zones: List[ExclusionZone],
    config: PanelConfig
) -> List[float]:
    """Find optimal joint locations using dynamic programming.

    Algorithm:
    1. Generate candidate joint positions at stud locations
    2. Filter out candidates in exclusion zones
    3. Use DP to find minimum panels while respecting max length

    The DP approach ensures we find the globally optimal solution
    (minimum number of panels) rather than a greedy local optimum.

    Args:
        wall_length: Total wall length in feet
        exclusion_zones: Regions where joints not allowed
        config: Panel configuration

    Returns:
        List of joint U-coordinates (not including 0 and wall_length)
    """
    # Handle walls shorter than max panel length
    if wall_length <= config.max_panel_length:
        return []  # No joints needed - single panel

    # Generate candidate positions at stud locations
    if config.snap_to_studs:
        candidates = _generate_stud_aligned_candidates(
            wall_length,
            config.stud_spacing,
        )
    else:
        # Generate candidates at regular intervals
        num_candidates = int(wall_length / config.stud_spacing) + 1
        candidates = [
            i * config.stud_spacing
            for i in range(1, num_candidates)
            if i * config.stud_spacing < wall_length
        ]

    # Filter out candidates in exclusion zones
    valid_candidates = [
        c for c in candidates
        if not _in_exclusion_zone(c, exclusion_zones)
    ]

    # Add wall boundaries (required for DP)
    all_positions = [0.0] + valid_candidates + [wall_length]
    all_positions = sorted(set(all_positions))

    n = len(all_positions)

    # Edge case: no valid candidates
    if n <= 2:
        # Check if wall can be single panel
        if wall_length <= config.max_panel_length:
            return []
        else:
            # Need to place joints even in exclusion zones (warning case)
            # Fall back to regular intervals
            num_panels = math.ceil(wall_length / config.max_panel_length)
            panel_length = wall_length / num_panels
            return [
                panel_length * i
                for i in range(1, num_panels)
            ]

    # DP: Find minimum number of panels
    # dp[i] = minimum panels to cover positions 0 to i
    # parent[i] = previous position for backtracking
    INF = float('inf')
    dp = [INF] * n
    parent = [-1] * n
    dp[0] = 0  # Starting point

    for i in range(1, n):
        for j in range(i):
            panel_length = all_positions[i] - all_positions[j]

            # Check panel length constraints
            if panel_length > config.max_panel_length:
                continue  # Panel too long

            # Allow short final panel, but not short interior panels
            if panel_length < config.min_panel_length:
                if i < n - 1:  # Not the last position
                    continue  # Panel too short

            # Check if this gives better solution
            if dp[j] + 1 < dp[i]:
                dp[i] = dp[j] + 1
                parent[i] = j

    # Check if solution exists
    if dp[n-1] == INF:
        # No valid solution found - try without length constraints
        # This shouldn't happen with proper candidates, but handle gracefully
        return _find_joints_greedy(wall_length, exclusion_zones, config)

    # Backtrack to find joint positions
    joints = []
    current = n - 1
    while parent[current] != -1:
        prev = parent[current]
        if prev != 0:  # Don't include start position as a joint
            joints.append(all_positions[prev])
        current = prev

    return sorted(joints)


def _find_joints_greedy(
    wall_length: float,
    exclusion_zones: List[ExclusionZone],
    config: PanelConfig
) -> List[float]:
    """Greedy fallback for finding joints when DP fails.

    Uses a simple greedy approach: place joints at maximum intervals
    while avoiding exclusion zones.

    Args:
        wall_length: Total wall length (feet)
        exclusion_zones: Exclusion zones to avoid
        config: Panel configuration

    Returns:
        List of joint positions
    """
    joints = []
    current_pos = 0.0

    while current_pos + config.max_panel_length < wall_length:
        # Target position for next joint
        target = current_pos + config.max_panel_length

        # Snap to stud
        if config.snap_to_studs:
            target = _snap_to_nearest_stud(target, config.stud_spacing)

        # Check if in exclusion zone
        if _in_exclusion_zone(target, exclusion_zones):
            # Find nearest valid position
            target = _find_nearest_valid_position(
                target, exclusion_zones, config.stud_spacing
            )

        # Ensure we're making progress
        if target <= current_pos:
            # Can't make progress - force placement
            target = current_pos + config.max_panel_length

        if target < wall_length:
            joints.append(target)
            current_pos = target
        else:
            break

    return joints


def _find_nearest_valid_position(
    target: float,
    zones: List[ExclusionZone],
    stud_spacing: float
) -> float:
    """Find nearest valid joint position outside exclusion zones.

    Searches both directions from target to find the closest
    valid stud-aligned position.

    Args:
        target: Target U coordinate
        zones: Exclusion zones to avoid
        stud_spacing: Stud spacing for alignment

    Returns:
        Nearest valid position
    """
    # Check target first
    if not _in_exclusion_zone(target, zones):
        return target

    # Search in both directions
    for offset in range(1, 20):  # Search up to 20 studs away
        # Try before target
        pos_before = target - offset * stud_spacing
        if pos_before > 0 and not _in_exclusion_zone(pos_before, zones):
            return pos_before

        # Try after target
        pos_after = target + offset * stud_spacing
        if not _in_exclusion_zone(pos_after, zones):
            return pos_after

    # Couldn't find valid position - return target anyway
    return target


def validate_joints(
    joints: List[float],
    wall_length: float,
    config: PanelConfig
) -> Tuple[bool, List[str]]:
    """Validate joint positions against configuration.

    Args:
        joints: List of joint U coordinates
        wall_length: Total wall length
        config: Panel configuration

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    # Check panel lengths
    boundaries = [0.0] + sorted(joints) + [wall_length]

    for i in range(len(boundaries) - 1):
        panel_length = boundaries[i + 1] - boundaries[i]

        if panel_length > config.max_panel_length:
            errors.append(
                f"Panel {i} length {panel_length:.2f} exceeds max "
                f"{config.max_panel_length:.2f}"
            )

        # Allow short final panel
        if panel_length < config.min_panel_length and i < len(boundaries) - 2:
            errors.append(
                f"Panel {i} length {panel_length:.2f} below min "
                f"{config.min_panel_length:.2f}"
            )

    return len(errors) == 0, errors


def get_panel_boundaries(
    joints: List[float],
    wall_length: float
) -> List[Tuple[float, float]]:
    """Get panel boundaries from joint positions.

    Args:
        joints: List of joint U coordinates
        wall_length: Total wall length

    Returns:
        List of (u_start, u_end) tuples for each panel
    """
    boundaries = [0.0] + sorted(joints) + [wall_length]
    return [
        (boundaries[i], boundaries[i + 1])
        for i in range(len(boundaries) - 1)
    ]


# =============================================================================
# Strategy Dispatcher
# =============================================================================


def find_joints_for_strategy(
    wall_data: dict,
    config: PanelConfig,
) -> List[float]:
    """Dispatch to strategy-specific joint finder.

    This is the main entry point for finding joint positions. It selects
    the appropriate algorithm based on ``config.strategy`` and returns
    joint U-coordinates (not including 0 and wall_length).

    Args:
        wall_data: WallData dictionary with openings, wall_length, etc.
        config: Panel configuration including strategy selection

    Returns:
        List of joint U-coordinates
    """
    wall_length = wall_data.get("wall_length", wall_data.get("length", 0))

    if config.strategy == PanelizationStrategy.OPENING_BOUNDED:
        return _find_joints_opening_bounded(wall_data, config)
    elif config.strategy == PanelizationStrategy.NO_SPLIT_THROUGH:
        return _find_joints_no_split_through(wall_data, config)
    elif config.strategy == PanelizationStrategy.EQUAL_LENGTH:
        return _find_joints_equal_length(wall_data, config)
    else:
        # LENGTH_OPTIMIZED (default) - existing behavior
        exclusion_zones = find_exclusion_zones(wall_data, config)
        return find_optimal_joints(wall_length, exclusion_zones, config)


# =============================================================================
# Opening-Bounded Strategy
# =============================================================================


def _find_joints_opening_bounded(
    wall_data: dict,
    config: PanelConfig,
) -> List[float]:
    """Find joints by forcing splits at opening king-stud edges.

    Each opening becomes its own panel. Mandatory joints are placed at
    the outer edge of the king stud (or trimmer) flanking each opening.
    Sub-segments between mandatory joints are further split via DP if
    they exceed max_panel_length.

    Args:
        wall_data: WallData dictionary
        config: Panel configuration

    Returns:
        List of joint U-coordinates
    """
    wall_length = wall_data.get("wall_length", wall_data.get("length", 0))
    openings = wall_data.get("openings", [])

    if not openings:
        # No openings: fall back to length-optimized
        exclusion_zones = find_exclusion_zones(wall_data, config)
        return find_optimal_joints(wall_length, exclusion_zones, config)

    # Compute mandatory joint positions at opening edges
    stud_w = config.stud_width  # 0.125 ft = 1.5" (one stud width)

    mandatory_joints = set()
    for opening in openings:
        u_start = opening.get("u_start", 0)
        u_end = opening.get("u_end", 0)

        if config.opening_edge_stud == "king_and_trimmer":
            # Joint at outer edge of king stud
            # King stud is outside trimmer, trimmer is flush with opening edge
            left_joint = u_start - stud_w - stud_w   # king outer edge
            right_joint = u_end + stud_w + stud_w     # king outer edge
        else:  # trimmer_only
            # Joint at outer edge of trimmer (flush with opening)
            left_joint = u_start - stud_w
            right_joint = u_end + stud_w

        # Snap to nearest stud if configured
        if config.snap_to_studs:
            left_joint = _snap_to_nearest_stud(left_joint, config.stud_spacing)
            right_joint = _snap_to_nearest_stud(right_joint, config.stud_spacing)

        # Clamp to wall bounds (exclude 0 and wall_length since those are boundaries)
        if left_joint > 0 and left_joint < wall_length:
            mandatory_joints.add(left_joint)
        if right_joint > 0 and right_joint < wall_length:
            mandatory_joints.add(right_joint)

    # Sort and build segment boundaries
    sorted_joints = sorted(mandatory_joints)
    segment_boundaries = [0.0] + sorted_joints + [wall_length]

    # For each sub-segment, check if it needs further splitting
    all_joints = list(sorted_joints)

    for i in range(len(segment_boundaries) - 1):
        seg_start = segment_boundaries[i]
        seg_end = segment_boundaries[i + 1]
        seg_length = seg_end - seg_start

        if seg_length > config.max_panel_length:
            # Build a mini wall_data for this sub-segment (no openings
            # since openings are already bounded by mandatory joints)
            sub_wall = {
                "wall_length": seg_length,
                "openings": [],
            }
            sub_zones = find_exclusion_zones(sub_wall, config)
            sub_joints = find_optimal_joints(seg_length, sub_zones, config)

            # Shift sub-joints back to wall-absolute coords
            for sj in sub_joints:
                absolute_joint = seg_start + sj
                if absolute_joint > 0 and absolute_joint < wall_length:
                    all_joints.append(absolute_joint)

    # Deduplicate and sort
    all_joints = sorted(set(all_joints))
    return all_joints


# =============================================================================
# No-Split-Through Strategy
# =============================================================================


def _find_joints_no_split_through(
    wall_data: dict,
    config: PanelConfig,
) -> List[float]:
    """Find joints preventing any split within opening horizontal ranges.

    Like LENGTH_OPTIMIZED but with wider exclusion zones that span the
    full U-range of each opening (plus the standard offset). This prevents
    L-shaped panels without forcing openings into their own panels.

    Args:
        wall_data: WallData dictionary
        config: Panel configuration

    Returns:
        List of joint U-coordinates
    """
    wall_length = wall_data.get("wall_length", wall_data.get("length", 0))
    openings = wall_data.get("openings", [])

    zones = []

    # Create wide exclusion zones spanning full opening U-range + offset
    for opening in openings:
        u_start = opening.get("u_start", 0)
        u_end = opening.get("u_end", 0)

        # Zone spans the full opening range plus offset on each side
        zone_start = max(0, u_start - config.min_joint_to_opening)
        zone_end = min(wall_length, u_end + config.min_joint_to_opening)

        zones.append(ExclusionZone(
            u_start=zone_start,
            u_end=zone_end,
            zone_type="opening_full_span",
            element_id=opening.get("id"),
        ))

    # Corner exclusion zones (same as standard)
    if config.min_joint_to_corner > 0:
        zones.append(ExclusionZone(
            u_start=0,
            u_end=min(wall_length, config.min_joint_to_corner),
            zone_type="corner_start",
        ))
        zones.append(ExclusionZone(
            u_start=max(0, wall_length - config.min_joint_to_corner),
            u_end=wall_length,
            zone_type="corner_end",
        ))

    # Sort and merge
    zones.sort(key=lambda z: z.u_start)
    merged_zones = _merge_overlapping_zones(zones)

    return find_optimal_joints(wall_length, merged_zones, config)


# =============================================================================
# Equal-Length Strategy
# =============================================================================


def _find_joints_equal_length(
    wall_data: dict,
    config: PanelConfig,
) -> List[float]:
    """Find joints by dividing wall into equal-length panels.

    Simple strategy: compute N = ceil(wall_length / max_panel_length),
    then place N-1 evenly spaced joints. Optionally snap to studs.
    No opening awareness.

    Args:
        wall_data: WallData dictionary
        config: Panel configuration

    Returns:
        List of joint U-coordinates
    """
    wall_length = wall_data.get("wall_length", wall_data.get("length", 0))

    if wall_length <= config.max_panel_length:
        return []  # Single panel, no joints needed

    num_panels = math.ceil(wall_length / config.max_panel_length)
    panel_length = wall_length / num_panels

    joints = []
    for i in range(1, num_panels):
        joint_pos = panel_length * i

        if config.snap_to_studs:
            joint_pos = _snap_to_nearest_stud(joint_pos, config.stud_spacing)

        # Avoid placing joints at wall boundaries
        if joint_pos > 0 and joint_pos < wall_length:
            joints.append(joint_pos)

    return sorted(set(joints))
