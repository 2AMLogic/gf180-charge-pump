# Work Plan

Backlog snapshot from current GitHub label state, maintained by the Guide role.

The body below is a snapshot of GitHub label state as of the last merged docs-maintenance PR — it may lag live labels until the next one merges. The `_Generated:` stamp at the top of the generated region dates the snapshot; `git log -1 -- WORK_PLAN.md` finds the merge that wrote it.

<!-- Maintained automatically by the Guide triage agent. Manual edits are fine but may be overwritten. -->

<!-- guide:plan-body:start -->
_Generated: 2026-11-25T01:39:42Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#1**: Ratify the target spec

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held, `loom:building`, and issues with an open linked PR.

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#2**: Harness bootstrap: pump testbenches, device-stress and load benches

## Backlog Balance

| Bucket | Count |
|------|-------|
| Very important | 0 |
| Important | 1 |
| Ready | 0 |
| In Progress | 1 |
| Held, no other bucket | 1 |
<!-- guide:plan-body:end -->
