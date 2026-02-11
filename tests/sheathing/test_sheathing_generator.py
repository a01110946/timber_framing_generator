# File: tests/sheathing/test_sheathing_generator.py
"""Tests for sheathing generation module."""

import pytest
from src.timber_framing_generator.sheathing import (
    SheathingGenerator,
    SheathingPanel,
    SheathingMaterial,
    SheathingType,
    PanelSize,
    SHEATHING_MATERIALS,
    PANEL_SIZES,
    get_sheathing_material,
    get_panel_size,
    generate_wall_sheathing,
)


from src.timber_framing_generator.sheathing.sheathing_generator import (
    _sanitize_layer_name,
)


class TestSanitizeLayerName:
    """Tests for _sanitize_layer_name helper."""

    def test_simple_name(self) -> None:
        assert _sanitize_layer_name("OSB") == "osb"

    def test_spaces_to_underscores(self) -> None:
        assert _sanitize_layer_name("Fiber Cement Siding") == "fiber_cement_siding"

    def test_slashes_to_underscores(self) -> None:
        assert _sanitize_layer_name("OSB 7/16") == "osb_7_16"

    def test_quotes_stripped(self) -> None:
        assert _sanitize_layer_name('1/2" Gypsum Board') == "1_2_gypsum_board"

    def test_leading_trailing_stripped(self) -> None:
        assert _sanitize_layer_name("  OSB  ") == "osb"

    def test_consecutive_specials_collapsed(self) -> None:
        assert _sanitize_layer_name("OSB - 7/16 ") == "osb_7_16"


class TestLayerNameInPanelIds:
    """Tests for layer_name parameter in SheathingGenerator."""

    def test_no_layer_name_backward_compatible(self) -> None:
        """Without layer_name, IDs use the old format."""
        wall_data = {
            "wall_id": "w1",
            "wall_length": 4.0,
            "wall_height": 8.0,
            "openings": [],
        }
        gen = SheathingGenerator(wall_data)
        panels = gen.generate_sheathing(face="exterior")
        assert panels[0].id == "w1_sheath_exterior_0_0"

    def test_layer_name_included_in_id(self) -> None:
        """With layer_name, IDs include the sanitized layer name."""
        wall_data = {
            "wall_id": "w1",
            "wall_length": 4.0,
            "wall_height": 8.0,
            "openings": [],
        }
        gen = SheathingGenerator(wall_data, layer_name="OSB Sheathing")
        panels = gen.generate_sheathing(face="exterior")
        assert panels[0].id == "w1_sheath_osb_sheathing_exterior_0_0"

    def test_two_layers_unique_ids(self) -> None:
        """Two generators with different layer names produce distinct IDs."""
        wall_data = {
            "wall_id": "w1",
            "wall_length": 8.0,
            "wall_height": 8.0,
            "openings": [],
        }
        gen_osb = SheathingGenerator(wall_data, layer_name="OSB")
        gen_siding = SheathingGenerator(wall_data, layer_name="Siding")

        panels_osb = gen_osb.generate_sheathing(face="exterior")
        panels_siding = gen_siding.generate_sheathing(face="exterior")

        osb_ids = {p.id for p in panels_osb}
        siding_ids = {p.id for p in panels_siding}

        # No overlap
        assert osb_ids.isdisjoint(siding_ids)


class TestSheathingProfiles:
    """Tests for sheathing material profiles."""

    def test_material_catalog_not_empty(self):
        """Material catalog should have entries."""
        assert len(SHEATHING_MATERIALS) > 0

    def test_panel_sizes_available(self):
        """Standard panel sizes should be defined."""
        assert "4x8" in PANEL_SIZES
        assert "4x9" in PANEL_SIZES
        assert "4x10" in PANEL_SIZES

    def test_get_default_material(self):
        """Should return default structural material."""
        material = get_sheathing_material()
        assert material is not None
        assert isinstance(material, SheathingMaterial)
        assert material.sheathing_type == SheathingType.STRUCTURAL

    def test_get_material_by_name(self):
        """Should return specific material by name."""
        material = get_sheathing_material("osb_1_2")
        assert material.name == "osb_1_2"
        assert material.thickness_inches == 0.5

    def test_get_material_by_type(self):
        """Should return default for sheathing type."""
        material = get_sheathing_material(sheathing_type=SheathingType.NON_STRUCTURAL)
        assert material.sheathing_type == SheathingType.NON_STRUCTURAL
        assert material.material_type == "gypsum"

    def test_material_unknown_raises(self):
        """Should raise for unknown material."""
        with pytest.raises(KeyError):
            get_sheathing_material("nonexistent_material")

    def test_panel_size_dimensions(self):
        """Panel size should have correct dimensions."""
        size = get_panel_size("4x8")
        assert size.width_feet == 4.0
        assert size.height_feet == 8.0
        assert size.width_inches == 48.0
        assert size.height_inches == 96.0


