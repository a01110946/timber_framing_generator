# File: src/timber_framing_generator/sheathing/multi_layer_generator.py

"""Multi-layer panel generator for wall assemblies.

Generates panels for every panelizable layer in a wall assembly
(insulation, drywall, cladding, sheathing) by reusing the core
SheathingGenerator layout algorithm with per-layer placement rules.

Each layer is positioned at its correct W offset computed from the
assembly's layer stack (see sheathing_geometry.calculate_layer_w_offsets).

Usage:
    from src.timber_framing_generator.sheathing.multi_layer_generator import (
        generate_assembly_layers,
        LayerPanelResult,
    )

    result = generate_assembly_layers(wall_data)
    for layer_result in result["layer_results"]:
        print(f"{layer_result['layer_name']}: {len(layer_result['panels'])} panels")
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple

from .sheathing_generator import SheathingGenerator
from .sheathing_profiles import SHEATHING_MATERIALS


# Layer functions that produce panelizable output.
# "structure" and "membrane" are typically not panelized in the same way.
PANELIZABLE_FUNCTIONS = {"substrate", "finish", "thermal"}

# Map layer function+side to a default material name from SHEATHING_MATERIALS.
# Used when the layer dict doesn't specify a material.
DEFAULT_LAYER_MATERIALS: Dict[Tuple[str, str], str] = {
    ("substrate", "exterior"): "osb_7_16",
    ("finish", "interior"): "gypsum_1_2",
    ("finish", "exterior"): "fiber_cement_5_16",
    ("thermal", "exterior"): "rigid_foam_1",
}

# Default panel sizes per layer function.
DEFAULT_LAYER_PANEL_SIZES: Dict[str, str] = {
    "substrate": "4x8",
    "finish": "4x8",
    "thermal": "4x8",
}

# Common display-name aliases for assembly catalog materials.
# Maps lowercase display name -> SHEATHING_MATERIALS key.
# Covers names used in config/assembly.py and typical Revit CompoundStructure names.
MATERIAL_ALIASES: Dict[str, str] = {
    "lap siding": "lp_smartside_7_16",
    "osb 7/16": "osb_7_16",
    "osb 1/2": "osb_1_2",
    "osb": "osb_7_16",
    "fiber cement siding": "fiber_cement_5_16",
    "fiber cement": "fiber_cement_5_16",
    '1/2" gypsum board': "gypsum_1_2",
    "1/2 gypsum board": "gypsum_1_2",
    '5/8" gypsum board': "gypsum_5_8",
    "5/8 gypsum board": "gypsum_5_8",
    "gypsum board": "gypsum_1_2",
    "gypsum": "gypsum_1_2",
    "drywall": "gypsum_1_2",
    "plywood": "structural_plywood_7_16",
    "rigid foam": "rigid_foam_1",
    "mineral wool": "mineral_wool_ci_1_5",
    "house wrap": "housewrap",
    "tyvek": "housewrap",
    "densglass": "densglass_1_2",
    "smartside": "lp_smartside_7_16",
}


def _build_display_name_map() -> Dict[str, str]:
    """Build reverse lookup: lowercase display_name -> SHEATHING_MATERIALS key."""
    result: Dict[str, str] = {}
    for key, mat in SHEATHING_MATERIALS.items():
        normalized = mat.display_name.lower().strip().rstrip('"').strip()
        result[normalized] = key
    return result


# Built once at import time.
_DISPLAY_NAME_MAP: Dict[str, str] = _build_display_name_map()


def _resolve_material_key(material_name: str) -> Optional[str]:
    """Resolve a material display name or alias to a SHEATHING_MATERIALS key.

    Lookup order:
    1. Exact match against SHEATHING_MATERIALS keys (already a valid key).
    2. Case-insensitive match against SHEATHING_MATERIALS display_name values.
    3. Case-insensitive match against MATERIAL_ALIASES.
    4. Returns None if no match found.

    Args:
        material_name: Material name from layer dict (may be a display name,
            alias, or valid SHEATHING_MATERIALS key).

    Returns:
        Valid SHEATHING_MATERIALS key, or None if unresolvable.
    """
    if not material_name:
        return None

    # 1. Already a valid key
    if material_name in SHEATHING_MATERIALS:
        return material_name

    # Normalize for case-insensitive lookups
    normalized = material_name.lower().strip().rstrip('"').strip()

    # 2. Match against display names
    if normalized in _DISPLAY_NAME_MAP:
        return _DISPLAY_NAME_MAP[normalized]

    # 3. Match against manual aliases
    if normalized in MATERIAL_ALIASES:
        return MATERIAL_ALIASES[normalized]

    return None


@dataclass
class LayerPanelResult:
    """Result for a single layer's panel generation.

    Attributes:
        layer_name: Name of the assembly layer.
        layer_function: Layer function (substrate, finish, thermal).
        layer_side: Layer side (exterior, core, interior).
        w_offset: W position of the layer's core-facing surface (feet).
        panels: List of panel dicts (serialized SheathingPanel).
        summary: Material summary for this layer.
        rules_applied: Placement rules that were used (serialized).
    """
    layer_name: str
    layer_function: str
    layer_side: str
    w_offset: Optional[float]
    panels: List[Dict[str, Any]]
    summary: Dict[str, Any]
    rules_applied: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "layer_name": self.layer_name,
            "layer_function": self.layer_function,
            "layer_side": self.layer_side,
            "w_offset": self.w_offset,
            "panel_count": len(self.panels),
            "panels": self.panels,
            "summary": self.summary,
            "rules_applied": self.rules_applied,
        }


def _get_layer_config(
    layer: Dict[str, Any],
    rules_config: Dict[str, Any],
    base_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build SheathingGenerator config for a single layer.

    Merges base_config (user overrides) with rules-derived config and
    layer-specific material/panel_size defaults.

    Args:
        layer: Layer dict from assembly with name, function, side, material.
        rules_config: Config from LayerPlacementRules.to_sheathing_config().
        base_config: Optional user-provided overrides.

    Returns:
        Config dict for SheathingGenerator.
    """
    config: Dict[str, Any] = {}

    # Start with rules-derived values
    config.update(rules_config)

    # Apply default material for this layer type
    func = layer.get("function", "substrate")
    side = layer.get("side", "exterior")
    material_key = (func, side)
    if material_key in DEFAULT_LAYER_MATERIALS:
        config.setdefault("material", DEFAULT_LAYER_MATERIALS[material_key])

    # Apply default panel size
    if func in DEFAULT_LAYER_PANEL_SIZES:
        config.setdefault("panel_size", DEFAULT_LAYER_PANEL_SIZES[func])

    # Layer may specify its own material (resolve display names to valid keys)
    layer_material = layer.get("material")
    if layer_material:
        resolved = _resolve_material_key(layer_material)
        if resolved:
            config["material"] = resolved

    # User overrides take highest priority
    if base_config:
        for key, value in base_config.items():
            config[key] = value

    return config


