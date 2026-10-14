"""One one-shot waiter for a lemon's brief subscriptions and inbox."""

import argparse
import os
import sys
from pathlib import Path

from ..brief import attached, identity, lemon
from ..hooks import session_gate
from ..inbox import db
from ..inbox.channel import full_channel_id
from ..messages import store, waiter
from . import batch_wait, cursors, delivery, own_edits, registry, wait_state, waiter_lock


def _attached(path: Path, channel: str) -> bool:
    with db.connect() as conn:
        session = db.get_by_channel(conn, channel, unread_only=False)
        return attached.by_channel(conn, [channel]).get(channel) == path and (
            session is None or not session.is_archived
        )


def run(args: argparse.Namespace) -> int:
    thread, problem = delivery.codex_thread(args.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2
    try:
        with db.connect() as conn:
            channel = (
                full_channel_id("codex", thread)
                if thread
                else lemon.self_channel(conn, args.channel)
            )
            attached.claim_pending(conn)
            path = attached.by_channel(conn, [channel]).get(channel)
            lemon_id = identity.ensure(conn, path) if path else ""
        if path is None:
            raise ValueError("No brief attached to this lemon")
        inbox = store.inbox_for_id(lemon_id)
    except (ValueError, LookupError, OSError) as error:
        print(f"not started: {error}")
        return 2
    if args.status:
        running = wait_state.is_armed(lemon_id)
        print("watcher running" if running else "no watcher running")
        return 0 if running else 1
    if thread and (problem := delivery.codex_setup_problem()):
        print(f"not started: {problem}")
        return 2
    wait_state.lock_path(lemon_id).parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(
        wait_state.lock_path(lemon_id), grace=40 if wait_state.delivering(lemon_id) else 1
    )
    if lock is None:
        print("not started: this lemon already has a unified watcher")
        return 3
    output = (
        delivery.to_codex(
            thread,
            "lemonaid watch",
            "Read the changed sources and handle the entire batch, then rearm `lemonaid watch --self --codex-thread`.",
        )
        if thread
        else delivery.to_stdout
    )
    wait_state.clear_delivery(lemon_id)

    def deliver(message: str) -> None:
        if thread:
            wait_state.mark_delivering(lemon_id)
        output(message)

    writer = own_edits.writer_from_env(os.environ, thread)
    session_gate.mark(own_edits.root(), writer, path)
    try:
        with (
            waiter.armed(inbox),
            registry.registered(
                "wait",
                (lemon_id,),
                channel,
                "lemonaid watch --self" + (" --codex-thread" if thread else ""),
            ),
        ):
            batch_wait.wait(
                path,
                inbox,
                cursors.root() / lemon_id,
                writer,
                deliver,
                lambda: _attached(path, channel),
                interval=args.interval,
                quiet=args.quiet,
            )
    except waiter.AlreadyArmed as error:
        print(f"not started: {error}")
        return 3
    except (delivery.Failed, ValueError, OSError) as error:
        print(f"{error}; undelivered changes remain for the next watcher")
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        wait_state.clear_delivery(lemon_id)
        lock.close()
    return 0


def _cmd(args: argparse.Namespace) -> None:
    if not args.use_self:
        print("Choose a watch target, or use lemonaid watch --self for your brief")
        sys.exit(2)
    sys.exit(run(args))


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("wait", help="Compatibility alias for watch --self")
    add_arguments(parser, require_self=True)


def add_arguments(parser: argparse.ArgumentParser, *, require_self: bool = False) -> None:
    parser.add_argument("--self", dest="use_self", action="store_true", required=require_self)
    parser.add_argument("--channel", default="", help="Override self detection")
    parser.add_argument(
        "--status", action="store_true", help="Check whether the unified watcher is running"
    )
    parser.add_argument(
        "--interval", type=float, default=0.5, help="Seconds between subscription and inbox reads"
    )
    parser.add_argument(
        "--quiet", type=float, default=2, help="Seconds to gather a batch after the last event"
    )
    delivery.add_codex_thread_argument(parser)
    parser.set_defaults(func=_cmd)
