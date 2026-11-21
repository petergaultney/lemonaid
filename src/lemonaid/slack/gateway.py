"""The scout host's one Slack socket: the web client's own gateway websocket, opened with the
user's session, which says when a message arrives in a thread or channel some lemon follows.

It only signals it (`wakes.signal`). Each follower then fetches what is new from its own
cursor, since the socket has no replay; on each connect the gateway signals everything
followed, so a message sent while it was down is fetched then. It runs, as a scout host
service, while a scout follows something, `[slack] push` is on and the `slack` extra is
installed.
"""

import dataclasses
import json
import threading
import time
from collections import abc

from ..config import load_config
from ..log import get_logger
from ..slack_config import SlackConfig
from ..watch import host_services
from . import api, gateway_socket, presence, session, signed_out, wakes

_log = get_logger("slack.gateway")

_PING = 20.0
_BEAT = 15.0
_FIRST_RETRY = 5.0
_LAST_RETRY = 300.0
_SIGNED_OUT_CHECK = 30.0
_CHECK = 5.0  # seconds between the service's looks at what is followed
_LINGER = 300.0  # the socket stays up this long after the last follower stops


def _signal(raw: str | bytes) -> str:
    """Signal the thread a message event belongs to, and its channel for a message posted
    there; the event's type."""
    try:
        event = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(event, dict):
        return ""

    if event.get("type") == "message":
        channel = event.get("channel", "")
        thread = event.get("thread_ts") or (event.get("message") or {}).get("thread_ts")
        if thread and wakes.signal(channel, thread):
            _log.info("reply in a followed thread %s %s", channel, thread)
        if (not thread or event.get("subtype") == "thread_broadcast") and wakes.signal(channel, ""):
            _log.info("message in a followed channel %s", channel)
    return str(event.get("type", ""))


def _listen(
    socket: gateway_socket.Socket,
    current: session.Session,
    generation: str,
    stop: threading.Event,
    every: float,
) -> None:
    """Until *stop*, Slack's goodbye, or the saved session replaced, removed or refused."""
    wakes.beat()
    for channel, ts in wakes.followed(time.time()):
        wakes.signal(channel, ts)
    beat_at = ping_at = presence_at = time.monotonic() - every
    pings = 0
    while not stop.is_set():
        try:
            raw = socket.recv(timeout=1.0)
        except TimeoutError:
            raw = ""
        if wakes.session_generation() != generation or signed_out.refused(current):
            _log.info("the saved Slack session changed; closing the socket")
            return

        now = time.monotonic()
        if now - beat_at >= _BEAT:
            wakes.beat()
            beat_at = now
        if now - ping_at >= _PING:
            pings += 1
            socket.send(json.dumps({"id": pings, "type": "ping"}))
            ping_at = now
        if every and now - presence_at >= every:
            presence.record(current)
            presence_at = now
        if raw and _signal(raw) == "goodbye":
            return


def follow(stop: threading.Event, connect: gateway_socket.Connect = gateway_socket.connect) -> None:
    """Keep the socket up until *stop*, reconnecting with backoff."""
    delay = _FIRST_RETRY
    while not stop.is_set():
        generation = wakes.session_generation()
        try:
            current = session.load()
        except session.KeychainError as error:
            _log.warning("cannot read the Slack session: %s", error)
            current = None
        if current is None or signed_out.refused(current):
            stop.wait(_SIGNED_OUT_CHECK)
            continue

        try:
            with connect(gateway_socket.url(current), f"d={current.cookie}") as socket:
                _log.info("Slack socket up")
                delay = _FIRST_RETRY
                _listen(socket, current, generation, stop, load_config().slack.presence_every)
        except gateway_socket.Refused as error:
            _log.warning("Slack refused the socket: %s", error)
            try:
                api.call(current, "auth.test")
            except api.Expired:
                signed_out.mark(current)
            except (api.Failed, api.Unavailable) as checked:
                _log.warning("could not check the Slack session: %s", checked)
        except api.Expired:
            signed_out.mark(current)
        except (OSError, ValueError) as error:
            _log.warning("Slack socket down: %s", error)
        finally:
            wakes.went_down()
        stop.wait(delay)
        delay = min(delay * 2, _LAST_RETRY)


@dataclasses.dataclass
class _State:
    checked_at: float = -_CHECK
    followed: int = 0
    wanted_at: float = 0.0
    thread: threading.Thread | None = None
    stop: threading.Event = dataclasses.field(default_factory=threading.Event)


def _tick(state: _State, settings: abc.Callable[[], SlackConfig]) -> int:
    """Start the socket when anything is followed, and stop it `_LINGER` after nothing is."""
    now = time.monotonic()
    if now - state.checked_at < _CHECK:
        return state.followed

    state.checked_at, state.followed = now, len(wakes.followed(time.time()))
    push = settings().push and gateway_socket.available()
    if push and state.followed:
        state.wanted_at = now
        if state.thread is None or not state.thread.is_alive():
            state.stop = threading.Event()
            state.thread = threading.Thread(
                target=follow, args=(state.stop,), name="slack-gateway", daemon=True
            )
            state.thread.start()
    elif not push or now - state.wanted_at >= _LINGER:
        state.stop.set()
    return state.followed


def service() -> host_services.Service:
    state = _State()

    def join() -> None:
        state.stop.set()
        if state.thread is not None:
            state.thread.join(timeout=5)

    return host_services.Service(
        lambda quitting: _tick(state, lambda: load_config().slack), join, lambda: False
    )
