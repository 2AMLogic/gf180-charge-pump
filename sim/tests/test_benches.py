import copy, json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "benches"))
from harness import corners, pdk, pump_evidence, report, testbench  # noqa: E402
from harness.simgate import requires_sim  # noqa: E402
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
            self.assertEqual(tuple(tb.corners), ("mos_mimcap",))
            self.assertTrue(tb.checks)

    def test_corner_set_is_pdk_sections(self):
        names = [c.sections[0] for c in corners.resolve_corners(["mos"])]
        self.assertEqual(names, ["typical", "ff", "ss", "fs", "sf"])

    def test_full_matrix_conformance(self):
        tb = testbench.load(SIM / "startup" / "testbench")
        pts = corners.build_grid(
            corners.resolve_corners(tb.corners), tb.temperatures_c,
            corners.supply_points(tb.nominal_supply_v, tb.supply_tolerance))
        self.assertEqual(len(pts), 135)
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


class EmptyStressRendering(unittest.TestCase):
    def test_empty_stress_states_absence(self):
        lines = pump_evidence.render_lines({"output_lines": [], "stress": []})
        self.assertEqual(lines, [pump_evidence.NO_STRESS_LINE])
        self.assertIn("not evidenced", lines[0])

    def test_nonempty_stress_has_no_none_line(self):
        stress = [{"at": "tt", "worst": "stress_a_vds_v", "worst_margin_v": 0.5, "violations": []}]
        lines = pump_evidence.render_lines({"output_lines": [], "stress": stress})
        self.assertNotIn(pump_evidence.NO_STRESS_LINE, lines)
        self.assertTrue(lines[0].startswith("- Worst device-stress margin: 0.5 V"))


class EmptyStressClaimIsTrue(unittest.TestCase):
    """The empty-stress line must hold for every record that can produce it."""

    def _scope(self, measure, checks, values, status="ok"):
        from harness.runner import PointResult
        tb = copy.deepcopy(testbench.load(SIM / "startup" / "testbench"))
        tb.measure, tb.checks = dict.fromkeys(measure, "x"), checks
        pt = corners.build_grid(corners.resolve_corners(["mos"]), [25.0], [3.3])[0]
        res = PointResult(point=pt, status=status, measurements=values)
        return report.analyze_results(tb, [pt], [res], allow_unswept_axes=True)

    def test_unrated_declared_stress_does_not_claim_none_declared(self):
        a = self._scope(["stress_a_vds_v"], {}, {"stress_a_vds_v": 1.0})
        self.assertEqual([f["kind"] for f in a["failures"]], ["stress_unrated"])
        self.assertEqual(a["scope"]["stress"], [])
        text = " ".join(pump_evidence.render_lines(a["scope"]))
        self.assertNotIn("declared", text)
        self.assertNotIn("in this bench", text)
        self.assertIn("not evidenced", text)

    def test_declared_rated_stress_with_no_ok_point_does_not_claim_none_declared(self):
        a = self._scope(["stress_a_vds_v"], {"stress_a_vds_v": {"max": 6.0}}, {}, status="error")
        self.assertEqual(a["scope"]["stress"], [])
        text = " ".join(pump_evidence.render_lines(a["scope"]))
        self.assertNotIn("declared", text)
        self.assertNotIn("no stress_*", text)


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

    @requires_sim(_can_simulate)
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

    @requires_sim(_can_simulate)
    def test_overstressed_dut_fails(self):
        """A DUT run at 2x supply must violate the real 6.0 V rating."""
        tb, res = single_point.run("device-stress", vdd=7.0)
        self.assertEqual(res.status, "ok", res.message)
        r = pump_evidence.stress_margins(res.measurements, generate.RATING_V)
        self.assertTrue(r["violations"])
        bad = report.analyze_results(tb, [res.point], [res], allow_unswept_axes=True)
        self.assertTrue(bad["failures"])


