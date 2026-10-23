"""Jumping to a session by its grove key.

Each row shows its lemon's key in the grove, as `0a`: its block's digit, then its tree's
letter, then a capital or a number for a later lemon on the tree. The key stays the same as
the list reorders. Typing a digit opens a bar that takes the rest of the key, as the grove
does, and switches to the lemon it names.
"""

import asyncio
import itertools

from lemonaid.grove.source import inbox_keys
from lemonaid.grove.tui.jump_bar import JumpBar
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.utils import jump_gutter
from lemonaid.inbox.tui.watchers import watcher_hooks

_ids = itertools.count(700)


def _active(name: str) -> int:
    """A live session in the main table, switchable from this environment."""
    with db.connect() as conn:
        n = db.add(
            conn,
            f"claude:{name}",
            "a message",
            name,
            {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
        )
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (n.id,))
        conn.commit()
        return n.id


def _run(steps, size=(120, 40), monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel: None)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def test_a_key_is_padded_so_names_stay_aligned():
    assert jump_gutter("0a", width=4).plain == "0a  "
    assert len(jump_gutter("0a1", width=4).plain) == len(jump_gutter("", width=4).plain)


def _names(app):
    from textual.widgets import DataTable

    table = app.query_one("#main_table", DataTable)
    return [table.get_row_at(r)[3].plain for r in range(table.row_count)]


def test_each_row_starts_with_its_grove_key(monkeypatch):
    for i in range(2):
        _active(f"jump-name-{i}")

    async def steps(app, pilot):
        return _names(app), app._content.inbox.grove

    names, grove = _run(steps, monkeypatch=monkeypatch)
    assert names, "no rows rendered"
    keys = {name.split()[0] for name in names}
    letter = grove.arrangement.trees[("", "/tmp")].letter
    assert keys == {f"0{letter}", f"0{letter.upper()}"}


def test_a_digit_then_a_letter_switches_to_that_lemon(monkeypatch):
    _active("jump-move-a")
    chosen: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_activate_lemon", lambda self, n: chosen.append(n.channel))

    async def steps(app, pilot):
        letter = app._content.inbox.grove.arrangement.trees[("", "/tmp")].letter
        await pilot.press("0")
        await pilot.pause()
        opened = isinstance(app.screen, JumpBar)
        await pilot.press(letter)
        await pilot.pause()
        return opened

    assert _run(steps, monkeypatch=monkeypatch)
    assert chosen == ["claude:jump-move-a"]


def test_escape_closes_the_bar_without_switching(monkeypatch):
    _active("jump-cancel")
    chosen: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_activate_lemon", lambda self, n: chosen.append(n.channel))

    async def steps(app, pilot):
        await pilot.press("0")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        return isinstance(app.screen, JumpBar)

    assert not _run(steps, monkeypatch=monkeypatch)
    assert chosen == []


def test_history_has_no_keys(monkeypatch):
    """Enter resumes in history, which is too costly to hang on a key or two."""

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app.action_jump_to_number("2")
        await pilot.pause()
        return isinstance(app.screen, JumpBar)

    assert not _run(steps, monkeypatch=monkeypatch)


def test_a_digit_typed_into_the_history_filter_stays_a_digit(monkeypatch):
    """The filter is a text box; a digit there is search input, not a jump."""

    async def steps(app, pilot):
        from textual.widgets import Input

        app._set_history_mode(True)
        await pilot.pause()
        app.action_filter_history()
        await pilot.pause()
        filter_input = app.query_one("#history_filter", Input)
        filter_input.focus()
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        return filter_input.value

    assert _run(steps, monkeypatch=monkeypatch) == "3"


def test_every_rows_key_switches_to_that_rows_lemon(monkeypatch):
    for i in range(4):
        _active(f"jump-every-{i}")
    chosen: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_activate_lemon", lambda self, n: chosen.append(n.channel))

    async def steps(app, pilot):
        pressed = []
        for channel, key in sorted(inbox_keys.names(app._content.inbox.grove).items()):
            pressed.append(channel)
            for character in key:
                await pilot.press(character)
                await pilot.pause()
        return pressed

    pressed = _run(steps, monkeypatch=monkeypatch)
    assert len(pressed) == 4
    assert chosen == pressed  # each key, in turn, reached its own lemon
