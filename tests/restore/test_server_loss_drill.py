"""The restore drill: kill a tmux server full of lemons and check what comes back.

Each test is one scenario from the restart design, run on the private server and
stand-in lemons of `tmux_world`.
"""

import contextlib
import json
import os
import signal
import subprocess
import time
from collections import abc

from lemonaid.config import load_config
from lemonaid.inbox import db, ended
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.lemon_watchers import watcher

from .tmux_world import IDS, WHERE, channel, crash, inbox_row, lemonaid, restore_all, tmux, wait


@contextlib.contextmanager
def _inbox() -> abc.Iterator[None]:
    """The inbox's watcher, running until the block ends."""
    watcher_hooks.start(load_config(), brief_cards.BriefCache(), lambda channels: None)
    try:
        yield
    finally:
        watcher.stop_unified_watcher()


def _cause(name: str) -> str:
    found = inbox_row(name)
    assert found is not None, name
    return ended.cause(found.metadata)


def _restore() -> dict:
    return json.loads(lemonaid("restore", "tmux", "--wait", "0", "--json").stdout)


def test_the_inbox_started_on_a_new_server_before_restore_keeps_every_lost_lemon(world):
    crash(world)
    tmux("new-session", "-d", "-s", "fresh")  # the server a person starts first

    with _inbox():
        wait("every lemon to be marked lost", lambda: all(_cause(n) for n in WHERE))
        time.sleep(3)  # more passes, in case one archives them

    for name in WHERE:
        found = inbox_row(name)
        assert found is not None and not found.is_archived, name
        assert _cause(name) == ended.SERVER_LOST, name

    restore_all(world)
    for name in WHERE:
        assert _cause(name) == "", name  # heard from again: lost no longer


def test_restoring_twice_starts_nothing_the_second_time(world):
    crash(world)
    restore_all(world)
    pids = {name: (world.running(name) or {}).get("pid") for name in WHERE}

    again = _restore()

    assert again["restored"] == []
    assert {name: (world.running(name) or {}).get("pid") for name in WHERE} == pids


def test_a_session_killed_on_a_living_server_is_closed_not_lost(world):
    crash(world)
    restore_all(world)
    c = world.running("C")
    assert c is not None
    tmux("kill-session", "-t", "side")
    wait("C to die with its session", lambda: world.running("C") is None)

    with _inbox():
        wait("C to be archived", lambda: (row := inbox_row("C")) and row.is_archived)

    assert _cause("C") == ended.PANE_CLOSED
    assert _restore()["restored"] == []
    assert world.running("C") is None


def test_a_lemon_that_ended_itself_stays_ended(world):
    crash(world)
    restore_all(world)
    a = world.running("A")
    assert a is not None
    subprocess.run(
        ["lemonaid", "claude", "session-end"],
        input=json.dumps({"session_id": IDS["A"], "reason": "prompt_input_exit"}),
        text=True,
        check=True,
    )
    os.kill(a["pid"], signal.SIGKILL)

    with _inbox():
        wait("A to be archived", lambda: (row := inbox_row("A")) and row.is_archived)
    assert _cause("A") == ended.USER_EXIT

    tmux("kill-server")
    assert channel("A") not in {r["channel"] for r in _restore()["lemons"]}
    assert world.running("A") is None


def test_dismissed_lemons_are_archived_and_not_restored(world):
    crash(world)

    dismissed = lemonaid("restore", "dismiss", channel("C"))

    assert dismissed.returncode == 0, dismissed.stderr
    assert _cause("C") == ended.DISMISSED
    found = inbox_row("C")
    assert found is not None and found.is_archived
    restored = _restore()
    assert channel("C") not in {r["channel"] for r in restored["lemons"]}
    assert restored["restored"] == ["work"]


def test_dismissing_all_leaves_nothing_to_restore(world):
    crash(world)

    assert lemonaid("restore", "dismiss", "--all").returncode == 0

    with db.connect() as conn:
        assert not [row for row in db.get_active(conn) if row.channel.startswith("claude:")]
    assert _restore()["restored"] == []


def test_a_channel_cleared_before_the_loss_is_replaced_and_only_its_successor_restored(world):
    crash(world)  # OLD ran in B's window first
    subprocess.run(
        ["lemonaid", "claude", "session-end"],
        input=json.dumps({"session_id": IDS["OLD"], "reason": "clear"}),
        text=True,
        check=True,
    )

    restored = restore_all(world)

    assert _cause("OLD") == ended.REPLACED
    found = inbox_row("OLD")
    assert found is not None and found.is_archived
    assert channel("OLD") not in {r["channel"] for r in restored["lemons"]}
