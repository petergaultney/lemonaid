"""The end-of-turn check, as lemonaid's Stop hook runs it in either harness."""

import datetime as dt
import json
import logging
import os
import time
from pathlib import Path

import pytest

from lemonaid import brief
from lemonaid.inbox import db
from lemonaid.rules import end_of_turn, hits, patterns, report, snapshot
from tests.rules import shared

_THREAD = "01a20000-1111-7222-8333-444455556666"
_CLAUDE = "abcd1234-0000-0000-0000-000000000000"


@pytest.fixture
def sent(monkeypatch) -> list[tuple[str, str, str]]:
    """(address, channel, text) of each report, instead of starting `lemonaid tell`."""
    found: list[tuple[str, str, str]] = []
    monkeypatch.setattr(report, "send", lambda *each: found.append(each))
    return found


def _live(tmp_path: Path, *fields: dict, report_to: str = "rules-desk") -> Path:
    source = shared.write(tmp_path / "patterns", *fields)
    snapshot.promote(source, patterns.load(source).patterns, dt.datetime.now().astimezone())
    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), source, report_to)
    return source


def _codex(said: str, **extra) -> dict:
    return {
        "session_id": _THREAD,
        "hook_event_name": "Stop",
        "cwd": "/work/repo",
        "transcript_path": "/work/rollout.jsonl",
        "stop_hook_active": False,
        "last_assistant_message": said,
        **extra,
    }


def _logged() -> list[dict]:
    return [json.loads(line) for line in hits.path().read_text().splitlines()]


def test_a_report_pattern_reports_without_telling_the_lemon(tmp_path, sent):
    _live(tmp_path, shared.MERGE_ASK)

    assert end_of_turn.reason_to_block(_codex("CI is green. Ready to merge?"), "codex") == ""

    [(address, channel, text)] = sent
    assert (address, channel) == ("rules-desk", f"codex:{_THREAD}")
    assert "`merge-ask` matched the end of a lemon's turn" in text
    assert "- Rule: the one starting '- **A PR ready to merge'" in text
    assert "- Mode: report (the lemon was not told)" in text
    assert "- Working directory: /work/repo" in text
    assert "- Transcript: /work/rollout.jsonl" in text
    assert "> CI is green. **Ready to merge?**" in text


def test_a_tell_pattern_also_tells_the_lemon_the_rule_read_fresh(tmp_path, sent):
    source = _live(tmp_path, {**shared.MERGE_ASK, "mode": "tell"})
    rules = source.parent / "rules.md"
    rules.write_text(rules.read_text().replace("Nothing else", "Nothing more"))

    reason = end_of_turn.reason_to_block(_codex("Want me to merge it?"), "codex")

    assert reason.startswith("Your final message matches `merge-ask`")
    assert "> - **A PR ready to merge gets the merge Status.** Nothing more" in reason
    assert ">   The user merges from the Status." in reason
    assert "Set the Status to merge and don't ask." in reason
    assert "- Mode: tell (the lemon was told the rule)" in sent[0][2]


def test_a_claude_lemon_is_checked_by_its_last_message(tmp_path, sent):
    _live(tmp_path, shared.REVIEWER_ASK)

    end_of_turn.reason_to_block(
        {"session_id": _CLAUDE, "cwd": "/w", "last_assistant_message": "Start a reviewer?"},
        "claude",
    )

    assert [channel for _, channel, _ in sent] == ["claude:abcd1234"]


def test_repeats_are_logged_but_reported_once(tmp_path, sent):
    _live(tmp_path, shared.MERGE_ASK)

    for _ in range(2):
        end_of_turn.reason_to_block(_codex("Ready to merge?"), "codex")

    assert len(sent) == 1
    assert [entry["outcome"] for entry in _logged()] == [hits.REPORTED, hits.REPEAT]


def test_without_a_report_address_matches_are_only_logged(tmp_path, sent):
    _live(tmp_path, {**shared.MERGE_ASK, "mode": "tell"}, report_to="")

    assert end_of_turn.reason_to_block(_codex("Ready to merge?"), "codex")
    assert sent == []
    assert [entry["outcome"] for entry in _logged()] == [hits.LOGGED]


