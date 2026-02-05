# File: src/timber_framing_generator/mep/routing/penetration_integration.py
"""
Penetration integration for MEP routing.

Bridges OAHS route output (routes_json) to existing penetration generation
logic. Converts route JSON to MEPRoute objects and calls the established
penetration rules for code-compliant penetration specifications.

Key Features:
1. JSON-to-MEPRoute conversion
2. Framing element parsing
3. Penetration generation with code compliance
4. Reinforcement flagging
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Any, Optional, Tuple

from src.timber_framing_generator.core.mep_system import MEPRoute, MEPDomain
from src.timber_framing_generator.mep.plumbing.penetration_rules import (
    generate_plumbing_penetrations,
    MAX_PENETRATION_RATIO,
    REINFORCEMENT_THRESHOLD,
    PLUMBING_PENETRATION_CLEARANCE,
)

logger = logging.getLogger(__name__)


# ============================================================================
# JSON Parsing
# ============================================================================

def _parse_routes_json(routes_json_str: str) -> List[Dict[str, Any]]:
    """
    Parse routes from JSON string.

    Args:
        routes_json_str: JSON string with routes data

    Returns:
        List of route dictionaries

    Raises:
        ValueError: If JSON is invalid or missing 'routes' key
    """
    try:
        data = json.loads(routes_json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid routes JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("Routes JSON must be an object")

    if "routes" not in data:
        raise ValueError("Routes JSON missing 'routes' key")

    return data.get("routes", [])


def _parse_framing_json(framing_json_str: str) -> List[Dict[str, Any]]:
    """
    Parse framing elements from JSON string.

    Args:
        framing_json_str: JSON string with framing data

    Returns:
        List of framing element dictionaries

    Raises:
        ValueError: If JSON is invalid
    """
    try:
        data = json.loads(framing_json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid framing JSON: {e}")

    # Support multiple JSON formats
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Try common keys
        for key in ["elements", "framing_elements", "framing", "walls"]:
            if key in data:
                elements = data[key]
                if isinstance(elements, list):
                    return elements

        # Flatten nested wall structures
        if "walls" in data:
            all_elements = []
            for wall in data["walls"]:
                if isinstance(wall, dict) and "elements" in wall:
                    all_elements.extend(wall["elements"])
            if all_elements:
                return all_elements

    return []


# ============================================================================
# Route Conversion
# ============================================================================

def _system_type_to_domain(system_type: str) -> MEPDomain:
    """
    Convert system type string to MEPDomain enum.

    Args:
        system_type: System type string (e.g., "sanitary_drain", "dhw")

    Returns:
        MEPDomain enum value
    """
    system_lower = system_type.lower() if system_type else ""

    if any(s in system_lower for s in ["sanitary", "drain", "vent", "dhw", "dcw", "water"]):
        return MEPDomain.PLUMBING
    elif any(s in system_lower for s in ["hvac", "duct", "supply", "return"]):
        return MEPDomain.HVAC
    elif any(s in system_lower for s in ["power", "electrical", "data", "lighting"]):
        return MEPDomain.ELECTRICAL
    else:
        return MEPDomain.PLUMBING  # Default


def _route_dict_to_mep_route(route_dict: Dict[str, Any]) -> MEPRoute:
    """
    Convert route dictionary to MEPRoute object.

    Args:
        route_dict: Route dictionary from routes_json

    Returns:
        MEPRoute object
    """
    route_id = route_dict.get("route_id", route_dict.get("id", "unknown"))
    system_type = route_dict.get("system_type", "unknown")
    domain = _system_type_to_domain(system_type)

    # Extract path points from segments
    path_points = []
    segments = route_dict.get("segments", [])

    for i, seg in enumerate(segments):
        start = seg.get("start", [])
        end = seg.get("end", [])

        # Add start point (avoid duplicates)
        if start and len(start) >= 3:
            point = (float(start[0]), float(start[1]), float(start[2]))
            if not path_points or path_points[-1] != point:
                path_points.append(point)

        # Add end point
        if end and len(end) >= 3:
            point = (float(end[0]), float(end[1]), float(end[2]))
            if not path_points or path_points[-1] != point:
                path_points.append(point)

    # Get pipe size (default to 1" if not specified)
    pipe_size = route_dict.get("pipe_size", 0.0833)  # 1" in feet
    if isinstance(pipe_size, str):
        # Try to parse size string
        try:
            pipe_size = float(pipe_size)
        except ValueError:
            pipe_size = 0.0833

    return MEPRoute(
        id=route_id,
        domain=domain,
        system_type=system_type,
        path_points=path_points,
        start_connector_id=route_dict.get("start_connector_id", ""),
        end_point_type=route_dict.get("end_point_type", "target"),
        pipe_size=pipe_size,
        end_point=path_points[-1] if path_points else None,
        penetrations=[],
    )


def _convert_routes(route_dicts: List[Dict[str, Any]]) -> List[MEPRoute]:
    """
    Convert list of route dictionaries to MEPRoute objects.

    Args:
        route_dicts: List of route dictionaries from routes_json

    Returns:
        List of MEPRoute objects
    """
    routes = []

    for route_dict in route_dicts:
        try:
            route = _route_dict_to_mep_route(route_dict)
            if route.path_points:  # Only add routes with valid paths
                routes.append(route)
        except Exception as e:
            logger.warning(f"Failed to convert route {route_dict.get('route_id', 'unknown')}: {e}")

    return routes


# ============================================================================
# Main Integration Function
# ============================================================================

def integrate_routes_to_penetrations(
    routes_json: str,
    framing_json: str,
    clearance: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Convert OAHS routes to penetration specifications.

    Bridges the JSON-based OAHS routing output to the existing penetration
    generation logic, producing validated penetration specs with code
    compliance information.

    Args:
        routes_json: JSON string from gh_mep_router (routes_json output)
        framing_json: JSON string from gh_framing_generator (framing_json output)
        clearance: Optional custom pipe clearance in feet (default 1/4")

    Returns:
        Dictionary with:
        - penetrations: List of penetration specifications
        - summary: Statistics about allowed/blocked/reinforcement needed

    Raises:
        ValueError: If JSON inputs are invalid
    """
    logger.info("Starting route-to-penetration integration")

    # Parse inputs
    route_dicts = _parse_routes_json(routes_json)
    framing_elements = _parse_framing_json(framing_json)

    logger.info(f"Parsed {len(route_dicts)} routes and {len(framing_elements)} framing elements")

    # Convert routes to MEPRoute objects
    routes = _convert_routes(route_dicts)
    logger.info(f"Converted {len(routes)} valid routes")

    # Generate penetrations using existing logic
    penetrations = generate_plumbing_penetrations(routes, framing_elements)

    # Build summary statistics
    total = len(penetrations)
    allowed = sum(1 for p in penetrations if p.get("is_allowed", False))
    blocked = total - allowed
    reinforcement_needed = sum(1 for p in penetrations if p.get("reinforcement_required", False))

    summary = {
        "total": total,
        "allowed": allowed,
        "blocked": blocked,
        "reinforcement_required": reinforcement_needed,
        "routes_processed": len(routes),
        "framing_elements": len(framing_elements),
    }

    logger.info(f"Generated {total} penetrations: {allowed} allowed, {blocked} blocked, {reinforcement_needed} need reinforcement")

    return {
        "penetrations": penetrations,
        "summary": summary,
    }


