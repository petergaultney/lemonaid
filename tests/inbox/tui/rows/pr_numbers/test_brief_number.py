import pytest

from lemonaid.brief import migrate
from lemonaid.inbox.tui.rows import pr_numbers

from .shared import table


@pytest.mark.parametrize("promoted", [False, True])
def test_brieftable_controls_fallback(promoted: bool):
    def brief(*numbers: int) -> str:
        text = table(*numbers)
        return migrate.layout(text) if promoted else text

    assert pr_numbers.brief_number("## Now\n### Next\n- PR #12") is None
    assert pr_numbers.brief_number(brief(12)) == pr_numbers.PR(
        "12", "https://github.com/owner/repo/pull/12"
    )
    assert pr_numbers.brief_number(brief()) is None
    assert pr_numbers.brief_number(brief(12, 13)) is None
    assert pr_numbers.brief_number("## Now\n### PRs\nnot a table") is None
    assert pr_numbers.brief_number("## PRs\nnot a table") is None
    assert pr_numbers.brief_number("## Context\n" + table(12).replace("## Now\n", "")) is None
    assert pr_numbers.brief_number(table(12) + "\n### PRs\n" + table(13)) is None


def test_mixed_layout_tables_are_ambiguous():
    promoted = migrate.layout(table(13)).replace("## Now\n", "")
    assert pr_numbers.brief_number(table(12) + "\n" + promoted) is None
    assert pr_numbers.brief_number(promoted + "\n" + promoted) is None


def test_promoted_table_without_now():
    assert pr_numbers.brief_number(migrate.layout(table(12)).replace("## Now\n", "")) == (
        pr_numbers.PR("12", "https://github.com/owner/repo/pull/12")
    )


def test_fencedtable_is_not_a_pr_section():
    assert pr_numbers.brief_number("## Now\n```\n### PRs\n```\n") is None
    assert pr_numbers.brief_number("```\n" + migrate.layout(table(12)) + "```\n") is None
