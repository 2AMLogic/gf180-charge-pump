# Work Log

Chronological record of merged PRs and closed issues, maintained by the Guide role.

## Archives

_None yet._

## Entries

### 2026-11-25

- **PR #37**: docs: record ngspice 45.2 vs 47 sim-tests outcome comparison
- **Issue #33** (closed): sim gate runs ngspice-45.2 while recorded evidence is ngspice-47: sensitivity unmeasured
- **PR #38**: fix: use PvtPoint.as_dict() for Vout scope lines so mimcap tag is recorded
- **Issue #31** (closed): pump_evidence.evaluate drops mimcap, leaving output_lines' mimcap branch dead on the report path
- **PR #34**: fix: expect NO_STRESS_LINE for empty scope in render_lines summary test
- **Issue #32** (closed): sim-tests fails deterministically on main: test_single_point_and_empty asserts [] while render_lines emits NO_STRESS_LINE
- **Issue #27** (closed): sim-tests CI pins the PDK revision but floats ngspice and ciel versions
- **PR #30**: ci: pin ciel and document floating ngspice in sim-tests
- **Issue #17** (closed): Scope-rule record section is silent on device stress for a bench with no stress_* measurements
- **PR #23**: feat: state absence of device-stress measurements in scope section
- **PR #26**: ci: run sim/tests in CI and fail instead of skip when the simulator is missing
- **Issue #21** (closed): No CI workflow runs the sim test suite — 'CI green' in this repo means CodeQL only
- **PR #25**: test: cover render_markdown MIM-corner UNVERIFIED tag
- **Issue #22** (closed): render_markdown's 'MIM-corner coverage UNVERIFIED' line has no test coverage
- **PR #24**: feat: summarize Vout scope bullets per measurement in Markdown record
- **Issue #18** (closed): Scope-rule section enumerates 405 Vout bullets per record on the default 135-point grid
- **PR #19**: feat: add mimcap axis to sensitivity checks and tag unverified MIM coverage
- **Issue #15** (closed): The mimcap corner axis is inert for every current bench: no bench instantiates a MIM cap device
- **PR #16**: feat: apply Vout-load and device-stress scope rule in the report path
- **Issue #12** (closed): pump_evidence.output_lines/stress_margins are never called outside tests: wire into report or drop
- **Issue #7** (closed): Flying-cap value is held at typical: the PVT grid does not sweep the PDK's MIM capacitor corners
- **PR #13**: feat: add mimcap corner family and 135-point PVT grid with report tagging
- **Issue #11** (closed): Report two Loom work-docs observations upstream (WORK_LOG seed template; archive footer handling)
- **Issue #9** (closed): WORK_LOG.md: dated entries land nested under '## Archives'
- **PR #10**: docs: add Entries heading to WORK_LOG.md above dated blocks
- **PR #5**: feat: add charge-pump stress, load, load-step and startup benches
- **Issue #2** (closed): Harness bootstrap: pump testbenches, device-stress and load benches

<!-- Maintained automatically by the Guide triage agent. Manual edits are fine but may be overwritten. -->
