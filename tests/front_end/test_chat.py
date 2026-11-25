"""A chat room as a front end: showing a lemon opens its room, and prompting it sends the text
through the gateway's `chat.send`; nothing starts one."""

import json
import stat

from lemonaid.config import Config
from lemonaid.front_end import chat, pick
from lemonaid.inbox import db
from lemonaid.openclaw import sessions

KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"


def test_room_url_names_the_matrix_room():
    assert chat.room_url(KEY) == "https://matrix.to/#/!g4rd3n:grove.example"


def test_room_url_is_empty_for_other_chats():
    assert chat.room_url("agent:main:signal:direct:uuid:1234") == ""
    assert chat.room_url("agent:main:cron:abc") == ""
    assert chat.room_url("") == ""


def test_show_opens_the_room(monkeypatch):
    opened = []
    monkeypatch.setattr(chat.webbrowser, "open", lambda url: opened.append(url) or True)

    assert chat.show({"session_key": KEY}, Config()) is True
    assert opened == ["https://matrix.to/#/!g4rd3n:grove.example"]


def test_show_without_a_room_does_nothing(monkeypatch):
    def opened(url):
        raise AssertionError(f"opened {url}")

    monkeypatch.setattr(chat.webbrowser, "open", opened)

    assert chat.show({"session_key": "agent:main:cron:abc"}, Config()) is False
    assert chat.show(None, Config()) is False


def test_the_chat_front_end_prompts_but_never_starts():
    found = pick.named(chat.NAME)

    assert found is not None
    assert found.terminal.name == chat.NAME
    assert found.start is None and found.prompt is chat.prompt
    assert found.terminal.exists("/dev/ttys1", None, None) is None


def _row(channel: str) -> db.Notification:
    with db.connect() as conn:
        return db.register_working(conn, channel, "", switch_source=chat.NAME)


def test_prompt_sends_the_text_with_chat_send(tmp_path, monkeypatch):
    log = tmp_path / "calls.jsonl"
    cli = tmp_path / "openclaw"
    cli.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "print(json.dumps({'runId': 'r', 'status': 'started'}))\n"
    )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(sessions, "cli", lambda: str(cli))

    assert chat.prompt(_row(f"openclaw:{KEY}"), Config(), "how is the deck?") == ""

    argv = json.loads(log.read_text())
    assert argv[:3] == ["gateway", "call", "chat.send"]
    params = json.loads(argv[argv.index("--params") + 1])
    assert (params["sessionKey"], params["message"]) == (KEY, "how is the deck?")
    assert params["idempotencyKey"]


def test_prompt_says_why_when_the_gateway_refuses(tmp_path, monkeypatch):
    cli = tmp_path / "openclaw"
    cli.write_text("#!/bin/sh\necho 'gateway down' >&2\nexit 1\n")
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(sessions, "cli", lambda: str(cli))

    assert chat.prompt(_row(f"openclaw:{KEY}"), Config(), "hi") == "chat.send failed: gateway down"
