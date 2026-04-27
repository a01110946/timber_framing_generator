# Demo Script: PDF to Fabrication-Ready Panels

> **Thesis**: A single AI agent session turns a PDF blueprint into fabrication-ready panelized BIM with shop drawings.
>
> **Target audience**: Prefab timber builders, construction tech investors, AEC innovators
>
> **Project**: 15051 S Padres Rd -- Single-family residential, 3-bed/2-bath, wood frame, Arizona
>
> **Duration**: ~8 minutes total
>
> **Agent**: Claude Code (via MCP to Grasshopper/Revit pipeline)

---

## Narrative Arc

The demo tells a story in three acts:

```
ACT 1: UNDERSTAND           ACT 2: BUILD              ACT 3: DELIVER
"What's in this PDF?"       "Make it real"             "Ready for the shop floor"

Web app (full screen)       Split screen:              Revit (full screen)
                            Revit left + Agent right

- Upload PDF                - Show EMPTY Revit model   - Panelized assemblies
- AI extracts specs         - Agent creates walls,     - Plan/elevation views
- Agent discusses findings    doors, windows (live!)   - Material schedules
- Detects elements          - Agent generates framing  - Fabrication sheets
  (walls, doors, windows)   - Add sheathing layers

Time: ~2 min               Time: ~4 min               Time: ~3 min
```

**The core promise**: "From PDF to fabrication-ready in one session."

---

## Pre-Demo Setup

### Revit/Grasshopper (hidden)
- [ ] Rhino 8 open with GH definition loaded (all MCP tools wired)
- [ ] Swiftlet MCP Server running on port 3001
- [ ] MCP tools available: `create_walls`, `analyze_walls`, `get_wall_summary`, `generate_framing`
- [ ] RiR active, connected to Revit
- [ ] "RR" shortcut set in Revit for Recompute (workaround for auto-recompute)
- [ ] GH window minimized/hidden (audience should not see it)
- [ ] **Fresh Revit project open -- EMPTY (no walls, no doors, no windows)**
- [ ] Verify empty: open 3D view + wall schedule + door schedule, confirm zero elements

### Agent (visible on right side of split screen)
- [ ] Claude Code or Claude Desktop open
- [ ] If Claude Code: `.mcp.json` configured and MCP tools connected
- [ ] If Claude Desktop: MCP server configured in settings
- [ ] Project context loaded (agent_context.md)
- [ ] Test one MCP tool call before demo to warm up the connection

### Web App (visible, full screen for ACT 1)
- [ ] ConstructAI web app open to upload screen
- [ ] PDF file ready: `15051 S PADRES RD.pdf`
- [ ] WS1 data pre-loaded (extraction results)
- [ ] WS3 data pre-loaded (Kreo detection results)

### Pre-baked Kreo Results
- [ ] Kreo API results JSON saved locally (walls, doors, windows detected)
- [ ] JSON wired into the `create_walls` MCP tool's GH pipeline
- [ ] If live Kreo call not possible, have results ready to paste

### Screen Layout
- [ ] ACT 1: Web app full screen
- [ ] ACT 1 -> 2 transition: Split screen (Revit left, Agent right)
- [ ] ACT 3: Revit full screen
- [ ] Practice the split-screen transition (Win+Left / Win+Right on Windows)

### Fallback
- [ ] Pre-built Revit model with completed framing + assemblies in separate file
- [ ] Can switch to this if live pipeline fails at any point

---

## ACT 1: UNDERSTAND (~2 minutes)

### Scene: Web App (ConstructAI platform)

**Presenter narrates while navigating the web app.**

> "Let me show you what happens when a set of plans arrives at a prefab shop."

**Step 1.1 -- Upload PDF**

> "We start with a PDF -- the same thing your estimator gets emailed on Monday morning."

*Upload `15051 S PADRES RD.pdf` to the ConstructAI platform.*

> "Our AI immediately processes every page. It reads the general notes, the framing specs, the nailing schedules -- everything a framer would look for."

**Step 1.2 -- Show Document Understanding (WS1)**

*Navigate to the extraction workspace. Show chunks being identified.*

> "Here you can see what our system extracted. Framing notes -- 2x4 interior, 2x6 exterior. Nailing schedule. Shear wall requirements. Header sizes. It reads the drawings the way an experienced framer reads them."

*Click on a few chunks to show bounding boxes on the document.*

**Step 1.3 -- Show Element Detection (WS3)**

*Navigate to the Plans workspace showing Kreo detection results.*

> "Now look at the floor plan. Our AI has detected every wall, door, and window -- with real-world dimensions. 35 walls, 16 doors, 8 windows."

