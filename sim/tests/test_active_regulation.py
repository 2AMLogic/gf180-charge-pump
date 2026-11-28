"""Validate circuit-bound regulator, shunt-port and native capacitor-coupon records."""

from functools import partial
import gzip
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import Mock, patch
import unittest

HERE = Path(__file__).resolve().parents[1] / "active-regulation"
TOOLS_NGSPICE = "/tools/ngspice"
BANNER_46 = "** ngspice-46 : Circuit level simulation program\n"
BANNER_47 = "** ngspice-47 : Circuit level simulation program\n"


def record(name):
    return json.loads((HERE / "records" / (name + ".json")).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def echo_spice(deck, folder, ngspice, omit=()):
    """Print each measurement a deck's control block requests, as ngspice does."""
    output = []
    for words in (line.split() for line in deck.split("\n.control\n")[1].splitlines()):
        if not words:
            continue
        if words[0] == "tran":
            end_time = float(words[2].rstrip("u")) * 1e-6
        elif words[0] == "meas" and words[2] not in omit:
            output.append(f"{words[2]:<20} =  1.0e+00")
        elif words[0] == "print":
            value = f"{end_time:.10e}" if words[1] == "end_time" else "1.0e+00"
            output.append(f"{words[1]} = {value}")
    return "\n".join(output)


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

    def test_shared_parser_leaves_only_missing_clock_periods_unset(self):
        producer = runpy.run_path(str(HERE / "screen.py"))
        parse = producer["read_measurements"]
        periods = {"twenty_clk", "twenty_clkb"}
        rows = (
            "end_time = 2.4000000000e-05\n"
            "before_out_min       =  4.97370e+00 at=  1.92000e-06\n"
            "twenty_clk           =  1.9999900000e-08\n"
            "twenty_clkb          =  2.0000100000e-08\n"
            "pair0_min = -3.30010e+00\n"
            "pair0_max =  3.30010e+00\n"
        )
        required = {"end_time", "before_out_min", "pair0_min"}
        self.assertEqual(
            list(parse(rows, required, periods).items()),
            [
                ("end_time", 24e-6),
                ("before_out_min", 4.9737),
                ("twenty_clk", 1.99999e-8),
                ("twenty_clkb", 2.00001e-8),
                ("pair0_min", -3.3001),
            ],
        )
        self.assertEqual(
            list(parse("end_time = 2.4000000000e-05\n", {"end_time"}, periods).items()),
            [
                ("end_time", 24e-6),
                ("twenty_clk", None),
                ("twenty_clkb", None),
            ],
        )
        with self.assertRaises(ValueError):
            parse(rows, required | {"all_out_max"}, periods)
        with self.assertRaises(ValueError):
            parse(rows + "twenty_clk           =  2.1e-08\n", required, periods)

    def test_transient_records_failed_clock_periods_as_unset(self):
        producer = runpy.run_path(str(HERE / "screen.py"))
        transient = producer["transient"]
        point = producer["Point"]("typical", "typical", "typical", "typical", 25, 3.3)
        periods = ("twenty_clk", "twenty_clkb")
        expected_keys = list(record("smoke")["records"][0]["measurements"])
        with patch.dict(
            transient.__globals__, {"run_spice": partial(echo_spice, omit=periods)}
        ):
            row = transient(point, Path("/pdk"), "/ngspice")
        self.assertEqual(row["point"], point.key())
        self.assertEqual(list(row["measurements"]), expected_keys)
        self.assertEqual(row["measurements"]["end_time"], 24e-6)
        self.assertEqual(row["measurements"]["before_out_min"], 1.0)
        self.assertEqual([row["measurements"][k] for k in periods], [None, None])
        with patch.dict(transient.__globals__, {"run_spice": echo_spice}):
            row = transient(point, Path("/pdk"), "/ngspice")
        self.assertEqual(list(row["measurements"]), expected_keys)
        self.assertEqual([row["measurements"][k] for k in periods], [1.0, 1.0])
        with patch.dict(transient.__globals__, {"run_spice": lambda *args: ""}):
            with self.assertRaises(ValueError) as failure:
                transient(point, Path("/pdk"), "/ngspice")
        self.assertIn(f"Incomplete {point.key()} transient", str(failure.exception))

    def test_shunt_port_probes_parse_through_the_shared_reader(self):
        with patch.object(sys, "path", [str(HERE), *sys.path]):
            bench = runpy.run_path(str(HERE / "impedance.py"))
        point = bench["screen"].Point(
            "typical", "typical", "typical", "typical", 25, 3.3
        )
        with patch.object(bench["screen"], "run_spice", echo_spice):
            result = bench["measure"](point, Path("/pdk"), "/ngspice")
        self.assertEqual(set(result["bias"]), {"5", "15", "30"})
        self.assertEqual(result["bias"]["15"]["vout_v"], 1.0)
        self.assertEqual(
            list(result["step"]["with_reservoir"]),
            list(record("impedance")["records"][0]["step"]["with_reservoir"]),
        )
        self.assertEqual(result["step"]["with_reservoir"]["end_time"], 1e-6)

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

    def test_transient_records_match_circuit_and_cover_points(self):
        producer = runpy.run_path(str(HERE / "screen.py"))
        pinned = {
            "controls": (
                ("point", "step_ns", "supply_ramp"),
                {
                    ("ff/ff/ff/ff/-40C/3.63V", 0.1, False),
                    ("ss/ff/ss/ss/125C/2.97V", 0.1, False),
                    ("typical/typical/typical/typical/25C/3.3V", 0.1, True),
                    ("ss/ff/ff/ff/125C/2.97V", 0.2, False),
                    ("ff/ss/ss/ss/-40C/3.63V", 0.2, False),
                },
            ),
            "isolation": (
                ("point", "variant"),
                {
                    ("ff/ff/ff/ff/-40C/3.63V", "open_shunt"),
                    ("ss/ss/ss/ss/125C/2.97V", "prescribed_driver"),
                    ("ff/ff/ff/ff/-40C/3.63V", "one_ns_load"),
                    ("ss/ss/ss/ss/125C/2.97V", "one_ns_load"),
                },
            ),
        }
        for suite in ("pvt", "controls", "isolation"):
            with self.subTest(suite=suite):
                data = record(suite)
                self.assertEqual(data["core_sha256"], digest(producer["ORIGINAL"]))
                self.assertEqual(
                    data["regulator_sha256"], digest(producer["REGULATORS"])
                )
                self.assertEqual(data["model_sha256"], producer["MODEL_SHA"])
                for row in data["records"]:
                    with self.subTest(suite=suite, point=row["point"]):
                        self.assertEqual(row["measurements"]["end_time"], 24e-6)
                if suite == "pvt":
                    self.assertEqual(
                        [row["point"] for row in data["records"]],
                        [point.key() for point in producer["points"]()],
                    )
                else:
                    fields, expected = pinned[suite]
                    self.assertEqual(len(data["records"]), len(expected))
                    self.assertEqual(
                        {
                            tuple(row[field] for field in fields)
                            for row in data["records"]
                        },
                        expected,
                    )

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

    def test_preflight_rejects_bad_arguments_before_looking_up_the_pdk(self):
        producer = runpy.run_path(str(HERE / "screen.py"))
        parser = Mock()
        parser.error.side_effect = SystemExit
        with (
            patch("shutil.which", return_value=TOOLS_NGSPICE),
            patch("subprocess.check_output", return_value=BANNER_46),
            patch.object(producer["pdk"], "find_pdk") as find_pdk,
            self.assertRaises(SystemExit),
        ):
            producer["preflight"](parser, 0)
        find_pdk.assert_not_called()
        parser.error.assert_called_once_with(
            "Use ngspice 46 and a positive worker count"
        )

    def test_preflight_pins_ngspice_46_and_the_model_hashes(self):
        producer = runpy.run_path(str(HERE / "screen.py"))
        preflight = producer["preflight"]
        parser = Mock()
        parser.error.side_effect = SystemExit
        with tempfile.TemporaryDirectory() as temp:
            models = Path(temp)
            hashes = {}
            for name in producer["MODEL_SHA"]:
                (models / name).write_text(name)
                hashes[name] = digest(models / name)
            install = Mock(model_lib=models / "sm141064.ngspice")
            with (
                patch.object(producer["pdk"], "find_pdk", return_value=install),
                patch("shutil.which", return_value=TOOLS_NGSPICE),
                patch.dict(preflight.__globals__, {"MODEL_SHA": hashes}),
            ):
                with patch("subprocess.check_output", return_value=BANNER_46):
                    self.assertEqual(preflight(Mock(), 2), (models, TOOLS_NGSPICE))
                for which, banner in ((None, BANNER_46), (TOOLS_NGSPICE, BANNER_47)):
                    with self.subTest(which=which, banner=banner):
                        with (
                            patch("shutil.which", return_value=which),
                            patch("subprocess.check_output", return_value=banner),
                            self.assertRaises(SystemExit),
                        ):
                            preflight(parser, 1)
                        parser.error.assert_called_with(
                            "Use ngspice 46 and a positive worker count"
                        )
                (models / sorted(hashes)[0]).write_text("drifted")
                with (
                    patch("subprocess.check_output", return_value=BANNER_46),
                    self.assertRaises(SystemExit),
                ):
                    preflight(parser, 1)
                parser.error.assert_called_with(
                    "GF180D model hashes differ from the pinned parent"
                )

    def test_runners_reject_bad_arguments_before_looking_up_the_pdk(self):
        pdk = runpy.run_path(str(HERE / "screen.py"))["pdk"]
        for runner, arguments in (
            ("screen.py", ["smoke", "--jobs", "0"]),
            ("host_pulses.py", ["--jobs", "0"]),
            ("impedance.py", ["--jobs", "0"]),
        ):
            with self.subTest(runner=runner):
                with patch.object(sys, "path", [str(HERE), *sys.path]):
                    main = runpy.run_path(str(HERE / runner))["main"]
                usage = io.StringIO()
                with (
                    patch("shutil.which", return_value=TOOLS_NGSPICE),
                    patch("subprocess.check_output", return_value=BANNER_46),
                    patch.object(
                        pdk, "find_pdk", side_effect=AssertionError("PDK looked up")
                    ),
                    patch.object(sys, "argv", [runner, *arguments]),
                    patch.object(sys, "stderr", usage),
                    self.assertRaises(SystemExit),
                ):
                    main()
                self.assertIn(
                    "Use ngspice 46 and a positive worker count", usage.getvalue()
                )
