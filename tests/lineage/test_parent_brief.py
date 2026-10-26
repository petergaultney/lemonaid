from lemonaid.brief import check, frontmatter, store
from lemonaid.inbox import db
from lemonaid.lineage import links

from .shared import lemon, run


def _brief(name: str, text: str) -> str:
    path = store.briefs_dir() / f"{name}.md"
    path.write_text(text)
    return path.read_text()


def _parent_value(name: str) -> object:
    block, _ = frontmatter.split((store.briefs_dir() / f"{name}.md").read_text())
    return frontmatter.readable(block or []).get("parent")


def test_set_rewrites_the_parent_in_frontmatter(capsys):
    old, new = lemon("old"), lemon("new")
    child = lemon("child")
    _brief("child", f"---\ntype: Brief\nbrief-id: {child}\nparent: {old}\n---\n# child\n")

    run(capsys, "lemon", "parent", child, "--set", new, "--json")

    assert _parent_value("child") == new


def test_set_adds_a_parent_a_brief_lacked(capsys):
    parent, child = lemon("parent"), lemon("child")

    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    assert _parent_value("child") == parent


def test_clear_removes_the_parent_line(capsys):
    parent, child = lemon("parent"), lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    run(capsys, "lemon", "parent", child, "--clear", "--json")

    assert _parent_value("child") is None
    assert "parent:" not in (store.briefs_dir() / "child.md").read_text()


def test_a_brief_that_already_agrees_is_not_rewritten(capsys):
    parent, child = lemon("parent"), lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    path = store.briefs_dir() / "child.md"
    path.touch()
    before = path.stat().st_mtime_ns

    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    assert path.stat().st_mtime_ns == before


def test_a_lemon_with_no_brief_file_still_changes_its_link(capsys):
    parent, child = lemon("parent"), lemon("child")
    (store.briefs_dir() / "child.md").unlink()

    result = run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    assert result["parent"]["lemon_id"] == parent
    assert "no brief file" in result["note"]


def test_a_rewritten_parent_passes_brief_check(capsys):
    parent, child = lemon("parent"), lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    path = store.briefs_dir() / "child.md"

    with db.connect() as conn:
        problems = check.parent_line(conn, path.read_text())

    assert problems == []


def _legacy(name: str, text: str) -> None:
    (store.briefs_dir() / f"{name}.md").write_text(text)


def test_clear_removes_a_parent_line_inside_now(capsys):
    child = lemon("child")
    _legacy("child", f"# child\n\nBrief-ID: {child}\n\n## Now\n\nParent: Old.one\n\nworking\n")
    with db.connect() as conn:
        links.set_parent(conn, child, lemon("old"))

    run(capsys, "lemon", "parent", child, "--clear", "--json")

    assert "Parent:" not in (store.briefs_dir() / "child.md").read_text()
    with db.connect() as conn:
        assert links.parent_of(conn, child) == ""


def test_a_fenced_parent_example_survives_a_change(capsys):
    parent, child = lemon("parent"), lemon("child")
    example = "```\nParent: Example.one\n```"
    _legacy("child", f"# child\n\nBrief-ID: {child}\n\n{example}\n")

    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    assert example in (store.briefs_dir() / "child.md").read_text()
    assert _parent_value("child") == parent
