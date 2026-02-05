# File: src/timber_framing_generator/mep/routing/target_generator.py
"""
Target Candidate Generator for MEP routing.

Orchestrates system-specific heuristics to find and rank routing targets
for MEP connectors.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import logging

from .targets import RoutingTarget, TargetCandidate, TargetType
from .domains import RoutingDomain, RoutingDomainType
from .heuristics.base import TargetHeuristic, ConnectorInfo, FallbackHeuristic
from .heuristics.plumbing import SanitaryHeuristic, VentHeuristic, SupplyHeuristic
from .heuristics.electrical import PowerHeuristic, DataHeuristic, LightingHeuristic

logger = logging.getLogger(__name__)


@dataclass
class WetWallInfo:
    """
    Information about a detected wet wall.

    Attributes:
        wall_id: ID of the wall
        fixture_count: Number of plumbing fixtures on this wall
        has_stack: Whether wall has existing drain stack
        is_back_to_back: Whether wall backs another wet wall
        score: Wet wall score (higher = more suitable)
    """
    wall_id: str
    fixture_count: int = 0
    has_stack: bool = False
    is_back_to_back: bool = False
    score: float = 0.0


class TargetCandidateGenerator:
    """
    Generates ranked target candidates for MEP connectors.

    Uses system-specific heuristics to find and rank potential
    routing targets based on fixture location, system type,
    and building geometry.

    Usage:
        generator = TargetCandidateGenerator()
        generator.add_targets(targets)
        generator.add_domains(domains)

        for connector in connectors:
            candidates = generator.find_candidates(connector)
            best_target = candidates[0].target if candidates else None
    """

    def __init__(self):
        """Initialize with default heuristics."""
        self._heuristics: Dict[str, TargetHeuristic] = {}
        self._targets: List[RoutingTarget] = []
        self._domains: List[RoutingDomain] = []
        self._domain_lookup: Dict[str, RoutingDomain] = {}
        self._fallback = FallbackHeuristic()

        # Register default heuristics
        self._register_default_heuristics()

    def _register_default_heuristics(self):
        """Register the default set of heuristics."""
        # Plumbing
        self.register_heuristic(SanitaryHeuristic())
        self.register_heuristic(VentHeuristic())
        self.register_heuristic(SupplyHeuristic())

        # Electrical
        self.register_heuristic(PowerHeuristic())
        self.register_heuristic(DataHeuristic())
        self.register_heuristic(LightingHeuristic())

    def register_heuristic(self, heuristic: TargetHeuristic):
        """
        Register a heuristic for specific system types.

        Args:
            heuristic: The heuristic to register
        """
        for system_type in heuristic.system_types:
            self._heuristics[system_type] = heuristic
            logger.debug(f"Registered heuristic for {system_type}")

    def get_heuristic(self, system_type: str) -> TargetHeuristic:
        """
        Get the appropriate heuristic for a system type.

        Args:
            system_type: MEP system type

        Returns:
            The registered heuristic or fallback
        """
        return self._heuristics.get(system_type, self._fallback)

    def add_target(self, target: RoutingTarget):
        """Add a routing target."""
        self._targets.append(target)

    def add_targets(self, targets: List[RoutingTarget]):
        """Add multiple routing targets."""
        self._targets.extend(targets)

    def clear_targets(self):
        """Remove all targets."""
        self._targets.clear()

    def add_domain(self, domain: RoutingDomain):
        """Add a routing domain."""
        self._domains.append(domain)
        self._domain_lookup[domain.id] = domain

    def add_domains(self, domains: List[RoutingDomain]):
        """Add multiple routing domains."""
        for domain in domains:
            self.add_domain(domain)

    def clear_domains(self):
        """Remove all domains."""
        self._domains.clear()
        self._domain_lookup.clear()

    def get_domain(self, domain_id: str) -> Optional[RoutingDomain]:
        """Get a domain by ID."""
        return self._domain_lookup.get(domain_id)

    @property
    def targets(self) -> List[RoutingTarget]:
        """Get all registered targets."""
        return self._targets.copy()

    @property
    def domains(self) -> List[RoutingDomain]:
        """Get all registered domains."""
        return self._domains.copy()

    def find_candidates(
        self,
        connector: ConnectorInfo,
        max_candidates: int = 5
    ) -> List[TargetCandidate]:
        """
        Find and rank target candidates for a connector.

        Uses the appropriate heuristic for the connector's system type
        to find compatible targets and rank them.

        Args:
            connector: The MEP connector needing a target
            max_candidates: Maximum number of candidates to return

        Returns:
            List of TargetCandidates sorted by score (best first)
        """
        heuristic = self.get_heuristic(connector.system_type)

        logger.debug(
            f"Finding candidates for {connector.id} ({connector.system_type}) "
            f"using {type(heuristic).__name__}"
        )

        candidates = heuristic.find_candidates(
            connector,
            self._targets,
            self._domains,
            max_candidates
        )

        logger.debug(f"Found {len(candidates)} candidates")
        return candidates

    def find_all_candidates(
        self,
        connectors: List[ConnectorInfo],
        max_candidates_per_connector: int = 5
    ) -> Dict[str, List[TargetCandidate]]:
        """
        Find candidates for multiple connectors.

        Args:
            connectors: List of connectors
            max_candidates_per_connector: Max candidates per connector

        Returns:
            Dict mapping connector ID to list of candidates
        """
        results = {}
        for connector in connectors:
            results[connector.id] = self.find_candidates(
                connector, max_candidates_per_connector
            )
        return results

    def to_dict(self) -> dict:
        """Serialize generator state to dictionary."""
        return {
            "targets": [t.to_dict() for t in self._targets],
            "domains": [d.to_dict() for d in self._domains],
            "registered_heuristics": list(self._heuristics.keys())
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TargetCandidateGenerator":
        """Deserialize generator from dictionary."""
        generator = cls()

        # Load targets
        for target_data in data.get("targets", []):
            generator.add_target(RoutingTarget.from_dict(target_data))

        # Load domains
        for domain_data in data.get("domains", []):
            generator.add_domain(RoutingDomain.from_dict(domain_data))

        return generator


def detect_wet_walls(
    walls: List[Dict[str, Any]],
    connectors: List[ConnectorInfo],
    adjacency_threshold: float = 2.0
) -> List[WetWallInfo]:
    """
    Identify walls that are or should be wet walls.

    Criteria for wet wall detection:
    - Multiple plumbing fixtures mounted on the wall
    - Contains bathroom or kitchen fixtures
    - Back-to-back with another potential wet wall
    - Has existing drain stack (from metadata)

    Args:
        walls: List of wall data dictionaries
        connectors: List of MEP connectors with fixture info
        adjacency_threshold: Distance threshold for adjacency (feet)

    Returns:
        List of WetWallInfo for detected wet walls
    """
    # Count plumbing fixtures per wall
    wall_fixtures: Dict[str, List[ConnectorInfo]] = {}

    plumbing_systems = {"Sanitary", "Vent", "DomesticHotWater", "DomesticColdWater",
                        "DHW", "DCW"}

    for connector in connectors:
        if connector.system_type in plumbing_systems and connector.wall_id:
            if connector.wall_id not in wall_fixtures:
                wall_fixtures[connector.wall_id] = []
            wall_fixtures[connector.wall_id].append(connector)

    # Build wet wall info
    wet_walls: List[WetWallInfo] = []

    for wall_id, fixtures in wall_fixtures.items():
        if len(fixtures) >= 2:  # At least 2 plumbing fixtures
            info = WetWallInfo(
                wall_id=wall_id,
                fixture_count=len(fixtures)
            )

            # Check for important fixture types
            has_toilet = any(
                c.fixture_type and "toilet" in c.fixture_type.lower()
                for c in fixtures
            )
            has_sink = any(
                c.fixture_type and "sink" in c.fixture_type.lower()
                for c in fixtures
            )

            # Score based on fixtures
            info.score = len(fixtures) * 10
            if has_toilet:
                info.score += 20  # Toilets strongly indicate wet wall
            if has_sink:
                info.score += 10

            wet_walls.append(info)

    # Check for back-to-back walls
    wall_centers = _get_wall_centers(walls)
    for i, info_a in enumerate(wet_walls):
        for info_b in wet_walls[i+1:]:
            if _are_back_to_back(
                wall_centers.get(info_a.wall_id),
                wall_centers.get(info_b.wall_id),
                adjacency_threshold
            ):
                info_a.is_back_to_back = True
                info_b.is_back_to_back = True
                info_a.score += 15
                info_b.score += 15

    # Sort by score
    wet_walls.sort(key=lambda w: w.score, reverse=True)

    return wet_walls


def _get_wall_centers(walls: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float, float]]:
    """Extract wall centers from wall data."""
    centers = {}
    for wall in walls:
        wall_id = wall.get("id") or wall.get("wall_id")
        if wall_id:
            # Try to get center from wall data
            if "center" in wall:
                centers[wall_id] = tuple(wall["center"])
            elif "start" in wall and "end" in wall:
                start = wall["start"]
                end = wall["end"]
                centers[wall_id] = (
                    (start[0] + end[0]) / 2,
                    (start[1] + end[1]) / 2,
                    start[2] if len(start) > 2 else 0
                )
    return centers


def _are_back_to_back(
    center_a: Optional[Tuple[float, float, float]],
    center_b: Optional[Tuple[float, float, float]],
    threshold: float
) -> bool:
    """Check if two walls are back-to-back (parallel and close)."""
    if not center_a or not center_b:
        return False

    # Simple distance check (full back-to-back detection would need wall normals)
    dx = abs(center_a[0] - center_b[0])
    dy = abs(center_a[1] - center_b[1])

    # Back-to-back walls are typically within wall thickness + clearance
    return (dx < threshold and dy > threshold * 2) or \
           (dy < threshold and dx > threshold * 2)


def generate_targets_from_walls(
    walls: List[Dict[str, Any]],
    connectors: List[ConnectorInfo],
    include_floor_penetrations: bool = True
) -> List[RoutingTarget]:
    """
    Generate routing targets from wall and connector data.

    Creates targets for:
    - Wet walls (for plumbing)
    - Panel boundaries (for electrical)
    - Floor penetrations (for cross-floor routing)

    Args:
        walls: List of wall data dictionaries
        connectors: List of MEP connectors
        include_floor_penetrations: Whether to add floor penetration targets

    Returns:
        List of generated RoutingTargets
    """
    targets = []
    target_counter = 0

    # Detect wet walls
    wet_walls = detect_wet_walls(walls, connectors)

    for wet_wall in wet_walls:
        # Find wall data for this wet wall
        wall_data = next(
            (w for w in walls
             if w.get("id") == wet_wall.wall_id or w.get("wall_id") == wet_wall.wall_id),
            None
        )

        if wall_data:
            # Get wall center for target location
            center = _get_wall_center(wall_data)
            if center:
                target = RoutingTarget(
                    id=f"wet_wall_{target_counter}",
                    target_type=TargetType.WET_WALL,
                    location=center,
                    domain_id=wet_wall.wall_id,
                    plane_location=(center[0], center[1]),
                    systems_served=["Sanitary", "Vent", "DomesticHotWater",
                                    "DomesticColdWater", "DHW", "DCW"],
                    capacity=0.333,  # 4" default
                    priority=max(0, 10 - wet_wall.fixture_count),
                    metadata={
                        "wall_id": wet_wall.wall_id,
                        "fixture_count": wet_wall.fixture_count,
                        "is_back_to_back": wet_wall.is_back_to_back
                    }
                )
                targets.append(target)
                target_counter += 1

    # Add floor penetration targets if requested
    if include_floor_penetrations:
        floor_targets = _generate_floor_penetration_targets(
            walls, connectors, target_counter
        )
        targets.extend(floor_targets)

    logger.info(f"Generated {len(targets)} routing targets")
    return targets


def _get_wall_center(wall_data: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    """Get center point of a wall."""
    if "center" in wall_data:
        c = wall_data["center"]
        return (c[0], c[1], c[2] if len(c) > 2 else 0)

    if "start" in wall_data and "end" in wall_data:
        start = wall_data["start"]
        end = wall_data["end"]
        return (
            (start[0] + end[0]) / 2,
            (start[1] + end[1]) / 2,
            start[2] if len(start) > 2 else 0
        )

    return None


def _generate_floor_penetration_targets(
    walls: List[Dict[str, Any]],
    connectors: List[ConnectorInfo],
    start_counter: int
) -> List[RoutingTarget]:
    """
    Generate floor penetration targets for isolated fixtures.

    Fixtures far from walls (like kitchen islands) need floor penetrations.
    """
    targets = []
    counter = start_counter

    # Find connectors without nearby walls
    for connector in connectors:
        if connector.system_type in ["Sanitary", "DomesticHotWater", "DomesticColdWater"]:
            if not connector.wall_id:
                # Connector not attached to wall - needs floor penetration
                target = RoutingTarget(
                    id=f"floor_pen_{counter}",
                    target_type=TargetType.FLOOR_PENETRATION,
                    location=(
                        connector.location[0],
                        connector.location[1],
                        connector.location[2] - 0.5  # Below fixture
                    ),
                    domain_id="floor_0",  # Default floor domain
                    plane_location=(connector.location[0], connector.location[1]),
                    systems_served=[connector.system_type],
                    capacity=0.333,
                    priority=5,  # Lower priority than wet wall
                    metadata={
                        "fixture_id": connector.fixture_id,
                        "generated_for": connector.id
                    }
                )
                targets.append(target)
                counter += 1

    return targets
