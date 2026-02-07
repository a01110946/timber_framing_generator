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

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple

from .sheathing_generator import SheathingGenerator
from .sheathing_profiles import SHEATHING_MATERIALS

logger = logging.getLogger(__name__)


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


# Standard nominal-to-actual lumber depths (inches).
# Used to infer the framing profile depth from the core material name
# (e.g., "2x4 SPF @ 16\" OC" -> 3.5 inches -> 3.5/12 feet).
_LUMBER_ACTUAL_DEPTHS: Dict[str, float] = {
    "4": 3.5,
    "6": 5.5,
    "8": 7.25,
    "10": 9.25,
    "12": 11.25,
}


def extract_max_framing_depth(
    framing_data: Any,
    wall_id: Optional[str] = None,
) -> Optional[float]:
    """Extract the maximum profile depth from framing generator output.

    Parses the framing_json structure (a FramingResults dict or list of
    them) and returns the largest ``profile.depth`` across all elements.
    This gives the actual framing depth regardless of what the assembly
    catalog says — essential when CFS profiles are used on a wall whose
    Revit type is a timber "2x4".

    Args:
        framing_data: Parsed framing_json — either a single
            FramingResults dict with an ``elements`` list, or a list of
            such dicts.
        wall_id: Optional wall ID to filter elements. When provided,
            only elements whose ``metadata.wall_id`` matches are
            considered. When None, all elements are used.

    Returns:
        Maximum profile depth in feet, or None if no elements found.
    """
    if framing_data is None:
        return None

    # Normalise to a list of FramingResults dicts
    if isinstance(framing_data, dict):
        results_list = [framing_data]
    elif isinstance(framing_data, list):
        results_list = framing_data
    else:
        return None

    max_depth: Optional[float] = None

    for result in results_list:
        if not isinstance(result, dict):
            continue
        elements = result.get("elements", [])
        for elem in elements:
            if not isinstance(elem, dict):
                continue

            # Optional wall_id filter
            if wall_id is not None:
                elem_wall_id = (elem.get("metadata") or {}).get("wall_id")
                if elem_wall_id is not None and str(elem_wall_id) != str(wall_id):
                    continue

            profile = elem.get("profile")
            if not isinstance(profile, dict):
                continue
            depth = profile.get("depth")
            if depth is not None:
                depth = float(depth)
                if max_depth is None or depth > max_depth:
                    max_depth = depth

    return max_depth


