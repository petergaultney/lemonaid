"""An OpenClaw lemon's turns as reports from its plugin arrive, in whatever order they do."""

import pytest

from lemonaid.inbox import db
from lemonaid.openclaw import run_records, sessions

KEY = "agent:main:x"


@pytest.fixture
def conn():
    with db.connect() as conn:
        db.add(conn, channel=sessions.channel(KEY), message="hi")
        yield conn


def _turn(conn) -> tuple:
    row = db.get_by_channel(conn, sessions.channel(KEY), unread_only=False)
    assert row is not None
    return row.turn_at, row.metadata.get("turn_run"), row.metadata.get("turn_started_at")


def test_a_late_end_of_the_turn_before_leaves_the_running_one_running(conn):
    run_records.running(conn, KEY, "r1", 100.0)
    run_records.running(conn, KEY, "r2", 102.0)

    assert run_records.ended(conn, KEY, "r1", 101.0) == 0
    assert _turn(conn) == (102.0, "r2", 102.0)


def test_a_late_end_without_a_run_from_before_the_turn_started_is_ignored(conn):
    run_records.running(conn, KEY, "r2", 102.0)

    assert run_records.ended(conn, KEY, "", 101.0) == 0
    assert _turn(conn)[0] == 102.0


def test_a_late_report_without_a_run_doesnt_reopen_a_turn_that_ended(conn):
    run_records.running(conn, KEY, "r1", 100.0)
    run_records.ended(conn, KEY, "r1", 102.0)

    run_records.running(conn, KEY, "", 101.0)

    assert _turn(conn)[0] is None


def test_a_report_without_a_run_renews_the_turn_running(conn):
    run_records.running(conn, KEY, "r1", 100.0)

    run_records.running(conn, KEY, "", 160.0)

    assert _turn(conn) == (160.0, "r1", 100.0)


def test_a_send_recorded_after_its_turn_was_reported_changes_nothing(conn):
    run_records.running(conn, KEY, "r1", 102.0)

    assert run_records.sent(conn, KEY, 100.0) == 0
    assert _turn(conn) == (102.0, "r1", 102.0)


def test_an_end_whose_start_was_missed_still_ends_the_turn_the_scout_sent(conn):
    run_records.sent(conn, KEY, 100.0)

    assert run_records.ended(conn, KEY, "r1", 105.0) == 1
    assert _turn(conn)[0] is None


def test_a_late_start_of_the_turn_before_leaves_the_running_one_to_end(conn):
    run_records.running(conn, KEY, "r2", 102.0)

    assert run_records.running(conn, KEY, "r1", 100.0) == 0
    assert run_records.ended(conn, KEY, "r1", 101.0) == 0
    assert _turn(conn) == (102.0, "r2", 102.0)
    assert run_records.ended(conn, KEY, "r2", 103.0) == 1


def test_a_renewal_that_arrives_after_a_later_one_changes_nothing(conn):
    run_records.running(conn, KEY, "r1", 100.0)
    run_records.running(conn, KEY, "r1", 220.0)

    assert run_records.running(conn, KEY, "r1", 160.0) == 0
    assert _turn(conn) == (220.0, "r1", 100.0)
