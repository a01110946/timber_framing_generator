# Swiftlet HTTP Integration Plan

> **Goal**: Enable the web app to trigger the existing framing pipeline
> via HTTP requests using Swiftlet's Server Input in Grasshopper.
>
> **Status**: Server Input + Deconstruct Request + Deconstruct Body + HTTP Trigger
> chain VERIFIED WORKING (2026-02-16). Port 9090, route "/generate-framing".
>
> **v2.0**: Staged execution to prevent Revit crashes from simultaneous heavy
> operations. Per-stage boolean outputs control which pipeline steps run.

---

## Architecture (Verified)

```
Web App (frontend)                 Grasshopper Canvas (background)
─────────────────                 ────────────────────────────────

POST /generate-framing  ────────> [Swiftlet: Server Input (:9090)]
{ stage: "analyze",                    |
  config... }                          | R (request object)
                                       v
                                  [Swiftlet: Deconstruct Request]
                                       |
                                       | B (RequestBodyByteArray)
                                       v
                                  [Swiftlet: Deconstruct Body]
                                       |
                                       | Tx (raw JSON text string)
                                       v
                                  [gh_http_trigger.py v2.0]
                                       | run_analyze ──> Wall Analyzer
                                       | run_frame ───> Decomposers + Framing + Geom
                                       | run_bake ────> RiR Baker
                                       | run_sheathing -> Sheathing components
                                       | run_assemble -> Assembly Creator (after sheathing)
                                       | config_json
                                       v
                                  [RiR: Query Elements (OST_Walls)]
                                       | walls
                                       v
                                  ┌─ PIPELINE (stage-gated) ────────┐
                                  | [Wall Analyzer]       run_analyze|
                                  | [Panel Decomposer]    run_frame  |
                                  | [Cell Decomposer]     run_frame  |
                                  | [Framing Generator]   run_frame  |
                                  | [Geometry Converter]  run_frame  |
                                  | [RiR Baker]           run_bake   |
                                  | [Multi-Layer Sheathing] run_sheathing|
                                  | [Sheathing Baker]    run_sheathing|
                                  | [Assembly Creator]    run_assemble|
                                  └──────────────────────────────────┘
                                       |
                                       v
                                  [gh_format_response.py]  (stats/debug only)
                                       |
                                       v
[Swiftlet: Server Response] <── static JSON or pipeline stats
     (wired to R from Deconstruct Request)
     Sends "OK" back to caller
```

### Staged Execution (v2.0)

Running the entire pipeline at once crashes Revit because baking hundreds
of elements + creating assemblies + views/sheets simultaneously is too much.
The solution: **cumulative stages** controlled via the `stage` field in the
HTTP request body.

| Stage | Level | What runs | Speed |
|-------|-------|-----------|-------|
| `analyze` | 1 | Wall Analyzer (Revit read) | Fast |
| `frame` | 2 | + Panel/Cell Decomposer, Framing Generator, Geometry Converter | Fast (computation) |
| `bake` | 3 | + RiR Baker (Revit write) | Slow |
| `sheathing` | 4 | + Multi-Layer Sheathing, Sheathing Baker | Slow |
| `assemble` | 5 | + Assembly Creator (Revit write, needs sheathing first) | Slow |
| `all` | 99 | Everything (backward compatible default) | Slow |

**Cumulative**: requesting `"stage": "bake"` runs analyze + frame + bake.

**Demo workflow**: The web app sends sequential requests, escalating the stage
after each succeeds. The agent narrates between requests.

### Swiftlet Component Chain (Verified)

```
[Server Input]          P = 9090, route = "/generate-framing"
      | R
      v
[Deconstruct Request]   Outputs: R, M, Rt, H, Q, B
      | B (RequestBodyByteArray object - NOT a string)
      v
[Deconstruct Body]      Input: B  |  Outputs: T (type), Tx (text), By (bytes)
      | Tx (the actual JSON string from the POST body)
      v
[gh_http_trigger v2.0]  Input: content = Tx
                        Outputs: run_analyze, config_json, info,
                                 run_frame, run_bake, run_assemble, run_sheathing
```

