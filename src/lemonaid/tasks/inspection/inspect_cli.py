"""`lemonaid task inspect`: run inspector passes, and list the open cases."""

import argparse
import contextlib
import fcntl
import time
from collections import abc

from ...config import load_config
from ...inbox import db
from .. import cli_common
from ..checker import replay
from . import cases, challenges, inspector, live


def _line(case: dict) -> str:
    sent = "sent" if case["notified_at"] else "not sent"
    return (
        f"{case['subject']}  {case['kind']} {case['obligation']} -> {case['target']}"
        f" ({sent}): {case['reason']}"
    )


@contextlib.contextmanager
def _sole_pass() -> abc.Iterator[bool]:
    """Whether this process may run a pass: one at a time, so two loops can't both send a
    challenge before either records it as sent."""
    state = live.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "task-inspector.lock", "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        yield True


def _once(args: argparse.Namespace) -> None:
    with _sole_pass() as mine:
        if not mine:
            cli_common.emit(args, {"skipped": True}, "another inspector pass is running; skipped")
            return

        _pass(args)


def _pass(args: argparse.Namespace) -> None:
    config = load_config().tasks
    with db.connect() as conn:
        done = inspector.run(
            conn,
            time.time(),
            config.checker or replay.DEFAULT_CHECKER,
            config.checker_timeout,
            config.policy,
        )
        sent = challenges.deliver(
            conn,
            0 if args.dry_run else config.challenge_interval,
            config.max_challenge_interval,
            config.opt_out.keys(),
            time.time(),
        )
        still = cases.open_cases(conn)
    result = {
        "evaluated": done.evaluated,
        "opened": done.opened,
        "failures": [{"subject": s, "error": e} for s, e in done.failures],
        "sent": sent,
        "open": still,
    }
    text = "\n".join(
        [
            f"{done.evaluated} tasks evaluated, {len(done.opened)} cases opened,"
            f" {len(still)} open, {len(done.failures)} checker failures",
            *(f"  failure {s}: {e}" for s, e in done.failures),
            *(f"  {line}" for line in sent),
            *(f"  {_line(c)}" for c in still),
        ]
    )
    cli_common.emit(args, result, text)


def _cmd_inspect(args: argparse.Namespace) -> None:
    _once(args)
    while args.loop:
        time.sleep(args.loop)
        _once(args)


def add_parser(tasks: argparse._SubParsersAction) -> None:
    inspect = tasks.add_parser(
        "inspect",
        help="Evaluate every open task, challenge the briefs that owe a move, and"
        " list the open cases",
    )
    inspect.add_argument(
        "--loop",
        type=float,
        default=0,
        metavar="SECONDS",
        help="Run a pass every SECONDS until interrupted (300 is the trial policy)",
    )
    inspect.add_argument(
        "--dry-run",
        action="store_true",
        help="Send nothing; list the challenges a pass would send (cases are still recorded)",
    )
    inspect.add_argument("--json", action="store_true", help="Print each pass as JSON")
    inspect.set_defaults(func=_cmd_inspect)
