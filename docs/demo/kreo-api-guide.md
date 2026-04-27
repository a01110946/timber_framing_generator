# Kreo AI Search API Guide

> **Source**: Kreo AI Search API Documentation v1.2.0 (November 2025)
> **Base URL**: `https://takeoff.kreo.net/api/ai-search/v1/takeoff2D/`
> **Purpose**: AI-powered extraction of geometric data (walls, doors, windows, rooms) from 2D design files (PDF, CAD, images)

---

## Authentication

All requests require an API key in the `X-API-KEY` header.

```
X-API-KEY: your-api-key-here
```

Keys are created at the Kreo key management page. The key is shown only once at creation.

---

## Workflow Overview

```
Upload File  -->  Create Project  -->  (Set Scale)  -->  Run AI Search  -->  Poll Results  -->  Get Results
   POST             POST                  PUT               POST               GET               GET
  /upload          /project         /projects/{id}/    /projects/{id}/    /projects/{id}/   /projects/{id}/
                                       scale              search         search/{jobId}    search/{jobId}
```

1. **Upload** a PDF/CAD/image file, receive a `fileKey`
2. **Create Project** from the uploaded file (one page per project)
3. **Set Scale** (optional if set during project creation) - maps drawing units to real-world units
4. **Run AI Search** for each element type (wall, door, window, polygon) - returns a `jobId`
5. **Poll** the job status until `Ready`
6. **Get Results** - structured geometric data with coordinates, dimensions, and measurements

---

## Endpoints

### 1. Upload File

**POST** `/upload`

| Field | Value |
|-------|-------|
| Content-Type | `multipart/form-data` |
| Body | `file` (binary) |
| Supported formats | PDF, DWG, DXF, DWF, DGN, PNG, TIFF, JPG, JPEG, BMP, EMF, GIF |

**Response** (200): plain text file key

```
temp/6c47cb338a7346d88ab843b1e6d8acf2
```

---

### 2. Create Project

**POST** `/project`

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fileKey` | string | Yes | From Upload endpoint |
| `pageIndex` | integer | No | Zero-based page index (default: 0). One page per project. |
| `scale` | object | No | Drawing scale calibration (can set later via Set Scale) |
| `scale.drawingCalibrationLineLength` | number | Yes* | Length of calibration line as measured on drawing |
| `scale.originalCalibrationLineLength` | number | Yes* | Actual real-world length of calibration line |

**Example:**

```json
{
  "fileKey": "temp/6c47cb338a7346d88ab843b1e6d8acf2",
  "pageIndex": 0,
  "scale": {
    "drawingCalibrationLineLength": 1,
    "originalCalibrationLineLength": 100
  }
}
```

**Response** (200):

```json
{
  "projectId": 100500,
  "status": "Ready"
}
```

Status values: `Ready` | `Calculating` | `Failed`

---

### 3. Get Project Status

**GET** `/projects/{projectId}/status`

Used to poll until `Calculating` becomes `Ready`.

**Response** (200):

```json
{
  "projectId": 100500,
  "status": "Ready"
}
```

---

### 4. Set Page Scale

**PUT** `/projects/{projectId}/scale`

Only allowed when project status is `Ready`.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `drawingCalibrationLineLength` | number | Yes | Drawing-space length |
| `originalCalibrationLineLength` | number | Yes | Real-world length |

Scale ratio = `originalCalibrationLineLength / drawingCalibrationLineLength`

---

### 5. Run AI Search

**POST** `/projects/{projectId}/search`

Asynchronous. Returns a `jobId` to poll.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dpi` | integer | Yes | Resolution. Values: `150`, `300`, `450`, `600` |
| `type` | string | Yes | Element type to detect (see below) |
| `text` | string | Conditional | Search text within polygons. **Required** if type is `polygon`, **must be omitted** otherwise. |
| `cropBox` | array[4 int] | No | `[x1, y1, x2, y2]` bounding box to restrict search area (pixels) |

**Supported `type` values:**

| Type | Returns | Description |
|------|---------|-------------|
| `polygon` | contours (areas) | Rooms, corridors, GIA, any enclosed space matching `text` |
| `wall` | lines | All walls (interior + exterior) |
| `externalWall` | lines | Exterior walls only |
| `internalWall` | lines | Interior walls only |
| `door` | lines | Door openings |
| `window` | lines | Window openings |

**Example:**

```json
{
  "dpi": 300,
  "type": "wall"
}
```

**Response** (200):

```json
{
  "jobId": "aaab5e87-f533-46da-a19a-98401acb678f-e1",
  "status": "Calculating"
}
```

