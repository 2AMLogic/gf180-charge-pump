"""Run the native GF180D MIM and full decks on the physical capacitor array."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import screen

sys.path.append(str(screen.ORIGINAL.parent))
import coupon_drc  # noqa: E402

PINS = {"klt_version": "0.9.2", "klayout_version": "0.30.14"}


def check(layout, pdk, group):
    report, _ = coupon_drc.run_group(
        layout,
        "ACTIVE_REG_CAP_ARRAY",
        pdk.path.parent,
        group,
        klt_prefix=("klt", "drc", "--deck", "gf180mcu"),
        extra_args=("--max-violations", "5"),
        check_versions=PINS,
    )
    observed = sorted(report["coverage"]["rules_checked"])
    return {
        "status": report["status"],
        "violation_count": report["violation_count"],
        "rule_counts": report["rule_counts"],
        "checked_categories": len(observed),
        "checked_names_sha256": sha256(
            ("\n".join(observed) + "\n").encode()
        ).hexdigest(),
        "coverage_assertion_satisfied": report["coverage_assertion"]["satisfied"],
        "provenance": report["provenance"],
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
