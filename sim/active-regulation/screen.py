"""Measure the physical shunt and LDO with the existing charge-pump core, using ngspice 46."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
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
from harness import pdk  # noqa: E402

ORIGINAL = HERE.parent / "clock-cap-screen" / "candidate.spice"
REGULATORS = HERE / "regulators.spice"
MODEL_SHA = json.loads((ORIGINAL.parent / "records/capacitance.json").read_text())[
    "model_sha256"
]
MOS = ("typical", "ff", "ss", "fs", "sf")
MIM = ("typical", "ff", "ss")
TEMPS = (-40, 25, 125)
VINS = (2.97, 3.30, 3.63)
TERMINALS = (
    ("gs", 1, 2),
    ("gd", 1, 0),
    ("gb", 1, 3),
    ("ds", 0, 2),
    ("db", 0, 3),
    ("sb", 2, 3),
)
SHUNT_BIASES_MA = (5, 15, 30)
FREQ_HZ = (1e3, 1e5, 1e6, 1e7, 1e8, 3e8)


@dataclass(frozen=True)
class Point:
    mos: str
    mim: str
    res: str
    bjt: str
    temp: int
    vin: float

    def key(self):
        return f"{self.mos}/{self.mim}/{self.res}/{self.bjt}/{self.temp}C/{self.vin}V"


def points():
    for mos, temp, vin in product(MOS, TEMPS, VINS):
        passive = mos if mos in ("ss", "ff") else "typical"
        # Exercise all three MIM corners at every S8 high-input hot/cold condition.
        mims = MIM if vin == 3.63 and temp != 25 else (passive,)
        for mim in mims:
            yield Point(mos, mim, passive, passive, temp, vin)


def replace_once(text, old, new):
    if text.splitlines().count(old) != 1:
        raise ValueError(f"Expected one parent circuit line: {old}")
    return text.replace(old, new)


def integrated():
    core = replace_once(
        ORIGINAL.read_text(),
        "* S8 control: externally ideal 5.45 V shunt reference and a 1 ohm on-slope.",
        "* Output feedback and shunt current probe.",
    )
    core = replace_once(
        core,
        "vdriver vr 0 {driver_v}",
        "xdrv vin ref drv regdriver\nvdriver drv vr 0\nxref vin ref bandgap",
    )
    return replace_once(
        core,
        "bshunt out 0 i={clamp_on*max(v(out)-5.45,0)}",
        "vshunt out sh 0\nxsh vin ref sh regshunt",
    )


def inventory(netlist):
    """Resolve the hierarchical primitive terminals that ngspice will actually simulate."""
    blocks, ports = {"": []}, {}
    current = ""
    for raw in netlist.lower().splitlines():
        tokens = raw.split()
        if not tokens:
            continue
        if tokens[0] == ".subckt":
            current = tokens[1]
            ports[current] = tokens[
                2 : tokens.index("params:") if "params:" in tokens else None
            ]
            blocks[current] = []
        elif tokens[0] == ".ends":
            current = ""
        elif tokens[0].startswith("x"):
            end = next((i for i, word in enumerate(tokens) if "=" in word), len(tokens))
            blocks[current].append((tokens[0], tokens[end - 1], tokens[1 : end - 1]))
    mos, caps, bipolar = {}, {}, {}

    def walk(block, prefix, mapping):
        for name, model, nets in blocks[block]:
            instance = prefix + name
            actual = [mapping.get(n, "0" if n == "0" else prefix + n) for n in nets]
            if model in blocks:
                if len(ports[model]) != len(actual):
                    raise ValueError(f"Port-count mismatch on {instance}")
                walk(model, instance + ".", dict(zip(ports[model], actual)))
            elif model in ("nfet_03v3", "pfet_03v3", "nfet_06v0", "pfet_06v0"):
                mos[instance] = (model, actual)
            elif model.startswith("cap_mim_"):
                caps[instance] = actual
            elif model.startswith("pnp_"):
                bipolar[instance] = actual
            elif not model.startswith("ppolyf_"):
                raise ValueError(f"Unclassified device {model} on {instance}")

    walk("", "", {})
    return mos, caps, bipolar


def voltage(node):
    return "0" if node == "0" else "v(" + node + ")"


def run_spice(deck, folder, ngspice):
    (folder / "bench.cir").write_text(deck)
    result = subprocess.run(
        [ngspice, "-b", "bench.cir"], cwd=folder, capture_output=True, text=True
    )
    text = result.stdout + "\n" + result.stderr
    if (
        result.returncode
        or "timestep too small" in text.lower()
        or "fatal error" in text.lower()
    ):
        raise RuntimeError(text[-1800:])
    return text


def read_measurements(output, required, optional=frozenset()):
    values = {}
    for key, value in re.findall(
        r"(?m)^([a-z][a-z0-9_]*)[ \t]*=[ \t]*([-+.Ee0-9]+)", output
    ):
        if key in required or key in optional:
            if key in values:
                raise ValueError(f"Duplicate ngspice measurement {key}")
            values[key] = float(value)
    missing = required - values.keys()
    if missing or not all(math.isfinite(v) for v in values.values()):
        raise ValueError(
            f"Missing or nonfinite ngspice measurements: {sorted(missing)}\n"
            f"{output[-700:]}"
        )
    for key in sorted(optional - values.keys()):
        values[key] = None
    return values


def header(point, models):
    return "\n".join(
        [
            "Feedback-controlled GF180D charge pump",
            f'.include "{models}/design.ngspice"',
            *(
                f'.lib "{models}/sm141064.ngspice" {section}'
                for section in (
                    point.mos,
                    "mimcap_" + point.mim,
                    "res_" + point.res,
                    "bjt_" + point.bjt,
                )
            ),
            f".temp {point.temp}",
            f".param input_v={point.vin} driver_v={point.vin} wire_c=5f delay_side=8u",
            ".options method=gear maxord=2",
            REGULATORS.read_text(),
        ]
    )


def extrema_pairs(devices, caps, bipolar):
    pairs = set()
    for model, nets in devices.values():
        pairs.update((nets[a], nets[b]) for _, a, b in TERMINALS)
    pairs.update(tuple(nets) for nets in caps.values())
    pairs.update((nets[2], nets[1]) for nets in bipolar.values())
    return sorted((a, b) for a, b in pairs if a != b)


def grouped_stress(devices, caps, bipolar, extrema):
    def values(a, b):
        return (0.0, 0.0) if a == b else extrema[a, b]

    groups = {}
    for name, (model, nets) in devices.items():
        group = groups.setdefault(model[5:], {})
        for label, a, b in TERMINALS:
            lo, hi = values(nets[a], nets[b])
            metrics = {label: max(abs(lo), abs(hi))}
            if label in ("db", "sb"):
                metrics[label + "_forward"] = hi if model.startswith("p") else -lo
            for k, v in metrics.items():
                if k not in group or v > group[k][0]:
                    group[k] = [v, name]
    max_mim = max(
        (max(abs(x) for x in values(*nets)), name) for name, nets in caps.items()
    )
    max_be = max((values(nets[2], nets[1])[1], name) for name, nets in bipolar.items())
    return {"mos_v": groups, "max_mim_v": max_mim, "max_pnp_eb_v": max_be}


def transient(point, models, ngspice, step_ns=0.2, ramp=False, variant=None):
    circuit = integrated()
    if variant == "open_shunt":
        circuit = replace_once(circuit, "xsh vin ref sh regshunt", "rprobe sh 0 1t")
    elif variant == "prescribed_driver":
        # Reuse the exact low-input driver supply from the parent experiment.
        if point.vin != 2.97:
            raise ValueError("This control compares the 2.97 V dropout corner")
        circuit = replace_once(
            circuit, "xdrv vin ref drv regdriver", "vforced drv 0 2.97"
        )
    elif variant == "one_ns_load":
        circuit = replace_once(
            circuit,
            "iload out 0 pwl(0 0 2u 0 12u 10m 22u 10m 22.1u 0)",
            "iload out 0 pwl(0 0 2u 0 2.001u 10m 22u 10m 22.1u 0)",
        )
    elif variant is not None:
        raise ValueError(f"Unknown control {variant}")
    if ramp:
        circuit = replace_once(
            circuit, "vinput vin 0 {input_v}", "vinput vin 0 pwl(0 0 1u {input_v})"
        )
        circuit = replace_once(
            circuit,
            "ven en 0 pwl(0 0 100n 0 102n {driver_v})",
            "ven en 0 pwl(0 0 1.5u 0 1.502u {driver_v})",
        )
    devices, caps, bipolar = inventory(REGULATORS.read_text() + "\n" + circuit)
    pairs = extrema_pairs(devices, caps, bipolar)
    nodes = sorted(
        {n for pair in pairs for n in pair if n != "0"}
        | {"clk", "out", "vr", "ref", "vin"}
    )
    commands = [
        ".control",
        "set numdgt=10",
        "save "
        + " ".join(voltage(n) for n in nodes)
        + " i(vinput) i(vshunt) i(vdriver) i(vbody1) i(vbody2)",
        f"tran {step_ns}n 24u 0 {step_ns}n",
        "let end_time = vecmax(time)",
        "print end_time",
    ]
    required = {"end_time"}
    periods = ("before", "ramp", "load", "settled", "release")
    windows = ((1.75, 2), (2, 12), (12, 22), (20, 22), (22, 24))
    for period, (lo, hi) in zip(periods, windows):
        for net in ("out", "vr", "ref"):
            for op in ("min", "max"):
                key = f"{period}_{net}_{op}"
                commands.append(f"meas tran {key} {op} v({net}) from={lo}u to={hi}u")
                required.add(key)
    for net in ("out", "ref", "vr"):
        key = "all_" + net + "_max"
        commands += [f"let {key} = vecmax(v({net}))", f"print {key}"]
        required.add(key)
    for label, expression in (
        ("shunt_a", "i(vshunt)"),
        ("input_a", "-i(vinput)"),
        ("driver_a", "i(vdriver)"),
        ("shunt_w", "v(out)*i(vshunt)"),
    ):
        commands.append(f"let sample = {expression}")
        for key, start, end in (("loaded", 20, 22), ("unloaded", 23.5, 24)):
            name = key + "_" + label
            commands.append(f"meas tran {name} avg sample from={start}u to={end}u")
            required.add(name)
    # A fully completed transient with insufficient clock crossings is a measured failure.
    optional = set()
    for net in ("clk", "clkb"):
        name = "twenty_" + net
        commands.append(
            f"meas tran {name} trig v({net}) val=1.3 rise=2 td=20u targ v({net}) val=1.3 rise=22 td=20u"
        )
        optional.add(name)
    for i, (a, b) in enumerate(pairs):
        commands.append(f"let delta_v = {voltage(a)} - {voltage(b)}")
        for op in ("min", "max"):
            key = f"pair{i}_{op}"
            commands += [f"let {key} = vec{op}(delta_v)", f"print {key}"]
            required.add(key)
    commands += ["quit", ".endc", ".end"]
    with tempfile.TemporaryDirectory() as tmp:
        output = run_spice(
            header(point, models) + "\n" + circuit + "\n" + "\n".join(commands) + "\n",
            Path(tmp),
            ngspice,
        )
    try:
        result = read_measurements(output, required, optional)
    except ValueError as exc:
        raise ValueError(f"Incomplete {point.key()} transient: {exc}") from exc
    if not math.isclose(result["end_time"], 24e-6):
        raise ValueError(
            f"Incomplete {point.key()} transient, end_time {result['end_time']}\n"
            f"{output[-700:]}"
        )
    extrema = {
        pair: tuple(result.pop(f"pair{i}_{op}") for op in ("min", "max"))
        for i, pair in enumerate(pairs)
    }
    return {
        "point": point.key(),
        "step_ns": step_ns,
        "supply_ramp": ramp,
        **({"variant": variant} if variant is not None else {}),
        "measurements": result,
        **grouped_stress(devices, caps, bipolar, extrema),
    }


def preflight(parser, jobs):
    ngspice = shutil.which("ngspice")
    if (
        jobs < 1
        or not ngspice
        or not re.search(
            r"ngspice-46\b", subprocess.check_output([ngspice, "--version"], text=True)
        )
    ):
        parser.error("Use ngspice 46 and a positive worker count")
    models = pdk.find_pdk(HERE.parent).model_lib.parent
    if {
        n: sha256((models / n).read_bytes()).hexdigest() for n in MODEL_SHA
    } != MODEL_SHA:
        parser.error("GF180D model hashes differ from the pinned parent")
    return models, ngspice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("pvt", "controls", "smoke", "isolation"))
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    models, device = preflight(parser, args.jobs)
    cases = [(p, 0.2, False) for p in points()]
    if args.suite == "smoke":
        cases = [
            (Point("typical", "typical", "typical", "typical", 25, 3.3), 0.2, False)
        ]
    if args.suite == "controls":
        cases = [
            (Point("ff", "ff", "ff", "ff", -40, 3.63), 0.1, False),
            (Point("ss", "ff", "ss", "ss", 125, 2.97), 0.1, False),
            (Point("typical", "typical", "typical", "typical", 25, 3.3), 0.1, True),
            (Point("ss", "ff", "ff", "ff", 125, 2.97), 0.2, False),
            (Point("ff", "ss", "ss", "ss", -40, 3.63), 0.2, False),
        ]
    cases = [(*case, None) for case in cases]
    if args.suite == "isolation":
        cold = Point("ff", "ff", "ff", "ff", -40, 3.63)
        hot = Point("ss", "ss", "ss", "ss", 125, 2.97)
        cases = [
            (cold, 0.2, False, "open_shunt"),
            (hot, 0.2, False, "prescribed_driver"),
            (cold, 0.2, False, "one_ns_load"),
            (hot, 0.2, False, "one_ns_load"),
        ]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(
            pool.map(lambda t: transient(t[0], models, device, t[1], t[2], t[3]), cases)
        )
    print(
        json.dumps(
            {
                "ngspice": 46,
                "model_sha256": MODEL_SHA,
                "core_sha256": sha256(ORIGINAL.read_bytes()).hexdigest(),
                "regulator_sha256": sha256(REGULATORS.read_bytes()).hexdigest(),
                "order": "MOS/MIM/resistor/bipolar/temperature/input",
                "records": rows,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
