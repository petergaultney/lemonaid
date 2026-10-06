import asyncio
import dataclasses

from textual.app import App

from lemonaid.brief import family, identity, pr, render, status, store, target
from lemonaid.inbox import db
from lemonaid.inbox.tui import brief_view
from lemonaid.inbox.tui.brief_view import BriefView

from .shared import lemon, run


def _shown(name: str) -> render.View:
    path = (store.briefs_dir() / f"{name}.md").resolve()
    brief = status.load(path)
    section = render.Section(
        None,
        name,
        "working",
        "working",
        (),
        path,
        brief.mtime,
        "",
        lemon_id=identity.from_path(path),
    )
    return render.View("", False, (section,), "")


def test_a_brief_shows_its_parent_and_its_childrens_status(capsys):
    parent = lemon("parent")
    child = lemon("child", status="done")
    grandchild = lemon("grandchild", status="blocked")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    run(capsys, "lemon", "parent", grandchild, "--set", child, "--json")

    [section] = family.added(_shown("child")).sections

    assert (section.parent, section.parent_name) == (parent, "")
    assert section.children == (render.Child("blocked", grandchild.split(".")[0], grandchild),)


def test_a_child_is_named_for_its_session_when_it_has_one(capsys):
    parent = lemon("parent")
    child = lemon("child", channel="claude:1a2b3c4d")
    with db.connect() as conn:
        db.add(conn, "claude:1a2b3c4d", "", name="fold waiting")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    [section] = family.added(_shown("parent")).sections

    assert section.children == (render.Child("working", "fold waiting", child),)


def test_a_parent_is_named_for_its_session_when_it_has_one(capsys):
    parent = lemon("parent", channel="claude:5e6f7a8b")
    with db.connect() as conn:
        db.add(conn, "claude:5e6f7a8b", "", name="lemonaid HQ")
    run(capsys, "lemon", "parent", lemon("child"), "--set", parent, "--json")
    path = (store.briefs_dir() / "child.md").resolve()
    found = target.Target([path], [path.parent], path.parent, ["child"], "child", "")
    lemon_ = target.Identity(name="child", backend="Claude")

    out = render.to_markdown(
        family.added(render.view(dataclasses.replace(found, lemon=lemon_), 0, pr.no_state)), 0
    )

    assert f"Parent: lemonaid HQ ({identity.markdown_id(parent)})" in out


def test_children_are_listed_one_per_line_before_done(capsys):
    parent = lemon("parent")
    path = store.briefs_dir() / "parent.md"
    path.write_text(
        path.read_text()
        + "\n## Now\n\n### Needs Peter\n\n- a decision\n\n### Done\n\n- the start\n"
    )
    first, second = (
        lemon(name, status=state) for name, state in (("first", "blocked"), ("second", "done"))
    )
    for child in (first, second):
        run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    found = target.Target([path], [path.parent], path.parent, ["parent"], "parent", "")

    out = render.to_markdown(family.added(render.view(found, 0, pr.no_state)), 0)

    assert (
        f"**Children:**\n\n- blocked · {identity.markdown_id(first)}\n"
        f"- done · {identity.markdown_id(second)}"
    ) in out
    assert out.index("a decision") < out.index("**Children:**") < out.index("**Done:**")


def test_a_brief_with_no_links_shows_no_family_line():
    lemon("alone")

    [section] = family.added(_shown("alone")).sections

    assert (section.parent, section.children) == ("", ())


def test_a_brief_with_a_broken_lemon_id_shows_no_family_line():
    path = store.briefs_dir() / "broken.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# broken\n\nLemon-ID: a/b\n\nStatus: working\n")

    [section] = family.added(
        render.view(target.Target([path], [], None, [], "", ""), 0, pr.no_state)
    ).sections

    assert (section.lemon_id, section.parent, section.children) == ("", "", ())


def test_the_brief_view_shows_the_parent_and_children(capsys):
    parent = lemon("parent")
    child = lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    grandchild = lemon("grandchild")
    run(capsys, "lemon", "parent", grandchild, "--set", child, "--json")
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
            return (
                view._rendered_markdown,
                str(view.query_one(brief_view._Card).render()),
                str(view.query_one(".brief-children").render()),
            )

    rendered, shown, children = asyncio.run(check())
    assert f"Brief-ID: {child}" in shown and f"Parent: {parent}" in shown
    assert (
        f"Brief-ID: {identity.markdown_id(child)}  \n" f"Parent: {identity.markdown_id(parent)}"
    ) in rendered
    assert children == f"Children:\n  working  {grandchild}"
