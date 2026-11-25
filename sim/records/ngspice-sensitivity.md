# ngspice version sensitivity of the sim-tests suite

Status: measurement record (append-only; supersede with a later record, do not edit).
Date: 2026-11-25. Issue: #33.

## Method

The full `sim/tests` suite, `python3 -m unittest discover -s sim/tests -t . -v`
with `REQUIRE_SIM=1`, was run at one commit under two simulator versions, same PDK:

| Run | Simulator line | Where | Commit | PDK (`open_pdks`) | Tests | Result |
|-----|----------------|-------|--------|-------------------|-------|--------|
| A | `** ngspice-45.2 : Circuit level simulation program` | CI, `sim-tests` run 45575159904 (ubuntu-latest apt) | `8cd63f2dbf9a400c89c6ee47a0082dee7663469b` | `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` | 46 | 45 pass, 1 fail |
| B | `** ngspice-47 : Circuit level simulation program` | loom worker, serial, `PDK_ROOT=~/.ciel` | `8cd63f2dbf9a400c89c6ee47a0082dee7663469b` | `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` | 46 | 45 pass, 1 fail |

The suite now has 46 tests, not the 42 the issue quoted; main gained tests since.
Neither run skipped a test.

## Result

Per-test outcome lines (name plus `ok`/`FAIL`) were extracted from both logs and
compared after sorting: **identical, 46/46 outcomes match.** No test differs
between ngspice-45.2 and ngspice-47.

- 45 tests pass on both versions.
- 1 test fails on both versions:
  `sim.tests.test_benches.RenderLinesSummary.test_single_point_and_empty`
  (`sim/tests/test_benches.py:196`). `render_lines({"output_lines": [], "stress": []})`
  returns one "No device-stress margin is recorded..." line where the test expects
  `[]`. This is a pure-Python rendering assertion that does not invoke ngspice. It
  is not simulator-sensitive; it is a stale expectation, tracked as #32. Measured
  history: `bde908b` added the test on a branch where `render_lines` returned `[]`
  for an empty scope (no `NO_STRESS_LINE` branch); a parallel lineage already
  emitted `NO_STRESS_LINE` unconditionally (`7991f56` only reworded its text). The
  expectation went stale when the two lineages merged. #32 owns the fix.

Conclusion: **insensitive to ngspice 45.2 vs 47 on this suite: outcomes identical
(45 pass / 1 identical non-simulator failure, 46/46 match).**

## Limits

The suite asserts pass/fail against bounds. Numeric values were not compared
between versions, so this bounds outcome sensitivity, not numeric agreement of
individual waveforms. The committed cap-model evidence was not re-run.

Run A's log is re-derivable from the CI run cited above. Run B's log (a local
run on a loom worker) is not committed or linked, so the "46/46 outcomes match"
comparison against it cannot be re-derived from the repository; it rests on the
recorder's local extraction. Re-running run B at `8cd63f2` with ngspice-47 and
the same PDK revision is the way to reproduce it.
