"""Matching a brief's `## Questions` entries to the Needs bullets that ask them."""

import argparse
from pathlib import Path

from lemonaid.brief import check, cli, now, questions, status

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


def test_a_heading_matches_the_first_line_of_a_multiline_needs_bullet():
    needs = "- merge #12\n  - CI is green"
    explained = {"merge #12": "- **Context:** merge is ready."}

    assert questions.items(needs, explained) == (
        questions.Item("merge #12\n  - CI is green", "merge #12", explained["merge #12"]),
    )
    assert questions.unmatched(needs, explained) == ()


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


def test_show_prints_questions_by_default_and_warns_about_unmatched_entries(tmp_path, capsys):
    brief = tmp_path / "ship.md"
    brief.write_text(_BRIEF)

    plain = _show(brief, capsys)
    explicit = _show(brief, capsys, "--questions")
    compact = _show(brief, capsys, "--no-questions")

    assert plain == explicit
    assert "> - Mark #5836 ready\n>\n>   - **Context:** CI is green." in plain
    assert "▶" not in plain
    assert "**Unmatched Questions:** `### a question no bullet asks`" in plain
    assert "Context" not in compact and "Mark #5836 ready" in compact
    assert "**Unmatched Questions:** `### a question no bullet asks`" in compact


def test_unmatched_questions_show_even_without_needs(tmp_path, capsys):
    brief = tmp_path / "orphan.md"
    brief.write_text(
        "# Orphan\n\nStatus: working\n\n## Questions\n\n### Who owns it\n\n- Context\n"
    )

    assert "**Unmatched Questions:** `### Who owns it`" in _show(brief, capsys)


def test_check_names_unmatched_questions_but_accepts_matched_ones():
    matched = _BRIEF.replace("### a question no bullet asks\n\n- **Context:** stale.\n\n", "")

    assert check.structure(matched) == []
    assert check.structure(_BRIEF) == [
        "`### a question no bullet asks` in ## Questions has no matching bullet "
        "under ### Needs Peter"
    ]


def test_multiline_needs_bullet_expands_without_a_warning(tmp_path, capsys):
    brief = tmp_path / "multiline.md"
    brief.write_text(
        "# Merge\n\nStatus: blocked\n\n## Now\n\n### Needs Peter\n\n"
        "- merge #12\n  - CI is green\n\n## Questions\n\n"
        "### merge #12\n\n- **Context:** merge is ready.\n"
    )

    shown = _show(brief, capsys)
    assert "> - merge #12\n>   - CI is green\n>\n>   - **Context:** merge is ready." in shown
    assert "Unmatched Questions" not in shown
    assert check.structure(brief.read_text()) == []


def test_a_brief_without_questions_shows_as_it_did(tmp_path, capsys):
    brief = tmp_path / "old.md"
    brief.write_text(
        "# Old\n\nStatus: blocked\n\n## Now\n\n- Needs Peter: pick one\n- Next: build\n"
    )

    assert _show(brief, capsys, "--questions") == _show(brief, capsys)
    assert _show(brief, capsys, "--no-questions") == _show(brief, capsys)
    assert "> **Needs Peter:** pick one" in _show(brief, capsys)
