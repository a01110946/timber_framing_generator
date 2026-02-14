# PRP-032: Revit Assembly Creator for Prefab Wall Panels

> **Version:** 1.0
> **Created:** 2026-02-06
> **Status:** Draft
> **Branch:** feature/revit-assembly-creator

---

## Goal

Create a GHPython component that groups already-placed Revit framing elements and sheathing layers into **Revit Assemblies** per panel, enabling prefabrication workflows where each assembly represents a finished wall panel (framing + all compound layers) ready for shop drawings and factory-to-site transport.

## Why

- **Prefab workflow enabler**: Assemblies are the standard Revit mechanism for grouping elements into fabrication units with dedicated views and schedules
- **Shop drawing automation**: Each assembly gets its own plan, section, 3D view, and material takeoff -- eliminates manual drafting per panel
- **BOM and logistics**: Assembly schedules track panel counts, weights, and sequencing for production planning
- **Completes the pipeline**: The project already handles wall decomposition -> framing -> sheathing -> Revit baking. Assemblies are the final step that ties baked elements into deliverable units

## What

A new GHPython component (`gh_revit_assembly_creator.py`) that:

1. Receives Revit ElementIds of placed framing members and sheathing panels (from upstream RiR baking components)
2. Groups them by `panel_id` using `baking_data_json` as the mapping key
3. Creates one `AssemblyInstance` per panel via the Revit API
4. Optionally generates assembly views (3D, detail section, material takeoff)
5. Outputs assembly data as JSON for downstream scheduling/tracking

### Success Criteria

- [ ] Framing elements (studs, plates, headers, etc.) grouped correctly per panel_id
- [ ] Sheathing layers included in the same assembly as their parent panel's framing
- [ ] Each AssemblyInstance created with a meaningful name (e.g., `W1-P01`, `W1-P02`)
- [ ] Assembly views generated on demand (3D orthographic + front elevation at minimum)
- [ ] Walls without panelization create a single assembly per wall
- [ ] Component handles partial inputs gracefully (framing-only or sheathing-only)
- [ ] Unit tests pass for grouping logic (no Revit dependency)
- [ ] Integration test in Grasshopper creates valid assemblies

---

## All Needed Context

### Documentation & References

```yaml
Project Docs:
  - file: docs/ai/ai-modular-architecture-plan.md
    why: Overall pipeline architecture and component interaction patterns

  - file: docs/ai/ai-rir-revit-patterns.md
    why: Existing Revit API patterns (transactions, element placement, baking)

  - file: docs/ai/ai-development-guidelines.md
    why: Coding standards, type hints, docstrings format

Feature-Specific:
  - file: src/timber_framing_generator/families/revit_loader.py
    why: MIRROR THIS - Conditional Revit imports, transaction pattern, CPython3 __namespace__ gotcha

  - file: scripts/gh_revit_baker.py
    why: Upstream component - produces baking_data_json with element data organized by wall

  - file: src/timber_framing_generator/panels/panel_decomposer.py
    why: Panel ID assignment logic - how elements map to panels via u_coord

  - file: src/timber_framing_generator/core/json_schemas.py
    why: FramingElementData, PanelData schemas - panel_id field definitions

Revit API:
  - url: https://www.revitapidocs.com/2015/e0a37a7b-b157-b992-21d2-95f68cc76abd.htm
    why: AssemblyInstance.Create(doc, ICollection<ElementId>, namingCategoryId)

  - url: https://www.revitapidocs.com/2023/5dbf6f6d-dee0-d39c-c1b7-1a0f4fc385c8.htm
    why: AssemblyViewUtils methods (Create3DOrthographic, CreateDetailSection, etc.)
```

### Desired Structure (files to add/modify)

```bash
src/timber_framing_generator/
├── assemblies/                      # NEW MODULE
│   ├── __init__.py                  # Public API exports
│   ├── assembly_creator.py          # Core logic: group elements, create assemblies
│   └── assembly_views.py            # View creation utilities (3D, section, schedule)

scripts/
├── gh_revit_assembly_creator.py     # NEW GH component

tests/
├── assemblies/                      # NEW
│   ├── __init__.py
│   ├── test_element_grouping.py     # Unit tests for panel->element grouping
│   └── test_assembly_creator.py     # Tests with mocked Revit API
```

### Data Flow: Where This Component Fits

