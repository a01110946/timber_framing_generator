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


# =============================================================================
# Panel-Bounded Sheathing Tests
# =============================================================================


class TestPanelBoundedSheathing:
    """Tests for sheathing bounded to framing panel boundaries.

    When a wall is split into multiple framing panels, sheathing should
    be generated per-panel so sheets don't extend past panel joints.
    """

    @pytest.fixture
    def long_wall(self):
        """24 ft wall split into 2 panels at u=12."""
        return {
            "wall_id": "wall_24ft",
            "wall_length": 24.0,
            "wall_height": 8.0,
            "openings": [],
        }

    def test_panel_id_set_on_sheathing(self, long_wall):
        """Sheathing panels should have panel_id when generated per-panel."""
        panel_wall = dict(long_wall)
        panel_wall["panel_id"] = "wall_24ft_panel_0"

        result = generate_wall_sheathing(
            panel_wall,
            u_start_bound=0.0,
            u_end_bound=12.0,
        )

        for panel in result["sheathing_panels"]:
            assert panel["panel_id"] == "wall_24ft_panel_0"

    def test_sheathing_bounded_to_panel(self, long_wall):
        """Sheathing should not extend past panel u_end boundary."""
        panel_wall = dict(long_wall)
        panel_wall["panel_id"] = "wall_24ft_panel_0"

        result = generate_wall_sheathing(
            panel_wall,
            u_start_bound=0.0,
            u_end_bound=12.0,
        )

        for panel in result["sheathing_panels"]:
            assert panel["u_start"] >= 0.0 - 0.01
            assert panel["u_end"] <= 12.0 + 0.01

    def test_second_panel_starts_at_boundary(self, long_wall):
        """Second panel's sheathing should start at the panel boundary."""
        panel_wall = dict(long_wall)
        panel_wall["panel_id"] = "wall_24ft_panel_1"

        result = generate_wall_sheathing(
            panel_wall,
            u_start_bound=12.0,
            u_end_bound=24.0,
        )

        min_u = min(p["u_start"] for p in result["sheathing_panels"])
        assert min_u == pytest.approx(12.0, abs=0.01)

    def test_two_panels_cover_full_wall(self, long_wall):
        """Two panel-bounded results should cover the full wall length."""
        # Panel 0: u=[0, 12]
        p0_wall = dict(long_wall)
        p0_wall["panel_id"] = "wall_24ft_panel_0"
        r0 = generate_wall_sheathing(p0_wall, u_start_bound=0.0, u_end_bound=12.0)

        # Panel 1: u=[12, 24]
        p1_wall = dict(long_wall)
        p1_wall["panel_id"] = "wall_24ft_panel_1"
        r1 = generate_wall_sheathing(p1_wall, u_start_bound=12.0, u_end_bound=24.0)

        all_panels = r0["sheathing_panels"] + r1["sheathing_panels"]

        min_u = min(p["u_start"] for p in all_panels)
        max_u = max(p["u_end"] for p in all_panels)
        assert min_u == pytest.approx(0.0, abs=0.01)
        assert max_u == pytest.approx(24.0, abs=0.01)

    def test_no_sheathing_straddles_panel_boundary(self, long_wall):
        """No single sheathing panel should cross the panel boundary at u=12."""
        # Panel 0: u=[0, 12]
        p0_wall = dict(long_wall)
        p0_wall["panel_id"] = "wall_24ft_panel_0"
        r0 = generate_wall_sheathing(p0_wall, u_start_bound=0.0, u_end_bound=12.0)

        for panel in r0["sheathing_panels"]:
            assert panel["u_end"] <= 12.0 + 0.01, (
                "Panel 0 sheathing extends past boundary: u_end=%s" % panel["u_end"]
            )

        # Panel 1: u=[12, 24]
        p1_wall = dict(long_wall)
        p1_wall["panel_id"] = "wall_24ft_panel_1"
        r1 = generate_wall_sheathing(p1_wall, u_start_bound=12.0, u_end_bound=24.0)

        for panel in r1["sheathing_panels"]:
            assert panel["u_start"] >= 12.0 - 0.01, (
                "Panel 1 sheathing starts before boundary: u_start=%s" % panel["u_start"]
            )

    def test_panel_bounded_with_opening(self):
        """Openings should create cutouts only in their panel's sheathing."""
        wall_data = {
            "wall_id": "wall_with_win",
            "wall_length": 24.0,
            "wall_height": 8.0,
            "openings": [
                {
                    "opening_type": "window",
                    "start_u_coordinate": 5.0,
                    "rough_width": 3.0,
                    "base_elevation_relative_to_wall_base": 3.0,
                    "rough_height": 4.0,
                }
            ],
        }

        # Panel 0 (u=0 to 12) should have cutout for window at u=5
        p0 = dict(wall_data)
        p0["panel_id"] = "win_wall_panel_0"
        r0 = generate_wall_sheathing(p0, u_start_bound=0.0, u_end_bound=12.0)
        cutout_panels_0 = [p for p in r0["sheathing_panels"] if p.get("cutouts")]
        assert len(cutout_panels_0) > 0

        # Panel 1 (u=12 to 24) should NOT have cutouts (window is in panel 0)
        p1 = dict(wall_data)
        p1["panel_id"] = "win_wall_panel_1"
        r1 = generate_wall_sheathing(p1, u_start_bound=12.0, u_end_bound=24.0)
        cutout_panels_1 = [p for p in r1["sheathing_panels"] if p.get("cutouts")]
        assert len(cutout_panels_1) == 0

    def test_unbounded_sheathing_crosses_panel_boundary(self, long_wall):
        """Without bounds, a 4ft panel at u=8 extends to u=12, crossing u=10.

        Demonstrates why panel-bounded generation is needed: standard 4ft
        layout on a 24ft wall creates a panel [8,12] that crosses u=10.
        """
        result = generate_wall_sheathing(long_wall)
        panels = result["sheathing_panels"]

        # u=10 is NOT aligned with 4ft grid, so a panel must cross it
        crossing = [
            p for p in panels
            if p["u_start"] < 10.0 and p["u_end"] > 10.0
        ]
        assert len(crossing) > 0, "Expected unbounded sheathing to cross u=10"

    def test_panelized_sheathing_ids_unique_across_panels(self, long_wall):
        """Sheathing from different framing panels must have unique IDs.

        When a wall is split into panels, each panel generates sheathing
        with column=0 reset. Without a panel prefix in the ID, panels
        from different framing panels would collide (both start at
        column=0 with the same wall_id).
        """
        # Panel 0: u=[0, 12]
        p0_wall = dict(long_wall)
        p0_wall["panel_id"] = "wall_24ft_panel_0"
        r0 = generate_wall_sheathing(p0_wall, u_start_bound=0.0, u_end_bound=12.0)

        # Panel 1: u=[12, 24]
        p1_wall = dict(long_wall)
        p1_wall["panel_id"] = "wall_24ft_panel_1"
        r1 = generate_wall_sheathing(p1_wall, u_start_bound=12.0, u_end_bound=24.0)

        all_panels = r0["sheathing_panels"] + r1["sheathing_panels"]
        all_ids = [p["id"] for p in all_panels]

        # Every ID must be unique
        assert len(all_ids) == len(set(all_ids)), (
            "Duplicate sheathing panel IDs found across framing panels: %s"
            % [x for x in all_ids if all_ids.count(x) > 1]
        )

    def test_panelized_sheathing_ids_contain_panel_prefix(self, long_wall):
        """Sheathing IDs should contain a panel prefix when panel_id is set."""
        panel_wall = dict(long_wall)
        panel_wall["panel_id"] = "wall_24ft_panel_0"

        result = generate_wall_sheathing(
            panel_wall,
            u_start_bound=0.0,
            u_end_bound=12.0,
        )

        for panel in result["sheathing_panels"]:
            assert "_p0_" in panel["id"], (
                "Expected panel prefix '_p0_' in sheathing ID: %s" % panel["id"]
            )

    def test_unpanelized_sheathing_ids_no_prefix(self, long_wall):
        """Sheathing IDs should NOT have panel prefix when no panel_id."""
        result = generate_wall_sheathing(long_wall)

        for panel in result["sheathing_panels"]:
            assert "_p0_" not in panel["id"]
            assert "_p1_" not in panel["id"]

    def test_segmented_panel_id_generates_correct_prefix(self, long_wall):
        """Segmented panel IDs like '529398_seg0_panel_1' should produce '_p1_'."""
        panel_wall = dict(long_wall)
        panel_wall["panel_id"] = "529398_seg0_panel_1"

        result = generate_wall_sheathing(
            panel_wall,
            u_start_bound=0.0,
            u_end_bound=12.0,
        )

        for panel in result["sheathing_panels"]:
            assert "_p1_" in panel["id"], (
                "Expected '_p1_' prefix from segmented panel_id: %s" % panel["id"]
            )


