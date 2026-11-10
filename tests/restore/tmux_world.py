"""`lemonaid restore` after a real tmux server dies, with stand-in Claude processes.

Each lemon is a stand-in `claude` (see `stand_in/`) that registers through lemonaid's
own SessionStart hook, on a private tmux server whose config sets `base-index 1`. The
server is killed, `restore` rebuilds it, and every check compares lemonaid's
answer with where each stand-in says it really runs.

The layout, before the crash:

    work:1  lemon A, idle after a turn the user hasn't read
    work:2  lemon B, mid-turn; lemon OLD ran here first, finished a turn the user never
            read, and crashed, so its unread row names this window too
    side:1  a shell
    side:3  lemon C, idle after a turn the user hasn't read; it has no brief
"""

import contextlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import typing as ty
from collections import abc
from pathlib import Path

import pytest

from lemonaid.claude import session_socket
from lemonaid.inbox import db

_STAND_IN = Path(__file__).parent / "stand_in"
IDS = {
    name: f"{n:08x}-0000-4000-8000-000000000000"
    for n, name in enumerate(["A", "B", "OLD", "C"], start=1)
}
WHERE = {"A": "work:1", "B": "work:2", "C": "side:3"}
BRIEFLESS = "C"  # restored without a prompt, so it says nothing until spoken to

_T = ty.TypeVar("_T")


def channel(name: str) -> str:
    return f"claude:{IDS[name][:8]}"


def wait(what: str, check: abc.Callable[[], _T | None], timeout: float = 30) -> _T:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if found := check():
            return found
        time.sleep(0.1)
    pytest.fail(f"timed out waiting for {what}")


