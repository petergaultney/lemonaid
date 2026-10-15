import asyncio
import statistics
import time

import pytest
from textual.app import App

from lemonaid import tmux
from lemonaid.brief import children, family, pr, render, store, target
from lemonaid.inbox import db
from lemonaid.inbox.tui.briefs.brief_view import BriefView
from lemonaid.lineage import links
from lemonaid.places import ownership

from .shared import lemon


def _forbidden(*args, **kwargs):
    raise AssertionError("Brief redraw must not discover cleanup state")


def _lead(count):
    parent = lemon("lead")
    with db.connect() as conn:
        for i in range(count):
            name = f"child-{i}"
            archived = bool(i % 2)
            channel = f"codex:{name}"
            child = lemon(
                name,
                channel=channel,
                status="" if archived else "blocked" if i % 10 == 0 else "done",
            )
            if archived:
                db.add(
                    conn, channel, "", metadata={"cwd": str(store.briefs_dir() / "removed-place")}
                )
                db.archive_channel(conn, channel, "test")
            links.set_parent(conn, child, parent)
    path = store.briefs_dir() / "lead.md"
    return target.Target([path], [], path.parent, ["lead"], "lead", "")


def test_done_children_remain_until_archived_and_status_edits_are_reflected():
    parent = lemon("parent")
    child = lemon("child", channel="codex:child", status="done")
    with db.connect() as conn:
        links.set_parent(conn, child, parent)
    path = store.briefs_dir() / "parent.md"
    found = target.Target([path], [], path.parent, ["parent"], "parent", "")
    shown = family.added(render.view(found, 0, pr.no_state))
    assert shown.sections[0].children == (render.Child("done", "child", child),)
    assert "- done" in render.to_markdown(shown, 0)
    path = store.briefs_dir() / "child.md"
    path.write_text(path.read_text().replace("Status: done", "Status: blocked"))
    assert family.added(render.view(found, 0, pr.no_state)).sections[0].children == (
        render.Child("blocked", "child", child),
    )

    with db.connect() as conn:
        db.archive_channel(conn, "codex:child", "test")
    shown = family.added(render.view(found, 0, pr.no_state))
    assert not shown.sections[0].children
    assert "**Children:**" not in render.to_markdown(shown, 0)


def test_a_hundred_children_redraw_without_cleanup_discovery(monkeypatch):
    found = _lead(100)
    monkeypatch.setattr(tmux, "run", _forbidden)
    monkeypatch.setattr(children, "of", _forbidden)
    monkeypatch.setattr(ownership, "managed_places", _forbidden)

    class _App(App):
        def compose(self):
            yield BriefView()

    async def check():
        app = _App()
        async with app.run_test(size=(90, 15)) as pilot:
            view = app.query_one(BriefView)
            view.show(found)
            await pilot.pause()
            assert len(view._sections[0].children) == 50
            durations = []
            for _ in range(30):
                start = time.perf_counter()
                view.update_brief(found)
                durations.append(time.perf_counter() - start)
            print(
                f"100 children (40 visible done, 50 archived): redraw median={statistics.median(durations)*1000:.2f}ms, max={max(durations)*1000:.2f}ms, n=30"
            )
            rebuilt = []
            for _ in range(10):
                view._rendered_markdown = None
                start = time.perf_counter()
                view.update_brief(found)
                rebuilt.append(time.perf_counter() - start)
                await pilot.pause()
            print(
                f"100 children (40 visible done, 50 archived): forced rebuild median={statistics.median(rebuilt)*1000:.2f}ms, max={max(rebuilt)*1000:.2f}ms, n=10"
            )
            view.focus()
            await pilot.press("pagedown")
            assert view.scroll_y > 0

    asyncio.run(check())


@pytest.mark.parametrize("state", ["", "done", "blocked", "running"])
@pytest.mark.parametrize("inbox_status", ["unread", "read", "snoozed", "archived"])
@pytest.mark.parametrize("exists", [False, True])
def test_child_visibility_follows_archive_state(tmp_path, monkeypatch, state, inbox_status, exists):
    found = _lead(0)
    parent = family.added(render.view(found, 0, pr.no_state)).sections[0].lemon_id
    cwd = tmp_path / "place"
    if exists:
        cwd.mkdir()
    child = lemon("child", channel="codex:child", status=state)
    with db.connect() as conn:
        db.add(
            conn,
            "codex:child",
            "",
            metadata={"cwd": str(cwd), "tmux_session": "work", "tmux_window": "2"},
        )
        conn.execute(
            "UPDATE notifications SET status = ? WHERE channel = ?", (inbox_status, "codex:child")
        )
        links.set_parent(conn, child, parent)
    monkeypatch.setattr(tmux, "run", _forbidden)
    monkeypatch.setattr(children, "of", _forbidden)
    monkeypatch.setattr(ownership, "managed_places", _forbidden)
    monkeypatch.setattr(type(cwd), "is_dir", _forbidden)
    shown = family.added(render.view(found, 0, pr.no_state))
    assert shown.sections[0].children == (
        () if inbox_status == "archived" else (render.Child(state, "child", child),)
    )


def test_pending_child_without_a_session_is_visible():
    found = _lead(0)
    parent = family.added(render.view(found, 0, pr.no_state)).sections[0].lemon_id
    child = lemon("pending", status="")
    with db.connect() as conn:
        links.set_parent(conn, child, parent)
    assert family.added(render.view(found, 0, pr.no_state)).sections[0].children == (
        render.Child("", "pending", child),
    )
