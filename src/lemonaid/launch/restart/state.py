"""A small operation record and channel barrier; never replay an interrupted action."""

import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import time
from collections import abc

from ...inbox import db

TERMINAL = {"started", "failed", "partial"}


def _path(name: str):
    root = db.get_db_path().parent / "restarts"
    return root / name


def key(channel: str) -> str:
    return hashlib.sha256(channel.encode()).hexdigest()


def read(name: str) -> dict | None:
    try:
        return json.loads(_path(name).read_text())
    except FileNotFoundError:
        return None


def write(name: str, value: dict) -> None:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{secrets.token_hex(6)}.tmp")
    with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
        json.dump(value, file)
    temporary.replace(path)


@contextlib.contextmanager
def barrier(channel: str, exclusive: bool = False) -> abc.Iterator[None]:
    path = _path(key(channel) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield


def worker_active(token: str) -> bool:
    try:
        with _path(token + ".lock").open("r") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
    except FileNotFoundError:
        pass
    return False


def get(token: str) -> dict:
    if len(token) != 24 or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("Invalid restart operation ID")
    operation = read(token + ".json")
    if operation is None:
        raise ValueError("No restart has that operation ID")
    if (
        operation["phase"] not in TERMINAL
        and time.time() >= operation["deadline"]
        and not worker_active(token)
    ):
        return {
            **operation,
            "phase": "partial",
            "error": "Restart worker interrupted; inspect the pane and saved resume command",
        }
    return operation


def update(token: str, phase: str, **fields) -> None:
    current = get(token)
    if current["phase"] in TERMINAL and phase != current["phase"]:
        raise ValueError("Restart is already terminal; no action was repeated")
    operation = {**current, **fields, "phase": phase}
    write(token + ".json", operation)


def latest(channel: str) -> dict | None:
    pointer = read(key(channel) + ".json")
    return get(pointer["token"]) if pointer else None


def blocked(channel: str) -> bool:
    operation = latest(channel)
    return bool(operation and operation["phase"] not in TERMINAL)


@contextlib.contextmanager
def admission(channel: str) -> abc.Iterator[bool]:
    with barrier(channel):
        yield not blocked(channel)


def reserve(plan: dict) -> str:
    channel = plan["channel"]
    with barrier(channel, exclusive=True):
        if blocked(channel):
            raise ValueError("This lemon already has a restart in progress")
        token = secrets.token_hex(12)
        write(
            token + ".json",
            {
                "token": token,
                "phase": "planned",
                "deadline": time.time() + 90,
                "plan": plan,
                "error": "",
            },
        )
        write(key(channel) + ".json", {"token": token})
        return token