*Show detected elements overlaid on the plan with measurements.*

> "We've gone from a flat PDF to structured data in seconds. But data alone doesn't build houses. Let's hand this off to our construction agent and watch it build a BIM model from scratch."

### Transition: Split Screen

*Switch to split screen: Revit on the left, web app (with agent chat) or Claude Desktop on the right.*

> "I'm going to split the screen so you can see what happens in real time. On the left is Revit -- completely empty right now. On the right is our AI agent."

**Step 1.4 -- Prove the model is empty**

*In Revit (left side), show:*
1. *The 3D view -- empty, just the default grid/levels*
2. *A wall schedule -- zero rows*
3. *A door schedule -- zero rows*

> "Nothing in the model. No walls, no doors, no windows. Zero elements. Everything our AI knows about this project is data from the PDF -- sitting in the platform's database. Now let's see what the agent can do with it."

---

## ACT 2: BUILD (~4 minutes)

### Scene: Split screen -- Revit (left) + Agent (right)

**The audience sees Revit on the left and the agent conversation on the right. As the agent calls tools, elements appear in the Revit 3D view in real time. The presenter hits "RR" in Revit after each tool call (invisible to audience -- can be done via keyboard while Revit is on screen).**

---

#### Exchange 1: Create the BIM Model (Walls, Doors, Windows)

**User says:**

```
I just processed the plans for 15051 S Padres Rd through our platform. It's a
single-family home in Arizona -- 3 bedrooms, 2 baths, attached 2-car garage.
Our AI detected 35 walls, 16 doors, and 8 windows from the floor plan. Can you
create the BIM model in Revit from the detected elements?
```

**[MCP tool call: `create_walls` -- takes Kreo JSON, creates Revit walls/doors/windows]**
*(Presenter hits RR -- walls, doors, and windows appear in the Revit 3D view on the left)*

**The audience watches the Revit 3D view go from empty to a full floor plan in seconds.**

**Agent responds:**

> Done. I've created the BIM model from the detected elements:
>
> - **35 walls** placed -- 12 exterior (2x6) and 23 interior (2x4)
> - **16 doors** inserted at detected locations
> - **8 windows** placed with correct sill and header heights
> - All walls at 8'-0" height per the framing notes
>
> The exterior walls are 2x6 for R-19 insulation per Arizona energy code.
> Interior partitions are standard 2x4. Everything is positioned based on
> the coordinates our AI extracted from the floor plan.
>
> Want me to analyze the walls and start generating the framing?

**Why this works**: The audience just watched an empty Revit model come to life from PDF data. This is the first "wow moment." The split screen makes it visceral -- they see the 3D view populate while the agent narrates.

**Presenter (optional, while walls appear):**

> "Watch the left side -- there go the walls. Doors are dropping in. Windows. All from the PDF we uploaded two minutes ago."

---

#### Exchange 2: Analyze + Generate Framing

**User says:**

```
Looks great. Let's go with 16" OC studs -- the shear walls call for 16" on
center anyway per the sheathing schedule. Go ahead and generate the framing
for all walls.
```

**[MCP tool call: `analyze_walls` -- reads the walls just created]**
*(Presenter hits RR)*

**[MCP tool call: `generate_framing` with `stud_spacing=16`]**
*(Presenter hits RR -- framing elements appear inside the walls in Revit)*

**Agent responds (based on tool results):**

> I've analyzed all 35 walls and generated the panelized framing at 16" OC.
> Here's the breakdown:
>
> - **621 framing elements** total
> - Studs: 398 | King studs: 48 | Trimmers: 48
> - Top plates: 70 | Bottom plates: 35 (split at door openings)
> - Headers: 24 | Sills: 8
> - Cripples (header + sill): 44
>
> Every wall has proper end studs, double top plates, and the bottom plates
> are split at door openings like they should be. Headers are sized per the
> framing plan -- (2)2x10 for standard openings, (2)2x12 for that large
> corner window.
>
> Want me to add the sheathing and generate the full fabrication package?

**Why this works**: The agent shows detailed knowledge of framing conventions (bottom plate splits at doors, end studs, header sizing from the actual plans). The audience can see the studs appearing inside the walls on the left side of the screen.

---

#### Exchange 3: Complete Pipeline -- Sheathing + Assemblies + Sheets

**User says:**

```
That looks right. Go ahead and generate the full package -- sheathing,
assemblies, and shop drawings. I want to see what the shop floor gets.
```

**Agent responds:**

> I'll run the complete pipeline now. This will:
> 1. Add sheathing layers -- 3/8" OSB exterior, 1/2" gypsum interior
> 2. Create panel assemblies with isolated views
> 3. Generate shop drawings with material schedules
>
> Give me about 30 seconds.

