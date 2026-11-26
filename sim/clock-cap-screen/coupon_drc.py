"""Replay the coupon through the two native GF180D DRC invocations."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RECORDS = Path("sim/clock-cap-screen/records")
EXTRA_DENSITY = {"DCF.1b", "PL.8", "M1.4", "M2.4", "M3.4"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdk-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="refresh both reports")
    args = parser.parse_args()
    pdk_root = args.pdk_root.resolve()
    variant = Path("gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc")
    for group in ("mim_b", "all"):
        base = [
            "uvx",
            "--from",
            "klayout-tools==0.9.2",
            "klt",
            "drc",
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
        listing = subprocess.check_output(
            [*base, "--list-rule-categories"], cwd=ROOT, text=True
        )
        rules = set(listing.splitlines())
        if group == "all":
            # The full deck declares these five extra density rules on the populated coupon.
            rules |= EXTRA_DENSITY
        if len(rules) != (768 if group == "all" else 12):
            raise ValueError(
                f"Unexpected native rule inventory for {group}: {len(rules)}"
            )
        with tempfile.NamedTemporaryFile(mode="w") as expected:
            expected.write("\n".join(sorted(rules)) + "\n")
            expected.flush()
            proc = subprocess.run(
                [
                    *base,
                    str(RECORDS / "cap-coupon.gds"),
                    "--top",
                    "CAPACITOR_COUPON",
                    "--expect-rule-categories-file",
                    expected.name,
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
        report = json.loads(proc.stdout)
        counts = dict.fromkeys(EXTRA_DENSITY, 1) if group == "all" else {}
        if (
            proc.returncode != (3 if counts else 0)
            or report.get("rule_counts") != counts
            or set(report["coverage"]["checked"]) != rules
        ):
            raise ValueError(
                f"Unexpected {group} DRC status: {proc.returncode}, {report.get('error', report.get('rule_counts'))}"
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
        print(f"{group}: {len(rules)} categories, {sum(counts.values())} markers")


if __name__ == "__main__":
    main()
