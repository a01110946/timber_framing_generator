# File: scripts/gh_mep_connector_extractor.py
"""MEP Connector Extractor for Grasshopper.

Extracts plumbing connectors from Revit fixtures for pipe routing.
This is the first step in the MEP integration pipeline.

Key Features:
1. Connector Extraction
   - Extracts position, direction, and system type from Revit MEP connectors
   - Handles MEPModel/ConnectorManager None checks gracefully

2. System Type Filtering
   - Optional filter for Sanitary, DomesticColdWater, DomesticHotWater, Vent

3. Routing Direction
   - Returns physical routing direction (DOWN for drains, UP for vents)
   - NOT the connector's local axis (which varies by family authoring)

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit

Dependencies:
    - Rhino.Geometry: Core geometry creation
    - Grasshopper: Component framework
    - RevitAPI: MEP connector access
    - timber_framing_generator.mep.plumbing: Connector extraction logic

Input Requirements:
    plumbing_fixtures (fixtures) - list:
        Revit FamilyInstance elements (sinks, toilets, etc.)
        Required: Yes
        Access: List

    system_types (sys_types) - list:
        Filter for system types ["Sanitary", "DomesticColdWater", etc.]
        Required: No (defaults to all types)
        Access: List

    exclude_connected (excl_conn) - bool:
        Skip connectors already connected to pipes
        Required: No (defaults to False)
        Access: Item

    run (run) - bool:
        Execute toggle
        Required: Yes
        Access: Item

Outputs:
    connectors_json (json) - str:
        JSON with connector data for downstream components

    connector_points (pts) - list of Point3d:
        Connector positions for visualization

    connector_vectors (vecs) - list of Vector3d:
        Routing directions for visualization

    debug_info (info) - str:
        Processing summary and diagnostics

Author: Claude AI Assistant
Version: 1.1.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import sys
import json
import traceback

# Force reload of project modules (development only)
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

# Rhino / Grasshopper
import Rhino
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Connector Extractor"
COMPONENT_NICKNAME = "MEPConn"
COMPONENT_MESSAGE = "v1.1"

# Project path
PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# =============================================================================
# Project Imports
# =============================================================================

try:
    from src.timber_framing_generator.mep.plumbing import extract_plumbing_connectors
    from src.timber_framing_generator.core import MEPConnector
    from src.timber_framing_generator.utils.geometry_factory import get_factory
    PROJECT_AVAILABLE = True
    PROJECT_ERROR = None
except ImportError as e:
    PROJECT_AVAILABLE = False
    PROJECT_ERROR = str(e)

# =============================================================================
# Logging Utilities
# =============================================================================

def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message."""
    print(f"[{level.upper()}] {message}")
    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)


def log_info(message):
    print(f"[INFO] {message}")


def log_warning(message):
    log_message(message, "warning")


def log_error(message):
    log_message(message, "error")

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component."""
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE

# =============================================================================
# Helper Functions
# =============================================================================

def validate_inputs():
    """Validate component inputs."""
    if not PROJECT_AVAILABLE:
        return False, f"Project import error: {PROJECT_ERROR}"

    if not run:
        return False, "Toggle 'run' to True to execute"

    if not plumbing_fixtures:
        return False, "No plumbing fixtures provided"

    return True, None


def build_filter_config():
    """Build filter configuration from inputs."""
    config = {}

    if system_types:
        filter_list = list(system_types) if hasattr(system_types, '__iter__') else [system_types]
        config["system_types"] = filter_list

    if exclude_connected:
        config["exclude_connected"] = True

    return config


def create_visualization_geometry(connectors, factory):
    """Create visualization points and vectors using RhinoCommonFactory.

    Args:
        connectors: List of MEPConnector objects
        factory: RhinoCommonFactory instance

    Returns:
        tuple: (points, vectors) lists
    """
    points = []
    vectors = []

    for conn in connectors:
        # Create point using factory (ensures RhinoCommon assembly)
        pt = factory.create_point3d(
            conn.origin[0],
            conn.origin[1],
            conn.origin[2]
        )
        points.append(pt)

        # Create vector using factory
        vec = factory.create_vector3d(
            conn.direction[0],
            conn.direction[1],
            conn.direction[2]
        )
        vectors.append(vec)

    return points, vectors

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component."""
    # Setup component
    setup_component()

    # Initialize outputs
    connectors_json = "{}"
    connector_points = []
    connector_vectors = []
    debug_lines = []

    debug_lines.append("=" * 50)
    debug_lines.append("MEP CONNECTOR EXTRACTOR")
    debug_lines.append("=" * 50)

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs()
        if not is_valid:
            debug_lines.append(error_msg)
            return connectors_json, connector_points, connector_vectors, "\n".join(debug_lines)

        debug_lines.append(f"Input fixtures: {len(plumbing_fixtures)}")

        # Build filter config
        filter_config = build_filter_config()
        if filter_config.get("system_types"):
            debug_lines.append(f"Filtering by: {filter_config['system_types']}")

        # Extract connectors
        debug_lines.append("")
        debug_lines.append("Extracting connectors...")
        connectors = extract_plumbing_connectors(plumbing_fixtures, filter_config)
        debug_lines.append(f"Extracted {len(connectors)} connectors")

        if not connectors:
            debug_lines.append("No plumbing connectors found")
            debug_lines.append("Ensure fixtures have MEP connectors in their families")
            return connectors_json, connector_points, connector_vectors, "\n".join(debug_lines)

        # Analyze by system type
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

        # Create visualization geometry using RhinoCommonFactory
        factory = get_factory()
        connector_points, connector_vectors = create_visualization_geometry(connectors, factory)

        debug_lines.append("")
        debug_lines.append(f"Created {len(connector_points)} visualization points")
        debug_lines.append(f"JSON output size: {len(connectors_json)} chars")

        # Summary
        debug_lines.append("")
        debug_lines.append("=" * 50)
        debug_lines.append("EXTRACTION COMPLETE")
        debug_lines.append(f"Total connectors: {len(connectors)}")
        debug_lines.append("=" * 50)

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return connectors_json, connector_points, connector_vectors, "\n".join(debug_lines)

# =============================================================================
# Execution
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

# Execute main and assign to output variables
connectors_json, connector_points, connector_vectors, debug_info = main()