class RenderLinesSummary(unittest.TestCase):
    def _scope(self, n):
        ol = []
        for i in range(n):
            at = f"c{i}"
            for name in ("vout_at_10ma_a_v", "vout_at_10ma_b_v"):
                v = 4.0 + i * 0.1
                ol.append({"at": at, "name": name, "value": v,
                           "line": f"{name}: {v:.4g} V at 10 mA load, {at} 25 C 3.3 V"})
        return {"output_lines": ol, "stress": []}

    def test_summarized_not_enumerated(self):
        scope = self._scope(135)
        before = copy.deepcopy(scope)
        out = pump_evidence.render_lines(scope)
        self.assertEqual(scope, before)
        self.assertLessEqual(len(out), 8)
        text = "\n".join(out)
        self.assertIn("Min `vout_at_10ma_a_v`: c0", text)
        self.assertIn("Max `vout_at_10ma_a_v`: c134", text)
        self.assertIn("10 mA load", text)
        self.assertIn("135 of 135 completed points", text)
        self.assertIn("JSON record", text)

    def test_single_point_and_empty(self):
        out = pump_evidence.render_lines(self._scope(1))
        self.assertIn("Min `vout_at_10ma_a_v`: c0", "\n".join(out))
        self.assertIn("Max `vout_at_10ma_a_v`: c0", "\n".join(out))
        self.assertEqual(
            pump_evidence.render_lines({"output_lines": [], "stress": []}),
            [pump_evidence.NO_STRESS_LINE],
        )


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
        self.assertIn("mimcap_typical", x["line"])

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


class ScopeHeadingAlwaysPresent(unittest.TestCase):
    """``## Scope rule`` is emitted for every record, incl. one with no ``scope`` key (#28)."""

    HEADING = "## Scope rule (output under load, device stress)"

    def _md(self, scope):
        from tests.test_mimcap_axis import MimcapMarkdownTag
        rec = dict(MimcapMarkdownTag._record(None))
        rec.pop("scope", None)
        if scope is not None:
            rec["scope"] = scope
        return report.render_markdown(rec)

    def test_no_scope_key(self):
        md = self._md(None)
        self.assertIn(self.HEADING, md)
        self.assertIn(pump_evidence.NO_STRESS_LINE, md)

    def test_load_only_scope(self):
        md = self._md({"output_lines": [{"at": "c0", "name": "vout_at_10ma_v", "value": 4.8,
                                         "line": "vout_at_10ma_v: 4.8 V at 10 mA load, c0"}],
                       "stress": []})
        self.assertIn(self.HEADING, md)
        self.assertIn("Min `vout_at_10ma_v`", md)

    def test_stress_only_scope(self):
        md = self._md({"output_lines": [], "stress": [
            {"at": "tt", "worst": "stress_a_vds_v", "worst_margin_v": 0.5, "violations": []}]})
        self.assertIn(self.HEADING, md)
        self.assertIn("Worst device-stress margin: 0.5 V", md)


