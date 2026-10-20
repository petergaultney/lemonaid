"""The archiver judges every tty from one process listing."""

import subprocess

import pytest

from lemonaid.lemon_watchers import tty_processes, watcher
from lemonaid.tmux import navigation


def _row(channel: str, tty: str):
    return (channel, "sid", "/work/feat", 100.0, False, tty, "msg", "tmux")


def test_one_listing_answers_for_every_tty_without_asking_about_each(monkeypatch):
    """A tty with no device is kept, as `ps -t` could not say whether anything ran there."""

    def per_tty(*args):
        raise AssertionError("asked ps about one tty")

    monkeypatch.setattr(watcher, "is_process_running_on_tty", per_tty)
    monkeypatch.setattr(watcher, "tty_device_exists", lambda name: name != "ttys005")
    archived: list[str] = []
    active = [
        _row("claude:alive", "/dev/ttys001"),
        _row("codex:alive", "/dev/ttys002"),
        _row("claude:exited", "/dev/ttys003"),
        _row("codex:quiet", "/dev/ttys004"),
        _row("claude:no-device", "/dev/ttys005"),
    ]
    panes = {None: {tty: navigation.PaneLocation("s", "0") for *_, tty, _, _ in active}}
    listing = {
        "ttys001": ["-fish", "claude --resume abc"],
        "ttys002": ["node /opt/bin/codex --no-daemon"],
        "ttys003": ["-fish"],
    }

    watcher._archive_stale_sessions(active, archived.append, {}, panes, tty_processes=listing)

    assert archived == ["claude:exited", "codex:quiet"]


def test_by_tty_groups_args_lines_under_their_terminal(monkeypatch):
    out = "??       /sbin/launchd\nttys001  -fish\nttys001  claude --resume abc\npts/3    vim x\n"
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, out, "")
    )

    assert tty_processes.by_tty() == {
        "??": ["/sbin/launchd"],
        "ttys001": ["-fish", "claude --resume abc"],
        "pts/3": ["vim x"],
    }


@pytest.mark.parametrize(
    "run",
    [
        lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "ps: boom"),
        lambda *a, **kw: (_ for _ in ()).throw(OSError("no ps")),
    ],
)
def test_by_tty_says_nothing_when_ps_cannot(monkeypatch, run):
    monkeypatch.setattr(subprocess, "run", run)

    assert tty_processes.by_tty() is None