```
[Wall Analyzer] -> walls_json
    |
[Panel Decomposer] -> panels_json (defines panel boundaries)
    |
[Framing Generator] -> framing_json (elements with panel_id)
    |
[Family Resolver] -> resolved_json (enriched with revit_family/revit_type)
    |
[Revit Baker] -> baking_data_json (element data organized by wall)
    |                |
    |    [RiR Add Structural Column] -> column_element_ids  --|
    |    [RiR Add Structural Framing] -> beam_element_ids   --|
    |                                                          |
[Multi-Layer Sheathing] -> sheathing panels                    |
    |                                                          |
    |    [RiR Bake Sheathing] -> sheathing_element_ids --------|
    |                                                          |
    v                                                          v
[THIS COMPONENT: Assembly Creator]
    Inputs: baking_data_json + panels_json + element_ids (from RiR)
    Output: assembly_json (created assembly data)
```

### Key Architectural Decision: ElementId Collection Strategy

The Assembly Creator receives **Revit ElementIds** from the RiR baking components that place elements into the Revit model. These come as GH DataTree outputs from:
- "Add Structural Column" component -> column ElementIds
- "Add Structural Framing" component -> beam ElementIds
- Sheathing baking component -> sheathing ElementIds

The `baking_data_json` from `gh_revit_baker.py` provides the `panel_id` mapping. The component must correlate:
- `baking_data_json.walls[wall_id].members[i].geometry_index` -> position in the RiR output DataTree
- `panels_json[panel_id].element_ids` -> which framing elements belong to which panel
- Sheathing ElementIds -> matched to panels via panel_id in the sheathing data

### Known Gotchas & Library Quirks

```python
# CRITICAL: AssemblyInstance.Create requires TWO separate transactions
# Transaction 1: Create the assembly (commit immediately)
# Transaction 2: Rename, set parameters, create views
# The assembly type is only assigned AFTER Transaction 1 commits
# Attempting to modify the assembly in the same transaction will FAIL

# CRITICAL: CPython3 interface implementation
# If implementing any .NET interface, MUST add __namespace__ class attribute
# See revit_loader.py FamilyLoadOptions pattern

# CRITICAL: ICollection<ElementId> from Python
# Use System.Collections.Generic.List[ElementId]() to create the collection
# Python lists do NOT auto-convert to ICollection<ElementId>
from System.Collections.Generic import List as NetList
element_id_list = NetList[ElementId]()
for eid in python_list:
    element_id_list.Add(eid)

# CRITICAL: namingCategoryId parameter
# Use the category of the primary element type (OST_StructuralFraming for timber/CFS)
# This determines how the assembly appears in Revit's browser and schedules

# CRITICAL: Rhino 8 cp1252 encoding
# NEVER use unicode arrows, bullets, or symbols in logger messages
# Use ASCII: -> instead of →, * instead of •

# CRITICAL: GHPython NickName injection is UNRELIABLE
# ALWAYS read inputs by parameter index, not by variable name
# Call setup_component() inside main() for display only, AFTER inputs are captured
```

---

## Implementation Blueprint

### Data Models

```python
# File: src/timber_framing_generator/assemblies/assembly_creator.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class PanelElementGroup:
    """Groups Revit ElementIds belonging to a single panel."""
    panel_id: str
    wall_id: str
    panel_index: int
    column_element_ids: List[Any] = field(default_factory=list)   # Revit ElementId objects
    beam_element_ids: List[Any] = field(default_factory=list)
    sheathing_element_ids: List[Any] = field(default_factory=list)

    @property
    def all_element_ids(self) -> List[Any]:
        """All ElementIds for this panel (framing + sheathing)."""
        return self.column_element_ids + self.beam_element_ids + self.sheathing_element_ids

    @property
    def element_count(self) -> int:
        return len(self.all_element_ids)

    @property
    def is_empty(self) -> bool:
        return self.element_count == 0


@dataclass
class AssemblyResult:
    """Result of creating a single assembly."""
    panel_id: str
    wall_id: str
    assembly_name: str
    assembly_id: Optional[int] = None       # Revit ElementId as int
    element_count: int = 0
    views_created: List[str] = field(default_factory=list)
    status: str = "pending"                 # pending | created | failed
    error: Optional[str] = None


@dataclass
class AssemblyBatchResult:
    """Result of creating all assemblies for a batch."""
    results: List[AssemblyResult] = field(default_factory=list)
    total_assemblies: int = 0
    successful: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assemblies": [
                {
                    "panel_id": r.panel_id,
                    "wall_id": r.wall_id,
                    "assembly_name": r.assembly_name,
                    "assembly_id": r.assembly_id,
                    "element_count": r.element_count,
                    "views_created": r.views_created,
                    "status": r.status,
                    "error": r.error,
                }
                for r in self.results
            ],
            "summary": {
                "total": self.total_assemblies,
                "successful": self.successful,
                "failed": self.failed,
            },
        }
```

