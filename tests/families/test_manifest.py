# File: tests/families/test_manifest.py
"""
Unit tests for family manifest schema.

Tests cover:
- FamilyManifest parsing from JSON
- Manifest serialization (round-trip)
- Manifest validation (required fields, types, dimensions)
- Profile-to-family mapping
"""

import json
import pytest

from src.timber_framing_generator.families.manifest import (
    FamilyTypeInfo,
    FamilyEntry,
    FamilyManifest,
    parse_manifest,
    serialize_manifest,
    validate_manifest,
    get_required_profiles,
    get_families_for_elements,
)


# =============================================================================
# Test Fixtures
# =============================================================================

SAMPLE_MANIFEST_JSON = json.dumps({
    "schema_version": "1.0",
    "revit_version": "2025",
    "base_url": "https://example.com/families",
    "families": {
        "TFG_Timber_Stud": {
            "file": "timber/structural_columns/TFG_Timber_Stud.rfa",
            "category": "OST_StructuralColumns",
            "domain": "framing",
            "types": {
                "2x4": {"width_in": 1.5, "depth_in": 3.5},
                "2x6": {"width_in": 1.5, "depth_in": 5.5}
            },
            "sha256": "abc123"
        },
        "TFG_Timber_Framing": {
            "file": "timber/structural_framing/TFG_Timber_Framing.rfa",
            "category": "OST_StructuralFraming",
            "domain": "framing",
            "types": {
                "2x4_Plate": {"width_in": 1.5, "depth_in": 3.5}
            },
            "sha256": "ghi789"
        }
    }
})


# =============================================================================
# Test: Manifest Parsing
# =============================================================================

