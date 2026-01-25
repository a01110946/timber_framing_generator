# File: scripts/gh_connector_diagnostics.py
"""MEP Connector Diagnostics for Grasshopper.

This diagnostic component extracts ALL available properties from Revit
MEP connectors to help understand how connector directions work across
different plumbing fixture types.

Key Questions to Investigate:
1. What does CoordinateSystem.BasisZ represent for different fixtures?
2. Does it vary by fixture type (faucet vs drain vs toilet)?
3. What other properties might indicate routing direction?
4. How does FlowDirection relate to physical pipe routing?

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit

Input Requirements:
    plumbing_fixtures (fixtures) - list:
        Revit FamilyInstance elements (sinks, toilets, etc.)
        Required: Yes
        Access: List

    run (run) - bool:
        Execute toggle
        Required: Yes
        Access: Item

Outputs:
    diagnostics_json (json) - str:
        Full JSON dump of all connector properties

    summary (summary) - str:
        Human-readable summary of findings

    debug_info (info) - str:
        Processing log

Author: Claude AI Assistant
Version: 1.0.0
"""

# =============================================================================
# Imports
# =============================================================================

import sys
import json
import traceback

# Force reload
FORCE_RELOAD = True
if FORCE_RELOAD:
    modules_to_reload = [k for k in sys.modules.keys()
                         if 'timber_framing_generator' in k]
    for mod_name in modules_to_reload:
        del sys.modules[mod_name]

# .NET / CLR
import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

import Rhino
import Rhino.Geometry as rg
import Grasshopper

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "Connector Diagnostics"
COMPONENT_NICKNAME = "ConnDiag"
COMPONENT_MESSAGE = "v1.0"

# =============================================================================
# Helper Functions
# =============================================================================

def get_element_info(element):
    """Extract basic element info."""
    info = {
        "id": 0,
        "family_name": "Unknown",
        "type_name": "Unknown",
        "category": "Unknown",
    }

    # Get ID
    elem_id = getattr(element, 'Id', None)
    if elem_id:
        info["id"] = int(getattr(elem_id, 'IntegerValue', 0))

    # Get family/type names
    try:
        symbol = getattr(element, 'Symbol', None)
        if symbol:
            family = getattr(symbol, 'Family', None)
            if family:
                info["family_name"] = str(getattr(family, 'Name', 'Unknown'))
            info["type_name"] = str(getattr(symbol, 'Name', 'Unknown'))
    except:
        pass

    # Get category
    try:
        category = getattr(element, 'Category', None)
        if category:
            info["category"] = str(getattr(category, 'Name', 'Unknown'))
    except:
        pass

    return info


