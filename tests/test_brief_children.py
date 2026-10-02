import argparse
import contextlib
import dataclasses
import json
import os
from pathlib import Path

import pytest

import lemonaid.brief.write_cli
from lemonaid.brief import attached, child_place, children, children_cli, identity, store
from lemonaid.config import PlaceRoot
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.places import ownership

_PRS = """
## Now

### PRs

| Work | PR | Review |
|---|---|---|
| The thing | [r#12](https://github.com/o/r/pull/12) | |
"""


@pytest.fixture(autouse=True)
def _no_inherited_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


def _lemon(
    name: str, status: str, channel: str = "", cwd: Path | None = None, now: str = ""
) -> str:
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {status}\n{now}")
    with db.connect() as conn:
        if channel:
            metadata = {"tmux_session": f"s-{name}", "tmux_window": "2"}
            db.add(
                conn,
                channel,
                "",
                name=f"{name} work",
                metadata=metadata | ({"cwd": str(cwd)} if cwd else {}),
            )
            attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def _link(child: str, parent: str) -> None:
    with db.connect() as conn:
        links.set_parent(conn, child, parent)


def _world(
    tmp_path: Path, clients: dict[str, int] | None = None, panes: dict | None = None
) -> child_place.World:
    root = PlaceRoot(path=tmp_path, protected=["main"])
    places = [
        ownership.Place(key, root, tmp_path / key) for key in ("feat", "gone", "main", "pending")
    ]
    for key in ("feat/src", "main", "pending"):
        (tmp_path / key).mkdir(parents=True, exist_ok=True)
    return child_place.World(
        sessions={"s-author", "s-reviewer", "pending-session"},
        clients=clients or {},
        places=places,
        panes=panes or {},
        roots=[root],
    )


def _of(parent: str, world: child_place.World) -> list[children.Child]:
    with db.connect() as conn:
        return children.of(conn, parent, world)


