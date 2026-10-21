from dataclasses import replace

import pytest

from lemonaid import handlers
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.inbox.tui.watchers import watcher_hooks

_AUTHOR = {
    "tty": "/dev/author",
    "tmux_session": "shared",
    "tmux_window": "2",
    "tmux_pane_identity": ["%2", 10],
    "tmux_session_order": [20, 10, 1],
    "tmux_socket": "/tmp/server",
}
_REVIEWER = {
    **_AUTHOR,
    "tty": "/dev/reviewer",
    "tmux_window": "4",
    "tmux_pane_identity": ["%4", 10],
}


def _add(conn, channel, location):
    added = db.add(
        conn,
        channel,
        "keep message",
        "keep name",
        {**location, "cwd": "/same", "session_id": channel[6:]},
        status="read",
        switch_source="tmux",
    )
    return db.get(conn, added.id)


def test_repair_existing_wrong_rows_preserves_every_non_location_field(monkeypatch):
    with db.connect() as conn:
        author = _add(conn, "codex:author", _REVIEWER)
        reviewer = _add(conn, "codex:reviewer", _AUTHOR)
        assert (
            handlers.repair_tmux_locations(conn, {"author": [_AUTHOR], "reviewer": [_REVIEWER]})
            == 2
        )
        fixed = db.get(conn, author.id)
        assert fixed == replace(author, metadata={**author.metadata, **_AUTHOR})
        assert db.get(conn, reviewer.id) == replace(
            reviewer, metadata={**reviewer.metadata, **_REVIEWER}
        )
        assert (
            handlers.repair_tmux_locations(conn, {"author": [_AUTHOR], "reviewer": [_REVIEWER]})
            == 0
        )


def test_concurrent_location_update_is_not_overwritten():
    with db.connect() as conn:
        old = _add(conn, "codex:author", _REVIEWER)
        newer = _add(conn, "codex:author", {**_AUTHOR, "tty": "/dev/new"})
        assert not db.repair_location(conn, old, _AUTHOR)
        assert db.get(conn, old.id) == newer


@pytest.mark.parametrize("matches", [[], [_AUTHOR, _REVIEWER]])
def test_ambiguous_or_absent_thread_is_not_repaired(monkeypatch, matches):
    monkeypatch.setattr(handlers, "codex_tmux_locations", lambda: {"author": matches})
    monkeypatch.setattr(
        handlers.tmux.navigation, "switch_to_pane", lambda *args: pytest.fail("wrong pane")
    )
    monkeypatch.setattr(handlers.tmux.recreate, "recreate", lambda *args: pytest.fail("duplicate"))
    with db.connect() as conn:
        row = _add(conn, "codex:author", _REVIEWER)
        assert handlers.repair_tmux_locations(conn, {"author": matches}) == 0
    with db.connect() as conn:
        assert db.get(conn, row.id) == row


def test_watcher_repairs_on_startup_and_periodically(monkeypatch):
    callbacks = {}
    monkeypatch.setattr(
        watcher_hooks, "start_unified_watcher", lambda **kwargs: callbacks.update(kwargs)
    )
    monkeypatch.setattr(handlers, "codex_tmux_locations", lambda: {"author": [_AUTHOR]})
    clock = iter([100.0, 101.0, 111.0])
    monkeypatch.setattr(watcher_hooks.time, "monotonic", lambda: next(clock))
    with db.connect() as conn:
        row = _add(conn, "codex:author", _REVIEWER)
    watcher_hooks.start(Config(), None, lambda channels: None)
    callbacks["get_active"]()
    with db.connect() as conn:
        assert db.get(conn, row.id).metadata["tty"] == _AUTHOR["tty"]
        _add(conn, "codex:author", _REVIEWER)
    callbacks["get_active"]()
    with db.connect() as conn:
        assert db.get(conn, row.id).metadata["tty"] == _REVIEWER["tty"]
    callbacks["get_active"]()
    with db.connect() as conn:
        assert db.get(conn, row.id).metadata["tty"] == _AUTHOR["tty"]


def test_selected_row_click_uses_saved_tty_without_process_scan_or_repair(monkeypatch):
    from lemonaid.inbox.tui.watchers import focus

    monkeypatch.setattr(
        handlers, "codex_tmux_locations", lambda: pytest.fail("click must not scan")
    )
    monkeypatch.setattr(focus, "behind_scratch", lambda *args: _REVIEWER["tty"])
    with db.connect() as conn:
        row = _add(conn, "codex:author", _REVIEWER)
    assert focus.is_behind_scratch(row, "%scratch")
    with db.connect() as conn:
        assert db.get(conn, row.id).metadata["tty"] == _REVIEWER["tty"]
