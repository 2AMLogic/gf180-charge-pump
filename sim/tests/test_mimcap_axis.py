"""MIM-cap axis sensitivity and unverified-coverage tagging (issue #15)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM))

from harness import corners, report, runner, testbench


def _results(mim_scale: float, mos_scale: float = 0.05):
    """Synthetic grid: value depends on MOS corner, and on MIM only if scaled."""
    mos_gain = {"typical": 0.0, "ff": 1.0, "ss": -1.0, "fs": 0.5, "sf": -0.5}
    mim_gain = {"mimcap_typical": 0.0, "mimcap_ss": 1.0, "mimcap_ff": -1.0}
    points = corners.build_grid(corners.resolve_corners(None), (-40.0, 25.0, 125.0),
                                corners.supply_points(3.3, 0.1))
    return [
        runner.PointResult(
            point=p, status="ok",
            measurements={"vout": 5.0 * (1 + mos_scale * mos_gain[p.corner.section("mos")]
                                         + mim_scale * mim_gain[p.mimcap])},
        )
        for p in points
    ]


class MimcapAxis(unittest.TestCase):
    def test_axis_registered(self):
        self.assertIn("mimcap", testbench.AXES)

    def test_inert_mim_axis_is_flat_and_unverified(self):
        # Negative control: DUT with no MIM device (as dut_reference.spice).
        sens = report.axis_sensitivity(_results(mim_scale=0.0), ["vout"])
        mim = sens["vout"]["mimcap"]
        self.assertEqual(mim["levels"], 3)
        self.assertEqual(mim["max_pct"], 0.0)
        # The MOS corners still move the output; MIM flatness is not absorbed.
        self.assertGreater(sens["vout"]["process"]["min_pct"], 0)
        cov = report.mimcap_coverage(sens)
        self.assertEqual(cov["status"], "unverified")
        self.assertIn("mim_corner_1p0ff", cov["reason"])

    def test_live_mim_axis_is_verified(self):
        sens = report.axis_sensitivity(_results(mim_scale=0.1), ["vout"])
        self.assertGreater(sens["vout"]["mimcap"]["min_pct"], 0)
        self.assertEqual(report.mimcap_coverage(sens)["status"], "verified")

    def test_process_axis_does_not_absorb_mim_spread(self):
        # MOS inert, MIM live: process slices hold MIM fixed, so they stay flat.
        sens = report.axis_sensitivity(_results(mim_scale=0.1, mos_scale=0.0), ["vout"])
        self.assertEqual(sens["vout"]["process"]["max_pct"], 0.0)
        self.assertGreater(sens["vout"]["mimcap"]["min_pct"], 0)

    def test_unswept_mim_axis_is_unverified(self):
        pts = [r for r in _results(0.1) if r.point.mimcap == "mimcap_typical"]
        sens = report.axis_sensitivity(pts, ["vout"])
        self.assertEqual(report.mimcap_coverage(sens)["status"], "unverified")

    def test_flat_axis_fails_min_spread_check(self):
        res = _results(0.0)
        sens = report.axis_sensitivity(res, ["vout"])
        fails = report.evaluate_checks(
            {"vout": {"min_spread_pct_by_axis": {"mimcap": 0.1}}}, res, {}, sens)
        self.assertEqual([f["axis"] for f in fails], ["mimcap"])


if __name__ == "__main__":
    unittest.main()
