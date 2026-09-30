"""A finished turn whose final message matches `[inbox] auto_read` leaves its row read."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from lemonaid import auto_read, for_lemons
from lemonaid.claude import notify as claude_notify
from lemonaid.codex import notify as codex_notify
from lemonaid.config import load_config
from lemonaid.inbox import db
from lemonaid.lemon_watchers import watcher
from lemonaid.openclaw import watcher as openclaw_watcher
from lemonaid.opencode import notify as opencode_notify
from lemonaid.opencode import watcher as opencode_watcher

_A_MINUTE_AGO = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
_THREAD = "01a03bff-a7bb-77a2-9b4d-d63cfe32fd00"


@pytest.fixture
def quiet_config():
    with open(os.environ["LEMONAID_CONFIG"], "w") as f:
        f.write("[inbox]\nauto_read = ['^\\(quiet\\)', '^\\(fyi\\)']\n")


def _status(channel: str) -> str:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return row.status


def _codex_turn(said: str | None, notification_type: str = "agent-turn-complete") -> None:
    payload = {"type": notification_type, "cwd": "/tmp", "thread-id": _THREAD}
    if said is not None:
        payload["last-assistant-message"] = said
    codex_notify.handle_notification(json.dumps(payload))


def test_matching_is_anchored_at_the_start():
    patterns = auto_read.compile_patterns([r"\(quiet\)"])

    assert auto_read.matching(patterns, "  (quiet)")
    assert auto_read.matching(patterns, "done. (quiet)") is None
    assert auto_read.matching(patterns, "") is None


def test_invalid_patterns_are_reported_and_skipped(capsys):
    with open(os.environ["LEMONAID_CONFIG"], "w") as f:
        f.write("[inbox]\nauto_read = ['^ok', '(unclosed', 3]\n")

    patterns = load_config().inbox.auto_read

    assert [p.pattern for p in patterns] == ["^ok"]
    err = capsys.readouterr().err
    assert "(unclosed" in err
    assert "3" in err


def test_no_patterns_by_default():
    assert load_config().inbox.auto_read == ()


@pytest.mark.usefixtures("quiet_config")
def test_codex_turn_ending_quietly_is_read():
    _codex_turn("(quiet)")

    assert _status(f"codex:{_THREAD}") == "read"


@pytest.mark.usefixtures("quiet_config")
@pytest.mark.parametrize("said", ["Need your call on X.", "", None])
def test_codex_turn_without_a_match_is_unread(said):
    _codex_turn(said)

    assert _status(f"codex:{_THREAD}") == "unread"


@pytest.mark.usefixtures("quiet_config")
def test_a_permission_prompt_is_never_auto_read():
    _codex_turn("(quiet)", notification_type="approval-requested")

    assert _status(f"codex:{_THREAD}") == "unread"


@pytest.mark.usefixtures("quiet_config")
def test_a_later_quiet_turn_reads_a_row_marked_unread():
    _codex_turn("Need your call on X.")
    _codex_turn("(fyi) pushed")

    assert _status(f"codex:{_THREAD}") == "read"


def _claude_stop(tmp_path, *entries: dict, hook: str = "Stop") -> str:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    claude_notify.handle_notification(
        json.dumps(
            {
                "session_id": "c1a2b3c4d5",
                "cwd": str(tmp_path),
                "transcript_path": str(transcript),
                "hook_event_name": hook,
            }
        )
    )
    return _status("claude:c1a2b3c4")


def _claude_prompt(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def _claude_said(*blocks: dict, message_id: str = "msg_final") -> dict:
    return {"type": "assistant", "message": {"id": message_id, "content": list(blocks)}}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


@pytest.mark.usefixtures("quiet_config")
@pytest.mark.parametrize("hook", ["Stop", "idle_prompt"])
def test_claude_reads_the_final_message_from_its_transcript(tmp_path, hook):
    status = _claude_stop(
        tmp_path,
        _claude_prompt("go"),
        _claude_said(_text("Working on it."), message_id="msg_1"),
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        _claude_said({"type": "thinking", "thinking": "..."}),
        _claude_said(_text("(quiet)")),
        {"type": "attachment"},
        hook=hook,
    )

    assert status == "read"


_IMAGE_PROMPT = {"type": "user", "message": {"content": [{"type": "image", "source": {}}]}}
_TOOL_USE = {"type": "tool_use", "name": "Bash", "input": {}}


@pytest.mark.usefixtures("quiet_config")
@pytest.mark.parametrize(
    "turn",
    [
        [_claude_prompt("and now?"), _claude_said(_TOOL_USE)],
        [_IMAGE_PROMPT],
        [_IMAGE_PROMPT, _claude_said(_TOOL_USE)],
        [_claude_said(_text("(quiet) first"), message_id="msg_2"), _claude_said(_TOOL_USE)],
    ],
    ids=["tool-only", "image-prompt", "image-prompt-then-tool", "quiet-text-then-tool"],
)
def test_claude_turn_not_ending_in_text_is_unread(tmp_path, turn):
    status = _claude_stop(tmp_path, _claude_said(_text("(quiet)"), message_id="msg_1"), *turn)

    assert status == "unread"


@pytest.mark.parametrize(
    "parts",
    [
        [("assistant", "m1", "text", "(quiet)"), ("user", "m2", "file", "")],
        [("assistant", "m1", "text", "(quiet)"), ("assistant", "m2", "tool", "")],
    ],
    ids=["file-prompt", "tool-only-message"],
)
def test_opencode_final_message_stays_in_the_final_message(parts):
    entries = [
        {"role": role, "part": {"type": kind, "text": text, "messageID": message}}
        for role, message, kind, text in parts
    ]

    assert opencode_watcher.final_message(reversed(entries)) == ""


def test_openclaw_final_message_stays_in_the_final_message():
    def said(*content: dict) -> dict:
        return {"type": "message", "message": {"role": "assistant", "content": list(content)}}

    entries = [said({"type": "text", "text": "(quiet)"}), said({"type": "toolCall", "name": "x"})]

    assert openclaw_watcher.final_message(reversed(entries)) == ""


@pytest.mark.usefixtures("quiet_config")
def test_opencode_idle_reads_its_last_text_part(monkeypatch):
    parts = [
        {"role": "user", "part": {"type": "text", "text": "go", "messageID": "m1"}},
        {"role": "assistant", "part": {"type": "text", "text": "(quiet)", "messageID": "m2"}},
        {"role": "assistant", "part": {"type": "step-finish", "reason": "stop", "messageID": "m2"}},
    ]
    monkeypatch.setattr(opencode_watcher, "get_session_path", lambda *_: "db#ses_1")
    monkeypatch.setattr(opencode_watcher, "read_lines", lambda _: [json.dumps(p) for p in parts])
    monkeypatch.setattr(opencode_notify, "get_cwd_and_name", lambda _: ("/tmp", "x"))

    opencode_notify.handle_notification(
        json.dumps({"type": "session.idle", "properties": {"sessionID": "ses_1"}})
    )

    assert _status("opencode:ses_1") == "read"


def _poll_once(monkeypatch, **callbacks) -> None:
    def finish_poll(_seconds):
        raise StopIteration

    monkeypatch.setattr(watcher.time, "sleep", finish_poll)
    with pytest.raises(StopIteration):
        watcher.unified_watch_loop(
            [openclaw_watcher],
            lambda: [
                (row.channel, "abc", "/tmp", row.created_at, row.status == "unread", None, "", None)
                for row in [_row("openclaw:abc")]
            ],
            poll_interval=0,
            **callbacks,
        )


def _row(channel: str) -> db.Notification:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return row


def test_a_manual_unread_outlasts_the_quiet_turn_that_read_it(tmp_path, monkeypatch):
    """Marking a session unread after an auto-read turn keeps it unread until a later turn."""
    _openclaw_session(tmp_path, monkeypatch, "(quiet)")
    with db.connect() as conn:
        db.add(conn, channel="openclaw:abc", message="m", created_at=0.0, status="read")

    def connected(fn):
        def call(*args):
            with db.connect() as conn:
                return fn(conn, *args)

        return call

    callbacks = {
        "mark_read": connected(db.mark_all_read_for_channel),
        "update_message": connected(db.update_message),
        "mark_unread": connected(db.mark_unread_for_channel),
        "mark_read_after_turn": connected(db.mark_read_after_turn),
        "auto_read_patterns": auto_read.compile_patterns([r"\(quiet\)"]),
    }
    _poll_once(monkeypatch, **callbacks)
    assert _row("openclaw:abc").status == "read"

    with db.connect() as conn:
        db.mark_unread(conn, _row("openclaw:abc").id)
    _poll_once(monkeypatch, **callbacks)

    assert _row("openclaw:abc").status == "unread"


def _openclaw_session(tmp_path, monkeypatch, said: str) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "message",
                "timestamp": _A_MINUTE_AGO,
                "message": {
                    "role": "assistant",
                    "stopReason": "stop",
                    "content": [{"type": "text", "text": said}],
                },
            }
        )
        + "\n"
    )
    monkeypatch.setattr(openclaw_watcher, "get_session_path", lambda *_: session)
    monkeypatch.setattr(openclaw_watcher, "read_lines", watcher.read_jsonl_tail)


def _watch_openclaw_turn(tmp_path, monkeypatch, said: str) -> list[str]:
    _openclaw_session(tmp_path, monkeypatch, said)
    marked_unread: list[str] = []

    def finish_poll(_seconds):
        raise StopIteration

    monkeypatch.setattr(watcher.time, "sleep", finish_poll)
    with pytest.raises(StopIteration):
        watcher.unified_watch_loop(
            [openclaw_watcher],
            lambda: [("openclaw:abc", "abc", "/tmp", 0.0, False, None, "", None)],
            lambda _channel: 0,
            lambda _channel, _message: 0,
            mark_unread=lambda channel: marked_unread.append(channel) or 1,
            auto_read_patterns=auto_read.compile_patterns([r"\(quiet\)"]),
            poll_interval=0,
        )
    return marked_unread


def test_watcher_leaves_a_quiet_openclaw_turn_read(tmp_path, monkeypatch):
    assert _watch_openclaw_turn(tmp_path, monkeypatch, "(quiet)") == []


def test_watcher_marks_other_openclaw_turns_unread(tmp_path, monkeypatch):
    assert _watch_openclaw_turn(tmp_path, monkeypatch, "Which one?") == ["openclaw:abc"]


@pytest.mark.usefixtures("quiet_config")
def test_for_lemons_lists_the_configured_patterns(capsys):
    for_lemons.cmd_for_lemons(argparse.Namespace(path=False))

    out = capsys.readouterr().out
    assert "## Auto-read on this machine" in out
    assert "- `^\\(quiet\\)`" in out


def test_for_lemons_says_when_there_are_none(capsys):
    for_lemons.cmd_for_lemons(argparse.Namespace(path=False))

    assert "No `[inbox] auto_read` patterns" in capsys.readouterr().out
