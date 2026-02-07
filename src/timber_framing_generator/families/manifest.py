# File: src/timber_framing_generator/families/manifest.py
"""
Family manifest schema definitions for the Family Resolver system.

Defines the JSON manifest structure that declares all required Revit
families, their types, categories, and download paths. Follows the
same dataclass + serialize/deserialize pattern as json_schemas.py.

Usage:
    from src.timber_framing_generator.families.manifest import (
        FamilyManifest, parse_manifest, validate_manifest,
        get_required_profiles,
    )

    manifest = parse_manifest(json_str)
    profiles = get_required_profiles(manifest)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, Union


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FamilyTypeInfo:
    """A single type within a Revit family.

    Attributes:
        width_in: Width in inches (e.g., 1.5 for a 2x4)
        depth_in: Depth in inches (e.g., 3.5 for a 2x4)
        properties: Additional type-specific properties
    """
    width_in: float
    depth_in: float
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FamilyEntry:
    """A single Revit family in the manifest.

    Attributes:
        file: Relative path to .rfa file (e.g., "timber/TFG_Timber_Stud.rfa")
        category: Revit built-in category (e.g., "OST_StructuralFraming")
        types: Dict mapping type name to FamilyTypeInfo
        sha256: SHA256 hash of the .rfa file for integrity verification
        domain: Organizational domain (e.g., "framing", "mep", "connections").
                Used for filtering — the resolver itself is domain-agnostic.
    """
    file: str
    category: str
    types: Dict[str, FamilyTypeInfo]
    sha256: str
    domain: str = "framing"


@dataclass
class FamilyManifest:
    """Top-level family manifest.

    Attributes:
        schema_version: Manifest schema version (e.g., "1.0")
        revit_version: Target Revit version (e.g., "2025")
        base_url: Base URL for downloading family files
        families: Dict mapping family key to FamilyEntry
    """
    schema_version: str
    revit_version: str
    base_url: str
    families: Dict[str, FamilyEntry]


# =============================================================================
# Serialization Functions
# =============================================================================

def parse_manifest(json_str: str) -> FamilyManifest:
    """Parse a JSON string into a FamilyManifest.

    Args:
        json_str: JSON string containing manifest data

    Returns:
        FamilyManifest object

    Raises:
        json.JSONDecodeError: If JSON is invalid
        KeyError: If required fields are missing
    """
    data = json.loads(json_str)

    families = {}
    for family_key, family_data in data.get("families", {}).items():
        types = {}
        for type_name, type_data in family_data.get("types", {}).items():
            properties = {
                k: v for k, v in type_data.items()
                if k not in ("width_in", "depth_in")
            }
            types[type_name] = FamilyTypeInfo(
                width_in=type_data["width_in"],
                depth_in=type_data["depth_in"],
                properties=properties,
            )

        families[family_key] = FamilyEntry(
            file=family_data["file"],
            category=family_data["category"],
            types=types,
            sha256=family_data.get("sha256", ""),
            domain=family_data.get("domain", "framing"),
        )

    return FamilyManifest(
        schema_version=data["schema_version"],
        revit_version=data["revit_version"],
        base_url=data.get("base_url", ""),
        families=families,
    )


def serialize_manifest(manifest: FamilyManifest) -> str:
    """Serialize a FamilyManifest to JSON string.

    Args:
        manifest: FamilyManifest object

    Returns:
        JSON string
    """
    data = {
        "schema_version": manifest.schema_version,
        "revit_version": manifest.revit_version,
        "base_url": manifest.base_url,
        "families": {},
    }

    for family_key, entry in manifest.families.items():
        types_data = {}
        for type_name, type_info in entry.types.items():
            type_dict = {
                "width_in": type_info.width_in,
                "depth_in": type_info.depth_in,
            }
            type_dict.update(type_info.properties)
            types_data[type_name] = type_dict

        data["families"][family_key] = {
            "file": entry.file,
            "category": entry.category,
            "types": types_data,
            "sha256": entry.sha256,
            "domain": entry.domain,
        }

    return json.dumps(data, indent=2)


# =============================================================================
# Validation
# =============================================================================

def validate_manifest(data: Union[str, Dict, FamilyManifest]) -> Tuple[bool, List[str]]:
    """Validate manifest data structure.

    Args:
        data: JSON string, dict, or FamilyManifest object

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: List[str] = []

    try:
        if isinstance(data, str):
            data = json.loads(data)

        if isinstance(data, FamilyManifest):
            data = json.loads(serialize_manifest(data))

        # Required top-level fields
        for field_name in ("schema_version", "revit_version", "families"):
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        if "families" not in data:
            return False, errors

        families = data["families"]
        if not isinstance(families, dict):
            errors.append("'families' must be a dictionary")
            return False, errors

        if len(families) == 0:
            errors.append("Manifest must contain at least one family")

        # Validate each family entry
        for family_key, family_data in families.items():
            prefix = f"Family '{family_key}'"

            if not isinstance(family_data, dict):
                errors.append(f"{prefix}: must be a dictionary")
                continue

            # Required family fields
            if "file" not in family_data:
                errors.append(f"{prefix}: missing 'file' field")
            elif not family_data["file"].endswith(".rfa"):
                errors.append(f"{prefix}: file must end with .rfa")

            if "category" not in family_data:
                errors.append(f"{prefix}: missing 'category' field")

            if "types" not in family_data:
                errors.append(f"{prefix}: missing 'types' field")
            elif not isinstance(family_data["types"], dict):
                errors.append(f"{prefix}: 'types' must be a dictionary")
            elif len(family_data["types"]) == 0:
                errors.append(f"{prefix}: must have at least one type")
            else:
                # Validate each type
                for type_name, type_data in family_data["types"].items():
                    type_prefix = f"{prefix}, type '{type_name}'"
                    if not isinstance(type_data, dict):
                        errors.append(f"{type_prefix}: must be a dictionary")
                        continue
                    if "width_in" not in type_data:
                        errors.append(f"{type_prefix}: missing 'width_in'")
                    elif type_data["width_in"] <= 0:
                        errors.append(f"{type_prefix}: width_in must be positive")
                    if "depth_in" not in type_data:
                        errors.append(f"{type_prefix}: missing 'depth_in'")
                    elif type_data["depth_in"] <= 0:
                        errors.append(f"{type_prefix}: depth_in must be positive")

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {str(e)}")
    except Exception as e:
        errors.append(f"Validation error: {str(e)}")

    return len(errors) == 0, errors


