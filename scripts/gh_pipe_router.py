# File: scripts/gh_pipe_router.py
"""
GHPython Component: Pipe Router

Calculates pipe routes from plumbing connectors to wall entry points.
This is the second step in the MEP integration pipeline.

Routing Strategy:
    1. From fixture connector, find nearest wall
    2. Calculate entry point on wall face
    3. Calculate first vertical connection inside wall

Inputs:
    connectors_json (str): JSON from MEP Connector Extractor
    walls_json (str): JSON with wall geometry data (from Wall Analyzer)
    max_search_distance (float): Maximum distance to search for walls (default: 10 ft)
    run (bool): Execute toggle

Outputs:
    routes_json (str): JSON with calculated routes for downstream components
    route_curves (list): Polyline curves showing pipe paths
    route_points (list): All route path points for visualization
    debug_info (str): Processing summary and diagnostics

Usage:
    1. Connect connectors_json from MEP Connector Extractor
    2. Connect walls_json from Wall Analyzer
    3. Toggle 'run' to True
    4. Use routes_json for penetration generation
    5. Visualize route_curves in Rhino

Author: Claude AI Assistant
Version: 1.0.0
"""

# =============================================================================
# IMPORTS
# =============================================================================

import sys
import json

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
        calculate_pipe_routes,
    )
    from src.timber_framing_generator.core import MEPConnector, MEPRoute
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

    Calculates pipe routes from connectors to wall entries
    and outputs JSON data plus visualization geometry.
    """
    # Initialize outputs
    routes_json = "{}"
    route_curves = []
    route_points = []
    debug_lines = []

    # Header
    debug_lines.append("=" * 50)
    debug_lines.append("PIPE ROUTER")
    debug_lines.append("=" * 50)

    # Check environment
    debug_lines.append(f"Rhino available: {RHINO_AVAILABLE}")
    debug_lines.append(f"Project modules available: {PROJECT_AVAILABLE}")

    if not PROJECT_AVAILABLE:
        debug_lines.append(f"Project import error: {PROJECT_ERROR}")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    # Check run toggle
    if not run:
        debug_lines.append("")
        debug_lines.append("Toggle 'run' to True to execute")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    # Parse connectors JSON
    if not connectors_json:
        debug_lines.append("")
        debug_lines.append("No connectors_json provided")
        debug_lines.append("Connect output from MEP Connector Extractor")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    try:
        connectors_data = json.loads(connectors_json)
        connector_list = connectors_data.get("connectors", [])
        debug_lines.append(f"Input connectors: {len(connector_list)}")
    except json.JSONDecodeError as e:
        debug_lines.append(f"ERROR parsing connectors_json: {e}")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    if not connector_list:
        debug_lines.append("No connectors in JSON data")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    # Parse walls JSON
    if not walls_json:
        debug_lines.append("")
        debug_lines.append("No walls_json provided")
        debug_lines.append("Connect output from Wall Analyzer")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    try:
        walls_data = json.loads(walls_json)
        debug_lines.append(f"Walls data loaded")
    except json.JSONDecodeError as e:
        debug_lines.append(f"ERROR parsing walls_json: {e}")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    # Convert connector dicts to MEPConnector objects
    connectors = []
    for conn_dict in connector_list:
        try:
            conn = MEPConnector.from_dict(conn_dict)
            connectors.append(conn)
        except Exception as e:
            debug_lines.append(f"Warning: Failed to parse connector: {e}")

    debug_lines.append(f"Parsed {len(connectors)} connectors")

    # Build routing config
    config = {
        "max_search_distance": max_search_distance if max_search_distance else 10.0,
        "wall_thickness": 0.333,  # Default 4" wall
    }

    debug_lines.append(f"Max search distance: {config['max_search_distance']} ft")

    # Calculate routes
    debug_lines.append("")
    debug_lines.append("Calculating routes...")

    try:
        # Build framing data structure expected by router
        framing_data = {"walls": _extract_walls_list(walls_data)}
        routes = calculate_pipe_routes(connectors, framing_data, [], config)
        debug_lines.append(f"Calculated {len(routes)} routes")
    except Exception as e:
        debug_lines.append(f"ERROR calculating routes: {e}")
        import traceback
        debug_lines.append(traceback.format_exc())
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    if not routes:
        debug_lines.append("No routes could be calculated")
        debug_lines.append("Check that fixtures are near walls")
        return (routes_json, route_curves, route_points, "\n".join(debug_lines))

    # Analyze routes
    total_length = sum(route.get_length() for route in routes)
    end_types = {}
    for route in routes:
        et = route.end_point_type
        end_types[et] = end_types.get(et, 0) + 1

    debug_lines.append("")
    debug_lines.append("Route summary:")
    debug_lines.append(f"  Total routes: {len(routes)}")
    debug_lines.append(f"  Total length: {total_length:.2f} ft")
    for et, count in end_types.items():
        debug_lines.append(f"  {et}: {count}")

    # Build JSON output
    output_data = {
        "routes": [route.to_dict() for route in routes],
        "count": len(routes),
        "total_length": total_length,
        "source": "gh_pipe_router",
    }
    routes_json = json.dumps(output_data, indent=2)

    debug_lines.append("")
    debug_lines.append(f"JSON output size: {len(routes_json)} chars")

    # Build geometry outputs for visualization
    if RHINO_AVAILABLE:
        for route in routes:
            if len(route.path_points) >= 2:
                # Create polyline from route path
                pts = [
                    rg.Point3d(p[0], p[1], p[2])
                    for p in route.path_points
                ]
                polyline = rg.Polyline(pts)
                route_curves.append(polyline.ToNurbsCurve())

                # Add points for visualization
                route_points.extend(pts)

        debug_lines.append(f"Created {len(route_curves)} route curves")
        debug_lines.append(f"Created {len(route_points)} route points")
    else:
        debug_lines.append("Rhino not available - skipping visualization geometry")

    # Summary
    debug_lines.append("")
    debug_lines.append("=" * 50)
    debug_lines.append("ROUTING COMPLETE")
    debug_lines.append(f"Total routes: {len(routes)}")
    debug_lines.append(f"Total length: {total_length:.2f} ft")
    debug_lines.append("=" * 50)

    return (routes_json, route_curves, route_points, "\n".join(debug_lines))


def _extract_walls_list(walls_data):
    """
    Extract list of walls from various JSON structures.

    Args:
        walls_data: Parsed JSON data from Wall Analyzer

    Returns:
        List of wall dictionaries
    """
    # Direct walls list
    if isinstance(walls_data, list):
        return walls_data

    # Walls key
    if isinstance(walls_data, dict):
        if "walls" in walls_data:
            return walls_data["walls"]

        # Single wall
        if "wall_id" in walls_data or "base_plane" in walls_data:
            return [walls_data]

        # Nested results
        if "results" in walls_data:
            return _extract_walls_list(walls_data["results"])

    return []


# =============================================================================
# EXECUTE
# =============================================================================

# Define default input values if not provided by Grasshopper
if 'run' not in dir():
    run = False

if 'connectors_json' not in dir():
    connectors_json = ""

if 'walls_json' not in dir():
    walls_json = ""

if 'max_search_distance' not in dir():
    max_search_distance = 10.0

# Execute main function
routes_json, route_curves, route_points, debug_info = main()
