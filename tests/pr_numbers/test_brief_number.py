from lemonaid.inbox.tui import pr_numbers

from .shared import table


def test_brieftable_controls_fallback():
    assert pr_numbers.brief_number("## Now\n### Next\n- PR #12") == ""
    assert pr_numbers.brief_number(table(12)) == "12"
    assert pr_numbers.brief_number(table()) == ""
    assert pr_numbers.brief_number(table(12, 13)) == ""
    assert pr_numbers.brief_number("## Now\n### PRs\nnot a table") == ""
    assert pr_numbers.brief_number("## Context\n" + table(12).replace("## Now\n", "")) == ""
    assert pr_numbers.brief_number(table(12) + "\n### PRs\n" + table(13)) == ""


def test_fencedtable_is_not_a_pr_section():
    assert pr_numbers.brief_number("## Now\n```\n### PRs\n```\n") == ""
