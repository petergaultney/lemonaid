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


def _listing_with(monkeypatch, pid: int) -> list[list[str]]:
    asked: list[list[str]] = []
    out = f"{pid}  pts/3  claude --resume abc\n1  ??  /sbin/launchd\n"
    monkeypatch.setattr(tty_processes.sys, "platform", "linux")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: asked.append(a[0]) or subprocess.CompletedProcess(a, 0, out, ""),
    )
    return asked


def _harnesses():
    return tty_processes.Reused(lambda args: watcher.is_harness(args, "claude"))


def test_a_listing_is_reused_while_its_harnesses_run(monkeypatch):
    asked = _listing_with(monkeypatch, os.getpid())
    reused = _harnesses()

    first = reused.by_tty(False, 100.0)
    again = reused.by_tty(False, 110.0)

    assert first == again == {"pts/3": ["claude --resume abc"], "??": ["/sbin/launchd"]}
    assert asked == [["ps", "-A", "-o", "pid=,tty=,args="]]


def test_a_listing_is_taken_again_once_a_harness_in_it_exits(monkeypatch):
    exited = subprocess.Popen([sys.executable, "-c", ""])
    exited.wait()
    asked = _listing_with(monkeypatch, exited.pid)
    reused = _harnesses()

    reused.by_tty(False, 100.0)
    reused.by_tty(False, 101.0)

    assert len(asked) == 2


@pytest.mark.parametrize(("fresh", "now"), [(True, 101.0), (False, 130.0)])
def test_a_listing_is_taken_again_when_asked_or_once_it_is_old(monkeypatch, fresh, now):
    asked = _listing_with(monkeypatch, os.getpid())
    reused = _harnesses()

    reused.by_tty(False, 100.0)
    reused.by_tty(fresh, now)

    assert len(asked) == 2


_RESUMED = ("claude:resume", "resume", "/tmp", 50.0, False, "/dev/ttys001", "msg", "tmux")
_PANES = {None: {"/dev/ttys001": navigation.PaneLocation("session", "0")}}


def _judge(monkeypatch, stale, fresh, protected=()):
    monkeypatch.setattr(watcher, "tty_device_exists", lambda name: True)
    relisted: list[bool] = []
    archived: list[str] = []
    watcher._archive_stale_sessions(
        [_RESUMED],
        archived.append,
        {},
        _PANES,
        protected_channels=set(protected),
        tty_processes=stale,
        relist=lambda: relisted.append(True) or fresh,
    )
    return archived, relisted


def test_an_absence_in_a_stale_listing_is_confirmed_before_archiving(monkeypatch):
    archived, relisted = _judge(
        monkeypatch, {"ttys001": ["-zsh"]}, {"ttys001": ["-zsh", "claude --resume resume"]}
    )

    assert archived == []
    assert relisted == [True]


def test_an_absence_confirmed_by_a_fresh_listing_archives(monkeypatch):
    archived, _ = _judge(monkeypatch, {"ttys001": ["-zsh"]}, {"ttys001": ["-zsh"]})

    assert archived == ["claude:resume"]


def test_a_protected_row_never_costs_a_fresh_listing(monkeypatch):
    archived, relisted = _judge(
        monkeypatch, {"ttys001": ["-zsh"]}, {"ttys001": ["-zsh"]}, protected=["claude:resume"]
    )

    assert archived == []
    assert relisted == []
