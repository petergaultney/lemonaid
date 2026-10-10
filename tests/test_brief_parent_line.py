"""No brief verb loses the `Parent:` line, wherever the brief keeps it."""

import argparse
import contextlib
import datetime
import json

import pytest

from lemonaid.brief import (
    attached,
    check,
    child,
    identity,
    layout,
    now_edit,
    pr_table,
    store,
    verbs_cli,
    waiters,
    write_cli,
)
from lemonaid.inbox import db
from lemonaid.lineage import links

_PARENT = "Parent: hq.BlessBar (hq), 2026-10-02"
_PR = "https://github.com/o/r/pull/7"


def _child_brief() -> str:
    return child.render(
        (child.PACKAGED_DIR / "child.md").read_text(),
        "the task",
        "task.QuickOdd",
        ("hq.BlessBar", "hq"),
        datetime.date(2026, 10, 2),
        {},
        area="lemonaid",
    )


_NOW = "## Now\n\n### Needs Peter\n\n- merge #12\n\n### Next\n\n- write the docs\n\n"
_QUESTIONS = "## Questions\n\n### merge #12\n\n- **Context:** x\n\n"

_BRIEFS = {
    "child, no Now": _child_brief(),
    "child, Now under Status": _child_brief().replace(
        "Status: working\n\n", f"Status: working\n\n{_NOW}", 1
    ),
    "rules template": _child_brief()
    .replace(f"{_PARENT}\n\nArea: lemonaid\n\n", "", 1)
    .replace("## Goal", f"{_NOW}{_QUESTIONS}{_PARENT}\n\n## Goal", 1),
    "rules template, no Questions": _child_brief()
    .replace(f"{_PARENT}\n\nArea: lemonaid\n\n", "", 1)
    .replace("## Goal", f"{_NOW}{_PARENT}\n\n## Goal", 1),
}

_VERBS = {
    "bullet add": lambda t: now_edit.add(t, "Next", "tag the release"),
    "bullet set": lambda t: now_edit.replace(now_edit.add(t, "Next", "tag it"), "tag", "tagged"),
    "bullet rm": lambda t: now_edit.remove(now_edit.add(t, "Next", "tag it"), "tag"),
    "pr add": lambda t: now_edit.with_section(
        t, "PRs", lambda body: pr_table.with_row(body, _PR, "Fix", None)
    ),
    "pr rm": lambda t: now_edit.with_section(
        now_edit.with_section(t, "PRs", lambda body: pr_table.with_row(body, _PR, "Fix", None)),
        "PRs",
        lambda body: pr_table.without(body, "7"),
    ),
    "waiter add": lambda t: waiters.add(t, "lemonaid inbox watch --self"),
    "status": lambda t: store.with_status(t, "blocked"),
    "now": lambda t: now_edit.with_now(t, layout.parse("### Next\n\n- start over")),
}


@pytest.mark.parametrize("verb", _VERBS)
@pytest.mark.parametrize("brief", _BRIEFS)
def test_every_verb_keeps_the_parent_line(brief, verb):
    out = _VERBS[verb](_BRIEFS[brief])

    assert out.count(_PARENT) == 1
    assert ("Area: lemonaid" in out) == ("Area: lemonaid" in _BRIEFS[brief])
    assert check.structure(out) == (
        ["`### merge #12` in ## Questions has no matching bullet under ### Needs Peter"]
        if brief == "rules template" and verb == "now"
        else []
    )


def test_a_new_now_goes_below_the_header_lines():
    out = now_edit.add(_BRIEFS["child, no Now"], "Next", "x")

    assert f"{_PARENT}\n\nArea: lemonaid\n\n## Now\n\n### Next\n\n- x\n\n## Goal" in out


@pytest.mark.parametrize("brief", _BRIEFS)
def test_now_given_a_parent_line_replaces_the_one_parent_line(brief):
    out = now_edit.with_now(_BRIEFS[brief], layout.parse("- x\n\nParent: other, 2026-10-03"))

    assert out.count("Parent:") == 1 and "Parent: other, 2026-10-03" in out
    assert ("Area: lemonaid" in out) == ("Area: lemonaid" in _BRIEFS[brief])


@pytest.mark.parametrize("brief", _BRIEFS)
def test_now_given_an_area_line_keeps_the_parent_line(brief):
    out = now_edit.with_now(_BRIEFS[brief], layout.parse("- x\n\nArea: elsewhere"))

    assert out.count(_PARENT) == 1
    assert out.count("Area:") == 1 and "Area: elsewhere" in out


def test_a_parent_line_in_a_code_fence_is_not_the_brief_s_parent():
    fenced = _BRIEFS["child, no Now"].replace(
        "## Context\n", "## Context\n\n```\nParent: example\n```\n", 1
    )

    out = now_edit.with_now(fenced, layout.parse("- x\n\nParent: other, 2026-10-03"))

    assert "```\nParent: example\n```" in out
    assert out.count("Parent: other, 2026-10-03") == 1 and _PARENT not in out


def _registered(text: str, parent: str = ""):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    with db.connect() as conn:
        identity.ensure(conn, path)
        if parent:
            links.set_parent(conn, identity.read(text), parent)
        db.add(conn, "codex:t1", "", metadata={"tmux_session": "work", "tmux_window": "2"})
        attached.attach(conn, "codex:t1", path)
    return path


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args([*argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def test_check_reports_a_lost_parent_line_when_a_parent_is_recorded(capsys):
    lost = _BRIEFS["child, no Now"].replace(f"{_PARENT}\n\n", "")
    path = _registered(lost, parent="hq.BlessBar")

    found = _run(capsys, "check", str(path))["problems"]

    assert found == [
        "No `Parent:` line, but hq.BlessBar is this brief's parent; add `Parent: hq.BlessBar`"
    ]


def test_check_does_not_ask_for_a_parent_line_without_a_recorded_parent(capsys):
    path = _registered(_BRIEFS["child, no Now"].replace(f"{_PARENT}\n\n", ""))

    assert _run(capsys, "check", str(path))["problems"] == []


def test_a_brief_that_lost_its_parent_line_still_takes_edits(capsys):
    lost = _BRIEFS["child, no Now"].replace(f"{_PARENT}\n\n", "")
    path = _registered(lost, parent="hq.BlessBar")

    result = _run(capsys, "bullet", "add", "--channel", "codex:t1", "Next", "more")

    assert result["error"] is None
    assert "- more" in path.read_text()


def test_an_edit_that_drops_the_parent_line_is_refused():
    path = _registered(_BRIEFS["rules template, no Questions"])

    error = verbs_cli.edit(path, lambda text: text.replace(f"{_PARENT}\n\n", ""))

    assert "drops the `Parent:` line" in error
    assert path.read_text() == _BRIEFS["rules template, no Questions"]
