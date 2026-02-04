# File: src/timber_framing_generator/materials/cfs/cfs_strategy.py
"""
CFS (Cold-Formed Steel) framing strategy implementation.

This module provides CFSFramingStrategy which implements the FramingStrategy
interface for light-gauge steel stud wall framing. It provides the same
material-agnostic interface as TimberFramingStrategy, enabling material
switching at runtime.

Usage:
    from src.timber_framing_generator.core import (
        get_framing_strategy, MaterialSystem
    )

    # Get CFS strategy via factory
    strategy = get_framing_strategy(MaterialSystem.CFS)

    # Generate framing elements
    elements = strategy.generate_framing(wall_data, cell_data, config)
"""

from typing import Dict, List, Any
import traceback

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    FramingStrategy,
    ElementType,
    ElementProfile,
    FramingElement,
    register_strategy,
)
from .cfs_profiles import (
    CFS_PROFILES,
    DEFAULT_CFS_PROFILES,
    get_cfs_profile,
)

# Import adapters from timber module - they're generic and work for CFS too
from src.timber_framing_generator.materials.timber.element_adapters import (
    reconstruct_wall_data,
    plate_geometry_to_framing_element,
    brep_to_framing_element,
    normalize_cells,
    RHINO_AVAILABLE,
)

# Import panel-aware helper for filtering openings
from src.timber_framing_generator.cell_decomposition import get_openings_in_range

