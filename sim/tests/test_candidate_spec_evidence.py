"""Check the specification's published device stresses and physical area against the retained records."""

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "sim/active-regulation/records"


def rows(name):
    return json.loads((ART / (name + ".json")).read_bytes())["records"]


class CandidateSpecTest(unittest.TestCase):
    def test_stress_table_and_outlying_controls(self):
        spec = (ROOT / "spec/0001-target-spec.md").read_text()
        grid = rows("pvt")
        self.assertEqual(len({r["point"] for r in grid}), 65)
        for key, label in (("03v3", "3.3 V"), ("06v0", "6 V")):
            fields = ("gs", "gd", "gb", "ds", "db", "sb", "db_forward", "sb_forward")
            numbers = [max(r["mos_v"][key][field][0] for r in grid) for field in fields]
            self.assertIn(
                "| " + " | ".join([label, *(f"{v:.5f}" for v in numbers)]) + " |", spec
            )
        intact = (
            grid
            + rows("controls")
            + [r for r in rows("isolation") if r["variant"] == "one_ns_load"]
        )
        self.assertEqual(len(intact), 72)
        self.assertIn(
            f"{min(r['measurements']['load_out_min'] for r in intact):.5f} V", spec
        )
        self.assertIn(f"{max(r['max_pnp_eb_v'][0] for r in intact):.5f} V", spec)
        (open_shunt,) = [r for r in rows("isolation") if r["variant"] == "open_shunt"]
        for value in [open_shunt["max_mim_v"][0], open_shunt["mos_v"]["06v0"]["gb"][0]]:
            self.assertIn(f"{value:.5f} V", spec)
        thin_above = sum(
            any(v[0] > 3.3 for v in r["mos_v"]["03v3"].values()) for r in grid
        )
        self.assertEqual(thin_above, 50)

    def test_capacitor_area_measured_on_the_delivered_coupon(self):
        coupon = ART / "capacitors.gds"
        report = json.loads((ART / "coupon-economy.json").read_bytes())
        self.assertEqual(
            report["provenance"]["input"]["content_hash"],
            "sha256:" + hashlib.sha256(coupon.read_bytes()).hexdigest(),
        )
        self.assertAlmostEqual(report["bbox_area_um2"] / 1e6, 0.442420, places=6)
