# File: scripts/gh_mep_graph_builder.py
"""MEP Graph Builder for Grasshopper.

Builds multi-domain routing graphs from wall and floor geometry for
MEP routing. Part of the OAHS (Obstacle-Aware Hanan Sequential)
MEP routing pipeline.

Key Features:
1. Wall Graph Construction
   - Creates 2D grid graphs in UV (wall) space
   - Marks stud obstacles with penetration costs
   - Handles plate zones (blocked routing)

2. Floor Graph Construction
   - Creates 2D grid graphs in XY space
   - Marks joist obstacles
   - Supports web opening zones

3. Transition Generation
   - Wall-to-floor transitions at base plates
   - Wall-to-wall transitions at corners
   - Cross-domain path support

4. Visualization
   - Node points for Rhino preview
   - Edge lines showing routing channels
   - Transition edges highlighted

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - networkx: Graph operations
    - Rhino.Geometry: Core geometry types
    - Grasshopper: DataTree for output
    - timber_framing_generator.mep.routing: Graph builders

Usage:
    1. Connect walls JSON to 'walls_json' input
    2. Optionally connect connectors and targets
    3. Set 'run' to True to execute
    4. Use output for debugging or downstream routing

Input Requirements:
    Walls JSON (walls_json) - str:
        JSON string with wall geometry data
        Required: Yes
        Access: Item

    Connectors JSON (connectors_json) - str:
        Optional JSON with MEP connectors
        Required: No
        Access: Item

    Targets JSON (targets_json) - str:
        Optional JSON with routing targets
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
    Graph JSON (graph_json) - str:
        Serialized graph for debugging

    Node Points (node_points) - DataTree[Point3d]:
        Graph nodes for visualization

    Edge Lines (edge_lines) - DataTree[Line]:
        Graph edges for visualization

    Transition Lines (transition_lines) - DataTree[Line]:
        Cross-domain transitions (highlighted)

    Debug Info (debug_info) - str:
        Statistics and debug information

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
    build_routing_graph,
    UnifiedGraphBuilder,
    MultiDomainGraph,
)
from src.timber_framing_generator.utils.geometry_factory import get_factory

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "MEP Graph Builder"
COMPONENT_NICKNAME = "MEPGraph"
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
    print(f"[DEBUG] {message}")


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
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    inputs = ghenv.Component.Params.Input
    input_config = [
        ("Walls JSON", "walls_json", "JSON string with wall geometry data",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Connectors JSON", "connectors_json", "Optional MEP connectors JSON",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Targets JSON", "targets_json", "Optional routing targets JSON",
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
        ("Graph JSON", "graph_json", "Serialized graph for debugging"),
        ("Node Points", "node_points", "Graph nodes for visualization"),
        ("Edge Lines", "edge_lines", "Graph edges for visualization"),
        ("Transition Lines", "transition_lines", "Cross-domain transitions"),
        ("Debug Info", "debug_info", "Statistics and debug info"),
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

def validate_inputs(walls_json, run):
    """Validate component inputs."""
    if not run:
        return False, "Component not running. Set 'run' to True."
    if not walls_json:
        return False, "No walls JSON provided"
    return True, None


def parse_config(config_json):
    """Parse configuration options."""
    default_config = {
        "wall_resolution": 0.5,
        "floor_resolution": 1.0,
        "show_all_edges": False
    }

    if not config_json:
        return default_config

    try:
        user_config = json.loads(config_json)
        default_config.update(user_config)
    except Exception:
        pass

    return default_config


def create_visualization_geometry(mdg: MultiDomainGraph, walls_data):
    """Create visualization geometry for Rhino preview."""
    factory = get_factory()

    node_points = DataTree[object]()
    edge_lines = DataTree[object]()
    transition_lines = DataTree[object]()

    if not mdg.unified_graph:
        return node_points, edge_lines, transition_lines

    # Build wall position lookup
    wall_positions = {}
    for wall in walls_data:
        wall_id = wall.get('id') or wall.get('wall_id')
        if wall_id and 'start' in wall:
            start = wall['start']
            end = wall.get('end', start)
            wall_positions[wall_id] = {
                'start': start,
                'end': end
            }

    # Create node points
    domain_idx = 0
    for domain_id, domain in mdg.domains.items():
        path = GH_Path(domain_idx)

        # Get nodes for this domain
        for node, data in mdg.unified_graph.nodes(data=True):
            if data.get('domain_id') != domain_id:
                continue

            loc = data.get('location', (0, 0))

            # Convert to world coordinates
            world_pt = _convert_to_world(
                loc, domain_id, domain, wall_positions
            )

            if world_pt:
                pt = factory.create_point3d(world_pt[0], world_pt[1], world_pt[2])
                node_points.Add(pt, path)

        domain_idx += 1

    # Create edge lines
    edge_idx = 0
    for u, v, data in mdg.unified_graph.edges(data=True):
        is_transition = data.get('is_transition', False)

        u_data = mdg.unified_graph.nodes[u]
        v_data = mdg.unified_graph.nodes[v]

        u_domain = u_data.get('domain_id', '')
        v_domain = v_data.get('domain_id', '')
        u_loc = u_data.get('location', (0, 0))
        v_loc = v_data.get('location', (0, 0))

        # Get domains
        u_domain_obj = mdg.domains.get(u_domain)
        v_domain_obj = mdg.domains.get(v_domain)

        u_world = _convert_to_world(u_loc, u_domain, u_domain_obj, wall_positions)
        v_world = _convert_to_world(v_loc, v_domain, v_domain_obj, wall_positions)

        if u_world and v_world:
            pt1 = factory.create_point3d(u_world[0], u_world[1], u_world[2])
            pt2 = factory.create_point3d(v_world[0], v_world[1], v_world[2])
            line = factory.create_line(pt1, pt2)

            path = GH_Path(edge_idx % 100)  # Group edges

            if is_transition:
                transition_lines.Add(line, path)
            else:
                edge_lines.Add(line, path)

        edge_idx += 1

    return node_points, edge_lines, transition_lines


def _convert_to_world(loc, domain_id, domain, wall_positions):
    """Convert domain coordinates to world XYZ."""
    from src.timber_framing_generator.mep.routing import RoutingDomainType

    if domain is None:
        return None

    if domain.domain_type == RoutingDomainType.WALL_CAVITY:
        # Wall: loc is (U, V) where U is along wall, V is height
        pos = wall_positions.get(domain_id, {})
        start = pos.get('start', [0, 0, 0])
        end = pos.get('end', start)

        # Calculate direction
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        import math
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            dir_x = dx / length
            dir_y = dy / length
        else:
            dir_x, dir_y = 1, 0

        u, v = loc
        world_x = start[0] + u * dir_x
        world_y = start[1] + u * dir_y
        world_z = v

        return (world_x, world_y, world_z)

    elif domain.domain_type == RoutingDomainType.FLOOR_CAVITY:
        # Floor: loc is (X, Y) directly
        return (loc[0], loc[1], 0)

    return None


def build_graph_json(mdg: MultiDomainGraph):
    """Build debug JSON output."""
    stats = mdg.get_statistics()

    output = {
        "statistics": stats,
        "domains": list(mdg.domains.keys()),
        "transitions": [
            {
                "id": t.id,
                "from": t.from_domain,
                "to": t.to_domain,
                "type": t.transition_type.value
            }
            for t in mdg.transitions
        ]
    }

    return json.dumps(output, indent=2)


# =============================================================================
# Main Processing
# =============================================================================

def main(walls_json, connectors_json, targets_json, config_json):
    """Main processing function."""
    debug_lines = []
    debug_lines.append("=== MEP Graph Builder ===")

    try:
        # Parse config
        config = parse_config(config_json)
        debug_lines.append(f"Config: wall_res={config['wall_resolution']}, floor_res={config['floor_resolution']}")

        # Parse walls
        walls_data = json.loads(walls_json)
        if isinstance(walls_data, dict) and 'walls' in walls_data:
            walls_data = walls_data['walls']
        debug_lines.append(f"Parsed {len(walls_data)} walls")

        # Build graph
        builder = UnifiedGraphBuilder(
            wall_grid_resolution=config['wall_resolution'],
            floor_grid_resolution=config['floor_resolution']
        )

        mdg = builder.build_from_json(
            walls_json,
            connectors_json=connectors_json,
            targets_json=targets_json
        )

        # Get statistics
        stats = mdg.get_statistics()
        debug_lines.append(f"Domains: {stats['num_domains']}")
        debug_lines.append(f"Transitions: {stats['num_transitions']}")

        for domain_id, domain_stats in stats.get('domains', {}).items():
            debug_lines.append(
                f"  {domain_id}: {domain_stats['num_nodes']} nodes, "
                f"{domain_stats['num_edges']} edges"
            )

        if 'unified' in stats:
            debug_lines.append(
                f"Unified: {stats['unified']['num_nodes']} nodes, "
                f"{stats['unified']['num_edges']} edges"
            )

        # Create visualization
        node_points, edge_lines, transition_lines = create_visualization_geometry(
            mdg, walls_data
        )

        # Build output JSON
        graph_json = build_graph_json(mdg)

        debug_lines.append("=== Complete ===")
        debug_info = "\n".join(debug_lines)

        return graph_json, node_points, edge_lines, transition_lines, debug_info

    except Exception as e:
        error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
        log_error(str(e))
        return None, DataTree[object](), DataTree[object](), DataTree[object](), error_msg


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    # Setup component on first run
    setup_component()

    # Validate inputs
    is_valid, error_msg = validate_inputs(walls_json, run)

    if not is_valid:
        graph_json = None
        node_points = DataTree[object]()
        edge_lines = DataTree[object]()
        transition_lines = DataTree[object]()
        debug_info = error_msg
        log_info(error_msg)
    else:
        # Run main processing
        graph_json, node_points, edge_lines, transition_lines, debug_info = main(
            walls_json, connectors_json, targets_json, config
        )
