"""The scratch pane's brief is always the brief of the lemon in its own window."""

import asyncio
import threading
from pathlib import Path

from textual.widgets import DataTable

from lemonaid.brief import session, sidebar, target, window_lemon
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_pane import BriefPane


def _lemon(
    tmp_path: Path, name: str, tmux_session: str, window: str, cwd: Path | None = None
) -> db.Notification | None:
    if cwd is None:
        cwd = tmp_path / name
        cwd.mkdir()
    with db.connect() as conn:
        row = db.add(
            conn,
            f"claude:{name}",
            "working",
            name,
            {"cwd": str(cwd), "tmux_session": tmux_session, "tmux_window": window},
        )
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (row.id,))
        conn.commit()
        return db.get(conn, row.id)


def _in_window(monkeypatch, tmp_path: Path, recorded: target.Target) -> list[tuple]:
    """Put this pane in window `work:2` (`@here`), whose sidebar records *recorded*."""
    remembered: list[tuple] = []
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(sidebar, "read", lambda pane: (recorded, "@here"))
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@here")
    monkeypatch.setattr(sidebar, "remember", lambda *args: remembered.append(args))
    monkeypatch.setattr(session, "current_session", lambda: "work:2")
    monkeypatch.setattr(session, "session_dir", lambda name: tmp_path)
    return remembered


def test_another_lemons_brief_recorded_for_this_window_is_replaced_by_its_own(
    monkeypatch, tmp_path
):
    own = _lemon(tmp_path, "own", "work", "2")
    hq = _lemon(tmp_path, "hq", "hq", "1")
    remembered = _in_window(monkeypatch, tmp_path, target.for_notification(hq, {}))

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            pane = app.query_one(BriefPane)
            pane.sync()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert pane.target is not None
            assert pane.target.lemon is not None and pane.target.lemon.name == "own"
            assert [(p, found.title, window) for p, found, window in remembered] == [
                ("%9", "own", "@here")
            ]
            table = app.query_one("#main_table", DataTable)
            assert str(table.coordinate_to_cell_key(table.cursor_coordinate)[0].value) == str(
                own.id
            )

    asyncio.run(check())


def test_this_windows_own_brief_is_left_as_it_is(monkeypatch, tmp_path):
    own = _lemon(tmp_path, "own", "work", "2")
    monkeypatch.setattr(session, "session_dir", lambda name: tmp_path)
    recorded = target.for_notification(own, {})
    remembered = _in_window(monkeypatch, tmp_path, recorded)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            pane = app.query_one(BriefPane)
            pane.sync()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert pane.target == recorded
            assert remembered == []

    asyncio.run(check())


def test_b_on_another_windows_lemon_switches_to_it_rather_than_recording_it_here(
    monkeypatch, tmp_path
):
    _lemon(tmp_path, "own", "work", "2")
    hq = _lemon(tmp_path, "hq", "hq", "1")
    _in_window(monkeypatch, tmp_path, target.for_notification(hq, {}))
    toggled: list[tuple] = []
    switches: list[int] = []
    monkeypatch.setattr(sidebar, "beside", lambda window: True)
    monkeypatch.setattr(sidebar, "toggle", lambda *args: toggled.append(args) or True)
    monkeypatch.setattr(
        BriefPane,
        "request_switch",
        lambda self, notification, found: switches.append(notification.id),
    )

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            pane = app.query_one(BriefPane)
            assert pane.toggle(hq, pane.target_for(hq), frozenset())
            await pilot.pause()
            assert toggled == []
            assert switches == [hq.id]
            assert pane.target is not None and pane.target.lemon is not None
            assert pane.target.lemon.name == "hq"

    asyncio.run(check())


def test_a_lemon_sharing_this_lemons_directory_is_told_apart(monkeypatch, tmp_path):
    _lemon(tmp_path, "own", "work", "2", cwd=tmp_path)
    other = _lemon(tmp_path, "other", "work", "3", cwd=tmp_path)
    monkeypatch.setattr(session, "session_dir", lambda name: tmp_path)
    _in_window(monkeypatch, tmp_path, target.for_notification(other, {}))

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            pane = app.query_one(BriefPane)
            pane.sync()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert pane.target is not None and pane.target.lemon is not None
            assert pane.target.lemon.name == "own"

    asyncio.run(check())


def test_a_check_finished_after_the_pane_moved_is_dropped(monkeypatch, tmp_path):
    shown = target.Target([], [tmp_path / "other"], None, ["other"], "Other")
    own = target.Target([], [tmp_path / "own"], None, ["own"], "Own")
    remembered = _in_window(monkeypatch, tmp_path, shown)
    where = {"window": "@here", "session": "work:2"}
    looking, release = threading.Event(), threading.Event()

    def find(here: str) -> tuple[target.Target, list[int]] | None:
        if here == "work:3":
            return None

        looking.set()
        assert release.wait(5)
        return own, [42]

    monkeypatch.setattr(sidebar, "window_id", lambda _: where["window"])
    monkeypatch.setattr(session, "current_session", lambda: where["session"])
    monkeypatch.setattr(window_lemon, "find", find)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            pane = app.query_one(BriefPane)
            pane.sync()
            for _ in range(100):
                if looking.is_set():
                    break
                await pilot.pause(0.01)
            where.update(window="@shell", session="work:3")  # a shell window: no lemon
            pane.sync()
            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert pane.target == shown
            assert remembered == []

    try:
        asyncio.run(check())
    finally:
        release.set()
