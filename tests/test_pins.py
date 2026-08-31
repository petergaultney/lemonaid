"""Pinned sessions: ordering, and what happens to pins nobody can see."""

import asyncio
import time

from rich.text import Span, Text

from lemonaid.inbox import db, pins
from lemonaid.inbox.tui import app
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.utils import (
    FIELD_STYLES,
    PIN_MARK,
    PIN_MARK_STYLE,
    backend_cell,
    styled_cell,
)


def _session(conn, channel: str, name: str = ""):
    return db.register_working(
        conn, channel=channel, message="working", name=name or channel, metadata={}
    )


def _order(conn) -> list[str]:
    return [n.channel for n in db.get_active(conn)]


def test_pinned_sessions_come_first(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        for channel in ("a:1", "b:2", "c:3"):
            _session(conn, channel)

        pins.pin(conn, "c:3")

        assert _order(conn)[0] == "c:3"


def test_a_pinned_session_stays_put_when_it_goes_unread(tmp_path):
    """Pinning fixes position; it does not exempt a session from being unread."""
    with db.connect(tmp_path / "t.db") as conn:
        _session(conn, "pinned:1")
        _session(conn, "loud:2")
        pins.pin(conn, "pinned:1")

        db.add(conn, channel="loud:2", message="needs you", name="loud", metadata={})

        assert _order(conn) == ["pinned:1", "loud:2"]


def test_pin_order_follows_position_not_pin_time(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        for channel in ("a:1", "b:2"):
            _session(conn, channel)
        pins.pin(conn, "a:1")
        pins.pin(conn, "b:2")

        pins.swap(conn, "a:1", "b:2")

        assert _order(conn)[:2] == ["b:2", "a:1"]


def test_unpinned_sessions_keep_sorting_unread_first(tmp_path):
    """Pinning must not reach rows that have no pin.

    A tiebreak between two pins sharing a position sorted every row when it was
    placed above the status test, and unpinned rows - all NULL position, so all
    tied - fell through to it and came out alphabetical.
    """
    with db.connect(tmp_path / "t.db") as conn:
        now = time.time()
        for channel, status, age in (
            ("z:1", "unread", 300),
            ("m:2", "read", 50),
            ("a:3", "read", 200),
        ):
            n = _session(conn, channel)
            conn.execute(
                "UPDATE notifications SET status = ?, created_at = ? WHERE id = ?",
                (status, now - age, n.id),
            )
        conn.commit()

        assert _order(conn) == ["z:1", "m:2", "a:3"]


def test_an_unread_below_a_pin_still_sorts_above_a_read(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        now = time.time()
        for channel, status, age in (
            ("pin:1", "read", 10),
            ("read:2", "read", 50),
            ("unread:3", "unread", 300),
        ):
            n = _session(conn, channel)
            conn.execute(
                "UPDATE notifications SET status = ?, created_at = ? WHERE id = ?",
                (status, now - age, n.id),
            )
        conn.commit()
        pins.pin(conn, "pin:1")

        assert _order(conn) == ["pin:1", "unread:3", "read:2"]


def test_toggle_reports_the_new_state(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        _session(conn, "a:1")

        assert pins.toggle(conn, "a:1") is True
        assert pins.toggle(conn, "a:1") is False
        assert not pins.is_pinned(conn, "a:1")


def test_pinning_twice_does_not_move_it(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        for channel in ("a:1", "b:2"):
            _session(conn, channel)
        pins.pin(conn, "a:1")
        pins.pin(conn, "b:2")

        pins.pin(conn, "a:1")

        assert _order(conn)[:2] == ["a:1", "b:2"]


def test_a_pin_survives_a_new_notification(tmp_path):
    """The reason pins live in their own table rather than on notification rows."""
    with db.connect(tmp_path / "t.db") as conn:
        _session(conn, "a:1")
        _session(conn, "b:2")
        pins.pin(conn, "b:2")

        db.add(conn, channel="b:2", message="fresh", name="b", metadata={})

        assert _order(conn)[0] == "b:2"


def test_a_snoozed_pin_keeps_its_place_while_away(tmp_path):
    """A pin nobody can see is not renumbered by a move made without it."""
    with db.connect(tmp_path / "t.db") as conn:
        for channel in ("a:1", "x:2", "b:3"):
            _session(conn, channel)
        for channel in ("a:1", "x:2", "b:3"):
            pins.pin(conn, channel)

        away = db.get_active(conn)
        db.snooze(conn, next(n.id for n in away if n.channel == "x:2"), time.time() + 3600)
        assert _order(conn) == ["a:1", "b:3"]

        pins.swap(conn, "b:3", "a:1")  # the move the user could make on screen
        db.unsnooze(conn, "x:2")

        assert _order(conn) == ["b:3", "x:2", "a:1"]


def test_a_move_does_not_pull_an_absent_pin_along(tmp_path):
    """Positions are never renumbered, so an absent pin keeps the place it held.

    The absent pin is first here, which is where renumbering the visible rows
    from zero would send it to the back of the list - a move onto a row the
    user could not see and said nothing about.
    """
    with db.connect(tmp_path / "t.db") as conn:
        for channel in ("a:1", "b:2", "c:3"):
            _session(conn, channel)
            pins.pin(conn, channel)

        away = db.get_active(conn)
        db.snooze(conn, next(n.id for n in away if n.channel == "a:1"), time.time() + 3600)

        pins.swap(conn, "c:3", "b:2")
        db.unsnooze(conn, "a:1")

        assert _order(conn) == ["a:1", "c:3", "b:2"]


def test_archiving_clears_the_pin(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        _session(conn, "a:1")
        pins.pin(conn, "a:1")

        db.archive(conn, db.get_active(conn)[0].id)

        assert not pins.is_pinned(conn, "a:1")


def test_snoozing_keeps_the_pin(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        _session(conn, "a:1")
        pins.pin(conn, "a:1")

        db.snooze(conn, db.get_active(conn)[0].id, time.time() + 3600)

        assert pins.is_pinned(conn, "a:1")


def test_swap_ignores_a_channel_that_is_not_pinned(tmp_path):
    with db.connect(tmp_path / "t.db") as conn:
        for channel in ("a:1", "b:2"):
            _session(conn, channel)
        pins.pin(conn, "a:1")

        pins.swap(conn, "a:1", "b:2")

        assert _order(conn) == ["a:1", "b:2"]


# --- the mark ---------------------------------------------------------------


def test_a_pinned_row_is_marked_in_the_backend_column():
    label = styled_cell("CC", False, "backend")

    assert backend_cell(label, True).plain == f"CC{PIN_MARK}"
    assert backend_cell(label, False).plain == "CC"


def test_the_mark_colours_only_itself():
    """The mark is a span over its own cell, so the label keeps its own colour."""
    marked = backend_cell(styled_cell("CC", False, "backend"), True)

    assert marked.spans == [Span(2, 3, PIN_MARK_STYLE)]
    assert marked.style == FIELD_STYLES["backend"]


def test_a_card_puts_the_mark_under_the_label():
    """A card has the height to give the mark its own line; a row does not."""
    label = styled_cell("CC", False, "backend")

    assert backend_cell(label, True, stacked=True).plain == f"CC\n{PIN_MARK}"


def test_the_stacked_mark_keeps_its_own_colour():
    marked = backend_cell(styled_cell("CC", False, "backend"), True, stacked=True)

    assert marked.spans == [Span(2, 4, PIN_MARK_STYLE)]


def test_the_mark_fits_the_column():
    """The backend column is three wide for a two-character label."""
    assert len(backend_cell(styled_cell("CC", False, "backend"), True).plain) == 3


def test_a_card_moves_an_inline_mark_onto_its_own_line():
    """Rows carry the mark inline; the card restacks what it is handed."""
    cells = [
        Text("15:48:29"),
        Text(""),
        backend_cell(styled_cell("CC", False, "backend"), True),
        Text("a-name"),
        Text(""),
        Text("~/w/x"),
        Text("a message"),
    ]
    _body, backend = app._as_card(cells, 40)

    assert backend.plain == f"CC\n{PIN_MARK}"


def test_an_unpinned_card_keeps_a_bare_label():
    cells = [
        Text("15:48:29"),
        Text(""),
        styled_cell("CC", False, "backend"),
        Text("a-name"),
        Text(""),
        Text("~/w/x"),
        Text("a message"),
    ]
    _body, backend = app._as_card(cells, 40)

    assert backend.plain == "CC"


# --- through the TUI -------------------------------------------------------
#
# Only the wiring is exercised here - that the keys reach the actions and that
# the actions read the list off the table. The ordering rules themselves are
# covered above, against the database, where no app is involved: a watcher
# thread from an earlier test outlives it and archives rows out of whichever
# database is current, so a test that keeps an app alive across several frames
# cannot rely on its rows still being there.


def test_the_keys_are_bound(monkeypatch):
    """`p` and the shift arrows reach their actions."""
    called: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)
    monkeypatch.setattr(LemonaidApp, "action_pin", lambda self: called.append("pin"))
    monkeypatch.setattr(LemonaidApp, "action_move_pin_up", lambda self: called.append("up"))
    monkeypatch.setattr(LemonaidApp, "action_move_pin_down", lambda self: called.append("down"))

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for key in ("p", "shift+up", "shift+down"):
                await pilot.press(key)
                await pilot.pause()

    asyncio.run(run())

    assert called == ["pin", "up", "down"]


def test_an_unbound_move_key_is_not_registered(monkeypatch):
    """Setting a move key to "" leaves it unbound rather than crashing."""
    from lemonaid import config as config_mod
    from lemonaid.inbox.tui import app as app_mod

    cfg = config_mod.load_config()
    cfg.tui.keybindings.move_pin_up = ""
    monkeypatch.setattr(app_mod, "load_config", lambda: cfg)

    called: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)
    monkeypatch.setattr(LemonaidApp, "action_move_pin_up", lambda self: called.append("up"))

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("shift+up")
            await pilot.pause()

    asyncio.run(run())

    assert called == []
