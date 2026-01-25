# File: src/timber_framing_generator/mep/plumbing/plumbing_system.py
"""
Plumbing system implementation.

This module implements the PlumbingSystem class which handles:
- Extraction of plumbing connectors from Revit fixtures
- Pipe routing to wall entry points and vertical connections
- Penetration generation for wall framing

This is the first MEP domain implementation, serving as a pattern
for HVAC and electrical domains.
"""

from typing import Dict, List, Any, Optional

from src.timber_framing_generator.core.mep_system import (
    MEPSystem,
    MEPDomain,
    MEPConnector,
    MEPRoute,
)


class PlumbingSystem(MEPSystem):
    """
    Plumbing-specific MEP system handler.

    Handles plumbing fixture connector extraction, pipe routing to walls,
    and penetration generation for wall framing members.

    Example:
        >>> system = PlumbingSystem()
        >>> connectors = system.extract_connectors(fixtures)
        >>> routes = system.calculate_routes(connectors, framing_data, [], config)
        >>> penetrations = system.generate_penetrations(routes, framing_elements)
    """

    @property
    def domain(self) -> MEPDomain:
        """
        Return the MEP domain this system handles.

        Returns:
            MEPDomain.PLUMBING
        """
        return MEPDomain.PLUMBING

    def extract_connectors(
        self,
        elements: List[Any],
        filter_config: Optional[Dict[str, Any]] = None
    ) -> List[MEPConnector]:
        """
        Extract plumbing connectors from Revit fixtures.

        Delegates to the connector_extractor module for actual extraction.

        Args:
            elements: List of Revit FamilyInstances (plumbing fixtures)
            filter_config: Optional filters:
                - system_types: List of system types to include
                  (e.g., ["Sanitary", "DomesticColdWater"])
                - exclude_connected: Skip already-connected connectors

        Returns:
            List of MEPConnector objects
        """
        from .connector_extractor import extract_plumbing_connectors
        return extract_plumbing_connectors(elements, filter_config)

    def calculate_routes(
        self,
        connectors: List[MEPConnector],
        framing_data: Dict[str, Any],
        target_points: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """
        Calculate pipe routes from connectors to wall entry + vertical connection.

        Routes are calculated using the following strategy:
        1. Find nearest wall to connector
        2. Calculate entry point on wall face
        3. Calculate first vertical connection inside wall

        Args:
            connectors: Source connectors from plumbing fixtures
            framing_data: Wall framing data containing wall geometry
            target_points: Not used in Phase 1 (auto-find nearest wall)
            config: Routing configuration:
                - max_search_distance: Max distance to find wall (default 10')
                - wall_thickness: Default wall thickness if not specified

        Returns:
            List of MEPRoute objects with path points and penetrations
        """
        from .pipe_router import calculate_pipe_routes
        return calculate_pipe_routes(
            connectors,
            framing_data,
            target_points,
            config
        )

    def generate_penetrations(
        self,
        routes: List[MEPRoute],
        framing_elements: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate penetration specifications for wall studs.

        For each route segment that passes through a stud, creates a
        penetration specification including size, location, and
        any required reinforcement.

        Args:
            routes: Calculated MEP routes
            framing_elements: List of framing element dictionaries

        Returns:
            List of penetration specifications:
                - id: Unique penetration ID
                - route_id: ID of route this penetration serves
                - element_id: ID of framing element to penetrate
                - location: (x, y, z) center of penetration
                - diameter: Hole diameter (pipe size + clearance)
                - is_allowed: Whether penetration meets code limits
                - warning: Description if not allowed
                - reinforcement_required: Whether reinforcement is needed
        """
        from .penetration_rules import generate_plumbing_penetrations
        return generate_plumbing_penetrations(routes, framing_elements)

    def size_elements(
        self,
        routes: List[MEPRoute],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """
        Size pipe elements based on fixture units and code.

        Note: Phase 1 uses connector radius directly. Future phases
        will implement proper sizing based on fixture unit counts.

        Args:
            routes: Routes to size
            config: Sizing configuration (not used in Phase 1)

        Returns:
            Routes with pipe_size populated
        """
        # Phase 1: Use connector radius as pipe size
        # Future: Implement fixture unit-based sizing
        return routes

    def validate_routes(
        self,
        routes: List[MEPRoute],
        framing_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Validate routes against framing and plumbing code requirements.

        Checks:
        - All routes have valid path points
        - Penetrations don't exceed member limits
        - Drain lines have proper slope (future)

        Args:
            routes: Routes to validate
            framing_data: Framing data for penetration checks

        Returns:
            List of validation issues (empty if all valid)
        """
        issues = super().validate_routes(routes, framing_data)

        # Additional plumbing-specific validation
        for route in routes:
            # Check pipe size is set
            if route.pipe_size is None or route.pipe_size <= 0:
                issues.append({
                    "route_id": route.id,
                    "issue_type": "missing_pipe_size",
                    "message": "Route has no pipe size specified"
                })

            # Check system type is valid
            valid_system_types = [
                "Sanitary", "DomesticColdWater", "DomesticHotWater",
                "Vent", "OtherPipe", "FireProtectionWet", "FireProtectionDry"
            ]
            if route.system_type not in valid_system_types:
                issues.append({
                    "route_id": route.id,
                    "issue_type": "unknown_system_type",
                    "message": f"Unknown system type: {route.system_type}"
                })

        return issues
