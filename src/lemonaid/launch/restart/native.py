"""Bind native hook evidence to a dedicated local harness generation."""

import dataclasses
import json
import os
import sqlite3
import time
import typing as ty
from pathlib import Path

from ...claude import launch_args
from ...inbox import db
from ...inbox.channel import channel_id, full_channel_id
from ...log import get_logger
from ...messages import recipient
from . import configuration, native_data, pane, process, settings, state

_log = get_logger("restart.native")


def channel(harness: str, session: str) -> str:
    return (
        channel_id(harness, session) if harness == "claude" else full_channel_id(harness, session)
    )


def harness_parent(harness: str) -> process.Identity | None:
    try:
        ancestors = process.ancestry(os.getppid())
    except (OSError, TimeoutError) as error:
        _log.info("Cannot inspect native hook ancestry: %s", error)
        return None

    for entry in ancestors:
        name = Path(entry.executable).name
        if name == harness or (harness == "claude" and recipient.is_harness(name)):
            return entry

    return None


def registered(conn: sqlite3.Connection, target: str) -> dict[str, ty.Any] | None:
    row = conn.execute("SELECT * FROM harness_generations WHERE channel = ?", (target,)).fetchone()
    if row is None:
        return None

    return {
        **dict(row),
        "identity": json.loads(row["identity"]),
        "settings": json.loads(row["settings"]),
    }


def observe(data: dict[str, ty.Any], harness: str) -> bool:
    session = data.get("session_id") or data.get("thread_id") or data.get("thread-id")
    if not session:
        return True

    target = channel(harness, session)
    token = os.environ.get("LEMONAID_RESTART_TOKEN", "")
    with state.barrier(target), db.connect() as conn:
        operation = state.active(conn, target)
        if operation and (
            token != operation["token"] or operation["phase"] not in ("starting", "verifying")
        ):
            return False

        identity = harness_parent(harness)
        previous = registered(conn, target)
        if identity is None:
            return operation is None and previous is None
        if (
            previous
            and previous["identity"] != dataclasses.asdict(identity)
            and process.same(process.Identity(**previous["identity"]))
        ):
            return False

        try:
            observed = data
            if harness == "codex":
                row = db.get_by_channel(conn, target, unread_only=False)
                observed = native_data.enrich(
                    data,
                    launch_args.argv(identity.pid),
                    session,
                    str(row.metadata.get("session_path") or "") if row else "",
                )
            effective = settings.capture(harness, identity.pid, observed, os.environ)
            effective["files"] = configuration.snapshot(
                configuration.paths(
                    harness,
                    os.environ,
                    str(data.get("cwd") or os.getcwd()),
                    str(effective.get("profile") or ""),
                    effective["argv"],
                ),
                identity.started,
            )
        except ValueError as error:
            _log.info("incomplete native settings for %s: %s", target, error)
            effective = {"error": str(error)}
        if operation:
            plan = operation["plan"]
            expected = pane.Pane(**plan["pane"])
            current = pane.by_id(expected.socket, expected.pane)
            ancestors = process.ancestry(identity.pid)
            if (
                session != plan["session_id"]
                or current.pane != expected.pane
                or current.window != expected.window
                or current.pid == expected.pid
                or not any(entry.pid == current.pid for entry in ancestors)
                or identity.tty != current.tty.removeprefix("/dev/")
            ):
                return False

        conn.execute(
            "INSERT OR REPLACE INTO harness_generations VALUES (?, ?, ?, ?, ?, ?)",
            (
                target,
                session,
                json.dumps(dataclasses.asdict(identity)),
                json.dumps(effective),
                token,
                time.time(),
            ),
        )
        conn.commit()
    return True


def accept_exit(target: str) -> bool:
    with db.connect() as conn:
        generation = registered(conn, target)
        operation = state.active(conn, target)
    if operation:
        return False
    if generation is None:
        return True

    current = harness_parent(target.partition(":")[0])
    return current is not None and dataclasses.asdict(current) == generation["identity"]


def turn_allowed(data: dict[str, ty.Any], harness: str) -> bool:
    session = data.get("session_id") or data.get("thread_id")
    if not session:
        return True

    return not state.blocked(channel(harness, session), replacement=True)
