"""scripts/stale-status.py counts a turn as nudged from the hook's log or its transcript."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "stale-status.py"
_SPEC = importlib.util.spec_from_file_location("stale_status", _SCRIPT)
stale_status = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stale_status)

_SESSION = "abcd1234-0000-0000-0000-000000000000"


def _tool(n: int, command: str) -> dict:
    return {
        "type": "assistant",
        "timestamp": f"2026-10-02T10:0{n}:00Z",
        "message": {
            "content": [
                {"type": "tool_use", "id": f"t{n}", "name": "Bash", "input": {"command": command}}
            ]
        },
    }


def _transcript(tmp_path: Path, attachment: dict | None) -> Path:
    brief = tmp_path / "lemon.md"
    entries = [
        _tool(0, f"lemonaid brief status --self blocked  # {brief.name}"),
        {
            "type": "user",
            "timestamp": "2026-10-02T10:01:00Z",
            "promptId": "turn-2",
            "origin": {"kind": "human"},
            "message": {"content": "yes, go ahead"},
        },
        _tool(2, "git status"),
        *([attachment] if attachment else []),
        _tool(3, "git commit -m x"),
    ]
    path = tmp_path / "projects" / "p" / f"{_SESSION}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return brief


def _run(tmp_path: Path, capsys, monkeypatch, notes: list[dict]) -> str:
    db = tmp_path / "lemonaid.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE session_briefs (channel TEXT, path TEXT, attached_at REAL)")
        conn.execute(
            "INSERT INTO session_briefs VALUES (?, ?, 0)",
            ("claude:abcd1234", str(tmp_path / "lemon.md")),
        )
    log = tmp_path / "status-notes.jsonl"
    log.write_text("".join(json.dumps(n) + "\n" for n in notes))

    argv = [
        "stale-status",
        "--db",
        str(db),
        "--projects",
        str(tmp_path / "projects"),
        "--notes",
        str(log),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    stale_status.main()
    return capsys.readouterr().out


def test_a_turn_the_hook_logged_is_nudged_without_a_transcript_entry(tmp_path, capsys, monkeypatch):
    _transcript(tmp_path, attachment=None)

    out = _run(
        tmp_path, capsys, monkeypatch, [{"session_id": _SESSION, "prompt_id": "turn-2", "at": 0}]
    )

    assert "  nudged: 1 of 1 answered turns stale" in out
    assert "  not nudged: 0 of 0" in out


def test_a_turn_with_the_note_in_its_transcript_is_nudged(tmp_path, capsys, monkeypatch):
    note = "Your brief's Status is `blocked`, on: nothing under Needs."
    _transcript(
        tmp_path,
        {
            "type": "attachment",
            "attachment": {"type": "hook_additional_context", "content": [note]},
        },
    )

    assert "  nudged: 1 of 1" in _run(tmp_path, capsys, monkeypatch, [])


def test_an_unlogged_turn_is_not_nudged(tmp_path, capsys, monkeypatch):
    _transcript(tmp_path, attachment=None)

    out = _run(
        tmp_path, capsys, monkeypatch, [{"session_id": _SESSION, "prompt_id": "other", "at": 0}]
    )

    assert "  not nudged: 1 of 1 answered turns stale" in out
