"""Tokened brief and user message readiness."""

import json
import time

import pytest

from lemonaid.brief import attached, handoff_claude, handoff_codex, handoff_state


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


@pytest.mark.parametrize("final_format", ["event_msg", "response_item"])
def test_codex_final_reply_can_supply_standalone_ready_marker(
    setup, monkeypatch, tmp_path, final_format
):
    conn, path = setup
    attached.attach(conn, "codex:new", path)
    row = handoff_state.request(
        conn, path, "codex:new", "claude", "work", "3", "@3", "%3", "codex", time.time() + 600
    )
    path.write_text(path.read_text().replace("Old notes.", "New notes."))
    transcript = tmp_path / "codex.jsonl"
    monkeypatch.setattr(handoff_codex.codex_watcher, "get_session_path", lambda *_: transcript)
    marker = f"Handoff-Ready: {row['token']}"
    if final_format == "event_msg":
        final_message = {
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": f"Done.\n{marker}"},
        }
    else:
        final_message = {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": f"Done.\n{marker}"}],
            },
        }
    transcript.write_text(
        "\n".join(
            json.dumps(entry)
            for entry in (
                {"type": "event_msg", "payload": {"type": "task_started"}},
                final_message,
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            )
        )
        + "\n"
    )

    assert handoff_state.ready(conn, row) == (True, "")


def test_codex_final_reply_marker_requires_a_completed_turn(setup, monkeypatch, tmp_path):
    conn, path = setup
    attached.attach(conn, "codex:new", path)
    row = handoff_state.request(
        conn, path, "codex:new", "claude", "work", "3", "@3", "%3", "codex", time.time() + 600
    )
    path.write_text(path.read_text().replace("Old notes.", "New notes."))
    transcript = tmp_path / "codex.jsonl"
    monkeypatch.setattr(handoff_codex.codex_watcher, "get_session_path", lambda *_: transcript)
    marker = f"Handoff-Ready: {row['token']}"
    transcript.write_text(
        json.dumps({"type": "event_msg", "payload": {"type": "task_started"}})
        + "\n"
        + json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": marker}],
                },
            }
        )
        + "\n"
    )

    assert "no matching end marker" in handoff_state.ready(conn, row)[1]


def test_codex_final_reply_marker_must_be_on_its_own_line(setup, monkeypatch, tmp_path):
    conn, path = setup
    attached.attach(conn, "codex:new", path)
    row = handoff_state.request(
        conn, path, "codex:new", "claude", "work", "3", "@3", "%3", "codex", time.time() + 600
    )
    path.write_text(path.read_text().replace("Old notes.", "New notes."))
    transcript = tmp_path / "codex.jsonl"
    monkeypatch.setattr(handoff_codex.codex_watcher, "get_session_path", lambda *_: transcript)
    transcript.write_text(
        "\n".join(
            json.dumps(entry)
            for entry in (
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": f"Done. The marker is Handoff-Ready: {row['token']}.",
                    },
                },
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            )
        )
        + "\n"
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
