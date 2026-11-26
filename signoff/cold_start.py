"""Exercise the shipped benches on their pinned PDK at one point each."""
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "sim"
sys.path.insert(0, str(SIM / "benches"))
from single_point import run
from harness.pdk import find_pdk


def main():
    inventory = json.loads((ROOT / "signoff/item9.json").read_text())
    pin = inventory["pins"]["pdk"]
    pdk = find_pdk(SIM)
    if (pdk.variant, pdk.version) != (pin["name"], "open_pdks " + pin["revision"]):
        sys.exit(f"Expected {pin}, found {pdk.variant} at {pdk.version}")

    subprocess.run([sys.executable, SIM / "benches/generate.py", "--check"], check=True)
    files = sorted(SIM.glob("*/testbench/tb.json"))
    expected = {str(f.relative_to(ROOT)) for f in files}
    inventoried = {f for f in inventory["testbenches"] if f.endswith("/tb.json")}
    if not expected or inventoried != expected:
        sys.exit(f"Bench inventory differs from shipped tb.json files: {inventoried ^ expected}")
    for path in files:
        slug = path.parent.parent.name
        bench, point = run(slug)
        if point.status != "ok" or set(point.measurements) != set(bench.measure):
            sys.exit(f"{slug}: {point.status}, {point.message}, missing {point.missing}")
        if not all(math.isfinite(v) for v in point.measurements.values()):
            sys.exit(f"{slug}: non-finite measurement")
        print(f"{slug}: {len(point.measurements)} measurements")
    subprocess.run([sys.executable, SIM / "cap-model/extract.py"], check=True)


if __name__ == "__main__":
    main()
