"""Check the public extraction report against the selected GF180D MIM option."""
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
from harness import pdk
from harness.simgate import requires_sim


def can_simulate():
    try:
        pdk.find_pdk(SIM)
    except (pdk.PdkNotFound, pdk.PdkConfigError):
        return False
    return shutil.which("ngspice") is not None


class CapModelTests(unittest.TestCase):
    @requires_sim(can_simulate)
    def test_density_and_plate_ratings(self):
        report = subprocess.check_output(
            [sys.executable, SIM / "cap-model/extract.py"], text=True
        )
        expected = {"1f0": (0.987, 20), "1f5": (1.470, 6), "2f0": (1.990, 6)}
        mim_rows = [line.split("|") for line in report.splitlines() if line.startswith("| MIM ")]
        self.assertEqual(len(mim_rows), len(expected))
        for option, (density, rating) in expected.items():
            with self.subTest(option=option):
                row, = [r for r in mim_rows if r[1].strip() == f"MIM cap_mim_{option}_m2m3_noshield"]
                self.assertAlmostEqual(float(row[2].split()[0]), density, delta=0.01)
                self.assertEqual(row[4].strip(), f"<= {rating} V between plates (PDK model header)")
