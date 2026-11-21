from lemonaid.slack import api, wake_text

from .shared import CHANNEL, SESSION, THREAD, Slack, post, reply


def test_a_reply_reads_as_its_author_time_link_and_plain_text(monkeypatch):
    slack = Slack()
    monkeypatch.setattr(api, "call", slack)
    text = "<@U0ANN> see <https://example.com/x|the doc> &amp; <#C0OPS|ops>\nsecond line"

    described = wake_text.describe(
        THREAD, [reply("1794858000.000100", text)], wake_text.namer(SESSION), ""
    )

    assert described.splitlines() == [
        f"Slack thread {THREAD.link}: 1 new reply",
        f"- Ann at {wake_text._when('1794858000.000100')}: https://acme.slack.com/archives/C0TEAM/"
        "p1794858000000100?thread_ts=1794857970.806329&cid=C0TEAM",
        "  > @Ann see the doc (https://example.com/x) & #ops",
        "  > second line",
    ]


def test_a_channels_messages_name_the_channel_and_the_pattern_that_chose_them(monkeypatch):
    monkeypatch.setattr(api, "call", Slack())
    messages = [post("1794858000.000100", "deploy one"), post("1794858100.000200", "deploy two")]
    name = wake_text.namer(SESSION)

    described = wake_text.describe(CHANNEL, messages, name, "deploy")

    assert described.splitlines()[0] == (
        f"Slack channel {CHANNEL.link}: 2 new messages matching 'deploy'"
    )
    assert "https://acme.slack.com/archives/C0TEAM/p1794858000000100\n" in described
    assert wake_text.label(CHANNEL, messages, name) == "2 Slack messages"
    assert wake_text.label(CHANNEL, messages[:1], name) == "Slack message from Ann"


def test_names_are_asked_of_slack_once(monkeypatch):
    slack = Slack()
    monkeypatch.setattr(api, "call", slack)

    assert wake_text.namer(SESSION)("U0ANN") == "Ann"
    assert wake_text.namer(SESSION)("U0ANN") == "Ann"
    assert [method for method, _ in slack.calls] == ["users.info"]
