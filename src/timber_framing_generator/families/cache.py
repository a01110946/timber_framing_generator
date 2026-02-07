# File: src/timber_framing_generator/families/cache.py
"""
Local cache manager for downloaded Revit family files.

Manages a local directory (default: %APPDATA%/TimberFramingGenerator/families/)
that stores downloaded .rfa files with SHA256 checksum verification. Supports
offline mode by serving cached families when the network is unavailable.

Usage:
    from src.timber_framing_generator.families.cache import FamilyCache

    cache = FamilyCache()
    if cache.is_cached("TFG_Stud_2x4", expected_sha256="abc123"):
        path = cache.get_cached_path("TFG_Stud_2x4")
"""

import hashlib
import json
import logging
import os
import shutil
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default cache location
DEFAULT_CACHE_DIR_NAME = "TimberFramingGenerator"
CACHE_FAMILIES_SUBDIR = "families"
CACHE_MANIFEST_FILENAME = "cache_manifest.json"


def _get_default_cache_dir() -> str:
    """Get the default cache directory path.

    Returns:
        Path to %APPDATA%/TimberFramingGenerator/families/ on Windows,
        or ~/.cache/TimberFramingGenerator/families/ on other platforms.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = os.path.join(appdata, DEFAULT_CACHE_DIR_NAME)
    else:
        home = os.path.expanduser("~")
        base = os.path.join(home, ".cache", DEFAULT_CACHE_DIR_NAME)
    return os.path.join(base, CACHE_FAMILIES_SUBDIR)


class FamilyCache:
    """Manages a local cache of downloaded Revit family (.rfa) files.

    The cache stores files in a directory structure mirroring the manifest's
    file paths, and tracks metadata (SHA256, download time) in a local
    cache_manifest.json file.

    Args:
        cache_dir: Path to cache directory. Defaults to %APPDATA%/TimberFramingGenerator/families/.
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self._cache_dir = cache_dir or _get_default_cache_dir()
        self._cache_manifest: Dict[str, Dict] = {}
        self._ensure_cache_dir()
        self._load_cache_manifest()

    @property
    def cache_dir(self) -> str:
        """Return the cache directory path."""
        return self._cache_dir

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        os.makedirs(self._cache_dir, exist_ok=True)

    def _load_cache_manifest(self) -> None:
        """Load the cache manifest from disk."""
        manifest_path = os.path.join(self._cache_dir, CACHE_MANIFEST_FILENAME)
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    self._cache_manifest = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load cache manifest: %s", e)
                self._cache_manifest = {}
        else:
            self._cache_manifest = {}

    def _save_cache_manifest(self) -> None:
        """Save the cache manifest to disk."""
        manifest_path = os.path.join(self._cache_dir, CACHE_MANIFEST_FILENAME)
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(self._cache_manifest, f, indent=2)
        except OSError as e:
            logger.error("Failed to save cache manifest: %s", e)

    def compute_sha256(self, file_path: str) -> str:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex-encoded SHA256 hash string
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_file_path(self, family_key: str) -> str:
        """Get the expected file path for a cached family.

        Args:
            family_key: Family key (e.g., "TFG_Stud_2x4")

        Returns:
            Full path to the cached .rfa file
        """
        entry = self._cache_manifest.get(family_key, {})
        relative_path = entry.get("relative_path", f"{family_key}.rfa")
        return os.path.join(self._cache_dir, relative_path)

    def is_cached(
        self, family_key: str, expected_sha256: Optional[str] = None
    ) -> bool:
        """Check if a family is cached and optionally verify its checksum.

        Args:
            family_key: Family key to check
            expected_sha256: If provided, verify the cached file matches this hash.
                           Placeholder hashes (starting with "placeholder") are skipped.

        Returns:
            True if family is cached (and checksum matches if provided)
        """
        if family_key not in self._cache_manifest:
            return False

        file_path = self._get_file_path(family_key)
        if not os.path.exists(file_path):
            # File was deleted outside of cache manager
            del self._cache_manifest[family_key]
            self._save_cache_manifest()
            return False

        # Skip checksum verification for placeholder hashes
        if expected_sha256 and not expected_sha256.startswith("placeholder"):
            cached_sha = self._cache_manifest[family_key].get("sha256", "")
            if cached_sha != expected_sha256:
                # Hash mismatch — file may be outdated
                return False

        return True

    def get_cached_path(self, family_key: str) -> Optional[str]:
        """Get the local file path for a cached family.

        Args:
            family_key: Family key to look up

        Returns:
            Full path to the cached .rfa file, or None if not cached
        """
        if family_key not in self._cache_manifest:
            return None

        file_path = self._get_file_path(family_key)
        if not os.path.exists(file_path):
            return None

        return file_path

    def store(
        self,
        family_key: str,
        source_path: str,
        relative_path: str,
        sha256: Optional[str] = None,
    ) -> str:
        """Store a family file in the cache.

        Args:
            family_key: Family key (e.g., "TFG_Stud_2x4")
            source_path: Path to the downloaded .rfa file
            relative_path: Relative path within cache (e.g., "timber/structural_framing/TFG_Stud_2x4.rfa")
            sha256: SHA256 hash (computed from source if not provided)

        Returns:
            Path to the cached file
        """
        if sha256 is None:
            sha256 = self.compute_sha256(source_path)

        dest_path = os.path.join(self._cache_dir, relative_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        # Copy file to cache (don't move — source may be a temp file)
        if os.path.abspath(source_path) != os.path.abspath(dest_path):
            shutil.copy2(source_path, dest_path)

        self._cache_manifest[family_key] = {
            "relative_path": relative_path,
            "sha256": sha256,
        }
        self._save_cache_manifest()

        logger.info("Cached family '%s' at %s", family_key, dest_path)
        return dest_path

    def remove(self, family_key: str) -> bool:
        """Remove a family from the cache.

        Args:
            family_key: Family key to remove

        Returns:
            True if family was removed, False if not found
        """
        if family_key not in self._cache_manifest:
            return False

        file_path = self._get_file_path(family_key)
        if os.path.exists(file_path):
            os.remove(file_path)

        del self._cache_manifest[family_key]
        self._save_cache_manifest()
        return True

    def clear_cache(self) -> int:
        """Remove all cached families.

        Returns:
            Number of families removed
        """
        count = len(self._cache_manifest)
        for family_key in list(self._cache_manifest.keys()):
            file_path = self._get_file_path(family_key)
            if os.path.exists(file_path):
                os.remove(file_path)

        self._cache_manifest = {}
        self._save_cache_manifest()
        return count

    def list_cached(self) -> List[str]:
        """List all cached family keys.

        Returns:
            List of family key strings
        """
        return list(self._cache_manifest.keys())
