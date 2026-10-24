"""The grove opened from the inbox, with the inbox's own bindings in place."""

import asyncio
import itertools

from lemonaid.grove.layout import view
from lemonaid.grove.tui.screen import GroveScreen
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.tmux import fast_popup

_ids = itertools.count(4100)


def _row(name: str, session: str) -> None:
    with db.connect() as conn:
        n = db.add(
            conn,
            f"claude:{name}",
            "a message",
            name,
            {
                "tty": f"/dev/ttys{next(_ids)}",
                "cwd": "/tmp",
                "session_id": f"s{next(_ids)}",
                "tmux_session": session,
            },
        )
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (n.id,))
        conn.commit()


def test_search_arrows_reach_the_grove_not_the_inbox(monkeypatch):
    monkeypatch.delenv("TMUX")
    _row("lemon one", "first")
    _row("lemon two", "second")

    async def run() -> int:
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            for key in ("slash", "l", "e", "m", "o", "n", "down"):
                await pilot.press(key)
                await pilot.pause()
            screen = app.screen
            assert isinstance(screen, GroveScreen)
            return screen._where.chosen

    assert asyncio.run(run()) == 1


def test_outside_tmux_space_opens_the_grove_and_closes_it(monkeypatch):
    monkeypatch.delenv("TMUX")
    _row("lemon three", "third")

    async def run() -> tuple[bool, bool]:
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            opened = isinstance(app.screen, GroveScreen)
            await pilot.press("space")
            await pilot.pause()
            return opened, isinstance(app.screen, GroveScreen)

    assert asyncio.run(run()) == (True, False)


def test_in_tmux_space_in_a_narrow_pane_opens_the_grove_popup(monkeypatch):
    opened = []
    monkeypatch.setattr(
        fast_popup,
        "show",
        lambda name, margin, title: opened.append((name, margin) == ("grove", 3)),
    )
    _row("lemon four", "fourth")

    async def run() -> bool:
        app = LemonaidApp()
        async with app.run_test(size=(69, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            return isinstance(app.screen, GroveScreen)

    assert asyncio.run(run()) is False
    assert opened == [True]


def test_in_tmux_the_inbox_starts_the_grove_popup_ahead_of_time(monkeypatch):
    warmed = []
    monkeypatch.setattr(fast_popup, "warm", lambda name, margin: warmed.append(name))

    async def run() -> None:
        async with LemonaidApp().run_test(size=(69, 48)) as pilot:
            await pilot.pause()
            await pilot.app.workers.wait_for_complete()

    asyncio.run(run())
    assert warmed == ["grove"]


def test_escape_with_nothing_open_leaves_the_scratch_pane_up():
    _row("lemon five", "fifth")

    async def run() -> bool:
        app = LemonaidApp(scratch_mode=True)
        hidden = []
        app._hide_scratch_pane = lambda: hidden.append(True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
        return bool(hidden)

    assert asyncio.run(run()) is False


def test_in_tmux_space_in_a_big_pane_draws_the_grove_in_place(monkeypatch):
    opened = []
    monkeypatch.setattr(
        fast_popup,
        "show",
        lambda name, margin, title: opened.append((name, margin) == ("grove", 3)),
    )
    _row("lemon six", "sixth")

    async def run() -> bool:
        app = LemonaidApp()
        async with app.run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            return isinstance(app.screen, GroveScreen)

    assert asyncio.run(run()) is True
    assert opened == []


def test_alt_r_a_letter_twice_then_enter_renames_that_lemon_from_the_grove(monkeypatch):
    monkeypatch.delenv("TMUX")
    _row("lemon four", "fourth")

    async def run() -> str:
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.app.workers.wait_for_complete()
            screen = app.screen
            assert isinstance(screen, GroveScreen)
            letter = screen._grove.arrangement.trees[("", "fourth")].letter
            typed = (
                "alt+r",
                "0",
                letter,
                letter,
                "enter",
                *["backspace"] * 5,
                "space",
                "5",
                "enter",
            )
            for key in typed:
                await pilot.press(key)
                await pilot.pause()
            return screen._where.note

    assert asyncio.run(run()) == "renamed lemon 5"
    with db.connect() as conn:
        assert db.get_by_channel(conn, "claude:lemon four", unread_only=False).name == "lemon 5"


def test_escape_closes_a_grove_that_opened_panned(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX")
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    view.save((30.0, 6.0))
    _row("lemon panned", "panned")

    async def run() -> bool:
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            return isinstance(app.screen, GroveScreen)

    assert not asyncio.run(run())


def test_zooming_and_searching_keep_the_saved_view(monkeypatch, tmp_path):
    monkeypatch.delenv("TMUX")
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    view.save((30.0, 2.0))  # within what a 160x48 screen can pan to
    _row("lemon kept", "kept")

    async def run() -> None:
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            for key in ("space", "0", "escape", "slash", "escape"):
                await pilot.press(key)
                await pilot.pause()

    asyncio.run(run())
    assert view.load() == (30.0, 2.0)