# Import our custom logging module
try:
    from src.timber_framing_generator.utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class CFSFramingStrategy(FramingStrategy):
    """
    CFS framing strategy implementing the FramingStrategy interface.

    This strategy generates cold-formed steel wall framing elements including:
    - Tracks (bottom and top - equivalent to plates)
    - Studs (standard, king, trimmer)
    - Opening components (headers, sills, cripples)
    - Bracing (bridging)

    The strategy provides a material-agnostic interface that allows for
    seamless switching between timber and CFS framing systems.

    Key CFS Differences from Timber:
        - Uses tracks (no lips) instead of plates for top/bottom
        - Uses C-section studs with lips for vertical members
        - Headers typically made from back-to-back studs
        - Bridging/blocking uses stud sections
        - All connections via screws (not nails)

    Attributes:
        material_system: Always returns MaterialSystem.CFS
        default_profiles: Maps element types to default CFS profiles

    Example:
        >>> strategy = CFSFramingStrategy()
        >>> sequence = strategy.get_generation_sequence()
        >>> print(sequence[0])
        ElementType.BOTTOM_PLATE
    """

    def __init__(self):
        """Initialize CFS strategy with wall property tracking."""
        self._current_wall_thickness_inches = None
        self._current_is_load_bearing = False

    def set_wall_properties(self, wall_data: Dict[str, Any]) -> None:
        """
        Set current wall properties from wall data for profile selection.

        Args:
            wall_data: Wall data containing wall_thickness (in feet) and is_load_bearing
        """
        # Set wall thickness (in inches)
        thickness_feet = wall_data.get("wall_thickness", 0)
        if thickness_feet > 0:
            self._current_wall_thickness_inches = thickness_feet * 12
            logger.info(f"Set wall thickness for profile selection: {self._current_wall_thickness_inches:.2f} inches")
        else:
            # Try to infer from wall type name (e.g., "Basic Wall - W1 - 6\"")
            wall_type = wall_data.get("wall_type", "")
            import re
            match = re.search(r'(\d+)"', wall_type)
            if match:
                self._current_wall_thickness_inches = float(match.group(1))
                logger.info(f"Inferred wall thickness from type name: {self._current_wall_thickness_inches} inches")

        # Set load-bearing status
        self._current_is_load_bearing = wall_data.get("is_load_bearing", False)
        if self._current_is_load_bearing:
            logger.info("Wall is load-bearing - using structural profiles (68 mil gauge)")
        else:
            logger.info("Wall is non-bearing - using standard profiles (54 mil gauge)")

    def set_wall_thickness(self, wall_data: Dict[str, Any]) -> None:
        """
        Set current wall thickness from wall data for profile selection.

        Deprecated: Use set_wall_properties() instead for full property support.

        Args:
            wall_data: Wall data containing wall_thickness (in feet)
        """
        self.set_wall_properties(wall_data)

    @property
    def material_system(self) -> MaterialSystem:
        """Return the material system this strategy handles."""
        return MaterialSystem.CFS

    @property
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        """
        Return default CFS profiles for each element type.

        Returns:
            Dict mapping ElementType to ElementProfile
        """
        return {
            element_type: CFS_PROFILES[profile_name]
            for element_type, profile_name in DEFAULT_CFS_PROFILES.items()
        }

    def get_generation_sequence(self) -> List[ElementType]:
        """
        Return the order in which element types should be generated.

        CFS framing follows a similar sequence to timber framing:
        1. Tracks (define top/bottom boundaries)
        2. King studs (frame openings)
        3. Headers and sills (span openings)
        4. Trimmers (support headers)
        5. Cripples (fill above/below openings)
        6. Standard studs (fill remaining space)
        7. Bridging (lateral bracing)

        Returns:
            Ordered list of ElementType values
        """
        return [
            ElementType.BOTTOM_PLATE,   # Bottom track
            ElementType.TOP_PLATE,      # Top track
            ElementType.KING_STUD,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.TRIMMER,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.STUD,
            ElementType.ROW_BLOCKING,   # Bridging in CFS terminology
        ]

    def get_element_types(self) -> List[ElementType]:
        """
        Return all element types used in CFS framing.

        Returns:
            List of ElementType values this strategy generates
        """
        return list(DEFAULT_CFS_PROFILES.keys())

    def get_profile(
        self,
        element_type: ElementType,
        config: Dict[str, Any] = None,
        wall_thickness_inches: float = None,
        is_load_bearing: bool = None
    ) -> ElementProfile:
        """
        Get the profile for a specific element type.

        Checks config for profile overrides, otherwise uses default.
        If wall_thickness_inches is provided, selects appropriate series
        (e.g., 600-series for 6" walls instead of default 362-series).
        If is_load_bearing is True, uses structural profiles (thicker gauge).

        Args:
            element_type: The type of framing element
            config: Optional configuration with profile overrides
            wall_thickness_inches: Optional wall thickness for series selection
            is_load_bearing: Optional load-bearing status for gauge selection

        Returns:
            ElementProfile for the element type
        """
        config = config or {}
        profile_overrides = config.get("profile_overrides", {})

        # Check for override in config
        override_name = profile_overrides.get(element_type.value)
        if override_name:
            return get_cfs_profile(element_type, override_name)

        # Use wall thickness and load-bearing aware selection
        # If not explicitly provided, use the current values from instance
        thickness = wall_thickness_inches or self._current_wall_thickness_inches
        load_bearing = is_load_bearing if is_load_bearing is not None else self._current_is_load_bearing
        return get_cfs_profile(
            element_type,
            wall_thickness_inches=thickness,
            is_load_bearing=load_bearing
        )

    def _set_framing_config(
        self,
        wall_data: Dict[str, Any],
        config: Dict[str, Any] = None
    ) -> None:
        """
        Set CFS-specific framing dimensions in wall_data.

        This method populates wall_data["framing_config"] with CFS profile
        dimensions. The framing element generators use get_framing_param()
        which checks this dict first, allowing material-specific dimensions.

        Args:
            wall_data: Wall data dict to modify (in-place)
            config: Optional configuration with profile overrides
        """
        # Get the stud profile for dimension reference
        stud_profile = self.get_profile(ElementType.STUD, config)
        track_profile = self.get_profile(ElementType.BOTTOM_PLATE, config)

        # CFS dimensions from profiles
        # Stud width = flange width (visible edge of C-section)
        # Stud depth = web depth (wall thickness direction)
        stud_width = stud_profile.width
        stud_depth = stud_profile.depth
        track_width = track_profile.width
        track_depth = track_profile.depth

        # Build framing config with CFS dimensions
        framing_config = {
            # Stud dimensions (same for king studs, trimmers, cripples)
            "stud_width": stud_width,
            "stud_depth": stud_depth,
            "king_stud_width": stud_width,
            "king_stud_depth": stud_depth,
            "trimmer_width": stud_width,
            "trimmer_depth": stud_depth,
            "cripple_width": stud_width,
            "cripple_depth": stud_depth,
            # Plate/track dimensions
            "plate_thickness": track_width,  # Track flange = vertical height
            "plate_width": track_depth,       # Track web = wall thickness
            # Header dimensions (using stud profile for now)
            "header_depth": stud_depth,
            # Sill dimensions
            "sill_height": track_width,
            "sill_depth": stud_depth,
        }

        wall_data["framing_config"] = framing_config
        logger.debug(f"Set CFS framing config: stud_width={stud_width*12:.2f}in, stud_depth={stud_depth*12:.2f}in")

    def create_horizontal_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate tracks (horizontal members) for CFS framing.

        In CFS framing, tracks (C-sections without lips) are used
        instead of plates for the top and bottom horizontal members.
        This method reuses the plate generation logic with CFS profiles.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            config: Configuration parameters

        Returns:
            List of FramingElement for tracks
        """
        logger.info("Creating horizontal members (CFS tracks)")
        elements = []

        # Set wall thickness for profile selection
        self.set_wall_thickness(wall_data)

        # Extract wall_id for element metadata
        wall_id = cell_data.get('wall_id', 'unknown')

        # Check if Rhino is available (only works inside Grasshopper)
        if not RHINO_AVAILABLE:
            logger.warning(
                "Rhino not available - returning empty list. "
                "This is expected when running unit tests outside Grasshopper."
            )
            return elements

        try:
            # Import plate generator (same as timber - geometry is the same)
            from src.timber_framing_generator.framing_elements.plates import create_plates

            # Reconstruct wall data with Rhino geometry
            rhino_wall_data = reconstruct_wall_data(wall_data)
            base_plane = rhino_wall_data.get("base_plane")

            # Set CFS-specific dimensions in wall_data for generators
            self._set_framing_config(rhino_wall_data, config)

            # Get configuration
            bottom_plate_layers = config.get("bottom_plate_layers", 1)
            top_plate_layers = config.get("top_plate_layers", 1)  # CFS typically uses single track
            representation_type = config.get("representation_type", "schematic")

            # Get panel boundaries from cell metadata for filtering
            cell_metadata = cell_data.get("metadata", {})
            panel_u_start = cell_metadata.get("panel_u_start")
            panel_u_end = cell_metadata.get("panel_u_end")

            # Filter openings to only those within this panel's range
            all_openings = rhino_wall_data.get("openings", [])
            if panel_u_start is not None and panel_u_end is not None:
                openings = get_openings_in_range(all_openings, panel_u_start, panel_u_end)
                logger.debug(f"Panel [{panel_u_start:.2f}-{panel_u_end:.2f}]: {len(openings)}/{len(all_openings)} openings")
            else:
                openings = all_openings

            # Generate bottom tracks (pass openings to skip door locations)
            logger.debug(f"Creating bottom tracks (layers={bottom_plate_layers}, openings={len(openings)})")
            bottom_plates = create_plates(
                rhino_wall_data,
                plate_type="bottom_plate",
                representation_type=representation_type,
                layers=bottom_plate_layers,
                openings=openings,
            )

            # Convert to FramingElement with CFS track profile
            bottom_profile = self.get_profile(ElementType.BOTTOM_PLATE, config)
            for i, plate in enumerate(bottom_plates):
                elem = plate_geometry_to_framing_element(
                    plate=plate,
                    element_id=f"bottom_track_{i}",
                    element_type=ElementType.BOTTOM_PLATE,
                    profile=bottom_profile,
                    base_plane=base_plane,
                    wall_id=wall_id,
                )
                elements.append(elem)
                logger.debug(f"Created bottom_track_{i}")

            # Generate top tracks
            logger.debug(f"Creating top tracks (layers={top_plate_layers})")
            top_plates = create_plates(
                rhino_wall_data,
                plate_type="top_plate",
                representation_type=representation_type,
                layers=top_plate_layers,
            )

            # Convert to FramingElement with CFS track profile
            top_profile = self.get_profile(ElementType.TOP_PLATE, config)
            for i, plate in enumerate(top_plates):
                elem = plate_geometry_to_framing_element(
                    plate=plate,
                    element_id=f"top_track_{i}",
                    element_type=ElementType.TOP_PLATE,
                    profile=top_profile,
                    base_plane=base_plane,
                    wall_id=wall_id,
                )
                elements.append(elem)
                logger.debug(f"Created top_track_{i}")

            # Store plate geometry for use by vertical member generation
            self._plate_geometry = {
                "bottom_plates": bottom_plates,
                "top_plates": top_plates,
                "rhino_wall_data": rhino_wall_data,
            }

            logger.info(f"Created {len(elements)} horizontal members (CFS tracks)")

        except Exception as e:
            logger.error(f"Error creating horizontal members: {e}")
            logger.error(traceback.format_exc())

        return elements

    def create_vertical_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        horizontal_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate vertical members (studs, king studs, trimmers).

        In CFS framing, C-section studs with lips are used for
        vertical members. Studs fit inside tracks (flanges overlap).
        This method reuses the stud generation logic with CFS profiles.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            horizontal_members: Previously generated tracks
            config: Configuration parameters

        Returns:
            List of FramingElement for vertical members
        """
        logger.info("Creating vertical members (CFS studs)")
        elements = []

        # Extract wall_id for element metadata
        wall_id = cell_data.get('wall_id', 'unknown')

        # Check if Rhino is available
        if not RHINO_AVAILABLE:
            logger.warning("Rhino not available - returning empty list.")
            return elements

        try:
            # Import generators
            from src.timber_framing_generator.framing_elements.king_studs import KingStudGenerator
            from src.timber_framing_generator.framing_elements.studs import StudGenerator
            from src.timber_framing_generator.framing_elements.trimmers import TrimmerGenerator

            # Get stored plate geometry or reconstruct
            if hasattr(self, "_plate_geometry"):
                bottom_plates = self._plate_geometry["bottom_plates"]
                top_plates = self._plate_geometry["top_plates"]
                rhino_wall_data = self._plate_geometry["rhino_wall_data"]
            else:
                rhino_wall_data = reconstruct_wall_data(wall_data)
                # Set CFS-specific dimensions (in case horizontal_members wasn't called)
                self._set_framing_config(rhino_wall_data, config)
                openings_for_plates = rhino_wall_data.get("openings", [])
                # Need to regenerate plates (pass openings to skip door locations)
                from src.timber_framing_generator.framing_elements.plates import create_plates
                bottom_plates = create_plates(
                    rhino_wall_data, plate_type="bottom_plate",
                    representation_type="schematic", layers=1,
                    openings=openings_for_plates
                )
                top_plates = create_plates(
                    rhino_wall_data, plate_type="top_plate",
                    representation_type="schematic", layers=1
                )

            base_plane = rhino_wall_data.get("base_plane")

            # Get panel boundaries from cell metadata for filtering
            cell_metadata = cell_data.get("metadata", {})
            panel_u_start = cell_metadata.get("panel_u_start")
            panel_u_end = cell_metadata.get("panel_u_end")

            # Filter openings to only those within this panel's range
            all_openings = rhino_wall_data.get("openings", [])
            if panel_u_start is not None and panel_u_end is not None:
                openings = get_openings_in_range(all_openings, panel_u_start, panel_u_end)
                logger.debug(f"Panel [{panel_u_start:.2f}-{panel_u_end:.2f}]: {len(openings)}/{len(all_openings)} openings for vertical members")
            else:
                openings = all_openings

            # Use first bottom plate and FIRST top plate (not cap plate)
            bottom_plate = bottom_plates[0] if bottom_plates else None
            top_plate = top_plates[0] if top_plates else None

            if not bottom_plate or not top_plate:
                logger.warning("No plates available for vertical member generation")
                return elements

            # Generate king studs for each opening
            king_stud_breps = []
            king_profile = self.get_profile(ElementType.KING_STUD, config)

            if openings:
                logger.debug(f"Creating king studs for {len(openings)} openings")
                king_gen = KingStudGenerator(rhino_wall_data, bottom_plate, top_plate)

                for i, opening in enumerate(openings):
                    try:
                        studs = king_gen.generate_king_studs(opening)
                        for j, brep in enumerate(studs):
                            king_stud_breps.append(brep)
                            elem = brep_to_framing_element(
                                brep=brep,
                                element_id=f"king_stud_{i}_{j}",
                                element_type=ElementType.KING_STUD,
                                profile=king_profile,
                                base_plane=base_plane,
                                wall_id=wall_id,
                                is_vertical=True,
                            )
                            if elem:
                                elements.append(elem)
                                logger.debug(f"Created king_stud_{i}_{j}")
                    except Exception as e:
                        logger.error(f"Error generating king studs for opening {i}: {e}")

            # Add cells to wall data for stud generator
            cells = cell_data.get("cells", [])
            normalized = normalize_cells(cells)
            rhino_wall_data["cells"] = normalized

            # Add panel boundaries for end stud placement at panel joints
            # Each panel needs its own end studs, not just at wall boundaries
            cell_metadata = cell_data.get("metadata", {})
            if "panel_u_start" in cell_metadata:
                rhino_wall_data["panel_u_start"] = cell_metadata["panel_u_start"]
            if "panel_u_end" in cell_metadata:
                rhino_wall_data["panel_u_end"] = cell_metadata["panel_u_end"]
            logger.debug(f"Panel bounds: u_start={rhino_wall_data.get('panel_u_start')}, u_end={rhino_wall_data.get('panel_u_end')}")

            # Generate standard studs
            logger.debug("Creating standard CFS studs")
            stud_profile = self.get_profile(ElementType.STUD, config)
            stud_gen = StudGenerator(
                rhino_wall_data,
                bottom_plate,
                top_plate,
                king_stud_breps,
            )
            stud_breps = stud_gen.generate_studs()

            # Get panel boundaries for element metadata (for stud orientation in Revit)
            panel_u_start = rhino_wall_data.get("panel_u_start")
            panel_u_end = rhino_wall_data.get("panel_u_end")

            for i, brep in enumerate(stud_breps):
                elem = brep_to_framing_element(
                    brep=brep,
                    element_id=f"stud_{i}",
                    element_type=ElementType.STUD,
                    profile=stud_profile,
                    base_plane=base_plane,
                    wall_id=wall_id,
                    is_vertical=True,
                    panel_u_start=panel_u_start,
                    panel_u_end=panel_u_end,
                )
                if elem:
                    elements.append(elem)

            logger.debug(f"Created {len(stud_breps)} standard studs")

            # Generate trimmers for each opening
            if openings:
                logger.debug("Creating trimmers")
                trimmer_profile = self.get_profile(ElementType.TRIMMER, config)
                trimmer_gen = TrimmerGenerator(rhino_wall_data)
                plate_boundary = bottom_plate.get_boundary_data()

                for i, opening in enumerate(openings):
                    try:
                        trimmers = trimmer_gen.generate_trimmers(opening, plate_boundary)
                        for j, brep in enumerate(trimmers or []):
                            elem = brep_to_framing_element(
                                brep=brep,
                                element_id=f"trimmer_{i}_{j}",
                                element_type=ElementType.TRIMMER,
                                profile=trimmer_profile,
                                base_plane=base_plane,
                                wall_id=wall_id,
                                is_vertical=True,
                            )
                            if elem:
                                elements.append(elem)
                    except Exception as e:
                        logger.error(f"Error generating trimmers for opening {i}: {e}")

            # Store for opening member generation
            self._vertical_geometry = {
                "king_stud_breps": king_stud_breps,
                "stud_breps": stud_breps,
            }

            logger.info(f"Created {len(elements)} vertical members (CFS studs)")

        except Exception as e:
            logger.error(f"Error creating vertical members: {e}")
            logger.error(traceback.format_exc())

        return elements

    def create_opening_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate opening-related members (headers, sills, cripples).

        This method reuses the header/sill/cripple generation logic
        with CFS profiles. CFS headers typically use back-to-back studs,
        but for now we use the same single-piece geometry as timber.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for opening members
        """
        logger.info("Creating opening members (CFS)")
        elements = []

        # Extract wall_id for element metadata
        wall_id = cell_data.get('wall_id', 'unknown')

        # Check if Rhino is available
        if not RHINO_AVAILABLE:
            logger.warning("Rhino not available - returning empty list.")
            return elements

        try:
            # Import generators
            from src.timber_framing_generator.framing_elements.headers import HeaderGenerator
            from src.timber_framing_generator.framing_elements.sills import SillGenerator
            from src.timber_framing_generator.framing_elements.header_cripples import HeaderCrippleGenerator
            from src.timber_framing_generator.framing_elements.sill_cripples import SillCrippleGenerator

            # Get wall data
            if hasattr(self, "_plate_geometry"):
                rhino_wall_data = self._plate_geometry["rhino_wall_data"]
                top_plates = self._plate_geometry["top_plates"]
                bottom_plates = self._plate_geometry["bottom_plates"]
            else:
                rhino_wall_data = reconstruct_wall_data(wall_data)
                # Set CFS-specific dimensions (in case previous methods weren't called)
                self._set_framing_config(rhino_wall_data, config)
                top_plates = []
                bottom_plates = []

            base_plane = rhino_wall_data.get("base_plane")

            # Get panel boundaries from cell metadata for filtering
            cell_metadata = cell_data.get("metadata", {})
            panel_u_start = cell_metadata.get("panel_u_start")
            panel_u_end = cell_metadata.get("panel_u_end")

            # Filter openings to only those within this panel's range
            all_openings = rhino_wall_data.get("openings", [])
            if panel_u_start is not None and panel_u_end is not None:
                openings = get_openings_in_range(all_openings, panel_u_start, panel_u_end)
                logger.debug(f"Panel [{panel_u_start:.2f}-{panel_u_end:.2f}]: {len(openings)}/{len(all_openings)} openings for opening members")
            else:
                openings = all_openings

            if not openings:
                logger.debug("No openings to process in this panel")
                return elements

            # Headers - use same profile as blocking (350S162-54 for CFS)
            logger.debug(f"Creating headers for {len(openings)} openings")
            header_profile = self.get_profile(ElementType.ROW_BLOCKING, config)
            logger.info(f"Header profile: {header_profile.name} (same as blocking)")
            logger.info(f"  Profile dimensions: width={header_profile.width*12}in, depth={header_profile.depth*12}in")
            header_gen = HeaderGenerator(rhino_wall_data)

            header_breps = []
            for i, opening in enumerate(openings):
                try:
                    # Pass actual profile dimensions to generate correct geometry
                    # For horizontal members: width = vertical dimension, depth = into wall
                    header = header_gen.generate_header(
                        opening,
                        profile_height=header_profile.width,  # vertical dimension
                        profile_depth=header_profile.depth,   # into wall
                    )
                    if header:
                        header_breps.append(header)
                        elem = brep_to_framing_element(
                            brep=header,
                            element_id=f"header_{i}",
                            element_type=ElementType.HEADER,
                            profile=header_profile,
                            base_plane=base_plane,
                            wall_id=wall_id,
                            is_vertical=False,
                        )
                        if elem:
                            elements.append(elem)
                except Exception as e:
                    logger.error(f"Error generating header for opening {i}: {e}")

            # Sills (windows only)
            logger.debug("Creating sills for window openings")
            sill_profile = self.get_profile(ElementType.SILL, config)
            sill_gen = SillGenerator(rhino_wall_data)

            sill_breps = []
            for i, opening in enumerate(openings):
                if opening.get("opening_type", "").lower() == "window":
                    try:
                        sill = sill_gen.generate_sill(opening)
                        if sill:
                            sill_breps.append(sill)
                            elem = brep_to_framing_element(
                                brep=sill,
                                element_id=f"sill_{i}",
                                element_type=ElementType.SILL,
                                profile=sill_profile,
                                base_plane=base_plane,
                                wall_id=wall_id,
                                is_vertical=False,
                            )
                            if elem:
                                elements.append(elem)
                    except Exception as e:
                        logger.error(f"Error generating sill for opening {i}: {e}")

            # Header cripples
            header_cripple_breps = []
            if top_plates:
                logger.debug("Creating header cripples")
                hc_profile = self.get_profile(ElementType.HEADER_CRIPPLE, config)
                hc_gen = HeaderCrippleGenerator(rhino_wall_data)
                top_plate_data = top_plates[0].get_boundary_data() if top_plates else {}

                for i, opening in enumerate(openings):
                    if i < len(header_breps):
                        try:
                            from src.timber_framing_generator.utils.safe_rhino import safe_get_bounding_box
                            header_bbox = safe_get_bounding_box(header_breps[i], True)
                            header_data = {"top_elevation": header_bbox.Max.Z}
                            cripples = hc_gen.generate_header_cripples(
                                opening, header_data, top_plate_data
                            )
                            for j, brep in enumerate(cripples or []):
                                header_cripple_breps.append(brep)
                                elem = brep_to_framing_element(
                                    brep=brep,
                                    element_id=f"header_cripple_{i}_{j}",
                                    element_type=ElementType.HEADER_CRIPPLE,
                                    profile=hc_profile,
                                    base_plane=base_plane,
                                    wall_id=wall_id,
                                    is_vertical=True,
                                )
                                if elem:
                                    elements.append(elem)
                        except Exception as e:
                            logger.error(f"Error generating header cripples for opening {i}: {e}")

            # Sill cripples (windows only)
            sill_cripple_breps = []
            if bottom_plates:
                logger.debug("Creating sill cripples")
                sc_profile = self.get_profile(ElementType.SILL_CRIPPLE, config)
                sc_gen = SillCrippleGenerator(rhino_wall_data)
                bottom_plate_data = bottom_plates[0].get_boundary_data() if bottom_plates else {}

                sill_idx = 0
                for i, opening in enumerate(openings):
                    if opening.get("opening_type", "").lower() == "window":
                        if sill_idx < len(sill_breps):
                            try:
                                from src.timber_framing_generator.utils.safe_rhino import safe_get_bounding_box
                                sill_bbox = safe_get_bounding_box(sill_breps[sill_idx], True)
                                sill_data = {"bottom_elevation": sill_bbox.Min.Z}
                                cripples = sc_gen.generate_sill_cripples(
                                    opening, sill_data, bottom_plate_data
                                )
                                for j, brep in enumerate(cripples or []):
                                    sill_cripple_breps.append(brep)
                                    elem = brep_to_framing_element(
                                        brep=brep,
                                        element_id=f"sill_cripple_{i}_{j}",
                                        element_type=ElementType.SILL_CRIPPLE,
                                        profile=sc_profile,
                                        base_plane=base_plane,
                                        wall_id=wall_id,
                                        is_vertical=True,
                                    )
                                    if elem:
                                        elements.append(elem)
                            except Exception as e:
                                logger.error(f"Error generating sill cripples for opening {i}: {e}")
                            sill_idx += 1

            # Store opening geometry for use by bracing members
            self._opening_geometry = {
                "header_cripple_breps": header_cripple_breps,
                "sill_cripple_breps": sill_cripple_breps,
            }
            logger.debug(f"Stored {len(header_cripple_breps)} header cripple breps and {len(sill_cripple_breps)} sill cripple breps")

            logger.info(f"Created {len(elements)} opening members (CFS)")

        except Exception as e:
            logger.error(f"Error creating opening members: {e}")
            logger.error(traceback.format_exc())

        return elements

    def create_bracing_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        existing_members: List[FramingElement],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate bracing members (bridging for CFS).

        CFS bridging provides lateral bracing and typically consists of:
        - Flat strap bridging
        - Cold-rolled channel bridging
        - Stud sections as blocking

        For Phase 1, this reuses the row blocking logic from timber.
        Future phases will implement CFS-specific bridging patterns.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for bracing members
        """
        logger.info("Creating bracing members (CFS bridging)")
        elements = []

        # Extract wall_id for element metadata
        wall_id = cell_data.get('wall_id', 'unknown')

        # Check if Rhino is available
        if not RHINO_AVAILABLE:
            logger.warning("Rhino not available - returning empty list.")
            return elements

        # Check if blocking is enabled
        include_blocking = config.get("include_blocking", True)
        if not include_blocking:
            logger.debug("Bridging/blocking disabled in config")
            return elements

        try:
            from src.timber_framing_generator.framing_elements.row_blocking import RowBlockingGenerator

            # Get wall data
            if hasattr(self, "_plate_geometry"):
                rhino_wall_data = self._plate_geometry["rhino_wall_data"]
            else:
                rhino_wall_data = reconstruct_wall_data(wall_data)
                # Set CFS-specific dimensions (in case previous methods weren't called)
                self._set_framing_config(rhino_wall_data, config)

            base_plane = rhino_wall_data.get("base_plane")

            # Add cells to wall data
            cells = cell_data.get("cells", [])
            rhino_wall_data["cells"] = normalize_cells(cells)

            # Get stud breps for blocking placement
            stud_breps = []
            king_stud_breps = []
            if hasattr(self, "_vertical_geometry"):
                stud_breps = self._vertical_geometry.get("stud_breps", [])
                king_stud_breps = self._vertical_geometry.get("king_stud_breps", [])

            # Get cripple breps from opening geometry for blocking placement
            header_cripple_breps = []
            sill_cripple_breps = []
            if hasattr(self, "_opening_geometry"):
                header_cripple_breps = self._opening_geometry.get("header_cripple_breps", [])
                sill_cripple_breps = self._opening_geometry.get("sill_cripple_breps", [])
                logger.debug(f"Retrieved {len(header_cripple_breps)} header cripple breps and {len(sill_cripple_breps)} sill cripple breps for bridging")

            # Create blocking generator (reusing timber logic for now)
            # TODO: Implement CFS-specific bridging patterns
            blocking_gen = RowBlockingGenerator(
                wall_data=rhino_wall_data,
                studs=stud_breps,
                king_studs=king_stud_breps,
                trimmers=[],
                header_cripples=header_cripple_breps,
                sill_cripples=sill_cripple_breps,
                blocking_pattern=config.get("blocking_pattern", "INLINE"),
                include_blocking=include_blocking,
                block_spacing=config.get("block_spacing", 4.0),
                first_block_height=config.get("first_block_height", 2.0),
            )

            blocking_breps = blocking_gen.generate_blocking()
            blocking_profile = self.get_profile(ElementType.ROW_BLOCKING, config)

            for i, brep in enumerate(blocking_breps):
                elem = brep_to_framing_element(
                    brep=brep,
                    element_id=f"bridging_{i}",
                    element_type=ElementType.ROW_BLOCKING,
                    profile=blocking_profile,
                    base_plane=base_plane,
                    is_vertical=False,
                    wall_id=wall_id,
                )
                if elem:
                    elements.append(elem)

            logger.info(f"Created {len(elements)} bridging elements (CFS)")

        except Exception as e:
            logger.error(f"Error creating bracing members: {e}")
            logger.error(traceback.format_exc())

        return elements


# =============================================================================
# Strategy Registration
# =============================================================================

# Register the CFS strategy when this module is imported
# This allows get_framing_strategy(MaterialSystem.CFS) to work
_cfs_strategy = CFSFramingStrategy()
register_strategy(_cfs_strategy)
