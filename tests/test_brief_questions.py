"""Matching a brief's `## Questions` entries to the Needs bullets that ask them."""

import argparse
from pathlib import Path

from lemonaid.brief import cli, now, questions, status

_BRIEF = """\
# Ship it

Status: blocked

## Now

### Needs Peter

- **render timeouts owner:** who fixes the rebuild?
  - it runs every 10 minutes
- Mark #5836 ready
- an aside nobody explains

### Next

- the follow-up

## Questions

### Render timeouts owner

- **Context:** the menu rebuilds in the request.
- **Options:** a new place, or hand it on.

### mark #5836 ready

- **Context:** CI is green.

### a question no bullet asks

- **Context:** stale.

Parent: hq, 2026-09-30

## Goal

Done.
"""


def test_an_entry_explains_the_bullet_whose_label_it_names():
    parts = status.split(_BRIEF)
    found = questions.items(now.parse(parts.now).needs, questions.entries(parts.questions))

    assert [(item.label, item.entry.splitlines()[0] if item.entry else "") for item in found] == [
        ("Render timeouts owner", "- **Context:** the menu rebuilds in the request."),
        ("mark #5836 ready", "- **Context:** CI is green."),
        ("", ""),
    ]
    assert found[0].text == (
        "**render timeouts owner:** who fixes the rebuild?\n  - it runs every 10 minutes"
    )


def test_a_label_must_be_the_whole_bullet_or_end_at_a_colon():
    explained = {"Mark": "body"}

    assert questions.items("- Mark #5836 ready", explained) == ()
    assert questions.items("- Mark: #5836", explained)[0].label == "Mark"


def test_needs_written_as_a_paragraph_is_one_item():
    assert questions.items("Pick a retry policy", {"pick a retry policy": "x"}) == (
        questions.Item("Pick a retry policy", "pick a retry policy", "x"),
    )


def test_questions_stay_out_of_the_rest_of_the_brief():
    parts = status.split(_BRIEF)

    assert parts.questions.startswith("### Render timeouts owner")
    assert "a question no bullet asks" in parts.questions
    assert "Questions" not in parts.rest and "Context" not in parts.rest
    assert parts.rest.startswith("Parent: hq") and "## Goal" in parts.rest


def _show(path: Path, capsys, *flags: str) -> str:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["brief", "show", "--file", str(path), *flags])
    args.func(args)
    return capsys.readouterr().out


def test_show_prints_entries_only_when_asked(tmp_path, capsys):
    brief = tmp_path / "ship.md"
    brief.write_text(_BRIEF)

    plain = _show(brief, capsys)
    expanded = _show(brief, capsys, "--questions")

    assert "Context" not in plain and "Mark #5836 ready" in plain
    assert "> - Mark #5836 ready\n>\n>   - **Context:** CI is green." in expanded
    assert "▶" not in expanded and "a question no bullet asks" not in expanded


def test_a_brief_without_questions_shows_as_it_did(tmp_path, capsys):
    brief = tmp_path / "old.md"
    brief.write_text(
        "# Old\n\nStatus: blocked\n\n## Now\n\n- Needs Peter: pick one\n- Next: build\n"
    )

    assert _show(brief, capsys, "--questions") == _show(brief, capsys)
    assert "> **Needs Peter:** pick one" in _show(brief, capsys)
