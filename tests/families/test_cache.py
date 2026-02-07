# File: tests/families/test_cache.py
"""
Unit tests for the family cache manager.

Tests cover:
- Cache directory creation
- File storage with SHA256 verification
- Cache hit/miss detection
- Cache clearing
- Offline cache listing
"""

import hashlib
import json
import os

import pytest

from src.timber_framing_generator.families.cache import FamilyCache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary cache directory."""
    return str(tmp_path / "test_cache" / "families")


@pytest.fixture
def cache(cache_dir):
    """Create a FamilyCache with a temporary directory."""
    return FamilyCache(cache_dir=cache_dir)


@pytest.fixture
def sample_rfa(tmp_path):
    """Create a sample .rfa file (just bytes for testing)."""
    rfa_path = tmp_path / "sample.rfa"
    rfa_path.write_bytes(b"fake rfa content for testing")
    return str(rfa_path)


def compute_sha256(file_path: str) -> str:
    """Helper to compute SHA256 of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


# =============================================================================
# Test: Cache Initialization
# =============================================================================

class TestCacheInit:
    """Test cache initialization and directory creation."""

    def test_cache_creates_directory(self, cache_dir):
        """Cache directory is created on init."""
        cache = FamilyCache(cache_dir=cache_dir)
        assert os.path.isdir(cache_dir)

    def test_cache_dir_property(self, cache, cache_dir):
        """cache_dir property returns configured directory."""
        assert cache.cache_dir == cache_dir

    def test_empty_cache_has_no_entries(self, cache):
        """Fresh cache has no cached families."""
        assert cache.list_cached() == []


# =============================================================================
# Test: Store and Retrieve
# =============================================================================

class TestCacheStore:
    """Test storing and retrieving family files."""

    def test_store_creates_file(self, cache, sample_rfa):
        """Storing a family creates the file in the cache directory."""
        cached_path = cache.store(
            "TFG_Stud_2x4", sample_rfa,
            "timber/structural_framing/TFG_Stud_2x4.rfa"
        )
        assert os.path.exists(cached_path)

    def test_store_updates_manifest(self, cache, sample_rfa):
        """Storing a family updates the cache manifest."""
        cache.store(
            "TFG_Stud_2x4", sample_rfa,
            "timber/structural_framing/TFG_Stud_2x4.rfa"
        )
        assert "TFG_Stud_2x4" in cache.list_cached()

    def test_get_cached_path_returns_path(self, cache, sample_rfa):
        """get_cached_path returns the file path after storing."""
        cache.store(
            "TFG_Stud_2x4", sample_rfa,
            "timber/structural_framing/TFG_Stud_2x4.rfa"
        )
        path = cache.get_cached_path("TFG_Stud_2x4")
        assert path is not None
        assert os.path.exists(path)

    def test_get_cached_path_missing_returns_none(self, cache):
        """get_cached_path returns None for uncached family."""
        path = cache.get_cached_path("nonexistent")
        assert path is None

    def test_store_preserves_content(self, cache, sample_rfa):
        """Stored file has identical content to source."""
        cached_path = cache.store(
            "TFG_Stud_2x4", sample_rfa,
            "timber/structural_framing/TFG_Stud_2x4.rfa"
        )
        with open(sample_rfa, "rb") as f:
            original = f.read()
        with open(cached_path, "rb") as f:
            cached = f.read()
        assert original == cached


# =============================================================================
# Test: SHA256 Verification
# =============================================================================

class TestCacheSHA256:
    """Test checksum verification."""

    def test_compute_sha256(self, cache, sample_rfa):
        """compute_sha256 returns correct hash."""
        expected = compute_sha256(sample_rfa)
        actual = cache.compute_sha256(sample_rfa)
        assert actual == expected

    def test_is_cached_with_matching_sha(self, cache, sample_rfa):
        """is_cached returns True when SHA256 matches."""
        sha = compute_sha256(sample_rfa)
        cache.store("TFG_Stud_2x4", sample_rfa, "test.rfa", sha256=sha)
        assert cache.is_cached("TFG_Stud_2x4", expected_sha256=sha)

    def test_is_cached_with_mismatching_sha(self, cache, sample_rfa):
        """is_cached returns False when SHA256 doesn't match."""
        cache.store("TFG_Stud_2x4", sample_rfa, "test.rfa", sha256="old_hash")
        assert not cache.is_cached("TFG_Stud_2x4", expected_sha256="new_hash")

    def test_is_cached_with_placeholder_sha_skips_check(self, cache, sample_rfa):
        """Placeholder SHA256 hashes skip verification."""
        cache.store("TFG_Stud_2x4", sample_rfa, "test.rfa", sha256="anything")
        assert cache.is_cached(
            "TFG_Stud_2x4",
            expected_sha256="placeholder_update_when_rfa_created"
        )

    def test_is_cached_without_sha_check(self, cache, sample_rfa):
        """is_cached without expected_sha256 only checks file existence."""
        cache.store("TFG_Stud_2x4", sample_rfa, "test.rfa")
        assert cache.is_cached("TFG_Stud_2x4")


# =============================================================================
# Test: Cache Management
# =============================================================================

class TestCacheManagement:
    """Test cache clearing and removal."""

    def test_remove_single_family(self, cache, sample_rfa):
        """Remove a single family from cache."""
        cache.store("TFG_Stud_2x4", sample_rfa, "stud.rfa")
        assert cache.remove("TFG_Stud_2x4")
        assert not cache.is_cached("TFG_Stud_2x4")

    def test_remove_nonexistent_returns_false(self, cache):
        """Removing a non-cached family returns False."""
        assert not cache.remove("nonexistent")

    def test_clear_cache_removes_all(self, cache, sample_rfa):
        """clear_cache removes all cached families."""
        cache.store("Family1", sample_rfa, "f1.rfa")
        cache.store("Family2", sample_rfa, "f2.rfa")
        count = cache.clear_cache()
        assert count == 2
        assert cache.list_cached() == []

    def test_clear_empty_cache_returns_zero(self, cache):
        """clear_cache on empty cache returns 0."""
        assert cache.clear_cache() == 0

    def test_list_cached_returns_all_keys(self, cache, sample_rfa):
        """list_cached returns all stored family keys."""
        cache.store("Family1", sample_rfa, "f1.rfa")
        cache.store("Family2", sample_rfa, "f2.rfa")
        cached = cache.list_cached()
        assert "Family1" in cached
        assert "Family2" in cached


# =============================================================================
# Test: Cache Persistence
# =============================================================================

class TestCachePersistence:
    """Test that cache survives re-initialization."""

    def test_cache_survives_reinit(self, cache_dir, sample_rfa):
        """Cache manifest persists across FamilyCache instances."""
        cache1 = FamilyCache(cache_dir=cache_dir)
        cache1.store("TFG_Stud_2x4", sample_rfa, "test.rfa")

        cache2 = FamilyCache(cache_dir=cache_dir)
        assert cache2.is_cached("TFG_Stud_2x4")
        assert cache2.get_cached_path("TFG_Stud_2x4") is not None

    def test_deleted_file_detected(self, cache_dir, sample_rfa):
        """Cache detects when file was deleted outside of cache manager."""
        cache = FamilyCache(cache_dir=cache_dir)
        cached_path = cache.store("TFG_Stud_2x4", sample_rfa, "test.rfa")

        # Delete the file manually
        os.remove(cached_path)

        assert not cache.is_cached("TFG_Stud_2x4")
