from lemonaid.slack import api, replies

from .shared import SESSION, THREAD, Slack, reply


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

    found = replies.after(SESSION, THREAD, "1794857999.000001")

    assert [m["text"] for m in found.replies] == ["b", "c"]
    assert found.latest == "1794857999.000003"
    assert {p["oldest"] for p in asked} == {"1794857999.000001"}


def test_a_reply_reads_as_its_author_time_link_and_plain_text(monkeypatch):
    slack = Slack()
    monkeypatch.setattr(api, "call", slack)
    text = "<@U0ANN> see <https://example.com/x|the doc> &amp; <#C0OPS|ops>\nsecond line"

    described = replies.describe(THREAD, [reply("1794858000.000100", text)], replies.namer(SESSION))

    assert described.splitlines() == [
        f"Slack thread {THREAD.link}: 1 new reply",
        f"- Ann at {replies._when('1794858000.000100')}: https://acme.slack.com/archives/C0TEAM/"
        "p1794858000000100?thread_ts=1794857970.806329&cid=C0TEAM",
        "  > @Ann see the doc (https://example.com/x) & #ops",
        "  > second line",
    ]


def test_names_are_asked_of_slack_once(monkeypatch):
    slack = Slack()
    monkeypatch.setattr(api, "call", slack)

    assert replies.namer(SESSION)("U0ANN") == "Ann"
    assert replies.namer(SESSION)("U0ANN") == "Ann"
    assert [method for method, _ in slack.calls] == ["users.info"]
