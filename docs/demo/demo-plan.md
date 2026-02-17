# Product Demo Plan — Prefab Builder Demo

> **Target audience**: Prefab timber builders
> **Demo date**: TBD (few days out)
> **PDF source**: `15051 S PADRES RD.pdf`
> **Thesis**: PDF blueprint → fabrication-ready panelized BIM in one session

---

## 1. Demo Flow (Audience Perspective)

The audience sees a single web application where an AI agent processes their PDF
and produces construction documentation in Revit. Everything below the surface is invisible.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WHAT THE AUDIENCE SEES                           │
│                                                                     │
│  Step 1: Upload PDF                                                 │
│  Step 2: AI extracts all text, tables, figures (WS1 - Extraction)   │
│  Step 3: AI detects walls, doors, windows (WS3 - Plans)            │
│  Step 4: Agent conversation — discusses findings                    │
│  Step 5: Agent pushes rough BIM into Revit (walls, doors, windows)  │
│  Step 6: Agent generates panelized framing + assemblies + sheets    │
│  Step 7: Show Revit model — panelized assemblies with shop drawings │
│                                                                     │
│  Narrative: "From PDF to fabrication-ready in minutes"              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture — What's Really Happening

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Web App         │     │  Grasshopper      │     │  Revit            │
│   (React/Node)    │────>│  (Swiftlet HTTP)  │────>│  (via RiR)        │
│                   │     │                   │     │                   │
│  - WS0: Upload    │     │  Endpoint 1:      │     │  - Walls          │
│  - WS1: Chunks    │     │  /create-walls    │     │  - Doors          │
│  - WS3: Plans     │     │                   │     │  - Windows        │
│  - Agent chat     │     │  Endpoint 2:      │     │  - Framing        │
│  - HTTP triggers  │     │  /generate-framing│     │  - Assemblies     │
│                   │     │                   │     │  - Views/Sheets   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
     Frontend               Background               Output
     (visible)              (invisible)               (shown at end)
```

### Communication Protocol: MCP via Swiftlet (VALIDATED)

**MCP integration is working end-to-end** (validated Feb 2026):
- Claude Code calls MCP tools directly via Swiftlet MCP Server (port 3001)
- SwiftletBridge.exe (stdio-to-HTTP) bridges Claude Code to the GH-hosted MCP Server
- 3 tools registered: `analyze_walls`, `generate_framing`, `get_wall_summary`
- Real framing pipeline wired to `generate_framing` tool (1172 elements across 35 walls)

**RiR recompute limitation**: Auto-recompute is suppressed under Rhino.Inside.Revit.
Workaround: use RiR Recompute shortcut "RR" in Revit after each tool call.

**HTTP fallback**: Swiftlet HTTP endpoints (port 8080) remain available as a fallback
for the demo frontend choreography if needed.

---

## 3. Components to Build

### 3.1 Pre-baked Data (Already Done or Easy)

| Item | Status | Notes |
|------|--------|-------|
| PDF file (15051 S PADRES RD) | Ready | In Downloads folder |
| Kreo API results (JSON) | Ready | Ran externally in Google Colab |
| WS3 mock data | TODO | Add Kreo results to WS3 frontend as mock data |
| Agent context docs (markdown) | TODO | What the agent "knows" about this project |

### 3.2 New GH Script: Kreo JSON to Revit (Stage 1 — Rough BIM)

**Purpose**: Takes Kreo API detection results and creates Revit walls, doors, and windows.

**Input**: JSON from Kreo API with:
```json
{
  "walls": [
    { "p1": {"x": 0.0, "y": 0.0}, "p2": {"x": 5.0, "y": 0.0}, "thickness": 0.15, "length": 5.0 }
  ],
  "doors": [
    { "p1": {"x": 2.0, "y": 0.0}, "p2": {"x": 2.9, "y": 0.0}, "length": 0.9 }
  ],
  "windows": [
    { "p1": {"x": 3.5, "y": 3.0}, "p2": {"x": 4.5, "y": 3.0}, "length": 1.0 }
  ]
}
```

**Output**: Revit ElementIds (walls, doors, windows placed in model)

**Key considerations**:
- Kreo returns 2D coordinates (plan view). Need to define wall height (assume standard 8' or from PDF data)
- Kreo coordinates are in meters — Revit internal units are feet, convert accordingly
- Wall type selection: use a default Revit wall type or a generic one
- Door/window placement: insert family instances at detected locations along walls
- This is a NEW GHPython component: `gh_kreo_to_revit.py`

**Revit API calls needed (via RiR)**:
- `DB.Wall.Create(doc, line, wallTypeId, levelId, height, offset, flip, structural)`
- `doc.Create.NewFamilyInstance(point, familySymbol, host, level, structuralType)`

### 3.3 Swiftlet HTTP Server in GH Definition

**Two endpoints exposed by Swiftlet in the GH canvas:**

#### Endpoint 1: `POST /create-walls`

```
Request body: Kreo JSON (walls, doors, windows)
Triggers: gh_kreo_to_revit.py component
Response: {
  "status": "success",
  "walls_created": 12,
  "doors_created": 3,
  "windows_created": 5,
  "message": "Rough BIM model created"
}
```

#### Endpoint 2: `generate_framing` (MCP tool — VALIDATED)

```
MCP args: { "stud_spacing": 16 }
  (stud_spacing in inches; defaults to 16 if omitted)

