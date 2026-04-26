# File: scripts/gh_sheathing_baker.py
"""Sheathing Baker for Grasshopper.

Bakes sheathing Breps into Revit as DirectShape elements with rich metadata,
producing ElementIds and JSON that the Assembly Creator needs to include
sheathing panels in framing assemblies.

Key Features:
1. DirectShape Creation
   - Creates DirectShape elements from sheathing Breps
   - One DirectShapeType per (material_display, face) combination
   - Supports configurable Revit category (default: OST_GenericModel)

2. Rich Metadata via Shared Parameters
   - TFG_WallId, TFG_PanelId, TFG_Face, TFG_Material, etc.
   - Shared parameters are schedulable in Revit
   - Built-in Mark parameter set to panel ID

3. Geometry Conversion
   - Primary: RhinoInside.Revit GeometryEncoder.ToShape()
   - Fallback: TessellatedShapeBuilder mesh conversion
   - Per-panel error handling (skip failures, continue batch)

4. Assembly Integration Output
   - sheathing_ids: Revit ElementIds parallel to input breps
   - sheathing_data_json: JSON matching assembly_creator expectations

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and runtime messages
    - RhinoCommon: CLR reference for .NET interop
    - RhinoInside.Revit: Revit document access and geometry conversion
    - Autodesk.Revit.DB: DirectShape, Transaction, SharedParameters

Performance Considerations:
    - Single transaction for all DirectShapes (lightweight elements)
    - Shared parameter setup is idempotent (safe on every run)
    - GeometryEncoder is preferred over tessellation for speed/fidelity
    - For >100 panels, expect 10-30 seconds total

Usage:
    1. Connect 'sheathing_json' from Sheathing Generator (list access)
    2. Connect 'breps' from Sheathing Geometry Converter
    3. Connect 'panel_ids' from Sheathing Geometry Converter
    4. Connect 'panel_functions' from Sheathing Geometry Converter
    5. Optionally set 'category' (default: OST_GenericModel)
    6. Set 'run' to True to bake
    7. Connect 'sheathing_ids' and 'sheathing_data_json' to Assembly Creator

Input Requirements:
    Sheathing JSON (sheathing_json) - list[str]:
        JSON strings from Sheathing Generator (one per wall).
        Contains panel metadata: wall_id, face, material, dimensions.
        Required: Yes
        Access: List
        Type hint: str (set via GH UI)

    Breps (breps) - list[Brep]:
        Brep geometry from Sheathing Geometry Converter.
        Parallel to panel_ids and panel_functions.
        Required: Yes
        Access: List
        Type hint: No type hint (set via GH UI)

    Panel IDs (panel_ids) - list[str]:
        Sheathing panel ID strings parallel to breps.
        Required: Yes
        Access: List
        Type hint: str (set via GH UI)

    Panel Functions (panel_functions) - list[str]:
        Layer function per panel: "finish", "substrate", "structure", etc.
        Parallel to breps.
        Required: Yes
        Access: List
        Type hint: str (set via GH UI)

    Category (category) - str:
        Revit category override. Default "OST_GenericModel".
        Supported: OST_GenericModel, OST_Parts, OST_StructuralConnections.
        Required: No
        Access: Item
        Type hint: str (set via GH UI)

    Run (run) - bool:
        Boolean toggle to trigger baking. Baking modifies Revit document.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

Outputs:
    Sheathing IDs (sheathing_ids) - list:
        Revit ElementIds parallel to input breps.
        Connect to Assembly Creator input 4.

    Sheathing Data JSON (sheathing_data_json) - str:
        JSON for Assembly Creator: {"panels": [{"panel_id": ..., "wall_id": ...}]}
        Connect to Assembly Creator input 5.

    Stats (stats) - str:
        Baking summary: counts, types created, failures.

    Info (info) - str:
        Detailed diagnostic information.

Technical Details:
    - Uses GeometryEncoder.ToShape() for Brep -> Revit geometry (preferred)
    - Falls back to TessellatedShapeBuilder if GeometryEncoder fails
    - Shared parameters created via temporary TFG_SharedParameters.txt file
    - DirectShapeType cached per (material, face) to avoid duplicates
    - Single Revit Transaction wraps all DirectShape creation

Error Handling:
    - Per-panel: geometry conversion failure skips panel, logs warning
    - Revit unavailable: returns empty outputs with error message
    - Empty inputs: returns empty outputs with info message
    - Mismatched list lengths: warns, processes up to minimum length
    - Invalid category: falls back to OST_GenericModel with warning

Author: Fernando Maytorena
Version: 1.0.0
"""

import sys
import json
import os
import traceback

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================
# Clear cached modules to ensure fresh imports when script changes.
# IMPORTANT: Must also clear 'src' package -- other GH components may have
# loaded it from a different PROJECT_PATH, and its __path__ would point there.
_modules_to_clear = [k for k in sys.modules.keys()
                     if 'timber_framing_generator' in k or k == 'src']
for _mod in _modules_to_clear:
    del sys.modules[_mod]
print("[RELOAD] Cleared %d cached modules" % len(_modules_to_clear))

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
    print("[INFO] RhinoInside.Revit not available: %s" % str(_revit_err))

