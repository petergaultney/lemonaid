"""Run the real coordinator, hooks, watcher and journal on a private tmux server."""

import contextlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from lemonaid.inbox import db
from lemonaid.launch.restart import pane
from lemonaid.watch import registry, stopping

from . import shared

_HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
  if (argc > 1 && !strcmp(argv[1], "queue")) {
    FILE *out = fopen(getenv("TEST_QUEUE"), "a");
    for (int i=0; i<argc; ++i) fprintf(out, "%s\n", argv[i]);
    const char *home = getenv("CODEX_HOME");
    const char *provider = getenv("CLAUDE_CODE_USE_BEDROCK");
    fprintf(out, "home=%s\nbedrock=%s\n", home ? home : "<unset>", provider ? provider : "<unset>");
    fclose(out); return 0;
  }
  FILE *hook = popen(getenv("TEST_HOOK"), "w");
  fprintf(hook, "{\"session_id\":\"%s\",\"model\":\"gpt-6\",\"effort\":\"high\",\"model_provider\":\"openai\",\"sandbox_policy\":\"workspace-write\",\"approval_policy\":\"on-request\"}", getenv("TEST_SESSION"));
  if (pclose(hook)) return 2;
  FILE *ready = fopen(getenv("TEST_STARTED"), "a");
  fprintf(ready, "%d\n", getpid()); fclose(ready);
  for (int i=1; i<argc; ++i) {
    if (strstr(argv[i], "You were just restarted")) {
      FILE *prompt = fopen(getenv("TEST_PROMPT"), "w");
      fprintf(prompt, "%s", argv[i]); fclose(prompt);
    }
  }
  while (1) {
    if (getenv("TEST_SELF") && !access(getenv("TEST_SELF"), F_OK)) {
      unlink(getenv("TEST_SELF"));
      system(getenv("TEST_SELF_COMMAND"));
    }
    usleep(50000);
  }
}
"""


def _until(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result := check():
            return result
        time.sleep(0.05)
    pytest.fail("runtime condition timed out")


@pytest.fixture
def runtime(tmp_path, monkeypatch, request):
    if not shutil.which("tmux") or not shutil.which("cc"):
        pytest.skip("tmux and a C compiler are needed")
    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    source = bin_dir / "harness.c"
    source.write_text(_HARNESS)
    subprocess.run(
        ["cc", str(source), "-o", str(bin_dir / "codex")], check=True, capture_output=True
    )
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    home = tmp_path / "home"
    # Native Codex creates this before arming its watcher; the synthetic CLI must too.
    (home / ".codex").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    if getattr(request, "param", False):
        monkeypatch.delenv("CODEX_HOME", raising=False)
    else:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
        Path(os.environ["CODEX_HOME"]).mkdir()
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    # Exercise SessionStart's real native observation without its automatic scout.
    # This fixture tests the coordinator leaving watcher startup to the resumed lemon;
    # automatic SessionStart startup is covered by the hook/scout tests separately.
    monkeypatch.setenv(
        "TEST_HOOK",
        shlex.join(
            [
                sys.executable,
                "-c",
                "from unittest.mock import patch; from lemonaid.hooks import session_start\n"
                "with patch.object(session_start.codex_scout, 'ensure_for', return_value=False):\n"
                "    session_start.handle('codex')",
            ]
        ),
    )
    monkeypatch.setenv("TEST_SESSION", shared.SESSION)
    monkeypatch.setenv("TEST_STARTED", str(tmp_path / "started"))
    monkeypatch.setenv("TEST_QUEUE", str(tmp_path / "queued"))
    monkeypatch.setenv("TEST_PROMPT", str(tmp_path / "prompt"))
    monkeypatch.setenv("TEST_SELF", str(tmp_path / "self-restart"))
    monkeypatch.setenv(
        "TEST_SELF_COMMAND",
        shlex.join(
            [
                sys.executable,
                "-m",
                "lemonaid",
                "lemon",
                "restart",
                shared.CHANNEL,
                "--force",
                "--json",
            ]
        )
        + " > "
        + shlex.quote(str(tmp_path / "operation.json"))
        + " 2> "
        + shlex.quote(str(tmp_path / "self-stderr")),
    )
    with db.connect() as conn:
        path, lemon_id = shared.setup(conn, tmp_path)
    directory = tempfile.TemporaryDirectory(prefix="restart-runtime-", dir="/tmp")
    socket = str(Path(directory.name) / "tmux")
    try:
        pane.run(
            socket,
            "-f",
            "/dev/null",
            "new-session",
            "-d",
            "-s",
            "test",
            "-c",
            str(tmp_path),
            f"exec {bin_dir / 'codex'} --no-daemon -m gpt-6 -s workspace-write -a on-request",
        )
        _until(lambda: (tmp_path / "started").exists())
        tty = pane.run(socket, "display-message", "-p", "-t", "test:0", "#{pane_tty}")
        target = pane.locate(socket, tty)
        with db.connect() as conn:
            conn.execute(
                "UPDATE notifications SET metadata = json_patch(metadata, ?) WHERE channel = ?",
                (json.dumps({"tmux_socket": socket, "tty": tty}), shared.CHANNEL),
            )
            conn.commit()
        yield path, lemon_id, target
    finally:
        for waiter in registry.mine(shared.CHANNEL):
            stopping.stop(waiter, "test cleanup")
        with contextlib.suppress(ValueError):
            pane.run(socket, "kill-server")
        directory.cleanup()
