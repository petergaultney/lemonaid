"""`lemonaid restore tmux` after a real tmux server dies, with stand-in Claude processes.

Each lemon is a stand-in `claude` (see `stand_in/`) that registers through lemonaid's
own SessionStart hook, on a private tmux server whose config sets `base-index 1`. The
server is killed, `restore tmux` rebuilds it, and every check compares lemonaid's
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
from lemonaid.config import load_config
from lemonaid.inbox import db
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.lemon_watchers import watcher
from lemonaid.messages import recipient

_STAND_IN = Path(__file__).parent / "stand_in"
_IDS = {
    name: f"{n:08x}-0000-4000-8000-000000000000"
    for n, name in enumerate(["A", "B", "OLD", "C"], start=1)
}
_WHERE = {"A": "work:1", "B": "work:2", "C": "side:3"}
_BRIEFLESS = "C"  # restored without a prompt, so it says nothing until spoken to

_T = ty.TypeVar("_T")


def _channel(name: str) -> str:
    return f"claude:{_IDS[name][:8]}"


def _wait(what: str, check: abc.Callable[[], _T | None], timeout: float = 30) -> _T:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if found := check():
            return found
        time.sleep(0.1)
    pytest.fail(f"timed out waiting for {what}")


def _tmux(*args: str) -> str:
    return subprocess.run(
        ["tmux", *args], capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()


def _lemonaid(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["lemonaid", *args], capture_output=True, text=True, timeout=120)


class _World(ty.NamedTuple):
    evidence: Path  # each stand-in's `<session id>.json` and `.received`

    def running(self, name: str) -> dict | None:
        """Where lemon *name*'s stand-in says it runs, once it has registered."""
        try:
            found = json.loads((self.evidence / f"{_IDS[name]}.json").read_text())
        except (OSError, ValueError):
            return None

        return found if _alive(found["pid"]) else None

    def start(self, name: str, target: str) -> dict:
        """Start lemon *name* in *target*, with a brief of its own unless it is C."""
        _tmux("send-keys", "-t", target, f"claude --session-id {_IDS[name]}", "Enter")
        running = _wait(f"{name} to start", lambda: self.running(name))
        for verb in (
            ()
            if name == _BRIEFLESS
            else (
                ["new", "--channel", _channel(name), f"Lemon {name}"],
                [
                    "watching",
                    "add",
                    "--channel",
                    _channel(name),
                    f"lemonaid watch doc /tmp/{name}.md",
                ],
            )
        ):
            assert _lemonaid("brief", *verb).returncode == 0, verb
        return running

    def turns(self, name: str) -> int:
        try:
            return len((self.evidence / f"{_IDS[name]}.turns").read_text().splitlines())
        except OSError:
            return 0

    def end_turn(self, name: str) -> None:
        """Have lemon *name* finish a turn, which leaves its row unread."""
        running, before = self.running(name), self.turns(name)
        assert running is not None
        os.kill(running["pid"], signal.SIGUSR1)
        _wait(f"{name} to finish its turn", lambda: self.turns(name) > before)
        row = _row(name)
        assert row is not None and row.is_unread, name

    def received(self, name: str) -> bytes:
        try:
            return (self.evidence / f"{_IDS[name]}.received").read_bytes()
        except OSError:
            return b""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _window(pane: str) -> str:
    return _tmux("display-message", "-p", "-t", pane, "#{session_name}:#{window_index}")


def _row(name: str) -> db.Notification | None:
    with db.connect() as conn:
        return db.get_by_channel(conn, _channel(name), unread_only=False)


@pytest.fixture
def world(tmp_path, monkeypatch) -> abc.Iterator[_World]:
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

    assert _lemonaid("claude", "hooks").returncode == 0
    settings = home / ".claude" / "settings.json"
    hooks = json.loads(settings.read_text())
    for event, command in (("UserPromptSubmit", "submit"), ("Stop", "notify")):
        hooks["hooks"][event] = [
            {"hooks": [{"type": "command", "command": f"lemonaid claude {command}"}]}
        ]
    settings.write_text(json.dumps(hooks))  # the hooks the README has users add
    try:
        yield _World(evidence)
    finally:
        subprocess.run(["tmux", "kill-server"], capture_output=True)
        for found in evidence.glob("*-*.json"):
            with contextlib.suppress(ProcessLookupError, ValueError, OSError):
                os.kill(json.loads(found.read_text())["pid"], signal.SIGKILL)
        shutil.rmtree(short, ignore_errors=True)


def _crash(world: _World) -> None:
    """Build the layout in the module docstring, then kill the tmux server under it."""
    _tmux("new-session", "-d", "-s", "work", "-x", "160", "-y", "48")
    world.start("A", "work:1")
    _tmux("new-window", "-t", "work:2")
    old = world.start("OLD", "work:2")["pid"]
    world.end_turn("OLD")
    os.kill(old, signal.SIGKILL)
    world.start("B", "work:2")
    _tmux("new-session", "-d", "-s", "side")
    _tmux("new-window", "-t", "side:3")
    world.start("C", "side:3")
    world.end_turn("A")
    world.end_turn("C")

    pids = [world.running(name)["pid"] for name in _WHERE]  # type: ignore[index]
    _tmux("kill-server")
    _wait("the lemons to die with their server", lambda: not any(map(_alive, pids)))

    # tmux dates a session to the second. Restore in a later second than the lemons
    # were last heard from, as any real restore is.
    with db.connect() as conn:
        heard = max(row.created_at for row in db.get_active(conn))
    time.sleep(max(0.0, math.floor(heard) + 1 - time.time()))


