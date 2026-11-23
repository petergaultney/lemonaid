import time
import types

import pytest

from lemonaid.watch import slack_events

NOW = 1794858000.0  # just after the newest fixture timestamps in these tests


@pytest.fixture(autouse=True)
def fixed_wall_clock(monkeypatch):
    """The quiet-thread rule compares fixture timestamps to `time.time()`; pin it."""
    monkeypatch.setattr(
        slack_events, "time", types.SimpleNamespace(time=lambda: NOW, monotonic=time.monotonic)
    )
