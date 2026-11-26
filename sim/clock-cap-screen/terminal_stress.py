"""Measure simultaneous MOS terminal differences over the complete 24 µs trace."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import screen

# Drain, gate, source, body order follows the pinned candidate. Only the
# common inv3 and inv6 stage types expand, exactly as instantiated there.
PAIRS = ("ds", "gs", "db", "gb", "gd", "sb")


def terminals():
    devices = {}
    blocks = {}
    sub = None
    for line in (screen.HERE / "candidate.spice").read_text().lower().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("*"):
            continue
        if fields[0] == ".subckt":
            sub = fields[1]
            blocks[sub] = []
        elif fields[0] == ".ends":
            sub = None
        elif sub:
            blocks[sub].append(fields)
        elif fields[0].startswith("x"):
            if fields[4] in ("inv3", "inv6"):
                pins = dict(zip(("a", "z", "vp", "0"), [*fields[1:4], "0"]))
                for transistor in blocks[fields[4]]:
                    rating = 3.3 if fields[4] == "inv3" else 6.0
                    devices[fields[0] + "." + transistor[0]] = (
                        rating,
                        [pins[n] for n in transistor[1:5]],
                    )
            elif len(fields) > 5 and fields[5] in ("n6", "p6"):
                devices[fields[0]] = (6.0, fields[1:5])
    if len(devices) != 24:
        raise ValueError(f"Unexpected transistor count: {len(devices)}")
    return devices


def differences(devices):
    result = {}
    for name, (rating, pins) in devices.items():
        nodes = dict(zip("dgsb", pins))
        result[name] = {
            "rating_v": rating,
            "pairs": {pair: [nodes[pair[0]], nodes[pair[1]]] for pair in PAIRS},
        }
    return result


def cases():
    for case in screen.points():
        yield "grid", case, False, 1
    for case in screen.SENSITIVITY:
        yield "controls", case, False, 1
    for case in screen.GEAR_CONTROLS:
        yield "gear", case, True, 1
    for temp, ohms in itertools.product((-40, 125), (1, 2, 4)):
        yield "shunt", ("ff", "mimcap_ff", temp, 3.63, 8, True, 0.05), True, ohms


def observe(job, models, ngspice, devices):
    suite, case, gear, ohms = job
    pairs = sorted(
        {
            tuple(nodes)
            for device in devices.values()
            for nodes in device["pairs"].values()
        }
    )
    lines = screen.transient_setup(case, models, True, gear, ohms)
    # Use the original voltage/current measurements and their generated
    # probe sources. Evaluate terminal differences on saved time samples
    # after the solve: no artificial current enters a device terminal.
    lines.extend(
        f".meas tran {key} {val}"
        for key, val in screen.measures(True, screen.DRIVER_V[case[3]]).items()
    )
    lines += [".control", "set numdgt=10", "run"]
    for a, b in pairs:
        if a == b:
            continue
        signal = "0" if a == "0" else f"v({a})"
        other = "0" if b == "0" else f"v({b})"
        stem = f"t_{a}_{b}"
        lines.extend(
            [
                f"let diff = {signal} - {other}",
                f"let {stem}_lo = minimum(diff)",
                f"let {stem}_hi = maximum(diff)",
                f"print {stem}_lo {stem}_hi",
            ]
        )
    lines.extend(
        [
            "meas tran full_t max time",
            "meas tran release_peak max v(out) from=22u to=24u",
            "meas tran hold_min min v(out) from=12u to=22u",
            "quit",
            ".endc",
            ".end",
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "stress.cir"
        path.write_text("\n".join(lines) + "\n")
        run = subprocess.run([ngspice, "-b", str(path)], capture_output=True, text=True)
    if run.returncode or "timestep too small" in (run.stdout + run.stderr).lower():
        raise ValueError(f"Incomplete stress transient {job}: {run.stderr[-500:]}")
    observed = {
        k: float(v)
        for k, v in re.findall(r"(?m)^([a-z_0-9]+)\s+=\s+([-+0-9.eE]+)", run.stdout)
    }
    if abs(observed.get("full_t", 0) - 24e-6) > 1e-10:
        raise ValueError(f"Truncated transient {job}: {run.stdout[-700:]}")
    extremes = {}
    for a, b in pairs:
        extrema = (
            [0, 0] if a == b else [observed[f"t_{a}_{b}_{s}"] for s in ("lo", "hi")]
        )
        if not all(map(math.isfinite, extrema)) or extrema[0] > extrema[1]:
            raise ValueError(f"Invalid {a}-{b}")
        extremes[a + "-" + b] = extrema
    return {
        "suite": suite,
        "mos": case[0],
        "mim": case[1],
        "temp_c": case[2],
        "vin_v": case[3],
        "delay_side_um": case[4],
        "shunt": case[5],
        "max_step_ns": case[6],
        "gear2": gear,
        "shunt_ohms": ohms if case[5] else None,
        "duration_s": observed["full_t"],
        "release_peak_v": observed["release_peak"],
        "hold_min_v": observed["hold_min"],
        "terminal_extrema_v": extremes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    models = screen.pdk.find_pdk(screen.HERE.parent).model_lib.parent
    sim = shutil.which("ngspice")
    if not sim or "ngspice-46 " not in subprocess.check_output(
        [sim, "--version"], text=True
    ):
        parser.error("ngspice 46 is required")
    if {
        name: screen.digest(models / name) for name in screen.MODEL_SHA
    } != screen.MODEL_SHA:
        parser.error("Unexpected GF180 model digest")
    devices = differences(terminals())
    with ThreadPoolExecutor(args.jobs) as workers:
        rows = list(
            workers.map(lambda job: observe(job, models, sim, devices), cases())
        )
    print(
        json.dumps(
            {
                "ngspice": 46,
                "circuit_sha256": screen.digest(screen.HERE / "candidate.spice"),
                "model_sha256": screen.MODEL_SHA,
                "device_terminals": devices,
                "records": rows,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