def _restored(world: _World, wait: int = 0) -> dict:
    before = {name: (world.running(name) or {}).get("pid") for name in _WHERE}
    result = _lemonaid("restore", "tmux", "--wait", str(wait), "--json")
    for name in _WHERE:
        _wait(
            f"{name} to be resumed",
            lambda name=name: (found := world.running(name)) and found["pid"] != before[name],
        )
    return json.loads(result.stdout)


def _attached_client(session: str) -> tuple[str, abc.Callable[[], None]]:
    """A tmux client attached to *session* on a pty of its own, and how to detach it."""
    master, slave = os.openpty()
    env = {**os.environ, "TERM": "xterm-256color"}
    process = subprocess.Popen(
        ["tmux", "attach-session", "-t", session], stdin=slave, stdout=slave, stderr=slave, env=env
    )
    name = _wait(
        "the client to attach",
        lambda: next(
            (
                line.split("|")[0]
                for line in _tmux(
                    "list-clients", "-F", "#{client_name}|#{session_name}"
                ).splitlines()
                if line.endswith(f"|{session}")
            ),
            None,
        ),
    )

    def detach() -> None:
        subprocess.run(["tmux", "detach-client", "-t", name], capture_output=True)
        os.close(master)
        os.close(slave)
        process.wait(timeout=5)

    return name, detach


def test_every_lemon_comes_back_in_its_own_window_and_its_row_points_there(world):
    _crash(world)

    restored = _restored(world, wait=30)

    assert restored["restored"] == ["work", "side"]
    assert {r["channel"]: r["outcome"] for r in restored["lemons"]} == {
        _channel("A"): "working",
        _channel("B"): "working",
        _channel("C"): "no brief",
        _channel("OLD"): "not restored",
    }
    for name, where in _WHERE.items():
        running = world.running(name)
        assert running is not None
        assert _window(running["pane"]) == where, name
        assert (f"/tmp/{name}.md" in running["prompt"]) != (name == _BRIEFLESS), name
        row = _row(name)
        assert row is not None and not row.is_archived, name
        assert row.metadata["tty"] == running["tty"], name
        assert f"{row.metadata['tmux_session']}:{row.metadata['tmux_window']}" == where, name


def test_go_jumps_to_each_restored_lemon_including_into_a_renamed_session(world):
    _crash(world)
    _restored(world)
    _tmux("rename-session", "-t", "side", "elsewhere")
    client, detach = _attached_client("elsewhere")
    try:
        for name in _WHERE:
            result = _lemonaid("go", _channel(name), "--client", client)
            assert result.returncode == 0, (name, result.stderr)
            assert _tmux("display-message", "-p", "-c", client, "#{pane_id}") == (
                world.running(name) or {}
            ).get("pane"), name
    finally:
        detach()


def _on_b_tty(world: _World) -> None:
    """Record OLD in the pane B runs in now.

    That is where OLD's row ends up when the restored server hands B the tty OLD had, as
    it usually does, and the watcher records the pane on that tty for every row there.
    Make it so, since that is the case being checked.
    """
    old, b = _row("OLD"), _row("B")
    assert old is not None and b is not None
    location = {
        key: b.metadata[key]
        for key in (
            "tty",
            "tmux_session",
            "tmux_window",
            "tmux_session_order",
            "tmux_pane_identity",
        )
    }
    with db.connect() as conn:
        conn.execute(
            "UPDATE notifications SET metadata = ? WHERE channel = ?",
            (json.dumps({**old.metadata, **location}), _channel("OLD")),
        )
        conn.commit()


def test_restoring_again_starts_nothing_and_forgets_a_pane_another_lemon_now_runs(world):
    _crash(world)
    _restored(world)
    _on_b_tty(world)

    again = _lemonaid("restore", "tmux", "--wait", "0", "--json")
    once_more = _lemonaid("restore", "tmux", "--wait", "0", "--json")

    first = json.loads(again.stdout)
    assert first["restored"] == []
    assert first["skipped"] == ["work", "side"]
    assert [(r["channel"], r["state"]) for r in first["relinked"]] == [
        (_channel("OLD"), "forgotten")
    ]
    assert json.loads(once_more.stdout)["relinked"] == []
    forgotten = _row("OLD")
    assert forgotten is not None and "tty" not in forgotten.metadata
    for name in _WHERE:
        row = _row(name)
        assert row is not None and row.metadata["tty"] == (world.running(name) or {}).get("tty")


def test_the_watcher_archives_the_row_whose_tty_another_lemon_now_runs(world):
    _crash(world)
    _restored(world)
    _on_b_tty(world)

    watcher_hooks.start(load_config(), brief_cards.BriefCache(), lambda channels: None)
    try:
        _wait("the watcher to archive OLD", lambda: (row := _row("OLD")) and row.is_archived)
        time.sleep(3)  # another pass, in case it archives B next
    finally:
        watcher.stop_unified_watcher()

    for name in _WHERE:
        row = _row(name)
        assert row is not None and not row.is_archived, name


def test_telling_a_dead_lemon_never_types_into_the_lemon_on_its_old_tty(world):
    _crash(world)
    _restored(world)
    _on_b_tty(world)
    b = world.running("B")
    old = _row("OLD")
    assert b is not None and old is not None
    assert recipient.harness_alive(old)  # by its tty alone, OLD would look alive

    told = _lemonaid("tell", "--channel", "claude:tester", _channel("OLD"), "read your inbox")

    assert "inbox" not in _tmux("capture-pane", "-p", "-t", b["pane"]), told.stderr
    assert world.received("B") == b""
    resumed = _wait("OLD to be resumed", lambda: world.running("OLD"))
    assert resumed["pane"] != b["pane"]
    assert "inbox" in resumed["prompt"]
    assert world.running("B") == b