def extract_all_connector_properties(conn):
    """Extract ALL available properties from a connector for investigation."""
    props = {}

    # Basic properties
    props["id"] = getattr(conn, 'Id', 0)

    # Domain
    domain = getattr(conn, 'Domain', None)
    props["domain"] = str(domain) if domain else None

    # System type
    pipe_sys = getattr(conn, 'PipeSystemType', None)
    props["pipe_system_type"] = str(pipe_sys) if pipe_sys else None

    # Connection status
    props["is_connected"] = getattr(conn, 'IsConnected', None)

    # Radius (for round connectors)
    radius = getattr(conn, 'Radius', None)
    if radius is not None:
        props["radius_ft"] = float(radius)
        props["radius_in"] = float(radius) * 12

    # Flow direction
    flow_dir = getattr(conn, 'FlowDirection', None)
    props["flow_direction"] = str(flow_dir) if flow_dir else None

    # Shape
    shape = getattr(conn, 'Shape', None)
    props["shape"] = str(shape) if shape else None

    # Direction (might be different from BasisZ)
    direction = getattr(conn, 'Direction', None)
    if direction:
        props["direction"] = {
            "x": float(getattr(direction, 'X', 0)),
            "y": float(getattr(direction, 'Y', 0)),
            "z": float(getattr(direction, 'Z', 0)),
        }

    # Origin
    origin = getattr(conn, 'Origin', None)
    if origin:
        props["origin"] = {
            "x": float(getattr(origin, 'X', 0)),
            "y": float(getattr(origin, 'Y', 0)),
            "z": float(getattr(origin, 'Z', 0)),
        }

    # CoordinateSystem (this is what we've been using)
    coord_sys = getattr(conn, 'CoordinateSystem', None)
    if coord_sys:
        props["coordinate_system"] = {}

        # BasisX
        basis_x = getattr(coord_sys, 'BasisX', None)
        if basis_x:
            props["coordinate_system"]["basis_x"] = {
                "x": float(getattr(basis_x, 'X', 0)),
                "y": float(getattr(basis_x, 'Y', 0)),
                "z": float(getattr(basis_x, 'Z', 0)),
            }

        # BasisY
        basis_y = getattr(coord_sys, 'BasisY', None)
        if basis_y:
            props["coordinate_system"]["basis_y"] = {
                "x": float(getattr(basis_y, 'X', 0)),
                "y": float(getattr(basis_y, 'Y', 0)),
                "z": float(getattr(basis_y, 'Z', 0)),
            }

        # BasisZ (what we've been using as "direction")
        basis_z = getattr(coord_sys, 'BasisZ', None)
        if basis_z:
            props["coordinate_system"]["basis_z"] = {
                "x": float(getattr(basis_z, 'X', 0)),
                "y": float(getattr(basis_z, 'Y', 0)),
                "z": float(getattr(basis_z, 'Z', 0)),
            }

        # Origin from coordinate system
        cs_origin = getattr(coord_sys, 'Origin', None)
        if cs_origin:
            props["coordinate_system"]["origin"] = {
                "x": float(getattr(cs_origin, 'X', 0)),
                "y": float(getattr(cs_origin, 'Y', 0)),
                "z": float(getattr(cs_origin, 'Z', 0)),
            }

    # Angle (if available)
    angle = getattr(conn, 'Angle', None)
    if angle is not None:
        props["angle_rad"] = float(angle)
        props["angle_deg"] = float(angle) * 180.0 / 3.14159265359

    # Connector type
    conn_type = getattr(conn, 'ConnectorType', None)
    props["connector_type"] = str(conn_type) if conn_type else None

    # Description (if any)
    description = getattr(conn, 'Description', None)
    props["description"] = str(description) if description else None

    # AllRefs (connected elements)
    try:
        all_refs = getattr(conn, 'AllRefs', None)
        if all_refs:
            props["connected_count"] = all_refs.Size
    except:
        pass

    return props


def analyze_directions(connectors_data):
    """Analyze direction patterns across fixtures."""
    analysis = {
        "by_system_type": {},
        "by_fixture_type": {},
        "direction_patterns": [],
    }

    for fixture_data in connectors_data:
        fixture_type = fixture_data.get("family_name", "Unknown")

        for conn in fixture_data.get("connectors", []):
            sys_type = conn.get("pipe_system_type", "Unknown")

            # Track by system type
            if sys_type not in analysis["by_system_type"]:
                analysis["by_system_type"][sys_type] = []

            basis_z = conn.get("coordinate_system", {}).get("basis_z", {})
            direction = conn.get("direction", {})
            flow = conn.get("flow_direction", "Unknown")

            pattern = {
                "fixture": fixture_type,
                "system_type": sys_type,
                "flow_direction": flow,
                "basis_z": basis_z,
                "direction_prop": direction,
            }

            analysis["by_system_type"][sys_type].append(pattern)
            analysis["direction_patterns"].append(pattern)

            # Track by fixture
            if fixture_type not in analysis["by_fixture_type"]:
                analysis["by_fixture_type"][fixture_type] = []
            analysis["by_fixture_type"][fixture_type].append(pattern)

    return analysis


