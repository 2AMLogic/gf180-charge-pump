"""Gate for tests that need ngspice and the PDK.

Locally, a box without ngspice or the PDK skips those tests. In CI the
workflow sets ``REQUIRE_SIM=1``: a missing tool then *fails* the test, so a
run that could not simulate never reports ``OK (skipped=N)``.
"""

from __future__ import annotations

import functools
import os
import unittest

REQUIRE_ENV = "REQUIRE_SIM"
MESSAGE = "needs ngspice and the gf180mcu PDK"


def require_sim_enabled() -> bool:
    return os.environ.get(REQUIRE_ENV, "") not in ("", "0")


def requires_sim(can_simulate):
    """Decorator: skip when unable to simulate, or fail if REQUIRE_SIM is set.

    ``can_simulate`` is a zero-argument callable evaluated at call time.
    """

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            if not can_simulate():
                if require_sim_enabled():
                    self.fail(f"{REQUIRE_ENV} is set but the simulator is unavailable: {MESSAGE}")
                raise unittest.SkipTest(MESSAGE)
            return fn(self, *args, **kwargs)

        return wrapper

    return decorate
