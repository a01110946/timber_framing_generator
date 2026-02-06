# File: src/timber_framing_generator/wall_data/assembly_extractor.py

"""Extract wall assembly (CompoundStructure) data from Revit wall types.

Provides functions to convert Revit's CompoundStructure into our
WallAssemblyDef format. The extraction function requires Revit API;
the mapping/conversion helpers are pure Python and fully testable.

Usage (inside Rhino/Revit environment):
    from src.timber_framing_generator.wall_data.assembly_extractor import (
        extract_compound_structure,
    )

    assembly_dict = extract_compound_structure(wall_type, doc)
    # Returns dict ready for JSON serialization, or None on failure.

Usage (pure Python, for testing):
    from src.timber_framing_generator.wall_data.assembly_extractor import (
        map_revit_layer_function,
        determine_layer_side,
        assembly_dict_to_def,
    )
"""

import logging
from typing import Dict, List, Optional, Any

from src.timber_framing_generator.wall_junctions.junction_types import (
    WallLayer,
    WallAssemblyDef,
    LayerFunction,
    LayerSide,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Revit MaterialFunctionAssignment -> LayerFunction mapping
# =============================================================================

# Revit's MaterialFunctionAssignment enum integer values.
# Source: Autodesk.Revit.DB.MaterialFunctionAssignment
_REVIT_FUNCTION_MAP: Dict[int, str] = {
    0: "structure",       # Structure
    1: "substrate",       # Substrate
    2: "thermal",         # Thermal/Air
    3: "membrane",        # Membrane Layer
    4: "finish",          # Finish 1 (typically exterior)
    5: "finish",          # Finish 2 (typically interior)
}

# String-based fallback mapping (for when enum .ToString() is used)
_REVIT_FUNCTION_NAME_MAP: Dict[str, str] = {
    "structure": "structure",
    "substrate": "substrate",
    "thermal": "thermal",
    "thermalair": "thermal",
    "membrane": "membrane",
    "finish1": "finish",
    "finish2": "finish",
    "structuraldeck": "structure",
}


def map_revit_layer_function(revit_function: Any) -> str:
    """Map a Revit MaterialFunctionAssignment to our LayerFunction string.

    Accepts integer enum values, string names, or enum objects with
    .value/.ToString() methods.

    Args:
        revit_function: Revit layer function (int, str, or enum).

    Returns:
        LayerFunction value string ("structure", "substrate", etc.).
    """
    # Integer value
    if isinstance(revit_function, int):
        return _REVIT_FUNCTION_MAP.get(revit_function, "structure")

    # String name
    if isinstance(revit_function, str):
        normalized = revit_function.lower().replace(" ", "").replace("/", "")
        return _REVIT_FUNCTION_NAME_MAP.get(normalized, "structure")

    # Enum object — try int conversion first, then string
    try:
        int_val = int(revit_function)
        return _REVIT_FUNCTION_MAP.get(int_val, "structure")
    except (TypeError, ValueError):
        pass

    try:
        name = str(revit_function).lower().replace(" ", "").replace("/", "")
        return _REVIT_FUNCTION_NAME_MAP.get(name, "structure")
    except Exception:
        return "structure"


def determine_layer_side(
    layer_index: int,
    first_core_index: int,
    last_core_index: int,
) -> str:
    """Determine which side of the core boundary a layer is on.

    Revit layers are ordered from exterior (index 0) to interior (last).
    Layers before the first core are exterior; layers after the last core
    are interior; layers between (inclusive) are core.

    Args:
        layer_index: Index of the layer in the CompoundStructure.
        first_core_index: Index of the first core layer.
        last_core_index: Index of the last core layer.

    Returns:
        LayerSide value string ("exterior", "core", or "interior").
    """
    if first_core_index < 0 or last_core_index < 0:
        # No core boundary defined — treat all as core
        return "core"
    if layer_index < first_core_index:
        return "exterior"
    elif layer_index > last_core_index:
        return "interior"
    else:
        return "core"


def assembly_dict_to_def(assembly_dict: Dict[str, Any]) -> WallAssemblyDef:
    """Convert a serialized assembly dictionary to a WallAssemblyDef.

    This is the inverse of WallAssemblyDef.to_dict(). Used when
    deserializing wall_assembly from JSON.

    Args:
        assembly_dict: Dictionary with "name", "layers", "source" keys.

    Returns:
        WallAssemblyDef instance.
    """
    layers = []
    for layer_data in assembly_dict.get("layers", []):
        layer = WallLayer(
            name=layer_data.get("name", "unknown"),
            function=LayerFunction(layer_data.get("function", "structure")),
            side=LayerSide(layer_data.get("side", "core")),
            thickness=float(layer_data.get("thickness", 0.0)),
            material=layer_data.get("material", ""),
            priority=int(layer_data.get("priority", 50)),
            wraps_at_ends=bool(layer_data.get("wraps_at_ends", False)),
            wraps_at_inserts=bool(layer_data.get("wraps_at_inserts", False)),
        )
        layers.append(layer)

    return WallAssemblyDef(
        name=assembly_dict.get("name", "unknown"),
        layers=layers,
        source=assembly_dict.get("source", "revit"),
    )


# =============================================================================
# Revit-dependent extraction (requires Autodesk.Revit.DB)
# =============================================================================


def extract_compound_structure(wall_type, doc) -> Optional[Dict[str, Any]]:
    """Extract CompoundStructure data from a Revit WallType.

    Reads each layer's width, function, material name, and position
    relative to the core boundary. Returns a plain dict suitable for
    JSON serialization and later conversion to WallAssemblyDef.

    Args:
        wall_type: Autodesk.Revit.DB.WallType instance.
        doc: Autodesk.Revit.DB.Document (needed for material lookup).

    Returns:
        Dict with "name", "layers", "source" keys, or None on failure.
        Each layer dict has: name, thickness, function, side, material, priority.
    """
    try:
        compound_structure = wall_type.GetCompoundStructure()
        if compound_structure is None:
            logger.debug(
                "No CompoundStructure on wall type %s", wall_type.Name
            )
            return None

        # Get core boundary indices for side determination
        first_core = compound_structure.GetFirstCoreLayerIndex()
        last_core = compound_structure.GetLastCoreLayerIndex()

        layers_data: List[Dict[str, Any]] = []
        layer_list = compound_structure.GetLayers()

        for i, cs_layer in enumerate(layer_list):
            # Thickness in feet (Revit internal units)
            thickness = float(cs_layer.Width)

            # Map Revit function enum to our function string
            function_str = map_revit_layer_function(cs_layer.Function)

            # Determine side relative to core boundary
            side_str = determine_layer_side(i, first_core, last_core)

            # Get material name
            material_name = _get_material_name(doc, cs_layer.MaterialId)

            # Assign priority based on function
            priority = _function_to_priority(function_str)

            layer_dict: Dict[str, Any] = {
                "name": _make_layer_name(function_str, side_str, i),
                "thickness": thickness,
                "function": function_str,
                "side": side_str,
                "material": material_name,
                "priority": priority,
            }

            # Check wrapping flags if available
            try:
                layer_dict["wraps_at_ends"] = bool(
                    compound_structure.IsEndCapped()
                )
                layer_dict["wraps_at_inserts"] = bool(
                    compound_structure.OpeningWrapping != 0
                )
            except (AttributeError, Exception):
                layer_dict["wraps_at_ends"] = False
                layer_dict["wraps_at_inserts"] = False

            layers_data.append(layer_dict)

        return {
            "name": wall_type.Name,
            "layers": layers_data,
            "source": "revit",
        }

    except Exception as e:
        logger.warning(
            "Failed to extract CompoundStructure from %s: %s",
            getattr(wall_type, "Name", "unknown"),
            e,
        )
        return None


def _get_material_name(doc, material_id) -> str:
    """Get material name from a Revit ElementId.

    Args:
        doc: Revit Document.
        material_id: ElementId of the material.

    Returns:
        Material name string, or "Unknown" if lookup fails.
    """
    try:
        from Autodesk.Revit import DB as RevitDB

        if material_id == RevitDB.ElementId.InvalidElementId:
            return "Unknown"
        material = doc.GetElement(material_id)
        if material is not None:
            return str(material.Name)
    except Exception:
        pass
    return "Unknown"


def _function_to_priority(function_str: str) -> int:
    """Map layer function to junction priority.

    Higher priority = extends through lower priority at junctions.
    """
    priorities = {
        "structure": 100,
        "substrate": 80,
        "thermal": 40,
        "membrane": 30,
        "finish": 10,
    }
    return priorities.get(function_str, 50)


def _make_layer_name(function_str: str, side_str: str, index: int) -> str:
    """Generate a descriptive layer name from function and side.

    Args:
        function_str: Layer function string.
        side_str: Layer side string.
        index: Layer index in the compound structure.

    Returns:
        Name like "exterior_finish", "framing_core", "interior_substrate".
    """
    if side_str == "core":
        return f"framing_{function_str}"
    return f"{side_str}_{function_str}"