# =============================================================================
# Profile Mapping
# =============================================================================

def get_required_profiles(manifest: FamilyManifest) -> Dict[str, str]:
    """Build a mapping of profile names to family keys.

    This maps the profile names used in framing elements (e.g., "2x4")
    to the manifest family keys (e.g., "TFG_Stud_2x4") that provide them.

    Args:
        manifest: Parsed FamilyManifest

    Returns:
        Dict mapping profile/type name -> family key
    """
    profiles: Dict[str, str] = {}
    for family_key, entry in manifest.families.items():
        for type_name in entry.types:
            profiles[type_name] = family_key
    return profiles


def get_families_for_elements(
    manifest: FamilyManifest,
    element_profiles: List[str],
) -> Dict[str, FamilyEntry]:
    """Determine which families are needed for a set of element profiles.

    Args:
        manifest: Parsed FamilyManifest
        element_profiles: List of profile names from framing elements

    Returns:
        Dict mapping family_key -> FamilyEntry for needed families
    """
    profile_map = get_required_profiles(manifest)
    needed: Dict[str, FamilyEntry] = {}

    for profile_name in set(element_profiles):
        family_key = profile_map.get(profile_name)
        if family_key and family_key not in needed:
            needed[family_key] = manifest.families[family_key]

    return needed
