"""Tests for the MIM capacitor corner axis in the PVT grid (issue #7)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM))

from harness import corners, pdk, pump_evidence, report, runner, testbench
from harness.simgate import requires_sim


def _can_simulate() -> bool:
    try:
        pdk.find_pdk(SIM)
    except (pdk.PdkNotFound, pdk.PdkConfigError):
        return False
    return shutil.which("ngspice") is not None


def _fake_pdk() -> pdk.Pdk:
    return pdk.Pdk(
        name="gf180",
        path=Path("/pdk/gf180mcuD"),
        variant="gf180mcuD",
        source="test",
        model_lib_rel="libs.tech/ngspice/sm141064.ngspice",
        design_include_rel="libs.tech/ngspice/design.ngspice",
    )


class MimcapCornerGrid(unittest.TestCase):
    def test_families_includes_mimcap(self):
        self.assertEqual(corners.FAMILIES, ("mos", "mimcap"))
        valid_mim = {"mimcap_typical", "mimcap_ss", "mimcap_ff"}
        for name, corner in corners.CORNERS.items():
            self.assertEqual(
                len(corner.sections),
                len(corners.FAMILIES),
                f"corner {name!r} sections length mismatch",
            )
            self.assertIn(corner.section("mimcap"), valid_mim, name)

    def test_register_corner_length_check(self):
        with self.assertRaises(ValueError):
            corners.register_corner("_test_too_short", ("typical",))
        with self.assertRaises(ValueError):
            corners.register_corner(
                "_test_too_long", ("typical", "mimcap_typical", "extra")
            )
        self.assertNotIn("_test_too_short", corners.CORNERS)
        self.assertNotIn("_test_too_long", corners.CORNERS)

    def test_grid_is_135_points_with_unique_ids(self):
        resolved = corners.resolve_corners(None)
        self.assertEqual(len(resolved), 15)
        pairs = {(c.section("mos"), c.section("mimcap")) for c in resolved}
        expected_pairs = {
            (m, c)
            for m in ("typical", "ff", "ss", "fs", "sf")
            for c in ("mimcap_typical", "mimcap_ss", "mimcap_ff")
        }
        self.assertEqual(pairs, expected_pairs)

        pts = corners.build_grid(
            resolved,
            corners.DEFAULT_TEMPERATURES_C,
            corners.supply_points(),
        )
        self.assertEqual(len(pts), 135)
        corners.check_unique_artifact_ids(pts)
        self.assertEqual(len({p.corner_id for p in pts}), 135)

    def test_sabotage_resets_mos_and_mimcap_to_typical(self):
        sabotaged = corners.sabotage(corners.resolve_corners(None))
        self.assertEqual(len(sabotaged), 15)
        for corner in sabotaged:
            self.assertEqual(corner.sections, ("typical", "mimcap_typical"))

    def test_compose_deck_includes_mimcap_section(self):
        tb = testbench.load(SIM / "load" / "testbench")
        fake_pdk = _fake_pdk()
        for mim_sec in ("mimcap_typical", "mimcap_ss", "mimcap_ff"):
            corner = corners.CORNERS[f"ss_{mim_sec}"]
            pt = corners.PvtPoint(corner=corner, temp_c=25.0, vdd=3.3)
            deck = runner.compose_deck(tb, fake_pdk, pt)
            self.assertIn(
                '.lib "/pdk/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" ss', deck
            )
            self.assertIn(
                f'.lib "/pdk/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {mim_sec}',
                deck,
            )


class MimcapPdkSimulation(unittest.TestCase):
    @requires_sim(_can_simulate)
    def test_deck_selects_mimcap_section_and_scales_mim_corner_1p0ff(self):
        """Verify ngspice evaluates the PDK's mim_corner_1p0ff and MIM cap.

        Note the PDK's digital RC-delay polarity in sm141064.ngspice:
        - mimcap_typical -> mim_corner_1p0ff = 1.0
        - mimcap_ss      -> mim_corner_1p0ff = 1.1 (+10 % capacitance)
        - mimcap_ff      -> mim_corner_1p0ff = 0.9 (-10 % capacitance, worst-case Cfly)
        """
        p = pdk.find_pdk(SIM)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tb_dir = tmp_path / "mim-probe" / "testbench"
            tb_dir.mkdir(parents=True)
            (tb_dir / "netlist.spice").write_text(
                "* minimal MIM corner probe\n"
                "vmim p_mim 0 dc {mim_corner_1p0ff}\n"
                "xc cap_n 0 cap_mim_1f0_m2m3_noshield c_length=20u c_width=20u\n"
                "vb cap_n 0 dc 0 ac 1\n"
            )
            (tb_dir / "tb.json").write_text(
                "{\n"
                '  "name": "mim-probe",\n'
                '  "netlist": "netlist.spice",\n'
                '  "netlist_provenance": "schematic",\n'
                '  "nominal_supply_v": 3.3,\n'
                '  "supply_tolerance": 0.1,\n'
                '  "temperatures_c": [25.0],\n'
                '  "corners": ["mos_mimcap"],\n'
                '  "analyses": ["op", "ac lin 1 1k 1k"],\n'
                '  "measure": {\n'
                '    "mim_corner": "op1.v(p_mim)",\n'
                '    "cap_f": "imag(-i(vb))/(2*pi*1k)"\n'
                "  },\n"
                '  "checks": {\n'
                '    "mim_corner": {"min": 0.5, "max": 1.5}\n'
                "  }\n"
                "}\n"
            )
            tb = testbench.load(tb_dir)
            expected = {
                "mimcap_typical": 1.0,
                "mimcap_ss": 1.1,
                "mimcap_ff": 0.9,
            }
            caps: dict[str, float] = {}
            for mim_sec, want_scale in expected.items():
                pt = corners.PvtPoint(
                    corner=corners.CORNERS[f"ss_{mim_sec}"],
                    temp_c=25.0,
                    vdd=3.3,
                )
                deck = runner.compose_deck(tb, p, pt)
                self.assertIn(
                    f'.lib "{runner.absolute_path(p.model_lib)}" {mim_sec}', deck
                )

                res = runner.run_point(tb, p, pt, tmp_path / "work")
                self.assertEqual(res.status, "ok", res.message)
                self.assertAlmostEqual(
                    res.measurements["mim_corner"], want_scale, places=6
                )
                caps[mim_sec] = res.measurements["cap_f"]

            self.assertAlmostEqual(
                caps["mimcap_ss"] / caps["mimcap_typical"], 1.1, places=4
            )
            self.assertAlmostEqual(
                caps["mimcap_ff"] / caps["mimcap_typical"], 0.9, places=4
            )


class MimcapReporting(unittest.TestCase):
    def _make_record(self, corner_names: list[str], failing_corner: str | None = None):
        tb = testbench.load(SIM / "load" / "testbench")
        fake_pdk = _fake_pdk()
        pts = corners.build_grid(
            corners.resolve_corners(corner_names),
            tb.temperatures_c,
            corners.supply_points(tb.nominal_supply_v, tb.supply_tolerance),
        )
        results = []
        for idx, pt in enumerate(pts):
            # Vary vout slightly so min falls on ss_mimcap_ff and max on ff_mimcap_ss
            base_v = 5.0
            if pt.mimcap == "mimcap_ff":
                base_v -= 0.25
            elif pt.mimcap == "mimcap_ss":
                base_v += 0.25
            if (
                failing_corner
                and pt.corner.name == failing_corner
                and pt.temp_c == -40.0
                and pt.vdd == 2.97
            ):
                base_v = 4.20  # below 4.5 V min check
            meas = {
                "vout_at_10ma_resistive_mean_v": base_v + 0.05,
                "vout_at_10ma_resistive_min_v": base_v - 0.0001 * idx,
                "vout_at_10ma_resistive_max_v": base_v + 0.10,
                "ripple_at_10ma_resistive_pp_v": 0.10,
                "iload_10ma_resistive_mean_a": 0.011,
                "iload_10ma_resistive_min_a": 0.0105,
            }
            results.append(
                runner.PointResult(
                    point=pt,
                    status="ok",
                    measurements=meas,
                    seconds=0.1,
                    deck=f"{pt.corner_id}.spice",
                    log=f"{pt.corner_id}.log",
                )
            )
        rec = report.build_record(
            tb=tb,
            pdk=fake_pdk,
            points=pts,
            results=results,
            ngspice="ngspice-46",
            repo_root=SIM.parent,
            record_id="20261125-000000-testsha",
            started_utc="2026-11-25T00:00:00Z",
            wall_seconds=1.0,
            evidence_dir=tb.experiment_dir / "corners" / "20261125-000000-testsha",
        )
        return tb, pts, rec

    def test_matrix_conformance_requires_all_mimcap_corners(self):
        tb, pts_full, rec_full = self._make_record(["mos_mimcap"])
        self.assertEqual(len(pts_full), 135)
        self.assertTrue(rec_full["matrix"]["full"], rec_full["matrix"]["missing"])

        pts_mos_only = corners.build_grid(
            corners.resolve_corners(["mos"]),
            tb.temperatures_c,
            corners.supply_points(tb.nominal_supply_v, tb.supply_tolerance),
        )
        conf_mos = report.matrix_conformance(tb, pts_mos_only)
        self.assertFalse(conf_mos["full"])
        self.assertTrue(
            any("mimcap" in m for m in conf_mos["missing"]), conf_mos["missing"]
        )

        # Sparse pairing (1 MIM per MOS, not full cross product) must not pass as full.
        pts_sparse = corners.build_grid(
            corners.resolve_corners(
                ["tt_mimcap_typical", "ss_mimcap_ss", "ff_mimcap_ff"]
            ),
            tb.temperatures_c,
            corners.supply_points(tb.nominal_supply_v, tb.supply_tolerance),
        )
        conf_sparse = report.matrix_conformance(tb, pts_sparse)
        self.assertFalse(conf_sparse["full"])

    def test_record_and_markdown_tag_points_with_mimcap(self):
        _, _, rec = self._make_record(["mos_mimcap"], failing_corner="ss_mimcap_ff")
        self.assertEqual(
            rec["grid"]["mimcap_corners"],
            ["mimcap_ff", "mimcap_ss", "mimcap_typical"],
        )
        for pt in rec["points"]:
            self.assertIn("mimcap", pt)
            self.assertIn(pt["mimcap"], ("mimcap_typical", "mimcap_ss", "mimcap_ff"))

        vout_summary = rec["summary"]["vout_at_10ma_resistive_min_v"]
        self.assertEqual(vout_summary["min_mimcap"], "mimcap_ff")
        self.assertEqual(vout_summary["max_mimcap"], "mimcap_ss")

        failures = rec["checks"]["failures"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["mimcap"], "mimcap_ff")
        self.assertIn("mimcap_ff", report.describe_failure(failures[0]))

        md = report.render_markdown(rec)
        self.assertIn("MIM cap: mimcap_ff, mimcap_ss, mimcap_typical", md)
        self.assertIn("(mimcap=mimcap_ff)", md)
        self.assertIn(", mimcap_ff)", md)

    def test_pump_evidence_output_lines_names_mimcap_corner(self):
        pt_full = corners.PvtPoint(
            corner=corners.CORNERS["ss_mimcap_ff"], temp_c=-40.0, vdd=2.97
        ).as_dict()
        (line_full,) = pump_evidence.output_lines(
            pt_full, {"vout_at_10ma_resistive_min_v": 4.52}
        )
        self.assertIn("10 mA", line_full)
        self.assertIn("mimcap_ff", line_full)

        # Even on shorthand corner name 'tt', the explicit mimcap tag must appear.
        pt_short = corners.PvtPoint(
            corner=corners.CORNERS["tt"], temp_c=25.0, vdd=3.3
        ).as_dict()
        (line_short,) = pump_evidence.output_lines(
            pt_short, {"vout_at_10ma_resistive_min_v": 5.01}
        )
        self.assertIn("mimcap_typical", line_short)


if __name__ == "__main__":
    unittest.main()
