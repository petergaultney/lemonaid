import datetime as dt
import json
from pathlib import Path

import pytest

from lemonaid.rules import transcripts

_SINCE = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


@pytest.fixture
def homes(monkeypatch, tmp_path) -> tuple[Path, Path]:
    claude, codex = tmp_path / "claude", tmp_path / "codex"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("CODEX_HOME", str(codex))
    return claude, codex


def _write(path: Path, *entries: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return path


def _assistant(message_id: str, block: dict, at: str = "2026-11-20T12:00:00Z", **extra) -> dict:
    return {
        "type": "assistant",
        "timestamp": at,
        "cwd": "/work/repo",
        "message": {"id": message_id, "content": [block]},
        **extra,
    }


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


_TOOL = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}
_PROMPT = {"type": "user", "message": {"content": "next please"}}
_RESULT = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1"}]}}


def _said(homes) -> list[tuple[str, str, str]]:
    return [(s.harness, s.cwd, s.text) for s in transcripts.turn_ends(_SINCE)]


def test_a_claude_turn_ends_with_text_no_tool_call_followed(homes):
    _write(
        homes[0] / "projects" / "-work-repo" / "s1.jsonl",
        _assistant("m1", _text("Let me look.")),
        _assistant("m1", _TOOL),
        _RESULT,
        _assistant("m2", _text("Found it.")),
        _assistant("m2", _text("Want me to merge?")),
        _PROMPT,
        _assistant("m3", _text("Merged.")),
        {"type": "system", "subtype": "stop_hook_summary"},
        {"type": "attachment"},
        _assistant("m4", _text("A background task finished.")),
    )

    assert _said(homes) == [
        ("claude", "/work/repo", "Found it.\n\nWant me to merge?"),
        ("claude", "/work/repo", "Merged."),
        ("claude", "/work/repo", "A background task finished."),
    ]


def test_subagents_and_api_errors_are_left_out(homes):
    _write(
        homes[0] / "projects" / "-work-repo" / "s1.jsonl",
        _assistant("m1", _text("Said by a subagent.")),
        _assistant("m2", _text("Sidechain."), isSidechain=True),
        _assistant("m3", _text("API Error: 500"), isApiErrorMessage=True),
    )
    _write(
        homes[0] / "projects" / "-work-repo" / "s1" / "subagents" / "a.jsonl",
        _assistant("m9", _text("Inside a subagent's own file.")),
    )

    assert _said(homes) == [("claude", "/work/repo", "Said by a subagent.")]


def test_a_codex_turn_end_is_its_task_complete(homes):
    _write(
        homes[1] / "sessions" / "2026" / "11" / "20" / "rollout-a.jsonl",
        {"type": "session_meta", "payload": {"cwd": "/work/a", "source": "cli"}},
        {
            "timestamp": "2026-11-20T12:00:00Z",
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": "Ready to merge?"},
        },
        {"type": "turn_context", "payload": {"cwd": "/work/b"}},
        {
            "timestamp": "2026-11-20T13:00:00Z",
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": None},
        },
        {
            "timestamp": "2026-11-20T14:00:00Z",
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": "Pushed."},
        },
    )
    _write(
        homes[1] / "archived_sessions" / "rollout-spawned.jsonl",
        {
            "type": "session_meta",
            "payload": {"parent_thread_id": "p", "source": {"subagent": {"other": "guardian"}}},
        },
        {
            "timestamp": "2026-11-20T12:00:00Z",
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": "allow"},
        },
    )

    assert _said(homes) == [
        ("codex", "/work/a", "Ready to merge?"),
        ("codex", "/work/b", "Pushed."),
    ]


def test_messages_before_since_are_left_out(homes):
    _write(
        homes[0] / "projects" / "-work-repo" / "s1.jsonl",
        _assistant("m1", _text("Old."), at="2026-10-30T12:00:00Z"),
        _PROMPT,
        _assistant("m2", _text("New."), at="2026-11-02T12:00:00Z"),
    )

    assert [said.text for said in transcripts.turn_ends(_SINCE)] == ["New."]
