# File: src/constructai_demo/kreo_parser.py
"""Parse filtered Kreo AI Search JSON into typed dataclasses.

Handles the raw Kreo API response format where coordinates are [x, y] arrays
and measurements (length, thickness, area) are in meters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class KreoPoint:
    """A 2D point in Kreo pixel space (top-left origin)."""

    x: float
    y: float

    @classmethod
    def from_any(cls, val) -> KreoPoint:
        """Create from [x, y] array or {"x": ..., "y": ...} dict."""
        if isinstance(val, dict):
            return cls(x=float(val["x"]), y=float(val["y"]))
        if isinstance(val, (list, tuple)):
            return cls(x=float(val[0]), y=float(val[1]))
        raise ValueError(f"Cannot parse point from {type(val).__name__}: {val}")

    @classmethod
    def from_array(cls, arr: List[float]) -> KreoPoint:
        """Create from [x, y] array. Kept for backward compatibility."""
        return cls.from_any(arr)


@dataclass
class KreoWall:
    """A wall detected by Kreo AI Search.

    Attributes:
        p1: Start point in pixel coordinates.
        p2: End point in pixel coordinates.
        length: Real-world length in meters.
        thickness: Real-world thickness in meters.
        is_exterior: Explicit exterior/interior flag (None = not specified).
        index: Original index in the JSON array.
    """

    p1: KreoPoint
    p2: KreoPoint
    length: float
    thickness: float
    is_exterior: Optional[bool] = None
    index: int = 0


@dataclass
class KreoOpening:
    """A door or window detected by Kreo AI Search.

    Attributes:
        p1: Start point in pixel coordinates.
        p2: End point in pixel coordinates.
        length: Real-world length (width) in meters.
        thickness: Real-world thickness in meters.
        opening_type: Either 'door' or 'window'.
        index: Original index in the JSON array.
        revit_type: Optional Revit "Family : Type" name override.
        sill_height_in: Optional sill height in inches (instance-level).
    """

    p1: KreoPoint
    p2: KreoPoint
    length: float
    thickness: float
    opening_type: str  # 'door' or 'window'
    index: int = 0
    revit_type: Optional[str] = None
    sill_height_in: Optional[float] = None


@dataclass
class KreoSpace:
    """A room/space polygon detected by Kreo AI Search.

    Attributes:
        contour: List of vertex points in pixel coordinates.
        text: Text labels found within the polygon.
        area: Area in square meters.
        perimeter: Perimeter in meters.
        index: Original index in the JSON array.
    """

    contour: List[KreoPoint] = field(default_factory=list)
    text: List[str] = field(default_factory=list)
    area: float = 0.0
    perimeter: float = 0.0
    index: int = 0


def parse_walls(json_str: str) -> List[KreoWall]:
    """Parse Kreo wall JSON into KreoWall dataclasses.

    Args:
        json_str: JSON string with top-level {"status": "Ready", "lines": [...]}.

    Returns:
        List of KreoWall objects with pixel coordinates and meter measurements.

    Raises:
        ValueError: If JSON is malformed or missing required fields.
    """
    data = _load_json(json_str)
    lines = _extract_lines(data)

    walls: List[KreoWall] = []
    for i, raw in enumerate(lines):
        norm = _normalize_line(raw, i, "wall")
        # Read optional is_exterior from top-level raw dict
        is_ext = raw.get("is_exterior")
        if is_ext is not None:
            is_ext = bool(is_ext)
        walls.append(KreoWall(
            p1=KreoPoint.from_any(norm["p1"]),
            p2=KreoPoint.from_any(norm["p2"]),
            length=float(norm["length"]),
            thickness=float(norm["thickness"]),
            is_exterior=is_ext,
            index=i,
        ))
    return walls


def parse_doors(json_str: str) -> List[KreoOpening]:
    """Parse Kreo door JSON into KreoOpening dataclasses.

    Args:
        json_str: JSON string with top-level {"status": "Ready", "lines": [...]}.

    Returns:
        List of KreoOpening objects with opening_type='door'.
    """
    return _parse_openings(json_str, "door")


def parse_windows(json_str: str) -> List[KreoOpening]:
    """Parse Kreo window JSON into KreoOpening dataclasses.

    Args:
        json_str: JSON string with top-level {"status": "Ready", "lines": [...]}.

    Returns:
        List of KreoOpening objects with opening_type='window'.
    """
    return _parse_openings(json_str, "window")


def parse_spaces(json_str: str) -> List[KreoSpace]:
    """Parse Kreo space/room JSON into KreoSpace dataclasses.

    Args:
        json_str: JSON string with top-level {"status": "Ready", "contours": [...]}.

    Returns:
        List of KreoSpace objects.
    """
    data = _load_json_contours(json_str)
    contours = data.get("contours")
    if contours is None:
        raise ValueError("Missing 'contours' key in space JSON")
    if not isinstance(contours, list):
        raise ValueError("'contours' must be a list")

    spaces: List[KreoSpace] = []
    for i, contour in enumerate(contours):
        points_raw = contour.get("points", [])
        points = [KreoPoint.from_array(p) for p in points_raw]
        spaces.append(KreoSpace(
            contour=points,
            text=contour.get("text", []),
            area=float(contour.get("area", 0.0)),
            perimeter=float(contour.get("perimeter", 0.0)),
            index=i,
        ))
    return spaces


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_json(json_str: str) -> dict:
    """Load JSON string, raising ValueError on failure.

    Accepts both full Kreo format {"status":"Ready","lines":[...]}
    and bare arrays [{...}, ...] (auto-wrapped as {"lines": [...]}).
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    if isinstance(data, list):
        # Bare array: wrap as lines
        return {"lines": data}
    if not isinstance(data, dict):
        raise ValueError(
            f"JSON root must be an object or array, got {type(data).__name__}"
        )
    return data