**IMPORTANT**: The Deconstruct Request "B" output is a `Swiftlet.DataModels.Implementations.RequestBodyByteArray`
object, NOT a raw string. You MUST use the Deconstruct Body component to extract the text content via its `Tx` output.

### Server Response

The Server Response component (orange) needs:
- **R** input: wired from Deconstruct Request's **R** output (request context)
- **B** input: the response body (static JSON panel or formatted response)
- **S** input: HTTP status code (200)
- **H** input: response headers (optional)

Currently returns "OK" as a static response. For the demo, this is sufficient
since the web app fires and forgets while the agent narrates.

### Port Note

Port 8080 is taken by Adminer (Docker database admin). Using **9090** instead.

---

## New Components

### 1. gh_http_trigger.py (v2.0 - Staged)

**Purpose**: Sits between Swiftlet's Deconstruct Body and the pipeline. Converts
the raw HTTP request body into per-stage boolean triggers and a validated
`config_json`. Supports staged execution to avoid Revit crashes.

**Gating**: The pipeline's `run` boolean inputs gate execution. Without this
component, the pipeline would auto-run on GH definition load. The trigger
component outputs all booleans=False until a valid HTTP request arrives.

```
Swiftlet Deconstruct Body
    | Tx (raw JSON text string)
    v
[gh_http_trigger v2.0]
    | run_analyze (bool)   --> Wall Analyzer "run"
    | config_json (str)    --> Framing Generator, Panel Decomposer, etc.
    | info (str)           --> debug panel
    | run_frame (bool)     --> Decomposers + Framing Gen + Geometry Conv "run"
    | run_bake (bool)      --> RiR Baker "run"
    | run_sheathing (bool) --> Sheathing components "run"
    | run_assemble (bool)  --> Assembly Creator "run" (after sheathing)
```

**Inputs:**
| # | Name | NickName | Description | Access |
|---|------|----------|-------------|--------|
| 0 | HTTP Content | content | Raw body from Swiftlet Deconstruct Body Tx output | Item |

**Outputs:**
| # | Name | NickName | Description |
|---|------|----------|-------------|
| 1 | Run Analyze | run_analyze | True when stage >= "analyze" (was: Trigger) |
| 2 | Config JSON | config_json | Validated config for downstream components |
| 3 | Info | info | Debug information about request and active stage |
| 4 | Run Frame | run_frame | True when stage >= "frame" (NEW) |
| 5 | Run Bake | run_bake | True when stage >= "bake" (NEW) |
| 6 | Run Sheathing | run_sheathing | True when stage >= "sheathing" (NEW) |
| 7 | Run Assemble | run_assemble | True when stage >= "assemble" (NEW) |

**Backward compatibility**: Outputs 1-3 preserve v1.0 indices. Existing wires
to config_json (index 2) and info (index 3) remain valid. Output 1 was renamed
from "Trigger" to "Run Analyze" but serves the same purpose at minimum stage.

### 2. gh_format_response.py

**Purpose**: Collects stats from the pipeline outputs and formats them into
a JSON response to send back through the HTTP Listener.

```
Pipeline outputs
    | framing_json, assembly_json, sheathing_json
    v
[gh_format_response]
    | response_json (str)
    v
Swiftlet: Create Text Body Custom ("application/json")
    v
Swiftlet HTTP Listener (Response Body input)
```

**Inputs:**
| # | Name | NickName | Description | Access |
|---|------|----------|-------------|--------|
| 0 | Framing JSON | framing_json | From Framing Generator output | Item |
| 1 | Assembly JSON | assembly_json | From Assembly Creator output | Item |
| 2 | Sheathing JSON | sheathing_json | From Multi-Layer Sheathing output (optional) | Item |
| 3 | Error | error | Error message if pipeline failed (optional) | Item |

**Outputs:**
| # | Name | NickName | Description |
|---|------|----------|-------------|
| 1 | Response JSON | response_json | HTTP response body for Swiftlet |
| 2 | Info | info | Debug information |

---

## Canvas Wiring Changes

### What CHANGES in the existing definition:

1. **Remove**: Manual wall selection (RiR Select component)
2. **Add**: RiR "All Elements of Category" (OST_Walls) or "Query Elements"
3. **Add**: Swiftlet Server Input component (port 9090, route "/generate-framing")
4. **Add**: Swiftlet Deconstruct Request + Deconstruct Body components
5. **Add**: gh_http_trigger.py v2.0 component (8 outputs: out + 7 custom)
6. **Add**: gh_format_response.py component
7. **Add**: Swiftlet Server Response + Create Text Body Custom components
8. **Rewire**: Per-stage `run` inputs (see wiring diagram below)
9. **Rewire**: Config inputs -> gh_http_trigger's `config_json` output

### What stays UNCHANGED:

- All existing pipeline components (Wall Analyzer through Assembly Creator)
- All existing wiring between pipeline components (walls_json, panels_json, etc.)
- Sheathing path (Multi-Layer Sheathing, Sheathing Baker)
- Assembly view config
- RiR Baker components

### Wiring Diagram (detailed, v2.0 staged)

```
[Swiftlet: Server Input (port=9090, route="/generate-framing")]
    |                                                  ^
    | R                                                | Response
    v                                                  |
[Swiftlet: Deconstruct Request]            [Swiftlet: Server Response]
    | R ──────────────────────────────────────> R       ^
    | B                                                |
    v                                       [Swiftlet: Create Text Body]
[Swiftlet: Deconstruct Body]                           ^
    | Tx                                               |
    v                                       [gh_format_response]
[gh_http_trigger v2.0]                          ^   ^   ^
    | run_analyze ──────────┐                   |   |   |
    | config_json ──────┐   |                   |   |   |
    | run_frame ─────┐  |   |                   |   |   |
    | run_bake ────┐ |  |   |                   |   |   |
    | run_sheathing┤ |  |   |                   |   |   |
    | run_assemble─┤ |  |   |                   |   |   |
    v              | |  |   v (run_analyze)     |   |   |
[RiR: Query Walls] | |  |   |                   |   |   |
    | walls        | |  |   |                   |   |   |
    v              | |  |   v                   |   |   |
[Wall Analyzer] ───┤ ├──┼──────> walls_json     |   |   |
    |              | |  v (config)              |   |   |
    v              | |  |                       |   |   |
[Panel Decomposer]─┤ v (run_frame)              |   |   |
    |              | |  panels_json             |   |   |
    v              | |                          |   |   |
[Cell Decomposer]──┤ v (run_frame)              |   |   |
    |              | cell_json                  |   |   |
    v              |                            |   |   |
[Framing Gen.]─────┤ v (run_frame)              |   |   |
    |              | framing_json ──────────────┘   |   |
    v              |                                |   |
[Geometry Conv.]───┤ v (run_frame)                  |   |
    |              | breps                          |   |
    v              |                                |   |
[RiR Baker]────────┤ v (run_bake)                   |   |
    |              | baking_data_json               |   |
    v              |                                |   |
[Multi-Layer Sheathing]──(run_sheathing)            |   |
    | sheathing_json ───────────────────────────────┘   |
    v              |                                    |
[Sheathing Baker]──┤ (run_sheathing)                    |
    |              |                                    |
    v              |                                    |
[Assembly Creator]─┘ v (run_assemble)                   |
    |              assembly_json ───────────────────────┘
```

---

## HTTP Request/Response Contract

### Request: POST /generate-framing

```json
{
  "stage": "analyze",
  "material": "timber",
  "stud_spacing_in": 16,
  "panel_max_length_ft": 24,
  "generate_assemblies": true,
  "generate_sheets": true,
  "assembly_naming_prefix": "W"
}
```

All fields are optional. Defaults: `stage="all"`, `material="timber"`,
`stud_spacing_in=16`, `panel_max_length_ft=24`.

**Stage values** (cumulative):
| Value | Runs |
|-------|------|
| `"analyze"` | Wall Analyzer only |
| `"frame"` | + Decomposers + Framing Generator + Geometry Converter |
| `"bake"` | + RiR Baker |
| `"sheathing"` | + Multi-Layer Sheathing + Sheathing Baker |
| `"assemble"` | + Assembly Creator (after sheathing, so panels are complete) |
| `"all"` | Everything (default, backward compatible) |

