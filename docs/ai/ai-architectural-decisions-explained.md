# Architectural Decisions - Detailed Explanation

This document explains the open architectural questions for the offsite framing system, providing context and implications for each decision.

---

## 1. Truss vs. Stick-Built Roofs

### What Are They?

**Stick-Built (Rafter) Roofs:**
Individual framing members cut and assembled on-site (or in-panel for offsite):
- **Rafters**: Sloped members from wall plate to ridge
- **Ridge board/beam**: Horizontal member at roof peak
- **Collar ties**: Horizontal members connecting opposing rafters
- **Ceiling joists**: Horizontal members for ceiling attachment
- **Hip/Valley rafters**: For complex roof shapes

```
Stick-Built Cross Section:

           /\           ← Ridge board
          /  \
         /    \         ← Rafters
        /______\        ← Collar tie
       /        \
      /          \
     /____________\     ← Top plate (wall)
     |            |
```

**Pre-Engineered Trusses:**
Factory-manufactured triangulated assemblies:
- Designed by truss manufacturer's engineer
- Use smaller lumber with metal connector plates
- Delivered as complete units
- Installed as single pieces spanning wall-to-wall

```
Truss Cross Section:

           /\           ← Top chord
          /  \
         /\  /\         ← Web members (diagonal)
        /__\/__\
       /        \       ← Bottom chord
      /          \
     /____________\     ← Bearing point (wall)
```

### Implications for Our System

| Aspect | Stick-Built | Pre-Engineered Truss |
|--------|-------------|---------------------|
| **What we generate** | Individual rafters, ridge, collar ties | Just the truss envelope/placement |
| **Engineering** | We calculate sizes and spacing | Truss company provides design |
| **Geometry complexity** | High (each member positioned) | Low (just truss outlines) |
| **Offsite fit** | Perfect (we control all pieces) | Trusses usually site-delivered |
| **MEP routing** | Through rafter bays | Through truss webs (more complex) |
| **Data from Revit** | Roof boundary, slope, overhangs | Truss family placement |

### Recommendation

