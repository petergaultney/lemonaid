"""The machine's one Slack socket: the web client's own gateway websocket, opened with the
user's session, which says when a message arrives in a thread or channel some lemon follows.

It only signals it (`wakes.signal`). Each follower then fetches what is new from its own
cursor, since the socket has no replay; on each connect the gateway signals everything
followed, so a message sent while it was down is fetched then. One plugin process holds it
(`tick`), while that process follows something, `[slack] push` is on and the `slack` extra
is installed.
"""

import dataclasses
import fcntl
import json
import logging
import threading
import time
import typing as ty

from . import api, gateway_socket, presence, session, signed_out, wakes
from .config import SlackConfig

_log = logging.getLogger("lemonaid_slack.gateway")

_PING = 20.0
_BEAT = 15.0
_FIRST_RETRY = 5.0
_LAST_RETRY = 300.0
_SIGNED_OUT_CHECK = 30.0
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


def follow(
    stop: threading.Event,
    presence_every: float,
    connect: gateway_socket.Connect = gateway_socket.connect,
) -> None:
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
                _listen(socket, current, generation, stop, presence_every)
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
class State:
    wanted_at: float = 0.0
    thread: threading.Thread | None = None
    stop: threading.Event = dataclasses.field(default_factory=threading.Event)
    lock: ty.TextIO | None = None  # held while this process may hold the socket


def _claim(state: State) -> bool:
    """Whether this process holds the socket's lock: one plugin process holds the socket for
    every lemonaid process on the machine, and the others hear it through the wake files."""
    if state.lock is not None:
        return True

    path = wakes.state_dir() / "gateway.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return False

    state.lock = lock
    return True


def _release(state: State) -> None:
    if state.lock is not None and (state.thread is None or not state.thread.is_alive()):
        state.lock.close()
        state.lock = None


def tick(state: State, following: bool, settings: SlackConfig) -> None:
    """Hold the socket while this process follows anything, and drop it `_LINGER` after it
    stops."""
    now = time.monotonic()
    push = settings.push and gateway_socket.available()
    if push and following:
        state.wanted_at = now
        alive = state.thread is not None and state.thread.is_alive()
        if not alive and _claim(state):
            state.stop = threading.Event()
            state.thread = threading.Thread(
                target=follow,
                args=(state.stop, settings.presence_every),
                name="slack-gateway",
                daemon=True,
            )
            state.thread.start()
    elif not push or now - state.wanted_at >= _LINGER:
        state.stop.set()
    _release(state)


def join(state: State) -> None:
    state.stop.set()
    if state.thread is not None:
        state.thread.join(timeout=5)
    _release(state)
