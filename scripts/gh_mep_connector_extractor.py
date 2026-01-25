# File: scripts/gh_mep_connector_extractor.py
"""
GHPython Component: MEP Connector Extractor

Extracts MEP connectors from plumbing fixtures for pipe routing.
This is the first step in the MEP integration pipeline.

Inputs:
    plumbing_fixtures (list): Revit FamilyInstance elements (plumbing fixtures)
    system_types (list): Optional filter for system types
        (e.g., ["Sanitary", "DomesticColdWater", "DomesticHotWater"])
    exclude_connected (bool): Skip already-connected connectors (default: False)
    run (bool): Execute toggle

Outputs:
    connectors_json (str): JSON with connector data for downstream components
    connector_points (list): Point3d for each connector (visualization)
    connector_vectors (list): Vector3d for each connector direction
    debug_info (str): Processing summary and diagnostics

Usage:
    1. Connect Revit plumbing fixtures to 'plumbing_fixtures' input
    2. Optionally filter by system type
    3. Toggle 'run' to True
    4. Use connectors_json for pipe routing
    5. Visualize connector_points and connector_vectors in Rhino

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

# Revit API imports (only available in RiR context)
try:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import Domain
    REVIT_AVAILABLE = True
except Exception:
    REVIT_AVAILABLE = False

# Project imports
try:
    from src.timber_framing_generator.mep.plumbing import (
        PlumbingSystem,
        extract_plumbing_connectors,
    )
    from src.timber_framing_generator.core import MEPConnector
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

    Extracts plumbing connectors from Revit fixtures and outputs
    JSON data plus visualization geometry.
    """
    # Initialize outputs
    connectors_json = "{}"
    connector_points = []
    connector_vectors = []
    debug_lines = []

    # Header
    debug_lines.append("=" * 50)
    debug_lines.append("MEP CONNECTOR EXTRACTOR")
    debug_lines.append("=" * 50)

    # Check environment
    debug_lines.append(f"Rhino available: {RHINO_AVAILABLE}")
    debug_lines.append(f"Revit available: {REVIT_AVAILABLE}")
    debug_lines.append(f"Project modules available: {PROJECT_AVAILABLE}")

    if not PROJECT_AVAILABLE:
        debug_lines.append(f"Project import error: {PROJECT_ERROR}")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    # Check run toggle
    if not run:
        debug_lines.append("")
        debug_lines.append("Toggle 'run' to True to execute")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    # Check inputs
    if not plumbing_fixtures:
        debug_lines.append("")
        debug_lines.append("No plumbing fixtures provided")
        debug_lines.append("Connect Revit FamilyInstances to 'plumbing_fixtures' input")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    debug_lines.append("")
    debug_lines.append(f"Input fixtures: {len(plumbing_fixtures)}")

    # Build filter config
    filter_config = {}

    if system_types:
        filter_list = list(system_types) if hasattr(system_types, '__iter__') else [system_types]
        filter_config["system_types"] = filter_list
        debug_lines.append(f"Filtering by system types: {filter_list}")

    if exclude_connected:
        filter_config["exclude_connected"] = True
        debug_lines.append("Excluding already-connected connectors")

    # Extract connectors
    debug_lines.append("")
    debug_lines.append("Extracting connectors...")

    try:
        connectors = extract_plumbing_connectors(plumbing_fixtures, filter_config)
        debug_lines.append(f"Extracted {len(connectors)} connectors")
    except Exception as e:
        debug_lines.append(f"ERROR extracting connectors: {e}")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    if not connectors:
        debug_lines.append("No plumbing connectors found on fixtures")
        debug_lines.append("Ensure fixtures have MEP connectors defined in their families")
        return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))

    # Analyze connectors
    system_type_counts = {}
    for conn in connectors:
        st = conn.system_type
        system_type_counts[st] = system_type_counts.get(st, 0) + 1

    debug_lines.append("")
    debug_lines.append("Connectors by system type:")
    for st, count in sorted(system_type_counts.items()):
        debug_lines.append(f"  {st}: {count}")

    # Build JSON output
    output_data = {
        "connectors": [conn.to_dict() for conn in connectors],
        "count": len(connectors),
        "system_types": list(system_type_counts.keys()),
        "source": "gh_mep_connector_extractor",
    }
    connectors_json = json.dumps(output_data, indent=2)

    debug_lines.append("")
    debug_lines.append(f"JSON output size: {len(connectors_json)} chars")

    # Build geometry outputs for visualization
    if RHINO_AVAILABLE:
        for conn in connectors:
            # Create point at connector origin
            pt = rg.Point3d(
                conn.origin[0],
                conn.origin[1],
                conn.origin[2]
            )
            connector_points.append(pt)

            # Create vector for connector direction
            vec = rg.Vector3d(
                conn.direction[0],
                conn.direction[1],
                conn.direction[2]
            )
            connector_vectors.append(vec)

        debug_lines.append(f"Created {len(connector_points)} visualization points")
    else:
        debug_lines.append("Rhino not available - skipping visualization geometry")

    # Summary
    debug_lines.append("")
    debug_lines.append("=" * 50)
    debug_lines.append("EXTRACTION COMPLETE")
    debug_lines.append(f"Total connectors: {len(connectors)}")
    debug_lines.append("=" * 50)

    return (connectors_json, connector_points, connector_vectors, "\n".join(debug_lines))


# =============================================================================
# EXECUTE
# =============================================================================

# Define default input values if not provided by Grasshopper
if 'run' not in dir():
    run = False

if 'plumbing_fixtures' not in dir():
    plumbing_fixtures = []

if 'system_types' not in dir():
    system_types = None

if 'exclude_connected' not in dir():
    exclude_connected = False

# Execute main function
connectors_json, connector_points, connector_vectors, debug_info = main()
