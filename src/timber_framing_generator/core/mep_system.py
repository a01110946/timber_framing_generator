# File: src/timber_framing_generator/core/mep_system.py
"""
MEP (Mechanical, Electrical, Plumbing) system abstractions.

This module defines the core types and interfaces for MEP integration:
- MEPDomain: Enum for MEP system domains (plumbing, HVAC, electrical)
- MEPConnector: Data class for connector information extracted from Revit
- MEPRoute: Data class for calculated MEP routes through framing
- MEPSystem: Abstract base class for domain-specific MEP handlers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Tuple, Optional


class MEPDomain(Enum):
    """
    MEP system domains.

    Each domain has specific:
    - Connector types and properties
    - Routing rules and constraints
    - Penetration requirements
    - Code compliance considerations

    Attributes:
        PLUMBING: Water supply, drainage, venting systems
        HVAC: Heating, ventilation, air conditioning systems
        ELECTRICAL: Power distribution, low voltage systems
    """
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"

    def __str__(self) -> str:
        """Return the string value for display."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "MEPDomain":
        """
        Create MEPDomain from string value.

        Args:
            value: String value (e.g., "plumbing", "hvac")

        Returns:
            Corresponding MEPDomain enum member

        Raises:
            ValueError: If value doesn't match any domain
        """
        value_lower = value.lower()
        for member in cls:
            if member.value == value_lower:
                return member
        raise ValueError(
            f"Unknown MEP domain: {value}. "
            f"Valid domains: {[m.value for m in cls]}"
        )


@dataclass
class MEPConnector:
    """
    Represents an MEP connector extracted from a Revit element.

    Connectors are the connection points on plumbing fixtures, mechanical
    equipment, and electrical devices. They define where MEP elements
    (pipes, ducts, conduits) can connect.

    Attributes:
        id: Unique identifier for this connector
        origin: (x, y, z) position in model coordinates (feet)
        direction: (x, y, z) unit vector pointing outward from connector
        domain: MEP domain (plumbing, hvac, electrical)
        system_type: Specific system type (e.g., "Sanitary", "DomesticColdWater")
        owner_element_id: Revit ElementId of the owning element
        radius: Connector radius in feet (for round connectors)
        flow_direction: Flow direction ("In", "Out", "Bidirectional")
        width: Connector width in feet (for rectangular connectors)
        height: Connector height in feet (for rectangular connectors)
        fixture_type: Normalized fixture type ("toilet", "sink", "bathtub",
            "shower", "floor_drain", "unknown", or None if not classified)
        fixture_family: Raw Revit family name for debugging/diagnostics
    """
    id: str
    origin: Tuple[float, float, float]
    direction: Tuple[float, float, float]
    domain: MEPDomain
    system_type: str
    owner_element_id: int
    radius: Optional[float] = None
    flow_direction: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None
    fixture_type: Optional[str] = None
    fixture_family: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the connector
        """
        result = {
            "id": self.id,
            "origin": {
                "x": self.origin[0],
                "y": self.origin[1],
                "z": self.origin[2]
            },
            "direction": {
                "x": self.direction[0],
                "y": self.direction[1],
                "z": self.direction[2]
            },
            "domain": self.domain.value,
            "system_type": self.system_type,
            "owner_element_id": self.owner_element_id,
            "radius": self.radius,
            "flow_direction": self.flow_direction,
            "width": self.width,
            "height": self.height,
        }
        if self.fixture_type is not None:
            result["fixture_type"] = self.fixture_type
        if self.fixture_family is not None:
            result["fixture_family"] = self.fixture_family
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MEPConnector":
        """
        Create MEPConnector from dictionary.

        Args:
            data: Dictionary with connector data

        Returns:
            MEPConnector instance
        """
        origin = data.get("origin", {})
        direction = data.get("direction", {})

        return cls(
            id=data["id"],
            origin=(origin.get("x", 0), origin.get("y", 0), origin.get("z", 0)),
            direction=(direction.get("x", 0), direction.get("y", 0), direction.get("z", 1)),
            domain=MEPDomain.from_string(data["domain"]),
            system_type=data["system_type"],
            owner_element_id=data["owner_element_id"],
            radius=data.get("radius"),
            flow_direction=data.get("flow_direction"),
            width=data.get("width"),
            height=data.get("height"),
            fixture_type=data.get("fixture_type"),
            fixture_family=data.get("fixture_family"),
        )


@dataclass
class MEPRoute:
    """
    Represents a calculated route for MEP elements.

    Routes define the path from a connector to a target point (wall entry,
    vertical connection, main line, etc.). They include sizing information
    and can be used to generate penetrations in framing members.

    Attributes:
        id: Unique identifier for this route
        domain: MEP domain (plumbing, hvac, electrical)
        system_type: Specific system type
        path_points: List of (x, y, z) points defining the route path
        start_connector_id: ID of the starting connector
        end_point_type: Type of endpoint ("wall_entry", "vertical_connection", etc.)
        pipe_size: Pipe/duct/conduit size in feet (diameter or width)
        end_point: Optional (x, y, z) of the route endpoint
        penetrations: List of penetration locations along the route
    """
    id: str
    domain: MEPDomain
    system_type: str
    path_points: List[Tuple[float, float, float]]
    start_connector_id: str
    end_point_type: str
    pipe_size: Optional[float] = None
    end_point: Optional[Tuple[float, float, float]] = None
    penetrations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the route
        """
        result = {
            "id": self.id,
            "domain": self.domain.value,
            "system_type": self.system_type,
            "path_points": [
                {"x": p[0], "y": p[1], "z": p[2]}
                for p in self.path_points
            ],
            "start_connector_id": self.start_connector_id,
            "end_point_type": self.end_point_type,
            "pipe_size": self.pipe_size,
            "penetrations": self.penetrations,
        }
        if self.end_point:
            result["end_point"] = {
                "x": self.end_point[0],
                "y": self.end_point[1],
                "z": self.end_point[2]
            }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MEPRoute":
        """
        Create MEPRoute from dictionary.

        Args:
            data: Dictionary with route data

        Returns:
            MEPRoute instance
        """
        path_points = [
            (p["x"], p["y"], p["z"])
            for p in data.get("path_points", [])
        ]

        end_point = None
        if "end_point" in data and data["end_point"]:
            ep = data["end_point"]
            end_point = (ep["x"], ep["y"], ep["z"])

        return cls(
            id=data["id"],
            domain=MEPDomain.from_string(data["domain"]),
            system_type=data["system_type"],
            path_points=path_points,
            start_connector_id=data["start_connector_id"],
            end_point_type=data["end_point_type"],
            pipe_size=data.get("pipe_size"),
            end_point=end_point,
            penetrations=data.get("penetrations", []),
        )

    def get_length(self) -> float:
        """
        Calculate total route length.

        Returns:
            Total length in feet
        """
        if len(self.path_points) < 2:
            return 0.0

        total = 0.0
        for i in range(len(self.path_points) - 1):
            p1 = self.path_points[i]
            p2 = self.path_points[i + 1]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dz = p2[2] - p1[2]
            total += (dx**2 + dy**2 + dz**2) ** 0.5

        return total


