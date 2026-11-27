"""Replay the coupon through the two native GF180D DRC invocations."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RECORDS = Path("sim/clock-cap-screen/records")
KLT = ("uvx", "--from", "klayout-tools==0.9.2", "klt", "drc")
EXTRA_DENSITY = {"DCF.1b", "PL.8", "M1.4", "M2.4", "M3.4"}
EXPECTED_CATEGORY_COUNTS = {"mim_b": 12, "all": 768}


def run_group(layout, top, pdk_root, group, *, klt_prefix, extra_args=(), cwd=None, check_versions=None):
    """Run the native GF180D ``group`` deck on ``layout`` and return ``(report, rules)``.

    ``klt_prefix`` is the command up to and including ``drc``. The deck must exit 0 on a
    clean coupon and 3 on the expected density markers, and its report must satisfy the
    coverage assertion, the expected rule counts and any ``check_versions`` pins on
    ``provenance``.
    """
    base = [
        *klt_prefix,
        "--engine",
        "klayout",
        "--pdk",
        "gf180mcuD",
        "--pdk-root",
        str(pdk_root),
        "--deck-var",
        "variant=D",
        "--deck-var",
        f"decks={group}",
        "--deck-var",
        "threads=1",
    ]
    listing = subprocess.check_output([*base, "--list-rule-categories"], cwd=cwd, text=True)
    rules = set(listing.splitlines())
    if group == "all":
        # The full deck declares these five extra density rules on the populated coupon.
        rules |= EXTRA_DENSITY
    if len(rules) != EXPECTED_CATEGORY_COUNTS[group]:
        raise ValueError(f"Unexpected native rule inventory for {group}: {len(rules)}")
    counts = dict.fromkeys(EXTRA_DENSITY, 1) if group == "all" else {}
    with tempfile.TemporaryDirectory() as tmp:
        expected = Path(tmp) / "expected.txt"
        expected.write_text("\n".join(sorted(rules)) + "\n")
        proc = subprocess.run(
            [
                *base,
                str(layout),
                "--top",
                top,
                "--expect-rule-categories-file",
                str(expected),
                *extra_args,
                "--format",
                "json",
            ],
            cwd=cwd,
            text=True,
            capture_output=True,
        )
    status = 3 if counts else 0
    if proc.returncode != status:
        raise RuntimeError(
            f"Unexpected {group} DRC exit status {proc.returncode}, expected {status}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    report = json.loads(proc.stdout)
    failing = [
        name
        for name, found, wanted in (
            ("coverage_assertion", report["coverage_assertion"]["satisfied"], True),
            ("rule_counts", report["rule_counts"], counts),
            ("coverage.checked", set(report["coverage"]["checked"]), rules),
            *(
                (f"provenance.{key}", report["provenance"].get(key), version)
                for key, version in (check_versions or {}).items()
            ),
        )
        if found != wanted
    ]
    if failing:
        raise ValueError(f"Unexpected {group} native DRC result: {', '.join(failing)}")
    return report, rules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="refresh both reports")
    args = parser.parse_args()
    pdk_root = args.pdk_root.resolve()
    variant = Path("gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc")
    for group in ("mim_b", "all"):
        report, rules = run_group(
            RECORDS / "cap-coupon.gds",
            "CAPACITOR_COUPON",
            pdk_root,
            group,
            klt_prefix=KLT,
            cwd=ROOT,
        )
        # Strip only the installation directory from these two display paths.
        # Keep KLT's native input, rule inventory and deck-tree provenance intact.
        for owner, field in ((report, "deck"), (report["native_deck"], "deck_file")):
            if Path(owner[field]).resolve() != (pdk_root / variant).resolve():
                raise ValueError(f"Unexpected deck location {owner[field]}")
            owner[field] = variant.as_posix()
        target = ROOT / RECORDS / f"drc-{group}.json"
        if args.write:
            target.write_text(json.dumps(report, indent=2) + "\n")
        else:
            saved = json.loads(target.read_text())
            # Runtime binaries can differ by host. Require the pinned engine and deck versions.
            for key in (
                "file",
                "status",
                "violation_count",
                "rule_counts",
                "coverage",
                "provenance",
                "native_deck",
            ):
                if saved[key] != report[key]:
                    raise ValueError(f"{group}: changed {key}")
        print(
            f"{group}: {len(rules)} categories, "
            f"{sum(report['rule_counts'].values())} markers"
        )


if __name__ == "__main__":
    main()
