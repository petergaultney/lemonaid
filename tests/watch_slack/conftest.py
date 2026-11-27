"""The Slack plugin runs in this process, behind the real protocol, so the fake Slack API and
Keychain (tests/lemonaid_slack/shared.py) stand in for the real ones."""

import json
import os
import subprocess
import threading
import time
import types

import pytest

from lemonaid.inbox import db
from lemonaid.plugins import processes, running
from lemonaid.sources import host, plugin
from lemonaid_slack import follow, gateway_socket, serve

NOW = 1794858000.0  # just after the newest fixture timestamps in these tests


class _InProcess:
    """`subprocess.Popen` for the plugin: `serve.main` on a thread, over pipes."""

    def __init__(self, argv, **pipes) -> None:
        to_plugin, self._into = os.pipe()
        self._out, from_plugin = os.pipe()
        self.stdin = os.fdopen(self._into, "wb")
        self.stdout = os.fdopen(self._out, "rb")
        reads, writes = os.fdopen(to_plugin, "rb"), os.fdopen(from_plugin, "wb")

        def body() -> None:
            with reads, writes:
                serve.main(reads, writes)

        self._thread = threading.Thread(target=body, daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> int:
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise subprocess.TimeoutExpired("lemonaid-slack", timeout or 0)
        return 0

    def kill(self) -> None:
        pass


def _reset() -> None:
    processes.close()
    processes._failed_at.clear()
    host._ready.clear()
    host.check.cache_clear()


@pytest.fixture(autouse=True)
def plugin_in_process(monkeypatch):
    _reset()  # a plugin another test started ran as a real process
    monkeypatch.setattr(
        running,
        "subprocess",
        types.SimpleNamespace(
            Popen=_InProcess, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired
        ),
    )
    monkeypatch.setattr(gateway_socket, "available", lambda: False)
    for name, value in host.env(plugin.defaults()[0]).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LEMONAID_PLUGIN_CONFIG", json.dumps({"fetch_every": 60}))
    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))  # for the plugin's `lemonaid inbox`
    yield
    _reset()


@pytest.fixture(autouse=True)
def fixed_wall_clock(monkeypatch):
    """The quiet-thread rule compares fixture timestamps to `time.time()`; pin it."""
    monkeypatch.setattr(
        follow, "time", types.SimpleNamespace(time=lambda: NOW, monotonic=time.monotonic)
    )