### Tasks (in execution order)

```yaml
Task 1: Create assemblies module with element grouping logic
  - CREATE: src/timber_framing_generator/assemblies/__init__.py
  - CREATE: src/timber_framing_generator/assemblies/assembly_creator.py
  - Contains: PanelElementGroup, AssemblyResult, AssemblyBatchResult dataclasses
  - Contains: group_elements_by_panel() - pure Python logic, no Revit dependency
  - Contains: create_assemblies() - Revit API calls behind REVIT_AVAILABLE guard
  - MIRROR pattern from: src/timber_framing_generator/families/revit_loader.py
    (conditional imports, transaction management, error handling)

Task 2: Create assembly views utility
  - CREATE: src/timber_framing_generator/assemblies/assembly_views.py
  - Contains: create_assembly_views() using AssemblyViewUtils
  - Supports: 3D orthographic, detail section (front elevation), material takeoff
  - Each view type is optional and configurable

Task 3: Create GH component
  - CREATE: scripts/gh_revit_assembly_creator.py
  - FOLLOW template: ~/.claude/skills/grasshopper-python-assistant/templates/ghpython_component.py
  - Inputs: baking_data_json, panels_json, column_ids, beam_ids, sheathing_ids,
            naming_prefix, create_views, run
  - Outputs: assembly_json, assembly_ids, info
  - Uses setup_component() for metadata, reads inputs by parameter index

Task 4: Write unit tests for element grouping
  - CREATE: tests/assemblies/__init__.py
  - CREATE: tests/assemblies/test_element_grouping.py
  - Tests: group_elements_by_panel() with various panel configurations
  - Tests: edge cases (no panels, single panel, missing elements, empty panels)
  - No Revit dependency needed

Task 5: Write tests for assembly creator with mocked Revit API
  - CREATE: tests/assemblies/test_assembly_creator.py
  - Tests: Assembly naming convention
  - Tests: Error handling (failed transactions, invalid ElementIds)
  - Tests: Batch result aggregation
  - Mock Revit API classes where needed
```

### Pseudocode (with CRITICAL details)

