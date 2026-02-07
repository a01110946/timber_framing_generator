# File: tests/families/test_resolver.py
"""
Unit tests for the FamilyResolver orchestrator.

Tests cover:
- Full resolution pipeline with mocked provider/cache
- Offline mode
- JSON enrichment
- Profile extraction from framing JSON
- ResolutionResult status computation
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.timber_framing_generator.families.resolver import (
    FamilyResolver,
    ResolutionResult,
)
from src.timber_framing_generator.families.manifest import (
    FamilyManifest,
    FamilyEntry,
    FamilyTypeInfo,
    parse_manifest,
)
from src.timber_framing_generator.families.cache import FamilyCache
from src.timber_framing_generator.families.providers import FamilyProvider


# =============================================================================
# Fixtures
# =============================================================================

def make_manifest() -> FamilyManifest:
    """Create a test manifest."""
    return FamilyManifest(
        schema_version="1.0",
        revit_version="2025",
        base_url="https://example.com/families",
        families={
            "TFG_Stud_2x4": FamilyEntry(
                file="timber/structural_framing/TFG_Stud_2x4.rfa",
                category="OST_StructuralFraming",
                types={"2x4": FamilyTypeInfo(width_in=1.5, depth_in=3.5)},
                sha256="abc123",
            ),
            "TFG_Plate_2x4": FamilyEntry(
                file="timber/plates/TFG_Plate_2x4.rfa",
                category="OST_StructuralFraming",
                types={"2x4_Plate": FamilyTypeInfo(width_in=1.5, depth_in=3.5)},
                sha256="def456",
            ),
        },
    )


def make_framing_json() -> str:
    """Create sample framing JSON with known profiles."""
    return json.dumps({
        "wall_id": "test_wall",
        "material_system": "timber",
        "elements": [
            {
                "id": "stud_1",
                "element_type": "stud",
                "profile": {"name": "2x4", "width": 0.125, "depth": 0.292},
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 0, "y": 0, "z": 8},
                "u_coord": 1.0,
                "v_start": 0.0,
                "v_end": 8.0,
            },
            {
                "id": "plate_1",
                "element_type": "bottom_plate",
                "profile": {"name": "2x4_Plate", "width": 0.125, "depth": 0.292},
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 10, "y": 0, "z": 0},
                "u_coord": 5.0,
                "v_start": 0.0,
                "v_end": 0.125,
            },
        ],
    })


class MockProvider(FamilyProvider):
    """Mock provider for testing."""

    def __init__(self, manifest: FamilyManifest = None, should_fail: bool = False):
        self._manifest = manifest or make_manifest()
        self._should_fail = should_fail
        self.download_calls = []

    @property
    def provider_name(self) -> str:
        return "MockProvider"

    def get_manifest(self) -> FamilyManifest:
        if self._should_fail:
            raise ConnectionError("Mock network failure")
        return self._manifest

    def download_family(self, family_entry: FamilyEntry, dest_path: str) -> bool:
        self.download_calls.append((family_entry.file, dest_path))
        if self._should_fail:
            return False
        # Create a fake .rfa file
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"fake rfa content")
        return True


# =============================================================================
# Test: ResolutionResult
# =============================================================================

class TestResolutionResult:
    """Test ResolutionResult dataclass."""

    def test_default_status(self):
        """Default status is 'pending'."""
        result = ResolutionResult()
        assert result.status == "pending"

    def test_to_dict(self):
        """to_dict returns serializable dict."""
        result = ResolutionResult(
            status="all_resolved",
            resolved={"2x4": "2x4"},
            missing=[],
            loaded=["TFG_Stud_2x4"],
        )
        d = result.to_dict()
        assert d["status"] == "all_resolved"
        assert d["resolved_count"] == 1
        assert d["missing_count"] == 0

    def test_empty_result_serializes(self):
        """Empty result can be serialized to dict."""
        result = ResolutionResult()
        d = result.to_dict()
        assert isinstance(d, dict)


# =============================================================================
# Test: Profile Extraction
# =============================================================================

class TestProfileExtraction:
    """Test extracting profiles from framing JSON."""

    def test_extract_profiles_from_framing_json(self):
        """Resolver extracts unique profiles from framing JSON."""
        resolver = FamilyResolver(
            provider=MockProvider(),
            manifest=make_manifest(),
        )
        profiles = resolver._extract_needed_profiles(make_framing_json())
        assert "2x4" in profiles
        assert "2x4_Plate" in profiles

    def test_extract_from_empty_json(self):
        """Empty framing JSON returns empty list."""
        resolver = FamilyResolver(provider=MockProvider())
        assert resolver._extract_needed_profiles("{}") == []

    def test_extract_from_none(self):
        """None framing JSON returns empty list."""
        resolver = FamilyResolver(provider=MockProvider())
        assert resolver._extract_needed_profiles(None) == []

    def test_extract_from_invalid_json(self):
        """Invalid JSON returns empty list."""
        resolver = FamilyResolver(provider=MockProvider())
        assert resolver._extract_needed_profiles("not json") == []


# =============================================================================
# Test: Resolve Pipeline (no Revit)
# =============================================================================

class TestResolvePipeline:
    """Test the full resolution pipeline without Revit."""

    def test_resolve_all_families_no_revit(self, tmp_path):
        """Resolve downloads and caches all families when no Revit doc."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        provider = MockProvider()
        resolver = FamilyResolver(
            provider=provider,
            cache=cache,
            manifest=make_manifest(),
        )

        result = resolver.resolve(doc=None, framing_json=make_framing_json())

        # Both families should be downloaded (or cached)
        assert len(provider.download_calls) == 2
        assert result.status in ("all_resolved", "partial")

    def test_resolve_with_preloaded_manifest(self, tmp_path):
        """Pre-loaded manifest skips provider's get_manifest() call."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        manifest = make_manifest()
        provider = MockProvider()

        resolver = FamilyResolver(
            provider=provider,
            cache=cache,
            manifest=manifest,
        )

        result = resolver.resolve(doc=None, framing_json=make_framing_json())

        # Manifest was pre-loaded, so log should say so
        assert any("pre-loaded" in msg.lower() for msg in result.log)
        # Downloads still happen via provider (manifest != provider)
        assert len(provider.download_calls) == 2

    def test_resolve_filters_by_framing_json(self, tmp_path):
        """Only families needed by framing elements are resolved."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        provider = MockProvider()

        # Framing JSON only uses "2x4" profile
        framing_json = json.dumps({
            "wall_id": "test",
            "material_system": "timber",
            "elements": [{
                "id": "stud_1",
                "element_type": "stud",
                "profile": {"name": "2x4"},
                "centerline_start": {"x": 0, "y": 0, "z": 0},
                "centerline_end": {"x": 0, "y": 0, "z": 8},
                "u_coord": 1.0, "v_start": 0.0, "v_end": 8.0,
            }],
        })

        resolver = FamilyResolver(
            provider=provider, cache=cache, manifest=make_manifest()
        )
        result = resolver.resolve(doc=None, framing_json=framing_json)

        # Only TFG_Stud_2x4 should be downloaded (not TFG_Plate_2x4)
        downloaded_files = [call[0] for call in provider.download_calls]
        assert any("TFG_Stud_2x4" in f for f in downloaded_files)
        assert not any("TFG_Plate_2x4" in f for f in downloaded_files)

    def test_resolve_uses_cache_on_second_run(self, tmp_path):
        """Second resolve uses cached files (no re-download)."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        provider = MockProvider()
        resolver = FamilyResolver(
            provider=provider, cache=cache, manifest=make_manifest()
        )

        # First resolve — downloads
        resolver.resolve(doc=None, framing_json=make_framing_json())
        first_call_count = len(provider.download_calls)
        assert first_call_count > 0

        # Second resolve — should use cache
        provider2 = MockProvider()
        resolver2 = FamilyResolver(
            provider=provider2, cache=cache, manifest=make_manifest()
        )
        result2 = resolver2.resolve(doc=None, framing_json=make_framing_json())

        assert len(provider2.download_calls) == 0
        assert len(result2.cached) > 0


# =============================================================================
# Test: Offline Mode
# =============================================================================

class TestOfflineMode:
    """Test offline/cache-only resolution."""

    def test_offline_fallback_on_network_error(self, tmp_path):
        """Falls back to cache when provider is unreachable."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))

        # Pre-populate cache with a fake file
        fake_rfa = tmp_path / "fake.rfa"
        fake_rfa.write_bytes(b"cached content")
        cache.store("TFG_Stud_2x4", str(fake_rfa), "stud.rfa")

        # Provider that fails
        provider = MockProvider(should_fail=True)
        resolver = FamilyResolver(provider=provider, cache=cache)

        result = resolver.resolve(doc=None)
        assert result.status == "offline"
        assert "TFG_Stud_2x4" in result.cached

    def test_offline_with_empty_cache_fails(self, tmp_path):
        """Offline mode with empty cache results in 'failed' status."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        provider = MockProvider(should_fail=True)
        resolver = FamilyResolver(provider=provider, cache=cache)

        result = resolver.resolve(doc=None)
        assert result.status == "failed"


# =============================================================================
# Test: JSON Enrichment
# =============================================================================

class TestJsonEnrichment:
    """Test framing JSON enrichment with family references."""

    def test_enrich_adds_revit_fields(self, tmp_path):
        """enrich_framing_json adds revit_family and revit_type fields."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        manifest = make_manifest()
        provider = MockProvider()
        resolver = FamilyResolver(
            provider=provider, cache=cache, manifest=manifest
        )

        result = resolver.resolve(doc=None, framing_json=make_framing_json())
        enriched_str = resolver.enrich_framing_json(
            make_framing_json(), result, manifest
        )

        enriched = json.loads(enriched_str)
        stud = enriched["elements"][0]
        assert "revit_family" in stud
        assert "revit_type" in stud

    def test_enrich_preserves_original_fields(self, tmp_path):
        """Enrichment preserves all original element fields."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        manifest = make_manifest()
        resolver = FamilyResolver(
            provider=MockProvider(), cache=cache, manifest=manifest
        )

        result = resolver.resolve(doc=None, framing_json=make_framing_json())
        enriched_str = resolver.enrich_framing_json(
            make_framing_json(), result, manifest
        )

        enriched = json.loads(enriched_str)
        stud = enriched["elements"][0]
        assert stud["id"] == "stud_1"
        assert stud["element_type"] == "stud"
        assert stud["profile"]["name"] == "2x4"

    def test_enrich_invalid_json_returns_original(self):
        """Invalid JSON input returns the original string unchanged."""
        resolver = FamilyResolver(provider=MockProvider())
        result = ResolutionResult()
        assert resolver.enrich_framing_json("not json", result) == "not json"

    def test_enrich_with_unresolved_profiles(self, tmp_path):
        """Unresolved profiles don't get revit_family/revit_type fields."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        manifest = make_manifest()
        resolver = FamilyResolver(
            provider=MockProvider(), cache=cache, manifest=manifest
        )

        # Empty result (nothing resolved)
        result = ResolutionResult(status="failed")
        enriched_str = resolver.enrich_framing_json(
            make_framing_json(), result, manifest
        )

        enriched = json.loads(enriched_str)
        stud = enriched["elements"][0]
        assert "revit_family" not in stud or stud.get("revit_family") is None


# =============================================================================
# Test: Resolver Configuration
# =============================================================================

class TestResolverConfig:
    """Test resolver initialization and properties."""

    def test_default_provider_is_github(self):
        """Default provider is GitHubProvider."""
        from src.timber_framing_generator.families.providers import GitHubProvider
        resolver = FamilyResolver()
        assert isinstance(resolver.provider, GitHubProvider)

    def test_custom_provider(self):
        """Custom provider is used when provided."""
        provider = MockProvider()
        resolver = FamilyResolver(provider=provider)
        assert resolver.provider is provider

    def test_custom_cache(self, tmp_path):
        """Custom cache is used when provided."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        resolver = FamilyResolver(provider=MockProvider(), cache=cache)
        assert resolver.cache is cache

    def test_resolution_log_has_entries(self, tmp_path):
        """Resolution result includes diagnostic log entries."""
        cache = FamilyCache(cache_dir=str(tmp_path / "cache"))
        resolver = FamilyResolver(
            provider=MockProvider(), cache=cache, manifest=make_manifest()
        )
        result = resolver.resolve(doc=None)
        assert len(result.log) > 0
