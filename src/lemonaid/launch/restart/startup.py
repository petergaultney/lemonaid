"""Token-bound readiness and one bounded recovery of a failed replacement."""

import dataclasses
import json
import sqlite3
import time
import typing as ty

from ...config import load_config
from ...log import get_logger
from ...messages import resume_log, store
from ...watch import registry, stopping
from . import environment, native, pane, process, settings, state, watchers

_log = get_logger("restart.startup")

_PROMPT = (
    "Your harness was restarted in the same native session. Keep your existing task and brief. "
    "Reply briefly without tools while restart verifies. Your rebuilt watcher will deliver "
    "pending messages and continuation instructions after verification; follow that batch."
)


def ready(conn: sqlite3.Connection, operation: dict[str, ty.Any]) -> bool:
    plan = operation["plan"]
    generation = native.registered(conn, plan["channel"])
    if (
        not generation
        or generation["token"] != operation["token"]
        or generation["session_id"] != plan["session_id"]
    ):
        return False

    replacement = pane.Pane(**operation["evidence"]["replacement"])
    pane.check(replacement)
    try:
        pane.model(
            replacement, plan["settings"]["model"], str(plan["settings"].get("effort") or "")
        )
    except ValueError as error:
        _log.debug("Replacement model not yet verified: %s", error)
        return False
    source = process.Identity(**generation["identity"])
    if not process.same(source) or not any(
        p.pid == replacement.pid for p in process.ancestry(source.pid)
    ):
        return False

    keys = set(plan["settings"]) - {"argv"}
    if any(generation["settings"].get(key) != plan["settings"][key] for key in keys):
        return False

    return watchers.ready(plan["channel"], operation["token"], source)


def _launch(
    conn: sqlite3.Connection, token: str, target: pane.Pane, root: process.Identity
) -> pane.Pane:
    plan = state.get(conn, token)["plan"]
    state.update(conn, token, "starting")
    replacement = pane.replace(
        target,
        root,
        plan["cwd"],
        settings.line(plan["argv"], _PROMPT, plan["settings"].get("environment", {})),
        {
            **environment.values(plan["settings"].get("environment", {})),
            "LEMONAID_RESTART_TOKEN": token,
        },
    )
    replacement_root = process.inspect(replacement.pid)
    if replacement_root is None:
        raise ValueError("Replacement exited before its process generation could be captured")

    state.update(
        conn,
        token,
        "verifying",
        replacement=dataclasses.asdict(replacement),
        replacement_root=dataclasses.asdict(replacement_root),
        watcher={},
    )
    watchers.start(plan, token)
    return replacement


def _recovery(
    conn: sqlite3.Connection, operation: dict[str, ty.Any], replacement: pane.Pane
) -> pane.Pane:
    plan, token = operation["plan"], operation["token"]
    if operation["evidence"].get("recovery_attempt"):
        raise ValueError("Replacement and its single recovery both exited before readiness")

    config = load_config().messages
    inbox = store.inbox_for_id(plan["lemon_id"])
    if (
        resume_log.within(resume_log.entries(inbox), time.time(), config.autoresume_window)
        >= config.autoresume_max
    ):
        raise ValueError("Recovery refused by the shared autoresume crash-loop limit")

    for waiter in registry.mine(plan["channel"]):
        stopping.stop(waiter, f"restart recovery {token}")
    state.evidence(conn, token, recovery_attempt=1)
    resume_log.record(inbox)
    return _launch(
        conn, token, replacement, process.Identity(**operation["evidence"]["replacement_root"])
    )


def run(conn: sqlite3.Connection, token: str) -> None:
    plan = state.get(conn, token)["plan"]
    target, root = pane.Pane(**plan["pane"]), process.Identity(**plan["root"])
    replacement = _launch(conn, token, target, root)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        operation = state.get(conn, token)
        if ready(conn, operation):
            generation = native.registered(conn, plan["channel"])
            conn.execute(
                "UPDATE notifications SET metadata = json_patch(json_remove(metadata, '$.exited_at', '$.exit_reason'), ?) WHERE channel = ?",
                (
                    json.dumps(
                        {
                            "harness_pid": generation["identity"]["pid"],
                            "harness_started": generation["identity"]["started"],
                            "tty": replacement.tty,
                            "tmux_socket": replacement.socket,
                            "session_start_source": "restart",
                            "session_start_at": time.time(),
                            "restart_generation": token,
                        }
                    ),
                    plan["channel"],
                ),
            )
            conn.commit()
            pane.restore(replacement, plan["exit_option"])
            store.send(
                store.inbox_for_id(plan["lemon_id"]),
                f"Restart {token} verified this session and rebuilt its watcher. "
                "Read pending messages, rearm your declared subscriptions if needed, and "
                "continue your existing task and brief. Do not start a new task.",
                "lemonaid restart",
            )
            state.update(conn, token, "complete")
            return

        if pane.check(replacement).dead:
            replacement = _recovery(conn, operation, replacement)
        time.sleep(0.1)
    raise TimeoutError("Harness or new-generation watcher did not verify within 60 seconds")
