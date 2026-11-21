"""The `kill-server` guard docs/tmux.md suggests, on the demo's own server."""

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("tmux"), reason="needs tmux")

_ROOT = Path(__file__).parent.parent
_SCRIPT = _ROOT / "scripts" / "demo-inbox.py"

# Not `--kill`, which also removes the real demo's state in /tmp/lemonaid-demo.
_END_SERVER = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("demo_inbox", sys.argv[1])
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)
demo._end_server()
"""


def _documented_guard() -> str:
    lines = (_ROOT / "docs" / "tmux.md").read_text().splitlines()
    return next(line for line in lines if line.startswith("set -s 'command-alias[4242]'"))


def test_the_guard_refuses_kill_server_and_the_demo_still_ends_its_server():
    with tempfile.TemporaryDirectory(prefix="lma-guard-", dir="/tmp") as directory:
        config = Path(directory) / "tmux.conf"
        config.write_text(_documented_guard() + "\n")
        env = {**os.environ, "TMUX_TMPDIR": directory}  # where the demo's `-L` server goes
        demo = ["tmux", "-L", "lemonaid-demo"]
        subprocess.run([*demo, "-f", str(config), "new-session", "-d"], env=env, check=True)
        pid = subprocess.run(
            [*demo, "display-message", "-p", "#{pid}"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        try:
            refused = subprocess.run(
                [*demo, "kill-server"], env=env, capture_output=True, text=True
            )
            ended = subprocess.run(
                [sys.executable, "-c", _END_SERVER, str(_SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
            )
            gone = subprocess.run([*demo, "has-session"], env=env, capture_output=True).returncode
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(pid), signal.SIGTERM)

    assert refused.returncode == 1 and "refuses kill-server" in refused.stdout
    assert ended.returncode == 0, ended.stderr
    assert gone != 0