def penetrations_to_json(result: Dict[str, Any]) -> str:
    """
    Convert penetration result to JSON string.

    Args:
        result: Result dictionary from integrate_routes_to_penetrations

    Returns:
        JSON string
    """
    return json.dumps(result, indent=2)


# ============================================================================
# Utility Functions
# ============================================================================

def extract_penetration_points(
    penetrations: List[Dict[str, Any]]
) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
    """
    Extract points from penetrations grouped by status.

    Args:
        penetrations: List of penetration specifications

    Returns:
        Tuple of (allowed_points, blocked_points, reinforcement_points)
    """
    allowed = []
    blocked = []
    reinforcement = []

    for pen in penetrations:
        loc = pen.get("location", {})
        point = (
            float(loc.get("x", 0)),
            float(loc.get("y", 0)),
            float(loc.get("z", 0))
        )

        if not pen.get("is_allowed", False):
            blocked.append(point)
        elif pen.get("reinforcement_required", False):
            reinforcement.append(point)
        else:
            allowed.append(point)

    return allowed, blocked, reinforcement


def get_penetration_info_string(result: Dict[str, Any]) -> str:
    """
    Generate a human-readable info string from penetration results.

    Args:
        result: Result dictionary from integrate_routes_to_penetrations

    Returns:
        Formatted info string
    """
    summary = result.get("summary", {})

    lines = [
        "Penetration Analysis Results",
        "=" * 30,
        f"Routes processed: {summary.get('routes_processed', 0)}",
        f"Framing elements: {summary.get('framing_elements', 0)}",
        "",
        f"Total penetrations: {summary.get('total', 0)}",
        f"  Allowed: {summary.get('allowed', 0)}",
        f"  Blocked: {summary.get('blocked', 0)}",
        f"  Reinforcement required: {summary.get('reinforcement_required', 0)}",
        "",
        f"Code limit: {MAX_PENETRATION_RATIO * 100:.0f}% of member depth",
        f"Reinforcement threshold: {REINFORCEMENT_THRESHOLD * 100:.0f}% of member depth",
    ]

    return "\n".join(lines)
