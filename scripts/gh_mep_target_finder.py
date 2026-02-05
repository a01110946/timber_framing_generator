# File: scripts/gh_mep_target_finder.py
"""MEP Target Finder for Grasshopper.

Finds and ranks routing target candidates for MEP connectors using
system-specific heuristics. Part of the OAHS (Obstacle-Aware Hanan Sequential)
MEP routing pipeline.

Key Features:
1. Target Generation
   - Generates targets from wall geometry (wet walls, penetration zones)
   - Detects wet walls from plumbing fixture density
   - Creates floor penetration targets for island fixtures

2. Heuristic-Based Ranking
   - System-specific heuristics (Sanitary, Vent, Supply, Power, Data)
   - Considers distance, priority, and system constraints
   - Gravity-aware routing for drains

3. Visualization
   - Target points for Rhino preview
   - Candidate lines from connectors to targets
   - Color-coded by system type

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)
    Rhino.Inside.Revit (optional - for Revit connector extraction)

Dependencies:
    - Rhino.Geometry: Core geometry types
    - Grasshopper: DataTree for output organization
    - timber_framing_generator.mep.routing: Target generator and heuristics

Performance Considerations:
    - Processing time scales with number of connectors and targets
    - Typical fixture finds candidates in < 10ms
    - Wet wall detection adds overhead proportional to wall count

Usage:
    1. Connect MEP connectors JSON to 'connectors_json' input
    2. Connect walls JSON to 'walls_json' input
    3. Optionally provide pre-generated targets
    4. Set 'run' to True to execute
    5. Connect 'targets_json' to downstream routing components

Input Requirements:
    Connectors JSON (connectors_json) - str:
        JSON string with MEP connector data
        Required: Yes
        Access: Item

    Walls JSON (walls_json) - str:
        JSON string with wall geometry data
        Required: Yes
        Access: Item

    Targets JSON (targets_json) - str:
        Optional pre-generated targets
        Required: No
        Access: Item

    Config (config) - str:
        Optional configuration JSON
        Required: No
        Access: Item

    Run (run) - bool:
        Boolean to trigger execution
        Required: Yes
        Access: Item

Outputs:
    Targets JSON (targets_out) - str:
        JSON with targets and ranked candidates per connector

    Target Points (target_points) - DataTree[Point3d]:
        Target locations for visualization

    Candidate Lines (candidate_lines) - DataTree[Line]:
        Lines from connectors to candidate targets

    Debug Info (debug_info) - str:
        Debug information and status messages

Technical Details:
    - Uses pluggable heuristics for each MEP system type
    - Sanitary heuristic enforces gravity (downward only)
    - Wet wall detection based on fixture density
    - Supports custom heuristic registration

Error Handling:
    - Invalid JSON returns error in debug_info
    - Missing connectors logged but doesn't halt
    - Unknown system types use fallback heuristic

Author: Timber Framing Generator
Version: 1.0.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import sys
import json
import traceback

# .NET / CLR
import clr
clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

# Rhino / Grasshopper
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# =============================================================================
# Force Module Reload (CPython 3 in Rhino 8)
# =============================================================================

_modules_to_clear = [k for k in sys.modules.keys() if 'timber_framing_generator' in k]
for mod in _modules_to_clear:
    del sys.modules[mod]

# =============================================================================
# Project Setup
# =============================================================================

PROJECT_PATH = r"C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

from src.timber_framing_generator.mep.routing import (
    TargetCandidateGenerator,
    ConnectorInfo,
    RoutingTarget,
    TargetType,
    RoutingDomain,
    RoutingDomainType,
    detect_wet_walls,
    generate_targets_from_walls,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Target Finder"
COMPONENT_NICKNAME = "MEPTargets"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "Timber Framing"
COMPONENT_SUBCATEGORY = "MEP Routing"

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


def log_debug(message):
    """Log debug message (console only)."""
    print(f"[DEBUG] {message}")


def log_info(message):
    """Log info message (console only)."""
    print(f"[INFO] {message}")


def log_warning(message):
    """Log warning message (console + GH UI)."""
    log_message(message, "warning")


def log_error(message):
    """Log error message (console + GH UI)."""
    log_message(message, "error")

# =============================================================================
# Component Setup
# =============================================================================

def setup_component():
    """Initialize and configure the Grasshopper component.

    Configures:
    1. Component metadata (name, category, etc.)
    2. Input parameter names, descriptions, and access
    3. Output parameter names and descriptions

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1]

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type
    """
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Connectors JSON", "connectors_json", "JSON string with MEP connector data",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Walls JSON", "walls_json", "JSON string with wall geometry data",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Targets JSON", "targets_json", "Optional pre-generated targets JSON",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Config", "config", "Optional configuration JSON",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run", "Boolean to trigger execution",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (start from index 1)
    outputs = ghenv.Component.Params.Output
    output_config = [
        ("Targets JSON", "targets_out", "JSON with targets and candidates"),
        ("Target Points", "target_points", "Target locations for visualization"),
        ("Candidate Lines", "candidate_lines", "Lines to candidate targets"),
        ("Debug Info", "debug_info", "Debug information and status"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1
        if idx < outputs.Count:
            outputs[idx].Name = name
            outputs[idx].NickName = nick
            outputs[idx].Description = desc

# =============================================================================
# Helper Functions
# =============================================================================

def validate_inputs(connectors_json, walls_json, run):
    """Validate component inputs.

    Args:
        connectors_json: JSON string with connector data
        walls_json: JSON string with wall data
        run: Boolean trigger

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run:
        return False, "Component not running. Set 'run' to True."

    if not connectors_json:
        return False, "No connectors JSON provided"

    if not walls_json:
        return False, "No walls JSON provided"

    return True, None