def _infer_framing_depth(wall_assembly: Dict[str, Any]) -> Optional[float]:
    """Infer framing profile depth from core material name.

    Parses "2xN" from material names like '2x4 SPF @ 16" OC' in the
    assembly's core layer(s). Returns the actual lumber depth in feet,
    or None if not determinable.

    Args:
        wall_assembly: Assembly dictionary with "layers" list.

    Returns:
        Framing depth in feet, or None if no standard lumber size found.
    """
    for layer in wall_assembly.get("layers", []):
        if layer.get("side") != "core":
            continue
        material = layer.get("material", "")
        match = re.search(r"2x(\d+)", str(material), re.IGNORECASE)
        if match:
            nominal = match.group(1)
            actual_inches = _LUMBER_ACTUAL_DEPTHS.get(nominal)
            if actual_inches is not None:
                return actual_inches / 12.0
    return None


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

    The face is used as a key into ``face_bounds`` to look up junction
    adjustments and as the ``face`` tag on generated panels.  Returning
    the side unchanged ensures that each layer (exterior / core /
    interior) receives its own junction adjustments rather than core
    layers silently inheriting exterior bounds.

    Args:
        side: Layer side ("exterior", "core", "interior").

    Returns:
        The side string unchanged.
    """
    return side


def generate_assembly_layers(
    wall_data: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    layer_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    u_start_bound: Optional[float] = None,
    u_end_bound: Optional[float] = None,
    include_functions: Optional[List[str]] = None,
    face_bounds: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None,
    framing_depth: Optional[float] = None,
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
        u_start_bound: Minimum U position for panels (feet). Used as
            fallback when face_bounds is not provided.
        u_end_bound: Maximum U position for panels (feet). Used as
            fallback when face_bounds is not provided.
        include_functions: If provided, only generate panels for layers
            whose function is in this list. Default: all panelizable
            functions (substrate, finish, thermal).
        face_bounds: Optional per-face junction bounds. Maps face name
            ("exterior"/"interior") to (u_start, u_end) tuple. When
            provided, each layer uses the bounds matching its face.
            Falls back to u_start_bound/u_end_bound if face not found.
        framing_depth: Optional actual framing profile depth in feet
            (e.g., 3.5/12 for a 2x4 stud). When provided, layer W
            offsets use ``max(core_half, framing_depth / 2)`` so
            sheathing never starts inside the framing zone. When None,
            the depth is auto-inferred from the assembly core material
            name (e.g., "2x4 SPF" -> 3.5/12). If inference fails, the
            assembly core thickness is used as-is.

    Returns:
        Dict with:
            - wall_id: Wall identifier.
            - layer_results: List of LayerPanelResult dicts.
            - total_panel_count: Sum of panels across all layers.
            - layers_processed: Number of layers that produced panels.
    """
    wall_assembly = wall_data.get("wall_assembly")
    if not wall_assembly:
        result: Dict[str, Any] = {
            "wall_id": wall_data.get("wall_id", "unknown"),
            "layer_results": [],
            "total_panel_count": 0,
            "layers_processed": 0,
        }
        _add_assembly_metadata(result, wall_data)
        return result

    layers = wall_assembly.get("layers", [])
    allowed_funcs = set(include_functions) if include_functions else PANELIZABLE_FUNCTIONS

    # Resolve framing depth: explicit > wall_thickness > auto-inferred > None
    effective_framing_depth = framing_depth
    if effective_framing_depth is None:
        effective_framing_depth = _infer_framing_depth(wall_assembly)

    # Also consider wall_thickness from Revit as a conservative bound.
    # When the actual framing material (e.g., CFS 550S = 5.5") exceeds
    # the assembly catalog's core_thickness (e.g., "2x4" = 3.5"),
    # wall_thickness from Revit is often the most reliable indicator
    # of the true framing depth.  Using it prevents sheathing from
    # starting inside the framing zone.
    wall_thickness = wall_data.get("wall_thickness", wall_data.get("thickness"))
    if wall_thickness is not None:
        if wall_thickness > 2.0:  # likely in inches
            wall_thickness = wall_thickness / 12.0
        if effective_framing_depth is None or wall_thickness > effective_framing_depth:
            effective_framing_depth = wall_thickness

    # Compute per-layer W offsets
    w_offsets = _safe_calculate_w_offsets(wall_assembly, effective_framing_depth)

    # Diagnostic: print W offset details (visible in GH component output)
    wall_id = wall_data.get("wall_id", "unknown")
    print(
        f"[W-DIAG] Wall {wall_id}: framing_depth={effective_framing_depth}, "
        f"wall_thickness={wall_data.get('wall_thickness', wall_data.get('thickness'))}, "
        f"w_offsets={w_offsets}"
    )

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

        # Resolve per-layer junction bounds.
        # Try individual layer name first (per-layer cumulative
        # adjustments), then fall back to aggregate face key.
        if face_bounds and name in face_bounds:
            layer_u_start, layer_u_end = face_bounds[name]
        elif face_bounds and face in face_bounds:
            layer_u_start, layer_u_end = face_bounds[face]
        else:
            layer_u_start = u_start_bound
            layer_u_end = u_end_bound

        # Generate panels using SheathingGenerator
        try:
            generator = SheathingGenerator(
                wall_data, layer_config,
                u_start_bound=layer_u_start,
                u_end_bound=layer_u_end,
                layer_name=name,
            )
            panels = generator.generate_sheathing(face=face)
            summary = generator.get_material_summary(panels)
        except Exception:
            panels = []
            summary = {}

        # Embed layer_w_offset directly in each panel dict so panels
        # are self-contained for geometry conversion. This prevents
        # issues where the geometry converter's flatten step doesn't
        # have access to the layer-level w_offset (e.g., when
        # _safe_calculate_w_offsets failed or JSON round-trip lost it).
        w_offset_value = w_offsets.get(name)
        panel_dicts: List[Dict[str, Any]] = []
        for p in panels:
            pd = p.to_dict()
            if w_offset_value is not None:
                pd["layer_w_offset"] = w_offset_value
            panel_dicts.append(pd)

        result = LayerPanelResult(
            layer_name=name,
            layer_function=func,
            layer_side=side,
            w_offset=w_offset_value,
            panels=panel_dicts,
            summary=summary,
            rules_applied=rules_dict,
        )
        layer_results.append(result.to_dict())
        total_panels += len(panels)

    result: Dict[str, Any] = {
        "wall_id": wall_data.get("wall_id", "unknown"),
        "layer_results": layer_results,
        "total_panel_count": total_panels,
        "layers_processed": len(layer_results),
    }
    _add_assembly_metadata(result, wall_data)
    return result


