"""Validate circuit-bound regulator, shunt-port and native capacitor-coupon records."""

import hashlib
import json
from pathlib import Path
import runpy
import unittest

HERE = Path(__file__).resolve().parents[1] / "active-regulation"


def record(name):
    return json.loads((HERE / "records" / (name + ".json")).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ActiveRegulation(unittest.TestCase):
    def test_integrated_circuit_uses_local_feedback(self):
        producer = runpy.run_path(str(HERE / "screen.py"))
        netlist = producer["integrated"]()
        self.assertNotIn("bshunt out", netlist)
        self.assertNotIn("vdriver vr 0", netlist)
        self.assertIn("xref vin ref bandgap", netlist)
        self.assertIn("xdrv vin ref drv regdriver", netlist)
        mos, caps, bipolars = producer["inventory"](
            producer["REGULATORS"].read_text() + netlist
        )
        self.assertEqual(len(bipolars), 10)
        self.assertIn("xsh.xclamp.xt", mos)
        self.assertIn("xdrv.xpass.xt", mos)
        self.assertIn("xco", caps)
        measurements = record("smoke")
        self.assertEqual(measurements["core_sha256"], digest(producer["ORIGINAL"]))
        self.assertEqual(
            measurements["regulator_sha256"], digest(producer["REGULATORS"])
        )
        self.assertEqual(measurements["model_sha256"], producer["MODEL_SHA"])
        (row,) = measurements["records"]
        for group in row["mos_v"].values():
            self.assertEqual(
                set(group),
                {"gs", "gd", "gb", "ds", "db", "sb", "db_forward", "sb_forward"},
            )
            self.assertTrue(all(instance in mos for _, instance in group.values()))
        self.assertEqual(row["measurements"]["end_time"], 24e-6)

    def test_port_probes_distinguish_fast_step_from_settled_gain(self):
        evidence = record("impedance")
        self.assertEqual(
            evidence["regulator_sha256"], digest(HERE / "regulators.spice")
        )
        self.assertEqual(len({r["point"] for r in evidence["records"]}), 11)
        for row in evidence["records"]:
            self.assertEqual(set(row["bias"]), {"5", "15", "30"})
            for bias in row["bias"].values():
                self.assertEqual(
                    {int(k) for k in bias["ac_ohm"]}, set(evidence["frequencies_hz"])
                )
            bare, bypassed = (row["step"][k] for k in ("bare_shunt", "with_reservoir"))
            self.assertGreater(
                bare["positive_step_peak_ohm"], bypassed["positive_step_peak_ohm"]
            )
            self.assertGreater(bypassed["positive_step_peak_ohm"], 4)
            self.assertLess(bare["dc_step_ohm"], 4)

    def test_native_coverage_and_coupon_identity(self):
        reports = record("coupon-drc")
        data = digest(HERE / "records/capacitors.gds")
        for group, count in (("mim_b", 12), ("all", 768)):
            r = reports[group]
            self.assertEqual(r["provenance"]["input"]["content_hash"], "sha256:" + data)
            self.assertEqual(r["checked_categories"], count)
            self.assertTrue(r["coverage_assertion_satisfied"])
            self.assertEqual(r["provenance"]["deck"]["options"]["variant"], "D")
        self.assertEqual(reports["mim_b"]["violation_count"], 0)
        self.assertEqual(
            reports["all"]["rule_counts"],
            dict.fromkeys(("DCF.1b", "M1.4", "M2.4", "M3.4", "PL.8"), 1),
        )
