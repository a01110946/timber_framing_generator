# File: src/timber_framing_generator/families/providers.py
"""
Family provider abstraction for downloading Revit families from remote sources.

Implements the Provider pattern (similar to the Strategy pattern in material_system.py)
to allow swapping between different family sources:
- Tier 1: GitHubProvider (free, direct download from GitHub raw URLs)
- Tier 2: CloudAPIProvider (future: GCS + FastAPI with signed URLs)

Usage:
    from src.timber_framing_generator.families.providers import GitHubProvider

    provider = GitHubProvider()
    manifest = provider.get_manifest()
    success = provider.download_family(entry, "/path/to/dest.rfa")
"""

import json
import logging
import os
import tempfile
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Optional

from src.timber_framing_generator.families.manifest import (
    FamilyEntry,
    FamilyManifest,
    parse_manifest,
)

logger = logging.getLogger(__name__)

# Default GitHub configuration
DEFAULT_GITHUB_BASE_URL = (
    "https://raw.githubusercontent.com/a01110946/timber_framing_generator/main/families"
)
DEFAULT_MANIFEST_FILENAME = "manifest.json"
DEFAULT_TIMEOUT_SECONDS = 30


# =============================================================================
# Abstract Base Class
# =============================================================================

class FamilyProvider(ABC):
    """Abstract base class for family download providers.

    All providers must implement get_manifest() and download_family()
    to support the family resolution pipeline.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable name for this provider."""
        ...

    @abstractmethod
    def get_manifest(self) -> FamilyManifest:
        """Fetch and parse the family manifest from the remote source.

        Returns:
            Parsed FamilyManifest

        Raises:
            ConnectionError: If the remote source is unreachable
            ValueError: If the manifest is invalid
        """
        ...

    @abstractmethod
    def download_family(
        self, family_entry: FamilyEntry, dest_path: str
    ) -> bool:
        """Download a family .rfa file to a local path.

        Args:
            family_entry: FamilyEntry from the manifest
            dest_path: Local path to save the .rfa file

        Returns:
            True if download succeeded, False otherwise
        """
        ...


# =============================================================================
# Tier 1: GitHub Provider
# =============================================================================

class GitHubProvider(FamilyProvider):
    """Downloads families from a GitHub repository via raw URLs.

    This is the Tier 1 (free) provider that downloads directly from
    GitHub's raw.githubusercontent.com. No authentication required
    for public repositories.

    Args:
        base_url: Base URL for family files. Defaults to the project's GitHub repo.
        manifest_url: Full URL to manifest.json. If not provided, constructed
                     from base_url + "manifest.json".
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        manifest_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = (base_url or DEFAULT_GITHUB_BASE_URL).rstrip("/")
        self._manifest_url = manifest_url
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "GitHub"

    @property
    def base_url(self) -> str:
        return self._base_url

    def _get_manifest_url(self) -> str:
        """Get the full URL to the manifest file."""
        if self._manifest_url:
            return self._manifest_url
        return f"{self._base_url}/{DEFAULT_MANIFEST_FILENAME}"

    def get_manifest(self) -> FamilyManifest:
        """Fetch and parse manifest.json from GitHub.

        Returns:
            Parsed FamilyManifest

        Raises:
            ConnectionError: If GitHub is unreachable
            ValueError: If manifest is invalid
        """
        url = self._get_manifest_url()
        logger.info("Fetching manifest from %s", url)

        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "TimberFramingGenerator/1.0")
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                content = response.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Failed to fetch manifest from {url}: {e}"
            ) from e

        try:
            manifest = parse_manifest(content)
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Invalid manifest at {url}: {e}") from e

        # Override base_url if manifest specifies one
        if not manifest.base_url:
            manifest.base_url = self._base_url

        logger.info(
            "Manifest loaded: %d families, Revit %s",
            len(manifest.families),
            manifest.revit_version,
        )
        return manifest

    def download_family(
        self, family_entry: FamilyEntry, dest_path: str
    ) -> bool:
        """Download a .rfa file from GitHub raw URL.

        Args:
            family_entry: FamilyEntry with file path
            dest_path: Local path to save the file

        Returns:
            True if download succeeded
        """
        url = f"{self._base_url}/{family_entry.file}"
        logger.info("Downloading %s from %s", family_entry.file, url)

        try:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            req = urllib.request.Request(url)
            req.add_header("User-Agent", "TimberFramingGenerator/1.0")

            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)

            logger.info("Downloaded %s to %s", family_entry.file, dest_path)
            return True

        except urllib.error.URLError as e:
            logger.error("Download failed for %s: %s", url, e)
            return False
        except OSError as e:
            logger.error("Failed to write %s: %s", dest_path, e)
            return False


# =============================================================================
# Local File Provider (for testing and offline scenarios)
# =============================================================================

class LocalFileProvider(FamilyProvider):
    """Serves families from a local directory.

    Useful for testing and for users who have families on disk
    but not loaded in Revit.

    Args:
        families_dir: Path to local directory containing manifest.json and .rfa files
    """

    def __init__(self, families_dir: str) -> None:
        self._families_dir = families_dir

    @property
    def provider_name(self) -> str:
        return "LocalFile"

    def get_manifest(self) -> FamilyManifest:
        """Load manifest.json from local directory.

        Returns:
            Parsed FamilyManifest

        Raises:
            FileNotFoundError: If manifest.json doesn't exist
        """
        manifest_path = os.path.join(self._families_dir, DEFAULT_MANIFEST_FILENAME)
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
        return parse_manifest(content)

    def download_family(
        self, family_entry: FamilyEntry, dest_path: str
    ) -> bool:
        """Copy a .rfa file from local directory.

        Args:
            family_entry: FamilyEntry with relative file path
            dest_path: Destination path

        Returns:
            True if copy succeeded
        """
        source_path = os.path.join(self._families_dir, family_entry.file)
        if not os.path.exists(source_path):
            logger.error("Local family file not found: %s", source_path)
            return False

        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            import shutil
            shutil.copy2(source_path, dest_path)
            return True
        except OSError as e:
            logger.error("Failed to copy %s to %s: %s", source_path, dest_path, e)
            return False
