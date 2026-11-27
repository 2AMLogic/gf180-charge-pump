"""Keep the physical-clock records tied to the circuit and its two-terminal measurements."""

from decimal import Decimal, ROUND_HALF_UP
from functools import partial
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import Mock, patch
import unittest


SCREEN = Path(__file__).resolve().parents[1] / "clock-cap-screen"
PAIRS = ("ds", "gs", "db", "gb", "gd", "sb")
TOOLS_NGSPICE = "/tools/ngspice"
BANNER_46 = "** ngspice-46 : Circuit level simulation program"
BANNER_47 = "** ngspice-47 : Circuit level simulation program"
NGSPICE_OUTPUT = {
    "ok": (
        "  Measurements for Transient Analysis\n"
        "\n"
        "short_name          =  1.00000e+00 at=  1.99949e-05\n"
        "a_very_long_measure_name=  2.00000e+00 at=  1.99949e-05\n"
    ),
    "step": "Error: timestep too small: 1.000000e-12 at 1.000000e-06\n",
    "fail": "Error: incomplete or empty netlist\n",
}
PF = {"xca_pf": "5.600000e+01", "xcb_pf": "5.600000e+01", "xco_pf": "1.090000e+02"}


def record(suite):
    return json.loads((SCREEN / "records" / f"{suite}.json").read_text())


def fake_ngspice(folder, banner, mode="ok"):
    folder.mkdir()
    (folder / "ngspice").write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        f"  --version) printf '%s\\n' '{banner}';;\n"
        "  -b)\n"
        f"    printf '%s\\n' \"$@\" > '{folder}/calls'\n"
        f"    cat \"$2\" >> '{folder}/calls'\n"
        f"    printf '%s' '{NGSPICE_OUTPUT[mode]}'{' >&2' if mode != 'ok' else ''}\n"
        f"    exit {int(mode == 'fail')};;\n"
        "esac\n"
    )
    (folder / "ngspice").chmod(0o755)
    return folder


def echo_spice(lines, ngspice, label, filename="bench.cir", omit=(), backwards=False, **values):
    values = {"full_t": "2.40000e-05", **PF, **values}
    output = []
    for words in (line.split() for line in lines):
        if words[:2] in ([".meas", "tran"], ["meas", "tran"]):
            names, template = words[2:3], "{:<20}= {} at=  1.99949e-05"
        elif words[:1] == ["print"]:
            names, template = words[1:], "{} = {}"
        else:
            continue
        for name in names:
            if name not in omit and values.setdefault(name, "1.00000e+00") is not None:
                output.append(template.format(name, values[name]))
    return "\n".join(output[::-1] if backwards else output)