# =============================================================================
# Multi-Segment ID Collision Tests
# =============================================================================


class TestMultiSegmentIdCollision:
    """Tests for segment_index parameter that prevents ID collisions.

    When a wall has midspan gaps (T-intersections, X-crossings), MLSheath
    splits the layer into multiple segments. Each segment creates a new
    SheathingGenerator with column=0. Without segment_index, panels from
    different segments get identical IDs.
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

    def test_two_segments_unique_ids(self, standard_wall):
        """Panels from two segments must have unique IDs."""
        # Segment 0: u=[0, 5]
        gen0 = SheathingGenerator(
            standard_wall,
            u_start_bound=0.0,
            u_end_bound=5.0,
            layer_name="OSB",
            segment_index=0,
        )
        panels0 = gen0.generate_sheathing(face="exterior")

        # Segment 1: u=[7, 12]  (gap at u=5..7 from T-intersection)
        gen1 = SheathingGenerator(
            standard_wall,
            u_start_bound=7.0,
            u_end_bound=12.0,
            layer_name="OSB",
            segment_index=1,
        )
        panels1 = gen1.generate_sheathing(face="exterior")

        all_ids = [p.id for p in panels0] + [p.id for p in panels1]
        assert len(all_ids) == len(set(all_ids)), (
            "Duplicate IDs across segments: %s"
            % [x for x in all_ids if all_ids.count(x) > 1]
        )

    def test_segment_tag_in_id(self, standard_wall):
        """Segment index should appear as '_s0_' or '_s1_' in panel IDs."""
        gen = SheathingGenerator(
            standard_wall,
            u_start_bound=0.0,
            u_end_bound=5.0,
            layer_name="OSB",
            segment_index=0,
        )
        panels = gen.generate_sheathing(face="exterior")

        for p in panels:
            assert "_s0_" in p.id, (
                "Expected '_s0_' segment tag in ID: %s" % p.id
            )

    def test_no_segment_tag_for_single_segment(self, standard_wall):
        """Single-segment walls (segment_index=None) should NOT have segment tag."""
        gen = SheathingGenerator(
            standard_wall,
            u_start_bound=0.0,
            u_end_bound=12.0,
            layer_name="OSB",
            segment_index=None,
        )
        panels = gen.generate_sheathing(face="exterior")

        for p in panels:
            assert "_s0_" not in p.id
            assert "_s1_" not in p.id

    def test_three_segments_all_unique(self, standard_wall):
        """Three segments (two gaps) should all produce unique IDs."""
        segments = [(0.0, 3.5), (4.5, 8.0), (9.0, 12.0)]
        all_ids = []

        for seg_idx, (u_start, u_end) in enumerate(segments):
            gen = SheathingGenerator(
                standard_wall,
                u_start_bound=u_start,
                u_end_bound=u_end,
                layer_name="OSB",
                segment_index=seg_idx,
            )
            panels = gen.generate_sheathing(face="exterior")
            all_ids.extend(p.id for p in panels)

        assert len(all_ids) == len(set(all_ids)), (
            "Duplicate IDs across 3 segments: %s"
            % [x for x in all_ids if all_ids.count(x) > 1]
        )

    def test_segment_plus_panel_prefix_combined(self, standard_wall):
        """Both panel and segment prefixes should coexist in the ID."""
        wall = dict(standard_wall)
        wall["panel_id"] = "wall_A_panel_0"

        gen = SheathingGenerator(
            wall,
            u_start_bound=0.0,
            u_end_bound=5.0,
            layer_name="OSB",
            segment_index=1,
        )
        panels = gen.generate_sheathing(face="exterior")

        for p in panels:
            assert "_p0_" in p.id, "Missing panel prefix: %s" % p.id
            assert "_s1_" in p.id, "Missing segment tag: %s" % p.id

    def test_without_segment_index_ids_collide(self, standard_wall):
        """Without segment_index, two segments produce colliding IDs.

        This is the bug we fixed: demonstrates that segment_index=None
        on both generators causes duplicate IDs.
        """
        # Both segments use segment_index=None (the old behavior)
        gen0 = SheathingGenerator(
            standard_wall,
            u_start_bound=0.0,
            u_end_bound=4.0,
            layer_name="OSB",
            segment_index=None,
        )
        panels0 = gen0.generate_sheathing(face="exterior")

        gen1 = SheathingGenerator(
            standard_wall,
            u_start_bound=8.0,
            u_end_bound=12.0,
            layer_name="OSB",
            segment_index=None,
        )
        panels1 = gen1.generate_sheathing(face="exterior")

        ids0 = {p.id for p in panels0}
        ids1 = {p.id for p in panels1}

        # Without segment_index, both have column=0 panels with same base ID
        assert ids0 & ids1, (
            "Expected ID collision without segment_index, but IDs were unique. "
            "This test documents the bug that segment_index fixes."
        )


# =============================================================================
# Embedded Panels Fallback Tests
# =============================================================================


class TestEmbeddedPanelsFallback:
    """Tests for the embedded panels fallback mechanism.

    When walls_json contains a 'panels' key (from enriched walls_json),
    MLSheath should use those panels for panel-bounded sheathing without
    needing a separate panels_json input.
    """

    def test_embedded_panels_triggers_panelized_ids(self):
        """Wall data with 'panels' key produces sheathing with panel_id set
        and unique IDs across panels."""
        wall_data = {
            "wall_id": "w1",
            "wall_length": 24.0,
            "wall_height": 8.0,
            "openings": [],
            "panels": [
                {"id": "w1_panel_0", "u_start": 0.0, "u_end": 12.0},
                {"id": "w1_panel_1", "u_start": 12.0, "u_end": 24.0},
            ],
        }

        all_sheathing = []
        for panel in wall_data["panels"]:
            panel_wall = dict(wall_data)
            panel_wall["panel_id"] = panel["id"]
            result = generate_wall_sheathing(
                panel_wall,
                u_start_bound=panel["u_start"],
                u_end_bound=panel["u_end"],
            )
            all_sheathing.extend(result["sheathing_panels"])

        # All panels should have panel_id set
        for p in all_sheathing:
            assert p.get("panel_id") is not None, (
                "Expected panel_id on sheathing panel: %s" % p["id"]
            )

        # All IDs should be unique across panels
        all_ids = [p["id"] for p in all_sheathing]
        assert len(all_ids) == len(set(all_ids)), (
            "Duplicate sheathing IDs across embedded panels: %s"
            % [x for x in all_ids if all_ids.count(x) > 1]
        )

    def test_embedded_panels_empty_list_ignored(self):
        """'panels': [] should NOT trigger the panelized path."""
        embedded = []
        # This is the exact condition from process_walls()
        triggers = embedded and isinstance(embedded, list) and len(embedded) > 0
        assert not triggers, "Empty panels list should not trigger panelized path"

    def test_embedded_panels_none_ignored(self):
        """'panels': None should NOT trigger the panelized path."""
        embedded = None
        triggers = embedded and isinstance(embedded, list) and len(embedded) > 0
        assert not triggers, "None panels should not trigger panelized path"

    def test_parse_panels_json_format(self):
        """Panel Decomposer output format should parse into wall_id -> panels map."""
        # Simulates what Panel Decomposer outputs
        panel_decomposer_output = [
            {
                "wall_id": "w1",
                "panels": [
                    {"id": "w1_panel_0", "u_start": 0.0, "u_end": 12.0},
                    {"id": "w1_panel_1", "u_start": 12.0, "u_end": 24.0},
                ],
                "joints": [],
            },
            {
                "wall_id": "w2",
                "panels": [
                    {"id": "w2_panel_0", "u_start": 0.0, "u_end": 10.0},
                ],
                "joints": [],
            },
        ]

        # Replicate parse_panels_json logic (from gh_multi_layer_sheathing.py)
        result = {}
        for wall_result in panel_decomposer_output:
            if not isinstance(wall_result, dict):
                continue
            wall_id = str(wall_result.get("wall_id", ""))
            panels = wall_result.get("panels", [])
            if wall_id and panels:
                result[wall_id] = sorted(
                    panels, key=lambda p: p.get("u_start", 0)
                )

        assert "w1" in result
        assert "w2" in result
        assert len(result["w1"]) == 2
        assert len(result["w2"]) == 1
        assert result["w1"][0]["u_start"] == 0.0
        assert result["w1"][1]["u_start"] == 12.0

    def test_embedded_panels_sheathing_respects_bounds(self):
        """Sheathing generated per embedded panel should stay within panel bounds."""
        wall_data = {
            "wall_id": "w1",
            "wall_length": 24.0,
            "wall_height": 8.0,
            "openings": [],
            "panels": [
                {"id": "w1_panel_0", "u_start": 0.0, "u_end": 12.0},
                {"id": "w1_panel_1", "u_start": 12.0, "u_end": 24.0},
            ],
        }

        for panel in wall_data["panels"]:
            panel_wall = dict(wall_data)
            panel_wall["panel_id"] = panel["id"]
            result = generate_wall_sheathing(
                panel_wall,
                u_start_bound=panel["u_start"],
                u_end_bound=panel["u_end"],
            )
            for sp in result["sheathing_panels"]:
                assert sp["u_start"] >= panel["u_start"] - 0.01, (
                    "Sheathing %s starts before panel bound %.2f: u_start=%.2f"
                    % (sp["id"], panel["u_start"], sp["u_start"])
                )
                assert sp["u_end"] <= panel["u_end"] + 0.01, (
                    "Sheathing %s extends past panel bound %.2f: u_end=%.2f"
                    % (sp["id"], panel["u_end"], sp["u_end"])
                )