# Assembly metadata keys set by assembly_resolver.resolve_all_walls().
_ASSEMBLY_METADATA_KEYS = (
    "assembly_source",
    "assembly_confidence",
    "assembly_notes",
    "assembly_name",
    "wall_type",
)


def _add_assembly_metadata(
    result: Dict[str, Any],
    wall_data: Dict[str, Any],
) -> None:
    """Pass through assembly resolution metadata to output.

    When wall_data has been enriched by resolve_all_walls(), copy the
    assembly metadata fields into the result dict for downstream transparency.

    Args:
        result: Output dict being built by generate_assembly_layers().
        wall_data: Wall dict that may contain assembly metadata.
    """
    for key in _ASSEMBLY_METADATA_KEYS:
        if key in wall_data:
            result[key] = wall_data[key]


def _safe_calculate_w_offsets(
    wall_assembly: Dict[str, Any],
    framing_depth: Optional[float] = None,
) -> Dict[str, float]:
    """Calculate W offsets with fallback on failure.

    Tries the full assembly_extractor-based calculation first. If that
    fails (e.g., import chain issue in GH), falls back to a simple
    dict-based computation that avoids external imports.

    Args:
        wall_assembly: Assembly dictionary with "layers" list.
        framing_depth: Optional actual framing profile depth in feet.
            Passed through to the offset calculation so layers start
            at ``max(core_half, framing_depth / 2)``.

    Returns:
        Dict mapping layer name to W offset (feet from centerline).
        Falls back to simple stacking if full calculation fails.
    """
    try:
        from .sheathing_geometry import calculate_layer_w_offsets
        return calculate_layer_w_offsets(wall_assembly, framing_depth=framing_depth)
    except Exception as e:
        logger.warning(
            "Full W offset calculation failed: %s. "
            "Falling back to dict-based computation.", e
        )
        return _compute_fallback_w_offsets(wall_assembly, framing_depth=framing_depth)


def _compute_fallback_w_offsets(
    wall_assembly: Dict[str, Any],
    framing_depth: Optional[float] = None,
) -> Dict[str, float]:
    """Compute per-layer W offsets directly from assembly dict.

    Fallback when calculate_layer_w_offsets() fails (e.g., due to import
    chain issues in the GH environment). Works directly with the dict
    format from the assembly resolver, avoiding assembly_extractor and
    junction_types imports.

    Layers are stacked outward from the structural core center:
    - Exterior layers: +effective_half, then increasingly positive
    - Interior layers: -effective_half, then increasingly negative

    When ``framing_depth`` is provided, ``effective_half`` is
    ``max(core_half, framing_depth / 2)`` to prevent sheathing from
    starting inside the framing zone.

    Args:
        wall_assembly: Assembly dictionary with "layers" list.
            Each layer has name, function, side, thickness.
        framing_depth: Optional actual framing profile depth in feet.

    Returns:
        Dict mapping layer name to W offset (feet from centerline).
        Empty dict if no core layer found.
    """
    layers = wall_assembly.get("layers", [])

    # Find core thickness
    core_thickness = 0.0
    for layer in layers:
        if layer.get("side") == "core":
            core_thickness += layer.get("thickness", 0.0)

    if core_thickness == 0.0:
        logger.warning("No core layer found in assembly; cannot compute W offsets")
        return {}

    core_half = core_thickness / 2.0

    # Use actual framing depth when it exceeds assembly core
    effective_half = core_half
    if framing_depth is not None:
        effective_half = max(core_half, framing_depth / 2.0)

    # Tiny outward nudge (matches SHEATHING_GAP in sheathing_geometry)
    effective_half += 0.001

    offsets: Dict[str, float] = {}

    # Exterior layers: stack outward from effective half.
    # Assembly order is outside-to-inside, so reverse to get core-outward.
    ext_layers = [l for l in layers if l.get("side") == "exterior"]
    cumulative = effective_half
    for layer in reversed(ext_layers):
        offsets[layer.get("name", "unknown")] = cumulative
        cumulative += layer.get("thickness", 0.0)

    # Interior layers: stack inward from effective half.
    # Assembly order has interior layers after core (closest to core first).
    int_layers = [l for l in layers if l.get("side") == "interior"]
    cumulative = -effective_half
    for layer in int_layers:
        offsets[layer.get("name", "unknown")] = cumulative
        cumulative -= layer.get("thickness", 0.0)

    logger.info("Fallback W offsets computed: %s", offsets)
    return offsets


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
