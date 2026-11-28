# T1 signoff

From the repo root, use a Python environment with ngspice on PATH. Install
the pinned tools and enable the PDK revision recorded in the evidence.

    python3 -m pip install ciel==3.3.0 -r signoff/requirements.txt
    export PDK_ROOT="$PWD/.pdk"
    ciel enable --pdk-family gf180mcu f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7
    bash signoff/check.sh

The check runs the reference doubler at TT, 25 °C and 3.3 V on each bench,
checks its declared measurements, repeats capacitor extraction and runs the
simulation-gate unit tests. CI also runs the entire simulation suite with
the PDK and ngspice required. The two attestations cover reproducible
testbenches and repository hygiene. Device implementation, layout and
performance evidence for a selected topology remain open.

After a deliberate change to an inventoried input, use the same environment
to regenerate the affected envelope. For example, for the bench inventory:

    klt signoff --attest 9 --inventory signoff/item9.json --output signoff/item9.generic.json

Use the printed manifest entry for that item in block-manifest.json. To update
the report, run the following and inspect its exit code. Exit 3 with the
graded items lists outstanding evidence. Other errors require investigation.

    klt signoff --manifest signoff/block-manifest.json --format json > signoff/block-manifest.signoff.json

Run signoff/check.sh again after regenerating and review the resulting diff.
