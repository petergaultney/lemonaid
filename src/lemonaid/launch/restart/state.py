"""Operation journal. Uncertain operations retain their reservation until reconciled."""

import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
import time
import typing as ty
from collections import abc

from ...inbox import db
from . import expiry

TERMINAL = ("complete", "failed", "partial")


def get(conn: sqlite3.Connection, token: str) -> dict[str, ty.Any]:
    row = conn.execute("SELECT * FROM lemon_restarts WHERE token = ?", (token,)).fetchone()
    if row is None:
        raise ValueError("No restart has that operation ID")

    return {**dict(row), "plan": json.loads(row["plan"]), "evidence": json.loads(row["evidence"])}


def active(conn: sqlite3.Connection, channel: str) -> dict[str, ty.Any] | None:
    row = conn.execute(
        "SELECT token FROM lemon_restarts WHERE channel = ? AND phase NOT IN (?, ?, ?)",
        (channel, *TERMINAL),
    ).fetchone()
    operation = get(conn, row["token"]) if row else None
    return None if operation and expiry.reconcile(conn, operation) else operation


@contextlib.contextmanager
def barrier(channel: str, exclusive: bool = False) -> abc.Iterator[None]:
    key = hashlib.sha256(channel.encode()).hexdigest()
    path = db.get_db_path().parent / f"restart-{key}.lock"
    with path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield


def blocked(channel: str, *, replacement: bool = False) -> bool:
    with db.connect() as conn:
        operation = active(conn, channel)
    if operation is None:
        return False

    token = os.environ.get("LEMONAID_RESTART_TOKEN", "")
    return not (
        replacement
        and token == operation["token"]
        and operation["phase"] in ("starting", "verifying")
    )


@contextlib.contextmanager
def admission(channel: str, *, replacement: bool = False) -> abc.Iterator[bool]:
    with barrier(channel):
        yield not blocked(channel, replacement=replacement)


def reserve(conn: sqlite3.Connection, plan: dict[str, ty.Any]) -> str:
    channel = plan["channel"]
    with barrier(channel, exclusive=True):
        if (
            active(conn, channel)
            or conn.execute(
                "SELECT 1 FROM brief_handoffs WHERE source = ? AND phase NOT IN ('complete','failed')",
                (channel,),
            ).fetchone()
        ):
            raise ValueError("This lemon already has a restart or handoff in progress")

        token = secrets.token_hex(12)
        conn.execute(
            "INSERT INTO lemon_restarts(token,channel,phase,created,deadline,plan) VALUES (?,?,'planned',?,?,?)",
            (token, channel, time.time(), time.time() + 90, json.dumps(plan)),
        )
        conn.commit()
    return token


def update(conn: sqlite3.Connection, token: str, phase: str, **evidence: ty.Any) -> None:
    conn.execute(
        "UPDATE lemon_restarts SET phase = ?, evidence = json_patch(evidence, ?), error = COALESCE(?, error) WHERE token = ?",
        (phase, json.dumps(evidence), evidence.get("error"), token),
    )
    conn.commit()


def evidence(conn: sqlite3.Connection, token: str, **fields: ty.Any) -> None:
    conn.execute(
        "UPDATE lemon_restarts SET evidence = json_patch(evidence, ?) WHERE token = ?",
        (json.dumps(fields), token),
    )
    conn.commit()


def recovery_required(conn: sqlite3.Connection, channel: str) -> bool:
    row = conn.execute(
        "SELECT * FROM lemon_restarts WHERE channel = ? ORDER BY created DESC LIMIT 1", (channel,)
    ).fetchone()
    if row is None or row["phase"] != "partial":
        return False

    generation = conn.execute(
        "SELECT registered FROM harness_generations WHERE channel = ?", (channel,)
    ).fetchone()
    return generation is None or generation["registered"] <= row["created"]
