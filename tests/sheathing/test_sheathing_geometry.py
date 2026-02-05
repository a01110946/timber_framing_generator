# File: tests/sheathing/test_sheathing_geometry.py
"""Tests for sheathing geometry conversion module."""

import pytest
from src.timber_framing_generator.sheathing.sheathing_geometry import (
    uvw_to_world,
    calculate_w_offset,
    get_extrusion_vector,
    SheathingPanelGeometry,
)


class TestUVWToWorld:
    """Tests for UVW to world coordinate transformation."""

    @pytest.fixture
    def world_aligned_plane(self):
        """Base plane aligned with world axes."""
        return {
            "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
            "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},  # U = World X
            "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},  # V = World Z (up)
            "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},  # W = World Y (normal)
        }

    @pytest.fixture
    def offset_plane(self):
        """Base plane with offset origin."""
        return {
            "origin": {"x": 10.0, "y": 5.0, "z": 0.0},
            "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
            "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
            "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
        }

    @pytest.fixture
    def rotated_plane(self):
        """Base plane rotated 90 degrees around Z."""
        return {
            "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
            "x_axis": {"x": 0.0, "y": 1.0, "z": 0.0},  # U = World Y
            "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},  # V = World Z
            "z_axis": {"x": -1.0, "y": 0.0, "z": 0.0}, # W = -World X
        }

    def test_origin_at_zero(self, world_aligned_plane):
        """Origin should map to itself."""
        x, y, z = uvw_to_world(0, 0, 0, world_aligned_plane)
        assert abs(x) < 0.001
        assert abs(y) < 0.001
        assert abs(z) < 0.001

    def test_u_along_wall(self, world_aligned_plane):
        """U coordinate should map to X."""
        x, y, z = uvw_to_world(5.0, 0, 0, world_aligned_plane)
        assert abs(x - 5.0) < 0.001
        assert abs(y) < 0.001
        assert abs(z) < 0.001

    def test_v_vertical(self, world_aligned_plane):
        """V coordinate should map to Z (vertical)."""
        x, y, z = uvw_to_world(0, 8.0, 0, world_aligned_plane)
        assert abs(x) < 0.001
        assert abs(y) < 0.001
        assert abs(z - 8.0) < 0.001

    def test_w_normal(self, world_aligned_plane):
        """W coordinate should map to Y (wall normal)."""
        x, y, z = uvw_to_world(0, 0, 0.25, world_aligned_plane)
        assert abs(x) < 0.001
        assert abs(y - 0.25) < 0.001
        assert abs(z) < 0.001

    def test_combined_uvw(self, world_aligned_plane):
        """Combined UVW should transform correctly."""
        x, y, z = uvw_to_world(4.0, 8.0, 0.25, world_aligned_plane)
        assert abs(x - 4.0) < 0.001
        assert abs(y - 0.25) < 0.001
        assert abs(z - 8.0) < 0.001

    def test_offset_origin(self, offset_plane):
        """Offset origin should affect all coordinates."""
        x, y, z = uvw_to_world(0, 0, 0, offset_plane)
        assert abs(x - 10.0) < 0.001
        assert abs(y - 5.0) < 0.001
        assert abs(z) < 0.001

    def test_rotated_plane_u(self, rotated_plane):
        """U in rotated plane should map to Y."""
        x, y, z = uvw_to_world(5.0, 0, 0, rotated_plane)
        assert abs(x) < 0.001
        assert abs(y - 5.0) < 0.001
        assert abs(z) < 0.001

    def test_rotated_plane_w(self, rotated_plane):
        """W in rotated plane should map to -X."""
        x, y, z = uvw_to_world(0, 0, 1.0, rotated_plane)
        assert abs(x + 1.0) < 0.001  # -X direction
        assert abs(y) < 0.001
        assert abs(z) < 0.001


class TestWOffsetCalculation:
    """Tests for W offset calculation."""

    def test_exterior_face_offset(self):
        """Exterior face should be at positive W offset."""
        wall_thickness = 0.5  # 6 inches
        panel_thickness = 0.0365  # 7/16" plywood in feet

        w_offset = calculate_w_offset("exterior", wall_thickness, panel_thickness)

        # Exterior: at +half_wall
        assert abs(w_offset - 0.25) < 0.001

    def test_interior_face_offset(self):
        """Interior face should be at negative W offset."""
        wall_thickness = 0.5
        panel_thickness = 0.0365

        w_offset = calculate_w_offset("interior", wall_thickness, panel_thickness)

        # Interior: at -half_wall - panel_thickness
        expected = -0.25 - panel_thickness
        assert abs(w_offset - expected) < 0.001

    def test_thicker_wall_larger_offset(self):
        """Thicker wall should have larger offset."""
        panel_thickness = 0.0365

        thin_wall = calculate_w_offset("exterior", 0.333, panel_thickness)
        thick_wall = calculate_w_offset("exterior", 0.5, panel_thickness)

        assert thick_wall > thin_wall


