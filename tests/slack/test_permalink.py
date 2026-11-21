import pytest

from lemonaid.slack import permalink

ROOT = "https://acme.slack.com/archives/C0TEAM/p1794857970806329"


def test_a_root_link_names_its_own_thread():
    assert permalink.parse(ROOT) == ("acme.slack.com", "C0TEAM", "1794857970.806329")


def test_a_reply_link_names_the_thread_it_is_in():
    reply = (
        "https://acme.slack.com/archives/C0TEAM/p1794858000000100"
        "?thread_ts=1794857970.806329&cid=C0TEAM"
    )

    thread = permalink.parse(reply)

    assert thread.ts == "1794857970.806329"
    assert thread.link == ROOT
    assert thread.target == ("C0TEAM", "1794857970.806329")
    assert permalink.message_link(thread, "1794858000.000100") == reply


def test_a_channel_link_names_the_channel():
    channel = permalink.parse("https://acme.slack.com/archives/C0TEAM/")

    assert channel == ("acme.slack.com", "C0TEAM", "")
    assert (channel.link, channel.target) == ("https://acme.slack.com/archives/C0TEAM", ("C0TEAM",))
    assert permalink.message_link(channel, "1794857970.806329") == ROOT
    assert permalink.message_link(channel, "1794858000.000100", "1794857970.806329") == (
        "https://acme.slack.com/archives/C0TEAM/p1794858000000100"
        "?thread_ts=1794857970.806329&cid=C0TEAM"
    )


@pytest.mark.parametrize(
    "link",
    [
        "http://acme.slack.com/archives/C0TEAM/p1794857970806329",
        "https://acme.slack.com/messages/C0TEAM",
        "https://acme.slack.com/archives/C0TEAM/files",
        "https://acme.slack.com/archives/C0TEAM/p1794857970806329?thread_ts=junk",
    ],
)
def test_anything_else_is_refused(link):
    with pytest.raises(ValueError):
        permalink.parse(link)


def test_timestamps_compare_to_the_microsecond():
    assert permalink.order("1794857970.806330") > permalink.order("1794857970.806329")