class TestManifestParsing:
    """Test parsing manifest from JSON."""

    def test_parse_valid_manifest(self):
        """Parse a well-formed manifest JSON string."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        assert isinstance(manifest, FamilyManifest)
        assert manifest.schema_version == "1.0"
        assert manifest.revit_version == "2025"
        assert manifest.base_url == "https://example.com/families"

    def test_parse_family_count(self):
        """Correct number of families parsed."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        assert len(manifest.families) == 2

    def test_parse_family_entry(self):
        """Family entry has correct structure."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        stud = manifest.families["TFG_Timber_Stud"]
        assert isinstance(stud, FamilyEntry)
        assert stud.file == "timber/structural_columns/TFG_Timber_Stud.rfa"
        assert stud.category == "OST_StructuralColumns"
        assert stud.sha256 == "abc123"
        assert stud.domain == "framing"

    def test_parse_family_types(self):
        """Family types parsed with correct dimensions."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        stud = manifest.families["TFG_Timber_Stud"]
        assert "2x4" in stud.types
        assert "2x6" in stud.types
        type_info = stud.types["2x4"]
        assert isinstance(type_info, FamilyTypeInfo)
        assert type_info.width_in == 1.5
        assert type_info.depth_in == 3.5

    def test_parse_multiple_types_in_one_family(self):
        """A single family can have multiple types."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        stud = manifest.families["TFG_Timber_Stud"]
        assert len(stud.types) == 2
        assert stud.types["2x4"].depth_in == 3.5
        assert stud.types["2x6"].depth_in == 5.5

    def test_parse_type_with_extra_properties(self):
        """Extra properties in type data are preserved."""
        data = json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "TestFamily": {
                    "file": "test.rfa",
                    "category": "OST_StructuralFraming",
                    "types": {
                        "TestType": {
                            "width_in": 1.5,
                            "depth_in": 3.5,
                            "treated": True,
                            "grade": "SPF #2"
                        }
                    },
                    "sha256": ""
                }
            }
        })
        manifest = parse_manifest(data)
        type_info = manifest.families["TestFamily"].types["TestType"]
        assert type_info.properties["treated"] is True
        assert type_info.properties["grade"] == "SPF #2"

    def test_parse_missing_sha256_defaults_empty(self):
        """Missing sha256 defaults to empty string."""
        data = json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "Test": {
                    "file": "test.rfa",
                    "category": "OST_StructuralFraming",
                    "types": {"t": {"width_in": 1.0, "depth_in": 1.0}}
                }
            }
        })
        manifest = parse_manifest(data)
        assert manifest.families["Test"].sha256 == ""

    def test_parse_missing_domain_defaults_framing(self):
        """Missing domain defaults to 'framing'."""
        data = json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "Test": {
                    "file": "test.rfa",
                    "category": "OST_StructuralFraming",
                    "types": {"t": {"width_in": 1.0, "depth_in": 1.0}}
                }
            }
        })
        manifest = parse_manifest(data)
        assert manifest.families["Test"].domain == "framing"

    def test_parse_custom_domain(self):
        """Custom domain is parsed correctly."""
        data = json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "Test": {
                    "file": "test.rfa",
                    "category": "OST_MechanicalEquipment",
                    "domain": "mep",
                    "types": {"t": {"width_in": 1.0, "depth_in": 1.0}},
                    "sha256": ""
                }
            }
        })
        manifest = parse_manifest(data)
        assert manifest.families["Test"].domain == "mep"

    def test_parse_cfs_revit_parameters(self):
        """CFS type properties include Revit dimension parameters."""
        data = json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "TFG_CFS_Stud": {
                    "file": "cfs/TFG_CFS_Stud.rfa",
                    "category": "OST_StructuralFraming",
                    "domain": "framing",
                    "types": {
                        "362S125-54": {
                            "width_in": 1.25,
                            "depth_in": 3.625,
                            "d": 3.625,
                            "bf": 1.25,
                            "tf": 0.0566,
                            "Return": 0.375,
                            "gauge": 16,
                            "fy_ksi": 50
                        }
                    },
                    "sha256": ""
                }
            }
        })
        manifest = parse_manifest(data)
        type_info = manifest.families["TFG_CFS_Stud"].types["362S125-54"]
        assert type_info.width_in == 1.25
        assert type_info.depth_in == 3.625
        # Revit dimension parameters stored in properties
        assert type_info.properties["d"] == 3.625
        assert type_info.properties["bf"] == 1.25
        assert type_info.properties["tf"] == 0.0566
        assert type_info.properties["Return"] == 0.375
        assert type_info.properties["gauge"] == 16
        assert type_info.properties["fy_ksi"] == 50

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            parse_manifest("not valid json")

    def test_parse_missing_schema_version_raises(self):
        """Missing required field raises KeyError."""
        data = json.dumps({"families": {}})
        with pytest.raises(KeyError):
            parse_manifest(data)


# =============================================================================
# Test: Manifest Serialization
# =============================================================================

class TestManifestSerialization:
    """Test round-trip serialization."""

    def test_serialize_produces_valid_json(self):
        """Serialized output is valid JSON."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        json_str = serialize_manifest(manifest)
        data = json.loads(json_str)
        assert "schema_version" in data
        assert "families" in data

    def test_roundtrip_preserves_data(self):
        """Parse -> serialize -> parse preserves all data."""
        original = parse_manifest(SAMPLE_MANIFEST_JSON)
        json_str = serialize_manifest(original)
        restored = parse_manifest(json_str)

        assert restored.schema_version == original.schema_version
        assert restored.revit_version == original.revit_version
        assert len(restored.families) == len(original.families)

        for key in original.families:
            assert key in restored.families
            assert restored.families[key].file == original.families[key].file
            assert restored.families[key].domain == original.families[key].domain
            assert len(restored.families[key].types) == len(original.families[key].types)

    def test_roundtrip_preserves_domain(self):
        """Parse -> serialize -> parse preserves domain field."""
        data = json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "Pipe": {
                    "file": "mep/pipe.rfa",
                    "category": "OST_PipeCurves",
                    "domain": "mep",
                    "types": {"4in": {"width_in": 4.0, "depth_in": 4.0}},
                    "sha256": ""
                }
            }
        })
        original = parse_manifest(data)
        json_str = serialize_manifest(original)
        restored = parse_manifest(json_str)
        assert restored.families["Pipe"].domain == "mep"


# =============================================================================
# Test: Manifest Validation
# =============================================================================