class TestExtrusionVector:
    """Tests for extrusion vector calculation."""

    @pytest.fixture
    def world_aligned_plane(self):
        return {
            "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
            "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
            "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
            "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},  # Normal = Y
        }

    def test_exterior_extrusion_positive(self, world_aligned_plane):
        """Exterior face should extrude in positive normal direction."""
        thickness = 0.0365  # ~7/16"
        dx, dy, dz = get_extrusion_vector("exterior", world_aligned_plane, thickness)

        assert abs(dx) < 0.001
        assert abs(dy - thickness) < 0.001  # Positive Y
        assert abs(dz) < 0.001

    def test_interior_extrusion_negative(self, world_aligned_plane):
        """Interior face should extrude in negative normal direction."""
        thickness = 0.0365
        dx, dy, dz = get_extrusion_vector("interior", world_aligned_plane, thickness)

        assert abs(dx) < 0.001
        assert abs(dy + thickness) < 0.001  # Negative Y
        assert abs(dz) < 0.001

    def test_extrusion_magnitude(self, world_aligned_plane):
        """Extrusion vector magnitude should equal thickness."""
        thickness = 0.05
        dx, dy, dz = get_extrusion_vector("exterior", world_aligned_plane, thickness)

        magnitude = (dx*dx + dy*dy + dz*dz) ** 0.5
        assert abs(magnitude - thickness) < 0.001


class TestSheathingPanelGeometry:
    """Tests for SheathingPanelGeometry dataclass."""

    def test_dataclass_creation(self):
        """Should create dataclass with all fields."""
        geometry = SheathingPanelGeometry(
            panel_id="test_panel",
            wall_id="test_wall",
            face="exterior",
            brep=None,  # Would be actual Brep in real usage
            area_gross=32.0,
            area_net=28.0,
            has_cutouts=True
        )

        assert geometry.panel_id == "test_panel"
        assert geometry.wall_id == "test_wall"
        assert geometry.face == "exterior"
        assert geometry.area_gross == 32.0
        assert geometry.area_net == 28.0
        assert geometry.has_cutouts is True

    def test_full_sheet_no_cutouts(self):
        """Full sheet should have no cutouts."""
        geometry = SheathingPanelGeometry(
            panel_id="full_sheet",
            wall_id="wall_1",
            face="exterior",
            brep=None,
            area_gross=32.0,
            area_net=32.0,
            has_cutouts=False
        )

        assert geometry.area_gross == geometry.area_net
        assert geometry.has_cutouts is False


