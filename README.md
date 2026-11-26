# gf180-charge-pump

A Charge pump on the [gf180mcu](https://github.com/google/gf180mcu-pdk) open PDK,
designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the open-source
flow — xschem + ngspice, with layout, DRC, and LVS through klayout-tools.

It turns the chip's 3.3 V core supply into a higher on-die voltage (target 5 V
at 10 mA) so one-time-programmable memories such as eFuses and gate-oxide
antifuses can be programmed without an external high-voltage pin, which a
3.3 V-only shuttle pad ring does not offer.

## Status

```
Area (measured, post-layout): not yet measured
Design stage: spec
```

<!-- The two fields above are correct as they stand for a repo where nothing is
     built yet, so there is nothing to fill in here — only to keep current. They
     are a fixed-location summary a chip-level integrator reads without parsing
     the prose below, so the keys, their spelling, and their order do not change.

     Area (measured, post-layout): the as-built area of a DRC-clean,
     LVS-matched layout, as a number with units (e.g. 1.059 mm²), taken from
     this repo's own committed measurement. Never a target, a plan, or an
     estimate — the ratified bound is the AREA row of the target-specification
     table below. Until a layout exists, the literal "not yet measured".

     Design stage: exactly one token, from this ladder, in order —
     spec | schematic-sim | layout-DRC-LVS-clean | extracted-verified | silicon
     — describing what this repo has produced and recorded evidence for, never
     what it is aiming at. One token; not a range, not a hedge, not prose. -->

**Just opened, specification phase.** Nothing is designed yet, nothing has been
taped out, and nothing has been measured.

Deliberately **not** being built yet:

- **Outputs above ~6 V.** Every node must stay within its device rating, and
  the 6.0 V `nfet_06v0`/`pfet_06v0` devices are the ceiling for now. Going
  higher needs the 10 V drain-extended `nfet_10v0_asym`, and the PDK's own
  KLayout PCell for that device currently fails the native DRC deck
  (`CO.4`, `DF.6_MV`, `PL.4_MV`) at default settings. A high-voltage stretch
  variant waits on a DRC-clean 10 V device.
- **Layout.** Nothing is drawn until the target spec below is ratified and
  the topology (Dickson vs. cross-coupled, stage count, clocking) is chosen in
  a decision record with simulated evidence.
- **A full regulator.** The first deliverable is the pump with enable,
  clocking and output-voltage limiting. Tight regulation and a programmable
  output are stretch rows.

## CI

The `sim-tests` workflow runs the whole `sim/tests` suite with ngspice and the
gf180mcu PDK installed and `REQUIRE_SIM=1`, so a missing simulator fails the
check instead of skipping. CodeQL green alone says nothing about the suite;
look for a green `sim-tests` check. Locally, without `REQUIRE_SIM`, the
simulator-dependent tests skip.

## Built agent-native

Every specification, decision record, testbench, and line of documentation in
this repo is produced by AI agents working from a ratified spec and an
append-only evidence trail — not human-authored work that agents merely
assisted with. Verification is the product: every claim traces to a recorded
result. Where the agents hit friction with the open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction gets
filed as a public issue against the tool itself, so the fix benefits everyone
using gf180mcu, not just this repo.

## Target specification

The target column takes effect on merge of the independently reviewed,
operator-approved [specification](spec/0001-target-spec.md) for issue #1.
The stretch column lists goals outside that decision.

| Parameter | Target | Stretch |
|---|---|---|
| Input supply | 3.3 V ±10% (2.97–3.63 V) | — |
| Output voltage at 10 mA load, all PVT corners (≤ 5.5 V with no load) | 5.0 V ±10% (4.5–5.5 V) | programmable 4.0–5.5 V |
| Load current at that output | ≥ 10 mA, continuous for ≥ 10 µs | ≥ 20 mA |
| Enable to output within spec | ≤ 10 µs | ≤ 2 µs |
| Output ripple at full load | ≤ 100 mV p-p | ≤ 25 mV p-p |
| Device stress | no device exceeds its rated Vds / Vgs / Vdb at any corner, transient included | — |
| Core area (footprint including all capacitors) | ≤ 0.50 mm² (draft 0.25 mm²; see record §3) | ≤ 0.10 mm² |
| PVT corners | tt/ff/ss/fs/sf × −40/25/125 °C × supply ±10% | — |

The output and load rows are the program-supply assumptions of the sibling
[gf180-efuse-otp](https://github.com/2AMLogic/gf180-efuse-otp) (its
assumptions A1–A3, which have no PDK source). They are inherited as targets
here, not measured facts. The central tension the review must settle is
**area vs. current**: 10 mA at ≤ 100 mV ripple needs about 0.36 mm² of MIM
capacitance at 100 MHz (more at lower clocks) before switches and overhead,
so the record proposes that the load and ripple rows govern and the area row
moves to ≤ 0.50 mm². The reviewers decide.

Issue #1 takes this target spec through review. A separate EE reviewer and a
separate market reviewer, neither the author of the PR or of the design, read centrally pinned
instructions and record their reviews against the PR's current head; the
operator then ratifies, and the `2am/ratification` status turns green. The
review instructions are not stored in this repo, and a new push to the PR
starts the reviews over.

## Repo layout

```
design/        schematics (xschem)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
sim/           analog testbenches + PVT corner results
spec/          ratified spec + decision records
WORK_LOG.md    chronological record of merged PRs and closed issues
WORK_PLAN.md   backlog snapshot from GitHub label state
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
