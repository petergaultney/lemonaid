"""`watch restart <lemon>` stops the waiters a lemon started by hand, without the lemon's help."""

import argparse
import subprocess
from pathlib import Path

import pytest

from lemonaid.brief import attached, identity, waiters
from lemonaid.inbox import db
from lemonaid.watch import lemon_restart, registry, restart_cli, wait_state

from .test_watch_stop import _briefed, _registered, _start


def _restart(capsys, *argv: str) -> str:
    parser = argparse.ArgumentParser()
    restart_cli.add_parser(parser.add_subparsers())
    assert restart_cli.run(parser.parse_args(["restart", "--wait", "20", *argv])) == 0
    return capsys.readouterr().out


def _watcher(channel: str, lemon_id: str, tmp_path: Path) -> subprocess.Popen:
    process = _start(channel, tmp_path, "watch", "--self")
    for _ in range(600):
        if wait_state.is_armed(lemon_id):
            return process

        subprocess.run(["sleep", "0.05"])
    raise AssertionError(f"no watcher for {lemon_id}")


def _stop_all(*processes: subprocess.Popen) -> None:
    for process in processes:
        process.kill()
        process.wait()


def test_a_hand_started_waiter_its_watcher_follows_is_stopped(capsys, tmp_path):
    watched = tmp_path / "watched.md"
    watched.write_text("one\n")
    brief = _briefed("claude:mine", "mine")
    _briefed("claude:other", "other")
    mine = identity.from_path(brief)
    by_hand = _start("claude:mine", tmp_path, "watch", "file", "--wait", str(watched))
    others = _start("claude:other", tmp_path, "watch", "file", "--wait", str(watched))
    assert _registered("claude:mine", "file") and _registered("claude:other", "file")
    watcher = _watcher("claude:mine", mine, tmp_path)
    try:
        listed = waiters.commands(brief.read_text())

        out = _restart(capsys, mine)

        _, err = by_hand.communicate(timeout=30)
        assert by_hand.returncode == 143
        assert "stopped by SIGTERM from `lemonaid watch restart` (pid" in err
        assert "Your watcher follows it from your brief's `## Watching`; don't rearm it." in err
        assert f"pid {by_hand.pid}; its watcher follows it" in out
        assert waiters.commands(brief.read_text()) == listed
        assert others.poll() is None and watcher.poll() is None
    finally:
        _stop_all(by_hand, others, watcher)


def test_without_a_watcher_a_hand_started_waiter_keeps_running(capsys, tmp_path):
    watched = tmp_path / "watched.md"
    watched.write_text("one\n")
    brief = _briefed("claude:mine", "mine")
    mine = identity.from_path(brief)
    by_hand = _start("claude:mine", tmp_path, "watch", "file", "--wait", str(watched))
    try:
        assert _registered("claude:mine", "file")

        out = _restart(capsys, mine, "--wait", "0")

        assert f"{mine}: could not start a push scout (no running Claude session" in out
        assert f"pid {by_hand.pid}, running: no watcher runs" in out
        assert by_hand.poll() is None
    finally:
        _stop_all(by_hand)


def test_a_waiter_started_before_its_lemon_moved_session_is_still_its_own(capsys, tmp_path):
    watched = tmp_path / "watched.md"
    watched.write_text("one\n")
    brief = _briefed("claude:old", "mine")
    by_hand = _start("claude:old", tmp_path, "watch", "file", "--wait", str(watched))
    assert _registered("claude:old", "file")
    with db.connect() as conn:
        db.add(conn, "claude:new", "")
        attached.attach(conn, "claude:new", Path(brief))  # as a /clear moves it
    watcher = _watcher("claude:new", identity.from_path(brief), tmp_path)
    try:
        out = _restart(capsys, "claude:new")

        assert by_hand.wait(timeout=30) == 143
        assert f"pid {by_hand.pid}; its watcher follows it" in out
    finally:
        _stop_all(by_hand, watcher)


_BRIEF = """\
# mine

Brief-ID: mine.Ant

## PRs

| Work | PR | Review |
|---|---|---|
| A change | [widgets#7](https://github.com/acme/widgets/pull/7) | |

## Watching

- `lemonaid watch file --wait /abs/a.txt`
- `lemonaid watch file --wait rel.txt`
- `lemonaid watch pr --wait 583 --me Test`
- `lemonaid watch doc --watch-list /abs/list.json --me Test`
- `lemonaid watch slack https://acme.slack.com/archives/C0123ABCD`
"""


def _waiter(kind: str, *targets: str) -> registry.Waiter:
    return registry.Waiter(1, "claude:mine", kind, targets, "", "/")


@pytest.mark.parametrize(
    "waiter, follows",
    [
        (_waiter("file", "/abs/a.txt"), True),
        (_waiter("file", "/watcher/rel.txt"), True),
        (_waiter("file", "/elsewhere/rel.txt"), False),  # started in another directory
        (_waiter("pr", "AcMe/Widgets#7"), True),  # from the PRs table
        (_waiter("pr", "acme/widgets#583"), False),  # its listed command has no repo
        (_waiter("doc", "/abs/list.json"), False),  # the reader takes no watch list
        (_waiter("slack", "C0123ABCD"), True),
        (_waiter("mailbox", "mine.Ant"), True),
    ],
)
def test_the_watcher_follows_only_what_it_reads_from_the_brief(waiter, follows):
    assert lemon_restart.followed(_BRIEF, "mine.Ant", Path("/watcher"))(waiter) is follows
