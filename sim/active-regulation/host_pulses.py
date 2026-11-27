"""Replay the host's 1, 10 and 100 µs program loads on the transistor-level pump."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import math
from pathlib import Path
import tempfile

from screen import (
    MODEL_SHA,
    ORIGINAL,
    REGULATORS,
    Point,
    header,
    integrated,
    preflight,
    read_measurements,
    replace_once,
    run_spice,
)


# Nominal, minimum loaded output and maximum no-load shunt power in pvt.json.
POINTS = (
    Point("typical", "typical", "typical", "typical", 25, 3.30),
    Point("ss", "ss", "ss", "ss", 125, 2.97),
    Point("ff", "ss", "ff", "ff", -40, 3.63),
)
PULSES = ((2, 1), (5, 10), (17, 100))


def measure(point, models, ngspice, log_dir):
    edges = ["0 0"]
    measurements = {}
    for start, duration in PULSES:
        # Full requested flat-top time after the 1 ns leading edge.
        on = start + 0.001
        off = on + duration
        edges += [
            f"{start}u 0",
            f"{on:.3f}u 10m",
            f"{off:.3f}u 10m",
            f"{off + 0.001:.3f}u 0",
        ]
        window = f"from={on:.3f}u to={off:.3f}u"
        for suffix, operation in (
            ("vmin", "min v(out)"),
            ("vmax", "max v(out)"),
            ("pin_w", "avg pin"),
            ("pout_w", "avg pout"),
        ):
            measurements[f"pulse{duration}_{suffix}"] = f"{operation} {window}"
        measurements[f"pulse{duration}_release_v"] = (
            f"max v(out) from={off:.3f}u to={off + 1:.3f}u"
        )
    load = "vload out load 0\niload load 0 pwl(" + " ".join(edges) + ")"
    circuit = replace_once(
        integrated(), "iload out 0 pwl(0 0 2u 0 12u 10m 22u 10m 22.1u 0)", load
    )
    measurements.update(
        {
            "before_first_pulse_v": "find v(out) at=1.999u",
            "last_idle_pin_w": "avg pin from=118u to=119u",
            "last_idle_shunt_w": "avg pshunt from=118u to=119u",
        }
    )
    commands = [
        ".control",
        "set numdgt=10",
        "save v(out) v(vin) i(vinput) i(vload) i(vshunt)",
        "tran 0.2n 119u 0 0.2n",
        "let pin = -v(vin)*i(vinput)",
        "let pout = v(out)*i(vload)",
        "let pshunt = v(out)*i(vshunt)",
    ]
    commands.extend(
        f"meas tran {key} {expression}" for key, expression in measurements.items()
    )
    commands.extend(
        ["let end_time = vecmax(time)", "print end_time", "quit", ".endc", ".end"]
    )
    with tempfile.TemporaryDirectory() as work:
        output = run_spice(
            "\n".join([header(point, models), circuit, *commands, ""]),
            Path(work),
            ngspice,
        )
    if log_dir is not None:
        name = point.key().replace("/", "_") + ".log"
        (log_dir / name).write_text(output)
    observed = read_measurements(output, set(measurements) | {"end_time"})
    if not math.isclose(observed["end_time"], 119e-6):
        raise ValueError(
            f"Truncated transient at {point.key()}: {observed['end_time']}"
        )
    for _, duration in PULSES:
        prefix = f"pulse{duration}_"
        power = observed[prefix + "pout_w"]
        if (
            not observed[prefix + "vmin"] * 0.01 - 1e-6
            <= power
            <= observed[prefix + "vmax"] * 0.01 + 1e-6
        ):
            raise ValueError(
                f"Delivered power disagrees with the 10 mA load at {point.key()}"
            )
        observed[prefix + "efficiency_pct"] = 100 * power / observed[prefix + "pin_w"]
    return {"point": point.key(), "measurements": observed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="retain the raw output of each completed ngspice case",
    )
    args = parser.parse_args()
    if args.log_dir:
        args.log_dir.mkdir(parents=True, exist_ok=True)
    models, ngspice = preflight(parser, args.jobs)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(
            pool.map(
                lambda point: measure(point, models, ngspice, args.log_dir), POINTS
            )
        )
    print(
        json.dumps(
            {
                "ngspice": 46,
                "model_sha256": MODEL_SHA,
                "step_ns": 0.2,
                "edge_ns": 1,
                "load_ma": 10,
                "pulse_us": [length for _, length in PULSES],
                "core_sha256": sha256(ORIGINAL.read_bytes()).hexdigest(),
                "regulator_sha256": sha256(REGULATORS.read_bytes()).hexdigest(),
                "records": rows,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
