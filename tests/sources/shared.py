import sys
import time
from pathlib import Path

from lemonaid.plugins import command
from lemonaid.sources import host, plugin

_SCRIPT = Path(__file__).with_name("fake_source.py")
FAKE = plugin.Source(command.Plugin("fake", (sys.executable, "-I", str(_SCRIPT))))
CONFIG = f"""
[[watch.sources]]
name = "fake"
command = "{sys.executable} -I {_SCRIPT}"
"""


def wait_ready(key: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while key not in host._ready:
        assert time.monotonic() < deadline, "the plugin never said ready"
        time.sleep(0.02)
