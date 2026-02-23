# File: scripts/gh_walls_json_inspector.py
"""walls_json Inspector for Grasshopper.

A read-only diagnostic component that sits between the Wall Analyzer output
(walls_json) and the rest of the framing pipeline. It parses walls_json and
prints a human-readable summary of each wall's dimensions and opening data,
flagging anomalies. It passes walls_json through unchanged so it can be
inserted in-line without breaking the pipeline.

Key Features:
1. Non-Destructive Pass-Through
   - Passes walls_json through unchanged on output index 1
   - Can be inserted anywhere after Wall Analyzer without side effects

2. Human-Readable Report
   - Summarizes wall count, opening count, and anomalies
   - Per-wall detail with opening start_u, end_u, sill, header_top
   - Printed to Rhino console and available as output string

3. Anomaly Detection
   - Openings starting before wall or ending past wall end
   - Openings wider/taller than wall
   - Negative sill heights
   - Headers exceeding wall height
   - Suspiciously narrow (<0.5 ft) or short (<1.0 ft) openings

4. Optional Wall Filtering
   - Filter report to walls matching a wall_id substring

Environment:
    Rhino 8
    Grasshopper
    Python component (CPython 3)

Dependencies:
    - Grasshopper: Component framework and runtime messages
    - json: Parsing walls_json string

Performance Considerations:
    - Pure JSON parsing, no geometry creation
    - Linear time in number of walls and openings
    - Negligible overhead for typical wall counts (<100)

Usage:
    1. Connect 'walls_json' from Wall Analyzer component
    2. Set 'run' to True to trigger inspection
    3. Optionally set 'wall_filter' to restrict report to matching wall_ids
    4. Connect 'walls_json' output to downstream components (pass-through)
    5. Inspect 'report' in a Panel component for the summary
    6. Inspect 'anomalies' in a Panel for flagged issues as JSON

Input Requirements:
    Walls JSON (walls_json) - str:
        JSON string from Wall Analyzer containing wall geometry and openings.
        Required: Yes
        Access: Item
        Type hint: str (set via GH UI)

    Run (run) - bool:
        Boolean to trigger execution. When False, passes walls_json through
        without generating a report.
        Required: Yes
        Access: Item
        Type hint: bool (set via GH UI)

    Wall Filter (wall_filter) - str:
        If non-empty, only report walls whose wall_id contains this substring.
        Required: No (defaults to empty string, showing all walls)
        Access: Item
        Type hint: str (set via GH UI)

Outputs:
    Walls JSON (walls_json) - str:
        Pass-through of the input walls_json, unchanged.

    Report (report) - str:
        Human-readable summary string with per-wall and per-opening detail,
        anomaly flags, and aggregate statistics.

    Anomalies (anomalies) - str:
        JSON array of anomaly dicts. Each dict has: wall_id, opening_index,
        type, and issue fields.

Technical Details:
    - Reads inputs by parameter index (not by NickName globals)
    - Uses safest VolatileData access pattern with Branch/Branches/AllData fallback
    - All string formatting uses % operator (no f-strings, no unicode)
    - Does not import anything from timber_framing_generator

Error Handling:
    - Invalid/missing walls_json: returns empty report with warning
    - JSON parse errors: returns error in report output
    - Missing fields on individual openings: logs and skips gracefully
    - All errors reported via dual logging (console + GH runtime messages)

Author: Fernando Maytorena
Version: 1.0.0
"""

# =============================================================================
# Imports
# =============================================================================

# Standard library
import json
import traceback

# .NET / CLR
import clr

clr.AddReference("Grasshopper")
clr.AddReference("RhinoCommon")

# Rhino / Grasshopper
import Grasshopper

# =============================================================================
# Constants
# =============================================================================

COMPONENT_NAME = "walls_json Inspector"
COMPONENT_NICKNAME = "WInspect"
COMPONENT_MESSAGE = "v1.0"
COMPONENT_CATEGORY = "TFG"
COMPONENT_SUBCATEGORY = "Diagnostics"

