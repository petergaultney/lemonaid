"""Calling the OpenClaw gateway: over one WebSocket held open for the process's life, or with a
fresh `openclaw gateway call` per request where that can't be had.

The CLI takes about a second for any call, almost all of it starting up and signing in, which
is too slow for a page that reads a conversation every few seconds, so a long-lived process
asks to `hold` a connection. It signs
in on loopback as a device of its own (a key kept in lemonaid's state directory), which the
gateway pairs without asking, and as the CLI's client kind, so what it sends reads as the
owner's, as the CLI's does.
"""

import base64
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import typing as ty
import uuid
from pathlib import Path

from ..log import get_logger
from . import turns

try:  # the `openclaw` extra
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from websockets import exceptions as websocket_errors
    from websockets.sync import client as websocket_client
except ImportError:
    websocket_client = None

_log = get_logger("openclaw.gateway")

_PROTOCOL = 4
_CLIENT, _MODE, _ROLE = "cli", "cli", "operator"
_SCOPES = ["operator.read", "operator.write"]
_CONNECT_SECONDS = 10


def _config() -> dict[str, ty.Any]:
    path = Path(os.environ.get("OPENCLAW_CONFIG_PATH") or "~/.openclaw/openclaw.json")
    try:
        return json.loads(path.expanduser().read_text()).get("gateway") or {}
    except (OSError, ValueError) as error:
        raise OSError(f"can't read OpenClaw's gateway settings: {error}") from error


def _key() -> "ed25519.Ed25519PrivateKey":
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    path = state / "openclaw-device.pem"
    if path.exists():
        loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
        assert isinstance(loaded, ed25519.Ed25519PrivateKey)
        return loaded

    key = ed25519.Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return key


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _device(key: "ed25519.Ed25519PrivateKey", token: str, nonce: str, signed_at: int) -> dict:
    """The connect request's `device`: the v3 payload signed, as the gateway checks it."""
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    device_id = hashlib.sha256(raw).hexdigest()
    payload = "|".join(
        [
            "v3",
            device_id,
            _CLIENT,
            _MODE,
            _ROLE,
            ",".join(_SCOPES),
            str(signed_at),
            token,
            nonce,
            sys.platform.lower(),
            "",
        ]
    )
    return {
        "id": device_id,
        "publicKey": _b64url(raw),
        "signature": _b64url(key.sign(payload.encode())),
        "signedAt": signed_at,
        "nonce": nonce,
    }


def _answer(frame: dict) -> dict:
    """A response frame's payload. Raises OSError for an error."""
    if not frame.get("ok"):
        error = frame.get("error") or {}
        raise OSError(f"{error.get('code')}: {error.get('message')}")
    return frame.get("payload") or {}


def _reply(socket: ty.Any, request_id: str, timeout: float) -> dict:
    """The response to *request_id* on a connection nothing else reads, passing over events."""
    while True:
        frame = json.loads(socket.recv(timeout=timeout))
        if frame.get("type") == "res" and frame.get("id") == request_id:
            return _answer(frame)


def _request(socket: ty.Any, method: str, params: dict, timeout: float) -> dict:
    request_id = str(uuid.uuid4())
    socket.send(json.dumps({"type": "req", "id": request_id, "method": method, "params": params}))
    return _reply(socket, request_id, timeout)


def _connect() -> ty.Any:
    settings = _config()
    token = (settings.get("auth") or {}).get("token")
    if not isinstance(token, str):
        raise OSError("OpenClaw's gateway token isn't a plain value lemonaid can read")

    port = int(os.environ.get("OPENCLAW_GATEWAY_PORT") or settings.get("port") or 18789)
    socket = websocket_client.connect(
        f"ws://127.0.0.1:{port}", open_timeout=_CONNECT_SECONDS, max_size=None
    )
    challenge = json.loads(socket.recv(timeout=_CONNECT_SECONDS)).get("payload") or {}
    params = {
        "minProtocol": _PROTOCOL,
        "maxProtocol": _PROTOCOL,
        "client": {"id": _CLIENT, "version": "lemonaid", "platform": sys.platform, "mode": _MODE},
        "role": _ROLE,
        "scopes": _SCOPES,
        "auth": {"token": token},
        "device": _device(_key(), token, str(challenge["nonce"]), int(challenge["ts"])),
    }
    try:
        _request(socket, "connect", params, _CONNECT_SECONDS)
    except OSError:
        socket.close()
        raise
    return socket


