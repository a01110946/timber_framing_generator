# File: scripts/gh_penetration_generator.py
"""
GHPython Component: Penetration Generator

Generates penetration specifications for pipes passing through framing.
This is the third step in the MEP integration pipeline.

Inputs:
    routes_json (str): JSON from Pipe Router
    framing_json (str): JSON with framing elements (from Framing Generator)
    run (bool): Execute toggle

Outputs:
    penetrations_json (str): JSON with penetration specifications
    penetration_points (list): Point3d at each penetration center
    penetration_circles (list): Circle curves representing holes
    warnings (list): List of warning messages for problematic penetrations
    debug_info (str): Processing summary and diagnostics

Usage:
    1. Connect routes_json from Pipe Router
    2. Connect framing_json from Framing Generator
    3. Toggle 'run' to True
    4. Review penetrations_json for hole specifications
    5. Check warnings for code compliance issues
    6. Visualize penetration_circles in Rhino

Author: Claude AI Assistant
Version: 1.0.0
"""

# =============================================================================
# IMPORTS
# =============================================================================

import sys
import json
import math

# Force reload of project modules for development
for mod_name in list(sys.modules.keys()):
    if 'timber_framing_generator' in mod_name:
        del sys.modules[mod_name]

# Rhino/Grasshopper imports
try:
    import Rhino.Geometry as rg
    RHINO_AVAILABLE = True
except ImportError:
    RHINO_AVAILABLE = False

# Project imports
try:
    from src.timber_framing_generator.mep.plumbing import (
        PlumbingSystem,
        generate_plumbing_penetrations,
    )
    from src.timber_framing_generator.core import MEPRoute
    PROJECT_AVAILABLE = True
except ImportError as e:
    PROJECT_AVAILABLE = False
    PROJECT_ERROR = str(e)


# =============================================================================
# MAIN COMPONENT LOGIC
# =============================================================================