# Conditional Revit DB imports
REVIT_DB_AVAILABLE = False
try:
    from Autodesk.Revit.DB import (
        BuiltInCategory,
        BuiltInParameter,
        DirectShape,
        DirectShapeType,
        ElementId,
        ExternalDefinitionCreationOptions,
        FilteredElementCollector,
        SpecTypeId,
        Transaction,
    )
    REVIT_DB_AVAILABLE = True
except ImportError as _db_err:
    print("[INFO] Revit DB imports not available: %s" % str(_db_err))

# Parameter group for binding: Revit 2024+ uses GroupTypeId, older uses BuiltInParameterGroup
PARAM_GROUP_DATA = None
try:
    from Autodesk.Revit.DB import GroupTypeId
    PARAM_GROUP_DATA = GroupTypeId.Data
except (ImportError, AttributeError):
    try:
        from Autodesk.Revit.DB import BuiltInParameterGroup
        PARAM_GROUP_DATA = BuiltInParameterGroup.PG_DATA
    except ImportError:
        pass  # Will be caught at usage time

# Conditional RiR geometry converter
RIR_GEOM_AVAILABLE = False
try:
    from RhinoInside.Revit.Convert.Geometry import GeometryEncoder
    RIR_GEOM_AVAILABLE = True
except ImportError:
    print("[INFO] RhinoInside.Revit geometry converter not available")

# Conditional TessellatedShapeBuilder fallback imports
TESS_AVAILABLE = False
try:
    from Autodesk.Revit.DB import (
        TessellatedShapeBuilder,
        TessellatedShapeBuilderTarget,
        TessellatedShapeBuilderFallback,
        TessellatedFace,
    )
    from Autodesk.Revit.DB import XYZ
    TESS_AVAILABLE = True
except ImportError:
    pass

# =============================================================================
# Rhino / Grasshopper
# =============================================================================

import Grasshopper

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Sheathing Baker"
COMPONENT_NICKNAME = "SheathBake"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "TFG"
COMPONENT_SUBCATEGORY = "Revit"

SHARED_PARAM_FILENAME = "TFG_SharedParameters.txt"

# Supported category strings (for documentation; resolved dynamically via getattr)
# "OST_GenericModel" (default), "OST_Parts", "OST_StructuralConnections", etc.

