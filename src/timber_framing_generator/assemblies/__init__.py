# File: src/timber_framing_generator/assemblies/__init__.py
"""Revit Assembly creation for prefab wall panels.

Groups framing elements and sheathing layers into Revit Assemblies
per panel, enabling prefabrication workflows with shop drawings and
material takeoffs.
"""

from src.timber_framing_generator.assemblies.assembly_creator import (
    PanelElementGroup,
    AssemblyResult,
    AssemblyBatchResult,
    group_elements_by_panel,
    create_assemblies,
)
from src.timber_framing_generator.assemblies.assembly_views import (
    AssemblyViewConfig,
    CreatedViewInfo,
    create_assembly_views,
)
from src.timber_framing_generator.assemblies.assembly_sheets import (
    SheetResult,
    create_assembly_sheet,
)

__all__ = [
    "PanelElementGroup",
    "AssemblyResult",
    "AssemblyBatchResult",
    "AssemblyViewConfig",
    "CreatedViewInfo",
    "SheetResult",
    "group_elements_by_panel",
    "create_assemblies",
    "create_assembly_views",
    "create_assembly_sheet",
]