---

### 6. Get AI Search Result

**GET** `/projects/{projectId}/search/{jobId}`

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `confidence` | number | No | Minimum AI confidence threshold (0-1). Filters low-confidence detections. |

**Response varies by search type:**

#### For `polygon` type (rooms/areas):

```json
{
  "status": "Ready",
  "contours": [
    {
      "text": ["MASTER BEDROOM", "13'-8\" x 12'-0\""],
      "area": 15.6,
      "perimeter": 20.3,
      "points": [
        [1715.523, 218.374],
        [1667.250, 525.628],
        [1800.100, 525.628],
        [1800.100, 218.374]
      ]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `Ready` / `Calculating` / `Failed` |
| `contours` | array | Array of detected polygons |
| `contours[].text` | string[] | Text strings found within the polygon |
| `contours[].area` | number | Area in **square meters** |
| `contours[].perimeter` | number | Perimeter in **meters** |
| `contours[].points` | number[][] | `[x, y]` vertices in **pixels** |

#### For `wall`, `externalWall`, `internalWall`, `door`, `window` types (linear elements):

```json
{
  "status": "Ready",
  "lines": [
    {
      "length": 5.0,
      "thickness": 0.15,
      "p1": [1715.523, 218.374],
      "p2": [1667.250, 525.628]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `Ready` / `Calculating` / `Failed` |
| `lines` | array | Array of detected linear elements |
| `lines[].length` | number | Length in **meters** |
| `lines[].thickness` | number | Thickness in **meters** |
| `lines[].p1` | number[] | Start point `[x, y]` of centerline in **pixels** |
| `lines[].p2` | number[] | End point `[x, y]` of centerline in **pixels** |

---

### 7. Download PDF

**GET** `/projects/{projectId}/pdf`

Downloads the processed PDF. Useful for projects created from images or CAD files.

---

## Async Polling Pattern

AI search jobs are asynchronous. Poll every 5-10 seconds:

```python
import requests
import time

BASE = "https://takeoff.kreo.net/api/ai-search/v1/takeoff2D"
HEADERS = {"X-API-KEY": "your-key"}

# Start search
resp = requests.post(f"{BASE}/projects/{project_id}/search",
                     json={"dpi": 300, "type": "wall"},
                     headers=HEADERS)
job_id = resp.json()["jobId"]

# Poll until ready
while True:
    result = requests.get(f"{BASE}/projects/{project_id}/search/{job_id}",
                          headers=HEADERS).json()
    if result["status"] == "Ready":
        break
    elif result["status"] == "Failed":
        raise Exception("Search failed")
    time.sleep(5)

# result["lines"] now contains detected walls
```

---

## Coordinate System

- **Pixel coordinates**: All `p1`, `p2`, and `points` values are in the input file's pixel space
- **Real-world measurements**: `length`, `thickness`, `area`, `perimeter` are in **meters** (after scale is applied)
- **Conversion to feet**: multiply by 3.28084
- **Coordinate origin**: top-left of the document page (standard image coordinates)

---

## Demo Integration Notes

### For 15051 S Padres Rd project:

1. **Upload** the PDF (multi-page - select the floor plan page via `pageIndex`)
2. **Set scale** using a known dimension from the architectural drawings (e.g., a room dimension)
3. **Run 4 searches** (one per element type):
   - `type: "wall"` - detect all walls
   - `type: "door"` - detect door openings
   - `type: "window"` - detect window openings
   - `type: "polygon", text: "bedroom"` (or room names) - detect room boundaries
4. **Combine results** into a unified JSON for downstream processing

### Expected output for this project (approximate):

Based on the architectural plans (Sheet A-1.0):
- ~35 wall segments (12 exterior, 23 interior)
- ~16 doors (3 exterior, 12 interior + 1 overhead)
- ~8 windows
- Rooms: Master Bedroom, Bedroom 2, Bedroom 3, Kitchen/Dining/Living, Hallway, Garage, Master Bath, Shared Bath

### Kreo-to-Revit coordinate pipeline:

```
Kreo pixel coords  -->  Real-world meters  -->  Feet (Revit internal)  -->  Revit Wall.Create()
     (p1, p2)           (already in meters      (* 3.28084)                 (line, type, level,
                          via length field)                                   height, offset)
```

- Wall height: 8'-0" (from framing notes, standard residential)
- Wall thickness: use Kreo's `thickness` field to select appropriate Revit wall type
  - ~0.089m (3.5") -> 2x4 interior wall
  - ~0.140m (5.5") -> 2x6 exterior wall
