# File: scripts/gh_revit_pipe_creator.py
"""Revit Pipe Creator for Grasshopper.

Creates Revit Pipe elements from calculated pipe routes using RhinoInside.Revit.
This is the third step in the MEP integration pipeline.

Key Features:
1. Pipe Creation
   - Creates Revit Pipe elements from route segments
   - Handles branch/trunk topology for merged routes
   - Assigns correct piping system types

2. Fitting Creation
   - Creates elbow fittings at 90-degree corners
   - Creates tee fittings at merge points (e.g., double sink drains)

3. Transaction Management
   - Groups all creation in a single transaction
   - Rollback on critical errors

Environment:
    Rhino 8
    Grasshopper
    RhinoInside.Revit
    Python component (CPython 3)

Dependencies:
    - RhinoInside.Revit: Document access
    - Autodesk.Revit.DB: Revit API
    - timber_framing_generator.mep.plumbing: Pipe creation logic

Input Requirements:
    routes_json (routes_json) - str:
        JSON from Pipe Router component
        Required: Yes
        Access: Item

    pipe_type (pipe_type) - Revit PipeType:
        Pipe type from RiR Type Picker
        Required: Yes
        Access: Item

    level (level) - Revit Level:
        Reference level for pipes
        Required: Yes
        Access: Item

    create_fittings (fittings) - bool:
        Create elbows at corners (default: True)
        Required: No
        Access: Item

    run (run) - bool:
        Execute toggle
        Required: Yes
        Access: Item

Outputs:
    created_pipes (pipes) - list:
        Created Revit Pipe elements

    created_fittings (fits) - list:
        Created Revit Fitting elements

    creation_json (json) - str:
        JSON log with element IDs and statistics

    debug_info (info) - str:
        Processing summary and diagnostics

Author: Claude AI Assistant
Version: 1.0.0
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

COMPONENT_NAME = "Revit Pipe Creator"
COMPONENT_NICKNAME = "PipeCrt"
COMPONENT_MESSAGE = "v1.0"

# Project path
PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# =============================================================================
# Project Imports
# =============================================================================

try:
    from src.timber_framing_generator.mep.plumbing import (
        build_all_pipe_networks,
        get_networks_summary,
        get_revit_system_type_name,
        PipeNetwork,
        PipeSegment,
    )
    PROJECT_AVAILABLE = True
    PROJECT_ERROR = None
except ImportError as e:
    PROJECT_AVAILABLE = False
    PROJECT_ERROR = str(e)

# =============================================================================
# Revit API Imports
# =============================================================================

REVIT_AVAILABLE = False
REVIT_ERROR = None

try:
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        Transaction,
        XYZ,
        ElementId,
        FilteredElementCollector,
        BuiltInCategory,
    )
    from Autodesk.Revit.DB.Plumbing import (
        Pipe,
        PipingSystemType,
    )
    from RhinoInside.Revit import Revit
    REVIT_AVAILABLE = True
except ImportError as e:
    REVIT_ERROR = str(e)
except Exception as e:
    REVIT_ERROR = str(e)

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
# Revit Helper Functions
# =============================================================================

def get_piping_system_type(doc, system_type_name):
    """Get PipingSystemType by name.

    Args:
        doc: Revit document
        system_type_name: System type name (e.g., "Sanitary", "Domestic Cold Water")

    Returns:
        PipingSystemType element or None
    """
    collector = FilteredElementCollector(doc)
    system_types = collector.OfClass(PipingSystemType).ToElements()

    for st in system_types:
        if st.Name == system_type_name:
            return st

    # Try partial match
    for st in system_types:
        if system_type_name.lower() in st.Name.lower():
            return st

    return None


def get_pipe_end_connector(pipe, at_end=True):
    """Get connector at start or end of pipe.

    Args:
        pipe: Revit Pipe element
        at_end: If True, get end connector; if False, get start connector

    Returns:
        Connector or None
    """
    connectors = pipe.ConnectorManager.Connectors

    # Get pipe curve to determine start/end
    curve = pipe.Location.Curve
    target_point = curve.GetEndPoint(1) if at_end else curve.GetEndPoint(0)

    closest_conn = None
    closest_dist = float('inf')

    for conn in connectors:
        dist = conn.Origin.DistanceTo(target_point)
        if dist < closest_dist:
            closest_dist = dist
            closest_conn = conn

    return closest_conn


def create_pipe_element(doc, segment, pipe_type_id, system_type_id, level_id):
    """Create a single Revit Pipe element.

    Args:
        doc: Revit document
        segment: PipeSegment with start/end points
        pipe_type_id: ElementId of PipeType
        system_type_id: ElementId of PipingSystemType
        level_id: ElementId of Level

    Returns:
        Pipe element or None
    """
    try:
        start_xyz = XYZ(
            segment.start_point[0],
            segment.start_point[1],
            segment.start_point[2]
        )
        end_xyz = XYZ(
            segment.end_point[0],
            segment.end_point[1],
            segment.end_point[2]
        )

        # Check for zero-length pipe
        if start_xyz.DistanceTo(end_xyz) < 0.01:  # Less than 0.01 ft
            log_warning(f"Skipping zero-length segment in route {segment.route_id}")
            return None

        pipe = Pipe.Create(
            doc,
            system_type_id,
            pipe_type_id,
            level_id,
            start_xyz,
            end_xyz
        )

        return pipe

    except Exception as e:
        log_warning(f"Failed to create pipe segment: {e}")
        return None


def create_elbow_fitting(doc, pipe1, pipe2):
    """Create elbow fitting between two pipes.

    Args:
        doc: Revit document
        pipe1: First pipe (get end connector)
        pipe2: Second pipe (get start connector)

    Returns:
        Fitting element or None
    """
    try:
        conn1 = get_pipe_end_connector(pipe1, at_end=True)
        conn2 = get_pipe_end_connector(pipe2, at_end=False)

        if conn1 is None or conn2 is None:
            log_warning("Could not find connectors for elbow")
            return None

        fitting = doc.Create.NewElbowFitting(conn1, conn2)
        return fitting

    except Exception as e:
        log_warning(f"Failed to create elbow fitting: {e}")
        return None


def create_tee_fitting(doc, branch_pipe, trunk_pipe):
    """Create tee fitting at merge point.

    Args:
        doc: Revit document
        branch_pipe: Branch pipe connecting to trunk
        trunk_pipe: Main trunk pipe

    Returns:
        Fitting element or None
    """
    try:
        # Get end connector of branch
        branch_conn = get_pipe_end_connector(branch_pipe, at_end=True)

        if branch_conn is None:
            log_warning("Could not find branch connector for tee")
            return None

        # Find closest connector on trunk pipe
        trunk_connectors = trunk_pipe.ConnectorManager.Connectors
        closest_conn = None
        closest_dist = float('inf')

        for conn in trunk_connectors:
            dist = conn.Origin.DistanceTo(branch_conn.Origin)
            if dist < closest_dist:
                closest_dist = dist
                closest_conn = conn

        if closest_conn is None:
            log_warning("Could not find trunk connector for tee")
            return None

        fitting = doc.Create.NewTeeFitting(branch_conn, closest_conn)
        return fitting

    except Exception as e:
        log_warning(f"Failed to create tee fitting: {e}")
        return None

# =============================================================================
# Main Processing
# =============================================================================

def create_pipes_from_network(doc, network, pipe_type_id, level_id, do_fittings):
    """Create pipes and fittings from a single PipeNetwork.

    Args:
        doc: Revit document
        network: PipeNetwork object
        pipe_type_id: ElementId of PipeType
        level_id: ElementId of Level
        do_fittings: Create fittings at corners

    Returns:
        tuple: (pipes list, fittings list, debug messages list)
    """
    pipes = []
    fittings = []
    debug = []

    # Get system type
    revit_system_name = get_revit_system_type_name(network.system_type)
    system_type = get_piping_system_type(doc, revit_system_name)

    if system_type is None:
        debug.append(f"WARNING: System type '{revit_system_name}' not found")
        return pipes, fittings, debug

    system_type_id = system_type.Id
    debug.append(f"Using system type: {system_type.Name}")

    # Create trunk pipes first (shared segments)
    trunk_pipes = []
    for segment in network.trunk:
        pipe = create_pipe_element(doc, segment, pipe_type_id, system_type_id, level_id)
        if pipe is not None:
            pipes.append(pipe)
            trunk_pipes.append(pipe)

    debug.append(f"Created {len(trunk_pipes)} trunk pipes")

    # Create elbows between trunk segments
    if do_fittings and len(trunk_pipes) > 1:
        for i in range(len(trunk_pipes) - 1):
            fitting = create_elbow_fitting(doc, trunk_pipes[i], trunk_pipes[i+1])
            if fitting is not None:
                fittings.append(fitting)

    # Create branch pipes (unique per connector)
    all_branch_pipes = []
    for branch_idx, branch_segments in enumerate(network.branches):
        branch_pipes = []
        for segment in branch_segments:
            pipe = create_pipe_element(doc, segment, pipe_type_id, system_type_id, level_id)
            if pipe is not None:
                pipes.append(pipe)
                branch_pipes.append(pipe)

        all_branch_pipes.append(branch_pipes)
        debug.append(f"Created {len(branch_pipes)} pipes for branch {branch_idx}")

        # Create elbows between branch segments
        if do_fittings and len(branch_pipes) > 1:
            for i in range(len(branch_pipes) - 1):
                fitting = create_elbow_fitting(doc, branch_pipes[i], branch_pipes[i+1])
                if fitting is not None:
                    fittings.append(fitting)

    # Create tee fittings at merge point
    if do_fittings and network.needs_tee_fitting() and len(trunk_pipes) > 0:
        first_trunk_pipe = trunk_pipes[0]
        for branch_pipes in all_branch_pipes:
            if len(branch_pipes) > 0:
                last_branch_pipe = branch_pipes[-1]
                fitting = create_tee_fitting(doc, last_branch_pipe, first_trunk_pipe)
                if fitting is not None:
                    fittings.append(fitting)
                    debug.append("Created tee fitting at merge point")

    return pipes, fittings, debug


def validate_inputs():
    """Validate component inputs."""
    if not PROJECT_AVAILABLE:
        return False, f"Project import error: {PROJECT_ERROR}"

    if not REVIT_AVAILABLE:
        return False, f"Revit API not available: {REVIT_ERROR}"

    if not run:
        return False, "Toggle 'run' to True to execute"

    if not routes_json:
        return False, "No routes_json provided"

    if pipe_type is None:
        return False, "No pipe_type provided (use RiR Type Picker)"

    if level is None:
        return False, "No level provided (use RiR Level Picker)"

    return True, None

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main entry point for the component."""
    # Setup component
    setup_component()

    # Initialize outputs
    created_pipes = []
    created_fittings = []
    creation_json = "{}"
    debug_lines = []

    debug_lines.append("=" * 50)
    debug_lines.append("REVIT PIPE CREATOR")
    debug_lines.append("=" * 50)

    try:
        # Validate inputs
        is_valid, error_msg = validate_inputs()
        if not is_valid:
            debug_lines.append(error_msg)
            return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

        # Get Revit document
        doc = Revit.ActiveDBDocument
        if doc is None:
            debug_lines.append("ERROR: No active Revit document")
            return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

        debug_lines.append(f"Document: {doc.Title}")

        # Get element IDs
        pipe_type_id = pipe_type.Id
        level_id = level.Id

        debug_lines.append(f"Pipe Type: {pipe_type.Name}")
        debug_lines.append(f"Level: {level.Name}")
        debug_lines.append(f"Create Fittings: {create_fittings}")

        # Build pipe networks from routes
        debug_lines.append("")
        debug_lines.append("Building pipe networks...")
        networks = build_all_pipe_networks(routes_json)

        if not networks:
            debug_lines.append("No pipe networks could be built from routes")
            return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

        # Show network summary
        summary = get_networks_summary(networks)
        debug_lines.append(f"Networks: {summary['total_networks']}")
        debug_lines.append(f"Total segments: {summary['total_segments']}")
        debug_lines.append(f"Tee fittings needed: {summary['tee_fittings_needed']}")

        # Start transaction
        debug_lines.append("")
        debug_lines.append("Creating pipes in Revit...")

        t = Transaction(doc, "Create Plumbing Pipes")
        t.Start()

        try:
            # Process each network
            for network in networks:
                debug_lines.append("")
                debug_lines.append(f"Network: Fixture {network.fixture_id} - {network.system_type}")

                pipes, fittings, net_debug = create_pipes_from_network(
                    doc, network, pipe_type_id, level_id, create_fittings
                )

                created_pipes.extend(pipes)
                created_fittings.extend(fittings)
                debug_lines.extend(net_debug)

            # Commit transaction
            t.Commit()
            debug_lines.append("")
            debug_lines.append("Transaction committed successfully")

        except Exception as e:
            t.RollBack()
            debug_lines.append(f"ERROR: Transaction rolled back: {e}")
            debug_lines.append(traceback.format_exc())
            return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

        # Build output JSON
        output_data = {
            "pipes_created": len(created_pipes),
            "fittings_created": len(created_fittings),
            "pipe_ids": [p.Id.IntegerValue for p in created_pipes],
            "fitting_ids": [f.Id.IntegerValue for f in created_fittings],
            "networks_processed": len(networks),
            "source": "gh_revit_pipe_creator",
        }
        creation_json = json.dumps(output_data, indent=2)

        # Summary
        debug_lines.append("")
        debug_lines.append("=" * 50)
        debug_lines.append("CREATION COMPLETE")
        debug_lines.append(f"Pipes created: {len(created_pipes)}")
        debug_lines.append(f"Fittings created: {len(created_fittings)}")
        debug_lines.append("=" * 50)

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        debug_lines.append(f"ERROR: {str(e)}")
        debug_lines.append(traceback.format_exc())

    return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

# =============================================================================
# Execution
# =============================================================================

# Define default input values if not provided by Grasshopper
if 'run' not in dir():
    run = False

if 'routes_json' not in dir():
    routes_json = ""

if 'pipe_type' not in dir():
    pipe_type = None

if 'level' not in dir():
    level = None

if 'create_fittings' not in dir():
    create_fittings = True

# Execute main and assign to output variables
created_pipes, created_fittings, creation_json, debug_info = main()
