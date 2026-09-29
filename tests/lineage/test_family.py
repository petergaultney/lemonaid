import asyncio
from pathlib import Path

from textual.app import App

from lemonaid.brief import family, render, status, store, target
from lemonaid.inbox import db
from lemonaid.inbox.tui.brief_view import BriefView

from .shared import lemon, run


def _shown(name: str) -> render.View:
    path = (store.briefs_dir() / f"{name}.md").resolve()
    brief = status.load(path)
    section = render.Section(None, name, "working", "working", (), path, brief.mtime, "")
    return render.View("", False, (section,), "")


def test_a_brief_shows_its_parent_and_its_childrens_status(capsys):
    parent = lemon("parent")
    child = lemon("child", status="done")
    grandchild = lemon("grandchild", status="blocked")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    run(capsys, "lemon", "parent", grandchild, "--set", child, "--json")

    [section] = family.added(_shown("child")).sections

    assert section.family == f"**Parent:** `{parent}` · **Children:** `{grandchild}` blocked"
    assert section.family in render.to_markdown(family.added(_shown("child")), 0)


def test_a_brief_with_no_links_shows_no_family_line():
    lemon("alone")

    [section] = family.added(_shown("alone")).sections

    assert section.family == ""


def test_a_brief_with_a_broken_lemon_id_shows_no_family_line():
    path = store.briefs_dir() / "broken.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# broken\n\nLemon-ID: a/b\n\nStatus: working\n")

    with db.connect() as conn:
        assert family.line(conn, Path(path)) == ""


def test_the_brief_view_shows_the_family_under_the_card(capsys):
    parent = lemon("parent")
    child = lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    path = (store.briefs_dir() / "child.md").resolve()
    found = target.Target([path], [path.parent], path.parent, ["child"], "child", "**child**")

    class _App(App):
        def compose(self):
            yield BriefView()

    async def check():
        app = _App()
        async with app.run_test(size=(80, 30)) as pilot:
            app.query_one(BriefView).show(found)
            await pilot.pause()
            return app.query_one(BriefView)._rendered_markdown

    assert f"**Parent:** `{parent}`" in asyncio.run(check())