**[MCP tool call or staged HTTP calls for sheathing + assemblies + sheets]**
*(Presenter hits RR for each stage)*

**Agent responds when complete:**

> All done. Here's what I've created:
>
> - **35 wall panels**, each as a separate Revit Assembly
> - **70 sheathing panels** (2 layers per wall)
> - Each assembly has: plan view, front elevation, back elevation,
>   section, and a material schedule
> - **35 fabrication sheets** ready for print
>
> You can open any assembly in Revit to see the shop drawings.

---

## ACT 3: DELIVER (~3 minutes)

### Scene: Revit (full screen)

**Presenter maximizes Revit to full screen. The model is now fully populated with walls, openings, framing, and sheathing.**

> "Let's take a closer look at what the agent built."

**Step 3.1 -- 3D Overview**

*Orbit the 3D model. The audience already saw elements appear during ACT 2, but now they see the complete picture at full resolution.*

> "Every wall, door, and window from the PDF -- placed at the correct position and height. And inside every wall, the complete framing package."

**Step 3.2 -- Zoom into Framing**

*Zoom into a wall section. Toggle visibility to show framing elements.*

> "Now look inside a wall. Every stud, plate, header, trimmer, and cripple -- placed exactly where a framer would put them. 16 on center, double top plates, king studs at every opening."

*Point out specific elements: end studs, bottom plate split at a door, header cripples.*

**Step 3.3 -- Open an Assembly**

*Double-click a wall panel assembly to open it.*

> "Each wall is its own panel assembly. This is what your shop floor gets."

*Show the assembly views:*

> "Plan view -- shows the stud layout from above. Front elevation -- the face your sheathing team sees. Back elevation -- for the other side. Section cut -- shows the layers: gypsum, studs, OSB."

**Step 3.4 -- Material Schedule**

*Click on the material schedule in the assembly.*

> "And here's the cut list. Every piece of lumber identified -- type, size, quantity. Your saw operator can work directly from this."

**Step 3.5 -- Fabrication Sheet**

*Open a sheet view.*

> "This is a fabrication sheet, ready to print and hand to the production line. It has the panel elevation, the stud layout, the section, and the material schedule -- all on one page."

---

## CLOSE (30 seconds)

*Switch back to the agent conversation or show a summary slide.*

> "Let's recap what just happened. We started with a PDF and an empty Revit model. Our AI read the entire plan set, detected every wall, door, and window. Then an AI agent created the BIM model from scratch -- you watched those walls appear in real time. It generated panelized framing at 16 on center, added sheathing, created assemblies, and produced shop drawings. All in under 8 minutes."
>
> "No manual modeling. No back-and-forth with the architect. No estimator spending three days on takeoff. From a PDF to fabrication-ready panels in one session."
>
> "That's ConstructAI. Fabrication-level certainty from day one."

---

## Choreography Reference

### Behind-the-scenes timing

| Step | What audience sees | Screen layout | What happens behind scenes | Time |
|------|--------------------|---------------|----------------------------|------|
| 1.1 | PDF upload in web app | Web app (full) | Kreo API processes PDF (pre-baked) | 10s |
| 1.2 | Extraction chunks | Web app (full) | Pre-loaded WS1 data | 30s |
| 1.3 | Element detection overlay | Web app (full) | Pre-loaded Kreo results | 30s |
| 1.4 | Empty Revit model + schedules | **Split: Revit L + Agent R** | Transition to split screen | 20s |
| 2.1 | Walls/doors/windows appear in Revit | Split | MCP `create_walls` + RR | 15-20s |
| 2.2 | Framing appears inside walls | Split | MCP `analyze_walls` + `generate_framing` + RR | 20-30s |
| 2.3 | Agent narrates completion | Split | MCP/HTTP staged calls + RR per stage | 30-45s |
| 3.1 | Full 3D model orbit | **Revit (full)** | Maximize Revit | 30s |
| 3.2 | Framing close-up | Revit (full) | Toggle framing visibility | 30s |
| 3.3 | Assembly views | Revit (full) | Open panel assembly | 45s |
| 3.4 | Material schedule | Revit (full) | Click schedule in assembly | 20s |
| 3.5 | Shop drawing sheet | Revit (full) | Open sheet view | 20s |

### Screen Layout Transitions

