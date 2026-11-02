"""A Needs bullet that links to a document heading is explained by that section."""

import urllib.parse
from pathlib import Path

from lemonaid.brief import doc_warnings, linked_asks, now, questions, status

_DOC = """\
# Decisions

## Retry policy

Which one?

### Detail

Retries pile up.

## Rename the flag

Short.

```
## not a heading
```
"""


def _needs(bullet: str) -> str:
    return now.parse(
        status.split(f"# T\n\nStatus: blocked\n\n## Now\n\n### Needs\n\n{bullet}\n").now
    ).needs


def _link(vault: Path, heading: str) -> str:
    file = urllib.parse.quote(f"decisions#{heading}", safe="")
    return f"[{heading}](obsidian://open?vault={vault.name}&file={file})"


def test_a_section_runs_to_the_next_heading_of_its_level(tmp_path: Path):
    assert (
        linked_asks.section(_DOC, "retry policy") == "Which one?\n\n### Detail\n\nRetries pile up."
    )
    assert linked_asks.section(_DOC, "Rename the flag").startswith("Short.")
    assert linked_asks.section(_DOC, "missing") is None


def test_a_linked_bullet_gets_its_section_as_an_entry(tmp_path: Path):
    (tmp_path / "decisions.md").write_text(_DOC)
    needs = _needs(f"- {_link(tmp_path, 'Retry policy')}: which one?")

    [item] = questions.items(needs, {}, linked_asks.reader([tmp_path]))

    assert item.label == "Retry policy"
    assert item.entry.startswith("Which one?")
    assert questions.labels(needs, without="Retry policy") == []


def test_a_questions_entry_wins_over_the_link(tmp_path: Path):
    (tmp_path / "decisions.md").write_text(_DOC)
    needs = _needs(f"- {_link(tmp_path, 'Retry policy')}")

    [item] = questions.items(needs, {"Retry policy": "mine"}, linked_asks.reader([tmp_path]))

    assert item.entry == "mine"


def test_a_missing_heading_gives_no_entry_and_a_check_warning(tmp_path: Path):
    (tmp_path / "decisions.md").write_text(_DOC)
    brief = f"# T\n\nStatus: blocked\n\n## Now\n\n### Needs\n\n- {_link(tmp_path, 'Gone')}\n"

    assert (
        questions.items(_needs(f"- {_link(tmp_path, 'Gone')}"), {}, linked_asks.reader([tmp_path]))
        == ()
    )
    assert [w for w in doc_warnings.warnings(brief, [tmp_path]) if "no heading" in w]


def test_check_ignores_the_heading_when_matching_docs_rows(tmp_path: Path):
    (tmp_path / "decisions.md").write_text(_DOC)
    brief = (
        "# T\n\nStatus: blocked\n\n## Now\n\n### Needs\n\n"
        f"- {_link(tmp_path, 'Retry policy')}\n\n### Docs\n\n"
        "| Document | Purpose | Watch |\n| --- | --- | --- |\n"
        f"| [decisions]({tmp_path / 'decisions.md'}) | asks | Relay comments |\n"
    )

    assert doc_warnings.warnings(brief, [tmp_path]) == []


def test_a_heading_keeps_literal_trailing_hashes():
    assert linked_asks.section("## Use C#\n\nChoose one.\n", "Use C#") == "Choose one."
    assert linked_asks.section("## Use C ##\n\nChoose.\n", "Use C") == "Choose."


def test_a_longer_fence_is_not_closed_by_a_shorter_one():
    doc = "## Ask\n\n````markdown\n```python\n```\n## Fake heading\n````\n\nAfter.\n\n## Next\n"

    assert linked_asks.section(doc, "Ask").endswith("After.")


def test_parentheses_in_an_angle_bracket_destination_do_not_end_the_link():
    needs = "[Retry policy](</tmp/notes (draft).md#Retry policy>): which one?"

    [item] = questions.items(needs, {"Retry policy": "mine"}, lambda text: "linked")

    assert item.entry == "mine"


def test_a_linked_section_shows_highlights_without_comment_blocks(tmp_path: Path):
    (tmp_path / "decisions.md").write_text(
        '## Retry policy\n\nKeep {==the old one==}{{authorId="a" >>why?<<}} here.\\n'.replace(
            "\\n", "\n"
        )
        + '{{authorId="b" >>stray<<}}\n\nEnd.\n'
    )
    needs = _needs(f"- {_link(tmp_path, 'Retry policy')}: which one?")

    [item] = questions.items(needs, {}, linked_asks.reader([tmp_path]))

    assert "{" not in item.entry
    assert item.entry.startswith("Keep the old one here.")
    assert item.entry.endswith("End.")
