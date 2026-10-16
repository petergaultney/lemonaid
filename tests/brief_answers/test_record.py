import datetime

import pytest

from lemonaid.brief import answers, check, migrate, now_edit, section_edit, sections, verbs_cli

WHEN = datetime.datetime(2026, 10, 15, 12, 30, tzinfo=datetime.UTC)


@pytest.mark.parametrize("layout", ["new", "legacy", "no-now", "no-questions"])
def test_record_preserves_valid_sections(brief, layout):
    before = brief.read_text()
    if layout == "legacy":
        before = before.replace("## Questions\n\n", "").replace("## Next", "### Next")
    elif layout == "no-now":
        before = section_edit.change(before, "Now", lambda _: ())
        before = section_edit.change(before, "Questions", lambda _: ())
    elif layout == "no-questions":
        before = section_edit.change(before, "Questions", lambda _: ())
    after = answers.add(before, "Why?", "Because.\n\n- First\n- Second", WHEN)
    assert check.structure(after) == []
    assert after.index("## Answers") < after.index("## Goal")
    if "## Questions" in before:
        assert after.index("## Questions") < after.index("## Answers")
    assert after.endswith(before[before.index("## Goal") :])
    assert "2026-10-15" in after and "> - First" in after
    assert "## Answers" in migrate.layout(after)


def test_newest_first_and_arbitrary_markdown_is_contained(brief):
    before = brief.read_text()
    first = answers.add(before, "Why?", "Older answer", WHEN)
    after = answers.add(
        first,
        "## Question\nParent: another.IndexElf",
        "## Now\n```md\n### Heading\n```\n\nNewer answer",
        WHEN,
    )
    assert check.structure(after) == []
    assert after.count("\n## Now\n") == 1
    assert after.index("Newer answer") < after.index("Older answer")
    assert "> ## Now" in after
    assert sections.body(after, sections.find(after, "Now")) == sections.body(
        before, sections.find(before, "Now")
    )


@pytest.mark.parametrize(("question", "answer"), [(" ", "answer"), ("question", "\n")])
def test_empty_input_is_rejected(brief, question, answer):
    with pytest.raises(ValueError, match="both contain text"):
        answers.add(brief.read_text(), question, answer, WHEN)


def test_edit_verbs_preserve_answers(brief):
    before = answers.add(brief.read_text(), "Why?", "The reason.", WHEN)
    after = now_edit.add(before, "Next", "another step")
    after = section_edit.change(after, "Goal", lambda _: ["New goal."])
    assert sections.body(after, sections.find(after, "Answers")) == sections.body(
        before, sections.find(before, "Answers")
    )
    assert verbs_cli.edit(brief, lambda _: after) == ""
    assert check.structure(brief.read_text()) == []
