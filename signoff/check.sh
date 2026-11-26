#!/usr/bin/env bash
# Run from any directory. A partial tier grade exits 3 on render, by design.
set -eu
cd "$(dirname "$0")/.."

required=$(sed -n 's/^klayout-tools==//p' signoff/requirements.txt)
if [ -z "$required" ] || [ "$(klt --version)" != "klt $required" ]; then
    echo "Install the grader with python3 -m pip install -r signoff/requirements.txt" >&2
    exit 1
fi
for item in 9 10; do
    klt signoff --attest "$item" --inventory "signoff/item$item.json" \
        --check "signoff/item$item.generic.json"
done
klt signoff --manifest signoff/block-manifest.json --check signoff/block-manifest.signoff.json
