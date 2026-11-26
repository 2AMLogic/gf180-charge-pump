"""Run the native GF180D MIM and full decks on the physical capacitor array."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

import screen


# These five low-density categories are declared only on measured coupon geometry.
# All other expected names come from the pinned deck's empty-layout listing.
DENSITY = {"DCF.1b", "M1.4", "M2.4", "M3.4", "PL.8"}


def check(layout, pdk, group):
    common = [
        "klt",
        "drc",
        "--deck",
        "gf180mcu",
        "--engine",
        "klayout",
        "--pdk",
        "gf180mcuD",
        "--pdk-root",
        str(pdk.path.parent),
        "--deck-var",
        "variant=D",
        "--deck-var",
        "decks=" + group,
        "--deck-var",
        "threads=1",
    ]
    listing = subprocess.check_output([*common, "--list-rule-categories"], text=True)
    names = set(listing.splitlines())
    if group == "all":
        names.update(DENSITY)
    with tempfile.TemporaryDirectory() as tmp:
        categories = Path(tmp) / "expected.txt"
        categories.write_text("\n".join(sorted(names)) + "\n")
        proc = subprocess.run(
            [
                *common,
                str(layout),
                "--top",
                "ACTIVE_REG_CAP_ARRAY",
                "--expect-rule-categories-file",
                str(categories),
                "--max-violations",
                "5",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode not in (0, 3):
            raise RuntimeError(proc.stdout + proc.stderr)
    result = json.loads(proc.stdout)
    expected_counts = {} if group == "mim_b" else dict.fromkeys(DENSITY, 1)
    if (
        not result["coverage_assertion"]["satisfied"]
        or result["rule_counts"] != expected_counts
        or result["provenance"]["klt_version"] != "0.9.2"
        or result["provenance"]["klayout_version"] != "0.30.14"
    ):
        raise ValueError(f"Unexpected {group} native coupon result or tool version")
    observed = sorted(result["coverage"]["rules_checked"])
    return {
        "status": result["status"],
        "violation_count": result["violation_count"],
        "rule_counts": result["rule_counts"],
        "checked_categories": len(observed),
        "checked_names_sha256": sha256(
            ("\n".join(observed) + "\n").encode()
        ).hexdigest(),
        "coverage_assertion_satisfied": result["coverage_assertion"]["satisfied"],
        "provenance": result["provenance"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    args = parser.parse_args()
    pdk = screen.pdk.find_pdk(screen.HERE.parent)
    groups = {g: check(args.layout, pdk, g) for g in ("mim_b", "all")}
    print(json.dumps(groups, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
