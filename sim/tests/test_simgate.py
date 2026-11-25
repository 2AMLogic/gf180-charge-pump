"""REQUIRE_SIM turns a missing simulator from a skip into a failure (issue #21)."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness import simgate  # noqa: E402


def _run(can_simulate, env):
    class Case(unittest.TestCase):
        @simgate.requires_sim(can_simulate)
        def test_x(self):
            pass

    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("REQUIRE_SIM", None)
        os.environ.update(env)
        result = unittest.TestResult()
        Case("test_x").run(result)
    return result


class SimGate(unittest.TestCase):
    def test_missing_sim_skips_without_env(self):
        r = _run(lambda: False, {})
        self.assertEqual((len(r.skipped), len(r.failures)), (1, 0))

    def test_missing_sim_fails_with_env(self):
        r = _run(lambda: False, {"REQUIRE_SIM": "1"})
        self.assertEqual((len(r.skipped), len(r.failures)), (0, 1))

    def test_zero_is_not_enabled(self):
        r = _run(lambda: False, {"REQUIRE_SIM": "0"})
        self.assertEqual(len(r.skipped), 1)

    def test_available_sim_runs(self):
        r = _run(lambda: True, {"REQUIRE_SIM": "1"})
        self.assertEqual((r.testsRun, len(r.skipped), len(r.failures), len(r.errors)), (1, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
