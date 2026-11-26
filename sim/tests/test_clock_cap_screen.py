"""Keep the physical-clock records tied to the circuit and its two-terminal measurements."""

import hashlib
import itertools
import json
from pathlib import Path
import runpy
import unittest


SCREEN = Path(__file__).resolve().parents[1] / "clock-cap-screen"


def record(suite):
    return json.loads((SCREEN / "records" / f"{suite}.json").read_text())


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
