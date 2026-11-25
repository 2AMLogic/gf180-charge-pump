import copy, json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "benches"))
from harness import corners, pdk, pump_evidence, report, testbench  # noqa: E402
import generate  # noqa: E402
import single_point  # noqa: E402

SLUGS = list(generate.BENCHES)


def _can_simulate():
    try:
        pdk.find_pdk(SIM)
    except Exception:
        return False
    return shutil.which("ngspice") is not None


class Manifests(unittest.TestCase):
    def test_discovered_and_valid(self):
        for slug in SLUGS:
            tb = testbench.load(SIM / slug / "testbench")
            self.assertEqual(tb.nominal_supply_v, 3.3)
            self.assertEqual(tb.supply_tolerance, 0.10)
            self.assertEqual(tuple(tb.temperatures_c), (-40.0, 25.0, 125.0))
            self.assertEqual(tuple(tb.corners), ("mos",))
            self.assertTrue(tb.checks)

    def test_corner_set_is_pdk_sections(self):
        names = [c.sections[0] for c in corners.resolve_corners(["mos"])]
        self.assertEqual(names, ["typical", "ff", "ss", "fs", "sf"])

    def test_full_matrix_conformance(self):
        tb = testbench.load(SIM / "startup" / "testbench")
        pts = corners.build_grid(
            corners.resolve_corners(["mos"]), tb.temperatures_c,
            corners.supply_points(tb.nominal_supply_v, tb.supply_tolerance))
        self.assertEqual(len(pts), 45)
        self.assertTrue(report.matrix_conformance(tb, pts)["full"])

    def test_committed_files_match_generator(self):
        self.assertEqual(generate.main(["--check"]), 0)

    def test_no_forbidden_device_and_every_bench_loaded(self):
        for slug in SLUGS:
            text = (SIM / slug / "testbench" / "netlist.spice").read_text()
            self.assertNotIn("nfet_10v0_asym", text)
            self.assertRegex(text, r"(?m)^(rload|bstep) ")  # a load is always present

    def test_vout_measurements_state_load(self):
        for slug in SLUGS:
            tb = testbench.load(SIM / slug / "testbench")
            for name in tb.measure:
                if name.startswith("vout_"):
                    pump_evidence.load_ma(name)

    def test_unloaded_vout_refused(self):
        with self.assertRaises(pump_evidence.UnloadedOutputError):
            pump_evidence.load_ma("vout_noload_v")

    def test_output_line_has_load_and_corner(self):
        pt = {"process": "ss", "temp_c": -40.0, "vdd": 2.97}
        (line,) = pump_evidence.output_lines(pt, {"vout_at_10ma_resistive_min_v": 4.61})
        self.assertIn("10 mA", line)
        self.assertIn("ss -40 C 2.97 V", line)


