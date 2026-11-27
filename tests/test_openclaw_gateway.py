"""Calling the OpenClaw gateway over a held connection, and falling back to the CLI."""

import base64
import hashlib
import json
import queue
import sqlite3
import subprocess
import sys
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from websockets import exceptions as websocket_errors

from lemonaid.openclaw import gateway, turns


class _Socket:
    """Answers each request with *answer*, after an event the reader must pass over; with *drop*,
    it has closed."""

    def __init__(self, answer: dict, drop: bool = False) -> None:
        self.answer, self.drop = answer, drop
        self.incoming: queue.Queue = queue.Queue()
        if drop:
            self.incoming.put(None)

    def send(self, text: str) -> None:
        if self.drop:
            raise websocket_errors.ConnectionClosedError(None, None)
        request = json.loads(text)
        self.incoming.put(json.dumps({"type": "event", "event": "tick", "payload": {}}))
        self.incoming.put(
            json.dumps({"type": "res", "id": request["id"], "ok": True, "payload": self.answer})
        )

    def recv(self, timeout: float | None = None) -> str:
        return self.incoming.get(timeout=timeout)

    def __iter__(self):
        while (text := self.incoming.get()) is not None:
            yield text


def _unpadded(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def test_the_device_is_the_key_s_fingerprint_and_signs_the_v3_payload():
    key = ed25519.Ed25519PrivateKey.generate()

    signed = gateway._device(key, "tok", "nonce-1", 1700)

    raw = _unpadded(signed["publicKey"])
    assert signed["id"] == hashlib.sha256(raw).hexdigest()
    payload = (
        f"v3|{signed['id']}|cli|cli|operator|operator.read,operator.write|1700|tok|nonce-1"
        f"|{sys.platform.lower()}|"
    )
    key.public_key().verify(_unpadded(signed["signature"]), payload.encode())


def test_a_held_call_passes_over_events_and_reconnects_once_after_a_drop(monkeypatch):
    sockets = [_Socket({}, drop=True), _Socket({"messages": [1]})]
    monkeypatch.setattr(gateway, "_connect", lambda: sockets.pop(0))

    held = gateway._Held()

    assert held.call("chat.history", {"sessionKey": "k"}, 5) == {"messages": [1]}
    assert sockets == []


def test_a_held_connection_keeps_the_turns_its_events_say_failed(monkeypatch):
    socket = _Socket({})
    failed = {
        "runId": "r1",
        "stream": "lifecycle",
        "ts": 1795671692929,
        "sessionKey": "agent:main:failing",
    }
    for payload in (
        {**failed, "data": {"phase": "error", "error": "Auth profile unavailable"}},
        {**failed, "runId": "r2", "data": {"phase": "end"}},
    ):
        socket.incoming.put(json.dumps({"type": "event", "event": "agent", "payload": payload}))
    monkeypatch.setattr(gateway, "_connect", lambda: socket)

    gateway._Held().call("chat.history", {"sessionKey": "k"}, 5)

    assert turns.failed("agent:main:failing") == [
        turns.Failure(1795671692929, "Auth profile unavailable")
    ]


def test_a_held_connection_tells_when_a_session_s_turn_runs_and_ends(monkeypatch):
    monkeypatch.setattr(turns, "_ended", {})
    monkeypatch.setattr(turns, "_recorded", {})
    monkeypatch.setattr(turns, "_started", {})
    socket = _Socket({})
    run = {"runId": "r1", "stream": "lifecycle", "ts": 1795671692000, "sessionKey": "agent:main:x"}
    for payload in (
        {**run, "data": {"phase": "start"}},
        {**run, "ts": 1795671693000, "data": {"phase": "end"}},
    ):
        socket.incoming.put(json.dumps({"type": "event", "event": "agent", "payload": payload}))
    monkeypatch.setattr(gateway, "_connect", lambda: socket)
    told: list[tuple[str, float | None]] = []

    gateway._Held(lambda key, at, *_: told.append((key, at))).call("chat.history", {}, 5)

    assert told == [("agent:main:x", 1795671692.0), ("agent:main:x", None)]


def test_listening_hears_a_turn_before_any_call(monkeypatch):
    monkeypatch.setattr(turns, "_ended", {})
    monkeypatch.setattr(turns, "_recorded", {})
    monkeypatch.setattr(turns, "_started", {})
    monkeypatch.setattr(gateway, "_held", None)
    socket = _Socket({})
    started = {"runId": "r1", "stream": "lifecycle", "ts": 1795671692000, "sessionKey": "k"}
    socket.incoming.put(json.dumps({"type": "event", "event": "agent", "payload": started}))
    monkeypatch.setattr(gateway, "_connect", lambda: socket)
    told: queue.Queue = queue.Queue()
    gateway.hold(lambda key, at, *_: told.put((key, at)))

    gateway.listen()

    assert told.get(timeout=5) == ("k", 1795671692.0)
    socket.incoming.put(None)


def test_a_held_connection_reconnects_after_its_turn_callback_raises(monkeypatch):
    monkeypatch.setattr(turns, "_ended", {})
    monkeypatch.setattr(turns, "_recorded", {})
    monkeypatch.setattr(turns, "_started", {})
    broken = _Socket({})
    started = {"runId": "r1", "stream": "lifecycle", "ts": 1795671692000, "sessionKey": "k"}
    broken.incoming.put(json.dumps({"type": "event", "event": "agent", "payload": started}))
    sockets = [broken, _Socket({"messages": [1]})]
    monkeypatch.setattr(gateway, "_connect", lambda: sockets.pop(0))

    entered: list[str] = []

    def locked(key: str, at: float | None, started: float, ended: float) -> None:
        entered.append(key)
        raise sqlite3.OperationalError("database is locked")

    held = gateway._Held(locked)

    assert held.call("chat.history", {}, 5) == {"messages": [1]}
    assert sockets == []
    assert entered == ["k"]


def test_an_error_answer_raises():
    socket = _Socket({})
    socket.send = lambda text: socket.incoming.put(  # type: ignore[method-assign]
        json.dumps(
            {"type": "res", "id": json.loads(text)["id"], "ok": False, "error": {"code": "NOPE"}}
        )
    )

    with pytest.raises(OSError, match="NOPE"):
        gateway._request(socket, "chat.history", {}, 5)


def test_a_held_connection_answers_concurrent_calls_each_with_its_own_reply(monkeypatch):
    monkeypatch.setattr(gateway, "_connect", lambda: _Socket({"ok": 1}))
    held = gateway._Held()

    results: list[dict] = []
    threads = [
        threading.Thread(target=lambda: results.append(held.call("health", {}, 5)))
        for _ in range(8)
    ]
    for each in threads:
        each.start()
    for each in threads:
        each.join()

    assert results == [{"ok": 1}] * 8


def test_call_falls_back_to_the_cli_when_the_held_connection_fails(monkeypatch):
    def refused() -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(gateway, "_connect", refused)
    monkeypatch.setattr(gateway, "_held", gateway._Held())
    ran = []

    def run(argv, **_):
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 0, '{"messages": []}', "")

    monkeypatch.setattr(gateway.subprocess, "run", run)

    assert gateway.call("openclaw", "chat.history", {"sessionKey": "k"}, 5) == {"messages": []}
    assert ran[0][:4] == ["openclaw", "gateway", "call", "chat.history"]


def test_a_call_kept_off_the_cli_fails_rather_than_fall_back(monkeypatch):
    def refused() -> None:
        raise OSError("connection refused")

    ran = []
    monkeypatch.setattr(gateway.subprocess, "run", lambda argv, **_: ran.append(argv))
    monkeypatch.setattr(gateway, "_connect", refused)
    monkeypatch.setattr(gateway, "_held", gateway._Held())

    with pytest.raises(OSError, match="held gateway connection failed"):
        gateway.call("openclaw", "chat.send", {"sessionKey": "k"}, 5, by_cli=False)

    monkeypatch.setattr(gateway, "_held", None)
    with pytest.raises(OSError, match="holds no gateway connection"):
        gateway.call("openclaw", "chat.send", {"sessionKey": "k"}, 5, by_cli=False)
    assert ran == []
