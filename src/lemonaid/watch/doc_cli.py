"""`lemonaid watch doc`: a blocking waiter on Markdown documents with Relay Comments.

With `--wait DOC`, watches one doc. By default it prints one line per event and never
exits on its own. With `--once`, it prints the first event and exits, so a Claude
background Bash task wakes its session once on completion. With `--codex-thread`, it
queues the first event into that Codex thread and exits. In both one-shot modes the woken
turn handles the event and starts a fresh waiter.

With `--watch-list FILE`, one waiter serves one actor: it watches every doc on that list
(see watch_list.py), re-reading the list on each pass, drops a doc after `--idle-expire`
seconds with no event, and exits when the list is empty. With `--openclaw-session`, each
event runs one OpenClaw agent turn in that session; `lemonaid watch openclaw` manages these.

Events:
- a Relay Comment thread whose last block is not by `--me` (or a `--legacy` name)
  appeared, or an unanswered one gained a block (always on)
- the document body changed outside comment threads, after `--quiet` seconds of no further
  change (unless `--no-edits`; a human types incrementally, and the session's own edits
  also trigger this, except those `own_edits` records - see below). A doc that doesn't
  exist yet has an empty body, so its creation is reported this way.

A waiter started inside Claude Code or Codex knows which session it serves. Body edits that
session made are recorded by Claude Code's edit hooks (`lemonaid claude hooks --own-edits`),
or by `--editing DOC` before and `--mine DOC` after an edit made any other way, and don't
wake its own waiter; edits by anyone else still do. Replies inside comment threads never wake their author.

Threads already reported, and with edits on the body as of the last reported edit, are
remembered per (doc, --me) in `--state-dir`, so a restarted waiter does not re-report a
thread nobody has touched since, and does report body edits made while no waiter ran. One
waiter per (doc, --me), and one per watch list, may run; a second exits at once, naming
the first. State files and locks match the standalone watch-doc.py, so either can replace
the other without losing what has been reported; unlike it, edits are on by default.

    lemonaid watch doc --wait <doc> --me Pliny --legacy Claude [--no-edits] [--once]
    lemonaid watch doc --wait <doc> --me Pliny --legacy Codex --codex-thread "$CODEX_THREAD_ID"
    lemonaid watch doc --watch-list <list.json> --me Pliny --openclaw-session <key> --idle-expire 604800
    lemonaid watch doc --status <doc> --me Pliny
    lemonaid watch doc --editing <doc>; <edit it>; lemonaid watch doc --mine <doc>
"""

import argparse
import os
import pathlib
import sys

from . import delivery, doc_events, doc_wait, own_edits, waiter_lock, watch_list

_OPENCLAW_TURN_TIMEOUT_MS = 600_000


def _record_own(a: argparse.Namespace) -> int:
    writer = own_edits.writer_from_env(os.environ)
    if not writer:
        print("not recorded: run this from the Claude Code or Codex session that watches the doc")
        return 2

    doc = a.editing or a.mine
    if a.editing:
        own_edits.before_edit(a.state_dir, writer, own_edits.cli_key(doc), doc)
        return 0

    if not own_edits.after_edit(a.state_dir, writer, own_edits.cli_key(doc), doc):
        print(f"not recorded: run --editing {doc} before the edit, then --mine after it")
        return 2

    return 0