def main():
    """
    Main component execution.

    Generates penetration specifications from routes and framing
    and outputs JSON data plus visualization geometry.
    """
    # Initialize outputs
    penetrations_json = "{}"
    penetration_points = []
    penetration_circles = []
    warnings = []
    debug_lines = []

    # Header
    debug_lines.append("=" * 50)
    debug_lines.append("PENETRATION GENERATOR")
    debug_lines.append("=" * 50)

    # Check environment
    debug_lines.append(f"Rhino available: {RHINO_AVAILABLE}")
    debug_lines.append(f"Project modules available: {PROJECT_AVAILABLE}")

    if not PROJECT_AVAILABLE:
        debug_lines.append(f"Project import error: {PROJECT_ERROR}")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    # Check run toggle
    if not run:
        debug_lines.append("")
        debug_lines.append("Toggle 'run' to True to execute")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    # Parse routes JSON
    if not routes_json:
        debug_lines.append("")
        debug_lines.append("No routes_json provided")
        debug_lines.append("Connect output from Pipe Router")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    try:
        routes_data = json.loads(routes_json)
        route_list = routes_data.get("routes", [])
        debug_lines.append(f"Input routes: {len(route_list)}")
    except json.JSONDecodeError as e:
        debug_lines.append(f"ERROR parsing routes_json: {e}")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    if not route_list:
        debug_lines.append("No routes in JSON data")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    # Parse framing JSON
    if not framing_json:
        debug_lines.append("")
        debug_lines.append("No framing_json provided")
        debug_lines.append("Connect output from Framing Generator")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    try:
        framing_data = json.loads(framing_json)
        debug_lines.append("Framing data loaded")
    except json.JSONDecodeError as e:
        debug_lines.append(f"ERROR parsing framing_json: {e}")
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    # Extract framing elements
    framing_elements = _extract_framing_elements(framing_data)
    debug_lines.append(f"Framing elements: {len(framing_elements)}")

    # Convert route dicts to MEPRoute objects
    routes = []
    for route_dict in route_list:
        try:
            route = MEPRoute.from_dict(route_dict)
            routes.append(route)
        except Exception as e:
            debug_lines.append(f"Warning: Failed to parse route: {e}")

    debug_lines.append(f"Parsed {len(routes)} routes")

    # Generate penetrations
    debug_lines.append("")
    debug_lines.append("Generating penetrations...")

    try:
        penetrations = generate_plumbing_penetrations(routes, framing_elements)
        debug_lines.append(f"Generated {len(penetrations)} penetrations")
    except Exception as e:
        debug_lines.append(f"ERROR generating penetrations: {e}")
        import traceback
        debug_lines.append(traceback.format_exc())
        return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))

    if not penetrations:
        debug_lines.append("No penetrations generated")
        debug_lines.append("Routes may not cross any framing members")

    # Analyze penetrations
    allowed_count = sum(1 for p in penetrations if p.get("is_allowed", True))
    disallowed_count = len(penetrations) - allowed_count
    reinforcement_count = sum(1 for p in penetrations if p.get("reinforcement_required", False))

    debug_lines.append("")
    debug_lines.append("Penetration summary:")
    debug_lines.append(f"  Total penetrations: {len(penetrations)}")
    debug_lines.append(f"  Code-compliant: {allowed_count}")
    debug_lines.append(f"  Requires review: {disallowed_count}")
    debug_lines.append(f"  Reinforcement needed: {reinforcement_count}")

    # Collect warnings
    for pen in penetrations:
        if not pen.get("is_allowed", True):
            warning_msg = pen.get("warning", "Penetration exceeds code limits")
            element_id = pen.get("element_id", "unknown")
            warnings.append(f"{element_id}: {warning_msg}")

        if pen.get("reinforcement_required", False) and pen.get("is_allowed", True):
            element_id = pen.get("element_id", "unknown")
            ratio = pen.get("penetration_ratio", 0) * 100
            warnings.append(f"{element_id}: Reinforcement recommended ({ratio:.1f}% of depth)")

    if warnings:
        debug_lines.append("")
        debug_lines.append(f"Warnings ({len(warnings)}):")
        for w in warnings[:5]:  # Show first 5
            debug_lines.append(f"  - {w}")
        if len(warnings) > 5:
            debug_lines.append(f"  ... and {len(warnings) - 5} more")

    # Build JSON output
    output_data = {
        "penetrations": penetrations,
        "count": len(penetrations),
        "allowed_count": allowed_count,
        "disallowed_count": disallowed_count,
        "reinforcement_count": reinforcement_count,
        "source": "gh_penetration_generator",
    }
    penetrations_json = json.dumps(output_data, indent=2)

    debug_lines.append("")
    debug_lines.append(f"JSON output size: {len(penetrations_json)} chars")

    # Build geometry outputs for visualization
    if RHINO_AVAILABLE:
        for pen in penetrations:
            loc = pen.get("location", {})
            diameter = pen.get("diameter", 0.0833)

            # Create point at penetration center
            pt = rg.Point3d(
                loc.get("x", 0),
                loc.get("y", 0),
                loc.get("z", 0)
            )
            penetration_points.append(pt)

            # Create circle representing hole
            # Circle in XZ plane (vertical, facing along Y)
            plane = rg.Plane(pt, rg.Vector3d.YAxis)
            radius = diameter / 2
            circle = rg.Circle(plane, radius)
            penetration_circles.append(circle.ToNurbsCurve())

        debug_lines.append(f"Created {len(penetration_points)} visualization points")
        debug_lines.append(f"Created {len(penetration_circles)} hole circles")
    else:
        debug_lines.append("Rhino not available - skipping visualization geometry")

    # Summary
    debug_lines.append("")
    debug_lines.append("=" * 50)
    debug_lines.append("PENETRATION GENERATION COMPLETE")
    debug_lines.append(f"Total penetrations: {len(penetrations)}")
    debug_lines.append(f"Code-compliant: {allowed_count}")
    debug_lines.append(f"Warnings: {len(warnings)}")
    debug_lines.append("=" * 50)

    return (penetrations_json, penetration_points, penetration_circles, warnings, "\n".join(debug_lines))


def _extract_framing_elements(framing_data):
    """
    Extract framing elements from various JSON structures.

    Args:
        framing_data: Parsed JSON data from Framing Generator

    Returns:
        List of framing element dictionaries
    """
    # Direct elements list
    if isinstance(framing_data, list):
        return framing_data

    if isinstance(framing_data, dict):
        # Elements key
        if "elements" in framing_data:
            return framing_data["elements"]

        # Nested in results
        if "results" in framing_data:
            results = framing_data["results"]
            if isinstance(results, dict) and "elements" in results:
                return results["elements"]

        # Framing_elements key
        if "framing_elements" in framing_data:
            return framing_data["framing_elements"]

    return []


# =============================================================================
# EXECUTE
# =============================================================================

# Define default input values if not provided by Grasshopper
if 'run' not in dir():
    run = False

if 'routes_json' not in dir():
    routes_json = ""

if 'framing_json' not in dir():
    framing_json = ""

# Execute main function
penetrations_json, penetration_points, penetration_circles, warnings, debug_info = main()
