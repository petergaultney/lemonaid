import argparse
import datetime
import sys
import textwrap
from pathlib import Path

import pytest

from lemonaid.brief import attached, child, hand_edit, hand_edit_cli, identity, store
from lemonaid.inbox import db
from lemonaid.messages import store as mailboxes

_PARENT = "Parent: hq.BlessBar (hq), 2026-10-02"


def _brief(*, goal: str = "Fix the flaky test.") -> str:
    return child.render(
        f"## Now\n\nStarting.\n\n## Goal\n\n{goal}\n\n## Watching\n",
        "the task",
        "task.QuickOdd",
        ("hq.BlessBar", "hq"),
        datetime.date(2026, 10, 2),
        {},
    )


def _registered(text: str):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    with db.connect() as conn:
        identity.ensure(conn, path)
        db.add(conn, "codex:t1", "", metadata={"tmux_session": "work", "tmux_window": "2"})
        attached.attach(conn, "codex:t1", path)
    return path


def _messages(path) -> list[str]:
    mailbox = mailboxes.mailbox_for_id(identity.read(path.read_text()))
    return [message.read_text() for message in sorted(mailbox.glob("*.md"))]


def test_apply_keeps_the_lemons_write_made_while_the_copy_was_open():
    path = _registered(_brief())
    base = hand_edit.copy_text(path)
    path.write_text(path.read_text().replace("Starting.", "Halfway there."))
    yours = base.replace("Fix the flaky test.", "Fix the flaky test, then the slow one.")

    outcome = hand_edit.apply(path, base, yours)

    assert isinstance(outcome, hand_edit.Applied)
    assert "Halfway there." in path.read_text()
    assert "Fix the flaky test, then the slow one." in path.read_text()
    assert "+Fix the flaky test, then the slow one.\n" in outcome.diff


def test_apply_returns_a_conflict_and_leaves_the_brief_when_both_changed_the_same_line():
    path = _registered(_brief())
    base = hand_edit.copy_text(path)
    path.write_text(path.read_text().replace("Starting.", "Halfway there."))
    lemons_write = path.read_text()
    yours = base.replace("Starting.", "Paused by me.")

    outcome = hand_edit.apply(path, base, yours)

    assert isinstance(outcome, hand_edit.Conflicted)
    assert (
        "<<<<<<< your edit\nPaused by me.\n=======\nHalfway there.\n>>>>>>> the brief now\n"
        in outcome.text
    )
    assert "Halfway there." in outcome.theirs
    assert path.read_text() == lemons_write


def test_apply_says_nothing_changed_when_the_brief_already_has_the_edit():
    path = _registered(_brief())
    base = hand_edit.copy_text(path)
    path.write_text(path.read_text().replace("Starting.", "Halfway there."))
    yours = base.replace("Starting.", "Halfway there.")

    outcome = hand_edit.apply(path, base, yours)

    assert outcome == hand_edit.Applied("")


def test_apply_is_refused_when_the_edit_would_fail_brief_check():
    path = _registered(_brief())
    before = path.read_text()
    base = hand_edit.copy_text(path)
    yours = base.replace(f"{_PARENT}\n", "")

    outcome = hand_edit.apply(path, base, yours)

    assert isinstance(outcome, str)
    assert "Parent:" in outcome
    assert path.read_text() == before


def _editor(tmp_path, old: str, new: str) -> str:
    """An editor command that replaces *old* with *new* in the file it is given."""
    script = tmp_path / "editor.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import pathlib, sys
            path = pathlib.Path(sys.argv[1])
            path.write_text(path.read_text().replace({old!r}, {new!r}))
            """
        )
    )
    return f"{sys.executable} {script}"


def test_cmd_edit_saves_the_edit_and_tells_the_lemon(tmp_path, capsys):
    path = _registered(_brief())
    args = argparse.Namespace(
        lemon=str(path),
        editor=_editor(tmp_path, "Fix the flaky test.", "Fix every flaky test."),
    )

    hand_edit_cli.cmd_edit(args)

    assert "Fix every flaky test." in path.read_text()
    assert capsys.readouterr().out == "Saved task.md, and told its lemon what changed\n"
    [message] = _messages(path)
    assert "+Fix every flaky test.\n" in message


def test_cmd_edit_neither_writes_nor_tells_when_the_copy_is_unchanged(tmp_path, capsys):
    path = _registered(_brief())
    before = path.read_text()
    args = argparse.Namespace(lemon=str(path), editor=_editor(tmp_path, "x", "x"))

    hand_edit_cli.cmd_edit(args)

    assert path.read_text() == before
    assert capsys.readouterr().out == "No change\n"
    assert _messages(path) == []


def test_cmd_edit_keeps_the_copy_when_the_person_stops_at_a_conflict(tmp_path, monkeypatch, capsys):
    path = _registered(_brief())
    script = tmp_path / "editor.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import pathlib, sys
            brief = pathlib.Path({str(path)!r})
            brief.write_text(brief.read_text().replace("Starting.", "Halfway there."))
            copy = pathlib.Path(sys.argv[1])
            copy.write_text(copy.read_text().replace("Starting.", "Paused by me."))
            """
        )
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    args = argparse.Namespace(lemon=str(path), editor=f"{sys.executable} {script}")

    with pytest.raises(SystemExit):
        hand_edit_cli.cmd_edit(args)

    assert "Halfway there." in path.read_text()
    kept = capsys.readouterr().err.rsplit("Your edit is in ", 1)[1].strip()
    assert "<<<<<<< your edit\nPaused by me.\n" in Path(kept).read_text()