# Parameter definitions: (name, spec_type_id_attr)
# spec_type_id_attr is resolved at runtime from SpecTypeId
TFG_PARAM_DEFS = [
    ("TFG_WallId", "string"),
    ("TFG_PanelId", "string"),
    ("TFG_Face", "string"),
    ("TFG_Material", "string"),
    ("TFG_ThicknessIn", "number"),
    ("TFG_WidthFt", "number"),
    ("TFG_HeightFt", "number"),
    ("TFG_AreaSqFt", "number"),
    ("TFG_LayerFunction", "string"),
]

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log (ASCII only -- no unicode)
        level: One of "info", "debug", "warning", "error", "remark"
    """
    print("[%s] %s" % (level.upper(), message))

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


def log_debug(message):
    """Log debug message (console only)."""
    print("[DEBUG] %s" % message)


def log_info(message):
    """Log info message (console only)."""
    print("[INFO] %s" % message)


def log_warning(message):
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message):
    """Log error message (console + GH UI)."""
    log_message(message, "error")


# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component.

    Sets component metadata, input parameters, and output parameters.

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1].

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    Required type hints:
        sheathing_json: str
        breps: No type hint (GH default)
        panel_ids: str
        panel_functions: str
        category: str
        run: bool
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Sheathing JSON", "sheathing_json",
         "JSON from Sheathing Generator (full metadata, one per wall)",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Breps", "breps",
         "Brep list from Sheathing Geometry Converter",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Panel IDs", "panel_ids",
         "Sheathing panel ID list (parallel to breps)",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Panel Functions", "panel_functions",
         "Layer function list (parallel to breps): finish, substrate, etc.",
         Grasshopper.Kernel.GH_ParamAccess.list),
        ("Category", "category",
         "Revit category override (default: OST_GenericModel)",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Boolean to trigger baking",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    # Guard: only set properties that actually differ from current values.
    # Setting Access unconditionally can trigger GH parameter reconstruction
    # which silently disconnects wires (even if the value doesn't change).
    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            p = inputs[i]
            if p.Name != name:
                p.Name = name
            if p.NickName != nick:
                p.NickName = nick
            if p.Description != desc:
                p.Description = desc
            if p.Access != access:
                p.Access = access

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Sheathing IDs", "sheathing_ids",
         "List of Revit ElementIds (parallel to input breps)"),
        ("Sheathing Data JSON", "sheathing_data_json",
         "JSON for Assembly Creator: {panels: [{panel_id, wall_id}]}"),
        ("Stats", "stats",
         "Baking summary (counts, types, failures)"),
        ("Info", "info",
         "Detailed diagnostic info"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1  # Skip Output[0]
        if idx < outputs.Count:
            o = outputs[idx]
            if o.Name != name:
                o.Name = name
            if o.NickName != nick:
                o.NickName = nick
            if o.Description != desc:
                o.Description = desc


# =============================================================================
# Helper Functions
# =============================================================================

def _get_first_branch(param):
    """Get the first branch of data from a GH parameter's VolatileData.

    Handles both typed (GH_Structure[GH_String]) and untyped
    (GH_Structure[IGH_Goo]) parameters.

    Args:
        param: A GH input parameter object

    Returns:
        List-like branch data, or None if empty
    """
    data = param.VolatileData

    # Try .Branch(0) first (works for typed parameters)
    if hasattr(data, 'Branch'):
        try:
            return data.Branch(0)
        except Exception:
            pass

    # Try get_Branch (pythonnet explicit getter)
    if hasattr(data, 'get_Branch'):
        try:
            return data.get_Branch(0)
        except Exception:
            pass

    # Fallback: iterate Branches property
    if hasattr(data, 'Branches'):
        try:
            branches = list(data.Branches)
            if branches:
                return branches[0]
        except Exception:
            pass

    # Last resort: AllData gives flat list of all items
    if hasattr(data, 'AllData'):
        try:
            all_items = data.AllData(True)
            return all_items
        except Exception:
            pass

    return None


def _read_string_input(inputs, index):
    """Read a string value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index

    Returns:
        str or None if input is empty or missing
    """
    if index >= inputs.Count:
        return None
    if inputs[index].VolatileDataCount == 0:
        return None
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return None
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return None
    return str(val)


def _read_list_input(inputs, index):
    """Read a list of values from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index

    Returns:
        list of values (may be empty)
    """
    result = []
    if index >= inputs.Count:
        return result
    if inputs[index].VolatileDataCount == 0:
        return result
    branch = _get_first_branch(inputs[index])
    if branch is None:
        return result
    for item in branch:
        val = item.Value if hasattr(item, 'Value') else item
        result.append(val)
    return result


def _read_bool_input(inputs, index, default=False):
    """Read a boolean value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index
        default: Default value if input is empty

    Returns:
        bool
    """
    if index >= inputs.Count:
        return default
    if inputs[index].VolatileDataCount == 0:
        return default
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return default
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return default
    return bool(val)


# =============================================================================
# Panel Metadata Lookup
# =============================================================================

def _build_panel_metadata_lookup(sheathing_json_list):
    """Build lookup: sheathing_panel_id -> metadata dict.

    Handles both single-layer and multi-layer JSON formats from the
    Sheathing Generator / Multi-Layer Sheathing Generator.

    Accepts JSON that parses to either:
    - A dict (single wall): {"wall_id": ..., "sheathing_panels": [...]}
    - A list of dicts (multiple walls): [{"wall_id": ..., ...}, ...]
    - A wrapper dict: {"walls": [...]} or {"results": [...]}

    Args:
        sheathing_json_list: List of JSON strings, one per wall (or per batch).

    Returns:
        dict: Mapping panel_id -> metadata dict with keys like
              wall_id, face, material_display, thickness_inches, etc.
    """
    lookup = {}
    for json_str in sheathing_json_list:
        if not json_str:
            continue
        try:
            data = json.loads(str(json_str))
        except (json.JSONDecodeError, TypeError):
            continue

        # Normalize to list of wall dicts
        wall_entries = _normalize_to_wall_entries(data)

        for wall_entry in wall_entries:
            _extract_panels_from_wall_entry(wall_entry, lookup)

    return lookup


def _normalize_to_wall_entries(data):
    """Normalize parsed JSON to a list of wall-level dicts.

    Args:
        data: Parsed JSON (dict or list)

    Returns:
        list of dicts, each representing one wall's sheathing data
    """
    if isinstance(data, dict):
        # Wrapper formats: {"walls": [...]} or {"results": [...]}
        if "walls" in data and isinstance(data["walls"], list):
            return data["walls"]
        if "results" in data and isinstance(data["results"], list):
            return data["results"]
        # Single wall dict
        return [data]
    elif isinstance(data, list):
        # Already a list of wall dicts
        return data
    return []


def _extract_panels_from_wall_entry(wall_entry, lookup):
    """Extract panel metadata from a single wall entry into the lookup.

    Args:
        wall_entry: Dict with wall sheathing data
        lookup: Dict to populate (panel_id -> metadata)
    """
    if not isinstance(wall_entry, dict):
        return

    wall_id = wall_entry.get("wall_id", "")

    # Single-layer format: has "sheathing_panels"
    panels = wall_entry.get("sheathing_panels", [])

    # Multi-layer format: has "layer_results" instead
    if not panels and "layer_results" in wall_entry:
        for layer in wall_entry.get("layer_results", []):
            layer_function = layer.get("layer_function", "unknown")
            for panel in layer.get("panels", []):
                enriched = dict(panel)
                enriched["layer_function"] = layer_function
                if "wall_id" not in enriched:
                    enriched["wall_id"] = wall_id
                pid = enriched.get("id")
                if pid:
                    if pid in lookup:
                        log_warning(
                            "Duplicate sheathing panel ID '%s' in wall %s "
                            "(panel_id collision -- restart Rhino to reload "
                            "sheathing_generator fix)" % (pid, wall_id)
                        )
                    lookup[pid] = enriched
    else:
        for panel in panels:
            enriched = dict(panel)
            if "wall_id" not in enriched:
                enriched["wall_id"] = wall_id
            pid = enriched.get("id")
            if pid:
                lookup[pid] = enriched


# =============================================================================
# DirectShapeType Caching
# =============================================================================

def _make_type_name(material_display, face):
    """Generate DirectShapeType name from material and face.

    Args:
        material_display: Material display name (e.g. 'OSB 7/16"')
        face: Face string (e.g. "exterior", "interior")

    Returns:
        str: Type name like 'OSB 7/16" - Exterior'
    """
    return "%s - %s" % (material_display, face.title())


def _get_or_create_ds_type(doc, material_display, face, category_id, type_cache):
    """Get or create a DirectShapeType for this material+face combination.

    Caches types to avoid recreating on the same run. Also checks existing
    types in the document to handle re-runs gracefully.

    Args:
        doc: Revit Document
        material_display: Material display string
        face: Face string (exterior/interior)
        category_id: ElementId of the target category
        type_cache: Dict for caching types within this run

    Returns:
        DirectShapeType instance
    """
    cache_key = (material_display, face)
    if cache_key in type_cache:
        return type_cache[cache_key]

    type_name = _make_type_name(material_display, face)

    # Check existing in document (handles re-runs)
    collector = FilteredElementCollector(doc).OfClass(DirectShapeType)
    for existing in collector:
        try:
            if existing.Name == type_name:
                type_cache[cache_key] = existing
                return existing
        except Exception:
            continue

    # Create new DirectShapeType
    ds_type = DirectShapeType.Create(doc, type_name, category_id)
    type_cache[cache_key] = ds_type
    return ds_type


# =============================================================================
# Shared Parameters
# =============================================================================

def _get_spec_type_id(param_type_str):
    """Get the SpecTypeId for a parameter type string.

    Args:
        param_type_str: "string" or "number"

    Returns:
        SpecTypeId value for the parameter
    """
    if param_type_str == "string":
        return SpecTypeId.String.Text
    else:
        return SpecTypeId.Number


def _ensure_shared_parameters(doc, bic):
    """Ensure TFG shared parameters exist and are bound to the target category.

    Creates a temporary shared parameter file if needed, defines all
    TFG_* parameters, and binds them as instance parameters to the category.
    Idempotent -- safe to call on every run.

    NOTE: ParameterBindings.Insert() modifies the Revit document and requires
    its own transaction. This function manages that transaction internally.

    Args:
        doc: Revit Document
        bic: BuiltInCategory enum value (NOT ElementId)
    """
    app = doc.Application

    # 1. Save current shared param file path (restore later)
    original_sp_path = app.SharedParametersFilename

    # 2. Create/open TFG shared parameter file in project directory
    sp_path = os.path.join(PROJECT_PATH, SHARED_PARAM_FILENAME)
    if not os.path.exists(sp_path):
        open(sp_path, "w").close()  # Create empty file (Revit requires it exists)
    app.SharedParametersFilename = sp_path
    sp_file = app.OpenSharedParameterFile()

    try:
        # 3. Get or create parameter group in shared param file (no transaction needed)
        group = sp_file.Groups.get_Item("TFG Sheathing")
        if group is None:
            group = sp_file.Groups.Create("TFG Sheathing")

        # 4. Define parameters in shared param file (no transaction needed)
        definitions = []
        for param_name, param_type_str in TFG_PARAM_DEFS:
            existing_def = group.Definitions.get_Item(param_name)
            if existing_def is None:
                spec_id = _get_spec_type_id(param_type_str)
                opts = ExternalDefinitionCreationOptions(param_name, spec_id)
                opts.UserModifiable = True
                existing_def = group.Definitions.Create(opts)
            definitions.append(existing_def)

        # 5. Bind parameters to category (REQUIRES transaction)
        cat = doc.Settings.Categories.get_Item(bic)
        cat_set = app.Create.NewCategorySet()
        cat_set.Insert(cat)
        instance_binding = app.Create.NewInstanceBinding(cat_set)

        # Check which definitions need binding
        defs_to_bind = [
            d for d in definitions
            if not doc.ParameterBindings.Contains(d)
        ]

        if defs_to_bind:
            t = Transaction(doc, "TFG: Bind Shared Parameters")
            t.Start()
            try:
                for defn in defs_to_bind:
                    if PARAM_GROUP_DATA is not None:
                        doc.ParameterBindings.Insert(
                            defn, instance_binding,
                            PARAM_GROUP_DATA,
                        )
                    else:
                        doc.ParameterBindings.Insert(
                            defn, instance_binding,
                        )
                t.Commit()
                log_info("Bound %d shared parameters" % len(defs_to_bind))
            except Exception:
                if t.HasStarted():
                    t.RollBack()
                raise
        else:
            log_info("All shared parameters already bound")

    finally:
        # 6. Restore original shared param file
        if original_sp_path:
            app.SharedParametersFilename = original_sp_path


# =============================================================================
# Geometry Conversion
# =============================================================================

# Discovery-based RiR geometry conversion method.
# RiR API changes across versions -- we probe for available methods once.
_RIR_CONVERT_FN = None
_RIR_PROBED = False


def _probe_rir_convert():
    """Discover the correct RiR geometry conversion function.

    Tries multiple method names on GeometryEncoder and alternative
    encoder classes. Logs available methods for debugging on first call.

    Returns:
        callable or None
    """
    global _RIR_CONVERT_FN, _RIR_PROBED
    if _RIR_PROBED:
        return _RIR_CONVERT_FN
    _RIR_PROBED = True

    if not RIR_GEOM_AVAILABLE:
        return None

    # Log available members for debugging
    members = [m for m in dir(GeometryEncoder) if not m.startswith('_')]
    log_info("GeometryEncoder available members: %s" % ", ".join(members))

    # Try known method names in preference order on GeometryEncoder
    for method_name in [
        "ToSolid", "ToShape", "ToGeometryObject", "ToGeometryObjects",
        "EncodeBrep", "Encode", "ToDirectShape",
    ]:
        fn = getattr(GeometryEncoder, method_name, None)
        if fn is not None:
            log_info("Found RiR convert method: GeometryEncoder.%s" % method_name)
            _RIR_CONVERT_FN = fn
            return fn

    # Try BrepEncoder if available
    try:
        from RhinoInside.Revit.Convert.Geometry import BrepEncoder
        be_members = [m for m in dir(BrepEncoder) if not m.startswith('_')]
        log_info("BrepEncoder available members: %s" % ", ".join(be_members))
        for method_name in ["ToSolid", "ToShape", "Encode", "ToBrep"]:
            fn = getattr(BrepEncoder, method_name, None)
            if fn is not None:
                log_info("Found RiR convert method: BrepEncoder.%s" % method_name)
                _RIR_CONVERT_FN = fn
                return fn
    except ImportError:
        pass

    # Try RawEncoder
    try:
        from RhinoInside.Revit.Convert.Geometry import RawEncoder
        re_members = [m for m in dir(RawEncoder) if not m.startswith('_')]
        log_info("RawEncoder available members: %s" % ", ".join(re_members))
        for method_name in ["ToHost", "ToSolid", "ToShape"]:
            fn = getattr(RawEncoder, method_name, None)
            if fn is not None:
                log_info("Found RiR convert method: RawEncoder.%s" % method_name)
                _RIR_CONVERT_FN = fn
                return fn
    except ImportError:
        pass

    # Try entire Convert.Geometry namespace for any encoder
    try:
        import RhinoInside.Revit.Convert.Geometry as rir_geom
        ns_members = [m for m in dir(rir_geom) if 'Encode' in m or 'Convert' in m]
        log_info("RiR Convert.Geometry namespace encoders: %s" % ", ".join(ns_members))
    except Exception:
        pass

    log_warning("No RiR geometry conversion method found")
    return None


def _convert_brep_to_revit(brep):
    """Convert a RhinoCommon Brep to Revit GeometryObject list.

    Primary: RiR GeometryEncoder (auto-discovered method).
    Fallback: TessellatedShapeBuilder mesh conversion.

    Args:
        brep: RhinoCommon Brep

    Returns:
        .NET IList<GeometryObject> or None if conversion fails
    """
    # Primary: RiR GeometryEncoder (discovery-based)
    convert_fn = _probe_rir_convert()
    if convert_fn is not None:
        try:
            result = convert_fn(brep)
            # Result may be a single GeometryObject or IList<GeometryObject>
            if result is not None:
                # If it has Count, it's a list
                if hasattr(result, 'Count'):
                    if result.Count > 0:
                        return result
                else:
                    # Single object -- wrap in .NET list
                    from System.Collections.Generic import List as NetList
                    from Autodesk.Revit.DB import GeometryObject
                    geom_list = NetList[GeometryObject]()
                    geom_list.Add(result)
                    return geom_list
        except Exception as e:
            log_debug("RiR convert failed: %s" % str(e))

    # Fallback: Tessellated mesh
    if TESS_AVAILABLE:
        return _convert_brep_tessellated(brep)

    return None


def _mesh_brep(brep):
    """Mesh a Brep using multiple fallback approaches for CPython3 compatibility.

    CPython3 + pythonnet may not expose Mesh.CreateFromBrep as a static method.
    We try multiple approaches to get mesh data from the Brep.

    Args:
        brep: RhinoCommon Brep

    Returns:
        list of Mesh objects, or None if all approaches fail
    """
    import Rhino.Geometry as rg

    # Approach 1: Mesh.CreateFromBrep static method (standard API)
    try:
        mesh_params = rg.MeshingParameters.Default
        meshes = rg.Mesh.CreateFromBrep(brep, mesh_params)
        if meshes and len(meshes) > 0:
            return list(meshes)
    except (AttributeError, Exception) as e:
        log_debug("Mesh.CreateFromBrep failed: %s" % str(e))

    # Approach 2: Per-face render mesh extraction
    # If the Brep already has render meshes attached, extract them directly
    try:
        combined = rg.Mesh()
        got_any = False
        for face_idx in range(brep.Faces.Count):
            face = brep.Faces[face_idx]
            face_mesh = face.GetMesh(rg.MeshType.Any)
            if face_mesh is not None:
                combined.Append(face_mesh)
                got_any = True
        if got_any and combined.Vertices.Count > 0:
            return [combined]
    except (AttributeError, Exception) as e:
        log_debug("Per-face mesh extraction failed: %s" % str(e))

    # Approach 3: Compute render meshes via brep.CreateMesh
    try:
        mesh_params = rg.MeshingParameters.Default
        if hasattr(brep, 'CreateMesh'):
            meshes = brep.CreateMesh(mesh_params)
            if meshes and len(meshes) > 0:
                return list(meshes)
    except (AttributeError, Exception) as e:
        log_debug("brep.CreateMesh failed: %s" % str(e))

    # Approach 4: Use Rhino's compute-based meshing
    try:
        import Rhino
        mesh_params = rg.MeshingParameters.Default
        meshes = Rhino.Geometry.Mesh.CreateFromBrep(brep, mesh_params)
        if meshes and len(meshes) > 0:
            return list(meshes)
    except (AttributeError, Exception) as e:
        log_debug("Rhino.Geometry.Mesh.CreateFromBrep failed: %s" % str(e))

    return None


def _convert_brep_tessellated(brep):
    """Convert Brep to Revit geometry via tessellation fallback.

    Meshes the Brep and builds a TessellatedShapeBuilder solid.

    Args:
        brep: RhinoCommon Brep

    Returns:
        .NET IList<GeometryObject> or None if conversion fails
    """
    try:
        meshes = _mesh_brep(brep)
        if not meshes:
            return None

        builder = TessellatedShapeBuilder()
        builder.OpenConnectedFaceSet(True)

        total_faces = 0
        for mesh in meshes:
            mesh.Faces.ConvertQuadsToTriangles()
            for i in range(mesh.Faces.Count):
                face = mesh.Faces[i]
                v0 = mesh.Vertices[face.A]
                v1 = mesh.Vertices[face.B]
                v2 = mesh.Vertices[face.C]

                p0 = XYZ(float(v0.X), float(v0.Y), float(v0.Z))
                p1 = XYZ(float(v1.X), float(v1.Y), float(v1.Z))
                p2 = XYZ(float(v2.X), float(v2.Y), float(v2.Z))

                tess_face = TessellatedFace(
                    [p0, p1, p2], ElementId.InvalidElementId
                )
                builder.AddFace(tess_face)
                total_faces += 1

        builder.CloseConnectedFaceSet()
        builder.Target = TessellatedShapeBuilderTarget.Solid
        builder.Fallback = TessellatedShapeBuilderFallback.Mesh
        builder.Build()

        result = builder.GetBuildResult()
        geom_objects = result.GetGeometricalObjects()
        if geom_objects and geom_objects.Count > 0:
            return geom_objects
    except Exception as e:
        log_debug("Tessellation fallback failed: %s" % str(e))

    return None


# =============================================================================
# Parameter Setting
# =============================================================================

def _set_panel_metadata(ds, panel_id_str, meta, layer_function, seq_index=0):
    """Set all metadata parameters on a DirectShape element.

    Sets both the built-in Mark parameter and all TFG_* shared parameters.

    Args:
        ds: DirectShape element
        panel_id_str: Panel ID string (stored in TFG_PanelId)
        meta: Panel metadata dict from the lookup
        layer_function: Layer function string (finish, substrate, etc.)
        seq_index: Sequential index for unique Mark value
    """
    # Built-in Mark parameter -- must be unique to avoid Revit warnings.
    # Combine wall_id + face + sequential index for uniqueness.
    wall_id = meta.get("wall_id", "")
    face = meta.get("face", "")
    mark_value = "SH-%s-%s-%04d" % (wall_id, face, seq_index)
    mark_param = ds.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if mark_param and not mark_param.IsReadOnly:
        mark_param.Set(mark_value)

    # TFG shared parameters via LookupParameter
    _set_str(ds, "TFG_WallId", meta.get("wall_id", ""))
    _set_str(ds, "TFG_PanelId", meta.get("panel_id", meta.get("id", "")))
    _set_str(ds, "TFG_Face", meta.get("face", ""))
    _set_str(ds, "TFG_Material", meta.get("material_display",
                                           meta.get("material", "")))
    _set_double(ds, "TFG_ThicknessIn", meta.get("thickness_inches", 0.0))
    _set_double(ds, "TFG_WidthFt", meta.get("width", 0.0))
    _set_double(ds, "TFG_HeightFt", meta.get("height", 0.0))
    _set_double(ds, "TFG_AreaSqFt", meta.get("area_net_sqft", 0.0))
    _set_str(ds, "TFG_LayerFunction", layer_function or "")


def _set_str(element, param_name, value):
    """Set a string parameter on a Revit element.

    Args:
        element: Revit Element
        param_name: Parameter name to look up
        value: String value to set
    """
    p = element.LookupParameter(param_name)
    if p and not p.IsReadOnly:
        p.Set(str(value))


def _set_double(element, param_name, value):
    """Set a double parameter on a Revit element.

    Args:
        element: Revit Element
        param_name: Parameter name to look up
        value: Numeric value to set
    """
    p = element.LookupParameter(param_name)
    if p and not p.IsReadOnly:
        p.Set(float(value))


# =============================================================================
# Category Resolution
# =============================================================================

def _resolve_category_id(doc, category_str):
    """Resolve a category string to a Revit ElementId and BuiltInCategory.

    Args:
        doc: Revit Document
        category_str: Category string (e.g. "OST_GenericModel")

    Returns:
        tuple: (category_id, actual_category_name, builtin_category_enum)
    """
    # Resolve string to BuiltInCategory enum (lazy lookup to avoid
    # AttributeError on categories that don't exist in this Revit version)
    bic = None
    try:
        bic = getattr(BuiltInCategory, category_str, None)
    except Exception:
        pass

    if bic is None:
        log_warning(
            "Unknown category '%s', falling back to OST_GenericModel"
            % category_str
        )
        bic = BuiltInCategory.OST_GenericModel
        category_str = "OST_GenericModel"

    category_id = ElementId(bic)

    # Validate the category is valid for DirectShape
    if not DirectShape.IsValidCategoryId(category_id, doc):
        log_warning(
            "Category '%s' is not valid for DirectShape, "
            "falling back to OST_GenericModel" % category_str
        )
        bic = BuiltInCategory.OST_GenericModel
        category_id = ElementId(bic)
        category_str = "OST_GenericModel"

    return category_id, category_str, bic


# =============================================================================
# Validation
# =============================================================================

def validate_inputs(breps_val, panel_ids_val, run_val):
    """Validate component inputs.

    Args:
        breps_val: List of Brep geometry
        panel_ids_val: List of panel ID strings
        run_val: Boolean run toggle

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_val:
        return False, "Set 'run' to True to execute"

    if not breps_val or len(breps_val) == 0:
        return False, "No breps provided"

    if not panel_ids_val or len(panel_ids_val) == 0:
        return False, "No panel_ids provided"

    if not REVIT_AVAILABLE:
        return False, "Revit document is not available (RhinoInside.Revit required)"

    if not REVIT_DB_AVAILABLE:
        return False, "Revit DB imports not available"

    return True, None


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the Sheathing Baker component.

    Coordinates the overall workflow:
    1. Read inputs by parameter index
    2. Setup component metadata (display only)
    3. Validate inputs
    4. Build metadata lookup from sheathing JSON
    5. Ensure shared parameters exist in Revit
    6. Create DirectShape elements in a single transaction
    7. Return IDs, JSON, stats, and info

    Returns:
        tuple: (sheathing_ids, sheathing_data_json, stats, info)
    """
    # -----------------------------------------------------------------
    # Read inputs by parameter index (CRITICAL: NickName injection is unreliable)
    # -----------------------------------------------------------------
    inputs = ghenv.Component.Params.Input

    sheathing_json_val = _read_list_input(inputs, 0)
    breps_val = _read_list_input(inputs, 1)
    panel_ids_val = _read_list_input(inputs, 2)
    panel_functions_val = _read_list_input(inputs, 3)
    category_val = _read_string_input(inputs, 4)
    run_val = _read_bool_input(inputs, 5, default=False)

    # -----------------------------------------------------------------
    # Setup component metadata (display only, AFTER inputs are captured)
    # -----------------------------------------------------------------
    setup_component()

    try:
        # -----------------------------------------------------------------
        # Validate inputs
        # -----------------------------------------------------------------
        is_valid, error_msg = validate_inputs(breps_val, panel_ids_val, run_val)

        if not is_valid:
            if run_val:
                log_warning(error_msg)
            else:
                log_info(error_msg or "Component disabled (run=False)")
            return ([], "", "", error_msg or "Not running")

        # -----------------------------------------------------------------
        # Build diagnostic info
        # -----------------------------------------------------------------
        info_lines = [
            "Sheathing Baker v1.0",
            "=" * 40,
        ]

        # Apply defaults
        category_str = category_val if category_val else "OST_GenericModel"

        info_lines.append("Category: %s" % category_str)
        info_lines.append("Revit Document: %s" % (
            REVIT_DOC.Title if REVIT_DOC else "N/A"))
        info_lines.append("")
        info_lines.append("Input Counts:")
        info_lines.append("  Sheathing JSON entries: %d" % len(sheathing_json_val))
        info_lines.append("  Breps: %d" % len(breps_val))
        info_lines.append("  Panel IDs: %d" % len(panel_ids_val))
        info_lines.append("  Panel Functions: %d" % len(panel_functions_val))

        # Check for mismatched list lengths
        min_count = min(len(breps_val), len(panel_ids_val))
        if len(breps_val) != len(panel_ids_val):
            log_warning(
                "Mismatched lengths: breps=%d, panel_ids=%d. "
                "Processing %d items."
                % (len(breps_val), len(panel_ids_val), min_count)
            )
            info_lines.append(
                "  WARNING: Mismatched lengths, processing %d items" % min_count
            )

        # Pad panel_functions if shorter
        while len(panel_functions_val) < min_count:
            panel_functions_val.append("unknown")

        # -----------------------------------------------------------------
        # Build metadata lookup
        # -----------------------------------------------------------------
        log_info("Building panel metadata lookup...")
        lookup = _build_panel_metadata_lookup(sheathing_json_val)
        info_lines.append("  Metadata lookup entries: %d" % len(lookup))

        # Debug: log first lookup entry to diagnose panel_id mapping
        if lookup:
            first_key = next(iter(lookup))
            first_meta = lookup[first_key]
            info_lines.append("  Sample lookup key: %s" % first_key)
            info_lines.append("  Sample meta keys: %s" % list(first_meta.keys()))
            info_lines.append("  Sample panel_id value: %s" % repr(first_meta.get("panel_id")))

        # Check how many input panel_ids match the lookup
        matched = sum(1 for pid in panel_ids_val[:min_count] if str(pid) in lookup)
        info_lines.append("  Lookup matches: %d / %d" % (matched, min_count))

        # -----------------------------------------------------------------
        # Resolve category
        # -----------------------------------------------------------------
        doc = REVIT_DOC
        category_id, actual_category, bic = _resolve_category_id(doc, category_str)
        info_lines.append("  Resolved category: %s" % actual_category)

        # -----------------------------------------------------------------
        # Ensure shared parameters
        # -----------------------------------------------------------------
        log_info("Ensuring shared parameters...")
        try:
            _ensure_shared_parameters(doc, bic)
            info_lines.append("  Shared parameters: OK")
        except Exception as sp_err:
            log_warning("Failed to create shared parameters: %s" % str(sp_err))
            info_lines.append("  Shared parameters: FAILED - %s" % str(sp_err))
            # Continue without shared params -- Mark param still works

        # -----------------------------------------------------------------
        # Bake DirectShapes in single transaction
        # -----------------------------------------------------------------
        log_info("Baking %d sheathing panels..." % min_count)

        t = Transaction(doc, "TFG: Bake Sheathing Panels")
        t.Start()

        created_ids = []
        data_entries = []
        type_cache = {}
        failed_count = 0
        types_created = set()

        try:
            for i in range(min_count):
                brep = breps_val[i]
                panel_id_str = str(panel_ids_val[i])
                layer_function = panel_functions_val[i] if i < len(panel_functions_val) else "unknown"

                meta = lookup.get(panel_id_str, {})

                # Convert geometry
                geom_list = _convert_brep_to_revit(brep)
                if geom_list is None:
                    log_warning(
                        "Panel %s: geometry conversion failed, skipping"
                        % panel_id_str
                    )
                    failed_count += 1
                    continue

                # Get material/face for type name
                material_display = meta.get(
                    "material_display",
                    meta.get("material", "Unknown Material"),
                )
                face = meta.get("face", "unknown")

                # Get/create DirectShapeType
                ds_type = _get_or_create_ds_type(
                    doc, material_display, face, category_id, type_cache
                )
                types_created.add(_make_type_name(material_display, face))

                # Create DirectShape
                ds = DirectShape.CreateElement(doc, category_id)
                ds.SetTypeId(ds_type.Id)
                ds.SetShape(geom_list)

                # Set metadata parameters
                _set_panel_metadata(ds, panel_id_str, meta, layer_function, seq_index=i)

                created_ids.append(ds.Id)

                # Build data entry for assembly creator
                # panel_id here refers to the framing panel this sheathing belongs to.
                # Include u_start/u_end for spatial matching fallback when
                # panel_id is not available (multi-layer generator doesn't set it).
                data_entries.append({
                    "panel_id": meta.get("panel_id") or "",
                    "wall_id": meta.get("wall_id", ""),
                    "u_start": meta.get("u_start"),
                    "u_end": meta.get("u_end"),
                })

            t.Commit()
            log_info("Transaction committed: %d DirectShapes created" % len(created_ids))

        except Exception as tx_err:
            if t.HasStarted():
                t.RollBack()
            raise RuntimeError(
                "Transaction failed: %s" % str(tx_err)
            )

        # -----------------------------------------------------------------
        # Build outputs
        # -----------------------------------------------------------------

        # sheathing_ids: list of ElementIds
        sheathing_ids_out = created_ids

        # sheathing_data_json: matches _build_sheathing_panel_map() expected format
        sheathing_data = {"panels": data_entries}
        sheathing_data_json_out = json.dumps(sheathing_data)

        # Stats summary
        stats_lines = [
            "Baked: %d / %d panels" % (len(created_ids), min_count),
            "Failed: %d" % failed_count,
            "Types created: %d" % len(types_created),
        ]
        for tn in sorted(types_created):
            stats_lines.append("  - %s" % tn)
        stats_out = "\n".join(stats_lines)

        # Info
        info_lines.append("")
        info_lines.append("Baking Results:")
        info_lines.append("  Created: %d" % len(created_ids))
        info_lines.append("  Failed: %d" % failed_count)
        info_lines.append("  Types: %s" % sorted(types_created))
        info_lines.append("")

        for i, entry in enumerate(data_entries[:5]):
            info_lines.append(
                "  [%d] panel_id=%s, wall_id=%s, u=[%s, %s]"
                % (i, entry["panel_id"], entry["wall_id"],
                   entry.get("u_start", "?"), entry.get("u_end", "?"))
            )
        if len(data_entries) > 5:
            info_lines.append("  ... (%d more)" % (len(data_entries) - 5))

        # Summary GH message
        if failed_count == 0 and len(created_ids) > 0:
            log_message(
                "Baked %d sheathing panels successfully" % len(created_ids),
                "remark",
            )
        elif failed_count > 0 and len(created_ids) > 0:
            log_warning(
                "Partial: %d baked, %d failed"
                % (len(created_ids), failed_count)
            )
        elif len(created_ids) == 0:
            log_error("All %d panels failed to bake" % min_count)

        info_out = "\n".join(info_lines)
        return (sheathing_ids_out, sheathing_data_json_out, stats_out, info_out)

    except Exception as e:
        error_msg = "Unexpected error: %s" % str(e)
        log_error(error_msg)
        log_debug(traceback.format_exc())
        return ([], "", "", error_msg + "\n" + traceback.format_exc())


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    sheathing_ids, sheathing_data_json, stats, info = main()
    # Print info to console so it's always visible regardless of output binding
    if info:
        print(info)
