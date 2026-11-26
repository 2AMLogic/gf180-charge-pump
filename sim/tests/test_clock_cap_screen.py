"""Keep the physical-clock records tied to the circuit and its two-terminal measurements."""

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import itertools
import json
from pathlib import Path
import runpy
import unittest


SCREEN = Path(__file__).resolve().parents[1] / "clock-cap-screen"
PAIRS = ("ds", "gs", "db", "gb", "gd", "sb")


def record(suite):
    return json.loads((SCREEN / "records" / f"{suite}.json").read_text())


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
