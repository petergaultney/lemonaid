import asyncio
from pathlib import Path

from textual.app import App

from lemonaid.brief import family, pr, render, status, store, target
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

    assert section.parent == parent
    assert section.children == (("blocked", grandchild.split(".")[0]),)


def test_a_child_is_named_for_its_session_when_it_has_one(capsys):
    parent = lemon("parent")
    child = lemon("child", channel="claude:1a2b3c4d")
    with db.connect() as conn:
        db.add(conn, "claude:1a2b3c4d", "", name="fold waiting")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    [section] = family.added(_shown("parent")).sections

    assert section.children == (("working", "fold waiting"),)


def test_children_are_listed_one_per_line_before_done(capsys):
    parent = lemon("parent")
    path = store.briefs_dir() / "parent.md"
    path.write_text(
        path.read_text()
        + "\n## Now\n\n### Needs Peter\n\n- a decision\n\n### Done\n\n- the start\n"
    )
    for name, state in (("first", "blocked"), ("second", "done")):
        run(capsys, "lemon", "parent", lemon(name, status=state), "--set", parent, "--json")
    found = target.Target([path], [path.parent], path.parent, ["parent"], "parent", "")

    out = render.to_markdown(family.added(render.view(found, 0, pr.no_state)), 0)

    assert "**Children:**\n\n- blocked · first\n- done · second" in out
    assert out.index("a decision") < out.index("**Children:**") < out.index("**Done:**")


def test_a_brief_with_no_links_shows_no_family_line():
    lemon("alone")

    [section] = family.added(_shown("alone")).sections

    assert (section.parent, section.children) == ("", ())


def test_a_brief_with_a_broken_lemon_id_shows_no_family_line():
    path = store.briefs_dir() / "broken.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# broken\n\nLemon-ID: a/b\n\nStatus: working\n")

    with db.connect() as conn:
        assert family.of(conn, Path(path)) == ("", ())


def test_the_brief_view_shows_the_parent_and_children(capsys):
    parent = lemon("parent")
    child = lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    run(capsys, "lemon", "parent", lemon("grandchild"), "--set", child, "--json")
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
            view = app.query_one(BriefView)
            return view._rendered_markdown, str(view.query_one(".brief-children").render())

    rendered, children = asyncio.run(check())
    assert f"**Parent:** `{parent}`" in rendered
    assert children == "Children:\n  working  grandchild"