def parse_connectors(connectors_json):
    """Parse connector data from JSON.

    Args:
        connectors_json: JSON string with connector data

    Returns:
        list: List of ConnectorInfo objects
    """
    data = json.loads(connectors_json)

    # Handle both list format and dict with 'connectors' key
    if isinstance(data, list):
        connector_list = data
    elif isinstance(data, dict) and "connectors" in data:
        connector_list = data["connectors"]
    else:
        connector_list = [data]  # Single connector

    connectors = []
    for item in connector_list:
        try:
            connector = ConnectorInfo.from_dict(item)
            connectors.append(connector)
        except Exception as e:
            log_warning(f"Failed to parse connector: {e}")

    return connectors


def parse_walls(walls_json):
    """Parse wall data from JSON.

    Args:
        walls_json: JSON string with wall data

    Returns:
        list: List of wall data dictionaries
    """
    data = json.loads(walls_json)

    # Handle both list format and dict with 'walls' key
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "walls" in data:
        return data["walls"]
    else:
        return [data]


def parse_targets(targets_json):
    """Parse pre-generated targets from JSON.

    Args:
        targets_json: JSON string with target data

    Returns:
        list: List of RoutingTarget objects
    """
    if not targets_json:
        return []

    data = json.loads(targets_json)

    # Handle both list format and dict with 'targets' key
    if isinstance(data, list):
        target_list = data
    elif isinstance(data, dict) and "targets" in data:
        target_list = data["targets"]
    else:
        target_list = [data]

    targets = []
    for item in target_list:
        try:
            target = RoutingTarget.from_dict(item)
            targets.append(target)
        except Exception as e:
            log_warning(f"Failed to parse target: {e}")

    return targets


def create_visualization_geometry(targets, connectors, candidates_by_connector):
    """Create visualization geometry for Rhino preview.

    Args:
        targets: List of RoutingTarget objects
        connectors: List of ConnectorInfo objects
        candidates_by_connector: Dict mapping connector ID to candidates

    Returns:
        tuple: (target_points DataTree, candidate_lines DataTree)
    """
    factory = get_factory()

    target_points = DataTree[object]()
    candidate_lines = DataTree[object]()

    # Create target points
    for i, target in enumerate(targets):
        path = GH_Path(i)
        pt = factory.create_point3d(
            target.location[0],
            target.location[1],
            target.location[2]
        )
        target_points.Add(pt, path)

    # Create lines from connectors to candidates
    for j, connector in enumerate(connectors):
        path = GH_Path(j)
        candidates = candidates_by_connector.get(connector.id, [])

        conn_pt = factory.create_point3d(
            connector.location[0],
            connector.location[1],
            connector.location[2]
        )

        for candidate in candidates[:3]:  # Top 3 candidates
            tgt_pt = factory.create_point3d(
                candidate.target.location[0],
                candidate.target.location[1],
                candidate.target.location[2]
            )
            line = factory.create_line(conn_pt, tgt_pt)
            candidate_lines.Add(line, path)

    return target_points, candidate_lines


