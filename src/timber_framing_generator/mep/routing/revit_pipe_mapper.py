# File: src/timber_framing_generator/mep/routing/revit_pipe_mapper.py
"""
Revit pipe/conduit type mapping for MEP routes.

Maps OAHS route system types to Revit pipe/conduit configurations,
detects fittings at direction changes, and generates specifications
for Revit element creation via Rhino.Inside.Revit.

Key Features:
1. System type to Revit type mapping
2. Direction change detection for elbow fittings
3. Junction detection for tee fittings
4. Size normalization to Revit nominal sizes
"""

from __future__ import annotations

import json
import math
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# System type to Revit configuration mapping
REVIT_PIPE_TYPES: Dict[str, Dict[str, str]] = {
    "sanitary_drain": {
        "category": "Pipe",
        "system_type": "Sanitary",
        "pipe_type": "Cast Iron - No Hub",
        "fitting_family": "Generic - CI",
    },
    "sanitary_vent": {
        "category": "Pipe",
        "system_type": "Sanitary",
        "pipe_type": "PVC - Schedule 40",
        "fitting_family": "Generic - PVC",
    },
    "dhw": {
        "category": "Pipe",
        "system_type": "Domestic Hot Water",
        "pipe_type": "Copper Type L",
        "fitting_family": "Generic - Copper",
    },
    "dcw": {
        "category": "Pipe",
        "system_type": "Domestic Cold Water",
        "pipe_type": "PEX",
        "fitting_family": "Generic - PEX",
    },
    "power": {
        "category": "Conduit",
        "system_type": "Power",
        "conduit_type": "EMT",
        "fitting_family": "Generic - EMT",
    },
    "data": {
        "category": "Conduit",
        "system_type": "Communications",
        "conduit_type": "EMT",
        "fitting_family": "Generic - EMT",
    },
    "lighting": {
        "category": "Conduit",
        "system_type": "Power - Lighting",
        "conduit_type": "EMT",
        "fitting_family": "Generic - EMT",
    },
}

# Default configuration for unknown system types
DEFAULT_PIPE_CONFIG: Dict[str, str] = {
    "category": "Pipe",
    "system_type": "Other",
    "pipe_type": "Default",
    "fitting_family": "Generic",
}

# Nominal pipe sizes (OD in feet to nominal size string)
NOMINAL_SIZES: Dict[float, str] = {
    0.0729: '1/2"',
    0.0875: '3/4"',
    0.1104: '1"',
    0.1396: '1-1/4"',
    0.1583: '1-1/2"',
    0.1979: '2"',
    0.2917: '3"',
    0.375: '4"',
}

# Angle tolerances for fitting detection (degrees)
ELBOW_90_MIN = 85.0
ELBOW_90_MAX = 95.0
ELBOW_45_MIN = 40.0
ELBOW_45_MAX = 50.0


# ============================================================================
# Enums
# ============================================================================

class FittingType(Enum):
    """Types of pipe/conduit fittings."""
    ELBOW_90 = "elbow_90"
    ELBOW_45 = "elbow_45"
    TEE = "tee"
    WYE = "wye"
    CROSS = "cross"
    COUPLING = "coupling"
    CAP = "cap"
    CUSTOM = "custom"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PipeSpec:
    """Specification for a single pipe segment."""
    id: str
    route_id: str
    system_type: str
    start_point: Tuple[float, float, float]
    end_point: Tuple[float, float, float]
    diameter: float
    revit_config: Dict[str, str]
    nominal_size: str = ""
    length: float = 0.0

    def __post_init__(self):
        """Calculate derived values."""
        if not self.nominal_size:
            self.nominal_size = get_nominal_size(self.diameter)
        if self.length == 0:
            self.length = self._calculate_length()

    def _calculate_length(self) -> float:
        """Calculate pipe length from endpoints."""
        dx = self.end_point[0] - self.start_point[0]
        dy = self.end_point[1] - self.start_point[1]
        dz = self.end_point[2] - self.start_point[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "route_id": self.route_id,
            "system_type": self.system_type,
            "start_point": list(self.start_point),
            "end_point": list(self.end_point),
            "diameter": self.diameter,
            "nominal_size": self.nominal_size,
            "length": self.length,
            "revit_config": self.revit_config,
        }


