"""Helpers for the Slack watch tests."""

import time

from lemonaid.sources import host


def wait_ready(key: str, timeout: float = 5.0) -> None:
    """Until the plugin has said subscription *key* is ready, which `serve` notices within a
    look at the wake files."""
    deadline = time.monotonic() + timeout
    while key not in host._host.ready:
        assert time.monotonic() < deadline, "the plugin never said ready"
        time.sleep(0.02)
