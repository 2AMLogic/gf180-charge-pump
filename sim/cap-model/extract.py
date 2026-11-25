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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    p = pdkmod.find_pdk(SIM)
    rows = []
    mim = "xc a 0 cap_mim_1f0_m2m3_noshield c_length={l}u c_width={w}u"
    c1 = measure(p, mim.format(l=20, w=20), 0)
    c2 = measure(p, mim.format(l=40, w=40), 0)
    # C = cox*A + capsw*P  -> solve for the two terms
    a1, p1, a2, p2 = 400, 80, 1600, 160
    cox = (c1 * p2 - c2 * p1) / (a1 * p2 - a2 * p1)
    capsw = (c1 - cox * a1) / p1
    rows.append(("MIM cap_mim_1f0_m2m3_noshield (1 fF/um2 option)", f"{cox*1e15:.4f} fF/um2 area, {capsw*1e15:.3f} fF/um perimeter", "ac 1 kHz, 20x20 and 40x40 um, solved for area+perimeter"))
    mim15 = "xc a 0 cap_mim_1f5_m2m3_noshield c_length={l}u c_width={w}u"
    d1, d2 = measure(p, mim15.format(l=20, w=20), 0), measure(p, mim15.format(l=40, w=40), 0)
    cox15 = (d1 * p2 - d2 * p1) / (a1 * p2 - a2 * p1)
    rows.append(("MIM cap_mim_1f5_m2m3_noshield (1.5 fF/um2 option)", f"{cox15*1e15:.4f} fF/um2 area", "same method"))
    for bias in (0.0, 1.0, 3.3, 5.0):
        c = measure(p, f"xc a 0 cap_nmos_06v0 c_length=10u c_width=10u", bias)
        rows.append((f"MOS cap cap_nmos_06v0, 10x10 um, terminal-1 bias {bias:g} V", f"{c/100*1e15:.4f} fF/um2", "ac 1 kHz at DC bias"))
    when = dt.datetime.now(dt.timezone.utc)
    md = [f"# Flying-capacitor model extraction -- {when:%Y-%m-%d %H:%M}Z", "",
          f"PDK: {p.variant}@{p.version}; ngspice: {subprocess.run([NGSPICE,'-v'],capture_output=True,text=True).stdout.split(chr(10))[1].strip() if True else ''}",
          "Corner: typical, 27 C (the PDK's passive models carry their own corner sections; not swept here).", "",
          "| device | extracted | method |", "|---|---|---|"]
    md += [f"| {a} | {b} | {c} |" for a, b, c in rows]
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
