"""Extract flying-capacitor model figures from the PDK models with ngspice.

Method: for each candidate device, an AC small-signal run at 1 kHz with a
1 V-amplitude source gives C = Im(i)/(2 pi f v) at DC bias points; MIM is
characterised by area (two sizes, so area and perimeter terms separate),
MOS cap (cap_nmos_06v0) at several biases. Bottom-plate parasitic is reported
as what the PDK model contains (the MIM subckt has no substrate terminal).

Prints Markdown to stdout; ``--write`` saves it as a NEW append-only record
``sim/cap-model/records/<UTC>-<pdkver>.md`` and refuses to overwrite.
"""
import argparse, datetime as dt, math, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness import pdk as pdkmod

SIM = Path(__file__).resolve().parent.parent
NGSPICE = "ngspice"
# Differential MIM ratings in the pinned sm141064.ngspice device list.
MIM_RATING_V = {"1f0": 20.0, "1f5": 6.0, "2f0": 6.0}


def deck(p, device_lines, bias):
    return f"""* cap extraction
.include "{p.design_include}"
.lib "{p.model_lib}" typical
.lib "{p.model_lib}" mimcap_typical
.lib "{p.model_lib}" moscap_typical
{device_lines}
vb a 0 dc {bias} ac 1
.control
set numdgt=8
ac lin 1 1k 1k
let m_cap = imag(-i(vb))/(2*pi*1k)
print m_cap
.endc
.end
"""


def measure(p, dev, bias):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "d.spice"
        f.write_text(deck(p, dev, bias))
        out = subprocess.run([NGSPICE, "-b", str(f)], capture_output=True, text=True, timeout=120, cwd=d)
    for line in out.stdout.splitlines():
        if line.strip().startswith("m_cap"):
            return abs(float(line.split("=")[1]))
    raise RuntimeError(out.stdout[-800:] + out.stderr[-400:])


def ngspice_version():
    out = subprocess.run([NGSPICE, "-v"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "ngspice-" in line:
            return line.strip().lstrip("* ").split(":")[0].strip()
    return "unknown"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    p = pdkmod.find_pdk(SIM)
    rows = []
    # C = cox*A + capsw*P for these two square plates (µm and µm²).
    a1, p1, a2, p2 = 400, 80, 1600, 160
    for option, rating in MIM_RATING_V.items():
        cell = f"cap_mim_{option}_m2m3_noshield"
        c1 = measure(p, f"xc a 0 {cell} c_length=20u c_width=20u", 0)
        c2 = measure(p, f"xc a 0 {cell} c_length=40u c_width=40u", 0)
        cox = (c1 * p2 - c2 * p1) / (a1 * p2 - a2 * p1)
        capsw = (c1 - cox * a1) / p1
        rows.append((f"MIM {cell}", f"{cox*1e15:.4f} fF/um2 area, "
                     f"{capsw*1e15:.3f} fF/um perimeter",
                     "AC 1 kHz at 0 V, 20x20 and 40x40 um",
                     f"<= {rating:g} V between plates (PDK model header)"))
    for bias in (0.0, 1.0, 3.3, 5.0):
        c = measure(p, f"xc a 0 cap_nmos_06v0 c_length=10u c_width=10u", bias)
        rows.append((f"MOS cap cap_nmos_06v0, 10x10 um, terminal-1 bias {bias:g} V", f"{c/100*1e15:.4f} fF/um2", "ac 1 kHz at DC bias", "6 V device (name-plate; no separate cap rating in the PDK)"))
    when = dt.datetime.now(dt.timezone.utc)
    md = [f"# Flying-capacitor model extraction -- {when:%Y-%m-%d %H:%M}Z", "",
          f"PDK: {p.variant}@{p.version}; ngspice: {ngspice_version()}",
          "Corner: typical model sections at ngspice's default 27 C (a model-parameter extraction; the PDK's passive models carry their own corner sections, not swept here, and this is independent of the block's -40/25/125 C PVT grid).", "",
          "Supersedes the voltage interpretation in [the November 25 record](20261125-020745.md). "
          "The pinned GF180MCU-D node configuration selects MIM_2P0. The other capacitor models "
          "are included for comparison.", "",
          "The ratings below apply to the voltage difference between plates. In the idealized boost phase, "
          "a 7.26 V top plate and a 3.63 V bottom plate give 3.63 V across the flying capacitor. "
          "A reservoir connected from 5.5 V VOUT to ground has 5.5 V across it. These are "
          "illustrative terminal pairs; the AC extraction does not measure switching stress. "
          "Check the two terminal waveforms during startup, switching and load release.", "",
          "| device | extracted | method | differential voltage rating |", "|---|---|---|---|"]
    md += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    md += ["", "Bottom-plate parasitic: **not present in the PDK MIM or MOS-cap models** (two-terminal subcircuits, no substrate node), "
           "so no bottom-plate ratio can be extracted from simulation. The DUT's `cp_ratio` is therefore a placeholder until a "
           "layout-extracted figure exists (out of scope for issue #2).", ""]
    text = "\n".join(md)
    if not a.write:
        print(text); return 0
    rec = SIM / "cap-model" / "records"; rec.mkdir(parents=True, exist_ok=True)
    path = rec / f"{when:%Y%m%d-%H%M%S}.md"
    with open(path, "x") as f:
        f.write(text)
    print(path); return 0


if __name__ == "__main__":
    raise SystemExit(main())
