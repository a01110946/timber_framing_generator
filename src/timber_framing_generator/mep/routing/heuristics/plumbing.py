# File: src/timber_framing_generator/mep/routing/heuristics/plumbing.py
"""
Plumbing-specific target heuristics.

Provides heuristics for sanitary (drain), vent, and supply systems.
"""

from typing import List, Optional

from .base import TargetHeuristic, ConnectorInfo
from ..targets import RoutingTarget, TargetCandidate, TargetType
from ..domains import RoutingDomain


class SanitaryHeuristic(TargetHeuristic):
    """
    Heuristic for sanitary (drain) systems.

    Priorities:
    1. Wet wall with drain stack (adjacent or back-to-back)
    2. Shaft with drain stack
    3. Floor penetration to below

    Considers: gravity flow (must slope down), pipe slope requirements,
    stack location constraints.

    Special rules:
    - Cannot route upward (gravity drain)
    - Prefers short horizontal runs (less slope required)
    - Toilet drains need 3" minimum stack
    """

    # Sanitary-specific weights
    wet_wall_bonus: float = -10.0  # Bonus for wet wall targets
    shaft_bonus: float = -5.0  # Bonus for shaft targets
    toilet_size_threshold: float = 0.25  # 3" minimum for toilets

    @property
    def system_types(self) -> List[str]:
        return ["Sanitary"]

    @property
    def preferred_target_types(self) -> List[TargetType]:
        return [
            TargetType.WET_WALL,
            TargetType.SHAFT,
            TargetType.FLOOR_PENETRATION
        ]

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """Score targets for sanitary routing with gravity considerations."""
        base_score = super().score_target(connector, target, domain)

        # Sanitary routes must go DOWN (gravity)
        if target.location[2] > connector.location[2]:
            return float('inf')  # Can't route upward

        # Bonus for wet walls (drain stacks already present)
        if target.target_type == TargetType.WET_WALL:
            base_score += self.wet_wall_bonus

        # Bonus for shafts
        if target.target_type == TargetType.SHAFT:
            base_score += self.shaft_bonus

        # Penalty for long horizontal runs (require more slope)
        horizontal_distance = (
            abs(connector.location[0] - target.location[0]) +
            abs(connector.location[1] - target.location[1])
        )
        # Minimum slope is 1/8" per foot = 0.0104 ft/ft
        # Long horizontal runs are harder to maintain slope
        slope_penalty = horizontal_distance * 0.5
        base_score += slope_penalty

        # Check toilet-specific constraints
        if connector.fixture_type and "toilet" in connector.fixture_type.lower():
            if target.capacity < self.toilet_size_threshold:
                return float('inf')  # 3" minimum for toilets

        return base_score

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find drain targets respecting gravity constraints."""
        # Filter to sanitary-compatible targets
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_target_type(valid_targets, self.preferred_target_types)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Filter targets that are at or below connector elevation
        # (can't route upward for gravity drain)
        valid_targets = [
            t for t in valid_targets
            if t.location[2] <= connector.location[2]
        ]

        # Score and rank
        candidates = []
        for target in valid_targets:
            score = self.score_target(connector, target)
            if score < float('inf'):
                candidate = self._create_candidate(
                    connector, target,
                    notes=f"Sanitary: {target.target_type.value}, elevation drop: "
                          f"{connector.location[2] - target.location[2]:.2f} ft"
                )
                candidates.append(candidate)

        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]


class VentHeuristic(TargetHeuristic):
    """
    Heuristic for vent systems.

    Priorities:
    1. Combine with existing sanitary route to wet wall (wet vent)
    2. Dedicated vent stack in wet wall
    3. Ceiling penetration to roof vent

    Vent pipes route UPWARD to atmosphere, unlike drains.
    Can be combined with drain stack as "wet vent" for efficiency.
    """

    wet_wall_bonus: float = -8.0
    ceiling_penalty: float = 5.0  # Prefer wall routes

    @property
    def system_types(self) -> List[str]:
        return ["Vent"]

    @property
    def preferred_target_types(self) -> List[TargetType]:
        return [
            TargetType.WET_WALL,
            TargetType.SHAFT,
            TargetType.CEILING_PENETRATION
        ]

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """Score targets for vent routing."""
        base_score = super().score_target(connector, target, domain)

        # Vent routes go UP - penalize targets below connector
        if target.location[2] < connector.location[2]:
            # Small penalty for going down first (J-trap loops)
            base_score += 5.0

        # Bonus for wet walls (can combine with drain stack)
        if target.target_type == TargetType.WET_WALL:
            base_score += self.wet_wall_bonus

        # Penalty for ceiling penetrations (more complex routing)
        if target.target_type == TargetType.CEILING_PENETRATION:
            base_score += self.ceiling_penalty

        return base_score

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find vent targets preferring wet walls."""
        # Filter to vent-compatible targets
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_target_type(valid_targets, self.preferred_target_types)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Score and rank
        candidates = []
        for target in valid_targets:
            score = self.score_target(connector, target)
            candidate = self._create_candidate(
                connector, target,
                notes=f"Vent: {target.target_type.value}"
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]


class SupplyHeuristic(TargetHeuristic):
    """
    Heuristic for DHW (Domestic Hot Water) and DCW (Domestic Cold Water) systems.

    These are pressure systems, so routing is more flexible than gravity drains.

    Priorities:
    1. Supply riser in wet wall
    2. Ceiling distribution with drop-down
    3. Floor penetration with rise

    Considerations:
    - Hot water should minimize run length (heat loss)
    - Cold water can have longer runs
    - Parallel hot/cold routing preferred
    """

    wet_wall_bonus: float = -5.0
    hot_water_length_penalty: float = 0.3  # Extra penalty for DHW

    @property
    def system_types(self) -> List[str]:
        return ["DomesticHotWater", "DomesticColdWater", "DHW", "DCW"]

    @property
    def preferred_target_types(self) -> List[TargetType]:
        return [
            TargetType.WET_WALL,
            TargetType.CEILING_PENETRATION,
            TargetType.FLOOR_PENETRATION,
            TargetType.SHAFT
        ]

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """Score targets for supply routing."""
        base_score = super().score_target(connector, target, domain)

        # Bonus for wet walls (risers present)
        if target.target_type == TargetType.WET_WALL:
            base_score += self.wet_wall_bonus

        # Extra distance penalty for hot water (heat loss)
        if connector.system_type in ["DomesticHotWater", "DHW"]:
            distance = self._manhattan_distance_3d(connector.location, target.location)
            base_score += self.hot_water_length_penalty * distance

        return base_score

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find supply targets with flexible routing."""
        # Filter to supply-compatible targets
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_target_type(valid_targets, self.preferred_target_types)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Score and rank
        candidates = []
        for target in valid_targets:
            score = self.score_target(connector, target)
            candidate = self._create_candidate(
                connector, target,
                notes=f"Supply ({connector.system_type}): {target.target_type.value}"
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]