def test_a_child_carries_its_place_session_prs_and_reviewer(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    author = _lemon("author", "merge", "claude:author", tmp_path / "feat" / "src", _PRS)
    reviewer = _lemon("reviewer", "waiting", "codex:reviewer", tmp_path / "feat")
    _link(author, parent)
    _link(reviewer, author)

    [child] = _of(parent, _world(tmp_path))

    assert (child.lemon_id, child.name, child.status) == (author, "author work", "merge")
    assert child.place == child_place.Place("feat", str(tmp_path / "feat"), True, listed=True)
    assert (child.tmux_session, child.alive, child.clients) == ("s-author", True, 0)
    assert child.prs == ("https://github.com/o/r/pull/12",)
    assert [c.lemon_id for c in child.children] == [reviewer]
    assert child.held_by == (
        "status merge",
        f"reviewer work ({reviewer.rsplit('.', 1)[-1]}) is waiting",
    )


def test_cleanup_is_ready_when_the_whole_family_is_done_and_nobody_is_attached(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    author = _lemon("author", "done", "claude:author", tmp_path / "feat")
    reviewer = _lemon("reviewer", "done", "codex:reviewer", tmp_path / "feat")
    _link(author, parent)
    _link(reviewer, author)

    [ready] = _of(parent, _world(tmp_path))
    [watched] = _of(parent, _world(tmp_path, clients={"s-reviewer": 1}))
    [unknown] = _of(parent, dataclasses.replace(_world(tmp_path), clients=None))

    assert (ready.cleanup, ready.held_by) == ("ready", ())
    assert watched.held_by == ("a client is attached to s-reviewer",)
    assert unknown.held_by == ("tmux didn't say who is attached",)


def test_with_tmux_unreachable_a_done_child_is_never_ready_or_cleaned(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    here = _lemon("here", "done", "claude:here", tmp_path / "feat")
    gone = _lemon("gone", "done", "claude:gone", tmp_path / "gone")
    for child in (here, gone):
        _link(child, parent)
    world = dataclasses.replace(_world(tmp_path), sessions=None, clients=None)

    found = _of(parent, world)

    assert [(c.alive, c.cleanup, c.held_by) for c in found] == [
        (None, "held", ("tmux didn't say who is attached",)),
        (None, "held", ("tmux didn't say who is attached",)),
    ]


def test_a_protected_place_is_never_a_childs_place(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    child = _lemon("child", "working", "claude:child", tmp_path / "main")
    _link(child, parent)

    [found] = _of(parent, _world(tmp_path))

    assert found.place is None


def test_a_child_not_started_yet_finds_its_place_through_its_sessions_panes(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    pending = _lemon("pending", "working")
    _link(pending, parent)
    with db.connect() as conn:
        attached.attach_pending(conn, "pending-session", "2", store.briefs_dir() / "pending.md", [])
    world = _world(tmp_path, panes={"pending-session": [tmp_path / "pending"]})

    [found] = _of(parent, world)

    assert (found.channel, found.tmux_session, found.alive) == ("", "pending-session", True)
    assert found.place == child_place.Place("pending", str(tmp_path / "pending"), True, listed=True)


def test_done_children_are_hidden_only_once_their_place_is_known_to_be_gone(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    kept = _lemon("kept", "done", "claude:kept", tmp_path / "feat")
    gone = _lemon("gone", "done", "claude:gone", tmp_path / "gone")
    nowhere = _lemon("nowhere", "done")
    working = _lemon("working", "working")
    for child in (kept, gone, nowhere, working):
        _link(child, parent)

    listed = _of(parent, _world(tmp_path))

    assert [c.lemon_id for c in listed if children.shown(c, everything=False)] == [
        kept,
        nowhere,
        working,
    ]
    assert [c.lemon_id for c in listed if children.shown(c, everything=True)] == [
        kept,
        gone,
        nowhere,
        working,
    ]


def test_under_a_root_with_no_list_hook_the_shallowest_path_is_the_place(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    child = _lemon("child", "working", "claude:child", tmp_path / "unlisted" / "x" / "src")
    _link(child, parent)
    (tmp_path / "unlisted" / "x" / "src").mkdir(parents=True)
    listless = PlaceRoot(path=tmp_path / "unlisted")
    world = dataclasses.replace(
        _world(tmp_path, panes={"s-child": [tmp_path / "unlisted" / "x"]}),
        sessions={"s-child"},
        roots=[listless],
    )

    [found] = _of(parent, world)

    assert found.place == child_place.Place(
        "x", str(tmp_path / "unlisted" / "x"), True, listed=False
    )


def test_a_child_not_done_whose_session_is_gone_is_an_orphan(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    orphan = _lemon("orphan", "working", "claude:orphan", tmp_path / "feat")
    finished = _lemon("finished", "done", "claude:finished", tmp_path / "feat")
    for child in (orphan, finished):
        _link(child, parent)

    found = {c.lemon_id: c for c in _of(parent, _world(tmp_path))}

    assert (found[orphan].cleanup, found[orphan].held_by) == (
        "orphan",
        ("session gone, status working",),
    )
    assert (found[finished].alive, found[finished].cleanup) == (False, "ready")


def test_a_done_child_with_no_session_or_directory_left_is_cleaned(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    gone = _lemon("gone", "done", "claude:gone", tmp_path / "gone")
    _link(gone, parent)

    [found] = _of(parent, _world(tmp_path))

    assert (found.place and found.place.exists, found.cleanup) == (False, "cleaned")


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    lemonaid.brief.write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(argv)
    with contextlib.suppress(SystemExit):
        args.func(args)

    out = capsys.readouterr()
    return json.loads(out.out) if "--json" in argv else {"out": out.out, "err": out.err}


def test_the_command_lists_self_s_children_as_json_and_text(capsys, monkeypatch, tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    author = _lemon("author", "done", "claude:author", tmp_path / "feat")
    reviewer = _lemon("reviewer", "waiting", "codex:reviewer", tmp_path / "feat")
    _link(author, parent)
    _link(reviewer, author)
    monkeypatch.setattr(children_cli, "_world", lambda: _world(tmp_path))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")

    listed = _run(capsys, "children", "--self", "--json")
    text = _run(capsys, "children", "--self")["out"]

    assert listed["lemon_id"] == parent
    [child] = listed["children"]
    assert (child["cleanup"], child["place"]["key"]) == ("held", "feat")
    assert [(c["lemon_id"], c["cleanup"]) for c in child["children"]] == [(reviewer, "held")]
    assert f"{author}  done" in text
    assert f"\n    {reviewer}  waiting" in text
    assert "    cleanup  held: reviewer work" in text


def test_self_without_a_brief_is_an_error(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(children_cli, "_world", lambda: _world(tmp_path))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:nobody")

    assert "No brief attached" in _run(capsys, "children", "--self", "--json")["error"]


def test_since_is_when_the_status_last_changed_not_the_last_edit(tmp_path):
    parent = _lemon("parent", "working", "claude:parent")
    child = _lemon("child", "waiting", "claude:child", tmp_path / "feat")
    _link(child, parent)
    path = store.briefs_dir() / "child.md"
    os.utime(path, (1000, 1000))
    [first] = _of(parent, _world(tmp_path))

    path.write_text(path.read_text() + "\n## Now\n\n### Next\n\n- more\n")
    os.utime(path, (2000, 2000))
    [edited] = _of(parent, _world(tmp_path))

    path.write_text(path.read_text().replace("Status: waiting", "Status: blocked"))
    os.utime(path, (3000, 3000))
    [changed] = _of(parent, _world(tmp_path))

    assert [(c.status, c.since, c.updated) for c in (first, edited, changed)] == [
        ("waiting", 1000, 1000),
        ("waiting", 1000, 2000),
        ("blocked", 3000, 3000),
    ]