class StressNegativeControl(unittest.TestCase):
    def test_margin_arithmetic(self):
        r = pump_evidence.stress_margins({"stress_a_vds_v": 6.0, "stress_b_vgs_v": 7.0}, 6.5)
        self.assertEqual(r["violations"], ["stress_b_vgs_v"])
        self.assertEqual(r["worst"], "stress_b_vgs_v")

    def test_stress_checks_cover_every_device_metric(self):
        want = {f"stress_{d[0]}_{m}_v" for d in generate.DEVICES for m in generate.METRICS}
        for slug in ("device-stress", "load-step", "startup"):
            tb = testbench.load(SIM / slug / "testbench")
            self.assertLessEqual(want, set(tb.checks), slug)
            self.assertLessEqual(want, set(tb.measure), slug)
            for k in want:
                self.assertEqual(tb.checks[k]["max"], generate.RATING_V)

    def test_devices_match_dut_netlist(self):
        import re
        dut = (SIM / "benches" / "dut_reference.spice").read_text()
        inst = set(re.findall(r"(?m)^(x\S+)\s.*\b(?:nfet|pfet)_06v0\b", dut))
        self.assertEqual(inst, {d[0] for d in generate.DEVICES})

    def test_time_base_follows_start_limit(self):
        self.assertGreaterEqual(generate.T_SETTLE_S, 2 * generate.START_MAX_S)
        for slug in ("device-stress", "load"):
            tb = testbench.load(SIM / slug / "testbench")
            tstop = float(tb.analyses[0].split()[2].rstrip("u")) * 1e-6
            self.assertGreater(tstop, generate.T_SETTLE_S)
        text = (SIM / "load-step" / "testbench" / "netlist.spice").read_text()
        self.assertIn(f".param tstep={generate.us(generate.T_SETTLE_S)}", text)

    @unittest.skipUnless(_can_simulate(), "needs ngspice and the gf180mcu PDK")
    def test_lowered_limit_fails_and_real_limit_passes(self):
        tb, res = single_point.run("device-stress")
        self.assertEqual(res.status, "ok", res.message)
        pt = [res.point]
        ok = report.analyze_results(tb, pt, [res], allow_unswept_axes=True)
        self.assertEqual(ok["failures"], [])  # reference DUT is inside 6.0 V at tt/25C/3.3 V
        low = copy.deepcopy(tb)
        for c in low.checks.values():
            c["max"] = 0.1  # negative control: limit far below any real stress
        bad = report.analyze_results(low, pt, [res], allow_unswept_axes=True)
        self.assertEqual(len(bad["failures"]), sum(x > 0.1 for x in res.measurements.values()))
        self.assertGreater(len(bad["failures"]), 0)

    @unittest.skipUnless(_can_simulate(), "needs ngspice and the gf180mcu PDK")
    def test_overstressed_dut_fails(self):
        """A DUT run at 2x supply must violate the real 6.0 V rating."""
        tb, res = single_point.run("device-stress", vdd=7.0)
        self.assertEqual(res.status, "ok", res.message)
        r = pump_evidence.stress_margins(res.measurements, generate.RATING_V)
        self.assertTrue(r["violations"])
        bad = report.analyze_results(tb, [res.point], [res], allow_unswept_axes=True)
        self.assertTrue(bad["failures"])


class ScopeRuleInRecords(unittest.TestCase):
    """The scope rule is enforced in the report path, not only on hand-built inputs."""

    def _run(self, measure, checks, values):
        from harness.runner import PointResult
        tb = copy.deepcopy(testbench.load(SIM / "startup" / "testbench"))
        tb.measure, tb.checks = dict.fromkeys(measure, "x"), checks
        pt = corners.build_grid(corners.resolve_corners(["mos"]), [25.0], [3.3])[0]
        res = PointResult(point=pt, status="ok", measurements=values)
        return report.analyze_results(tb, [pt], [res], allow_unswept_axes=True)

    def test_vout_line_states_load_and_corner(self):
        a = self._run(["vout_at_10ma_v"], {}, {"vout_at_10ma_v": 4.8})
        (x,) = a["scope"]["output_lines"]
        self.assertIn("10 mA load", x["line"])
        self.assertIn("25 C 3.3 V", x["line"])

    def test_unloaded_vout_fails_record(self):
        a = self._run(["vout_noload_v"], {}, {"vout_noload_v": 6.0})
        self.assertEqual([f["kind"] for f in a["failures"]], ["unloaded_vout"])
        self.assertEqual(a["scope"]["output_lines"], [])

    def test_negative_stress_margin_fails_record(self):
        chk = {"stress_a_vds_v": {"max": 6.0}}
        a = self._run(["stress_a_vds_v"], chk, {"stress_a_vds_v": 6.5})
        self.assertEqual([f["kind"] for f in a["failures"]], ["max"])  # not double-counted
        self.assertEqual(a["scope"]["stress"][0]["violations"], ["stress_a_vds_v"])
        # No bench max check: the scope rule still refuses a verdict.
        b = self._run(["stress_a_vds_v"], {}, {"stress_a_vds_v": 1.0})
        self.assertEqual([f["kind"] for f in b["failures"]], ["stress_unrated"])

    def test_inside_rating_passes_with_margin_reported(self):
        chk = {"stress_a_vds_v": {"max": 6.0}}
        a = self._run(["stress_a_vds_v"], chk, {"stress_a_vds_v": 5.0})
        self.assertEqual(a["failures"], [])
        self.assertAlmostEqual(a["scope"]["stress"][0]["worst_margin_v"], 1.0)


if __name__ == "__main__":
    unittest.main()
