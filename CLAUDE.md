# gf180-charge-pump — agent instructions

Open-source canary block: a Charge pump on the gf180mcu PDK,
designed and verified by AI agents — an **analog** block.

- **PDK**: gf180mcu (open PDK).
  Schematics in xschem, simulation in ngspice.
  Layout, DRC, and LVS go through klayout-tools (`klt`).
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker is
  scoped to the tool, so keep design-specific detail (spec values, this repo's
  content) out of it and describe the gap, not the design.
- **Verification is the product**: no claim without a testbench. Recorded
  results are append-only evidence; a result is not superseded by deletion, it
  is superseded by a later record that says why.
- Spec changes go through `spec/` with a decision record. Agents do not relax
  the ratified spec to make a result pass.
- **Ratification is a merged PR, and the status line merges with it.**
  Open the record's PR with `Status: proposed`. When ready, set
  `Status: RATIFIED` or mark only the ratified rows for a partial ratification.
  Push the status change in the ratifying PR before requesting any review.
  A change to a spec row or bound needs an EE review and a market review; a
  process record (no spec row or bound) needs only the EE review, and a record
  whose classification is unclear gets both. The reviewers must be distinct,
  and neither may have authored the PR or the design. They follow
  centrally pinned instructions and record their reviews against that head.
  Once the operator ratifies and `2am/ratification` turns green, merge that
  head. If you push again, repeat the reviews that apply on the new head
  before the operator ratifies it. Keep reviewer files out of this repo.

- **Scope discipline: the output is only the output under load, at the worst
  corner, inside device ratings.** The easy mistake here is quoting a no-load,
  typical-corner output voltage, or an output reached by overstressing a
  device. Every output-voltage claim states its load current and corner, and
  every simulation checks every node against its device's rated
  Vds/Vgs/Vdb, transients included. A topology that meets the output by
  exceeding a rating is a failing result, not a stretch. Do not use the
  `nfet_10v0_asym` PCell (known native-DRC findings inside the unmodified
  PCell) without a decision record. This repo is public: do not reference
  private 2AM repos or describe downstream product applications. The only
  framing is the generic one: programming supply for on-die OTP cells.

## Harness bootstrap

Copy the analog harness pattern of
[`gf180-buck`](https://github.com/2AMLogic/gf180-buck) (a switched power
stage on `nfet_06v0`/`pfet_06v0` with `device-stress`, `load-step` and
`current-limit` benches): it supplies the **testbench and device-stress
half**. [`gf180-ldo`](https://github.com/2AMLogic/gf180-ldo) supplies the
**output-regulation and PVT-corner reporting half**. Load requirements come
from [`gf180-efuse-otp`](https://github.com/2AMLogic/gf180-efuse-otp)'s
program-path assumptions; track that repo's decision records if they change.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/2AMLogic/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.

Work is coordinated through `loom:` labels on issues and pull requests, and the same roles run either under `loom-daemon` or by hand in an attended session — daemon mode is optional. Create the labels once with `.loom/scripts/sync-labels.sh` (an install ships `.github/labels.yml` but does not create the labels on the forge). A pull request ready for review carries `loom:review-requested`; Judge reviews it and applies `loom:pr` (approved) or `loom:changes-requested`; Doctor fixes a `loom:changes-requested` pull request and returns it to `loom:review-requested`. Only a `loom:pr` pull request gets merged, and always via this repo's merge script (`.loom/scripts/merge-pr.sh`) — never a raw forge merge command such as `gh pr merge`. Full state machine: `.loom/docs/label-state-machine.md`.
<!-- END LOOM ORCHESTRATION -->
