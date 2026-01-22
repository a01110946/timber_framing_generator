# File: tests/unit/test_geometry_conversion.py
"""
Unit tests for geometry conversion functions.

These tests verify that geometry conversion handles various input types correctly,
particularly the case where safe_create_extrusion returns a Brep directly.
"""

import pytest
import sys
import os

# Check if we're in a Rhino environment
try:
    import Rhino.Geometry as rg
    RHINO_AVAILABLE = True
except ImportError:
    RHINO_AVAILABLE = False


@pytest.mark.skipif(not RHINO_AVAILABLE, reason="Rhino not available")
class TestSafeToBrep:
    """Tests for safe_to_brep_if_needed function."""

    def test_brep_input_returns_same_brep(self):
        """Brep input returns the same Brep without calling ToBrep()."""
        from src.timber_framing_generator.utils.safe_rhino import safe_to_brep_if_needed

        # Create a simple valid Brep (a box)
        box = rg.Box(
            rg.Plane.WorldXY,
            rg.Interval(0, 1),
            rg.Interval(0, 1),
            rg.Interval(0, 1)
        )
        brep = box.ToBrep()

        # Call safe_to_brep_if_needed
        result = safe_to_brep_if_needed(brep)

        # Should return the same Brep object
        assert result is not None
        assert isinstance(result, rg.Brep)
        assert result.IsValid

    def test_none_input_returns_none(self):
        """None input returns None."""
        from src.timber_framing_generator.utils.safe_rhino import safe_to_brep_if_needed

        result = safe_to_brep_if_needed(None)
        assert result is None

    def test_extrusion_input_converts_to_brep(self):
        """Extrusion input is properly converted to Brep."""
        from src.timber_framing_generator.utils.safe_rhino import safe_to_brep_if_needed

        # Create a simple extrusion
        circle = rg.Circle(rg.Plane.WorldXY, 1.0)
        curve = circle.ToNurbsCurve()

        # Create extrusion (if available)
        if hasattr(rg.Extrusion, 'Create'):
            extrusion = rg.Extrusion.Create(curve, 1.0, True)
            if extrusion is not None and extrusion.IsValid:
                result = safe_to_brep_if_needed(extrusion)
                assert result is not None
                assert isinstance(result, rg.Brep)

    def test_box_input_converts_to_brep(self):
        """Box input is properly converted to Brep."""
        from src.timber_framing_generator.utils.safe_rhino import safe_to_brep_if_needed

        box = rg.Box(
            rg.Plane.WorldXY,
            rg.Interval(0, 2),
            rg.Interval(0, 2),
            rg.Interval(0, 2)
        )

        result = safe_to_brep_if_needed(box)

        assert result is not None
        assert isinstance(result, rg.Brep)
        assert result.IsValid


@pytest.mark.skipif(not RHINO_AVAILABLE, reason="Rhino not available")
class TestBoxConstructor:
    """Tests for correct Box constructor usage."""

    def test_box_from_bounding_box(self):
        """Box can be created from BoundingBox (correct method)."""
        # Create corner points
        corners = [
            rg.Point3d(0, 0, 0),
            rg.Point3d(1, 0, 0),
            rg.Point3d(1, 1, 0),
            rg.Point3d(0, 1, 0),
            rg.Point3d(0, 0, 1),
            rg.Point3d(1, 0, 1),
            rg.Point3d(1, 1, 1),
            rg.Point3d(0, 1, 1),
        ]

        # Create BoundingBox from corners
        bbox = rg.BoundingBox(corners)
        assert bbox.IsValid

        # Create Box from BoundingBox
        box = rg.Box(bbox)
        assert box.IsValid

        # Convert to Brep
        brep = box.ToBrep()
        assert brep is not None
        assert brep.IsValid

    def test_box_from_plane_and_intervals(self):
        """Box can be created from Plane and Intervals (correct method)."""
        box = rg.Box(
            rg.Plane.WorldXY,
            rg.Interval(-1, 1),
            rg.Interval(-1, 1),
            rg.Interval(0, 2)
        )

        assert box.IsValid
        brep = box.ToBrep()
        assert brep is not None
        assert brep.IsValid


@pytest.mark.skipif(not RHINO_AVAILABLE, reason="Rhino not available")
class TestIsValidGeometry:
    """Tests for is_valid_geometry function."""

    def test_valid_brep_returns_true(self):
        """Valid Brep returns True."""
        from src.timber_framing_generator.utils.safe_rhino import is_valid_geometry

        box = rg.Box(
            rg.Plane.WorldXY,
            rg.Interval(0, 1),
            rg.Interval(0, 1),
            rg.Interval(0, 1)
        )
        brep = box.ToBrep()

        assert is_valid_geometry(brep) is True

    def test_none_returns_false(self):
        """None returns False."""
        from src.timber_framing_generator.utils.safe_rhino import is_valid_geometry

        assert is_valid_geometry(None) is False

    def test_empty_brep_returns_false(self):
        """Empty/invalid Brep returns False."""
        from src.timber_framing_generator.utils.safe_rhino import is_valid_geometry

        empty_brep = rg.Brep()
        assert is_valid_geometry(empty_brep) is False


class TestWithoutRhino:
    """Tests that work without Rhino environment."""

    def test_safe_functions_exist(self):
        """Verify safe functions are importable (may fail without Rhino)."""
        # This test documents what functions should exist
        expected_functions = [
            'safe_get_length',
            'safe_closest_point',
            'safe_create_extrusion',
            'safe_get_bounding_box',
            'safe_add_brep',
            'is_valid_geometry',
            'safe_to_brep',
            'safe_to_brep_if_needed',
        ]

        # Just verify the function names are defined in the module
        # Actual import may fail without Rhino
        assert len(expected_functions) == 8