```python
# =============================================================================
# Task 1: assembly_creator.py - Element Grouping (Pure Python)
# =============================================================================

def group_elements_by_panel(
    baking_data_json: str,
    panels_json: str,
    column_ids: list,
    beam_ids: list,
    sheathing_ids: Optional[list] = None,
    sheathing_data_json: Optional[str] = None,
) -> List[PanelElementGroup]:
    """Group Revit ElementIds by panel_id.

    Strategy:
    1. Parse baking_data_json to get element -> geometry_index mapping
    2. Parse panels_json to get panel_id -> element_ids mapping
    3. For each panel, collect the corresponding Revit ElementIds
       by matching geometry_index to position in column_ids/beam_ids lists
    4. Add sheathing ElementIds by matching panel_id in sheathing data

    Args:
        baking_data_json: From gh_revit_baker.py (has geometry_index per member)
        panels_json: From panel decomposer (has panel_id -> element mapping)
        column_ids: Revit ElementIds from RiR "Add Structural Column" (flat list)
        beam_ids: Revit ElementIds from RiR "Add Structural Framing" (flat list)
        sheathing_ids: Optional Revit ElementIds from sheathing baking
        sheathing_data_json: Optional JSON mapping sheathing elements to panels

    Returns:
        List of PanelElementGroup, one per panel
    """
    baking_data = json.loads(baking_data_json)
    panels_data = json.loads(panels_json)

    # Build index: element_id_str -> (classification, geometry_index)
    element_index = {}
    for wall_id, wall_data in baking_data.get("walls", {}).items():
        for member in wall_data.get("members", []):
            element_index[member["id"]] = {
                "classification": member["classification"],  # "column" or "beam"
                "geometry_index": member["geometry_index"],
                "panel_id": member.get("panel_id"),
            }

    # Build panel groups
    groups = []
    for panel in panels_data:
        panel_id = panel["id"]
        wall_id = panel["wall_id"]
        panel_index = panel["panel_index"]

        group = PanelElementGroup(
            panel_id=panel_id,
            wall_id=wall_id,
            panel_index=panel_index,
        )

        # Collect framing ElementIds for this panel
        for elem_id_str in panel.get("element_ids", []):
            info = element_index.get(elem_id_str)
            if not info:
                continue
            idx = info["geometry_index"]
            if info["classification"] == "column" and idx < len(column_ids):
                group.column_element_ids.append(column_ids[idx])
            elif info["classification"] == "beam" and idx < len(beam_ids):
                group.beam_element_ids.append(beam_ids[idx])

        # Collect sheathing ElementIds for this panel
        if sheathing_ids and sheathing_data_json:
            sheathing_data = json.loads(sheathing_data_json)
            for i, spanel in enumerate(sheathing_data.get("panels", [])):
                if spanel.get("panel_id") == panel_id and i < len(sheathing_ids):
                    group.sheathing_element_ids.append(sheathing_ids[i])

        if not group.is_empty:
            groups.append(group)

    return groups


# =============================================================================
# Task 1 continued: Revit Assembly Creation
# =============================================================================

def create_assemblies(
    doc,
    groups: List[PanelElementGroup],
    naming_prefix: str = "W",
    naming_category_id=None,
    create_views: bool = False,
) -> AssemblyBatchResult:
    """Create Revit AssemblyInstances from grouped elements.

    CRITICAL: Two-transaction pattern required.
    Transaction 1: AssemblyInstance.Create() + commit
    Transaction 2: Rename assembly type + create views
    """
    if not REVIT_AVAILABLE:
        logger.error("Revit API not available")
        return AssemblyBatchResult()

    from System.Collections.Generic import List as NetList

    # Default naming category: Structural Framing
    if naming_category_id is None:
        naming_category_id = ElementId(
            BuiltInCategory.OST_StructuralFraming
        )

    batch = AssemblyBatchResult()
    batch.total_assemblies = len(groups)

    for group in groups:
        result = AssemblyResult(
            panel_id=group.panel_id,
            wall_id=group.wall_id,
            assembly_name=_generate_assembly_name(
                group.wall_id, group.panel_index, naming_prefix
            ),
            element_count=group.element_count,
        )

        try:
            # Build .NET List<ElementId>
            id_list = NetList[ElementId]()
            for eid in group.all_element_ids:
                id_list.Add(eid)

            # Transaction 1: Create assembly
            t1 = Transaction(doc, f"Create Assembly: {result.assembly_name}")
            t1.Start()
            try:
                assembly = AssemblyInstance.Create(doc, id_list, naming_category_id)
                t1.Commit()
            except Exception as e:
                if t1.HasStarted():
                    t1.RollBack()
                raise

            # Transaction 2: Rename + views (assembly type exists NOW)
            t2 = Transaction(doc, f"Configure Assembly: {result.assembly_name}")
            t2.Start()
            try:
                # Rename assembly type
                assembly_type_id = assembly.GetTypeId()
                assembly_type = doc.GetElement(assembly_type_id)
                if assembly_type:
                    assembly_type.Name = result.assembly_name

                # Create views if requested
                if create_views:
                    result.views_created = create_assembly_views(
                        doc, assembly.Id
                    )

                t2.Commit()
            except Exception as e:
                if t2.HasStarted():
                    t2.RollBack()
                raise

            result.assembly_id = assembly.Id.IntegerValue
            result.status = "created"
            batch.successful += 1

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            batch.failed += 1
            logger.error("Failed to create assembly '%s': %s",
                        result.assembly_name, e)

        batch.results.append(result)

    return batch


def _generate_assembly_name(
    wall_id: str, panel_index: int, prefix: str = "W"
) -> str:
    """Generate assembly name like W1-P01, W2-P03.

    Extracts wall number from wall_id (e.g., "wall_1" -> 1).
    """
    # Extract numeric part from wall_id
    import re
    match = re.search(r'(\d+)', wall_id)
    wall_num = int(match.group(1)) if match else 0
    return f"{prefix}{wall_num}-P{panel_index + 1:02d}"


# =============================================================================
# Task 2: assembly_views.py
# =============================================================================

def create_assembly_views(
    doc,
    assembly_id,
    include_3d: bool = True,
    include_front_elevation: bool = True,
    include_material_takeoff: bool = True,
) -> List[str]:
    """Create standard assembly views.

    CRITICAL: Must be called AFTER the assembly creation transaction is committed.
    """
    from Autodesk.Revit.DB import AssemblyViewUtils, AssemblyDetailViewOrientation

    created = []

    if include_3d and AssemblyViewUtils.IsValidForAssemblyView(doc, assembly_id):
        view_3d = AssemblyViewUtils.Create3DOrthographic(doc, assembly_id)
        if view_3d:
            created.append("3D Orthographic")

    if include_front_elevation:
        view_front = AssemblyViewUtils.CreateDetailSection(
            doc, assembly_id,
            AssemblyDetailViewOrientation.ElevationFront
        )
        if view_front:
            created.append("Front Elevation")

    if include_material_takeoff:
        view_takeoff = AssemblyViewUtils.CreateMaterialTakeoff(
            doc, assembly_id
        )
        if view_takeoff:
            created.append("Material Takeoff")

    return created
```

