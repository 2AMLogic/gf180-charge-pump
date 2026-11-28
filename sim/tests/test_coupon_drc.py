"""Drive the shared native GF180D coupon DRC runner and its two callers with a stand-in klt."""

import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SIM = Path(__file__).resolve().parents[1]
SCREEN = SIM / "clock-cap-screen"
ACTIVE = SIM / "active-regulation"
DENSITY = {"DCF.1b", "PL.8", "M1.4", "M2.4", "M3.4"}
DECK = "gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc"
PINS = {"klt_version": "0.9.2", "klayout_version": "0.30.14"}
BARE_KLT = ("klt", "drc")
ACTIVE_KLT = (*BARE_KLT, "--deck", "gf180mcu")
CLOCK_KLT = ("uvx", "--from", "klayout-tools==0.9.2", "klt", "drc")
SUMMARY = "mim_b: 12 categories, 0 markers\nall: 768 categories, 5 markers\n"
GROUPS = ("mim_b", "all")


def report(group):
    """A native klt 0.9.2 report, as committed with the clock-cap-screen coupon."""
    return json.loads((SCREEN / "records" / f"drc-{group}.json").read_text())


def listing(group):
    """The empty-layout `--list-rule-categories` output: no geometry-dependent density rule."""
    return "\n".join(sorted(set(report(group)["coverage"]["checked"]) - DENSITY)) + "\n"


def flags(group, prefix=ACTIVE_KLT, pdk="/pdk"):
    """The klt flags both experiments send, after their own command prefix."""
    return [
        *prefix,
        "--engine",
        "klayout",
        "--pdk",
        "gf180mcuD",
        "--pdk-root",
        str(pdk),
        "--deck-var",
        "variant=D",
        "--deck-var",
        f"decks={group}",
        "--deck-var",
        "threads=1",
    ]


class StandIn:
    """Answer the two `klt drc` calls `run_group` makes and record each one."""

    def __init__(self, listings, runs):
        self.listings = listings  # group -> text printed by --list-rule-categories
        self.runs = runs  # group -> (exit status, stdout, stderr)
        self.calls = []

    @staticmethod
    def group(argv):
        return next(word.partition("=")[2] for word in argv if word.startswith("decks="))

    def check_output(self, argv, cwd=None, text=False):
        self.calls.append(SimpleNamespace(cwd=cwd, argv=argv, expected=None, path=None))
        return self.listings[self.group(argv)]

    def run(self, argv, cwd=None, text=False, capture_output=False):
        path = Path(argv[argv.index("--expect-rule-categories-file") + 1])
        self.calls.append(SimpleNamespace(cwd=cwd, argv=argv, expected=path.read_text(), path=path))
        code, out, err = self.runs[self.group(argv)]
        return subprocess.CompletedProcess(argv, code, out, err)


def masked(call):
    """The deck argv with its throwaway expected-categories path masked."""
    argv = call.argv
    at = argv.index("--expect-rule-categories-file") + 1
    return [*argv[:at], "<categories>", *argv[at + 1 :]]


def coupon_drc():
    return runpy.run_path(str(SCREEN / "coupon_drc.py"))


@contextlib.contextmanager
def check_coupon():
    """Load check_coupon.py the way its CLI does, with its own `screen` module first on the path."""
    with patch.dict(sys.modules), patch.object(sys, "path", [str(ACTIVE), *sys.path]):
        sys.modules.pop("screen", None)
        yield runpy.run_path(str(ACTIVE / "check_coupon.py"))


def native_reports():
    """A stand-in klt serving the committed native reports, and the committed summary."""
    committed = json.loads((ACTIVE / "records" / "coupon-drc.json").read_text())
    klt = StandIn(
        {g: listing(g) for g in GROUPS},
        {g: (3 * (g == "all"), json.dumps(report(g)), "") for g in GROUPS},
    )
    return committed, klt


