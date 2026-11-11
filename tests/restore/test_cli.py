"""`lemonaid restore` bringing back tmux lemons, and pointing each row at its new pane."""

import argparse
import json
from collections import abc

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db, ended
from lemonaid.restore import cli, inbox_report, report
from lemonaid.restore_config import RestoreConfig
from lemonaid.tmux import home, navigation, relink, restore_relink, server
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
                    "session_id": channel.removeprefix("claude:"),
                    "cwd": "/tmp",
                    "tmux_session": session,
                    "tmux_window": "1",
                    "tmux_socket": "/tmp/tmux-dead/default",
                },
                upsert=False,
                switch_source="tmux",
            )


def _terminal(monkeypatch, **changes) -> None:
    """tmux's restore terminal, placing lemons in an empty server, with *changes* made."""
    terminal = tmux_restore.terminal(True)
    monkeypatch.setattr(tmux_restore, "layout", dict)
    monkeypatch.setattr(home, "socket", lambda: "/tmp/tmux-dead/default")
    monkeypatch.setattr(
        tmux_restore,
        "terminal",
        lambda start: terminal._replace(
            type=lambda window, line: "", seen=lambda where: report.Seen(False, ""), **changes
        ),
    )


def _restore(
    monkeypatch,
    running: set[str],
    opened: abc.Callable[[str], None] = lambda channel: None,
    closed: list[str] | None = None,
) -> None:
    """Run `restore` with a tmux terminal in which only the *running* channels come up.

    *opened* is called with each lemon's channel as its window opens; *closed* collects
    the windows restore closes.
    """
    monkeypatch.setattr(cli, "load_config", lambda: Config(restore=RestoreConfig(1, 0.05)))
    monkeypatch.setattr(cli.plan, "transcript_missing", lambda row: False)
    _terminal(
        monkeypatch,
        open=lambda spot, cwd, environment: (
            opened(_channel_at(spot)) or f"@{spot.at.session}",
            "",
        ),
        close=(closed if closed is not None else []).append,
        running=lambda lemons: {lemon.channel for lemon in lemons} & running,
    )
    cli.cmd_restore(
        argparse.Namespace(dry_run=False, wait=0, json=True, auto=False, into_running=False)
    )


def _channel_at(spot) -> str:
    return next(channel for channel, session in LEMONS.items() if session == spot.at.session)


def _rows() -> dict[str, db.Notification]:
    with db.connect() as conn:
        return {n.channel: n for n in db.get_active(conn) if n.channel in LEMONS}


def test_a_lemon_never_proven_running_stays_lost_and_is_listed_in_the_inbox(monkeypatch, capsys):
    _lemons_from_the_dead_server()
    monkeypatch.setattr(relink, "survey", lambda conn, rows=None: [])

    with pytest.raises(SystemExit):
        _restore(monkeypatch, {"claude:main"})

    out = json.loads(capsys.readouterr().out)
    assert out["restored"] == ["claude:main"]
    assert {r["channel"]: r["outcome"] for r in out["lemons"]} == {
        "claude:main": report.NO_BRIEF,
        "claude:work": report.NOT_RESTORED,
    }
    rows = _rows()
    assert {channel: n.metadata["tty"] for channel, n in rows.items()} == DEAD_TTYS
    assert ended.lost(rows["claude:work"].metadata)
    assert "did not start" in rows["claude:work"].metadata["ended"]["detail"]
    with db.connect() as conn:
        listed = db.get_by_channel(conn, inbox_report.CHANNEL, unread_only=False)
    assert listed is not None and "claude:work" in listed.message


def test_restore_ends_by_dropping_a_pane_another_running_lemon_now_holds(monkeypatch):
    """A lemon left out of the restore keeps a tty from the dead server, which on the new one
    is a restored lemon's pane; a jump would land there."""
    _lemons_from_the_dead_server()
    with db.connect() as conn:
        db.add(
            conn,
            "codex:crowded-out",
            "waiting",
            metadata={
                "tty": "/dev/ttys902",
                "tmux_session": "main",
                "tmux_window": "1",
                "tmux_socket": "/tmp/tmux-dead/default",
            },
            upsert=False,
            switch_source="tmux",
        )
    monkeypatch.setattr(
        relink,
        "survey",
        lambda conn, rows=None: relink.plan(
            db.get_active(conn, switch_source="tmux"), {"main-session": {"/dev/ttys902"}}, {}
        ),
    )
    with pytest.raises(SystemExit):  # it is reported not restored
        _restore(monkeypatch, set())

    with db.connect() as conn:
        [row] = [n for n in db.get_active(conn) if n.channel == "codex:crowded-out"]
    assert {key: row.metadata.get(key) for key in ("tty", "tmux_session", "tmux_window")} == {
        "tty": None,
        "tmux_session": "main",
        "tmux_window": "1",
    }


@pytest.mark.parametrize("as_json", [True, False], ids=["json", "text"])
def test_a_dry_run_with_nothing_to_rebuild_still_shows_the_rows_it_would_repair(
    monkeypatch, capsys, as_json
):
    with db.connect() as conn:
        db.add(
            conn,
            "codex:crowded-out",
            "waiting",
            metadata={"tty": "/dev/ttys902", "tmux_session": "main"},
            switch_source="tmux",
        )
    monkeypatch.setattr(
        relink,
        "survey",
        lambda conn, rows=None: relink.plan(db.get_active(conn), {"other": {"/dev/ttys902"}}, {}),
    )

    cli.cmd_restore(
        argparse.Namespace(dry_run=True, wait=0, json=as_json, auto=False, into_running=False)
    )

    out = capsys.readouterr().out
    if as_json:
        assert json.loads(out) == {
            "lemons": [],
            "not_restored": [],
            "running": [],
            "relinked": [
                {
                    "channel": "codex:crowded-out",
                    "state": "forgotten",
                    "recorded": "main:None (/dev/ttys902)",
                    "pane": None,
                }
            ],
        }
    else:
        assert "forget pane" in out and "codex:crowded-out" in out
    with db.connect() as conn:
        assert db.get_by_channel(conn, "codex:crowded-out").metadata["tty"] == "/dev/ttys902"


