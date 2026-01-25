# MEP Connectors Reference

Learnings from researching Revit MEP connectors for plumbing fixtures, HVAC, and electrical systems.

---

## What Are Connectors?

Connectors are **special MEP elements** defined within Revit families that represent physical connection points. They are NOT parameters - they are geometric entities with position, direction, and system information.

**Key Characteristics:**
- Created in the family document (Family Editor)
- Exposed on placed instances via API
- Define where pipes/ducts/conduits can connect
- Carry flow, sizing, and system type information
- Enable Revit's automatic routing and system analysis

---

## Accessing Connectors via Revit API

### For FamilyInstance (Fixtures, Fittings, Equipment)

```python
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

# For plumbing fixtures, mechanical equipment, fittings, etc.
family_instance = element  # A FamilyInstance

# Access path: FamilyInstance → MEPModel → ConnectorManager → Connectors
mep_model = family_instance.MEPModel
if mep_model is not None:
    connector_manager = mep_model.ConnectorManager
    if connector_manager is not None:
        connector_set = connector_manager.Connectors
        for connector in connector_set:
            # Process each connector
            pass
```

### For MEPCurve (Pipes, Ducts, Conduits)

```python
# For pipes, ducts, cable trays, conduits, etc.
mep_curve = element  # A Pipe, Duct, Conduit, etc.

# Access path: MEPCurve → ConnectorManager → Connectors
connector_manager = mep_curve.ConnectorManager
if connector_manager is not None:
    connector_set = connector_manager.Connectors
    for connector in connector_set:
        # Process each connector
        pass
```

### For FabricationPart

```python
# For fabrication parts
fab_part = element  # A FabricationPart

# Access path: FabricationPart → ConnectorManager → Connectors
connector_manager = fab_part.ConnectorManager
```

---

## Connector Properties

### Position and Orientation

| Property | Type | Description |
|----------|------|-------------|
| `Connector.Origin` | `XYZ` | Position in model coordinates (feet) |
| `Connector.CoordinateSystem` | `Transform` | Full coordinate system |
| `CoordinateSystem.Origin` | `XYZ` | Same as Connector.Origin |
| `CoordinateSystem.BasisX` | `XYZ` | Local X-axis vector |
| `CoordinateSystem.BasisY` | `XYZ` | Local Y-axis vector |
| `CoordinateSystem.BasisZ` | `XYZ` | **Direction connector faces** (outward normal) |

**Critical Insight**: `CoordinateSystem.BasisZ` points **outward** from the element - this is the direction to route pipes/ducts.

### System Information

| Property | Type | Description |
|----------|------|-------------|
| `Connector.Domain` | `Domain` enum | `DomainPiping`, `DomainHvac`, `DomainElectrical`, `DomainCableTrayConduit` |
| `Connector.ConnectorType` | `ConnectorType` enum | `End`, `Curve`, `Physical`, `Logical` |
| `Connector.IsConnected` | `bool` | Whether connector is already connected |
| `Connector.Owner` | `Element` | The element that owns this connector |
| `Connector.Id` | `int` | Unique ID within the element |

### Piping-Specific Properties

| Property | Type | Description |
|----------|------|-------------|
| `Connector.PipeSystemType` | `PipeSystemType` enum | `Sanitary`, `DomesticHotWater`, `DomesticColdWater`, `OtherPipe`, etc. |
| `Connector.Radius` | `double` | Connector radius (for round connectors) |
| `Connector.Width` | `double` | Width (for rectangular connectors) |
| `Connector.Height` | `double` | Height (for rectangular connectors) |
| `Connector.Flow` | `double` | Flow rate |
| `Connector.FlowDirection` | `FlowDirectionType` enum | `In`, `Out`, `Bidirectional` |

### HVAC-Specific Properties

| Property | Type | Description |
|----------|------|-------------|
| `Connector.DuctSystemType` | `DuctSystemType` enum | `SupplyAir`, `ReturnAir`, `ExhaustAir`, etc. |
| `Connector.Shape` | `ConnectorProfileType` enum | `Round`, `Rectangular`, `Oval` |