class TestSheathingGenerator:
    """Tests for SheathingGenerator class."""

    @pytest.fixture
    def simple_wall_data(self):
        """Create simple wall data without openings."""
        return {
            "wall_id": "test_wall_1",
            "wall_length": 12.0,  # 12 feet
            "wall_height": 8.0,   # 8 feet
            "openings": [],
        }

    @pytest.fixture
    def wall_with_window(self):
        """Create wall data with a window opening."""
        return {
            "wall_id": "test_wall_2",
            "wall_length": 16.0,
            "wall_height": 8.0,
            "openings": [
                {
                    "opening_type": "window",
                    "start_u_coordinate": 6.0,
                    "rough_width": 4.0,
                    "base_elevation_relative_to_wall_base": 3.0,
                    "rough_height": 4.0,
                }
            ],
        }

    @pytest.fixture
    def wall_with_door(self):
        """Create wall data with a door opening."""
        return {
            "wall_id": "test_wall_3",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [
                {
                    "opening_type": "door",
                    "start_u_coordinate": 4.0,
                    "rough_width": 3.0,
                    "base_elevation_relative_to_wall_base": 0.0,
                    "rough_height": 7.0,
                }
            ],
        }

    def test_generator_creation(self, simple_wall_data):
        """Generator should initialize correctly."""
        generator = SheathingGenerator(simple_wall_data)
        assert generator.wall_length == 12.0
        assert generator.wall_height == 8.0
        assert generator.wall_id == "test_wall_1"

    def test_generate_simple_wall(self, simple_wall_data):
        """Should generate panels for simple wall."""
        generator = SheathingGenerator(simple_wall_data)
        panels = generator.generate_sheathing()

        # 12' wall with 4' panels = 3 panels in one row
        assert len(panels) == 3
        assert all(isinstance(p, SheathingPanel) for p in panels)

    def test_panel_coverage(self, simple_wall_data):
        """Panels should cover entire wall width."""
        generator = SheathingGenerator(simple_wall_data)
        panels = generator.generate_sheathing()

        # Check first and last panel bounds
        u_values = [(p.u_start, p.u_end) for p in panels]
        min_u = min(p.u_start for p in panels)
        max_u = max(p.u_end for p in panels)

        assert min_u == 0.0
        assert max_u == 12.0

    def test_panel_with_window_cutout(self, wall_with_window):
        """Panels intersecting window should have cutouts."""
        generator = SheathingGenerator(wall_with_window)
        panels = generator.generate_sheathing()

        # Find panels with cutouts
        panels_with_cutouts = [p for p in panels if p.cutouts]

        assert len(panels_with_cutouts) > 0
        # Window is at u=6-10, panels are 4' wide, so should affect panel at u=4-8 and u=8-12
        cutout_types = [c.opening_type for p in panels_with_cutouts for c in p.cutouts]
        assert "window" in cutout_types

    def test_panel_with_door_cutout(self, wall_with_door):
        """Panels intersecting door should have cutouts."""
        generator = SheathingGenerator(wall_with_door)
        panels = generator.generate_sheathing()

        panels_with_cutouts = [p for p in panels if p.cutouts]
        assert len(panels_with_cutouts) > 0

        cutout_types = [c.opening_type for p in panels_with_cutouts for c in p.cutouts]
        assert "door" in cutout_types

    def test_stagger_offset(self, simple_wall_data):
        """Multi-row walls should have staggered joints."""
        # Make wall taller to need 2 rows
        simple_wall_data["wall_height"] = 16.0
        config = {"stagger_offset": 2.0}

        generator = SheathingGenerator(simple_wall_data, config)
        panels = generator.generate_sheathing()

        # Find row 0 and row 1 panels
        row0_panels = [p for p in panels if p.row == 0]
        row1_panels = [p for p in panels if p.row == 1]

        # Row 1 should have stagger offset
        row1_offsets = [p.stagger_offset for p in row1_panels]
        assert any(offset > 0 for offset in row1_offsets)

    def test_custom_panel_size(self, simple_wall_data):
        """Should use custom panel size from config."""
        config = {"panel_size": "4x10"}
        generator = SheathingGenerator(simple_wall_data, config)

        assert generator.panel_size.height_feet == 10.0

    def test_custom_material(self, simple_wall_data):
        """Should use custom material from config."""
        config = {"material": "gypsum_5_8"}
        generator = SheathingGenerator(simple_wall_data, config)

        assert generator.material.name == "gypsum_5_8"
        assert generator.material.thickness_inches == 5/8

    def test_exterior_and_interior_faces(self, simple_wall_data):
        """Should generate panels for specified face."""
        generator = SheathingGenerator(simple_wall_data)

        ext_panels = generator.generate_sheathing(face="exterior")
        int_panels = generator.generate_sheathing(face="interior")

        assert all(p.face == "exterior" for p in ext_panels)
        assert all(p.face == "interior" for p in int_panels)

    def test_material_summary(self, simple_wall_data):
        """Should calculate correct material summary."""
        generator = SheathingGenerator(simple_wall_data)
        panels = generator.generate_sheathing()
        summary = generator.get_material_summary(panels)

        assert summary["total_panels"] == 3
        assert summary["gross_area_sqft"] == 12.0 * 8.0  # Full wall coverage
        assert "material" in summary

    def test_empty_wall(self):
        """Should handle zero-dimension wall."""
        wall_data = {
            "wall_id": "empty",
            "wall_length": 0,
            "wall_height": 0,
            "openings": [],
        }
        generator = SheathingGenerator(wall_data)
        panels = generator.generate_sheathing()

        assert len(panels) == 0


