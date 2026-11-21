"""`slack_events.poller`: one lemon following one Slack thread or channel."""

import datetime
import time

import pytest

from lemonaid.brief import attached, identity, store, waiters
from lemonaid.inbox import db
from lemonaid.slack import api, session, signed_out, wakes
from lemonaid.slack_config import SlackConfig
from lemonaid.watch import delivery, slack_events

from ..slack.shared import CHANNEL, LINK, SESSION, THREAD, Slack, post, reply

OLD = "1794857980.000001"
NEW = "1794857990.000002"


@pytest.fixture
def slack(monkeypatch):
    fake = Slack(replies=[reply(OLD, "an old reply")])
    monkeypatch.setattr(api, "call", fake)
    monkeypatch.setattr(session, "load", lambda: SESSION)
    return fake


def _poller(
    tmp_path,
    delivered: list,
    *,
    lemon_id="",
    after="",
    match="",
    done=False,
    every=60.0,
    conversation=THREAD,
):
    directory = tmp_path / "cursors" / (lemon_id or "lemon.Ann") / "slack"
    directory.mkdir(parents=True, exist_ok=True)
    return slack_events.poller(
        conversation,
        after,
        match,
        done,
        directory,
        lemon_id,
        delivered.append,
        lambda problem: signed_out.tell_once(directory.parent, problem, delivered.append),
        SlackConfig(fetch_every=every),
    )


def _signal(conversation=THREAD) -> None:
    time.sleep(0.01)
    assert wakes.signal(conversation.channel, conversation.ts)


def test_a_first_poll_takes_the_thread_as_seen_and_a_signalled_reply_is_delivered(tmp_path, slack):
    delivered: list = []
    poll = _poller(tmp_path, delivered)
    poll()
    slack.replies.append(reply(NEW, "a new reply"))
    poll()
    assert delivered == []

    _signal()
    poll()

    [message] = delivered
    assert "a new reply" in message and "an old reply" not in message
    assert delivery.label_of(message) == "Slack reply from Ann"


def test_after_names_where_the_first_fetch_starts(tmp_path, slack):
    slack.replies.append(reply(NEW, "a new reply"))
    delivered: list = []

    _poller(tmp_path, delivered, after=OLD)()

    [message] = delivered
    assert "a new reply" in message and "an old reply" not in message


def test_a_reply_that_was_not_delivered_is_delivered_by_the_next_poller(tmp_path, slack):
    _poller(tmp_path, [])()
    slack.replies.append(reply(NEW, "a new reply"))

    def fail(message: str) -> None:
        raise delivery.Failed("Batch was not delivered")

    directory = tmp_path / "cursors" / "lemon.Ann" / "slack"
    failing = slack_events.poller(THREAD, "", "", False, directory, "", fail, fail, SlackConfig())
    with pytest.raises(delivery.Failed):
        failing()

    delivered: list = []
    _poller(tmp_path, delivered)()  # a restarted scout catches up from the cursor
    assert len(delivered) == 1 and "a new reply" in delivered[0]


def test_without_a_gateway_threads_are_fetched_on_a_timer_and_with_one_only_when_signalled(
    tmp_path, slack
):
    poll = _poller(tmp_path, [], every=0)
    poll()
    poll()
    assert slack.fetches() == 2

    wakes.beat()
    poll()
    assert slack.fetches() == 2


def test_with_a_gateway_up_a_backstop_fetch_still_finds_what_it_never_signalled(
    tmp_path, slack, monkeypatch
):
    delivered: list = []
    poll = _poller(tmp_path, delivered)
    wakes.beat()
    poll()
    slack.replies.append(reply(NEW, "in a channel the socket does not report"))
    poll()
    assert delivered == []

    monkeypatch.setattr(slack_events, "_BACKSTOP", 0.0)
    poll()

    assert len(delivered) == 1 and "the socket does not report" in delivered[0]


