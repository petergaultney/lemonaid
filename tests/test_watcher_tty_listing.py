"""The archiver judges every tty from one process listing."""

import os
import subprocess
import sys

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


def test_by_tty_names_macos_device_numbers_from_dev(monkeypatch):
    out = "   ??  /sbin/launchd\n 16/1  -fish\n 16/1  claude --resume abc\n 16/9  closed since\n"
    asked = []
    monkeypatch.setattr(tty_processes.sys, "platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: asked.append(a[0]) or subprocess.CompletedProcess(a, 0, out, ""),
    )
    monkeypatch.setattr(tty_processes, "_terminal_names", lambda: {os.makedev(16, 1): "ttys001"})

    assert tty_processes.by_tty() == {
        "??": ["/sbin/launchd", "closed since"],
        "ttys001": ["-fish", "claude --resume abc"],
    }
    assert asked == [["ps", "-A", "-o", "tdev=,args="]]


def test_by_tty_asks_linux_ps_for_terminal_names(monkeypatch):
    asked = []
    monkeypatch.setattr(tty_processes.sys, "platform", "linux")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: (
            asked.append(a[0]) or subprocess.CompletedProcess(a, 0, "pts/3  vim\n", "")
        ),
    )

    assert tty_processes.by_tty() == {"pts/3": ["vim"]}
    assert asked == [["ps", "-A", "-o", "tty=,args="]]


@pytest.mark.skipif(sys.platform != "darwin", reason="ps -o tdev is macOS's")
def test_device_numbers_name_every_process_as_ps_does():
    def column(name: str) -> dict[str, str]:
        out = subprocess.run(["ps", "-A", "-o", f"pid=,{name}="], capture_output=True, text=True)
        return dict(line.split() for line in out.stdout.splitlines() if line.strip())

    names = tty_processes._terminal_names()
    tdevs, ttys = column("tdev"), column("tty")
    both = tdevs.keys() & ttys.keys()

    assert both
    assert {pid: tty_processes._tty_name(tdevs[pid], names) for pid in both} == {
        pid: ttys[pid] for pid in both
    }