def test_a_lost_lemon_found_running_elsewhere_is_relinked_and_lost_no_longer(monkeypatch):
    _lemons_from_the_dead_server()
    with db.connect() as conn:
        db.mark_lost(conn, "claude:main", "test", "")
    new = {"tty": "/dev/ttys902", "tmux_session": "main", "tmux_window": "1"}
    monkeypatch.setattr(
        relink,
        "survey",
        lambda conn, rows=None: [
            relink.Relink(row, relink.RELINKED, new)
            for row in db.get_active(conn)
            if row.channel == "claude:main"
        ],
    )

    [relinked] = restore_relink._relinks(dry_run=False)

    assert relinked.row.channel == "claude:main"
    row = _rows()["claude:main"]
    assert row.metadata["tty"] == "/dev/ttys902"
    assert "ended" not in row.metadata


def test_a_lost_lemon_whose_tty_another_lemon_runs_on_stays_lost_and_restorable(monkeypatch):
    _lemons_from_the_dead_server()
    with db.connect() as conn:
        db.mark_lost(conn, "claude:main", "test", "")
    monkeypatch.setattr(
        relink,
        "survey",
        lambda conn, rows=None: [
            relink.Relink(row, relink.FORGOTTEN, None)
            for row in db.get_active(conn)
            if row.channel == "claude:main"
        ],
    )
    monkeypatch.setattr(server, "started", lambda socket: 200)

    [forgotten] = restore_relink._relinks(dry_run=False)

    assert forgotten.state == relink.FORGOTTEN
    row = _rows()["claude:main"]
    assert "tty" not in row.metadata
    assert ended.lost(row.metadata)
    assert "claude:main" in {r.channel for r in cli._lost(dry_run=True)}


def test_a_lemon_that_registered_before_failing_stays_lost_for_the_next_restore(monkeypatch):
    """Its SessionStart replaced the row's metadata, so it records the new server."""
    _lemons_from_the_dead_server()
    monkeypatch.setattr(relink, "survey", lambda conn, rows=None: [])

    def registered(channel: str) -> None:
        with db.connect() as conn:
            row = db.get_by_channel(conn, channel, unread_only=False)
            assert row is not None
            metadata = {k: v for k, v in row.metadata.items() if k != "ended"}
            db.add(conn, channel, "started", metadata=metadata, switch_source="tmux")

    closed: list[str] = []
    with pytest.raises(SystemExit):
        _restore(monkeypatch, set(), registered, closed)

    assert closed == ["@main", "@main", "@work", "@work"]  # each attempt's own window only
    rows = _rows()
    assert all(ended.failed(row.metadata) for row in rows.values())
    monkeypatch.setattr(server, "started", lambda socket: 900)  # a running, current server
    assert {r.channel for r in cli._lost(dry_run=True)} == set(LEMONS)


def test_a_window_that_could_not_be_opened_is_never_closed(monkeypatch):
    _lemons_from_the_dead_server()
    monkeypatch.setattr(relink, "survey", lambda conn, rows=None: [])
    monkeypatch.setattr(cli, "load_config", lambda: Config(restore=RestoreConfig(1, 0.05)))
    monkeypatch.setattr(cli.plan, "transcript_missing", lambda row: False)
    closed: list[str] = []
    _terminal(
        monkeypatch,
        open=lambda spot, cwd, environment: ("", "index in use"),
        close=closed.append,
        running=lambda lemons: set(),
    )

    with pytest.raises(SystemExit):
        cli.cmd_restore(
            argparse.Namespace(dry_run=False, wait=0, json=True, auto=False, into_running=False)
        )

    assert closed == []
    assert {row.metadata["ended"]["detail"] for row in _rows().values()} == {"index in use"}


@pytest.mark.parametrize("ups", [(True, False), (False, True)], ids=["went", "came"])
def test_a_lost_lemon_is_restored_or_waits_however_tmux_changes_meanwhile(monkeypatch, capsys, ups):
    """A restore that may not start tmux asks once whether it runs."""
    _lemons_from_the_dead_server()
    monkeypatch.setattr(relink, "survey", lambda conn, rows=None: [])
    monkeypatch.setattr(cli, "load_config", lambda: Config(restore=RestoreConfig(1, 0.05)))
    monkeypatch.setattr(cli.plan, "transcript_missing", lambda row: False)
    answers = iter(ups)
    _terminal(
        monkeypatch,
        open=lambda spot, cwd, environment: ("@1", ""),
        close=lambda window: None,
        running=lambda lemons: {lemon.channel for lemon in lemons},
        up=lambda: next(answers),
    )

    cli.cmd_restore(
        argparse.Namespace(dry_run=False, wait=0, json=True, auto=False, into_running=True)
    )

    out = json.loads(capsys.readouterr().out)
    if ups[0]:
        assert sorted(out["restored"]) == sorted(LEMONS) and out["waiting"] == []
    else:
        assert out["restored"] == [] and sorted(out["waiting"]) == sorted(LEMONS)
