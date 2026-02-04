# File: src/timber_framing_generator/materials/timber/timber_strategy.py
"""
Timber framing strategy implementation.

This module provides TimberFramingStrategy which implements the FramingStrategy
interface for standard timber/lumber wall framing. It wraps the existing
framing generation logic while conforming to the material-agnostic interface.

Usage:
    from src.timber_framing_generator.core import (
        get_framing_strategy, MaterialSystem
    )

    # Get timber strategy via factory
    strategy = get_framing_strategy(MaterialSystem.TIMBER)

    # Generate framing elements
    elements = strategy.generate_framing(wall_data, cell_data, config)
"""

from typing import Dict, List, Any, Optional
import traceback

from src.timber_framing_generator.core.material_system import (
    MaterialSystem,
    FramingStrategy,
    ElementType,
    ElementProfile,
    FramingElement,
    register_strategy,
)
from .timber_profiles import (
    TIMBER_PROFILES,
    DEFAULT_TIMBER_PROFILES,
    get_timber_profile,
)

# Import adapters - these require Rhino but import is now safe
from .element_adapters import (
    reconstruct_wall_data,
    plate_geometry_to_framing_element,
    brep_to_framing_element,
    normalize_cells,
    RHINO_AVAILABLE,
)

# Import our custom logging module
try:
    from src.timber_framing_generator.utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class TimberFramingStrategy(FramingStrategy):
    """
    Timber framing strategy implementing the FramingStrategy interface.

    This strategy generates standard timber wall framing elements including:
    - Plates (bottom and top)
    - Studs (standard, king, trimmer)
    - Opening components (headers, sills, cripples)
    - Bracing (row blocking)

    The strategy wraps existing framing generation logic while providing
    a material-agnostic interface that allows for future multi-material
    support (e.g., CFS framing).

    Attributes:
        material_system: Always returns MaterialSystem.TIMBER
        default_profiles: Maps element types to default lumber profiles

    Example:
        >>> strategy = TimberFramingStrategy()
        >>> sequence = strategy.get_generation_sequence()
        >>> print(sequence[0])
        ElementType.BOTTOM_PLATE
    """

    @property
    def material_system(self) -> MaterialSystem:
        """Return the material system this strategy handles."""
        return MaterialSystem.TIMBER

    @property
    def default_profiles(self) -> Dict[ElementType, ElementProfile]:
        """
        Return default lumber profiles for each element type.

        Returns:
            Dict mapping ElementType to ElementProfile
        """
        return {
            element_type: TIMBER_PROFILES[profile_name]
            for element_type, profile_name in DEFAULT_TIMBER_PROFILES.items()
        }

    def get_generation_sequence(self) -> List[ElementType]:
        """
        Return the order in which element types should be generated.

        Timber framing follows a specific sequence where certain elements
        must be generated before others due to dependencies:
        1. Plates (define top/bottom boundaries)
        2. King studs (frame openings)
        3. Headers and sills (span openings)
        4. Trimmers (support headers)
        5. Cripples (fill above/below openings)
        6. Standard studs (fill remaining space)
        7. Row blocking (lateral bracing)

        Returns:
            Ordered list of ElementType values
        """
        return [
            ElementType.BOTTOM_PLATE,
            ElementType.TOP_PLATE,
            ElementType.KING_STUD,
            ElementType.HEADER,
            ElementType.SILL,
            ElementType.TRIMMER,
            ElementType.HEADER_CRIPPLE,
            ElementType.SILL_CRIPPLE,
            ElementType.STUD,
            ElementType.ROW_BLOCKING,
        ]

    def get_element_types(self) -> List[ElementType]:
        """
        Return all element types used in timber framing.

        Returns:
            List of ElementType values this strategy generates
        """
        return list(DEFAULT_TIMBER_PROFILES.keys())

    def get_profile(
        self,
        element_type: ElementType,
        config: Dict[str, Any] = None
    ) -> ElementProfile:
        """
        Get the profile for a specific element type.

        Checks config for profile overrides, otherwise uses default.

        Args:
            element_type: The type of framing element
            config: Optional configuration with profile overrides

        Returns:
            ElementProfile for the element type
        """
        config = config or {}
        profile_overrides = config.get("profile_overrides", {})

        # Check for override in config
        override_name = profile_overrides.get(element_type.value)
        if override_name:
            return get_timber_profile(element_type, override_name)

        return get_timber_profile(element_type)

    def _set_framing_config(
        self,
        wall_data: Dict[str, Any],
        config: Dict[str, Any] = None
    ) -> None:
        """
        Set timber-specific framing dimensions in wall_data.

        This method populates wall_data["framing_config"] with timber profile
        dimensions. The framing element generators use get_framing_param()
        which checks this dict first, allowing material-specific dimensions.

        Args:
            wall_data: Wall data dict to modify (in-place)
            config: Optional configuration with profile overrides
        """
        # Get the stud profile for dimension reference
        stud_profile = self.get_profile(ElementType.STUD, config)
        plate_profile = self.get_profile(ElementType.BOTTOM_PLATE, config)

        # Timber dimensions from profiles
        # For 2x4: width = 1.5", depth = 3.5"
        # For 2x6: width = 1.5", depth = 5.5"
        stud_width = stud_profile.width
        stud_depth = stud_profile.depth
        plate_width = plate_profile.width
        plate_depth = plate_profile.depth

        # Build framing config with timber dimensions
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
            # Plate dimensions
            "plate_thickness": plate_width,  # Plate thickness = lumber width (1.5")
            "plate_width": plate_depth,       # Plate width = lumber depth (3.5" or 5.5")
            # Header dimensions
            "header_depth": stud_depth,
            # Sill dimensions
            "sill_height": plate_width,
            "sill_depth": stud_depth,
        }

        wall_data["framing_config"] = framing_config
        logger.debug(f"Set timber framing config: stud_width={stud_width*12:.2f}in, stud_depth={stud_depth*12:.2f}in")

    def create_horizontal_members(
        self,
        wall_data: Dict[str, Any],
        cell_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[FramingElement]:
        """
        Generate plates (horizontal members) for timber framing.

        This method delegates to the existing plate generation logic
        and converts the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            config: Configuration parameters

        Returns:
            List of FramingElement for plates
        """
        logger.info("Creating horizontal members (plates)")
        elements = []

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
            # Import plate generator
            from src.timber_framing_generator.framing_elements.plates import create_plates

            # Reconstruct wall data with Rhino geometry
            rhino_wall_data = reconstruct_wall_data(wall_data)
            base_plane = rhino_wall_data.get("base_plane")

            # Set timber-specific dimensions in wall_data for generators
            self._set_framing_config(rhino_wall_data, config)

            # Get configuration
            bottom_plate_layers = config.get("bottom_plate_layers", 1)
            top_plate_layers = config.get("top_plate_layers", 2)
            representation_type = config.get("representation_type", "schematic")

            # Generate bottom plates (pass openings to skip door locations)
            openings = rhino_wall_data.get("openings", [])
            logger.debug(f"Creating bottom plates (layers={bottom_plate_layers}, openings={len(openings)})")
            bottom_plates = create_plates(
                rhino_wall_data,
                plate_type="bottom_plate",
                representation_type=representation_type,
                layers=bottom_plate_layers,
                openings=openings,
            )

            # Convert to FramingElement
            bottom_profile = self.get_profile(ElementType.BOTTOM_PLATE, config)
            for i, plate in enumerate(bottom_plates):
                elem = plate_geometry_to_framing_element(
                    plate=plate,
                    element_id=f"bottom_plate_{i}",
                    element_type=ElementType.BOTTOM_PLATE,
                    profile=bottom_profile,
                    base_plane=base_plane,
                    wall_id=wall_id,
                )
                elements.append(elem)
                logger.debug(f"Created bottom_plate_{i}")

            # Generate top plates
            logger.debug(f"Creating top plates (layers={top_plate_layers})")
            top_plates = create_plates(
                rhino_wall_data,
                plate_type="top_plate",
                representation_type=representation_type,
                layers=top_plate_layers,
            )

            # Convert to FramingElement
            top_profile = self.get_profile(ElementType.TOP_PLATE, config)
            for i, plate in enumerate(top_plates):
                elem = plate_geometry_to_framing_element(
                    plate=plate,
                    element_id=f"top_plate_{i}",
                    element_type=ElementType.TOP_PLATE,
                    profile=top_profile,
                    base_plane=base_plane,
                    wall_id=wall_id,
                )
                elements.append(elem)
                logger.debug(f"Created top_plate_{i}")

            # Store plate geometry for use by vertical member generation
            self._plate_geometry = {
                "bottom_plates": bottom_plates,
                "top_plates": top_plates,
                "rhino_wall_data": rhino_wall_data,
            }

            logger.info(f"Created {len(elements)} horizontal members")

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

        This method delegates to the existing stud generation logic
        and converts the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            horizontal_members: Previously generated plates
            config: Configuration parameters

        Returns:
            List of FramingElement for vertical members
        """
        logger.info("Creating vertical members (studs)")
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
                # Set timber-specific dimensions (in case horizontal_members wasn't called)
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
                    representation_type="schematic", layers=2
                )

            base_plane = rhino_wall_data.get("base_plane")
            openings = rhino_wall_data.get("openings", [])

            # Use first bottom plate and FIRST top plate (not cap plate)
            # Vertical members (studs, king studs) should end at the bottom of the
            # first top plate, not at the cap plate.
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
            # Normalize cells - generators expect "type" but JSON uses "cell_type"
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
            logger.debug("Creating standard studs")
            stud_profile = self.get_profile(ElementType.STUD, config)
            stud_gen = StudGenerator(
                rhino_wall_data,
                bottom_plate,
                top_plate,
                king_stud_breps,
            )
            stud_breps = stud_gen.generate_studs()

            for i, brep in enumerate(stud_breps):
                elem = brep_to_framing_element(
                    brep=brep,
                    element_id=f"stud_{i}",
                    element_type=ElementType.STUD,
                    profile=stud_profile,
                    base_plane=base_plane,
                    wall_id=wall_id,
                    is_vertical=True,
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

            logger.info(f"Created {len(elements)} vertical members")

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

        This method delegates to the existing opening component
        generation logic and converts the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for opening members
        """
        logger.info("Creating opening members")
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
                # Set timber-specific dimensions (in case previous methods weren't called)
                self._set_framing_config(rhino_wall_data, config)
                top_plates = []
                bottom_plates = []

            base_plane = rhino_wall_data.get("base_plane")
            openings = rhino_wall_data.get("openings", [])

            if not openings:
                logger.debug("No openings to process")
                return elements

            # Headers - use same profile as blocking (2x4 for timber)
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

            # Header cripples - collect breps for row blocking
            header_cripple_breps = []
            if top_plates:
                logger.debug("Creating header cripples")
                hc_profile = self.get_profile(ElementType.HEADER_CRIPPLE, config)
                hc_gen = HeaderCrippleGenerator(rhino_wall_data)
                # Use FIRST top plate (not cap plate) - header cripples go from header
                # top to the bottom of the first top plate
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
                                header_cripple_breps.append(brep)  # Collect for row blocking
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

            # Sill cripples (windows only) - collect breps for row blocking
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
                                    sill_cripple_breps.append(brep)  # Collect for row blocking
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

            # Store opening geometry for use by bracing members (row blocking)
            self._opening_geometry = {
                "header_cripple_breps": header_cripple_breps,
                "sill_cripple_breps": sill_cripple_breps,
            }
            logger.debug(f"Stored {len(header_cripple_breps)} header cripple breps and {len(sill_cripple_breps)} sill cripple breps")

            logger.info(f"Created {len(elements)} opening members")

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
        Generate bracing members (row blocking for timber).

        This method delegates to the existing row blocking generation
        logic and converts the results to FramingElement format.

        Args:
            wall_data: Wall geometry and properties
            cell_data: Cell decomposition data
            existing_members: Previously generated members
            config: Configuration parameters

        Returns:
            List of FramingElement for bracing members
        """
        logger.info("Creating bracing members (row blocking)")
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
            logger.debug("Row blocking disabled in config")
            return elements

        try:
            from src.timber_framing_generator.framing_elements.row_blocking import RowBlockingGenerator

            # Get wall data
            if hasattr(self, "_plate_geometry"):
                rhino_wall_data = self._plate_geometry["rhino_wall_data"]
            else:
                rhino_wall_data = reconstruct_wall_data(wall_data)
                # Set timber-specific dimensions (in case previous methods weren't called)
                self._set_framing_config(rhino_wall_data, config)

            base_plane = rhino_wall_data.get("base_plane")

            # Add cells to wall data
            # Normalize cells - generators expect "type" but JSON uses "cell_type"
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
                logger.debug(f"Retrieved {len(header_cripple_breps)} header cripple breps and {len(sill_cripple_breps)} sill cripple breps for blocking")

            # Create blocking generator
            blocking_gen = RowBlockingGenerator(
                wall_data=rhino_wall_data,
                studs=stud_breps,
                king_studs=king_stud_breps,
                trimmers=[],  # TODO: Add trimmers
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
                    element_id=f"blocking_{i}",
                    element_type=ElementType.ROW_BLOCKING,
                    profile=blocking_profile,
                    base_plane=base_plane,
                    is_vertical=False,
                    wall_id=wall_id,
                )
                if elem:
                    elements.append(elem)

            logger.info(f"Created {len(elements)} blocking elements")

        except Exception as e:
            logger.error(f"Error creating bracing members: {e}")
            logger.error(traceback.format_exc())

        return elements


# =============================================================================
# Strategy Registration
# =============================================================================

# Register the timber strategy when this module is imported
# This allows get_framing_strategy(MaterialSystem.TIMBER) to work
_timber_strategy = TimberFramingStrategy()
register_strategy(_timber_strategy)
