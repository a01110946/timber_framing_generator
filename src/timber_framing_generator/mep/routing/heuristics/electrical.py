# File: src/timber_framing_generator/mep/routing/heuristics/electrical.py
"""
Electrical-specific target heuristics.

Provides heuristics for power, data, and low-voltage systems.
"""

from typing import List, Optional

from .base import TargetHeuristic, ConnectorInfo
from ..targets import RoutingTarget, TargetCandidate, TargetType
from ..domains import RoutingDomain


class PowerHeuristic(TargetHeuristic):
    """
    Heuristic for electrical power circuits.

    Priorities:
    1. Panel boundary (wall route to electrical panel)
    2. Junction box in ceiling (homerun consolidation)

    Electrical routing typically:
    - Runs through wall cavities (stud bays)
    - Can run through ceiling space
    - Must avoid plumbing and gas
    - Follows cable tray or conduit
    """

    panel_boundary_bonus: float = -8.0
    ceiling_bonus: float = -3.0

    @property
    def system_types(self) -> List[str]:
        return ["Power", "Electrical", "Circuit"]

    @property
    def preferred_target_types(self) -> List[TargetType]:
        return [
            TargetType.PANEL_BOUNDARY,
            TargetType.CEILING_PENETRATION,
            TargetType.EQUIPMENT
        ]

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """Score targets for power routing."""
        base_score = super().score_target(connector, target, domain)

        # Strong preference for panel boundary
        if target.target_type == TargetType.PANEL_BOUNDARY:
            base_score += self.panel_boundary_bonus

        # Ceiling routes for homerun
        if target.target_type == TargetType.CEILING_PENETRATION:
            base_score += self.ceiling_bonus

        # Slight penalty for equipment (needs specific location)
        if target.target_type == TargetType.EQUIPMENT:
            base_score += 2.0

        return base_score

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find power routing targets."""
        # Filter to power-compatible targets
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_target_type(valid_targets, self.preferred_target_types)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Score and rank
        candidates = []
        for target in valid_targets:
            score = self.score_target(connector, target)
            candidate = self._create_candidate(
                connector, target,
                notes=f"Power: {target.target_type.value}"
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]


class DataHeuristic(TargetHeuristic):
    """
    Heuristic for data and low-voltage systems.

    Priorities:
    1. Patch panel / IDF (Intermediate Distribution Frame)
    2. Ceiling raceway
    3. Equipment locations

    Data routing:
    - Must maintain separation from power (EMI)
    - Prefers dedicated raceways
    - Cat6 has distance limitations (~100m)
    """

    patch_panel_bonus: float = -10.0
    ceiling_bonus: float = -5.0
    separation_requirement: float = 1.0  # Minimum separation from power in feet

    @property
    def system_types(self) -> List[str]:
        return ["Data", "LowVoltage", "Network", "Audio", "Security"]

    @property
    def preferred_target_types(self) -> List[TargetType]:
        return [
            TargetType.PANEL_BOUNDARY,  # For patch panel
            TargetType.CEILING_PENETRATION,
            TargetType.EQUIPMENT
        ]

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """Score targets for data routing with separation considerations."""
        base_score = super().score_target(connector, target, domain)

        # Strong preference for patch panel / IDF locations
        if target.target_type == TargetType.PANEL_BOUNDARY:
            # Check if it's a data panel (not electrical)
            if target.metadata.get("panel_type") == "data":
                base_score += self.patch_panel_bonus
            else:
                base_score += self.patch_panel_bonus * 0.5  # Less bonus for generic panel

        # Ceiling routes for raceway
        if target.target_type == TargetType.CEILING_PENETRATION:
            base_score += self.ceiling_bonus

        # Check distance limitations (Cat6 ~328 ft / 100m)
        distance = self._manhattan_distance_3d(connector.location, target.location)
        if distance > 300:  # Near Cat6 limit
            base_score += (distance - 300) * 2.0  # Increasing penalty

        return base_score

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find data routing targets."""
        # Filter to data-compatible targets
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_target_type(valid_targets, self.preferred_target_types)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Score and rank
        candidates = []
        for target in valid_targets:
            score = self.score_target(connector, target)
            candidate = self._create_candidate(
                connector, target,
                notes=f"Data: {target.target_type.value}"
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]


class LightingHeuristic(TargetHeuristic):
    """
    Heuristic for lighting circuits.

    Priorities:
    1. Junction box in ceiling (homerun to lighting circuits)
    2. Switch loop locations in wall
    3. Panel boundary for homerun

    Lighting typically:
    - Runs in ceiling cavities
    - Has switch loops dropping to wall switches
    - Grouped by circuit
    """

    ceiling_bonus: float = -10.0
    wall_switch_bonus: float = -5.0

    @property
    def system_types(self) -> List[str]:
        return ["Lighting"]

    @property
    def preferred_target_types(self) -> List[TargetType]:
        return [
            TargetType.CEILING_PENETRATION,
            TargetType.PANEL_BOUNDARY,
            TargetType.EQUIPMENT
        ]

    def score_target(
        self,
        connector: ConnectorInfo,
        target: RoutingTarget,
        domain: Optional[RoutingDomain] = None
    ) -> float:
        """Score targets for lighting routing."""
        base_score = super().score_target(connector, target, domain)

        # Strong preference for ceiling
        if target.target_type == TargetType.CEILING_PENETRATION:
            base_score += self.ceiling_bonus

        # Panel boundary for homerun
        if target.target_type == TargetType.PANEL_BOUNDARY:
            base_score += self.wall_switch_bonus

        return base_score

    def find_candidates(
        self,
        connector: ConnectorInfo,
        targets: List[RoutingTarget],
        domains: List[RoutingDomain],
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """Find lighting routing targets."""
        # Filter to lighting-compatible targets
        valid_targets = self._filter_available(targets)
        valid_targets = self._filter_by_target_type(valid_targets, self.preferred_target_types)
        valid_targets = self._filter_by_capacity(valid_targets, connector.diameter)

        # Score and rank
        candidates = []
        for target in valid_targets:
            score = self.score_target(connector, target)
            candidate = self._create_candidate(
                connector, target,
                notes=f"Lighting: {target.target_type.value}"
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.score)
        return candidates[:max_candidates]
