"""Run the GF180D clock and MIM feasibility experiment with ngspice 46."""

import argparse
import concurrent.futures
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from harness import corners, pdk  # noqa: E402

MODEL_SHA = {
    "design.ngspice": "7e222f050318388f37543a64fbd0be55cc15e4b93f57501a09f7c159c4c9e561",
    "sm141064.ngspice": "f6f4a96e18fc5ad11270ad3451aaecc7ac37fc81eb61e15b0d7d94c7bc594a24",
    "sm141064.spice": "f6f4a96e18fc5ad11270ad3451aaecc7ac37fc81eb61e15b0d7d94c7bc594a24",
    "sm141064_mim.spice": "9b85cd009968d9aeb6b61046b24a63f39d6a463c4e4aee3949c8fd183c06666f",
}
DRIVER_V = {2.97: 2.97, 3.30: 2.85, 3.63: 2.80}
SENSITIVITY = [
    # (MOS, MIM, temperature, input, timing side, shunt, maximum step in ns)
    ("ss", "mimcap_ss", 125, 3.63, 9, True, 0.1),
    ("ff", "mimcap_ff", -40, 3.63, 8, False, 0.1),
    ("ff", "mimcap_ff", 125, 3.63, 8, False, 0.1),
    ("typical", "mimcap_typical", 25, 3.30, 8, True, 0.05),
]
GEAR_CONTROLS = [
    ("typical", "mimcap_typical", 25, 3.30, 8, True, 0.05),
    ("ss", "mimcap_ss", 125, 3.63, 8, True, 0.05),
    ("fs", "mimcap_ss", -40, 3.63, 8, True, 0.05),
    ("ff", "mimcap_ff", -40, 3.63, 8, False, 0.05),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def points():
    for c, t, v in itertools.product(
        corners.resolve_corners(["mos_mimcap"]), (-40, 25, 125), DRIVER_V
    ):
        yield (*c.sections, t, v, 8, True, 0.1)


def measures(long_run, driver):
    values = {}
    # Use the final driver output for frequency; twenty whole cycles reject a glitch.
    start = "20u" if long_run else "200n"
    for name, net in (("period20_a", "clk"), ("period20_b", "clkb")):
        values[name] = (
            f"trig v({net}) val={driver / 2} rise=2 td={start} "
            f"targ v({net}) val={driver / 2} rise=22 td={start}"
        )
    if long_run:
        for name, signal in {
            "a_ground": "v(a)",
            "b_ground": "v(b)",
            "clk_ground": "v(clk)",
            "clkb_ground": "v(clkb)",
            "reservoir": "v(out)",
            "fly_a": "par('v(a)-v(clk)')",
            "fly_b": "par('v(b)-v(clkb)')",
            "delay0": "v(r0)",
            "delay1": "v(r1)",
            "delay2": "v(r2)",
        }.items():
            for op in ("min", "max"):
                values[f"{name}_{op}"] = f"{op} {signal}"
        for name, (first, last) in {
            "before_load": (1.5, 2),
            "ramp": (2, 12),
            "at_10ma": (12, 22),
            "steady_10ma": (20, 22),
            "release": (22, 24),
        }.items():
            for op in ("min", "max"):
                values[f"{name}_{op}"] = f"{op} v(out) from={first}u to={last}u"
        for name, signal in (
            ("body1", "i(vbody1)"),
            ("body2", "i(vbody2)"),
            ("driver", "i(vdriver)"),
        ):
            for op in ("min", "max"):
                values[f"{name}_{op}"] = f"{op} {signal}"
    return values


def transient_setup(case, models, long_run, gear, shunt_ohms=1):
    mos, mim, temp, vin, side, clamp, step = case
    driver = DRIVER_V[vin]
    return [
        "Enabled ring and pump capacitor feasibility",
        f'.include "{models}/design.ngspice"',
        f'.lib "{models}/sm141064.ngspice" {mos}',
        f'.lib "{models}/sm141064.ngspice" {mim}',
        f".temp {temp}",
        f".param input_v={vin} driver_v={driver} wire_c=5f delay_side={side}u clamp_on={int(clamp) / shunt_ohms:g}",
        f'.include "{HERE / "candidate.spice"}"',
        *([".options method=gear maxord=2"] if gear else []),
        f".tran {step}n {'24u' if long_run else '650n'} 0 {step}n",
    ]


def run_spice(lines, ngspice, label, filename="bench.cir"):
    with tempfile.TemporaryDirectory() as workspace:
        deck = Path(workspace) / filename
        deck.write_text("\n".join(lines) + "\n")
        run = subprocess.run([ngspice, "-b", str(deck)], capture_output=True, text=True)
    output = run.stdout + "\n" + run.stderr
    if run.returncode or "timestep too small" in output.lower():
        raise ValueError(f"Incomplete {label}:\n{output[-1000:]}")
    return output


def read_measurements(output, required):
    values = {}
    for key, value in re.findall(r"(?m)^([a-z_0-9]+)[ \t]*=[ \t]*([-+0-9.eE]+)", output):
        if key in required:
            if key in values:
                raise ValueError(f"Duplicate ngspice measurement {key}")
            values[key] = float(value)
    unusable = sorted(required - values.keys()) + sorted(
        key for key, value in values.items() if not math.isfinite(value)
    )
    if unusable:
        raise ValueError(f"Missing or non-finite ngspice measurements {unusable}:\n{output[-700:]}")
    return values


def simulate(case, models, ngspice, long_run, gear=False):
    mos, mim, temp, vin, side, clamp, step = case
    driver = DRIVER_V[vin]
    values = measures(long_run, driver)
    if gear:
        for name, signal in (
            ("body1", "i(vbody1)"),
            ("body2", "i(vbody2)"),
            ("driver", "i(vdriver)"),
        ):
            for op in ("min", "max"):
                values[f"steady_{name}_{op}"] = f"{op} {signal} from=20u to=22u"
    lines = [
        *transient_setup(case, models, long_run, gear),
        *(f".meas tran {name} {expr}" for name, expr in values.items()),
        ".end",
    ]
    output = run_spice(lines, ngspice, f"measurements for {case}", "screen.cir")
    # Do not let a missing measure or truncated transient become a passing corner.
    try:
        observed = read_measurements(output, values.keys())
    except ValueError as exc:
        raise ValueError(f"Incomplete measurements for {case}: {exc}") from exc
    result = {name: observed[name] for name in values}
    return {
        "mos": mos,
        "mim": mim,
        "temp_c": temp,
        "vin_v": vin,
        "driver_v": driver,
        "delay_side_um": side,
        "shunt": clamp,
        "step_ns": step,
        "measurements": result,
    }


def capacitance(models, ngspice):
    """Measure the actual subcircuit multipliers in isolation at 25 C and zero DC bias."""
    source = (HERE / "candidate.spice").read_text().splitlines()
    cells = {
        line.split()[0]: " ".join(line.split()[3:])
        for line in source
        if line.startswith(("xca ", "xcb ", "xco ", "xtime0 "))
    }
    cells["xunit"] = "cap_mim_2f0_m4m5_noshield c_length=40u c_width=40u"
    results = []
    for mim in ("mimcap_ff", "mimcap_typical", "mimcap_ss"):
        deck = [
            "Isolated candidate capacitor banks",
            f'.include "{models}/design.ngspice"',
            f'.lib "{models}/sm141064.ngspice" {mim}',
            ".temp 25",
            ".param delay_side=8u",
        ]
        for name, cell in cells.items():
            deck.extend([f"v{name} {name} 0 ac 1", f"{name} {name} 0 {cell}"])
        deck.extend([".control", "ac lin 1 1k 1k"])
        for name in cells:
            deck.extend([f"let {name}_pf = -imag(i(v{name}))/(2*pi*1k)/1p", f"print {name}_pf"])
        deck.extend(["quit", ".endc", ".end"])
        text = run_spice(deck, ngspice, f"AC capacitor measurements at {mim}", "caps.cir")
        try:
            printed = read_measurements(text, {f"{name}_pf" for name in cells})
        except ValueError as exc:
            raise ValueError(f"Missing AC capacitor measurements at {mim}: {exc}") from exc
        values = {name: printed[f"{name}_pf"] for name in cells}
        if not all(v > 0 for v in values.values()):
            raise ValueError(f"Missing AC capacitor measurements at {mim}")
        for name, count in (("xca", 56), ("xcb", 56), ("xco", 109)):
            if not math.isclose(values[name] / values["xunit"], count, rel_tol=1e-5):
                raise ValueError(f"{name} did not reproduce {count} unit capacitors")
        results.append({"mim": mim, "capacitance_pf": values})
    return results


def preflight(parser, jobs):
    if jobs < 1:
        parser.error("--jobs must be positive")
    tool = shutil.which("ngspice")
    if not tool or not re.search(
        r"ngspice-46\b", subprocess.check_output([tool, "--version"], text=True)
    ):
        parser.error("Install ngspice 46 on PATH")
    models = pdk.find_pdk(HERE.parent).model_lib.parent
    if {name: digest(models / name) for name in MODEL_SHA} != MODEL_SHA:
        parser.error("The installed GF180 models differ from open_pdks f6eeac7d")
    return models, tool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("clock", "load", "controls", "gear", "capacitance"))
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    models, tool = preflight(parser, args.jobs)
    cases = list(points())
    if args.suite == "controls":
        cases = SENSITIVITY
    elif args.suite == "gear":
        cases = GEAR_CONTROLS
    if args.suite == "capacitance":
        records = capacitance(models, tool)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            records = list(
                pool.map(
                    lambda case: simulate(
                        case, models, tool, args.suite != "clock", args.suite == "gear"
                    ),
                    cases,
                )
            )
    print(
        json.dumps(
            {
                "ngspice": 46,
                "circuit_sha256": digest(HERE / "candidate.spice"),
                "model_sha256": MODEL_SHA,
                "suite": args.suite,
                "records": records,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