class MEPSystem(ABC):
    """
    Abstract base class for MEP system handlers.

    Each MEP domain (plumbing, HVAC, electrical) implements this interface
    with domain-specific logic for:
    - Extracting connectors from Revit elements
    - Calculating routes through framing
    - Sizing elements per code requirements
    - Generating penetration specifications

    Example:
        >>> class PlumbingSystem(MEPSystem):
        ...     @property
        ...     def domain(self) -> MEPDomain:
        ...         return MEPDomain.PLUMBING
        ...
        ...     def extract_connectors(self, elements, filter_config=None):
        ...         # Plumbing-specific extraction logic
        ...         pass
    """

    @property
    @abstractmethod
    def domain(self) -> MEPDomain:
        """
        Return the MEP domain this system handles.

        Returns:
            MEPDomain enum value
        """
        pass

    @abstractmethod
    def extract_connectors(
        self,
        elements: List[Any],
        filter_config: Optional[Dict[str, Any]] = None
    ) -> List[MEPConnector]:
        """
        Extract MEP connectors from Revit elements.

        Args:
            elements: List of Revit FamilyInstances (fixtures, equipment)
            filter_config: Optional filters:
                - system_types: List of system types to include
                - exclude_connected: Whether to exclude already-connected connectors

        Returns:
            List of MEPConnector objects
        """
        pass

    @abstractmethod
    def calculate_routes(
        self,
        connectors: List[MEPConnector],
        framing_data: Dict[str, Any],
        target_points: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """
        Calculate routes from connectors through framing.

        Args:
            connectors: Source connectors to route from
            framing_data: Generated framing data (for avoidance/penetration)
            target_points: Destination points with type and location:
                - type: "wall_entry", "vertical_connection", "main_line"
                - location: (x, y, z) tuple
            config: Routing configuration:
                - min_slope: Minimum slope for gravity drainage
                - max_penetration_ratio: Max hole size as ratio of member depth
                - prefer_vertical: Whether to prefer vertical runs

        Returns:
            List of calculated MEPRoute objects
        """
        pass

    @abstractmethod
    def generate_penetrations(
        self,
        routes: List[MEPRoute],
        framing_elements: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate penetration data for framing members.

        Args:
            routes: Calculated MEP routes
            framing_elements: Framing elements that routes pass through

        Returns:
            List of penetration specifications:
                - element_id: ID of framing element to penetrate
                - location: (x, y, z) center of penetration
                - diameter: Hole diameter (pipe size + clearance)
                - route_id: ID of route this penetration serves
                - reinforcement_required: Whether reinforcement is needed
        """
        pass

    def size_elements(
        self,
        routes: List[MEPRoute],
        config: Dict[str, Any]
    ) -> List[MEPRoute]:
        """
        Size MEP elements based on code and flow requirements.

        This method has a default implementation that passes routes through
        unchanged. Subclasses can override for domain-specific sizing logic.

        Args:
            routes: Routes to size
            config: Sizing configuration (code requirements, fixture units, etc.)

        Returns:
            Routes with sizing information populated
        """
        # Default implementation - subclasses should override for sizing
        return routes

    def validate_routes(
        self,
        routes: List[MEPRoute],
        framing_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Validate routes against framing and code requirements.

        This method checks routes for:
        - Penetration size limits
        - Required clearances
        - Slope requirements (for gravity systems)

        Args:
            routes: Routes to validate
            framing_data: Framing data for penetration checks

        Returns:
            List of validation issues (empty if all valid):
                - route_id: ID of problematic route
                - issue_type: Type of issue
                - message: Description of the issue
        """
        # Default implementation - basic validation
        issues = []
        for route in routes:
            if len(route.path_points) < 2:
                issues.append({
                    "route_id": route.id,
                    "issue_type": "invalid_path",
                    "message": "Route must have at least 2 path points"
                })
        return issues
