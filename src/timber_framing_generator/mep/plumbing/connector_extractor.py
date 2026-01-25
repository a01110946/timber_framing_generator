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
                exclude_connected
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
    exclude_connected: bool
) -> Optional[MEPConnector]:
    """
    Process a single Revit connector and create MEPConnector.

    Args:
        conn: Revit Connector object
        element_id: ID of the owning element
        system_types: List of system types to include
        exclude_connected: Skip already-connected connectors

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
    # TODO: Investigate how Revit manages connector directions for different
    # fixture types. The BasisZ may represent the family's local axis rather
    # than the physical routing direction. Different fixtures have different
    # pipe connection patterns (faucets from below, drains down, etc.).
    # For now, we store the raw BasisZ for diagnostic purposes.
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
    )


def _get_connector_direction(conn: Any) -> Tuple[float, float, float]:
    """
    Get the direction vector from a Revit connector.

    This returns the raw CoordinateSystem.BasisZ from the connector.
    The meaning of this vector may vary by fixture type and family authoring.

    TODO: Investigate what BasisZ actually represents for different fixture types:
    - Faucets: supply comes UP from below
    - Drains: pipes go DOWN (gravity)
    - Toilets: often horizontal flex connectors
    - Wall-mounted vs floor-mounted fixtures differ

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