class TestManifestValidation:
    """Test manifest validation."""

    def test_valid_manifest_passes(self):
        """Well-formed manifest passes validation."""
        is_valid, errors = validate_manifest(SAMPLE_MANIFEST_JSON)
        assert is_valid
        assert len(errors) == 0

    def test_valid_manifest_object_passes(self):
        """FamilyManifest object passes validation."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        is_valid, errors = validate_manifest(manifest)
        assert is_valid

    def test_missing_schema_version(self):
        """Missing schema_version fails validation."""
        data = {"revit_version": "2025", "families": {}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("schema_version" in e for e in errors)

    def test_missing_families(self):
        """Missing families field fails validation."""
        data = {"schema_version": "1.0", "revit_version": "2025"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid

    def test_empty_families(self):
        """Empty families dict fails validation."""
        data = {"schema_version": "1.0", "revit_version": "2025", "families": {}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("at least one family" in e for e in errors)

    def test_missing_file_field(self):
        """Family without 'file' field fails."""
        data = {
            "schema_version": "1.0", "revit_version": "2025",
            "families": {
                "Bad": {
                    "category": "OST_StructuralFraming",
                    "types": {"t": {"width_in": 1, "depth_in": 1}}
                }
            }
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("file" in e for e in errors)

    def test_file_must_end_with_rfa(self):
        """Family file must end with .rfa."""
        data = {
            "schema_version": "1.0", "revit_version": "2025",
            "families": {
                "Bad": {
                    "file": "test.txt",
                    "category": "OST_StructuralFraming",
                    "types": {"t": {"width_in": 1, "depth_in": 1}}
                }
            }
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any(".rfa" in e for e in errors)

    def test_missing_type_dimensions(self):
        """Type without width_in/depth_in fails."""
        data = {
            "schema_version": "1.0", "revit_version": "2025",
            "families": {
                "Bad": {
                    "file": "test.rfa",
                    "category": "OST_StructuralFraming",
                    "types": {"t": {}}
                }
            }
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid

    def test_negative_dimensions_fail(self):
        """Negative dimensions fail validation."""
        data = {
            "schema_version": "1.0", "revit_version": "2025",
            "families": {
                "Bad": {
                    "file": "test.rfa",
                    "category": "OST_StructuralFraming",
                    "types": {"t": {"width_in": -1.0, "depth_in": 3.5}}
                }
            }
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid

    def test_invalid_json_string(self):
        """Invalid JSON string fails validation."""
        is_valid, errors = validate_manifest("not json")
        assert not is_valid
        assert any("Invalid JSON" in e for e in errors)


# =============================================================================
# Test: Profile Mapping
# =============================================================================

class TestProfileMapping:
    """Test profile-to-family mapping functions."""

    def test_get_required_profiles(self):
        """Maps type names to family keys."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        profiles = get_required_profiles(manifest)

        assert profiles["2x4"] == "TFG_Timber_Stud"
        assert profiles["2x6"] == "TFG_Timber_Stud"
        assert profiles["2x4_Plate"] == "TFG_Timber_Framing"

    def test_get_required_profiles_all_types(self):
        """All types across all families are mapped."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        profiles = get_required_profiles(manifest)
        assert len(profiles) == 3  # 2x4, 2x6, 2x4_Plate

    def test_get_families_for_elements(self):
        """Returns only families needed for given profile names."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        needed = get_families_for_elements(manifest, ["2x4", "2x4_Plate"])

        assert "TFG_Timber_Stud" in needed
        assert "TFG_Timber_Framing" in needed

    def test_get_families_for_elements_consolidates(self):
        """Multiple types from same family return one family entry."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        needed = get_families_for_elements(manifest, ["2x4", "2x6"])
        assert len(needed) == 1
        assert "TFG_Timber_Stud" in needed

    def test_get_families_for_unknown_profile(self):
        """Unknown profile names are silently ignored."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        needed = get_families_for_elements(manifest, ["unknown_profile"])
        assert len(needed) == 0

    def test_get_families_deduplicates(self):
        """Duplicate profile names produce single family entry."""
        manifest = parse_manifest(SAMPLE_MANIFEST_JSON)
        needed = get_families_for_elements(manifest, ["2x4", "2x4", "2x4"])
        assert len(needed) == 1