# Anomaly thresholds
TOLERANCE = 0.1  # ft tolerance for boundary checks
MIN_OPENING_WIDTH = 0.5  # ft - below this is suspiciously narrow
MIN_OPENING_HEIGHT = 1.0  # ft - below this is suspiciously short

# =============================================================================
# Logging Utilities
# =============================================================================


def log_message(message, level="info"):
    """Log to console and optionally add GH runtime message.

    Args:
        message: The message to log (ASCII only -- no unicode)
        level: One of "info", "debug", "warning", "error", "remark"
    """
    print("[%s] %s" % (level.upper(), message))

    if level == "warning":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, message)
    elif level == "error":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Error, message)
    elif level == "remark":
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark, message)


def log_debug(message):
    """Log debug message (console only)."""
    print("[DEBUG] %s" % message)


def log_info(message):
    """Log info message (console only)."""
    print("[INFO] %s" % message)


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

    Sets component metadata, input parameters, and output parameters.

    Note: Output[0] is reserved for GH's internal 'out' - start from Output[1].

    IMPORTANT: Type Hints cannot be set programmatically in Rhino 8.
    They must be configured via UI: Right-click input -> Type hint -> Select type.
    Required type hints:
        walls_json: str
        run: bool
        wall_filter: str
    """
    # Component metadata
    ghenv.Component.Name = COMPONENT_NAME
    ghenv.Component.NickName = COMPONENT_NICKNAME
    ghenv.Component.Message = COMPONENT_MESSAGE
    ghenv.Component.Category = COMPONENT_CATEGORY
    ghenv.Component.SubCategory = COMPONENT_SUBCATEGORY

    # Configure inputs
    # Format: (DisplayName, variable_name, Description, Access)
    inputs = ghenv.Component.Params.Input

    input_config = [
        ("Walls JSON", "walls_json",
         "JSON string from Wall Analyzer",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Run", "run",
         "Boolean to trigger execution",
         Grasshopper.Kernel.GH_ParamAccess.item),
        ("Wall Filter", "wall_filter",
         "Optional wall_id substring filter (leave empty for all walls)",
         Grasshopper.Kernel.GH_ParamAccess.item),
    ]

    for i, (name, nick, desc, access) in enumerate(input_config):
        if i < inputs.Count:
            p = inputs[i]
            if p.Name != name:
                p.Name = name
            if p.NickName != nick:
                p.NickName = nick
            if p.Description != desc:
                p.Description = desc
            if p.Access != access:
                p.Access = access

    # Configure outputs (start from index 1, as 0 is reserved for 'out')
    outputs = ghenv.Component.Params.Output

    output_config = [
        ("Walls JSON", "walls_json",
         "Pass-through of input walls_json, unchanged"),
        ("Report", "report",
         "Human-readable inspection summary"),
        ("Anomalies", "anomalies",
         "JSON array of anomaly dicts"),
    ]

    for i, (name, nick, desc) in enumerate(output_config):
        idx = i + 1  # Skip Output[0]
        if idx < outputs.Count:
            p = outputs[idx]
            if p.Name != name:
                p.Name = name
            if p.NickName != nick:
                p.NickName = nick
            if p.Description != desc:
                p.Description = desc


# =============================================================================
# Helper Functions - Input Reading
# =============================================================================


def _get_first_branch(param):
    """Get the first branch of data from a GH parameter's VolatileData.

    Handles both typed (GH_Structure[GH_String]) and untyped
    (GH_Structure[IGH_Goo]) parameters. CPython3/pythonnet does not
    always expose .Branch() on the generic IGH_Goo variant.

    Args:
        param: A GH input parameter object

    Returns:
        List-like branch data, or None if empty
    """
    data = param.VolatileData

    # Try .Branch(0) first (works for typed parameters)
    if hasattr(data, 'Branch'):
        try:
            return data.Branch(0)
        except Exception:
            pass

    # Try get_Branch (pythonnet explicit getter)
    if hasattr(data, 'get_Branch'):
        try:
            return data.get_Branch(0)
        except Exception:
            pass

    # Fallback: iterate Branches property
    if hasattr(data, 'Branches'):
        try:
            branches = list(data.Branches)
            if branches:
                return branches[0]
        except Exception:
            pass

    # Last resort: AllData gives flat list of all items
    if hasattr(data, 'AllData'):
        try:
            all_items = list(data.AllData(True))
            return all_items
        except Exception:
            pass

    return None


def _read_string_input(inputs, index):
    """Read a string value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index

    Returns:
        str or None if input is empty or missing
    """
    if index >= inputs.Count:
        return None
    if inputs[index].VolatileDataCount == 0:
        return None
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return None
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return None
    return str(val)


def _read_bool_input(inputs, index, default=False):
    """Read a boolean value from a GH input by parameter index.

    Args:
        inputs: ghenv.Component.Params.Input collection
        index: Zero-based parameter index
        default: Default value if input is empty

    Returns:
        bool
    """
    if index >= inputs.Count:
        return default
    if inputs[index].VolatileDataCount == 0:
        return default
    branch = _get_first_branch(inputs[index])
    if branch is None or len(branch) == 0:
        return default
    item = branch[0]
    val = item.Value if hasattr(item, 'Value') else item
    if val is None:
        return default
    return bool(val)


# =============================================================================
# Helper Functions - Inspection Logic
# =============================================================================


def _check_opening_anomalies(wall_id, opening_index, opening, wall_length, wall_height):
    """Check a single opening for anomalies.

    Args:
        wall_id: Wall identifier string
        opening_index: Zero-based index of the opening within the wall
        opening: Opening dict from walls_json
        wall_length: Wall length in feet
        wall_height: Wall height in feet

    Returns:
        list of anomaly dicts, each with wall_id, opening_index, type, issue
    """
    anomalies = []
    opening_type = opening.get("opening_type", "unknown").upper()

    start_u = opening.get("start_u_coordinate", 0.0)
    rough_width = opening.get("rough_width", 0.0)
    end_u = start_u + rough_width
    rough_height = opening.get("rough_height", 0.0)
    sill_height = opening.get("base_elevation_relative_to_wall_base", 0.0)
    header_top = sill_height + rough_height

    def _add(issue_text):
        anomalies.append({
            "wall_id": str(wall_id),
            "opening_index": opening_index,
            "type": opening_type,
            "issue": issue_text,
        })

    # Check: opening starts before wall
    if start_u < -TOLERANCE:
        _add("opening starts before wall (start_u=%.3f)" % start_u)

    # Check: opening ends past wall end
    if end_u > wall_length + TOLERANCE:
        _add("opening ends past wall end (end_u=%.3f, wall_length=%.3f)"
             % (end_u, wall_length))

    # Check: opening wider than wall
    if rough_width > wall_length:
        _add("opening wider than wall")

    # Check: negative sill height
    if sill_height < 0:
        _add("negative sill height (%.3f)" % sill_height)

    # Check: header exceeds wall height
    if header_top > wall_height + TOLERANCE:
        _add("header exceeds wall height (header_top=%.3f, wall_height=%.3f)"
             % (header_top, wall_height))

    # Check: opening taller than wall
    if rough_height > wall_height:
        _add("opening taller than wall")

    # Check: suspiciously narrow opening
    if rough_width < MIN_OPENING_WIDTH:
        _add("suspiciously narrow opening (%.3f ft)" % rough_width)

    # Check: suspiciously short opening
    if rough_height < MIN_OPENING_HEIGHT:
        _add("suspiciously short opening (%.3f ft)" % rough_height)

    return anomalies


def _inspect_walls(walls, wall_filter):
    """Inspect a list of wall dicts and produce report lines and anomaly list.

    Args:
        walls: List of wall dicts from walls_json
        wall_filter: Substring filter for wall_id (empty string = all)

    Returns:
        tuple: (report_lines, all_anomalies)
            report_lines: list of str
            all_anomalies: list of anomaly dicts
    """
    report_lines = []
    all_anomalies = []

    # Aggregate stats
    total_walls = len(walls)
    walls_with_openings = 0
    total_openings = 0
    filtered_walls = []

    for wall in walls:
        wall_id = str(wall.get("wall_id", wall.get("id", "unknown")))
        openings = wall.get("openings", [])
        if openings:
            walls_with_openings += 1
            total_openings += len(openings)

        # Apply filter
        if wall_filter and wall_filter not in wall_id:
            continue
        filtered_walls.append(wall)

    # First pass: collect anomalies for all filtered walls
    for wall in filtered_walls:
        wall_id = str(wall.get("wall_id", wall.get("id", "unknown")))
        wall_length = float(wall.get("wall_length", 0.0))
        wall_height = float(wall.get("wall_height", 0.0))
        openings = wall.get("openings", [])

        for oi, opening in enumerate(openings):
            opening_anomalies = _check_opening_anomalies(
                wall_id, oi, opening, wall_length, wall_height,
            )
            all_anomalies.extend(opening_anomalies)

    # Header
    report_lines.append("=== walls_json Inspector ===")
    report_lines.append(
        "Total walls: %d   Walls with openings: %d   Total openings: %d"
        % (total_walls, walls_with_openings, total_openings)
    )
    report_lines.append("Anomalies: %d" % len(all_anomalies))

    if wall_filter:
        report_lines.append(
            "Filter: '%s' (%d of %d walls shown)"
            % (wall_filter, len(filtered_walls), total_walls)
        )

    report_lines.append("")

    # Per-wall detail
    for wall in filtered_walls:
        wall_id = str(wall.get("wall_id", wall.get("id", "unknown")))
        wall_length = float(wall.get("wall_length", 0.0))
        wall_height = float(wall.get("wall_height", 0.0))
        openings = wall.get("openings", [])

        report_lines.append(
            "Wall %s  length=%.2f ft  height=%.2f ft  openings=%d"
            % (wall_id, wall_length, wall_height, len(openings))
        )

        # Build a set of (wall_id, opening_index) that have anomalies
        anomaly_set = set()
        for a in all_anomalies:
            if str(a["wall_id"]) == wall_id:
                anomaly_set.add(a["opening_index"])

        for oi, opening in enumerate(openings):
            opening_type = opening.get("opening_type", "unknown").upper()
            start_u = opening.get("start_u_coordinate", 0.0)
            rough_width = opening.get("rough_width", 0.0)
            end_u = start_u + rough_width
            rough_height = opening.get("rough_height", 0.0)
            sill_height = opening.get(
                "base_elevation_relative_to_wall_base", 0.0)
            header_top = sill_height + rough_height

            # Base opening line
            line = (
                "  [%d] %s  start_u=%.2f  end_u=%.2f  width=%.2f"
                "  sill=%.2f  header_top=%.2f"
                % (oi, opening_type, start_u, end_u, rough_width,
                   sill_height, header_top)
            )

            if oi in anomaly_set:
                # Collect all issues for this opening
                issues = [
                    a["issue"] for a in all_anomalies
                    if str(a["wall_id"]) == wall_id
                    and a["opening_index"] == oi
                ]
                line += "  !! ANOMALY: %s" % "; ".join(issues)
            else:
                line += "  ** OK **"

            report_lines.append(line)

        report_lines.append("")

    return report_lines, all_anomalies


def validate_inputs(walls_json_val, run_val):
    """Validate component inputs.

    Args:
        walls_json_val: Raw walls_json string
        run_val: Boolean run toggle

    Returns:
        tuple: (is_valid, error_message)
    """
    if not run_val:
        return False, "Set 'run' to True to execute"

    if walls_json_val is None or not walls_json_val.strip():
        return False, "walls_json is required"

    return True, None


# =============================================================================
# Main Function
# =============================================================================


def main():
    """Main entry point for the walls_json Inspector component.

    Coordinates the overall workflow:
    1. Read inputs by parameter index
    2. Setup component metadata (display only)
    3. Validate inputs
    4. Parse walls_json and inspect each wall
    5. Return pass-through walls_json, report, and anomalies JSON

    Returns:
        tuple: (walls_json_out, report, anomalies_json)
    """
    # Default outputs
    default_outputs = ("", "", "[]")

    # -----------------------------------------------------------------
    # Read inputs by parameter index (CRITICAL: NickName injection is unreliable)
    # -----------------------------------------------------------------
    inputs = ghenv.Component.Params.Input

    walls_json_val = _read_string_input(inputs, 0)
    run_val = _read_bool_input(inputs, 1, default=False)
    wall_filter_val = _read_string_input(inputs, 2)

    # Normalize wall_filter
    if wall_filter_val is None:
        wall_filter_val = ""
    wall_filter_val = wall_filter_val.strip()

    # -----------------------------------------------------------------
    # Setup component metadata (display only, AFTER inputs are captured)
    # -----------------------------------------------------------------
    setup_component()

    try:
        # -----------------------------------------------------------------
        # Validate inputs
        # -----------------------------------------------------------------
        is_valid, error_msg = validate_inputs(walls_json_val, run_val)

        if not is_valid:
            if run_val:
                log_warning(error_msg)
            else:
                log_info(error_msg or "Component disabled (run=False)")
            # Still pass through walls_json even when not running
            passthrough = walls_json_val if walls_json_val else ""
            return (passthrough, error_msg or "", "[]")

        # -----------------------------------------------------------------
        # Parse walls_json
        # -----------------------------------------------------------------
        try:
            data = json.loads(walls_json_val)
        except json.JSONDecodeError as e:
            error_msg = "Invalid JSON in walls_json: %s" % str(e)
            log_error(error_msg)
            return (walls_json_val, error_msg, "[]")

        # Handle both {"walls": [...]} and bare [...] formats
        if isinstance(data, dict):
            walls = data.get("walls", [])
        elif isinstance(data, list):
            walls = data
        else:
            error_msg = "Unexpected walls_json format: expected dict or list, got %s" % type(data).__name__
            log_error(error_msg)
            return (walls_json_val, error_msg, "[]")

        if not walls:
            report_text = "=== walls_json Inspector ===\nNo walls found in walls_json."
            log_info("No walls found in walls_json")
            return (walls_json_val, report_text, "[]")

        # -----------------------------------------------------------------
        # Inspect walls
        # -----------------------------------------------------------------
        report_lines, all_anomalies = _inspect_walls(walls, wall_filter_val)
        report_text = "\n".join(report_lines)

        # Print report to Rhino console
        for line in report_lines:
            print(line)

        # Anomalies as JSON
        anomalies_json = json.dumps(all_anomalies, indent=2)

        # Summary GH message
        if all_anomalies:
            log_warning(
                "%d anomalies found across %d walls"
                % (len(all_anomalies), len(walls))
            )
        else:
            log_message(
                "All %d walls inspected -- no anomalies" % len(walls),
                "remark",
            )

        return (walls_json_val, report_text, anomalies_json)

    except Exception as e:
        error_msg = "Unexpected error: %s" % str(e)
        log_error(error_msg)
        log_debug(traceback.format_exc())
        passthrough = walls_json_val if walls_json_val else ""
        return (passthrough, error_msg, "[]")


# =============================================================================
# Execution
# =============================================================================

if __name__ == "__main__":
    walls_json, report, anomalies = main()
