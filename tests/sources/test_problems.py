import pytest

from lemonaid.sources import problems
from lemonaid.watch import delivery

NOTICE = "Slack is not signed in for your lemons; run `lemonaid slack signin`"


def _failing(message: str) -> None:
    raise delivery.Failed("Batch was not delivered")


def test_a_notice_whose_batch_failed_is_delivered_by_the_next_try(tmp_path):
    with pytest.raises(delivery.Failed):
        problems.tell_once(tmp_path, "slack", NOTICE, _failing)

    told: list[str] = []
    problems.tell_once(tmp_path, "slack", NOTICE, told.append)
    problems.tell_once(tmp_path, "slack", NOTICE, told.append)

    assert told == [NOTICE]


def test_a_sibling_scout_stays_quiet_while_another_delivers_the_notice(tmp_path):
    sibling: list[str] = []

    def deliver(message: str) -> None:
        problems.tell_once(tmp_path, "slack", message, sibling.append)  # the batch is still out

    problems.tell_once(tmp_path, "slack", NOTICE, deliver)
    problems.tell_once(tmp_path, "slack", NOTICE, sibling.append)

    assert sibling == []


def test_a_successful_call_makes_the_next_notice_news_again(tmp_path):
    told: list[str] = []
    problems.tell_once(tmp_path, "slack", NOTICE, told.append)

    problems.heard_again(tmp_path, "slack")
    problems.tell_once(tmp_path, "slack", NOTICE, told.append)

    assert told == [NOTICE, NOTICE]


def test_a_reworded_notice_in_the_same_lapse_is_not_news(tmp_path):
    told: list[str] = []
    problems.tell_once(tmp_path, "slack", NOTICE, told.append)

    problems.tell_once(
        tmp_path, "slack", "Slack is not signed in: ask your user to sign in", told.append
    )

    assert told == [NOTICE]
