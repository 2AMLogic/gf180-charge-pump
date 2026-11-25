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
  is not simulator-sensitive; it is a stale expectation after `7991f56`
  (empty-stress line change), already tracked as #32.

Conclusion: **insensitive to ngspice 45.2 vs 47 on this suite: outcomes identical
(45 pass / 1 identical non-simulator failure, 46/46 match).**

## Limits

The suite asserts pass/fail against bounds. Numeric values were not compared
between versions, so this bounds outcome sensitivity, not numeric agreement of
individual waveforms. The committed cap-model evidence was not re-run.
