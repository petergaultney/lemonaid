"""`lemonaid restore tmux` pointing each restored lemon's row at its new pane."""

import argparse

import pytest

from lemonaid.inbox import db
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.lemon_watchers import watcher
from lemonaid.restore import cli, report
from lemonaid.tmux import navigation
from lemonaid.tmux import restore as tmux_restore

# Two lemons in window 1 of two sessions, as restore commonly rebuilds them.
LEMONS = {"claude:main": "main", "claude:work": "work"}
# Their panes on the server that died.
DEAD_TTYS = {"claude:main": "/dev/ttys901", "claude:work": "/dev/ttys903"}
NEW_PANES = {
    "/dev/ttys902": navigation.PaneLocation("main", "1", (1000, 900, 3)),
    "/dev/ttys904": navigation.PaneLocation("work", "1", (1001, 900, 4)),
}


def _lemons_from_the_dead_server() -> None:
    with db.connect() as conn:
        for channel, session in LEMONS.items():
            db.add(
                conn,
                channel,
                "waiting",
                metadata={
                    "tty": DEAD_TTYS[channel],
                    "cwd": "/tmp",
                    "tmux_session": session,
                    "tmux_window": "1",
                    "tmux_socket": "/tmp/tmux-dead/default",
                },
                upsert=False,
                switch_source="tmux",
            )


def _restore(monkeypatch, panes: dict[str, navigation.PaneLocation] | None) -> None:
    """Run `restore tmux` as if tmux put each lemon in window 1 and then listed *panes*."""
    monkeypatch.setattr(
        cli.tmux_restore,
        "plan_restore",
        lambda *_: [
            tmux_restore.SessionPlan(
                session,
                [tmux_restore.Window(1, "/tmp", "claude", {}, channel, channel, report.NO_BRIEF)],
            )
            for channel, session in LEMONS.items()
        ],
    )
    monkeypatch.setattr(
        cli.tmux_restore,
        "restore",
        lambda plans: tmux_restore.Restored(
            list(LEMONS.values()),
            [],
            [
                report.Placed(channel, channel, f"{session}:1", report.NO_BRIEF)
                for channel, session in LEMONS.items()
            ],
            [],
        ),
    )
    monkeypatch.setattr(navigation, "locations_by_tty", lambda socket=None: panes)
    cli.cmd_tmux(argparse.Namespace(dry_run=False, wait=0, json=True))


def _rows() -> dict[str, db.Notification]:
    with db.connect() as conn:
        return {n.channel: n for n in db.get_active(conn) if n.channel in LEMONS}


def test_the_watcher_keeps_restored_lemons_in_their_new_panes(monkeypatch):
    _lemons_from_the_dead_server()
    _restore(monkeypatch, NEW_PANES)

    rows = _rows()
    sockets = watcher_hooks.recorded_sockets()
    active = [
        (channel, "", "/tmp", n.created_at, True, n.metadata["tty"], "", "tmux")
        for channel, n in rows.items()
    ]
    archived = watcher._archive_stale_sessions(
        active,
        lambda channel: None,
        sockets,
        {socket: NEW_PANES for socket in sockets.values()},
        session_orders=watcher_hooks.recorded_tmux_session_orders(),
        tty_processes={tty.removeprefix("/dev/"): ["claude"] for tty in NEW_PANES},
    )

    assert archived == set()
    assert {
        channel: (n.metadata["tty"], n.metadata["tmux_session"], n.metadata["tmux_socket"])
        for channel, n in rows.items()
    } == {
        "claude:main": ("/dev/ttys902", "main", navigation.current_socket()),
        "claude:work": ("/dev/ttys904", "work", navigation.current_socket()),
    }


@pytest.mark.parametrize(
    "panes",
    [pytest.param(None, id="tmux-did-not-answer"), pytest.param({}, id="window-not-listed")],
)
def test_a_lemon_tmux_does_not_list_keeps_its_row_as_it_was(monkeypatch, panes):
    _lemons_from_the_dead_server()
    _restore(monkeypatch, panes)

    assert {channel: n.metadata["tty"] for channel, n in _rows().items()} == DEAD_TTYS