def create_summary(connectors_data, analysis):
    """Create human-readable summary."""
    lines = []
    lines.append("=" * 60)
    lines.append("CONNECTOR DIRECTION ANALYSIS")
    lines.append("=" * 60)

    lines.append("")
    lines.append(f"Total fixtures analyzed: {len(connectors_data)}")
    total_connectors = sum(len(f.get("connectors", [])) for f in connectors_data)
    lines.append(f"Total connectors found: {total_connectors}")

    # By system type
    lines.append("")
    lines.append("-" * 40)
    lines.append("DIRECTION ANALYSIS BY SYSTEM TYPE")
    lines.append("-" * 40)

    for sys_type, patterns in analysis["by_system_type"].items():
        lines.append(f"\n{sys_type} ({len(patterns)} connectors):")

        # Summarize BasisZ directions
        z_values = [p.get("basis_z", {}).get("z", 0) for p in patterns]
        avg_z = sum(z_values) / len(z_values) if z_values else 0

        lines.append(f"  Average BasisZ.z: {avg_z:.3f}")
        lines.append(f"  Range: {min(z_values):.3f} to {max(z_values):.3f}")

        # Flow directions
        flows = set(p.get("flow_direction") for p in patterns)
        lines.append(f"  Flow directions: {flows}")

        # Sample connectors
        lines.append("  Sample BasisZ vectors:")
        for p in patterns[:3]:
            bz = p.get("basis_z", {})
            lines.append(f"    {p['fixture']}: ({bz.get('x', 0):.3f}, {bz.get('y', 0):.3f}, {bz.get('z', 0):.3f})")

    # By fixture type
    lines.append("")
    lines.append("-" * 40)
    lines.append("DIRECTION ANALYSIS BY FIXTURE TYPE")
    lines.append("-" * 40)

    for fixture_type, patterns in analysis["by_fixture_type"].items():
        lines.append(f"\n{fixture_type}:")

        for p in patterns:
            bz = p.get("basis_z", {})
            sys = p.get("system_type", "?")
            flow = p.get("flow_direction", "?")
            lines.append(f"  {sys} (flow={flow}): BasisZ=({bz.get('x', 0):.3f}, {bz.get('y', 0):.3f}, {bz.get('z', 0):.3f})")

    # Key observations
    lines.append("")
    lines.append("-" * 40)
    lines.append("KEY QUESTIONS TO ANSWER")
    lines.append("-" * 40)
    lines.append("1. Do drain connectors consistently point DOWN (Z < 0)?")
    lines.append("2. Do supply connectors point toward pipe source?")
    lines.append("3. Is 'Direction' property different from BasisZ?")
    lines.append("4. Does FlowDirection correlate with physical routing?")

    return "\n".join(lines)


# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point."""
    # Initialize outputs
    diagnostics_json = "{}"
    summary = ""
    debug_lines = []

    debug_lines.append("=" * 50)
    debug_lines.append("CONNECTOR DIAGNOSTICS")
    debug_lines.append("=" * 50)

    try:
        # Check run
        if not run:
            debug_lines.append("Toggle 'run' to True to execute")
            return diagnostics_json, summary, "\n".join(debug_lines)

        # Check input
        if not plumbing_fixtures:
            debug_lines.append("No plumbing fixtures provided")
            return diagnostics_json, summary, "\n".join(debug_lines)

        debug_lines.append(f"Analyzing {len(plumbing_fixtures)} fixtures...")

        # Extract all connector data
        all_fixture_data = []

        for element in plumbing_fixtures:
            element_info = get_element_info(element)
            fixture_data = {
                **element_info,
                "connectors": [],
            }

            # Get MEP connectors
            mep_model = getattr(element, 'MEPModel', None)
            if mep_model is None:
                debug_lines.append(f"  {element_info['id']}: No MEPModel")
                continue

            conn_manager = getattr(mep_model, 'ConnectorManager', None)
            if conn_manager is None:
                debug_lines.append(f"  {element_info['id']}: No ConnectorManager")
                continue

            connector_set = getattr(conn_manager, 'Connectors', None)
            if connector_set is None:
                continue

            for conn in connector_set:
                # Only plumbing connectors
                domain = getattr(conn, 'Domain', None)
                domain_str = str(domain) if domain else ""
                if 'Piping' not in domain_str:
                    continue

                # Extract all properties
                conn_props = extract_all_connector_properties(conn)
                fixture_data["connectors"].append(conn_props)

            if fixture_data["connectors"]:
                all_fixture_data.append(fixture_data)
                debug_lines.append(f"  {element_info['family_name']}: {len(fixture_data['connectors'])} connectors")

        debug_lines.append(f"\nTotal fixtures with connectors: {len(all_fixture_data)}")

        # Analyze patterns
        analysis = analyze_directions(all_fixture_data)

        # Build output
        output = {
            "fixtures": all_fixture_data,
            "analysis": analysis,
        }
        diagnostics_json = json.dumps(output, indent=2)

        # Create summary
        summary = create_summary(all_fixture_data, analysis)

        debug_lines.append("")
        debug_lines.append("=" * 50)
        debug_lines.append("DIAGNOSTICS COMPLETE")
        debug_lines.append("=" * 50)

    except Exception as e:
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return diagnostics_json, summary, "\n".join(debug_lines)


# =============================================================================
# Execution
# =============================================================================

if 'run' not in dir():
    run = False

if 'plumbing_fixtures' not in dir():
    plumbing_fixtures = []

diagnostics_json, summary, debug_info = main()
