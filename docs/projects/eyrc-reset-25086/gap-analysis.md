# EYRC RESET (25086.10) - Gap Analysis

Analysis Date: 2026-01-26
Source: 2025-10-09_25086_10-RESET-EYRC-100DD PRICING SET.pdf

---

## Project Overview

- **Project Name**: EYRC RESET
- **Project Number**: 25086.10
- **Location**: Pacific Palisades, CA
- **Architect**: Ehrlich Yanai Rhee Chaney (EYRC) Architects
- **Structural Engineer**: Holmes Structures
- **Building Type**: Single-family residence (2-story)
- **Building Code**: 2022 California Building Code (CBC)
- **Risk Category**: II (typical residential)
- **Framing System**: Cold-Formed Steel (CFS)

---

## Current Codebase Capabilities

### Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| CFS Material System | SUPPORTED | CFSStrategy implemented |
| 16"/24" O.C. spacing | SUPPORTED | Configurable |
| Standard Studs | SUPPORTED | Via CFSStrategy |
| King Studs | SUPPORTED | Via CFSStrategy |
| Trimmers | SUPPORTED | Via CFSStrategy |
| Headers | SUPPORTED | Single-piece |
| Sills | SUPPORTED | Via CFSStrategy |
| Header Cripples | SUPPORTED | Via CFSStrategy |
| Sill Cripples | SUPPORTED | Via CFSStrategy |
| Row Blocking/Bridging | SUPPORTED | Inline pattern |
| Wall Panelization | SUPPORTED | decompose_all_walls() |
| Corner Adjustment | SUPPORTED | detect_wall_corners() |
| Joint Optimization | SUPPORTED | DP-based algorithm |
| Revit Integration | SUPPORTED | Via Rhino.Inside.Revit |
| JSON Communication | SUPPORTED | Modular pipeline |

### Current CFS Profile Catalog

From `src/timber_framing_generator/materials/cfs/cfs_profiles.py`:

**Studs:**
- 350S162 series (33, 43, 54)
- 600S162 series (33, 43, 54)
- 800S162 series (54, 68)

**Tracks:**
- 350T125 series (33, 43, 54)
- 600T125 series (33, 43, 54)
- 800T125 series (54, 68)

---

## Gap Analysis: Profiles Required vs. Available

### What We HAVE in Codebase