class RunGroup(unittest.TestCase):
    def run_group(self, klt, group, **options):
        runner = coupon_drc()["run_group"]
        with patch.dict(runner.__globals__, {"subprocess": klt}):
            return runner(
                "coupon.gds", "TOP", "/pdk", group, klt_prefix=BARE_KLT, cwd="/repo", **options
            )

    def test_both_decks_run_against_the_exact_rule_inventory(self):
        for group, code in (("mim_b", 0), ("all", 3)):
            with self.subTest(group=group):
                saved = report(group)
                rules = set(saved["coverage"]["checked"])
                klt = StandIn({group: listing(group)}, {group: (code, json.dumps(saved), "")})
                found, names = self.run_group(klt, group, extra_args=("--max-violations", "5"))
                self.assertEqual((found, names), (saved, rules))
                listing_call, deck_call = klt.calls
                self.assertEqual(
                    (listing_call.cwd, listing_call.argv, listing_call.expected),
                    ("/repo", [*flags(group, BARE_KLT), "--list-rule-categories"], None),
                )
                self.assertEqual(
                    (deck_call.cwd, masked(deck_call), deck_call.expected),
                    (
                        "/repo",
                        [
                            *flags(group, BARE_KLT),
                            "coupon.gds",
                            "--top",
                            "TOP",
                            "--expect-rule-categories-file",
                            "<categories>",
                            "--max-violations",
                            "5",
                            "--format",
                            "json",
                        ],
                        "\n".join(sorted(rules)) + "\n",
                    ),
                )
                self.assertFalse(deck_call.path.exists())

    def test_an_unexpected_exit_status_surfaces_stdout_and_stderr_unparsed(self):
        for group, code, out, err in (
            ("mim_b", 3, "", "klt: error: the deck reported violations\n"),
            ("all", 0, "Traceback (most recent call last)\n", ""),
            ("mim_b", 1, '{"schema_version": 3, "error": {"code": "klayout_failed"}}', "klayout: exit 1\n"),
            ("all", 4, "", ""),
        ):
            with self.subTest(group=group, code=code):
                klt = StandIn({group: listing(group)}, {group: (code, out, err)})
                with self.assertRaises(RuntimeError) as failure:
                    self.run_group(klt, group)
                message = str(failure.exception)
                self.assertIn(f"{group} DRC exit status {code}", message)
                self.assertIn(out, message)
                self.assertIn(err, message)

    def test_a_drifted_rule_inventory_stops_before_the_deck_runs(self):
        for group, names, count in (
            ("mim_b", listing("mim_b").splitlines()[1:], 11),
            ("all", [*listing("all").splitlines(), "MIMTM.1x"], 769),
        ):
            with self.subTest(group=group):
                klt = StandIn({group: "\n".join(names) + "\n"}, {group: (0, "{}", "")})
                with self.assertRaises(ValueError) as failure:
                    self.run_group(klt, group)
                self.assertIn(f"rule inventory for {group}: {count}", str(failure.exception))
                self.assertEqual(len(klt.calls), 1)

    def test_a_report_that_disagrees_with_the_deck_or_inventory_is_rejected(self):
        for field, change in (
            ("coverage_assertion", lambda r: r["coverage_assertion"].update(satisfied=False)),
            ("rule_counts", lambda r: r["rule_counts"].update({"PL.8": 2})),
            ("coverage.checked", lambda r: r["coverage"]["checked"].remove("PL.8")),
        ):
            with self.subTest(field=field):
                drifted = report("all")
                change(drifted)
                klt = StandIn({"all": listing("all")}, {"all": (3, json.dumps(drifted), "")})
                with self.assertRaises(ValueError) as failure:
                    self.run_group(klt, "all")
                self.assertIn(field, str(failure.exception))

    def test_requested_version_pins_are_checked_against_provenance(self):
        drifted = report("mim_b")
        drifted["provenance"]["klayout_version"] = "0.30.12"
        for version, pins, rejected in (
            (report("mim_b"), PINS, None),
            (drifted, PINS, "provenance.klayout_version"),
            (drifted, None, None),
            (report("mim_b"), {"klt_version": "0.9.3"}, "provenance.klt_version"),
        ):
            with self.subTest(pins=pins, rejected=rejected):
                klt = StandIn({"mim_b": listing("mim_b")}, {"mim_b": (0, json.dumps(version), "")})
                if rejected is None:
                    self.assertEqual(
                        self.run_group(klt, "mim_b", check_versions=pins),
                        (version, set(version["coverage"]["checked"])),
                    )
                    continue
                with self.assertRaises(ValueError) as failure:
                    self.run_group(klt, "mim_b", check_versions=pins)
                self.assertIn(rejected, str(failure.exception))


