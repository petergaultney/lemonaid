"""A chat room as a front end: showing a lemon opens its room, and nothing starts or prompts it."""

from lemonaid.config import Config
from lemonaid.front_end import chat, pick

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


def test_the_chat_front_end_neither_starts_nor_prompts():
    found = pick.named(chat.NAME)

    assert found is not None
    assert found.terminal.name == chat.NAME
    assert found.start is None and found.prompt is None
    assert found.terminal.exists("/dev/ttys1", None, None) is None
