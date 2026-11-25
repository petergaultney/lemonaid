"""Calling the OpenClaw gateway over a held connection, and falling back to the CLI."""

import base64
import hashlib
import json
import queue
import subprocess
import sys
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from websockets import exceptions as websocket_errors

from lemonaid.openclaw import gateway


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
