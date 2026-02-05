# File: scripts/gh_mep_router.py
"""
MEP Router GHPython Component

Grasshopper component that routes MEP connectors to targets using
the OAHS (Obstacle-Aware Hanan Sequential) routing algorithm.

Inputs:
    connectors_json: JSON string with MEP connector definitions
    walls_json: JSON string with wall geometry (from Wall Analyzer)
    targets_json: JSON string with routing target definitions
    trade_filter: Optional trade filter ("plumbing", "electrical", etc.)
    run: Boolean trigger to execute routing

Outputs:
    routes_json: JSON string with computed routes
    stats_json: JSON string with routing statistics
    info: Diagnostic information
"""

import sys
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GH component metadata
ghenv.Component.Name = "MEP Router"
ghenv.Component.NickName = "MEP-Router"
ghenv.Component.Message = "v0.1.0"
ghenv.Component.Category = "TimberFraming"
ghenv.Component.SubCategory = "MEP"


def setup_component():
    """Configure component parameters."""
    # Note: In Rhino 8 with CPython, type hints must be set via GH UI
    inputs = ghenv.Component.Params.Input
    outputs = ghenv.Component.Params.Output

    input_config = [
        ("connectors_json", "conn", "JSON with MEP connectors", GH_ParamAccess.item),
        ("walls_json", "walls", "JSON with wall geometry", GH_ParamAccess.item),
        ("targets_json", "targets", "JSON with routing targets", GH_ParamAccess.item),
        ("trade_filter", "trade", "Optional trade filter", GH_ParamAccess.item),
        ("run", "run", "Execute routing when True", GH_ParamAccess.item),
    ]

    output_config = [
        ("routes_json", "routes", "JSON with computed routes"),
        ("stats_json", "stats", "Routing statistics"),
        ("info", "info", "Diagnostic information"),
    ]

    # Configure inputs
    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            inputs[i].Name = name
            inputs[i].NickName = nick
            inputs[i].Description = desc
            inputs[i].Access = access

    # Configure outputs (starting from index 1, skipping 'out')
    for i, (name, nick, desc) in enumerate(output_config):
        if i + 1 < outputs.Count:
            outputs[i + 1].Name = name
            outputs[i + 1].NickName = nick
            outputs[i + 1].Description = desc


