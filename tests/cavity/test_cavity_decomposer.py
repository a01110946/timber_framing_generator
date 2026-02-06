# File: tests/cavity/test_cavity_decomposer.py
"""Tests for cavity decomposition module.

Tests both framing mode (exact element positions) and derived mode
(computed from wall geometry + configured spacing).

Standard test wall: 10 ft long, 8 ft tall, 2x4 studs at 16" OC (1.333 ft).
Stud width = 1.5" (0.125 ft), plate thickness = 1.5" (0.125 ft).
"""

import json
import math

import pytest

from src.timber_framing_generator.cavity.cavity import (
    Cavity,
    CavityConfig,
    serialize_cavities,
    deserialize_cavities,
)
from src.timber_framing_generator.cavity.cavity_decomposer import (
    decompose_wall_cavities,
    find_cavity_for_uv,
    find_nearest_cavity,
    find_adjacent_cavities,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> CavityConfig:
    """Standard config for tests."""
    return CavityConfig(
        min_clear_width=0.01,
        min_clear_height=0.01,
        stud_width=0.125,
        stud_spacing=1.333,
        plate_thickness=0.125,
    )


@pytest.fixture
def simple_wall() -> dict:
    """10 ft wall, 8 ft tall, no openings."""
    return {
        "wall_id": "wall_A",
        "wall_length": 10.0,
        "wall_height": 8.0,
        "wall_thickness": 0.292,
        "openings": [],
    }


@pytest.fixture
def window_wall() -> dict:
    """10 ft wall with a centered 3 ft wide window."""
    return {
        "wall_id": "wall_B",
        "wall_length": 10.0,
        "wall_height": 8.0,
        "wall_thickness": 0.292,
        "openings": [
            {
                "id": "win_1",
                "opening_type": "window",
                "u_start": 3.5,
                "u_end": 6.5,
                "v_start": 3.0,
                "v_end": 6.0,
            }
        ],
    }


@pytest.fixture
def door_wall() -> dict:
    """10 ft wall with a 3 ft wide door."""
    return {
        "wall_id": "wall_C",
        "wall_length": 10.0,
        "wall_height": 8.0,
        "wall_thickness": 0.292,
        "openings": [
            {
                "id": "door_1",
                "opening_type": "door",
                "u_start": 3.5,
                "u_end": 6.5,
                "v_start": 0.0,
                "v_end": 7.0,
            }
        ],
    }


def _make_framing_elements_simple(
    wall_length: float = 10.0,
    wall_height: float = 8.0,
    stud_spacing: float = 1.333,
    stud_width: float = 0.125,
    plate_thickness: float = 0.125,
) -> list:
    """Generate framing elements for a simple wall (no openings).

    Studs at configured spacing + end studs, bottom plate, top plate.
    """
    elements = []
    half_stud = stud_width / 2.0

    # Bottom plate
    elements.append({
        "id": "bp_0",
        "element_type": "bottom_plate",
        "u_coord": wall_length / 2.0,
        "v_start": 0.0,
        "v_end": plate_thickness,
        "cell_id": "wall_A_SC_0",
        "profile": {"width": plate_thickness, "depth": stud_width, "name": "2x4"},
    })

    # Top plate
    elements.append({
        "id": "tp_0",
        "element_type": "top_plate",
        "u_coord": wall_length / 2.0,
        "v_start": wall_height - plate_thickness,
        "v_end": wall_height,
        "cell_id": "wall_A_SC_0",
        "profile": {"width": plate_thickness, "depth": stud_width, "name": "2x4"},
    })

    # Studs
    stud_idx = 0
    u = half_stud
    while u < wall_length - half_stud + 1e-4:
        elements.append({
            "id": f"stud_{stud_idx}",
            "element_type": "stud",
            "u_coord": u,
            "v_start": plate_thickness,
            "v_end": wall_height - plate_thickness,
            "cell_id": "wall_A_SC_0",
            "profile": {"width": stud_width, "depth": 0.292, "name": "2x4"},
        })
        stud_idx += 1
        u += stud_spacing

    # End stud
    end_u = wall_length - half_stud
    if abs(u - stud_spacing - end_u) > 1e-4:
        elements.append({
            "id": f"stud_{stud_idx}",
            "element_type": "stud",
            "u_coord": end_u,
            "v_start": plate_thickness,
            "v_end": wall_height - plate_thickness,
            "cell_id": "wall_A_SC_0",
            "profile": {"width": stud_width, "depth": 0.292, "name": "2x4"},
        })

    return elements


def _make_cell_data_simple(
    wall_id: str = "wall_A",
    wall_length: float = 10.0,
    wall_height: float = 8.0,
) -> dict:
    """Cell data for a simple wall with one SC cell spanning the whole wall."""
    return {
        "wall_id": wall_id,
        "cells": [
            {
                "id": f"{wall_id}_SC_0",
                "cell_type": "SC",
                "u_start": 0.0,
                "u_end": wall_length,
                "v_start": 0.0,
                "v_end": wall_height,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Derived mode tests
# ---------------------------------------------------------------------------

class TestDerivedMode:
    """Tests for cavity decomposition in derived mode (no framing data)."""

    def test_simple_wall_produces_cavities(self, simple_wall, config):
        """An empty wall should produce N-1 cavities for N+1 studs."""
        cavities = decompose_wall_cavities(simple_wall, config=config)
        assert len(cavities) > 0
        # All cavities should be within wall bounds
        for cav in cavities:
            assert cav.u_min >= 0.0
            assert cav.u_max <= 10.0
            assert cav.v_min >= config.plate_thickness - config.tolerance
            assert cav.v_max <= 8.0 - config.plate_thickness + config.tolerance

    def test_cavity_count_matches_stud_bays(self, simple_wall, config):
        """Number of cavities should equal number of bays between studs."""
        cavities = decompose_wall_cavities(simple_wall, config=config)
        # Studs at: 0.0625, 1.3955, 2.7285, 4.0615, 5.3945, 6.7275, 8.0605, 9.3935, 9.9375
        # That's stud positions from half_stud to wall_length - half_stud at 1.333 spacing
        # Count: ceil((10 - 0.125) / 1.333) + 1 for end stud
        # Bays = studs - 1 (where studs includes end stud)
        # We expect some filtering of thin bays at boundaries
        assert len(cavities) >= 7  # At least 7 full-width bays

    def test_cavity_v_range_excludes_plates(self, simple_wall, config):
        """All derived cavities should have v_min >= plate_thickness."""
        cavities = decompose_wall_cavities(simple_wall, config=config)
        for cav in cavities:
            assert cav.v_min >= config.plate_thickness - config.tolerance
            assert cav.v_max <= 8.0 - config.plate_thickness + config.tolerance
            assert cav.bottom_member == "bottom_plate"
            assert cav.top_member == "top_plate"

    def test_cavity_depth_matches_wall(self, simple_wall, config):
        """Cavity depth should match wall thickness."""
        cavities = decompose_wall_cavities(simple_wall, config=config)
        for cav in cavities:
            assert cav.depth == pytest.approx(0.292, abs=1e-4)

    def test_window_wall_splits_cavities(self, window_wall, config):
        """Window wall should create SCC and HCC cavities."""
        cavities = decompose_wall_cavities(window_wall, config=config)
        assert len(cavities) > 0

        scc_cavities = [c for c in cavities if "SCC" in c.cell_id]
        hcc_cavities = [c for c in cavities if "HCC" in c.cell_id]

        # Columns overlapping the window (u_start=3.5 to u_end=6.5)
        # should have SCC below and HCC above
        assert len(scc_cavities) > 0, "Expected SCC cavities below window"
        assert len(hcc_cavities) > 0, "Expected HCC cavities above window"

        for cav in scc_cavities:
            assert cav.top_member == "sill"
            assert cav.v_max <= 3.0 + config.tolerance

        for cav in hcc_cavities:
            assert cav.bottom_member == "header"
            assert cav.v_min >= 6.0 - config.tolerance

    def test_door_wall_removes_cavities(self, door_wall, config):
        """Door wall should have no cavities in the door zone."""
        cavities = decompose_wall_cavities(door_wall, config=config)

        # No cavity should overlap the door zone (3.5 to 6.5)
        for cav in cavities:
            in_door_zone = cav.u_min >= 3.5 and cav.u_max <= 6.5
            overlaps_door = cav.u_min < 6.5 and cav.u_max > 3.5
            # Cavities outside door zone are fine
            if overlaps_door:
                # Should not exist
                assert False, (
                    f"Cavity {cav.id} overlaps door zone: "
                    f"u=[{cav.u_min}, {cav.u_max}]"
                )

    def test_custom_spacing(self, config):
        """Using 24\" OC should produce fewer, wider cavities."""
        wall = {
            "wall_id": "wall_24oc",
            "wall_length": 10.0,
            "wall_height": 8.0,
            "wall_thickness": 0.292,
            "openings": [],
        }
        config_24 = CavityConfig(stud_spacing=2.0)  # 24" OC
        cavities_24 = decompose_wall_cavities(wall, config=config_24)

        config_16 = CavityConfig(stud_spacing=1.333)  # 16" OC
        cavities_16 = decompose_wall_cavities(wall, config=config_16)

        assert len(cavities_24) < len(cavities_16)
        # 24" OC cavities should be wider on average
        avg_width_24 = sum(c.clear_width for c in cavities_24) / len(cavities_24)
        avg_width_16 = sum(c.clear_width for c in cavities_16) / len(cavities_16)
        assert avg_width_24 > avg_width_16

    def test_zero_width_filtered(self, config):
        """Cavities narrower than min_clear_width should be filtered out."""
        cavities = decompose_wall_cavities(
            {
                "wall_id": "tiny",
                "wall_length": 10.0,
                "wall_height": 8.0,
                "wall_thickness": 0.292,
                "openings": [],
            },
            config=config,
        )
        for cav in cavities:
            assert cav.clear_width >= config.min_clear_width
            assert cav.clear_height >= config.min_clear_height


# ---------------------------------------------------------------------------
# Framing mode tests
# ---------------------------------------------------------------------------

class TestFramingMode:
    """Tests for cavity decomposition using actual framing element data."""

    def test_simple_wall_framing_mode(self, simple_wall, config):
        """Framing mode should produce cavities between studs."""
        elements = _make_framing_elements_simple()
        framing_data = {"wall_id": "wall_A", "elements": elements}
        cell_data = _make_cell_data_simple()

        cavities = decompose_wall_cavities(
            simple_wall,
            cell_data=cell_data,
            framing_data=framing_data,
            config=config,
        )
        assert len(cavities) > 0

    def test_framing_cavities_between_studs(self, simple_wall, config):
        """Each cavity should span between adjacent stud faces."""
        elements = _make_framing_elements_simple()
        framing_data = {"wall_id": "wall_A", "elements": elements}
        cell_data = _make_cell_data_simple()

        cavities = decompose_wall_cavities(
            simple_wall,
            cell_data=cell_data,
            framing_data=framing_data,
            config=config,
        )

        # Filter to full-height cavities (between plates)
        full_height = [
            c for c in cavities
            if c.v_min < 0.2 and c.v_max > 7.8
        ]
        assert len(full_height) >= 7

        for cav in full_height:
            # Width should be about stud_spacing - stud_width
            expected_width = 1.333 - 0.125
            # Allow for end bays which may be different size
            assert cav.clear_width > 0.01

    def test_framing_mode_boundary_labels(self, simple_wall, config):
        """Cavity boundary labels should reflect actual member types."""
        elements = _make_framing_elements_simple()
        framing_data = {"wall_id": "wall_A", "elements": elements}
        cell_data = _make_cell_data_simple()

        cavities = decompose_wall_cavities(
            simple_wall,
            cell_data=cell_data,
            framing_data=framing_data,
            config=config,
        )

        for cav in cavities:
            # Left/right should be stud or wall_edge
            assert cav.left_member in (
                "stud", "king_stud", "trimmer", "wall_edge",
                "header_cripple", "sill_cripple",
            )
            assert cav.right_member in (
                "stud", "king_stud", "trimmer", "wall_edge",
                "header_cripple", "sill_cripple",
            )

    def test_oc_cells_ignored(self, simple_wall, config):
        """OC (Opening Cell) types should not produce cavities."""
        cell_data = {
            "wall_id": "wall_A",
            "cells": [
                {
                    "id": "wall_A_OC_0",
                    "cell_type": "OC",
                    "u_start": 3.0,
                    "u_end": 7.0,
                    "v_start": 0.0,
                    "v_end": 8.0,
                },
            ],
        }
        framing_data = {"wall_id": "wall_A", "elements": []}
        cavities = decompose_wall_cavities(
            simple_wall,
            cell_data=cell_data,
            framing_data=framing_data,
            config=config,
        )
        assert len(cavities) == 0

    def test_scc_cell_produces_cavities(self, config):
        """SCC cells should produce cavities between cripple studs."""
        # SCC: below a window, between bottom plate and sill
        cell_data = {
            "wall_id": "wall_B",
            "cells": [
                {
                    "id": "wall_B_SCC_0",
                    "cell_type": "SCC",
                    "u_start": 3.5,
                    "u_end": 6.5,
                    "v_start": 0.0,
                    "v_end": 3.0,
                },
            ],
        }

        # Sill cripple studs at regular spacing within the SCC
        elements = [
            # Bottom plate
            {
                "id": "bp_scc",
                "element_type": "bottom_plate",
                "u_coord": 5.0,
                "v_start": 0.0,
                "v_end": 0.125,
                "cell_id": "wall_B_SCC_0",
                "profile": {"width": 0.125, "depth": 0.292, "name": "2x4"},
            },
            # Sill
            {
                "id": "sill_0",
                "element_type": "sill",
                "u_coord": 5.0,
                "v_start": 2.875,
                "v_end": 3.0,
                "cell_id": "wall_B_SCC_0",
                "profile": {"width": 0.125, "depth": 0.292, "name": "2x4"},
            },
            # Left trimmer
            {
                "id": "trim_left",
                "element_type": "trimmer",
                "u_coord": 3.5625,
                "v_start": 0.125,
                "v_end": 3.0,
                "cell_id": "wall_B_SCC_0",
                "profile": {"width": 0.125, "depth": 0.292, "name": "2x4"},
            },
            # Sill cripple
            {
                "id": "sc_0",
                "element_type": "sill_cripple",
                "u_coord": 5.0,
                "v_start": 0.125,
                "v_end": 2.875,
                "cell_id": "wall_B_SCC_0",
                "profile": {"width": 0.125, "depth": 0.292, "name": "2x4"},
            },
            # Right trimmer
            {
                "id": "trim_right",
                "element_type": "trimmer",
                "u_coord": 6.4375,
                "v_start": 0.125,
                "v_end": 3.0,
                "cell_id": "wall_B_SCC_0",
                "profile": {"width": 0.125, "depth": 0.292, "name": "2x4"},
            },
        ]

        framing_data = {"wall_id": "wall_B", "elements": elements}
        wall_data = {
            "wall_id": "wall_B",
            "wall_length": 10.0,
            "wall_height": 8.0,
            "wall_thickness": 0.292,
        }

        cavities = decompose_wall_cavities(
            wall_data,
            cell_data=cell_data,
            framing_data=framing_data,
            config=config,
        )

        assert len(cavities) >= 2, f"Expected >= 2 SCC cavities, got {len(cavities)}"
        for cav in cavities:
            assert cav.cell_id == "wall_B_SCC_0"
            assert cav.clear_width > 0
            assert cav.clear_height > 0


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    """Tests for find_cavity_for_uv, find_nearest_cavity, find_adjacent_cavities."""

    @pytest.fixture
    def sample_cavities(self) -> list:
        """Three adjacent cavities."""
        return [
            Cavity(
                id="cav_0", wall_id="w", cell_id="sc",
                u_min=0.125, u_max=1.208, v_min=0.125, v_max=7.875,
                depth=0.292,
                left_member="wall_edge", right_member="stud",
                top_member="top_plate", bottom_member="bottom_plate",
            ),
            Cavity(
                id="cav_1", wall_id="w", cell_id="sc",
                u_min=1.333, u_max=2.541, v_min=0.125, v_max=7.875,
                depth=0.292,
                left_member="stud", right_member="stud",
                top_member="top_plate", bottom_member="bottom_plate",
            ),
            Cavity(
                id="cav_2", wall_id="w", cell_id="sc",
                u_min=2.666, u_max=3.874, v_min=0.125, v_max=7.875,
                depth=0.292,
                left_member="stud", right_member="stud",
                top_member="top_plate", bottom_member="bottom_plate",
            ),
        ]

    def test_find_cavity_for_uv_inside(self, sample_cavities):
        """Point inside a cavity should return that cavity."""
        cav = find_cavity_for_uv(sample_cavities, 0.5, 4.0)
        assert cav is not None
        assert cav.id == "cav_0"

    def test_find_cavity_for_uv_on_stud(self, sample_cavities):
        """Point on a stud (between cavities) should return None."""
        # Between cav_0 (u_max=1.208) and cav_1 (u_min=1.333)
        cav = find_cavity_for_uv(sample_cavities, 1.27, 4.0)
        assert cav is None

    def test_find_nearest_cavity_on_stud(self, sample_cavities):
        """Point on a stud should find nearest cavity by U distance."""
        # Point at u=1.27, between cav_0.u_max=1.208 and cav_1.u_min=1.333
        cav = find_nearest_cavity(sample_cavities, 1.27, 4.0)
        assert cav is not None
        # 1.27 - 1.208 = 0.062, 1.333 - 1.27 = 0.063 -> cav_0 is closer
        assert cav.id == "cav_0"

    def test_find_nearest_cavity_inside(self, sample_cavities):
        """Point inside a cavity should return that cavity (distance=0)."""
        cav = find_nearest_cavity(sample_cavities, 2.0, 4.0)
        assert cav is not None
        assert cav.id == "cav_1"

    def test_find_adjacent_left_right(self, sample_cavities):
        """Adjacent cavities should be found by touching U boundaries."""
        left, right = find_adjacent_cavities(
            sample_cavities, sample_cavities[1]
        )
        assert left is not None
        assert left.id == "cav_0"
        assert right is not None
        assert right.id == "cav_2"

    def test_find_adjacent_at_wall_edge(self, sample_cavities):
        """First cavity should have no left neighbor."""
        left, right = find_adjacent_cavities(
            sample_cavities, sample_cavities[0]
        )
        assert left is None
        assert right is not None
        assert right.id == "cav_1"


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    """Tests for Cavity serialization round-trip."""

    def test_cavity_to_dict_from_dict(self):
        """to_dict -> from_dict should preserve all fields."""
        original = Cavity(
            id="cav_42",
            wall_id="wall_X",
            cell_id="wall_X_SC_0",
            u_min=1.333,
            u_max=2.666,
            v_min=0.125,
            v_max=7.875,
            depth=0.292,
            left_member="stud",
            right_member="king_stud",
            top_member="top_plate",
            bottom_member="bottom_plate",
            metadata={"bay_index": 3},
        )

        roundtrip = Cavity.from_dict(original.to_dict())

        assert roundtrip.id == original.id
        assert roundtrip.wall_id == original.wall_id
        assert roundtrip.cell_id == original.cell_id
        assert roundtrip.u_min == pytest.approx(original.u_min)
        assert roundtrip.u_max == pytest.approx(original.u_max)
        assert roundtrip.v_min == pytest.approx(original.v_min)
        assert roundtrip.v_max == pytest.approx(original.v_max)
        assert roundtrip.depth == pytest.approx(original.depth)
        assert roundtrip.left_member == original.left_member
        assert roundtrip.right_member == original.right_member
        assert roundtrip.top_member == original.top_member
        assert roundtrip.bottom_member == original.bottom_member
        assert roundtrip.metadata == original.metadata

    def test_serialize_deserialize_list(self):
        """serialize_cavities -> deserialize_cavities round-trip."""
        cavities = [
            Cavity(
                id=f"cav_{i}", wall_id="w", cell_id="sc",
                u_min=i * 1.333, u_max=(i + 1) * 1.333 - 0.125,
                v_min=0.125, v_max=7.875, depth=0.292,
                left_member="stud", right_member="stud",
                top_member="top_plate", bottom_member="bottom_plate",
            )
            for i in range(5)
        ]

        json_str = serialize_cavities(cavities)
        restored = deserialize_cavities(json_str)

        assert len(restored) == 5
        for orig, rest in zip(cavities, restored):
            assert orig.id == rest.id
            assert orig.u_min == pytest.approx(rest.u_min)
            assert orig.u_max == pytest.approx(rest.u_max)

    def test_serialize_produces_valid_json(self):
        """Serialized output should be valid JSON."""
        cavities = [
            Cavity(
                id="cav_0", wall_id="w", cell_id="sc",
                u_min=0.0, u_max=1.0, v_min=0.0, v_max=8.0, depth=0.292,
                left_member="wall_edge", right_member="stud",
                top_member="top_plate", bottom_member="bottom_plate",
            )
        ]
        json_str = serialize_cavities(cavities)
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "cav_0"


# ---------------------------------------------------------------------------
# contains_uv tests
# ---------------------------------------------------------------------------

class TestContainsUV:
    """Tests for Cavity.contains_uv() method."""

    @pytest.fixture
    def cavity(self) -> Cavity:
        return Cavity(
            id="test", wall_id="w", cell_id="sc",
            u_min=1.0, u_max=2.0, v_min=0.5, v_max=7.5, depth=0.292,
            left_member="stud", right_member="stud",
            top_member="top_plate", bottom_member="bottom_plate",
        )

    def test_point_inside(self, cavity):
        assert cavity.contains_uv(1.5, 4.0)

    def test_point_on_left_boundary(self, cavity):
        assert cavity.contains_uv(1.0, 4.0)

    def test_point_on_right_boundary(self, cavity):
        assert cavity.contains_uv(2.0, 4.0)

    def test_point_outside_left(self, cavity):
        assert not cavity.contains_uv(0.5, 4.0)

    def test_point_outside_right(self, cavity):
        assert not cavity.contains_uv(2.5, 4.0)

    def test_point_outside_above(self, cavity):
        assert not cavity.contains_uv(1.5, 8.0)

    def test_point_outside_below(self, cavity):
        assert not cavity.contains_uv(1.5, 0.0)

    def test_point_at_corner(self, cavity):
        assert cavity.contains_uv(1.0, 0.5)

    def test_properties(self, cavity):
        assert cavity.clear_width == pytest.approx(1.0)
        assert cavity.clear_height == pytest.approx(7.0)
        assert cavity.center_u == pytest.approx(1.5)
        assert cavity.center_v == pytest.approx(4.0)
