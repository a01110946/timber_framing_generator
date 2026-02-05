# File: src/timber_framing_generator/mep/plumbing/connector_extractor.py
"""
Plumbing connector extraction from Revit fixtures.

This module provides functions to extract MEP connectors from Revit
plumbing fixtures. It handles:
- MEPModel and ConnectorManager None checks
- Domain filtering (plumbing only)
- System type filtering (Sanitary, DomesticColdWater, etc.)
- Connection status filtering

The extraction works with Revit FamilyInstances that have MEP connectors
defined in their families.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging

from src.timber_framing_generator.core.mep_system import (
    MEPDomain,
    MEPConnector,
)

logger = logging.getLogger(__name__)


# Priority-ordered keyword rules for fixture type classification.
# First match wins, so more specific keywords come first.
FIXTURE_TYPE_RULES: List[Tuple[str, str]] = [
    ("water closet", "toilet"),
    ("water_closet", "toilet"),
    ("toilet", "toilet"),
    ("wc", "toilet"),
    ("urinal", "urinal"),
    ("lavatory", "sink"),
    ("sink", "sink"),
    ("basin", "sink"),
    ("vanity", "sink"),
    ("bathtub", "bathtub"),
    ("bath tub", "bathtub"),
    ("bath_tub", "bathtub"),
    ("tub", "bathtub"),
    ("shower", "shower"),
    ("floor_drain", "floor_drain"),
    ("floor drain", "floor_drain"),
    ("drain", "floor_drain"),
    ("dishwasher", "dishwasher"),
    ("washing machine", "washing_machine"),
    ("washing_machine", "washing_machine"),
    ("washer", "washing_machine"),
    ("hose_bib", "hose_bib"),
    ("hose bib", "hose_bib"),
]


def _classify_fixture_type(family_name: str) -> str:
    """Classify fixture type from Revit family name using keyword matching.

    Performs case-insensitive matching against FIXTURE_TYPE_RULES.
    First match wins (rules are priority-ordered).

    Args:
        family_name: Revit family name string.

    Returns:
        Normalized fixture type string, or "unknown" if no match.
    """
    name_lower = family_name.lower()
    for keyword, fixture_type in FIXTURE_TYPE_RULES:
        if keyword in name_lower:
            return fixture_type
    return "unknown"


def _get_fixture_info(element: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extract fixture type and family name from a Revit element.

    Traverses element.Symbol.Family.Name safely using getattr chains.
    Pattern from scripts/gh_connector_diagnostics.py.

    Args:
        element: Revit FamilyInstance.

    Returns:
        Tuple of (fixture_type, fixture_family). Both None if extraction fails.
    """
    symbol = getattr(element, 'Symbol', None)
    if symbol is None:
        return (None, None)

    family = getattr(symbol, 'Family', None)
    if family is None:
        return (None, None)

    family_name = getattr(family, 'Name', None)
    if family_name is None:
        return (None, None)

    family_name_str = str(family_name)
    fixture_type = _classify_fixture_type(family_name_str)
    return (fixture_type, family_name_str)


def extract_plumbing_connectors(
    elements: List[Any],
    filter_config: Optional[Dict[str, Any]] = None
) -> List[MEPConnector]:
    """
    Extract plumbing connectors from Revit FamilyInstances.

    This function iterates through Revit FamilyInstances and extracts
    all plumbing connectors (Domain.DomainPiping) with their position,
    direction, and system type information.

    Args:
        elements: List of Revit FamilyInstances (plumbing fixtures)
            Each element should have MEPModel property for MEP access
        filter_config: Optional filters:
            - system_types: List of PipeSystemType values to include
              (e.g., ["Sanitary", "DomesticColdWater"])
            - exclude_connected: Skip already-connected connectors (bool)

    Returns:
        List of MEPConnector objects with position, direction, and metadata

    Example:
        >>> connectors = extract_plumbing_connectors(fixtures)
        >>> for conn in connectors:
        ...     print(f"{conn.system_type}: {conn.origin}")
    """
    connectors = []

    if not elements:
        return connectors

    # Parse filter config
    system_types = None
    exclude_connected = False

    if filter_config:
        system_types = filter_config.get("system_types")
        exclude_connected = filter_config.get("exclude_connected", False)

    for element in elements:
        try:
            element_connectors = _extract_connectors_from_element(
                element,
                system_types,
                exclude_connected
            )
            connectors.extend(element_connectors)
        except Exception as e:
            # Log warning but continue processing other elements
            element_id = _get_element_id(element)
            logger.warning(f"Failed to extract connectors from element {element_id}: {e}")

    logger.info(f"Extracted {len(connectors)} plumbing connectors from {len(elements)} elements")
    return connectors


def _extract_connectors_from_element(
    element: Any,
    system_types: Optional[List[str]],
    exclude_connected: bool
) -> List[MEPConnector]:
    """
    Extract connectors from a single Revit FamilyInstance.

    Args:
        element: Revit FamilyInstance with MEP connectors
        system_types: List of system types to include (None = all)
        exclude_connected: Skip already-connected connectors

    Returns:
        List of MEPConnector objects from this element
    """
    connectors = []
    element_id = _get_element_id(element)

    # Extract fixture info once per element (shared across all connectors)
    fixture_type, fixture_family = _get_fixture_info(element)

    # Get MEPModel - may be None for non-MEP families
    mep_model = getattr(element, 'MEPModel', None)
    if mep_model is None:
        logger.debug(f"Element {element_id} has no MEPModel")
        return connectors

    # Get ConnectorManager - may be None
    conn_manager = getattr(mep_model, 'ConnectorManager', None)
    if conn_manager is None:
        logger.debug(f"Element {element_id} has no ConnectorManager")
        return connectors

    # Get Connectors collection
    connector_set = getattr(conn_manager, 'Connectors', None)
    if connector_set is None:
        logger.debug(f"Element {element_id} has no Connectors")
        return connectors

    # Iterate through connectors
    for conn in connector_set:
        try:
            mep_connector = _process_connector(
                conn,
                element_id,
                system_types,
                exclude_connected,
                fixture_type=fixture_type,
                fixture_family=fixture_family,
            )
            if mep_connector is not None:
                connectors.append(mep_connector)
        except Exception as e:
            logger.warning(f"Failed to process connector on element {element_id}: {e}")

    return connectors


