# Postmortem — Opening U-Coordinate Bug (2026-04-27)

**File:** `src/timber_framing_generator/wall_data/revit_data_extractor.py`
**Status:** Fixed.
**Severity:** High — every opening on every wall was silently dropped, so all framing pipelines downstream (panels → cells → king studs / headers / sills / cripples) ran as if the openings didn't exist.

---

## Symptom

For every wall, every door and window was being silently skipped with:

```
WARNING: Skipping opening {id} - entirely outside wall (u={start} to {end}, wall_length={L})
```

`walls_json` came out with `"openings": []` for every wall, even though the Revit
model had 17 doors + 7 windows correctly hosted on those walls. construction-graph
then framed every wall as if it were solid (no king studs, no headers, no sills).

## Diagnosis

The `[DBG]` logs from `extract_wall_data_from_revit()` revealed the pattern:

| wall_id  | wall_length | t       | reported u | inside [0, L]? |
|----------|-------------|---------|------------|----------------|
| 4453678  | 4.14 ft     | 1.89    | 7.82       | no             |
| 4453691  | 21.98 ft    | 10.66   | 234.35     | no             |
| 4453698  | 54.52 ft    | 35.54   | 1937.69    | no             |
| 4453679  | 23.19 ft    | 4.88    | 113.18     | no             |

For every wall, `u_reported = t × wall_length`. Since `t` was already in feet
(arc-length), multiplying by `wall_length` produced values way past the wall
end → opening discarded as out-of-bounds.

## Root cause

`extract_wall_data_from_revit()` had two paths for getting the curve parameter
at the opening location:

1. `safe_closest_point()` → `curve.ClosestPoint(point)`. Per a comment block,
   this was claimed to return a NORMALIZED `[0, 1]` parameter.
2. **LineCurve fallback** (the path actually taken for straight walls):
   `wall_base_curve_rhino.Line.ClosestParameter(point)` — which returns
   ARC-LENGTH IN FEET, as the inline comment correctly stated.

The code then unconditionally did `opening_center_u = t * wall_curve_length`
after both paths. That doubles the units when `t` is already absolute. Every
real wall in the test model was a LineCurve, so this fired for every opening.

The "GOTCHA (Rhino 8 CPython3): Curve.ClosestPoint() returns a NORMALIZED
parameter in [0, 1]…" comment block was based on a one-off empirical
observation (27.4 ft wall, opening at 23.75 ft, t=0.867). That value was
likely from a NurbsCurve path or a different Rhino build, but it was
generalized to an unconditional multiplication that broke the LineCurve
path. A half-finished refactor: the LineCurve fallback was added to fix an
`AttributeError`, with a correct comment about its units, but the
multiplication on the next line was never gated.

## Fix

Replaced lines ~457-471 of `revit_data_extractor.py` with a domain-aware
normalization that's correct for both LineCurve (`Domain = [0, L]`) and
NurbsCurve (`Domain = [0, 1]` or `[0, L]`):

```python
# Normalize t to [0, 1] from the curve's own domain, so this
# works whether the underlying API returns arc-length
# (LineCurve.Line.ClosestParameter → domain [0, L]) or a
# pre-normalized parameter (some Curve.ClosestPoint paths).
domain = wall_base_curve_rhino.Domain
domain_length = domain.T1 - domain.T0
t_normalized = (
    (t - domain.T0) / domain_length
    if domain_length > 1e-9 else 0.0
)
wall_curve_length = curve_length(wall_base_curve_rhino)
opening_center_u = t_normalized * wall_curve_length
print(f"Opening {insert_id} centered at u={opening_center_u:.3f} "
      f"(t={t:.4f}, t_norm={t_normalized:.4f}, "
      f"wall_length={wall_curve_length:.3f})")
```

### Why this is correct in every case

| curve type      | Domain      | what `t` is        | `t_norm`      | `u`                |
|-----------------|-------------|--------------------|---------------|--------------------|
| LineCurve       | `[0, L]`    | arc-length in ft   | `t / L`       | `(t/L) × L = t` ✓  |
| NurbsCurve      | `[0, 1]`    | normalized param   | `t`           | `t × L` ✓          |
| NurbsCurve      | `[0, L]`    | arc-length in ft   | `t / L`       | `t` ✓              |
| Curved walls    | varies      | varies             | normalized    | `t_norm × L` ✓     |

For curved walls, `wall_curve_length` is the true arc-length, so
`t_normalized * wall_curve_length` is the correct world-space u-coordinate.

### Verification

Re-ran the test model after the fix:

- Wall 4459394 (21.98 ft, 16x8 garage door centered):
  `t=10.66, t_norm=0.4851, u=10.66, u_start=2.55, u_end=18.78` — inside wall ✓
- All 17 doors + 7 windows now appear in `walls_json` with valid u-coordinates.
- Downstream framing (king studs, headers, sills, cripples) renders correctly
  in Revit.

## Prevention

1. **Regression test.** Add a test in `tests/wall_data/` that builds a
   LineCurve-backed wall with one centered opening and asserts the resulting
   `start_u_coordinate` lies in `[0, wall_length]`. Without this, the next
   refactor of this block can break it silently — there's no exception, just
   a warning log and an empty openings array.
2. **Audit `safe_closest_point` usage.** Anywhere else in TFG that does
   `t * length` after a `safe_closest_point` or `ClosestParameter` call has
   the same potential bug. Search:
   ```
   rg -n "safe_closest_point|ClosestParameter|ClosestPoint" src/
   ```
3. **Tighten `safe_closest_point`.** Consider having it always return a
   normalized parameter, or always return absolute, and document which —
   instead of leaking the inconsistency to every caller. The current
   shape (consumer must guess the unit) is the structural source of this
   class of bug.

## Scope clarification

This bug was independent of the four known `constructai-revit-plugin` issues
(CSR rotation, Revit auto-join, opening width fallback, opening center
projection). Those four are still pending and tracked separately for the
plugin Claude conversation. With this TFG fix in place, the data pipeline
from Revit → WallAnalyzer → construction-graph is verified end-to-end correct.
