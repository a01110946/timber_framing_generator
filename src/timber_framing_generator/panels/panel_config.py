# File: src/timber_framing_generator/panels/panel_config.py
"""
Panel configuration for wall panelization.

This module defines configuration parameters for the panelization system,
including size constraints, joint rules, corner handling, and transport limits.

Industry Standards Referenced:
    - GA-216: Gypsum board joint placement (12" from openings)
    - APA E30: Wall construction guide (1/2" minimum bearing)
    - IRC Wall Bracing: 48" minimum braced wall panel length

Example:
    >>> config = PanelConfig(
    ...     max_panel_length=24.0,
    ...     min_joint_to_opening=1.0,
    ...     corner_priority=CornerPriority.LONGER_WALL
    ... )
    >>> print(config.stud_spacing)  # 1.333 feet (16" OC)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class CornerPriority(Enum):
    """Strategy for determining which wall extends at corners.

    When two walls meet at a corner, one must extend to cover the
    other's thickness. This enum determines how that decision is made.

    Attributes:
        LONGER_WALL: Longer wall extends, shorter wall recedes
        SPECIFIED: User explicitly specifies which wall extends
        ALTERNATE: Alternating pattern for visual consistency
    """
    LONGER_WALL = "longer_wall"
    SPECIFIED = "specified"
    ALTERNATE = "alternate"


@dataclass
class ExclusionZone:
    """Region where panel joints are not allowed.

    Exclusion zones prevent joints from being placed near structural
    or architectural features that require continuity.

    Attributes:
        u_start: Start position along wall (U coordinate, feet)
        u_end: End position along wall (U coordinate, feet)
        zone_type: Type of exclusion ("opening", "corner", "shear_panel")
        element_id: Optional ID of the element creating this zone
    """
    u_start: float
    u_end: float
    zone_type: str
    element_id: Optional[str] = None

    def __post_init__(self):
        """Validate zone bounds."""
        if self.u_end < self.u_start:
            raise ValueError(
                f"ExclusionZone u_end ({self.u_end}) must be >= u_start ({self.u_start})"
            )

    @property
    def width(self) -> float:
        """Width of the exclusion zone in feet."""
        return self.u_end - self.u_start

    def contains(self, u: float) -> bool:
        """Check if a U coordinate is within this exclusion zone.

        Args:
            u: U coordinate to check (feet)

        Returns:
            True if u is within [u_start, u_end]
        """
        return self.u_start <= u <= self.u_end

    def overlaps(self, other: "ExclusionZone") -> bool:
        """Check if this zone overlaps with another.

        Args:
            other: Another ExclusionZone to check

        Returns:
            True if zones overlap
        """
        return self.u_start <= other.u_end and other.u_start <= self.u_end


@dataclass
class PanelConfig:
    """Configuration for wall panelization.

    This dataclass contains all parameters needed to control panel
    decomposition, including size limits, joint rules, and transport
    constraints.

    Attributes:
        max_panel_length: Maximum panel length in feet (default 24.0)
        min_panel_length: Minimum panel length in feet (default 4.0)
        max_panel_height: Maximum panel height in feet (default 12.0)
        min_joint_to_opening: Minimum distance from joint to opening edge (feet)
        min_joint_to_corner: Minimum distance from joint to wall corner (feet)
        min_joint_to_shear: Minimum distance from joint to shear panel (feet)
        corner_priority: Strategy for corner handling
        max_transport_length: Maximum length for transport (feet)
        max_transport_weight: Maximum weight for transport (lbs)
        stud_spacing: Stud spacing for joint alignment (feet)
        snap_to_studs: Whether to snap joints to stud locations
        weight_per_sqft: Estimated panel weight per square foot (lbs)

    Example:
        >>> config = PanelConfig(max_panel_length=20.0)
        >>> config.validate()  # Raises ValueError if invalid
    """
    # Size constraints
    max_panel_length: float = 24.0  # feet (typical manufacturing limit)
    min_panel_length: float = 4.0   # feet (minimum practical size)
    max_panel_height: float = 12.0  # feet (single-story typical)

    # Joint rules (distances in feet)
    min_joint_to_opening: float = 1.0   # 12" from opening edges (GA-216)
    min_joint_to_corner: float = 2.0    # 24" from wall corners
    min_joint_to_shear: float = 0.0     # Joints allowed at shear panel edges

    # Corner handling
    corner_priority: CornerPriority = field(
        default_factory=lambda: CornerPriority.LONGER_WALL
    )

    # Transport constraints
    max_transport_length: float = 40.0   # feet (standard flatbed)
    max_transport_weight: float = 10000.0  # lbs (crane/forklift limit)

    # Stud alignment
    stud_spacing: float = 1.333  # 16" OC in feet (16/12 = 1.333)
    snap_to_studs: bool = True

    # Weight estimation
    weight_per_sqft: float = 5.0  # lbs/sqft (rough estimate for framed wall)

    def __post_init__(self):
        """Convert corner_priority string to enum if needed."""
        if isinstance(self.corner_priority, str):
            self.corner_priority = CornerPriority(self.corner_priority)

    def validate(self) -> List[str]:
        """Validate configuration parameters.

        Returns:
            List of validation error messages (empty if valid)

        Raises:
            ValueError: If any validation fails
        """
        errors = []

        # Size constraint validation
        if self.max_panel_length <= 0:
            errors.append("max_panel_length must be positive")
        if self.min_panel_length <= 0:
            errors.append("min_panel_length must be positive")
        if self.min_panel_length > self.max_panel_length:
            errors.append(
                f"min_panel_length ({self.min_panel_length}) cannot exceed "
                f"max_panel_length ({self.max_panel_length})"
            )
        if self.max_panel_height <= 0:
            errors.append("max_panel_height must be positive")

        # Transport constraint validation
        if self.max_transport_length < self.max_panel_length:
            errors.append(
                f"max_transport_length ({self.max_transport_length}) cannot be "
                f"less than max_panel_length ({self.max_panel_length})"
            )
        if self.max_transport_weight <= 0:
            errors.append("max_transport_weight must be positive")

        # Joint rule validation
        if self.min_joint_to_opening < 0:
            errors.append("min_joint_to_opening cannot be negative")
        if self.min_joint_to_corner < 0:
            errors.append("min_joint_to_corner cannot be negative")
        if self.min_joint_to_shear < 0:
            errors.append("min_joint_to_shear cannot be negative")

        # Stud spacing validation
        if self.stud_spacing <= 0:
            errors.append("stud_spacing must be positive")

        if errors:
            raise ValueError("PanelConfig validation failed:\n" + "\n".join(errors))

        return errors

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization.

        Returns:
            Dictionary representation of config
        """
        return {
            "max_panel_length": self.max_panel_length,
            "min_panel_length": self.min_panel_length,
            "max_panel_height": self.max_panel_height,
            "min_joint_to_opening": self.min_joint_to_opening,
            "min_joint_to_corner": self.min_joint_to_corner,
            "min_joint_to_shear": self.min_joint_to_shear,
            "corner_priority": self.corner_priority.value,
            "max_transport_length": self.max_transport_length,
            "max_transport_weight": self.max_transport_weight,
            "stud_spacing": self.stud_spacing,
            "snap_to_studs": self.snap_to_studs,
            "weight_per_sqft": self.weight_per_sqft,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PanelConfig":
        """Create config from dictionary.

        Args:
            data: Dictionary with config parameters

        Returns:
            PanelConfig instance
        """
        return cls(
            max_panel_length=data.get("max_panel_length", 24.0),
            min_panel_length=data.get("min_panel_length", 4.0),
            max_panel_height=data.get("max_panel_height", 12.0),
            min_joint_to_opening=data.get("min_joint_to_opening", 1.0),
            min_joint_to_corner=data.get("min_joint_to_corner", 2.0),
            min_joint_to_shear=data.get("min_joint_to_shear", 0.0),
            corner_priority=CornerPriority(
                data.get("corner_priority", "longer_wall")
            ),
            max_transport_length=data.get("max_transport_length", 40.0),
            max_transport_weight=data.get("max_transport_weight", 10000.0),
            stud_spacing=data.get("stud_spacing", 1.333),
            snap_to_studs=data.get("snap_to_studs", True),
            weight_per_sqft=data.get("weight_per_sqft", 5.0),
        )

    @classmethod
    def for_24_oc(cls) -> "PanelConfig":
        """Create config for 24" on-center stud spacing.

        Returns:
            PanelConfig with 24" OC stud spacing
        """
        return cls(stud_spacing=2.0)  # 24" = 2 feet

    @classmethod
    def for_residential(cls) -> "PanelConfig":
        """Create config with typical residential defaults.

        Returns:
            PanelConfig for residential construction
        """
        return cls(
            max_panel_length=24.0,
            min_panel_length=4.0,
            max_panel_height=10.0,  # Standard 8-9 ft ceilings
            stud_spacing=1.333,     # 16" OC
        )

    @classmethod
    def for_commercial(cls) -> "PanelConfig":
        """Create config with typical commercial defaults.

        Returns:
            PanelConfig for commercial construction
        """
        return cls(
            max_panel_length=32.0,  # Larger manufacturing capacity
            min_panel_length=4.0,
            max_panel_height=14.0,  # Taller ceilings
            stud_spacing=1.333,     # 16" OC for load-bearing
        )
