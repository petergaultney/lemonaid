"""One one-shot waiter for a lemon's brief subscriptions and inbox."""

import argparse
import contextlib
import functools
import os
import sys
from collections import abc
from pathlib import Path

from ..brief import attached, identity, lemon
from ..claude import session_socket
from ..codex import channels
from ..hooks import session_gate
from ..inbox import db
from ..messages import store, waiter
from . import (
    batch_wait,
    codex_scout,
    cursors,
    deaf_waiter,
    delivery,
    notes,
    own_edits,
    pr_poller,
    push_scout,
    registry,
    restart,
    wait_state,
    wait_status,
    waiter_lock,
)


def _attached(path: Path, channel: str, harness_alive: abc.Callable[[], bool]) -> bool:
    """An archived inbox row ends the watch unless the lemon's harness is known to run.

    The inbox archives a row when the lemon's process exits, and a resumed lemon's row
    stays archived until its first turn ends.
    """
    with db.connect() as conn:
        session = db.get_by_channel(conn, channel, unread_only=False)
        return attached.by_channel(conn, [channel]).get(channel) == path and (
            session is None or not session.is_archived or harness_alive()
        )


def run(args: argparse.Namespace) -> int:
    thread, problem = delivery.codex_thread(args.codex_thread)
    if args.push and not thread:  # `watch --self --push` run by a Codex lemon itself
        thread = os.environ.get("CODEX_THREAD_ID", "")
    if problem:
        print(f"not started: {problem}")
        return 2
    try:
        with db.connect() as conn:
            channel = (
                channels.for_session(conn, thread)
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
        return wait_status.report(lemon_id, channel, thread, path)
    if thread and not args.push and push_scout.running(lemon_id) and not wait_state.deaf(lemon_id):
        print("push scout running; nothing to rearm")
        return 0
    if args.push and not args.foreground:
        return (
            codex_scout.start(channel, thread, lemon_id)
            if thread
            else push_scout.start(channel.removeprefix("claude:"), lemon_id)
        )

    session = (
        push_scout.session(channel.removeprefix("claude:"), wait=30)
        if args.push and not thread
        else None
    )
    if args.push and not thread and (problem := push_scout.problem(session)):
        print(f"not started: {problem}")
        return 2
    if thread and (problem := delivery.codex_setup_problem()):
        print(f"not started: {problem}")
        return 2
    wait_state.lock_path(lemon_id).parent.mkdir(parents=True, exist_ok=True)
    deaf_waiter.clear(lemon_id, channel)
    lock = waiter_lock.acquire(
        wait_state.lock_path(lemon_id), grace=40 if wait_state.delivering(lemon_id) else 1
    )
    if lock is None:
        print("not started: this lemon already has a unified watcher")
        return 3
    output = (
        push_scout.to_session(session)
        if session
        else codex_scout.to_thread(thread)
        if thread and args.push
        else delivery.to_codex(
            thread,
            "lemonaid watch",
            "Read the changed sources and handle the entire batch, then rearm `lemonaid watch --self --codex-thread`.",
        )
        if thread
        else delivery.to_stdout
    )
    wait_state.clear_delivery(lemon_id)

    def deliver(message: str) -> None:
        if thread and not args.push:
            wait_state.mark_delivering(lemon_id)
        output(message)

    thread_alive = codex_scout.liveness(thread) if thread and args.push else lambda: True

    harness_alive = (
        (lambda: session_socket.alive(session))
        if session
        else thread_alive
        if thread and args.push
        else lambda: False
    )

    def still() -> bool:
        return (
            _attached(path, channel, harness_alive)
            and (session is None or session_socket.alive(session))
            and thread_alive()
        )

    if not still():
        lock.close()
        print(
            f"not watching: {path.name} is not attached to {channel}, or its session has ended",
            file=sys.stderr,
        )
        return 0

    writer = (
        own_edits.claude_writer(session.session_id)
        if session
        else own_edits.writer_from_env(os.environ, thread)
    )
    session_gate.mark(own_edits.root(), writer, path)
    restarting = False
    code = restart.fingerprint()  # before arming: hashing the sources takes a moment
    try:
        with (
            restart.listening(),
            waiter.armed(inbox),
            registry.registered(
                "wait",
                (lemon_id,),
                channel,
                "lemonaid watch --self"
                + (" --codex-thread" if thread else "")
                + (f" {push_scout.FLAG}" if args.push else ""),
                version=restart.version(),
                restartable=True,
                code=code,
            ),
            push_scout.logged(lemon_id, session, lambda: restarting)
            if session
            else contextlib.nullcontext(),
        ):
            if session:
                push_scout.announce(session)
            pr_poller.ensure_running()
            while still() and not restarting:
                restarting = batch_wait.wait(
                    path,
                    inbox,
                    cursors.root() / lemon_id,
                    writer,
                    deliver,
                    still,
                    interval=args.interval,
                    quiet=args.quiet,
                    notes=notes.reader(notes.default_dir(), "codex" if thread else "claude"),
                    restart_requested=restart.requested,
                    beat=functools.partial(wait_state.beat, lemon_id),
                )
                if not args.push:
                    break
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
    if restarting:
        restart.restart()
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
    parser.add_argument(
        push_scout.FLAG,
        dest="push",
        action="store_true",
        help="start a detached scout that pushes each batch into this session (Claude: its "
        "inbox socket; Codex: `codex queue`), unless a watcher already runs",
    )
    parser.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)
    delivery.add_codex_thread_argument(parser)
    parser.set_defaults(func=_cmd)
