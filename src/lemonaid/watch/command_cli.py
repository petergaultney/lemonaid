"""`lemonaid watch command`: a blocking waiter on a process, reporting once when it exits.

A process started with `lemonaid run` is reported with its command and exit status; any other
process is reported as exited, with its status unknown. A pid reused by a later process counts
as the watched one having exited. Once the exit is delivered, this watch's line leaves the
lemon's `## Watching`, since the process can't exit twice.

With `--once`, it prints the exit and exits, so a Claude background Bash task wakes its
session. With `--codex-thread`, it queues the exit into that Codex thread and exits.

    lemonaid watch command --wait <pid> --once
    lemonaid watch command --wait <pid> --codex-thread
    lemonaid watch command --status <pid>
"""

import argparse
import pathlib
import shlex
import sys
import time

from ..brief import lemon, verbs_cli, waiters
from ..inbox import db
from ..log import get_logger
from . import brief_record, command_events, cursors, delivery, registry, waiter_lock

_log = get_logger("watch.command_cli")


def _watches(command: str, pid: int) -> bool:
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if words[:3] != ["lemonaid", "watch", "command"]:
        return False

    return any(
        word == f"--wait={pid}" or (word == "--wait" and words[i + 1 : i + 2] == [str(pid)])
        for i, word in enumerate(words)
    )


def forget(lemon_id: str, pid: int) -> None:
    """Remove the `watch command` line for *pid* from *lemon_id*'s brief, if it has one."""
    with db.connect() as conn:
        path = lemon.brief_of(conn, lemon_id) if lemon_id else None
    if path is None or not path.is_file():
        return

    if not any(_watches(c, pid) for c in waiters.commands(path.read_text())):
        return

    if error := verbs_cli.edit(
        path,
        lambda text: waiters.remove_where(text, lambda command: _watches(command, pid)),
        preserve_existing=True,
    ):
        _log.warning("could not remove the watch on pid %s from %s: %s", pid, path, error)


def run(a: argparse.Namespace) -> int:
    a.codex_thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2

    pid = a.wait or a.status
    state_dir = a.state_dir or cursors.directory("command", a.me, a.codex_thread)
    state_dir.mkdir(parents=True, exist_ok=True)
    cursor_key = a.me if a.state_dir else ""
    lock_path = command_events.state_stem(state_dir, pid, cursor_key).with_suffix(".lock")
    if a.status:
        running = waiter_lock.held(lock_path)
        print(
            f"waiter running: {waiter_lock.lock_holder(lock_path)}"
            if running
            else "no waiter running"
        )
        return 0 if running else 1

    lock = waiter_lock.acquire(lock_path)
    if lock is None:
        print(
            f"not started: a waiter for pid {pid} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(a.codex_thread, "lemonaid watch command", "Handle it.")
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    if error := brief_record.record(a, "command", a.codex_thread):
        print(f"not started: could not record waiter: {error}")
        lock.close()
        return 2

    once = a.once or bool(a.codex_thread)
    try:
        with registry.watching(a, "command", [str(pid)], a.codex_thread):
            w = command_events.open_watch(state_dir, pid, cursor_key)
            while True:
                if command_events.poll(w, deliver):
                    forget(cursors.owner(a.me, a.codex_thread), pid)
                    if once:
                        break
                if w.reported and once:
                    print(f"pid {pid}'s exit was already reported")
                    break

                time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    except delivery.Failed as e:
        print(f"{e}; the exit was not recorded and will be reported to the next waiter")
        return 1
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "command",
        help="Wait for a process to exit",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", type=int, metavar="PID", help="the process to wait for")
    mode.add_argument(
        "--status", type=int, metavar="PID", help="report whether a waiter for PID is running"
    )
    ap.add_argument("--me", default="", help="your lemon name, so two lemons' waiters stay apart")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between checks")
    ap.add_argument("--once", action="store_true", help="print the exit and exit")
    delivery.add_codex_thread_argument(ap)
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=None,
        help="where the cursor and waiter lock live (default: this lemon's cursor directory)",
    )
    ap.set_defaults(func=_cmd)