class WriteRecordFiles(unittest.TestCase):
    """write_record persists the companion JSON record the Markdown scope
    bullets point to (issue #46), append-only alongside the .md record."""

    def _record(self, record_id):
        from harness.runner import PointResult
        tb = copy.deepcopy(testbench.load(SIM / "startup" / "testbench"))
        tb.measure, tb.checks = {"vout_at_10ma_resistive_min_v": "x"}, {}
        pts = corners.build_grid(corners.resolve_corners(["mos"]), [25.0], [3.3])
        results = [
            PointResult(point=pt, status="ok",
                        measurements={"vout_at_10ma_resistive_min_v": 4.4 + 0.1 * i})
            for i, pt in enumerate(pts)
        ]
        fake_pdk = pdk.Pdk(name="gf180", path=Path("/pdk/gf180mcuD"),
                           variant="gf180mcuD", source="test", model_lib_rel="models")
        return report.build_record(
            tb, fake_pdk, pts, results, "ngspice-46", SIM.parent, record_id,
            "2026-01-01T00:00:00Z", 1.0,
            git={"commit": "testsha", "short": "testsha", "branch": "test", "dirty": False},
        )

    def test_writes_md_and_companion_json(self):
        rid = "20260101-000000-testsha"
        record = self._record(rid)
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            md = exp / "records" / f"{rid}.md"
            js = exp / "records" / f"{rid}.json"
            self.assertEqual(report.write_record(record, exp), md)
            data = json.loads(js.read_text())
            self.assertEqual(data["record_id"], rid)
            # the Markdown bullet points readers at the full per-point list;
            # the JSON record must actually carry it, unsummarized
            self.assertEqual(len(data["scope"]["output_lines"]), 5)
            self.assertIn("scope.output_lines", md.read_text())
            # private rendering keys are serialized nowhere
            self.assertNotIn("_evidence_lines", data)
            self.assertFalse([k for k in data if k.startswith("_")])
            # the in-memory dict is untouched
            self.assertIn("_evidence_lines", record)
            self.assertEqual(len(record["scope"]["output_lines"]), 5)
            # the .md file remains the finished-record marker
            self.assertTrue(report.record_exists(exp, rid))

    def test_second_write_refused_without_overwriting(self):
        rid = "20260101-000001-testsha"
        record = self._record(rid)
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            report.write_record(record, exp)
            md = exp / "records" / f"{rid}.md"
            js = exp / "records" / f"{rid}.json"
            before = (md.read_bytes(), js.read_bytes())
            with self.assertRaises(report.RecordExists):
                report.write_record(record, exp)
            self.assertEqual((md.read_bytes(), js.read_bytes()), before)

    def test_existing_md_refuses_without_orphan_json(self):
        rid = "20260101-000002-testsha"
        record = self._record(rid)
        with tempfile.TemporaryDirectory() as td:
            rec_dir = Path(td) / "records"
            rec_dir.mkdir(parents=True)
            (rec_dir / f"{rid}.md").write_text("prior record without a JSON companion\n")
            with self.assertRaises(report.RecordExists):
                report.write_record(record, rec_dir.parent)
            self.assertFalse((rec_dir / f"{rid}.json").exists())

    def test_orphan_json_blocks_ids_but_is_not_a_finished_record(self):
        rid = "20260101-000003-testsha"
        record = self._record(rid)
        with tempfile.TemporaryDirectory() as td:
            rec_dir = Path(td) / "records"
            rec_dir.mkdir(parents=True)
            (rec_dir / f"{rid}.json").write_text("{}\n")
            with self.assertRaises(report.RecordExists):
                report.write_record(record, rec_dir.parent)
            self.assertFalse((rec_dir / f"{rid}.md").exists())
            self.assertTrue(report._id_taken(rec_dir.parent, rid))
            self.assertFalse(report.record_exists(rec_dir.parent, rid))

    def test_id_taken_covers_md_json_and_spice(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            rec_dir = exp / "records"
            rec_dir.mkdir(parents=True)
            (exp / report.SNAPSHOT_DIR).mkdir()
            md_rid, js_rid, spice_rid = (
                "20260101-000004-testsha",
                "20260101-000005-testsha",
                "20260101-000006-testsha",
            )
            (rec_dir / f"{md_rid}.md").write_text("x\n")
            (rec_dir / f"{js_rid}.json").write_text("{}\n")
            (exp / report.SNAPSHOT_DIR / f"{spice_rid}.spice").write_text("*\n")
            self.assertTrue(report._id_taken(exp, md_rid))
            self.assertTrue(report._id_taken(exp, js_rid))
            self.assertTrue(report._id_taken(exp, spice_rid))
            self.assertFalse(report._id_taken(exp, "20260101-000007-testsha"))


if __name__ == "__main__":
    unittest.main()
