import pytest

from lemonaid.brief import migrate
from lemonaid.inbox.tui.rows import pr_numbers

from .shared import table


@pytest.mark.parametrize("promoted", [False, True])
def test_brieftable_controls_fallback(promoted: bool):
    def brief(*numbers: int) -> str:
        text = table(*numbers)
        return migrate.layout(text) if promoted else text

    assert pr_numbers.brief_numbers("## Now\n### Next\n- PR #12") == ()
    assert pr_numbers.brief_numbers(brief(12)) == (
        pr_numbers.PR("12", "https://github.com/owner/repo/pull/12"),
    )
    assert pr_numbers.brief_numbers(brief()) == ()
    assert pr_numbers.brief_numbers(brief(12, 13)) == (
        pr_numbers.PR("12", "https://github.com/owner/repo/pull/12"),
        pr_numbers.PR("13", "https://github.com/owner/repo/pull/13"),
    )
    assert pr_numbers.brief_numbers("## Now\n### PRs\nnot a table") == ()
    assert pr_numbers.brief_numbers("## PRs\nnot a table") == ()
    assert pr_numbers.brief_numbers("## Context\n" + table(12).replace("## Now\n", "")) == ()
    assert pr_numbers.brief_numbers(table(12) + "\n### PRs\n" + table(13)) == ()


def test_mixed_layout_tables_are_ambiguous():
    promoted = migrate.layout(table(13)).replace("## Now\n", "")
    assert pr_numbers.brief_numbers(table(12) + "\n" + promoted) == ()
    assert pr_numbers.brief_numbers(promoted + "\n" + promoted) == ()


def test_promoted_table_without_now():
    assert pr_numbers.brief_numbers(migrate.layout(table(12)).replace("## Now\n", "")) == (
        pr_numbers.PR("12", "https://github.com/owner/repo/pull/12"),
    )


def test_fencedtable_is_not_a_pr_section():
    assert pr_numbers.brief_numbers("## Now\n```\n### PRs\n```\n") == ()
    assert pr_numbers.brief_numbers("```\n" + migrate.layout(table(12)) + "```\n") == ()


def test_same_number_in_different_repositories_keeps_both_links():
    text = table(12, 13).replace("owner/repo/pull/13", "other/project/pull/12")
    assert pr_numbers.brief_numbers(text) == (
        pr_numbers.PR("12", "https://github.com/owner/repo/pull/12"),
        pr_numbers.PR("12", "https://github.com/other/project/pull/12"),
    )


def test_invalid_or_duplicate_row_does_not_show_partial_markers():
    assert pr_numbers.brief_numbers(table(12, 12)) == ()
    assert (
        pr_numbers.brief_numbers(table(12, 13).replace("owner/repo/pull/13", "example.org")) == ()
    )


@pytest.mark.parametrize("count", [3, 4, 20])
@pytest.mark.parametrize("promoted", [False, True])
def test_more_than_two_prs_have_no_marker(count, promoted):
    text = table(*range(1, count + 1))
    assert pr_numbers.brief_numbers(migrate.layout(text) if promoted else text) == ()
