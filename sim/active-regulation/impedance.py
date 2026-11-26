"""Measure the biased shunt port in isolation and with the candidate reservoir."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import screen


def measure(point, models, ngspice):
    common = (
        screen.header(point, models)
        + f"""
vinput vin 0 {point.vin}
xref vin ref bandgap
xsh vin ref out regshunt
"""
    )
    result = {"point": point.key(), "bias": {}, "step": {}}
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)
        for current in screen.SHUNT_BIASES_MA:
            commands = [
                "op",
                "let operating_v = v(out)",
                "print operating_v",
                "ac dec 40 1k 1g",
                "let impedance = mag(v(out))",
            ]
            names = {(f"z_{int(f)}"): f for f in screen.FREQ_HZ}
            commands.extend(
                f"meas ac {k} find impedance at={f}" for k, f in names.items()
            )
            deck = (
                common
                + f"iin 0 out dc {current}m ac 1\n.control\nset numdgt=10\n"
                + "\n".join(commands)
                + "\nquit\n.endc\n.end\n"
            )
            data = parse(screen.run_spice(deck, path, ngspice), {"operating_v", *names})
            result["bias"][str(current)] = {
                "vout_v": data["operating_v"],
                "ac_ohm": {str(int(f)): data[k] for k, f in names.items()},
            }
        for reservoir in (False, True):
            cap = (
                "xreservoir out 0 cap_mim_2f0_m4m5_noshield c_length=40u c_width=40u m=109\n"
                if reservoir
                else ""
            )
            deck = (
                common
                + cap
                + """iin 0 out pwl(0 5m .5u 5m .501u 15m .7u 15m .701u 5m)
.control
set numdgt=10
save v(out)
tran .05n 1u 0 .05n
let end_time = vecmax(time)
print end_time
meas tran baseline_v avg v(out) from=.45u to=.49u
meas tran peak_v max v(out) from=.5u to=.7u
meas tran valley_v min v(out) from=.7u to=1u
meas tran hold_v avg v(out) from=.68u to=.69u
quit
.endc
.end
"""
            )
            data = parse(
                screen.run_spice(deck, path, ngspice),
                {"end_time", "baseline_v", "peak_v", "valley_v", "hold_v"},
            )
            if not math.isclose(data["end_time"], 1e-6):
                raise ValueError(f"Incomplete step on {point.key()}")
            data["positive_step_peak_ohm"] = (
                data["peak_v"] - data["baseline_v"]
            ) / 0.010
            data["dc_step_ohm"] = (data["hold_v"] - data["baseline_v"]) / 0.010
            result["step"]["with_reservoir" if reservoir else "bare_shunt"] = data
    return result


def parse(text, names):
    result = {
        k: float(v)
        for k, v in re.findall(r"(?m)^([a-z][a-z0-9_]+)\s+=\s+([-+Ee0-9.]+)", text)
        if k in names
    }
    if set(result) != names or any(not math.isfinite(v) for v in result.values()):
        raise ValueError(
            f"Missing or invalid shunt-port probe: {names - result.keys()}\n{text[-700:]}"
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    models = screen.pdk.find_pdk(screen.HERE.parent).model_lib.parent
    ngspice = shutil.which("ngspice")
    if (
        args.jobs < 1
        or not ngspice
        or not re.search(
            r"ngspice-46\b", subprocess.check_output([ngspice, "--version"], text=True)
        )
    ):
        parser.error("Use ngspice 46 and a positive worker count")
    if {
        n: sha256((models / n).read_bytes()).hexdigest() for n in screen.MODEL_SHA
    } != screen.MODEL_SHA:
        parser.error("GF180D model hashes differ from the pinned parent")
    points = [
        p
        for p in screen.points()
        if p.vin == 3.63
        and p.temp in (-40, 125)
        and p.mim == (p.mos if p.mos in ("ss", "ff") else "typical")
    ]
    points.append(screen.Point("typical", "typical", "typical", "typical", 25, 3.3))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda p: measure(p, models, ngspice), points))
    print(
        json.dumps(
            {
                "ngspice": 46,
                "regulator_sha256": sha256(screen.REGULATORS.read_bytes()).hexdigest(),
                "model_sha256": screen.MODEL_SHA,
                "frequencies_hz": screen.FREQ_HZ,
                "dc_injection_ma": screen.SHUNT_BIASES_MA,
                "records": results,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
