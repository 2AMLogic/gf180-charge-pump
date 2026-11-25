"""Charge-pump evidence helpers (block-specific; extends, does not fork, the core).

EXTENSION of ``evidence.py``/``report.py``: renders the two things this block's
scope rule demands of every record --

* an output-voltage line always states its load current and its PVT point
  (:func:`output_lines`; a Vout measurement whose name carries no load is
  refused, so an unloaded figure cannot be reported), and
* device-stress margins against the rating (:func:`stress_margins`), where any
  negative margin is a violation.

:func:`evaluate` is called from ``report.analyze_results``, so both rules apply
to every recorded run and a violation fails the record.
"""

from __future__ import annotations

import re

_LOAD = re.compile(r"_(?:at|to)_(\d+)ma_")
_VOUT = re.compile(r"^vout_")


class UnloadedOutputError(ValueError):
    """A Vout measurement that does not state its load current."""


def load_ma(name: str) -> int:
    m = _LOAD.search(name)
    if not m:
        raise UnloadedOutputError(
            f"{name!r}: a Vout measurement must name its load current "
            "(e.g. vout_at_10ma_...); unloaded figures are not reported")
    return int(m.group(1))


def output_lines(point: dict, measurements: dict[str, float]) -> list[str]:
    """``<name>: <v> V at <load> mA load, <corner> [<mimcap>] <T> C <vdd> V``."""
    proc = point.get("process", point.get("corner"))
    if proc is None:
        raise KeyError("point must carry 'process' or 'corner'")
    mimcap = point.get("mimcap")
    if mimcap and mimcap not in proc:
        where = f"{proc} {mimcap} {point['temp_c']:g} C {point['vdd']:g} V"
    else:
        where = f"{proc} {point['temp_c']:g} C {point['vdd']:g} V"
    return [
        f"{name}: {value:.4g} V at {load_ma(name)} mA load, {where}"
        for name, value in measurements.items() if _VOUT.match(name)
    ]


def stress_margins(measurements: dict[str, float], rating_v: float | dict[str, float]) -> dict:
    """Margin (rating - stress) per ``stress_*`` measurement and the worst one.

    ``rating_v`` is one rating for every measurement, or a per-measurement map.
    """
    def rating(k):
        return rating_v[k] if isinstance(rating_v, dict) else rating_v

    margins = {k: rating(k) - x for k, x in measurements.items() if k.startswith("stress_")}
    if not margins:
        raise ValueError("no stress_* measurements to evaluate")
    worst = min(margins, key=margins.get)
    return {"margins": margins, "worst": worst, "worst_margin_v": margins[worst],
            "violations": sorted(k for k, m in margins.items() if m < 0)}


def evaluate(checks: dict, measure_names, results) -> dict:
    """Apply the scope rule to every completed point of a run.

    Returns ``{"output_lines", "stress", "failures"}``. Failures use the
    ``report.evaluate_checks`` shape and make the record fail:

    * ``unloaded_vout``: a Vout measurement that names no load current;
    * ``stress_unrated``: a ``stress_*`` measurement with no ``max`` rating check
      (the rating is read from the bench's own check, never assumed);
    * ``stress_margin``: a negative margin against that rating (a rating is
      exceeded -- a failing result, not a stretch).
    """
    failures: list[dict] = []
    lines: list[dict] = []
    stress: list[dict] = []
    names = list(measure_names)
    vouts = [n for n in names if _VOUT.match(n)]
    stresses = [n for n in names if n.startswith("stress_")]
    for n in vouts:
        try:
            load_ma(n)
        except UnloadedOutputError as exc:
            failures.append({"measurement": n, "kind": "unloaded_vout", "limit": None,
                             "value": None, "at": "bench", "note": str(exc)})
    for n in stresses:
        if (checks.get(n) or {}).get("max") is None:
            failures.append({"measurement": n, "kind": "stress_unrated", "limit": None,
                             "value": None, "at": "bench",
                             "note": "no max rating check -- stress cannot be judged"})
    loaded = [n for n in vouts if not any(f["measurement"] == n for f in failures)]
    rated = {n: checks[n]["max"] for n in stresses
             if (checks.get(n) or {}).get("max") is not None}
    for r in results:
        if r.status != "ok":
            continue
        point = {"process": r.point.corner.name, "temp_c": r.point.temp_c, "vdd": r.point.vdd}
        for k, v in r.measurements.items():
            if k not in loaded:
                continue
            (text,) = output_lines(point, {k: v})
            lines.append({"at": r.point.corner_id, "line": text, "name": k, "value": v})
        have = {k: v for k, v in r.measurements.items() if k in rated}
        if not have:
            continue
        m = stress_margins(have, rated)
        stress.append({"at": r.point.corner_id, "worst": m["worst"],
                       "worst_margin_v": m["worst_margin_v"], "violations": m["violations"]})
        for k in m["violations"]:
            failures.append({"measurement": k, "kind": "stress_margin", "limit": rated[k],
                             "value": have[k], "at": r.point.corner_id})
    return {"output_lines": lines, "stress": stress, "failures": failures}


def render_lines(scope: dict) -> list[str]:
    """Markdown bullets for a record's ``scope`` section.

    Vout entries are summarized per measurement name (min, max, point count) so
    the section stays O(#measurements); each bullet still names its load and
    corner. The complete per-point list stays in ``scope["output_lines"]`` of
    the JSON record. Entries without ``name``/``value`` (older records) are
    listed individually.
    """
    entries = scope["output_lines"]
    out: list[str] = []
    groups: dict[str, list[dict]] = {}
    for x in entries:
        if "name" in x and "value" in x:
            groups.setdefault(x["name"], []).append(x)
        else:
            out.append(f"- {x['at']}: {x['line']}")
    total = len({x["at"] for x in entries})
    for name, xs in groups.items():
        lo = min(xs, key=lambda x: x["value"])
        hi = max(xs, key=lambda x: x["value"])
        out.append(f"- Min `{name}`: {lo['at']}: {lo['line']}")
        out.append(f"- Max `{name}`: {hi['at']}: {hi['line']}")
        out.append(f"- `{name}` covers {len(xs)} of {total} completed points")
    if groups:
        out.append("- Full per-point output list: `scope.output_lines` in the JSON record")
    stress = scope["stress"]
    if stress:
        worst = min(stress, key=lambda s: s["worst_margin_v"])
        out.append(f"- Worst device-stress margin: {worst['worst_margin_v']:.4g} V on "
                   f"`{worst['worst']}` at {worst['at']} "
                   f"({sum(1 for s in stress if s['violations'])} of {len(stress)} points violate)")
    return out