@dataclass
class FittingSpec:
    """Specification for a pipe fitting."""
    id: str
    fitting_type: FittingType
    location: Tuple[float, float, float]
    connected_pipes: List[str]
    angle: Optional[float] = None
    system_type: str = ""
    fitting_family: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.fitting_type.value,
            "location": list(self.location),
            "connected_pipes": self.connected_pipes,
            "angle": self.angle,
            "system_type": self.system_type,
            "fitting_family": self.fitting_family,
        }


@dataclass
class PipeCreatorResult:
    """Result from pipe creation processing."""
    pipes: List[PipeSpec] = field(default_factory=list)
    fittings: List[FittingSpec] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pipes": [p.to_dict() for p in self.pipes],
            "fittings": [f.to_dict() for f in self.fittings],
            "warnings": self.warnings,
            "summary": {
                "total_pipes": len(self.pipes),
                "total_fittings": len(self.fittings),
                "total_warnings": len(self.warnings),
            }
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# ============================================================================
# Utility Functions
# ============================================================================

def get_revit_config(system_type: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Get Revit configuration for a system type.

    Args:
        system_type: MEP system type (e.g., "sanitary_drain", "dhw")
        overrides: Optional dictionary of type overrides

    Returns:
        Dictionary with Revit configuration
    """
    # Normalize system type
    sys_key = system_type.lower().strip() if system_type else "default"

    # Check overrides first
    if overrides and sys_key in overrides:
        config = DEFAULT_PIPE_CONFIG.copy()
        config.update(overrides[sys_key])
        return config

    # Use standard mapping
    if sys_key in REVIT_PIPE_TYPES:
        return REVIT_PIPE_TYPES[sys_key].copy()

    # Default config
    logger.warning(f"Unknown system type '{system_type}', using default config")
    return DEFAULT_PIPE_CONFIG.copy()


def get_nominal_size(diameter_ft: float) -> str:
    """
    Get nominal pipe size string from diameter.

    Args:
        diameter_ft: Pipe outer diameter in feet

    Returns:
        Nominal size string (e.g., '1-1/2"')
    """
    if not diameter_ft or diameter_ft <= 0:
        return "Unknown"

    # Find closest match
    best_match = "Custom"
    best_diff = float('inf')

    for od, nominal in NOMINAL_SIZES.items():
        diff = abs(od - diameter_ft)
        if diff < best_diff:
            best_diff = diff
            best_match = nominal

    # If very different from any standard size, mark as custom
    if best_diff > 0.02:  # More than ~1/4" off
        return f'{diameter_ft * 12:.2f}" (custom)'

    return best_match


def calculate_angle(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    p3: Tuple[float, float, float]
) -> float:
    """
    Calculate angle at p2 between segments p1-p2 and p2-p3.

    Args:
        p1: First point
        p2: Vertex point (where angle is measured)
        p3: Third point

    Returns:
        Angle in degrees (0-180)
    """
    # Vectors from p2
    v1 = (p1[0] - p2[0], p1[1] - p2[1], p1[2] - p2[2])
    v2 = (p3[0] - p2[0], p3[1] - p2[1], p3[2] - p2[2])

    # Magnitudes
    mag1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
    mag2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)

    if mag1 == 0 or mag2 == 0:
        return 180.0  # Degenerate - treat as straight

    # Dot product
    dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]

    # Cosine of angle
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp for numerical stability

    # Angle in degrees
    angle = math.degrees(math.acos(cos_angle))

    return angle


def detect_fitting_type(angle: float) -> Optional[FittingType]:
    """
    Detect fitting type from angle.

    Args:
        angle: Angle in degrees at direction change

    Returns:
        FittingType or None if straight (no fitting needed)
    """
    # Straight segment (no fitting needed)
    if angle >= 175:
        return None

    # 90 degree elbow
    if ELBOW_90_MIN <= angle <= ELBOW_90_MAX:
        return FittingType.ELBOW_90

    # 45 degree elbow
    if ELBOW_45_MIN <= angle <= ELBOW_45_MAX:
        return FittingType.ELBOW_45

    # Custom angle fitting
    return FittingType.CUSTOM


# ============================================================================
# Route Processing
# ============================================================================

def process_route(
    route: Dict[str, Any],
    route_index: int,
    type_overrides: Optional[Dict[str, Any]] = None,
    create_fittings: bool = True
) -> Tuple[List[PipeSpec], List[FittingSpec], List[str]]:
    """
    Process a single route into pipe and fitting specs.

    Args:
        route: Route dictionary from routes_json
        route_index: Index for ID generation
        type_overrides: Optional pipe type overrides
        create_fittings: Whether to detect and create fittings

    Returns:
        Tuple of (pipes, fittings, warnings)
    """
    pipes = []
    fittings = []
    warnings = []

    route_id = route.get("route_id", f"route_{route_index:03d}")
    system_type = route.get("system_type", "default")
    pipe_diameter = route.get("pipe_size", 0.0833)  # Default 1"

    # Get Revit configuration
    revit_config = get_revit_config(system_type, type_overrides)

    # Extract path points from segments
    segments = route.get("segments", [])
    if not segments:
        warnings.append(f"Route {route_id} has no segments")
        return pipes, fittings, warnings

    # Build point sequence
    path_points = []
    for seg in segments:
        start = seg.get("start", [])
        end = seg.get("end", [])

        if start and len(start) >= 3:
            point = (float(start[0]), float(start[1]), float(start[2]))
            if not path_points or path_points[-1] != point:
                path_points.append(point)

        if end and len(end) >= 3:
            point = (float(end[0]), float(end[1]), float(end[2]))
            if not path_points or path_points[-1] != point:
                path_points.append(point)

    if len(path_points) < 2:
        warnings.append(f"Route {route_id} has fewer than 2 points")
        return pipes, fittings, warnings

    # Create pipe specs for each segment
    for i in range(len(path_points) - 1):
        pipe_id = f"pipe_{route_id}_{i:03d}"
        pipe = PipeSpec(
            id=pipe_id,
            route_id=route_id,
            system_type=system_type,
            start_point=path_points[i],
            end_point=path_points[i + 1],
            diameter=pipe_diameter,
            revit_config=revit_config,
        )
        pipes.append(pipe)

    # Detect fittings at direction changes
    if create_fittings and len(path_points) >= 3:
        for i in range(1, len(path_points) - 1):
            p1 = path_points[i - 1]
            p2 = path_points[i]
            p3 = path_points[i + 1]

            angle = calculate_angle(p1, p2, p3)
            fitting_type = detect_fitting_type(angle)

            if fitting_type:
                fitting_id = f"fitting_{route_id}_{i:03d}"
                # Get connected pipe IDs
                connected = [
                    f"pipe_{route_id}_{i-1:03d}",
                    f"pipe_{route_id}_{i:03d}"
                ]

                fitting = FittingSpec(
                    id=fitting_id,
                    fitting_type=fitting_type,
                    location=p2,
                    connected_pipes=connected,
                    angle=angle,
                    system_type=system_type,
                    fitting_family=revit_config.get("fitting_family", "Generic"),
                )
                fittings.append(fitting)

                if fitting_type == FittingType.CUSTOM:
                    warnings.append(
                        f"Route {route_id}: Non-standard angle {angle:.1f}° at point {i}"
                    )

    return pipes, fittings, warnings


def process_routes_to_pipes(
    routes_json: str,
    type_overrides: Optional[str] = None,
    create_fittings: bool = True
) -> PipeCreatorResult:
    """
    Convert OAHS routes to pipe/fitting specifications.

    Args:
        routes_json: JSON string from gh_mep_router
        type_overrides: Optional JSON string with pipe type overrides
        create_fittings: Whether to create fitting specs

    Returns:
        PipeCreatorResult with pipes, fittings, and warnings
    """
    logger.info("Processing routes to pipe specifications")

    result = PipeCreatorResult()

    # Parse routes
    try:
        data = json.loads(routes_json)
    except json.JSONDecodeError as e:
        result.warnings.append(f"Invalid routes JSON: {e}")
        return result

    routes = data.get("routes", [])
    if not routes:
        result.warnings.append("No routes found in routes_json")
        return result

    # Parse overrides if provided
    overrides = None
    if type_overrides:
        try:
            overrides = json.loads(type_overrides)
        except json.JSONDecodeError:
            result.warnings.append("Invalid type_overrides JSON, using defaults")

    # Process each route
    for i, route in enumerate(routes):
        try:
            pipes, fittings, warnings = process_route(
                route, i, overrides, create_fittings
            )
            result.pipes.extend(pipes)
            result.fittings.extend(fittings)
            result.warnings.extend(warnings)
        except Exception as e:
            route_id = route.get("route_id", f"route_{i}")
            result.warnings.append(f"Error processing {route_id}: {e}")
            logger.exception(f"Error processing route {route_id}")

    logger.info(
        f"Generated {len(result.pipes)} pipes, "
        f"{len(result.fittings)} fittings, "
        f"{len(result.warnings)} warnings"
    )

    return result


def detect_junctions(routes_json: str, tolerance: float = 0.01) -> List[Dict[str, Any]]:
    """
    Detect junction points where multiple routes meet.

    Args:
        routes_json: JSON string with routes
        tolerance: Distance tolerance for point matching (feet)

    Returns:
        List of junction dictionaries with location and connected routes
    """
    # Parse routes
    try:
        data = json.loads(routes_json)
    except json.JSONDecodeError:
        return []

    routes = data.get("routes", [])

    # Collect all endpoints
    endpoints = []  # List of (point, route_id, is_start)

    for route in routes:
        route_id = route.get("route_id", "unknown")
        segments = route.get("segments", [])

        if segments:
            # Start point
            first_seg = segments[0]
            start = first_seg.get("start", [])
            if start and len(start) >= 3:
                endpoints.append((
                    (float(start[0]), float(start[1]), float(start[2])),
                    route_id,
                    True
                ))

            # End point
            last_seg = segments[-1]
            end = last_seg.get("end", [])
            if end and len(end) >= 3:
                endpoints.append((
                    (float(end[0]), float(end[1]), float(end[2])),
                    route_id,
                    False
                ))

    # Find junction points (endpoints within tolerance)
    junctions = []
    used = set()

    for i, (pt1, rid1, is_start1) in enumerate(endpoints):
        if i in used:
            continue

        connected = [(rid1, is_start1)]
        location = pt1

        for j, (pt2, rid2, is_start2) in enumerate(endpoints):
            if j <= i or j in used:
                continue

            # Check distance
            dx = pt1[0] - pt2[0]
            dy = pt1[1] - pt2[1]
            dz = pt1[2] - pt2[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)

            if dist <= tolerance:
                connected.append((rid2, is_start2))
                used.add(j)

        # Create junction if multiple routes meet
        if len(connected) >= 2:
            junctions.append({
                "id": f"junction_{len(junctions):03d}",
                "location": list(location),
                "connected_routes": [
                    {"route_id": rid, "at_start": is_start}
                    for rid, is_start in connected
                ],
                "fitting_type": "tee" if len(connected) == 2 else "cross",
            })

    logger.info(f"Detected {len(junctions)} junction points")
    return junctions