class TestGenerateWallSheathing:
    """Tests for the convenience function."""

    def test_generate_wall_sheathing(self):
        """Convenience function should work."""
        wall_data = {
            "wall_id": "test",
            "wall_length": 8.0,
            "wall_height": 8.0,
            "openings": [],
        }

        result = generate_wall_sheathing(wall_data)

        assert "wall_id" in result
        assert "sheathing_panels" in result
        assert "summary" in result
        assert len(result["sheathing_panels"]) == 2  # 8' wall = 2 x 4' panels

    def test_generate_both_faces(self):
        """Should generate for multiple faces."""
        wall_data = {
            "wall_id": "test",
            "wall_length": 8.0,
            "wall_height": 8.0,
            "openings": [],
        }

        result = generate_wall_sheathing(wall_data, faces=["exterior", "interior"])

        # 2 panels per face x 2 faces = 4 panels
        assert len(result["sheathing_panels"]) == 4

    def test_panel_to_dict(self):
        """SheathingPanel should serialize to dict."""
        wall_data = {
            "wall_id": "test",
            "wall_length": 4.0,
            "wall_height": 8.0,
            "openings": [],
        }

        result = generate_wall_sheathing(wall_data)
        panel_dict = result["sheathing_panels"][0]

        assert "id" in panel_dict
        assert "u_start" in panel_dict
        assert "u_end" in panel_dict
        assert "material" in panel_dict
        assert "thickness_inches" in panel_dict


# =============================================================================
# Junction Bounds Integration Tests
# =============================================================================