```
ACT 1 (Steps 1.1-1.3)          ACT 1->2 Transition (Step 1.4)       ACT 2 (Steps 2.1-2.3)
+---------------------+        +-----------+-----------+             +-----------+-----------+
|                     |        |           |           |             |  Revit    |  Agent    |
|   Web App           |  --->  |  Revit    |  Agent    |   --->      |  (walls   |  (conv.)  |
|   (full screen)     |        |  (EMPTY)  |  (chat)   |             |  appear!) |           |
+---------------------+        +-----------+-----------+             +-----------+-----------+

ACT 3 (Steps 3.1-3.5)
+---------------------+
|                     |
|  Revit              |
|  (full screen)      |
+---------------------+
```

### RR Shortcut Protocol

Every MCP tool call requires a manual Revit Recompute (Swiftlet limitation under RiR):
1. User sends message in Claude Code / Claude Desktop
2. Agent calls MCP tool (request goes to Swiftlet)
3. Presenter hits **RR** in Revit (keyboard shortcut while Revit is on left side of split screen -- natural and barely noticeable)
4. GH recomputes, pipeline runs, Swiftlet returns result
5. Agent receives response, elements appear in Revit 3D view, agent continues conversation

**Key advantage of split screen**: Revit is on the left and already in focus. Hitting RR while Revit is visible looks completely natural -- no suspicious window switching. The audience's attention is on the agent (right side) while elements silently appear on the left.

**Practice this sequence until it's muscle memory.**

---

## Conversation Variants

### If the audience asks about wall thickness:

**User:** "How did you determine which walls are 2x4 vs 2x6?"

**Agent:** "The exterior walls in the model are defined as 2x6 framing with R-19 insulation -- that's standard for Arizona's climate zone and matches the spec on sheet GN-1.0. Interior partitions are 2x4 with R-13 where they separate living space from the garage, standard 2x4 elsewhere."

### If the audience asks about shear walls:

**User:** "What about the shear wall requirements?"

**Agent:** "The shear plan on sheet A-3.0 shows P1 sheathing panels -- that's 3/8" C-D plywood with 8d nails at 6" OC edges and 12" OC field, plus hold-downs at segment ends. The studs on shear walls are at 16" OC, which is what we're running. For the full shear wall integration, we'd add the blocking and hold-down connections as a separate pass."

### If the audience asks about panel sizes:

**User:** "How big are the panels? Can they fit on a truck?"

**Agent:** "Panels are currently decomposed at wall breaks -- door/window openings and wall intersections create natural panel boundaries. The longest panels are around 12-14 feet, well within standard transport limits. If your shop needs shorter panels for table size constraints, I can re-run with a maximum panel length -- say 8 feet."

### If something fails:

**Presenter (to audience):** "Let me pull up the model I generated earlier -- same project, same parameters."

*Open the pre-baked Revit file and continue from Act 3.*

---

## Key Talking Points

### For Builders
- "No more 3-day takeoffs. The AI reads the plans and builds the model."
- "Every panel is an assembly with its own cut list and shop drawing."
- "16 OC, double top plates, proper end studs, bottom plates split at doors -- it knows how to frame."
- "Headers sized from the actual framing plan, not guessed."

### For Investors
- "We automate the most expensive bottleneck in prefab: going from architect's plans to shop drawings."
- "The AI doesn't just detect geometry -- it understands construction. It knows a bottom plate splits at a door."
- "This is a 10x improvement in time-to-fabrication."

### For Tech Audience
- "The AI agent uses MCP (Model Context Protocol) to communicate with the Revit/Grasshopper pipeline."
- "Each tool call triggers a specific pipeline stage -- wall analysis, framing generation, assembly creation."
- "The framing engine uses a cell decomposition algorithm: walls break into Opening Cells, Stud Cells, Cripple Cells -- each with its own framing rules."

---

## Risk Mitigation

| Risk | Probability | Mitigation |
|------|------------|------------|
| MCP tool call hangs | Medium | RR shortcut. If still stuck, restart Swiftlet. Fallback: pre-baked model. |
| `create_walls` places geometry wrong | Medium | Pre-test with exact Kreo JSON. Verify wall positions match floor plan. Have backup. |
| Agent says something wrong | Low | Keep project context tight. Stick to scripted exchanges. |
| Revit crashes during bake | Medium | Use staged execution (analyze -> frame -> bake separately). Have backup file. |
| Audience asks about Kreo | Medium | "Our document understanding pipeline handles the extraction." Don't name third-party tools. |
| Pipeline produces wrong geometry | Low | Test with this exact project beforehand. Verify in rehearsal. |
| Slow response time | Medium | Narrate during waits: "Watch the left side -- walls are going up now..." |
| Split screen glitch | Low | Practice Win+Left/Win+Right transitions. Have backup screen layout saved. |
| Empty model not convincing | Low | Show wall schedule with zero rows, not just 3D view. Numbers don't lie. |
