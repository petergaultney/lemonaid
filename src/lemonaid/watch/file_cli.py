"""`lemonaid watch file`: a blocking waiter on files and directories.

Reports when a watched file is created, changed, or removed, or when a regular file directly
in a watched directory is added, removed, or rewritten, once the change has been quiet for
`--quiet` seconds. Hidden files and subdirectories are ignored.

By default prints one line per event and never exits on its own. With `--once`, it prints
the first event and exits, so a Claude background Bash task wakes its session once on
completion. With `--codex-thread`, it queues the first event into that Codex thread and
exits. The woken turn handles the event and starts a fresh waiter, which reports anything
that changed in between.

One waiter per (paths, --me) may run; a second exits at once, naming the first.

    lemonaid watch file --wait <path> [--wait <path> ...] --me <name> --once
    lemonaid watch file --wait <dir> --me <name> --codex-thread "$CODEX_THREAD_ID"
    lemonaid watch file --status <path> --me <name>
"""

import argparse
import pathlib
import sys
import time

from . import delivery, file_events, waiter_lock


def _wait(w: file_events.FileWatch, deliver: delivery.Deliver, once: bool, interval: float) -> None:
    while True:
        if file_events.poll(w, deliver) and once:
            return

        time.sleep(interval)


def run(a: argparse.Namespace) -> int:
    paths = a.wait or a.status
    a.state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = file_events.state_stem(a.state_dir, paths, a.me).with_suffix(".lock")
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
            f"not started: a waiter for {', '.join(map(str, paths))} as {a.me or '(no --me)'} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(
            a.codex_thread, "lemonaid watch file", "Handle it, then rearm the waiter."
        )
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    try:
        _wait(
            file_events.open_watch(a.state_dir, paths, a.me, a.quiet),
            deliver,
            a.once or bool(a.codex_thread),
            a.interval,
        )
    except KeyboardInterrupt:
        pass
    except delivery.Failed as e:
        print(f"{e}; the change was not recorded and will be reported to the next waiter")
        return 1
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "file",
        help="Wait for files or directories to change",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--wait",
        type=pathlib.Path,
        action="append",
        metavar="PATH",
        help="file or directory to watch (repeatable)",
    )
    mode.add_argument(
        "--status",
        type=pathlib.Path,
        action="append",
        metavar="PATH",
        help="report whether a waiter for these paths is running (repeatable)",
    )
    ap.add_argument("--me", default="", help="your lemon name, so two lemons' waiters stay apart")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between reads")
    ap.add_argument(
        "--quiet",
        type=float,
        default=2.0,
        help="seconds of no further change before a change is reported",
    )
    ap.add_argument("--once", action="store_true", help="print the first event and exit")
    ap.add_argument(
        "--codex-thread",
        default="",
        metavar="THREAD_ID",
        help="queue one event into this Codex thread and exit instead of printing events forever",
    )
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=file_events.default_state_dir(),
        help="where reported state and waiter locks live (default: $TMPDIR/lemonaid-watch-file)",
    )
    ap.set_defaults(func=_cmd)
