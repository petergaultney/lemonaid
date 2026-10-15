import asyncio
import statistics
import time

from textual.app import App

from lemonaid import tmux
from lemonaid.brief import attached, children, family, pr, render, store, target
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
            channel = f"codex:{name}" if archived else ""
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


def test_all_done_children_hide_the_section_and_status_edits_are_reflected():
    parent = lemon("parent")
    child = lemon("child", status="done")
    with db.connect() as conn:
        links.set_parent(conn, child, parent)
    path = store.briefs_dir() / "parent.md"
    found = target.Target([path], [], path.parent, ["parent"], "parent", "")
    shown = family.added(render.view(found, 0, pr.no_state))
    assert not shown.sections[0].children
    assert "**Children:**" not in render.to_markdown(shown, 0)
    path = store.briefs_dir() / "child.md"
    path.write_text(path.read_text().replace("Status: done", "Status: blocked"))
    assert family.added(render.view(found, 0, pr.no_state)).sections[0].children == (
        render.Child("blocked", "child", child),
    )


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
            assert len(view._sections[0].children) == 10
            durations = []
            for _ in range(30):
                start = time.perf_counter()
                view.update_brief(found)
                durations.append(time.perf_counter() - start)
            print(
                f"100 children (40 done, 50 archived with no directory): redraw median={statistics.median(durations)*1000:.2f}ms, max={max(durations)*1000:.2f}ms, n=30"
            )
            rebuilt = []
            for _ in range(10):
                view._rendered_markdown = None
                start = time.perf_counter()
                view.update_brief(found)
                rebuilt.append(time.perf_counter() - start)
                await pilot.pause()
            print(
                f"100 children (40 done, 50 archived with no directory): forced rebuild median={statistics.median(rebuilt)*1000:.2f}ms, max={max(rebuilt)*1000:.2f}ms, n=10"
            )
            view.focus()
            await pilot.press("pagedown")
            assert view.scroll_y > 0

    asyncio.run(check())


def test_archived_children_without_a_directory_hide_but_cleanup_and_live_children_remain(
    tmp_path, monkeypatch
):
    found = _lead(0)
    parent = family.added(render.view(found, 0, pr.no_state)).sections[0].lemon_id
    kept = []
    for name, archived, exists in (
        ("gone", True, False),
        ("cleanup", True, True),
        ("live", False, False),
    ):
        cwd = tmp_path / name
        if exists:
            cwd.mkdir()
        channel = f"codex:{name}"
        child = lemon(name, channel=channel, status="")
        with db.connect() as conn:
            db.add(conn, channel, "", metadata={"cwd": str(cwd)})
            attached.attach(conn, channel, store.briefs_dir() / f"{name}.md")
            links.set_parent(conn, child, parent)
            if archived:
                db.archive_channel(conn, channel, "test")
        if not archived or exists:
            kept.append(child)
    monkeypatch.setattr(tmux, "run", _forbidden)
    monkeypatch.setattr(children, "of", _forbidden)
    monkeypatch.setattr(ownership, "managed_places", _forbidden)
    assert {
        c.lemon_id for c in family.added(render.view(found, 0, pr.no_state)).sections[0].children
    } == set(kept)