_FRONTMATTER_BRIEF = """---
type: Brief
created: { at: 2026-10-30T13:21:28-04:00, by: LaughAll }
responsible-parties:
  - Sam Person
contributors:
  - LaughAll
brief-id: LaughAll.reduce-costs
status: running
---
# Reduce costs

## Now

Starting.

## Goal

Spend less.

## Watching
"""


def test_copy_text_shows_frontmatter_fields_as_header_lines():
    path = _registered(_FRONTMATTER_BRIEF)

    copy = hand_edit.copy_text(path)

    assert copy.startswith(
        "# Reduce costs\n\nBrief-ID: LaughAll.reduce-costs\nStatus: running\n\n## Now\n"
    )


def test_apply_writes_a_header_line_edit_back_into_the_frontmatter():
    path = _registered(_FRONTMATTER_BRIEF)
    base = hand_edit.copy_text(path)
    yours = base.replace("Status: running\n", "Status: blocked\n")

    outcome = hand_edit.apply(path, base, yours)

    assert isinstance(outcome, hand_edit.Applied)
    text = path.read_text()
    assert "\nstatus: blocked\n" in text
    assert "Status:" not in text
    assert "responsible-parties:\n  - Sam Person\n" in text


def test_apply_numbers_the_diff_by_the_file_not_the_copy():
    path = _registered(_FRONTMATTER_BRIEF)
    base = hand_edit.copy_text(path)
    yours = base.replace("Spend less.\n", "Spend less.\nMeasure first.\n")

    outcome = hand_edit.apply(path, base, yours)

    added = path.read_text().splitlines().index("Measure first.") + 1
    assert isinstance(outcome, hand_edit.Applied)
    assert f"@@ -{added - 3},5 +{added - 3},6 @@" in outcome.diff


def test_cmd_edit_applies_nothing_when_the_editor_exits_with_an_error(
    tmp_path, monkeypatch, capsys
):
    path = _registered(_brief())
    before = path.read_text()
    script = tmp_path / "editor.py"
    script.write_text(
        textwrap.dedent(
            """
            import pathlib, sys
            copy = pathlib.Path(sys.argv[1])
            copy.write_text(copy.read_text().replace("Fix the flaky test.", "Unfinished goal."))
            sys.exit(1)
            """
        )
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    args = argparse.Namespace(lemon=str(path), editor=f"{sys.executable} {script}")

    with pytest.raises(SystemExit):
        hand_edit_cli.cmd_edit(args)

    assert path.read_text() == before
    assert _messages(path) == []
    err = capsys.readouterr().err
    assert "The editor exited with status 1, so nothing was applied." in err
    assert "Unfinished goal." in Path(err.rsplit("Your edit is in ", 1)[1].strip()).read_text()


_MARKER_EXAMPLE = "```text\n<<<<<<< example\nleft\n=======\nright\n>>>>>>> example\n```"


@pytest.mark.parametrize(
    ("old", "new", "expected_out"),
    [
        ("x", "x", "No change\n"),
        ("Starting.", "Halfway there.", "Saved task.md, and told its lemon what changed\n"),
    ],
    ids=["unchanged", "an unrelated line"],
)
def test_cmd_edit_accepts_a_brief_holding_literal_conflict_markers(
    tmp_path, capsys, old, new, expected_out
):
    path = _registered(_brief(goal=_MARKER_EXAMPLE))
    args = argparse.Namespace(lemon=str(path), editor=_editor(tmp_path, old, new))

    hand_edit_cli.cmd_edit(args)

    assert capsys.readouterr().out == expected_out
    assert _MARKER_EXAMPLE in path.read_text()


def test_copy_shows_an_empty_status_line_for_a_brief_without_one():
    path = _registered(_brief())

    assert "\nStatus:\n" in hand_edit.copy_text(path)


def test_apply_sets_a_status_typed_into_the_empty_line():
    path = _registered(_brief())
    base = hand_edit.copy_text(path)

    outcome = hand_edit.apply(path, base, base.replace("\nStatus:\n", "\nStatus: blocked\n"))

    assert isinstance(outcome, hand_edit.Applied)
    assert "status: blocked" in path.read_text()


def test_apply_leaves_the_brief_without_a_status_when_the_line_stays_empty():
    path = _registered(_brief())
    base = hand_edit.copy_text(path)

    outcome = hand_edit.apply(path, base, base.replace("Fix the flaky test.", "Fix it."))

    assert isinstance(outcome, hand_edit.Applied)
    assert "status" not in path.read_text().split("\n---\n")[0]


def test_apply_refuses_a_status_word_the_cli_would_not_set():
    path = _registered(_brief())
    before = path.read_text()
    base = hand_edit.copy_text(path)

    outcome = hand_edit.apply(path, base, base.replace("\nStatus:\n", "\nStatus: bogus\n"))

    assert isinstance(outcome, str) and "bogus" in outcome
    assert path.read_text() == before
