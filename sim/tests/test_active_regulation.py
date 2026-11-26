"""Validate circuit-bound regulator, shunt-port and native capacitor-coupon records."""

import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch
import unittest

HERE = Path(__file__).resolve().parents[1] / "active-regulation"


def record(name):
    return json.loads((HERE / "records" / (name + ".json")).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ActiveRegulation(unittest.TestCase):
    def test_ngspice_long_measurement_name_and_failed_windows(self):
        with patch.object(sys, "path", [str(HERE), *sys.path]):
            parse = runpy.run_path(str(HERE / "host_pulses.py"))["read_measurements"]
        required = {"before_first_pulse_v", "end_time"}
        rows = "before_first_pulse_v=  5.01614e+00\nend_time = 1.19e-4\n"
        self.assertEqual(
            parse(rows, required),
            {"before_first_pulse_v": 5.01614, "end_time": 119e-6},
        )
        with self.assertRaises(ValueError):
            parse("end_time = 1.19e-4\n", required)
        with self.assertRaises(ValueError):
            parse(rows + rows, required)

    def test_host_pulse_record_matches_signed_measurements(self):
        with patch.object(sys, "path", [str(HERE), *sys.path]):
            bench = runpy.run_path(str(HERE / "host_pulses.py"))
        data = record("host-pulses")
        self.assertEqual(data["model_sha256"], bench["MODEL_SHA"])
        self.assertEqual(data["core_sha256"], digest(bench["ORIGINAL"]))
        self.assertEqual(data["regulator_sha256"], digest(bench["REGULATORS"]))
        self.assertEqual(data["pulse_us"], [duration for _, duration in bench["PULSES"]])
        self.assertEqual(data["load_ma"], 10)
        self.assertEqual(data["edge_ns"], 1)
        self.assertEqual(data["step_ns"], 0.2)
        self.assertEqual(
            [row["point"] for row in data["records"]],
            [point.key() for point in bench["POINTS"]],
        )
        for row in data["records"]:
            with self.subTest(point=row["point"]):
                name = row["point"].replace("/", "_") + ".log.gz"
                with gzip.open(HERE / "records/host-pulses" / name, "rt") as log:
                    output = log.read()
                saved = row["measurements"]
                required = {
                    "end_time", "before_first_pulse_v",
                    "last_idle_pin_w", "last_idle_shunt_w",
                }
                for duration in data["pulse_us"]:
                    prefix = f"pulse{duration}_"
                    fields = ("vmin", "vmax", "pin_w", "pout_w", "release_v")
                    required.update(prefix + field for field in fields)
                    self.assertGreater(saved[prefix + "pin_w"], 0)
                    self.assertAlmostEqual(
                        saved[prefix + "efficiency_pct"],
                        100 * saved[prefix + "pout_w"] / saved[prefix + "pin_w"],
                    )
                self.assertEqual(
                    bench["read_measurements"](output, required),
                    {key: saved[key] for key in required},
                )
                self.assertEqual(saved["end_time"], 119e-6)

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