### Integration Points

```yaml
CONFIG:
  - No new config parameters needed (assembly naming is input-driven)

IMPORTS:
  - file: src/timber_framing_generator/assemblies/__init__.py
  - exports: group_elements_by_panel, create_assemblies, PanelElementGroup,
             AssemblyResult, AssemblyBatchResult

GRASSHOPPER:
  - file: scripts/gh_revit_assembly_creator.py
  - pattern: New component, sits after Revit Baker + RiR baking components
  - inputs: baking_data_json (str), panels_json (str),
            column_ids (List<ElementId>), beam_ids (List<ElementId>),
            sheathing_ids (List<ElementId>, optional),
            sheathing_data_json (str, optional),
            naming_prefix (str, default "W"),
            create_views (bool, default False),
            run (bool)
  - outputs: assembly_json (str), assembly_ids (list), info (str)

UPSTREAM DEPENDENCIES:
  - gh_revit_baker.py -> baking_data_json (element mapping with geometry_index)
  - gh_panel_decomposer.py -> panels_json (panel boundaries and element lists)
  - RiR "Add Structural Column" -> column ElementIds
  - RiR "Add Structural Framing" -> beam ElementIds
  - RiR sheathing baking -> sheathing ElementIds (optional)
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
cd "C:\Users\Fernando Maytorena\OneDrive\Documentos\GitHub\timber_framing_generator"

# Linting
ruff check src/timber_framing_generator/assemblies/

# Type checking
mypy src/timber_framing_generator/assemblies/
```

### Level 2: Unit Tests

```bash
# Element grouping tests (no Revit needed)
pytest tests/assemblies/test_element_grouping.py -v

# Assembly creator tests (mocked Revit)
pytest tests/assemblies/test_assembly_creator.py -v

# All tests (ensure no regressions)
pytest tests/ -v
```

### Level 3: Integration Test (Grasshopper)

```bash
# Manual test in Grasshopper:
# 1. Open Rhino + Grasshopper with Rhino.Inside.Revit
# 2. Run full pipeline: Wall Analyzer -> Panel Decomposer -> Framing Generator
#    -> Family Resolver -> Revit Baker -> RiR baking components
# 3. Connect baking_data_json, panels_json, and ElementId outputs to Assembly Creator
# 4. Set create_views = True
# 5. Set run = True
# 6. Verify in Revit:
#    - Assemblies appear in Project Browser under Assemblies
#    - Each assembly contains the correct framing + sheathing elements
#    - Assembly views are created (3D, section, takeoff)
#    - Disassembling returns elements to their original state
```

---

## Final Checklist

- [ ] All unit tests pass: `pytest tests/assemblies/ -v`
- [ ] No linting errors: `ruff check src/timber_framing_generator/assemblies/`
- [ ] No type errors: `mypy src/timber_framing_generator/assemblies/`
- [ ] Full test suite passes: `pytest tests/ -v`
- [ ] GH component follows mandatory template structure
- [ ] Inputs read by parameter index (not NickName globals)
- [ ] No unicode characters in logger messages
- [ ] Transaction pattern: two separate transactions (create then configure)
- [ ] Conditional Revit imports with REVIT_AVAILABLE guard
- [ ] Walls without panels create single assembly per wall
- [ ] Empty panels are skipped gracefully
- [ ] assembly_json output is valid JSON
- [ ] Integration test in Grasshopper creates valid Revit assemblies

---

## Anti-Patterns to Avoid

- Do NOT modify the assembly in the same transaction that creates it (type assignment happens after commit)
- Do NOT pass Python list directly to AssemblyInstance.Create (must use System.Collections.Generic.List[ElementId])
- Do NOT assume ElementIds arrive in the same order as baking_data members (use geometry_index mapping)
- Do NOT create assembly views before the creation transaction is committed
- Do NOT use unicode characters in log messages (cp1252 encoding in Rhino 8)
- Do NOT read GH inputs by NickName-based globals (read by parameter index)
- Do NOT skip the REVIT_AVAILABLE guard on any Revit API call

---

## Notes

- The two-transaction pattern for assemblies is a well-known Revit API requirement documented in the official API guide and Building Coder blog
- Assembly naming follows the convention `{prefix}{wall_num}-P{panel_num}` (e.g., W1-P01) which aligns with common prefab panel labeling
- View creation is optional since it adds processing time and may not be needed during iterative development
- If panels_json is not provided (non-panelized walls), the component should fall back to creating one assembly per wall using all elements from that wall's baking data
- Future enhancement: Assembly sheet creation with automatic view placement for shop drawing packages