### Electrical-Specific Properties

| Property | Type | Description |
|----------|------|-------------|
| `Connector.ElectricalSystemType` | `ElectricalSystemType` enum | `PowerCircuit`, `Data`, `Telephone`, etc. |

### Connection Information

| Property | Type | Description |
|----------|------|-------------|
| `Connector.AllRefs` | `ConnectorSet` | All connected connectors |
| `Connector.MEPSystem` | `MEPSystem` | The system this connector belongs to |

---

## Domain Enum Values

```python
from Autodesk.Revit.DB import Domain

Domain.DomainPiping           # Plumbing/piping
Domain.DomainHvac             # HVAC/mechanical
Domain.DomainElectrical       # Electrical (power)
Domain.DomainCableTrayConduit # Cable tray and conduit
```

---

## Pipe System Types

```python
from Autodesk.Revit.DB.Plumbing import PipeSystemType

# Common plumbing system types
PipeSystemType.Sanitary           # Waste/drain
PipeSystemType.DomesticHotWater   # Hot water supply
PipeSystemType.DomesticColdWater  # Cold water supply
PipeSystemType.Vent               # Vent pipes
PipeSystemType.OtherPipe          # Other/undefined
PipeSystemType.FireProtectionWet  # Fire sprinkler (wet)
PipeSystemType.FireProtectionDry  # Fire sprinkler (dry)
```

---

## Complete GHPython Example

```python
"""
GHPython Component: MEP Connector Extractor

Extracts connector data from plumbing fixtures.

Inputs:
    fixtures (list): Plumbing fixture FamilyInstances
    run (bool): Execute toggle

Outputs:
    connector_data (list): Connector information as dictionaries
    connector_points (list): Connector origin points
    connector_vectors (list): Connector direction vectors
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RhinoCommon')

from Autodesk.Revit.DB import *
import Rhino.Geometry as rg

def extract_connectors(fixture):
    """Extract all connectors from a plumbing fixture."""
    connectors = []

    # Get MEPModel (only available for MEP-enabled families)
    mep_model = fixture.MEPModel
    if mep_model is None:
        return connectors

    # Get ConnectorManager
    conn_manager = mep_model.ConnectorManager
    if conn_manager is None:
        return connectors

    # Iterate through all connectors
    for conn in conn_manager.Connectors:
        # Get position
        origin = conn.Origin

        # Get direction (BasisZ points outward)
        coord_sys = conn.CoordinateSystem
        direction = coord_sys.BasisZ

        # Build connector data
        conn_data = {
            "id": conn.Id,
            "origin": {
                "x": origin.X,
                "y": origin.Y,
                "z": origin.Z
            },
            "direction": {
                "x": direction.X,
                "y": direction.Y,
                "z": direction.Z
            },
            "domain": str(conn.Domain),
            "is_connected": conn.IsConnected,
            "owner_id": fixture.Id.IntegerValue,
        }

        # Add domain-specific properties
        if conn.Domain == Domain.DomainPiping:
            conn_data["pipe_system_type"] = str(conn.PipeSystemType)
            conn_data["radius"] = conn.Radius  # feet
            conn_data["flow_direction"] = str(conn.FlowDirection)

        connectors.append(conn_data)

    return connectors

# Main execution
connector_data = []
connector_points = []
connector_vectors = []

if run and fixtures:
    for fixture in fixtures:
        connectors = extract_connectors(fixture)
        for conn in connectors:
            connector_data.append(conn)

            # Create Rhino geometry for visualization
            pt = rg.Point3d(
                conn["origin"]["x"],
                conn["origin"]["y"],
                conn["origin"]["z"]
            )
            vec = rg.Vector3d(
                conn["direction"]["x"],
                conn["direction"]["y"],
                conn["direction"]["z"]
            )
            connector_points.append(pt)
            connector_vectors.append(vec)
```

---

