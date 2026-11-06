"""
Test setup

Upstream v2.53.0 declares the package globals (cfg, api, realtime_state...)
without values, they are only set by tinypedal.start(). Modules import them at
import time, so give them a None placeholder for tests, as before v2.53.0.
Tests replace the ones they use with monkeypatch.
"""

import sys

sys.path.append(".")
sys.path.append("thirdparty")

import tinypedal  # noqa: E402

for _name in tinypedal.__annotations__:
    if not hasattr(tinypedal, _name):
        setattr(tinypedal, _name, None)
