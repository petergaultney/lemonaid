import datetime as dt
import re

import pytest

from lemonaid import rules_config
from lemonaid.inbox import db
from lemonaid.openclaw import sessions, turn_end
from lemonaid.rules import patterns, report, snapshot
from tests.rules import shared

KEY = "agent:main:signal:direct:uuid:abc"
QUIET = (re.compile(r"\(quiet\)"),)
NO_RULES = rules_config.RulesConfig()


def _row(status: str, created_at: float = 1.0) -> db.Notification:
    with db.connect() as conn:
        n = db.add(conn, channel=sessions.channel(KEY), message="hi")
        conn.execute(
            "UPDATE notifications SET status = ?, created_at = ? WHERE id = ?",
            (status, created_at, n.id),
        )
        conn.commit()
        return db.get(conn, n.id)


def _now(n: db.Notification) -> db.Notification:
    with db.connect() as conn:
        return db.get(conn, n.id)


@pytest.mark.parametrize("before", ["read", "unread"])
def test_a_finished_turn_leaves_its_row_unread_as_of_now(monkeypatch, before):
    n = _row(before)

    turn_end.settle(KEY, "Done, PR is up", QUIET, NO_RULES, failed=False)

    assert (_now(n).status, _now(n).created_at > 1.0) == ("unread", True)


@pytest.mark.parametrize("before", ["read", "unread"])
def test_a_turn_ending_with_an_auto_read_message_leaves_it_read_as_of_now(monkeypatch, before):
    n = _row(before)

    turn_end.settle(KEY, "(quiet) rearmed", QUIET, NO_RULES, failed=False)

    assert (_now(n).status, _now(n).created_at > 1.0) == ("read", True)


def test_a_failed_turn_is_unread_whatever_the_lemon_said_last(monkeypatch):
    n = _row("read")

    turn_end.settle(KEY, "(quiet) from the turn before", QUIET, NO_RULES, failed=True)

    assert _now(n).status == "unread"


def test_an_archived_row_stays_archived(monkeypatch):
    n = _row("archived")

    turn_end.settle(KEY, "Done", QUIET, NO_RULES, failed=False)

    assert (_now(n).status, _now(n).created_at) == ("archived", 1.0)


def test_a_snooze_held_through_turns_stays_and_wakes_unread(monkeypatch):
    n = _row("read")
    with db.connect() as conn:
        db.snooze(conn, n.id, 9e12)
        db.hold_snooze_through_turns(conn, n.id)

    turn_end.settle(KEY, "Done", QUIET, NO_RULES, failed=False)

    assert (_now(n).status, _now(n).snooze_prev_status) == ("snoozed", "unread")


def _rules(tmp_path, mode: str) -> rules_config.RulesConfig:
    source = shared.write(tmp_path / "patterns", {**shared.MERGE_ASK, "mode": mode})
    snapshot.promote(source, patterns.load(source).patterns, dt.datetime.now().astimezone())
    return rules_config.RulesConfig(source, "rules-desk")


@pytest.fixture
def sent(monkeypatch) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    monkeypatch.setattr(report, "send", lambda *each: found.append(each))
    return found


def test_a_report_pattern_reports_the_turn_and_tells_the_lemon_nothing(monkeypatch, tmp_path, sent):
    _row("read")

    turn_end.settle(
        KEY, "CI is green. Ready to merge?", (), _rules(tmp_path, "report"), failed=False
    )

    [(address, channel, text)] = sent
    assert (address, channel) == ("rules-desk", sessions.channel(KEY))
    assert f"- Transcript: OpenClaw session {KEY}" in text


def test_a_tell_pattern_tells_the_lemon_after_its_turn(monkeypatch, tmp_path, sent):
    _row("read")

    turn_end.settle(KEY, "CI is green. Ready to merge?", (), _rules(tmp_path, "tell"), failed=False)

    told = [each for each in sent if each[0] == sessions.channel(KEY)]
    [(_, _, text)] = told
    assert text.startswith("Your last turn's final message matches `merge-ask`")
    assert "Set the Status to merge and don't ask." in text
    assert text.endswith("If it didn't break the rule, there is nothing to do.")


def test_a_failed_turn_is_not_checked(monkeypatch, tmp_path, sent):
    _row("read")

    turn_end.settle(KEY, "CI is green. Ready to merge?", (), _rules(tmp_path, "tell"), failed=True)

    assert sent == []