def test_the_report_address_s_own_session_is_not_checked(tmp_path, sent):
    desk = brief.store.briefs_dir() / "desk.md"
    desk.parent.mkdir(parents=True, exist_ok=True)
    desk.write_text("# desk\n")
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "", metadata={"session_id": _CLAUDE})
        brief.attached.attach(conn, "claude:abcd1234", desk)
    _live(tmp_path, shared.MERGE_ASK, report_to="desk")

    said = {"session_id": _CLAUDE, "cwd": "/w", "last_assistant_message": "Ready to merge?"}

    assert end_of_turn.reason_to_block(said, "claude") == ""
    assert sent == []
    assert not hits.path().exists()


def test_a_pattern_limited_to_a_directory_skips_others(tmp_path, sent):
    _live(tmp_path, {**shared.MERGE_ASK, "cwd": "/work/other/*"})

    end_of_turn.reason_to_block(_codex("Ready to merge?"), "codex")
    end_of_turn.reason_to_block(_codex("Ready to merge?", cwd="/work/other/a/b"), "codex")

    assert [entry["cwd"] for entry in _logged()] == ["/work/other/a/b"]


def test_only_the_last_20_kb_of_a_message_is_read(tmp_path, sent):
    _live(tmp_path, shared.MERGE_ASK)

    end_of_turn.reason_to_block(_codex("Ready to merge? " + "x" * 21 * 1024), "codex")

    assert sent == []


def test_nothing_is_checked_until_the_config_names_the_promoted_file(tmp_path, sent):
    _live(tmp_path, shared.MERGE_ASK)
    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), None, "rules-desk")

    assert end_of_turn.reason_to_block(_codex("Ready to merge?"), "codex") == ""

    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), tmp_path / "elsewhere.toml")

    assert end_of_turn.reason_to_block(_codex("Ready to merge?"), "codex") == ""
    assert sent == []


def test_a_fault_lets_the_turn_end_and_logs_one_line(tmp_path, sent, caplog):
    _live(tmp_path, {**shared.MERGE_ASK, "mode": "tell"})
    snapshot.path().write_text("{not json")
    logging.getLogger("lemonaid").addHandler(caplog.handler)
    try:
        assert end_of_turn.reason_to_block(_codex("Ready to merge?"), "codex") == ""
    finally:
        logging.getLogger("lemonaid").removeHandler(caplog.handler)

    [line] = [record.getMessage() for record in caplog.records]
    assert line.startswith("rule check skipped: JSONDecodeError")


_SLOW = [
    {**shared.REVIEWER_ASK, "id": "overlapping", "regex": r"(a|aa)+$", "match": ["aa"]},
    {**shared.REVIEWER_ASK, "id": "adjacent", "regex": r"a*a*a*a*a*b", "match": ["ab"]},
]
_BACKTRACKS = "a" * 10000 + "! Ready to merge?"


def test_a_pattern_that_backtracks_is_stopped_and_the_rest_still_run(
    tmp_path, sent, monkeypatch, caplog
):
    monkeypatch.setattr(end_of_turn, "_SEARCH_SECONDS", 0.05)
    _live(tmp_path, *_SLOW, shared.MERGE_ASK)
    logging.getLogger("lemonaid").addHandler(caplog.handler)
    started = time.monotonic()
    try:
        end_of_turn.reason_to_block(_codex(_BACKTRACKS), "codex")
    finally:
        logging.getLogger("lemonaid").removeHandler(caplog.handler)

    assert time.monotonic() - started < 1
    assert [entry["pattern"] for entry in _logged()] == ["merge-ask"]
    assert [r.getMessage() for r in caplog.records if r.getMessage().startswith("skipped")] == [
        "skipped overlapping, out of time on a final message in /work/repo",
        "skipped adjacent, out of time on a final message in /work/repo",
    ]


def test_once_the_budget_is_spent_the_remaining_patterns_are_skipped(tmp_path, sent, monkeypatch):
    monkeypatch.setattr(end_of_turn, "_SEARCH_SECONDS", 0.05)
    monkeypatch.setattr(end_of_turn, "_BUDGET", 0.08)
    _live(tmp_path, *_SLOW, shared.MERGE_ASK)
    started = time.monotonic()

    assert end_of_turn.reason_to_block(_codex(_BACKTRACKS), "codex") == ""

    assert time.monotonic() - started < 1
    assert sent == []
