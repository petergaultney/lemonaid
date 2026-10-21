"""Lowercase typing never acts on a session; the capital letter does, and Escape backs out."""

import asyncio
import itertools

import pytest
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input

from lemonaid import config as config_mod
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.edits.screens import RenameScreen, SnoozeScreen

_ids = itertools.count(1500)


def _row(name: str, status: str = "unread") -> db.Notification:
    with db.connect() as conn:
        n = db.add(
            conn,
            f"claude:{name}",
            "a message",
            name,
            {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
        )
        conn.execute(
            "UPDATE notifications SET switch_source = 'tmux', status = ? WHERE id = ?",
            (status, n.id),
        )
        conn.commit()
        return n


def _state(n: db.Notification) -> tuple[str, str]:
    with db.connect() as conn:
        row = db.get(conn, n.id)
        return row.status, row.name or ""


def _run(steps):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _press_each(*keys: str):
    async def steps(app, pilot):
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        return app

    return steps


@pytest.mark.parametrize(
    ("lowercase", "capital", "status_after"),
    [("a", "A", "archived"), ("m", "M", "read")],
)
def test_state_changing_keys_need_the_capital(lowercase, capital, status_after):
    n = _row("guarded")

    _run(_press_each(lowercase, "x", "z", "p", "f", "k", "d", "c"))
    assert _state(n) == ("unread", n.name)

    _run(_press_each(capital))
    assert _state(n)[0] == status_after


def test_alt_m_marks_unread_and_lowercase_does_not():
    n = _row("was-read", "read")

    _run(_press_each("m"))
    assert _state(n)[0] == "read"

    _run(_press_each("alt+m"))
    assert _state(n)[0] == "unread"


@pytest.mark.parametrize(("key", "screen"), [("r", RenameScreen), ("s", SnoozeScreen)])
def test_dialog_keys_open_a_prompt_and_escape_changes_nothing(key, screen):
    n = _row("prompted")

    async def steps(app, pilot):
        await pilot.press(key)
        await pilot.pause()
        opened = isinstance(app.screen, screen)
        await pilot.press(*"typed text", "escape")
        await pilot.pause()
        return opened, isinstance(app.screen, ModalScreen)

    assert _run(steps) == (True, False)
    assert _state(n) == ("unread", n.name)


@pytest.mark.parametrize(
    ("action", "lowercase", "capital"),
    [
        ("action_pin", "p", "P"),
        ("action_undo", "z", "Z"),
        ("action_flip_position", "f", "F"),
    ],
)
def test_other_guarded_actions_need_the_capital(monkeypatch, action, lowercase, capital):
    _row("spied")
    calls: list[str] = []
    monkeypatch.setattr(LemonaidApp, action, lambda self: calls.append(action))

    async def steps(app, pilot):
        await pilot.press(lowercase)
        await pilot.pause()
        before = len(calls)
        await pilot.press(capital)
        await pilot.pause()
        return before, len(calls)

    before, after = _run(steps)

    assert before == 0
    assert after == 1


def test_escape_leaves_search_without_changing_anything():
    n = _row("searchable")

    async def steps(app, pilot):
        await pilot.press("slash", *"sear", "escape")
        await pilot.pause()
        return app.query_one("#main_table", DataTable).row_count, isinstance(app.focused, Input)

    assert _run(steps) == (1, False)
    assert _state(n) == ("unread", n.name)


def test_escape_closes_the_key_reference():
    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        opened = isinstance(app.screen, ModalScreen)
        await pilot.press("escape")
        await pilot.pause()
        return opened, isinstance(app.screen, ModalScreen)

    assert _run(steps) == (True, False)


@pytest.mark.parametrize("scratch_mode", [False, True])
def test_escape_leaves_history_for_the_inbox(scratch_mode):
    _row("historic")

    async def run():
        app = LemonaidApp(scratch_mode=scratch_mode)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            in_history = app._mode is not None
            await pilot.press("escape")
            await pilot.pause()
            return in_history, app._mode, app.is_running

    assert asyncio.run(run()) == (True, None, True)


@pytest.mark.parametrize(
    ("override", "pressed"), [("alt+m", "alt+m"), ("vk", "v"), ("vk", "k"), (",", "comma")]
)
def test_mark_unread_accepts_a_named_key_or_several_characters(monkeypatch, override, pressed):
    n = _row("was-read-too", "read")
    cfg = config_mod.Config()
    cfg.tui.keybindings.mark_unread = override
    monkeypatch.setattr("lemonaid.inbox.tui.app.load_config", lambda: cfg)

    _run(_press_each(pressed))

    assert _state(n)[0] == "unread"
