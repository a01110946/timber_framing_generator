# File: src/timber_framing_generator/sheathing/sheathing_generator.py
"""
Sheathing panel generation for wall framing.

Generates sheathing panels (plywood, OSB, gypsum) for walls with proper
layout, joint staggering, and opening cutouts.

Usage:
    from src.timber_framing_generator.sheathing import SheathingGenerator

    generator = SheathingGenerator(wall_data, config)
    panels = generator.generate_sheathing()
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from .sheathing_profiles import (
    SheathingMaterial,
    SheathingType,
    PanelSize,
    get_sheathing_material,
    get_panel_size,
    PANEL_SIZES,
)


@dataclass
class Cutout:
    """
    Represents a cutout in a sheathing panel for an opening.

    Attributes:
        opening_type: Type of opening (window, door)
        u_start: Start position along wall (feet)
        u_end: End position along wall (feet)
        v_start: Bottom position (feet)
        v_end: Top position (feet)
    """
    opening_type: str
    u_start: float
    u_end: float
    v_start: float
    v_end: float

    @property
    def width(self) -> float:
        return self.u_end - self.u_start

    @property
    def height(self) -> float:
        return self.v_end - self.v_start


@dataclass
class SheathingPanel:
    """
    Represents a single sheathing panel.

    Attributes:
        id: Unique panel identifier
        wall_id: Parent wall ID
        panel_id: Parent framing panel ID (if panelized)
        face: Which face of wall ("exterior" or "interior")
        material: Sheathing material specification
        u_start: Start position along wall (feet)
        u_end: End position along wall (feet)
        v_start: Bottom position (feet)
        v_end: Top position (feet)
        row: Row number (0 = bottom)
        column: Column number (0 = left)
        is_full_sheet: Whether this is an uncut full sheet
        cutouts: List of cutouts for openings
        stagger_offset: Offset from base alignment (feet)
    """
    id: str
    wall_id: str
    panel_id: Optional[str]
    face: str
    material: SheathingMaterial
    u_start: float
    u_end: float
    v_start: float
    v_end: float
    row: int
    column: int
    is_full_sheet: bool = True
    cutouts: List[Cutout] = field(default_factory=list)
    stagger_offset: float = 0.0

    @property
    def width(self) -> float:
        return self.u_end - self.u_start

    @property
    def height(self) -> float:
        return self.v_end - self.v_start

    @property
    def area_gross(self) -> float:
        """Gross area before cutouts (sq ft)."""
        return self.width * self.height

    @property
    def area_cutouts(self) -> float:
        """Total area of cutouts (sq ft)."""
        return sum(c.width * c.height for c in self.cutouts)

    @property
    def area_net(self) -> float:
        """Net area after cutouts (sq ft)."""
        return self.area_gross - self.area_cutouts

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "wall_id": self.wall_id,
            "panel_id": self.panel_id,
            "face": self.face,
            "material": self.material.name,
            "material_display": self.material.display_name,
            "thickness_inches": self.material.thickness_inches,
            "u_start": self.u_start,
            "u_end": self.u_end,
            "v_start": self.v_start,
            "v_end": self.v_end,
            "width": self.width,
            "height": self.height,
            "row": self.row,
            "column": self.column,
            "is_full_sheet": self.is_full_sheet,
            "area_gross_sqft": self.area_gross,
            "area_net_sqft": self.area_net,
            "cutouts": [
                {
                    "type": c.opening_type,
                    "u_start": c.u_start,
                    "u_end": c.u_end,
                    "v_start": c.v_start,
                    "v_end": c.v_end,
                }
                for c in self.cutouts
            ],
        }


def _sanitize_layer_name(name: str) -> str:
    """Sanitize a layer name for use in panel IDs.

    Converts to lowercase, replaces spaces/special chars with underscores,
    and collapses consecutive underscores.

    Args:
        name: Raw layer name (e.g., "Fiber Cement Siding", "OSB 7/16").

    Returns:
        Sanitized name suitable for IDs (e.g., "fiber_cement_siding", "osb_7_16").
    """
    import re
    sanitized = name.lower().strip()
    sanitized = re.sub(r'[^a-z0-9]+', '_', sanitized)
    sanitized = sanitized.strip('_')
    return sanitized


class SheathingGenerator:
    """
    Generates sheathing panels for a wall or wall panel.

    The generator lays out standard-width panels (typically 4') across the
    wall face, staggering vertical joints between rows for structural
    integrity. Openings are handled by creating cutouts in intersecting panels.

    Attributes:
        wall_data: Wall geometry and opening data
        config: Configuration options

    Example:
        >>> generator = SheathingGenerator(wall_data, config)
        >>> panels = generator.generate_sheathing(face="exterior")
    """

    def __init__(
        self,
        wall_data: Dict[str, Any],
        config: Dict[str, Any] = None,
        u_start_bound: Optional[float] = None,
        u_end_bound: Optional[float] = None,
        layer_name: Optional[str] = None,
    ):
        """
        Initialize the sheathing generator.

        Args:
            wall_data: Wall data containing:
                - wall_length: Length of wall (feet)
                - wall_height: Height of wall (feet)
                - openings: List of opening dicts with u_start, rough_width, etc.
                - wall_id: Optional wall identifier
                - panel_id: Optional framing panel identifier
            config: Optional configuration with:
                - panel_size: Standard panel size ("4x8", "4x9", "4x10")
                - stagger_offset: Joint stagger between rows (feet, default 2.0)
                - material: Sheathing material name
                - sheathing_type: Type of sheathing application
                - min_piece_width: Minimum acceptable piece width (feet)
            u_start_bound: Minimum U position for panels (feet). Negative values
                extend before wall start. Default: 0.0.
            u_end_bound: Maximum U position for panels (feet). Values beyond
                wall_length extend past wall end. Default: wall_length.
            layer_name: Optional assembly layer name for multi-layer ID
                disambiguation. When provided, panel IDs include the
                sanitized layer name (e.g., "529398_sheath_osb_exterior_0_0").
        """
        self.wall_data = wall_data
        self.config = config or {}
        self.layer_name = layer_name

        # Extract wall dimensions
        self.wall_length = wall_data.get("wall_length", 0)
        self.wall_height = wall_data.get("wall_height", 0)
        self.wall_id = str(wall_data.get("wall_id", "unknown"))
        self.panel_id = wall_data.get("panel_id")

        # Junction-adjusted panel bounds
        self.u_start_bound = u_start_bound if u_start_bound is not None else 0.0
        self.u_end_bound = u_end_bound if u_end_bound is not None else self.wall_length

        # Get configuration
        panel_size_name = self.config.get("panel_size", "4x8")
        self.panel_size = get_panel_size(panel_size_name)
        self.stagger_offset = self.config.get("stagger_offset", 2.0)  # feet
        self.min_piece_width = self.config.get("min_piece_width", 0.5)  # 6 inches min

        # Get material
        material_name = self.config.get("material")
        sheathing_type = self.config.get("sheathing_type")
        if sheathing_type and isinstance(sheathing_type, str):
            sheathing_type = SheathingType(sheathing_type)
        self.material = get_sheathing_material(material_name, sheathing_type)

        # Parse openings
        self.openings = self._parse_openings(wall_data.get("openings", []))

    def _parse_openings(self, openings_data: List[Dict]) -> List[Dict[str, float]]:
        """
        Parse opening data into consistent format.

        Args:
            openings_data: Raw opening data from wall_data

        Returns:
            List of opening dicts with u_start, u_end, v_start, v_end
        """
        parsed = []
        for opening in openings_data:
            # Handle different key names
            u_start = opening.get("u_start", opening.get("start_u_coordinate", 0))
            width = opening.get("width", opening.get("rough_width", 0))
            v_start = opening.get("v_start", opening.get("base_elevation_relative_to_wall_base", 0))
            height = opening.get("height", opening.get("rough_height", 0))
            opening_type = opening.get("opening_type", opening.get("type", "window"))

            parsed.append({
                "opening_type": opening_type,
                "u_start": u_start,
                "u_end": u_start + width,
                "v_start": v_start,
                "v_end": v_start + height,
            })

        return parsed

    def generate_sheathing(
        self,
        face: str = "exterior"
    ) -> List[SheathingPanel]:
        """
        Generate sheathing panels for the specified wall face.

        Args:
            face: Which face to sheathe ("exterior" or "interior")

        Returns:
            List of SheathingPanel objects
        """
        if self.wall_length <= 0 or self.wall_height <= 0:
            return []

        panels = []
        panel_width = self.panel_size.width_feet
        panel_height = self.panel_size.height_feet

        # Calculate number of rows needed
        num_rows = self._calculate_num_rows(panel_height)

        # Generate panels row by row
        for row in range(num_rows):
            row_panels = self._generate_row(
                row=row,
                panel_width=panel_width,
                panel_height=panel_height,
                num_rows=num_rows,
                face=face
            )
            panels.extend(row_panels)

        return panels

    def _calculate_num_rows(self, panel_height: float) -> int:
        """Calculate number of rows needed to cover wall height."""
        if panel_height <= 0:
            return 0
        return max(1, int((self.wall_height + panel_height - 0.001) / panel_height))

    def _generate_row(
        self,
        row: int,
        panel_width: float,
        panel_height: float,
        num_rows: int,
        face: str
    ) -> List[SheathingPanel]:
        """
        Generate panels for a single row.

        Args:
            row: Row number (0 = bottom)
            panel_width: Standard panel width
            panel_height: Standard panel height
            num_rows: Total number of rows
            face: Wall face being sheathed

        Returns:
            List of SheathingPanel for this row
        """
        panels = []

        # Calculate vertical bounds for this row
        v_start = row * panel_height
        v_end = min((row + 1) * panel_height, self.wall_height)

        # Apply stagger offset for alternating rows
        stagger = (row % 2) * self.stagger_offset

        # Panel layout bounds (may differ from wall length due to junction adjustments)
        u_min = self.u_start_bound
        u_max = self.u_end_bound

        # Start position (may be before u_min due to stagger)
        u_position = u_min - stagger if stagger > 0 else u_min
        column = 0

        while u_position < u_max:
            # Calculate panel bounds, clipped to layout region
            u_start = max(u_min, u_position)
            u_end = min(u_position + panel_width, u_max)

            # Skip if panel would be too narrow
            if u_end - u_start < self.min_piece_width:
                u_position += panel_width
                continue

            # Determine if this is a full sheet
            is_full = (
                (u_end - u_start) >= panel_width - 0.01 and
                (v_end - v_start) >= panel_height - 0.01
            )

            # Find cutouts for openings that intersect this panel
            cutouts = self._find_cutouts(u_start, u_end, v_start, v_end)

            # Create panel
            layer_tag = f"_{_sanitize_layer_name(self.layer_name)}" if self.layer_name else ""
            panel = SheathingPanel(
                id=f"{self.wall_id}_sheath{layer_tag}_{face}_{row}_{column}",
                wall_id=self.wall_id,
                panel_id=self.panel_id,
                face=face,
                material=self.material,
                u_start=u_start,
                u_end=u_end,
                v_start=v_start,
                v_end=v_end,
                row=row,
                column=column,
                is_full_sheet=is_full and len(cutouts) == 0,
                cutouts=cutouts,
                stagger_offset=stagger if column == 0 else 0,
            )
            panels.append(panel)

            u_position += panel_width
            column += 1

        # Extend last panel to cover any remaining gap smaller than min_piece_width.
        # This happens when junction bounds extend past the last panel grid position
        # by an amount too small for a standalone panel (e.g., 0.2 ft wall extension).
        if panels and panels[-1].u_end < u_max:
            gap = u_max - panels[-1].u_end
            if gap < self.min_piece_width:
                panels[-1].u_end = u_max
                panels[-1].is_full_sheet = False

        # Similarly, extend first panel backward if the start gap was too small.
        if panels and panels[0].u_start > u_min:
            gap = panels[0].u_start - u_min
            if gap < self.min_piece_width:
                panels[0].u_start = u_min
                panels[0].is_full_sheet = False

        return panels

    def _find_cutouts(
        self,
        u_start: float,
        u_end: float,
        v_start: float,
        v_end: float
    ) -> List[Cutout]:
        """
        Find all opening cutouts that intersect the given panel bounds.

        Args:
            u_start, u_end: Panel horizontal bounds
            v_start, v_end: Panel vertical bounds

        Returns:
            List of Cutout objects for intersecting openings
        """
        cutouts = []

        for opening in self.openings:
            # Check for intersection
            if (opening["u_start"] < u_end and opening["u_end"] > u_start and
                opening["v_start"] < v_end and opening["v_end"] > v_start):

                # Calculate the cutout bounds (clipped to panel)
                cutout = Cutout(
                    opening_type=opening["opening_type"],
                    u_start=max(opening["u_start"], u_start),
                    u_end=min(opening["u_end"], u_end),
                    v_start=max(opening["v_start"], v_start),
                    v_end=min(opening["v_end"], v_end),
                )
                cutouts.append(cutout)

        return cutouts

    def get_material_summary(
        self,
        panels: List[SheathingPanel]
    ) -> Dict[str, Any]:
        """
        Calculate material summary for generated panels.

        Args:
            panels: List of generated SheathingPanel objects

        Returns:
            Dictionary with material quantities and statistics
        """
        if not panels:
            return {
                "total_panels": 0,
                "full_sheets": 0,
                "partial_sheets": 0,
                "panels_with_cutouts": 0,
                "gross_area_sqft": 0,
                "net_area_sqft": 0,
                "waste_area_sqft": 0,
                "waste_percentage": 0,
            }

        full_sheets = sum(1 for p in panels if p.is_full_sheet)
        partial_sheets = len(panels) - full_sheets
        panels_with_cutouts = sum(1 for p in panels if p.cutouts)
        gross_area = sum(p.area_gross for p in panels)
        net_area = sum(p.area_net for p in panels)
        waste_area = gross_area - net_area

        return {
            "total_panels": len(panels),
            "full_sheets": full_sheets,
            "partial_sheets": partial_sheets,
            "panels_with_cutouts": panels_with_cutouts,
            "gross_area_sqft": round(gross_area, 2),
            "net_area_sqft": round(net_area, 2),
            "waste_area_sqft": round(waste_area, 2),
            "waste_percentage": round(waste_area / gross_area * 100, 1) if gross_area > 0 else 0,
            "material": self.material.name,
            "material_display": self.material.display_name,
            "panel_size": self.panel_size.name,
        }


def _apply_layer_rules_to_config(
    config: Optional[Dict[str, Any]],
    face: str,
    wall_assembly: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merge layer placement rules into sheathing config.

    When a wall assembly is available, looks up the placement rules for the
    outermost panelized layer on the given face and merges stagger_offset
    and min_piece_width into the config. Explicit config values take priority.

    Args:
        config: Existing sheathing config (may be None).
        face: Wall face ("exterior" or "interior").
        wall_assembly: Optional assembly dict with "layers" list.

    Returns:
        Config dict with layer rules applied (original values preserved).
    """
    merged = dict(config) if config else {}

    if not wall_assembly:
        return merged

    try:
        from src.timber_framing_generator.materials.layer_rules import (
            get_rules_for_assembly,
        )

        rules_by_name = get_rules_for_assembly(wall_assembly)

        # Find the layer matching the face's panelized material.
        # For exterior face: look for substrate/exterior first, then finish/exterior.
        # For interior face: look for finish/interior first.
        target_layer_name = None
        layers = wall_assembly.get("layers", [])
        side = "exterior" if face == "exterior" else "interior"

        # Priority order for exterior: substrate > finish
        # Priority order for interior: finish > substrate
        priority = (
            ["substrate", "finish", "membrane", "thermal"]
            if face == "exterior"
            else ["finish", "substrate", "membrane", "thermal"]
        )

        for target_func in priority:
            for layer in layers:
                if (
                    layer.get("side") == side
                    and layer.get("function") == target_func
                    and layer.get("name") in rules_by_name
                ):
                    target_layer_name = layer["name"]
                    break
            if target_layer_name:
                break

        if target_layer_name and target_layer_name in rules_by_name:
            rules = rules_by_name[target_layer_name]
            rules_config = rules.to_sheathing_config()

            # Only apply rule values that weren't explicitly set in config
            for key, value in rules_config.items():
                if key not in merged:
                    merged[key] = value

    except Exception:
        pass  # If rules lookup fails, use config as-is

    return merged


def generate_wall_sheathing(
    wall_data: Dict[str, Any],
    config: Dict[str, Any] = None,
    faces: List[str] = None,
    u_start_bound: Optional[float] = None,
    u_end_bound: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Convenience function to generate sheathing for a wall.

    When wall_data contains a "wall_assembly", layer placement rules are
    automatically applied to fill in missing config values (stagger_offset,
    min_piece_width) based on the assembly's layer composition.

    Args:
        wall_data: Wall geometry and opening data
        config: Sheathing configuration. Explicit values take priority
            over layer rules.
        faces: List of faces to sheathe (default: ["exterior"])
        u_start_bound: Minimum U position for panels. Negative = extend before
            wall start. None = use 0.0.
        u_end_bound: Maximum U position for panels. > wall_length = extend past
            wall end. None = use wall_length.

    Returns:
        Dictionary with sheathing panels and summary
    """
    if faces is None:
        faces = ["exterior"]

    wall_assembly = wall_data.get("wall_assembly")
    all_panels = []

    for face in faces:
        # Apply layer rules per face (exterior substrate vs interior finish)
        face_config = _apply_layer_rules_to_config(config, face, wall_assembly)

        generator = SheathingGenerator(
            wall_data, face_config,
            u_start_bound=u_start_bound,
            u_end_bound=u_end_bound,
        )
        panels = generator.generate_sheathing(face=face)
        all_panels.extend(panels)

    # Use last generator for summary (or create one with base config)
    if not all_panels:
        generator = SheathingGenerator(
            wall_data, config,
            u_start_bound=u_start_bound,
            u_end_bound=u_end_bound,
        )

    summary = generator.get_material_summary(all_panels)

    return {
        "wall_id": wall_data.get("wall_id", "unknown"),
        "sheathing_panels": [p.to_dict() for p in all_panels],
        "summary": summary,
    }
