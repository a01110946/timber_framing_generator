# File: src/timber_framing_generator/families/revit_loader.py
"""
Revit API integration for loading and activating family types.

This module isolates all Revit-specific API calls behind a clean interface,
keeping the rest of the family resolver system testable without a Revit
environment. All Revit imports are conditional — the module degrades
gracefully when Revit is unavailable.

CPython3 Gotcha:
    Implementing .NET interfaces (like IFamilyLoadOptions) in CPython3
    requires the ``__namespace__`` class attribute. Without it,
    instantiation fails with ``TypeError: interface takes exactly one argument``.

Usage (inside Grasshopper/Rhino.Inside.Revit only):
    from src.timber_framing_generator.families.revit_loader import (
        get_loaded_families, load_family, activate_family_type,
    )

    loaded = get_loaded_families(doc)
    family = load_family(doc, "/path/to/TFG_Stud_2x4.rfa")
    symbol = activate_family_type(doc, family, "2x4")
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# =============================================================================
# Conditional Revit Imports
# =============================================================================

REVIT_AVAILABLE = False
REVIT_ERROR: Optional[str] = None

try:
    import clr
    clr.AddReference("RevitAPI")
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        FamilySymbol,
        Family,
        Transaction,
        ElementId,
        BuiltInCategory,
    )
    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_ERROR = str(e)
except Exception as e:
    REVIT_ERROR = str(e)


# =============================================================================
# IFamilyLoadOptions Implementation (CPython3 compatible)
# =============================================================================

if REVIT_AVAILABLE:
    class FamilyLoadOptions(DB.IFamilyLoadOptions):
        """CPython3-compatible IFamilyLoadOptions implementation.

        CRITICAL: The ``__namespace__`` attribute is REQUIRED for CPython3/pythonnet.
        Without it, ``DB.IFamilyLoadOptions`` instantiation fails with:
            TypeError: interface takes exactly one argument

        This implementation always overwrites existing families/types,
        which is the desired behavior for keeping families up to date.
        """
        __namespace__ = "TimberFramingFamilyLoader"

        def OnFamilyFound(
            self, familyInUse: bool, overwriteParameterValues
        ) -> bool:
            """Called when family is already loaded in project.

            Args:
                familyInUse: Whether the family is currently placed in the project
                overwriteParameterValues: Output - whether to overwrite parameters

            Returns:
                True to continue loading
            """
            overwriteParameterValues.Value = True
            return True

        def OnSharedFamilyFound(
            self, sharedFamily, familyInUse: bool, source, overwriteParameterValues
        ) -> bool:
            """Called when a shared (nested) family is found.

            Args:
                sharedFamily: The shared family
                familyInUse: Whether the shared family is in use
                source: Output - where to load the family from
                overwriteParameterValues: Output - whether to overwrite parameters

            Returns:
                True to continue loading
            """
            source.Value = DB.FamilySource.Family
            overwriteParameterValues.Value = True
            return True


# =============================================================================
# Revit Category Mapping
# =============================================================================

# Map manifest category strings to Revit BuiltInCategory
CATEGORY_MAP: Dict[str, Any] = {}
if REVIT_AVAILABLE:
    CATEGORY_MAP = {
        "OST_StructuralFraming": BuiltInCategory.OST_StructuralFraming,
        "OST_StructuralColumns": BuiltInCategory.OST_StructuralColumns,
        "OST_GenericModel": BuiltInCategory.OST_GenericModel,
    }


# =============================================================================
# Public API
# =============================================================================

def get_loaded_families(
    doc, category_name: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """Query the Revit document for already-loaded families and their types.

    Args:
        doc: Revit Document object
        category_name: Optional manifest category string (e.g., "OST_StructuralFraming")
                       to filter results. If None, returns all families.

    Returns:
        Dict mapping family_name -> {
            "family": Family object,
            "types": { type_name: FamilySymbol }
        }
    """
    if not REVIT_AVAILABLE:
        logger.warning("Revit API not available: %s", REVIT_ERROR)
        return {}

    result: Dict[str, Dict[str, Any]] = {}

    try:
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)

        if category_name and category_name in CATEGORY_MAP:
            bic = CATEGORY_MAP[category_name]
            collector = collector.OfCategory(bic)

        for symbol in collector:
            family_name = symbol.Family.Name
            type_name = symbol.Name

            if family_name not in result:
                result[family_name] = {
                    "family": symbol.Family,
                    "types": {},
                }
            result[family_name]["types"][type_name] = symbol

    except Exception as e:
        logger.error("Error querying loaded families: %s", e)

    return result


def load_family(doc, rfa_path: str) -> Optional[Any]:
    """Load a .rfa family file into the Revit document.

    Uses IFamilyLoadOptions to handle already-loaded families
    (overwrites parameters by default).

    Args:
        doc: Revit Document object
        rfa_path: Absolute path to the .rfa file

    Returns:
        Loaded Family object, or None if loading failed
    """
    if not REVIT_AVAILABLE:
        logger.warning("Revit API not available: %s", REVIT_ERROR)
        return None

    try:
        load_options = FamilyLoadOptions()
        family_ref = clr.Reference[Family]()

        t = Transaction(doc, f"Load Family: {rfa_path}")
        t.Start()

        try:
            success = doc.LoadFamily(rfa_path, load_options, family_ref)
            if success:
                t.Commit()
                print("[LOADER] Loaded family from %s (fresh)" % rfa_path)
                return family_ref.Value
            else:
                # LoadFamily returns False when family already exists
                # BUT with IFamilyLoadOptions returning True, it should
                # have overwritten. Either way, commit (not rollback)
                # to persist any parameter updates.
                t.Commit()
                print("[LOADER] LoadFamily returned False for %s "
                      "(family already in doc, overwrite attempted)" % rfa_path)

                # Return the already-loaded family
                import os
                family_name = os.path.splitext(os.path.basename(rfa_path))[0]
                loaded = get_loaded_families(doc)
                if family_name in loaded:
                    print("[LOADER] Found existing '%s' in document" % family_name)
                    return loaded[family_name]["family"]

                return None
        except Exception as e:
            if t.HasStarted():
                t.RollBack()
            raise

    except Exception as e:
        logger.error("Failed to load family from %s: %s", rfa_path, e)
        return None


def activate_family_type(
    doc, family: Any, type_name: str
) -> Optional[Any]:
    """Activate a specific FamilySymbol (type) so it can be used for placement.

    Revit requires FamilySymbol.Activate() before placing instances.
    See: https://thebuildingcoder.typepad.com/blog/2014/08/activate-your-family-symbol-before-using-it.html

    Args:
        doc: Revit Document object
        family: Revit Family object
        type_name: Name of the type to activate (e.g., "2x4")

    Returns:
        Activated FamilySymbol, or None if not found/activation failed
    """
    if not REVIT_AVAILABLE:
        logger.warning("Revit API not available: %s", REVIT_ERROR)
        return None

    try:
        # Get all symbols for this family
        symbol_ids = family.GetFamilySymbolIds()
        for symbol_id in symbol_ids:
            symbol = doc.GetElement(symbol_id)
            if symbol and symbol.Name == type_name:
                if not symbol.IsActive:
                    t = Transaction(doc, f"Activate Type: {type_name}")
                    t.Start()
                    try:
                        symbol.Activate()
                        doc.Regenerate()
                        t.Commit()
                    except Exception:
                        if t.HasStarted():
                            t.RollBack()
                        raise
                logger.info("Activated type '%s' in family '%s'", type_name, family.Name)
                return symbol

        logger.warning(
            "Type '%s' not found in family '%s'. Available: %s",
            type_name,
            family.Name,
            [doc.GetElement(sid).Name for sid in symbol_ids],
        )
        return None

    except Exception as e:
        logger.error("Failed to activate type '%s': %s", type_name, e)
        return None


def get_all_family_types(doc, family: Any) -> List[str]:
    """Get all type names for a given family.

    Args:
        doc: Revit Document object
        family: Revit Family object

    Returns:
        List of type name strings
    """
    if not REVIT_AVAILABLE:
        return []

    try:
        symbol_ids = family.GetFamilySymbolIds()
        return [doc.GetElement(sid).Name for sid in symbol_ids]
    except Exception as e:
        logger.error("Failed to get family types: %s", e)
        return []


# =============================================================================
# Type Duplication (for families missing manifest-declared types)
# =============================================================================

# Parameter-name fallbacks for framing dimensions. Different .rfa templates use
# different conventions: "b"/"d" (classic structural), "Width"/"Depth" (generic),
# "Section Width"/"Section Height" (some lumber families). Try each in order.
FRAMING_WIDTH_PARAM_NAMES = [
    "b", "Width", "Section Width", "Thickness", "Actual Width",
]
FRAMING_DEPTH_PARAM_NAMES = [
    "d", "Depth", "Section Height", "Height", "Actual Depth",
]


def _set_first_matching_param(symbol, param_names, value_ft) -> Optional[str]:
    """Try each parameter name in order; set the first editable match.

    Returns the name of the parameter that was set, or None if none matched.
    """
    for name in param_names:
        p = symbol.LookupParameter(name)
        if p is not None and not p.IsReadOnly:
            try:
                p.Set(value_ft)
                return name
            except Exception:
                continue
    return None


def _list_editable_params(symbol) -> List[str]:
    """Return names of editable (non-read-only) parameters on a FamilySymbol."""
    try:
        return [p.Definition.Name for p in symbol.Parameters if not p.IsReadOnly]
    except Exception:
        return []


def ensure_type_exists(
    doc,
    family: Any,
    type_name: str,
    width_in: Optional[float] = None,
    depth_in: Optional[float] = None,
) -> Optional[Any]:
    """Return an activated FamilySymbol for the requested type, creating it
    via Duplicate() if it doesn't exist yet.

    Used when a family is already loaded in Revit but is missing types that
    the manifest declares. Looks up the type by name; if absent, duplicates
    an existing type in the family and sets width/depth dimension parameters
    (with fallbacks for common framing parameter conventions).

    Args:
        doc: Revit Document object.
        family: Revit Family object to ensure the type in.
        type_name: Name of the type that should exist (e.g., "2x10").
        width_in: Desired width in inches. If None and type is missing,
            returns None (can't create without dimensions).
        depth_in: Desired depth in inches. If None and type is missing,
            returns None.

    Returns:
        Activated FamilySymbol, or None if lookup/duplication failed.
    """
    if not REVIT_AVAILABLE:
        return None

    try:
        symbol_ids = list(family.GetFamilySymbolIds())

        # Fast path: type already exists — just activate if needed
        for symbol_id in symbol_ids:
            sym = doc.GetElement(symbol_id)
            if sym is not None and sym.Name == type_name:
                if not sym.IsActive:
                    t = Transaction(doc, f"Activate Type: {type_name}")
                    t.Start()
                    try:
                        sym.Activate()
                        doc.Regenerate()
                        t.Commit()
                    except Exception:
                        if t.HasStarted():
                            t.RollBack()
                        raise
                return sym

        # Type missing — need to duplicate
        if width_in is None or depth_in is None:
            logger.warning(
                "Type '%s' missing in family '%s' and no dimensions provided; "
                "cannot create via Duplicate",
                type_name, family.Name,
            )
            return None

        if not symbol_ids:
            logger.warning(
                "Family '%s' has no existing types to duplicate from", family.Name
            )
            return None

        source = doc.GetElement(symbol_ids[0])
        if source is None:
            return None

        width_ft = width_in / 12.0
        depth_ft = depth_in / 12.0

        t = Transaction(doc, f"Create Type: {type_name}")
        t.Start()
        try:
            new_sym = source.Duplicate(type_name)

            width_param = _set_first_matching_param(
                new_sym, FRAMING_WIDTH_PARAM_NAMES, width_ft
            )
            depth_param = _set_first_matching_param(
                new_sym, FRAMING_DEPTH_PARAM_NAMES, depth_ft
            )

            if width_param is None or depth_param is None:
                available = _list_editable_params(new_sym)
                logger.warning(
                    "Duplicated '%s' but failed to set dimensions "
                    "(width_param=%s, depth_param=%s). Editable params: %s",
                    type_name, width_param, depth_param, available,
                )

            if not new_sym.IsActive:
                new_sym.Activate()
            doc.Regenerate()
            t.Commit()

            logger.info(
                "Created type '%s' in family '%s' via Duplicate (width=%.4f ft, "
                "depth=%.4f ft, width_param=%s, depth_param=%s)",
                type_name, family.Name, width_ft, depth_ft,
                width_param, depth_param,
            )
            return new_sym

        except Exception:
            if t.HasStarted():
                t.RollBack()
            raise

    except Exception as e:
        logger.error(
            "ensure_type_exists('%s') failed in family '%s': %s",
            type_name, getattr(family, "Name", "?"), e,
        )
        return None
