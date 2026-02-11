# EYRC RESET (25086.10) - Quick Wins Analysis

Analysis Date: 2026-01-26

---

## Feature Comparison

| Feature | Effort | Value | Quick Win? | Notes |
|---------|--------|-------|------------|-------|
| **Sheathing generation** | Low | High | **Best** | Simple geometry, high visual impact |
| **Holddowns** | Low | Medium | Good | Point locations, structural coordination |
| **Shear vs non-bearing framing** | Medium | High | Partial | Need wall type input |
| **Span-specific headers** | Medium-High | Medium | No | Requires span tables |
| **Vertical panelization** | Medium | Medium | No | Multi-story complexity |

---

## Recommended: Sheathing Generation

### Why It's the Quickest Win

1. **Simple geometry** - Rectangles on wall face (4'x8', 4'x9', or 4'x10' panels)

2. **Clear rules**:
   - Standard panel widths: 4 ft (48")
   - Stagger vertical joints between rows
   - Cut around openings
   - Panel edges land on stud centers

3. **High visual impact** - Makes model look substantially more complete

4. **Practical value**:
   - Material takeoffs (panel count, waste calculation)
   - Shop drawing generation
   - Identifies blocking locations (panel edges)

5. **Leverages existing code**:
   - Wall geometry and openings
   - Panel decomposition logic
   - UVW coordinate system

### Basic Algorithm

```
For each wall/panel:
  1. Get bounds (u_start, u_end, wall_height)
  2. Determine sheathing type (structural vs non-structural)
  3. Lay out 4' wide sheets starting from panel edge
  4. Stack rows vertically (standard heights: 8', 9', 10')
  5. Stagger vertical joints by 2' or 4' between rows
  6. Cut openings from sheets that intersect them
  7. Output panel geometry with material properties
```

### Sheathing Types to Support

| Type | Material | Typical Thickness | Application |
|------|----------|-------------------|-------------|
| Structural | Plywood/OSB | 7/16", 15/32", 1/2", 19/32" | Shear walls, exterior |
| Non-structural | Gypsum | 1/2", 5/8" | Interior partitions |
| Exterior | DensGlass, Plywood | 1/2", 5/8" | Weather barrier |

### Output Schema (Proposed)

```json
{
  "sheathing_panels": [
    {
      "id": "wall_1_panel_0_sheath_0",
      "wall_id": "wall_1",
      "panel_id": "wall_1_panel_0",
      "face": "exterior",  // or "interior"
      "material": "structural_plywood",
      "thickness_inches": 0.4375,
      "u_start": 0.0,
      "u_end": 4.0,
      "v_start": 0.0,
      "v_end": 8.0,
      "is_full_sheet": true,
      "cutouts": []
    },
    {
      "id": "wall_1_panel_0_sheath_1",
      "cutouts": [
        {
          "type": "window",
          "u_start": 2.0,
          "u_end": 5.0,
          "v_start": 3.0,
          "v_end": 7.0
        }
      ]
    }
  ]
}
```

---

## Second Choice: Holddowns

### Why It's Also Quick

- Point elements at shear wall ends
- Simple geometry (location marker or small bracket)
- Useful for structural coordination
- Foundation/framing interface

### Basic Algorithm

```
For each shear wall:
  1. Identify as shear wall (input flag or wall type)
  2. Place holddown at each end (u=0 and u=wall_length)
  3. Output location, type, and capacity
```

### Holddown Types

| Type | Capacity | Typical Use |
|------|----------|-------------|
| HDU2 | 3,075 lb | Light shear walls |
| HDU4 | 4,565 lb | Medium shear walls |
| HDU8 | 6,780 lb | Heavy shear walls |
| PAHD | 8,000+ lb | High-load applications |

---

## Implementation Priority

1. **Phase 1**: Sheathing generation (structural panels)
2. **Phase 2**: Holddown locations
3. **Phase 3**: Shear wall framing differences (tighter spacing, blocking)
4. **Phase 4**: Span-specific headers (requires engineering tables)
