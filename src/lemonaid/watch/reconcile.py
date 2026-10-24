"""`lemonaid watch reconcile`: one pass that makes the running push scouts match the lemons that need them.

Nothing in lemonaid schedules it; the first commands after an install start one until a
pass completes.
"""

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import sqlite3
import subprocess
import sys
import time
import typing as ty
from collections import abc
from pathlib import Path

from ..brief import attached, identity, status
from ..config import load_config
from ..inbox import db
from ..log import LOG_PATH, get_logger
from ..messages import recipient
from . import codex_waiter, push_scout, registry, restart, wait_state, waiter_lock

_log = get_logger("watch.reconcile")


def _lock_path() -> Path:
    return registry.root() / "reconcile.lock"


_RETRY_SECONDS = 60.0
_ATTEMPTS = 5  # per installed version


class _Progress(ty.NamedTuple):
    version: str = ""
    complete: bool = False
    attempts: int = 0
    at: float = 0.0


def _progress_path() -> Path:
    return registry.root() / "reconciled" / hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]


def _progress() -> _Progress:
    try:
        return _Progress(**json.loads(_progress_path().read_text()))
    except (OSError, ValueError, TypeError):
        return _Progress()


def _record(progress: _Progress) -> None:
    _progress_path().parent.mkdir(parents=True, exist_ok=True)
    _progress_path().write_text(json.dumps(progress._asdict()))


def _claude_lemons_without_scout(
    conn: sqlite3.Connection,
) -> abc.Iterator[tuple[str, str, bool | None]]:
    """(session, Lemon-ID, alive) for each idle one whose harness is not known to be gone."""
    for entry in attached.everything(conn):
        row = entry.notification
        if (
            not entry.channel.startswith("claude:")
            or row is None
            or row.is_archived
            or row.turn_at is not None
        ):
            continue

        try:
            text = entry.path.read_text()
            lemon_id = identity.read(text)
        except (OSError, ValueError):
            continue
        if status.split(text).status == "done" or wait_state.is_armed(lemon_id):
            continue

        alive = recipient.harness_alive(row)
        if alive is not False:
            yield entry.channel.removeprefix("claude:"), lemon_id, alive


def run() -> list[str]:
    """One pass; what it did, one line per action. Empty when another pass is running."""
    _lock_path().parent.mkdir(parents=True, exist_ok=True)
    with open(_lock_path(), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return []

        current = restart.version()
        done = [
            f"asked {', '.join(w.targets)}'s watcher (pid {w.pid}) to restart"
            for w in restart.send(w for w in registry.running() if restart.outdated(w, current))
        ]
        with db.connect() as conn:
            codex = codex_waiter.restore(conn)
            done += [f"started a scout for {lemon_id}" for lemon_id in codex.started]
            unsettled = codex.unsettled
            for session, lemon_id, alive in list(_claude_lemons_without_scout(conn)):
                if alive is None:
                    unsettled = True
                elif why := push_scout.problem(push_scout.session(session)):
                    done.append(f"no scout for {lemon_id}: {why}")
                elif push_scout.ensure(session, lemon_id):
                    done.append(f"started a scout for {lemon_id}")
                else:
                    unsettled = True
                    done.append(f"could not start a scout for {lemon_id}")
        if unsettled:
            done.append("some lemons were not settled; a later pass will try again")
        last = _progress()
        _record(
            _Progress(
                current, not unsettled, last.attempts if last.version == current else 0, last.at
            )
        )
    for line in done:
        _log.info("%s", line)
    return done


def _editable() -> bool:
    """A dev checkout's install, whose commands must not start scouts for every lemon."""
    try:
        found = importlib.metadata.distribution("lemonaid-inbox").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        return True

    return bool(found and json.loads(found).get("dir_info", {}).get("editable"))


def after_install() -> None:
    """Start a background pass until one settles every lemon for the installed version.

    Retries are spaced `_RETRY_SECONDS` apart and stop after `_ATTEMPTS`, so a lemon that
    can't be settled doesn't turn every command into a pass.
    """
    current = restart.version()
    last = _progress()
    if not current or (
        last.version == current
        and (last.complete or last.attempts >= _ATTEMPTS or time.time() - last.at < _RETRY_SECONDS)
    ):
        return

    if waiter_lock.held(_lock_path()) or _editable() or not load_config().watch.reconcile:
        return

    _record(
        _Progress(
            current, False, (last.attempts if last.version == current else 0) + 1, time.time()
        )
    )
    try:
        with LOG_PATH.open("a") as log:
            subprocess.Popen(
                [sys.executable, "-m", "lemonaid", "watch", "reconcile"],
                env={k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
    except OSError as error:
        _log.warning("could not start a reconcile pass: %s", error)


def _cmd(a: argparse.Namespace) -> None:
    if not load_config().watch.reconcile:
        print("reconcile is off ([watch] reconcile = false)")
        return

    print("\n".join(run()) or "nothing to do")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "reconcile",
        help="Start, replace or restart push scouts so every live lemon that needs one has one",
    )
    parser.set_defaults(func=_cmd)
