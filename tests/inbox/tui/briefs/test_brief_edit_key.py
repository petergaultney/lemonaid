"""`e` edits the brief a brief view shows, in the scratch pane and in the brief popup."""

import asyncio
from pathlib import Path

import pytest

from lemonaid import config
from lemonaid.brief import attached, target
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.inbox.tui import bindings
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs import brief_popup
from lemonaid.inbox.tui.briefs.brief_pane import BriefPane
from lemonaid.inbox.tui.edits import inbox_brief_edit


def _attached_brief(name: str, channel: str) -> Path:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: running\n\n## Now\n\n- Working on {name}.\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
    return path


def _edits(monkeypatch) -> list[tuple[Path, object]]:
    """Each call to `inbox_brief_edit.edit`, as (path, front end), instead of opening an editor."""
    calls: list[tuple[Path, object]] = []
    monkeypatch.setattr(
        inbox_brief_edit,
        "edit",
        lambda app, path, title, front_end: calls.append((path, front_end)) or "",
    )
    return calls


@pytest.mark.parametrize(
    ("brief_shown", "brief_unselected", "overlaid", "searching", "expected"),
    [
        (False, False, False, False, True),
        (True, False, False, False, True),
        (True, True, False, False, True),
        (False, False, True, False, False),
        (False, False, False, True, False),
    ],
    ids=["inbox", "a brief shown", "a brief whose row is unselected", "a dialog", "searching"],
)
def test_edit_brief_is_permitted(brief_shown, brief_unselected, overlaid, searching, expected):
    assert (
        bindings.permitted(
            "edit_brief",
            brief_shown=brief_shown,
            overlaid=overlaid,
            searching=searching,
            history_focused=lambda: False,
            resume_available=lambda: False,
            brief_unselected=brief_unselected,
        )
        is expected
    )


def test_e_in_the_scratch_pane_edits_the_brief_shown_not_the_row_under_the_cursor(monkeypatch):
    _attached_brief("row-under-cursor", "claude:row")
    shown = _attached_brief("shown", "claude:shown")
    calls = _edits(monkeypatch)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            app._set_brief_view(target.Target([shown], [shown.parent], None, [], "shown"))
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()

    asyncio.run(check())

    assert [path for path, _ in calls] == [shown]


def test_e_edits_the_one_brief_shown_when_no_inbox_row_is_selected(monkeypatch):
    shown = _attached_brief("shown", "claude:shown")
    calls = _edits(monkeypatch)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            app._set_brief_view(target.Target([shown], [shown.parent], None, [], "shown"))
            await pilot.pause()
            app.query_one(BriefPane).unselected = True
            await pilot.press("e")
            await pilot.pause()

    asyncio.run(check())

    assert [path for path, _ in calls] == [shown]


def test_e_in_a_view_of_several_briefs_edits_none(monkeypatch):
    first = _attached_brief("first", "claude:first")
    second = _attached_brief("second", "claude:second")
    calls = _edits(monkeypatch)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            app._set_brief_view(target.Target([first, second], [first.parent], None, [], "both"))
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()

    asyncio.run(check())

    assert calls == []


def test_e_in_the_brief_popup_edits_its_brief_in_place(monkeypatch):
    shown = _attached_brief("shown", "claude:shown")
    calls = _edits(monkeypatch)

    async def check() -> None:
        found = target.Target([shown], [shown.parent], None, [], "shown")
        app = brief_popup.BriefPopup(found, config.Config())
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()

    asyncio.run(check())

    assert calls == [(shown, None)]