### Response: 200 OK

```json
{
  "status": "success",
  "walls_processed": 12,
  "framing": {
    "total_elements": 487,
    "by_type": {
      "bottom_plate": 24,
      "top_plate": 48,
      "stud": 312,
      "king_stud": 16,
      "trimmer": 16,
      "header": 8,
      "sill": 4,
      "sill_cripple": 12,
      "header_cripple": 20,
      "row_blocking": 27
    }
  },
  "assemblies": {
    "count": 24,
    "ids": ["123456", "123457"]
  },
  "sheathing": {
    "layers": 2,
    "total_panels": 96
  },
  "message": "Framing pipeline complete"
}
```

### Response: Error

```json
{
  "status": "error",
  "message": "Pipeline failed: no walls found in model",
  "walls_processed": 0
}
```

---

## Setup Checklist

1. [X] Install Swiftlet v0.2.0 via Yak package manager in Rhino 8
2. [X] Copy gh_http_trigger.py and gh_format_response.py to scripts/
3. [X] Open existing GH definition in Rhino 8
4. [X] Add Swiftlet Server Input component (Swiftlet > Server tab)
5. [X] Set Port = 9090, Route = "/generate-framing"
6. [X] Add Swiftlet Deconstruct Request + Deconstruct Body components
7. [X] Wire Server Input R -> Deconstruct Request
8. [X] Wire Deconstruct Request B -> Deconstruct Body
9. [X] Add gh_http_trigger.py v2.0 as a GHPython component (8 outputs)
10. [X] Wire Deconstruct Body Tx -> gh_http_trigger content input
11. [X] Wire gh_http_trigger config_json -> pipeline config inputs
12. [X] Replace wall selection with RiR "All Elements of Category" (OST_Walls)
13. [ ] Wire per-stage boolean outputs to pipeline components:
    - [ ] run_analyze (output 1) -> Wall Analyzer "run"
    - [ ] run_frame (output 4) -> Panel Decomposer, Cell Decomposer,
          Framing Generator, Geometry Converter "run" inputs
    - [ ] run_bake (output 5) -> RiR Baker "run"
    - [ ] run_sheathing (output 6) -> Multi-Layer Sheathing, Sheathing Baker "run"
    - [ ] run_assemble (output 7) -> Assembly Creator "run"
14. [X] Add gh_format_response.py as a GHPython component
15. [X] Wire pipeline outputs -> gh_format_response inputs
16. [X] Add Swiftlet Server Response + Create Text Body Custom components
17. [X] Wire gh_format_response response_json -> Create Text Body Content
18. [X] Set Create Text Body ContentType = "application/json"
19. [X] Wire Create Text Body output -> Server Response B input
20. [X] Wire Deconstruct Request R -> Server Response R input

---

## Test Commands (Staged)

Test incrementally, starting with the lightest stage:

```bash
# Stage 1: Analyze only (Revit read, fast)
curl -X POST http://localhost:9090/generate-framing \
  -H "Content-Type: application/json" \
  -d "{\"stage\": \"analyze\"}"

# Stage 2: Analyze + Frame (computation, fast)
curl -X POST http://localhost:9090/generate-framing \
  -H "Content-Type: application/json" \
  -d "{\"stage\": \"frame\"}"

# Stage 3: Analyze + Frame + Bake (Revit write, slow)
curl -X POST http://localhost:9090/generate-framing \
  -H "Content-Type: application/json" \
  -d "{\"stage\": \"bake\"}"

# Stage 4: + Sheathing (must come before assemble)
curl -X POST http://localhost:9090/generate-framing \
  -H "Content-Type: application/json" \
  -d "{\"stage\": \"sheathing\"}"

# Stage 5: + Assembly Creator (sheathing included in assemblies)
curl -X POST http://localhost:9090/generate-framing \
  -H "Content-Type: application/json" \
  -d "{\"stage\": \"assemble\"}"

# Full pipeline (backward compatible, same as omitting stage)
curl -X POST http://localhost:9090/generate-framing \
  -H "Content-Type: application/json" \
  -d "{}"
```