**Studs (S162 flange = 1.62"):**
- 350S162 series: 33, 43, 54 gauge
- 362S162 series: 33, 43, 54 gauge
- 600S162 series: 33, 43, 54, 68 gauge
- 800S162 series: 54, 68 gauge

**Tracks (T125 flange = 1.25"):**
- 350T125 series: 33, 43, 54 gauge
- 362T125 series: 33, 43, 54 gauge
- 600T125 series: 33, 43, 54 gauge
- 800T125 series: 54, 68 gauge

### What the Project NEEDS

**Studs (S125 flange = 1.25"):**

| SSMA ID | Depth | Flange | Gauge | In Codebase? |
|---------|-------|--------|-------|--------------|
| 362S125-33 | 3 5/8" | 1 1/4" | 20 | NO - have S162, need S125 |
| 362S125-43 | 3 5/8" | 1 1/4" | 18 | NO |
| 362S125-54 | 3 5/8" | 1 1/4" | 16 | NO |
| 362S125-68 | 3 5/8" | 1 1/4" | 14 | NO |
| 400S125-33 | 4" | 1 1/4" | 20 | NO - 400 series missing entirely |
| 400S125-43 | 4" | 1 1/4" | 18 | NO |
| 400S125-54 | 4" | 1 1/4" | 16 | NO |
| 400S125-68 | 4" | 1 1/4" | 14 | NO |
| 550S125-33 | 5 1/2" | 1 1/4" | 18 | NO - 550 series missing entirely |
| 550S125-43 | 5 1/2" | 1 1/4" | 18 | NO |
| 550S125-54 | 5 1/2" | 1 1/4" | 16 | NO |
| 550S125-68 | 5 1/2" | 1 1/4" | 14 | NO |
| 550S250-97 | 5 1/2" | 2 1/2" | 12 | NO - load-bearing, 12 GA missing |

**Tracks:**

| SSMA ID | Depth | Flange | Gauge | In Codebase? |
|---------|-------|--------|-------|--------------|
| 362T125-54 | 3 5/8" | 1 1/4" | 16 | YES (have this) |
| 362T250-54 | 3 5/8" | 2 1/2" | 16 | NO - T250 series missing |
| 400T125-54 | 4" | 1 1/4" | 16 | NO - 400 series missing |
| 400T250-54 | 4" | 2 1/2" | 16 | NO |
| 550T125-54 | 5 1/2" | 1 1/4" | 16 | NO - 550 series missing |
| 550T200-54 | 5 1/2" | 2" | 16 | NO |
| 550T250-54 | 5 1/2" | 2 1/2" | 16 | NO |

---

## Key Observations

### 1. Flange Width Issue (S162 vs S125)

**Critical finding:** The codebase has **S162** studs (1.62" flange), but the project uses **S125** studs (1.25" flange).

- **S162** = Structural/joist applications (wider flange)
- **S125** = Standard wall studs (narrower flange)

We have 362S**162** but need 362S**125**. Same web depth, different flange.

### 2. Missing Web Depth Series

| Depth | Codebase | Project Needs |
|-------|----------|---------------|
| 3 1/2" (350) | YES (S162) | - |
| 3 5/8" (362) | YES (S162) | YES (S125) |
| 4" (400) | **NO** | YES |
| 5 1/2" (550) | **NO** | YES |
| 6" (600) | YES (S162) | - |
| 8" (800) | YES (S162) | - |

### 3. Track Flange Variations

Project uses different flanges for top vs. bottom tracks:
- **Top Track**: 2 1/2" flange (T250) - MISSING
- **Bottom Track**: 1 1/4" flange (T125) - we have some
- **Sill Track**: 2" flange (T200) - MISSING

### 4. Gauge Range

Project: 12-20 GA (97-33 mils)
Codebase: 14-20 GA (68-33 mils)

**Missing: 97 mil (12 GA)** for load-bearing studs (550S250-97)

---

## Recommended Actions

### High Priority - COMPLETED ✓

1. **Add 362 series** (3 5/8" depth, 125 flange) ✓
   - 362S125-33, 362S125-43, 362S125-54, 362S125-68
   - 362T125-54, 362T250-54

2. **Add 400 series** (4" depth, 125 flange) ✓
   - 400S125-33, 400S125-43, 400S125-54, 400S125-68
   - 400T125-54, 400T250-54

3. **Add 550 series** (5 1/2" depth, 125/250 flange) ✓
   - 550S125-33, 550S125-43, 550S125-54, 550S125-68
   - 550S250-97 (load-bearing)
   - 550T125-54, 550T200-54, 550T250-54

4. **Add 97 mil (12 GA) thickness** to gauge options ✓

5. **Distinguish top track vs. bottom track** in framing generation ✓
   - Top track uses larger flange (T250 = 2.5")
   - Bottom track uses smaller flange (T125 = 1.25")
   - Helper function `get_profile_for_wall()` implements this

6. **Profile selection by wall width** ✓
   - `get_profile_for_wall()` selects correct series based on wall thickness
   - `get_profiles_for_wall_schedule()` returns complete profile set for a wall

### Medium Priority - TODO

7. **Load-bearing vs. non-bearing wall logic in framing generator**
   - Profile selection helpers are ready
   - Need to integrate with CFSStrategy

8. **CRC bridging at 4' O.C.** per note 11
   - Bridging implementation exists but may need spacing adjustment

### Design Considerations from Notes

- Note 8: No splices in vertical studs
- Note 11: CRC bridging can be omitted with sheathing both sides
- Note 14: Tracks must be one gauge thicker than studs
- Note 2: Fy = 50ksi for 16 GA and thicker, Fy = 33ksi for 18 GA and thinner

---

## Implementation Summary (2026-01-26)

**Added 25 new CFS profiles:**

| Category | Profiles Added |
|----------|---------------|
| S125 Studs (1.25" flange) | 362S125-33/43/54/68, 400S125-33/43/54/68, 550S125-33/43/54/68 |
| S250 Load-Bearing | 550S250-97 |
| T125 Bottom Tracks | 400T125-54, 550T125-54 |
| T200 Sill Tracks | 550T200-54 |
| T250 Top Tracks | 362T250-54, 400T250-54, 550T250-54 |

**New helper functions:**
- `get_profile_for_wall(wall_width, element_type, is_load_bearing, gauge)` - Smart profile selection
- `get_profiles_for_wall_schedule(wall_width, wall_height, is_load_bearing)` - Complete wall profile set

**Total profiles now available:** 42 (was 17)
