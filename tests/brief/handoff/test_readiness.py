"""Tokened brief and user message readiness."""

import json
import time

from lemonaid.brief import attached, handoff_codex, handoff_state


def test_codex_user_phrase_is_detected_from_transcript(setup, monkeypatch, tmp_path):
    conn, path = setup
    attached.attach(conn, "codex:new", path)
    row = handoff_state.request(
        conn, path, "codex:new", "claude", "work", "3", "@3", "%3", "codex", time.time() + 600
    )
    path.write_text(path.read_text().replace("Old notes.", f"New.\nHandoff-Ready: {row['token']}"))
    transcript = tmp_path / "codex.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": f"lemonaid handoff ready {row['token']}"}
                    ],
                },
            }
        )
        + "\n"
    )
    monkeypatch.setattr(handoff_codex.codex_watcher, "get_session_path", lambda *_: transcript)
    handoff_codex.phrases(conn, row)
    assert handoff_state.get(conn, row["token"])["ready"] == 1


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