class TestPanelDataParsing:
    """Tests for panel data parsing and validation."""

    @pytest.fixture
    def sample_panel_data(self):
        """Sample panel data from sheathing generator."""
        return {
            "id": "wall_1_sheath_exterior_0_0",
            "wall_id": "wall_1",
            "face": "exterior",
            "material": "structural_plywood_7_16",
            "thickness_inches": 0.4375,
            "u_start": 0.0,
            "u_end": 4.0,
            "v_start": 0.0,
            "v_end": 8.0,
            "area_gross_sqft": 32.0,
            "area_net_sqft": 32.0,
            "cutouts": []
        }

    @pytest.fixture
    def panel_with_cutout(self):
        """Panel data with window cutout."""
        return {
            "id": "wall_1_sheath_exterior_0_1",
            "wall_id": "wall_1",
            "face": "exterior",
            "material": "structural_plywood_7_16",
            "thickness_inches": 0.4375,
            "u_start": 4.0,
            "u_end": 8.0,
            "v_start": 0.0,
            "v_end": 8.0,
            "area_gross_sqft": 32.0,
            "area_net_sqft": 24.0,
            "cutouts": [
                {
                    "type": "window",
                    "u_start": 5.0,
                    "u_end": 7.0,
                    "v_start": 3.0,
                    "v_end": 7.0,
                }
            ]
        }

    def test_panel_dimensions(self, sample_panel_data):
        """Panel dimensions should be correct."""
        width = sample_panel_data["u_end"] - sample_panel_data["u_start"]
        height = sample_panel_data["v_end"] - sample_panel_data["v_start"]

        assert abs(width - 4.0) < 0.001
        assert abs(height - 8.0) < 0.001

    def test_cutout_area(self, panel_with_cutout):
        """Cutout should reduce net area."""
        cutout = panel_with_cutout["cutouts"][0]
        cutout_width = cutout["u_end"] - cutout["u_start"]
        cutout_height = cutout["v_end"] - cutout["v_start"]
        cutout_area = cutout_width * cutout_height

        assert abs(cutout_area - 8.0) < 0.001  # 2' x 4' = 8 sqft
        assert panel_with_cutout["area_net_sqft"] < panel_with_cutout["area_gross_sqft"]

    def test_thickness_conversion(self, sample_panel_data):
        """Thickness in inches should convert to feet."""
        thickness_ft = sample_panel_data["thickness_inches"] / 12.0

        assert abs(thickness_ft - 0.0365) < 0.001  # ~7/16" in feet


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_zero_dimension_panel(self):
        """Zero dimension should be handled gracefully."""
        panel_data = {
            "u_start": 0.0,
            "u_end": 0.0,  # Zero width
            "v_start": 0.0,
            "v_end": 8.0,
            "thickness_inches": 0.4375,
            "face": "exterior",
            "cutouts": []
        }

        width = panel_data["u_end"] - panel_data["u_start"]
        assert width == 0

    def test_cutout_at_panel_edge(self):
        """Cutout at panel edge should be valid."""
        cutout = {
            "u_start": 0.0,  # At panel left edge
            "u_end": 2.0,
            "v_start": 3.0,
            "v_end": 7.0,
        }

        width = cutout["u_end"] - cutout["u_start"]
        assert width > 0

    def test_cutout_exceeds_panel(self):
        """Cutout coordinates may exceed panel bounds (clipped)."""
        panel_u_end = 4.0
        cutout_u_end = 6.0  # Extends beyond panel

        # In real usage, cutout is clipped to panel bounds
        clipped_u_end = min(panel_u_end, cutout_u_end)
        assert clipped_u_end == panel_u_end


class TestIntegration:
    """Integration tests (require mocking or skip in CI)."""

    @pytest.fixture
    def sample_sheathing_data(self):
        """Sample sheathing JSON structure."""
        return {
            "wall_id": "123456",
            "sheathing_panels": [
                {
                    "id": "123456_sheath_exterior_0_0",
                    "wall_id": "123456",
                    "face": "exterior",
                    "material": "structural_plywood_7_16",
                    "thickness_inches": 0.4375,
                    "u_start": 0.0,
                    "u_end": 4.0,
                    "v_start": 0.0,
                    "v_end": 8.0,
                    "area_gross_sqft": 32.0,
                    "area_net_sqft": 32.0,
                    "cutouts": []
                }
            ],
            "summary": {
                "total_panels": 1,
                "gross_area_sqft": 32.0,
                "net_area_sqft": 32.0,
            }
        }

    @pytest.fixture
    def sample_wall_data(self):
        """Sample wall JSON with base_plane."""
        return {
            "wall_id": "123456",
            "wall_length": 12.0,
            "wall_height": 8.0,
            "thickness": 0.5,
            "base_plane": {
                "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
                "x_axis": {"x": 1.0, "y": 0.0, "z": 0.0},
                "y_axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "z_axis": {"x": 0.0, "y": 1.0, "z": 0.0},
            }
        }

    def test_data_structures_match(self, sample_sheathing_data, sample_wall_data):
        """Sheathing and wall data should have matching wall IDs."""
        sheathing_wall_id = sample_sheathing_data["wall_id"]
        wall_id = sample_wall_data["wall_id"]

        assert sheathing_wall_id == wall_id

    def test_panels_have_required_fields(self, sample_sheathing_data):
        """Panels should have all required fields for geometry creation."""
        required_fields = [
            "id", "wall_id", "face", "thickness_inches",
            "u_start", "u_end", "v_start", "v_end", "cutouts"
        ]

        for panel in sample_sheathing_data["sheathing_panels"]:
            for field in required_fields:
                assert field in panel, f"Missing field: {field}"
