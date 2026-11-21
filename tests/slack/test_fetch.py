from lemonaid.slack import api, fetch

from .shared import CHANNEL, SESSION, THREAD, Slack, post, reply


def test_replies_after_the_cursor_are_read_through_every_page(monkeypatch):
    pages = {
        "": {
            "ok": True,
            "messages": [
                {"ts": THREAD.ts, "latest_reply": "1794857999.000003"},
                reply("1794857999.000002", "b"),
            ],
            "has_more": True,
            "response_metadata": {"next_cursor": "page2"},
        },
        "page2": {"ok": True, "messages": [reply("1794857999.000003", "c")], "has_more": False},
    }
    asked: list[dict] = []

    def call(current, method, **params):
        asked.append(params)
        return pages[params.get("cursor", "")]

    monkeypatch.setattr(api, "call", call)

    found = fetch.after(SESSION, THREAD, "1794857999.000001")

    assert [m["text"] for m in found.messages] == ["b", "c"]
    assert found.latest == found.cursor == "1794857999.000003"
    assert {p["oldest"] for p in asked} == {"1794857999.000001"}


def test_a_channels_messages_leave_out_joins_but_the_cursor_passes_them(monkeypatch):
    slack = Slack(
        posts=[
            post("1794857999.000001", "seen"),
            post("1794857999.000002", "hello"),
            post("1794857999.000003", "joined", subtype="channel_join"),
        ]
    )
    monkeypatch.setattr(api, "call", slack)

    found = fetch.after(SESSION, CHANNEL, "1794857999.000001")

    assert [m["text"] for m in found.messages] == ["hello"]
    assert found.latest == found.cursor == "1794857999.000003"
    assert [method for method, _ in slack.calls] == ["conversations.history"]


def test_a_first_fetch_starts_at_the_newest_message(monkeypatch):
    slack = Slack(
        replies=[reply("1794857999.000002", "a reply")],
        posts=[post("1794857999.000001", "a"), post("1794857999.000005", "b")],
    )
    monkeypatch.setattr(api, "call", slack)

    assert fetch.latest(SESSION, THREAD) == "1794857999.000002"
    assert fetch.latest(SESSION, CHANNEL) == "1794857999.000005"
