"""`lemonaid task inspect`: run one inspector pass now, and list the open cases."""

import argparse

from ...config import load_config
from .. import cli_common
from ..checker import replay, session
from . import passes


def _line(case: dict) -> str:
    sent = "sent" if case["notified_at"] else "not sent"
    return (
        f"{case['subject']}  {case['kind']} {case['obligation']} -> {case['target']}"
        f" ({sent}): {case['reason']}"
    )


def _cmd_inspect(args: argparse.Namespace) -> None:
    config = load_config().tasks
    with passes.sole() as mine:
        if not mine:
            cli_common.emit(args, {"skipped": True}, "another inspector pass is running; skipped")
            return

        with session.Session(
            config.checker or replay.DEFAULT_CHECKER, config.checker_timeout
        ) as checker:
            done = passes.run(config, checker.ask, send=not args.dry_run)
    result = {
        "evaluated": done.judged.evaluated,
        "opened": done.judged.opened,
        "failures": [{"subject": s, "error": e} for s, e in done.judged.failures],
        "sent": done.sent,
        "open": done.open,
    }
    text = "\n".join(
        [
            f"{done.judged.evaluated} tasks evaluated, {len(done.judged.opened)} cases opened,"
            f" {len(done.open)} open, {len(done.judged.failures)} checker failures",
            *(f"  failure {s}: {e}" for s, e in done.judged.failures),
            *(f"  {line}" for line in done.sent),
            *(f"  {_line(c)}" for c in done.open),
        ]
    )
    cli_common.emit(args, result, text)


def add_parser(tasks: argparse._SubParsersAction) -> None:
    inspect = tasks.add_parser(
        "inspect",
        help="Run one inspector pass now: evaluate every open task, challenge the briefs that"
        " owe a move, and list the open cases (the scout host runs passes on its own when"
        " [tasks] inspect_interval is set)",
    )
    inspect.add_argument(
        "--dry-run",
        action="store_true",
        help="Send nothing; list the challenges a pass would send (cases are still recorded)",
    )
    inspect.add_argument("--json", action="store_true", help="Print the pass as JSON")
    inspect.set_defaults(func=_cmd_inspect)