Triggers: Full pipeline via MCP adapter scripts:
  Deconstruct Tool Call -> MCP Args Extractor -> Junction Analyzer ->
  Panel Decomposer -> Cell Decomposer -> Framing Generator ->
  MCP Response Formatter -> MCP Tool Response

Response: {
  "status": "success",
  "walls_processed": 35,
  "framing": {
    "total_elements": 1172,
    "by_type": { "bottom_plate": 70, "header": 33, "king_stud": 66, ... }
  },
  "wall_details": [ { "wall_id": "...", "element_count": 22 }, ... ],
  "message": "Generated 1172 framing elements across 35 walls: ..."
}
```

**Gotchas discovered during validation:**
- MCP args arrive as JToken objects from Swiftlet -- need Deserialize JToken component before Script A
- Junction Analyzer is REQUIRED -- it enriches walls_json with `framing_segments` that downstream components need
- Junction Analyzer's `walls_json_out` (output 4), NOT the original walls_json, must feed Panel Decomposer, Cell Decomposer, and Framing Generator

#### GH Definition Layout — MCP Pipeline (VALIDATED)

```
[Swiftlet MCP Server: port 3001]
    │
    ├── [Tool: analyze_walls]
    │       Deconstruct Tool Call -> gh_wall_analyzer -> MCP Tool Response
    │
    ├── [Tool: get_wall_summary]
    │       Deconstruct Tool Call -> gh_wall_summary -> MCP Tool Response
    │
    └── [Tool: generate_framing] (VALIDATED — real pipeline)
            │
            │  R (request ctx) ──────────────────────> [MCP Tool Response]
            │  Args                                            ^
            │  v                                               | body
            │  [Deserialize JToken]                    [gh_mcp_framing_response]
            │  v                                               ^
            │  [gh_mcp_framing_args]                           | framing_json
            │  | walls_json_out, stud_space_ft, run, config    |
            │  v                                               |
            │  [gh_junction_analyzer]                          |
            │  | walls_json_out (enriched)                     |
            │  v                                               |
            │  [gh_panel_decomposer]                           |
            │  | panels_json                                   |
            │  v                                               |
            │  [gh_cell_decomposer]                            |
            │  | cell_json                                     |
            │  v                                               |
            │  [gh_framing_generator] ─────────────────────────┘
            │
            (geometry/baking NOT wired yet — computation only)
```

#### GH Definition Layout — HTTP Fallback (Stage 2: Baking)

```
[Swiftlet HTTP Server: port 8080]
    │
    ├── [Route: POST /create-walls]
    │       │
    │       ├── [Parse JSON body]
    │       ├── [gh_kreo_to_revit component]
    │       └── [Send JSON response]
    │
    └── [Route: POST /generate-framing]
            │
            ├── [Parse JSON body]
            ├── [gh_wall_analyzer]
            ├── [gh_junction_analyzer]
            ├── [gh_panel_decomposer]
            ├── [gh_cell_decomposer]
            ├── [gh_framing_generator]
            ├── [gh_geometry_converter]
            ├── [gh_revit_baker]
            ├── [gh_revit_assembly_creator]
            ├── [gh_assembly_view_config]
            └── [Send JSON response]
```

### 3.4 Frontend Choreography (Web App Side)

A simple state machine in the web app that fires HTTP requests at scripted
moments during the agent conversation.

```
State 0: IDLE
  → User navigates WS0 → WS1 → WS3 (manual, showing off detection)

State 1: AGENT_INTRO
  → User opens agent chat
  → Agent: "I've analyzed the structural plans for 15051 S Padres Rd.
     I found 12 walls, 3 doors, and 5 windows across the floor plan.
     Would you like me to create the BIM model?"