class CheckCoupon(unittest.TestCase):
    PDK = SimpleNamespace(path=Path("/pdk/gf180mcuD"))

    def test_check_projects_the_native_reports_into_the_committed_summary(self):
        committed, klt = native_reports()
        with check_coupon() as runner, patch.dict(vars(runner["coupon_drc"]), {"subprocess": klt}):
            screen = runner["screen"]
            self.assertIs(sys.modules["screen"], screen)
            self.assertEqual(sys.path[:2], [str(screen.HERE.parent), str(screen.HERE)])
            self.assertEqual(sys.path[-1], str(screen.ORIGINAL.parent))
            self.assertEqual(runner["coupon_drc"].__file__, str(SCREEN / "coupon_drc.py"))
            for group, row in committed.items():
                with self.subTest(group=group):
                    found = runner["check"]("/tmp/active-reg-coupon.gds", self.PDK, group)
                    self.assertEqual(
                        {k: v for k, v in found.items() if k != "provenance"},
                        {k: v for k, v in row.items() if k != "provenance"},
                    )
                    self.assertEqual(
                        {k: v for k, v in found["provenance"].items() if k != "input"},
                        {k: v for k, v in row["provenance"].items() if k != "input"},
                    )
                    self.assertEqual(found["provenance"]["input"], report(group)["provenance"]["input"])
                listing_call, deck_call = klt.calls[-2:]
                self.assertEqual(listing_call.argv, [*flags(group), "--list-rule-categories"])
                self.assertIsNone(listing_call.cwd)
                self.assertEqual(
                    masked(deck_call),
                    [
                        *flags(group),
                        "/tmp/active-reg-coupon.gds",
                        "--top",
                        "ACTIVE_REG_CAP_ARRAY",
                        "--expect-rule-categories-file",
                        "<categories>",
                        "--max-violations",
                        "5",
                        "--format",
                        "json",
                    ],
                )

    def test_check_rejects_a_drifted_inventory_or_tool_version(self):
        for drift, complaint in (("inventory", "rule inventory for all: 767"), ("klt_version", "provenance.klt_version")):
            with self.subTest(drift=drift):
                _, klt = native_reports()
                if drift == "inventory":
                    klt.listings["all"] = "\n".join(listing("all").splitlines()[1:]) + "\n"
                else:
                    row = report("all")
                    row["provenance"]["klt_version"] = "0.9.3"
                    klt.runs["all"] = (3, json.dumps(row), "")
                with check_coupon() as runner, patch.dict(vars(runner["coupon_drc"]), {"subprocess": klt}):
                    with self.assertRaises(ValueError) as failure:
                        runner["check"]("/tmp/active-reg-coupon.gds", self.PDK, "all")
                self.assertIn(complaint, str(failure.exception))

    def test_cli_prints_the_sorted_summary_for_both_decks(self):
        committed, klt = native_reports()
        out = io.StringIO()
        with (
            check_coupon() as runner,
            patch.dict(vars(runner["coupon_drc"]), {"subprocess": klt}),
            patch.object(runner["screen"].pdk, "find_pdk", return_value=self.PDK),
            patch.object(sys, "argv", ["check_coupon.py", "/tmp/active-reg-coupon.gds"]),
            contextlib.redirect_stdout(out),
        ):
            runner["main"]()
        self.assertEqual(
            out.getvalue(),
            json.dumps(
                {g: {**row, "provenance": report(g)["provenance"]} for g, row in committed.items()},
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )


class CouponDrcCli(unittest.TestCase):
    def standin(self, pdk, **drifted):
        """A klt whose reports name `pdk` as the deck location, as the real CLI reports it."""
        runs = {}
        for group in GROUPS:
            row = drifted.get(group) or report(group)
            row["deck"] = row["native_deck"]["deck_file"] = str(pdk / DECK)
            runs[group] = (3 * (group == "all"), json.dumps(row), "")
        return StandIn({g: listing(g) for g in GROUPS}, runs)

    def test_cli_compares_or_refreshes_the_committed_reports(self):
        main = coupon_drc()["main"]
        with tempfile.TemporaryDirectory() as tmp:
            pdk = Path(tmp).resolve() / "ciel"
            klt = self.standin(pdk)
            for runs, mode in enumerate(((), ("--write",)), start=1):
                with self.subTest(mode=mode):
                    root = main.__globals__["ROOT"] if not mode else Path(tmp) / "written"
                    if mode:
                        (root / "sim/clock-cap-screen/records").mkdir(parents=True)
                    out = io.StringIO()
                    with (
                        patch.dict(main.__globals__, {"subprocess": klt, "ROOT": root}),
                        patch.object(sys, "argv", ["coupon_drc.py", "--pdk-root", str(pdk), *mode]),
                        contextlib.redirect_stdout(out),
                    ):
                        main()
                    self.assertEqual(out.getvalue(), SUMMARY)
                    self.assertEqual(len(klt.calls), 4 * runs)
                    for call in klt.calls[-4:]:
                        shared = flags(StandIn.group(call.argv), CLOCK_KLT, pdk)
                        if call.expected is None:
                            self.assertEqual(call.argv, [*shared, "--list-rule-categories"])
                        else:
                            self.assertEqual(
                                masked(call),
                                [
                                    *shared,
                                    "sim/clock-cap-screen/records/cap-coupon.gds",
                                    "--top",
                                    "CAPACITOR_COUPON",
                                    "--expect-rule-categories-file",
                                    "<categories>",
                                    "--format",
                                    "json",
                                ],
                            )
                        self.assertEqual(call.cwd, root)
                    for group in GROUPS:
                        written = root / "sim/clock-cap-screen/records" / f"drc-{group}.json"
                        self.assertEqual(written.read_text(), (SCREEN / "records" / f"drc-{group}.json").read_text())

    def test_cli_names_the_field_that_drifted_from_the_committed_report(self):
        main = coupon_drc()["main"]
        drifted = report("all")
        drifted["violation_count"] = 6
        klt = self.standin(Path("/nonexistent/ciel"), all=drifted)
        out = io.StringIO()
        with (
            patch.dict(main.__globals__, {"subprocess": klt}),
            patch.object(sys, "argv", ["coupon_drc.py", "--pdk-root", "/nonexistent/ciel"]),
            contextlib.redirect_stdout(out),
            self.assertRaisesRegex(ValueError, "all: changed violation_count"),
        ):
            main()
        self.assertEqual(out.getvalue(), SUMMARY.splitlines(keepends=True)[0])
        self.assertEqual(len(klt.calls), 4)
