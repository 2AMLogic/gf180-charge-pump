"""Run ONE PVT point of a bench locally (debug probe). The full grid is a
`klt sim` batch request, not a loop over this script."""
import argparse, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness import corners, pdk, runner, testbench

def run(slug, corner="tt", temp=25.0, vdd=3.3, tb_dir=None, *, num_threads=0):
    sim = Path(__file__).resolve().parent.parent
    tb = testbench.load(Path(tb_dir) if tb_dir else sim / slug / "testbench")
    point = corners.build_grid(corners.resolve_corners([corner]), [temp], [vdd])[0]
    with tempfile.TemporaryDirectory() as d:
        return tb, runner.run_point(tb, pdk.find_pdk(sim), point, Path(d), num_threads=num_threads)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slug")
    ap.add_argument("--corner", default="tt"); ap.add_argument("--temp", type=float, default=25.0)
    ap.add_argument("--vdd", type=float, default=3.3)
    a = ap.parse_args()
    tb, r = run(a.slug, a.corner, a.temp, a.vdd)
    print(r.status, r.message, r.missing)
    for k, x in r.measurements.items(): print(f"  {k} = {x:.6g}")
