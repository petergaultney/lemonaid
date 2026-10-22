"""Consumer coverage for briefs whose progress sections have been promoted."""

import argparse

import pytest

from lemonaid.brief import (
    check,
    cli,
    doc_table,
    doc_warnings,
    lemon_table,
    migrate,
    now,
    nudge,
    questions,
    render,
    sections,
    status,
    target,
    waiters,
)
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.watch import needs_text, subscriptions, wait_requirements


@pytest.fixture
def brief(tmp_path):
    doc = tmp_path / "review.md"
    text = f"""# Task

Brief-ID: task.IndexElf
Status: blocked
Area: inbox

## Now

### Needs Sam

- Decision: choose a color

### Running

- build in work:3

### Waiting on

- reviewer

### Lemons

| Lemon | Purpose | Watch |
|---|---|---|
| child.IndexElf | review | merge, needs |

### Next

- apply the color

### PRs

| Work | PR | Review |
|---|---|---|
| Fix | [r#12](https://github.com/o/r/pull/12) | [review]({doc.as_uri()}) |

### Docs

| Document | Purpose | Watch |
|---|---|---|
| [review]({doc.as_uri()}) | Review | All edits |

### Done

- implemented

## Questions

### Decision

Pick blue or green.

## Goal

Keep the inbox useful.

## Executive Summary of Results

The lookup works.

## Watching

- `lemonaid watch file --wait {tmp_path / "source"}`
"""
    return migrate.layout(text), doc


def test_status_questions_and_progress_read_promoted_sections(brief):
    text, _ = brief
    parts = status.split(text)
    parsed = now.parse(parts.now)
    assert (parts.status, parts.area, parts.summary) == ("blocked", "inbox", "The lookup works.")
    assert parsed.needs == "- Decision: choose a color"
    assert parsed.running == "- build in work:3"
    assert parsed.waiting_on == "- reviewer"
    assert parsed.next == "- apply the color"
    assert parsed.done == "- implemented"
    assert questions.entries(parts.questions) == {"Decision": "Pick blue or green."}
    assert "Keep the inbox useful." in parts.rest


def test_card_reads_now_without_absorbing_promoted_sections(brief, tmp_path):
    text, _ = brief
    path = tmp_path / "brief.md"
    path.write_text(text)
    card = brief_cards.BriefCache().get(path)
    assert (card.status, card.area) == ("blocked", "inbox")
    assert card.needs == "Decision: choose a color"
    assert card.running == "build in work:3"
    assert card.waiting_on == "reviewer"


def test_renderer_used_by_popup_and_sidebar_includes_promoted_sections(brief, tmp_path):
    text, _ = brief
    path = tmp_path / "brief.md"
    path.write_text(text)
    out = render.markdown(
        target.Target([path], [], None, [], ""), 0, lambda *_: "open", expanded=True
    )
    for expected in ("apply the color", "implemented", "r#12", "Review", "reviewer", "#12 open"):
        assert expected in out
    assert "Pick blue or green." in out
    assert out.index("The lookup works.") < out.index("Decision")


def test_brief_show_cli_reads_promoted_sections(brief, tmp_path, capsys):
    text, _ = brief
    path = tmp_path / "brief.md"
    path.write_text(text)
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["brief", "show", "--file", str(path)])
    args.func(args)
    out = capsys.readouterr().out
    assert "apply the color" in out and "implemented" in out
    assert "https://github.com/o/r/pull/12" in out
    assert "Review" in out and "Decision" in out


def test_table_and_watcher_readers_keep_all_subscriptions(brief, tmp_path):
    text, doc = brief
    assert doc_table.rows(text) == [doc_table.Row(doc, "Review", doc_table.Watch.ALL_EDITS)]
    assert lemon_table.rows(text) == [
        lemon_table.Row("child.IndexElf", "review", ("merge", "needs"))
    ]
    reading = subscriptions.report(text, tmp_path)
    assert not reading.problems
    specs = {spec.key: spec for spec in reading.specs}
    assert not specs[("pr", ("o/r", "12"))].ci
    assert specs[("pr", ("o/r", "12"))].comments
    assert specs[("doc", (str(doc),))].edits
    assert specs[("briefs", ("task.IndexElf",))].lemons == tuple(lemon_table.rows(text))
    assert ("file", (str(tmp_path / "source"),)) in specs
    assert wait_requirements.needs_unified(text, False)
    assert waiters.commands(text) == [f"lemonaid watch file --wait {tmp_path / 'source'}"]
    assert needs_text.needs(text) == "Decision: choose a color"


def test_checks_and_answer_nudges_read_the_promoted_brief(brief, tmp_path):
    text, doc = brief
    assert check.structure(text) == []
    assert check.warnings(text) == []
    assert check.question_problems(text) == []
    assert doc_warnings.warnings(text, [tmp_path]) == []
    assert str(doc) in doc_warnings.warnings(text.replace("## Docs", "## Unlisted"), [tmp_path])[0]
    assert '"Decision"' in nudge.note(text)
    assert 'This answers "Decision"' in nudge.after_answer(text, "Decision")


@pytest.mark.parametrize("heading", ["PRs", "Docs"])
def test_promoted_table_alone_requires_unified_watching(brief, tmp_path, heading):
    from_text, _ = brief
    section = sections.find(from_text, heading)
    text = f"# Task\n\n## {heading}\n\n" + "\n".join(sections.body(from_text, section))
    assert wait_requirements.needs_unified(text, False)
    kinds = {spec.kind for spec in subscriptions.read(text, tmp_path)}
    assert ("pr" if heading == "PRs" else "doc") in kinds
