"""Arrows in the sidebar brief redraw at once and move the main pane behind them."""

import asyncio
import dataclasses
import threading
from pathlib import Path

from textual.widgets import ContentSwitcher, DataTable, Input

from lemonaid.brief import sidebar, target
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.brief_view import BriefView
from lemonaid.inbox.tui.table import ClickToActTable


def _lemons(monkeypatch, tmp_path: Path, count: int) -> tuple[list[db.Notification], dict]:
    """Rows in list order, each with its own brief, and the sidebar state they share."""
    with db.connect() as conn:
        rows = [
            db.add(
                conn,
                f"claude:lemon-{index}",
                "working",
                f"lemon-{index}",
                {"cwd": str(tmp_path), "tty": f"/dev/test-{index}"},
                switch_source="tmux",
                status="read",
                created_at=1000.0 - index,
            )
            for index in range(count)
        ]
    targets = {}
    for index, row in enumerate(rows):
        place = tmp_path / f"lemon-{index}"
        place.mkdir()
        path = place / "task.md"
        path.write_text(f"# Lemon {index}\n\nStatus: working\n\n## Now\n- Step {index}.\n")
        targets[row.channel] = target.Target([path], [place], place, ["work"], f"Lemon {index}")

    state: dict = {"shown": None, "switched": [], "cleared": 0, "result": True}
    state["gate"] = threading.Event()
    state["gate"].set()

    def switch_beside(metadata, switch_source, config, found):
        state["switched"].append(metadata["channel"])
        state["gate"].wait(5)
        if state["result"]:
            state["shown"] = found
        return state["result"]

    def clear(pane):
        state["cleared"] += 1
        state["shown"] = None

    def toggle(found, window):
        state["shown"] = found
        return True

    def show(found, window):
        state["shown"] = found
        return True

    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr("lemonaid.inbox.tui.app.is_follow_enabled", lambda: True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.current_position", lambda _: "left")
    monkeypatch.setattr("lemonaid.inbox.tui.app.brief.attached.for_rows", lambda *args: {})
    real_for_notification = target.for_notification
    monkeypatch.setattr(
        target,
        "for_notification",
        lambda row, *args: dataclasses.replace(
            targets[row.channel], lemon=real_for_notification(row, {}).lemon
        ),
    )
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")
    monkeypatch.setattr(sidebar, "toggle", toggle)
    monkeypatch.setattr(sidebar, "clear", clear)
    monkeypatch.setattr(sidebar, "switch_beside", switch_beside)
    monkeypatch.setattr(sidebar, "show", show)
    monkeypatch.setattr(
        sidebar, "read", lambda pane: (state["shown"], "@target") if state["shown"] else None
    )
    state["targets"] = [target.for_notification(row, {}) for row in rows]
    return rows, state


async def _until(pilot, condition) -> None:
    for _ in range(200):
        if condition():
            return
        await pilot.pause(0.01)
    raise AssertionError("condition never held")


def test_the_brief_is_drawn_before_the_main_pane_switches(monkeypatch, tmp_path):
    rows, state = _lemons(monkeypatch, tmp_path, 2)
    state["gate"].clear()

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.action_brief()
            await pilot.press("down")
            await _until(pilot, lambda: state["switched"])
            assert app._brief_target == state["targets"][1]
            assert "Step 1." in app.query_one(BriefView)._rendered_markdown
            assert app._get_current_row_key() == str(rows[1].id)
            assert state["shown"] == state["targets"][0]  # the main pane has not moved yet

            state["gate"].set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert state["switched"] == [rows[1].channel]
            assert state["shown"] == app._brief_target == state["targets"][1]

    asyncio.run(check())


def test_repeated_arrows_switch_only_to_the_newest_row(monkeypatch, tmp_path):
    rows, state = _lemons(monkeypatch, tmp_path, 4)
    state["gate"].clear()

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.action_brief()
            await pilot.press("down")
            await _until(pilot, lambda: state["switched"])
            await pilot.press("down", "down")
            await pilot.pause()
            assert app._brief_target == state["targets"][3]

            state["gate"].set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert state["switched"] == [rows[1].channel, rows[3].channel]
            assert app._get_current_row_key() == str(rows[3].id)
            assert app._brief_target == state["targets"][3]

    asyncio.run(check())


def test_a_wake_during_a_switch_keeps_the_new_brief(monkeypatch, tmp_path):
    """The follow hook clears the sidebar brief and wakes the pane mid-switch."""
    _, state = _lemons(monkeypatch, tmp_path, 2)
    state["gate"].clear()

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.action_brief()
            await pilot.press("down")
            await _until(pilot, lambda: state["switched"])
            state["shown"] = None
            await pilot.press("f12")
            await pilot.pause()
            assert app.query_one(ContentSwitcher).current == "brief_view"
            assert app._brief_target == state["targets"][1]

            state["gate"].set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app._brief_target == state["targets"][1]

    asyncio.run(check())


def test_a_failed_switch_goes_back_to_the_lemon_beside_it(monkeypatch, tmp_path):
    rows, state = _lemons(monkeypatch, tmp_path, 2)
    state["result"] = False

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.action_brief()
            await pilot.press("down")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app._get_current_row_key() == str(rows[0].id)
            assert app._brief_target == state["targets"][0]

    asyncio.run(check())


def test_closing_during_a_switch_leaves_no_brief_beside_the_lemon(monkeypatch, tmp_path):
    rows, state = _lemons(monkeypatch, tmp_path, 2)
    state["gate"].clear()

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.action_brief()
            await pilot.press("down")
            await _until(pilot, lambda: state["switched"])
            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one(ContentSwitcher).current == "inbox_content"

            state["gate"].set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert state["shown"] is None
            assert app.query_one(ContentSwitcher).current == "inbox_content"
            assert app._get_current_row_key() == str(rows[1].id)

    asyncio.run(check())


def test_m_and_M_mark_the_row_whose_brief_is_shown(monkeypatch, tmp_path):
    rows, _ = _lemons(monkeypatch, tmp_path, 2)

    def dots(app) -> list[bool]:
        return ["●" in card.render().plain for card in app.query_one(BriefView).query("_Card")]

    def unread(row) -> bool:
        with db.connect() as conn:
            return db.get(conn, row.id).is_unread

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.query_one("#main_table", DataTable).move_cursor(row=1)
            app.action_brief()
            await pilot.pause()
            assert dots(app) == [False]

            await pilot.press("M")
            await pilot.pause()
            assert unread(rows[1]) and not unread(rows[0])
            assert dots(app) == [True]
            assert app._get_current_row_key() == str(rows[1].id)

            await pilot.press("m")
            await pilot.pause()
            assert not unread(rows[1])
            assert dots(app) == [False]

            await pilot.press("z")
            await pilot.pause()
            assert unread(rows[1])
            assert dots(app) == [True]

    asyncio.run(check())


def test_r_renames_the_row_whose_brief_is_shown(monkeypatch, tmp_path):
    rows, state = _lemons(monkeypatch, tmp_path, 2)

    def headlines(app) -> list[str]:
        return [
            card.render().plain.splitlines()[0] for card in app.query_one(BriefView).query("_Card")
        ]

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.query_one("#main_table", DataTable).move_cursor(row=1)
            app.action_brief()
            await pilot.pause()
            assert "lemon-1" in headlines(app)[0]

            await pilot.press("r")
            await pilot.pause()
            app.screen.query_one(Input).value = "renamed"
            await pilot.press("enter")
            await pilot.pause()
            with db.connect() as conn:
                assert db.get(conn, rows[1].id).name == "renamed"
                assert db.get(conn, rows[0].id).name == "lemon-0"
            assert "renamed" in headlines(app)[0]
            assert state["shown"].lemon.name == "renamed"

            await pilot.press("z")
            await pilot.pause()
            assert "lemon-1" in headlines(app)[0]

    asyncio.run(check())


def test_clicking_the_selected_row_in_a_focused_scratch_pane_stays_put(monkeypatch, tmp_path):
    rows, _ = _lemons(monkeypatch, tmp_path, 2)
    switched: list[int] = []
    monkeypatch.setattr(
        LemonaidApp,
        "_switch_to_notification",
        lambda self, row: switched.append(row.id) or True,
    )

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            table = app.query_one("#main_table", ClickToActTable)
            key = table.coordinate_to_cell_key(table.cursor_coordinate)[0]

            app.set_class(True, "-input-active")
            table.post_message(ClickToActTable.SelectedRowClicked(table, key))
            await pilot.pause()
            assert switched == []

            await pilot.press("enter")
            await pilot.pause()
            assert switched == [rows[0].id]

            app.set_class(False, "-input-active")
            table.post_message(ClickToActTable.SelectedRowClicked(table, key))
            await pilot.pause()
            assert switched == [rows[0].id, rows[0].id]

    asyncio.run(check())
