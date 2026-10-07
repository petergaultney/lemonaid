from lemonaid.inbox.tui import pr_numbers

from .shared import table


def test_brieftable_controls_fallback():
    assert pr_numbers.brief_number("## Now\n### Next\n- PR #12") is None
    assert pr_numbers.brief_number(table(12)) == pr_numbers.PR(
        "12", "https://github.com/owner/repo/pull/12"
    )
    assert pr_numbers.brief_number(table()) is None
    assert pr_numbers.brief_number(table(12, 13)) is None
    assert pr_numbers.brief_number("## Now\n### PRs\nnot a table") is None
    assert pr_numbers.brief_number("## Context\n" + table(12).replace("## Now\n", "")) is None
    assert pr_numbers.brief_number(table(12) + "\n### PRs\n" + table(13)) is None


def test_fencedtable_is_not_a_pr_section():
    assert pr_numbers.brief_number("## Now\n```\n### PRs\n```\n") is None