def tmux(*args: str) -> str:
    return subprocess.run(
        ["tmux", *args], capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()


def lemonaid(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["lemonaid", *args], capture_output=True, text=True, timeout=120)


class World(ty.NamedTuple):
    evidence: Path  # each stand-in's `<session id>.json` and `.received`

    def running(self, name: str) -> dict | None:
        """Where lemon *name*'s stand-in says it runs, once it has registered."""
        try:
            found = json.loads((self.evidence / f"{IDS[name]}.json").read_text())
        except (OSError, ValueError):
            return None

        return found if alive(found["pid"]) else None

    def start(self, name: str, target: str) -> dict:
        """Start lemon *name* in *target*, with a brief of its own unless it is C."""
        tmux("send-keys", "-t", target, f"claude --session-id {IDS[name]}", "Enter")
        running = wait(f"{name} to start", lambda: self.running(name))
        for verb in (
            ()
            if name == BRIEFLESS
            else (
                ["new", "--channel", channel(name), f"Lemon {name}"],
                [
                    "watching",
                    "add",
                    "--channel",
                    channel(name),
                    f"lemonaid watch doc /tmp/{name}.md",
                ],
            )
        ):
            assert lemonaid("brief", *verb).returncode == 0, verb
        return running

    def turns(self, name: str) -> int:
        try:
            return len((self.evidence / f"{IDS[name]}.turns").read_text().splitlines())
        except OSError:
            return 0

    def end_turn(self, name: str) -> None:
        """Have lemon *name* finish a turn, which leaves its row unread."""
        running, before = self.running(name), self.turns(name)
        assert running is not None
        os.kill(running["pid"], signal.SIGUSR1)
        wait(f"{name} to finish its turn", lambda: self.turns(name) > before)
        row = inbox_row(name)
        assert row is not None and row.is_unread, name

    def typed(self, name: str) -> str:
        """What was typed into lemon *name*'s composer."""
        try:
            return (self.evidence / f"{IDS[name]}.typed").read_text()
        except OSError:
            return ""

    def received(self, name: str) -> bytes:
        try:
            return (self.evidence / f"{IDS[name]}.received").read_bytes()
        except OSError:
            return b""


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def window(pane: str) -> str:
    return tmux("display-message", "-p", "-t", pane, "#{session_name}:#{window_index}")


def inbox_row(name: str) -> db.Notification | None:
    with db.connect() as conn:
        return db.get_by_channel(conn, channel(name), unread_only=False)


@pytest.fixture
def world(tmp_path, monkeypatch) -> abc.Iterator[World]:
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")

    # Unix sockets need a short path: tmux's own and each stand-in's.
    short = Path(tempfile.mkdtemp(prefix="lma-e2e-", dir="/tmp"))
    evidence = short / "ev"
    evidence.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    # The panes run a non-login /bin/sh, so no shell config, the user's or the system's,
    # can put the real claude back ahead of the stand-in on PATH.
    (home / ".tmux.conf").write_text(
        "set -g default-shell /bin/sh\nset -g default-command /bin/sh\nset -g base-index 1\n"
    )
    python = short / "bin" / "claude"
    python.parent.mkdir()
    python.symlink_to(os.path.realpath(sys.executable))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))  # tmux reads a config there too
    monkeypatch.setenv("SHELL", "/bin/sh")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "lemonaid.db"))
    monkeypatch.setenv("TMUX_TMPDIR", str(short))
    monkeypatch.setenv("STAND_IN_PYTHON", str(python))
    monkeypatch.setenv("STAND_IN_DIR", str(evidence))
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [
                str(_STAND_IN),
                str(Path(sys.executable).parent),
                str(Path(shutil.which("tmux") or "/usr/bin/tmux").parent),
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ]
        ),
    )
    monkeypatch.setattr(session_socket, "claude_dir", lambda: home / ".claude")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)

    assert lemonaid("claude", "hooks").returncode == 0
    settings = home / ".claude" / "settings.json"
    hooks = json.loads(settings.read_text())
    for event, command in (("UserPromptSubmit", "submit"), ("Stop", "notify")):
        hooks["hooks"][event] = [
            {"hooks": [{"type": "command", "command": f"lemonaid claude {command}"}]}
        ]
    settings.write_text(json.dumps(hooks))  # the hooks the README has users add
    try:
        yield World(evidence)
    finally:
        subprocess.run(["tmux", "kill-server"], capture_output=True)
        for found in evidence.glob("*-*.json"):
            with contextlib.suppress(ProcessLookupError, ValueError, OSError):
                os.kill(json.loads(found.read_text())["pid"], signal.SIGKILL)
        shutil.rmtree(short, ignore_errors=True)


def crash(world: World) -> None:
    """Build the layout in the module docstring, then kill the tmux server under it."""
    tmux("new-session", "-d", "-s", "work", "-x", "160", "-y", "48")
    world.start("A", "work:1")
    tmux("new-window", "-t", "work:2")
    old = world.start("OLD", "work:2")["pid"]
    world.end_turn("OLD")
    os.kill(old, signal.SIGKILL)
    world.start("B", "work:2")
    tmux("new-session", "-d", "-s", "side")
    tmux("new-window", "-t", "side:3")
    world.start("C", "side:3")
    world.end_turn("A")
    world.end_turn("C")

    pids = [world.running(name)["pid"] for name in WHERE]  # type: ignore[index]
    tmux("kill-server")
    wait("the lemons to die with their server", lambda: not any(map(alive, pids)))

    # tmux dates a session to the second. Restore in a later second than the lemons
    # were last heard from, as any real restore is.
    with db.connect() as conn:
        heard = max(row.created_at for row in db.get_active(conn))
    time.sleep(max(0.0, math.floor(heard) + 1 - time.time()))


def restore_all(world: World, seconds: int = 0) -> dict:
    before = {name: (world.running(name) or {}).get("pid") for name in WHERE}
    result = lemonaid("restore", "--wait", str(seconds), "--json")
    for name in WHERE:
        wait(
            f"{name} to be resumed",
            lambda name=name: (found := world.running(name)) and found["pid"] != before[name],
        )
    return json.loads(result.stdout)
