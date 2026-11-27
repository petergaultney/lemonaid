"""A lemon's page in the web grove: what it shows, and which way typed text goes in."""

import base64
import json
import time

import pytest

from lemonaid.brief import attached, pr
from lemonaid.brief import store as brief_store
from lemonaid.config import Config
from lemonaid.front_end import interface, pick
from lemonaid.grove.web import attachments, lemon
from lemonaid.inbox import db
from lemonaid.messages import tell_delivery
from lemonaid.openclaw import turns

CHANNEL = "claude:abc"


@pytest.fixture
def worker(tmp_path):
    transcript = tmp_path / "abc.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "origin": {"kind": "human"}, "message": {"content": "hi"}})
        + "\n"
    )
    path = brief_store.briefs_dir() / "worker.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Worker\n")
    with db.connect() as conn:
        db.register_working(
            conn,
            CHANNEL,
            "",
            name="worker",
            metadata={"transcript_path": str(transcript)},
            switch_source="tmux",
        )
        attached.attach(conn, CHANNEL, path)
    return path


def test_view_shows_the_brief_and_how_text_goes_in(worker):
    shown = lemon.view(CHANNEL, Config(), pr.no_state)

    assert (shown["name"], shown["how"]) == ("worker", "tmux")
    assert "Worker" in shown["brief"]["sections"][0]["card"]  # drawn as the inbox's brief pane
    assert "<span style=" in shown["brief"]["sections"][0]["card"]
    assert shown["pinned"] is False


def test_the_page_shows_and_is_told_when_its_lemon_is_mid_turn(worker):
    before = lemon.mark(CHANNEL)
    assert lemon.view(CHANNEL, Config(), pr.no_state)["working"] is False

    with db.connect() as conn:
        db.record_turn(conn, CHANNEL, time.time())

    assert lemon.view(CHANNEL, Config(), pr.no_state)["working"] is True
    assert lemon.mark(CHANNEL) != before


def test_talk_reads_the_conversation(worker):
    said = lemon.talk(CHANNEL)

    assert [each["text"] for each in said["entries"]] == ["hi"]
    assert said["conversation_problem"] == ""
    assert lemon.talk("claude:gone") == {"error": "No live lemon on claude:gone"}


def test_talk_reads_a_conversation_again_only_once_it_changed(worker, monkeypatch, tmp_path):
    reads = []
    real = lemon.conversation.claude.read
    monkeypatch.setattr(lemon.conversation.claude, "read", lambda *a: reads.append(1) or real(*a))
    transcript = tmp_path / "abc.jsonl"

    lemon.talk(CHANNEL)
    lemon.talk(CHANNEL)
    with transcript.open("a") as f:
        f.write(
            json.dumps(
                {"type": "user", "origin": {"kind": "human"}, "message": {"content": "again"}}
            )
            + "\n"
        )
    said = lemon.talk(CHANNEL)

    assert len(reads) == 2
    assert [each["text"] for each in said["entries"]] == ["hi", "again"]


def test_an_openclaw_turn_that_failed_changes_its_page(monkeypatch):
    monkeypatch.setattr(turns, "_failed", {})
    monkeypatch.setattr(lemon.conversation.openclaw, "mark", lambda *_args: "history")
    with db.connect() as conn:
        db.register_working(conn, "openclaw:agent:main:probe", "", name="probe")
    before = lemon.mark("openclaw:agent:main:probe")

    turns.note(
        {
            "stream": "lifecycle",
            "sessionKey": "agent:main:probe",
            "runId": "r1",
            "ts": 1000,
            "data": {"phase": "error", "error": "rate limited"},
        }
    )

    assert lemon.mark("openclaw:agent:main:probe") != before


def test_view_of_a_lemon_that_isnt_there():
    assert lemon.view("claude:gone", Config(), pr.no_state) == {
        "error": "No live lemon on claude:gone"
    }