def _load_json_contours(json_str: str) -> dict:
    """Load JSON for space/contour data.

    Accepts both full Kreo format {"status":"Ready","contours":[...]}
    and bare arrays [{...}, ...] (auto-wrapped as {"contours": [...]}).
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    if isinstance(data, list):
        return {"contours": data}
    if not isinstance(data, dict):
        raise ValueError(
            f"JSON root must be an object or array, got {type(data).__name__}"
        )
    return data


def _extract_lines(data: dict) -> list:
    """Extract 'lines' array from parsed JSON dict."""
    lines = data.get("lines")
    if lines is None:
        raise ValueError("Missing 'lines' key in JSON")
    if not isinstance(lines, list):
        raise ValueError("'lines' must be a list")
    return lines


def _normalize_line(raw: dict, index: int, element_type: str) -> dict:
    """Normalize a line element to canonical format {p1, p2, length, thickness}.

    Handles two Kreo formats:
      - Raw API:      {"p1": [x,y], "p2": [x,y], "length": m, "thickness": m}
      - Filtered:     {"line": {"p1": {"x":..,"y":..}, "p2": {"x":..,"y":..}},
                        "length": m, "thickness": m}
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"{element_type}[{index}] expected dict, got {type(raw).__name__}: "
            f"{str(raw)[:200]}"
        )

    # Format B: points nested inside "line" key
    if "line" in raw and isinstance(raw["line"], dict):
        line_obj = raw["line"]
        result = {
            "p1": line_obj.get("p1"),
            "p2": line_obj.get("p2"),
            "length": raw.get("length"),
            "thickness": raw.get("thickness"),
        }
    elif "p1" in raw:
        # Format A: p1/p2 at top level (raw Kreo API)
        result = raw
    else:
        raise ValueError(
            f"{element_type}[{index}] unrecognized format. "
            f"Expected 'p1'/'p2' at top level or nested in 'line'. "
            f"Available keys: {list(raw.keys())}"
        )

    # Validate required fields
    for field_name in ("p1", "p2", "length", "thickness"):
        if result.get(field_name) is None:
            raise ValueError(
                f"{element_type}[{index}] missing required field '{field_name}'"
            )

    return result


def _parse_openings(json_str: str, opening_type: str) -> List[KreoOpening]:
    """Parse door or window JSON into KreoOpening list."""
    data = _load_json(json_str)
    lines = _extract_lines(data)

    openings: List[KreoOpening] = []
    for i, raw in enumerate(lines):
        norm = _normalize_line(raw, i, opening_type)
        openings.append(KreoOpening(
            p1=KreoPoint.from_any(norm["p1"]),
            p2=KreoPoint.from_any(norm["p2"]),
            length=float(norm["length"]),
            thickness=float(norm["thickness"]),
            opening_type=opening_type,
            index=i,
            revit_type=raw.get("revit_type"),
            sill_height_in=raw.get("sill_height_in"),
        ))
    return openings