def test_a_pattern_delivers_only_the_messages_it_matches_and_passes_the_rest(tmp_path, slack):
    delivered: list = []
    poll = _poller(tmp_path, delivered, match="(?i)deploy")
    poll()
    slack.replies.append(reply(NEW, "lunch?"))
    _signal()
    poll()
    assert delivered == []

    slack.replies.append(reply("1794857995.000003", "<@U0ANN> the Deploy is done"))
    _signal()
    poll()

    [message] = delivered
    assert "Deploy is done" in message and "lunch" not in message
    assert "1 new reply matching '(?i)deploy'" in message


def test_a_channel_delivers_the_messages_posted_in_it(tmp_path, slack):
    slack.posts.append(post(OLD, "an old post"))
    delivered: list = []
    poll = _poller(tmp_path, delivered, conversation=CHANNEL)
    poll()
    slack.posts.append(post(NEW, "a new post"))

    _signal(CHANNEL)
    poll()

    [message] = delivered
    assert message.startswith(f"Slack channel {CHANNEL.link}: 1 new message\n")
    assert "a new post" in message and "an old post" not in message
    assert delivery.label_of(message) == "Slack message from Ann"
    assert (tmp_path / "cursors" / "lemon.Ann" / "slack" / f"{CHANNEL.channel}.json").exists()


def _lemon_following(tmp_path) -> tuple:
    path = store.create("following", datetime.date(2026, 11, 20))
    with db.connect() as conn:
        attached.attach(conn, "claude:follower", path)
        lemon_id = identity.ensure(conn, path)
    path.write_text(waiters.add(path.read_text(), f"lemonaid watch slack {LINK}"))
    return path, lemon_id


def test_a_thread_quiet_for_seven_days_ends_once_and_leaves_watching(tmp_path, slack):
    path, lemon_id = _lemon_following(tmp_path)
    slack.replies[:] = [reply(f"{int(time.time()) - 8 * 86400}.000100", "long ago")]
    delivered: list = []
    poll = _poller(tmp_path, delivered, lemon_id=lemon_id)

    poll()
    poll()

    [message] = delivered
    assert message.startswith(f"Stopped following Slack thread {LINK}: nothing new in 7 days")
    assert waiters.commands(path.read_text()) == []


def test_a_done_brief_ends_it_without_asking_slack(tmp_path, slack):
    path, lemon_id = _lemon_following(tmp_path)
    delivered: list = []

    _poller(tmp_path, delivered, lemon_id=lemon_id, done=True)()

    assert [m.split(":")[-1] for m in delivered] == [
        " your brief is done; its line left ## Watching"
    ]
    assert slack.calls == []
    assert waiters.commands(path.read_text()) == []


def _inbox_row():
    with db.connect() as conn:
        return db.get_by_channel(conn, signed_out.CHANNEL, unread_only=False)


def test_with_no_sign_in_the_lemon_hears_once_and_the_user_sees_it_in_the_inbox(
    tmp_path, slack, monkeypatch
):
    current = [None]
    monkeypatch.setattr(session, "load", lambda: current[0])
    delivered: list = []
    poll = _poller(tmp_path, delivered, every=0)

    poll()
    poll()

    assert len(delivered) == 1 and "lemonaid slack signin" in delivered[0]
    assert "lemonaid slack signin" in _inbox_row().message
    assert slack.calls == []

    current[0] = SESSION
    signed_out.signed_in()
    poll()
    assert slack.fetches() == 1
    assert _inbox_row().is_archived


def test_a_session_slack_refuses_pauses_every_call_until_a_new_sign_in(tmp_path, slack):
    slack.error = api.Expired("conversations.replies: invalid_auth")
    delivered: list = []
    poll = _poller(tmp_path, delivered)

    poll()
    slack.error = None
    _signal()
    poll()

    assert len(delivered) == 1 and "no longer accepts" in delivered[0]
    assert slack.fetches() == 1
    assert signed_out.refused(SESSION)


def test_an_unreachable_slack_tells_nobody_and_is_tried_again(tmp_path, slack):
    slack.error = api.Unavailable("conversations.replies: URLError")
    delivered: list = []

    _poller(tmp_path, delivered, every=0)()
    slack.error = None
    _poller(tmp_path, delivered)()

    assert delivered == []
    assert slack.fetches() == 2