def test_say_types_through_the_front_end(worker, monkeypatch):
    typed = []
    found = pick.named("tmux")
    assert found is not None
    prompt = lambda row, config, text: typed.append((row.channel, text)) or ""  # noqa: E731
    monkeypatch.setattr(
        lemon.pick,
        "named",
        lambda name: interface.FrontEnd(found.terminal, found.open_beside, None, prompt),
    )

    with db.connect() as conn:
        db.mark_unread_for_channel(conn, CHANNEL)

    assert lemon.say(CHANNEL, "go on", Config()) == ""
    assert typed == [(CHANNEL, "go on")]
    with db.connect() as conn:
        assert not db.get_by_channel(conn, CHANNEL, unread_only=False).is_unread


def test_say_sends_mail_when_the_front_end_cant_type(worker, monkeypatch):
    sent = []

    def deliver(to, body, sender, wake_it):
        sent.append((to.lemon_id, body, sender.endswith("(web grove)")))
        return tell_delivery.Delivery(worker, "", True, False, "listening")

    monkeypatch.setattr(tell_delivery, "deliver", deliver)
    monkeypatch.setattr(lemon.pick, "named", lambda name: None)

    assert lemon.say(CHANNEL, "when you can", Config()) == ""
    assert [(body, web) for _, body, web in sent] == [("when you can", True)]
    assert lemon.view(CHANNEL, Config(), pr.no_state)["how"] == lemon.MAIL


def test_say_refuses_empty_text(worker):
    assert lemon.say(CHANNEL, "  ", Config()) == "nothing to send"


def _attached(name: str, mime: str, raw: bytes) -> str:
    saved = attachments.save(name, mime, base64.b64encode(raw).decode())
    assert isinstance(saved, dict)
    return saved["id"]


def test_say_puts_attached_files_paths_into_a_typing_lemons_text(worker, monkeypatch):
    typed = []
    found = pick.named("tmux")
    assert found is not None
    prompt = lambda row, config, text: typed.append(text) or ""  # noqa: E731
    monkeypatch.setattr(
        lemon.pick,
        "named",
        lambda name: interface.FrontEnd(found.terminal, found.open_beside, None, prompt),
    )
    file_id = _attached("notes.txt", "text/plain", b"hi")

    assert lemon.say(CHANNEL, "", Config(), [file_id]) == ""
    [path] = attachments.found([file_id])  # type: ignore[misc]
    assert typed == [f"Attached file:\n- {path.path}"]


def test_say_sends_an_openclaw_session_the_files_themselves(monkeypatch):
    sent = []
    monkeypatch.setattr(
        lemon.chat, "send", lambda key, text, files=(): sent.append((key, text, files)) or ""
    )
    with db.connect() as conn:
        db.register_working(
            conn, "openclaw:agent:main:probe", "", name="probe", switch_source="openclaw-chat"
        )
    file_id = _attached("photo.png", "image/png", b"png")

    assert lemon.say("openclaw:agent:main:probe", "look", Config(), [file_id]) == ""
    assert sent == [
        (
            "agent:main:probe",
            "look",
            [
                {
                    "type": "image",
                    "mimeType": "image/png",
                    "fileName": "photo.png",
                    "content": base64.b64encode(b"png").decode(),
                }
            ],
        )
    ]


def test_say_refuses_a_file_the_server_no_longer_has(worker):
    assert lemon.say(CHANNEL, "see this", Config(), ["20261126-120000-0123abcd"]) == (
        "an attachment is gone from the server; remove it and attach it again"
    )


def test_an_openclaw_lemon_takes_files_only_over_a_held_gateway_connection(monkeypatch):
    with db.connect() as conn:
        db.register_working(
            conn, "openclaw:agent:main:probe", "", name="probe", switch_source="openclaw-chat"
        )
    monkeypatch.setattr(lemon.gateway, "_held", None)
    assert lemon.view("openclaw:agent:main:probe", Config(), pr.no_state)["attach"] is False

    monkeypatch.setattr(lemon.gateway, "_held", object())
    assert lemon.view("openclaw:agent:main:probe", Config(), pr.no_state)["attach"] is True


def test_a_terminal_lemon_always_takes_files(worker, monkeypatch):
    monkeypatch.setattr(lemon.gateway, "_held", None)
    assert lemon.view(CHANNEL, Config(), pr.no_state)["attach"] is True
