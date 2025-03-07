# File: src/wall_data/wall_selector.py

from Autodesk.Revit.DB import BuiltInCategory, Wall
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from RhinoInside.Revit import Revit

# Custom selection filter to allow only wall elements.
class WallSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        # Accept only wall elements (filter by category)
        return element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Walls)

    def AllowReference(self, ref, point):
        return True


def pick_walls_from_active_view():
    """
    Prompts the user to pick wall elements in the active view.

    Returns:
        List[Wall]: A list of Revit Wall elements selected by the user.
    """
    uidoc = Revit.ActiveUIDocument  # Use RhinoInside.Revit's active UIDocument
    try:
        # Use the custom filter to allow only walls.
        references = uidoc.Selection.PickObjects(
            ObjectType.Element, WallSelectionFilter(), "Select walls in the active view"
        )
    except Exception as e:
        print("Selection cancelled or error: {}".format(e))
        return []

    doc = uidoc.Document
    walls = []
    for ref in references:
        element = doc.GetElement(ref)
        if (
            element
            and element.Category
            and element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Walls)
        ):
            walls.append(element)
    return walls


if __name__ == "__main__":
    walls = pick_walls_from_active_view()
    print("Selected {} walls:".format(len(walls)))
    for wall in walls:
        print("Wall Id:", wall.Id)