def rounded(value):
    text = str(Decimal(repr(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
    return text.replace("-", "\u2212")


def span(low, high):
    return "0" if low == high == 0 else f"{rounded(low)}…{rounded(high)}"


class ClockCapScreenTest(unittest.TestCase):
    def test_records_match_circuit_and_cover_grid(self):
        digest = hashlib.sha256((SCREEN / "candidate.spice").read_bytes()).hexdigest()
        for suite in ("clock", "load", "controls", "gear", "capacitance"):
            self.assertEqual(record(suite)["circuit_sha256"], digest, suite)
        grid = set(
            itertools.product(
                ("typical", "ff", "ss", "fs", "sf"),
                ("mimcap_typical", "mimcap_ff", "mimcap_ss"),
                (-40, 25, 125),
                (2.97, 3.30, 3.63),
            )
        )
        for suite in ("clock", "load"):
            rows = record(suite)["records"]
            self.assertEqual(len(rows), len(grid))
            self.assertEqual({(r["mos"], r["mim"], r["temp_c"], r["vin_v"]) for r in rows}, grid)

    def test_flying_and_reservoir_terminal_stresses_are_distinct(self):
        measures = runpy.run_path(str(SCREEN / "screen.py"))["measures"](True, 2.8)
        for op in ("min", "max"):
            self.assertEqual(measures[f"fly_a_{op}"], f"{op} par('v(a)-v(clk)')")
            self.assertEqual(measures[f"fly_b_{op}"], f"{op} par('v(b)-v(clkb)')")
            self.assertEqual(measures[f"reservoir_{op}"], f"{op} v(out)")
        for suite, count in (("controls", 2), ("gear", 1)):
            open_shunt = [r["measurements"] for r in record(suite)["records"] if not r["shunt"]]
            self.assertEqual(len(open_shunt), count)
            for m in open_shunt:
                self.assertGreater(m["reservoir_max"], 6.0)
                self.assertGreater(max(m["a_ground_max"], m["b_ground_max"]), 6.0)
                self.assertLess(
                    max(abs(m[f"fly_{leg}_{op}"]) for leg in ("a", "b") for op in ("min", "max")),
                    6.0,
                )

    def test_signed_mos_terminal_grid_and_open_shunt(self):
        result = record("terminal-stress")
        self.assertEqual(result["circuit_sha256"], record("load")["circuit_sha256"])
        devices = result["device_terminals"]
        self.assertEqual(len(devices), 24)
        self.assertEqual(devices["xp1"]["pairs"]["gs"], ["b", "out"])
        self.assertEqual(devices["xn2"]["pairs"]["ds"], ["b", "vin"])
        grid = [row for row in result["records"] if row["suite"] == "grid"]
        self.assertEqual(len(grid), 135)
        self.assertEqual(len({(r["mos"], r["mim"], r["temp_c"], r["vin_v"]) for r in grid}), 135)
        for row in result["records"]:
            self.assertAlmostEqual(row["duration_s"], 24e-6, delta=1e-10)
            for device in devices.values():
                self.assertEqual(set(device["pairs"]), {"ds", "gs", "db", "gb", "gd", "sb"})
                for nodes in device["pairs"].values():
                    low, high = row["terminal_extrema_v"]["-".join(nodes)]
                    self.assertLessEqual(low, high)
                    if row["suite"] == "grid":
                        self.assertLessEqual(max(abs(low), abs(high)), device["rating_v"])
        shunt = [r for r in result["records"] if r["suite"] == "shunt"]
        self.assertEqual({(r["temp_c"], r["shunt_ohms"]) for r in shunt}, set(itertools.product((-40, 125), (1, 2, 4))))
        for r in shunt:
            self.assertEqual(r["release_peak_v"] > 5.5, r["shunt_ohms"] == 4)
        open_controls = [r for r in result["records"] if not r["shunt"]]
        self.assertEqual(len(open_controls), 3)
        for r in open_controls:
            self.assertGreater(max(r["terminal_extrema_v"][p][1] for p in ("a-0", "b-0")), 6.0)

    def test_readme_mos_stress_table_matches_grid_extrema(self):
        result = record("terminal-stress")
        devices = result["device_terminals"]
        names = {
            "Power PMOS": ("xp1", "xp2"),
            "Power NMOS": ("xn1", "xn2"),
            "Oscillator and NAND": ("xnand1", "xnand2", "xpand1", "xpand2", "xring1.xn", "xring1.xp", "xring2.xn", "xring2.xp"),
            "Clock drivers": ("xsense.xn", "xsense.xp", "xtrue.xn", "xtrue.xp", "xtrueout.xn", "xtrueout.xp", "xcomp.xn", "xcomp.xp", "xcomp2.xn", "xcomp2.xp", "xcompout.xn", "xcompout.xp"),
        }
        self.assertEqual(sorted(sum(names.values(), ())), sorted(devices))
        lines = (SCREEN / "README.md").read_text().splitlines()
        grid = [row for row in result["records"] if row["suite"] == "grid"]
        for group, members in names.items():
            ratings = {devices[name]["rating_v"] for name in members}
            self.assertEqual(len(ratings), 1)
            rows = [[field.strip() for field in line.strip("|").split("|")] for line in lines if line.startswith(f"| {group} · ")]
            self.assertEqual([row[0] for row in rows], [f"{group} · {ratings.pop():g} V"])
            self.assertEqual(len(rows[0]), 1 + len(PAIRS))
            for pair, cell in zip(PAIRS, rows[0][1:]):
                extrema = [row["terminal_extrema_v"]["-".join(devices[name]["pairs"][pair])] for row in grid for name in members]
                with self.subTest(group=group, pair=pair):
                    self.assertEqual(cell, span(min(low for low, _ in extrema), max(high for _, high in extrema)))

    def test_read_measurements_keeps_output_order_and_rejects_bad_values(self):
        read = runpy.run_path(str(SCREEN / "screen.py"))["read_measurements"]
        rows = (
            "  Measurements for Transient Analysis\n"
            "\n"
            "period20_a          =  8.531235e-09 at=  2.034500e-05\n"
            "period20_b          =  8.531236e-09 at=  2.034500e-05\n"
            "a_ground_min        = -9.91000e-01 at=  1.10000e-06\n"
            "a_very_long_measure_name= -1.00000e+00 at=  1.99949e-05\n"
            "b_ground_max        =  5.94500e+00 at=  1.50000e-05\n"
            "clk_ground_min      = -2.00000e-02 at=  1.20000e-06\n"
            "hold_min            =  4.76400e+00 at=  2.00010e-05\n"
            "unrelated           =  1.00000e+00 at=  1.99949e-05\n"
        )
        required = {
            "hold_min", "a_very_long_measure_name", "period20_a", "period20_b",
            "a_ground_min", "b_ground_max", "clk_ground_min",
        }
        self.assertEqual(
            list(read(rows, required).items()),
            [
                ("period20_a", 8.531235e-9),
                ("period20_b", 8.531236e-9),
                ("a_ground_min", -0.991),
                ("a_very_long_measure_name", -1.0),
                ("b_ground_max", 5.945),
                ("clk_ground_min", -0.02),
                ("hold_min", 4.764),
            ],
        )
        self.assertEqual(read("xca_pf = 1.624000e+02\n", {"xca_pf"}), {"xca_pf": 162.4})
        with self.assertRaises(ValueError) as failure:
            read(rows + rows, required)
        self.assertEqual(str(failure.exception), "Duplicate ngspice measurement period20_a")
        for output, needed, unusable in (
            (rows, required | {"release_peak"}, "['release_peak']"),
            (rows.replace("4.76400e+00", "1e400"), required, "['hold_min']"),
        ):
            with self.subTest(unusable=unusable):
                with self.assertRaises(ValueError) as failure:
                    read(output, needed)
                self.assertIn(f"Missing or non-finite ngspice measurements {unusable}", str(failure.exception))

    def test_run_spice_passes_the_deck_to_ngspice_and_rejects_failed_runs(self):
        producer = runpy.run_path(str(SCREEN / "screen.py"))
        lines = ["* measurement format probe", ".meas tran short_name max v(1)", ".end"]
        with tempfile.TemporaryDirectory() as temp:
            for index, mode in enumerate(("ok", "step", "fail")):
                with self.subTest(mode=mode):
                    tools = fake_ngspice(Path(temp) / str(index), BANNER_46, mode)
                    with patch.dict(os.environ, {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"}):
                        if mode == "ok":
                            output = producer["run_spice"](lines, "ngspice", "probe deck")
                            self.assertEqual(
                                producer["read_measurements"](output, {"short_name", "a_very_long_measure_name"}),
                                {"short_name": 1.0, "a_very_long_measure_name": 2.0},
                            )
                        else:
                            with self.assertRaises(ValueError) as failure:
                                producer["run_spice"](lines, "ngspice", "probe deck")
                            self.assertIn("Incomplete probe deck", str(failure.exception))
                            self.assertIn(NGSPICE_OUTPUT[mode].strip(), str(failure.exception))
                    calls = (tools / "calls").read_text().split("\n")
                    self.assertEqual(calls[0], "-b")
                    self.assertEqual(Path(calls[1]).name, "bench.cir")
                    self.assertFalse(Path(calls[1]).exists())
                    self.assertEqual(calls[2:], [*lines, ""])

    def test_preflight_rejects_bad_arguments_before_looking_up_the_pdk(self):
        producer = runpy.run_path(str(SCREEN / "screen.py"))
        preflight, parser = producer["preflight"], Mock()
        parser.error.side_effect = SystemExit
        with (
            patch("shutil.which", return_value=TOOLS_NGSPICE),
            patch("subprocess.check_output", return_value=BANNER_46) as version,
            patch.object(producer["pdk"], "find_pdk") as find_pdk,
            self.assertRaises(SystemExit),
        ):
            preflight(parser, 0)
        find_pdk.assert_not_called()
        version.assert_not_called()
        parser.error.assert_called_once_with("--jobs must be positive")
        for which, banner in ((None, BANNER_46), (TOOLS_NGSPICE, BANNER_47)):
            with self.subTest(which=which, banner=banner):
                parser.reset_mock()
                with (
                    patch("shutil.which", return_value=which),
                    patch("subprocess.check_output", return_value=banner) as version,
                    patch.object(producer["pdk"], "find_pdk") as find_pdk,
                    self.assertRaises(SystemExit),
                ):
                    preflight(parser, 1)
                find_pdk.assert_not_called()
                parser.error.assert_called_once_with("Install ngspice 46 on PATH")
                self.assertEqual(version.call_count, int(which is not None))

    def test_preflight_pins_ngspice_46_and_the_model_hashes(self):
        producer = runpy.run_path(str(SCREEN / "screen.py"))
        preflight, parser = producer["preflight"], Mock()
        parser.error.side_effect = SystemExit
        with tempfile.TemporaryDirectory() as temp:
            models = Path(temp)
            hashes = {}
            for name in producer["MODEL_SHA"]:
                (models / name).write_text(name)
                hashes[name] = hashlib.sha256((models / name).read_bytes()).hexdigest()
            install = Mock(model_lib=models / "sm141064.ngspice")
            with (
                patch.object(producer["pdk"], "find_pdk", return_value=install),
                patch("shutil.which", return_value=TOOLS_NGSPICE),
                patch("subprocess.check_output", return_value=BANNER_46),
                patch.dict(preflight.__globals__, {"MODEL_SHA": hashes}),
            ):
                self.assertEqual(preflight(Mock(), 2), (models, TOOLS_NGSPICE))
                (models / sorted(hashes)[0]).write_text("drifted")
                with self.assertRaises(SystemExit):
                    preflight(parser, 1)
                parser.error.assert_called_with("The installed GF180 models differ from open_pdks f6eeac7d")

    def test_runners_reject_bad_arguments_before_looking_up_the_pdk(self):
        pdk = runpy.run_path(str(SCREEN / "screen.py"))["pdk"]
        refusals = (
            ("screen.py", ["clock", "--jobs", "0"], BANNER_46, "--jobs must be positive"),
            ("terminal_stress.py", ["--jobs", "0"], BANNER_46, "--jobs must be positive"),
            ("screen.py", ["clock"], BANNER_47, "Install ngspice 46 on PATH"),
            ("terminal_stress.py", [], BANNER_47, "Install ngspice 46 on PATH"),
        )
        with tempfile.TemporaryDirectory() as temp:
            for index, (runner, arguments, banner, message) in enumerate(refusals):
                with self.subTest(runner=runner, arguments=arguments, banner=banner):
                    tools = fake_ngspice(Path(temp) / str(index), banner)
                    usage = io.StringIO()
                    with (
                        patch.dict(os.environ, {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"}),
                        patch.object(sys, "path", [str(SCREEN), *sys.path]),
                        patch.dict(sys.modules),
                        patch.object(pdk, "find_pdk", side_effect=AssertionError("PDK looked up")),
                        patch.object(sys, "argv", [runner, *arguments]),
                        patch.object(sys, "stderr", usage),
                        self.assertRaises(SystemExit) as stop,
                    ):
                        sys.modules.pop("screen", None)
                        main = runpy.run_path(str(SCREEN / runner))["main"]
                        main()
                    self.assertEqual(stop.exception.code, 2)
                    self.assertIn(f"{runner}: error: {message}", usage.getvalue())

    def test_runners_read_measurements_through_the_shared_helpers(self):
        producer = runpy.run_path(str(SCREEN / "screen.py"))
        simulate, capacitance = producer["simulate"], producer["capacitance"]
        case = next(iter(producer["points"]()))
        shuffled = partial(echo_spice, backwards=True)
        with patch.dict(simulate.__globals__, {"run_spice": shuffled}):
            row = simulate(case, Path("/pdk"), "/ngspice", True)
            geared = simulate(producer["GEAR_CONTROLS"][0], Path("/pdk"), "/ngspice", True, True)
        with (
            patch.dict(simulate.__globals__, {"run_spice": partial(echo_spice, period20_b=None)}),
            self.assertRaises(ValueError) as failure,
        ):
            simulate(case, Path("/pdk"), "/ngspice", True)
        self.assertIn("Incomplete measurements for", str(failure.exception))
        self.assertIn("['period20_b']", str(failure.exception))
        self.assertEqual(list(row["measurements"]), list(record("load")["records"][0]["measurements"]))
        self.assertEqual(list(geared["measurements"]), list(record("gear")["records"][0]["measurements"]))
        with patch.dict(capacitance.__globals__, {"run_spice": shuffled}):
            banks = capacitance(Path("/pdk"), "/ngspice")
        with (
            patch.dict(capacitance.__globals__, {"run_spice": partial(echo_spice, omit=("xco_pf",))}),
            self.assertRaises(ValueError) as failure,
        ):
            capacitance(Path("/pdk"), "/ngspice")
        self.assertIn("Missing AC capacitor measurements at mimcap_ff", str(failure.exception))
        self.assertEqual(
            [list(bank["capacitance_pf"]) for bank in banks],
            [list(bank["capacitance_pf"]) for bank in record("capacitance")["records"]],
        )
        with (
            patch.object(sys, "path", [str(SCREEN), *sys.path]),
            patch.dict(sys.modules),
        ):
            sys.modules.pop("screen", None)
            stress = runpy.run_path(str(SCREEN / "terminal_stress.py"))
        observe = stress["observe"]
        devices = stress["differences"](stress["terminals"]())
        job = ("grid", case, False, 1)
        expected = next(r for r in record("terminal-stress")["records"] if r["suite"] == "grid")
        with patch.object(stress["screen"], "run_spice", shuffled):
            row = observe(job, Path("/pdk"), "/ngspice", devices)
            self.assertEqual(list(row), list(expected))
            self.assertEqual(list(row["terminal_extrema_v"]), list(expected["terminal_extrema_v"]))
            for omitted in ("hold_min", "release_peak"):
                with self.subTest(omitted=omitted):
                    with (
                        patch.object(stress["screen"], "run_spice", partial(echo_spice, omit=(omitted,))),
                        self.assertRaises(ValueError) as failure,
                    ):
                        observe(job, Path("/pdk"), "/ngspice", devices)
                    self.assertIn(f"Incomplete stress transient {job}", str(failure.exception))
                    self.assertIn(f"['{omitted}']", str(failure.exception))
            for name, value, complaint in (
                ("release_peak", "1e400", f"Incomplete stress transient {job}"),
                ("full_t", "1.20000e-05", f"Truncated transient {job}"),
            ):
                with self.subTest(name=name, value=value):
                    with (
                        patch.object(stress["screen"], "run_spice", partial(echo_spice, **{name: value})),
                        self.assertRaises(ValueError) as failure,
                    ):
                        observe(job, Path("/pdk"), "/ngspice", devices)
                    self.assertIn(complaint, str(failure.exception))

    def test_coupon_native_coverage_and_provenance(self):
        digest = hashlib.sha256((SCREEN / "records/cap-coupon.gds").read_bytes()).hexdigest()
        for name, categories, findings in (
            ("mim_b", 12, {}), ("all", 768, dict.fromkeys(("DCF.1b", "PL.8", "M1.4", "M2.4", "M3.4"), 1))
        ):
            report = record("drc-" + name)
            self.assertEqual(report["provenance"]["input"]["content_hash"], "sha256:" + digest)
            self.assertEqual(report["provenance"]["deck"]["options"]["decks"], name)
            self.assertTrue(report["coverage"]["known"])
            self.assertEqual(len(report["coverage"]["checked"]), categories)
            self.assertEqual(report["rule_counts"], findings)
