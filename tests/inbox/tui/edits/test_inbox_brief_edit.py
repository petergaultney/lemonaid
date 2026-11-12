"""A running app edits a brief itself: it keeps the copy, merges and tells the lemon, and
starts only the editor, in a popup it waits on from a worker or in its own terminal."""

import asyncio
import contextlib
import datetime
from collections import abc
from pathlib import Path

from textual.app import App

from lemonaid.brief import attached, child, identity
from lemonaid.brief import store as brief_store
from lemonaid.front_end import interface
from lemonaid.inbox import db
from lemonaid.inbox.tui.edits import inbox_brief_edit
from lemonaid.messages import store as mailboxes


def _brief() -> Path:
    path = brief_store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        child.render(
            "## Now\n\nStarting.\n\n## Goal\n\nFix the flaky test.\n\n## Watching\n",
            "the task",
            "task.QuickOdd",
            ("hq.BlessBar", "hq"),
            datetime.date(2026, 10, 2),
            {},
        )
    )
    with db.connect() as conn:
        identity.ensure(conn, path)
        db.add(conn, "codex:t1", "", metadata={})
        attached.attach(conn, "codex:t1", path)
    return path


def _messages(path: Path) -> list[str]:
    mailbox = mailboxes.mailbox_for_id(identity.read(path.read_text()))
    return [message.read_text() for message in sorted(mailbox.glob("*.md"))]


def _front_end(popup: abc.Callable[[abc.Sequence[str], str], int | None]) -> interface.FrontEnd:
    terminal = interface.Terminal("test", "", lambda: True, lambda *a: True, lambda *a: True)
    return interface.FrontEnd(terminal, lambda *a: ({}, ""), None, None, popup=popup)


def _edits_copy(*changes: tuple[str, str], exit_status: int = 0, then=lambda: None):
    """A popup that applies each (old, new) to the copy it is given, one per call."""
    calls: list[str] = []

    def popup(argv: abc.Sequence[str], title: str) -> int | None:
        copy = Path(argv[-1])
        calls.append(copy.read_text())
        old, new = changes[len(calls) - 1]
        copy.write_text(copy.read_text().replace(old, new))
        then()
        return exit_status

    return popup, calls


async def _settle(pilot) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def test_a_popup_edit_is_merged_and_its_lemon_told(monkeypatch):
    path = _brief()
    popup, _ = _edits_copy(("Fix the flaky test.", "Fix every flaky test."))
    notices: list[str] = []

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "notify", lambda message, **kw: notices.append(message))
            said = inbox_brief_edit.edit(app, path, "task", _front_end(popup))
            await _settle(pilot)
            assert said == ""

    asyncio.run(run())

    assert "Fix every flaky test." in path.read_text()
    assert notices == ["Saved task.md, and told its lemon what changed"]
    [message] = _messages(path)
    assert "+Fix every flaky test.\n" in message


def test_a_conflict_asks_and_e_reopens_the_copy_with_both_sides(monkeypatch):
    path = _brief()

    def lemon_writes() -> None:
        if "Halfway" not in path.read_text():
            path.write_text(path.read_text().replace("Starting.", "Halfway there."))

    popup, calls = _edits_copy(
        ("Starting.", "Paused by me."),
        (
            "<<<<<<< your edit\nPaused by me.\n=======\nHalfway there.\n>>>>>>> the brief now\n",
            "Paused by me, halfway there.\n",
        ),
        then=lemon_writes,
    )

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            inbox_brief_edit.edit(app, path, "task", _front_end(popup))
            await _settle(pilot)
            assert isinstance(app.screen, inbox_brief_edit.EditAgainScreen)
            await pilot.press("e")
            await _settle(pilot)

    asyncio.run(run())

    assert "<<<<<<< your edit\nPaused by me.\n" in calls[1]
    assert "Paused by me, halfway there." in path.read_text()
    assert "<<<<<<<" not in path.read_text()


def test_an_error_exit_asks_and_s_stops_with_the_brief_unchanged(monkeypatch):
    path = _brief()
    before = path.read_text()
    popup, calls = _edits_copy(("Fix the flaky test.", "Unfinished goal."), exit_status=1)
    notices: list[str] = []

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "notify", lambda message, **kw: notices.append(message))
            inbox_brief_edit.edit(app, path, "task", _front_end(popup))
            await _settle(pilot)
            assert isinstance(app.screen, inbox_brief_edit.EditAgainScreen)
            await pilot.press("s")
            await pilot.pause()

    asyncio.run(run())

    assert len(calls) == 1
    assert path.read_text() == before
    assert _messages(path) == []
    [stopped] = notices
    kept = stopped.rsplit("Your edit is in ", 1)[1]
    assert "Unfinished goal." in Path(kept).read_text()


def test_a_popup_that_never_ran_the_editor_changes_nothing(monkeypatch):
    path = _brief()
    before = path.read_text()
    notices: list[str] = []

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            monkeypatch.setattr(app, "notify", lambda message, **kw: notices.append(message))
            inbox_brief_edit.edit(app, path, "task", _front_end(lambda argv, title: None))
            await _settle(pilot)

    asyncio.run(run())

    assert path.read_text() == before
    assert notices[0].startswith("The editor didn't start. Stopped: the brief is unchanged.")


def test_without_a_popup_the_editor_runs_in_the_apps_own_terminal(monkeypatch, tmp_path):
    path = _brief()
    script = tmp_path / "editor.py"
    script.write_text(
        "import pathlib, sys\n"
        "p = pathlib.Path(sys.argv[1])\n"
        "p.write_text(p.read_text().replace('Fix the flaky test.', 'Fix it here.'))\n"
    )
    monkeypatch.setenv("VISUAL", f"python3 {script}")
    monkeypatch.setattr(App, "suspend", lambda self: contextlib.nullcontext())

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            inbox_brief_edit.edit(app, path, "task", None)
            await pilot.pause()

    asyncio.run(run())

    assert "Fix it here." in path.read_text()
    assert len(_messages(path)) == 1
