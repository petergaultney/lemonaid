import dataclasses

from lemonaid.grove.source.blocks import main_first

from .shared import NOW, lemon


def test_a_hidden_reviewer_comes_after_its_author_even_when_older_and_in_a_lower_window():
    author = dataclasses.replace(lemon("claude:author", born=NOW), window="2")
    reviewer = dataclasses.replace(
        lemon("codex:reviewer", born=NOW - 3600), window="1", hidden=True
    )
    assert [m.channel for m in main_first([reviewer, author])] == [
        "claude:author",
        "codex:reviewer",
    ]


def test_among_visible_lemons_the_lower_window_comes_first():
    late = dataclasses.replace(lemon("claude:late", born=NOW - 3600), window="5")
    early = dataclasses.replace(lemon("claude:early", born=NOW), window="2")
    assert [m.channel for m in main_first([late, early])] == ["claude:early", "claude:late"]


def test_the_groups_lead_comes_first_on_its_tree():
    lead = dataclasses.replace(lemon("claude:lead", born=NOW), window="3")
    other = dataclasses.replace(lemon("claude:other", born=NOW - 3600), window="1")
    assert [m.channel for m in main_first([other, lead], "claude:lead")] == [
        "claude:lead",
        "claude:other",
    ]
