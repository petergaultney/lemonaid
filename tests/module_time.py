"""Replace `time` functions as one module sees them, leaving every other thread the real ones.

`monkeypatch.setattr(module.time, "monotonic", ...)` patches the one `time` module the
whole worker shares, so a thread left running by an earlier test can take the values a
test scripted for the code under test.
"""

import time
import types
from collections import abc

import pytest


def patch(
    monkeypatch: pytest.MonkeyPatch, module: types.ModuleType, **functions: abc.Callable
) -> None:
    monkeypatch.setattr(module, "time", types.SimpleNamespace(**{**vars(time), **functions}))