def _process_connector(
    conn: Any,
    element_id: int,
    system_types: Optional[List[str]],
    exclude_connected: bool,
    fixture_type: Optional[str] = None,
    fixture_family: Optional[str] = None,
) -> Optional[MEPConnector]:
    """
    Process a single Revit connector and create MEPConnector.

    Args:
        conn: Revit Connector object
        element_id: ID of the owning element
        system_types: List of system types to include
        exclude_connected: Skip already-connected connectors
        fixture_type: Normalized fixture type from parent element
        fixture_family: Raw Revit family name from parent element

    Returns:
        MEPConnector if connector passes filters, None otherwise
    """
    # Check domain - only process plumbing connectors
    domain = getattr(conn, 'Domain', None)
    if domain is None:
        return None

    # Domain enum check - need to compare string values for cross-assembly compatibility
    domain_str = str(domain)
    if 'DomainPiping' not in domain_str and 'Piping' not in domain_str:
        return None

    # Check connection status
    if exclude_connected:
        is_connected = getattr(conn, 'IsConnected', False)
        if is_connected:
            return None

    # Get system type
    pipe_system_type = getattr(conn, 'PipeSystemType', None)
    system_type_str = str(pipe_system_type) if pipe_system_type else "Unknown"

    # Filter by system type
    if system_types:
        if system_type_str not in system_types:
            return None

    # Get position
    origin = getattr(conn, 'Origin', None)
    if origin is None:
        return None

    origin_tuple = (
        float(getattr(origin, 'X', 0)),
        float(getattr(origin, 'Y', 0)),
        float(getattr(origin, 'Z', 0))
    )

    # Get connector direction from CoordinateSystem.BasisZ
    # Note: BasisZ behavior varies by system type:
    # - Sanitary: Always (0, 0, -1) DOWN - reliable for routing
    # - Supply: Points toward pipe source - varies by fixture
    # The pipe_router module handles these differences appropriately.
    direction_tuple = _get_connector_direction(conn)

    # Get radius (for round connectors)
    radius = getattr(conn, 'Radius', None)
    if radius is not None:
        radius = float(radius)

    # Get flow direction
    flow_direction = getattr(conn, 'FlowDirection', None)
    flow_direction_str = str(flow_direction) if flow_direction else None

    # Get connector ID
    conn_id = getattr(conn, 'Id', 0)

    # Create MEPConnector
    return MEPConnector(
        id=f"{element_id}_{conn_id}",
        origin=origin_tuple,
        direction=direction_tuple,
        domain=MEPDomain.PLUMBING,
        system_type=system_type_str,
        owner_element_id=element_id,
        radius=radius,
        flow_direction=flow_direction_str,
        fixture_type=fixture_type,
        fixture_family=fixture_family,
    )


def _get_connector_direction(conn: Any) -> Tuple[float, float, float]:
    """
    Get the direction vector from a Revit connector.

    This returns the raw CoordinateSystem.BasisZ from the connector.
    The meaning varies by system type (based on empirical analysis):

    System Type Behavior:
    - **Sanitary (drains)**: BasisZ consistently points DOWN (0, 0, -1)
      regardless of fixture type. This is reliable for routing.
    - **Vent**: Similar to sanitary but pipes route UP.
    - **Supply (DomesticColdWater, DomesticHotWater)**: BasisZ points
      toward the pipe source. This varies by fixture design:
      - Upward-facing faucets: points DOWN toward supply
      - Side-connected fixtures: points horizontally

    Note: The pipe_router module handles these differences by using
    get_wall_search_direction() for wall finding and
    get_vertical_routing_direction() for vertical pipe routing.

    Args:
        conn: Revit Connector object

    Returns:
        Direction tuple (x, y, z) - raw BasisZ from connector
    """
    coord_sys = getattr(conn, 'CoordinateSystem', None)
    if coord_sys is not None:
        basis_z = getattr(coord_sys, 'BasisZ', None)
        if basis_z is not None:
            return (
                float(getattr(basis_z, 'X', 0)),
                float(getattr(basis_z, 'Y', 0)),
                float(getattr(basis_z, 'Z', 1))
            )

    # Default: up (Z+)
    return (0.0, 0.0, 1.0)


def _get_element_id(element: Any) -> int:
    """
    Get integer ID from Revit element.

    Args:
        element: Revit element (FamilyInstance, etc.)

    Returns:
        Integer element ID
    """
    element_id = getattr(element, 'Id', None)
    if element_id is not None:
        int_value = getattr(element_id, 'IntegerValue', None)
        if int_value is not None:
            return int(int_value)
    return 0


def extract_connectors_from_json(
    elements_json: List[Dict[str, Any]]
) -> List[MEPConnector]:
    """
    Create MEPConnector objects from JSON data.

    This is useful for testing or when connector data has already
    been serialized to JSON.

    Args:
        elements_json: List of connector dictionaries

    Returns:
        List of MEPConnector objects
    """
    connectors = []
    for data in elements_json:
        try:
            connector = MEPConnector.from_dict(data)
            connectors.append(connector)
        except Exception as e:
            logger.warning(f"Failed to parse connector from JSON: {e}")
    return connectors
