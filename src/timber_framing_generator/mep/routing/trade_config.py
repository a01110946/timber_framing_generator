# File: src/timber_framing_generator/mep/routing/trade_config.py
"""
Trade configuration for MEP routing.

Defines trade priorities, system mappings, and clearance requirements
for sequential multi-trade routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum


class Trade(Enum):
    """MEP trade categories."""
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
    FIRE_PROTECTION = "fire_protection"


# Default trade routing order (most constrained first)
DEFAULT_TRADE_ORDER = [
    Trade.PLUMBING,
    Trade.HVAC,
    Trade.FIRE_PROTECTION,
    Trade.ELECTRICAL,
]

# Default mapping of system types to trades
DEFAULT_TRADE_SYSTEMS: Dict[Trade, List[str]] = {
    Trade.PLUMBING: [
        "sanitary_drain",
        "sanitary_vent",
        "domestic_hot_water",
        "domestic_cold_water",
        "dhw",
        "dcw",
        "sanitary",
        "vent",
        "storm_drain",
    ],
    Trade.HVAC: [
        "supply_air",
        "return_air",
        "exhaust_air",
        "outside_air",
        "refrigerant",
        "condensate",
    ],
    Trade.FIRE_PROTECTION: [
        "fire_sprinkler",
        "fire_standpipe",
    ],
    Trade.ELECTRICAL: [
        "power",
        "lighting",
        "data",
        "low_voltage",
        "audio",
        "security",
        "controls",
    ],
}

# Default clearances between trades (in feet)
DEFAULT_CLEARANCES: Dict[Trade, float] = {
    Trade.PLUMBING: 0.25,       # 3" minimum
    Trade.HVAC: 0.5,            # 6" minimum
    Trade.FIRE_PROTECTION: 0.167,  # 2" minimum
    Trade.ELECTRICAL: 0.125,    # 1.5" minimum
}


@dataclass
class TradeConfig:
    """
    Configuration for trade prioritization and routing.

    Attributes:
        trade_order: List of trades in routing priority (first = highest)
        trade_systems: Mapping from trade to system type names
        clearances: Minimum clearances between trades (feet)
        enabled_trades: Set of trades to include in routing
    """
    trade_order: List[Trade] = field(default_factory=lambda: list(DEFAULT_TRADE_ORDER))
    trade_systems: Dict[Trade, List[str]] = field(
        default_factory=lambda: dict(DEFAULT_TRADE_SYSTEMS)
    )
    clearances: Dict[Trade, float] = field(
        default_factory=lambda: dict(DEFAULT_CLEARANCES)
    )
    enabled_trades: Optional[Set[Trade]] = None

    def get_trade_for_system(self, system_type: str) -> Optional[Trade]:
        """
        Get the trade that owns a system type.

        Args:
            system_type: System type name (e.g., "sanitary_drain")

        Returns:
            Trade enum value or None if not found
        """
        system_lower = system_type.lower()
        for trade, systems in self.trade_systems.items():
            if system_lower in [s.lower() for s in systems]:
                return trade
        return None

    def get_systems_for_trade(self, trade: Trade) -> List[str]:
        """
        Get all system types for a trade.

        Args:
            trade: Trade enum value

        Returns:
            List of system type names
        """
        return self.trade_systems.get(trade, [])

    def get_clearance(self, trade: Trade) -> float:
        """
        Get minimum clearance for a trade.

        Args:
            trade: Trade enum value

        Returns:
            Clearance in feet
        """
        return self.clearances.get(trade, 0.125)  # Default 1.5"

    def get_priority(self, trade: Trade) -> int:
        """
        Get routing priority for a trade (lower = higher priority).

        Args:
            trade: Trade enum value

        Returns:
            Priority index (0 = highest)
        """
        try:
            return self.trade_order.index(trade)
        except ValueError:
            return len(self.trade_order)  # Unknown trades last

    def get_enabled_trades(self) -> List[Trade]:
        """
        Get trades that are enabled for routing, in priority order.

        Returns:
            List of enabled trades
        """
        if self.enabled_trades is None:
            return self.trade_order
        return [t for t in self.trade_order if t in self.enabled_trades]

    def is_trade_enabled(self, trade: Trade) -> bool:
        """Check if a trade is enabled for routing."""
        if self.enabled_trades is None:
            return True
        return trade in self.enabled_trades

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "trade_order": [t.value for t in self.trade_order],
            "trade_systems": {
                t.value: systems for t, systems in self.trade_systems.items()
            },
            "clearances": {t.value: c for t, c in self.clearances.items()},
            "enabled_trades": (
                [t.value for t in self.enabled_trades]
                if self.enabled_trades else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TradeConfig':
        """Create from dictionary."""
        trade_order = [Trade(t) for t in data.get("trade_order", [])]
        trade_systems = {
            Trade(k): v for k, v in data.get("trade_systems", {}).items()
        }
        clearances = {
            Trade(k): v for k, v in data.get("clearances", {}).items()
        }
        enabled_raw = data.get("enabled_trades")
        enabled_trades = (
            {Trade(t) for t in enabled_raw} if enabled_raw else None
        )

        return cls(
            trade_order=trade_order or list(DEFAULT_TRADE_ORDER),
            trade_systems=trade_systems or dict(DEFAULT_TRADE_SYSTEMS),
            clearances=clearances or dict(DEFAULT_CLEARANCES),
            enabled_trades=enabled_trades,
        )


@dataclass
class RoutingZone:
    """
    A routing zone representing a bounded region.

    Attributes:
        id: Unique zone identifier
        name: Human-readable name
        level: Floor/level number
        bounds: (min_x, max_x, min_y, max_y) in world coordinates
        wall_ids: IDs of walls in this zone
        connector_ids: IDs of connectors in this zone
    """
    id: str
    name: str = ""
    level: int = 0
    bounds: tuple = (0.0, 0.0, 0.0, 0.0)  # min_x, max_x, min_y, max_y
    wall_ids: List[str] = field(default_factory=list)
    connector_ids: List[str] = field(default_factory=list)

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within zone bounds."""
        min_x, max_x, min_y, max_y = self.bounds
        return min_x <= x <= max_x and min_y <= y <= max_y

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "bounds": list(self.bounds),
            "wall_ids": self.wall_ids,
            "connector_ids": self.connector_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'RoutingZone':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            level=data.get("level", 0),
            bounds=tuple(data.get("bounds", (0, 0, 0, 0))),
            wall_ids=data.get("wall_ids", []),
            connector_ids=data.get("connector_ids", []),
        )


def create_default_trade_config() -> TradeConfig:
    """Create a TradeConfig with default settings."""
    return TradeConfig()


def create_plumbing_only_config() -> TradeConfig:
    """Create a TradeConfig for plumbing-only routing."""
    return TradeConfig(enabled_trades={Trade.PLUMBING})


def create_electrical_only_config() -> TradeConfig:
    """Create a TradeConfig for electrical-only routing."""
    return TradeConfig(enabled_trades={Trade.ELECTRICAL})