State 2: CREATING_WALLS
  → User: "Yes, create the model"
  → Frontend fires: POST http://localhost:8080/create-walls
  → Agent: "I'm pushing the detected elements into Revit now...
     Creating walls, placing doors and windows..."
  → On HTTP response:
  → Agent: "Done. I've created {n} walls, {n} doors, and {n} windows
     in Revit. Would you like me to generate the panelized framing?"

State 3: GENERATING_FRAMING
  → User: "Yes, generate the framing"
  → Frontend fires: POST http://localhost:8080/generate-framing
  → Agent: "Generating panelized timber framing for all walls...
     This takes about 30-45 seconds as I process each panel."
  → Show loading indicator / progress
  → On HTTP response:
  → Agent: "Complete. I've generated {n} panel assemblies, each with
     plan views, elevation views, material schedules, and
     fabrication sheets. You can now review them in Revit."

State 4: SHOW_REVIT
  → Presenter switches to Revit window
  → Walk through: 3D model → open an assembly → show views/sheets
```

### 3.5 Agent Configuration

**Type**: Conversational only (no tool use)

**Context documents** (markdown files the agent has access to):
- Project summary extracted from WS1 chunks
- Kreo detection results summary (wall count, door count, etc.)
- Framing specifications (timber, 16" OC, panel sizes)
- What it CAN discuss: project data, element counts, framing approach
- What it CANNOT discuss: how the AI works, Kreo, third-party tools

**Guardrails**:
- Responses must stay within provided context docs
- Never mention Kreo, Swiftlet, Grasshopper, or Rhino
- Present everything as "ConstructAI's" capabilities
- Keep responses concise and confident

**Pre-scripted conversation flow** (3-4 exchanges):
1. Agent intro → summarizes what it found in the plans
2. User asks to create BIM → agent narrates wall creation
3. User asks for framing → agent narrates framing generation
4. Agent summarizes output → invites user to review in Revit

---

## 4. Technical Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Swiftlet HTTP server crashes | Demo dead | Test thoroughly; have pre-baked Revit model as fallback |
| Framing pipeline takes too long | Awkward wait | Loading state: "~30 seconds"; use small floor plan; or pre-bake |
| Kreo coordinates don't map cleanly to Revit | Wrong geometry | Pre-process JSON manually if needed; test with actual data first |
| Agent says something unexpected | Breaks narrative | Hardcode responses; use very constrained system prompt |
| Revit transaction fails mid-pipeline | Partial model | Wrap in try/catch; have clean backup model |
| Network issues (Swiftlet localhost) | HTTP fails | Everything runs local; no external dependencies during demo |

### Fallback Plan

If live triggering fails during the demo:
1. Have a pre-built Revit model already open in another Revit session
2. The agent can narrate as if it just created it
3. Switch to the pre-built model and continue the walkthrough
4. Audience won't know the difference

---

## 5. File Inventory

### Files to Create

| File | Location | Purpose |
|------|----------|---------|
| `gh_kreo_to_revit.py` | `scripts/` | New GH component: Kreo JSON -> Revit walls/doors/windows |
| `demo_server.gh` | `grasshopper/` or TBD | GH definition with Swiftlet server + both pipelines |
| `kreo_results.json` | `docs/ai/demo/` | Pre-baked Kreo API results for 15051 S Padres Rd |
| `agent_context.md` | `docs/ai/demo/` | Markdown context the agent uses for responses |
| `agent_conversation_script.md` | `docs/ai/demo/` | Pre-scripted conversation flow |
| `demo-plan.md` | `docs/demo/` | This document |

### Created Files (MCP Pipeline)

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `gh_mcp_framing_args.py` | `scripts/` | MCP adapter: extracts tool args, gates pipeline | DONE |
| `gh_mcp_framing_response.py` | `scripts/` | MCP adapter: formats pipeline output for MCP response | DONE |

### Existing Files to Leverage

| File | Purpose in Demo |
|------|----------------|
| `scripts/gh_wall_analyzer.py` | Stage 2: Analyze created walls |
| `scripts/gh_junction_analyzer.py` | Stage 2: Enrich walls with junction/framing data |
| `scripts/gh_panel_decomposer.py` | Stage 2: Panelize walls |
| `scripts/gh_cell_decomposer.py` | Stage 2: Cell decomposition |
| `scripts/gh_framing_generator.py` | Stage 2: Generate framing elements |
| `scripts/gh_geometry_converter.py` | Stage 2: Convert to Breps |
| `scripts/gh_revit_baker.py` | Stage 2: Place in Revit |
| `scripts/gh_revit_assembly_creator.py` | Stage 2: Create assemblies |
| `scripts/gh_assembly_view_config.py` | Stage 2: Generate views/sheets |
| `scripts/gh_multi_layer_sheathing.py` | Stage 2: Sheathing layers |

---

## 6. Task Breakdown

### Phase A: Data Preparation (Day 1)

- [ ] Process Kreo API results for 15051 S Padres Rd
- [ ] Clean/transform Kreo JSON into the format expected by the new GH script
- [ ] Add Kreo results as mock data in WS3 frontend
- [ ] Write agent context markdown documents
- [ ] Write agent conversation script

### Phase B: New GH Script — Kreo to Revit (Day 1-2)

- [ ] Create `gh_kreo_to_revit.py` following GHPython template
- [ ] Implement coordinate transformation (meters → feet, 2D → 3D)
- [ ] Implement wall creation via `DB.Wall.Create()`
- [ ] Implement door/window insertion via `NewFamilyInstance()`
- [ ] Test with actual Kreo data in Grasshopper
- [ ] Verify walls/doors/windows appear correctly in Revit

### Phase C: Swiftlet MCP + HTTP Server (Day 2)

- [x] Install Swiftlet v0.2.0 in Rhino 8
- [x] Create MCP Server on port 3001 with 3 tools (analyze_walls, generate_framing, get_wall_summary)
- [x] Wire `generate_framing` to real pipeline via MCP adapter scripts
- [x] Test MCP end-to-end: analyze_walls (35 walls) -> generate_framing (1172 elements at 16" OC)
- [ ] Wire Endpoint 1: `/create-walls` -> `gh_kreo_to_revit` pipeline (HTTP fallback)
- [ ] Wire geometry/baking chain for full demo (converter -> baker -> assemblies -> views)
- [ ] Handle error cases and response formatting

### Phase D: Frontend Integration (Day 2-3)

- [ ] Implement choreography state machine in web app
- [ ] Connect agent conversation flow to HTTP triggers
- [ ] Add loading states and progress indicators
- [ ] Style agent responses for demo polish
- [ ] Test full end-to-end flow

### Phase E: Rehearsal (Day 3)

- [ ] Full dry run: PDF → WS1 → WS3 → Agent → Revit
- [ ] Time each step, identify slow points
- [ ] Prepare fallback (pre-baked Revit model)
- [ ] Practice narration and transitions
- [ ] Record backup video of successful run

---

## 7. Demo Script (Presenter Notes)

### Opening (30 seconds)
> "Let me show you how ConstructAI turns a PDF blueprint into
> fabrication-ready panel assemblies."

### WS0 → WS1: Document Understanding (1 minute)
> "We start by uploading the PDF. Our AI immediately processes every page,
> extracting all text, tables, and figures. Here in the extraction
> workspace you can see every chunk our system identified."
>
> Show: chunk list, click on a few, show bounding boxes on the drawing.

### WS3: Element Detection (1 minute)
> "Now in the Plans workspace, our AI has identified every wall, door,
> and window in the floor plan — with real-world dimensions.
> You can see each element highlighted with its measurements."
>
> Show: detected elements overlaid on the plan, instance list on the right.

### Agent Conversation (2 minutes)
> "Let me ask our AI agent about this project."
>
> Trigger the scripted conversation. Agent summarizes findings, user asks
> to create BIM, agent narrates creation, user asks for framing, agent
> narrates framing generation (with ~30s loading state).

### Revit Walkthrough (2-3 minutes)
> Switch to Revit. Show:
> 1. 3D view — all walls with doors/windows
> 2. Zoom into panelized framing — studs, plates, headers visible
> 3. Open one assembly — show plan, elevations, section
> 4. Show material schedule — every stud, plate, header listed
> 5. Open a sheet — fabrication drawing ready for the shop floor
>
> "Each panel has its own assembly with all the views and schedules
> your shop floor needs. From PDF to fabrication drawings."

### Close (15 seconds)
> "That's ConstructAI. Fabrication-level certainty from day one."

---

## 8. Open Questions

1. **Wall height**: Kreo returns 2D plan data. What wall height to use? (8'0" default? Extract from PDF?)
2. **Wall type**: Which Revit wall type for the rough BIM? Generic? Or match detected thickness?
3. **Door/window families**: Which Revit families to use for doors and windows?
4. **Floor plan scope**: Use the full PDF or just one floor/section for demo speed?
5. **Swiftlet port**: Port 8080 okay? Need to check for conflicts with other services.
6. **Agent platform**: Which LLM backend for the conversational agent? Claude API via the web app?
7. **Demo recording**: Should we record a backup video in case of live demo failure?
