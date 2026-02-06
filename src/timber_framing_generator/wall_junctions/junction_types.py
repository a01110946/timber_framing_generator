# File: src/timber_framing_generator/wall_junctions/junction_types.py

"""Data models for wall junction analysis.

Defines the core types used throughout the wall junction detection,
classification, and resolution pipeline. All measurements are in feet.

Key Types:
    JunctionType: Classification of how walls meet (L-corner, T, X, etc.)
    JoinType: Resolution strategy (butt, miter)
    JunctionNode: A point where walls meet, with connections
    LayerAdjustment: Per-layer extend/trim amount at one wall end
    JunctionGraph: Complete analysis result with all adjustments
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum


# =============================================================================
# Enumerations
# =============================================================================


class JunctionType(Enum):
    """Classification of wall junction geometry."""

    FREE_END = "free_end"
    """Wall endpoint connects to nothing."""

    L_CORNER = "l_corner"
    """Two walls meeting at an angle (typically 90 degrees)."""

    T_INTERSECTION = "t_intersection"
    """One wall ending mid-span of another, or 3 walls where one pair is inline."""

    X_CROSSING = "x_crossing"
    """Two walls crossing through each other (4 connections, two inline pairs)."""

    INLINE = "inline"
    """Two collinear walls end-to-end (continuation, not a real junction)."""

    MULTI_WAY = "multi_way"
    """3+ walls meeting at one point with no clear inline pair."""


class JoinType(Enum):
    """How two walls connect at a junction."""

    BUTT = "butt"
    """One wall extends, the other trims square against it."""

    MITER = "miter"
    """Both walls are cut at the bisector angle."""

    NONE = "none"
    """Free end or inline — no join resolution needed."""


class AdjustmentType(Enum):
    """Direction of wall length adjustment at a junction."""

    EXTEND = "extend"
    """Wall endpoint moves away from wall center (wall gets longer)."""

    TRIM = "trim"
    """Wall endpoint moves toward wall center (wall gets shorter)."""

    MITER = "miter"
    """Wall is cut at an angle (used with miter joins)."""

    NONE = "none"
    """No adjustment (free end)."""


class LayerFunction(Enum):
    """Wall layer function classification (Revit/IFC convention).

    Priority order: Structure (highest) > Substrate > Thermal > Membrane > Finish (lowest).
    Higher-priority layers can extend through lower-priority layers at junctions.
    """

    STRUCTURE = "structure"
    """Priority 1 — Studs, structural sheathing, load-bearing elements."""

    SUBSTRATE = "substrate"
    """Priority 2 — Sheathing, backer board, structural panel."""

    THERMAL = "thermal"
    """Priority 3 — Insulation, air gaps, continuous insulation."""

    MEMBRANE = "membrane"
    """Priority 4 — WRB (Tyvek), vapor retarder, air barrier."""

    FINISH = "finish"
    """Priority 5 — Siding, gypsum board, stucco, paint."""


class LayerSide(Enum):
    """Which side of the core boundary a layer is on.

    Determines junction behavior: at butt joints, exterior-side layers
    follow the primary wall while interior-side layers follow the secondary wall
    (the crossed pattern).
    """

    EXTERIOR = "exterior"
    """Outside the core boundary (toward building exterior)."""

    CORE = "core"
    """The structural core itself."""

    INTERIOR = "interior"
    """Inside the core boundary (toward building interior)."""


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class WallConnection:
    """A wall's participation in a junction.

    Represents one wall endpoint (or mid-span point) at a junction node.
    Tracks which end of the wall is involved and the wall's properties.

    Attributes:
        wall_id: Unique wall identifier from walls_json.
        end: Which end of the wall is at this junction ("start" or "end").
        direction: Wall direction vector (x, y, z) from base_plane.x_axis.
        angle_at_junction: Angle in degrees relative to first connection (computed).
        wall_thickness: Total wall thickness in feet.
        wall_length: Wall length in feet.
        is_exterior: Whether the wall is an exterior wall.
        is_midspan: True if junction is at wall's mid-span (T-intersection).
        midspan_u: U-coordinate along wall where T meets (feet), if is_midspan.
    """

    wall_id: str
    end: str
    direction: Tuple[float, float, float]
    angle_at_junction: float
    wall_thickness: float
    wall_length: float
    is_exterior: bool = False
    is_midspan: bool = False
    midspan_u: Optional[float] = None


@dataclass
class JunctionNode:
    """A point where walls meet.

    Represents a graph node at a wall intersection. Contains all walls
    participating in this junction and the classified junction type.

    Attributes:
        id: Unique junction identifier.
        position: World XYZ coordinates of the junction point.
        junction_type: Classified type (L_CORNER, T_INTERSECTION, etc.).
        connections: List of wall connections at this junction.
        resolved: True after join resolution has been applied.
    """

    id: str
    position: Tuple[float, float, float]
    junction_type: JunctionType
    connections: List[WallConnection]
    resolved: bool = False


@dataclass
class WallLayerInfo:
    """Thickness breakdown for a wall's layers.

    All thicknesses in feet. The three layers (exterior, core, interior)
    should sum to total_thickness.

    Attributes:
        wall_id: Wall identifier.
        total_thickness: Overall wall thickness in feet.
        exterior_thickness: Sheathing/cladding layer thickness in feet.
        core_thickness: Structural framing layer thickness in feet.
        interior_thickness: Gypsum/finish layer thickness in feet.
        source: Where layer data came from ("default", "revit", "override").
    """

    wall_id: str
    total_thickness: float
    exterior_thickness: float
    core_thickness: float
    interior_thickness: float
    source: str = "default"


@dataclass
class WallLayer:
    """A single layer in a wall assembly.

    Attributes:
        name: Human-readable layer name (e.g., "structural_sheathing").
        function: Layer function classification.
        side: Which side of core boundary.
        thickness: Layer thickness in feet.
        material: Material name (e.g., "OSB 7/16").
        priority: Junction priority [1-100]. Higher priority layers extend
                  through lower priority layers at junctions.
        wraps_at_ends: Whether this layer wraps at free wall ends.
        wraps_at_inserts: Whether this layer wraps at openings.
    """

    name: str
    function: LayerFunction
    side: LayerSide
    thickness: float
    material: str = ""
    priority: int = 50
    wraps_at_ends: bool = False
    wraps_at_inserts: bool = False


@dataclass
class WallAssemblyDef:
    """Multi-layer wall assembly definition.

    Layers are ordered from exterior to interior (outside to inside).
    The core boundary is implicit: layers with side=CORE are the core.

    Attributes:
        name: Assembly name (e.g., "2x4_exterior").
        layers: Ordered list of layers from exterior to interior.
        source: Where this assembly came from ("default", "revit", "override").
    """

    name: str
    layers: List[WallLayer]
    source: str = "default"

    @property
    def total_thickness(self) -> float:
        """Total assembly thickness in feet."""
        return sum(layer.thickness for layer in self.layers)

    @property
    def core_thickness(self) -> float:
        """Total thickness of core layers in feet."""
        return sum(l.thickness for l in self.layers if l.side == LayerSide.CORE)

    @property
    def exterior_thickness(self) -> float:
        """Total thickness of exterior-side layers in feet."""
        return sum(l.thickness for l in self.layers if l.side == LayerSide.EXTERIOR)

    @property
    def interior_thickness(self) -> float:
        """Total thickness of interior-side layers in feet."""
        return sum(l.thickness for l in self.layers if l.side == LayerSide.INTERIOR)

    def get_layers_by_side(self, side: LayerSide) -> List["WallLayer"]:
        """Get all layers on a specific side."""
        return [l for l in self.layers if l.side == side]

    def to_legacy_layer_info(self, wall_id: str) -> "WallLayerInfo":
        """Convert to legacy 3-layer WallLayerInfo for backward compatibility."""
        return WallLayerInfo(
            wall_id=wall_id,
            total_thickness=self.total_thickness,
            exterior_thickness=self.exterior_thickness,
            core_thickness=self.core_thickness,
            interior_thickness=self.interior_thickness,
            source=self.source,
        )

    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "name": self.name,
            "source": self.source,
            "total_thickness": round(self.total_thickness, 6),
            "layers": [
                {
                    "name": l.name,
                    "function": l.function.value,
                    "side": l.side.value,
                    "thickness": round(l.thickness, 6),
                    "material": l.material,
                    "priority": l.priority,
                    "wraps_at_ends": l.wraps_at_ends,
                    "wraps_at_inserts": l.wraps_at_inserts,
                }
                for l in self.layers
            ],
        }


@dataclass
class LayerAdjustment:
    """Per-layer extension/trim at one end of one wall.

    Tells a downstream component (framing, sheathing, finishes) exactly
    how much to extend or trim a specific layer at a specific wall end.

    Attributes:
        wall_id: Wall to adjust.
        end: Which end ("start" or "end").
        junction_id: Junction this adjustment belongs to.
        layer_name: Which layer ("core", "exterior", "interior").
        adjustment_type: EXTEND, TRIM, or MITER.
        amount: Distance in feet (always positive).
        miter_angle: Angle in degrees for miter joins.
        connecting_wall_id: The other wall at this junction.
    """

    wall_id: str
    end: str
    junction_id: str
    layer_name: str
    adjustment_type: AdjustmentType
    amount: float
    miter_angle: Optional[float] = None
    connecting_wall_id: str = ""


@dataclass
class JunctionResolution:
    """Resolved join strategy for a pair of walls at a junction.

    Attributes:
        junction_id: Junction this resolution applies to.
        join_type: BUTT or MITER.
        primary_wall_id: Wall that extends (butt) or reference wall (miter).
        secondary_wall_id: Wall that trims (butt) or other wall (miter).
        confidence: 0.0-1.0, auto-detection confidence.
        reason: Human-readable explanation of the resolution.
        layer_adjustments: Per-layer adjustments for both walls.
        is_user_override: True if user specified this resolution.
    """

    junction_id: str
    join_type: JoinType
    primary_wall_id: str
    secondary_wall_id: str
    confidence: float
    reason: str
    layer_adjustments: List[LayerAdjustment] = field(default_factory=list)
    is_user_override: bool = False


@dataclass
class JunctionGraph:
    """Complete wall junction graph with resolutions.

    The main output of the junction analysis pipeline. Contains the graph
    topology, layer info, resolutions, and a convenient per-wall lookup
    of adjustments.

    Attributes:
        nodes: Junction nodes keyed by junction_id.
        wall_layers: Layer info keyed by wall_id.
        resolutions: All resolved junctions.
        wall_adjustments: Per-wall adjustment lookup (wall_id -> list).
    """

    nodes: Dict[str, JunctionNode] = field(default_factory=dict)
    wall_layers: Dict[str, WallLayerInfo] = field(default_factory=dict)
    resolutions: List[JunctionResolution] = field(default_factory=list)
    wall_adjustments: Dict[str, List[LayerAdjustment]] = field(default_factory=dict)

    def get_adjustments_for_wall(self, wall_id: str) -> List[LayerAdjustment]:
        """Get all layer adjustments for a specific wall."""
        return self.wall_adjustments.get(wall_id, [])

    def get_adjustments_for_wall_end(
        self, wall_id: str, end: str
    ) -> List[LayerAdjustment]:
        """Get layer adjustments for a specific wall end."""
        return [
            adj
            for adj in self.wall_adjustments.get(wall_id, [])
            if adj.end == end
        ]

    def get_adjustment_for_layer(
        self, wall_id: str, end: str, layer_name: str
    ) -> Optional[LayerAdjustment]:
        """Get the adjustment for a specific wall/end/layer combination."""
        for adj in self.wall_adjustments.get(wall_id, []):
            if adj.end == end and adj.layer_name == layer_name:
                return adj
        return None

    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "version": "1.0",
            "junction_count": len(self.nodes),
            "junctions": [
                _serialize_node(node) for node in self.nodes.values()
            ],
            "wall_adjustments": {
                wall_id: [_serialize_adjustment(adj) for adj in adjs]
                for wall_id, adjs in self.wall_adjustments.items()
            },
            "summary": self._build_summary(),
        }

    def _build_summary(self) -> Dict:
        """Build summary statistics."""
        type_counts = {}
        for node in self.nodes.values():
            key = node.junction_type.value
            type_counts[key] = type_counts.get(key, 0) + 1

        override_count = sum(
            1 for r in self.resolutions if r.is_user_override
        )

        return {
            "l_corners": type_counts.get("l_corner", 0),
            "t_intersections": type_counts.get("t_intersection", 0),
            "x_crossings": type_counts.get("x_crossing", 0),
            "free_ends": type_counts.get("free_end", 0),
            "inline": type_counts.get("inline", 0),
            "multi_way": type_counts.get("multi_way", 0),
            "total_junctions": len(self.nodes),
            "total_resolutions": len(self.resolutions),
            "user_overrides_applied": override_count,
        }


# =============================================================================
# Serialization Helpers
# =============================================================================


def _serialize_node(node: JunctionNode) -> Dict:
    """Serialize a JunctionNode to a dictionary."""
    resolution_data = None
    # Find resolution for this node (if any)
    # Resolution is attached during graph building, not here

    return {
        "id": node.id,
        "position": {
            "x": node.position[0],
            "y": node.position[1],
            "z": node.position[2],
        },
        "junction_type": node.junction_type.value,
        "connections": [
            {
                "wall_id": c.wall_id,
                "end": c.end,
                "is_midspan": c.is_midspan,
                "midspan_u": c.midspan_u,
                "wall_thickness": c.wall_thickness,
                "is_exterior": c.is_exterior,
            }
            for c in node.connections
        ],
    }


def _serialize_adjustment(adj: LayerAdjustment) -> Dict:
    """Serialize a LayerAdjustment to a dictionary."""
    result = {
        "end": adj.end,
        "junction_id": adj.junction_id,
        "layer_name": adj.layer_name,
        "adjustment_type": adj.adjustment_type.value,
        "amount": round(adj.amount, 6),
        "connecting_wall_id": adj.connecting_wall_id,
    }
    if adj.miter_angle is not None:
        result["miter_angle"] = round(adj.miter_angle, 2)
    return result
