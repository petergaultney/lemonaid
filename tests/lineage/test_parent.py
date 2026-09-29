from pathlib import Path

from lemonaid.brief import store

from .shared import lemon, run


def test_a_parent_set_by_self_is_found_by_the_child(capsys, monkeypatch):
    parent = lemon("parent", "claude:parent")
    child = lemon("child", "codex:child")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")

    run(capsys, "lemon", "parent", child, "--set", "self", "--json")
    monkeypatch.setenv("LEMONAID_CHANNEL", "codex:child")
    shown = run(capsys, "lemon", "parent", "--self", "--json")

    assert shown["lemon_id"] == child
    assert shown["parent"]["lemon_id"] == parent
    assert shown["parent"]["channel"] == "claude:parent"


def test_a_lemon_with_no_parent_says_none(capsys):
    child = lemon("child")

    assert run(capsys, "lemon", "parent", child)["out"] == "none\n"


def test_a_lemon_cannot_be_its_own_parent(capsys):
    child = lemon("child")

    refused = run(capsys, "lemon", "parent", child, "--set", child, "--json")

    assert "own parent" in refused["error"]


def test_a_link_that_would_make_a_cycle_is_refused(capsys):
    grandparent, parent, child = lemon("grandparent"), lemon("parent"), lemon("child")
    run(capsys, "lemon", "parent", parent, "--set", grandparent, "--json")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    refused = run(capsys, "lemon", "parent", grandparent, "--set", child, "--json")

    assert "cycle" in refused["error"]
    assert run(capsys, "lemon", "parent", grandparent, "--json")["parent"] is None


def test_renaming_a_brief_keeps_its_links(capsys):
    parent, child = lemon("parent"), lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    old = store.briefs_dir() / "child.md"
    renamed = Path(old.rename(store.briefs_dir() / "child-renamed.md"))

    moved = run(capsys, "lemon", "parent", str(renamed), "--json")

    assert moved["lemon_id"] == child
    assert moved["parent"]["lemon_id"] == parent


def test_clear_removes_the_link(capsys):
    parent, child = lemon("parent"), lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")

    cleared = run(capsys, "lemon", "parent", child, "--clear", "--json")

    assert cleared["parent"] is None
