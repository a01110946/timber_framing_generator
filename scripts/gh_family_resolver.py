# File: scripts/gh_family_resolver.py
"""Family Resolver for Grasshopper.

Resolves Revit family references for framing elements before the bake step.
This component sits between the Framing Generator and Revit Baker in the
pipeline: it fetches a family manifest, downloads missing .rfa files,
loads them into the Revit document, and enriches the framing JSON with
revit_family and revit_type fields.

Key Features:
1. Manifest-Driven Resolution
   - Fetches family manifest from GitHub (or custom URL)
   - Determines which families are needed from framing_json profiles
   - Downloads missing .rfa files to local cache

2. Local Cache with Offline Support
   - Caches .rfa files in %APPDATA%/TimberFramingGenerator/families/
   - SHA256 integrity verification
   - Graceful offline fallback using cached families

3. Revit Integration
   - Loads .rfa families into the active Revit document
   - Activates FamilySymbols for placement
   - Reports already-loaded families to skip redundant work

4. Enriched JSON Output
   - Adds revit_family and revit_type fields to each framing element
   - Pass-through compatible: downstream components receive richer data
   - Missing families listed separately for user action

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and runtime messages
    - RhinoCommon: CLR reference for .NET interop
    - RhinoInside.Revit: Revit document access (conditional)
    - timber_framing_generator.families.resolver: FamilyResolver orchestrator
    - timber_framing_generator.families.providers: GitHubProvider for manifest
    - timber_framing_generator.families.cache: FamilyCache for local storage

Performance Considerations:
    - First run downloads families (network-dependent, ~5-30s)
    - Subsequent runs serve from cache (<1s)
    - Revit LoadFamily calls require transactions (~0.5s per family)
    - For large projects, pre-cache families to avoid network delays

Usage:
    1. Connect 'framing_json' from Framing Generator component
    2. Optionally set 'manifest_url' for custom manifest location
    3. Optionally set 'cache_dir' for custom cache directory
    4. Set 'run' to True to trigger resolution
    5. Connect 'resolved_json' to Revit Baker component
    6. Check 'missing' output for unresolved families

Input Requirements:
    Framing JSON (framing_json) - str:
        JSON string from Framing Generator with all framing elements.
        Must contain "elements" array with "profile.name" fields.
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Manifest URL (manifest_url) - str:
        Full URL to manifest.json file. If not provided, defaults to
        the project's GitHub repository raw URL.
        Required: No (defaults to GitHub URL)
        Access: Item
        Type hint: str (set via GH UI)

    Cache Dir (cache_dir) - str:
        Local directory path for caching .rfa files. If not provided,
        defaults to %APPDATA%/TimberFramingGenerator/families/.
        Required: No (defaults to %APPDATA%)
        Access: Item
        Type hint: str (set via GH UI)

    Run (run) - bool:
        Boolean toggle to trigger execution. When False, component
        outputs empty defaults without processing.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

Outputs:
    Resolved JSON (resolved_json) - str:
        Framing JSON enriched with revit_family and revit_type fields
        on each element. Pass directly to Revit Baker.

    Missing (missing) - list of str:
        List of family keys that could not be resolved. Empty list
        means all families are available.

    Status (status) - str:
        Resolution status: "all_resolved", "partial", "failed", or "offline".
        - all_resolved: every needed family is available
        - partial: some families resolved, some missing
        - failed: no families could be resolved
        - offline: network unavailable, using cached families only

    Info (info) - list of str:
        Diagnostic log with step-by-step resolution details.
        Useful for debugging manifest, network, or Revit loading issues.

Technical Details:
    - Uses FamilyResolver orchestrator for the full resolution pipeline
    - GitHubProvider fetches manifest and .rfa files from GitHub raw URLs
    - FamilyCache stores files with SHA256 integrity verification
    - Revit API calls (LoadFamily, Activate) are isolated in revit_loader.py
    - RhinoInside.Revit import is conditional (component works without Revit)

Error Handling:
    - Invalid/missing framing_json: returns empty output with warning
    - Network errors: falls back to offline/cache-only mode
    - Revit unavailable: resolves and caches families without loading
    - Invalid manifest: logs error, returns failed status
    - All errors reported via dual logging (console + GH runtime messages)

Author: Fernando Maytorena
Version: 1.0.0
"""

import sys
import json
import traceback

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================
# Clear cached modules to ensure fresh imports when script changes.
# IMPORTANT: Must also clear 'src' package — other GH components may have
# loaded it from a different PROJECT_PATH, and its __path__ would point there.
_modules_to_clear = [k for k in sys.modules.keys()
                     if 'timber_framing_generator' in k or k == 'src']
for _mod in _modules_to_clear:
    del sys.modules[_mod]
print(f"[RELOAD] Cleared {len(_modules_to_clear)} cached modules")

# =============================================================================
# .NET / CLR
# =============================================================================

import clr

clr.AddReference('RhinoCommon')
clr.AddReference('Grasshopper')

# Conditional RhinoInside.Revit import
REVIT_AVAILABLE = False
REVIT_DOC = None