class TestSheathingWithJunctionBounds:
    """Tests for sheathing generation with junction-adjusted panel bounds.

    When walls meet at junctions, sheathing panels need to extend or trim
    beyond the wall's own length to properly cover (or avoid) the junction area.
    The u_start_bound and u_end_bound parameters control this.
    """

    @pytest.fixture
    def standard_wall(self):
        """12 ft wall, 8 ft tall, no openings."""
        return {
            "wall_id": "wall_A",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [],
        }

    def test_extend_at_start(self, standard_wall):
        """Panels should start before u=0 when u_start_bound is negative."""
        generator = SheathingGenerator(
            standard_wall, u_start_bound=-0.2, u_end_bound=12.0
        )
        panels = generator.generate_sheathing()

        min_u = min(p.u_start for p in panels)
        assert min_u == pytest.approx(-0.2, abs=0.01)

    def test_extend_at_end(self, standard_wall):
        """Panels should extend past wall_length when u_end_bound exceeds it."""
        generator = SheathingGenerator(
            standard_wall, u_start_bound=0.0, u_end_bound=12.2
        )
        panels = generator.generate_sheathing()

        max_u = max(p.u_end for p in panels)
        assert max_u == pytest.approx(12.2, abs=0.01)

    def test_trim_at_start(self, standard_wall):
        """Panels should not start before u_start_bound when it's positive."""
        generator = SheathingGenerator(
            standard_wall, u_start_bound=0.15, u_end_bound=12.0
        )
        panels = generator.generate_sheathing()

        min_u = min(p.u_start for p in panels)
        assert min_u == pytest.approx(0.15, abs=0.01)

    def test_trim_at_end(self, standard_wall):
        """Panels should stop before wall_length when u_end_bound is less."""
        generator = SheathingGenerator(
            standard_wall, u_start_bound=0.0, u_end_bound=11.85
        )
        panels = generator.generate_sheathing()

        max_u = max(p.u_end for p in panels)
        assert max_u == pytest.approx(11.85, abs=0.01)

    def test_default_bounds_match_wall_length(self, standard_wall):
        """Without bounds, panels should span exactly 0 to wall_length."""
        generator = SheathingGenerator(standard_wall)
        panels = generator.generate_sheathing()

        min_u = min(p.u_start for p in panels)
        max_u = max(p.u_end for p in panels)
        assert min_u == pytest.approx(0.0, abs=0.01)
        assert max_u == pytest.approx(12.0, abs=0.01)

    def test_bounds_via_convenience_function(self, standard_wall):
        """generate_wall_sheathing should pass bounds through correctly."""
        result = generate_wall_sheathing(
            standard_wall,
            u_start_bound=-0.15,
            u_end_bound=12.3,
        )
        panels = result["sheathing_panels"]

        min_u = min(p["u_start"] for p in panels)
        max_u = max(p["u_end"] for p in panels)
        assert min_u == pytest.approx(-0.15, abs=0.01)
        assert max_u == pytest.approx(12.3, abs=0.01)

    def test_both_ends_extended(self, standard_wall):
        """Extending both ends should widen the total panel coverage."""
        result_default = generate_wall_sheathing(standard_wall)
        result_extended = generate_wall_sheathing(
            standard_wall,
            u_start_bound=-0.2,
            u_end_bound=12.2,
        )

        default_area = result_default["summary"]["gross_area_sqft"]
        extended_area = result_extended["summary"]["gross_area_sqft"]

        # Extended coverage should be larger
        assert extended_area > default_area

    def test_both_ends_trimmed(self, standard_wall):
        """Trimming both ends should reduce total panel coverage."""
        result_default = generate_wall_sheathing(standard_wall)
        result_trimmed = generate_wall_sheathing(
            standard_wall,
            u_start_bound=0.15,
            u_end_bound=11.85,
        )

        default_area = result_default["summary"]["gross_area_sqft"]
        trimmed_area = result_trimmed["summary"]["gross_area_sqft"]

        # Trimmed coverage should be smaller
        assert trimmed_area < default_area

    def test_stagger_respects_bounds(self, standard_wall):
        """Staggered rows should clip to bounds, not extend past them."""
        standard_wall["wall_height"] = 16.0  # Force 2 rows
        generator = SheathingGenerator(
            standard_wall,
            config={"stagger_offset": 2.0},
            u_start_bound=-0.2,
            u_end_bound=12.2,
        )
        panels = generator.generate_sheathing()

        for p in panels:
            assert p.u_start >= -0.2 - 0.01
            assert p.u_end <= 12.2 + 0.01

    def test_extend_with_opening(self):
        """Bounds extension should work correctly with openings."""
        wall_data = {
            "wall_id": "wall_with_win",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "openings": [
                {
                    "opening_type": "window",
                    "start_u_coordinate": 4.0,
                    "rough_width": 3.0,
                    "base_elevation_relative_to_wall_base": 3.0,
                    "rough_height": 4.0,
                }
            ],
        }
        result = generate_wall_sheathing(
            wall_data, u_start_bound=-0.15, u_end_bound=12.15
        )
        panels = result["sheathing_panels"]

        # Panels should still have cutouts for the window
        panels_with_cutouts = [p for p in panels if p.get("cutouts")]
        assert len(panels_with_cutouts) > 0

        # And coverage should extend past wall length
        min_u = min(p["u_start"] for p in panels)
        max_u = max(p["u_end"] for p in panels)
        assert min_u == pytest.approx(-0.15, abs=0.01)
        assert max_u == pytest.approx(12.15, abs=0.01)
