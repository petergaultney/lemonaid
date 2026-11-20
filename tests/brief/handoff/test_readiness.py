"""Tokened brief and user message readiness."""

import json
import time

from lemonaid.brief import attached
from lemonaid.brief.handoff import claude as handoff_claude
from lemonaid.brief.handoff import codex as handoff_codex
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.codex import stored


def _codex_request(setup, notes: str):
    conn, path = setup
    attached.attach(conn, "codex:new", path)
    row = handoff_state.request(
        conn, path, "codex:new", "claude", "work", "3", "@3", "%3", "codex", time.time() + 600
    )
    path.write_text(path.read_text().replace("Old notes.", notes.format(token=row["token"])))
    return conn, row


def _turns(monkeypatch, *turns: stored.Turn) -> None:
    monkeypatch.setattr(handoff_codex.threads, "latest_turns", lambda thread, count: list(turns))


def test_codex_user_phrase_is_detected_from_codex_s_turns(setup, monkeypatch):
    conn, row = _codex_request(setup, "New.\nHandoff-Ready: {token}")
    _turns(monkeypatch, stored.Turn(True, (), (f"lemonaid handoff ready {row['token']}",)))

    handoff_codex.phrases(conn, row)

    assert handoff_state.get(conn, row["token"])["ready"] == 1


def test_codex_final_reply_can_supply_standalone_ready_marker(setup, monkeypatch):
    conn, row = _codex_request(setup, "New notes.")
    _turns(
        monkeypatch, stored.Turn(True, ("Working.", f"Done.\nHandoff-Ready: {row['token']}"), ())
    )

    assert handoff_state.ready(conn, row) == (True, "")


def test_codex_final_reply_marker_requires_a_completed_turn(setup, monkeypatch):
    conn, row = _codex_request(setup, "New notes.")
    _turns(monkeypatch, stored.Turn(False, (f"Handoff-Ready: {row['token']}",), ()))

    assert "no matching end marker" in handoff_state.ready(conn, row)[1]


def test_codex_final_reply_marker_must_be_on_its_own_line(setup, monkeypatch):
    conn, row = _codex_request(setup, "New notes.")
    _turns(
        monkeypatch,
        stored.Turn(True, (f"Done. The marker is Handoff-Ready: {row['token']}.",), ()),
    )

    assert "no matching end marker" in handoff_state.ready(conn, row)[1]


def test_ready_requires_new_valid_section_and_matching_channel(setup):
    conn, path = setup
    row = handoff_state.request(
        conn, path, "claude:old", "codex", "work", "2", "@2", "%2", "claude", time.time() + 600
    )
    assert not handoff_state.ready(conn, row)[0]
    path.write_text(path.read_text().replace("Old notes.", "New notes."))
    assert "no matching end marker" in handoff_state.ready(conn, row)[1]
    path.write_text(path.read_text() + f"Handoff-Ready: {row['token']}\n")
    assert not handoff_state.typed_message(
        conn, "codex:new", f"lemonaid handoff ready {row['token']}"
    )
    assert handoff_state.typed_message(conn, "claude:old", f"lemonaid handoff ready {row['token']}")


def test_claude_final_reply_can_supply_standalone_marker(setup, monkeypatch, tmp_path):
    conn, path = setup
    row = handoff_state.request(
        conn, path, "claude:old", "codex", "work", "2", "@2", "%2", "claude", time.time() + 600
    )
    path.write_text(path.read_text().replace("Old notes.", "New notes."))
    transcript = tmp_path / "old.jsonl"
    monkeypatch.setattr(handoff_claude.watcher, "get_session_path", lambda *_: transcript)

    def write_reply(message: str, *, source: bool = True, ended: bool = True) -> None:
        entries = [
            {
                "type": "assistant" if source else "user",
                "message": {"id": "reply", "content": [{"type": "text", "text": message}]},
            }
        ]
        if ended:
            entries.append({"type": "system", "subtype": "turn_duration"})
        transcript.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

    marker = f"Handoff-Ready: {row['token']}"
    write_reply(marker, ended=False)
    assert not handoff_state.ready(conn, row)[0]
    write_reply(marker, source=False)
    assert not handoff_state.ready(conn, row)[0]
    write_reply(f"Handoff-Ready: {'0' * 24}")
    assert not handoff_state.ready(conn, row)[0]
    write_reply(f"A handoff is ready: {row['token']}")
    assert not handoff_state.ready(conn, row)[0]
    write_reply(f"Done.\n{marker}\n")
    assert handoff_state.ready(conn, row) == (True, "")

    path.write_text(path.read_text().replace("Status: working", "Status: invented"))
    assert "brief check failed" in handoff_state.ready(conn, row)[1]