try:
    clr.AddReference('RhinoInside.Revit')
    from RhinoInside.Revit import Revit
    REVIT_DOC = Revit.ActiveDBDocument
    if REVIT_DOC is not None:
        REVIT_AVAILABLE = True
except Exception as _revit_err:
    print(f"[INFO] RhinoInside.Revit not available: {_revit_err}")

# =============================================================================
# Rhino / Grasshopper
# =============================================================================

import Grasshopper

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\tfg-family-resolver"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.families.resolver import FamilyResolver, ResolutionResult
from src.timber_framing_generator.families.providers import GitHubProvider
from src.timber_framing_generator.families.cache import FamilyCache

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Family Resolver"
COMPONENT_NICKNAME = "FamRes"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "TFG"
COMPONENT_SUBCATEGORY = "4-Resolve"

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/a01110946/timber_framing_generator/main/families/manifest.json"
)

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message: str, level: str = "info") -> None:
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log
        level: One of "info", "debug", "warning", "error", "remark"
    """
    print(f"[{level.upper()}] {message}")

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


def log_debug(message: str) -> None:
    """Log debug message (console only)."""
    print(f"[DEBUG] {message}")


def log_info(message: str) -> None:
    """Log info message (console only)."""
    print(f"[INFO] {message}")


def log_warning(message: str) -> None:
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message: str) -> None:
    """Log error message (console + GH UI)."""
    log_message(message, "error")


# =============================================================================
# Component Setup
# =============================================================================

def setup_component() -> None:
    """Initialize and configure the Grasshopper component.

    Sets component metadata, input parameters, and output parameters.

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1].

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    Required type hints:
        framing_json: str
        manifest_url: str
        cache_dir: str
        run: bool
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # IMPORTANT: NickName becomes the Python variable name
    # Format: (DisplayName, variable_name, Description, Access)
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Framing JSON", "framing_json", "JSON string from Framing Generator",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Manifest URL", "manifest_url", "URL to manifest.json (optional, uses default GitHub URL)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Cache Dir", "cache_dir", "Local cache directory (optional, defaults to %APPDATA%)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run", "Boolean to trigger execution",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Resolved JSON", "resolved_json", "Framing JSON enriched with Revit family references"),
        ("Missing", "missing", "List of families that could not be resolved"),
        ("Status", "status", "Resolution status (all_resolved / partial / failed / offline)"),
        ("Info", "info", "Diagnostic log"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1  # Skip Output[0]
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc


# =============================================================================
# Helper Functions
# =============================================================================

def _unwrap_gh_input(value):
    """Unwrap Grasshopper list wrapping from a single-item input.

    Grasshopper sometimes wraps item-access inputs in a list.
    This function extracts the first element if wrapped.

    Args:
        value: Input value that may be a list

    Returns:
        Unwrapped value, or None if empty
    """
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def validate_inputs(framing_json_raw, run_raw):
    """Validate component inputs.

    Args:
        framing_json_raw: Raw framing_json input (may be list-wrapped)
        run_raw: Raw run input (may be list-wrapped)

    Returns:
        tuple: (is_valid, framing_json_str, should_run, error_message)
    """
    # Unwrap run toggle
    should_run = _unwrap_gh_input(run_raw)
    if should_run is None:
        should_run = False
    should_run = bool(should_run)

    if not should_run:
        return False, None, False, "Set 'run' to True to execute"

    # Unwrap framing_json
    framing_json_str = _unwrap_gh_input(framing_json_raw)

    if framing_json_str is None or (isinstance(framing_json_str, str) and not framing_json_str.strip()):
        return False, None, True, "No framing_json input provided"

    # Basic JSON validation
    try:
        data = json.loads(framing_json_str)
        if not isinstance(data, dict):
            return False, None, True, "framing_json must be a JSON object (dict)"
        elements = data.get("elements", [])
        if not elements:
            return False, framing_json_str, True, None  # Valid but empty — still allow resolution
    except json.JSONDecodeError as e:
        return False, None, True, f"Invalid JSON in framing_json: {e}"

    return True, framing_json_str, True, None


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the Family Resolver component.

    Coordinates the overall workflow:
    1. Setup component metadata
    2. Validate inputs
    3. Create provider and cache from optional inputs
    4. Run FamilyResolver.resolve() pipeline
    5. Enrich framing_json with resolved family references
    6. Return results

    Returns:
        tuple: (resolved_json, missing, status, info)
    """
    # Default outputs
    default_outputs = ("", [], "pending", [])

    # Setup component
    setup_component()

    try:
        # Validate inputs
        is_valid, framing_json_str, should_run, error_msg = validate_inputs(
            framing_json, run
        )

        if not should_run:
            log_info(error_msg or "Component disabled (run=False)")
            return ("", [], "pending", [error_msg or "Set 'run' to True"])

        if not is_valid:
            if error_msg:
                log_warning(error_msg)
                return ("", [], "failed", [error_msg])
            return default_outputs

        # Build diagnostic info list
        info_lines = [
            "Family Resolver v1.0",
            "=" * 40,
        ]

        # -----------------------------------------------------------------
        # Configure provider
        # -----------------------------------------------------------------
        manifest_url_str = _unwrap_gh_input(manifest_url) if 'manifest_url' in dir() else None
        if not manifest_url_str or not isinstance(manifest_url_str, str) or not manifest_url_str.strip():
            manifest_url_str = DEFAULT_MANIFEST_URL

        info_lines.append(f"Manifest URL: {manifest_url_str}")

        provider = GitHubProvider(manifest_url=manifest_url_str)

        # -----------------------------------------------------------------
        # Configure cache
        # -----------------------------------------------------------------
        cache_dir_str = _unwrap_gh_input(cache_dir) if 'cache_dir' in dir() else None
        if cache_dir_str and isinstance(cache_dir_str, str) and cache_dir_str.strip():
            cache = FamilyCache(cache_dir=cache_dir_str.strip())
            info_lines.append(f"Cache Dir: {cache_dir_str.strip()}")
        else:
            cache = FamilyCache()
            info_lines.append(f"Cache Dir: {cache.cache_dir} (default)")

        # -----------------------------------------------------------------
        # Revit document
        # -----------------------------------------------------------------
        doc = REVIT_DOC
        if doc is not None:
            info_lines.append(f"Revit Document: {doc.Title}")
        else:
            info_lines.append("Revit Document: NOT AVAILABLE (cache-only mode)")
            log_message("No Revit document — families will be cached but not loaded", "remark")

        # -----------------------------------------------------------------
        # Count profiles needed from framing_json
        # -----------------------------------------------------------------
        try:
            data = json.loads(framing_json_str)
            elements = data.get("elements", [])
            profiles = set()
            element_types = {}
            for elem in elements:
                profile = elem.get("profile", {})
                name = profile.get("name", "")
                if name:
                    profiles.add(name)
                elem_type = elem.get("element_type", "unknown")
                element_types[elem_type] = element_types.get(elem_type, 0) + 1

            info_lines.append(f"Total Elements: {len(elements)}")
            info_lines.append(f"Unique Profiles: {sorted(profiles)}")
            info_lines.append(f"Element Types: {dict(sorted(element_types.items()))}")
        except Exception as e:
            info_lines.append(f"Framing JSON parse note: {e}")

        info_lines.append("")

        # -----------------------------------------------------------------
        # Run resolver
        # -----------------------------------------------------------------
        log_info("Starting family resolution...")
        resolver = FamilyResolver(provider=provider, cache=cache)
        result = resolver.resolve(doc=doc, framing_json=framing_json_str)

        # Append resolver's log to our info
        info_lines.append("Resolution Log:")
        for line in result.log:
            info_lines.append(f"  {line}")
        info_lines.append("")

        # -----------------------------------------------------------------
        # Enrich JSON
        # -----------------------------------------------------------------
        if result.status in ("all_resolved", "partial", "offline"):
            enriched_json = resolver.enrich_framing_json(framing_json_str, result)
            log_info(f"Enriched framing JSON ({result.status})")
        else:
            enriched_json = framing_json_str
            log_warning(f"Resolution {result.status} — returning original framing JSON")

        # -----------------------------------------------------------------
        # Build summary
        # -----------------------------------------------------------------
        info_lines.append("Summary:")
        info_lines.append(f"  Status: {result.status}")
        info_lines.append(f"  Resolved: {len(result.resolved)}")
        info_lines.append(f"  Already Loaded: {len(result.already_loaded)}")
        info_lines.append(f"  Newly Loaded: {len(result.loaded)}")
        info_lines.append(f"  Cached: {len(result.cached)}")
        info_lines.append(f"  Missing: {len(result.missing)}")

        if result.missing:
            info_lines.append("")
            info_lines.append("Missing Families:")
            for fam_key in result.missing:
                info_lines.append(f"  - {fam_key}")

        # Status message for GH UI
        if result.status == "all_resolved":
            log_message(
                f"All {len(result.resolved)} families resolved", "remark"
            )
        elif result.status == "partial":
            log_warning(
                f"Partial resolution: {len(result.resolved)} resolved, "
                f"{len(result.missing)} missing"
            )
        elif result.status == "offline":
            log_warning(
                f"Offline mode: {len(result.cached)} families from cache"
            )
        elif result.status == "failed":
            log_error(
                f"Resolution failed — {len(result.missing)} families missing"
            )

        return (enriched_json, result.missing, result.status, info_lines)

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log_error(error_msg)
        log_debug(traceback.format_exc())
        return ("", [], "failed", [error_msg, traceback.format_exc()])


# =============================================================================
# Default Input Handling
# =============================================================================
# Set defaults for optional inputs that may not be wired in Grasshopper.
# This ensures variables exist in global scope before main() references them.

try:
    framing_json
except NameError:
    framing_json = None

try:
    manifest_url
except NameError:
    manifest_url = None

try:
    cache_dir
except NameError:
    cache_dir = None

try:
    run
except NameError:
    run = False

# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    resolved_json, missing, status, info = main()