def validate_inputs(connectors_json, walls_json, targets_json, run):
    """
    Validate component inputs.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not run:
        return False, "Set run=True to execute routing"

    if not connectors_json:
        return False, "Missing connectors_json input"

    if not walls_json:
        return False, "Missing walls_json input"

    if not targets_json:
        return False, "Missing targets_json input"

    # Validate JSON parsing
    try:
        json.loads(connectors_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid connectors_json: {e}"

    try:
        json.loads(walls_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid walls_json: {e}"

    try:
        json.loads(targets_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid targets_json: {e}"

    return True, ""


def parse_connectors(connectors_json):
    """
    Parse connectors from JSON.

    Returns:
        List of ConnectorInfo objects
    """
    from src.timber_framing_generator.mep.routing import ConnectorInfo

    data = json.loads(connectors_json)
    connectors = []

    # Handle both list and dict with "connectors" key
    if isinstance(data, dict):
        items = data.get("connectors", [])
    else:
        items = data

    for item in items:
        conn = ConnectorInfo(
            id=item.get("id", f"conn_{len(connectors)}"),
            system_type=item.get("system_type", "unknown"),
            location=tuple(item.get("location", [0, 0, 0])),
            direction=item.get("direction", "outward"),
            diameter=item.get("diameter", 0.0833),
            wall_id=item.get("wall_id", ""),
        )
        connectors.append(conn)

    return connectors


def parse_walls(walls_json):
    """
    Parse walls from JSON.

    Returns:
        List of wall dictionaries
    """
    data = json.loads(walls_json)

    if isinstance(data, dict):
        return data.get("walls", [])
    return data


def parse_targets(targets_json):
    """
    Parse routing targets from JSON.

    Returns:
        List of RoutingTarget objects
    """
    from src.timber_framing_generator.mep.routing import RoutingTarget, TargetType

    data = json.loads(targets_json)
    targets = []

    if isinstance(data, dict):
        items = data.get("targets", [])
    else:
        items = data

    for item in items:
        # Parse target type
        type_str = item.get("target_type", "wet_wall")
        try:
            target_type = TargetType(type_str)
        except ValueError:
            target_type = TargetType.WET_WALL

        target = RoutingTarget(
            id=item.get("id", f"target_{len(targets)}"),
            target_type=target_type,
            location=tuple(item.get("location", [0, 0, 0])),
            domain_id=item.get("domain_id", ""),
            plane_location=tuple(item.get("plane_location", [0, 0])),
            systems_served=item.get("systems_served", []),
            capacity=item.get("capacity", 1.0),
            priority=item.get("priority", 0),
        )
        targets.append(target)

    return targets


def get_trade_config(trade_filter):
    """
    Create TradeConfig based on filter.

    Args:
        trade_filter: Trade name to filter, or None for all trades

    Returns:
        TradeConfig instance
    """
    from src.timber_framing_generator.mep.routing import (
        TradeConfig,
        Trade,
        create_default_trade_config,
        create_plumbing_only_config,
        create_electrical_only_config,
    )

    if not trade_filter:
        return create_default_trade_config()

    filter_lower = trade_filter.lower().strip()

    if filter_lower == "plumbing":
        return create_plumbing_only_config()
    elif filter_lower == "electrical":
        return create_electrical_only_config()
    elif filter_lower == "hvac":
        return TradeConfig(enabled_trades={Trade.HVAC})
    elif filter_lower == "fire_protection":
        return TradeConfig(enabled_trades={Trade.FIRE_PROTECTION})
    else:
        return create_default_trade_config()


def run_routing(connectors, walls, targets, trade_config):
    """
    Execute MEP routing.

    Returns:
        OrchestrationResult
    """
    from src.timber_framing_generator.mep.routing import (
        SequentialOrchestrator,
        SingleZoneStrategy,
    )

    # Use single zone for simplicity in this component
    orchestrator = SequentialOrchestrator(
        trade_config=trade_config,
        zone_strategy=SingleZoneStrategy()
    )

    result = orchestrator.route_building(connectors, walls, targets)

    return result


def format_routes_json(result):
    """
    Format routes for JSON output.

    Args:
        result: OrchestrationResult

    Returns:
        JSON string with routes
    """
    routes_data = []

    for route in result.get_all_routes():
        route_dict = route.to_dict()
        routes_data.append(route_dict)

    return json.dumps({
        "routes": routes_data,
        "total_count": len(routes_data),
    }, indent=2)


def format_stats_json(result):
    """
    Format statistics for JSON output.

    Args:
        result: OrchestrationResult

    Returns:
        JSON string with statistics
    """
    stats = result.statistics.to_dict()

    # Add zone breakdown
    stats["zones"] = {
        zone_id: zone_result.statistics.to_dict()
        for zone_id, zone_result in result.zone_results.items()
    }

    # Add trade breakdown
    stats["trades"] = {
        trade: trade_result.statistics.to_dict()
        for trade, trade_result in result.trade_results.items()
    }

    return json.dumps(stats, indent=2)


def main():
    """Main entry point for GHPython component."""
    global routes_json, stats_json, info

    # Initialize outputs
    routes_json = ""
    stats_json = ""
    info = []

    # Get inputs (these come from Grasshopper)
    conn_input = connectors_json if 'connectors_json' in dir() else None
    walls_input = walls_json if 'walls_json' in dir() else None
    targets_input = targets_json if 'targets_json' in dir() else None
    trade_input = trade_filter if 'trade_filter' in dir() else None
    run_input = run if 'run' in dir() else False

    # Validate inputs
    is_valid, error = validate_inputs(conn_input, walls_input, targets_input, run_input)
    if not is_valid:
        info.append(f"Validation: {error}")
        return

    info.append("Inputs validated successfully")

    try:
        # Parse inputs
        connectors = parse_connectors(conn_input)
        info.append(f"Parsed {len(connectors)} connectors")

        walls = parse_walls(walls_input)
        info.append(f"Parsed {len(walls)} walls")

        targets = parse_targets(targets_input)
        info.append(f"Parsed {len(targets)} targets")

        # Get trade config
        trade_config = get_trade_config(trade_input)
        enabled_trades = trade_config.get_enabled_trades()
        info.append(f"Enabled trades: {[t.value for t in enabled_trades]}")

        # Run routing
        info.append("Starting routing...")
        result = run_routing(connectors, walls, targets, trade_config)

        # Format outputs
        routes_json = format_routes_json(result)
        stats_json = format_stats_json(result)

        # Summary
        info.append(f"Routing complete:")
        info.append(f"  - Successful routes: {result.statistics.successful_routes}")
        info.append(f"  - Failed routes: {result.statistics.failed_routes}")
        info.append(f"  - Success rate: {result.statistics.success_rate:.1f}%")
        info.append(f"  - Time: {result.statistics.orchestration_time_ms:.1f}ms")

    except ImportError as e:
        info.append(f"Import error: {e}")
        info.append("Make sure timber_framing_generator is installed")
    except Exception as e:
        info.append(f"Error: {type(e).__name__}: {e}")
        import traceback
        info.append(traceback.format_exc())


# Execute
if __name__ == "__main__":
    setup_component()
    main()
