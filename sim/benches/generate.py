"""Generate the charge-pump benches: device-stress, load, load-step, startup.

The harness forbids ``.include`` in a fragment, so the DUT cannot be pulled in
by reference. Each bench's ``testbench/netlist.spice`` is therefore
``dut_reference.spice`` + a bench-specific stimulus section, assembled here, and
``testbench/tb.json`` is written from the tables below. ``--check`` fails if a
committed file differs from what this script would write.

Replacing the DUT (#1): edit ``dut_reference.spice`` and ``DEVICES``; stimulus,
corner set and limits do not change. The time base is derived from
``START_MAX_S`` (see ``T_SETTLE``): a DUT allowed that long to start is still
fully started, and at steady load, before any stress window or load step.
``tests/test_benches.py`` checks ``DEVICES`` against the DUT netlist.

ASSUMPTIONS (values, not structure; ratification of #1 changes a number here):
  * Vout 5.0 V +/-10 %, >= 10 mA: efuse-otp program-path assumptions as quoted
    in issue #2. The 10 us is taken as the load-step edge time.
  * RATING_V = 6.0 V on every |Vds|, |Vgs|, |Vdb|, |Vsb|, |Vgb| of the 6 V
    devices: the PDK names them "6.0V" devices and carries no numeric terminal
    rating, so the name-plate is the only supported number (deliberately NOT
    padded). UNCONFIRMED against a foundry document: confirm in the
    spec/decision record; do not raise it without one.
  * RIPPLE_MAX_V and START_MAX_S are PLACEHOLDERS pending #1.

Output-voltage rule: every Vout measurement name carries its load current, the
corner/temperature/supply come from the PVT point, and no bench measures an
unloaded output (tests/test_benches.py enforces both).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
DUT = (HERE / "dut_reference.spice").read_text()

NOMINAL_V = 3.3
TOL = 0.10
TEMPS = [-40.0, 25.0, 125.0]
CORNERS = ["tt", "ff", "ss", "fs", "sf"]
VOUT_NOM, VOUT_TOL = 5.0, 0.10
VOUT_MIN = VOUT_NOM * (1 - VOUT_TOL)
ILOAD_MA = 10
RATING_V = 6.0
RIPPLE_MAX_V = 0.25
START_MAX_S = 100e-6
#: A DUT may take START_MAX_S to start; every measurement window and the load
#: step begin after twice that, so a slow starter is never measured mid-ramp.
T_SETTLE_S = 2 * START_MAX_S
T_WINDOW_S = 10e-6   # steady-state measurement window after T_SETTLE_S
T_STEP_S = 10e-6     # load-step edge time
T_POST_S = 40e-6     # observation after the load-step edge completes
TDEL_START_S = 1e-6  # start-up bench: clock enable delay

#: (instance, drain, gate, source, bulk) as nodes of the testbench.
DEVICES = [
    ("xmn1", "xdut.a", "xdut.b", "vin", "0"),
    ("xmn2", "xdut.b", "xdut.a", "vin", "0"),
    ("xmp1", "xdut.a", "xdut.b", "vout", "vout"),
    ("xmp2", "xdut.b", "xdut.a", "vout", "vout"),
]
METRICS = {"vds": (0, 2), "vgs": (1, 2), "vdb": (0, 3), "vsb": (2, 3), "vgb": (1, 3)}

COMMON = """\
* ---- stimulus (harness owns vdd_val / temp_c) -----------------------------
.param fclk=10meg tr=2n tdel=%(tdel)s
vin vin 0 dc {vdd_val}
vclk clk 0 pulse(0 {vdd_val} {tdel} {tr} {tr} {0.5/fclk-tr} {1/fclk})
vclkb clkb 0 pulse({vdd_val} 0 {tdel} {tr} {tr} {0.5/fclk-tr} {1/fclk})
xdut vin vout clk clkb 0 pump_dut
cout vout 0 1n
"""
TMAX = "1n"


def us(t: float) -> str:
    return f"{t * 1e6:.6g}u"

# Windowed statistics: mask * value over ngspice's own time points. NOTE: these
# are sample statistics over non-uniform timesteps, so ``mean`` is not a true
# time average (biased toward dense-edge regions). Every pass/fail check uses
# min/max, which are unaffected; means are reported values only.


def v(node: str) -> str:
    return "0" if node == "0" else f"v({node})"


def window(t0: str, t1: str) -> str:
    return f"((time>{t0})&(time<{t1}))"


def w_mean(vec: str, t0: str, t1: str) -> str:
    s = window(t0, t1)
    return f"mean({s}*{vec})/mean({s})"


def w_max(vec: str, t0: str, t1: str) -> str:
    s = window(t0, t1)
    return f"maximum({s}*{vec}-(1-{s})*1e3)"


def w_min(vec: str, t0: str, t1: str) -> str:
    s = window(t0, t1)
    return f"-maximum(-{s}*{vec}-(1-{s})*1e3)"


def stress():
    """(measure, checks) for every device terminal pair over the whole transient."""
    measure = {}
    for inst, *n in DEVICES:
        for name, (i, j) in METRICS.items():
            measure[f"stress_{inst}_{name}_v"] = f"maximum(abs({v(n[i])}-{v(n[j])}))"
    checks = {k: {"max": RATING_V,
                  "description": f"rated limit {RATING_V} V (UNCONFIRMED; see generate.py)"}
              for k in measure}
    return measure, checks


def device_stress():
    measure, checks = stress()
    t_stop = T_SETTLE_S + T_WINDOW_S
    stim = COMMON % {"tdel": "0"} + (
        f"* full load: resistor sized for {ILOAD_MA} mA at {VOUT_MIN:g} V. (An ideal current\n"
        f"* sink would drive Vout unphysically negative if the pump cannot supply it.)\n"
        + f"rload vout 0 {VOUT_MIN / (ILOAD_MA * 1e-3):g}\n"
    )
    return stim, dict(
        description="Per-device Vds/Vgs/Vdb/Vsb/Vgb maxima over the full transient at every PVT "
                    f"point at {ILOAD_MA} mA load, each against the device rating.",
        claim=f"No device exceeds its rated terminal voltage at any PVT point at {ILOAD_MA} mA "
              "load, transients included.",
        analyses=[f"tran 1n {us(t_stop)} 0 {TMAX}"], measure=measure, checks=checks)


def load():
    r = f"{VOUT_MIN / (ILOAD_MA * 1e-3):g}"
    stim = COMMON % {"tdel": "0"} + (
        f"* resistive load sized for {ILOAD_MA} mA at the {VOUT_MIN:g} V lower bound.\n"
        f"rload vout 0 {r}\n"
    )
    t0, t1 = us(T_SETTLE_S), us(T_SETTLE_S + T_WINDOW_S)
    measure = {
        f"vout_at_{ILOAD_MA}ma_resistive_mean_v": w_mean("v(vout)", t0, t1),
        f"vout_at_{ILOAD_MA}ma_resistive_min_v": w_min("v(vout)", t0, t1),
        f"vout_at_{ILOAD_MA}ma_resistive_max_v": w_max("v(vout)", t0, t1),
        f"ripple_at_{ILOAD_MA}ma_resistive_pp_v":
            f"{w_max('v(vout)', t0, t1)}-({w_min('v(vout)', t0, t1)})",
        f"iload_{ILOAD_MA}ma_resistive_mean_a": w_mean("v(vout)", t0, t1) + f"/{r}",
        f"iload_{ILOAD_MA}ma_resistive_min_a": w_min("v(vout)", t0, t1) + f"/{r}",
    }
    checks = {
        f"vout_at_{ILOAD_MA}ma_resistive_min_v": {"min": VOUT_MIN},
        f"vout_at_{ILOAD_MA}ma_resistive_max_v": {"max": VOUT_NOM * (1 + VOUT_TOL)},
        f"ripple_at_{ILOAD_MA}ma_resistive_pp_v": {"max": RIPPLE_MAX_V},
        # The realized load is a checked quantity, not an inference from the name.
        f"iload_{ILOAD_MA}ma_resistive_min_a": {"min": ILOAD_MA * 1e-3},
    }
    return stim, dict(
        description=f"Steady Vout and ripple into a {r} ohm resistive load ({ILOAD_MA} mA at "
                    f"{VOUT_MIN:g} V), reported per corner. No unloaded figure is measured.",
        claim=f"Vout stays within {VOUT_NOM}V+/-{VOUT_TOL*100:g}% at >= {ILOAD_MA} mA at every PVT point.",
        analyses=[f"tran 1n {us(T_SETTLE_S + T_WINDOW_S)} 0 {TMAX}"], measure=measure, checks=checks)


def load_step():
    tstep, t_end = T_SETTLE_S, T_SETTLE_S + T_STEP_S + T_POST_S
    t_ramped = tstep + T_STEP_S
    stim = COMMON % {"tdel": "0"} + (
        f".param tstep={us(tstep)}\n"
        f"* step: a resistive load ({ILOAD_MA} mA at {VOUT_MIN:g} V) ramps in over {us(T_STEP_S)} at tstep.\n"
        f"* The 5 kohm pre-step resistor is a keep-alive, NOT a reported load.\n"
        f"rkeep vout 0 5k\n"
        f"bstep vout 0 i='v(vout)/{VOUT_MIN / (ILOAD_MA * 1e-3):g}*min(max((time-tstep)/{T_STEP_S * 1e6:g}u,0),1)'\n"
    )
    measure = {
        f"vout_step_to_{ILOAD_MA}ma_post_mean_v": w_mean("v(vout)", us(t_ramped + T_POST_S / 2), us(t_end)),
        f"vout_step_to_{ILOAD_MA}ma_post_min_v": w_min("v(vout)", us(t_ramped), us(t_end)),
        f"vout_step_to_{ILOAD_MA}ma_post_max_v": w_max("v(vout)", us(t_ramped), us(t_end)),
        "vds_peak_pmos_during_step_v": w_max("abs(v(xdut.a)-v(vout))", us(tstep), us(t_end)),
    }
    checks = {
        f"vout_step_to_{ILOAD_MA}ma_post_min_v": {"min": VOUT_MIN},
        f"vout_step_to_{ILOAD_MA}ma_post_max_v": {"max": VOUT_NOM * (1 + VOUT_TOL)},
        "vds_peak_pmos_during_step_v": {"max": RATING_V},
    }
    # Full stress coverage over the whole step transient (startup + step edge).
    s_measure, s_checks = stress()
    measure.update(s_measure)
    checks.update(s_checks)
    return stim, dict(
        description=f"Vout after a {T_STEP_S * 1e6:g} us step to {ILOAD_MA} mA, min over the transient and settled "
                    "mean; peak Vds of the output devices during the step; every device terminal pair against "
                    "its rating over the whole transient.",
        claim=f"Vout never leaves {VOUT_NOM}V+/-{VOUT_TOL*100:g}% through a step to {ILOAD_MA} mA.",
        analyses=[f"tran 1n {us(t_end)} 0 {TMAX}"], measure=measure, checks=checks)


def startup():
    t_stop = TDEL_START_S + START_MAX_S + 20e-6  # long enough to see a limit miss
    stim = COMMON % {"tdel": us(TDEL_START_S)} + (
        f"* enable = clock start at {us(TDEL_START_S)}; supply present from t=0; resistive full load.\n"
        + f"rload vout 0 {VOUT_MIN / (ILOAD_MA * 1e-3):g}\n"
    )
    above = f"(v(vout)>{VOUT_MIN})"
    measure = {
        f"startup_to_{round(VOUT_MIN*1000)}mv_at_{ILOAD_MA}ma_s": f"minimum(time+(1-{above})*1)-{us(TDEL_START_S)}",
    }
    checks = {f"startup_to_{round(VOUT_MIN*1000)}mv_at_{ILOAD_MA}ma_s": {"max": START_MAX_S}}
    s_measure, s_checks = stress()  # every device terminal pair over the whole start-up
    measure.update(s_measure)
    checks.update(s_checks)
    return stim, dict(
        description=f"Enable-to-{VOUT_MIN:g} V time at {ILOAD_MA} mA load per PVT point. A pump that "
                    "never reaches the threshold measures 1 s and fails.",
        claim=f"Output reaches {VOUT_MIN:g} V within {START_MAX_S*1e6:g} us of enable at every PVT point.",
        analyses=[f"tran 1n {us(t_stop)} 0 {TMAX}"], measure=measure, checks=checks)


BENCHES = {"device-stress": device_stress, "load": load, "load-step": load_step, "startup": startup}


def render(slug: str) -> dict[str, str]:
    stim, tb = BENCHES[slug]()
    tb = {
        "name": f"charge-pump-{slug}",
        "netlist": "netlist.spice",
        "netlist_provenance": "schematic",
        "nominal_supply_v": NOMINAL_V,
        "supply_tolerance": TOL,
        "temperatures_c": TEMPS,
        "corners": ["mos_mimcap"],
        **tb,
    }
    return {"netlist.spice": DUT + "\n" + stim, "tb.json": json.dumps(tb, indent=2) + "\n"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    bad = 0
    for slug in BENCHES:
        d = SIM / slug / "testbench"
        for name, text in render(slug).items():
            p = d / name
            if args.check:
                if not p.exists() or p.read_text() != text:
                    print(f"stale: {p.relative_to(SIM.parent)}", file=sys.stderr)
                    bad += 1
            else:
                d.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
