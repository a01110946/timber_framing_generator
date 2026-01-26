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
        Pipe type from RiR Type Picker.
        IMPORTANT: This must be a PipeType (physical pipe configuration like
        "Standard", "Copper", "PVC"), NOT a PipingSystemType (like "Domestic
        Cold Water" or "Sanitary").
        Use: Element Type Picker > Category: Pipe Types
        Required: No (will use first available if not provided)
        Access: Item

    level (level) - Revit Level:
        Reference level for pipes
        Required: Yes
        Access: Item

    create_fittings (fittings) - bool:
        Create elbows at corners (default: False)
        WARNING: Fitting creation can cause Revit errors due to pipe
        direction/flow issues. Leave False until pipes are verified.
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
        MergePointInfo,
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
        BuiltInParameter,
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

def get_available_pipe_types(doc):
    """Get all available PipeType elements in the document.

    Returns:
        List of (name, ElementId) tuples
    """
    from Autodesk.Revit.DB.Plumbing import PipeType

    collector = FilteredElementCollector(doc)
    pipe_types = collector.OfClass(PipeType).ToElements()

    return [(pt.Name, pt.Id) for pt in pipe_types]


def validate_pipe_type(doc, pipe_type_element):
    """Validate that the input is actually a PipeType.

    Args:
        doc: Revit document
        pipe_type_element: Element from RiR Type Picker

    Returns:
        tuple: (is_valid, error_message, pipe_type_id)
    """
    from Autodesk.Revit.DB.Plumbing import PipeType

    if pipe_type_element is None:
        return False, "No pipe_type provided", None

    # Debug: show what type we received
    element_clr_type = pipe_type_element.GetType()
    log_info(f"pipe_type input CLR type: {element_clr_type.FullName}")

    # Get the actual element from document to verify
    try:
        element_id = pipe_type_element.Id
        log_info(f"pipe_type.Id = {element_id.IntegerValue}")

        element = doc.GetElement(element_id)

        if element is None:
            return False, f"Could not find element with Id {element_id.IntegerValue}", None

        element_type_name = element.GetType().Name
        log_info(f"Element from doc: {element_type_name}")

        # Check if it's a PipeType
        if isinstance(element, PipeType):
            log_info(f"Validated as PipeType: {element.Name}")
            return True, None, element_id

        # It's not a PipeType - provide helpful error
        actual_type = element.GetType().Name
        available = get_available_pipe_types(doc)
        available_names = [name for name, _ in available]

        error_msg = (
            f"Input is a {actual_type}, not a PipeType.\n"
            f"Element name: {pipe_type_element.Name}\n"
            f"Available PipeTypes in document: {', '.join(available_names)}\n"
            f"Use a Type Picker filtered to 'Pipe Types' category."
        )
        return False, error_msg, None

    except Exception as e:
        import traceback
        return False, f"Error validating pipe type: {e}\n{traceback.format_exc()}", None


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
    try:
        conn_manager = pipe.ConnectorManager
        if conn_manager is None:
            log_info(f"    Pipe {pipe.Id.IntegerValue} has no ConnectorManager")
            return None

        connectors = conn_manager.Connectors
        if connectors is None:
            log_info(f"    Pipe {pipe.Id.IntegerValue} has no Connectors")
            return None

        # Get pipe curve to determine start/end
        location = pipe.Location
        if location is None:
            log_info(f"    Pipe {pipe.Id.IntegerValue} has no Location")
            return None

        curve = location.Curve
        if curve is None:
            log_info(f"    Pipe {pipe.Id.IntegerValue} has no Curve")
            return None

        target_point = curve.GetEndPoint(1) if at_end else curve.GetEndPoint(0)

        closest_conn = None
        closest_dist = float('inf')

        for conn in connectors:
            dist = conn.Origin.DistanceTo(target_point)
            if dist < closest_dist:
                closest_dist = dist
                closest_conn = conn

        return closest_conn

    except Exception as e:
        log_info(f"    get_pipe_end_connector error: {e}")
        return None


def create_pipe_element(doc, segment, pipe_type_id, system_type_id, level_id):
    """Create a single Revit Pipe element.

    Args:
        doc: Revit document
        segment: PipeSegment with start/end points and pipe_size
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
        length = start_xyz.DistanceTo(end_xyz)
        if length < 0.01:  # Less than 0.01 ft
            log_warning(f"Skipping zero-length segment in route {segment.route_id}")
            return None

        # Get pipe size (in feet) - use segment's pipe_size which has system-appropriate defaults
        pipe_diameter = segment.pipe_size if segment.pipe_size and segment.pipe_size > 0 else 0.0417  # 0.5" fallback
        pipe_diameter_inches = pipe_diameter * 12

        log_info(f"Creating pipe: len={length:.3f}ft, dia={pipe_diameter_inches:.2f}in ({segment.system_type})")
        log_info(f"  system_type_id={system_type_id.IntegerValue}, pipe_type_id={pipe_type_id.IntegerValue}, level_id={level_id.IntegerValue}")

        pipe = Pipe.Create(
            doc,
            system_type_id,
            pipe_type_id,
            level_id,
            start_xyz,
            end_xyz
        )

        # Set the pipe diameter
        # The diameter parameter is RBS_PIPE_DIAMETER_PARAM
        diameter_param = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if diameter_param is not None and not diameter_param.IsReadOnly:
            diameter_param.Set(pipe_diameter)
            log_info(f"  Set diameter to {pipe_diameter:.4f} ft ({pipe_diameter * 12:.2f} in)")
        else:
            # Try setting via LookupParameter
            diameter_param2 = pipe.LookupParameter("Diameter")
            if diameter_param2 is not None and not diameter_param2.IsReadOnly:
                diameter_param2.Set(pipe_diameter)
                log_info(f"  Set diameter via LookupParameter to {pipe_diameter:.4f} ft")
            else:
                log_info(f"  Could not set diameter - parameter is read-only or not found")

        log_info(f"  Created pipe Id: {pipe.Id.IntegerValue}")
        return pipe

    except Exception as e:
        log_warning(f"Failed to create pipe segment: {e}")
        log_info(f"  Segment: {segment.start_point} -> {segment.end_point}")
        log_info(f"  IDs: system={system_type_id.IntegerValue}, pipe={pipe_type_id.IntegerValue}, level={level_id.IntegerValue}")
        return None


def create_elbow_fitting(doc, pipe1, pipe2):
    """Create elbow fitting between two pipes.

    Args:
        doc: Revit document
        pipe1: First pipe (get end connector)
        pipe2: Second pipe (get start connector)

    Returns:
        Fitting element or None

    Note:
        Tries multiple approaches:
        1. NewElbowFitting - requires fitting families loaded
        2. Connector.ConnectTo - may auto-insert fittings
    """
    try:
        conn1 = get_pipe_end_connector(pipe1, at_end=True)
        conn2 = get_pipe_end_connector(pipe2, at_end=False)

        if conn1 is None or conn2 is None:
            log_info(f"  Elbow: Could not find connectors (conn1={conn1}, conn2={conn2})")
            return None

        # Check if connectors are already connected
        if conn1.IsConnected:
            log_info(f"  Elbow: conn1 already connected")
            return None
        if conn2.IsConnected:
            log_info(f"  Elbow: conn2 already connected")
            return None

        # Log connector info for debugging
        dist = conn1.Origin.DistanceTo(conn2.Origin)
        log_info(f"  Elbow: Pipes {pipe1.Id.IntegerValue} -> {pipe2.Id.IntegerValue}, dist={dist:.4f}")

        # Try Method 1: NewElbowFitting
        try:
            fitting = doc.Create.NewElbowFitting(conn1, conn2)
            if fitting is not None:
                log_info(f"  Elbow: Created fitting Id {fitting.Id.IntegerValue}")
                return fitting
        except Exception as e1:
            log_info(f"  Elbow: NewElbowFitting failed - {e1}")

        # Try Method 2: Direct connector connection
        # This may auto-insert a fitting if routing preferences allow
        try:
            conn1.ConnectTo(conn2)
            if conn1.IsConnected:
                log_info(f"  Elbow: Connected via ConnectTo (fitting may be auto-inserted)")
                return "connected"  # Return non-None to indicate success
        except Exception as e2:
            log_info(f"  Elbow: ConnectTo failed - {e2}")

        return None

    except Exception as e:
        log_info(f"  Elbow: FAILED - {e}")
        return None


def create_tee_fitting(doc, branch_pipe, trunk_pipe, merge_point, all_trunk_pipes=None):
    """Connect branch pipe to trunk at merge point.

    Args:
        doc: Revit document
        branch_pipe: Branch pipe connecting to trunk
        trunk_pipe: First trunk pipe (merge point is at its start)
        merge_point: (x, y, z) tuple where branch meets trunk
        all_trunk_pipes: List of all trunk pipes (to find connectors)

    Returns:
        Fitting element, "connected" string, or None

    Note:
        The merge point is at the START of the trunk pipes (not middle).
        Multiple branches may connect to the same point - we need to find
        any available connector near the merge point.
    """
    try:
        # Get end connector of branch (the end that meets the trunk)
        branch_conn = get_pipe_end_connector(branch_pipe, at_end=True)

        if branch_conn is None:
            log_info(f"  Tee: Could not find branch connector")
            return None

        if branch_conn.IsConnected:
            log_info(f"  Tee: Branch connector already connected")
            return None

        merge_xyz = XYZ(merge_point[0], merge_point[1], merge_point[2])
        log_info(f"  Tee: Branch {branch_pipe.Id.IntegerValue} seeking connection at ({merge_point[0]:.2f}, {merge_point[1]:.2f}, {merge_point[2]:.2f})")

        # Collect all pipes to search for connectors
        pipes_to_check = [trunk_pipe]
        if all_trunk_pipes:
            pipes_to_check = list(all_trunk_pipes)

        # Find any unconnected connector near the merge point
        best_conn = None
        best_dist = float('inf')

        for pipe in pipes_to_check:
            if pipe is None:
                continue
            try:
                for conn in pipe.ConnectorManager.Connectors:
                    if not conn.IsConnected:
                        dist = conn.Origin.DistanceTo(branch_conn.Origin)
                        if dist < best_dist:
                            best_dist = dist
                            best_conn = conn
            except:
                pass

        if best_conn is not None and best_dist < 0.1:  # Within 0.1 ft tolerance
            try:
                branch_conn.ConnectTo(best_conn)
                if branch_conn.IsConnected:
                    log_info(f"  Tee: Connected branch to trunk (dist={best_dist:.4f})")
                    return "connected"
            except Exception as e_connect:
                log_info(f"  Tee: ConnectTo failed - {e_connect}")

        # If no direct connection possible, the user needs to manually add fitting
        # This happens when multiple branches meet at one point (need a cross/wye)
        if best_dist >= 0.1:
            log_info(f"  Tee: No connector found near merge point (closest={best_dist:.2f}ft)")
        else:
            log_info(f"  Tee: Could not connect - connector may already be used")
            log_info(f"  Tee: Note: Multiple branches at same point need manual wye/cross fitting")

        return None

    except Exception as e:
        log_info(f"  Tee: FAILED - {e}")
        return None


def create_wye_fitting(doc, all_branch_pipes, trunk_pipes, merge_info):
    """Create wye fitting connecting branches to trunk at merge point.

    Uses Revit's NewTeeFitting(conn1, conn2, conn3) which requires 3 connectors
    from 3 different pipe elements. The trimmed pipe ends provide these connectors.

    For 2 branches:
        - conn1: End of branch 1 (becomes "run in")
        - conn2: Start of trunk (becomes "run out")
        - conn3: End of branch 2 (becomes "branch")

    Args:
        doc: Revit document
        all_branch_pipes: List of lists of branch pipes [[branch1_pipes], [branch2_pipes], ...]
        trunk_pipes: List of trunk pipe elements
        merge_info: MergePointInfo with trimmed coordinates

    Returns:
        Fitting element, "connected" string, or None
    """
    if len(all_branch_pipes) < 2:
        log_info("  Wye: Need at least 2 branches")
        return None

    if not trunk_pipes:
        log_info("  Wye: No trunk pipes available")
        return None

    # Get the last pipe of each branch (these have ends near merge point)
    branch1_pipes = all_branch_pipes[0] if all_branch_pipes[0] else []
    branch2_pipes = all_branch_pipes[1] if len(all_branch_pipes) > 1 and all_branch_pipes[1] else []

    if not branch1_pipes or not branch2_pipes:
        log_info("  Wye: One or both branches have no pipes")
        return None

    branch1_last = branch1_pipes[-1]
    branch2_last = branch2_pipes[-1]
    trunk_first = trunk_pipes[0]

    log_info(f"  Wye: Connecting branch1={branch1_last.Id.IntegerValue}, branch2={branch2_last.Id.IntegerValue}, trunk={trunk_first.Id.IntegerValue}")

    # Get connectors (end of branches, start of trunk)
    branch1_conn = get_pipe_end_connector(branch1_last, at_end=True)
    branch2_conn = get_pipe_end_connector(branch2_last, at_end=True)
    trunk_conn = get_pipe_end_connector(trunk_first, at_end=False)  # START of trunk

    # Validate all connectors exist
    if branch1_conn is None:
        log_info("  Wye: Branch 1 end connector not found")
        return None
    if branch2_conn is None:
        log_info("  Wye: Branch 2 end connector not found")
        return None
    if trunk_conn is None:
        log_info("  Wye: Trunk start connector not found")
        return None

    # Check if connectors are already connected
    if branch1_conn.IsConnected:
        log_info("  Wye: Branch 1 connector already connected")
        return None
    if branch2_conn.IsConnected:
        log_info("  Wye: Branch 2 connector already connected")
        return None
    if trunk_conn.IsConnected:
        log_info("  Wye: Trunk connector already connected")
        return None

    # Log connector positions for debugging
    log_info(f"  Wye: Branch1 conn at ({branch1_conn.Origin.X:.3f}, {branch1_conn.Origin.Y:.3f}, {branch1_conn.Origin.Z:.3f})")
    log_info(f"  Wye: Branch2 conn at ({branch2_conn.Origin.X:.3f}, {branch2_conn.Origin.Y:.3f}, {branch2_conn.Origin.Z:.3f})")
    log_info(f"  Wye: Trunk conn at ({trunk_conn.Origin.X:.3f}, {trunk_conn.Origin.Y:.3f}, {trunk_conn.Origin.Z:.3f})")

    # For NewTeeFitting: conn1 and conn2 form the "run" (straight through), conn3 is the "branch"
    # Based on geometry: Branch1 (left) → Branch2 (right) = horizontal run, Trunk = perpendicular branch

    # Try Method 1: Branch1-Branch2 as run, Trunk as branch (most likely correct for this geometry)
    try:
        fitting = doc.Create.NewTeeFitting(branch1_conn, branch2_conn, trunk_conn)
        if fitting is not None:
            log_info(f"  Wye: Created tee fitting (b1-b2 run, trunk branch) Id {fitting.Id.IntegerValue}")
            return fitting
    except Exception as e1:
        log_info(f"  Wye: NewTeeFitting(b1, b2, trunk) failed - {e1}")

    # Try Method 2: Reverse the run direction
    try:
        fitting = doc.Create.NewTeeFitting(branch2_conn, branch1_conn, trunk_conn)
        if fitting is not None:
            log_info(f"  Wye: Created tee fitting (b2-b1 run, trunk branch) Id {fitting.Id.IntegerValue}")
            return fitting
    except Exception as e2:
        log_info(f"  Wye: NewTeeFitting(b2, b1, trunk) failed - {e2}")

    # Try Method 3: Trunk as part of run (less likely but worth trying)
    try:
        fitting = doc.Create.NewTeeFitting(branch1_conn, trunk_conn, branch2_conn)
        if fitting is not None:
            log_info(f"  Wye: Created tee fitting (b1-trunk run) Id {fitting.Id.IntegerValue}")
            return fitting
    except Exception as e3:
        log_info(f"  Wye: NewTeeFitting(b1, trunk, b2) failed - {e3}")

    # Try Method 4: Other combinations
    try:
        fitting = doc.Create.NewTeeFitting(trunk_conn, branch1_conn, branch2_conn)
        if fitting is not None:
            log_info(f"  Wye: Created tee fitting (trunk-b1 run) Id {fitting.Id.IntegerValue}")
            return fitting
    except Exception as e4:
        log_info(f"  Wye: NewTeeFitting(trunk, b1, b2) failed - {e4}")

    log_info("  Wye: All NewTeeFitting attempts failed - connectors may need to be at exact same point")

    # Fallback: Connect branches directly to trunk
    # When ConnectTo is used, Revit may auto-insert fittings based on routing preferences
    log_info("  Wye: All NewTeeFitting attempts failed, trying direct connections")
    connected_count = 0

    # Connect branch1 to trunk
    try:
        branch1_conn.ConnectTo(trunk_conn)
        if branch1_conn.IsConnected:
            log_info("  Wye: Connected branch1 to trunk via ConnectTo")
            connected_count += 1
    except Exception as e:
        log_info(f"  Wye: branch1→trunk ConnectTo failed - {e}")

    # Try to connect branch2 - need to find an available connector
    # IMPORTANT: After ConnectTo, Revit may have modified the document, invalidating connector references.
    # We need to re-fetch branch2's connector to get a fresh reference.
    if connected_count > 0:
        # Re-fetch branch2 connector (original may be stale after document modification)
        try:
            branch2_conn = get_pipe_end_connector(branch2_last, at_end=True)
            if branch2_conn is None:
                log_info("  Wye: Could not re-fetch branch2 connector")
            elif branch2_conn.IsConnected:
                log_info("  Wye: branch2 already connected")
                connected_count += 1
        except Exception as e:
            log_info(f"  Wye: Error re-fetching branch2 connector - {e}")
            branch2_conn = None

    if connected_count > 0 and branch2_conn is not None and not branch2_conn.IsConnected:
        fitting_found = False

        # Re-fetch branch1 connector too (needed to access AllRefs after document modification)
        try:
            branch1_conn = get_pipe_end_connector(branch1_last, at_end=True)
        except Exception as e:
            log_info(f"  Wye: Error re-fetching branch1 connector - {e}")
            branch1_conn = None

        # Strategy 1: Find the fitting that branch1 is now connected to
        if branch1_conn is not None:
            try:
                log_info("  Wye: Looking for fitting connected to branch1...")
                for ref in branch1_conn.AllRefs:
                    if ref is None:
                        continue
                    owner = ref.Owner
                    if owner is None:
                        continue

                    # Check if this is a fitting (has MEPModel)
                    owner_type = owner.GetType().Name
                    log_info(f"  Wye: branch1 connected to {owner_type} Id={owner.Id.IntegerValue}")

                    if hasattr(owner, 'MEPModel') and owner.MEPModel is not None:
                        # This is a fitting - find available connectors
                        try:
                            fitting_connectors = owner.MEPModel.ConnectorManager.Connectors
                            log_info(f"  Wye: Fitting has {fitting_connectors.Size} connectors")

                            for fc in fitting_connectors:
                                try:
                                    if not fc.IsConnected:
                                        log_info(f"  Wye: Found unconnected fitting connector, attempting branch2 connection...")
                                        branch2_conn.ConnectTo(fc)
                                        if branch2_conn.IsConnected:
                                            log_info(f"  Wye: Connected branch2 to fitting {owner.Id.IntegerValue}")
                                            connected_count += 1
                                            fitting_found = True
                                            break
                                except Exception as fc_err:
                                    log_info(f"  Wye: Fitting connector error - {fc_err}")
                        except Exception as mep_err:
                            log_info(f"  Wye: MEPModel access error - {mep_err}")

                    if fitting_found:
                        break
            except Exception as e:
                log_info(f"  Wye: Strategy 1 (fitting search) failed - {e}")

        # Strategy 2: If no fitting found, try using PlumbingUtils to break the pipe
        # and insert a tee (this requires the trunk pipe to still be valid)
        if not fitting_found and connected_count < 2:
            log_info("  Wye: No fitting connector found for branch2")
            # At this point, branch1 is connected but branch2 isn't.
            # The user will need to manually add a cross fitting or adjust the connection.

    if connected_count >= 2:
        log_info(f"  Wye: Successfully connected {connected_count} branches")
        return "connected"
    elif connected_count == 1:
        log_info("  Wye: Only 1 branch connected - second branch needs manual connection")
        return "partial"

    log_info("  Wye: All connection attempts failed - manual wye/cross fitting needed")
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
        debug.append(f"Attempting {len(trunk_pipes)-1} trunk elbows...")
        for i in range(len(trunk_pipes) - 1):
            try:
                fitting = create_elbow_fitting(doc, trunk_pipes[i], trunk_pipes[i+1])
                if fitting is not None:
                    fittings.append(fitting)
            except Exception as e:
                debug.append(f"  Trunk elbow {i} failed: {e}")

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
            debug.append(f"  Attempting {len(branch_pipes)-1} branch elbows...")
            for i in range(len(branch_pipes) - 1):
                try:
                    fitting = create_elbow_fitting(doc, branch_pipes[i], branch_pipes[i+1])
                    if fitting is not None:
                        fittings.append(fitting)
                except Exception as e:
                    debug.append(f"    Branch elbow {i} failed: {e}")

    # Debug: Show merge info state
    log_info(f"Merge point check: merge_point={network.merge_point is not None}, merge_info={network.merge_info is not None}")
    log_info(f"  branches={len(all_branch_pipes)}, trunk_pipes={len(trunk_pipes)}")
    if network.merge_info:
        log_info(f"  merge_info.branch_endpoints={len(network.merge_info.branch_endpoints)}")
    else:
        log_info(f"  merge_info is None - will use legacy fallback")

    # Create wye fitting at merge point (for 2+ branches with merge_info)
    if do_fittings and network.merge_info is not None and len(all_branch_pipes) >= 2 and len(trunk_pipes) > 0:
        merge_info = network.merge_info
        debug.append(f"Creating wye fitting at merge point")
        debug.append(f"  Original merge: {merge_info.original_point}")
        debug.append(f"  Trimmed trunk start: {merge_info.trunk_startpoint}")
        debug.append(f"  {len(merge_info.branch_endpoints)} branch endpoints trimmed")

        try:
            fitting = create_wye_fitting(doc, all_branch_pipes, trunk_pipes, merge_info)
            if fitting is not None:
                fittings.append(fitting)
                debug.append("  Wye fitting created successfully")
            else:
                debug.append("  Wye fitting failed - manual connection needed")
        except Exception as e:
            debug.append(f"  Wye fitting error: {e}")

    # For single branch, use simple tee fitting at merge point
    elif do_fittings and network.needs_tee_fitting() and len(trunk_pipes) > 0 and len(all_branch_pipes) == 1:
        merge_point = network.merge_point
        debug.append(f"Attempting single branch tee fitting at: {merge_point}")
        first_trunk_pipe = trunk_pipes[0]
        branch_pipes_list = all_branch_pipes[0]
        if len(branch_pipes_list) > 0:
            try:
                last_branch_pipe = branch_pipes_list[-1]
                fitting = create_tee_fitting(doc, last_branch_pipe, first_trunk_pipe, merge_point, trunk_pipes)
                if fitting is not None:
                    fittings.append(fitting)
                    debug.append("  Connected branch to trunk")
                else:
                    debug.append("  Branch: Manual connection needed")
            except Exception as e:
                debug.append(f"  Tee fitting failed: {e}")

    # Fallback for merge point without merge_info (shouldn't happen with new code)
    elif do_fittings and network.merge_point is not None and len(all_branch_pipes) >= 2 and len(trunk_pipes) > 0:
        merge_point = network.merge_point
        debug.append(f"Attempting tee fittings at merge point (legacy): {merge_point}")
        debug.append(f"  {len(all_branch_pipes)} branches need to connect to trunk")
        first_trunk_pipe = trunk_pipes[0]
        for bi, branch_pipes_list in enumerate(all_branch_pipes):
            if len(branch_pipes_list) > 0:
                try:
                    last_branch_pipe = branch_pipes_list[-1]
                    fitting = create_tee_fitting(doc, last_branch_pipe, first_trunk_pipe, merge_point, trunk_pipes)
                    if fitting is not None:
                        fittings.append(fitting)
                        debug.append(f"  Connected branch {bi} to trunk")
                    else:
                        debug.append(f"  Branch {bi}: Manual connection needed (wye/cross fitting)")
                except Exception as e:
                    debug.append(f"  Tee fitting for branch {bi} failed: {e}")

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

    # pipe_type is optional - will use first available if not provided

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

        # Show available pipe types for debugging
        available_pipe_types = get_available_pipe_types(doc)
        debug_lines.append("")
        debug_lines.append(f"Available PipeTypes in document: {len(available_pipe_types)}")
        for pt_name, pt_id in available_pipe_types:
            debug_lines.append(f"  - {pt_name} (Id: {pt_id.IntegerValue})")

        # Validate pipe type input
        pipe_type_name = "Unknown"
        if pipe_type is not None:
            is_valid_type, type_error, pipe_type_id = validate_pipe_type(doc, pipe_type)
            if not is_valid_type:
                debug_lines.append("")
                debug_lines.append(f"ERROR: Invalid pipe_type input")
                debug_lines.append(type_error)
                log_error(type_error)
                return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)
            pipe_type_name = pipe_type.Name
        else:
            # No pipe_type provided - use first available
            if len(available_pipe_types) > 0:
                pipe_type_name, pipe_type_id = available_pipe_types[0]
                debug_lines.append("")
                debug_lines.append(f"No pipe_type input - using first available: {pipe_type_name}")
            else:
                debug_lines.append("")
                debug_lines.append("ERROR: No pipe_type provided and no PipeTypes found in document")
                return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

        level_id = level.Id

        debug_lines.append("")
        debug_lines.append(f"Using Pipe Type: {pipe_type_name} (Id: {pipe_type_id.IntegerValue})")
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
        debug_lines.append(f"Fittings enabled: {create_fittings}")

        t = Transaction(doc, "Create Plumbing Pipes")
        t.Start()

        networks_succeeded = 0
        networks_failed = 0

        try:
            # Process each network with individual error handling
            for network in networks:
                debug_lines.append("")
                debug_lines.append(f"Network: Fixture {network.fixture_id} - {network.system_type}")

                try:
                    pipes, fittings, net_debug = create_pipes_from_network(
                        doc, network, pipe_type_id, level_id, create_fittings
                    )

                    created_pipes.extend(pipes)
                    created_fittings.extend(fittings)
                    debug_lines.extend(net_debug)

                    if len(pipes) > 0:
                        networks_succeeded += 1
                    else:
                        networks_failed += 1
                        debug_lines.append("  No pipes created for this network")

                except Exception as net_error:
                    networks_failed += 1
                    debug_lines.append(f"  ERROR processing network: {net_error}")
                    log_warning(f"Network {network.fixture_id} {network.system_type} failed: {net_error}")
                    # Continue with other networks

            # Only commit if we created something
            if len(created_pipes) > 0:
                t.Commit()
                debug_lines.append("")
                debug_lines.append("Transaction committed successfully")
            else:
                t.RollBack()
                debug_lines.append("")
                debug_lines.append("Transaction rolled back - no pipes created")

        except Exception as e:
            if t.HasStarted():
                t.RollBack()
            debug_lines.append(f"ERROR: Transaction rolled back: {e}")
            debug_lines.append(traceback.format_exc())
            return created_pipes, created_fittings, creation_json, "\n".join(debug_lines)

        debug_lines.append(f"Networks succeeded: {networks_succeeded}")
        debug_lines.append(f"Networks failed: {networks_failed}")

        # Build output JSON
        # Filter out string placeholders from fittings (ConnectTo returns "connected" not an element)
        actual_fittings = [f for f in created_fittings if hasattr(f, 'Id')]
        output_data = {
            "pipes_created": len(created_pipes),
            "fittings_created": len(actual_fittings),
            "connections_made": len(created_fittings) - len(actual_fittings),
            "pipe_ids": [p.Id.IntegerValue for p in created_pipes],
            "fitting_ids": [f.Id.IntegerValue for f in actual_fittings],
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
    create_fittings = False  # Disabled by default - can cause Revit crashes

# Execute main and assign to output variables
created_pipes, created_fittings, creation_json, debug_info = main()