def _determine_face(side: str) -> str:
    """Map layer side to sheathing face.

    Args:
        side: Layer side ("exterior", "core", "interior").

    Returns:
        Face string for SheathingGenerator ("exterior" or "interior").
    """
    if side == "interior":
        return "interior"
    return "exterior"


def generate_assembly_layers(
    wall_data: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    layer_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    u_start_bound: Optional[float] = None,
    u_end_bound: Optional[float] = None,
    include_functions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate panels for all panelizable layers in a wall assembly.

    Iterates the layers in wall_data["wall_assembly"], applies
    LayerPlacementRules for each, and runs SheathingGenerator to
    produce panels positioned at the correct W offset.

    Args:
        wall_data: Wall data with "wall_assembly" containing "layers" list.
        config: Optional base config applied to all layers. Individual
            layer_configs take precedence.
        layer_configs: Optional per-layer config overrides keyed by layer
            name (e.g., {"OSB": {"panel_size": "4x10"}}).
        u_start_bound: Minimum U position for panels (feet).
        u_end_bound: Maximum U position for panels (feet).
        include_functions: If provided, only generate panels for layers
            whose function is in this list. Default: all panelizable
            functions (substrate, finish, thermal).

    Returns:
        Dict with:
            - wall_id: Wall identifier.
            - layer_results: List of LayerPanelResult dicts.
            - total_panel_count: Sum of panels across all layers.
            - layers_processed: Number of layers that produced panels.
    """
    wall_assembly = wall_data.get("wall_assembly")
    if not wall_assembly:
        return {
            "wall_id": wall_data.get("wall_id", "unknown"),
            "layer_results": [],
            "total_panel_count": 0,
            "layers_processed": 0,
        }

    layers = wall_assembly.get("layers", [])
    allowed_funcs = set(include_functions) if include_functions else PANELIZABLE_FUNCTIONS

    # Compute per-layer W offsets
    w_offsets = _safe_calculate_w_offsets(wall_assembly)

    # Get rules for all layers
    rules_by_name = _safe_get_rules(wall_assembly)

    layer_results: List[Dict[str, Any]] = []
    total_panels = 0

    for layer in layers:
        func = layer.get("function", "structure")
        if func not in allowed_funcs:
            continue

        name = layer.get("name", "unknown")
        side = layer.get("side", "exterior")
        face = _determine_face(side)

        # Get placement rules for this layer
        rules = rules_by_name.get(name)
        rules_config = rules.to_sheathing_config() if rules else {}
        rules_dict = rules.to_dict() if rules else {}

        # Build per-layer config
        layer_override = (layer_configs or {}).get(name)
        layer_config = _get_layer_config(layer, rules_config, layer_override or config)

        # Generate panels using SheathingGenerator
        try:
            generator = SheathingGenerator(
                wall_data, layer_config,
                u_start_bound=u_start_bound,
                u_end_bound=u_end_bound,
            )
            panels = generator.generate_sheathing(face=face)
            summary = generator.get_material_summary(panels)
        except Exception:
            panels = []
            summary = {}

        result = LayerPanelResult(
            layer_name=name,
            layer_function=func,
            layer_side=side,
            w_offset=w_offsets.get(name),
            panels=[p.to_dict() for p in panels],
            summary=summary,
            rules_applied=rules_dict,
        )
        layer_results.append(result.to_dict())
        total_panels += len(panels)

    return {
        "wall_id": wall_data.get("wall_id", "unknown"),
        "layer_results": layer_results,
        "total_panel_count": total_panels,
        "layers_processed": len(layer_results),
    }


def _safe_calculate_w_offsets(
    wall_assembly: Dict[str, Any],
) -> Dict[str, float]:
    """Calculate W offsets, returning empty dict on failure."""
    try:
        from .sheathing_geometry import calculate_layer_w_offsets
        return calculate_layer_w_offsets(wall_assembly)
    except Exception:
        return {}


def _safe_get_rules(
    wall_assembly: Dict[str, Any],
) -> Dict[str, Any]:
    """Get placement rules, returning empty dict on failure.

    Uses importlib.util to load layer_rules directly from its file path,
    avoiding the materials/__init__.py which triggers Rhino-dependent imports
    from the timber/cfs strategy modules.
    """
    try:
        import importlib.util
        import os

        module_name = "src.timber_framing_generator.materials.layer_rules"
        # Check if already loaded (e.g., in Grasshopper where Rhino IS available)
        import sys
        if module_name in sys.modules:
            mod = sys.modules[module_name]
            return mod.get_rules_for_assembly(wall_assembly)

        # Load directly from file to avoid package __init__.py
        this_dir = os.path.dirname(os.path.abspath(__file__))
        layer_rules_path = os.path.normpath(
            os.path.join(this_dir, "..", "materials", "layer_rules.py")
        )
        spec = importlib.util.spec_from_file_location(module_name, layer_rules_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod.get_rules_for_assembly(wall_assembly)
    except Exception:
        return {}
