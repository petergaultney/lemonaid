"""The `### PRs` table: one row per PR, updated in place and removed by number or URL."""

import pytest

from lemonaid.brief import pr_table

_ONE = "https://github.com/o/lemonaid/pull/81"
_OTHER = "https://github.com/o/monorepo/pull/81"


def test_the_first_row_brings_the_header():
    assert pr_table.with_row([], _ONE, "Delivery service", None) == [
        "| Work | PR | Review |",
        "|---|---|---|",
        f"| Delivery service | [lemonaid#81]({_ONE}) | |",
    ]


def test_adding_a_pr_again_updates_its_row_and_keeps_its_review():
    body = pr_table.with_row([], _ONE, "Delivery", "[review doc](https://r)")

    updated = pr_table.with_row(body, _ONE, "Delivery service | v2", None)

    assert updated[2:] == [
        f"| Delivery service \\| v2 | [lemonaid#81]({_ONE}) | [review doc](https://r) |"
    ]


def test_a_number_two_repos_share_needs_the_url():
    body = pr_table.with_row(pr_table.with_row([], _ONE, "a", None), _OTHER, "b", None)

    with pytest.raises(ValueError, match="by its URL"):
        pr_table.without(body, "81")
    assert pr_table.without(body, _OTHER)[2:] == [f"| a | [lemonaid#81]({_ONE}) | |"]


def test_the_last_row_takes_the_table_with_it():
    assert pr_table.without(pr_table.with_row([], _ONE, "a", None), "#81") == []


def test_a_malformed_table_is_left_for_a_hand_fix():
    with pytest.raises(ValueError, match="by hand"):
        pr_table.with_row(["| Work | PR |", "| a | b |"], _ONE, "a", None)