def build_output_json(targets, connectors, candidates_by_connector, wet_walls):
    """Build output JSON with targets and candidates.

    Args:
        targets: List of RoutingTarget objects
        connectors: List of ConnectorInfo objects
        candidates_by_connector: Dict mapping connector ID to candidates
        wet_walls: List of detected wet walls

    Returns:
        str: JSON string with complete output
    """
    output = {
        "targets": [t.to_dict() for t in targets],
        "wet_walls": [
            {
                "wall_id": ww.wall_id,
                "fixture_count": ww.fixture_count,
                "score": ww.score,
                "is_back_to_back": ww.is_back_to_back
            }
            for ww in wet_walls
        ],
        "candidates": {}
    }

    for connector_id, candidates in candidates_by_connector.items():
        output["candidates"][connector_id] = [
            {
                "target_id": c.target.id,
                "score": c.score,
                "distance": c.distance,
                "routing_domain": c.routing_domain,
                "requires_floor_routing": c.requires_floor_routing,
                "notes": c.notes
            }
            for c in candidates
        ]

    return json.dumps(output, indent=2)


# =============================================================================
# Main Processing
# =============================================================================

def main(connectors_json, walls_json, targets_json, config):
    """Main processing function.

    Args:
        connectors_json: JSON string with connector data
        walls_json: JSON string with wall data
        targets_json: Optional pre-generated targets
        config: Optional configuration

    Returns:
        tuple: (targets_out, target_points, candidate_lines, debug_info)
    """
    debug_lines = []
    debug_lines.append("=== MEP Target Finder ===")

    try:
        # Parse inputs
        connectors = parse_connectors(connectors_json)
        debug_lines.append(f"Parsed {len(connectors)} connectors")

        walls = parse_walls(walls_json)
        debug_lines.append(f"Parsed {len(walls)} walls")

        # Create generator
        generator = TargetCandidateGenerator()

        # Generate or load targets
        if targets_json:
            targets = parse_targets(targets_json)
            debug_lines.append(f"Loaded {len(targets)} pre-generated targets")
        else:
            targets = generate_targets_from_walls(walls, connectors)
            debug_lines.append(f"Generated {len(targets)} targets from walls")

        generator.add_targets(targets)

        # Detect wet walls for info
        wet_walls = detect_wet_walls(walls, connectors)
        debug_lines.append(f"Detected {len(wet_walls)} wet walls")

        for ww in wet_walls[:3]:  # Show top 3
            debug_lines.append(f"  - {ww.wall_id}: {ww.fixture_count} fixtures, score={ww.score:.1f}")

        # Find candidates for each connector
        candidates_by_connector = generator.find_all_candidates(connectors, max_candidates_per_connector=5)

        total_candidates = sum(len(c) for c in candidates_by_connector.values())
        debug_lines.append(f"Found {total_candidates} total candidates")

        # Log system breakdown
        system_counts = {}
        for conn in connectors:
            system_counts[conn.system_type] = system_counts.get(conn.system_type, 0) + 1

        debug_lines.append("Connectors by system:")
        for sys_type, count in sorted(system_counts.items()):
            debug_lines.append(f"  - {sys_type}: {count}")

        # Create visualization
        target_points, candidate_lines = create_visualization_geometry(
            targets, connectors, candidates_by_connector
        )

        # Build output JSON
        targets_out = build_output_json(targets, connectors, candidates_by_connector, wet_walls)

        debug_lines.append("=== Complete ===")
        debug_info = "\n".join(debug_lines)

        return targets_out, target_points, candidate_lines, debug_info

    except Exception as e:
        error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
        log_error(str(e))
        return None, DataTree[object](), DataTree[object](), error_msg


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    # Setup component on first run
    setup_component()

    # Validate inputs
    is_valid, error_msg = validate_inputs(connectors_json, walls_json, run)

    if not is_valid:
        targets_out = None
        target_points = DataTree[object]()
        candidate_lines = DataTree[object]()
        debug_info = error_msg
        log_info(error_msg)
    else:
        # Run main processing
        targets_out, target_points, candidate_lines, debug_info = main(
            connectors_json, walls_json, targets_json, config
        )