## Checking Connector Alignment

When connecting two connectors, verify they are aligned (same origin, opposite directions):

```python
def are_connectors_aligned(conn1, conn2, tolerance=0.001):
    """Check if two connectors are aligned for connection."""
    # Check origins are close
    origin1 = conn1.Origin
    origin2 = conn2.Origin

    if not origin1.IsAlmostEqualTo(origin2, tolerance):
        return False

    # Check directions are opposite
    dir1 = conn1.CoordinateSystem.BasisZ
    dir2 = conn2.CoordinateSystem.BasisZ

    # Opposite directions: dot product should be -1
    dot = dir1.DotProduct(dir2)

    return abs(dot + 1.0) < tolerance

def are_connectors_parallel_opposite(conn1, conn2, tolerance=0.001):
    """Check if connectors face opposite directions (for linear connections)."""
    dir1 = conn1.CoordinateSystem.BasisZ
    dir2 = conn2.CoordinateSystem.BasisZ

    # Use IsAlmostEqualTo for floating point comparison
    neg_dir2 = dir2.Negate()

    return dir1.IsAlmostEqualTo(neg_dir2, tolerance)
```

---

## Typical Plumbing Fixture Connectors

| Fixture Type | Typical Connectors |
|--------------|-------------------|
| **Sink** | Sanitary (drain), DomesticColdWater, DomesticHotWater |
| **Toilet** | Sanitary (drain), DomesticColdWater, Vent |
| **Shower** | Sanitary (drain), DomesticColdWater, DomesticHotWater |
| **Bathtub** | Sanitary (drain), DomesticColdWater, DomesticHotWater, Vent |
| **Water Heater** | DomesticColdWater (in), DomesticHotWater (out) |
| **Washing Machine** | Sanitary (drain), DomesticColdWater, DomesticHotWater |

---

## RiR Considerations

### Known Limitations

1. **MEP functionality is developing**: RiR's MEP support is still evolving. See [GitHub Issue #743](https://github.com/mcneel/rhino.inside-revit/issues/743).

2. **Potential crashes**: Users have reported Revit crashes when:
   - Referencing MEP elements and updating geometry
   - Accessing deleted connector references
   - Modifying MEP connections programmatically

3. **No native RiR MEP components**: Most MEP operations require direct Revit API access via GHPython/C#.

### Best Practices

1. **Always check for None**: MEPModel, ConnectorManager, and Connectors can all be None.

2. **Use transactions carefully**: MEP operations often require transactions. In RiR:
   ```python
   from RhinoInside.Revit import Revit
   doc = Revit.ActiveDBDocument

   with Transaction(doc, "MEP Operation") as t:
       t.Start()
       # ... do MEP work ...
       t.Commit()
   ```

3. **Validate connector domain**: Always check `Connector.Domain` before accessing domain-specific properties.

4. **Handle units**: Revit API uses feet internally. Convert as needed.

---

## References

- [Autodesk Revit 2024 API - Connectors](https://help.autodesk.com/cloudhelp/2024/ESP/Revit-API/files/Revit_API_Developers_Guide/Discipline_Specific_Functionality/MEP_Engineering/Revit_API_Revit_API_Developers_Guide_Discipline_Specific_Functionality_MEP_Engineering_Connectors_html.html)
- [The Building Coder - Connector Orientation](http://jeremytammik.github.io/tbc/a/0773_connector_orientation.htm)
- [The Building Coder - MEP API Overview](https://jeremytammik.github.io/tbc/a/0219_mep_api.htm)
- [RevitAPI Docs - Connector Properties](https://www.revitapidocs.com/2019/2741d0f3-6216-2e1a-3f59-de2dc47a689b.htm)
- [RiR GitHub - MEP Issues](https://github.com/mcneel/rhino.inside-revit/issues/743)

---

## Future Topics

- Creating pipes/ducts programmatically
- Connecting MEP elements via API
- System traversal and analysis
- Auto-routing algorithms
- Penetration generation for framing
