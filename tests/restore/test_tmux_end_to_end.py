"""`lemonaid restore` after a real tmux server dies, with stand-in Claude processes.

The world and its layout before the crash are in `tmux_world`.
"""

import json
import os
import signal
import subprocess
import time
from collections import abc

from lemonaid.brief import attached, identity
from lemonaid.config import load_config
from lemonaid.inbox import db
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.lemon_watchers import watcher
from lemonaid.messages import recipient
from lemonaid.watch import wait_state

from .tmux_world import (
    WHERE,
    World,
    channel,
    crash,
    inbox_row,
    lemonaid,
    restore_all,
    tmux,
    wait,
    window,
)


def _attached_client(session: str) -> tuple[str, abc.Callable[[], None]]:
    """A tmux client attached to *session* on a pty of its own, and how to detach it."""
    master, slave = os.openpty()
    env = {**os.environ, "TERM": "xterm-256color"}
    process = subprocess.Popen(
        ["tmux", "attach-session", "-t", session], stdin=slave, stdout=slave, stderr=slave, env=env
    )
    name = wait(
        "the client to attach",
        lambda: next(
            (
                line.split("|")[0]
                for line in tmux(
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
    crash(world)

    restored = restore_all(world, seconds=30)

    assert sorted(restored["restored"]) == sorted(channel(name) for name in [*WHERE, "OLD"])
    assert {r["channel"]: r["outcome"] for r in restored["lemons"]} == {
        channel("A"): "subscribed",  # its push scout runs, so it needs no prompt
        channel("B"): "subscribed",
        channel("C"): "no brief",
        channel("OLD"): "subscribed",
    }
    for name, where in {**WHERE, "OLD": "work:3"}.items():  # B was heard from last in work:2
        running = world.running(name)
        assert running is not None
        assert window(running["pane"]) == where, name
        assert world.typed(name) == "", name
        row = inbox_row(name)
        assert row is not None and not row.is_archived, name
        assert row.metadata["tty"] == running["tty"], name
        assert f"{row.metadata['tmux_session']}:{row.metadata['tmux_window']}" == where, name


def test_go_jumps_to_each_restored_lemon_including_into_a_renamed_session(world):
    crash(world)
    restore_all(world)
    tmux("rename-session", "-t", "side", "elsewhere")
    client, detach = _attached_client("elsewhere")
    try:
        for name in WHERE:
            result = lemonaid("go", channel(name), "--client", client)
            assert result.returncode == 0, (name, result.stderr)
            assert tmux("display-message", "-p", "-c", client, "#{pane_id}") == (
                world.running(name) or {}
            ).get("pane"), name
    finally:
        detach()


def _on_b_tty(world: World) -> None:
    """Stop OLD and record it in the pane B runs in now.

    That is where a dead lemon's row ends up when the restored server hands B the tty it
    had, as it usually does, and the watcher records the pane on that tty for every row
    there. Make it so, since that is the case being checked.
    """
    pid = (world.running("OLD") or {}).get("pid")
    if pid:
        os.kill(pid, signal.SIGKILL)
        wait("OLD to die", lambda: world.running("OLD") is None)
        with db.connect() as conn:
            brief = attached.by_channel(conn, [channel("OLD")])[channel("OLD")]
        lemon_id = identity.read(brief.read_text())
        # A scout pushing into a dead session counts as listening until it notices.
        wait("OLD's scout to stop", lambda: not wait_state.is_armed(lemon_id))
    old, b = inbox_row("OLD"), inbox_row("B")
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
            (json.dumps({**old.metadata, **location}), channel("OLD")),
        )
        conn.commit()


def test_restoring_again_starts_nothing_and_forgets_a_pane_another_lemon_now_runs(world):
    crash(world)
    restore_all(world)
    _on_b_tty(world)

    again = lemonaid("restore", "--wait", "0", "--json")
    once_more = lemonaid("restore", "--wait", "0", "--json")

    first = json.loads(again.stdout)
    assert first["restored"] == []
    assert [(r["channel"], r["state"]) for r in first["relinked"]] == [
        (channel("OLD"), "forgotten")
    ]
    assert json.loads(once_more.stdout)["relinked"] == []
    forgotten = inbox_row("OLD")
    assert forgotten is not None and "tty" not in forgotten.metadata
    for name in WHERE:
        row = inbox_row(name)
        assert row is not None and row.metadata["tty"] == (world.running(name) or {}).get("tty")


def test_the_watcher_archives_the_row_whose_tty_another_lemon_now_runs(world):
    crash(world)
    restore_all(world)
    _on_b_tty(world)

    watcher_hooks.start(load_config(), brief_cards.BriefCache(), lambda channels: None)
    try:
        wait("the watcher to archive OLD", lambda: (row := inbox_row("OLD")) and row.is_archived)
        time.sleep(3)  # another pass, in case it archives B next
    finally:
        watcher.stop_unified_watcher()

    for name in WHERE:
        row = inbox_row(name)
        assert row is not None and not row.is_archived, name


def test_telling_a_dead_lemon_never_types_into_the_lemon_on_its_old_tty(world):
    crash(world)
    restore_all(world)
    _on_b_tty(world)
    b = world.running("B")
    old = inbox_row("OLD")
    assert b is not None and old is not None
    assert recipient.harness_alive(old)  # by its tty alone, OLD would look alive

    told = lemonaid("tell", "--channel", "claude:tester", channel("OLD"), "read your mailbox")

    assert "mailbox" not in tmux("capture-pane", "-p", "-t", b["pane"]), told.stderr
    assert b"read your mailbox" not in world.received("B")
    resumed = wait("OLD to be resumed", lambda: world.running("OLD"))
    assert resumed["pane"] != b["pane"]
    assert "mailbox" in resumed["prompt"]
    assert world.running("B") == b
