import json
from pathlib import Path

import pytest

from lemonaid.brief import attached, render, target, turn_end_question
from lemonaid.claude import notify as claude_notify
from lemonaid.codex import notify as codex_notify
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp


@pytest.fixture
def brief(tmp_path: Path) -> Path:
    path = tmp_path / "brief.md"
    path.write_text("# Task\n\nStatus: waiting\n\n## Now\n- Waiting on: review\n")
    return path


def _attach(channel: str, brief: Path) -> None:
    with db.connect() as conn:
        attached.attach(conn, channel, brief)


def _row(channel: str) -> db.Notification:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return row


def test_codex_turn_end_question_is_derived_from_last_paragraph(monkeypatch, brief: Path) -> None:
    _attach("codex:thread", brief)
    monkeypatch.setattr(codex_notify, "_resolve_session_path", lambda *args: None)
    monkeypatch.setattr(codex_notify, "get_git_branch", lambda cwd: None)
    monkeypatch.setattr(codex_notify, "get_tty", lambda: None)
    monkeypatch.setattr(codex_notify, "detect_terminal_switch_source", lambda: "unknown")

    codex_notify.handle_notification(
        json.dumps(
            {
                "type": "agent-turn-complete",
                "thread-id": "thread",
                "cwd": "/tmp/project",
                "last-assistant-message": "Earlier question?\n\nCan you review this?",
            }
        )
    )

    row = _row("codex:thread")
    assert row.message == "Can you review this?"
    assert row.metadata["turn_end_question"] == "Can you review this?"
    assert "Status: waiting" in brief.read_text()
    shown = render.view(
        target.Target([brief], [], None, [], "Task"),
        0,
        lambda ref, cwd: "",
        {brief: row.metadata["turn_end_question"]},
    )
    rendered = render.to_markdown(shown, 0)
    assert "**Status:** blocked" in rendered
    assert "**Needs Peter:** Can you review this?" in rendered

    codex_notify.handle_notification(
        json.dumps(
            {
                "type": "agent-turn-complete",
                "thread-id": "thread",
                "cwd": "/tmp/project",
                "last-assistant-message": "A question earlier?\n\nThe work is ready.",
            }
        )
    )
    assert "turn_end_question" not in _row("codex:thread").metadata


def test_claude_stop_reads_final_transcript_message(
    monkeypatch, tmp_path: Path, brief: Path
) -> None:
    _attach("claude:session", brief)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps(entry)
            for entry in [
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Old question?"}]},
                },
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Ready.\n\nWhich option?"}]},
                },
            ]
        )
    )
    monkeypatch.setattr(
        claude_notify,
        "_resolve_session",
        lambda data, kind: (
            "claude:session",
            "session",
            "Test",
            "unknown",
            {"transcript_path": str(transcript)},
        ),
    )

    claude_notify.handle_notification(
        json.dumps(
            {
                "session_id": "session",
                "cwd": "/tmp/project",
                "hook_event_name": "Stop",
            }
        )
    )

    row = _row("claude:session")
    assert row.message == "Which option?"
    assert row.metadata["turn_end_question"] == "Which option?"


def test_claude_stop_prefers_hook_message_over_transcript(
    monkeypatch, tmp_path: Path, brief: Path
) -> None:
    _attach("claude:session", brief)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Old ask?"}]}}
        )
    )
    monkeypatch.setattr(
        claude_notify,
        "_resolve_session",
        lambda data, kind: (
            "claude:session",
            "session",
            "Test",
            "unknown",
            {"transcript_path": str(transcript)},
        ),
    )

    claude_notify.handle_notification(
        json.dumps(
            {
                "session_id": "session",
                "cwd": "/tmp/project",
                "hook_event_name": "Stop",
                "last_assistant_message": "New ask?",
            }
        )
    )

    assert _row("claude:session").metadata["turn_end_question"] == "New ask?"


def test_codex_answer_clears_derived_question(brief: Path) -> None:
    _attach("codex:thread", brief)
    with db.connect() as conn:
        db.add(
            conn,
            "codex:thread",
            "Old ask?",
            metadata={"turn_end_question": "Old ask?", "cwd": "/tmp/project"},
        )
    LemonaidApp()._mark_channel_read("codex:thread")

    assert _row("codex:thread").metadata == {"cwd": "/tmp/project"}
    assert _row("codex:thread").is_read


def test_derived_state_and_ask_share_precedence() -> None:
    assert turn_end_question.effective("waiting", "review", "Waiting on", "New ask?") == (
        "blocked",
        "New ask?",
        "Needs Peter",
    )
    assert turn_end_question.effective("blocked", "Existing ask", "Needs Peter", "New ask?") == (
        "blocked",
        "Existing ask",
        "Needs Peter",
    )


def test_explicit_blocked_brief_wins(brief: Path) -> None:
    brief.write_text("# Task\n\nStatus: blocked\n\n## Now\n- Needs Peter: Existing ask\n")
    _attach("codex:thread", brief)
    with db.connect() as conn:
        metadata: dict[str, str] = {}
        assert turn_end_question.add_ask(conn, "codex:thread", "New ask?", metadata) == ""
    assert metadata == {}
    rendered = render.to_markdown(
        render.view(
            target.Target([brief], [], None, [], "Task"),
            0,
            lambda ref, cwd: "",
            {brief: "New ask?"},
        ),
        0,
    )
    assert "**Status:** blocked" in rendered
    assert "**Needs Peter:** New ask?" not in rendered


def test_question_only_in_earlier_paragraph_does_not_count() -> None:
    assert turn_end_question.last_paragraph("Question?\n\nFinal statement.") == ""
    assert turn_end_question.last_paragraph("Statement.\n\nFinal question?") == "Final question?"


def test_question_mark_inside_url_or_code_does_not_count() -> None:
    assert turn_end_question.last_paragraph("`obsidian://open?vault=trove&file=note`") == ""
    assert turn_end_question.last_paragraph("[note](obsidian://open?vault=trove&file=note)") == ""
    assert turn_end_question.last_paragraph("See https://example.com/search?q=lemons") == ""
    assert turn_end_question.last_paragraph("Use `is_ready?` to check.") == ""


def test_question_outside_url_or_code_still_counts() -> None:
    message = "Can you review [the note](obsidian://open?vault=trove&file=note)?"
    assert turn_end_question.last_paragraph(message) == message