**Start with stick-built rafters** because:
1. Matches our wall framing pattern (individual members in cells)
2. Better fit for panelized offsite construction
3. Simpler MEP penetration logic
4. Can add truss support later as "pass-through" (just locate them, don't detail them)

---

## 2. Floor System Types

### What Are They?

**Platform Framing (Most Common in North America):**
Each floor is a complete platform; walls sit on top of the subfloor.

```
Platform Framing:

    ═══════════════════  ← 2nd floor subfloor
    ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐  ← 2nd floor joists
    ═══════════════════  ← Rim board
    │ │ │ │ │ │ │ │ │ │  ← 1st floor walls (on subfloor)
    ═══════════════════  ← 1st floor subfloor
    ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐  ← 1st floor joists
    ═══════════════════  ← Rim board / sill plate
    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ← Foundation
```

**Balloon Framing (Historic, Rare Today):**
Studs run continuously from foundation to roof; floors hang off studs.

```
Balloon Framing:

    │ │         │ │      ← Continuous studs (2+ stories)
    │ │ ┌─┐ ┌─┐ │ │      ← 2nd floor joists (nailed to studs)
    │ │ └─┘ └─┘ │ │
    │ │         │ │
    │ │ ┌─┐ ┌─┐ │ │      ← 1st floor joists
    │ │ └─┘ └─┘ │ │
    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    ← Foundation
```

**Engineered I-Joist Systems:**
Manufactured joists with OSB web and LVL flanges; deeper spans, lighter weight.

```
I-Joist Cross Section:

    ════════  ← Top flange (LVL or solid wood)
       │
       │      ← OSB or plywood web
       │
    ════════  ← Bottom flange (LVL or solid wood)
```

**Open-Web Floor Trusses:**
Similar concept to roof trusses but for floors; allows MEP to pass through webs.

```
Open-Web Floor Truss:

    ══════════════════════  ← Top chord
      \    /\    /\    /
       \  /  \  /  \  /     ← Diagonal webs (open space for MEP)
        \/    \/    \/
    ══════════════════════  ← Bottom chord
```

### Implications for Our System

| Aspect | Platform (Solid Joist) | I-Joist | Open-Web Truss |
|--------|------------------------|---------|----------------|
| **Cell decomposition** | Joist bays (like stud cells) | Same pattern | Same pattern |
| **Profile definition** | Standard lumber (2x10, 2x12) | Manufacturer-specific | Manufacturer-designed |
| **MEP routing** | Drill through joists (limited) | Knockouts in web | Pass through webs (easy) |
| **Blocking pattern** | Solid blocking between joists | Squash blocks at bearings | Varies |
| **Offsite fit** | Excellent | Good | Trusses often site-delivered |

### Recommendation

**Start with platform framing using solid lumber joists** because:
1. Most similar to wall framing logic (parallel members at spacing)
2. Standard profiles we already support (2x10, 2x12)
3. Common in residential offsite construction
4. Can add I-joist support as profile type later

---

## 3. MEP Connection Points

### The Question

When we route a pipe from a plumbing fixture, where does it go?

### Options

**Option A: Route to Wall Face (Stub-Out)**
Pipe goes from fixture connector horizontally to nearest wall, stops at wall face.

```
Plan View:

    ┌─────────────────────┐
    │                     │
    │    ┌───┐            │
    │    │WC │────────────┼──  ← Stub-out at wall face
    │    └───┘            │
    │                     │
    └─────────────────────┘
```

**Pros:**
- Simple routing logic
- Clear interface between trades
- Panel can be fabricated without knowing main line locations

**Cons:**
- Doesn't show complete system
- Requires field connection

**Option B: Route to Main Line Location**
Pipe goes from fixture to a main line (vertical stack or horizontal main).

```
Section View:

    Roof Vent ↑
         │
         │  ← Vent stack
    ┌────┼────┐
    │    │    │  2nd Floor
    │ ┌──┴──┐ │
    │ │ WC  │ │────┐
    │ └─────┘ │    │ ← Branch to stack
    ├─────────┤    │
    │    │    │    │
    │ ┌──┴──┐ │    │  1st Floor
    │ │Sink │─┼────┤
    │ └─────┘ │    │
    └─────────┘    │
         │         │
         ▼         ▼
    To Sewer   Drain Stack
```

**Pros:**
- Complete system visualization
- Enables system analysis (venting, sizing)

**Cons:**
- Need to know main line locations
- More complex routing
- Cross-panel coordination

**Option C: Route to Configurable Target Points**
User defines target points (could be wall face, stack location, or custom).

```
Grasshopper Setup:

    [Fixture Connectors] ──┐
                          ├──► [MEP Router] ──► Routes
    [Target Points]    ───┘
         │
         ├── Wall stub points (auto-generated)
         ├── Stack locations (user-defined)
         └── Main line paths (user-defined)
```

### Recommendation

**Start with Option A (wall stub-out)** for Phase 2, then expand:

1. **Phase 2**: Route to nearest wall face (simple, useful)
2. **Phase 3**: Add configurable target points
3. **Future**: Full system routing with stacks and mains

This gives immediate value while building toward complete systems.

---

## 4. Panel Joint Strategy

### The Question

How do we divide a long wall (or floor/roof) into shippable panel sizes?

### Options

**Fixed Grid Joints:**
Panels are fixed sizes (e.g., 8', 10', 12' max), joints at regular intervals.

```
40' Wall with Fixed 10' Grid:

    ┌──────────┬──────────┬──────────┬──────────┐
    │  Panel 1 │  Panel 2 │  Panel 3 │  Panel 4 │
    │   10'    │   10'    │   10'    │   10'    │
    └──────────┴──────────┴──────────┴──────────┘
         │          │          │          │
       Joint      Joint      Joint     (end)
```

**Pros:**
- Simple logic
- Predictable panel sizes
- Easier production planning

**Cons:**
- Joint might land on a window/door
- Might cut through MEP routes
- Doesn't optimize for structural efficiency
- May create awkward small panels at ends

**Optimized Irregular Joints:**
Joints placed intelligently to avoid openings, MEP, and minimize waste.

```
40' Wall with 6' Window:

Fixed Grid (Problem):
    ┌──────────┬──────────┬──────────┬──────────┐
    │          │   ┌──────┼──┐       │          │
    │          │   │Window│xx│ ← Joint through window!
    │          │   └──────┼──┘       │          │
    └──────────┴──────────┴──────────┴──────────┘

Optimized (Solution):
    ┌────────┬────────────────┬──────────────────┐
    │        │    ┌──────┐    │                  │
    │  8'    │    │Window│    │       16'        │
    │        │    └──────┘    │                  │
    └────────┴────────────────┴──────────────────┘
              ↑                ↑
         Joint before      Joint after
         window            window
```

**Pros:**
- Avoids cutting through openings
- Avoids MEP penetration locations
- Can align with stud locations
- Structural integrity maintained

**Cons:**
- More complex algorithm
- Variable panel sizes
- Harder production scheduling

### Recommendation

**Implement optimized joints** because:
1. Fixed grid is too naive (will hit openings constantly)
2. The optimization rules are straightforward:
   - Never cut through openings
   - Prefer joints at stud locations
   - Respect max panel size constraint
   - Avoid MEP penetration zones
3. Variable panel sizes are normal in offsite construction

---

## 5. Code Compliance

### The Question

How much building code checking should the system perform?

### User's Decision

**Leave to engineers, make configurable.**

### Implementation Approach

```python
# Configuration-driven approach

framing_config = {
    # Stud spacing - engineer sets based on code/loads
    "stud_spacing": 16,  # inches OC (could be 12, 16, 24)

    # Header sizing - engineer specifies or we provide lookup
    "header_sizing_mode": "user_specified",  # or "auto_lookup"
    "header_sizes": {
        "up_to_4ft": "2x6",
        "4ft_to_6ft": "2x8",
        "6ft_to_8ft": "2x10",
    },

    # MEP penetration rules - engineer sets limits
    "max_hole_diameter_ratio": 0.4,  # Max hole = 40% of joist depth
    "min_edge_distance": 2.0,  # inches from edge
    "min_hole_spacing": 2.0,  # inches between holes

    # Panel constraints - based on shipping/handling
    "max_panel_length": 12.0,  # feet
    "max_panel_weight": 2000,  # lbs
}
```

### What We Provide vs. What Engineers Decide

| Aspect | System Provides | Engineer Configures |
|--------|-----------------|---------------------|
| **Stud generation** | Geometry at specified spacing | Spacing value, profile size |
| **Header generation** | Geometry at specified size | Size for each span range |
| **MEP penetrations** | Holes at calculated locations | Max size, edge distance rules |
| **Panel joints** | Optimized locations | Max panel size, weight limits |
| **Profiles** | Catalog of standard sizes | Which sizes for which elements |

This keeps the system flexible while ensuring engineering judgment drives the design.

---

## 6. Level of Detail (LOD)

### What Is LOD?

Level of Detail/Development describes how much information is in the model:

| LOD | Name | Description |
|-----|------|-------------|
| **100** | Conceptual | Overall mass/volume, no detail |
| **200** | Schematic | Approximate geometry, generic elements |
| **300** | Design Development | Accurate geometry, specific elements |
| **350** | Construction Documentation | Accurate with detailing for construction |
| **400** | Fabrication | Precise for manufacturing/assembly |
| **500** | As-Built | Verified field conditions |

### Our Current Level of Detail

Based on my understanding of the codebase, we're currently at **LOD 300-350**:

**What We Generate:**

```
✓ Accurate centerlines for all framing members
✓ Correct profiles assigned (2x4, 2x6, 350S162-54, etc.)
✓ Proper positioning (stud spacing, plate locations)
✓ Opening framing (headers, sills, king studs, trimmers, cripples)
✓ Blocking at specified heights
✓ Material-specific geometry (timber vs CFS)
```

**What We DON'T Generate (Yet):**

```
✗ Connections (nails, screws, brackets, straps)
✗ Fastener schedules
✗ Sheathing panels with nailing patterns
✗ Hold-down locations
✗ Simpson ties and connectors
✗ Precise end cuts (bird's mouth, etc.)
✗ CNC-ready geometry (with tool paths)
```

### Visual Comparison

```
LOD 300 (Current - Schematic Framing):
┌────────────────────────────────────┐
│ ══════════════════════════════════ │ ← Top plate (solid member)
│ │  │  │  │  │  │  │  │  │  │  │  │ │ ← Studs (solid members)
│ │  │  │  │  ╔══╗  │  │  │  │  │  │ │
│ │  │  │  │  ║  ║  │  │  │  │  │  │ │ ← Header (solid)
│ │  │  │  │  ║  ║  │  │  │  │  │  │ │
│ │  │  │  │  ║  ║  │  │  │  │  │  │ │
│ ══════════════════════════════════ │ ← Bottom plate
└────────────────────────────────────┘

LOD 400 (Fabrication - Connection Detail):
┌────────────────────────────────────┐
│ ══════════════════════════════════ │ ← Top plate
│ ○│○ ○│○ ○│○ ╔══╗○ ○│○ ○│○ ○│○ ○│○ │ ← Nails at each stud (○)
│  │   │   │  ║  ║   │   │   │   │  │
│  │   │   │  ║HH║   │   │   │   │  │ ← Header with hanger (HH)
│  │   │   │T ║  ║ T│   │   │   │  │ ← Trimmers with tie (T)
│  │   │   │  ╚══╝   │   │   │   │  │
│ ○│○ ○│○ ○│○      ○│○ ○│○ ○│○ ○│○ │ ← Nails at bottom
│ ══════════════════════════════════ │ ← Bottom plate
│ [A]              [A]           [A] │ ← Anchor bolts (A)
└────────────────────────────────────┘
```

### Implications

**For MEP Integration:**
Our current LOD 300-350 is sufficient - we generate accurate framing geometry that MEP can route through.

**For Offsite Fabrication:**
To be truly fabrication-ready (LOD 400), we'd eventually need:
1. Connection hardware specification
2. Fastener schedules
3. Sheathing layout with nailing patterns
4. CNC-compatible geometry export

### Recommendation

**Stay at LOD 300-350 for now**, with a path to LOD 400:
1. Current LOD enables MEP routing and visualization
2. Add connection details as a future phase
3. CNC export can be a specialized output module

---

## Summary of Decisions Needed

| Question | Options | Recommendation |
|----------|---------|----------------|
| **1. Roof framing** | Stick-built vs Trusses | Start with stick-built rafters |
| **2. Floor system** | Platform vs Balloon vs I-joist | Start with platform + solid joists |
| **3. MEP termination** | Wall face vs Main line vs Configurable | Start with wall stub-out |
| **4. Panel joints** | Fixed grid vs Optimized | Implement optimized joints |
| **5. Code compliance** | Built-in vs Engineer config | **DECIDED: Engineer configures** |
| **6. Level of detail** | Current is LOD 300-350 | Sufficient for MEP; add connections later |

---

## Next Steps

Once you confirm these decisions, I can:
1. Update the architecture document with final decisions
2. Begin implementing MEP connector extraction (Phase 2)
3. Create the first GHPython component for plumbing fixture analysis