class _Held:
    """One connection, opened on first use or `listen` and again after it drops. A reader thread
    takes every frame as it comes, handing each answer to the call waiting on it and each `agent`
    event to `turns`, and dropping the other events: a connection nothing reads stops answering its keepalive pings, and the gateway's events (a tick
    every 15 s, and more) would back up until it does."""

    def __init__(self, on_turn: turns.Record | None = None) -> None:
        self._on_turn = on_turn
        self._lock = threading.Lock()  # opening a connection, and sending on it
        self._socket: ty.Any = None
        self._waiting: dict[
            str, tuple[ty.Any, queue.Queue]
        ] = {}  # request id: its socket, its answer

    def _read(self, socket: ty.Any) -> None:
        try:
            for text in socket:
                frame = json.loads(text)
                if frame.get("type") == "res" and (waiting := self._waiting.get(frame.get("id"))):
                    waiting[1].put(frame)
                elif frame.get("type") == "event" and frame.get("event") == "agent":
                    turns.note(frame.get("payload") or {})
                    if self._on_turn:
                        turns.track(frame.get("payload") or {}, self._on_turn)
        except (websocket_errors.ConnectionClosed, ValueError) as error:
            _log.info("gateway connection closed: %s", error)
        except Exception:  # the reader thread's top: log it, and let the next call reconnect
            _log.exception("gateway reader failed")
        with self._lock:
            if self._socket is socket:
                self._socket = None
        for on, answer in list(self._waiting.values()):
            if on is socket:
                answer.put(None)

    def _open(self) -> ty.Any:
        """The connection, opened with its reader if it isn't; the caller holds the lock."""
        if self._socket is None:
            self._socket = _connect()
            threading.Thread(target=self._read, args=(self._socket,), daemon=True).start()
        return self._socket

    def listen(self) -> None:
        with self._lock:
            self._open()

    def _send(self, request: dict, answer: queue.Queue) -> None:
        with self._lock:
            self._waiting[request["id"]] = (self._open(), answer)
            try:
                self._socket.send(json.dumps(request))
            except websocket_errors.ConnectionClosed:
                self._socket = None  # before its reader notices, so the retry opens another
                raise

    def call(self, method: str, params: dict, timeout: float) -> dict:
        for attempt in (1, 2):
            request_id = str(uuid.uuid4())
            answer: queue.Queue = queue.Queue()
            try:
                self._send(
                    {"type": "req", "id": request_id, "method": method, "params": params}, answer
                )
                frame = answer.get(timeout=timeout)
            except websocket_errors.ConnectionClosed:
                frame = None
            except queue.Empty as error:
                raise OSError(f"{method} took longer than {timeout:g}s") from error
            finally:
                self._waiting.pop(request_id, None)
            if frame is not None:
                return _answer(frame)

            if attempt == 2:
                raise OSError("the gateway connection dropped")
        raise AssertionError("unreachable")


_held: _Held | None = None


def hold(on_turn: turns.Record | None = None) -> bool:
    """Call the gateway over one held connection from now on, for a long-lived process, telling
    *on_turn* when a session's turn runs or ends. False without the `openclaw` extra, which
    leaves calls on the CLI."""
    global _held
    if websocket_client is not None and _held is None:
        _held = _Held(on_turn)
    return _held is not None


def listen() -> None:
    """Open the held connection now if it isn't open, so its events arrive without waiting for a
    call. Raises when the gateway can't be reached."""
    if _held is not None:
        _held.listen()


def _by_cli(cli: str, method: str, params: dict, timeout: float) -> dict:
    try:
        done = subprocess.run(
            [cli, "gateway", "call", method, "--json", "--params", json.dumps(params)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OSError(f"{method}: {error}") from error

    if done.returncode != 0:
        raise OSError(done.stderr.strip() or f"{method} exited {done.returncode}")

    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise OSError(f"{method} said something other than JSON: {error}") from error


def held() -> bool:
    """Whether calls go over a held connection, which takes *params* of any size; the CLI's go
    in one command-line argument, which the system caps."""
    return _held is not None


def call(cli: str, method: str, params: dict, timeout: float, by_cli: bool = True) -> dict:
    """The gateway's answer to *method*, by the CLI only if the held connection fails and
    *by_cli*. Raises OSError when it gives none."""
    if _held is not None:
        try:
            return _held.call(method, params, timeout)
        except (OSError, ValueError, KeyError) as error:
            if not by_cli:
                raise OSError(f"the held gateway connection failed: {error}") from error

            _log.warning("held gateway connection failed, using the CLI: %s", error)
    if not by_cli:
        raise OSError("lemonaid holds no gateway connection here (the openclaw extra)")

    return _by_cli(cli, method, params, timeout)