def run(a: argparse.Namespace) -> int:
    if a.editing or a.mine:
        return _record_own(a)

    if not a.me:
        print("not started: --me is required")
        return 2

    if a.codex_thread and a.openclaw_session:
        print("not started: --codex-thread and --openclaw-session are exclusive")
        return 2

    if a.watch_list and (a.once or a.codex_thread):
        print(
            "not started: --watch-list keeps watching, so it takes neither --once nor --codex-thread"
        )
        return 2

    a.state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = (
        a.watch_list.with_suffix(".waiter")
        if a.watch_list
        else doc_events.state_stem(a.state_dir, a.wait or a.status, a.me).with_suffix(".lock")
    )
    if a.status:
        running = waiter_lock.held(lock_path)
        print(
            f"waiter running: {waiter_lock.lock_holder(lock_path)}"
            if running
            else "no waiter running"
        )
        return 0 if running else 1

    lock = watch_list.hold_waiter(a.watch_list) if a.watch_list else waiter_lock.acquire(lock_path)
    if lock is None:
        print(
            f"not started: a waiter for {a.wait or a.watch_list} as {a.me} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem, deliver, once = (
            delivery.codex_setup_problem(),
            delivery.to_codex(
                a.codex_thread,
                "watch-doc",
                "Use $watch-doc to handle every pending thread, then rearm the waiter.",
            ),
            True,
        )
    elif a.openclaw_session:
        problem = delivery.openclaw_setup_problem(a.openclaw_cli)
        deliver = delivery.to_openclaw(
            a.openclaw_session, a.me, a.hq_session, a.openclaw_cli, _OPENCLAW_TURN_TIMEOUT_MS
        )
        once = a.once
    else:
        problem, deliver, once = "", delivery.to_stdout, a.once
    if problem:
        print(f"not started: {problem}")
        return 2

    try:
        if a.watch_list:
            doc_wait.wait_list(
                a.state_dir,
                a.watch_list,
                lock,
                a.me,
                a.legacy,
                a.edits,
                a.quiet,
                deliver,
                a.idle_expire,
                a.interval,
            )
        else:
            doc_wait.wait_doc(
                doc_events.open_watch(
                    a.state_dir,
                    a.wait,
                    a.me,
                    a.legacy,
                    a.edits,
                    a.quiet,
                    own_edits.writer_from_env(os.environ),
                ),
                deliver,
                once,
                a.interval,
            )
    except KeyboardInterrupt:
        pass
    except delivery.Failed as e:
        print(f"{e}; the event was not recorded and will be reported to the next waiter")
        return 1
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "doc",
        help="Wait for Relay Comments and body edits on vault documents",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", type=pathlib.Path, metavar="DOC", help="document to watch")
    mode.add_argument(
        "--watch-list",
        type=pathlib.Path,
        metavar="FILE",
        help="watch every doc on this actor's list",
    )
    mode.add_argument(
        "--status", type=pathlib.Path, metavar="DOC", help="report whether a waiter is running"
    )
    mode.add_argument(
        "--editing",
        type=pathlib.Path,
        metavar="DOC",
        help="before editing DOC outside Claude's Edit/Write tools: note its body, for --mine",
    )
    mode.add_argument(
        "--mine",
        type=pathlib.Path,
        metavar="DOC",
        help="after that edit: record it as yours, so your waiter does not wake you for it",
    )
    ap.add_argument("--me", default="", help="author name you sign replies with")
    ap.add_argument(
        "--legacy",
        action="append",
        default=[],
        metavar="NAME",
        help="another author name whose blocks count as your replies, e.g. your harness name (repeatable)",
    )
    ap.add_argument(
        "--edits",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="also report body edits outside comment threads (default: on)",
    )
    ap.add_argument("--interval", type=float, default=15.0, help="seconds between reads")
    ap.add_argument(
        "--quiet",
        type=float,
        default=20.0,
        help="seconds of no further change before a body edit is reported",
    )
    ap.add_argument("--once", action="store_true", help="print the first event and exit")
    ap.add_argument(
        "--codex-thread",
        default="",
        metavar="THREAD_ID",
        help="queue one event into this Codex thread and exit instead of printing events forever",
    )
    ap.add_argument(
        "--openclaw-session",
        default="",
        metavar="SESSION_KEY",
        help="run an OpenClaw agent turn in this session for each event",
    )
    ap.add_argument(
        "--hq-session",
        default="agent:main:main",
        help="OpenClaw session that reaches the human directly",
    )
    ap.add_argument("--openclaw-cli", default="openclaw", help="the openclaw executable")
    ap.add_argument(
        "--idle-expire",
        type=float,
        default=0.0,
        help="with --watch-list: drop a doc after this many seconds with no event (0: never)",
    )
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=doc_events.default_state_dir(),
        help="where reported threads and waiter locks live (default: $TMPDIR/watch-doc)",
    )
    ap.set_defaults(func=_cmd)
