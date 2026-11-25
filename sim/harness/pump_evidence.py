"""Charge-pump evidence helpers (block-specific; extends, does not fork, the core).

EXTENSION of ``evidence.py``/``report.py``: renders the two things this block's
scope rule demands of every record --

* an output-voltage line always states its load current and its PVT point
  (:func:`output_lines`; a Vout measurement whose name carries no load is
  refused, so an unloaded figure cannot be reported), and
* device-stress margins against the rating (:func:`stress_margins`), where any
  negative margin is a violation.
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
    """``Vout <v> V at <load> mA, <corner> <T> C <vdd> V`` for each Vout measurement."""
    where = f"{point['process']} {point['temp_c']:g} C {point['vdd']:g} V"
    return [
        f"{name}: {value:.4g} V at {load_ma(name)} mA load, {where}"
        for name, value in measurements.items() if _VOUT.match(name)
    ]


def stress_margins(measurements: dict[str, float], rating_v: float) -> dict:
    """Margin (rating - stress) per ``stress_*`` measurement and the worst one."""
    margins = {k: rating_v - x for k, x in measurements.items() if k.startswith("stress_")}
    if not margins:
        raise ValueError("no stress_* measurements to evaluate")
    worst = min(margins, key=margins.get)
    return {"margins": margins, "worst": worst, "worst_margin_v": margins[worst],
            "violations": sorted(k for k, m in margins.items() if m < 0)}
