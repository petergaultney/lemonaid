import contextlib
import dataclasses
import json
import threading
import time
import types

import pytest

from lemonaid.inbox import db
from lemonaid.slack import api, gateway, gateway_socket, presence, session, signed_out, wakes
from lemonaid.slack_config import SlackConfig

from .shared import CHANNEL, SESSION, THREAD, Keychain

OTHER = ("C0ELSE", "1794850000.000001")


class _Socket:
    """Hands out *frames*, then sets *stop*, as the user leaving would."""

    def __init__(self, frames: list[dict], stop: threading.Event) -> None:
        self.frames, self.stop, self.sent = [json.dumps(f) for f in frames], stop, []

    def recv(self, timeout: float | None = None) -> str:
        if not self.frames:
            self.stop.set()
            raise TimeoutError

        return self.frames.pop(0)

    def send(self, message: str) -> None:
        self.sent.append(message)


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(session, "load", lambda: SESSION)
    monkeypatch.setattr(
        gateway, "load_config", lambda: types.SimpleNamespace(slack=SlackConfig(presence_every=0))
    )


def _follow_once(frames: list[dict]) -> _Socket:
    stop = threading.Event()
    socket = _Socket(frames, stop)

    @contextlib.contextmanager
    def connect(address: str, cookie: str):
        assert (
            address.startswith("wss://wss-primary.slack.com/") and cookie == f"d={SESSION.cookie}"
        )
        yield socket

    gateway.follow(stop, connect)
    return socket


def test_a_message_in_a_followed_thread_wakes_its_followers_and_no_others():
    wakes.follow(THREAD.channel, THREAD.ts, "lemon.Ann")
    before = wakes.stamp(THREAD.channel, THREAD.ts)
    time.sleep(0.01)

    def event(channel: str, thread: str, nested: bool = False) -> str:
        found = {"type": "message", "channel": channel, "ts": "1794857999.000001"}
        return json.dumps(
            {**found, "message": {"thread_ts": thread}}
            if nested
            else {**found, "thread_ts": thread}
        )

    assert gateway._signal(event(*OTHER)) == "message"
    assert not wakes.wake_path(*OTHER).exists()
    assert wakes.stamp(THREAD.channel, THREAD.ts) == before

    gateway._signal(event(THREAD.channel, THREAD.ts, nested=True))  # an edit names it inside
    assert wakes.stamp(THREAD.channel, THREAD.ts) > before


def test_a_message_posted_in_a_followed_channel_wakes_its_followers_and_a_reply_does_not():
    wakes.follow(CHANNEL.channel, CHANNEL.ts, "lemon.Ann")
    before = wakes.stamp(CHANNEL.channel, CHANNEL.ts)
    time.sleep(0.01)
    posted = {"type": "message", "channel": CHANNEL.channel, "ts": "1794857999.000001"}

    gateway._signal(json.dumps({**posted, "thread_ts": THREAD.ts}))
    assert wakes.stamp(CHANNEL.channel, CHANNEL.ts) == before

    gateway._signal(json.dumps({**posted, "thread_ts": THREAD.ts, "subtype": "thread_broadcast"}))
    broadcast = wakes.stamp(CHANNEL.channel, CHANNEL.ts)
    assert broadcast > before
    time.sleep(0.01)

    gateway._signal(json.dumps(posted))
    assert wakes.stamp(CHANNEL.channel, CHANNEL.ts) > broadcast


def test_each_connect_wakes_everything_followed_and_the_beat_ends_with_the_socket(signed_in):
    wakes.follow(THREAD.channel, THREAD.ts, "lemon.Ann")
    wakes.follow(CHANNEL.channel, CHANNEL.ts, "lemon.Sam")
    before = [wakes.stamp(c.channel, c.ts) for c in (THREAD, CHANNEL)]
    time.sleep(0.01)

    _follow_once([])

    after = [wakes.stamp(c.channel, c.ts) for c in (THREAD, CHANNEL)]
    assert all(a > b for a, b in zip(after, before, strict=True))  # catching up what it missed
    assert not wakes.gateway_up()


def test_a_refused_socket_with_a_session_slack_refuses_pauses_slack_and_tells_the_user(
    signed_in, monkeypatch
):
    stop = threading.Event()

    def refuse(address: str, cookie: str):
        stop.set()
        raise gateway_socket.Refused("HTTP 401")

    def call(current, method, **params):
        assert method == "auth.test"
        raise api.Expired("auth.test: invalid_auth")

    monkeypatch.setattr(api, "call", call)

    gateway.follow(stop, refuse)

    assert signed_out.refused(SESSION)
    with db.connect() as conn:
        row = db.get_by_channel(conn, signed_out.CHANNEL, unread_only=False)
    assert row is not None and "lemonaid slack signin" in row.message


def test_the_service_runs_the_socket_only_while_a_thread_is_followed_and_push_is_on(monkeypatch):
    started: list[threading.Event] = []

    def follow(stop: threading.Event) -> None:
        started.append(stop)
        stop.wait(5)

    monkeypatch.setattr(gateway, "follow", follow)
    monkeypatch.setattr(gateway_socket, "available", lambda: True)
    push = [SlackConfig(push=True)]
    state = gateway._State()

    assert gateway._tick(state, lambda: push[0]) == 0
    assert started == []

    wakes.follow(THREAD.channel, THREAD.ts, "lemon.Ann")
    state.checked_at = -gateway._CHECK
    assert gateway._tick(state, lambda: push[0]) == 1
    assert len(started) == 1 and not started[0].is_set()

    push[0] = SlackConfig(push=False)
    state.checked_at = -gateway._CHECK
    gateway._tick(state, lambda: push[0])
    assert started[0].is_set()


@pytest.mark.parametrize("change", ["removed", "replaced"])
def test_an_open_socket_closes_once_the_saved_session_is_removed_or_replaced(monkeypatch, change):
    monkeypatch.setattr(session, "_run", Keychain())
    session.save(SESSION)
    monkeypatch.setattr(
        gateway, "load_config", lambda: types.SimpleNamespace(slack=SlackConfig(presence_every=1))
    )
    used: list[session.Session] = []
    monkeypatch.setattr(presence, "record", used.append)
    stop = threading.Event()

    class _Changing(_Socket):
        def recv(self, timeout: float | None = None) -> str:
            if change == "removed":
                session.delete()
            else:
                session.save(dataclasses.replace(SESSION, token="xoxc-new", captured_at=2000.0))
            stop.set()  # so the test ends after one connection
            return json.dumps({"type": "hello"})

    @contextlib.contextmanager
    def connect(address: str, cookie: str):
        yield _Changing([], stop)

    gateway.follow(stop, connect)

    assert used == []  # due at once, but the old session was gone before it could be used
    assert not wakes.gateway_up()
