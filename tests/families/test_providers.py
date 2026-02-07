# File: tests/families/test_providers.py
"""
Unit tests for family providers.

Tests cover:
- GitHubProvider URL construction
- GitHubProvider manifest fetching (mocked)
- GitHubProvider file download (mocked)
- LocalFileProvider operations
- Provider ABC enforcement
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from src.timber_framing_generator.families.providers import (
    FamilyProvider,
    GitHubProvider,
    LocalFileProvider,
    DEFAULT_GITHUB_BASE_URL,
)
from src.timber_framing_generator.families.manifest import (
    FamilyEntry,
    FamilyTypeInfo,
    FamilyManifest,
)


# =============================================================================
# Fixtures
# =============================================================================

SAMPLE_MANIFEST_RESPONSE = json.dumps({
    "schema_version": "1.0",
    "revit_version": "2025",
    "base_url": "https://example.com/families",
    "families": {
        "TFG_Stud_2x4": {
            "file": "timber/structural_framing/TFG_Stud_2x4.rfa",
            "category": "OST_StructuralFraming",
            "types": {
                "2x4": {"width_in": 1.5, "depth_in": 3.5}
            },
            "sha256": "abc123"
        }
    }
}).encode("utf-8")


def make_family_entry() -> FamilyEntry:
    """Create a sample FamilyEntry for testing."""
    return FamilyEntry(
        file="timber/structural_framing/TFG_Stud_2x4.rfa",
        category="OST_StructuralFraming",
        types={"2x4": FamilyTypeInfo(width_in=1.5, depth_in=3.5)},
        sha256="abc123",
    )


# =============================================================================
# Test: GitHubProvider
# =============================================================================

class TestGitHubProvider:
    """Test GitHub-based family provider."""

    def test_default_base_url(self):
        """Default base URL points to the project repo."""
        provider = GitHubProvider()
        assert provider.base_url == DEFAULT_GITHUB_BASE_URL

    def test_custom_base_url(self):
        """Custom base URL is used when provided."""
        provider = GitHubProvider(base_url="https://custom.com/families")
        assert provider.base_url == "https://custom.com/families"

    def test_trailing_slash_stripped(self):
        """Trailing slash in base URL is stripped."""
        provider = GitHubProvider(base_url="https://example.com/families/")
        assert provider.base_url == "https://example.com/families"

    def test_provider_name(self):
        """Provider name is 'GitHub'."""
        provider = GitHubProvider()
        assert provider.provider_name == "GitHub"

    @patch("src.timber_framing_generator.families.providers.urllib.request.urlopen")
    def test_get_manifest_success(self, mock_urlopen):
        """get_manifest parses response into FamilyManifest."""
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_MANIFEST_RESPONSE
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        provider = GitHubProvider()
        manifest = provider.get_manifest()

        assert isinstance(manifest, FamilyManifest)
        assert len(manifest.families) == 1
        assert "TFG_Stud_2x4" in manifest.families

    @patch("src.timber_framing_generator.families.providers.urllib.request.urlopen")
    def test_get_manifest_network_error(self, mock_urlopen):
        """get_manifest raises ConnectionError on network failure."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        provider = GitHubProvider()
        with pytest.raises(ConnectionError):
            provider.get_manifest()

    @patch("src.timber_framing_generator.families.providers.urllib.request.urlopen")
    def test_get_manifest_invalid_json(self, mock_urlopen):
        """get_manifest raises ValueError on invalid JSON response."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        provider = GitHubProvider()
        with pytest.raises(ValueError):
            provider.get_manifest()

    @patch("src.timber_framing_generator.families.providers.urllib.request.urlopen")
    def test_download_family_success(self, mock_urlopen, tmp_path):
        """download_family writes file to disk."""
        mock_response = MagicMock()
        mock_response.read.side_effect = [b"fake rfa content", b""]
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        dest = str(tmp_path / "test.rfa")
        provider = GitHubProvider()
        entry = make_family_entry()

        success = provider.download_family(entry, dest)
        assert success
        assert os.path.exists(dest)
        with open(dest, "rb") as f:
            assert f.read() == b"fake rfa content"

    @patch("src.timber_framing_generator.families.providers.urllib.request.urlopen")
    def test_download_family_network_error(self, mock_urlopen, tmp_path):
        """download_family returns False on network error."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Timeout")

        dest = str(tmp_path / "test.rfa")
        provider = GitHubProvider()
        entry = make_family_entry()

        success = provider.download_family(entry, dest)
        assert not success

    def test_manifest_url_construction(self):
        """Manifest URL is correctly constructed from base_url."""
        provider = GitHubProvider(base_url="https://example.com/families")
        url = provider._get_manifest_url()
        assert url == "https://example.com/families/manifest.json"

    def test_custom_manifest_url(self):
        """Custom manifest_url overrides base_url construction."""
        provider = GitHubProvider(
            manifest_url="https://custom.com/my_manifest.json"
        )
        url = provider._get_manifest_url()
        assert url == "https://custom.com/my_manifest.json"


# =============================================================================
# Test: LocalFileProvider
# =============================================================================

class TestLocalFileProvider:
    """Test local file-based provider."""

    def test_provider_name(self):
        """Provider name is 'LocalFile'."""
        provider = LocalFileProvider("/tmp/test")
        assert provider.provider_name == "LocalFile"

    def test_get_manifest_from_file(self, tmp_path):
        """get_manifest reads from local manifest.json."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0",
            "revit_version": "2025",
            "base_url": "",
            "families": {
                "Test": {
                    "file": "test.rfa",
                    "category": "OST_StructuralFraming",
                    "types": {"t": {"width_in": 1.0, "depth_in": 1.0}},
                    "sha256": ""
                }
            }
        }))

        provider = LocalFileProvider(str(tmp_path))
        manifest = provider.get_manifest()
        assert "Test" in manifest.families

    def test_get_manifest_missing_file(self, tmp_path):
        """get_manifest raises FileNotFoundError if manifest.json doesn't exist."""
        provider = LocalFileProvider(str(tmp_path / "nonexistent"))
        with pytest.raises(FileNotFoundError):
            provider.get_manifest()

    def test_download_family_copies_file(self, tmp_path):
        """download_family copies .rfa from source directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.rfa").write_bytes(b"rfa data")

        dest = str(tmp_path / "dest" / "test.rfa")
        provider = LocalFileProvider(str(source_dir))
        entry = FamilyEntry(
            file="test.rfa",
            category="OST_StructuralFraming",
            types={},
            sha256="",
        )

        success = provider.download_family(entry, dest)
        assert success
        assert os.path.exists(dest)

    def test_download_family_missing_source(self, tmp_path):
        """download_family returns False if source file doesn't exist."""
        provider = LocalFileProvider(str(tmp_path))
        entry = FamilyEntry(
            file="nonexistent.rfa",
            category="OST_StructuralFraming",
            types={},
            sha256="",
        )
        success = provider.download_family(entry, str(tmp_path / "dest.rfa"))
        assert not success


# =============================================================================
# Test: ABC Enforcement
# =============================================================================

class TestProviderABC:
    """Test that FamilyProvider ABC requires all methods."""

    def test_cannot_instantiate_abc(self):
        """FamilyProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            FamilyProvider()

    def test_subclass_must_implement_methods(self):
        """Subclass missing abstract methods cannot be instantiated."""
        class IncompleteProvider(FamilyProvider):
            @property
            def provider_name(self):
                return "test"

        with pytest.raises(TypeError):
            IncompleteProvider()
